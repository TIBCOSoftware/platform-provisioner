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
# PCP-23440: in CLI mode the three 'Start <capability> App' toggles were silent no-ops.
# orchestrator.py wrote ENV.TP_AUTO_START_{FLOGO,BWCE,BW5CE}_APP into the capability task
# dict as 'start_enabled' and then NEVER read it back, so:
#
#   1. the app was always deployed with the payload's hardcoded "replicas": 1, and
#   2. phase 3 always waited for its pods, tested the endpoint and made it public.
#
# GUI mode (page_dp.py) gates only *_app_start / *_app_test_endpoint on the flag, so a
# disabled app ends up DEPLOYED BUT NOT RUNNING. These tests pin the CLI path to that
# same outcome. Both halves matter: replicas alone would still be endpoint-tested, and
# the phase-3 gate alone would leave the app running via the payload's replicas: 1.
#
# PCP-23459 then closed the three edges that fix left open:
#
#   a. the toggle was inert on a RESUMED run — _deploy_worker returned at its ReportYaml
#      status short-circuit before reading the toggle, while select_endpoint_test_tasks
#      read it outside that short-circuit, so OFF-then-ON left the app at replicas: 0 and
#      burned the full wait_for_app_pods timeout on every subsequent run, forever;
#   b. 'replicas' was persisted into the GIT-TRACKED upload/*-payload.json, making one
#      run's toggle the next run's starting point (and dirtying the working tree);
#   c. 'replicas: 0' did not neutralise an HPA whose minReplicas is 1, so with an
#      autoscaling payload the stopped app was scaled straight back up.
#
# Pure JSON-mutation / task-list logic — no cluster, no tibcop, no browser.

import json
import os

import pytest

from cli_object.orchestrator import (
    TibcopOrchestrator,
    prepare_deploy_config,
    recorded_bool,
    select_endpoint_test_tasks,
)
from utils.report import ReportYaml


def write_config(tmp_path, config, name="payload.json"):
    """Write a deploy config JSON like upload/{bwce,bw5ce,flogo}-payload.json."""
    path = tmp_path / name
    path.write_text(json.dumps(config, indent=2))
    return str(path)


def read_config(path):
    with open(path) as f:
        return json.load(f)


@pytest.fixture
def scratch(tmp_path):
    """The run-scoped directory _deploy_worker hands to prepare_deploy_config."""
    d = tmp_path / "scratch"
    d.mkdir()
    return str(d)


# --------------------------------------------------------------------------
# prepare_deploy_config — the tracked payload is READ-ONLY
# --------------------------------------------------------------------------

def test_the_source_payload_is_never_written_to(tmp_path, scratch):
    """PCP-23459(b): the whole point of the run-scoped copy.

    'replicas' is per-run policy read from an env var, while upload/*-payload.json is
    checked into the repo and shared by every run. Persisting the toggle there dirties
    the working tree, invites committing a 'replicas: 0', and makes the next run's
    starting point depend on the last run's toggle.
    """
    source = write_config(tmp_path, {"appName": "rest-bwce-1", "replicas": 1})
    before = open(source, "rb").read()

    run_config = prepare_deploy_config(source, False, scratch)

    assert read_config(run_config)["replicas"] == 0
    assert open(source, "rb").read() == before  # byte-identical, not merely equivalent


def test_the_run_config_is_a_separate_file_inside_the_scratch_dir(tmp_path, scratch):
    source = write_config(tmp_path, {"appName": "rest-bwce-1", "replicas": 1},
                          name="bwce-payload.json")

    run_config = prepare_deploy_config(source, False, scratch)

    assert os.path.dirname(run_config) == scratch
    assert os.path.basename(run_config) == "bwce-payload.json"
    assert os.path.abspath(run_config) != os.path.abspath(source)


def test_a_tracked_payload_is_not_reformatted(tmp_path, scratch):
    """PCP-23459(b), item 5: upload/flogo-payload.json is 4-space indented and flogo.py
    re-writes it with indent=4, while this helper writes indent=2. In-place that meant an
    early return could leave the whole tracked file reformatted. Copying makes the
    indentation of the copy irrelevant — the source keeps its own bytes.
    """
    source = tmp_path / "flogo-payload.json"
    source.write_text(json.dumps({"appName": "rest-flogo-1", "replicas": 1}, indent=4))
    before = source.read_text()

    prepare_deploy_config(str(source), False, scratch)

    assert source.read_text() == before


