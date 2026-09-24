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
# PCP-24380 — EMS was the only capability with no CLI path, and provision_capability()
# would have silently mis-provisioned it if one had simply been switched on.
#
# The defect the first test pins is structural, not a typo. provision_capability() was
# shaped:
#
#     if capability == "TIBCOHUB":  ...developer-hub flags...
#     else:                         --path-prefix "<prefix>" --fluentbit-sidecar-enabled
#
# and that `else` is a CATCH-ALL. Adding EMS to the capability enum without adding an arm
# in front of it sends EMS a literal `--path-prefix "None"` (path_prefix is only computed
# for BWCE/BW5CE/FLOGO) plus a fluentbit sidecar it has no use for. Both flags are
# accepted by tibcop, so nothing fails at the boundary; the mistake surfaces as a
# capability that provisions and then behaves oddly.
#
# The second and third tests pin the two places where "EMS is different" is load-bearing
# rather than cosmetic:
#
#   * Storage. There are FOUR storage naming schemes in this codebase. EMS binds the Data
#     Plane's own resource ('<dp>-storage' in CLI mode, the StorageClass name in GUI mode),
#     NOT the per-capability '{cap}-{sc}-storage' the other capabilities auto-create.
#     Getting this the wrong way round is PCP-23953 with the roles reversed.
#   * Idempotency. A Data Plane may legitimately hold SEVERAL EMS servers, so "an EMS
#     exists" is not the same question as "the EMS that was asked for exists".
#
# These drive the real command construction (cli_object.capability) down to the real sink
# (cli_object.base), monkeypatching subprocess.run so nothing executes — the same shape as
# tests/test_run_cli_script_injection.py. Command construction is asserted on the captured
# ARGV, not on the command string, because argv is what the child actually receives.

import ast
import json
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import page_cli
from cli_object.base import TibcopBase
from cli_object.capability import EMS_SIZINGS, TibcopCapability
from utils import naming
from utils.env import ENV

DP = "k8s-auto-dp1"
EMS_NAME = "ems-sn"
STORAGE_CLASS = "nfs"
DP_STORAGE_ID = "storage-res-id-1"

# Captured verbatim from a live CP 1.21 Data Plane (AWS lab ins-chchen-24380-02, DP
# 'k8s-auto-dp1') with:
#   tibcop tplatform:list-capability-instances --dataplane-name="k8s-auto-dp1" --json
# — the command list_capabilities() actually issues (the Python method name says
# "capabilities", the subcommand says "capability-instances"). Recorded because the
# POSITIVE branch of the name match had only ever been exercised against a hand-written
# stand-in. What the real payload settles:
#   * the top level is a BARE ARRAY, not wrapped in a `response` object;
#   * the keys are exactly id / name / capability;
#   * for EMS, `name` is the INSTANCE name ('ems-sn') — which is what makes matching on
#     capability_name correct for EMS;
#   * for FLOGO, `name` is the CAPABILITY name — so `name` is NOT an instance name in
#     general, and the EMS row has to be picked out of a mixed list on `capability` first.
LIVE_CAPABILITY_INSTANCES = [
    {"id": "dam4t3t8o7is73bm5dig", "name": "FLOGO", "capability": "FLOGO"},
    {"id": "dam4u6l8o7is73bm5djg", "name": "ems-sn", "capability": "EMS"},
]


def _capturing_base(monkeypatch, stdout="✔ done"):
    """A TibcopBase whose subprocess.run sink is captured, not executed."""
    calls = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(list(cmd))
        return types.SimpleNamespace(stdout=stdout, stderr="", returncode=0)

    monkeypatch.setattr("cli_object.base.subprocess.run", fake_run)
    return TibcopBase(), calls


