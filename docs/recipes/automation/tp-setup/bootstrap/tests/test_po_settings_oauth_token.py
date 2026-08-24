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
# Regression tests for PCP-20425 — the "Create OAuth Token (Config MCP Server)"
# case crashing with an opaque `Locator.wait_for: Timeout 30000ms exceeded`.
#
# Two real bugs, both introduced by the PCP-16529 OAuth token table redesign
# (which added a checkbox column + a token-type column):
#
#   Bug A (root cause): the existence check matched the token name with
#     `td:first-child`, but the name moved to the 3rd <td>, so the row was never
#     found. An already-existing auto-token was misread as "does not exist", the
#     UI delete was skipped, and a DUPLICATE-named token was generated -> the CP
#     rejected it ("Invalid request: Duplicate AccessToken name.") -> the success
#     modal never rendered. These tests pin that the row selector now keys on the
#     version-stable `#token-name-` id (present in BOTH the old and new layouts)
#     and never on `td:first-child`.
#
#   Bug B (diagnosability): generation result was awaited with a bare
#     `wait_for(#copy-oauth2-token-btn)`, so any backend rejection became an
#     opaque 30s timeout with no error text. `_wait_for_generate_result` now
#     detects success vs the error notification vs timeout. These tests pin all
#     three branches.

import base64
import json
import re
from unittest.mock import MagicMock, patch

from page_object.po_settings import PageObjectSettings

TOKEN_NAME = "auto-token"


def _make_po():
    """Build PageObjectSettings without __init__ (which only stores the page)."""
    po = PageObjectSettings.__new__(PageObjectSettings)
    po.page = MagicMock()
    return po


# --- Bug A: row-existence selector ------------------------------------------------

def test_token_row_locator_keys_on_token_name_id_not_first_child():
    po = _make_po()
    po._token_row_locator(TOKEN_NAME)

    selectors = [c.args[0] for c in po.page.locator.call_args_list if c.args]
    # Outer row selector + inner name-cell selector.
    assert "oauth-token table tr" in selectors
    assert "[id^='token-name-']" in selectors
    # The redesign-broken selector must be gone for good.
    assert not any("td:first-child" in s for s in selectors), \
        f"td:first-child must not be used any more; got {selectors}"


def test_token_row_locator_matches_name_exactly():
    """The name cell is matched with an anchored regex so 'auto-token' does not
    also match e.g. 'auto-token-2'."""
    po = _make_po()
    po._token_row_locator(TOKEN_NAME)

    name_calls = [c for c in po.page.locator.call_args_list
                  if c.args and c.args[0] == "[id^='token-name-']"]
    assert name_calls, "expected a #token-name- locator call"
    has_text = name_calls[0].kwargs.get("has_text")
    assert isinstance(has_text, re.Pattern)
    assert has_text.match(TOKEN_NAME)
    assert not has_text.match(TOKEN_NAME + "-2")


# --- Bug B: generate-result detection --------------------------------------------

def _loc(visible=False, count=0, text=""):
    m = MagicMock()
    m.is_visible.return_value = visible
    m.count.return_value = count
    m.first.is_visible.return_value = visible
    m.first.text_content.return_value = text
    return m


def test_wait_returns_success_when_result_modal_visible():
    po = _make_po()
    with patch("page_object.po_settings.Util.check_dom_visibility", return_value=True), \
         patch.object(po, "_result_dialog_locator", return_value=_loc(visible=True)), \
         patch.object(po, "_error_notification_locator", return_value=_loc()):
        status, message = po._wait_for_generate_result()
    assert status == "success"
    assert message is None


def test_wait_returns_error_with_message_from_notification():
    po = _make_po()
    err = _loc(visible=True, count=1, text="Invalid request: Duplicate AccessToken name.")
    with patch("page_object.po_settings.Util.check_dom_visibility", return_value=True), \
         patch.object(po, "_result_dialog_locator", return_value=_loc(visible=False)), \
         patch.object(po, "_error_notification_locator", return_value=err):
        status, message = po._wait_for_generate_result()
    assert status == "error"
    assert message == "Invalid request: Duplicate AccessToken name."


