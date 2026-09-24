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
# Regression tests for PCP-23839 — the admin bootstrap must be RESUMABLE.
#
# Root cause: `POST /platform-console/api/v1/init` creates the account and is NOT
# idempotent, but the IAT it returns only ever lived in a local variable. A read timeout
# registering the admin OAuth client (CP still warming up) dropped that IAT, and
# `run.sh`'s `run-with-retry deploy-subscription` re-ran the WHOLE step from /init, which
# collided with the account the first attempt had just created — so no retry could ever
# succeed. See CHANGELOG.md for the full incident.
#
# FakeCp reproduces that server behaviour exactly (second /init -> the real ATMOSPHERE-11001
# 400), so `test_whole_step_retry_after_step2_timeout_does_not_repost_init` fails against
# the pre-fix code and passes against the fixed code.

import importlib
import inspect
import json
import re
import shlex

import pytest

from api_object import api_auth
from api_object.api_auth import (
    ADMIN_CLIENT_REGISTER_ATTEMPTS,
    ADMIN_CLIENT_SECRET,
    ADMIN_IAT_SECRET,
    ApiAuth,
    ApiAuthError,
)

HOST_PREFIX_400 = json.dumps({
    "errorCode": "ATMOSPHERE-11001",
    "errorMsg": "Failed to create account with error: "
                "'host_prefix has been used in another account'",
})


# --- fakes -------------------------------------------------------------------------

