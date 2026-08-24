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
# Regression tests for PCP-23371 — click_action_menu's "..." button selector
# went stale after tp-o11y-service's Fresco migration (PCP-21299, commit
# c9403d121): the button.test-reset-layout class moved off the real <button>
# onto the <tibco-button> host, so the old class-based selector matched 0
# elements and the automation timed out.
#
# Fix: switch to `[data-testid="widget-more-option-button"]` — that attribute
# is unchanged across the migration (present on both the old <button> and the
# new <tibco-button> host), matching this file's own convention for the
# sibling Add/Save dashboard buttons (widget-add-dashboard-button /
# widget-save-dashboard-button), which the same migration commit did not break.
# Scoped to .dashboard-actions-row (its real parent) + `.first` as a strict-mode
# safety net, in case any other widget-level control reuses the same test-id.
#
# These tests pin that contract on the deterministic MagicMock-page path (no
# browser), following the sibling suites' object.__new__ + MagicMock pattern.
#
# Limitation: since there is no real page here, these tests can only confirm
# the selector string hasn't changed — they cannot confirm it still matches
# the live DOM. If tp-o11y-service migrates this button again, this suite
# stays green while the automation breaks the same way PCP-23371 did. The
# live-verification evidence for "the selector matches the real DOM" is the
# GCP end-to-end runs on ins-owen-tas-73 recorded in the PR/Jira, not this
# file; e2e/observability/test_o11y_list.py exercises a real page and is the
# candidate to gate on if this selector needs a repeatable, non-manual check.

from unittest.mock import MagicMock, call

from page_object.po_o11y import PageObjectO11y

EXPECTED_SELECTOR = '.dashboard-actions-row [data-testid="widget-more-option-button"]'


def _new():
    """Build the page object without running __init__ (no real browser/page)."""
    po = object.__new__(PageObjectO11y)
    po.page = MagicMock()
    return po


def _install_locator_router(po):
    """Route self.page.locator(...) to distinct mocks by selector/has_text so each
    call site (options button, menu item, confirmation Yes) is independently
    assertable."""
    options_button = MagicMock(name="options-button")
    menu_item = MagicMock(name="menu-item")
    yes_button = MagicMock(name="yes-button")

    def router(selector, has_text=None):
        if selector == EXPECTED_SELECTOR:
            return options_button
        if selector == ".p-menu-list li span":
            return menu_item
        return yes_button

    po.page.locator.side_effect = router
    return options_button, menu_item, yes_button


def test_click_action_menu_uses_the_migration_stable_data_testid_selector():
    """Regression pin: the options-button selector must be the data-testid hook
    (stable across the Fresco migration), not the class-based selector that
    broke when tp-o11y-service moved test-reset-layout onto the <tibco-button>
    host."""
    po = _new()
    options_button, menu_item, _ = _install_locator_router(po)

    po.click_action_menu("Save Snapshot")

    po.page.locator.assert_any_call(EXPECTED_SELECTOR)
    options_button.first.wait_for.assert_called_once_with(state="visible")
    options_button.first.click.assert_called_once()


def test_click_action_menu_clicks_requested_menu_item():
    po = _new()
    _, menu_item, _ = _install_locator_router(po)

    po.click_action_menu("Reset Layout")

    po.page.locator.assert_any_call(".p-menu-list li span", has_text="Reset Layout")
    menu_item.wait_for.assert_called_once_with(state="visible")
    menu_item.click.assert_called_once()


def test_click_action_menu_confirms_when_requested():
    po = _new()
    po.selector_dialog_footer_btn = MagicMock(return_value="#dialog-footer .yes-btn")
    _, _, yes_button = _install_locator_router(po)

    po.click_action_menu("Revert to Snapshot", confirmation=True)

    yes_button.click.assert_called_once()


def test_click_action_menu_skips_confirmation_by_default():
    po = _new()
    po.selector_dialog_footer_btn = MagicMock(return_value="#dialog-footer .yes-btn")
    options_button, menu_item, yes_button = _install_locator_router(po)

    po.click_action_menu("Save Snapshot")

    # Only the options button and menu item locators are used; no Yes-button click.
    assert call("#dialog-footer .yes-btn", has_text="Yes") not in po.page.locator.call_args_list
    yes_button.click.assert_not_called()
