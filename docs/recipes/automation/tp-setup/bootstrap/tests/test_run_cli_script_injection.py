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
# Regression test for TPSEC-134 / finding f023 — unauthenticated OS command
# injection via the /run-cli-script query params.
#
# Attacker-controlled request params (TIBCOP_CLI_OTHER_ARGS and the structured
# TIBCOP_CLI_* params) are interpolated into a command that reaches
# cli_object.base.TibcopBase.run_command. On the vulnerable code the sink runs
# subprocess.run(command_string, shell=True), so a payload like ";touch /tmp/pwned"
# is executed by /bin/sh. The fix executes a single tibcop invocation WITHOUT a
# shell (shell=False + an argv list), so shell metacharacters survive only as
# inert literal argv tokens.
#
# These tests exercise the real command construction (cli_object.dataplane) down
# to the real sink (cli_object.base), monkeypatching subprocess.run so nothing
# actually executes. They FAIL on the vulnerable code (shell=True / string command)
# and pass after the fix.

import types

from cli_object.base import TibcopBase
from cli_object.dataplane import TibcopDataPlane


def _capturing_base(monkeypatch):
    """Build a TibcopBase whose subprocess.run sink is captured, not executed."""
    calls = []

    def fake_run(cmd, *args, **kwargs):
        calls.append({"cmd": cmd, "kwargs": kwargs})
        # list_dataplanes(--json) parses stdout as JSON; return a benign empty list.
        return types.SimpleNamespace(stdout="[]", stderr="", returncode=0)

    monkeypatch.setattr("cli_object.base.subprocess.run", fake_run)
    return TibcopBase(), calls


def _assert_no_shell(call):
    """The core security contract: no OS shell interprets the command."""
    assert call["kwargs"].get("shell") is not True, (
        "subprocess.run still runs with shell=True — an injected shell "
        "metacharacter from a request param would be executed (f023)"
    )
    assert isinstance(call["cmd"], (list, tuple)), (
        "command must be passed as an argv list (shell=False), got "
        f"{type(call['cmd']).__name__}: {call['cmd']!r}"
    )


def test_other_args_is_not_shell_injectable(monkeypatch):
    """A ';touch /tmp/pwned' payload in TIBCOP_CLI_OTHER_ARGS must not reach a shell."""
    base, calls = _capturing_base(monkeypatch)
    dp = TibcopDataPlane(base)

    dp.list_dataplanes(other_args=";touch /tmp/pwned")

    assert calls, "expected the run_command sink to be invoked"
    call = calls[-1]
    _assert_no_shell(call)

    argv = list(call["cmd"])
    assert argv[0] == "tibcop", f"argv[0] should be the tibcop executable: {argv!r}"
    # The payload survives only as inert literal token(s); there is no bare ';'
    # element that a shell would treat as a command separator.
    assert ";" not in argv, f"a bare ';' separator reached argv: {argv!r}"
    # And the payload IS handed to tibcop as inert argument token(s) (not executed).
    assert any("touch" in tok for tok in argv), f"payload should be an inert tibcop arg: {argv!r}"


def test_structured_param_is_not_shell_injectable(monkeypatch):
    """A quote-breakout payload in a structured param (TIBCOP_CLI_DP_NAME) must not reach a shell."""
    base, calls = _capturing_base(monkeypatch)
    dp = TibcopDataPlane(base)

    # is_dataplane_created(dp_name) -> list_dataplanes(--name="<dp_name>" --json)
    dp.is_dataplane_created('x"; touch /tmp/pwned; echo "')

    assert calls, "expected the run_command sink to be invoked"
    call = calls[-1]
    _assert_no_shell(call)
    # The payload is carried as inert argv token(s) handed to tibcop, not shell-parsed.
    assert any("touch" in tok for tok in call["cmd"]), (
        f"payload should survive as an inert tibcop arg token: {call['cmd']!r}"
    )
    assert ";" not in list(call["cmd"]), (
        f"a bare ';' separator reached argv: {call['cmd']!r}"
    )


def test_benign_other_args_still_work(monkeypatch):
    """Backward-compat: legitimate multi-flag other_args round-trip as proper argv tokens."""
    base, calls = _capturing_base(monkeypatch)
    dp = TibcopDataPlane(base)

    dp.list_dataplanes(other_args="--json")

    argv = list(calls[-1]["cmd"])
    assert argv[:2] == ["tibcop", "tplatform:list-dataplanes"], f"unexpected command: {argv!r}"
    assert "--json" in argv, f"benign --json flag was lost: {argv!r}"


def test_node_tls_flag_moved_to_env(monkeypatch):
    """The NODE_TLS_REJECT_UNAUTHORIZED=0 shell prefix must move to the child env,
    not remain as an 'export ... &&' shell string (which forced shell=True)."""
    base, calls = _capturing_base(monkeypatch)
    dp = TibcopDataPlane(base)

    dp.list_dataplanes(other_args="--json")

    call = calls[-1]
    argv = list(call["cmd"])
    assert not any("export" in tok or "&&" in tok for tok in argv), (
        f"shell 'export ... &&' prefix still present in argv: {argv!r}"
    )
    env = call["kwargs"].get("env") or {}
    assert env.get("NODE_TLS_REJECT_UNAUTHORIZED") == "0", (
        "NODE_TLS_REJECT_UNAUTHORIZED=0 must be passed via env now"
    )


def test_unbalanced_quote_returns_none_without_raising(monkeypatch):
    """A lone-quote payload makes shlex.split raise ValueError; run_command must
    preserve the old contract (return None) instead of crashing the worker thread."""
    base, calls = _capturing_base(monkeypatch)
    dp = TibcopDataPlane(base)

    result = dp.list_dataplanes(other_args='"')  # unbalanced quote

    assert result is None, "unparseable command should return None"
    assert not calls, "the sink must not run when the command cannot be tokenized"


