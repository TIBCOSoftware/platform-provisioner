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
# Regression tests for PCP-20999 — deploy-mcp-hub fails at logout (Sign Out click times out).
#
# Root cause (see docs/plan/PCP-20999-plan.md): logout() is the FINAL teardown of ~20 cases,
# run AFTER their real work already succeeded. Post-#372 the gateway-centric deploy ends on the
# gateway detail MFE (/cp/mcphub/gateways/{id}); from there the CP-shell left-nav '.nav-bar-pointer'
# "Sign Out" is present-but-unclickable (a 30s Locator.click timeout). The raw timeout propagated
# out of logout() into the case's except -> Util.exit_error -> sys.exit(1), turning a GREEN deploy
# RED and triggering full re-deploy retries.
#
# The fix makes logout() a ROBUST, NON-FATAL teardown: it re-navigates to the CP entry first (a
# full navigation re-mounts the shell + left-nav and drops any lingering MFE overlay), then clicks
# Sign Out, and WARNS instead of raising/exiting on any failure (logout is teardown — its failure
# must never abort an already-successful run).
#
# MagicMock-page paradigm, following the sibling suites' _make_po() pattern. PageObjectGlobal
# .__init__ only stores the page (no navigation), so PageObjectAuth(MagicMock()) constructs cleanly.

from unittest.mock import MagicMock, patch

from page_object.po_auth import PageObjectAuth
from utils.env import ENV


def _make_po():
    """PageObjectAuth with a MagicMock page. page.wait_for_timeout / goto / locator(...).click are
    no-op MagicMocks; check_dom_visibility / warning_screenshot / exit_error are patched per test."""
    return PageObjectAuth(MagicMock())


def test_logout_is_non_fatal_when_signout_click_times_out():
    """THE PCP-20999 regression: when the left-nav 'Sign Out' is present but its click times out
    (the post-#372 MFE end-state), logout() — a post-success teardown — must WARN, not raise and
    not Util.exit_error. RED before the fix (the raw click timeout propagates out of logout())."""
    po = _make_po()
    # The nav is reported visible, but clicking it times out (the exact reported failure).
    po.page.locator.return_value.click.side_effect = Exception(
        "Locator.click: Timeout 30000ms exceeded.")
    with patch("page_object.po_auth.Util.check_dom_visibility", return_value=True), \
         patch("page_object.po_auth.Util.warning_screenshot") as warn, \
         patch("page_object.po_auth.Util.exit_error",
               side_effect=SystemExit("logout teardown must not exit_error the run")):
        po.logout()  # must NOT raise
    assert warn.called, "a failed logout teardown must surface a loud warning"


def test_logout_renavigates_to_cp_entry_before_signout():
    """Robustness: logout() must re-navigate to the CP entry (so the CP-shell left-nav re-mounts and
    any lingering MFE overlay is dropped) before clicking Sign Out. RED before the fix (logout() did
    no page.goto at all)."""
    po = _make_po()
    with patch("page_object.po_auth.Util.check_dom_visibility", return_value=True), \
         patch("page_object.po_auth.Util.warning_screenshot"), \
         patch("page_object.po_auth.Util.exit_error",
               side_effect=SystemExit("happy-path logout must not exit_error")):
        po.logout()
    goto_targets = [c.args[0] for c in po.page.goto.call_args_list if c.args]
    assert ENV.TP_AUTO_LOGIN_URL in goto_targets, \
        f"logout() must re-nav to the CP entry {ENV.TP_AUTO_LOGIN_URL}; saw {goto_targets}"


def test_logout_happy_path_clicks_signout_and_confirm():
    """No-regression: when the nav is reachable, logout() still clicks the left-nav Sign Out and the
    confirm-dialog Sign Out (.nav-bar-display-block #confirm-button) and emits NO warning."""
    po = _make_po()
    with patch("page_object.po_auth.Util.check_dom_visibility", return_value=True), \
         patch("page_object.po_auth.Util.warning_screenshot") as warn, \
         patch("page_object.po_auth.Util.exit_error",
               side_effect=SystemExit("happy-path logout must not exit_error")):
        po.logout()
    confirm_located = any(
        c.args and ".nav-bar-display-block #confirm-button" in str(c.args[0])
        for c in po.page.locator.call_args_list)
    assert confirm_located, "logout() must locate the confirm-dialog Sign Out button"
    assert po.page.locator.return_value.click.called, "logout() must CLICK Sign Out, not just locate it"
    assert not warn.called, "a clean logout must not emit a warning"


def test_logout_is_non_fatal_when_renav_navigation_fails():
    """The re-nav is INSIDE the non-fatal wrapper: a page.goto failure (e.g. a navigation timeout)
    must also warn, not raise — fully bounding the wrapper. RED before the fix (logout() did no
    page.goto, so the failure never fired and no warning was emitted)."""
    po = _make_po()
    po.page.goto.side_effect = Exception("net::ERR navigation timeout")
    with patch("page_object.po_auth.Util.check_dom_visibility", return_value=True), \
         patch("page_object.po_auth.Util.warning_screenshot") as warn, \
         patch("page_object.po_auth.Util.exit_error",
               side_effect=SystemExit("logout teardown must not exit_error the run")):
        po.logout()  # must NOT raise
    assert warn.called, "a re-nav failure during logout teardown must warn, not raise"
