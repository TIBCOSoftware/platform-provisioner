#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary

from utils.color_logger import ColorLogger
from utils.util import Util
from utils.env import ENV
from utils.report import ReportYaml
from page_object.po_dataplane import PageObjectDataPlane

class PageObjectDataPlaneTibcoHub(PageObjectDataPlane):
    capability = "tibcohub"
    def __init__(self, page):
        super().__init__(page)

    def tibcohub_provision_capability(self, dp_name, hub_name):
        capability = self.capability
        if ReportYaml.is_capability_for_dataplane_created(dp_name, capability):
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, capability '{capability}' is already created in DataPlane '{dp_name}'.")
            return
        capability_name = f"{hub_name}"
        ColorLogger.info("TibcoHub Provisioning capability...")
        self.goto_dataplane(dp_name)
        if self.page.locator("capability-card #tibcohub .pl-tooltip__trigger", has_text=capability_name).is_visible():
            ColorLogger.success("TibcoHub capability is already provisioned.")
            ReportYaml.set_capability(dp_name, capability)
            return

        print("Checking if 'Provision a capability' button is visible.")
        if Util.check_dom_visibility(self.page, self.page.locator('button', has_text="Provision a capability"), 10, 100):
            print("'Provision a capability' button is visible.")
            ColorLogger.success(f"Data Plane '{dp_name}' status is running.")
            self.page.locator('button', has_text="Provision a capability").click()
            print("Clicked 'Provision a capability' button")
            self.page.wait_for_timeout(2000)
            print(f"Waiting for capability list is loaded")
            self.page.locator(".capability-select-container").wait_for(state="visible")
            if not Util.check_dom_visibility(self.page, self.page.locator('#TIBCOHUB-capability-select-button'), 5, 5):
                Util.warning_screenshot("TIBCOHUB capability 'Start' button is not visible.", self.page, "tibcohub_provision_capability-1.png")
                return
            Util.click_button_until_enabled(self.page, self.page.locator('#TIBCOHUB-capability-select-button'))
            print("Clicked 'Provision TIBCO® Developer Hub' -> 'Start' button")

            print("Waiting for TibcoHub capability page is loaded")
            self.page.locator(".resources-content").wait_for(state="visible")
            print("TibcoHub capability page is loaded")
            self.page.wait_for_timeout(3000)

            # step1: Resources for TibcoHub capability
            if self.page.locator('#storage-class-resource-table').is_visible():
                self.page.locator('#storage-class-resource-table tr', has=self.page.locator('td', has_text=ENV.TP_AUTO_STORAGE_CLASS)).locator('label').wait_for(state="visible")
                self.page.locator('#storage-class-resource-table tr', has=self.page.locator('td', has_text=ENV.TP_AUTO_STORAGE_CLASS)).locator('label').click()
                print(f"Selected '{ENV.TP_AUTO_STORAGE_CLASS}' Storage Class for TibcoHub capability")

            if self.page.locator('#ingress-resource-table').is_visible():
                self.page.locator('#ingress-resource-table tr', has=self.page.locator('td', has_text=ENV.TP_AUTO_INGRESS_CONTROLLER_TIBCOHUB)).locator('label').wait_for(state="visible")
                self.page.locator('#ingress-resource-table tr', has=self.page.locator('td', has_text=ENV.TP_AUTO_INGRESS_CONTROLLER_TIBCOHUB)).locator('label').click()
                print(f"Selected '{ENV.TP_AUTO_INGRESS_CONTROLLER_TIBCOHUB}' Ingress Controller for TibcoHub capability")

            self.page.locator("#btnNextCapabilityProvision", has_text="Next").click()
            print("Clicked TibcoHub step 1 'Next' button")

            # step2: Configuration
            self.page.locator("#thub-config-capability-instance").wait_for(state="visible")
            print("Waiting for TibcoHub configuration step 2 is loaded")
            self.page.fill("#thub-config-capability-instance", hub_name)
            print(f"Filled TibcoHub 'Developer Hub Name' with '{hub_name}'")
            self.page.locator("label[for='thub-config-eula']").click()
            print("Clicked TibcoHub 'EUA' checkbox")
            self.page.locator("#btn_next_configuration", has_text="Next").click()
            print("Clicked TibcoHub step 2 'Next' button")

            # step3: Custom Configuration
            self.page.locator("#btn_next_custom_configuration", has_text="Next").click()
            print("Clicked TibcoHub step 3 'Next' button")

            # step4: Confirmation
            self.page.locator("#btn_next_confirmation", has_text="Next").click()
            print("Clicked TibcoHub step 4 'Next' button, waiting for TibcoHub Capability Provision Request Completed")

            if Util.check_dom_visibility(self.page, self.page.get_by_text("Sit back while we provision your capability"), 5, 60):
                ColorLogger.success("Provision TibcoHub capability successful.")
            self.page.locator("#btn_go_to_dta_pln").click()
            print("Clicked 'Go Back To Data Plane Details' button")
        else:
            Util.exit_error("'Provision a capability' button is not visible.", self.page, "tibcohub_provision_capability.png")

        print("Reload Data Plane page, and check if TibcoHub capability is provisioned...")
        Util.refresh_page(self.page)
        print("Waiting for TibcoHub capability is in capability list...")
        is_dataplane_container_available = Util.check_dom_visibility(self.page, self.page.locator(".data-plane-container"), 5, 20, True)
        if is_dataplane_container_available and self.is_capability_provisioned(capability, capability_name):
            ColorLogger.success(f"TibcoHub capability {capability_name} is in capability list")
            ReportYaml.set_capability(dp_name, capability)
        else:
            ColorLogger.warning(f"TibcoHub capability {capability_name} is not in capability list")