def _capability(monkeypatch, provisioned=None, resources=None, create_ok=True):
    """A TibcopCapability wired to stubs for everything except the command it builds.

    `provisioned` is the list-capability-instances payload; `resources` maps resource
    name -> id, and anything absent is "does not exist yet".
    """
    base, calls = _capturing_base(monkeypatch)
    # BOTH modules, because both read the storage class and they are different name
    # bindings: utils.naming builds the candidate list, cli_object.capability builds
    # --ems-*-storage-name and passes the class to create_storage_resource. ENV is a frozen
    # dataclass, so the module reference is what gets swapped; patching only one leaves the
    # other reading the ambient value (which is '' on a box with no cluster), and a test
    # that half-pins its input passes or fails for reasons it is not about.
    env = types.SimpleNamespace(TP_AUTO_STORAGE_CLASS=STORAGE_CLASS,
                                TP_AUTO_EMS_CAPABILITY_SERVER_NAME=EMS_NAME,
                                TP_AUTO_EMS_CAPABILITY_SIZING="small",
                                TP_AUTO_INGRESS_OBJECT="ingress")
    monkeypatch.setattr(naming, "ENV", env)
    monkeypatch.setattr("cli_object.capability.ENV", env)

    dataplane = MagicMock()
    dataplane.get_dataplane_id.return_value = "dp-abc123"

    created = []
    store = dict(resources or {})

    resource = MagicMock()
    resource.get_resource_id_by_name.side_effect = lambda _dp, name: store.get(name)

    def _create_storage(dp_name, resource_name, storage_class_name=None, description=None, **_kw):
        created.append((resource_name, storage_class_name))
        if not create_ok:
            return None
        store[resource_name] = f"{resource_name}-id"
        return "ok"

    resource.create_storage_resource.side_effect = _create_storage

    capability = TibcopCapability(base, dataplane=dataplane, resource=resource)
    # list_capabilities is the idempotency read; stub it rather than the sink so the
    # provision command is the only thing that reaches argv.
    monkeypatch.setattr(capability, "list_capabilities",
                        lambda *_a, **_kw: json.dumps(provisioned or []))
    return capability, calls, created


def _argv_after(calls):
    """The single provision command the run issued."""
    assert len(calls) >= 1, "expected the tibcop sink to be invoked"
    provisions = [c for c in calls if "tplatform:provision-capability" in c]
    assert len(provisions) == 1, f"expected exactly one provision command, got {provisions!r}"
    return provisions[0]


def _flag(argv, name):
    """The value of `--name` in an argv list, or None if the flag is absent."""
    return argv[argv.index(name) + 1] if name in argv else None


# ---------------------------------------------------------------------------
# 1. Command construction — and the catch-all `else` this arm exists to escape
# ---------------------------------------------------------------------------

def test_ems_provision_command_uses_the_ems_flags(monkeypatch):
    capability, calls, _ = _capability(monkeypatch, resources={f"{DP}-storage": DP_STORAGE_ID})

    capability.provision_capability(DP, "EMS", ems_name=EMS_NAME, ems_sizing="small")

    argv = _argv_after(calls)
    assert argv[0] == "tibcop"
    assert argv[1] == "tplatform:provision-capability"
    assert _flag(argv, "--dataplane-name") == DP
    assert _flag(argv, "--capability") == "EMS"
    # The two data resources, which is what EMS binds instead of one storage resource.
    assert _flag(argv, "--msg-data-resource-instance-id") == DP_STORAGE_ID
    assert _flag(argv, "--log-data-resource-instance-id") == DP_STORAGE_ID
    assert _flag(argv, "--ems-name") == EMS_NAME
    assert _flag(argv, "--ems-sizing") == "small"
    assert _flag(argv, "--ems-use") == "dev"


def test_ems_provision_sends_neither_path_prefix_nor_fluentbit(monkeypatch):
    """THE regression this file exists for.

    Without an `elif` before the catch-all `else`, EMS is provisioned with
    `--path-prefix "None"` (path_prefix is only computed for BWCE/BW5CE/FLOGO, so it is
    still the literal default) and `--fluentbit-sidecar-enabled`. tibcop accepts both, so
    nothing fails at the boundary and nothing downstream says so.

    A/B: delete the `elif is_ems:` arm in provision_capability() and this goes red.
    """
    capability, calls, _ = _capability(monkeypatch, resources={f"{DP}-storage": DP_STORAGE_ID})

    capability.provision_capability(DP, "EMS", ems_name=EMS_NAME)

    argv = _argv_after(calls)
    assert "--path-prefix" not in argv, f"EMS has no HTTP path prefix: {argv!r}"
    assert "None" not in argv, f"the catch-all arm leaked a literal 'None': {argv!r}"
    assert "--fluentbit-sidecar-enabled" not in argv, f"EMS has no fluentbit sidecar: {argv!r}"
    # ... and not the single-storage/route flags either: EMS takes the data-resource pair
    # and no route at all, so these would be a wrong binding rather than a no-op.
    assert "--storage-resource-instance-id" not in argv, argv
    assert "--ingress-resource-instance-id" not in argv, argv
    assert "--gateway-resource-instance-id" not in argv, argv


