#
# Copyright 2025 Cloud Software Group, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# PCP-23553 — the o11y contract for a CLI-mode deploy, asserted as an OUTCOME:
#
#   Global            -> CREATE the one observability resource set
#   k8s-auto-dp1      -> SWITCH to that Global resource
#   k8s-auto-bmdp1    -> SWITCH to that Global resource
#
# and its regression guard: no non-Global subject may ever reach
# o11y_config_dataplane_resource(), which would create a second/third DP-local resource
# set. Three previous fixes regressed because a newly added path called it again, so the
# guard is asserted both behaviourally (below) and at source level over the sibling paths
# that get copy-pasted (test_no_non_global_path_creates_a_dataplane_resource).
#
# O11Y_CONFIG_VIA_UI is a code constant that is always True; the retained API branches
# for a data plane must raise NotImplementedError rather than fall back to create-local.

import ast
import importlib
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import page_cli
from utils.env import ENV

BOOTSTRAP_DIR = Path(page_cli.__file__).resolve().parent

DP_NAME = "k8s-auto-dp1"
BMDP_NAME = "k8s-auto-bmdp1"


def _enable_o11y(monkeypatch):
    # class-level attrs (no dataclass annotation) -> patch on the class.
    monkeypatch.setattr(type(ENV), "TP_AUTO_IS_CONFIG_O11Y", True)
    # a license path that doesn't exist so the (unrelated) activation step is skipped.
    monkeypatch.setattr(type(ENV), "TP_AUTO_LICENSE_FILE_PATH", "/nonexistent/license.zip")


def _make_cli():
    cli = MagicMock()
    cli.orchestrator.report_lock = None      # take the no-lock branch
    cli.resource.create_o11y_resources.return_value = "ok"
    return cli


def _patch_bmdp_api(monkeypatch):
    """Neutralize everything _run_api_bmdp_config does besides o11y."""
    for name in ("ConsoleApiClient", "BmdpBw5Api", "BmdpBw6Api", "BmdpEmsApi",
                 "ApiUserPermission", "LicenseApi", "ReportYaml", "Helper"):
        monkeypatch.setattr(page_cli, name, MagicMock())
    for flag in ("TP_AUTO_IS_ENABLE_RVDM", "TP_AUTO_IS_ENABLE_EMSDM", "TP_AUTO_IS_ENABLE_BW6DM"):
        monkeypatch.setattr(type(ENV), flag, False)


# ---------------------------------------------------------------------------
# The contract, per subject: which page-object call each subject ends up making
# ---------------------------------------------------------------------------

def _patch_gui(monkeypatch, wizard_succeeded=True):
    """Run the real _run_gui_o11y body against mocked page objects.

    `wizard_succeeded` drives the report keys (`o11yConfig` for Global, `switchGlobal`
    for a data plane), which are the ONLY reliable success signals: both wizards warn
    instead of raising when they fail, and write their key only on a confirmed success.
    """
    monkeypatch.setattr(page_cli, "Util", MagicMock())
    monkeypatch.setattr(page_cli, "PageObjectAuth", MagicMock())
    report = MagicMock()
    report.get_dataplane_info.return_value = "true" if wizard_succeeded else ""
    monkeypatch.setattr(page_cli, "ReportYaml", report)
    dp_cfg_cls = MagicMock()
    bmdp_cfg_cls = MagicMock()
    monkeypatch.setattr(page_cli, "PageObjectDataPlaneConfiguration", dp_cfg_cls)
    monkeypatch.setattr(page_cli, "PageObjectBMDPConfiguration", bmdp_cfg_cls)
    monkeypatch.setattr(type(ENV), "TP_AUTO_DP_NAME_GLOBAL", "Global")
    return dp_cfg_cls.return_value, bmdp_cfg_cls.return_value


def test_global_creates_the_observability_resource(monkeypatch):
    dp_cfg, bmdp_cfg = _patch_gui(monkeypatch)

    assert page_cli._run_gui_o11y("Global") is True

    dp_cfg.o11y_config_dataplane_resource.assert_called_once_with("Global")
    dp_cfg.o11y_config_switch_to_global.assert_not_called()
    bmdp_cfg.o11y_config_dataplane_resource.assert_not_called()


def test_k8s_dp_switches_to_global(monkeypatch):
    dp_cfg, bmdp_cfg = _patch_gui(monkeypatch)

    assert page_cli._run_gui_o11y(DP_NAME) is True

    dp_cfg.o11y_config_switch_to_global.assert_called_once_with(DP_NAME)
    dp_cfg.o11y_config_dataplane_resource.assert_not_called()
    bmdp_cfg.o11y_config_dataplane_resource.assert_not_called()