# --------------------------------------------------------------------------
# prepare_deploy_config — replicas
# --------------------------------------------------------------------------

def test_start_disabled_sets_replicas_to_zero(tmp_path, scratch):
    """Toggle OFF: the shipped payload's replicas: 1 must become 0 (deployed, not running)."""
    source = write_config(tmp_path, {"appName": "rest-bwce-1", "replicas": 1})

    assert read_config(prepare_deploy_config(source, False, scratch))["replicas"] == 0


def test_start_disabled_preserves_other_config_keys(tmp_path, scratch):
    """Only replicas changes — buildId, resourceLimits, systemProperties survive intact."""
    original = {
        "buildId": "3d9eb6b19be94f83a7a755c399445445",
        "appName": "rest-bwce-1",
        "eula": True,
        "replicas": 1,
        "resourceLimits": {"limits": {"cpu": "1", "memory": "4Gi"}},
        "systemProperties": [{"name": "BW_ENGINE_THREADCOUNT", "value": "8", "type": "integer"}],
        "tags": ["cli-created"],
    }
    source = write_config(tmp_path, original)

    updated = read_config(prepare_deploy_config(source, False, scratch))

    assert updated == {**original, "replicas": 0}


def test_start_enabled_keeps_replicas_one(tmp_path, scratch):
    source = write_config(tmp_path, {"appName": "rest-bwce-1", "replicas": 1})

    assert read_config(prepare_deploy_config(source, True, scratch))["replicas"] == 1


def test_start_enabled_restores_a_previously_stopped_app(tmp_path, scratch):
    """A payload a user deliberately saved with replicas: 0 must still start when the
    toggle says so — 'Start app' is the instruction, the payload is the template."""
    source = write_config(tmp_path, {"appName": "rest-bwce-1", "replicas": 0})

    assert read_config(prepare_deploy_config(source, True, scratch))["replicas"] == 1


def test_start_enabled_keeps_an_explicit_scale_out(tmp_path, scratch):
    """replicas: 3 is a deliberate choice; 'start the app' must not flatten it to 1."""
    source = write_config(tmp_path, {"appName": "rest-bwce-1", "replicas": 3})

    assert read_config(prepare_deploy_config(source, True, scratch))["replicas"] == 3


def test_start_enabled_defaults_a_config_without_replicas(tmp_path, scratch):
    source = write_config(tmp_path, {"appName": "rest-bwce-1"})

    assert read_config(prepare_deploy_config(source, True, scratch))["replicas"] == 1


def test_start_disabled_on_config_without_replicas(tmp_path, scratch):
    source = write_config(tmp_path, {"appName": "rest-bwce-1"})

    assert read_config(prepare_deploy_config(source, False, scratch))["replicas"] == 0


# --------------------------------------------------------------------------
# prepare_deploy_config — autoscaling (PCP-23459 c)
# --------------------------------------------------------------------------

def test_stopping_an_autoscaled_app_also_disables_autoscaling(tmp_path, scratch):
    """replicas: 0 does not stop an app whose HPA floor is 1.

    upload/{bwce,bw5ce}-payload-full.json ship enableAutoscaling: true with
    minReplicas: 1 and are reachable via TP_AUTO_BWCE_APP_PAYLOAD_JSON and the
    /save-{bwce,flogo}-payload editor endpoints. Leaving the HPA on scales the stopped
    app straight back to 1 and the toggle silently reverts to the no-op PCP-23440 fixed.
    """
    source = write_config(tmp_path, {
        "appName": "rest-bwce-1",
        "replicas": 1,
        "enableAutoscaling": True,
        "autoscalingConfig": {"minReplicas": 1, "maxReplicas": 3},
    })

    updated = read_config(prepare_deploy_config(source, False, scratch))

    assert updated["replicas"] == 0
    assert updated["enableAutoscaling"] is False
    # autoscalingConfig is inert once autoscaling is off, so it is left alone rather than
    # deleted — the user's min/max survive for whenever they turn the app back on.
    assert updated["autoscalingConfig"] == {"minReplicas": 1, "maxReplicas": 3}


