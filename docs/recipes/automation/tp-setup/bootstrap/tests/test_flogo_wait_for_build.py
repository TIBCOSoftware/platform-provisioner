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
# PCP-23045: flogo:create-build is ASYNCHRONOUS — it returns as soon as the build is
# accepted, with status "Queued". The old build_and_deploy_app called deploy_app right
# after it, so deploy-app failed every time the build outlived the CLI round-trip:
#
#   Failed to deploy app: Build status is not successful for buildID: <id>,
#   buildStatus: Queued
#
# These tests pin the fix: the deploy must not start until the build reaches a terminal
# Success, and a failed/timed-out build must abort instead of deploying.
#
# All CLI I/O is stubbed at cli_object.base.TibcopBase.run_command, and time.sleep is
# neutralized, so the suite is hermetic and instant (no cluster, no tibcop, no waiting).

import re
import time

import pytest

from cli_object.base import TibcopBase
from cli_object.flogo import TibcopFlogo


class FakeBase:
    """TibcopBase stand-in: scripts run_command output and records commands.

    is_cli_error is the REAL TibcopBase implementation, not a stub — the code under
    test relies on its exact text-matching semantics (it matches the substring
    'failed', which is why get_build_status must parse the JSON before classifying).
    """

    TIBCOP_CLI_PATH = "tibcop"
    is_cli_error = staticmethod(TibcopBase.is_cli_error)

    def __init__(self, status_outputs=None):
        # One entry consumed per get-build-status call; the last one repeats forever
        self.status_outputs = list(status_outputs or [])
        self.commands = []
        # Last status this fake actually served, so a test can assert what the build
        # status was at the moment deploy ran. Stays None if nothing ever asked.
        self.last_status_served = None

    def run_command(self, command, custom_env_dict=None, verbose=True):
        self.commands.append(command)
        if "flogo:get-build-status" in command:
            if not self.status_outputs:
                return None
            if len(self.status_outputs) > 1:
                output = self.status_outputs.pop(0)
            else:
                output = self.status_outputs[0]
            self.last_status_served = _status_of(output)
            return output
        return ""

    def status_call_count(self):
        return len([c for c in self.commands if "flogo:get-build-status" in c])


def _status_of(output):
    """Best-effort status string of a scripted CLI output (None when unparseable)."""
    if not isinstance(output, str):
        return None
    match = re.search(r'"status"\s*:\s*"([^"]+)"', output)
    return match.group(1) if match else None


def _status_json(status):
    return (
        '{\n'
        f'  "status": "{status}",\n'
        '  "elapsedTimeSeconds": 53,\n'
        '  "queued": { "queuedForSeconds": 29, "queueTimeoutSeconds": 600 },\n'
        '  "building": { "buildingForSeconds": 24, "buildTimeoutSeconds": 300 }\n'
        '}'
    )


@pytest.fixture(autouse=True)
def fake_clock(monkeypatch):
    """Virtual clock: sleep() advances monotonic() instead of waiting for real.

    wait_for_build bounds itself on a real monotonic deadline, so the tests must move
    that clock — otherwise a mocked no-op sleep would spin until the deadline.
    """
    now = {"t": 1000.0}
    monkeypatch.setattr(time, "monotonic", lambda: now["t"])
    monkeypatch.setattr(time, "sleep", lambda seconds: now.__setitem__("t", now["t"] + seconds))
    return now


# --------------------------------------------------------------------------
# get_build_status — parsing
# --------------------------------------------------------------------------

def test_get_build_status_parses_status():
    base = FakeBase([_status_json("Success")])
    flogo = TibcopFlogo(base)

    assert flogo.get_build_status("bid1", "dp1") == ("Success", None)

    command = base.commands[0]
    assert "flogo:get-build-status" in command
    assert '--build-id "bid1"' in command
    assert '--dataplane-name "dp1"' in command
    # --no-loop: this code owns the polling loop, not the CLI
    assert "--no-loop" in command
    assert "--json" in command


def test_get_build_status_tolerates_debug_output_before_json():
    base = FakeBase(["some debug line\nanother line\n" + _status_json("Building")])
    flogo = TibcopFlogo(base)

    assert flogo.get_build_status("bid1", "dp1") == ("Building", None)


