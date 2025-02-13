from utils.color_logger import ColorLogger
from utils.util import Util
from utils.env import ENV
from utils.report import ReportYaml
from page_object.po_dataplane import PageObjectDataPlane

class PageObjectDataPlaneBWCE(PageObjectDataPlane):
    capability = "bwce"
    def __init__(self, page):
        super().__init__(page)

    def bwce_provision_capability(self, dp_name):
        capability = self.capability
        if ReportYaml.is_capability_for_dataplane_created(dp_name, capability):
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, capability '{capability}' is already created in DataPlane '{dp_name}'.")
            return
        ColorLogger.info("BWCE Provisioning capability...")
        self.goto_dataplane(dp_name)
        if self.page.locator("capability-card #bwce").is_visible():
            ColorLogger.success("BWCE capability is already provisioned.")
            ReportYaml.set_capability(dp_name, capability)
            return

        print("Checking if 'Provision a capability' button is visible.")
        if Util.check_dom_visibility(self.page, self.page.locator('button', has_text="Provision a capability"), 10, 100):
            print("'Provision a capability' button is visible.")
            ColorLogger.success(f"Data Plane '{dp_name}' status is running.")
            self.page.locator('button', has_text="Provision a capability").click()
            print("Clicked 'Provision a capability' button")
            self.page.wait_for_timeout(2000)
            Util.click_button_until_enabled(self.page, self.page.locator('#BWCE-capability-select-button'))
            print("Clicked 'Provision TIBCO BusinessWorks™ Container Edition' -> 'Start' button")

            print("Waiting for BWCE capability page is loaded")
            self.page.locator(".resources-content").wait_for(state="visible")
            print("BWCE capability page is loaded")
            self.page.wait_for_timeout(3000)

            if self.page.locator('#storage-class-resource-table').is_visible():
                self.page.locator('#storage-class-resource-table tr', has=self.page.locator('td', has_text=ENV.TP_AUTO_STORAGE_CLASS)).locator('label').wait_for(state="visible")
                self.page.locator('#storage-class-resource-table tr', has=self.page.locator('td', has_text=ENV.TP_AUTO_STORAGE_CLASS)).locator('label').click()
                print(f"Selected '{ENV.TP_AUTO_STORAGE_CLASS}' Storage Class for BWCE capability")

            if self.page.locator('#ingress-resource-table').is_visible():
                self.page.locator('#ingress-resource-table tr', has=self.page.locator('td', has_text=ENV.TP_AUTO_INGRESS_CONTROLLER_BWCE)).locator('label').wait_for(state="visible")
                self.page.locator('#ingress-resource-table tr', has=self.page.locator('td', has_text=ENV.TP_AUTO_INGRESS_CONTROLLER_BWCE)).locator('label').click()
                print(f"Selected '{ENV.TP_AUTO_INGRESS_CONTROLLER_BWCE}' Ingress Controller for BWCE capability")

            self.page.locator("#btnNextCapabilityProvision", has_text="Next").click()
            print("Clicked BWCE 'Next' button, finished step 1")
            self.page.locator(".resource-agree label").click()
            print("Clicked BWCE 'EUA' checkbox")
            self.page.locator("#btnNextCapabilityProvision", has_text="BWCE Provision Capability").click()
            print("Clicked 'BWCE Provision Capability' button, waiting for BWCE Capability Provision Request Completed")
            if Util.check_dom_visibility(self.page, self.page.locator(".resource-success .title", has_text="Capability Provision Request Completed"), 5, 60):
                ColorLogger.success("Provision Flogo capability successful.")
            self.page.locator("#capProvBackToDPBtn").click()
            print("Clicked 'Go Back To Data Plane Details' button")
        else:
            Util.exit_error("'Provision a capability' button is not visible.", self.page, "bwce_provision_capability.png")

        print("Reload Data Plane page, and check if BWCE capability is provisioned...")
        Util.refresh_page(self.page)
        print("Waiting for BWCE capability is in capability list...")
        self.page.locator(".data-plane-container").wait_for(state="visible")
        if self.is_capability_provisioned(capability):
            ColorLogger.success("BWCE capability is in capability list")
            ReportYaml.set_capability(dp_name, capability)
        else:
            Util.warning_screenshot("BWCE capability is not in capability list", self.page, "bwce_provision_capability-2.png")