def test_bmdp_switches_to_global_using_the_bmdp_page_object(monkeypatch):
    dp_cfg, bmdp_cfg = _patch_gui(monkeypatch)

    assert page_cli._run_gui_o11y(BMDP_NAME, is_bmdp=True) is True

    bmdp_cfg.o11y_config_switch_to_global.assert_called_once_with(BMDP_NAME)
    bmdp_cfg.o11y_config_dataplane_resource.assert_not_called()
    dp_cfg.o11y_config_switch_to_global.assert_not_called()


@pytest.mark.parametrize("dp_name,is_bmdp", [(DP_NAME, False), (BMDP_NAME, True), ("any-other-dp", False)])
def test_no_non_global_subject_creates_a_dataplane_resource(monkeypatch, dp_name, is_bmdp):
    """The regression guard (PCP-23553 AC#2) — every previous fix failed here."""
    dp_cfg, bmdp_cfg = _patch_gui(monkeypatch)

    assert page_cli._run_gui_o11y(dp_name, is_bmdp=is_bmdp) is True

    dp_cfg.o11y_config_dataplane_resource.assert_not_called()
    bmdp_cfg.o11y_config_dataplane_resource.assert_not_called()


# ---------------------------------------------------------------------------
# A switch that did not link must NOT be reported as success
# (the silent-green half of PCP-23553 — the pipeline stayed green while both data
# planes were unlinked, and only a-gcp-doctor Check #5 noticed)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("dp_name,is_bmdp", [
    ("Global", False),          # o11y_config_dataplane_resource -> o11yConfig
    (DP_NAME, False),           # o11y_config_switch_to_global   -> switchGlobal
    (BMDP_NAME, True),
])
def test_unconfirmed_wizard_returns_failure(monkeypatch, dp_name, is_bmdp):
    """Neither wizard raises when it fails — it warns, screenshots and returns — so
    _run_gui_o11y must key on the recorded report key, not on 'it did not raise'."""
    _patch_gui(monkeypatch, wizard_succeeded=False)

    assert page_cli._run_gui_o11y(dp_name, is_bmdp=is_bmdp) is False


def test_dp_entry_point_does_not_record_success_when_switch_fails(monkeypatch):
    _enable_o11y(monkeypatch)
    report = MagicMock()
    report.get_dataplane_info.return_value = ""
    monkeypatch.setattr(page_cli, "ReportYaml", report)
    monkeypatch.setattr(page_cli, "_run_gui_o11y", MagicMock(return_value=False))

    page_cli._run_dp_o11y(_make_cli(), DP_NAME)

    for call in report.set_dataplane_info.call_args_list:
        assert call.args[:2] != (DP_NAME, "o11yResources")


# ---------------------------------------------------------------------------
# ... but a failed switch must NOT take the activation upload down with it
# (PCP-23558 — the o11y `except` used to `return`, so the DP never got its license
# file and every Flogo app CrashLooped on TIBCO_FLOGO_CCS, pipeline still SUCCESS)
# ---------------------------------------------------------------------------

def _patch_dp_activation(monkeypatch, tmp_path, dp_id="dp-abc123"):
    """A real license file on disk + a CLI whose DP id / CP url / token all resolve."""
    license_file = tmp_path / "license-file.bin"
    license_file.write_bytes(b"license")
    monkeypatch.setattr(type(ENV), "TP_AUTO_IS_CONFIG_O11Y", True)
    monkeypatch.setattr(type(ENV), "TP_AUTO_LICENSE_FILE_PATH", str(license_file))

    license_api = MagicMock()
    license_api.return_value.upload_license_file.return_value = True
    monkeypatch.setattr(page_cli, "LicenseApi", license_api)

    cli = _make_cli()
    cli.dataplane.get_dataplane_id.return_value = dp_id
    cli.base.CUSTOM_ENV = {"TIBCOP_CLI_CPURL": "https://cp.example.com",
                           "TIBCOP_CLI_OAUTH_TOKEN": "tok"}
    return cli, license_api, str(license_file)


