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
# Regression test for TPSEC-166 — unauthenticated SSRF that leaked the live CP
# cluster-admin bearer token via the request-controlled TIBCOP_CLI_CPURL.
#
# /run-cli-script?case=create-activation-file-resource builds LicenseApi(cp_url, token)
# where cp_url comes from the request param TIBCOP_CLI_CPURL and token is the live
# auto-token. On the vulnerable code upload_license_file ran `curl -sk` against that
# arbitrary cp_url, sending "Authorization: Bearer <token>" to any host with TLS
# verification disabled. The fix pins the cp_url host to the tenant CP (the token is
# only ever sent there) and restores TLS verification (-k only for a self-signed CP).
#
# These tests exercise the real host gate + curl construction, monkeypatching
# subprocess.run so nothing executes. They FAIL on the vulnerable code (which invokes
# the curl sink for an off-host URL, leaking the bearer) and pass after the fix.

import types

import pytest

from api_object.resources import LicenseApi, is_cp_url_allowed, _expected_cp_host
from utils.env import ENV

CP_HOST = "cp-sub1.cp1-my.localhost.dataplanes.pro"


@pytest.fixture
def pinned_cp_host(monkeypatch):
    """Pin ENV to a known tenant CP host so the gate is deterministic off-cluster."""
    # EnvConfig is a frozen dataclass; these are plain (unannotated) CLASS attributes,
    # so patch the class (type(ENV)) — the established pattern in this test suite.
    monkeypatch.setattr(type(ENV), "DP_HOST_PREFIX", "cp-sub1")
    monkeypatch.setattr(type(ENV), "TP_AUTO_CP_SERVICE_DNS_DOMAIN",
                        "cp1-my.localhost.dataplanes.pro")
    monkeypatch.setattr(type(ENV), "TP_IS_CERT_SELF_SIGNED", False)
    assert _expected_cp_host() == CP_HOST
    return CP_HOST


@pytest.fixture
def curl_spy(monkeypatch):
    """Capture (never execute) the curl subprocess.run invocation."""
    calls = []

    def fake_run(cmd, *args, **kwargs):
        calls.append({"cmd": cmd, "kwargs": kwargs})
        return types.SimpleNamespace(stdout='{"status":"ok"}', stderr="", returncode=0)

    monkeypatch.setattr("api_object.resources.subprocess.run", fake_run)
    return calls


@pytest.fixture
def license_file(tmp_path):
    p = tmp_path / "license-file.bin"
    p.write_text("x")
    return str(p)


# --- the credential-leak gate: an off-host cp_url must never reach curl -----------

@pytest.mark.parametrize("evil_url", [
    "https://evil.com",
    "http://evil.com",
    "http://cp-sub1.cp1-my.localhost.dataplanes.pro",            # https-only: cleartext downgrade
    "https://cp-sub1.cp1-my.localhost.dataplanes.pro.evil.com",   # suffix trick
    "https://cp-sub1.cp1-my.localhost.dataplanes.pro@evil.com",   # userinfo trick
    "https://evil.com/cp-sub1.cp1-my.localhost.dataplanes.pro",   # path trick
    "//cp-sub1.cp1-my.localhost.dataplanes.pro",                 # schemeless
    "cp-sub1.cp1-my.localhost.dataplanes.pro",                   # bare host, no scheme
    "file:///etc/passwd",                                         # non-http scheme
    "",                                                            # empty
])
def test_offhost_cp_url_never_sends_bearer(evil_url, pinned_cp_host, curl_spy, license_file):
    result = LicenseApi(evil_url, "SUPER-SECRET-TOKEN").upload_license_file(license_file)
    assert result is None
    assert not curl_spy, (
        f"bearer token would leak: subprocess.run was invoked for off-host cp_url "
        f"{evil_url!r}: {curl_spy!r}"
    )


# --- the legitimate tenant-CP upload still works ---------------------------------

def test_legit_cp_url_uploads_with_bearer(pinned_cp_host, curl_spy, license_file):
    result = LicenseApi(f"https://{CP_HOST}", "TOK").upload_license_file(license_file)
    assert result == {"status": "ok"}
    assert curl_spy, "legit upload should invoke curl"
    argv = list(curl_spy[-1]["cmd"])
    assert argv[0] == "curl"
    # The connection URL is reconstructed from ENV: https + canonical host.
    assert any(tok == f"https://{CP_HOST}/cp/api/v1/subscription/license" for tok in argv), argv
    assert any(tok == "Authorization: Bearer TOK" for tok in argv), argv


def test_connection_url_reconstructed_not_raw_request_string(pinned_cp_host, curl_spy, license_file):
    """Parser-differential guard (TPSEC-166): even when the (host-matching) request
    URL carries an attacker-chosen port / path / trailing slash, the actual curl
    target is rebuilt from ENV — https, canonical host, no port, fixed endpoint."""
    LicenseApi(f"https://{CP_HOST}:8443/ignored/path/", "TOK").upload_license_file(license_file)
    assert curl_spy, "host-matching URL must be allowed"
    argv = list(curl_spy[-1]["cmd"])
    url = argv[argv.index("--url") + 1]
    assert url == f"https://{CP_HOST}/cp/api/v1/subscription/license", url
    assert ":8443" not in url and "/ignored/" not in url, url


# --- TLS verification: -k only for a self-signed CP ------------------------------

def test_tls_verification_on_by_default(pinned_cp_host, curl_spy, license_file):
    LicenseApi(f"https://{CP_HOST}", "TOK").upload_license_file(license_file)
    argv = list(curl_spy[-1]["cmd"])
    assert "-k" not in argv, f"TLS verification must be ON by default (no -k): {argv!r}"
    assert "-sk" not in argv, f"the unconditional -sk must be gone: {argv!r}"


def test_self_signed_cp_keeps_insecure_flag(pinned_cp_host, curl_spy, license_file, monkeypatch):
    monkeypatch.setattr(type(ENV), "TP_IS_CERT_SELF_SIGNED", True)
    LicenseApi(f"https://{CP_HOST}", "TOK").upload_license_file(license_file)
    argv = list(curl_spy[-1]["cmd"])
    assert "-k" in argv, f"a self-signed CP still needs -k (backward compat): {argv!r}"


# --- the pure host predicate -----------------------------------------------------

def test_is_cp_url_allowed_predicate(pinned_cp_host):
    # allowed: https to the tenant CP host (case-insensitive, port/path ignored)
    assert is_cp_url_allowed(f"https://{CP_HOST}")
    assert is_cp_url_allowed(f"https://{CP_HOST}:443/cp")
    assert is_cp_url_allowed(f"https://{CP_HOST.upper()}")     # DNS is case-insensitive
    # rejected: cleartext http (downgrade), off-host, tricks, non-http, schemeless
    assert not is_cp_url_allowed(f"http://{CP_HOST}")          # https-only
    assert not is_cp_url_allowed("https://evil.com")
    assert not is_cp_url_allowed(f"https://{CP_HOST}@evil.com")
    assert not is_cp_url_allowed(f"https://{CP_HOST}.evil.com")
    assert not is_cp_url_allowed(f"https://{CP_HOST}.")        # trailing dot != host
    assert not is_cp_url_allowed(f"//{CP_HOST}")               # schemeless
    assert not is_cp_url_allowed(CP_HOST)                       # bare host, no scheme
    assert not is_cp_url_allowed("file:///etc/passwd")
    assert not is_cp_url_allowed("")
    assert not is_cp_url_allowed(None)
