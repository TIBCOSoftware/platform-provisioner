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
# Regression tests for PCP-22376 — add_mcp_server must (1) drive the MCP Hub 1.20.0
# gateway-centric "Add" flow (Install -> Add, Installed on this DP -> Added on this
# DP, confirm "Install on N DP" -> "Add to N DP"), keeping backward-compat with the
# older "Install" wording, and (2) treat an already-added registry card as an
# idempotent SUCCESS skip, not a hard error.
#
# Root cause: MCP Hub 1.20.0 renamed the whole server-install flow to "Add" and the
# in-gateway registry card no longer has an "Install" button (it shows an "Add"
# button, or — once added — an "Added on this DP" badge with no button). The old
# selectors ("Install" button, "Installed on this DP", dialog title "Install <X>")
# no longer match, so deploy-mcp-hub failed with "Install button not found". Verified
# live on ins-owen-mcp-19 (MCP Hub 1.20.0).

from unittest.mock import MagicMock, patch

from page_object.po_mcp_hub import PageObjectMcpHub

CATALOG_NAME = "TIBCO® Control Plane MCP Server"
SERVER_KEY = "cp-mcp-server"  # maps to CATALOG_NAME via MCP_SERVER_CATALOG


def _make_po():
    """Build a PageObjectMcpHub without __init__ (no real Playwright page)."""
    po = PageObjectMcpHub.__new__(PageObjectMcpHub)
    po.page = MagicMock()
    po.gateway_id = "gw-1"
    po._gateways_api_url = None
    return po


# --- _card_installed_on_dp: the deterministic already-added signal ------------------

def test_card_installed_badge_regex_matches_added_and_installed_not_not_added():
    """PCP-22376: the already-added detector matches BOTH the 1.20.0 'Added on this DP'
    and the legacy 'Installed on this DP', but NEVER the not-added pill 'Not added'
    (which lacks the '… on this DP' suffix), so the two states are never confused."""
    po = _make_po()
    card = MagicMock()
    with patch("page_object.po_mcp_hub.Util.check_dom_visibility", return_value=True):
        assert po._card_installed_on_dp(card) is True
    rx = card.get_by_text.call_args[0][0]
    assert hasattr(rx, "search"), "badge must be matched by a regex"
    assert rx.search("Added on this DP")          # 1.20.0
    assert rx.search("Installed on this DP")       # legacy
    assert not rx.search("Not added")              # not-installed pill must NOT match


def test_card_installed_on_dp_false_when_badge_absent():
    po = _make_po()
    card = MagicMock()
    with patch("page_object.po_mcp_hub.Util.check_dom_visibility", return_value=False):
        assert po._card_installed_on_dp(card) is False


# --- add_mcp_server idempotency + Add/Install button/dialog adaptation --------------
#
# check_dom_visibility calls in add_mcp_server up to the install decision. PCP-22620 inserted
# the `catalog-card-install` test-id probe BEFORE the role+name fallback:
#   1 servers-page, 2 registry button, 3 catalog-card present (dialog open), 4 card present,
#   5 catalog-card-install test-id (present?), 6 add/install button present, 7 add-dialog open.
# When the test-id is visible at 5, the role+name fallback is skipped (step 6 re-checks the
# same test-id locator). _card_installed_on_dp, _install_dialog, _servers_registry_button,
# _install_wizard, _close_browse_registry are patched per-test so only that gate is consumed.


def _patched_add_mcp_server(po, cdv_side_effect, installed_side_effect):
    """Run add_mcp_server with the page-flow gates + the installed-signal stubbed.
    Returns the mocks the assertions inspect."""
    close = MagicMock()
    install_wizard = MagicMock()
    installed = MagicMock(side_effect=installed_side_effect)
    with patch.object(PageObjectMcpHub, "goto_gateway"), \
         patch.object(PageObjectMcpHub, "_servers_registry_button", return_value=MagicMock()), \
         patch.object(PageObjectMcpHub, "_close_browse_registry", close), \
         patch.object(PageObjectMcpHub, "_install_wizard", install_wizard), \
         patch.object(PageObjectMcpHub, "_install_dialog", return_value=MagicMock()), \
         patch.object(PageObjectMcpHub, "_card_installed_on_dp", installed), \
         patch("page_object.po_mcp_hub.Util.click_button_until_enabled"), \
         patch("page_object.po_mcp_hub.Util.check_dom_visibility", side_effect=cdv_side_effect), \
         patch("page_object.po_mcp_hub.Util.exit_error", side_effect=SystemExit(1)) as exit_error:
        raised = False
        try:
            po.add_mcp_server(name=SERVER_KEY, token="tok")
        except SystemExit:
            raised = True
    return close, install_wizard, exit_error, raised


def test_add_mcp_server_skips_when_precheck_sees_installed():
    """Pre-check sees the added badge -> skip without clicking Add."""
    po = _make_po()
    close, install_wizard, exit_error, raised = _patched_add_mcp_server(
        po, cdv_side_effect=[True, True, True, True], installed_side_effect=[True])
    assert not raised
    assert not exit_error.called
    install_wizard.assert_not_called()
    close.assert_called_once()


