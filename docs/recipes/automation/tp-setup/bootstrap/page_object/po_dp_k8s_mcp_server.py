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


class PageObjectDataPlaneK8sMcpServer(PageObjectDataPlane):
    capability = "k8smcpserver"

    def __init__(self, page):
        super().__init__(page)

    def k8s_mcp_server_provision_capability(self, dp_name):
        capability = self.capability
        if ReportYaml.is_capability_for_dataplane_created(dp_name, capability):
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, capability '{capability}' is already created in DataPlane '{dp_name}'.")
            return
        ColorLogger.info("Kubernetes MCP Server Provisioning capability...")
        self.goto_dataplane(dp_name)
        if self.page.locator(f"capability-card #{capability} .pl-tooltip__trigger", has_text="KubernetesMCPServer").is_visible():
            ColorLogger.success("Kubernetes MCP Server capability is already provisioned.")
            ReportYaml.set_capability(dp_name, capability)
            return

        print("Checking if 'Provision a capability' button is visible.")
        if not Util.check_dom_visibility(self.page, self.page.locator('button', has_text="Provision a capability"), 10, 100):
            Util.exit_error("'Provision a capability' button is not visible.", self.page, "k8s_mcp_server_provision_capability.png")
            return

        print("'Provision a capability' button is visible.")
        ColorLogger.success(f"Data Plane '{dp_name}' status is running.")
        self.page.locator('button', has_text="Provision a capability").click()
        print("Clicked 'Provision a capability' button")
        self.page.wait_for_timeout(2000)
        print("Waiting for capability list is loaded")
        self.page.locator(".capability-select-container").wait_for(state="visible")
        if not Util.check_dom_visibility(self.page, self.page.locator('#K8SMCPSERVER-capability-select-button'), 5, 10):
            Util.warning_screenshot("K8SMCPSERVER capability 'Start' button is not visible.", self.page, "k8s_mcp_server_provision_capability-1.png")
            return
        Util.click_button_until_enabled(self.page, self.page.locator('#K8SMCPSERVER-capability-select-button'))
        print("Clicked 'Provision Kubernetes MCP Server' -> 'Start' button")

        # Step 1: Resources — select a route resource
        print("Waiting for Kubernetes MCP Server resources page is loaded")
        self.page.locator(".resources-content").wait_for(state="visible")
        print("Kubernetes MCP Server resources page is loaded")
        self.page.wait_for_timeout(3000)

        ingress_table_sel = "#ingress-resource-table, #route-resource-table"
        if self.page.locator(ingress_table_sel).first.is_visible():
            ingress_name = ENV.TP_AUTO_INGRESS_CONTROLLER_K8S_MCP_SERVER
            self.page.locator(ingress_table_sel).first.locator(
                'tr', has=self.page.locator('td', has_text=ingress_name)
            ).locator('input[type="radio"]').check(force=True)
            print(f"Selected '{ingress_name}' Route Resource for Kubernetes MCP Server")

        self.page.locator("#btnNextCapabilityProvision", has_text="Next").click()
        print("Clicked Step 1 'Next' button")

        # Step 2: Capability Configuration — EUA checkbox
        print("Waiting for Capability Configuration step is loaded")
        self.page.wait_for_timeout(3000)

        self.page.locator("input[type='checkbox']").first.check(force=True)
        print("Clicked EUA checkbox")

        self.page.locator("button", has_text="Next").click()
        print("Clicked Step 2 'Next' button")

        # Step 3: Provision capability — recipe preview and provision
        print("Waiting for Provision Capability step is loaded")
        self.page.wait_for_timeout(3000)

        self.page.locator("button", has_text="Provision Kubernetes MCP Server").click()
        print("Clicked 'Provision Kubernetes MCP Server' button, waiting for Capability Provision Request Completed")

        if Util.check_dom_visibility(self.page, self.page.get_by_text("Capability Provision Request Completed"), 5, 120):
            ColorLogger.success("Provision Kubernetes MCP Server capability successful.")
        else:
            Util.exit_error("Kubernetes MCP Server capability provision did not complete within timeout.", self.page, "k8s_mcp_server_provision_timeout.png")

        self.page.locator("button", has_text="Go Back To Data Plane Details").click()
        print("Clicked 'Go Back To Data Plane Details' button")

        print("Reload Data Plane page, and check if Kubernetes MCP Server capability is provisioned...")
        Util.refresh_page(self.page)
        print("Waiting for Kubernetes MCP Server capability is in capability list...")
        is_dataplane_container_available = Util.check_dom_visibility(self.page, self.page.locator(".data-plane-container"), 5, 20, True)
        if is_dataplane_container_available and self.is_capability_provisioned(capability):
            ColorLogger.success("Kubernetes MCP Server capability is in capability list")
            ReportYaml.set_capability(dp_name, capability)
        else:
            Util.warning_screenshot("Kubernetes MCP Server capability is not in capability list", self.page, "k8s_mcp_server_provision_capability-2.png")