class _Resp:
    def __init__(self, status_code, payload=None, text=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text if text is not None else json.dumps(payload or {})

    def json(self):
        if self._payload is None:
            raise ValueError("no json body")
        return self._payload


class FakeCp:
    """Emulates the CP endpoints the admin bootstrap touches.

    Crucially it emulates /init's NON-idempotency: the first POST creates the account
    and returns an IAT, every later POST returns the ATMOSPHERE-11001 host_prefix 400.
    """

    def __init__(self, register_outcomes=None):
        self.init_calls = 0
        self.register_calls = 0
        self.revoke_calls = 0
        self.token_calls = 0
        self.timeouts_seen = []
        # each entry: "ok", an Exception instance to raise, or a _Resp to return
        self.register_outcomes = list(register_outcomes or [])

    def post(self, url, **kwargs):
        self.timeouts_seen.append(kwargs.get("timeout"))
        if url.endswith("/platform-console/api/v1/init"):
            self.init_calls += 1
            if self.init_calls > 1:
                return _Resp(400, text=HOST_PREFIX_400)
            return _Resp(200, {"iat": {"accessToken": "IAT-1"}})
        if url.endswith("/idm/v1/oauth2/clients"):
            self.register_calls += 1
            outcome = self.register_outcomes.pop(0) if self.register_outcomes else "ok"
            if isinstance(outcome, Exception):
                raise outcome
            if outcome == "ok":
                return _Resp(200, {"client_id": "cid-1", "client_secret": "csec-1"})
            return outcome
        if url.endswith("/idm/v1/oauth2/token"):
            self.token_calls += 1
            return _Resp(200, {"access_token": "ADMIN-TOKEN"})
        raise AssertionError(f"unexpected POST {url}")

    def delete(self, url, **kwargs):
        self.revoke_calls += 1
        self.timeouts_seen.append(kwargs.get("timeout"))
        return _Resp(200, {})


class FakeSecretStore:
    """A tiny in-memory stand-in for the kubectl secret commands ApiAuth shells out to.

    Deliberately emulates kubectl rather than stubbing ApiAuth's own helpers, so the
    tests prove the fix really persists/reads state across a whole-step rerun.

    `fail_creates_for` reproduces the failure mode that makes an unchecked write
    dangerous: `Helper.get_command_output` catches `subprocess.CalledProcessError` and
    returns `None`, so a `kubectl create secret` that fails (RBAC, quota, apiserver
    hiccup) is SILENT — the secret simply never appears.
    """

    _GET = re.compile(r"kubectl get secret (\S+) .*jsonpath=\"\{\.data\['([^']+)'\]\}\"")
    _DELETE = re.compile(r"kubectl delete secret (\S+) ")
    _CREATE = re.compile(r"kubectl create secret generic (\S+) ")

    @staticmethod
    def _literals(command):
        """Parse --from-literal args the way the shell would, so a value containing a
        quote is read back exactly as kubectl would receive it."""
        out = {}
        for tok in shlex.split(command):
            if tok.startswith("--from-literal="):
                k, _, v = tok[len("--from-literal="):].partition("=")
                out[k] = v
        return out

    def __init__(self, fail_creates_for=()):
        self.data = {}       # {secret_name: {key: value}}
        self.commands = []
        self.fail_creates_for = set(fail_creates_for)

    def run(self, command, *_args, **_kwargs):
        self.commands.append(command)
        m = self._GET.search(command)
        if m:
            return self.data.get(m.group(1), {}).get(m.group(2), "")
        m = self._DELETE.search(command)
        if m:
            self.data.pop(m.group(1), None)
            return ""
        m = self._CREATE.search(command)
        if m:
            if m.group(1) in self.fail_creates_for:
                return None  # what Helper.get_command_output returns on a failed command
            self.data[m.group(1)] = self._literals(command)
            return ""
        return ""  # create namespace, etc.


@pytest.fixture
def cp_env(monkeypatch):
    """Patch the CP HTTP calls, the kubectl secret store and the backoff sleeps."""
    store = FakeSecretStore()
    monkeypatch.setattr(api_auth.Helper, "get_command_output", store.run)
    monkeypatch.setattr(api_auth.time, "sleep", lambda *_: None)

    def install(cp):
        monkeypatch.setattr(api_auth.requests, "post", cp.post)
        monkeypatch.setattr(api_auth.requests, "delete", cp.delete)
        return cp

    return store, install


def _auth():
    return ApiAuth(admin_url="https://admin.cp1-my.localhost.dataplanes.pro",
                   admin_email="cp-test@tibco.com", admin_password="Tibco@123")


# --- the A/B regression: a whole-step retry must not re-POST /init -------------------

def test_whole_step_retry_after_step2_timeout_does_not_repost_init(cp_env):
    """PCP-23839 core: /init succeeds, step 2 exhausts its in-process retries on the
    observed bare TimeoutError, then the OUTER run-with-retry re-runs the whole step.

    The second run must resume from the cached IAT and never touch /init again — the
    pre-fix code re-POSTed it and died on 'host_prefix has been used in another account'.
    """
    store, install = cp_env
    timeouts = [TimeoutError("The read operation timed out")] * ADMIN_CLIENT_REGISTER_ATTEMPTS
    cp = install(FakeCp(register_outcomes=timeouts + ["ok"]))

    # attempt 1 (the run that used to poison every retry)
    with pytest.raises(ApiAuthError):
        _auth().bootstrap_admin()
    assert cp.init_calls == 1
    assert store.data[ADMIN_IAT_SECRET]["iat"] == "IAT-1", "IAT must survive the failure"

    # attempt 2 — a brand new process/object, exactly like the outer whole-step rerun
    token = _auth().bootstrap_admin()

    assert token == "ADMIN-TOKEN"
    assert cp.init_calls == 1, "the non-idempotent /init must NOT be re-POSTed on retry"
    assert store.data[ADMIN_CLIENT_SECRET]["client-id"] == "cid-1"


def test_fake_cp_reproduces_the_host_prefix_400_on_a_second_init(cp_env):
    """Guards the A/B above: prove the fake really is non-idempotent, so a regression
    that re-POSTs /init genuinely fails instead of silently passing."""
    _, install = cp_env
    cp = install(FakeCp())
    cp.post("https://x/platform-console/api/v1/init")
    second = cp.post("https://x/platform-console/api/v1/init")
    assert second.status_code == 400
    assert "host_prefix has been used" in second.text


# --- persistence ordering: state is stored the moment it exists ----------------------

def test_iat_is_persisted_before_step_2_runs(cp_env):
    """The IAT must be in the secret store BEFORE the call that can lose it."""
    store, install = cp_env
    seen = {}
    cp = FakeCp()
    orig_post = cp.post

    def post(url, **kwargs):
        if url.endswith("/idm/v1/oauth2/clients"):
            seen["iat_at_step2"] = store.data.get(ADMIN_IAT_SECRET, {}).get("iat")
        return orig_post(url, **kwargs)

    cp.post = post
    install(cp)

    _auth().bootstrap_admin()
    assert seen["iat_at_step2"] == "IAT-1"


def test_admin_client_is_persisted_before_revoke_and_exchange(cp_env):
    """If the token exchange times out, the retry must still find the cached client and
    take ensure_admin_token()'s fast path instead of re-bootstrapping."""
    store, install = cp_env
    cp = FakeCp()
    seen = {}
    orig_post, orig_delete = cp.post, cp.delete

    def post(url, **kwargs):
        if url.endswith("/idm/v1/oauth2/token"):
            seen["client_at_exchange"] = ADMIN_CLIENT_SECRET in store.data
        return orig_post(url, **kwargs)

    def delete(url, **kwargs):
        seen["client_at_revoke"] = ADMIN_CLIENT_SECRET in store.data
        return orig_delete(url, **kwargs)

    cp.post, cp.delete = post, delete
    install(cp)

    _auth().bootstrap_admin()
    assert seen["client_at_revoke"] is True
    assert seen["client_at_exchange"] is True


def test_cached_iat_is_cleared_once_the_client_is_stored(cp_env):
    """Step 3 revokes the IAT, so leaving it cached would let a later run resume from a
    dead token. A successful bootstrap must end with only the client cached."""
    store, install = cp_env
    install(FakeCp())

    _auth().bootstrap_admin()

    assert ADMIN_IAT_SECRET not in store.data
    assert ADMIN_CLIENT_SECRET in store.data


# --- silent kubectl write failures (cross-review: the riskiest uncovered path) --------

def test_unconfirmed_client_write_keeps_the_iat_and_skips_the_revoke(cp_env):
    """A failed write is SILENT, so an unchecked one destroys both resume paths at once:
    the client never lands, yet the IAT gets revoked and deleted right after. When the
    client cannot be confirmed the IAT must survive AND stay un-revoked (a revoked IAT is
    as dead an end as a deleted one)."""
    store, install = cp_env
    store.fail_creates_for.add(ADMIN_CLIENT_SECRET)
    cp = install(FakeCp())

    token = _auth().bootstrap_admin()

    assert token == "ADMIN-TOKEN", "this attempt itself still succeeds"
    assert store.data[ADMIN_IAT_SECRET]["iat"] == "IAT-1", "the only resume path must survive"
    assert cp.revoke_calls == 0, "revoking would make the surviving IAT useless"

    # ...and the retry really can resume: still exactly one /init across both runs.
    store.fail_creates_for.clear()
    assert _auth().bootstrap_admin() == "ADMIN-TOKEN"
    assert cp.init_calls == 1


def test_a_silent_iat_write_failure_is_reported_but_not_fatal(cp_env):
    """Failing the attempt outright would be worse — it can still succeed end-to-end.
    But the run must say plainly that it is no longer recoverable."""
    store, install = cp_env
    store.fail_creates_for.add(ADMIN_IAT_SECRET)
    install(FakeCp())

    assert _auth().bootstrap_admin() == "ADMIN-TOKEN"
    assert ADMIN_IAT_SECRET not in store.data


def test_secret_writes_are_retried_before_being_declared_failed(cp_env, monkeypatch):
    """A busy cluster fails kubectl the same way it fails HTTP.

    Step 2 is made to fail throughout so the bootstrap aborts there — a SUCCESSFUL
    bootstrap deletes the cached IAT on its way out, which would hide the durable
    outcome this test is about.
    """
    store, install = cp_env
    install(FakeCp(register_outcomes=[TimeoutError("timed out")] * 5))
    store.fail_creates_for.add(ADMIN_IAT_SECRET)
    original_run = store.run
    calls = {"create": 0}

    def flaky(command, *a, **k):
        if "create secret generic" in command and ADMIN_IAT_SECRET in command:
            calls["create"] += 1
            if calls["create"] >= 2:          # recovers on the second attempt
                store.fail_creates_for.discard(ADMIN_IAT_SECRET)
        return original_run(command, *a, **k)

    monkeypatch.setattr(api_auth.Helper, "get_command_output", flaky)

    with pytest.raises(ApiAuthError):
        _auth().bootstrap_admin()

    assert calls["create"] == 2, "the failed write must be retried, not accepted"
    assert store.data[ADMIN_IAT_SECRET]["iat"] == "IAT-1"


def test_secret_values_are_shell_quoted(cp_env):
    """`Helper.get_command_output` runs with shell=True, and admin-url comes from an env
    var, so a value with shell metacharacters must be quoted rather than interpolated."""
    store, install = cp_env
    install(FakeCp())
    nasty = "https://admin.example'; touch /tmp/pwned; echo '"

    auth = ApiAuth(admin_url=nasty, admin_email="a@b.c", admin_password="x")
    assert auth._store_secret("probe", {"iat": "IAT-1", "admin-url": auth.admin_url}) is True

    # Round-trips intact, and the injected command never became its own shell word.
    assert store.data["probe"]["admin-url"] == nasty
    create = [c for c in store.commands if "create secret generic probe" in c][-1]
    assert "touch /tmp/pwned" in create, "sanity: the payload is present as DATA"
    assert "; touch /tmp/pwned;" not in shlex.split(create), "but never as a shell token"


def test_no_secret_writer_interpolates_a_raw_value():
    """Every `--from-literal=` in the module must be shlex-quoted, not `'{v}'`.

    `_store_secret` was quoted first; review then found `_persist_cp_iat`,
    `bootstrap_tenant_token`'s OAuth-client write and its auto-token write still raw. The
    reachable vector is the same one that justified the first fix — `host-prefix` and the
    `subscription-url` fallback derive from `DP_HOST_PREFIX` /
    `TP_AUTO_CP_SERVICE_DNS_DOMAIN`, i.e. environment variables, not CP-issued tokens.
    A file-wide assertion so the next writer cannot quietly reintroduce it.
    """
    src = inspect.getsource(api_auth)
    raw = [line.strip() for line in src.splitlines()
           if "--from-literal=" in line and "shlex.quote" not in line
           and not line.strip().startswith("#")]
    assert not raw, "raw-interpolated secret values:\n  " + "\n  ".join(raw)


def test_every_secret_write_suppresses_command_echo():
    """`Helper.get_command_output` prints the whole failed command, so a create that
    carries a credential must pass is_print_error=False."""
    src = inspect.getsource(api_auth)
    creates = [b for b in src.split("Helper.get_command_output(")[1:]
               if "create secret generic" in b.split(")")[0] + b[:400]]
    missing = [b[:90].replace("\n", " ") for b in creates
               if "create secret generic" in b[:400] and "is_print_error=False" not in b[:400]]
    assert not missing, "secret create without is_print_error=False:\n  " + "\n  ".join(missing)


def test_secret_write_never_puts_the_credential_in_the_error_log(cp_env, monkeypatch):
    """Helper.get_command_output echoes the whole failed command on error, so the create
    must opt out of that printing — otherwise a failed write leaks the raw IAT into the
    pipeline log."""
    store, install = cp_env
    install(FakeCp())
    seen = []

    def record(command, *a, **kwargs):
        seen.append((command, kwargs.get("is_print_error", True)))
        return store.run(command, *a, **kwargs)

    monkeypatch.setattr(api_auth.Helper, "get_command_output", record)

    _auth().bootstrap_admin()

    creates = [(c, p) for c, p in seen if "create secret generic" in c]
    assert creates, "no secret was written"
    assert all(printing is False for _, printing in creates)


# --- cached-client fast path must not manufacture a permanent failure -----------------

def test_a_transient_exchange_failure_does_not_re_run_init(cp_env):
    """_exchange_client_credentials used to raise ApiAuthError for EVERY >=400 and
    ensure_admin_token re-bootstrapped on it, so a momentary 503 sent a perfectly good
    cached client back through /init and turned a blip into an unrecoverable deploy."""
    store, install = cp_env
    store.data[ADMIN_CLIENT_SECRET] = {"client-id": "cid-9", "client-secret": "csec-9"}
    cp = FakeCp()
    cp.post = lambda url, **kw: (
        _Resp(503, text="upstream not ready") if url.endswith("/idm/v1/oauth2/token")
        else FakeCp.post(cp, url, **kw)
    )
    install(cp)

    with pytest.raises(ApiAuthError, match="NOT re-bootstrapping"):
        _auth().ensure_admin_token()

    assert cp.init_calls == 0


def test_a_transport_error_on_exchange_also_does_not_re_run_init(cp_env):
    store, install = cp_env
    store.data[ADMIN_CLIENT_SECRET] = {"client-id": "cid-9", "client-secret": "csec-9"}
    cp = FakeCp()

    def post(url, **kw):
        if url.endswith("/idm/v1/oauth2/token"):
            raise TimeoutError("The read operation timed out")
        return FakeCp.post(cp, url, **kw)

    cp.post = post
    install(cp)

    with pytest.raises(ApiAuthError, match="NOT re-bootstrapping"):
        _auth().ensure_admin_token()
    assert cp.init_calls == 0


def test_a_definitively_rejected_cached_client_still_re_bootstraps(cp_env):
    """401/403 is the one answer that really does prove the credentials are dead, so the
    pre-existing re-bootstrap must be preserved for it."""
    store, install = cp_env
    store.data[ADMIN_CLIENT_SECRET] = {"client-id": "cid-9", "client-secret": "csec-9"}
    cp = FakeCp()
    exchanges = {"n": 0}

    def post(url, **kw):
        if url.endswith("/idm/v1/oauth2/token"):
            exchanges["n"] += 1
            if exchanges["n"] == 1:
                return _Resp(401, text="invalid_client")
        return FakeCp.post(cp, url, **kw)

    cp.post = post
    install(cp)

    assert _auth().ensure_admin_token() == "ADMIN-TOKEN"
    assert cp.init_calls == 1, "a dead client legitimately falls through to a bootstrap"


# --- the cached IAT is scoped to its CP ------------------------------------------------

def test_an_iat_cached_for_a_different_cp_is_ignored(cp_env):
    """A CP reinstalled in this cluster leaves the old secret behind; resuming with an IAT
    from a CP that no longer exists would fail at step 2 with the wrong advice."""
    store, install = cp_env
    store.data[ADMIN_IAT_SECRET] = {"iat": "OLD-IAT", "admin-url": "https://admin.other-cp"}
    cp = install(FakeCp())

    assert _auth().bootstrap_admin() == "ADMIN-TOKEN"
    assert cp.init_calls == 1, "a foreign cached IAT must not suppress /init"
    # The replacement is written scoped to THIS CP. (Asserted on the command rather than
    # the store, because a successful bootstrap deletes the secret on its way out.)
    creates = [c for c in store.commands if f"create secret generic {ADMIN_IAT_SECRET}" in c]
    assert creates
    assert FakeSecretStore._literals(creates[-1])["admin-url"] == \
        "https://admin.cp1-my.localhost.dataplanes.pro"


def test_an_iat_cached_for_this_cp_is_used(cp_env):
    store, install = cp_env
    store.data[ADMIN_IAT_SECRET] = {
        "iat": "IAT-1", "admin-url": "https://admin.cp1-my.localhost.dataplanes.pro",
    }
    cp = install(FakeCp())

    assert _auth().bootstrap_admin() == "ADMIN-TOKEN"
    assert cp.init_calls == 0


# --- step 2 in-process retry ---------------------------------------------------------

def test_step2_retries_in_process_without_a_second_init(cp_env):
    """The transient failure is absorbed where the IAT is still in hand."""
    _, install = cp_env
    cp = install(FakeCp(register_outcomes=[TimeoutError("The read operation timed out"), "ok"]))

    token = _auth().bootstrap_admin()

    assert token == "ADMIN-TOKEN"
    assert cp.register_calls == 2
    assert cp.init_calls == 1


def test_step2_retries_on_5xx_but_not_on_4xx(cp_env):
    """A 5xx is transient; a 4xx (other than the IAT rejection) is a real error and must
    fail fast rather than burn the retry budget."""
    _, install = cp_env

    cp = install(FakeCp(register_outcomes=[_Resp(503, text="upstream not ready"), "ok"]))
    assert _auth().bootstrap_admin() == "ADMIN-TOKEN"
    assert cp.register_calls == 2

    cp = install(FakeCp(register_outcomes=[_Resp(400, text="bad scope")]))
    with pytest.raises(ApiAuthError, match="Step 2 register client failed: 400"):
        _auth().bootstrap_admin()
    assert cp.register_calls == 1


def test_step2_retries_the_conventionally_transient_4xx(cp_env):
    """408/429 are retryable and plausible against a CP that is still warming up."""
    _, install = cp_env
    for status in (408, 429):
        cp = install(FakeCp(register_outcomes=[_Resp(status, text="slow down"), "ok"]))
        assert _auth().bootstrap_admin() == "ADMIN-TOKEN"
        assert cp.register_calls == 2, f"{status} should have been retried"


def test_step2_uses_a_fresh_client_name_per_attempt(cp_env):
    """A read timeout may mean the server DID create the client, so reusing the name
    could collide on a uniqueness constraint on the retry."""
    _, install = cp_env
    cp = FakeCp(register_outcomes=[TimeoutError("timed out"), "ok"])
    names = []
    orig_post = cp.post

    def post(url, **kwargs):
        if url.endswith("/idm/v1/oauth2/clients"):
            names.append(kwargs["data"]["client_name"])
        return orig_post(url, **kwargs)

    cp.post = post
    install(cp)

    _auth().bootstrap_admin()
    assert len(names) == 2
    assert names[0] != names[1]


def test_a_rejected_cached_iat_fails_fast_with_guidance(cp_env):
    """A stale/revoked cached IAT must not be retried, and must not fall back to /init
    (which cannot succeed against the existing account)."""
    store, install = cp_env
    store.data[ADMIN_IAT_SECRET] = {"iat": "STALE"}
    cp = install(FakeCp(register_outcomes=[_Resp(401, text="invalid token")]))

    with pytest.raises(ApiAuthError, match="stale or already"):
        _auth().bootstrap_admin()

    assert cp.register_calls == 1, "a rejected IAT must not be retried"
    assert cp.init_calls == 0, "must not fall back to the non-idempotent /init"


# --- error message -------------------------------------------------------------------

def test_host_prefix_400_message_names_this_cluster_not_another_environment(cp_env):
    """The raw CP wording ('used in another account') sent the original diagnosis down a
    cross-environment path. The message must say it was this run's own account."""
    _, install = cp_env
    cp = install(FakeCp())
    cp.init_calls = 1  # pretend a previous attempt already created the account

    with pytest.raises(ApiAuthError) as exc:
        _auth().bootstrap_admin()

    message = str(exc.value)
    assert "ATMOSPHERE-11001" in message
    assert "THIS cluster" in message
    assert "TP_AUTO_USE_CLI=false" in message


def test_other_init_failures_keep_the_plain_message(cp_env):
    _, install = cp_env
    cp = FakeCp()
    cp.post = lambda url, **kw: _Resp(500, text="gateway exploded")
    install(cp)

    with pytest.raises(ApiAuthError, match="Step 1 /init failed: 500"):
        _auth().bootstrap_admin()


# --- timeout configurability ---------------------------------------------------------

def test_timeout_defaults_to_env():
    # Only the wiring is asserted here. ENV is a frozen dataclass read at import, so the
    # "> 30" claim is pinned in the env-var test below against a controlled default
    # instead of against whatever the ambient shell happens to export.
    assert _auth().timeout == api_auth.ENV.TP_AUTO_API_TIMEOUT


def test_timeout_is_applied_to_every_bootstrap_call(cp_env):
    _, install = cp_env
    cp = install(FakeCp())
    auth = ApiAuth(admin_url="https://admin.example", timeout=77)

    auth.bootstrap_admin()

    assert cp.timeouts_seen, "no HTTP call was made"
    assert set(cp.timeouts_seen) == {77}


def test_api_timeout_is_read_from_the_environment(monkeypatch):
    """TP_AUTO_API_TIMEOUT must actually reach ENV, and its default must beat the old 30s."""
    import utils.env as env_module
    try:
        monkeypatch.setenv("TP_AUTO_API_TIMEOUT", "45")
        assert importlib.reload(env_module).ENV.TP_AUTO_API_TIMEOUT == 45

        monkeypatch.delenv("TP_AUTO_API_TIMEOUT", raising=False)
        default = importlib.reload(env_module).ENV.TP_AUTO_API_TIMEOUT
        assert default == 120
        assert default > 30, "30s while the CP warms up is what PCP-23839 tripped on"
    finally:
        monkeypatch.delenv("TP_AUTO_API_TIMEOUT", raising=False)
        importlib.reload(env_module)


# --- the pre-existing fast path must not regress -------------------------------------

def test_ensure_admin_token_still_short_circuits_on_a_cached_client(cp_env):
    store, install = cp_env
    store.data[ADMIN_CLIENT_SECRET] = {"client-id": "cid-9", "client-secret": "csec-9"}
    cp = install(FakeCp())

    assert _auth().ensure_admin_token() == "ADMIN-TOKEN"

    assert cp.init_calls == 0
    assert cp.register_calls == 0
    assert cp.token_calls == 1
