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
# Regression tests for TPSEC-124 (finding f024): the unauthenticated GET /get_env
# endpoint must NOT disclose secrets. Before the fix it returned the whole process
# environment (os.environ) merged with every EnvConfig attribute plus a freshly
# fetched cluster-admin OAuth bearer token — i.e. CP_ADMIN_PASSWORD, GITHUB_TOKEN,
# TP_AUTO_ELASTIC_PASSWORD, TIBCOP_CLI_OAUTH_TOKEN, and any injected secret env var.
#
# The fix makes /get_env a strict default-deny allowlist of non-secret config. These
# tests pin both halves of the contract: secrets never on the wire (the leak vectors)
# AND legitimate non-secret pre-fill still works (so the fix didn't over-redact). The
# subset-invariant + drift-guard tests keep it refactor-proof (a future secret cannot
# silently re-open the leak).

import re

import server
from server import app, _strip_url_userinfo
from utils.env import ENV
from utils.helper import Helper

# Secret-bearing keys that must never appear in the /get_env response.
SECRET_KEYS = {
    "CP_ADMIN_PASSWORD",
    "DP_USER_PASSWORD",
    "GITHUB_TOKEN",
    "TP_BW5_CHART_REPO_TOKEN",
    "TP_AUTO_K8S_BMDP_BW5_EMS_PASSWORD",
    "TP_AUTO_ELASTIC_PASSWORD",
    "TP_AUTO_PROMETHEUS_PASSWORD",
    "TIBCOP_CLI_OAUTH_TOKEN",
    "TIBCOP_CLI_K8S_SECRET",
    "TP_ACTIVATION_ZIP_FILE_BASE64",
}


# --- leak vectors (RED before the fix) ------------------------------------------------------

def test_get_env_omits_known_secret_keys():
    """/get_env must not carry any secret-bearing key (value-independent check)."""
    resp = app.test_client().get("/get_env")
    assert resp.status_code == 200
    data = resp.get_json()
    leaked = SECRET_KEYS & set(data.keys())
    assert not leaked, f"/get_env leaked secret-bearing keys: {sorted(leaked)}"


def test_get_env_does_not_return_cluster_admin_oauth_token(monkeypatch):
    """The k8s auto-token (cluster-admin bearer) must never be placed on the wire."""
    monkeypatch.setattr(Helper, "get_auto_token", staticmethod(lambda: "SENTINEL-OAUTH-TOKEN"))
    body = app.test_client().get("/get_env").get_data(as_text=True)
    assert "SENTINEL-OAUTH-TOKEN" not in body


def test_get_env_does_not_call_get_auto_token(monkeypatch):
    """/get_env must not even fetch the cluster-admin token (no kubectl shell-out)."""
    calls = []
    monkeypatch.setattr(Helper, "get_auto_token", staticmethod(lambda: calls.append(1) or "x"))
    app.test_client().get("/get_env")
    assert not calls, "/get_env must not call Helper.get_auto_token()"


def test_get_env_does_not_dump_arbitrary_environment(monkeypatch):
    """An arbitrary injected secret env var must not be echoed back by /get_env."""
    monkeypatch.setenv("SOME_INJECTED_SECRET_XYZ", "SENTINEL-ENV-LEAK")
    body = app.test_client().get("/get_env").get_data(as_text=True)
    assert "SENTINEL-ENV-LEAK" not in body


# --- default-deny invariants (refactor-proof: keep the leak from silently re-opening) --------

def test_get_env_returns_only_allowlisted_keys():
    """The response key set must be a SUBSET of the allowlist — the general default-deny property,
    not just the ~10 hand-listed secret keys. Goes RED the instant any code path returns a
    non-allowlisted key (e.g. a reverted `return jsonify(merged)`)."""
    data = app.test_client().get("/get_env").get_json()
    extra = set(data) - server.GET_ENV_SAFE_KEYS
    assert not extra, f"/get_env returned non-allowlisted keys: {sorted(extra)}"


def test_allowlist_excludes_secret_looking_env_attrs():
    """Guard against a FUTURE secret EnvConfig attr being wrongly added to the allowlist."""
    _secret_re = re.compile(r"(PASSWORD|SECRET|_TOKEN|TOKEN$|BASE64|PRIVATE_KEY|API_?KEY)", re.I)
    name_only = {"TP_AUTO_TOKEN_NAME"}  # a secret's *name*, not a secret
    attrs = [k for k in dir(ENV) if not k.startswith("_") and not callable(getattr(ENV, k))]
    offenders = [
        k for k in attrs
        if _secret_re.search(k) and k in server.GET_ENV_SAFE_KEYS and k not in name_only
    ]
    assert not offenders, f"secret-looking EnvConfig attrs in the allowlist: {offenders}"