@pytest.mark.parametrize("output", ["", "   ", "not json at all", '{"noStatusKey": 1}'])
def test_get_build_status_returns_no_status_when_unreadable(output):
    """Unreadable but not an error -> no status, no error text."""
    flogo = TibcopFlogo(FakeBase([output]))
    assert flogo.get_build_status("bid1", "dp1") == (None, None)


@pytest.mark.parametrize("output", [
    "✖ Dataplane not found",
    "Error: request failed with status 401",
    "unauthorized",
])
def test_get_build_status_reports_cli_errors(output):
    """A CLI error must come back as error text, not as an anonymous blank read."""
    status, error = TibcopFlogo(FakeBase([output])).get_build_status("bid1", "dp1")
    assert status is None
    assert error == output.strip()


def test_get_build_status_reports_nonzero_exit_as_error():
    """run_command returns None on a non-zero exit."""
    status, error = TibcopFlogo(FakeBase([None])).get_build_status("bid1", "dp1")
    assert status is None
    assert error == "command failed"


def test_get_build_status_parses_before_classifying_errors():
    """A FAILED BUILD is not a FAILED COMMAND.

    TibcopBase.is_cli_error matches the substring 'failed', so classifying before
    parsing would turn a perfectly valid {"status": "Failed"} payload into a CLI
    error. Parsing must win.
    """
    payload = _status_json("Failed")
    assert TibcopBase.is_cli_error(payload) is True  # the trap this ordering avoids

    assert TibcopFlogo(FakeBase([payload])).get_build_status("bid1", "dp1") == ("Failed", None)




# --------------------------------------------------------------------------
# wait_for_build — terminal states
# --------------------------------------------------------------------------

def test_wait_for_build_polls_until_success():
    base = FakeBase([_status_json("Queued"), _status_json("Building"), _status_json("Success")])
    flogo = TibcopFlogo(base)

    assert flogo.wait_for_build("bid1", "dp1", timeout=100, interval=10) is True
    assert base.status_call_count() == 3


def test_wait_for_build_returns_false_on_failed_build():
    base = FakeBase([_status_json("Queued"), _status_json("Failure")])
    flogo = TibcopFlogo(base)

    assert flogo.wait_for_build("bid1", "dp1", timeout=100, interval=10) is False
    # Stops at the terminal failure instead of polling out the whole timeout
    assert base.status_call_count() == 2


def test_wait_for_build_times_out_when_build_never_finishes():
    base = FakeBase([_status_json("Queued")])
    flogo = TibcopFlogo(base)

    assert flogo.wait_for_build("bid1", "dp1", timeout=30, interval=10) is False
    assert base.status_call_count() == 3


def test_wait_for_build_rides_out_a_transient_unreadable_status():
    """A brief unreadable read must not be mistaken for a failed build."""
    base = FakeBase([None, "not json", _status_json("Success")])
    flogo = TibcopFlogo(base)

    assert flogo.wait_for_build("bid1", "dp1", timeout=100, interval=10) is True
    assert base.status_call_count() == 3


def test_wait_for_build_gives_up_after_repeated_unreadable_statuses():
    """A PERMANENT error (bad dataplane, expired token) must surface in seconds, not
    hide behind 'did not complete within 900s' 15 minutes later."""
    base = FakeBase(["✖ Dataplane not found"])
    flogo = TibcopFlogo(base)

    assert flogo.wait_for_build("bid1", "dp1", timeout=900, interval=10) is False
    assert base.status_call_count() == TibcopFlogo.BUILD_STATUS_MAX_FAILURES


def test_wait_for_build_resets_the_unreadable_streak_on_a_good_read():
    """Scattered blips must not accumulate into a spurious give-up."""
    base = FakeBase([
        None, None, _status_json("Building"),
        None, None, _status_json("Success"),
    ])
    flogo = TibcopFlogo(base)

    assert flogo.wait_for_build("bid1", "dp1", timeout=900, interval=10) is True
    assert base.status_call_count() == 6