def test_starting_an_autoscaled_app_leaves_autoscaling_alone(tmp_path, scratch):
    """The toggle only ever STOPS autoscaling. Re-enabling it would be guessing at a
    value the user never gave us, which is the persisted-policy problem all over again.
    """
    source = write_config(tmp_path, {
        "appName": "rest-bwce-1", "replicas": 1, "enableAutoscaling": True,
    })

    updated = read_config(prepare_deploy_config(source, True, scratch))

    assert updated["enableAutoscaling"] is True


def test_stopping_a_non_autoscaled_app_does_not_invent_the_key(tmp_path, scratch):
    """A payload without enableAutoscaling must not grow one — deploy-app validates the
    payload schema, so an invented key is a new way to fail."""
    source = write_config(tmp_path, {"appName": "rest-bwce-1", "replicas": 1})

    assert "enableAutoscaling" not in read_config(prepare_deploy_config(source, False, scratch))


def test_stopping_respects_an_explicitly_disabled_autoscaling_flag(tmp_path, scratch):
    """The shipped payloads are enableAutoscaling: false; the key stays false, untouched."""
    source = write_config(tmp_path, {
        "appName": "rest-bwce-1", "replicas": 1, "enableAutoscaling": False,
    })

    assert read_config(prepare_deploy_config(source, False, scratch))["enableAutoscaling"] is False


# --------------------------------------------------------------------------
# prepare_deploy_config — failure paths
# --------------------------------------------------------------------------

def test_missing_config_file_reports_failure(tmp_path, scratch):
    """A missing/unreadable config returns None so the caller can fail the deploy instead
    of silently deploying a running app while claiming it is stopped."""
    assert prepare_deploy_config(str(tmp_path / "nope.json"), False, scratch) is None


def test_malformed_config_file_reports_failure(tmp_path, scratch):
    path = tmp_path / "payload.json"
    path.write_text("{not json")

    assert prepare_deploy_config(str(path), False, scratch) is None


def test_non_object_config_root_reports_failure(tmp_path, scratch):
    """Valid JSON whose root is not an object must return None, not raise.

    config.get() would be an AttributeError on a list/string root, which the
    (OSError, ValueError) catch does not cover — the function is documented to
    report failure by returning None, so the caller can fail the deploy.
    """
    path = tmp_path / "payload.json"
    path.write_text('["not", "an", "object"]')

    assert prepare_deploy_config(str(path), False, scratch) is None


@pytest.mark.parametrize("start_enabled", [True, False])
def test_unwritable_scratch_dir_reports_failure(tmp_path, scratch, monkeypatch, start_enabled):
    """An unwritable scratch dir returns None whichever way the toggle is set.

    The source is still readable and still untouched — the failure cannot leave a
    half-written tracked payload behind, which is exactly what the in-place write could.
    """
    source = write_config(tmp_path, {"appName": "rest-bwce-1", "replicas": 1})
    before = open(source, "rb").read()
    real_open = open

    def deny_scratch_write(file, mode="r", *args, **kwargs):
        if "w" in mode and str(file).startswith(scratch):
            raise OSError("read-only file system")
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr("builtins.open", deny_scratch_write)

    assert prepare_deploy_config(source, start_enabled, scratch) is None
    assert real_open(source, "rb").read() == before


# --------------------------------------------------------------------------
# recorded_bool — reading the report back
# --------------------------------------------------------------------------

@pytest.mark.parametrize("recorded,expected", [
    ("true", True),
    ("false", False),
    ("True", True),      # ReportYaml round-trips through yq, so casing is not guaranteed
    ("FALSE", False),
    (" true ", True),    # yq output is stripped by ReportYaml.get, but do not rely on it
    (True, True),
    (False, False),
])
def test_recorded_bool_reads_the_yq_string_back(recorded, expected):
    assert recorded_bool(recorded) is expected