# --- non-secret pre-fill must still work (guards against over-redaction) ---------------------

def test_get_env_still_returns_non_secret_prefill():
    """Legitimate non-secret config the UI pre-fills must still be returned. TP_AUTO_TOKEN_NAME
    is a k8s secret *name* (not a secret) and is the field a naive TOKEN-substring denylist would
    have wrongly dropped — assert it survives."""
    data = app.test_client().get("/get_env").get_json()
    assert data.get("TP_AUTO_TOKEN_NAME"), "non-secret TP_AUTO_TOKEN_NAME must still pre-fill"
    assert "TP_AUTO_LOGIN_URL" in data and data["TP_AUTO_LOGIN_URL"].startswith("http")


# --- CORS locked (no wildcard) --------------------------------------------------------------

def test_get_env_no_wildcard_cors():
    """Send an Origin so the check is deterministic regardless of flask_cors internals."""
    resp = app.test_client().get("/get_env", headers={"Origin": "https://evil.example"})
    assert resp.headers.get("Access-Control-Allow-Origin") not in ("*", "https://evil.example")


# --- URL fields carry no credentials --------------------------------------------------------

def test_get_env_cpurl_has_no_userinfo():
    """The computed TIBCOP_CLI_CPURL must be scheme://host[:port] only — no user:pass@, no path."""
    data = app.test_client().get("/get_env").get_json()
    cpurl = data.get("TIBCOP_CLI_CPURL", "")
    if cpurl:
        assert "@" not in cpurl, f"TIBCOP_CLI_CPURL leaked userinfo: {cpurl}"
        assert cpurl.count("/") == 2, f"TIBCOP_CLI_CPURL should be scheme://host only: {cpurl}"


def test_get_env_strips_userinfo_from_env_url(monkeypatch):
    """End-to-end: an operator-injected credential-bearing URL is stripped in the response (proves
    the _GET_ENV_URL_KEYS strip loop is wired, not just the helper). TIBCOP_CLI_CPURL is the
    env-injectable URL key (not frozen into EnvConfig)."""
    monkeypatch.setenv("TIBCOP_CLI_CPURL", "https://user:secretpw@cp.example.com/x")
    data = app.test_client().get("/get_env").get_json()
    assert "@" not in data["TIBCOP_CLI_CPURL"]
    assert "secretpw" not in data["TIBCOP_CLI_CPURL"]


def test_strip_url_userinfo():
    assert _strip_url_userinfo("https://u:p@cp.example.com/cp/login") == "https://cp.example.com/cp/login"
    assert _strip_url_userinfo("https://u:p@cp.example.com:8443/a") == "https://cp.example.com:8443/a"
    assert _strip_url_userinfo("https://cp.example.com/cp/login") == "https://cp.example.com/cp/login"
    # scheme-relative userinfo is also stripped (was an early-return bypass before the fix)
    assert _strip_url_userinfo("//u:p@cp.example.com/a") == "//cp.example.com/a"
    # IPv6 host brackets preserved, userinfo removed, malformed port does not raise
    assert _strip_url_userinfo("https://u:p@[::1]:8443/a") == "https://[::1]:8443/a"
    assert _strip_url_userinfo("https://u:p@host:notaport/a") == "https://host:notaport/a"
    # passthrough for non-URLs / empties / non-str
    assert _strip_url_userinfo("not-a-url") == "not-a-url"
    assert _strip_url_userinfo("") == ""
    assert _strip_url_userinfo(None) is None


# --- DEV opt-in flag TP_AUTO_GET_ENV_EXPOSE_SECRETS -----------------------------------------
# Default OFF keeps the TPSEC-124 default-deny; only an explicit opt-in on a trusted dev
# instance serves the Admin/User Password + CLI Token so the UI fields pre-fill on load.

def test_get_env_secrets_hidden_without_flag(monkeypatch):
    """Even with the secret values present in the environment, the default (flag unset) response
    must NOT include them — the TPSEC-124 default-deny holds unless explicitly opted in."""
    monkeypatch.delenv("TP_AUTO_GET_ENV_EXPOSE_SECRETS", raising=False)
    monkeypatch.setenv("CP_ADMIN_PASSWORD", "Tibco@123")
    monkeypatch.setenv("DP_USER_PASSWORD", "Tibco@123")
    monkeypatch.setenv("TIBCOP_CLI_OAUTH_TOKEN", "dev-token-xyz")
    data = app.test_client().get("/get_env").get_json()
    for key in ("CP_ADMIN_PASSWORD", "DP_USER_PASSWORD", "TIBCOP_CLI_OAUTH_TOKEN"):
        assert key not in data, f"/get_env leaked {key} with the opt-in flag OFF"


