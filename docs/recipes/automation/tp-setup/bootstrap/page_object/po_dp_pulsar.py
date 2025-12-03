#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary

from utils.color_logger import ColorLogger
from utils.util import Util
from utils.env import ENV
from utils.report import ReportYaml
from page_object.po_dataplane import PageObjectDataPlane

class PageObjectDataPlanePulsar(PageObjectDataPlane):
    capability = "pulsar"
    def __init__(self, page):
        super().__init__(page)

    def pulsar_provision_capability(self, dp_name, pulsar_server_name):
        capability = self.capability
        if ReportYaml.is_capability_for_dataplane_created(dp_name, capability):
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, capability '{capability}' is already created in DataPlane '{dp_name}'.")
            return
        capability_name = f"{pulsar_server_name}-dev"
        ColorLogger.info("Pulsar Provisioning capability...")
        self.goto_dataplane(dp_name)
        if self.page.locator("capability-card #pulsar .pl-tooltip__trigger", has_text=capability_name).is_visible():
            ColorLogger.success("Pulsar capability is already provisioned.")
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
            if not Util.check_dom_visibility(self.page, self.page.locator('#PULSAR-capability-select-button'), 5, 5):
                ColorLogger.warning("'Pulsar capability' has been removed from the capability list from CP version 1.10.x")
                Util.warning_screenshot("Pulsar capability 'Start' button is not visible.", self.page, "pulsar_provision_capability-1.png")
                return
            Util.click_button_until_enabled(self.page, self.page.locator('#PULSAR-capability-select-button'))
            print("Clicked 'Provision TIBCO® Messaging Quasar - Powered by Apache Pulsar™' -> 'Start' button")

            print("Waiting for Pulsar capability page is loaded")
            self.page.locator(".resources-content").wait_for(state="visible")
            print("Pulsar capability page is loaded")
            self.page.wait_for_timeout(3000)

            # step1: Resources
            if self.page.locator('#message-storage-resource-table').is_visible():
                self.page.locator('#message-storage-resource-table tr', has=self.page.locator('td', has_text=ENV.TP_AUTO_STORAGE_CLASS)).locator('label').wait_for(state="visible")
                self.page.locator('#message-storage-resource-table tr', has=self.page.locator('td', has_text=ENV.TP_AUTO_STORAGE_CLASS)).locator('label').click()
                print(f"Selected '{ENV.TP_AUTO_STORAGE_CLASS}' Message Storage")

            if self.page.locator('#journal-storage-resource-table').is_visible():
                self.page.locator('#journal-storage-resource-table tr', has=self.page.locator('td', has_text=ENV.TP_AUTO_STORAGE_CLASS)).locator('label').wait_for(state="visible")
                self.page.locator('#journal-storage-resource-table tr', has=self.page.locator('td', has_text=ENV.TP_AUTO_STORAGE_CLASS)).locator('label').click()
                print(f"Selected '{ENV.TP_AUTO_STORAGE_CLASS}' Journal Storage")

            if self.page.locator('#log-storage-resource-table').is_visible():
                self.page.locator('#log-storage-resource-table tr', has=self.page.locator('td', has_text=ENV.TP_AUTO_STORAGE_CLASS)).locator('label').wait_for(state="visible")
                self.page.locator('#log-storage-resource-table tr', has=self.page.locator('td', has_text=ENV.TP_AUTO_STORAGE_CLASS)).locator('label').click()
                print(f"Selected '{ENV.TP_AUTO_STORAGE_CLASS}' Log Storage")

            self.page.locator("#btnNextCapabilityProvision", has_text="Next").click()
            print("Clicked Pulsar step 1 'Next' button")

            # step2: Configuration
            self.page.locator("#cap-config-capability-instance").wait_for(state="visible")
            print("Waiting for Pulsar configuration step 2 is loaded")
            self.page.fill("#cap-config-capability-instance", pulsar_server_name)
            print(f"Filled Pulsar 'Server Name' with '{pulsar_server_name}'")
            self.page.locator("label[for='cap-config-eula']").click()
            print("Clicked Pulsar 'EUA' checkbox")
            self.page.locator("#btn_next_configuration", has_text="Next").click()
            print("Clicked Pulsar step 2 'Next' button")

            # step3: Custom Config
            print("Skipped Pulsar step 3")

            # step4: Configuration
            self.page.locator("#btn_next_confirmation", has_text="Provision TIBCO® Messaging Quasar - Powered by Apache Pulsar™").click()
            print("Clicked Pulsar step 4 'Provision TIBCO® Messaging Quasar - Powered by Apache Pulsar™' button, waiting for Pulsar Capability Provision Request Completed")

            if Util.check_dom_visibility(self.page, self.page.get_by_text("Pulsar server is provisioned and ready to use!"), 5, 60):
                ColorLogger.success("Provision Pulsar capability successful.")
                ReportYaml.set_capability(dp_name, capability)
            self.page.locator("#btn_go_to_dta_pln").click()
            print("Clicked 'Go Back To Data Plane Details' button")
        else:
            Util.exit_error("'Provision a capability' button is not visible.", self.page, "pulsar_provision_capability.png")

        print("Reload Data Plane page, and check if Pulsar capability is provisioned...")
        Util.refresh_page(self.page)
        print("Waiting for Pulsar capability is in capability list...")
        is_dataplane_container_available = Util.check_dom_visibility(self.page, self.page.locator(".data-plane-container"), 5, 20, True)
        if is_dataplane_container_available and self.is_capability_provisioned(capability, capability_name):
            ColorLogger.success(f"Pulsar capability {capability_name} is in capability list")
        else:
            Util.warning_screenshot(f"Pulsar capability {capability_name} is not in capability list", self.page, "pulsar_provision_capability-2.png")