def test_an_unrecorded_toggle_is_unknown_not_a_default():
    """A report written before this field existed does not say which toggle produced it.

    It must NOT be guessed. A pre-PCP-23440 run ignored the toggle and always deployed the
    app running, but a PCP-23440 run (release 1.7.80, already in main) honoured it and could
    have deployed the app at replicas: 0 without recording why. Defaulting to True would
    leave such an app stopped on a toggle-ON run — the exact defect this change fixes — so
    the answer is None and the caller converges by re-deploying once.
    """
    assert recorded_bool(None) is None


# --------------------------------------------------------------------------
# select_endpoint_test_tasks
# --------------------------------------------------------------------------

def cap_task(key, start_enabled=True, endpoint_path="/"):
    task = {"key": key, "endpoint_path": endpoint_path}
    if start_enabled is not None:
        task["start_enabled"] = start_enabled
    return task


def test_stopped_app_is_not_endpoint_tested():
    """A stopped app has no pods, so waiting for them would only burn the
    wait_for_app_pods timeout and log a misleading warning."""
    tasks = [cap_task("FLOGO", start_enabled=True), cap_task("BWCE", start_enabled=False)]
    deploy_results = {"FLOGO": True, "BWCE": True}

    selected = select_endpoint_test_tasks(tasks, deploy_results)

    assert [t["key"] for t in selected] == ["FLOGO"]


def test_all_started_apps_are_endpoint_tested():
    tasks = [
        cap_task("FLOGO", start_enabled=True),
        cap_task("BWCE", start_enabled=True),
        cap_task("BW5CE", start_enabled=True),
    ]
    deploy_results = {"FLOGO": True, "BWCE": True, "BW5CE": True}

    selected = select_endpoint_test_tasks(tasks, deploy_results)

    assert [t["key"] for t in selected] == ["FLOGO", "BWCE", "BW5CE"]


def test_failed_deploy_is_not_endpoint_tested():
    tasks = [cap_task("FLOGO", start_enabled=True), cap_task("BWCE", start_enabled=True)]
    deploy_results = {"FLOGO": True, "BWCE": False}

    selected = select_endpoint_test_tasks(tasks, deploy_results)

    assert [t["key"] for t in selected] == ["FLOGO"]


def test_provision_only_capability_is_not_endpoint_tested():
    """TIBCOHUB has no deploy_func and no endpoint_path."""
    tasks = [cap_task("FLOGO", start_enabled=True), cap_task("TIBCOHUB", endpoint_path=None)]
    deploy_results = {"FLOGO": True, "TIBCOHUB": True}

    selected = select_endpoint_test_tasks(tasks, deploy_results)

    assert [t["key"] for t in selected] == ["FLOGO"]


def test_task_without_start_enabled_key_defaults_to_started():
    """Backward compatible: a task dict that predates the flag is still tested."""
    tasks = [cap_task("FLOGO", start_enabled=None)]

    selected = select_endpoint_test_tasks(tasks, {"FLOGO": True})

    assert [t["key"] for t in selected] == ["FLOGO"]


# --------------------------------------------------------------------------
# The two halves together: the toggle must reach BOTH the deploy config and phase 3
# --------------------------------------------------------------------------

@pytest.mark.parametrize("start_enabled,expected_replicas,expected_tested", [
    (True, 1, True),
    (False, 0, False),
])
def test_toggle_drives_both_replicas_and_endpoint_test(tmp_path, scratch, start_enabled,
                                                       expected_replicas, expected_tested):
    source = write_config(tmp_path, {"appName": "rest-bwce-1", "replicas": 1})
    task = {"key": "BWCE", "endpoint_path": "/swagger/", "start_enabled": start_enabled}

    run_config = prepare_deploy_config(source, start_enabled, scratch)

    assert read_config(run_config)["replicas"] == expected_replicas
    assert bool(select_endpoint_test_tasks([task], {"BWCE": True})) is expected_tested


# --------------------------------------------------------------------------
# _deploy_worker wiring: the helper must actually be called on the deploy path
# --------------------------------------------------------------------------

class FakeApp:
    """cli.app stand-in for _get_app_state."""

    @staticmethod
    def _get_apps_data(dp_name):
        return [{"app_name": "rest-bwce-1", "capability_id": "BWCE", "app_state": "Deployed"}]