@pytest.mark.parametrize("switch_succeeded", [True, False])
def test_dp_activation_file_is_uploaded_whatever_the_o11y_outcome(monkeypatch, tmp_path, switch_succeeded):
    """The activation upload is a separate concern from the o11y switch.

    Before PCP-23558 the upload sat AFTER the o11y `except: ... return`, so a single
    failed switch skipped it entirely — silently, since the exit code ignores both.
    """
    report = MagicMock()
    report.get_dataplane_info.return_value = ""          # nothing configured yet
    monkeypatch.setattr(page_cli, "ReportYaml", report)
    monkeypatch.setattr(page_cli, "_run_gui_o11y", MagicMock(return_value=switch_succeeded))
    cli, license_api, license_path = _patch_dp_activation(monkeypatch, tmp_path)

    page_cli._run_dp_o11y(cli, DP_NAME)

    license_api.return_value.upload_license_file.assert_called_once_with(license_path, "dp-abc123")
    report.set_dataplane_info.assert_any_call(DP_NAME, "activation", "uploaded")


def test_failed_switch_still_uploads_but_does_not_claim_o11y_success(monkeypatch, tmp_path):
    """Decoupling the upload must not re-introduce the lying report of PCP-23553."""
    report = MagicMock()
    report.get_dataplane_info.return_value = ""
    monkeypatch.setattr(page_cli, "ReportYaml", report)
    monkeypatch.setattr(page_cli, "_run_gui_o11y", MagicMock(return_value=False))
    cli, license_api, _ = _patch_dp_activation(monkeypatch, tmp_path)

    page_cli._run_dp_o11y(cli, DP_NAME)

    license_api.return_value.upload_license_file.assert_called_once()
    for call in report.set_dataplane_info.call_args_list:
        assert call.args[:2] != (DP_NAME, "o11yResources")


def test_systemexit_from_the_o11y_step_does_not_skip_the_upload(monkeypatch, tmp_path):
    """The same defect through a second door (raised in cross-review).

    Util.exit_error() deep in a shared navigation helper calls sys.exit(1), and SystemExit
    is a BaseException that a plain `except Exception` does not catch — it would leave
    _run_dp_o11y before the activation upload, i.e. exactly PCP-23558 again. Reachable
    both from the o11y step's own navigation and from the new re-check re-navigation.
    """
    report = MagicMock()
    report.get_dataplane_info.return_value = ""
    monkeypatch.setattr(page_cli, "ReportYaml", report)
    monkeypatch.setattr(page_cli, "_run_gui_o11y", MagicMock(side_effect=SystemExit(1)))
    cli, license_api, license_path = _patch_dp_activation(monkeypatch, tmp_path)

    page_cli._run_dp_o11y(cli, DP_NAME)          # must not propagate SystemExit

    license_api.return_value.upload_license_file.assert_called_once_with(license_path, "dp-abc123")
    for call in report.set_dataplane_info.call_args_list:
        assert call.args[:2] != (DP_NAME, "o11yResources")


def test_keyboardinterrupt_still_aborts_the_dp_thread(monkeypatch, tmp_path):
    """Catching SystemExit must not widen into BaseException — Ctrl-C still aborts."""
    report = MagicMock()
    report.get_dataplane_info.return_value = ""
    monkeypatch.setattr(page_cli, "ReportYaml", report)
    monkeypatch.setattr(page_cli, "_run_gui_o11y", MagicMock(side_effect=KeyboardInterrupt))
    cli, license_api, _ = _patch_dp_activation(monkeypatch, tmp_path)

    with pytest.raises(KeyboardInterrupt):
        page_cli._run_dp_o11y(cli, DP_NAME)

    license_api.return_value.upload_license_file.assert_not_called()


@pytest.mark.parametrize("switch_outcome", [False, SystemExit(1), RuntimeError("boom")])
def test_bmdp_activation_file_is_uploaded_whatever_the_o11y_outcome(monkeypatch, tmp_path, switch_outcome):
    """The BMDP had the SAME defect one function over (found in cross-review).

    In _run_api_bmdp_config the license upload sat INSIDE the o11y try, after the
    `raise RuntimeError("o11y UI config returned False")` — so a failed BMDP switch
    skipped the BMDP's activation file exactly the way it skipped the k8s DP's. Fixing
    only _run_dp_o11y would have left half of PCP-23558 in place.
    """
    license_file = tmp_path / "license-file.bin"
    license_file.write_bytes(b"license")
    monkeypatch.setattr(type(ENV), "TP_AUTO_IS_CONFIG_O11Y", True)
    monkeypatch.setattr(type(ENV), "TP_AUTO_LICENSE_FILE_PATH", str(license_file))
    _patch_bmdp_api(monkeypatch)
    report = page_cli.ReportYaml

    license_api = MagicMock()
    license_api.return_value.upload_license_file.return_value = True
    monkeypatch.setattr(page_cli, "LicenseApi", license_api)
    if isinstance(switch_outcome, BaseException):
        monkeypatch.setattr(page_cli, "_run_gui_o11y", MagicMock(side_effect=switch_outcome))
    else:
        monkeypatch.setattr(page_cli, "_run_gui_o11y", MagicMock(return_value=switch_outcome))

    page_cli._run_api_bmdp_config(BMDP_NAME, threading.Lock())

    license_api.return_value.upload_license_file.assert_called_once()
    assert license_api.return_value.upload_license_file.call_args.args[0] == str(license_file)
    report.set_dataplane_info.assert_any_call(BMDP_NAME, "activation", "uploaded")
    # ... and still no lying o11y report
    for call in report.set_dataplane_info.call_args_list:
        assert call.args[:2] != (BMDP_NAME, "o11yResources")


