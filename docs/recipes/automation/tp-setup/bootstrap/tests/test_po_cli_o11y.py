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
# CLI mode configures o11y over the Console API and never launches a browser for it.
# PCP-22010 added the O11Y_CONFIG_VIA_UI constant as an explicitly TEMPORARY detour
# through the wizard, "to be removed (with the _run_gui_o11y branch) once the API side
# is fixed"; the API side is fixed (api_object/o11y_console.py links a data plane), so
# both are gone. The wizard itself is untouched — page_dp.py / page_bmdp.py and the
# case/ scripts still drive it; it is only CLI mode that no longer detours through it.

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


def test_dp_entry_point_does_not_record_success_when_switch_fails(monkeypatch):
    _enable_o11y(monkeypatch)
    report = MagicMock()
    report.get_dataplane_info.return_value = ""
    monkeypatch.setattr(page_cli, "ReportYaml", report)
    monkeypatch.setattr(page_cli, "_run_api_o11y", MagicMock(return_value=False))

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
    monkeypatch.setattr(page_cli, "_run_api_o11y", MagicMock(return_value=switch_succeeded))
    cli, license_api, license_path = _patch_dp_activation(monkeypatch, tmp_path)

    page_cli._run_dp_o11y(cli, DP_NAME)

    license_api.return_value.upload_license_file.assert_called_once_with(license_path, "dp-abc123")
    report.set_dataplane_info.assert_any_call(DP_NAME, "activation", "uploaded")


def test_failed_switch_still_uploads_but_does_not_claim_o11y_success(monkeypatch, tmp_path):
    """Decoupling the upload must not re-introduce the lying report of PCP-23553."""
    report = MagicMock()
    report.get_dataplane_info.return_value = ""
    monkeypatch.setattr(page_cli, "ReportYaml", report)
    monkeypatch.setattr(page_cli, "_run_api_o11y", MagicMock(return_value=False))
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
    monkeypatch.setattr(page_cli, "_run_api_o11y", MagicMock(side_effect=SystemExit(1)))
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
    monkeypatch.setattr(page_cli, "_configure_o11y", MagicMock(side_effect=KeyboardInterrupt))
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
        monkeypatch.setattr(page_cli, "_run_api_o11y", MagicMock(side_effect=switch_outcome))
    else:
        monkeypatch.setattr(page_cli, "_run_api_o11y", MagicMock(return_value=switch_outcome))

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
    monkeypatch.setattr(page_cli, "_run_api_o11y", MagicMock(return_value=False))

    page_cli._run_api_bmdp_config(BMDP_NAME, threading.Lock())

    for call in report.set_dataplane_info.call_args_list:
        assert call.args[:2] != (BMDP_NAME, "o11yResources")


def test_global_o11y_failure_aborts_the_bootstrap(monkeypatch):
    """Every data plane switches TO the Global resource, so continuing without it
    guarantees the exact failure this ticket fixes."""
    _enable_o11y(monkeypatch)
    monkeypatch.setenv("TIBCOP_CLI_OAUTH_TOKEN", "tok")
    monkeypatch.setenv("TIBCOP_CLI_CPURL", "https://cp.example.com")
    monkeypatch.setattr(page_cli, "_run_api_o11y", MagicMock(return_value=False))
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
# End-to-end wiring: each CLI entry point reaches the API path for its subject
# ---------------------------------------------------------------------------

def _console(monkeypatch, linked=True):
    """Patch page_cli._o11y_console and return the O11yConsoleApi mock it hands back."""
    console = MagicMock()
    console.link_to_global.return_value = linked
    monkeypatch.setattr(page_cli, "_o11y_console", MagicMock(return_value=console))
    return console


def _report(monkeypatch, confirmed_key=None):
    """ReportYaml mock: nothing recorded yet, except `confirmed_key` which reads back
    'true' so the shared outcome assertion in _configure_o11y is satisfied."""
    report = MagicMock()
    report.get_dataplane_info.side_effect = (
        lambda _dp, key: "true" if key == confirmed_key else "")
    monkeypatch.setattr(page_cli, "ReportYaml", report)
    return report