def test_a_caller_supplied_storage_or_route_id_is_dropped_for_ems(monkeypatch):
    """The Web UI does not offer those fields for EMS, but /run-cli-script is a URL and
    the CLI layer is the only thing that can refuse them."""
    capability, calls, _ = _capability(monkeypatch, resources={f"{DP}-storage": DP_STORAGE_ID})

    capability.provision_capability(DP, "EMS", ems_name=EMS_NAME,
                                    storage_resource_id="wrong-1",
                                    ingress_resource_id="wrong-2",
                                    gateway_resource_id="wrong-3")

    argv = _argv_after(calls)
    for leaked in ("wrong-1", "wrong-2", "wrong-3"):
        assert leaked not in argv, f"{leaked} must not reach an EMS provision: {argv!r}"


def test_the_storage_names_come_from_the_storage_class(monkeypatch):
    """--ems-msg-storage-name / --ems-log-storage-name are NOT exposed as parameters.

    They are the Kubernetes StorageClass. A value disagreeing with the resolved resource
    instance is the PCP-23953 failure class, and whether the CP even reads them is
    unverifiable without deliberately sending a wrong one — so they are derived, not asked
    for. Pinned here so "just add two more fields" is a decision someone has to make on
    purpose.
    """
    capability, calls, _ = _capability(monkeypatch, resources={f"{DP}-storage": DP_STORAGE_ID})

    capability.provision_capability(DP, "EMS", ems_name=EMS_NAME)

    argv = _argv_after(calls)
    assert _flag(argv, "--ems-msg-storage-name") == STORAGE_CLASS
    assert _flag(argv, "--ems-log-storage-name") == STORAGE_CLASS


def test_a_blank_storage_class_omits_the_storage_names_rather_than_sending_empty(monkeypatch):
    """ENV.TP_AUTO_STORAGE_CLASS is read off the cluster with awk, so blank is reachable.
    Sending `--ems-msg-storage-name ""` asserts a name; omitting it asserts nothing."""
    capability, calls, _ = _capability(monkeypatch, resources={f"{DP}-storage": DP_STORAGE_ID})
    monkeypatch.setattr("cli_object.capability.ENV",
                        types.SimpleNamespace(TP_AUTO_STORAGE_CLASS="   ",
                                              TP_AUTO_EMS_CAPABILITY_SERVER_NAME=EMS_NAME,
                                              TP_AUTO_EMS_CAPABILITY_SIZING="small",
                                              TP_AUTO_INGRESS_OBJECT="ingress"))

    capability.provision_capability(DP, "EMS", ems_name=EMS_NAME)

    argv = _argv_after(calls)
    assert "--ems-msg-storage-name" not in argv, argv
    assert "--ems-log-storage-name" not in argv, argv


@pytest.mark.parametrize("sizing", EMS_SIZINGS)
def test_every_documented_sizing_is_accepted(monkeypatch, sizing):
    capability, calls, _ = _capability(monkeypatch, resources={f"{DP}-storage": DP_STORAGE_ID})

    capability.provision_capability(DP, "EMS", ems_name=EMS_NAME, ems_sizing=sizing)

    assert _flag(_argv_after(calls), "--ems-sizing") == sizing