def test_get_env_flag_false_still_hidden(monkeypatch):
    """An explicit non-true value is treated as OFF (only the literal 'true' opts in)."""
    monkeypatch.setenv("TP_AUTO_GET_ENV_EXPOSE_SECRETS", "false")
    monkeypatch.setenv("CP_ADMIN_PASSWORD", "Tibco@123")
    data = app.test_client().get("/get_env").get_json()
    assert "CP_ADMIN_PASSWORD" not in data


def test_get_env_exposes_secrets_when_flag_on(monkeypatch):
    """With the opt-in flag ON, /get_env serves the Admin/User Password + CLI Token.

    Admin/User Password are EnvConfig attributes, so env_dict wins the {**env_vars, **env_dict}
    merge and they are served as their ENV values (default 'Tibco@123', or whatever the
    deployment set at import time). The CLI token is NOT an EnvConfig attribute, so the
    request-time env value survives the merge and is served verbatim.
    """
    monkeypatch.setenv("TP_AUTO_GET_ENV_EXPOSE_SECRETS", "true")
    monkeypatch.setenv("TIBCOP_CLI_OAUTH_TOKEN", "cli-oauth-token-abc")
    data = app.test_client().get("/get_env").get_json()
    assert ENV.CP_ADMIN_PASSWORD and ENV.DP_USER_PASSWORD  # non-empty → actually served below
    assert data.get("CP_ADMIN_PASSWORD") == ENV.CP_ADMIN_PASSWORD
    assert data.get("DP_USER_PASSWORD") == ENV.DP_USER_PASSWORD
    assert data.get("TIBCOP_CLI_OAUTH_TOKEN") == "cli-oauth-token-abc"


def test_get_env_flag_on_refetches_token(monkeypatch):
    """When the flag is ON and the token is not already in the env, it is re-fetched on demand
    via Helper.get_auto_token() (the fetch TPSEC-124 removed, re-enabled only under the flag)."""
    monkeypatch.setenv("TP_AUTO_GET_ENV_EXPOSE_SECRETS", "true")
    monkeypatch.delenv("TIBCOP_CLI_OAUTH_TOKEN", raising=False)
    monkeypatch.setattr(server.Helper, "get_auto_token", staticmethod(lambda: "fetched-token-999"))
    data = app.test_client().get("/get_env").get_json()
    assert data.get("TIBCOP_CLI_OAUTH_TOKEN") == "fetched-token-999"


def test_get_env_flag_truthy_non_true_still_hidden(monkeypatch):
    """Fail-closed parsing: only the literal 'true' opts in. A truthy-looking-but-not-'true'
    value an operator might fat-finger ('1', 'yes', 'on') must still hide the secrets."""
    # Note: case/whitespace-insensitive "true" (e.g. "TRUE ", "True") DOES opt in by design;
    # these are the truthy-LOOKING-but-not-"true" tokens that must stay fail-closed.
    monkeypatch.setenv("CP_ADMIN_PASSWORD", "Tibco@123")
    for val in ("1", "yes", "on", "enabled", "y"):
        monkeypatch.setenv("TP_AUTO_GET_ENV_EXPOSE_SECRETS", val)
        data = app.test_client().get("/get_env").get_json()
        assert "CP_ADMIN_PASSWORD" not in data, f"value {val!r} unexpectedly opted in"


def test_get_env_request_arg_cannot_flip_flag(monkeypatch):
    """The gate reads os.environ, which a request never mutates. A query arg of the flag name
    must NOT enable exposure when the real env flag is unset (locks syan's crux-2 property)."""
    monkeypatch.delenv("TP_AUTO_GET_ENV_EXPOSE_SECRETS", raising=False)
    monkeypatch.setenv("CP_ADMIN_PASSWORD", "Tibco@123")
    data = app.test_client().get("/get_env?TP_AUTO_GET_ENV_EXPOSE_SECRETS=true").get_json()
    for key in ("CP_ADMIN_PASSWORD", "DP_USER_PASSWORD", "TIBCOP_CLI_OAUTH_TOKEN"):
        assert key not in data, f"request arg flipped the flag and leaked {key}"
