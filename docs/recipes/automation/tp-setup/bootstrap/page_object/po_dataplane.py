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

import json
from urllib.parse import urlparse

from page_object.po_global import PageObjectGlobal
from utils.color_logger import ColorLogger
from utils.util import Util
from utils.helper import Helper
from utils.env import ENV
from utils.report import ReportYaml

class PageObjectDataPlane(PageObjectGlobal):
    def __init__(self, page):
        super().__init__(page)

    def goto_left_navbar_dataplane(self):
        self.goto_left_navbar("Data Planes")
        self.page.locator(".data-planes-content").wait_for(state="visible")
        print(f"Waiting for Data Planes page is loaded")
        self.detect_fresco_ui()

    def goto_global_dataplane(self):
        ColorLogger.info(f"Going to Global Data Plane...")
        self.goto_left_navbar_dataplane()
        # wait for 1 second
        self.page.wait_for_timeout(1000)

        self.page.locator("button", has_text="Global configuration").click()
        print("Clicked 'Global configuration' button")
        self.page.locator('breadcrumbs a', has_text="Global configuration").wait_for(state="visible")
        print(f"Navigated to Global Data Plane page")

    def goto_dataplane(self, dp_name):
        ColorLogger.info(f"Going to k8s Data Plane '{dp_name}'...")
        self.goto_left_navbar_dataplane()
        is_dataplane_visible = Util.refresh_until_success(self.page,
                                                          self.page.locator('.data-plane-name', has_text=dp_name),
                                                          self.page.locator(".data-planes-content"),
                                                          "DataPlane list page is load.")

        if is_dataplane_visible:
            self.page.locator('data-plane-card', has=self.page.locator('.data-plane-name', has_text=dp_name)).locator('button', has_text="Go to Data Plane").click()
            print("Clicked 'Go to Data Plane' button")
            self.page.wait_for_timeout(2000)
            nav_dp_selector = ".domain-data-title"
            if self.is_fresco:
                nav_dp_selector = "tibco-header .header-title-readonly-text"

            is_dataplane_detail_visible = Util.refresh_until_success(self.page,
                                                                     self.page.locator(nav_dp_selector, has_text=dp_name),
                                                                     self.page.locator(nav_dp_selector, has_text=dp_name),
                                                                     f"DataPlane '{dp_name}' detail page is load.")
            if is_dataplane_detail_visible:
                print(f"Navigated to Data Plane '{dp_name}' detail page")
                ReportYaml.set_dataplane(dp_name)
                self.page.wait_for_timeout(1000)
            else:
                Util.exit_error(f"DataPlane {dp_name} detail page is not load.", self.page, "goto_dataplane.png")

        else:
            Util.exit_error(f"DataPlane {dp_name} does not exist", self.page, "goto_dataplane.png")

    def goto_capability(self, dp_name, capability, capability_selector_path, is_check_status=True):
        ColorLogger.info(f"{capability} Going to capability...")
        self.goto_dataplane(dp_name)
        print(f"Check if {capability} capability is ready...")
        card_id = capability.lower()
        if Util.check_dom_visibility(self.page, self.page.locator(f"capability-card #{card_id}"), 10, 120, True):
            ColorLogger.success(f"{capability} capability is already provisioned.")
            ReportYaml.set_capability(dp_name, capability)
            print(f"Waiting for {capability} capability status is ready...")
            is_capability_success = Util.check_dom_visibility(self.page, self.page.locator(f"capability-card #{card_id} .status .success"))
            if not is_check_status or is_capability_success:
                self.page.locator(f"capability-card #{card_id} .image-name").click()
                print(f"Clicked '{capability}' capability")
                self.page.wait_for_timeout(3000)
                if not is_check_status:
                    print(f"Ignore check '{capability}' capability status, get into '{capability}' capability page")
                if is_capability_success:
                    print(f"{capability} capability status is ready")

                is_capability_loaded = Util.refresh_until_success(self.page,
                                                                  self.page.locator(capability_selector_path),
                                                                  self.page.locator(capability_selector_path),
                                                                  f"{capability} capability detail page is loaded")
                if is_capability_loaded:
                    print(f"Navigated to {capability} capability detail page")
                    self.page.wait_for_timeout(1000)
                else:
                    Util.exit_error(f"{capability} capability page is not loaded.", self.page, f"{card_id}_goto_capability.png")
            else:
                Util.exit_error(f"{capability} capability is provisioned, but status is not ready.", self.page, f"{card_id}_goto_capability.png")
        else:
            Util.exit_error(f"{capability} capability is not provisioned yet.", self.page, f"{card_id}_goto_capability.png")

    def goto_app_detail(self, dp_name, app_name, app_selector_path):
        ColorLogger.info(f"Going to app '{app_name}' detail page")
        self.goto_dataplane(dp_name)
        is_app_visible = Util.refresh_until_success(self.page,
                                                    self.page.locator("apps-list td.app-name a", has_text=app_name),
                                                    self.page.locator("apps-list td.app-name a", has_text=app_name),
                                                    "App detail page is load.")
        if is_app_visible:
            self.page.locator("apps-list td.app-name a", has_text=app_name).click()
            print(f"Clicked app '{app_name}'")
            self.page.locator(app_selector_path, has_text=app_name).wait_for(state="visible")
            print(f"Navigated to app '{app_name}' detail page")
            self.page.wait_for_timeout(500)
        else:
            Util.exit_error(f"The app '{app_name}' is not deployed yet.", self.page, "goto_app_detail.png")

    def is_capability_provisioned(self, capability, capability_name=""):
        ColorLogger.info(f"Checking if '{capability}' is provisioned")
        try:
            print(f"Checking if '{capability}' is already provisioned...")
            card_id = capability.lower()
            self.page.wait_for_timeout(3000)
            if self.page.locator(f"capability-card #{card_id}").is_visible():
                ColorLogger.success(f"'{capability}' is already provisioned.")
                if capability_name == "":
                    return True
                else:
                    if self.page.locator(f"capability-card #{card_id} .pl-tooltip__trigger", has_text=capability_name).is_visible():
                        ColorLogger.success(f"'{capability}' with name '{capability_name}' is provisioned.")
                        return True
                    else:
                        ColorLogger.warning(f"'{capability}' with name '{capability_name}' has not been provisioned.")
                        return False
            else:
                ColorLogger.warning(f"'{capability}' has not been provisioned.")
                return False
        except Exception as e:
            ColorLogger.warning(f"An error occurred while Checking capability '{capability}': {e}")
            return False

    def is_app_created(self, capability, app_name):
        ColorLogger.info(f"Checking if {capability} app '{app_name}' is created")
        # Guard against a missing app_name: with has_text=None Playwright applies no text
        # filter, so the locator matches every app row and is_visible() raises a strict-mode
        # violation ("resolved to N elements"). No app name => nothing to check => not created.
        if not app_name:
            print(f"No app_name provided for capability '{capability}', treating as not created.")
            return False
        try:
            print(f"Checking if {capability} app '{app_name}' is already created...")
            self.page.locator("apps-list").wait_for(state="visible")
            self.page.wait_for_timeout(3000)
            if self.page.locator("#app-list-table tr.pl-table__row td.app-name", has_text=app_name).is_visible():
                ColorLogger.success(f"{capability} app '{app_name}' is already created.")
                return True
            else:
                print(f"{capability} app '{app_name}' has not been created.")
                return False
        except Exception as e:
            ColorLogger.warning(f"An error occurred while Checking {capability} app '{app_name}': {e}")
            return False

    def is_app_running(self, dp_name, capability, app_name):
        ColorLogger.info(f"Checking if {capability} app '{app_name}' is running")
        try:
            self.goto_dataplane(dp_name)
            print(f"Checking if {capability} app '{app_name}' is already running...")
            self.page.wait_for_timeout(3000)
            if self.page.locator(f"#app-list-table tr.{capability.upper()}", has=self.page.locator("td.app-name", has_text=app_name)).locator("td", has_text="Running").is_visible():
                ColorLogger.success(f"{capability} app '{app_name}' is already running.")
                ReportYaml.set_capability_app_info(dp_name, capability, app_name, "status", "Running")
                return True
            else:
                print(f"{capability} app '{app_name}' has not been running.")
                return False
        except Exception as e:
            ColorLogger.warning(f"An error occurred while Checking {capability} app '{app_name}': {e}")
            return False

    def k8s_delete_dataplane(self, dp_name):
        ColorLogger.info(f"Deleting Data Plane '{dp_name}'")
        self.goto_left_navbar_dataplane()

        is_dataplane_visible = Util.refresh_until_success(self.page,
                                                          self.page.locator('.data-plane-name', has_text=dp_name),
                                                          self.page.locator(".data-planes-content"),
                                                          "DataPlane list page is load.")

        if is_dataplane_visible:
            self.page.locator('data-plane-card', has=self.page.locator('.data-plane-name', has_text=dp_name)).locator('.delete-dp-dropdown button').nth(0).click()
            print(f"Clicked '...' icon in Data Plane {dp_name} card")
            self.page.locator(".is-shown .pl-dropdown-menu__action", has_text="Delete Data Plane").nth(0).wait_for(state="visible")
            # check if 'Force Delete Data Plane' is visible, use Force Delete Data Plane as first choice
            if self.page.locator(".is-shown .pl-dropdown-menu__action", has_text="Force Delete Data Plane").is_visible():
                self.page.locator(".is-shown .pl-dropdown-menu__action", has_text="Force Delete Data Plane").click()
            else:
                self.page.locator(".is-shown .pl-dropdown-menu__action", has_text="Delete Data Plane").nth(0).click()
            print(f"Clicked 'Delete Data Plane' menu item")
            self.page.locator(".delete-dp-modal").wait_for(state="visible")
            print("'Delete Data Plane' dialog popup.")
            if Util.check_dom_visibility(self.page, self.page.locator(".delete-dp-modal #download-commands"), 2, 4):
                print("Delete Data Plane command is displayed.")
                # Note: the label height is too small, need to adjust it to trigger click event
                self.page.evaluate("""
                    document.querySelector(".delete-dp-modal label[for='agree-delete-btn']").style.minHeight = '20px';
                    document.querySelector(".delete-dp-modal label[for='agree-delete-btn']").style.width = '100%';
                """)
                self.page.locator(".delete-dp-modal label[for='agree-delete-btn']").click()
                print("Clicked confirm checkbox")
                self.k8s_run_dataplane_command(dp_name, "Delete Data Plane", self.page.locator(".delete-dp-modal #download-commands"), 0)

            self.page.locator(".delete-dp-modal #confirm-button").click()
            print("Clicked 'Delete' button in Delete Data Plane dialog")
            if Util.wait_for_success_message(self.page, 5):
                print("'Delete Data Plane' success message is displayed.")
                self.page.locator('.data-plane-name', has_text=dp_name).wait_for(state="detached")
                ColorLogger.success(f"Deleted Data Plane '{dp_name}'")
                ReportYaml.remove_dataplane(dp_name)
        else:
            ColorLogger.warning(f"Data Plane '{dp_name}' does not exist.")
            return

    def k8s_create_dataplane(self, dp_name, retry=0):
        if ReportYaml.is_dataplane_created(dp_name):
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, DataPlane '{dp_name}' is already created.")
            return

        ColorLogger.info(f"Creating k8s Data Plane '{dp_name}'...")
        self.page.wait_for_timeout(2000)

        if self.page.locator(".data-plane-name").count() > ENV.TP_AUTO_MAX_DATA_PLANE:
            Util.exit_error("Too many data planes, please delete some data planes first.", self.page, "k8s_create_dataplane.png")

        if self.page.locator('.data-plane-name', has_text=dp_name).is_visible():
            ReportYaml.set_dataplane(dp_name)
            ColorLogger.success(f"DataPlane '{dp_name}' is already created.")
            return

        self.page.click("#register-dp-button")
        if not Util.check_dom_visibility(self.page, self.page.locator("#select-existing-dp-button"), 10, 60, True):
            Util.exit_error("DP registration modal did not load within 60s", self.page, "k8s_create_dataplane.png")
        self.page.locator("#select-existing-dp-button").click()
        # step 1 Basic
        print("Waiting for Step 1: 'Basic' page is loaded")
        self.page.locator(".pl-secondarynav a.is-active", has_text="Basic").wait_for(state="visible")
        self.page.fill("#data-plane-name-text-input", dp_name)
        print(f"Input Data Plane Name: {dp_name}")
        self.page.locator('label[for="eua-checkbox"]').click()
        self.page.click("#data-plane-basics-btn")
        print("Clicked Next button, Finish step 1 Basic")

        # step 2 Namespace & Service account
        print("Waiting for Step 2: 'Namespace & Service account' page is loaded")
        self.page.locator(".pl-secondarynav a.is-active", has_text="Namespace & Service account").wait_for(state="visible")
        self.page.fill("#namespace-text-input", ENV.TP_AUTO_K8S_DP_NAMESPACE)
        print(f"Input NameSpace: {ENV.TP_AUTO_K8S_DP_NAMESPACE}")
        self.page.fill("#service-account-text-input", ENV.TP_AUTO_K8S_DP_SERVICE_ACCOUNT)
        print(f"Input Service Account: {ENV.TP_AUTO_K8S_DP_SERVICE_ACCOUNT}")
        self.page.click("#data-plane-namespace-btn")
        print("Clicked Next button, Finish step 2 Namespace & Service account")

        # step 3 Configuration
        print("Waiting for Step 3: 'Configuration' page is loaded")
        self.page.locator(".pl-secondarynav a.is-active", has_text="Configuration").wait_for(state="visible")

        # Handle non-hybrid connectivity: fill the Reachable DP URL when hybrid is disabled
        if Util.check_dom_visibility(self.page, self.page.locator("#hybrid-conn-url-host-input"), 2, 4):
            reachable_dp_url = ENV.TP_AUTO_REACHABLE_DP_URL
            self.page.fill("#hybrid-conn-url-host-input", reachable_dp_url)
            self.page.locator("#hybrid-conn-url-host-input").press("Tab")
            print(f"Hybrid connectivity disabled, Input Reachable DP URL: {reachable_dp_url}")

        if ENV.TP_IS_CERT_SELF_SIGNED:
            self.page.fill("#custom-certificate-secret-name-text-input", "self-signed-cert")
            print("Input Custom Certificate Secret Name: self-signed-cert")

        self.page.click("#data-plane-config-btn")
        print("Clicked Next button, Finish step 3 Configuration")

        # step Preview (for 1.4 and above)
        if Util.check_dom_visibility(self.page, self.page.locator(".pl-secondarynav a.is-active", has_text="Preview"), 3, 9):
            print("Step 4: 'Preview' page is loaded")
            self.page.wait_for_timeout(1000)
            if self.page.locator("#data-plane-preview-btn").is_visible():
                self.page.click("#data-plane-preview-btn")
                print("Clicked Next button, Finish step 4 Preview")

        # step Register Data Plane
        print("Check if create Data Plane is successful...")
        if not Util.check_dom_visibility(self.page, self.page.locator(".register-data-plane-content"), 3, 45):
            self.k8s_delete_dataplane(dp_name)
            if retry >= 3:
                Util.exit_error(f"Data Plane '{dp_name}' creation failed.", self.page, "k8s_create_dataplane_finish.png")

            ColorLogger.warning(f"Data Plane '{dp_name}' creation failed, retry {retry + 1} times.")
            self.k8s_create_dataplane(dp_name, retry + 1)

        download_commands = self.page.locator("#download-commands")
        commands_title = self.page.locator(".register-data-plane p.title").all_text_contents()
        print("commands_title:", commands_title)

        # Execute each command dynamically based on its position
        for index, step_name in enumerate(commands_title):
            self.k8s_run_dataplane_command(dp_name, step_name, download_commands.nth(index), index + 1)

        # click Done button
        self.page.click("#data-plane-finished-btn")
        print("Data Plane create successful, clicked 'Done' button")
        ReportYaml.set_dataplane_info(dp_name, "runCommands", True)
        self.page.locator('#confirm-button', has_text="Yes").wait_for(state="visible")
        self.page.locator('#confirm-button', has_text="Yes").click()

        # verify data plane is created in the list
        self.page.wait_for_timeout(2000)
        print(f"Verifying Data Plane {dp_name} is created in the list")
        # No-tibtunnel mode: make the registered Reachable DP URL reachable (ingress or netpol labels).
        self.k8s_setup_dp_reachability(dp_name, ENV.TP_AUTO_K8S_DP_NAMESPACE, ENV.TP_AUTO_REACHABLE_DP_URL)
        self.k8s_wait_tunnel_connected(dp_name)

    def k8s_create_bmdp(self, dp_name, retry=0):
        if ReportYaml.is_dataplane_created(dp_name):
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, DataPlane '{dp_name}' is already created.")
            return

        ColorLogger.info(f"Creating k8s Data Plane '{dp_name}'...")
        self.page.wait_for_timeout(2000)

        if self.page.locator(".data-plane-name").count() > ENV.TP_AUTO_MAX_DATA_PLANE:
            Util.exit_error("Too many data planes, please delete some data planes first.", self.page, "k8s_create_dataplane.png")

        if self.page.locator('.data-plane-name', has_text=dp_name).is_visible():
            ReportYaml.set_dataplane(dp_name)
            ColorLogger.success(f"DataPlane '{dp_name}' is already created.")
            return

        self.page.click("#register-dp-button")
        self.page.locator("#select-control-tower-dp-button").wait_for(state="visible")
        self.page.locator(".pl-primary-spinner").wait_for(state="hidden", timeout=60000)
        self.page.wait_for_timeout(2000)

        # check if #select-control-tower-dp-button is disabled, if it's disabled, should return error, and exit.
        start_btn = self.page.locator("#select-control-tower-dp-button")
        if "pcp-disabled" in (start_btn.get_attribute("class") or ""):
            tooltip = self.page.locator("#control-tower-dp-register-button-tooltip")
            hint = tooltip.text_content(timeout=3000) if tooltip.is_visible(timeout=2000) else "unknown prerequisite"
            Util.exit_error(
                f"Control Tower DP 'Start' button is disabled: {hint}",
                self.page, "bmdp_button_disabled.png"
            )

        start_btn.click()
        print("Waiting for Step 1: 'Pre-Requisites' page is loaded")
        if Util.check_dom_visibility(self.page, self.page.locator("#data-plane-pre-requisites-btn"), 2, 4):
            tp_version = 1.4
            # step 1 Pre-Requisites
            print("configure for 1.4")
            self.page.click("#data-plane-pre-requisites-btn")
            print("Clicked Next button, Finish Pre-Requisites")
            # step 2 Basic
            self.page.locator(".pl-secondarynav a.is-active", has_text="Basic").wait_for(state="visible")
            self.page.fill("#data-plane-name-text-input", dp_name)
            print(f"Input Data Plane Name: {dp_name}")
            self.page.locator('label[for="terms-checkbox"]').click()
            self.page.click("#data-plane-basics-btn")
            print("Clicked Next button, Finish Basic")
        else:
            tp_version = 1.5
            self.page.fill("#data-plane-name-text-input", dp_name)
            print(f"Input Data Plane Name: {dp_name}")
            self.page.fill("#data-plane-machine-host-name-text-input", ENV.TP_AUTO_FQDN_BMDP)
            print(f"Input Machine Host Name: {ENV.TP_AUTO_FQDN_BMDP}")

            # Reachable DP URL is always required for BMDP registration (TP 1.15+)
            reachable_url_field = self.page.locator("#reachable-dp-url-text-input")
            if reachable_url_field.is_visible():
                reachable_dp_url = ENV.TP_AUTO_REACHABLE_BMDP_URL
                reachable_url_field.fill(reachable_dp_url)
                print(f"Input Reachable DP URL: {reachable_dp_url}")

            self.page.locator('label[for="terms-checkbox"]').click()
            self.page.locator(".pl-button.pl-button--no-border.big-button.big-button-secondary").click()
            print("Clicked Advanced Configuration button. Go with Advanced Configuration")

        # step 3 Namespace & Service account
        print("Waiting for 'Namespace & Service account' page is loaded")
        self.page.locator(".pl-secondarynav a.is-active", has_text="Namespace & Service account").wait_for(state="visible")
        self.page.fill("#namespace-text-input", ENV.TP_AUTO_K8S_BMDP_NAMESPACE)
        print(f"Input NameSpace: {ENV.TP_AUTO_K8S_BMDP_NAMESPACE}")
        self.page.fill("#service-account-text-input", ENV.TP_AUTO_K8S_BMDP_SERVICE_ACCOUNT)
        print(f"Input Service Account: {ENV.TP_AUTO_K8S_BMDP_SERVICE_ACCOUNT}")
        self.page.click("#data-plane-namespace-btn")
        print("Clicked Next button, Finish Namespace & Service account")

        # step 4 Configure resources - storage class
        print("Waiting for 'Configure resources' page is loaded")
        self.page.locator(".pl-secondarynav a.is-active", has_text="Resources").wait_for(state="visible")
        self.page.fill("#storage-resource-name-text-input", "storageclass")
        print(f"Input Storage Resource Name: storageclass")
        self.page.fill("#storage-description-text-input", "storageclass")
        print(f"Input Storage Description: storageclass")
        # set the storage class to nfs for now, due to a known issue with hawkconsole
        # self.page.fill("#storage-class-name-text-input", "{ENV.TP_AUTO_STORAGE_CLASS}")
        self.page.fill("#storage-class-name-text-input", "nfs")
        print(f"Input Storage Class Name: nfs")

        # step 4 Configure resources - ingress / gateway controller
        # CP 1.18 added a Gateway API Controller radio next to the Ingress Controller
        # radio. Switching to Gateway exposes a different dropdown (Nginx / GKE / Istio /
        # Traefik / NetScaler / Other) and a different field set with `gateway-*` IDs
        # instead of `ingress-*`. Earlier CPs (≤1.17) only have the ingress flow.
        gateway_radio = self.page.locator('#gateway-radio-button')
        if ENV.TP_AUTO_INGRESS_OBJECT == "gateway" and gateway_radio.is_visible():
            # CP 1.18+ gateway path
            gateway_radio.click(force=True)
            print("Switched to 'Gateway API Controller' radio (CP 1.18 BMDP wizard)")
            self.page.wait_for_timeout(1500)

            # Same `.ingress pcp-dropdown` container; in gateway mode the inner div is
            # #gatewayController and options are Nginx/GKE/Istio/Traefik/NetScaler/Other.
            self.page.locator('.ingress pcp-dropdown input[type="button"]').click()
            print("Clicked Gateway Controller dropdown")
            select_gateway_controller = ENV.TP_AUTO_GATEWAY_CONTROLLER.capitalize()
            opt = self.page.locator('.ingress pcp-dropdown li', has_text=select_gateway_controller).first
            opt.wait_for(state="visible")
            opt.click()
            print(f"Selected Gateway Controller: {select_gateway_controller}")

            self.page.fill("#gateway-resource-name-text-input", ENV.TP_AUTO_GATEWAY_CONTROLLER)
            print(f"Input Gateway Resource Name: {ENV.TP_AUTO_GATEWAY_CONTROLLER}")
            self.page.fill("#gateway-name-text-input", ENV.TP_AUTO_GATEWAY_NAME)
            print(f"Input Gateway Name: {ENV.TP_AUTO_GATEWAY_NAME}")
            self.page.fill("#gateway-namespace-text-input", ENV.TP_AUTO_GATEWAY_NAMESPACE)
            print(f"Input Gateway Namespace: {ENV.TP_AUTO_GATEWAY_NAMESPACE}")
            self.page.fill("#gateway-hostname-text-input", ENV.TP_AUTO_FQDN_BMDP)
            print(f"Input Gateway Hostname (FQDN): {ENV.TP_AUTO_FQDN_BMDP}")
        else:
            # Ingress path (CP <= 1.17 always; CP 1.18 when TP_AUTO_INGRESS_OBJECT != "gateway")
            # For 1.13 and above, the ingress controller changed to dropdown selection from a readonly input box
            if not self.page.locator("ingress-controller-text-input").is_visible():
                # click dropdown and select ENV.TP_AUTO_INGRESS_CONTROLLER
                print("For 1.13 and above, the ingress controller changed to dropdown selection from a readonly input box")
                if self.page.locator('.ingress pcp-dropdown').is_visible():
                    print("Selecting Ingress Controller from dropdown")
                    self.page.locator('.ingress pcp-dropdown input[type="button"]').click()
                    print("Clicked Ingress Controller dropdown")
                    self.page.locator('.ingress pcp-dropdown div#ingressController').wait_for(state="visible")
                    print("Ingress Controller options are visible")
                    select_ingress_controller = ENV.TP_AUTO_INGRESS_CONTROLLER.capitalize()
                    self.page.locator('.ingress pcp-dropdown div#ingressController li', has_text=select_ingress_controller).click()
                    print(f"Selected Ingress Controller: {select_ingress_controller}")

            self.page.fill("#ingress-resource-name-text-input", ENV.TP_AUTO_INGRESS_CONTROLLER)
            print(f"Input Ingress Resource Name: {ENV.TP_AUTO_INGRESS_CONTROLLER}")
            self.page.fill("#ingress-class-name-text-input", ENV.TP_AUTO_INGRESS_CONTROLLER_CLASS_NAME)
            print(f"Input Ingress Class Name: {ENV.TP_AUTO_INGRESS_CONTROLLER_CLASS_NAME}")
            self.page.fill("#ingress-fqdn-text-input", ENV.TP_AUTO_FQDN_BMDP)
            print(f"Input Ingress FQDN: {ENV.TP_AUTO_FQDN_BMDP}")

        self.page.click("#data-plane-resources-btn")
        print("Clicked Next button, Finish Configure resources")

        # step 5 Configuration
        print("Waiting for 'Configuration' page is loaded")
        self.page.locator(".pl-secondarynav a.is-active", has_text="Configuration").wait_for(state="visible")

        if ENV.TP_IS_CERT_SELF_SIGNED:
            self.page.fill("#custom-certificate-secret-name-text-input", "self-signed-cert")
            print("Input Custom Certificate Secret Name: self-signed-cert")

        self.page.click("#data-plane-preview-next-btn")
        print("Clicked Next button, Finish Configuration")

        # step 6 Preview (for 1.4 and above)
        if Util.check_dom_visibility(self.page, self.page.locator(".pl-secondarynav a.is-active", has_text="Preview"), 3, 9):
            print("'Preview' page is loaded")
            self.page.wait_for_timeout(1000)
            if self.page.locator("#data-plane-preview-create-btn").is_visible():
                self.page.click("#data-plane-preview-create-btn")
                print("Clicked Next button, Finish Preview")
            elif self.page.locator("#data-plane-config-prev-btn").is_visible():
                self.page.click("#data-plane-config-prev-btn")
                print("Clicked  'Register on Control Plane now', Finish Preview")

        # step 7 Register Data Plane
        print("Check if create Data Plane is successful...")
        if not Util.check_dom_visibility(self.page, self.page.locator(".install-content"), 2, 10) \
                and not Util.check_dom_visibility(self.page, self.page.locator(".pl-button.pl-button--primary .pl-button__text"), 1, 3):
            self.k8s_delete_dataplane(dp_name)
            if retry >= 3:
                Util.exit_error(f"Data Plane '{dp_name}' creation failed.", self.page, "k8s_create_dataplane_finish.png")

            ColorLogger.warning(f"Data Plane '{dp_name}' creation failed, retry {retry + 1} times.")
            self.k8s_create_bmdp(dp_name, retry + 1)

        if tp_version == 1.4:
            download_commands = self.page.locator("#download-commands")
            commands_title = self.page.locator(".install-content p.title").all_text_contents()
            commands_title.pop(0)
        else:
            self.page.locator(".pl-button.pl-button--no-border .pl-button__text").click()
            download_commands = self.page.locator("#download-commands")
            commands_title = self.page.locator(".expandable.register-commands-container p.title").all_text_contents()

        print("commands_title:", commands_title)

        # Execute each command dynamically based on its position
        for index, step_name in enumerate(commands_title):
            self.k8s_run_dataplane_command(dp_name, step_name, download_commands.nth(index), index + 1)

        # click Done button
        self.page.click("#data-plane-finished-btn")
        print("BMDP create successful, clicked 'Done' button")
        ReportYaml.set_dataplane_info(dp_name, "runCommands", True)
        self.page.locator('#confirm-button', has_text="Yes").wait_for(state="visible")
        self.page.locator('#confirm-button', has_text="Yes").click()

        # verify data plane is created in the list
        self.page.wait_for_timeout(2000)
        print(f"Verifying Data Plane {dp_name} is created in the list")
        # No-tibtunnel mode: make the registered Reachable BMDP URL reachable (ingress or netpol labels).
        self.k8s_setup_dp_reachability(dp_name, ENV.TP_AUTO_K8S_BMDP_NAMESPACE, ENV.TP_AUTO_REACHABLE_BMDP_URL, is_bmdp=True)
        self.k8s_wait_tunnel_connected(dp_name, False)
        self.k8s_wait_bmdp_ready(dp_name)

    def k8s_run_dataplane_command(self, dp_name, step_name, download_selector, step):
        ColorLogger.info(f"Running command for: {step_name}")
        print(f"Download: {step_name}")
        with self.page.expect_download() as download_info:
            download_selector.click()

        file_name = f"{dp_name}_{step}.sh"
        file_path = Util.download_file(download_info.value, file_name)
        if step_name == "1. Helm Repository configuration":
            # read the file content
            with open(file_path, "r", encoding="utf-8") as f:
                file_content = f.read()
                # get name "tibco-platform-public" from "helm repo add tibco-platform-public https://"
                repo_name = file_content.split("helm repo add ")[1].split(" ")[0]
                if repo_name:
                    # remove the repo first
                    print(f"Removing existing helm repo: {repo_name}")
                    Helper.get_command_output(f"helm repo remove {repo_name}", True)

        # add network_policies if ENV.TP_CREATE_NETWORK_POLICIES is true
        if step_name == "3. Service Account creation":
            if ENV.TP_CREATE_NETWORK_POLICIES == "true":
                # add network_policies at the end of the file
                network_policies = f" --set networkPolicy.create=true --set networkPolicy.createDeprecatedPolicies=true --set networkPolicy.createInternetScopePolicies=true --set networkPolicy.createClusterScopePolicies=true --set networkPolicy.createDeprecatedPolicies=false  --set networkPolicy.nodeCidrIpBlock={ENV.TP_CLUSTER_NODE_CIDR} --set networkPolicy.podCidrIpBlock={ENV.TP_CLUSTER_POD_CIDR} --set networkPolicy.serviceCidrIpBlock={ENV.TP_CLUSTER_SERVICE_CIDR}"
                with open(file_path, "a", encoding="utf-8") as f:
                    f.write(network_policies)
                    ColorLogger.info(f"Adding Network Policies: {network_policies} for {step_name} to {file_name}")

            if ENV.TP_AUTO_K8S_DP_SERVICE_ACCOUNT_CREATION_ADDITIONAL_SETTINGS:
                # add namespace to the file
                other_settings = f" {ENV.TP_AUTO_K8S_DP_SERVICE_ACCOUNT_CREATION_ADDITIONAL_SETTINGS}"
                with open(file_path, "a", encoding="utf-8") as f:
                    f.write(other_settings)
                    ColorLogger.info(f"Adding additional settings: {other_settings} for {step_name} to {file_name}")

        if ENV.TP_IS_CERT_SELF_SIGNED:
            with open(file_path, "r", encoding="utf-8") as f:
                file_content = f.read()
            if 'helm upgrade' in file_content:
                modified = False
                dp_namespace = f"{dp_name}ns"
                if 'dp-configure-namespace' in file_content:
                    # Create cert secret before the namespace configuration step
                    secret_cmd = (
                        f'kubectl get secret default-certificate -n ingress-system -o jsonpath="{{.data.tls\\.crt}}" | base64 --decode > /tmp/cp-cert.pem\n'
                        f'kubectl create secret generic self-signed-cert -n {dp_namespace} --from-file=cert=/tmp/cp-cert.pem\n'
                        f'rm -f /tmp/cp-cert.pem\n'
                    )
                    ColorLogger.info("Self-signed certificate detected, inserting cert secret creation...")
                    file_content = file_content.replace('helm upgrade', secret_cmd + 'helm upgrade', 1)
                    modified = True
                if modified:
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(file_content)

        print(f"Run command for: {step_name}")
        Helper.run_shell_file(file_path)
        print(f"Command for step: {step_name} is executed, wait for 3 seconds.")
        self.page.wait_for_timeout(3000)

    def k8s_wait_bmdp_ready(self, dp_name):
        ColorLogger.info(f"Wait for '{dp_name}' getting ready...")
        data_plane_card = self.page.locator(".data-plane-card", has=self.page.locator('.data-plane-name', has_text=dp_name))
        if not Util.check_dom_visibility(self.page, data_plane_card.locator('.data-plane-status svg.green'), 20, 300, True):
            Util.exit_error(f"Data Plane '{dp_name}' is not ready.", self.page, "dp_config_bmdp_status.png")

        ColorLogger.success(f"Data Plane '{dp_name}' is ready.")
        ReportYaml.set_dataplane(dp_name)
        ReportYaml.set_dataplane_info(dp_name, "status", "Running successfully")

    def k8s_wait_tunnel_connected(self, dp_name, is_update_report=True):
        print(f"Waiting for Data Plane {dp_name} to be created and ready.")
        self.goto_left_navbar_dataplane()
        print(f"Navigated to Data Planes list page, and checking for {dp_name} is created.")
        self.page.locator('.data-plane-name', has_text=dp_name).wait_for(state="visible")
        if not self.page.locator('.data-plane-name', has_text=dp_name).is_visible():
            Util.exit_error(f"DataPlane {dp_name} is not created.", self.page, "k8s_wait_tunnel_connected_1.png")

        if is_update_report:
            ReportYaml.set_dataplane(dp_name)
        data_plane_card = self.page.locator(".data-plane-card", has=self.page.locator('.data-plane-name', has_text=dp_name))

        # No-tibtunnel mode (hybrid connectivity disabled): there is no tibtunnel to
        # wait for — the CP reaches the DP over the configured Reachable DP URL. Skip
        # the tunnel-status wait and instead confirm DP readiness via the card-level
        # DP status icon (the same signal k8s_wait_bmdp_ready uses).
        if not ENV.TP_AUTO_ENABLE_HYBRID_CONNECTIVITY:
            ColorLogger.success(f"DataPlane {dp_name} is created. Hybrid connectivity disabled, skipping tunnel-connected wait.")
            print(f"Waiting for DataPlane {dp_name} to be ready (no-tibtunnel mode)...")
            # Match k8s_wait_bmdp_ready: poll every 20s up to 300s and refresh the DP list page
            # between polls (is_refresh=True) — the DP status icon only turns green after a reload.
            if not Util.check_dom_visibility(self.page, data_plane_card.locator('.data-plane-status svg.green'), 20, 300, True):
                Util.exit_error(f"DataPlane {dp_name} is not ready, exit program and recheck again.", self.page, "k8s_wait_dp_ready.png")
            ColorLogger.success(f"DataPlane {dp_name} is ready.")
            ReportYaml.set_dataplane_info(dp_name, "tunnelConnected", False)
            return

        ColorLogger.success(f"DataPlane {dp_name} is created, waiting for tunnel connected.")
        print(f"Waiting for DataPlane {dp_name} tunnel connected...")
        if not Util.check_dom_visibility(self.page, data_plane_card.locator('.tunnel-status svg.green'), 10, 180):
            Util.exit_error(f"DataPlane {dp_name} tunnel is not connected, exit program and recheck again.", self.page, "k8s_wait_tunnel_connected_2.png")

        ColorLogger.success(f"DataPlane {dp_name} tunnel is connected.")
        ReportYaml.set_dataplane_info(dp_name, "tunnelConnected", True)

    def k8s_setup_dp_reachability(self, dp_name, namespace, reachable_url, is_bmdp=False):
        # No-tibtunnel (hybrid disabled) reachability: make the registered Reachable DP URL actually
        # reachable from the CP. Option A (default): create a controller-adaptive ingress in the DP
        # namespace pointing at the cpdpproxy service. Option B (TP_AUTO_DP_APPLY_NETPOL_LABELS=true):
        # label the cpdpproxy (DP) and tp-dp-proxy (CP) deployments so tp-dp-proxy can reach the
        # cpdpproxy ClusterIP directly through the namespace deny-all NetworkPolicies.
        if ENV.TP_AUTO_ENABLE_HYBRID_CONNECTIVITY:
            return
        if not ENV.TP_AUTO_DP_MANAGE_REACHABILITY:
            ColorLogger.info("TP_AUTO_DP_MANAGE_REACHABILITY is false, skipping no-tibtunnel reachability setup.")
            return
        if not ENV.IS_CLUSTER_ACCESSIBLE:
            ColorLogger.warning("Cluster is not accessible, skipping no-tibtunnel reachability setup.")
            return

        dp_type = "BMDP" if is_bmdp else "DataPlane"
        if ENV.TP_AUTO_DP_APPLY_NETPOL_LABELS:
            ColorLogger.info(f"No-tibtunnel {dp_type} '{dp_name}': applying private-reachability NetworkPolicy labels (Option B).")
            self._apply_dp_reachability_netpol_labels(namespace)
        else:
            ColorLogger.info(f"No-tibtunnel {dp_type} '{dp_name}': creating public cpdpproxy {ENV.TP_AUTO_INGRESS_OBJECT} (Option A).")
            self._apply_cpdpproxy_public_ingress(namespace, reachable_url)

        # Cross-cutting: dp-proxy (CP side) caches DP connection-details and keeps dialing the
        # previous (stale) address until the cache expires. Restart it so it re-reads the
        # registered reachable URL and uses the now-in-place ingress/labels immediately.
        self._restart_dp_proxy()

    def _restart_dp_proxy(self):
        cp_ns = ENV.TP_AUTO_CP_NAMESPACE
        deploy = ENV.TP_AUTO_CP_DP_PROXY_DEPLOYMENT
        ColorLogger.info(f"Restarting {deploy} in {cp_ns} to invalidate the no-tibtunnel connection-details cache.")
        out = Helper.get_command_output(f"kubectl rollout restart deployment {deploy} -n {cp_ns}", is_print_cmd=True)
        if out is None:
            ColorLogger.warning(f"Could not restart {deploy} in {cp_ns}; the CP may keep using the cached DP address.")
            return
        print(out)
        # Best-effort wait so the refreshed dp-proxy is ready before we verify DP readiness.
        Helper.get_command_output(f"kubectl rollout status deployment {deploy} -n {cp_ns} --timeout=150s", is_print_cmd=True)

    def _apply_cpdpproxy_public_ingress(self, namespace, reachable_url):
        host = urlparse(reachable_url).hostname or reachable_url.split("://")[-1].split("/")[0]
        controller = ENV.TP_AUTO_GATEWAY_CONTROLLER if ENV.TP_AUTO_INGRESS_OBJECT == "gateway" else ENV.TP_AUTO_INGRESS_CONTROLLER
        manifest = self._build_cpdpproxy_ingress_manifest(host, namespace)
        ColorLogger.info(f"Applying cpdpproxy public {ENV.TP_AUTO_INGRESS_OBJECT} (controller: {controller}) for host '{host}' in namespace '{namespace}'.")
        print(f"Manifest:\n{manifest}")
        cmd = "cat <<'EOF' | kubectl apply -f -\n" + manifest + "EOF\n"
        output = Helper.get_command_output(cmd, is_print_cmd=True)
        if output is None:
            ColorLogger.warning(f"Failed to apply cpdpproxy public {ENV.TP_AUTO_INGRESS_OBJECT} for host '{host}'; the CP may not be able to reach the DP.")
        else:
            ColorLogger.success(f"cpdpproxy public {ENV.TP_AUTO_INGRESS_OBJECT} applied for host '{host}'.")
            print(output)

    def _apply_dp_reachability_netpol_labels(self, dp_namespace):
        # cpdpproxy (DP side) must accept cross-namespace ingress; tp-dp-proxy (CP side) must be allowed
        # to egress to the DP namespace. Label both the Deployment object and its pod template so the
        # pods carry the label (NetworkPolicy selects on pod labels) and it survives restarts.
        self._label_deployment_and_template(ENV.TP_AUTO_DP_PROXY_SERVICE_NAME, dp_namespace,
                                            "networking.platform.tibco.com/cluster-ingress", "enable")
        self._label_deployment_and_template(ENV.TP_AUTO_CP_DP_PROXY_DEPLOYMENT, ENV.TP_AUTO_CP_NAMESPACE,
                                            "networking.platform.tibco.com/cluster-egress", "enable")

    @staticmethod
    def _label_deployment_and_template(deployment, namespace, label_key, label_value):
        labels = {label_key: label_value}
        patch = json.dumps({"metadata": {"labels": labels}, "spec": {"template": {"metadata": {"labels": labels}}}})
        cmd = f"kubectl patch deployment {deployment} -n {namespace} --type=merge -p '{patch}'"
        output = Helper.get_command_output(cmd, is_print_cmd=True)
        if output is None:
            ColorLogger.warning(f"Could not label deployment '{deployment}' in '{namespace}' ({label_key}={label_value}); it may not exist.")
        else:
            ColorLogger.success(f"Labeled deployment '{deployment}' in '{namespace}': {label_key}={label_value}")
            print(output)

    def _build_cpdpproxy_ingress_manifest(self, host, namespace):
        # Mirror the capability charts' controller-adaptive ingress pattern (dp-flogo-app / dp-bwce-app):
        # one shape per deployed controller, selected from the same ENV the automation feeds the CP
        # "Add Ingress/Route" wizard. cpdpproxy needs a plain host -> service route (no prefix strip).
        svc = ENV.TP_AUTO_DP_PROXY_SERVICE_NAME
        port = ENV.TP_AUTO_DP_PROXY_SERVICE_PORT
        name = "cpdpproxy-public"

        if ENV.TP_AUTO_INGRESS_OBJECT == "gateway":
            section_name = f"\n    sectionName: {ENV.TP_AUTO_GATEWAY_SECTION_NAME}" if ENV.TP_AUTO_GATEWAY_SECTION_NAME else ""
            return (
                "apiVersion: gateway.networking.k8s.io/v1\n"
                "kind: HTTPRoute\n"
                "metadata:\n"
                f"  name: {name}\n"
                f"  namespace: {namespace}\n"
                "  annotations:\n"
                f"    platform.tibco.com/controller-name: \"{ENV.TP_AUTO_GATEWAY_CONTROLLER}\"\n"
                "spec:\n"
                "  parentRefs:\n"
                f"  - name: {ENV.TP_AUTO_GATEWAY_NAME}\n"
                f"    namespace: {ENV.TP_AUTO_GATEWAY_NAMESPACE}{section_name}\n"
                "  hostnames:\n"
                f"  - \"{host}\"\n"
                "  rules:\n"
                "  - matches:\n"
                "    - path:\n"
                "        type: PathPrefix\n"
                "        value: /\n"
                "    backendRefs:\n"
                f"    - name: {svc}\n"
                f"      port: {port}\n"
                "      weight: 100\n"
            )

        controller = ENV.TP_AUTO_INGRESS_CONTROLLER
        if controller == "openshiftRouter":
            return (
                "apiVersion: route.openshift.io/v1\n"
                "kind: Route\n"
                "metadata:\n"
                f"  name: {name}\n"
                f"  namespace: {namespace}\n"
                "  annotations:\n"
                f"    platform.tibco.com/controller-name: \"{controller}\"\n"
                "spec:\n"
                f"  host: {host}\n"
                "  path: /\n"
                "  to:\n"
                "    kind: Service\n"
                f"    name: {svc}\n"
                "    weight: 100\n"
                "  port:\n"
                f"    targetPort: {port}\n"
                "  wildcardPolicy: None\n"
            )

        # Classic Ingress (traefik / nginx / haProxy / kong) — controller chosen via ingressClassName.
        annotations = f"    platform.tibco.com/controller-name: \"{controller}\"\n"
        if controller == "nginx":
            annotations += "    nginx.ingress.kubernetes.io/proxy-body-size: \"0\"\n"
        return (
            "apiVersion: networking.k8s.io/v1\n"
            "kind: Ingress\n"
            "metadata:\n"
            f"  name: {name}\n"
            f"  namespace: {namespace}\n"
            "  annotations:\n"
            f"{annotations}"
            "spec:\n"
            f"  ingressClassName: {ENV.TP_AUTO_INGRESS_CONTROLLER_CLASS_NAME}\n"
            "  rules:\n"
            f"  - host: {host}\n"
            "    http:\n"
            "      paths:\n"
            "      - path: /\n"
            "        pathType: Prefix\n"
            "        backend:\n"
            "          service:\n"
            f"            name: {svc}\n"
            "            port:\n"
            f"              number: {port}\n"
        )

    def k8s_delete_app(self, dp_name, capability, app_name):
        ColorLogger.info(f"Deleting {capability} app '{app_name}' in DataPlane {dp_name}")
        self.goto_dataplane(dp_name)
        self.page.wait_for_timeout(3000)
        app_row = self.page.locator(f"#app-list-table tr.{capability.upper()}", has=self.page.locator("td.app-name", has_text=app_name))
        if app_row.is_visible():
            app_row.locator(".actions a:has(svg[id^='delete'])").click()
            print(f"Clicked 'Delete' icon in app '{app_name}' row")
            self.page.locator(".confirmation .pl-modal__container").wait_for(state="visible")
            print(f"Delete confirmation dialog is displayed.")
            self.page.locator(".confirmation #confirm-button", has_text="Yes").click()
            print("Clicked 'Yes' button in confirmation dialog")
            self.page.wait_for_timeout(2000)
            if not self.page.locator(f"#app-list-table tr.{capability.upper()}", has=self.page.locator("td.app-name", has_text=app_name)).is_visible():
                ColorLogger.success(f"Deleted {capability} app '{app_name}' in DataPlane {dp_name}")
                ReportYaml.remove_capability_app(dp_name, capability, app_name)
        else:
            ColorLogger.warning(f"{capability} app '{app_name}' does not exist.")

    def switch_to_global_config(self, dp_name):
        ColorLogger.info(f"Switch to Global Observability Resource")
        # NOTE on waits: the o11y panel is an Angular component that can take several seconds
        # to (re-)render. The checks below poll without reloading the page (is_refresh=False)
        # so a transient slow render does not get reset mid-flow. Previously these were
        # single-shot checks with is_refresh=True, where a miss on the legacy ".switch-to-global"
        # selector reloaded the page and the following ".use-global-resource" check then raced
        # the freshly re-rendering panel -> a false "link failed".
        print("PreCheck if Data Plane is already linked to Global Observability Resource...")
        if Util.check_dom_visibility(self.page, self.page.locator(".o11y-panel-actions .global-resource-name", has_text="View in Global Configuration"), 5, 10):
            ColorLogger.success(f"Linked {dp_name} to Global Observability Resource successfully.")
            ReportYaml.set_dataplane_info(dp_name, "switchGlobal", True)
            return

        print("Check if 'Switch to Global' or 'Use Global Resource' button is visible...")
        # ".switch-to-global" is the legacy (pre-1.5) selector; absent on newer CP versions.
        if Util.check_dom_visibility(self.page, self.page.locator(".switch-to-global"), 5, 5) and self.page.locator(".switch-to-global").is_enabled():
            ColorLogger.info(f"Switching current Data Plane '{dp_name}' configuration to Global Observability Resource")
            self.page.locator(".switch-to-global").click()
            print("Clicked 'Switch to Global' button")
            self.page.locator(".confirmation .pl-modal__heading", has_text="Switch to Global Observability Resource?").wait_for(state="visible")
            print("Confirmation dialog is visible")
            self.page.locator("#confirm-button", has_text="Yes").click()
            print("Clicked 'Yes' button in confirmation dialog")
        elif Util.check_dom_visibility(self.page, self.page.locator(".use-global-resource .o11y-btn"), 3, 30) and self.page.locator(".use-global-resource .o11y-btn").is_enabled():
            ColorLogger.info(f"Data Plane '{dp_name}' does not have configuration, Use Global Resource")
            self.page.locator(".use-global-resource .o11y-btn").click()
            print("Clicked 'Use Global Resource' button")
            self.page.locator(".confirmation .pl-modal__heading", has_text="Link Data plane to this resource ?").wait_for(state="visible")
            print("Confirmation dialog is visible")
            self.page.locator("#confirm-button", has_text="Link").click()
            print("Clicked 'Link' button in confirmation dialog")

        print("Double Check if Data Plane is already linked to Global Observability Resource...")
        # Linking applies global o11y config on the backend, so the confirmation can lag a few
        # seconds; poll (with reload) for up to 30s before declaring failure.
        if Util.check_dom_visibility(self.page, self.page.locator(".o11y-panel-actions .global-resource-name", has_text="View in Global Configuration"), 5, 30, True):
            ColorLogger.success(f"Linked {dp_name} to Global Observability Resource successfully.")
            ReportYaml.set_dataplane_info(dp_name, "switchGlobal", True)
        else:
            ColorLogger.warning(f"Linked {dp_name} to Global Observability Resource failed.")