def test_a_bad_sizing_fails_before_anything_is_sent(monkeypatch):
    """tibcop takes --ems-sizing as free text and the chart only rejects it during the
    DP-side Helm render — i.e. after the capability has been accepted. Validate here or
    the typo surfaces as a capability that never comes up."""
    capability, calls, _ = _capability(monkeypatch, resources={f"{DP}-storage": DP_STORAGE_ID})

    assert capability.provision_capability(DP, "EMS", ems_name=EMS_NAME, ems_sizing="huge") is None
    assert not calls, "nothing may be sent once the sizing is known to be bad"


# ---------------------------------------------------------------------------
# 2. Storage resolution
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("resource_name", [f"{DP}-storage", STORAGE_CLASS])
def test_both_naming_conventions_resolve(monkeypatch, resource_name):
    """CLI mode calls it '<dp>-storage'; GUI mode names it after the StorageClass. Both
    are real and both must be found, or the CLI arm repeats PCP-23953 with the roles
    reversed."""
    capability, calls, created = _capability(monkeypatch, resources={resource_name: "found-id"})

    capability.provision_capability(DP, "EMS", ems_name=EMS_NAME)

    assert created == [], "an existing resource must be reused, not duplicated"
    assert _flag(_argv_after(calls), "--msg-data-resource-instance-id") == "found-id"


def test_the_dataplane_named_resource_wins_when_both_exist(monkeypatch):
    capability, calls, _ = _capability(
        monkeypatch, resources={STORAGE_CLASS: "gui-id", f"{DP}-storage": "cli-id"})

    capability.provision_capability(DP, "EMS", ems_name=EMS_NAME)

    assert _flag(_argv_after(calls), "--msg-data-resource-instance-id") == "cli-id"


def test_a_missing_resource_is_created_under_the_cli_convention(monkeypatch):
    capability, calls, created = _capability(monkeypatch, resources={})

    capability.provision_capability(DP, "EMS", ems_name=EMS_NAME)

    assert created == [(f"{DP}-storage", STORAGE_CLASS)], (
        "the created resource must use the same name cli_object/orchestrator.py uses, or "
        "the next run creates a second one")
    assert _flag(_argv_after(calls), "--msg-data-resource-instance-id") == f"{DP}-storage-id"


def test_a_create_failure_returns_none_before_any_provision_command(monkeypatch):
    """Provisioning EMS against a storage resource that does not exist fails on the CP
    side with a far less obvious message than the one already logged here."""
    capability, calls, created = _capability(monkeypatch, resources={}, create_ok=False)

    assert capability.provision_capability(DP, "EMS", ems_name=EMS_NAME) is None
    assert created, "the create was attempted"
    assert not [c for c in calls if "tplatform:provision-capability" in c], (
        "no provision command may be issued once the storage resource could not be created")


def test_message_and_log_bind_the_same_resource_by_default(monkeypatch):
    """What the UI wizard does when the Data Plane offers one storage resource — which is
    the normal case, not a degenerate one."""
    capability, calls, _ = _capability(monkeypatch, resources={f"{DP}-storage": DP_STORAGE_ID})

    capability.provision_capability(DP, "EMS", ems_name=EMS_NAME)

    argv = _argv_after(calls)
    assert (_flag(argv, "--msg-data-resource-instance-id")
            == _flag(argv, "--log-data-resource-instance-id") == DP_STORAGE_ID)


def test_explicit_ids_skip_resolution_entirely(monkeypatch):
    capability, calls, created = _capability(monkeypatch, resources={})

    capability.provision_capability(DP, "EMS", ems_name=EMS_NAME,
                                    msg_data_resource_id="msg-1", log_data_resource_id="log-1")

    assert created == [], "nothing should be created when both ids are supplied"
    argv = _argv_after(calls)
    assert _flag(argv, "--msg-data-resource-instance-id") == "msg-1"
    assert _flag(argv, "--log-data-resource-instance-id") == "log-1"


# ---------------------------------------------------------------------------
# 3. Idempotency — a DP may hold several EMS servers
# ---------------------------------------------------------------------------