def test_add_mcp_server_skips_on_late_badge_when_add_button_absent():
    """PCP-22376 core: pre-check MISSES a late badge (False), the Add button is also
    absent (already-added card), and the re-check now sees the badge -> idempotent
    skip, NOT a hard error."""
    po = _make_po()
    close, install_wizard, exit_error, raised = _patched_add_mcp_server(
        po,
        # 1-4 flow gates True, 5 catalog-card-install test-id absent, 6 role+name button absent
        cdv_side_effect=[True, True, True, True, False, False],
        installed_side_effect=[False, True])
    assert not raised
    assert not exit_error.called
    install_wizard.assert_not_called()
    close.assert_called_once()


def test_add_mcp_server_hard_fails_when_no_button_and_not_installed():
    """A genuine missing Add button (badge also absent) still fails loud — the
    idempotency skip must not mask a real registry/selector defect."""
    po = _make_po()
    close, install_wizard, exit_error, raised = _patched_add_mcp_server(
        po,
        # 5 catalog-card-install test-id absent, 6 role+name button absent, badge re-check also absent
        cdv_side_effect=[True, True, True, True, False, False],
        installed_side_effect=[False, False])
    assert raised
    assert exit_error.called
    assert "Add button not found" in exit_error.call_args[0][0]
    install_wizard.assert_not_called()


def test_add_mcp_server_installs_normally_when_button_present():
    """Not added + the catalog-card-install test-id present -> click it and drive the install
    wizard (happy path on a current Hub; regression guard that the flip didn't break it)."""
    po = _make_po()
    close, install_wizard, exit_error, raised = _patched_add_mcp_server(
        po,
        # 5 catalog-card-install test-id present -> role+name fallback never built; 6 button
        # present re-check True; 7 add-dialog open True.
        cdv_side_effect=[True, True, True, True, True, True, True],
        installed_side_effect=[False])
    assert not raised
    assert not exit_error.called
    install_wizard.assert_called_once()
    close.assert_not_called()
    # PCP-22620: the card action was resolved by the catalog-card-install test-id, card-scoped.
    card = po.page.get_by_test_id.return_value.filter.return_value.first
    card.get_by_test_id.assert_called_with("catalog-card-install")
    card.get_by_role.assert_not_called()  # test-id hit -> role+name never consulted


def test_add_mcp_server_card_button_fallback_matches_add_and_install_not_uninstall():
    """PCP-22376 + PCP-22620: on an OLDER Hub (no catalog-card-install test-id) the card
    action FALLBACK is matched by a word-boundary regex covering BOTH the 1.20.0 'Add' and
    the legacy 'Install' — never the bare string. Playwright name=<string> is a
    case-insensitive SUBSTRING match, so 'Add'/'Install' would also match 'Uninstall'/'Added';
    a bare-string locator could resolve to a destructive button on an already-added card and
    bypass the installed re-check. \\b(Add|Install)\\b (case-sensitive, glyph-tolerant) excludes
    'Uninstall' and 'Added'."""
    po = _make_po()
    # 5 catalog-card-install test-id ABSENT -> the role+name fallback builds (what this pins);
    # 6 button present True, 7 add-dialog open True.
    _patched_add_mcp_server(
        po, cdv_side_effect=[True, True, True, True, False, True, True], installed_side_effect=[False])
    card = po.page.get_by_test_id.return_value.filter.return_value.first
    name_arg = card.get_by_role.call_args.kwargs["name"]
    assert hasattr(name_arg, "pattern"), "Add button must be a regex, not a bare string"
    assert name_arg.pattern == r"\b(Add|Install)\b"
    assert name_arg.search("Add")               # 1.20.0
    assert name_arg.search("Install")           # legacy
    assert name_arg.search("Add")   # PrimeReact icon glyph folded into the a11y name
    assert not name_arg.search("Uninstall")     # destructive, case-sensitive -> excluded
    assert not name_arg.search("Added")         # trailing \b fails before "ed" -> excluded


# === PCP-22620: install-flow controls flipped to test-id-first ======================
#
# PCP-22619 re-added stable data-testids on the install flow (Fresco alpha.87 passthrough /
# PLTUX-1299): catalog-card-install (card), install-next (dialog Next), install-submit (dialog
# confirm), install-done / install-close (dialog terminal). The automation now prefers each
# test-id and falls back to the visible label by role+name only for older Hub builds. The
# catalog-card-install flip is pinned by test_add_mcp_server_installs_normally_when_button_present
# (test-id path) and ..._fallback_matches_add_and_install... (role path); these pin the wizard
# helpers, which the add_mcp_server gate-flow tests patch out.