@pytest.mark.parametrize("status", ["Success", "success", "SUCCESSFUL", "Succeeded"])
def test_wait_for_build_accepts_success_variants(status):
    flogo = TibcopFlogo(FakeBase([_status_json(status)]))
    assert flogo.wait_for_build("bid1", "dp1", timeout=30, interval=10) is True


@pytest.mark.parametrize("status", [
    "Failure", "failed", "ERROR", "Cancelled",
    # Spellings never observed live: failure is matched by substring precisely so an
    # unlisted terminal failure fails fast instead of looking like "still running".
    "Aborted", "BuildFailed", "Rejected", "Timed Out", "Expired",
])
def test_wait_for_build_rejects_failure_variants(status):
    base = FakeBase([_status_json(status)])
    flogo = TibcopFlogo(base)

    assert flogo.wait_for_build("bid1", "dp1", timeout=900, interval=10) is False
    assert base.status_call_count() == 1  # fails fast, does not burn the timeout


def test_wait_for_build_treats_an_unknown_non_failure_status_as_in_progress():
    """Unknown but not failure-like -> keep waiting (a new in-progress state is not
    a reason to abandon a healthy build)."""
    base = FakeBase([_status_json("Materializing"), _status_json("Success")])
    flogo = TibcopFlogo(base)

    assert flogo.wait_for_build("bid1", "dp1", timeout=100, interval=10) is True
    assert base.status_call_count() == 2


def test_wait_for_build_bounds_itself_on_real_elapsed_time(fake_clock):
    """The budget is wall-clock, not a count of intervals: each poll spawns a tibcop
    subprocess that costs seconds of its own, and those must count against it."""
    started = fake_clock["t"]

    class SlowBase(FakeBase):
        def run_command(self, command, custom_env_dict=None, verbose=True):
            fake_clock["t"] += 5  # every status poll costs 5s of real time
            return super().run_command(command, custom_env_dict, verbose)

    base = SlowBase([_status_json("Queued")])
    assert TibcopFlogo(base).wait_for_build("bid1", "dp1", timeout=30, interval=10) is False

    # 5s poll + 10s sleep per round => 2 rounds fit in 30s, not 3
    assert base.status_call_count() == 2
    assert fake_clock["t"] - started <= 30


def test_in_progress_vocabulary_stays_disjoint_from_the_failure_markers():
    """Pins the invariant documented next to the constants: the failure check is a
    substring match and runs first, so an in-progress state whose name contained a
    failure marker would silently read as a terminal failure."""
    for status in TibcopFlogo.BUILD_IN_PROGRESS_STATUSES:
        clashes = [m for m in TibcopFlogo.BUILD_FAILURE_MARKERS if m in status]
        assert not clashes, f"in-progress status {status!r} contains failure marker(s) {clashes}"

    for status in TibcopFlogo.BUILD_SUCCESS_STATUSES:
        clashes = [m for m in TibcopFlogo.BUILD_FAILURE_MARKERS if m in status]
        assert not clashes, f"success status {status!r} contains failure marker(s) {clashes}"


def test_wait_for_build_logs_progress_on_every_poll(capsys):
    """The wait must stay visible in the pipeline log (CLAUDE.md rule #5: poll and
    report, never wait silently) — a stuck build has to show progress rather than
    look like a hang."""
    base = FakeBase([
        _status_json("Queued"), _status_json("Building"), None, _status_json("Success"),
    ])
    assert TibcopFlogo(base).wait_for_build("bid1", "dp1", timeout=100, interval=10) is True

    lines = [ln for ln in capsys.readouterr().out.splitlines() if "bid1" in ln]
    # One line per poll (Queued, Building, unreadable, Success) plus the opening notice
    assert len(lines) == base.status_call_count() + 1
    assert any("Waiting for Flogo build" in ln for ln in lines)
    assert any("'Queued'" in ln for ln in lines)
    assert any("'Building'" in ln for ln in lines)
    assert any("unreadable" in ln for ln in lines)
    assert any("finished: Success" in ln for ln in lines)
    # Elapsed time is reported so a stuck build is measurable from the log alone
    assert any("elapsed" in ln for ln in lines)