class FakeCLI:
    def __init__(self):
        self.app = FakeApp()


class FakeReport:
    """Stateful stand-in for the app section of report.yaml.

    A dict is not enough for the resume tests: _deploy_worker now READS BACK what a
    previous run wrote, so the fake has to round-trip the value the way ReportYaml does
    — through yq, i.e. as a lowercase string.
    """

    def __init__(self, initial=None):
        self.info = dict(initial or {})
        self.writes = []

    def get(self, dp_name, capability, app_name, app_key):
        value = self.info.get(app_key)
        return None if value is None else str(value).lower()

    def set(self, dp_name, capability, app_name, app_key, app_value):
        self.info[app_key] = app_value
        self.writes.append((app_key, app_value))


@pytest.fixture
def deploy_worker_env(tmp_path, monkeypatch):
    """Neutralize the report + upload-folder I/O so _deploy_worker can run offline.

    Returns (make_env) — a factory taking the report's starting state, so a test can set
    up "a previous run already deployed this app with the toggle ON" and then run again.
    """
    def make_env(report_state=None, config=None):
        upload = tmp_path / "upload"
        upload.mkdir(exist_ok=True)
        app_file = upload / "rest-bwce-1.ear"
        app_file.write_text("ear")
        config_file = upload / "bwce-payload.json"
        config_file.write_text(json.dumps(config or {"appName": "rest-bwce-1", "replicas": 1},
                                          indent=2))

        files = {"rest-bwce-1.ear": str(app_file), "bwce-payload.json": str(config_file)}
        monkeypatch.setattr("cli_object.orchestrator.Helper.get_file_fullpath_in_upload_folder",
                            staticmethod(lambda name: files[name]))

        report = FakeReport(report_state)
        monkeypatch.setattr(ReportYaml, "get_capability_app_info", report.get)
        monkeypatch.setattr(ReportYaml, "set_capability_app", lambda *a, **k: None)
        monkeypatch.setattr(ReportYaml, "set_capability_app_info", report.set)

        seen = {"calls": 0}

        def deploy_func(dp_name, app_file_path, deploy_config_file, dp_namespace):
            seen["calls"] += 1
            seen["config_path"] = deploy_config_file
            seen["config"] = read_config(deploy_config_file)
            seen["replicas"] = seen["config"].get("replicas")
            # build_and_deploy_app stamps the buildId into whatever path it is handed;
            # do the same so the tests prove upload/ survives THAT write too. Read the
            # file back HERE — the scratch dir is gone by the time the test body runs.
            stamped = dict(seen["config"], buildId="deadbeef")
            with open(deploy_config_file, "w") as f:
                json.dump(stamped, f, indent=2)
            seen["config_after_write"] = read_config(deploy_config_file)
            return True

        return TibcopOrchestrator(FakeCLI()), deploy_func, seen, report, str(config_file)

    return make_env


def bwce_task(deploy_func, start_enabled):
    return {
        "key": "BWCE", "report_name": "bwce", "app_name": "rest-bwce-1",
        "app_file": "rest-bwce-1.ear", "deploy_config": "bwce-payload.json",
        "deploy_func": deploy_func, "start_enabled": start_enabled,
    }


@pytest.mark.parametrize("start_enabled,expected_replicas", [(True, 1), (False, 0)])
def test_deploy_worker_applies_the_start_toggle(deploy_worker_env, start_enabled,
                                                expected_replicas):
    """The PCP-23440 regression: with the toggle OFF, deploy-app must receive replicas: 0.

    Before that fix, _deploy_worker called deploy_func straight after resolving the file
    paths, so the payload's hardcoded replicas: 1 always reached the platform.
    """
    orchestrator, deploy_func, seen, _report, _source = deploy_worker_env()
    results = {}

    orchestrator._deploy_worker("k8s-auto-dp1", "k8s-auto-dp1ns",
                                bwce_task(deploy_func, start_enabled), results)

    assert results["BWCE"] is True
    assert seen["replicas"] == expected_replicas