def test_install_click_next_prefers_test_id():
    """_install_click_next resolves the wizard 'Next' by the install-next test-id FIRST; when
    visible the role+name locator is never built."""
    po = _make_po()
    dialog = MagicMock()
    with patch.object(PageObjectMcpHub, "_install_dialog", return_value=dialog), \
         patch("page_object.po_mcp_hub.Util.check_dom_visibility", return_value=True), \
         patch("page_object.po_mcp_hub.Util.click_button_until_enabled") as click:
        po._install_click_next()
    dialog.get_by_test_id.assert_called_with("install-next")
    dialog.get_by_role.assert_not_called()
    click.assert_called_once_with(po.page, dialog.get_by_test_id.return_value.first)


def test_install_click_next_falls_back_to_role_name():
    """Older Hub: install-next test-id absent -> fall back to role+name 'Next'."""
    po = _make_po()
    dialog = MagicMock()
    # first cdv (install-next test-id) False -> role fallback; second cdv (visible) True -> click
    with patch.object(PageObjectMcpHub, "_install_dialog", return_value=dialog), \
         patch("page_object.po_mcp_hub.Util.check_dom_visibility", side_effect=[False, True]), \
         patch("page_object.po_mcp_hub.Util.click_button_until_enabled") as click:
        po._install_click_next()
    dialog.get_by_test_id.assert_called_with("install-next")
    dialog.get_by_role.assert_called_with("button", name="Next")
    click.assert_called_once_with(po.page, dialog.get_by_role.return_value.first)


def test_install_wizard_confirm_prefers_install_submit_test_id():
    """_install_wizard resolves the footer confirm by the install-submit test-id FIRST (dialog
    scoped). cdv: preselected T, creds F (skip), review T, install-submit test-id T, visible T."""
    po = _make_po()
    dialog = MagicMock()
    with patch.object(PageObjectMcpHub, "_install_dialog", return_value=dialog), \
         patch.object(PageObjectMcpHub, "_install_click_next"), \
         patch.object(PageObjectMcpHub, "_install_finish"), \
         patch("page_object.po_mcp_hub.Util.check_dom_visibility",
               side_effect=[True, False, True, True, True]), \
         patch("page_object.po_mcp_hub.Util.exit_error", side_effect=SystemExit(1)) as exit_error:
        po._install_wizard(token="")
    assert not exit_error.called
    dialog.get_by_test_id.assert_any_call("install-submit")
    dialog.get_by_test_id.return_value.first.click.assert_called_once()
    dialog.get_by_role.assert_not_called()  # test-id hit -> role+name fallback not consulted


def test_install_wizard_confirm_falls_back_to_role_name():
    """Older Hub: install-submit test-id absent -> dialog-scoped role+name '(Add to|Install on)
    N DP(s)' fallback (unanchored, glyph-tolerant). cdv: preselected T, creds F, review T,
    install-submit test-id F (-> role), visible T."""
    po = _make_po()
    dialog = MagicMock()
    with patch.object(PageObjectMcpHub, "_install_dialog", return_value=dialog), \
         patch.object(PageObjectMcpHub, "_install_click_next"), \
         patch.object(PageObjectMcpHub, "_install_finish"), \
         patch("page_object.po_mcp_hub.Util.check_dom_visibility",
               side_effect=[True, False, True, False, True]), \
         patch("page_object.po_mcp_hub.Util.exit_error", side_effect=SystemExit(1)) as exit_error:
        po._install_wizard(token="")
    assert not exit_error.called
    dialog.get_by_test_id.assert_any_call("install-submit")
    name_arg = dialog.get_by_role.call_args.kwargs["name"]
    assert name_arg.search("Add to 2 DPs")       # 1.20.0
    assert name_arg.search("Install on 1 DP")    # legacy
    dialog.get_by_role.return_value.first.click.assert_called_once()


def test_install_finish_prefers_done_test_id():
    """_install_finish resolves the terminal 'Done' by the install-done test-id FIRST; when
    visible the role+name locator is never built."""
    po = _make_po()
    dialog = MagicMock()
    done_btn = MagicMock()
    done_btn.is_visible.return_value = True

    def _by_test_id(tid):
        m = MagicMock()
        m.first = done_btn if tid == "install-done" else MagicMock()
        return m

    dialog.get_by_test_id.side_effect = _by_test_id
    with patch.object(PageObjectMcpHub, "_install_dialog", return_value=dialog):
        po._install_finish()
    dialog.get_by_test_id.assert_any_call("install-done")
    done_btn.click.assert_called_once()
    dialog.get_by_role.assert_not_called()  # test-id hit -> role+name never consulted


def test_install_finish_falls_back_to_label():
    """Older Hub: install-done test-id absent -> fall back to the role+name 'Done' label."""
    po = _make_po()
    dialog = MagicMock()
    testid_btn = MagicMock()
    testid_btn.is_visible.return_value = False   # test-id not present
    role_btn = MagicMock()
    role_btn.is_visible.return_value = True       # role+name label present
    dialog.get_by_test_id.return_value.first = testid_btn
    dialog.get_by_role.return_value.first = role_btn
    with patch.object(PageObjectMcpHub, "_install_dialog", return_value=dialog):
        po._install_finish()
    dialog.get_by_test_id.assert_any_call("install-done")
    dialog.get_by_role.assert_any_call("button", name="Done")
    role_btn.click.assert_called_once()