def test_bmdp_entry_point_does_not_record_success_when_switch_fails(monkeypatch):
    _enable_o11y(monkeypatch)
    _patch_bmdp_api(monkeypatch)
    report = page_cli.ReportYaml
    monkeypatch.setattr(page_cli, "_run_gui_o11y", MagicMock(return_value=False))

    page_cli._run_api_bmdp_config(BMDP_NAME, threading.Lock())

    for call in report.set_dataplane_info.call_args_list:
        assert call.args[:2] != (BMDP_NAME, "o11yResources")


def test_global_o11y_failure_aborts_the_bootstrap(monkeypatch):
    """Every data plane switches TO the Global resource, so continuing without it
    guarantees the exact failure this ticket fixes."""
    _enable_o11y(monkeypatch)
    monkeypatch.setenv("TIBCOP_CLI_OAUTH_TOKEN", "tok")
    monkeypatch.setenv("TIBCOP_CLI_CPURL", "https://cp.example.com")
    monkeypatch.setattr(page_cli, "_run_gui_o11y", MagicMock(return_value=False))
    monkeypatch.setattr(page_cli, "ConsoleApiClient", MagicMock())
    monkeypatch.setattr(page_cli, "ReportYaml", MagicMock())

    with pytest.raises(RuntimeError, match="Global o11y"):
        page_cli._run_api_steps()


def test_bootstrap_failure_exits_non_zero(monkeypatch):
    """run() used to log the bootstrap failure and `return`, exiting 0 — a green
    pipeline for a deploy that created nothing."""
    monkeypatch.setattr(page_cli, "ENV", MagicMock())
    monkeypatch.setattr(page_cli, "Util", MagicMock())
    monkeypatch.setattr(page_cli, "_run_api_steps", MagicMock(side_effect=RuntimeError("boom")))
    cli_factory = MagicMock()
    monkeypatch.setattr(page_cli, "TibcopCLI", cli_factory)

    with pytest.raises(SystemExit) as exc:
        page_cli.run()

    assert exc.value.code == 1
    cli_factory.from_env.assert_not_called()   # must not carry on past the failure


# ---------------------------------------------------------------------------
# End-to-end wiring: each CLI entry point reaches the UI path for its subject
# ---------------------------------------------------------------------------

def test_global_entry_point_goes_through_the_ui(monkeypatch):
    _enable_o11y(monkeypatch)
    monkeypatch.setenv("TIBCOP_CLI_OAUTH_TOKEN", "tok")          # Step 1: skip bootstrap
    monkeypatch.setenv("TIBCOP_CLI_CPURL", "https://cp.example.com")

    gui = MagicMock(return_value=True)
    olly = MagicMock()
    monkeypatch.setattr(page_cli, "_run_gui_o11y", gui)
    monkeypatch.setattr(page_cli, "OllyApi", olly)
    monkeypatch.setattr(page_cli, "ConsoleApiClient", MagicMock())
    monkeypatch.setattr(page_cli, "ReportYaml", MagicMock())

    page_cli._run_api_steps()

    gui.assert_called_once_with(ENV.TP_AUTO_DP_NAME_GLOBAL)
    olly.assert_not_called()   # API path must NOT be used


def test_dp_entry_point_goes_through_the_ui(monkeypatch):
    _enable_o11y(monkeypatch)
    report = MagicMock()
    report.get_dataplane_info.return_value = ""    # not already configured
    monkeypatch.setattr(page_cli, "ReportYaml", report)
    gui = MagicMock(return_value=True)
    monkeypatch.setattr(page_cli, "_run_gui_o11y", gui)

    cli = _make_cli()
    page_cli._run_dp_o11y(cli, DP_NAME)

    gui.assert_called_once_with(DP_NAME)
    cli.resource.create_o11y_resources.assert_not_called()   # API path must NOT be used
    # idempotency key still recorded so a re-run short-circuits
    report.set_dataplane_info.assert_any_call(DP_NAME, "o11yResources", True)


