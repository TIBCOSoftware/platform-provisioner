#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary
from page_object.po_global import PageObjectGlobal
from utils.color_logger import ColorLogger
from utils.env import ENV
from utils.report import ReportYaml
from utils.util import Util

class PageObjectUserManagement(PageObjectGlobal):
    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.env = ENV

    def grant_permission(self, permission, checked="true"):
        ColorLogger.info(f"Granting permission for {permission}...")
        self.page.locator(".policy-description", has_text=permission).click()
        input_selectors = self.page.locator('.dp-selector-container input').all()
        for input_selector in input_selectors:
            # check if input aria-checked="true" does not exist, then click
            is_selected = input_selector.get_attribute("aria-checked")
            print(f"Permission {permission} is selected: {is_selected}")
            if is_selected != checked:
                input_selector.locator("xpath=..").locator("label").click()

                print("Grant permission for " + permission)

    def goto_assign_permissions(self):
        print("Start set user permission...")
        self.page.click("#nav-bar-menu-item-usrMgmt")
        self.page.click("#users-menu-item")
        self.page.locator(f'.user-name-text[id="go-to-user-details-{ENV.DP_USER_EMAIL}"]').wait_for(state="visible")
        print(f"{ENV.DP_USER_EMAIL} is found.")

        self.page.locator("team-members tr", has=self.page.locator(f'.user-name-text[id="go-to-user-details-{ENV.DP_USER_EMAIL}"]')).locator("dropdown-button button#changeME-dropdown-label").click()
        print(f"Click on dropdown button for user {ENV.DP_USER_EMAIL}")
        self.page.locator(".pl-dropdown-menu__action", has_text="Update permissions").wait_for(state="visible")
        self.page.locator(".pl-dropdown-menu__action", has_text="Update permissions").click()
        print(f"Clicked 'Update permissions' from dropdown list")

        self.page.locator(".policy-selector-container").wait_for(state="visible")
        print("Assign permissions page is loaded.")

    def set_user_permission(self):
        if ReportYaml.get(".ENV.REPORT_USER_PERMISSION") == "true":
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, user permission is already set.")
            return
        ColorLogger.info("Setting user permission...")
        self.goto_left_navbar("Data Planes")
        self.page.locator("#register-dp-button").wait_for(state="visible")
        print("Checking if user has permission...")
        if not self.page.locator("#register-dp-button").is_disabled():
            ColorLogger.success(f"User {ENV.DP_USER_EMAIL} already has all permissions.")
            ReportYaml.set(".ENV.REPORT_USER_PERMISSION", True)
            return

        self.goto_assign_permissions()
        print(f"Assign Permissions for {ENV.DP_USER_EMAIL}")
        # if it has 8 green icons, then exit this function
        if self.page.locator(".policy-selector-container .green-check-icon").count() >= 8:
            ColorLogger.success(f"User {ENV.DP_USER_EMAIL} already has all permissions.")
            ReportYaml.set(".ENV.REPORT_USER_PERMISSION", True)
            return

        self.grant_permission("IdP Manager")
        self.grant_permission("Team Admin")
        self.grant_permission("Data plane Manager")
        self.grant_permission("Capability Manager")
        self.grant_permission("Application Manager")
        self.grant_permission("Application Viewer")
        self.grant_permission("View permissions")
        # if button is not disabled, then click
        if not self.page.locator("#next-assign-permissions").is_disabled():
            self.page.click("#next-assign-permissions")
            self.page.click("#assign-permissions-update")
            ColorLogger.success(f"Grant All permission to {ENV.DP_USER_EMAIL}")
            ReportYaml.set(".ENV.REPORT_USER_PERMISSION", True)
        else:
            ColorLogger.success(f"User {ENV.DP_USER_EMAIL} already has all permissions.")
            ReportYaml.set(".ENV.REPORT_USER_PERMISSION", True)

    def grant_product_permission(self, dp_name, app_name):
        permission = "Product Permission"
        ColorLogger.info(f"Granting  {permission} for "+ dp_name + " => " + app_name)
        self.goto_assign_permissions()
        print("Checking if product permission is visible...")
        if Util.check_dom_visibility(self.page, self.page.locator(".policy-description", has_text=permission), 2, 4):
            print("Product permission is visible.")
            self.page.locator(".policy-description", has_text=permission).click()
            print("Checking product permission for " + dp_name + " => " + app_name)

            dataplane_selector = self.page.locator('.dataplane-selector', has=self.page.locator('.dp-name-text', has_text=dp_name))
            if Util.check_dom_visibility(self.page, dataplane_selector, 2, 4):
                print("Dataplane " + dp_name + " is found in product permission list.")
                dataplane_selector.click()
                print("Clicked on dataplane " + dp_name)

                app_selector = dataplane_selector.locator(".products-container .product-item", has_text=app_name)
                if Util.check_dom_visibility(self.page, app_selector, 2, 4):
                    print("Product " + dp_name + " => " + app_name + " is found in product permission list.")
                    app_selector.click()
                    print("Clicked on product " + dp_name + " => " + app_name)

                    is_all_domain_checked = self.page.locator(".domain-selector-container .wildcard-domains-checkbox input").get_attribute("aria-checked")
                    if is_all_domain_checked != "true":
                        self.page.locator(".domain-selector-container .wildcard-domains-checkbox label", has_text="All current and future domains").click()
                        is_all_domain_checked = "true"
                        print("Clicked on 'All current and future domains' for " + dp_name + " => " + app_name)

                    is_write_selected = self.page.locator(".domains-table-container .pl-table__header input[name='allDomainsWriteSelected']").get_attribute("aria-checked")
                    if is_write_selected != "true":
                        self.page.locator(".domains-table-container .pl-table__header label", has_text="Write").click()
                        is_write_selected = "true"
                        print("Clicked on 'Write' permission for " + dp_name + " => " + app_name)

                    print("All current and future domains: " + is_all_domain_checked)
                    print("Write permission: " + is_write_selected)

                    if not self.page.locator("#next-assign-permissions").is_disabled():
                        self.page.click("#next-assign-permissions")
                        self.page.click("#assign-permissions-update")
                        ColorLogger.success(f"Grant All permission to {ENV.DP_USER_EMAIL}")
                        ReportYaml.set(".ENV.REPORT_USER_PERMISSION", True)
                    else:
                        ColorLogger.warning("Next button is disabled, nothing to update.")
                else:
                    ColorLogger.warning(f"Product {dp_name} => {app_name} is not found in product permission list.")
            else:
                ColorLogger.warning(f"Dataplane {dp_name} is not found in product permission list.")
        else:
            ColorLogger.info("Product permission is not visible, skipping...")