def test_deploy_worker_never_writes_to_the_tracked_payload(deploy_worker_env):
    """PCP-23459(b) end to end: neither the toggle nor deploy_func's buildId stamp may
    reach upload/. deploy_func here writes a buildId exactly as build_and_deploy_app does.
    """
    orchestrator, deploy_func, seen, _report, source = deploy_worker_env()
    before = open(source, "rb").read()

    orchestrator._deploy_worker("k8s-auto-dp1", "k8s-auto-dp1ns",
                                bwce_task(deploy_func, False), {})

    assert seen["replicas"] == 0
    assert seen["config_after_write"]["buildId"] == "deadbeef"  # the stamp landed on the copy
    assert open(source, "rb").read() == before                  # and never on the source


def test_deploy_worker_hands_over_a_path_outside_the_upload_folder(deploy_worker_env):
    """The run-scoped copy must not live next to the tracked payload — a crash mid-deploy
    would otherwise leave a stray file in upload/ for the next run to pick up."""
    orchestrator, deploy_func, seen, _report, source = deploy_worker_env()

    orchestrator._deploy_worker("k8s-auto-dp1", "k8s-auto-dp1ns",
                                bwce_task(deploy_func, False), {})

    assert os.path.dirname(seen["config_path"]) != os.path.dirname(source)
    # TemporaryDirectory cleans up on the way out, so nothing survives the deploy.
    assert not os.path.exists(seen["config_path"])


def test_deploy_worker_fails_loudly_when_the_config_cannot_be_prepared(deploy_worker_env,
                                                                       capsys):
    """No usable config means no deploy. Falling back to the tracked payload would run the
    app at whatever replicas it happens to hold — the silent no-op this path exists to
    prevent. A JSON root that is not an object is the reachable trigger: the file exists,
    so it passes _deploy_worker's os.path.isfile guard.
    """
    orchestrator, deploy_func, seen, _report, _source = deploy_worker_env(
        config=["not", "an", "object"])
    results = {}

    orchestrator._deploy_worker("k8s-auto-dp1", "k8s-auto-dp1ns",
                                bwce_task(deploy_func, True), results)

    assert results["BWCE"] is False
    assert seen["calls"] == 0
    assert "Could not prepare the deploy config" in capsys.readouterr().out


def test_deploy_worker_records_the_toggle_it_deployed_with(deploy_worker_env):
    """The resume comparison is only possible if the toggle is written next to the status."""
    orchestrator, deploy_func, _seen, report, _source = deploy_worker_env()

    orchestrator._deploy_worker("k8s-auto-dp1", "k8s-auto-dp1ns",
                                bwce_task(deploy_func, False), {})

    assert ("startEnabled", False) in report.writes
    assert report.info["deploySucceeded"] is True
    assert report.info["status"] == "Deployed"


def test_deploy_worker_records_the_outcome_even_when_the_deploy_fails(deploy_worker_env):
    """A failed deploy must record deploySucceeded: False, not merely a Failure status.

    The resume short-circuit keys on this field precisely so it never has to parse the
    platform's failure vocabulary out of `status`."""
    orchestrator, _deploy_func, _seen, report, _source = deploy_worker_env()

    orchestrator._deploy_worker(
        "k8s-auto-dp1", "k8s-auto-dp1ns",
        bwce_task(lambda *a, **k: False, True), {})

    assert report.info["status"] == "Failure"
    assert report.info["deploySucceeded"] is False
    assert report.info["startEnabled"] is True


# --------------------------------------------------------------------------
# PCP-23459(a): the resumed run must converge
# --------------------------------------------------------------------------

def test_a_resumed_run_with_an_unchanged_toggle_still_skips(deploy_worker_env):
    """The resume short-circuit is not being removed — only narrowed. An unchanged toggle
    must not trigger a pointless rebuild-and-redeploy on every run."""
    orchestrator, deploy_func, seen, _report, _source = deploy_worker_env(
        {"status": "Running", "deploySucceeded": True, "startEnabled": True})
    results = {}

    orchestrator._deploy_worker("k8s-auto-dp1", "k8s-auto-dp1ns",
                                bwce_task(deploy_func, True), results)

    assert results["BWCE"] is True
    assert seen["calls"] == 0