def test_the_same_ems_server_is_not_provisioned_twice(monkeypatch):
    """Driven by the captured live payload, so the positive branch is pinned to what a
    real CP returns — including the FLOGO row, whose `name` is a capability name rather
    than an instance name. The EMS row must be selected out of that mixture."""
    assert EMS_NAME in [row["name"] for row in LIVE_CAPABILITY_INSTANCES]
    capability, calls, _ = _capability(
        monkeypatch, provisioned=LIVE_CAPABILITY_INSTANCES,
        resources={f"{DP}-storage": DP_STORAGE_ID})

    result = capability.provision_capability(DP, "EMS", ems_name=EMS_NAME)

    assert result == "ALREADY_PROVISIONED"
    assert not calls, "an already-provisioned server must not be re-sent"


def test_a_differently_named_ems_does_not_cause_a_skip(monkeypatch):
    """The reason is_capability_provisioned grew a capability_name: matching on the
    capability TYPE alone means the first EMS server on a Data Plane permanently blocks
    provisioning any other one, and the run reports success for a server that is not
    there."""
    capability, calls, _ = _capability(
        monkeypatch, provisioned=[{"id": "1", "name": "some-other-ems", "capability": "EMS"}],
        resources={f"{DP}-storage": DP_STORAGE_ID})

    result = capability.provision_capability(DP, "EMS", ems_name=EMS_NAME)

    assert result != "ALREADY_PROVISIONED"
    assert _flag(_argv_after(calls), "--ems-name") == EMS_NAME


def test_the_other_capabilities_still_match_on_type_alone(monkeypatch):
    """The four existing callers pass no name and must be behaviourally unchanged: a BWCE
    instance is named 'BW6(Containers)' by the CP, which no caller knows or should."""
    capability, _calls, _ = _capability(
        monkeypatch, provisioned=[{"id": "1", "name": "BW6(Containers)", "capability": "BWCE"}])

    assert capability.is_capability_provisioned(DP, "BWCE") is True
    assert capability.is_capability_provisioned(DP, "BWCE", capability_name="BW6(Containers)") is True
    assert capability.is_capability_provisioned(DP, "BWCE", capability_name="something-else") is False


# ---------------------------------------------------------------------------
# 4. Orchestrator wiring — EMS reaches the CLI, and reaches it exactly once
# ---------------------------------------------------------------------------

def test_the_dp_setup_callback_provisions_ems_through_the_cli(monkeypatch):
    cli = MagicMock()
    cli.capability.provision_capability.return_value = "ok"
    monkeypatch.setattr(page_cli, "ReportYaml", MagicMock())
    monkeypatch.setattr(type(ENV), "TP_AUTO_EMS_CAPABILITY_SERVER_NAME", EMS_NAME)
    monkeypatch.setattr(type(ENV), "TP_AUTO_EMS_CAPABILITY_SIZING", "small")

    page_cli._run_cli_ems_provision(cli, DP)

    cli.capability.provision_capability.assert_called_once()
    args, kwargs = cli.capability.provision_capability.call_args
    assert args == (DP, "EMS")
    assert kwargs["ems_name"] == EMS_NAME
    assert kwargs["ems_sizing"] == "small"


def test_a_failed_provision_raises_rather_than_reporting_a_green_run(monkeypatch):
    """provision_capability returns None on failure and never raises, so the RETURN VALUE
    is the outcome — the silent-green trap of PCP-23553. _run_dp_setup only records a
    failure it can catch."""
    cli = MagicMock()
    cli.capability.provision_capability.return_value = None
    report = MagicMock()
    monkeypatch.setattr(page_cli, "ReportYaml", report)

    with pytest.raises(RuntimeError, match="EMS provisioning failed"):
        page_cli._run_cli_ems_provision(cli, DP)

    report.set_capability.assert_not_called()


def test_the_orchestrator_still_runs_ems_last_and_serially(monkeypatch):
    """EMS is deliberately NOT in cap_tasks: that list's provision -> build+deploy ->
    wait+test shape does not fit a capability with no app. Pinned at source level because
    the cost of the choice (~3 min unoverlapped) makes "just add it to cap_tasks" a
    tempting edit."""
    import inspect

    from cli_object.orchestrator import TibcopOrchestrator

    src = inspect.getsource(TibcopOrchestrator._provision_and_deploy)
    assert "on_ems_needed(dp_name)" in src
    assert src.rstrip().endswith("on_ems_needed(dp_name)"), (
        "EMS must stay the LAST statement of _provision_and_deploy — anything after it "
        "would be skipped when EMS raises, which is how it reports failure")