def test_bmdp_entry_point_goes_through_the_ui(monkeypatch):
    """Before PCP-23553 the BMDP called OllyApi.create_o11y_resources directly, with no
    O11Y_CONFIG_VIA_UI check at all — a third, BMDP-local resource set."""
    _enable_o11y(monkeypatch)
    _patch_bmdp_api(monkeypatch)
    olly = MagicMock()
    monkeypatch.setattr(page_cli, "OllyApi", olly)
    gui = MagicMock(return_value=True)
    monkeypatch.setattr(page_cli, "_run_gui_o11y", gui)

    page_cli._run_api_bmdp_config(BMDP_NAME, threading.Lock())

    gui.assert_called_once_with(BMDP_NAME, is_bmdp=True)
    olly.assert_not_called()


# ---------------------------------------------------------------------------
# The retained API branches must fail loudly, never fall back to create-local
# ---------------------------------------------------------------------------

def test_o11y_config_via_ui_is_on_by_default():
    """A code constant by design (never a recipe/guiEnv key). Flipping it off without
    implementing switch-to-global on the API side reintroduces PCP-23553."""
    assert page_cli.O11Y_CONFIG_VIA_UI is True


def test_dp_api_branch_raises_instead_of_creating_a_local_resource(monkeypatch):
    _enable_o11y(monkeypatch)
    monkeypatch.setattr(page_cli, "O11Y_CONFIG_VIA_UI", False)
    report = MagicMock()
    report.get_dataplane_info.return_value = ""
    monkeypatch.setattr(page_cli, "ReportYaml", report)
    gui = MagicMock(return_value=True)
    monkeypatch.setattr(page_cli, "_run_gui_o11y", gui)

    cli = _make_cli()
    with pytest.raises(NotImplementedError, match="PCP-23553"):
        page_cli._run_dp_o11y(cli, DP_NAME)

    cli.resource.create_o11y_resources.assert_not_called()
    gui.assert_not_called()


def test_bmdp_api_branch_raises_instead_of_creating_a_local_resource(monkeypatch):
    _enable_o11y(monkeypatch)
    _patch_bmdp_api(monkeypatch)
    monkeypatch.setattr(page_cli, "O11Y_CONFIG_VIA_UI", False)
    olly = MagicMock()
    monkeypatch.setattr(page_cli, "OllyApi", olly)
    gui = MagicMock(return_value=True)
    monkeypatch.setattr(page_cli, "_run_gui_o11y", gui)

    with pytest.raises(NotImplementedError, match="PCP-23553"):
        page_cli._run_api_bmdp_config(BMDP_NAME, threading.Lock())

    olly.assert_not_called()
    gui.assert_not_called()


def test_global_api_branch_stays_functional(monkeypatch):
    """Only the DATA PLANE API branches are blocked — creating the Global resource over
    the API is correct (it is a create, not a link) and must keep working."""
    _enable_o11y(monkeypatch)
    monkeypatch.setenv("TIBCOP_CLI_OAUTH_TOKEN", "tok")
    monkeypatch.setenv("TIBCOP_CLI_CPURL", "https://cp.example.com")
    monkeypatch.setattr(page_cli, "O11Y_CONFIG_VIA_UI", False)

    gui = MagicMock(return_value=True)
    olly_instance = MagicMock()
    monkeypatch.setattr(page_cli, "_run_gui_o11y", gui)
    monkeypatch.setattr(page_cli, "OllyApi", MagicMock(return_value=olly_instance))
    monkeypatch.setattr(page_cli, "ConsoleApiClient", MagicMock())
    monkeypatch.setattr(page_cli, "ReportYaml", MagicMock())

    page_cli._run_api_steps()

    gui.assert_not_called()
    olly_instance.create_o11y_resources.assert_called_once_with("global")


