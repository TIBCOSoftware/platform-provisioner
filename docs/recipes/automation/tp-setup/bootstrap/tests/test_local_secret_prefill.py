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

"""
Regression test for PCP-22623.

TPSEC-124 (f024) hardened /get_env to a non-secret allowlist, which (correctly) stopped
serving Admin Password / User Password / CLI Token to the browser. The fix restores the
pre-fill convenience via a client-side localStorage "Save to Local" path (no server-side
secret exposure). This test drives the real Automation Hub page (Flask served in-process,
no CP / cluster needed) and asserts:

  1. Typing the three secrets + clicking "Save to Local", then reloading, re-populates them
     from localStorage (the UX regression is fixed).
  2. /get_env still does NOT return any of the three secret keys (TPSEC-124 stays intact).

Before the fix, saveGuiSetting/loadGuiSetting and the GUI "Save to Local" button do not
exist, so the reload assertions fail — i.e. this is a true regression test.
"""

import json
import os
import threading
import urllib.request

import pytest
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright

import server as hub_server

# The three secret fields that TPSEC-124 removed from /get_env (PCP-22623).
ADMIN_PASSWORD = "AdminSecret@123"
USER_PASSWORD = "UserSecret@456"
CLI_TOKEN = "cli-oauth-token-abc123"
SECRET_KEYS = ["CP_ADMIN_PASSWORD", "DP_USER_PASSWORD", "TIBCOP_CLI_OAUTH_TOKEN"]


@pytest.fixture(scope="module")
def hub_base_url():
    """Serve the Automation Hub Flask app on an ephemeral local port for the test session."""
    # threaded=True: the browser holds a keep-alive connection for the document, so a
    # single-threaded dev server would block subsequent same-origin requests (/get_env,
    # static assets) and the page's loading overlay would never clear.
    srv = make_server("127.0.0.1", 0, hub_server.app, threaded=True)
    port = srv.server_port
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        srv.shutdown()
        srv.server_close()  # close the listening socket so repeated runs don't leak ports
        thread.join(timeout=5)


@pytest.fixture()
def page():
    """A fresh, isolated browser context/page (own localStorage) per test."""
    headless = os.getenv("HEADLESS", "true").lower() != "false"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        pg = context.new_page()
        try:
            yield pg
        finally:
            context.close()
            browser.close()


def test_secret_fields_prefill_from_local_storage(hub_base_url, page):
    page.goto(hub_base_url)
    # The full-screen ".is_loading" overlay (z-index 9999) intercepts clicks until loadData()
    # resolves and jQuery hides it. Wait for it to clear before interacting.
    page.wait_for_selector(".is_loading", state="hidden")
    page.wait_for_selector("#guiAutoCase", state="visible")

    # Admin Password row is hidden until a case that needs it is selected — mirror real usage.
    page.select_option("#guiAutoCase", "page_auth")
    page.wait_for_selector("#CP_ADMIN_PASSWORD", state="visible")

    # GUI tab: type both passwords, then click the "Save to Local" button in the Admin row.
    page.fill("#CP_ADMIN_PASSWORD", ADMIN_PASSWORD)
    page.fill("#DP_USER_PASSWORD", USER_PASSWORD)
    page.click(".CP_ADMIN_PASSWORD button:has-text('Save to Local')")

    # CLI tab: type the token and save it (existing localStorage path).
    page.click(".tab-button:has-text('CLI Commands')")
    page.wait_for_selector("#TIBCOP_CLI_OAUTH_TOKEN", state="visible")
    page.fill("#TIBCOP_CLI_OAUTH_TOKEN", CLI_TOKEN)
    page.click(".TIBCOP_CLI_OAUTH_TOKEN button:has-text('Save to Local')")

    # Reload: with no secrets in /get_env, the values must come back from localStorage.
    # (The active tab is now #tab2/CLI because we clicked it above; loadCliSetting/loadGuiSetting
    # run synchronously in window.onload, so once the loading overlay clears the values are set
    # regardless of which tab is visible.)
    page.reload()
    page.wait_for_selector(".is_loading", state="hidden")

    # input_value() reads the value even while the field/tab is not currently visible.
    assert page.locator("#CP_ADMIN_PASSWORD").input_value() == ADMIN_PASSWORD
    assert page.locator("#DP_USER_PASSWORD").input_value() == USER_PASSWORD
    assert page.locator("#TIBCOP_CLI_OAUTH_TOKEN").input_value() == CLI_TOKEN


def test_get_env_excludes_secrets(hub_base_url, monkeypatch):
    """Security invariant: TPSEC-124 must stay intact — /get_env returns no secret keys.

    /get_env builds its candidate map from os.environ at request time (server.py:576), so we
    inject all three secrets into the environment first. That makes the assertion a real
    default-deny proof — each key is genuinely present pre-filter and must be dropped by
    GET_ENV_SAFE_KEYS — rather than passing trivially because the key happened to be unset.
    """
    monkeypatch.setenv("CP_ADMIN_PASSWORD", ADMIN_PASSWORD)
    monkeypatch.setenv("DP_USER_PASSWORD", USER_PASSWORD)
    monkeypatch.setenv("TIBCOP_CLI_OAUTH_TOKEN", CLI_TOKEN)
    with urllib.request.urlopen(f"{hub_base_url}/get_env", timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    for key in SECRET_KEYS:
        assert key not in data, f"/get_env unexpectedly exposed secret key {key}"