# ---------------------------------------------------------------------------
# 5. Browser-free guard (§4.5) — page_cli imports no page object
# ---------------------------------------------------------------------------

def test_cli_mode_imports_no_page_object():
    """EMS was the last browser step in CLI mode. Asserted at SOURCE level, by AST, for
    two reasons a behavioural test cannot cover:

      * the property is invisible at runtime until the one code path that needs a browser
        happens to run — and in a suite with no cluster, none of them do;
      * an import is a module-level fact, so importing page_cli at all is enough to make
        the regression real (Playwright, a browser download, ~1s of import time in a CLI
        container that has no display).

    AST, not a grep: a grep matches this docstring, and the words 'page object' appear
    all over the module's comments. tests/test_po_cli_o11y.py uses the same technique for
    the same reason.

    A/B: add `from page_object.po_auth import PageObjectAuth` to page_cli.py and this
    goes red — verified by doing exactly that before committing.
    """
    source = Path(page_cli.__file__).read_text(encoding="utf-8")

    offenders = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            offenders += [a.name for a in node.names if a.name.split(".")[0] == "page_object"]
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] == "page_object":
                offenders.append(node.module)

    assert not offenders, (
        "CLI mode is browser-free (PCP-24380); page_cli.py must not import a page object. "
        f"Found: {sorted(set(offenders))}")


def test_cli_mode_launches_no_browser():
    """The import guard's twin: an import could be avoided while still reaching the
    browser through Util, whose module page_cli legitimately keeps for set_cp_env() and
    print_env_info()."""
    source = Path(page_cli.__file__).read_text(encoding="utf-8")

    called = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in {"browser_launch", "browser_close"}:
                called.add(node.func.attr)

    assert not called, f"CLI mode must not drive a browser; found calls to {sorted(called)}"


# ---------------------------------------------------------------------------
# 6. is_cli_error — pinned, not changed
# ---------------------------------------------------------------------------

class TestIsCliError:
    """Untested until now, and the EMS arm's success/failure verdict runs through it.

    Nothing here is a new requirement: these pin the behaviour as it already is, so the
    next person to touch it finds out what they broke. The ✔-then-✖ ordering in
    particular was checked by reading base.py:270-283 and is correct — tibcop draws a
    spinner and replaces it, so BOTH marks can be present and only the LAST one counts.
    """

    @pytest.mark.parametrize("result", [
        "✔ EMS capability provisioned",
        "",                                   # empty stdout is not an error
        "Warning: No capability instances found",
    ])
    def test_success_shapes(self, result):
        assert TibcopBase.is_cli_error(result) is False

    @pytest.mark.parametrize("result", [
        None,                                 # run_command returns None on a non-zero exit
        "✖ Dataplane not found",
        "Error: something went wrong",
        "request failed",
        "unauthorized",
    ])
    def test_failure_shapes(self, result):
        assert TibcopBase.is_cli_error(result) is True

    def test_a_cross_after_a_check_is_a_failure(self):
        assert TibcopBase.is_cli_error("✔ step one\n✖ step two failed") is True

    def test_a_check_after_a_cross_is_a_success(self):
        """The spinner case: tibcop draws progress and overwrites it, so a ✖ earlier in
        the buffer than the final ✔ is stale output, not a failure."""
        assert TibcopBase.is_cli_error("✖ retrying\n✔ EMS capability provisioned") is False

    def test_the_tls_warning_is_not_an_error(self):
        """run_command sets NODE_TLS_REJECT_UNAUTHORIZED=0, so Node prints a warning on
        every single invocation. It contains no error keyword today, and the filter keeps
        it that way if Node reworks the wording."""
        warning = ("(node:1) Warning: Setting the NODE_TLS_REJECT_UNAUTHORIZED "
                   "environment variable to '0' makes TLS connections insecure.\n"
                   "(Use `node --trace-warnings ...` to show where the warning was created)\n"
                   "provisioned")
        assert TibcopBase.is_cli_error(warning) is False