# ---------------------------------------------------------------------------
# WHETHER (TP_AUTO_IS_CONFIG_O11Y) lives with the page object, not with each caller
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("module_name,cls_name", [
    ("page_object.po_dp_config", "PageObjectDataPlaneConfiguration"),
    ("page_object.po_bmdp_config", "PageObjectBMDPConfiguration"),
])
def test_switch_to_global_respects_the_config_o11y_flag(monkeypatch, module_name, cls_name):
    """The call this replaced (`o11y_config_dataplane_resource`) opens with a
    TP_AUTO_IS_CONFIG_O11Y guard. Without the same guard here, driving the `case/`
    scripts with the flag off — a no-op before PCP-23553 — would start performing the
    switch. The guard belongs beside its sibling, not in every caller."""
    module = importlib.import_module(module_name)
    report = MagicMock()
    report.get_dataplane_info.return_value = ""      # not already switched
    monkeypatch.setattr(module, "ReportYaml", report)
    monkeypatch.setattr(type(ENV), "TP_AUTO_IS_CONFIG_O11Y", False)

    po = getattr(module, cls_name)(MagicMock())
    nav = MagicMock()
    monkeypatch.setattr(po, "goto_left_navbar_dataplane", nav)

    po.o11y_config_switch_to_global(DP_NAME)

    nav.assert_not_called()
    report.set_dataplane_info.assert_not_called()


# ---------------------------------------------------------------------------
# Source-level guard for the sibling paths that get copy-pasted into new ones
# ---------------------------------------------------------------------------

# Swept directories are EVERYTHING under the bootstrap tree except these, each with its
# reason. A hardcoded file list was the first cut and was wrong for the same reason the
# per-line regex before it was wrong: it only sees the paths that exist today, so the
# fifth path added next quarter — which IS regression #4 — would be invisible unless
# whoever adds it also remembers to extend the list, and the premise of this guard is
# that they will not.
_SWEEP_EXCLUDED_DIRS = {
    # Test modules drive the wizard directly — that IS their subject — so a non-Global
    # argument here is legitimate (e.g. test_po_o11y_create_global_config_toggle.py).
    "tests",
    ".venv",
    "__pycache__",
}

# Modules whose non-literal argument is legitimate, each with its reason.
_SWEEP_ALLOWLIST = {
    # page_cli._run_gui_o11y passes `dp_name`, but only inside the
    # `if dp_name == ENV.TP_AUTO_DP_NAME_GLOBAL` branch. The behavioural tests above pin
    # that routing directly, which is a stronger check than reading the source.
    "page_cli.py",
}


def _is_global_name(node):
    """True for the literal `ENV.TP_AUTO_DP_NAME_GLOBAL`."""
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "TP_AUTO_DP_NAME_GLOBAL"
        and isinstance(node.value, ast.Name)
        and node.value.id == "ENV"
    )


def _sweep_dataplane_resource_calls():
    """Every `o11y_config_dataplane_resource(...)` call site under the bootstrap tree.

    Parsed, not regexed: a line-based pattern silently matches NOTHING once a call is
    wrapped across lines (by a formatter or a long argument), so the guard meant to
    catch regression #4 would pass vacuously. The AST ignores formatting and comments
    for free.

    Yields `(rel_posix_path, lineno, arg_node_or_None)`.
    """
    for path in sorted(BOOTSTRAP_DIR.rglob("*.py")):
        rel = path.relative_to(BOOTSTRAP_DIR)
        if _SWEEP_EXCLUDED_DIRS.intersection(rel.parts):
            continue
        if rel.as_posix() in _SWEEP_ALLOWLIST:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:                      # not ours to police
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "o11y_config_dataplane_resource":
                yield rel.as_posix(), node.lineno, (node.args[0] if node.args else None)


def test_no_non_global_path_creates_a_dataplane_resource():
    """The regression guard, swept over the WHOLE tree rather than a hardcoded list."""
    calls = list(_sweep_dataplane_resource_calls())

    # Non-vacuity: a sweep that suddenly sees nothing (wrong root, everything excluded,
    # a rename) would otherwise pass while checking exactly zero call sites — the same
    # silent-pass failure this guard exists to prevent.
    assert len(calls) >= 3, (
        f"the sweep found only {len(calls)} call site(s) under {BOOTSTRAP_DIR} — it is "
        "almost certainly not looking where it thinks it is, so it is not guarding "
        "anything. Fix the sweep before trusting a green result."
    )

    offenders = [
        f"{rel}:{lineno} -> o11y_config_dataplane_resource({ast.unparse(arg) if arg else ''})"
        for rel, lineno, arg in calls
        if not _is_global_name(arg)
    ]
    assert not offenders, (
        "these call sites create a DP-LOCAL observability resource set; a data plane "
        "must switch to the Global resource via o11y_config_switch_to_global() "
        "(PCP-23553):\n  " + "\n  ".join(offenders)
    )
