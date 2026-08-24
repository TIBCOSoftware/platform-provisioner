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
# Tests for _diff_confirm_push — the deploy-mcp-hub push-to-gateway diff-confirm selector.
#
# PCP-22620: flipped to test-id-FIRST. PCP-22619 re-added the stable `dp-action-diff-push`
# hook on the PushFlowDialog (Fresco alpha.87 test-id passthrough / PLTUX-1299), so the
# automation now prefers it and falls back to the 'Push to Gateway' label by role+name only
# for older Hub builds (supersedes the earlier PCP-20368 role+name-first adaptation).
#
# The role+name FALLBACK stays dialog-scoped: the button renders in the dialog FOOTER
# (.p-dialog-footer) — outside the 'dp-action-diff-preview' content div — so it is scoped to
# the role=dialog that CONTAINS that content marker (filter has=...), which also keeps it from
# colliding with the gateway-detail 'Push Changes to Gateway' button.
#
# These tests pin the parts most likely to silently rot — pure logic (MagicMock, zero
# browser); the live-DOM behavior is proven by e2e (a selector match against a real ::before
# glyph cannot be unit-tested honestly):
#   * the ORDERING: test-id (dp-action-diff-push) -> role+name -> test-id when neither visible;
#   * the selectors actually used (test-id first; the fallback's dialog filtered by the content
#     marker + role=button);
#   * the regex SEMANTICS: unanchored (tolerates the pi-cloud-upload ::before glyph that folds
#     into the accessible name) yet does NOT collide with "Push Changes to Gateway".

from unittest.mock import MagicMock, patch

from page_object.po_mcp_hub import PageObjectMcpHub

# The PrimeReact 'pi pi-cloud-upload' icon renders as a ::before glyph in the PUA
# block (U+E944) that Playwright folds into the button's accessible name *before*
# the label — the live-DOM fact (alpha.113) the unanchored regex must tolerate.
GLYPH_NAME = chr(0xE944) + "Push to Gateway"


def _make_po():
    """Build a PageObjectMcpHub without running __init__ (which needs a real
    Playwright page). Inject a MagicMock page; install distinct sentinels for the
    role-based ('role_loc') and test-id ('test_id_loc') locators so the test can
    assert which one the helper returns.

    Helper locator chain (PCP-22620, test-id first):
      page.get_by_test_id("dp-action-diff-push").first                         (preferred)
      page.get_by_role("dialog").filter(has=...).get_by_role("button", ...).first  (fallback)
    """
    po = PageObjectMcpHub.__new__(PageObjectMcpHub)
    po.page = MagicMock()
    po.gateway_id = None
    role_loc = MagicMock(name="role-locator")     # dialog.filter(...).get_by_role("button", ...).first
    test_id_loc = MagicMock(name="test-id")        # get_by_test_id("dp-action-diff-push").first
    po.page.get_by_role.return_value.filter.return_value.get_by_role.return_value.first = role_loc
    po.page.get_by_test_id.return_value.first = test_id_loc
    return po, role_loc, test_id_loc


def _testid_calls(po):
    """The positional testid names get_by_test_id was called with, in order."""
    return [c.args[0] for c in po.page.get_by_test_id.call_args_list if c.args]


def test_returns_test_id_when_visible():
    """PCP-22620: dp-action-diff-push visible -> return it; the role+name fallback (and its
    dialog scope) is never even built."""
    po, _role, test_id_loc = _make_po()
    with patch("page_object.po_mcp_hub.Util.check_dom_visibility", side_effect=[True]):
        result = po._diff_confirm_push()
    assert result is test_id_loc
    assert "dp-action-diff-push" in _testid_calls(po)
    # test-id hit first -> the fallback dialog (role=dialog) + content marker are never queried.
    po.page.get_by_role.assert_not_called()
    assert "dp-action-diff-preview" not in _testid_calls(po)


def test_falls_back_to_role_when_test_id_absent():
    """test-id absent + role locator visible -> return the dialog-scoped role+name button."""
    po, role_loc, _test_id = _make_po()
    with patch("page_object.po_mcp_hub.Util.check_dom_visibility", side_effect=[False, True]):
        result = po._diff_confirm_push()
    assert result is role_loc
    po.page.get_by_test_id.assert_any_call("dp-action-diff-push")


def test_returns_test_id_when_both_invisible_for_caller_to_guard():
    """Neither visible -> return the durable test-id locator (a current Hub renders the
    test-id) so the caller's check_dom_visibility guard fires with a screenshot, instead of
    polling a "Push to Gateway" label a current Hub no longer relies on."""
    po, _role, test_id_loc = _make_po()
    with patch("page_object.po_mcp_hub.Util.check_dom_visibility", side_effect=[False, False]):
        result = po._diff_confirm_push()
    assert result is test_id_loc


def test_fallback_scopes_to_dialog_filtered_by_content_marker_then_button():
    """The role+name FALLBACK scopes role=button under the role=dialog that CONTAINS the
    'dp-action-diff-preview' content marker (the button is in the dialog footer, outside that
    content div)."""
    po, _role, _test_id = _make_po()
    # test-id not visible -> the fallback dialog+role path builds.
    with patch("page_object.po_mcp_hub.Util.check_dom_visibility", side_effect=[False, True]):
        po._diff_confirm_push()
    # outer: get_by_role("dialog")  (no header-text dependency)
    assert po.page.get_by_role.call_args.args[0] == "dialog"
    # the dialog is filtered by the proven content marker, passed AS has= (not has_text)
    po.page.get_by_role.return_value.filter.assert_called_once()
    assert "dp-action-diff-preview" in _testid_calls(po)
    assert (po.page.get_by_role.return_value.filter.call_args.kwargs["has"]
            is po.page.get_by_test_id.return_value)
    # inner: .get_by_role("button", name=<regex mentioning the label>)
    inner = po.page.get_by_role.return_value.filter.return_value.get_by_role.call_args
    assert inner.args[0] == "button"
    assert "Push to Gateway" in inner.kwargs["name"].pattern


def test_fallback_button_regex_is_glyph_tolerant_and_non_colliding():
    """The fallback button regex must be UNANCHORED (tolerate the pi-cloud-upload ::before
    glyph that folds into the accessible name) yet NOT collide with the gateway-detail
    'Push Changes to Gateway' button."""
    po, _role, _test_id = _make_po()
    with patch("page_object.po_mcp_hub.Util.check_dom_visibility", side_effect=[False, True]):
        po._diff_confirm_push()
    pattern = po.page.get_by_role.return_value.filter.return_value.get_by_role.call_args.kwargs["name"]
    # plain label matches
    assert pattern.search("Push to Gateway")
    # glyph-prefixed accessible name (PUA U+E944 folded in before the label) matches
    assert pattern.search(GLYPH_NAME)
    # the gateway-detail push button must NOT match (no contiguous substring)
    assert pattern.search("Push Changes to Gateway") is None
    # a leading-^ / exact match would FAIL against the glyph-prefixed name — confirm
    # the helper did not anchor to the start.
    assert pattern.pattern[:1] != "^"
