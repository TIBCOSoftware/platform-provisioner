#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary

from page_object.po_global import PageObjectGlobal
from utils.color_logger import ColorLogger
from utils.e2e_util import E2EUtils

class PageObjectO11y(PageObjectGlobal):
    def __init__(self, page):
        super().__init__(page)

    def goto_left_navbar_o11y(self):
        self.goto_left_navbar("Observability")
        self.page.locator(".widget-list-header h1", has_text="Observability").wait_for(state="visible")
        print(f"Waiting for Data Planes page is loaded")

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

    def is_data_plane_in_list(self, dp_name):
        self.page.locator(".widget-list-header p-dropdown").click()
        is_available = self.page.locator(".p-dropdown-item .dp-item:not(.dp-item-disabled)", has_text=dp_name).count() > 0
        print(f"Check 'Data Plane' dropdown '{dp_name}' is is_available: {is_available}")
        if is_available:
            self.page.locator(".p-dropdown-item .dp-item-label span", has_text=dp_name).click()
            print(f"Selected '{dp_name}' in 'Data Plane' dropdown")
        return is_available

    def select_data_plane(self, dp_name):
        self.page.locator(".widget-list-header p-dropdown").click()
        print(f"Clicked 'Data Plane' dropdown")
        self.page.locator(".p-dropdown-item .dp-item-label span", has_text=dp_name).wait_for(state="visible")
        self.page.locator(".p-dropdown-item .dp-item-label span", has_text=dp_name).click()
        print(f"Selected '{dp_name}' in 'Data Plane' dropdown")

    def get_chart_card(self, card_name):
        return self.page.locator(".widget-card", has=self.page.locator('.highcharts-title', has_text=card_name))

    # action menu: "Save Snapshot", "Revert to Snapshot", "Reset Layout"
    def click_action_menu(self, action_item, confirmation=False):
        self.page.locator(".dashboard-actions-row button.test-reset-layout").wait_for(state="visible")
        self.page.locator(".dashboard-actions-row button.test-reset-layout").click()
        print(f"Clicked '...' icon")
        self.page.locator(".dashboard-actions-row .p-menuitem-link span", has_text=action_item).wait_for(state="visible")
        self.page.locator(".dashboard-actions-row .p-menuitem-link span", has_text=action_item).click()
        print(f"Clicked '{action_item}' Button")
        if confirmation:
            self.page.locator("p-confirmdialog button", has_text="Yes").click()
            print(f"Clicked 'Yes' button in '{action_item}' confirmation dialog")
        self.page.wait_for_timeout(500)

    def click_add_widget_button(self):
        self.get_add_card_button().click()
        print(f"Clicked 'Add Card' Button")
        self.page.locator("card-catalog-modal").wait_for(state="visible")
        print(f"'Select card to add' dialog is visible")

    def click_widget_dialog_left_menu(self, level1_menu, level2_menu = None):
        self.page.locator(".categories-menu-panel .p-treenode-label", has_text=level1_menu).wait_for(state="visible")
        self.page.locator(".categories-menu-panel .p-treenode-label", has_text=level1_menu).click()
        print(f"Clicked 'Left side bar' -> '{level1_menu}' menu")

        if level2_menu:
            self.page.locator(".categories-menu-panel .p-treenode-label", has_text=level2_menu).wait_for(state="visible")
            self.page.locator(".categories-menu-panel .p-treenode-label", has_text=level2_menu).click()
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
