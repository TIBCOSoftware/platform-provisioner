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
# Regression tests for PCP-20368 — the deploy-mcp-hub push-to-gateway diff-confirm
# selector drift.
#
# Root cause (see docs/plan/PCP-20368-plan.md): on the Fresco-redesigned MCP Hub the
# Preview-Changes diff dialog's confirm button renders as a Fresco Button
# 'Push to Gateway' (no data-testid) in the dialog FOOTER — outside the
# 'dp-action-diff-preview' content div — so the old
# get_by_test_id("dp-action-diff-push").click() matches nothing and times out.
# The fix is _diff_confirm_push(): scope to the role=dialog that CONTAINS the
# 'dp-action-diff-preview' content marker (filter has=...), select the footer button
# by role+accessible-name, with the legacy testid as a backward-compat fallback.
#
# These tests pin the parts most likely to silently rot — and are pure logic
# (MagicMock, zero browser); the live-DOM behavior is proven by e2e (a selector
# match against a real ::before glyph cannot be unit-tested honestly):
#   * the fallback ORDERING: new (role+name) -> legacy (testid) -> unusable new;
#   * the selectors actually used (dialog filtered by the content marker, role=button,
#     legacy testid);
#   * the regex SEMANTICS: unanchored (tolerates the pi-cloud-upload ::before glyph
#     that folds into the accessible name) yet does NOT collide with the
#     gateway-detail "Push Changes to Gateway" button.

from unittest.mock import MagicMock, patch

from page_object.po_mcp_hub import PageObjectMcpHub

# The PrimeReact 'pi pi-cloud-upload' icon renders as a ::before glyph in the PUA
# block (U+E944) that Playwright folds into the button's accessible name *before*
# the label — the live-DOM fact (alpha.113) the unanchored regex must tolerate.
GLYPH_NAME = chr(0xE944) + "Push to Gateway"


def _make_po():
    """Build a PageObjectMcpHub without running __init__ (which needs a real
    Playwright page). Inject a MagicMock page; install distinct sentinels for the
    role-based ('new') and legacy-testid ('legacy') locators so the test can assert
    which one the helper returns.

    Helper locator chain:
      page.get_by_role("dialog").filter(has=...).get_by_role("button", ...).first
      page.get_by_test_id("dp-action-diff-push").first  (legacy fallback)
    """
    po = PageObjectMcpHub.__new__(PageObjectMcpHub)
    po.page = MagicMock()
    po.gateway_id = None
    new = MagicMock(name="role-locator")        # dialog.filter(...).get_by_role("button", ...).first
    legacy = MagicMock(name="legacy-testid")     # get_by_test_id("dp-action-diff-push").first
    po.page.get_by_role.return_value.filter.return_value.get_by_role.return_value.first = new
    po.page.get_by_test_id.return_value.first = legacy
    return po, new, legacy


def _testid_calls(po):
    """The positional testid names get_by_test_id was called with, in order."""
    return [c.args[0] for c in po.page.get_by_test_id.call_args_list if c.args]


def test_returns_role_locator_when_visible():
    """new (role+name) visible -> return it; never consult the legacy testid."""
    po, new, _legacy = _make_po()
    with patch("page_object.po_mcp_hub.Util.check_dom_visibility", side_effect=[True]):
        result = po._diff_confirm_push()
    assert result is new
    # The dialog is scoped by the content marker; the legacy push testid must NOT be
    # queried when the role locator is visible.
    assert "dp-action-diff-preview" in _testid_calls(po)
    assert "dp-action-diff-push" not in _testid_calls(po)


def test_falls_back_to_legacy_testid_when_role_locator_invisible():
    """new invisible + legacy visible -> return the legacy dp-action-diff-push testid."""
    po, _new, legacy = _make_po()
    with patch("page_object.po_mcp_hub.Util.check_dom_visibility", side_effect=[False, True]):
        result = po._diff_confirm_push()
    assert result is legacy
    po.page.get_by_test_id.assert_any_call("dp-action-diff-push")


def test_returns_unusable_new_when_both_invisible_for_caller_to_guard():
    """Neither visible -> return new (unusable) so the caller's check_dom_visibility
    guard fires with a screenshot, instead of a silent timeout."""
    po, new, _legacy = _make_po()
    with patch("page_object.po_mcp_hub.Util.check_dom_visibility", side_effect=[False, False]):
        result = po._diff_confirm_push()
    assert result is new


def test_scopes_to_dialog_filtered_by_content_marker_then_button():
    """The helper scopes role=button under the role=dialog that CONTAINS the
    'dp-action-diff-preview' content marker (the button is in the dialog footer,
    outside that content div)."""
    po, _new, _legacy = _make_po()
    with patch("page_object.po_mcp_hub.Util.check_dom_visibility", side_effect=[True]):
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


def test_button_regex_is_glyph_tolerant_and_non_colliding():
    """The button regex must be UNANCHORED (tolerate the pi-cloud-upload ::before
    glyph that folds into the accessible name) yet NOT collide with the
    gateway-detail 'Push Changes to Gateway' button."""
    po, _new, _legacy = _make_po()
    with patch("page_object.po_mcp_hub.Util.check_dom_visibility", side_effect=[True]):
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
