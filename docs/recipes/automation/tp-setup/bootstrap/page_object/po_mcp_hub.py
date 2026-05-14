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

import re

from page_object.po_global import PageObjectGlobal
from utils.color_logger import ColorLogger
from utils.env import ENV
from utils.util import Util


class PageObjectMcpHub(PageObjectGlobal):
    def __init__(self, page):
        super().__init__(page)

    def goto_mcp_hub(self):
        """Navigate to MCP Hub page via left sidebar."""
        ColorLogger.info("Navigating to MCP Hub...")
        self.page.locator("text=MCP Hub").click()
        self.page.wait_for_timeout(2000)
        ColorLogger.success("Navigated to MCP Hub page")

    def goto_dataplane(self, dp_name):
        """Navigate to a specific Data Plane detail page in MCP Hub."""
        ColorLogger.info(f"Navigating to Data Plane '{dp_name}' in MCP Hub...")
        self.page.get_by_role("link", name=dp_name).click()
        self.page.wait_for_timeout(3000)
        ColorLogger.success(f"Navigated to Data Plane '{dp_name}'")

    def is_gateway_deployed(self):
        """Check if MCP Gateway is deployed on current Data Plane."""
        return not self.page.locator("text=MCP Gateway Not Deployed").is_visible(timeout=5000)

    def is_gateway_online(self):
        """Check if MCP Gateway status is online."""
        if Util.check_dom_visibility(self.page, self.page.locator("span.p-tag-label", has_text="online"), 1, 2):
            return True
        return Util.check_dom_visibility(self.page, self.page.locator("text=online").first, 1, 2)

    def _wait_for_gateway_online(self):
        """Wait for MCP Gateway to come online (up to 15 minutes).
        Reloads the page each iteration since status doesn't auto-refresh.
        """
        if self.is_gateway_online():
            ColorLogger.success("MCP Gateway is online!")
            return

        ColorLogger.info("Waiting for MCP Gateway to come online...")
        for i in range(30):  # Up to 15 minutes
            self.page.wait_for_timeout(30000)
            self.page.reload(wait_until="domcontentloaded")
            self.page.wait_for_timeout(2000)
            if self.is_gateway_online():
                ColorLogger.success("MCP Gateway is online!")
                return
            ColorLogger.info(f"Still waiting... ({(i+1)*30}s)")

        Util.exit_error("MCP Gateway did not come online within 15 minutes", self.page, "mcp_gateway_not_online.png")

    def deploy_mcp_gateway(self, dp_name):
        """Deploy MCP Gateway on a Data Plane via the provisioning wizard.

        CP >= 1.17 uses a 5-step wizard; older versions use 3 steps.

        Steps:
          1. Network Access — select ingress controller (or create one)
          2. Deployment Mode — select storage class, keep Lite mode defaults
          3. Advanced (CP >= 1.17) — accept defaults (path prefix, logs)
          4. Gateway Configuration (CP >= 1.17) — accept auth defaults
          5. Review — accept defaults and click Deploy

        Args:
            dp_name: Data Plane name (ingress pattern: mcp-<dp_name>)
        """
        if not self.is_gateway_deployed():
            ColorLogger.info(f"Deploying MCP Gateway for '{dp_name}'...")

            self.page.get_by_role("button", name="Deploy MCP Gateway").click()
            self.page.wait_for_timeout(1000)

            dialog = self.page.get_by_role("dialog", name="Provisioning MCP Gateway")

            # --- Step 1: Network Access (was Resource Selection) ---
            self._wizard_step1_resource_selection(dialog, dp_name)

            # --- Step 2: Deployment Mode (was Capability Configuration) ---
            self._wizard_step2_capability_configuration(dialog)

            # --- Step 3: Advanced (CP >= 1.17) ---
            if Util.check_dom_visibility(self.page, dialog.locator("text=Enable Path Prefix"), 1, 3):
                self._wizard_step3_advanced(dialog)

            # --- Step 4: Gateway Configuration (CP >= 1.17) ---
            if Util.check_dom_visibility(self.page, dialog.locator("text=MCP Client Authentication"), 1, 3):
                self._wizard_step4_gateway_configuration(dialog)

            # --- Final Step: Review — accept defaults and deploy ---
            ColorLogger.info("Review — accepting defaults")
            deploy_btn = dialog.get_by_role("button", name="Deploy MCP Gateway")
            deploy_btn.click()
            self.page.wait_for_timeout(3000)
            ColorLogger.info("Deploy MCP Gateway submitted")
        else:
            ColorLogger.info("MCP Gateway already deployed")

        self._wait_for_gateway_online()

    def _wizard_step1_resource_selection(self, dialog, dp_name):
        """Handle Step 1 of the provisioning wizard: select or create ingress."""
        ColorLogger.info("Step 1: Resource Selection")
        ingress_name = f"mcp-{dp_name}"

        row = dialog.locator("tr", has_text=ingress_name)
        if Util.check_dom_visibility(self.page, row, 1, 3):
            row.locator("input[type='radio']").check(force=True)
            ColorLogger.info(f"Selected existing ingress: {ingress_name}")
        else:
            ColorLogger.info(f"Ingress '{ingress_name}' not found, creating one...")
            self._create_ingress_controller(dialog, ingress_name, dp_name)
            row = dialog.locator("tr", has_text=ingress_name)
            row.locator("input[type='radio']").check(force=True)
            ColorLogger.info(f"Selected newly created ingress: {ingress_name}")

        dialog.get_by_role("button", name="Next").click()
        self.page.wait_for_timeout(1000)
        ColorLogger.success("Step 1 completed")

    def _wizard_step2_capability_configuration(self, dialog):
        """Handle Step 2 of the provisioning wizard: deployment mode + storage class."""
        ColorLogger.info("Step 2: Capability Configuration")

        storage_class = ENV.TP_AUTO_STORAGE_CLASS
        storage_row = dialog.locator("tr", has_text=storage_class)
        if Util.check_dom_visibility(self.page, storage_row, 1, 3):
            storage_row.locator("input[type='radio']").check(force=True)
            ColorLogger.info(f"Selected storage class: {storage_class}")
        else:
            ColorLogger.info(f"Storage class '{storage_class}' not found, creating...")
            self._create_storage_class(dialog, storage_class)
            storage_row = dialog.locator("tr", has_text=storage_class)
            storage_row.locator("input[type='radio']").check(force=True)
            ColorLogger.info(f"Selected newly created storage class: {storage_class}")

        dialog.get_by_role("button", name="Next").click()
        self.page.wait_for_timeout(1000)
        ColorLogger.success("Step 2 completed")

    def _wizard_step3_advanced(self, dialog):
        """Handle Step 3 of the provisioning wizard (CP >= 1.17): accept advanced defaults."""
        ColorLogger.info("Step 3: Advanced — accepting defaults")
        dialog.get_by_role("button", name="Next").click()
        self.page.wait_for_timeout(1000)
        ColorLogger.success("Step 3 completed")

    def _wizard_step4_gateway_configuration(self, dialog):
        """Handle Step 4 of the provisioning wizard (CP >= 1.17): accept auth defaults."""
        ColorLogger.info("Step 4: Gateway Configuration — accepting defaults")
        dialog.get_by_role("button", name="Next").click()
        self.page.wait_for_timeout(1000)
        ColorLogger.success("Step 4 completed")

    def _create_storage_class(self, wizard_dialog, storage_class):
        """Create a new Storage Class resource inside the deploy wizard step 2.

        Args:
            wizard_dialog: Locator for the Provisioning MCP Gateway dialog
            storage_class: Storage class name (e.g. 'hostpath')
        """
        wizard_dialog.get_by_role("button", name="Add Storage Class").click()
        self.page.wait_for_timeout(1000)

        add_dialog = self.page.get_by_role("dialog", name="Add Storage Class")

        add_dialog.get_by_placeholder("Enter resource name").fill(storage_class)
        add_dialog.get_by_placeholder("Enter description").fill(storage_class)
        add_dialog.get_by_placeholder("Enter Storage Class Name").fill(storage_class)

        add_dialog.get_by_role("button", name="Add").click()
        self.page.wait_for_timeout(2000)
        ColorLogger.success(f"Storage class '{storage_class}' created")

    def _create_ingress_controller(self, deploy_dialog, ingress_name, dp_name):
        """Create a new Ingress Controller resource inside the deploy wizard step 1.

        Args:
            deploy_dialog: Locator for the Provisioning MCP Gateway dialog
            ingress_name: Resource name (e.g. 'mcp-dp3')
            dp_name: Data Plane name for FQDN (e.g. 'dp3')
        """
        ingress_controller = ENV.TP_AUTO_INGRESS_CONTROLLER
        fqdn = f"mcp-hub-{dp_name}.{ENV.TP_AUTO_CP_DNS_DOMAIN}"

        deploy_dialog.get_by_role("button", name="Add Ingress Controller").click()
        self.page.wait_for_timeout(1000)

        add_dialog = self.page.get_by_role("dialog", name="Add Ingress Controller")

        add_dialog.get_by_placeholder("Enter resource name").fill(ingress_name)

        add_dialog.get_by_role("button", name="dropdown trigger").click()
        self.page.wait_for_timeout(500)
        self.page.get_by_role("listbox").get_by_text(
            ingress_controller, exact=True
        ).click()
        self.page.wait_for_timeout(500)
        ColorLogger.info(f"Selected ingress controller: {ingress_controller}")

        add_dialog.get_by_placeholder("Enter Ingress Class Name").fill(ingress_controller)

        add_dialog.get_by_placeholder("Enter Default FQDN").fill(fqdn)
        ColorLogger.info(f"FQDN: {fqdn}")

        add_dialog.get_by_role("button", name="Add").click()
        self.page.wait_for_timeout(2000)
        ColorLogger.success(f"Ingress controller '{ingress_name}' created")

    def _delete_mcp_server(self, name):
        """Delete an MCP Server by name from the MCP Servers tab."""
        row = self.page.locator("tr", has_text=name)
        row.get_by_role("button").last.click()
        self.page.wait_for_timeout(500)
        confirm_btn = self.page.get_by_role("button", name="Yes")
        if confirm_btn.is_visible(timeout=2000):
            confirm_btn.click()
        self.page.wait_for_timeout(2000)
        ColorLogger.info(f"Deleted MCP server '{name}'")

    def add_mcp_server(self, name, url, token="", auth_type="Bearer Token"):
        """Add an MCP Server configuration. If server exists with sync failed, recreate it.

        Args:
            name: Server name (e.g. 'cp-mcp-server')
            url: Server URL (e.g. 'https://host/cp/mcp')
            token: Bearer token for authentication
            auth_type: Auth type ('Bearer Token' or 'None')
        """
        mcp_servers_link = self.page.get_by_role("link", name="MCP Servers")
        if Util.check_dom_visibility(self.page, mcp_servers_link, 1, 3):
            mcp_servers_link.click()
        else:
            self.page.get_by_role("tab", name=re.compile(r"MCP Servers")).click()
        self.page.wait_for_timeout(1000)

        if self.page.locator("tr", has_text=name).is_visible(timeout=2000):
            if self.page.locator("text=sync: failed").is_visible(timeout=2000):
                ColorLogger.warning(f"MCP server '{name}' exists but sync failed, recreating...")
                self._delete_mcp_server(name)
            else:
                ColorLogger.info(f"MCP server '{name}' already exists, skipping")
                return

        ColorLogger.info(f"Adding MCP Server '{name}'...")

        self.page.get_by_role("button", name="Add MCP Server").click()
        self.page.wait_for_timeout(1000)

        dialog = self.page.get_by_role("dialog", name="Add MCP Server")
        dialog.get_by_role("textbox", name="Name").fill(name)
        dialog.get_by_role("textbox", name="URL").fill(url)

        if auth_type != "None" and token:
            dialog.get_by_role("combobox", name="None").click()
            self.page.wait_for_timeout(500)

            self.page.get_by_role("option", name=auth_type).click()
            self.page.wait_for_timeout(500)

            dialog.get_by_role("textbox", name="Token").fill(token)
            ColorLogger.info("Token configured")

        dialog.get_by_role("button", name="Create").click()
        self.page.wait_for_timeout(2000)
        ColorLogger.success(f"MCP Server '{name}' created")

    def push_to_gateway(self):
        """Push configuration to MCP Gateway, wait for sync and tool discovery.

        Returns:
            int: Number of tools discovered after sync
        """
        ColorLogger.info("Pushing to MCP Gateway...")

        self.page.get_by_role("button", name="Push to Gateway").first.click()
        self.page.wait_for_timeout(1000)

        preview_dialog = self.page.get_by_role("dialog", name="Preview Changes")
        if Util.check_dom_visibility(self.page, preview_dialog, 1, 3):
            ColorLogger.info("Preview Changes dialog shown, confirming push...")
            preview_dialog.get_by_role("button", name="Push to Gateway").click()

        self.page.locator("text=Sync Result").wait_for(state="visible", timeout=60000)
        dialog = self.page.get_by_role("dialog")

        discovering = dialog.locator("text=Discovering tools...")
        if Util.check_dom_visibility(self.page, discovering, 2, 15):
            ColorLogger.info("Tool discovery in progress...")
            discovering.wait_for(state="hidden", timeout=120000)

        discovered = dialog.locator("text=/\\d+ tools from/")
        tools_count = 0
        if Util.check_dom_visibility(self.page, discovered, 2, 5):
            discovered_text = discovered.text_content(timeout=5000)
            match = re.search(r'(\d+) tools', discovered_text)
            tools_count = int(match.group(1)) if match else 0

        if dialog.locator("text=Partial Failure").is_visible(timeout=2000):
            ColorLogger.warning(f"Sync partial failure, {tools_count} tools discovered")
        elif dialog.locator("text=Success").is_visible(timeout=2000):
            ColorLogger.success(f"Sync success, {tools_count} tools discovered")
        else:
            ColorLogger.info(f"Sync completed, {tools_count} tools discovered")

        close_btn = dialog.get_by_role("button", name="Close")
        if Util.check_dom_visibility(self.page, close_btn, 1, 3):
            close_btn.click()
            dialog.wait_for(state="hidden", timeout=10000)
        self.page.wait_for_timeout(2000)
        return tools_count

    def get_tools_count(self):
        """Get the number of discovered tools from the MCP Tools link or tab label."""
        tools_link = self.page.get_by_role("link", name="MCP Tools")
        if Util.check_dom_visibility(self.page, tools_link, 1, 2):
            text = tools_link.text_content()
        else:
            tab = self.page.get_by_role("tab", name=re.compile(r"MCP Tools"))
            tab.wait_for(state="visible", timeout=10000)
            text = tab.text_content()
        match = re.search(r'\((\d+)\)', text) or re.search(r'(\d+)', text)
        return int(match.group(1)) if match else 0

    def verify_tools(self):
        """Navigate to MCP Tools page and verify tools are discovered."""
        tools_link = self.page.get_by_role("link", name="MCP Tools")
        if Util.check_dom_visibility(self.page, tools_link, 1, 2):
            tools_link.click()
        else:
            self.page.wait_for_timeout(3000)
            mcp_tools_tab = self.page.get_by_role("tab", name=re.compile(r"MCP Tools"))
            mcp_tools_tab.wait_for(state="visible", timeout=30000)
            mcp_tools_tab.click()
        self.page.wait_for_timeout(3000)

        count = self.get_tools_count()
        if count > 0:
            ColorLogger.success(f"Tools verified: {count} tools discovered")
        else:
            ColorLogger.warning("No tools discovered")
        return count
