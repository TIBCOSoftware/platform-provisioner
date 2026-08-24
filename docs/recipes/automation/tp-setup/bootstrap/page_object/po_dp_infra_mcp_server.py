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

from utils.color_logger import ColorLogger
from utils.util import Util
from utils.env import ENV
from utils.report import ReportYaml
from page_object.po_dataplane import PageObjectDataPlane


class PageObjectDataPlaneInfraMcpServer(PageObjectDataPlane):
    capability = "inframcpserver"
    # The Infra MCP Server wizard is the shared "fresco" modal, whose footer navigation buttons
    # carry NO ids (unlike the #btnNextCapabilityProvision / #btnCapabilityProvision used by the
    # other capabilities), so they are matched by their footer container + exact label text.
    WIZARD_FOOTER = ".fresco-wizard-modal-footer-system-actions"

    def __init__(self, page):
        super().__init__(page)

    def infra_mcp_server_provision_capability(self, dp_name):
        capability = self.capability
        if ReportYaml.is_capability_for_dataplane_created(dp_name, capability):
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, capability '{capability}' is already created in DataPlane '{dp_name}'.")
            return
        ColorLogger.info("Infra MCP Server Provisioning capability...")
        self.goto_dataplane(dp_name)
        if self.page.locator(f"capability-card #{capability}").is_visible():
            ColorLogger.success("Infra MCP Server capability is already provisioned.")
            ReportYaml.set_capability(dp_name, capability)
            return

        print("Checking if 'Provision a capability' button is visible.")
        if not Util.check_dom_visibility(self.page, self.page.locator('button', has_text="Provision a capability"), 10, 100):
            Util.exit_error("'Provision a capability' button is not visible.", self.page, "infra_mcp_server_provision_capability.png")
            return

        print("'Provision a capability' button is visible.")
        ColorLogger.success(f"Data Plane '{dp_name}' status is running.")
        self.page.locator('button', has_text="Provision a capability").click()
        print("Clicked 'Provision a capability' button")
        self.page.wait_for_timeout(2000)
        print("Waiting for capability list is loaded")
        self.page.locator(".capability-select-container").wait_for(state="visible")
        if not Util.check_dom_visibility(self.page, self.page.locator(f'#{self.capability.upper()}-capability-select-button'), 5, 60):
            Util.exit_error("INFRAMCPSERVER capability 'Start' button is not visible.", self.page, "infra_mcp_server_provision_capability-1.png")
            return
        Util.click_button_until_enabled(self.page, self.page.locator(f'#{self.capability.upper()}-capability-select-button'))
        print("Clicked 'Provision Infra MCP Server' -> 'Start' button")

        # Step 1: Capability Configuration — accept defaults (Infra MCP has NO Resources step).
        #   Service Account "Create automatically" and fluentbit sidecar "Enabled" are pre-selected by the wizard.
        print("Waiting for Infra MCP Server 'Capability Configuration' step is loaded")
        next_button = self.page.locator(f'{self.WIZARD_FOOTER} button:text-is("Next")')
        if not Util.check_dom_visibility(self.page, next_button, 5, 60):
            Util.exit_error("Infra MCP Server 'Capability Configuration' step did not load.",
                            self.page, "infra_mcp_server_provision_capability-config.png")
            return
        self.page.wait_for_timeout(2000)

        # The End User Agreement checkbox is REQUIRED on this wizard: until it is checked, 'Next'
        # stays soft-disabled via CSS (pointer-events: none) while still reporting
        # disabled == false, so any wait keyed on the disabled property passes and the click then
        # fails as intercepted. The checkbox is a bare <input> sibling of its text (there is no
        # <label> wrapper), so clicking the text is a no-op — the input itself must be clicked.
        # Anchored on the agreement text because the container's CSS-module class is build-hashed.
        eua_checkbox = self.page.locator('div:has(> span:has-text("End User Agreement")) > input[type="checkbox"]')
        if not Util.check_dom_visibility(self.page, eua_checkbox, 5, 30):
            Util.exit_error("Infra MCP Server 'End User Agreement' checkbox is not visible.",
                            self.page, "infra_mcp_server_provision_capability-eua.png")
            return
        eua_checkbox.click()
        print("Accepted End User Agreement")

        # Playwright's actionability auto-wait covers the CSS soft-disable released by the EUA click.
        next_button.click(timeout=60000)
        print("Accepted Capability Configuration defaults, clicked Step 1 'Next'")

        # Step 2: Provision Capability — the footer button label is exactly "Provision".
        print("Waiting for Provision Capability step is loaded")
        self.page.wait_for_timeout(3000)

        provision_btn = self.page.locator(f'{self.WIZARD_FOOTER} button:text-is("Provision")')
        if not Util.check_dom_visibility(self.page, provision_btn, 5, 60):
            Util.exit_error("Infra MCP Server 'Provision Capability' button is not visible.", self.page, "infra_mcp_server_provision_capability-provision.png")
            return
        provision_btn.click(timeout=60000)
        print("Clicked 'Provision' button, waiting for Capability Provision Request Completed")

        # The success title is a plain <h2> under a build-hashed CSS-module class, so match on text.
        success_title = self.page.locator('h2:text-is("Capability Provision Request Completed")')
        if Util.check_dom_visibility(self.page, success_title, 5, 120):
            ColorLogger.success("Provision Infra MCP Server capability successful.")
        else:
            Util.exit_error("Infra MCP Server capability provision did not complete within timeout.", self.page, "infra_mcp_server_provision_timeout.png")

        done_button = self.page.locator('button:text-is("Done")')
        if done_button.is_visible():
            done_button.click()
            print("Clicked 'Done' button")
        elif self.page.locator("#capProvBackToDPBtn").is_visible():
            self.page.locator("#capProvBackToDPBtn").click()
            print("Clicked 'Go Back To Data Plane Details' button")
        else:
            ColorLogger.warning("Can not find 'Done' or 'Go Back To Data Plane Details' button")

        # Dismissing the wizard leaves the browser on the capability page, so navigate back to the
        # Data Plane explicitly before verifying the capability card.
        self.goto_dataplane(dp_name)

        print("Reload Data Plane page, and check if Infra MCP Server capability is provisioned...")
        Util.refresh_page(self.page)
        print("Waiting for Infra MCP Server capability is in capability list...")
        is_dataplane_container_available = Util.check_dom_visibility(self.page, self.page.locator(".data-plane-container"), 5, 20, True)
        if is_dataplane_container_available and self.is_capability_provisioned(capability):
            ColorLogger.success("Infra MCP Server capability is in capability list")
            ReportYaml.set_capability(dp_name, capability)
        else:
            Util.warning_screenshot("Infra MCP Server capability is not in capability list", self.page, "infra_mcp_server_provision_capability-2.png")
