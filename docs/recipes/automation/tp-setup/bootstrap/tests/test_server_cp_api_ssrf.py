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
# Regression tests for the /cp_api host-suffix / userinfo SSRF guard (TPSEC-116 / f027).
#
# /cp_api concatenates the request-supplied `api_path` onto base_url (a bare CP host with
# no trailing slash) and curls the result with a LIVE CP bearer token. An api_path that
# does not start with a single "/" can rewrite the URL authority and exfiltrate the token
# to an attacker host. These tests assert that such inputs are rejected with 400 BEFORE
# any curl runs (the token never leaves), while a legitimate absolute path still works.

from unittest.mock import MagicMock, patch

import pytest

import server as srv
from utils.env import ENV


@pytest.fixture
def client():
    srv.app.config["TESTING"] = True
    with srv.app.test_client() as c:
        yield c


def _base_url():
    return f"https://{ENV.DP_HOST_PREFIX}.{ENV.TP_AUTO_CP_SERVICE_DNS_DOMAIN}"


# api_path values that must be rejected because they rewrite the URL authority (or are
# otherwise not a safe absolute path). None of these may ever reach curl.
MALICIOUS_API_PATHS = [
    "@evil.com/x",                 # userinfo: base host becomes credentials, authority = evil.com
    ".evil.com/x",                 # host suffix: authority = <cp-host>.evil.com
    "@evil.com",                   # userinfo, no path
    "//evil.com/x",               # protocol-relative authority
    "https://evil.com/x",          # absolute URL, does not start with "/"
    "evil.com/x",                  # relative, no leading slash
    "",                            # empty -> caught by the earlier "Missing" branch (also 400, no curl)
]


@pytest.mark.parametrize("api_path", MALICIOUS_API_PATHS)
def test_cp_api_rejects_authority_rewrite_without_curl(client, api_path):
    """Malicious api_path -> 400, and subprocess.Popen (curl) is NEVER invoked."""
    with patch.object(srv, "subprocess") as mock_subprocess, \
            patch.object(srv.Helper, "get_auto_token", return_value="SECRET-CP-TOKEN") as mock_token:
        resp = client.get("/cp_api", query_string={"api_path": api_path})

    assert resp.status_code == 400, f"expected 400 for api_path={api_path!r}, got {resp.status_code}"
    # The security-critical assertions: curl never ran AND the token was never even
    # fetched (the requirement is "reject with 400 before the CP bearer is read").
    mock_subprocess.Popen.assert_not_called()
    mock_token.assert_not_called()


def test_cp_api_allows_absolute_path_and_keeps_cp_host(client):
    """A legitimate absolute api_path is proxied to the CP host with the bearer token."""
    fake_proc = MagicMock()
    fake_proc.communicate.return_value = (b'{"ok": true}', b"")

    with patch.object(srv.subprocess, "Popen", return_value=fake_proc) as mock_popen, \
            patch.object(srv.Helper, "get_auto_token", return_value="SECRET-CP-TOKEN"):
        resp = client.get("/cp_api", query_string={"api_path": "/tibco/v1/dataplanes"})

    assert resp.status_code == 200
    mock_popen.assert_called_once()
    curl_cmd = mock_popen.call_args[0][0]
    expected_url = _base_url() + "/tibco/v1/dataplanes"
    # The composed URL targets the CP host (authority unchanged) ...
    assert expected_url in curl_cmd
    # ... and carries the bearer token (only ever to the CP host).
    assert any(str(arg).startswith("Authorization: Bearer ") for arg in curl_cmd)


# Legitimate absolute paths that contain "tricky" bytes but must STILL be proxied to the
# CP host — every attacker-controlled byte lands after the leading "/", so the authority
# stays the CP host. These lock in the host-pinning invariant and guard against a future
# over-tightening (e.g. naively rejecting any "@") that would break real CP paths.
LEGIT_TRICKY_API_PATHS = [
    "/tibco/v1/resources/foo@bar",   # "@" inside the path is legal, not userinfo
    "/tibco/v1/dataplanes?scope=all",  # query string ("?" terminates the netloc, not "/")
    "/\\evil.com",                    # backslash stays in the path (not an authority sep)
    "/%2F%2Fevil.com",               # encoded slashes stay in the path
    "/../secret",                    # dot-segment: same host, path namespace only
]


@pytest.mark.parametrize("api_path", LEGIT_TRICKY_API_PATHS)
def test_cp_api_tricky_but_legit_paths_stay_on_cp_host(client, api_path):
    """A leading-single-slash path with tricky bytes is proxied to the CP host unchanged."""
    fake_proc = MagicMock()
    fake_proc.communicate.return_value = (b'{"ok": true}', b"")

    with patch.object(srv.subprocess, "Popen", return_value=fake_proc) as mock_popen, \
            patch.object(srv.Helper, "get_auto_token", return_value="SECRET-CP-TOKEN"):
        resp = client.get("/cp_api", query_string={"api_path": api_path})

    assert resp.status_code == 200
    mock_popen.assert_called_once()
    curl_cmd = mock_popen.call_args[0][0]
    # The URL curl is asked to dial must still target the CP host (authority not rewritten).
    url_arg = next(a for a in curl_cmd if str(a).startswith("https://"))
    from urllib.parse import urlsplit
    assert urlsplit(url_arg).netloc == urlsplit(_base_url()).netloc


def test_cp_api_missing_param_is_400(client):
    """No api_path at all -> 400, no curl."""
    with patch.object(srv, "subprocess") as mock_subprocess, \
            patch.object(srv.Helper, "get_auto_token", return_value="SECRET-CP-TOKEN") as mock_token:
        resp = client.get("/cp_api")

    assert resp.status_code == 400
    mock_subprocess.Popen.assert_not_called()
    mock_token.assert_not_called()