def test_wait_error_with_none_text_content_does_not_crash():
    """text_content() returning None must not crash .strip() (which would re-mask
    the backend error); it is coerced to an empty string."""
    po = _make_po()
    err = _loc(visible=True, count=1, text=None)
    with patch("page_object.po_settings.Util.check_dom_visibility", return_value=True), \
         patch.object(po, "_result_dialog_locator", return_value=_loc(visible=False)), \
         patch.object(po, "_error_notification_locator", return_value=err):
        status, message = po._wait_for_generate_result()
    assert status == "error"
    assert message == ""


def test_wait_returns_timeout_when_dom_never_appears():
    """check_dom_visibility times out (False) -> timeout, no error read."""
    po = _make_po()
    with patch("page_object.po_settings.Util.check_dom_visibility", return_value=False) as cdv, \
         patch.object(po, "_result_dialog_locator", return_value=_loc(visible=False)), \
         patch.object(po, "_error_notification_locator", return_value=_loc(count=0)):
        status, message = po._wait_for_generate_result()
    assert status == "timeout"
    assert message is None
    assert cdv.called


def test_wait_success_wins_over_coexisting_error_toast():
    """When both the success modal and an error toast are present, success wins
    (discrimination checks the result modal first)."""
    po = _make_po()
    err = _loc(visible=True, count=1, text="some stale error")
    with patch("page_object.po_settings.Util.check_dom_visibility", return_value=True), \
         patch.object(po, "_result_dialog_locator", return_value=_loc(visible=True)), \
         patch.object(po, "_error_notification_locator", return_value=err):
        status, message = po._wait_for_generate_result()
    assert status == "success"
    assert message is None


def test_wait_delegates_to_check_dom_visibility_with_combined_first_locator():
    """The wait reuses Util.check_dom_visibility (project polling convention) with
    the success-OR-error combined locator narrowed by .first (a bare .or_() would
    raise a strict-mode violation when both appear at once)."""
    po = _make_po()
    succ = _loc(visible=False)
    err = _loc(count=0)
    with patch("page_object.po_settings.Util.check_dom_visibility", return_value=False) as cdv, \
         patch.object(po, "_result_dialog_locator", return_value=succ), \
         patch.object(po, "_error_notification_locator", return_value=err):
        po._wait_for_generate_result(interval=3, max_wait=24)
    cdv.assert_called_once()
    args = cdv.call_args.args
    # signature: check_dom_visibility(page, locator, interval, max_wait)
    assert args[0] is po.page
    assert args[2] == 3 and args[3] == 24
    # the locator passed is _result_dialog_locator().or_(_error_notification_locator()).first
    succ.or_.assert_called_once_with(err)
    assert args[1] is succ.or_.return_value.first


# === PCP-21482: reveal race — never store the masked "********" placeholder ==========
#
# Clicking "View" flips isTokenVisible, which the cp/web-ui template renders via *ngIf
# (masked "********" span -> real-token span). Under Angular 21 (base 1.19.0-alpha.160+)
# that DOM swap is async, so reading .value immediately returns "********". The old code
# read straight after the click and its `if not token_value` guard let the non-empty
# "********" through -> it was stored in the auto-token secret -> every downstream CLI/API
# call 401'd (and provision-tenant's token-fetch got a 12-byte body). The fix waits for
# #hide-token-btn (rendered only once isTokenVisible=true) before reading, and rejects
# "********" as well as empty.


def _drive_set_oauth_token(revealed_value, hide_visible=True):
    """Run set_oauth_token() with every external mocked, controlling the revealed
    .value text and whether #hide-token-btn appeared. Returns (po, util_mock, calls)
    where calls records ReportYaml.set args and Helper shell commands."""
    po = _make_po()
    calls = {"report": [], "cmds": []}
    # The token read is page.locator(..).locator(".value").text_content().strip();
    # drive the innermost text_content to the value under test.
    po.page.locator.return_value.locator.return_value.text_content.return_value = revealed_value
    with patch("page_object.po_settings.Util") as util, \
         patch("page_object.po_settings.Helper") as helper, \
         patch("page_object.po_settings.ReportYaml") as report, \
         patch.object(po, "_token_row_locator", return_value=_loc(visible=False)), \
         patch.object(po, "delete_oauth_token"), \
         patch.object(po, "_wait_for_generate_result", return_value=("success", None)), \
         patch.object(po, "_result_dialog_locator", return_value=MagicMock()), \
         patch.object(po, "print_oauth_token_info"), \
         patch.object(po, "is_created_oauth_token", return_value=True):
        util.check_dom_visibility.return_value = hide_visible
        report.set.side_effect = lambda *a, **k: calls["report"].append(a)
        helper.get_command_output.side_effect = lambda *a, **k: calls["cmds"].append(a[0] if a else "")
        po.set_oauth_token()
    return po, util, calls