def test_global_entry_point_goes_through_the_api(monkeypatch):
    _enable_o11y(monkeypatch)
    monkeypatch.setenv("TIBCOP_CLI_OAUTH_TOKEN", "tok")          # Step 1: skip bootstrap
    monkeypatch.setenv("TIBCOP_CLI_CPURL", "https://cp.example.com")
    console = _console(monkeypatch)
    _report(monkeypatch, confirmed_key="o11yConfig")

    page_cli._run_api_steps()

    console.ensure_global_config.assert_called_once_with()


def test_dp_entry_point_goes_through_the_api(monkeypatch):
    _enable_o11y(monkeypatch)
    report = _report(monkeypatch, confirmed_key="switchGlobal")
    console = _console(monkeypatch)
    console.client.resolve_dataplane_id.return_value = "dp-abc123"

    cli = _make_cli()
    page_cli._run_dp_o11y(cli, DP_NAME)

    console.link_to_global.assert_called_once_with("dp-abc123")
    console.ensure_pillars.assert_not_called()    # a DP LINKS, it never creates its own
    cli.resource.create_o11y_resources.assert_not_called()
    report.set_dataplane_info.assert_any_call(DP_NAME, "o11yResources", True)


def test_bmdp_entry_point_goes_through_the_api(monkeypatch):
    """The BMDP takes the identical contract — no Control-Tower special case."""
    _enable_o11y(monkeypatch)
    _patch_bmdp_api(monkeypatch)
    _report(monkeypatch, confirmed_key="switchGlobal")
    console = _console(monkeypatch)
    console.client.resolve_dataplane_id.return_value = "bmdp-xyz"

    page_cli._run_api_bmdp_config(BMDP_NAME, threading.Lock())

    console.link_to_global.assert_called_once_with("bmdp-xyz")
    console.ensure_pillars.assert_not_called()


# ---------------------------------------------------------------------------
# The o11y step is API-only: no browser, and one definition of success
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("subject,is_bmdp,confirmed_key", [
    ("Global", False, "o11yConfig"),
    (DP_NAME, False, "switchGlobal"),
    (BMDP_NAME, True, "switchGlobal"),
])
def test_configuring_o11y_never_launches_a_browser(monkeypatch, subject, is_bmdp, confirmed_key):
    """PCP-22010 routed this step through the wizard as an explicitly temporary detour;
    it is gone, and it must not come back by accident.

    Asserted behaviourally rather than by grepping the module. That was originally
    because page_cli still launched a browser for EMS and so "page_cli opens a browser
    somewhere" stayed true; since PCP-24380 it does not, and the source-level half is
    covered by the browser-free guard in tests/test_capability_ems_provision.py. The
    behavioural assertion is kept anyway: it pins that THIS step takes the API path,
    which a module-wide import check cannot say.
    """
    _enable_o11y(monkeypatch)
    monkeypatch.setattr(type(ENV), "TP_AUTO_DP_NAME_GLOBAL", "Global")
    _report(monkeypatch, confirmed_key=confirmed_key)
    console = _console(monkeypatch)
    console.client.resolve_dataplane_id.return_value = "dp-abc123"
    util = MagicMock()
    monkeypatch.setattr(page_cli, "Util", util)

    assert page_cli._configure_o11y(subject, is_bmdp=is_bmdp) is True

    util.browser_launch.assert_not_called()
    util.browser_close.assert_not_called()


def test_an_unconfirmed_outcome_fails_even_though_the_call_returned_true(monkeypatch):
    """A returning call is not enough — the report key it writes is the outcome.
    Both of PCP-23553's silent-green regressions passed this point."""
    _enable_o11y(monkeypatch)
    _report(monkeypatch, confirmed_key=None)          # nothing ever recorded
    monkeypatch.setattr(page_cli, "_run_api_o11y", MagicMock(return_value=True))
    assert page_cli._configure_o11y(DP_NAME) is False


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
