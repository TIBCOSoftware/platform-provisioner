#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary

from utils.color_logger import ColorLogger
from utils.util import Util
from utils.env import ENV
from utils.report import ReportYaml
from page_object.po_dataplane import PageObjectDataPlane

class PageObjectDataPlaneEMS(PageObjectDataPlane):
    capability = "ems"
    def __init__(self, page):
        super().__init__(page)

    def ems_provision_capability(self, dp_name, ems_server_name):
        capability = self.capability
        if ReportYaml.is_capability_for_dataplane_created(dp_name, capability):
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, capability '{capability}' is already created in DataPlane '{dp_name}'.")
            return
        capability_name = f"{ems_server_name}-dev"
        ColorLogger.info("EMS Provisioning capability...")
        self.goto_dataplane(dp_name)
        if self.page.locator("capability-card #ems .pl-tooltip__trigger", has_text=capability_name).is_visible():
            ColorLogger.success("EMS capability is already provisioned.")
            ReportYaml.set_capability(dp_name, capability)
            return

        print("Checking if 'Provision a capability' button is visible.")
        if Util.check_dom_visibility(self.page, self.page.locator('button', has_text="Provision a capability"), 10, 100):
            print("'Provision a capability' button is visible.")
            ColorLogger.success(f"Data Plane '{dp_name}' status is running.")
            self.page.locator('button', has_text="Provision a capability").click()
            print("Clicked 'Provision a capability' button")
            self.page.wait_for_timeout(2000)
            if not Util.check_dom_visibility(self.page, self.page.locator('#EMS-capability-select-button'), 5, 5):
                Util.warning_screenshot("EMS capability 'Start' button is not visible.", self.page, "ems_provision_capability-1.png")
                return
            Util.click_button_until_enabled(self.page, self.page.locator('#EMS-capability-select-button'))
            print("Clicked 'Provision TIBCO Enterprise Message Service™' -> 'Start' button")

            print("Waiting for EMS capability page is loaded")
            self.page.locator(".resources-content").wait_for(state="visible")
            print("EMS capability page is loaded")
            self.page.wait_for_timeout(3000)

            # step1: Resources
            if self.page.locator('#message-storage-resource-table').is_visible():
                self.page.locator('#message-storage-resource-table tr', has=self.page.locator('td', has_text=ENV.TP_AUTO_STORAGE_CLASS)).locator('label').wait_for(state="visible")
                self.page.locator('#message-storage-resource-table tr', has=self.page.locator('td', has_text=ENV.TP_AUTO_STORAGE_CLASS)).locator('label').click()
                print(f"Selected '{ENV.TP_AUTO_STORAGE_CLASS}' Message Storage")

            if self.page.locator('#log-storage-resource-table').is_visible():
                self.page.locator('#log-storage-resource-table tr', has=self.page.locator('td', has_text=ENV.TP_AUTO_STORAGE_CLASS)).locator('label').wait_for(state="visible")
                self.page.locator('#log-storage-resource-table tr', has=self.page.locator('td', has_text=ENV.TP_AUTO_STORAGE_CLASS)).locator('label').click()
                print(f"Selected '{ENV.TP_AUTO_STORAGE_CLASS}' Log Storage")

            self.page.locator("#btnNextCapabilityProvision", has_text="Next").click()
            print("Clicked EMS step 1 'Next' button")

            # step2: Configuration
            self.page.locator("#ems-config-capability-instance").wait_for(state="visible")
            print("Waiting for EMS configuration step 2 is loaded")
            self.page.fill("#ems-config-capability-instance", ems_server_name)
            print(f"Filled EMS 'Server Name' with '{ems_server_name}'")
            self.page.locator("label[for='ems-config-eula']").click()
            print("Clicked EMS 'EUA' checkbox")
            self.page.locator("#btn_next_configuration", has_text="Next").click()
            print("Clicked EMS step 2 'Next' button")

            # step3: Custom Config
            print("Skipped EMS step 3")

            # step4: Configuration
            self.page.locator("#btn_next_confirmation", has_text="Provision TIBCO Enterprise Message Service").click()
            print("Clicked EMS step 4 'Provision TIBCO Enterprise Message Service' button, waiting for EMS Capability Provision Request Completed")

            if Util.check_dom_visibility(self.page, self.page.get_by_text("EMS server is provisioned and ready to use!"), 5, 60):
                ColorLogger.success("Provision EMS capability successful.")
            self.page.locator("#btn_go_to_dta_pln").click()
            print("Clicked 'Go Back To Data Plane Details' button")
        else:
            Util.exit_error("'Provision a capability' button is not visible.", self.page, "ems_provision_capability.png")

        print("Reload Data Plane page, and check if EMS capability is provisioned...")
        Util.refresh_page(self.page)
        print("Waiting for EMS capability is in capability list...")
        is_dataplane_container_available = Util.check_dom_visibility(self.page, self.page.locator(".data-plane-container"), 5, 20, True)
        if is_dataplane_container_available and self.is_capability_provisioned(capability, capability_name):
            ColorLogger.success(f"EMS capability {capability_name} is in capability list")
            ReportYaml.set_capability(dp_name, capability)
        else:
            Util.warning_screenshot(f"EMS capability {capability_name} is not in capability list", self.page, "ems_provision_capability-2.png")