@pytest.mark.parametrize("start_enabled", [True, False])
def test_a_resumed_run_with_an_unrecorded_toggle_converges_once(deploy_worker_env, capsys,
                                                                start_enabled):
    """A report from before startEnabled existed must be re-deployed, either way.

    This is the 1.7.80 upgrade path and it is NOT symmetric to guess at. PCP-23440 shipped
    in 1.7.80 already honouring the toggle but never recording it, so a report with
    `status` and no `startEnabled` may describe an app that is running OR one sitting at
    replicas: 0. Defaulting to True skips the toggle-ON case and leaves a stopped app
    stopped — the reported defect, unfixed. Defaulting to False re-deploys the toggle-OFF
    case for nothing. Only 'unknown, so converge' is right in both, and the cost is bounded:
    the re-deploy records startEnabled, so it happens once per report, not once per run.
    """
    orchestrator, deploy_func, seen, report, _source = deploy_worker_env({"status": "Running"})

    orchestrator._deploy_worker("k8s-auto-dp1", "k8s-auto-dp1ns",
                                bwce_task(deploy_func, start_enabled), {})

    assert seen["calls"] == 1
    assert seen["replicas"] == (1 if start_enabled else 0)
    assert "predates the report's 'deploySucceeded'/'startEnabled' fields" in capsys.readouterr().out
    assert report.info["startEnabled"] is start_enabled  # and never again after this run


def test_an_unrecorded_toggle_costs_exactly_one_redeploy(deploy_worker_env):
    """The bounded-cost half of the claim above: the upgrade run re-deploys, the next
    run skips. Without this, 'converge on unknown' would rebuild every app every run."""
    orchestrator, deploy_func, seen, _report, _source = deploy_worker_env({"status": "Running"})
    task = bwce_task(deploy_func, True)

    orchestrator._deploy_worker("k8s-auto-dp1", "k8s-auto-dp1ns", task, {})
    assert seen["calls"] == 1

    orchestrator._deploy_worker("k8s-auto-dp1", "k8s-auto-dp1ns", task, {})

    assert seen["calls"] == 1  # unchanged: the second run skipped


# --------------------------------------------------------------------------
# A recorded 'Failure' is not a success — it must be retried, not skipped
# --------------------------------------------------------------------------

def test_a_previously_failed_deploy_is_retried_not_reported_as_success(deploy_worker_env,
                                                                       capsys):
    """`if app_status:` was truthy for 'Failure' too.

    So a deploy that failed last run was skipped on the next one AND recorded
    results[key] = True. select_endpoint_test_tasks then selected that app for phase 3,
    which waited for pods of an app that had never been deployed and burned the full
    wait_for_app_pods timeout on it — the same symptom, reached from the other side.
    """
    orchestrator, deploy_func, seen, _report, _source = deploy_worker_env(
        {"status": "Failure", "deploySucceeded": False, "startEnabled": True})
    results = {}

    orchestrator._deploy_worker("k8s-auto-dp1", "k8s-auto-dp1ns",
                                bwce_task(deploy_func, True), results)

    assert seen["calls"] == 1
    assert results["BWCE"] is True  # True because THIS deploy succeeded, not because it skipped
    assert "its last deploy failed" in capsys.readouterr().out


def test_the_skip_does_not_depend_on_the_platforms_failure_vocabulary(deploy_worker_env,
                                                                       capsys):
    """A failed deploy whose recorded status is NOT the literal word "Failure".

    `status` holds whatever _get_app_state returned, i.e. an unbounded string from the
    platform. Keying the skip on matching failure words there means any spelling this code
    does not itself write - "Failed", "Error", "CrashLoopBackOff" - reads as a success, and
    phase 3 endpoint-tests an app that never came up. deploySucceeded is written by this
    code, so the platform's wording cannot change the decision.
    """
    orchestrator, deploy_func, seen, _report, _source = deploy_worker_env(
        {"status": "CrashLoopBackOff", "deploySucceeded": False, "startEnabled": True})

    orchestrator._deploy_worker("k8s-auto-dp1", "k8s-auto-dp1ns",
                                bwce_task(deploy_func, True), {})

    assert seen["calls"] == 1
    assert "its last deploy failed" in capsys.readouterr().out