def test_masked_token_is_rejected_and_not_stored():
    """Reveal never completed (#hide-token-btn absent) and .value is still '********'
    -> report failure, and NEVER create the auto-token secret with the masked value."""
    po, util, calls = _drive_set_oauth_token("********", hide_visible=False)
    assert (".ENV.REPORT_OAUTH_TOKEN", False) in calls["report"]
    assert (".ENV.REPORT_OAUTH_TOKEN", True) not in calls["report"]
    assert not any("create secret" in c for c in calls["cmds"]), \
        f"masked '********' must never be stored; cmds={calls['cmds']}"
    # it warned about the failed reveal
    assert util.warning_screenshot.called


def test_masked_rejected_even_if_reveal_flag_flipped():
    """Even if #hide-token-btn appeared, a '********' read must still be rejected (the
    guard keys on the value, not only on the reveal wait)."""
    po, util, calls = _drive_set_oauth_token("********", hide_visible=True)
    assert (".ENV.REPORT_OAUTH_TOKEN", False) in calls["report"]
    assert not any("create secret" in c for c in calls["cmds"])


def test_real_token_is_stored_with_actual_value():
    """A real revealed token is stored verbatim in the secret (never '********')."""
    real = "CIC~SYNTHETIC-fake-token-for-tests-only"  # not a real credential
    po, util, calls = _drive_set_oauth_token(real, hide_visible=True)
    assert (".ENV.REPORT_OAUTH_TOKEN", True) in calls["report"]
    create = [c for c in calls["cmds"] if "create secret generic" in c]
    assert create, "expected a kubectl create secret command for the real token"
    assert real in create[0]
    assert "********" not in create[0]


def test_waits_for_hide_token_btn_before_reading():
    """The read is gated on #hide-token-btn visibility (the 'real token now shown'
    signal), via the project's Util.check_dom_visibility polling convention."""
    po, util, calls = _drive_set_oauth_token("CIC~real-token-000000000000", hide_visible=True)
    assert any(c.args and c.args[0] == "#hide-token-btn"
               for c in po.page.locator.call_args_list), \
        "the reveal wait must target #hide-token-btn"
    assert util.check_dom_visibility.called


# --- get_oauth_token: a previously-poisoned '********' secret must self-heal --------
# The idempotent early-exit in set_oauth_token reuses get_oauth_token()'s value when a
# token already exists. If an earlier run stored the masked '********' (the pre-fix
# bug), get_oauth_token must NOT return it as valid — else the poison persists forever
# and the reveal-race fix (in the generate path) is never reached. So '********' is
# treated like empty: delete the secret + return False -> set_oauth_token regenerates.


def _secret_json(token_value):
    b64 = base64.b64encode(token_value.encode()).decode()
    return json.dumps({"data": {"auto-token": b64}})


def test_get_oauth_token_rejects_masked_placeholder():
    po = _make_po()
    with patch("page_object.po_settings.Helper") as helper, \
         patch.object(po, "delete_oauth_token") as dele:
        helper.get_command_output.return_value = _secret_json("********")
        result = po.get_oauth_token()
    assert result is False
    assert dele.called  # poisoned secret deleted so it regenerates


def test_get_oauth_token_returns_real_value():
    po = _make_po()
    with patch("page_object.po_settings.Helper") as helper, \
         patch.object(po, "delete_oauth_token") as dele:
        helper.get_command_output.return_value = _secret_json("CIC~real-token-abc")
        result = po.get_oauth_token()
    assert result == "CIC~real-token-abc"
    assert not dele.called
