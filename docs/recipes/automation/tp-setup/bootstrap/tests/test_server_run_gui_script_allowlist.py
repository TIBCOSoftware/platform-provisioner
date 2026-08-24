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
# Regression tests for TPSEC-135 (security finding f026):
#   /run-gui-script must NOT load an arbitrary attacker-controlled module, and
#   set_env_vars_from_request must NOT propagate attacker-controlled process
#   loader-hijack environment variables (PYTHONPATH / LD_PRELOAD / PATH / ...).
#
# These are hermetic: subprocess.Popen is replaced by a spy, so no real child
# process is ever spawned. Red before the fix, green after.

import io
import os

import pytest

import server


@pytest.fixture
def client():
    server.app.config.update(TESTING=True)
    return server.app.test_client()


class _FakePopen:
    """Minimal stand-in for subprocess.Popen so run_gui_script's generate() can
    drive it without spawning a real process. poll() returns 0 (already
    finished) so the streaming loop exits immediately."""

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.pid = 4321
        self.stdout = io.BytesIO(b"")

    def poll(self):
        return 0

    def wait(self, timeout=None):
        return 0

    def terminate(self):
        pass

    def kill(self):
        pass


@pytest.fixture
def popen_spy(monkeypatch, tmp_path):
    calls = []

    def _spy(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return _FakePopen(*args, **kwargs)

    monkeypatch.setattr(server.subprocess, "Popen", _spy)
    # keep report-folder cleanup hermetic (run_gui_script touches cwd/report)
    monkeypatch.setattr(server.os, "getcwd", lambda: str(tmp_path))
    return calls


def _spawned_modules(calls):
    """Module names passed to `python -u -m <module>` across all spy calls."""
    mods = []
    for c in calls:
        argv = c["args"][0] if c["args"] else None
        if isinstance(argv, (list, tuple)) and "-m" in argv:
            i = argv.index("-m")
            if i + 1 < len(argv):
                mods.append(argv[i + 1])
    return mods


# --- AC1: arbitrary module execution is refused -----------------------------

@pytest.mark.parametrize("bad_case", ["http.server", "os", "venv", "upload.evil"])
def test_run_gui_script_rejects_non_allowlisted_module(client, popen_spy, bad_case):
    resp = client.get(f"/run-gui-script?case={bad_case}")
    resp.get_data()  # consume the streaming response so generate() would run
    assert resp.status_code == 404, f"non-allowlisted case {bad_case!r} must be rejected"
    # The 404 must happen BEFORE any process is spawned — assert nothing ran at all,
    # not merely that the bad module wasn't the one spawned.
    assert popen_spy == [], f"a rejected case ({bad_case!r}) must not spawn ANY process"


# --- AC2: legitimate automation cases still run (no over-restriction) --------

# Parametrize over the FULL allowlist so a future silent drop of ANY entry is caught.
@pytest.mark.parametrize("good_case", sorted(server.ALLOWED_GUI_CASES))
def test_run_gui_script_allows_legit_case(client, popen_spy, good_case):
    resp = client.get(f"/run-gui-script?case={good_case}")
    resp.get_data()
    assert resp.status_code == 200, f"legit case {good_case!r} must be accepted"
    assert good_case in _spawned_modules(popen_spy), \
        f"legit case {good_case!r} must be spawned"


# --- AC3/AC4: env-var injection is blocked, legit vars pass through ----------

def test_set_env_vars_blocks_loader_hijack_keys():
    injected = {
        "PYTHONPATH": "/upload_dir",
        "PYTHONSTARTUP": "/tmp/startup.py",
        "LD_PRELOAD": "/tmp/evil.so",
        "DYLD_INSERT_LIBRARIES": "/tmp/evil.dylib",
        "PATH": "/attacker/bin",
        "BASH_ENV": "/tmp/x.sh",
        "GIT_SSH_COMMAND": "touch /tmp/pwned;",
        "NODE_OPTIONS": "--require=/tmp/evil.js",
        "JAVA_TOOL_OPTIONS": "-javaagent:/tmp/evil.jar",
        "KUBECONFIG": "/app/upload/evil.yaml",
        "HOME": "/app/upload",
    }
    env = server.set_env_vars_from_request({
        **injected,
        "TP_AUTO_X": "ok",
        "TIBCOP_CLI_DP_NAME": "dp1",
    })
    # A request must never set/override a load/exec-hijack var. Hermetic assertion:
    # the value the request tried to inject must NOT win — the key keeps the
    # server's own os.environ baseline (absent if the server didn't have it),
    # independent of whatever the host/CI environment happens to set.
    for key, attacker_value in injected.items():
        assert env.get(key) == os.environ.get(key), \
            f"{key} must keep the server baseline, not the request value"
        assert env.get(key) != attacker_value, f"{key} carried the injected value"
    # legit automation vars still pass through (AC4)
    assert env.get("TP_AUTO_X") == "ok"
    assert env.get("TIBCOP_CLI_DP_NAME") == "dp1"
    # `case` is never propagated as an env var
    assert "case" not in env


# --- F-A: allowlist drift guard --------------------------------------------
# Reviewed snapshot of the security allowlist. If you change server.ALLOWED_GUI_CASES
# (add/remove a GUI or MCP automation case), update this snapshot in the SAME PR — the
# forced diff makes the security-boundary change reviewable and catches an accidental
# drop (which would 404 a real case and break automation) or an unreviewed broadening.
# Source of truth: templates/index.html #guiAutoCase options AFTER static/index.js
# handleGuiSpecialCase(), plus the mcps run_automation_task(...) call sites.
_EXPECTED_ALLOWED_GUI_CASES = frozenset({
    "page_env", "page_setting", "page_auth", "page_o11y",
    "case.create_global_config",
    "case.k8s_create_dp", "case.k8s_config_dp_o11y", "case.k8s_delete_dp",
    "case.k8s_provision_capability",
    "case.k8s_create_and_start_bwce_app",
    "case.k8s_create_and_start_flogo_app",
    "case.k8s_create_and_start_springboot_app",
    "case.k8s_deploy_mcp_hub", "case.k8s_delete_app",
    "case.bmdp_create_dp", "case.bmdp_config_dp_o11y", "case.bmdp_create_bw5dm",
    "case.bmdp_provision_capability", "case.bmdp_delete_dp", "case.bmdp_delete_bw5dm",
})


def test_allowlist_matches_reviewed_snapshot():
    """Iterating ALLOWED_GUI_CASES elsewhere can't catch an add/drop; this pins the
    exact set so any change to the security boundary is deliberate and reviewed."""
    assert server.ALLOWED_GUI_CASES == _EXPECTED_ALLOWED_GUI_CASES


# --- F-C: missing / empty case must 400 (and never spawn) ------------------

@pytest.mark.parametrize("url", ["/run-gui-script", "/run-gui-script?case="])
def test_run_gui_script_missing_case_400(client, popen_spy, url):
    resp = client.get(url)
    resp.get_data()
    assert resp.status_code == 400
    assert popen_spy == []


# --- F-D: allowlist is EXACT; env block is case-insensitive ----------------

@pytest.mark.parametrize("mangled", [
    "PAGE_ENV", "Case.K8s_Create_Dp",
    " case.k8s_create_dp", "case.k8s_create_dp ",
])
def test_run_gui_script_allowlist_is_exact(client, popen_spy, mangled):
    resp = client.get(f"/run-gui-script?case={mangled}")
    resp.get_data()
    assert resp.status_code == 404, f"{mangled!r} must not match the allowlist"
    assert popen_spy == []


def test_set_env_vars_block_is_case_insensitive():
    """The block check upper()s the key, so mixed-case gadget vars are still dropped
    (a case-fold bypass guard). Pinned so removing .upper() fails a test."""
    env = server.set_env_vars_from_request({
        "Ld_Preload": "/x.so", "pythonpath": "/e", "KubeConfig": "/app/upload/e.yaml",
    })
    assert env.get("Ld_Preload") != "/x.so"
    assert env.get("pythonpath") != "/e"
    assert env.get("KubeConfig") != "/app/upload/e.yaml"


# --- F-E: the ACTUAL spawned gui child env is filtered (route-level AC3) ----

def test_run_gui_script_child_env_excludes_injected_keys(client, popen_spy):
    resp = client.get(
        "/run-gui-script?case=case.k8s_create_dp"
        "&PYTHONPATH=/evil&KUBECONFIG=/app/upload/evil.yaml&TP_AUTO_X=ok"
    )
    resp.get_data()
    assert popen_spy, "a legit case should spawn"
    child_env = popen_spy[-1]["kwargs"].get("env", {})
    assert child_env.get("PYTHONPATH") == os.environ.get("PYTHONPATH")
    assert child_env.get("KUBECONFIG") == os.environ.get("KUBECONFIG")
    assert child_env.get("TP_AUTO_X") == "ok"  # legit var still reaches the child


# --- F2: the 404 body must not reflect raw user input (reflected XSS) -------

def test_run_gui_script_404_body_escapes_case(client, popen_spy):
    resp = client.get("/run-gui-script?case=<img src=x onerror=alert(1)>")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 404
    assert "<img" not in body, "raw HTML must not be reflected in the 404 body"
    assert "&lt;img" in body, "the case value must be HTML-escaped"
    assert popen_spy == []