def test_an_unrecognised_but_healthy_status_still_skips(deploy_worker_env):
    """The mirror of the above, and why this is not a whitelist of healthy states.

    A whitelist would re-deploy on an unrecognised state - and never converge, because the
    same state gets written back on every run. Keying on the recorded outcome means a CP
    version that invents a new healthy status costs nothing.
    """
    orchestrator, deploy_func, seen, _report, _source = deploy_worker_env(
        {"status": "SomeFutureCpState", "deploySucceeded": True, "startEnabled": True})

    orchestrator._deploy_worker("k8s-auto-dp1", "k8s-auto-dp1ns",
                                bwce_task(deploy_func, True), {})

    assert seen["calls"] == 0


def test_a_still_failing_deploy_is_not_laundered_into_a_success(deploy_worker_env):
    """The retry must report the retry's own outcome. Previously the skip path returned
    True for an app whose only recorded state was 'Failure'."""
    orchestrator, _deploy_func, _seen, report, _source = deploy_worker_env(
        {"status": "Failure", "deploySucceeded": False, "startEnabled": True})
    results = {}

    orchestrator._deploy_worker("k8s-auto-dp1", "k8s-auto-dp1ns",
                                bwce_task(lambda *a, **k: False, True), results)

    assert results["BWCE"] is False
    assert report.info["status"] == "Failure"


def test_toggling_off_then_on_re_deploys_the_stopped_app(deploy_worker_env, capsys):
    """THE reported defect.

    Run 1 with the toggle OFF leaves the app at replicas: 0. Run 2 with the toggle ON used
    to return at the status short-circuit before the toggle was read, so nothing
    re-deployed the app — yet select_endpoint_test_tasks, which reads the live toggle
    outside that short-circuit, still selected it. _wait_and_test_worker's own skip needs
    both endpointPublic and testedEndpoint, which are only written on a successful
    endpoint test and so were never set, so wait_for_app_pods burned its full 120s and
    logged 'App pods not ready, skipping endpoint test' — the exact warning PCP-23440
    removed, on the one path where the user explicitly asked for the app to run. And it
    never converged: every later run paid it again.
    """
    orchestrator, deploy_func, seen, _report, _source = deploy_worker_env(
        {"status": "Deployed", "deploySucceeded": True, "startEnabled": False})

    orchestrator._deploy_worker("k8s-auto-dp1", "k8s-auto-dp1ns",
                                bwce_task(deploy_func, True), {})

    assert seen["calls"] == 1
    assert seen["replicas"] == 1
    assert "to converge: it was deployed with 'Start app' False" in capsys.readouterr().out


def test_toggling_on_then_off_re_deploys_the_running_app(deploy_worker_env):
    """The benign direction, but still a divergence: without this the app keeps running
    and the cores the user asked to reclaim are never released."""
    orchestrator, deploy_func, seen, _report, _source = deploy_worker_env(
        {"status": "Running", "deploySucceeded": True, "startEnabled": True})

    orchestrator._deploy_worker("k8s-auto-dp1", "k8s-auto-dp1ns",
                                bwce_task(deploy_func, False), {})

    assert seen["calls"] == 1
    assert seen["replicas"] == 0


def test_a_flip_converges_in_one_run_not_two(deploy_worker_env):
    """Convergence, not oscillation: after the re-deploy the report agrees with the
    toggle, so the NEXT resumed run skips again instead of re-deploying forever."""
    orchestrator, deploy_func, seen, report, _source = deploy_worker_env(
        {"status": "Deployed", "deploySucceeded": True, "startEnabled": False})

    orchestrator._deploy_worker("k8s-auto-dp1", "k8s-auto-dp1ns",
                                bwce_task(deploy_func, True), {})
    assert seen["calls"] == 1

    orchestrator._deploy_worker("k8s-auto-dp1", "k8s-auto-dp1ns",
                                bwce_task(deploy_func, True), {})

    assert seen["calls"] == 1  # unchanged: the second run skipped
    assert report.info["startEnabled"] is True
