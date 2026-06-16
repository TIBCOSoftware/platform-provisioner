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

from page_object.po_global import PageObjectGlobal
from utils.color_logger import ColorLogger
from utils.e2e_util import E2EUtils
from utils.util import Util

class PageObjectO11y(PageObjectGlobal):
    def __init__(self, page):
        super().__init__(page)

    def goto_left_navbar_o11y(self):
        self.goto_left_navbar("Observability")
        # Gate on the always-present dashboard action row (Add card / Add dashboard / "..." menu).
        # Newer CP renders the header via 'tibco-header' (.header-title) instead of the old
        # '.widget-list-header h1', so waiting on the title text breaks on those versions.
        if not Util.check_dom_visibility(self.page, self.page.locator(".dashboard-actions-row"), 5, 60):
            Util.warning_screenshot("Observability dashboard action row did not appear", self.page, "o11y-not-loaded.png")
        print("Observability page is loaded")

    def get_add_card_button(self):
        return self.page.locator(".dashboard-actions-row button", has_text="Add Card")

    def is_support_add_widget(self):
        try:
            self.get_add_card_button().wait_for(state="visible", timeout=3000)
            is_visible = self.get_add_card_button().is_visible()
            is_enabled = self.get_add_card_button().is_enabled()
            if not is_enabled:
                ColorLogger.warning("Add Card button is visible but disabled")
            return is_visible and is_enabled

        except TimeoutError:
            ColorLogger.warning("Add Card button not found or not visible")
            return False

    def selector_data_plane_dropdown(self):
        # after dataplane dropdown list changed to autocomplete, the dataplane selector also need to be updated
        selector = ".widget-list-header .dataplane-list p-autocomplete .p-autocomplete-dropdown"
        if not self.page.locator(selector).is_visible():
            # if not found, use old selector, for CP 1.14 and earlier versions
            selector = ".widget-list-header p-dropdown"
        return selector

    def selector_none_disabled_data_plane(self, dp_name):
        # after dataplane dropdown list changed to autocomplete, the none disabled item selector also need to be updated
        selector = ".widget-list-header .dataplane-list .dd-item:not(.dd-item-disabled) .dd-item-label span"
        if not self.page.locator(selector, has_text=dp_name).is_visible():
            # if not found, use old selector, for CP 1.14 and earlier versions
            selector = ".p-dropdown-item .dp-item:not(.dp-item-disabled)"
        return selector

    def selector_data_plane_item(self, dp_name):
        # after dataplane dropdown list changed to autocomplete, the none disabled item selector also need to be updated
        selector = ".widget-list-header .dataplane-list .dd-item-label span"
        if not self.page.locator(selector, has_text=dp_name).is_visible():
            # if not found, use old selector, for CP 1.14 and earlier versions
            selector = ".p-dropdown-item .dp-item-label span"
        return selector

    def selector_dialog_footer_btn(self, btn_text):
        selector = ".p-dialog-footer button"
        if not self.page.locator(selector, has_text=btn_text).is_visible():
            # if not found, use old selector, before upgrade to PrimeNG 18
            selector = "p-confirmdialog button"
        return selector

    def selector_dialog_left_menu(self, menu_text):
        # Pick the tree-label class by which one the tree renders, NOT by whether
        # this specific menu_text is currently visible: a level-2 node (e.g. Engine)
        # is not rendered until its parent capability node is expanded, which would
        # otherwise make this fall back to the old class and time out on PrimeNG 18.
        selector = ".categories-menu-panel .p-tree-node-label"
        if self.page.locator(selector).count() == 0:
            # if not found, use old selector, before upgrade to PrimeNG 18
            selector = ".categories-menu-panel .p-treenode-label"
        return selector

    def is_data_plane_in_list(self, dp_name):
        self.page.locator(self.selector_data_plane_dropdown()).click()
        is_available = self.page.locator(self.selector_none_disabled_data_plane(dp_name), has_text=dp_name).count() > 0
        print(f"Check 'Data Plane' dropdown '{dp_name}' is is_available: {is_available}")
        if is_available:
            self.page.locator(self.selector_data_plane_item(dp_name), has_text=dp_name).click()
            print(f"Selected '{dp_name}' in 'Data Plane' dropdown")
        return is_available

    def select_data_plane(self, dp_name):
        self.page.locator(self.selector_data_plane_dropdown()).click()
        print(f"Clicked 'Data Plane' dropdown")
        self.page.locator(self.selector_data_plane_item(dp_name), has_text=dp_name).wait_for(state="visible")
        self.page.locator(self.selector_data_plane_item(dp_name), has_text=dp_name).click()
        print(f"Selected '{dp_name}' in 'Data Plane' dropdown")

    def get_chart_card(self, card_name):
        return self.page.locator(".widget-card", has=self.page.locator('.highcharts-title', has_text=card_name))

    # action menu: "Save Snapshot", "Revert to Snapshot", "Reset Layout"
    def click_action_menu(self, action_item, confirmation=False):
        self.page.locator(".dashboard-actions-row button.test-reset-layout").wait_for(state="visible")
        self.page.locator(".dashboard-actions-row button.test-reset-layout").click()
        print(f"Clicked '...' icon")
        self.page.locator(".p-menu-list li span", has_text=action_item).wait_for(state="visible")
        self.page.locator(".p-menu-list li span", has_text=action_item).click()
        print(f"Clicked '{action_item}' Button")
        if confirmation:
            self.page.locator(self.selector_dialog_footer_btn("Yes"), has_text="Yes").click()
            print(f"Clicked 'Yes' button in '{action_item}' confirmation dialog")
        self.page.wait_for_timeout(500)

    def click_add_widget_button(self):
        self.get_add_card_button().click()
        print(f"Clicked 'Add Card' Button")
        self.page.locator("card-catalog-modal").wait_for(state="visible")
        print(f"'Select card to add' dialog is visible")

    def click_widget_dialog_left_menu(self, level1_menu, level2_menu = None):
        self.page.locator(self.selector_dialog_left_menu(level1_menu), has_text=level1_menu).wait_for(state="visible")
        self.page.locator(self.selector_dialog_left_menu(level1_menu), has_text=level1_menu).click()
        print(f"Clicked 'Left side bar' -> '{level1_menu}' menu")

        if level2_menu:
            self.page.locator(self.selector_dialog_left_menu(level2_menu), has_text=level2_menu).wait_for(state="visible")
            self.page.locator(self.selector_dialog_left_menu(level2_menu), has_text=level2_menu).click()
            print(f"Clicked 'Left side bar' -> '{level1_menu}' -> '{level2_menu}' menu")

    def click_widget_dialog_middle_menu(self, middle_menu, data_plane_type=None):
        item_selector = f"li.widget-list-item:has-text('{middle_menu}')"
        if data_plane_type:
            item_selector = f".widgets-menu-panel li.widget-list-item-category:has-text('{data_plane_type}') ~ {item_selector}"

        item = self.page.locator(item_selector).first
        item.hover()
        item.locator(".widget-list-btn-add").click()
        print(f"Clicked '{middle_menu}' menu")

    def select_chart_type_toggle_button(self, chart_type=""):
        self.page.locator(".pl-text-toggle .pl-text-toggle__label", has_text=chart_type).click()
        print(f"Selected '{chart_type}' toggle button")

    def click_add_card_to_dashboard_button(self):
        self.page.locator(".selected-widget-panel-btn-add").click()
        print(f"Clicked 'Add to Dashboard' button")

    def add_widget(self, level1_menu, level2_menu, middle_menu, data_plane_type=None):
        if self.get_add_card_button().is_disabled():
            ColorLogger.warning("Add Card button is disabled, cannot add widget")
            return
        self.click_add_widget_button()
        self.click_widget_dialog_left_menu(level1_menu, level2_menu)
        self.click_widget_dialog_middle_menu(middle_menu, data_plane_type)
        self.page.locator("card-catalog-modal").wait_for(state="detached")
        print(f"'Select card to add' dialog is hidden")
        ColorLogger.success(
            f"Add '{level1_menu}' -> '{level2_menu}' -> '{middle_menu}'"
            + (f" -> '{data_plane_type}'" if data_plane_type else "") +
            " Card successfully"
        )

    def add_widgets(self, level1_menu, level2_menu, cards, data_plane_type=None):
        """Batch wrapper over add_widget() for a list of cards sharing the same
        left-menu path. add_widget() already guards against the disabled 'Add Card'
        button (per-dashboard 15-card limit), so cards beyond the limit are skipped."""
        for middle_menu in cards:
            self.add_widget(level1_menu, level2_menu, middle_menu, data_plane_type)

    # ---------------------------------------------------------------------------
    # Dashboard management (PCP-20053)
    # ---------------------------------------------------------------------------
    def selector_add_dashboard_button(self):
        return '[data-testid="widget-add-dashboard-button"]'

    def has_add_dashboard_button(self):
        """Pre-gate: the per-capability dashboard flow is only supported on CP
        versions that expose the 'Add dashboard' button. Older versions skip it."""
        is_visible = Util.check_dom_visibility(self.page, self.page.locator(self.selector_add_dashboard_button()), 2, 8)
        if not is_visible:
            ColorLogger.warning("'Add dashboard' button not found; this CP version does not support the dashboard flow")
        return is_visible

    def selector_catalog_menu_label(self):
        selector = ".categories-menu-panel .p-tree-node-label"
        if self.page.locator(selector).count() == 0:
            # fallback for versions before the PrimeNG 18 upgrade
            selector = ".categories-menu-panel .p-treenode-label"
        return selector

    def close_add_widget_dialog(self):
        close_button = "card-catalog-modal [data-testid='widget-catalog-modal-close']"
        if self.page.locator(close_button).is_visible():
            self.page.locator(close_button).click()
        else:
            self.page.keyboard.press("Escape")
        self.page.locator("card-catalog-modal").wait_for(state="detached")
        print("Closed 'Select card to add' dialog")

    def get_catalog_menu_labels(self):
        """Open the Add Card catalog once, collect the left-tree node labels
        (root + capability/category labels), then close. Used to decide which
        capability dashboards to create and whether Messaging cards exist."""
        if self.get_add_card_button().is_disabled():
            ColorLogger.warning("Add Card button is disabled, cannot read catalog menu labels")
            return []
        self.click_add_widget_button()
        label_selector = self.selector_catalog_menu_label()
        self.page.locator(label_selector).first.wait_for(state="visible")
        labels = [text.strip() for text in self.page.locator(label_selector).all_inner_texts() if text.strip()]
        self.close_add_widget_dialog()
        print(f"Catalog menu labels: {labels}")
        return labels

    def is_catalog_card_available(self, level1_menu, level2_menu, card_name):
        """Whether a specific card is available under the given left-menu path."""
        if self.get_add_card_button().is_disabled():
            return False
        self.click_add_widget_button()
        self.click_widget_dialog_left_menu(level1_menu, level2_menu)
        present = self.page.locator("li.widget-list-item", has_text=card_name).count() > 0
        self.close_add_widget_dialog()
        print(f"Card '{card_name}' under '{level1_menu}' available: {present}")
        return present

    def selector_dashboard_option(self):
        return ".p-select-option, .p-dropdown-item, [role='option']"

    def open_dashboard_dropdown(self):
        """Open the header dashboard dropdown (the one listing dashboards, which
        always contains the built-in 'Default'). The Observability header renders
        two dropdowns (data plane + dashboard); pick the one whose panel lists
        'Default'."""
        trigger_selectors = ["shared-header p-select", "shared-header p-dropdown", ".widget-list-header p-dropdown"]
        option_selector = self.selector_dashboard_option()
        overlay = self.page.locator(".p-select-overlay, .p-dropdown-panel")
        for _attempt in range(3):
            # clear any stray overlay so a previous open does not block the trigger click
            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(300)
            for selector in trigger_selectors:
                triggers = self.page.locator(selector)
                count = triggers.count()
                # iterate from last to first: the dashboard dropdown is rendered after the data plane one
                for i in range(count - 1, -1, -1):
                    try:
                        triggers.nth(i).click()
                    except Exception:
                        continue
                    if Util.check_dom_visibility(self.page, overlay.first, 1, 3):
                        if self.page.locator(option_selector, has_text="Default").count() > 0:
                            return True
                    # not the dashboard dropdown, close and try the next one
                    self.page.keyboard.press("Escape")
                    self.page.wait_for_timeout(200)
        ColorLogger.warning("Could not open the dashboard dropdown")
        return False

    def get_dashboard_names(self):
        if not self.open_dashboard_dropdown():
            return []
        names = [text.strip() for text in self.page.locator(self.selector_dashboard_option()).all_inner_texts() if text.strip()]
        self.page.keyboard.press("Escape")
        return names

    def is_dashboard_exists(self, name):
        exists = name in self.get_dashboard_names()
        print(f"Dashboard '{name}' exists: {exists}")
        return exists

    def goto_dashboard(self, name=""):
        """Navigate to a dashboard via the header dashboard dropdown. Empty name
        means the built-in 'Default' dashboard."""
        target = name if name else "Default"
        if not self.open_dashboard_dropdown():
            Util.warning_screenshot(f"Cannot open dashboard dropdown to go to '{target}'", self.page, "o11y-dashboard-dropdown.png")
            return False
        self.page.locator(self.selector_dashboard_option(), has_text=target).first.click()
        self.page.locator(".widget-list-content").wait_for(state="visible")
        print(f"Navigated to dashboard '{target}'")
        return True

    def close_add_dashboard_dialog(self):
        close_button = ".add-dashboard-dialog [data-testid='widget-catalog-modal-close']"
        if self.page.locator(close_button).is_visible():
            self.page.locator(close_button).click()
        else:
            self.page.keyboard.press("Escape")

    def create_dashboard(self, name):
        """Add dashboard -> fill name -> Save -> wait for navigation to the new
        (empty) dashboard. Returns True on success. A duplicate/invalid name keeps
        the dialog open with an inline error; in that case it logs and returns False."""
        self.page.locator(self.selector_add_dashboard_button()).click()
        print("Clicked 'Add dashboard' button")
        self.page.locator("#dashboard-name").wait_for(state="visible")
        self.page.locator("#dashboard-name").fill(name)
        print(f"Filled dashboard name '{name}'")
        self.page.locator('[data-testid="widget-save-dashboard-button"]').click()
        print("Clicked 'Save' dashboard button")

        error_locator = self.page.locator(".add-dashboard-dialog .error-message")
        if Util.check_dom_visibility(self.page, error_locator, 1, 3):
            ColorLogger.warning(f"Create dashboard '{name}' failed: {error_locator.inner_text().strip()}")
            self.close_add_dashboard_dialog()
            return False

        # success: the dialog closes and the app navigates to the new empty dashboard
        self.page.locator("#dashboard-name").wait_for(state="hidden")
        self.page.locator(".widget-list-content").wait_for(state="visible")
        ColorLogger.success(f"Created dashboard '{name}'")
        return True

    def click_widget_card_button(self, widget_title, icon_name):
        widget_dom = self.page.locator('custom-metric-widget', has=self.page.locator('.highcharts-title', has_text=widget_title))
        widget_dom.locator(f'custom-metrics-filter .widget-filter-button[title="{icon_name}"]').wait_for(state="visible")
        widget_dom.locator(f'custom-metrics-filter .widget-filter-button[title="{icon_name}"]').click()
        print(f"Clicked '{widget_title}' -> '{icon_name}' button")

    def click_filter_dialog_button(self, label):
        self.page.locator(".widget-filter-dialog-v2 button", has_text=label).click()
        print(f"Clicked Custom Filter -> '{label}' button")

    def click_filter_dialog_menu(self, label):
        self.page.locator(".widget-filter-dialog-v2 .menu-item", has_text=label).click()
        print(f"Clicked Custom Filter -> '{label}' menu")

    def input_filter_dialog_card_name(self, current_card_name, new_card_name):
        self.page.locator('.widget-filter-dialog-v2 .title-button').click()
        self.page.locator('.widget-filter-dialog-v2 input.title-input').clear()
        self.page.locator('.widget-filter-dialog-v2 input.title-input').fill(new_card_name)
        print(f"Change Custom Filter -> Card Name From '{current_card_name}' to '{new_card_name}'")

    def click_filter_dialog_chart_type(self, label):
        self.page.locator('.widget-filter-dialog-v2 label.pl-text-toggle__label[for^="chart-type-"]', has_text=label).click()
        print(f"Clicked Custom Filter -> Chart Type: '{label}'")

    def assert_after_custom_metrics_apply_filter(self, expected_query_params: dict):
        """
        After click 'Apply' button in the filter dialog,
        Wait and verify if the api url request contains the expected query parameters
        :param expected_query_params: need to match query parameters (in dictionary form)
        """
        E2EUtils.assert_api_request_and_response(
            self.page,
            "/o11y/v2/metrics",
            lambda: self.click_filter_dialog_button("Apply"),
            'GET',
            200,
            expected_query_params
        )
