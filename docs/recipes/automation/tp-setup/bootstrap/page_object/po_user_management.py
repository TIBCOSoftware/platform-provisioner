#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary

from utils.color_logger import ColorLogger
from utils.env import ENV
from utils.report import ReportYaml

class PageObjectUserManagement:
    def __init__(self, page):
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

    # TODO: remove this function after bug: PCP-11136 is fixed
    def set_user_permission_for_bug(self):
        print("For bug: PCP-11136, Start set user permission...")
        self.page.click("#nav-bar-menu-item-usrMgmt")
        self.page.click("#users-menu-item")
        self.page.locator(f'.user-name-text[id="go-to-user-details-{ENV.DP_USER_EMAIL}"]').wait_for(state="visible")
        print(f"{ENV.DP_USER_EMAIL} is found.")

        self.page.locator("team-members tr", has=self.page.locator(f'.user-name-text[id="go-to-user-details-{ENV.DP_USER_EMAIL}"]')).locator("dropdown-button button#changeME-dropdown-label").click()
        print(f"Click on dropdown button for user {ENV.DP_USER_EMAIL}")
        self.page.locator(".pl-dropdown-menu__action", has_text="Update permissions").wait_for(state="visible")
        self.page.locator(".pl-dropdown-menu__action", has_text="Update permissions").click()
        print(f"Clicked 'Update permissions' from dropdown list")

        self.page.wait_for_timeout(1000)
        print(f"Assign Permissions for {ENV.DP_USER_EMAIL}")

        self.grant_permission("Data plane Manager")
        self.grant_permission("Capability Manager")
        self.grant_permission("Application Manager")

        if not self.page.locator("#next-assign-permissions").is_disabled():
            self.page.click("#next-assign-permissions")
            self.page.click("#assign-permissions-update")
            ColorLogger.success(f"Grant permission to {ENV.DP_USER_EMAIL}")
        else:
            ColorLogger.warning(f"Nothing changed for user permission.")

        print("For bug: PCP-11136, End set user permission...")

    def set_user_permission(self):
        if ReportYaml.get(".ENV.REPORT_USER_PERMISSION") == "true":
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, user permission is already set.")
            return
        ColorLogger.info("Setting user permission...")
        self.page.locator("#nav-bar-menu-list-dataPlanes").wait_for(state="visible")
        self.page.click("#nav-bar-menu-list-dataPlanes")
        self.page.locator("#register-dp-button").wait_for(state="visible")
        print("Checking if user has permission...")
        if not self.page.locator("#register-dp-button").is_disabled():
            ColorLogger.success(f"User {ENV.DP_USER_EMAIL} already has all permissions.")
            ReportYaml.set(".ENV.REPORT_USER_PERMISSION", True)
            return

        # self.set_user_permission_for_bug()

        print("Start set user permission...")
        self.page.click("#nav-bar-menu-item-usrMgmt")
        self.page.click("#users-menu-item")
        self.page.locator(f'.user-name-text[id="go-to-user-details-{ENV.DP_USER_EMAIL}"]').wait_for(state="visible")
        print(f"{ENV.DP_USER_EMAIL} is found.")
        # check if user has all permissions
        # self.page.locator(f'.user-name-text[id="go-to-user-details-{ENV.DP_USER_EMAIL}"]').click()

        # self.page.wait_for_timeout(1000)
        # print(f"Assign Permissions for {ENV.DP_USER_EMAIL}")
        # # if table.permissions has 8 rows, then exit this function
        # if self.page.locator("table.permissions .pl-table__row").count() == 8:
        #     ColorLogger.success(f"User {ENV.DP_USER_EMAIL} already has all permissions.")
        #     ReportYaml.set(".ENV.REPORT_USER_PERMISSION", True)
        #     return

        # self.page.click("#assign-permissions-btn")

        self.page.locator("team-members tr", has=self.page.locator(f'.user-name-text[id="go-to-user-details-{ENV.DP_USER_EMAIL}"]')).locator("dropdown-button button#changeME-dropdown-label").click()
        print(f"Click on dropdown button for user {ENV.DP_USER_EMAIL}")
        self.page.locator(".pl-dropdown-menu__action", has_text="Update permissions").wait_for(state="visible")
        self.page.locator(".pl-dropdown-menu__action", has_text="Update permissions").click()
        print(f"Clicked 'Update permissions' from dropdown list")

        self.page.wait_for_timeout(1000)
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
