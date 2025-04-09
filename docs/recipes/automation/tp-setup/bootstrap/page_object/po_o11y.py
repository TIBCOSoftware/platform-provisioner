from page_object.po_global import PageObjectGlobal

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

    def reset_layout(self):
        self.page.locator(".dashboard-actions-row button.test-reset-layout").click()
        print(f"Clicked 'Reset Layout' icon")
        self.page.locator(".dashboard-actions-row .p-menuitem-link span", has_text="Reset Layout").wait_for(state="visible")
        self.page.locator(".dashboard-actions-row .p-menuitem-link span", has_text="Reset Layout").click()
        print(f"Clicked 'Reset Layout' Button")

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

