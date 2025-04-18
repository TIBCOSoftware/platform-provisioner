#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary

from page_object.po_global import PageObjectGlobal
from utils.e2e_util import E2EUtils

class PageObjectO11y(PageObjectGlobal):
    def __init__(self, page):
        super().__init__(page)

    def goto_left_navbar_o11y(self):
        self.goto_left_navbar("Observability")
        self.page.locator(".widget-list-header h1", has_text="Observability").wait_for(state="visible")
        print(f"Waiting for Data Planes page is loaded")

    def select_data_plane(self, dp_name):
        self.page.locator(".widget-list-header p-dropdown").click()
        print(f"Clicked 'Data Plane' dropdown")
        self.page.locator(".p-dropdown-item .dp-item-label span", has_text=dp_name).wait_for(state="visible")
        self.page.locator(".p-dropdown-item .dp-item-label span", has_text=dp_name).click()
        print(f"Selected '{dp_name}' in 'Data Plane' dropdown")

    # action menu: "Save Snapshot", "Revert to Snapshot", "Reset Layout"
    def click_action_menu(self, action_item):
        self.page.locator(".dashboard-actions-row button.test-reset-layout").wait_for(state="visible")
        self.page.locator(".dashboard-actions-row button.test-reset-layout").click()
        print(f"Clicked '...' icon")
        self.page.locator(".dashboard-actions-row .p-menuitem-link span", has_text=action_item).wait_for(state="visible")
        self.page.locator(".dashboard-actions-row .p-menuitem-link span", has_text=action_item).click()
        print(f"Clicked '{action_item}' Button")
        self.page.wait_for_timeout(500)

    def click_add_widget_button(self):
        self.page.locator(".dashboard-actions-row button", has_text="Add Widget").click()
        print(f"Clicked 'Add Widget' Button")
        self.page.locator("card-catalog-modal").wait_for(state="visible")
        print(f"'Select card to add' dialog is visible")

    def click_widget_dialog_left_menu(self, level1_menu, level2_menu = None):
        self.page.locator(".categories-menu-panel .p-treenode-label", has_text=level1_menu).wait_for(state="visible")
        self.page.locator(".categories-menu-panel .p-treenode-label", has_text=level1_menu).click()
        print(f"Clicked 'Integration Application' -> '{level1_menu}' menu")

        if level2_menu:
            self.page.locator(".categories-menu-panel .p-treenode-label", has_text=level2_menu).wait_for(state="visible")
            self.page.locator(".categories-menu-panel .p-treenode-label", has_text=level2_menu).click()
            print(f"Clicked 'Integration Application' -> '{level1_menu}' -> '{level2_menu}' menu")

    def click_widget_dialog_middle_menu(self, middle_menu):
        self.page.locator(".widgets-menu-panel .widget-list-item div", has_text=middle_menu).click()
        print(f"Clicked '{middle_menu}' menu")

    def select_chart_type_toggle_button(self, chart_type=""):
        self.page.locator(".pl-text-toggle .pl-text-toggle__label", has_text=chart_type).click()
        print(f"Selected '{chart_type}' toggle button")

    def click_add_card_to_dashboard_button(self):
        self.page.locator(".selected-widget-panel-btn-add").click()
        print(f"Clicked 'Add Card to Dashboard' button")

    def add_widget(self, level1_menu, level2_menu, middle_menu, chart_type):
        self.click_add_widget_button()
        self.click_widget_dialog_left_menu(level1_menu, level2_menu)
        self.click_widget_dialog_middle_menu(middle_menu)
        if chart_type:
            self.select_chart_type_toggle_button(chart_type)
        self.click_add_card_to_dashboard_button()
        self.page.locator("card-catalog-modal").wait_for(state="detached")
        print(f"'Select card to add' dialog is hidden")

    def click_widget_filter_button(self, widget_title):
        widget_dom = self.page.locator('custom-metric-widget', has=self.page.locator('.highcharts-title', has_text=widget_title))
        widget_dom.locator("custom-metrics-filter .widget-filter-button", has=self.page.locator(".ci-filter")).wait_for(state="visible")
        widget_dom.locator("custom-metrics-filter .widget-filter-button", has=self.page.locator(".ci-filter")).click()
        print(f"Clicked '{widget_title}' -> 'Filter' button")

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