def test_run_cli_script_env_blocks_process_control_vars():
    """Vector 2 (env injection): request params cannot inject process/interpreter
    control vars into the child env; /run-cli-script is restricted to TIBCOP_CLI_*."""
    import server

    args = {
        "case": "tplatform:list-dataplanes",
        "TIBCOP_CLI_CPURL": "https://cp",
        "NODE_OPTIONS": "--require /app/upload/evil.js",
        "LD_PRELOAD": "/evil.so",
        "GCONV_PATH": "/app/upload",
        "PATH": "/attacker/bin",
        "PYTHONPATH": "/evil",
        "PYTHONUSERBASE": "/app/upload",
        "HOME": "/app/upload",
        "KUBECONFIG": "/app/upload/evil.yaml",
        "GIT_SSH_COMMAND": "/app/upload/evil.sh",
        "TP_AUTO_FOO": "bar",
    }
    dangerous = ("NODE_OPTIONS", "LD_PRELOAD", "GCONV_PATH", "PATH",
                 "PYTHONPATH", "PYTHONUSERBASE", "HOME",
                 "KUBECONFIG", "GIT_SSH_COMMAND")

    # /run-cli-script path: only TIBCOP_CLI_* request keys reach the tibcop child env.
    env = server.set_env_vars_from_request(
        args, include_system_env=False, allowed_prefixes=("TIBCOP_CLI_",)
    )
    assert env.get("TIBCOP_CLI_CPURL") == "https://cp"
    for k in dangerous + ("TP_AUTO_FOO", "case"):
        assert k not in env, f"{k} must not reach the /run-cli-script child env"

    # Other callers (no allowlist): the global denylist still blocks process-control
    # vars, while legitimate automation vars pass through.
    env2 = server.set_env_vars_from_request(args, include_system_env=False)
    for k in dangerous:
        assert k not in env2, f"{k} must be denylisted for every caller"
    assert env2.get("TP_AUTO_FOO") == "bar"
    assert env2.get("TIBCOP_CLI_CPURL") == "https://cp"


def test_license_upload_curl_is_argv_not_shell(monkeypatch, tmp_path):
    """Sibling sink (B): the license-upload curl must run without a shell so an
    attacker-controlled param cannot break out of quoting.

    cp_url itself is now host-pinned to the tenant CP (TPSEC-166) and an off-host
    value never reaches curl at all — so the argv/no-shell contract is exercised
    here with the still-request-controllable OAuth token (TIBCOP_CLI_OAUTH_TOKEN),
    carried over a legitimate tenant-CP cp_url."""
    from api_object.resources import LicenseApi
    from utils.env import ENV

    # Pin ENV to a known tenant CP host so the cp_url passes the TPSEC-166 gate.
    monkeypatch.setattr(type(ENV), "DP_HOST_PREFIX", "cp-sub1")
    monkeypatch.setattr(type(ENV), "TP_AUTO_CP_SERVICE_DNS_DOMAIN",
                        "cp1-my.localhost.dataplanes.pro")
    cp_url = "https://cp-sub1.cp1-my.localhost.dataplanes.pro"

    lic = tmp_path / "license.bin"
    lic.write_text("x")

    calls = []

    def fake_run(cmd, *args, **kwargs):
        calls.append({"cmd": cmd, "kwargs": kwargs})
        return types.SimpleNamespace(stdout='{"status":"ok"}', stderr="", returncode=0)

    monkeypatch.setattr("api_object.resources.subprocess.run", fake_run)

    malicious_token = "tok'; touch /tmp/pwned; x"
    LicenseApi(cp_url, malicious_token).upload_license_file(str(lic))

    assert calls, "curl sink was not invoked"
    call = calls[-1]
    assert call["kwargs"].get("shell") is not True, "license upload still uses a shell"
    assert isinstance(call["cmd"], (list, tuple)), "curl must be an argv list"
    # The malicious token survives only as one inert argv element (the auth header).
    assert any(malicious_token in tok for tok in call["cmd"]), (
        f"token should be a single inert argv token: {call['cmd']!r}"
    )
    assert ";" not in list(call["cmd"]), (
        f"a bare ';' separator reached argv: {call['cmd']!r}"
    )


def test_boundary_rejects_shell_metacharacters():
    """Second-order defense (register/unregister run tibcop output via a shell): the
    /run-cli-script boundary rejects shell command-substitution / chaining chars."""
    import server

    for payload in ("$(id)", "`id`", "a;id", "a|id", "a&&id", "a<x", "a>x", "a\nid"):
        assert server._has_shell_dangerous_chars(payload), f"{payload!r} must be rejected"
    # Legitimate values (flags, names, FQDNs, versions, quoted multi-word) are allowed.
    for ok in ("my-dp", "--json", "--name=foo", "1.2.3", "cp-sub1.example.com", "a b", 'foo "bar"'):
        assert not server._has_shell_dangerous_chars(ok), f"{ok!r} must be allowed"


def test_k8s_label_validation_for_namespace_and_sa():
    """Namespace / service-account names land in kubectl/helm in the generated script,
    so they must be valid RFC-1123 labels (positive validation, not just metachar reject)."""
    import server

    for good in ("my-dp", "dp1ns", "a", "x-y-z", "cp-sub1sa"):
        assert server._K8S_LABEL_RE.match(good), f"{good!r} should be a valid label"
    for bad in ("My_DP", "dp ns", "-dp", "dp-", "dp$", "UPPER", "a.b", "ns;rm",
                'x" --post-renderer=/app/upload/e.sh "'):  # arg-injection breakout via dp_name
        assert not server._K8S_LABEL_RE.match(bad), f"{bad!r} should be rejected"