def test_wait_for_build_clamps_a_degenerate_interval(fake_clock):
    """interval=0 must not become a tight loop that spams the CLI."""
    started = fake_clock["t"]
    base = FakeBase([_status_json("Queued")])

    assert TibcopFlogo(base).wait_for_build("bid1", "dp1", timeout=3, interval=0) is False
    assert base.status_call_count() == 3  # clamped to 1s, not unbounded
    assert fake_clock["t"] - started == 3


# --------------------------------------------------------------------------
# build_and_deploy_app — the regression this ticket is about
# --------------------------------------------------------------------------

class _StubVersionApi:
    def get_capability_version(self, capability, dp_name, select_last=False):
        return "2.26.6-b584"

    def get_connector_version(self, dp_name, connector_id='General'):
        return "1.6.15-b04"


class _StubCapability:
    def is_capability_provisioned(self, dp_name, capability):
        return True

    def provision_version(self, capability, dp_name, version, other_args=None):
        return "ok"


def _flogo_under_test(base, monkeypatch, deploy_calls):
    """TibcopFlogo with steps 1-3 stubbed, so only the step 4 -> 5 seam is exercised."""
    flogo = TibcopFlogo(base, version_api=_StubVersionApi(), capability=_StubCapability())
    monkeypatch.setattr(flogo, "list_versions", lambda *a, **k: "2.26.6-b584")
    monkeypatch.setattr(flogo, "create_build", lambda *a, **k: "bid1")

    def fake_deploy(dp_name, dp_namespace, deploy_config_file, build_id=None, other_args=None):
        # Record the build status as last reported to the code under test. None means
        # the deploy ran without the build status ever having been checked — which is
        # exactly the PCP-23045 bug, and keeps this assertion meaningful on the old
        # code too (where wait_for_build/get_build_status do not exist at all).
        deploy_calls.append(base.last_status_served)
        return "deployed"

    monkeypatch.setattr(flogo, "deploy_app", fake_deploy)
    return flogo


def test_build_and_deploy_waits_for_success_before_deploying(monkeypatch, tmp_path):
    """Regression: deploy must not run while the build is still Queued/Building."""
    app_file = tmp_path / "rest-flogo-1.json"
    app_file.write_text("{}")
    config_file = tmp_path / "flogo-payload.json"
    config_file.write_text("{}")

    base = FakeBase([_status_json("Queued"), _status_json("Building"), _status_json("Success")])
    deploy_calls = []
    flogo = _flogo_under_test(base, monkeypatch, deploy_calls)

    assert flogo.build_and_deploy_app("dp1", str(app_file), str(config_file), "dp1ns") is True
    # Deploy ran exactly once, and only after the build reported Success.
    # Pre-fix this was [None] — deploy fired while the build was still Queued.
    assert deploy_calls == ["Success"]


def test_build_and_deploy_skips_deploy_when_build_fails(monkeypatch, tmp_path):
    app_file = tmp_path / "rest-flogo-1.json"
    app_file.write_text("{}")
    config_file = tmp_path / "flogo-payload.json"
    config_file.write_text("{}")

    base = FakeBase([_status_json("Failure")])
    deploy_calls = []
    flogo = _flogo_under_test(base, monkeypatch, deploy_calls)

    assert flogo.build_and_deploy_app("dp1", str(app_file), str(config_file), "dp1ns") is False
    assert deploy_calls == []


def test_build_and_deploy_does_not_forward_other_args_to_the_status_poll(monkeypatch, tmp_path):
    """The operator's free-form flags target the operation they picked (create-build /
    deploy-app). One that get-build-status rejects would abort the wait, so the poll
    keeps a fixed argv."""
    app_file = tmp_path / "rest-flogo-1.json"
    app_file.write_text("{}")
    config_file = tmp_path / "flogo-payload.json"
    config_file.write_text("{}")

    base = FakeBase([_status_json("Success")])
    flogo = _flogo_under_test(base, monkeypatch, [])

    flogo.build_and_deploy_app("dp1", str(app_file), str(config_file), "dp1ns",
                               other_args="--flogo-version 1.2.3")

    status_commands = [c for c in base.commands if "flogo:get-build-status" in c]
    assert status_commands
    for command in status_commands:
        assert "--flogo-version" not in command
