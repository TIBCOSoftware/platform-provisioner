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
from dataclasses import dataclass
from typing import Dict

from utils.color_logger import ColorLogger
from utils.util import Util
from utils.helper import Helper
from utils.env import ENV
from utils.report import ReportYaml
from page_object.po_dataplane import PageObjectDataPlane
from page_object.po_dp_config import PageObjectDataPlaneConfiguration

@dataclass(frozen=True)
class EnvConfig:
    ingress_controller: str
    fqdn: str
    app_name: str
    app_file_name: str
    create_app_build_button_selector: str
    provision_plugin_button_selector: str


class PageObjectDataPlaneBWCE(PageObjectDataPlane):
    CONFIGS: Dict[str, EnvConfig] = {
        "bw5ce": EnvConfig(
            ENV.TP_AUTO_INGRESS_CONTROLLER_BW5CE,
            ENV.TP_AUTO_FQDN_BW5CE,
            ENV.BW5CE_APP_NAME,
            ENV.BW5CE_APP_FILE_NAME,
            "#buildComp-btn-importAppBuild",
            "#capContainer-cont-appPackages #buildComp-btn-importAppBuild",
        ),
        "bwce": EnvConfig(
            ENV.TP_AUTO_INGRESS_CONTROLLER_BWCE,
            ENV.TP_AUTO_FQDN_BWCE,
            ENV.BWCE_APP_NAME,
            ENV.BWCE_APP_FILE_NAME,
            "#capBuildsCreateNewBuildBtn",
            "#capPackagesBackToDP",
        ),
    }

    po_dp_config = None
    capability = "bwce"
    capability_upper = capability.upper()
    ingress_controller = CONFIGS[capability].ingress_controller
    fqdn = CONFIGS[capability].fqdn
    app_name = CONFIGS[capability].app_name
    app_file_name = CONFIGS[capability].app_file_name
    create_app_build_button_selector = CONFIGS[capability].create_app_build_button_selector
    provision_plugin_button_selector = CONFIGS[capability].provision_plugin_button_selector
    def __init__(self, page, capability):
        super().__init__(page)
        self.po_dp_config = PageObjectDataPlaneConfiguration(page)
        self.set_capability(capability)

    def selector_header_dp_name(self):
        selector = super().selector_header_dp_name()
        if not self.is_fresco:
            selector = "#capabilityHeader-lbl-dpname"
        return selector

    def selector_header_app_name(self):
        selector = super().selector_header_app_name()
        if not self.is_fresco:
            selector = ".app-name"
        return selector

    def selector_header_app_scale_input(self):
        selector = super().selector_header_app_scale_input()
        if not self.is_fresco:
            selector = "#appDtls-appName-cont input.input-scale"
        return selector

    def selector_header_app_action_btn(self):
        selector = super().selector_header_app_action_btn()
        if not self.is_fresco:
            selector = ".start_stop"
        return selector

    def set_capability(self, capability):
        key = capability.strip().lower()
        if key not in self.CONFIGS:
            raise ValueError(f"Unknown capability '{capability}'. Valid options: {list(self.CONFIGS.keys())}")

        self.capability = key
        self.capability_upper = key.upper()

        conf = self.CONFIGS[key]
        self.ingress_controller = conf.ingress_controller
        self.app_name = conf.app_name
        self.app_file_name = conf.app_file_name
        self.create_app_build_button_selector = conf.create_app_build_button_selector
        self.provision_plugin_button_selector = conf.provision_plugin_button_selector
        return self

    def _set_capability(self, capability, ingress_controller):
        self.capability = capability
        self.capability_upper = capability.upper()
        self.ingress_controller = ingress_controller

    def bwce_provision_capability(self, dp_name):
        if ReportYaml.is_capability_for_dataplane_created(dp_name, self.capability):
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, capability '{self.capability}' is already created in DataPlane '{dp_name}'.")
            return
        ColorLogger.info(f"{self.capability_upper} Provisioning capability...")
        self.goto_dataplane(dp_name)
        if self.page.locator(f"capability-card #{self.capability}").is_visible():
            ColorLogger.success(f"{self.capability_upper} capability is already provisioned.")
            ReportYaml.set_capability(dp_name, self.capability)
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
            selected_card_title = self.page.locator('capability-select-card', has=self.page.locator(f'#{self.capability_upper}-capability-select-button')).locator('.capability-title').inner_text().strip()
            selected_card_title = " ".join(selected_card_title.split())
            Util.click_button_until_enabled(self.page, self.page.locator(f'#{self.capability_upper}-capability-select-button'))
            print(f"Clicked '{selected_card_title}' -> 'Start' button")

            print(f"Waiting for {self.capability_upper} capability page is loaded")
            self.page.locator(".resources-content").wait_for(state="visible")
            print(f"{self.capability_upper} capability page is loaded")
            self.page.wait_for_timeout(3000)

            if self.page.locator('#storage-class-resource-table').is_visible():
                print(f"Checking Storage Class table has '{ENV.TP_AUTO_STORAGE_CLASS}' visible...")
                if not Util.check_dom_visibility(self.page, self.page.locator('#storage-class-resource-table tr', has=self.page.locator('td', has_text=ENV.TP_AUTO_STORAGE_CLASS)), 2, 4):
                    ColorLogger.info(f"Adding Storage Class: {ENV.TP_AUTO_STORAGE_CLASS} for {self.capability_upper} capability")
                    if self.page.locator("#add-storage-resource-storage-class-btn").is_visible():
                        self.page.locator("#add-storage-resource-storage-class-btn").click()
                        print("Clicked 'Adding Storage Class' button")
                        # Adding Storage Class dialog popup
                        self.po_dp_config.add_storage(ENV.TP_AUTO_STORAGE_CLASS)

                if Util.check_dom_visibility(self.page, self.page.locator('#storage-class-resource-table tr', has=self.page.locator('td', has_text=ENV.TP_AUTO_STORAGE_CLASS)), 3, 6):
                    self.page.locator('#storage-class-resource-table tr', has=self.page.locator('td', has_text=ENV.TP_AUTO_STORAGE_CLASS)).locator('label').click()
                    print(f"Selected '{ENV.TP_AUTO_STORAGE_CLASS}' Storage Class for {self.capability_upper} capability")
                else:
                    Util.exit_error(f"'{ENV.TP_AUTO_STORAGE_CLASS}' Storage Class is still not available, please check if it is provisioned in Data Plane '{dp_name}'", self.page, f"{self.capability}_provision_capability.png")

            if ENV.TP_AUTO_INGRESS_OBJECT == "gateway":
                # CP 1.17 wizard splits Ingress vs Gateway via an `ingressRouteType-GATEWAYAPI`
                # radio. CP 1.18 dropped that radio: Ingress and Gateway entries coexist in a
                # single Route Resource table and the row label is clicked directly. Click the
                # radio only when present.
                gw_radio = self.page.locator('label[for="ingressRouteType-GATEWAYAPI"]')
                if gw_radio.is_visible():
                    gw_radio.click()
                    self.page.wait_for_timeout(2000)
                    print("Selected 'Gateway API' radio button (CP 1.17 wizard)")
                else:
                    print("'Gateway API' radio not present (CP 1.18 wizard) — picking row directly")
                route_resource_name = ENV.TP_AUTO_GATEWAY_CONTROLLER_BW5CE if self.capability == "bw5ce" else ENV.TP_AUTO_GATEWAY_CONTROLLER_BWCE
            else:
                route_resource_name = self.ingress_controller

            # CP 1.18+ renamed #ingress-resource-table to #route-resource-table
            ingress_table_sel = "#ingress-resource-table, #route-resource-table"
            if self.page.locator(ingress_table_sel).first.is_visible():
                print(f"Checking Ingress/Route table has '{route_resource_name}' visible...")
                if not Util.check_dom_visibility(self.page, self.page.locator(ingress_table_sel).first.locator('tr', has=self.page.locator('td', has_text=route_resource_name)), 2, 4):
                    if ENV.TP_AUTO_INGRESS_OBJECT != "gateway":
                        ColorLogger.info(f"Adding Ingress/Route: {route_resource_name} for {self.capability_upper} capability")
                        add_btn_sel = "#add-ingress-resource-ingress-controller-btn, #add-route-resource-btn"
                        if self.page.locator(add_btn_sel).first.is_visible():
                            self.page.locator(add_btn_sel).first.click()
                            print("Clicked 'Add Ingress/Route Resource' button")
                            self.po_dp_config.add_ingress_controller(
                                ENV.TP_AUTO_INGRESS_CONTROLLER, route_resource_name,
                                ENV.TP_AUTO_INGRESS_CONTROLLER_CLASS_NAME, self.fqdn,
                                "route" if self.page.locator('#route-resource-table').is_visible() else "ingress"
                            )

                if Util.check_dom_visibility(self.page, self.page.locator(ingress_table_sel).first.locator('tr', has=self.page.locator('td', has_text=route_resource_name)), 3, 6):
                    self.page.locator(ingress_table_sel).first.locator('tr', has=self.page.locator('td', has_text=route_resource_name)).locator('label').click()
                    print(f"Selected '{route_resource_name}' Ingress/Route for {self.capability_upper} capability")
                else:
                    Util.exit_error(f"'{route_resource_name}' Ingress/Route is still not available, please check if it is provisioned in Data Plane '{dp_name}'", self.page, f"{self.capability}_provision_capability.png")

            self.page.locator("#btnNextCapabilityProvision", has_text="Next").click()
            print(f"Clicked {self.capability_upper} 'Next' button, finished step 1")
            self.page.wait_for_timeout(3000)
            # CP 1.18+ removed the EULA checkbox
            if self.page.locator(".resource-agree label").is_visible():
                self.page.locator(".resource-agree label").click()
                print(f"Clicked {self.capability_upper} 'EUA' checkbox")
                self.page.wait_for_timeout(500)
            else:
                print(f"No EULA checkbox (CP 1.18+), skipping")
            self.page.locator("#btnNextCapabilityProvision").click()

            # for bw5ce dom selector
            if Util.check_dom_visibility(self.page, self.page.locator("#btnProvCapabilityProvision"), 2, 2):
                self.page.locator("#btnProvCapabilityProvision").click()
                print(f"Preview/Customize Recipe page is loaded, clicked '{self.capability_upper} (Containers) Provision Capability' button")

            # for bwce dom selector
            if Util.check_dom_visibility(self.page, self.page.locator("#btnCapabilityProvision"), 2, 2):
                self.page.locator("#btnCapabilityProvision").click()
                print(f"Preview/Customize Recipe page is loaded, clicked '{self.capability_upper} (Containers) Provision Capability' button")

            print(f"Clicked '{self.capability_upper} Provision Capability' button, waiting for {self.capability_upper} Capability Provision Request Completed")
            if Util.check_dom_visibility(self.page, self.page.locator(".resource-success .title", has_text="Capability Provision Request Completed"), 5, 120):
                ColorLogger.success(f"Provision {self.capability_upper} capability successful.")
            if self.page.locator("#capProvBackToDPBtn").is_visible():
                self.page.locator("#capProvBackToDPBtn").click()
                print("Clicked 'Go Back To Data Plane Details' button")
            else:
                ColorLogger.warning(f"Can not find 'Go Back To Data Plane Details' button, click left menu navigator to Data Plane '{dp_name}'")
                self.goto_dataplane(dp_name)
        else:
            Util.exit_error("'Provision a capability' button is not visible.", self.page, f"{self.capability}_provision_capability.png")

        print(f"Reload Data Plane page, and check if {self.capability_upper} capability is provisioned...")
        Util.refresh_page(self.page)
        print(f"Waiting for {self.capability_upper} capability is in capability list...")
        is_dataplane_container_available = Util.check_dom_visibility(self.page, self.page.locator(".data-plane-container"), 5, 20, True)
        if is_dataplane_container_available and self.is_capability_provisioned(self.capability):
            ColorLogger.success(f"{self.capability_upper} capability is in capability list")
            ReportYaml.set_capability(dp_name, self.capability)
        else:
            Util.warning_screenshot(f"{self.capability_upper} capability is not in capability list", self.page, f"{self.capability}_provision_capability-2.png")

    def bwce_provision_connector(self, dp_name, app_name = None):
        app_name = app_name or self.app_name
        if ReportYaml.get_capability_info(dp_name, self.capability, "provisionConnector") == "true":
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, '{self.capability}' Connector is already created in DataPlane '{dp_name}'.")
            return
        ColorLogger.info(f"{self.capability_upper} Provisioning connector...")

        # if app is created, not need to check capability status
        is_check_status = True
        if ReportYaml.is_app_created(dp_name, self.capability, app_name) or self.is_app_created(self.capability, app_name):
            is_check_status = False
            print(f"'{self.capability}'App '{app_name}' has been created, no need to check '{self.capability}' capability status")

        capability_selector_path = "#capContainer-cont-appPackages"
        self.goto_capability(dp_name, self.capability, capability_selector_path, is_check_status)

        self.page.locator(capability_selector_path).wait_for(state="visible")
        print(f"{self.capability_upper} capability page loaded, Checking Plugins...")
        self.page.wait_for_timeout(3000)

        if self.page.locator("#capContainer-cont-appPackages .caret-icon").is_visible():
            self.page.locator("#capContainer-cont-appPackages .caret-icon").click()
            print("Clicked 'Expand' icon to show Plugins list")

        plugins = [text.strip() for text in self.page.locator("#pkgsTbl-table-listPkg td:first-child").all_inner_texts()]
        # Note: check 2 times, because sometimes BWCE Plugins cannot be loaded in time
        # if plugin is empty, reload page, and check again, only check 2 times, if still empty, exit for loop
        for i in range(2):
            if plugins:
                break
            Util.refresh_page(self.page)
            self.page.locator(capability_selector_path).wait_for(state="visible")
            print(f"{self.capability_upper} capability page loaded, Checking Plugins...")
            self.page.wait_for_timeout(3000)
            plugins = [text.strip() for text in self.page.locator("#pkgsTbl-table-listPkg td:first-child").all_inner_texts()]

        print(f"{self.capability_upper} Plugins: {plugins}")
        required_connectors = {self.capability_upper}
        # This is a compatibility handling after BWCE changed to BW6 (Containers) in version 1.10
        name_map = {
            "BWCE": "BW6 (Containers)",
            "BW5CE": "BW5 (Containers)"
        }
        mapped_name = name_map.get(self.capability_upper)
        if required_connectors.issubset(set(plugins)) or (mapped_name and {mapped_name}.issubset(set(plugins))):
            ColorLogger.success(f"{self.capability_upper} Plugins are already provisioned.")
            ReportYaml.set_capability_info(dp_name, self.capability, "provisionConnector", True)
            self.page.locator(self.selector_header_dp_name(), has_text=dp_name).click()
            print(f"Clicked menu navigator Data Plane '{dp_name}', go back to Data Plane detail page")
            return

        print(f"Start to Provision {self.capability_upper} Plugins...")

        # Note: do not change below locator, this is to be compatible with both BWCE and BW5CE
        self.page.locator(self.provision_plugin_button_selector, has_text="Provision").wait_for(state="visible")
        self.page.locator(self.provision_plugin_button_selector, has_text="Provision").click()
        print("Clicked 'Provision' button")
        self.page.locator("#provisionPluginUpdt-footBtn-nextStep").click()
        print("Clicked 'Next' button")
        self.page.locator("#FinishedProvisionPlugin img[src*='success.svg']").wait_for(state="visible")
        self.page.locator("#btnNavigationToIntegrationDetailsbtnRight", has_text="View Integration Capabilities details").click()
        print("Clicked 'View Integration Capabilities detail' button")
        if required_connectors.issubset(set(plugins)):
            ColorLogger.success("Provision successful.")
            ReportYaml.set_capability_info(dp_name, self.capability, "provisionConnector", True)
        self.page.locator(self.selector_header_dp_name(), has_text=dp_name).click()
        print(f"Clicked menu navigator Data Plane '{dp_name}', go back to Data Plane detail page")

    def bwce_provision_version(self, dp_name):
        """Provision the runtime version (with its default plugins) so the
        'Create New App Build & Deploy' button appears on the capability page.

        On a FRESH capability the App Builds area shows a 'Provision (Containers) &
        Plug-ins' button instead of the build button (App Builds reads 0 /
        "version provisioned yet"). This walks the 2-step provision wizard
        (Step 1 'Select Versions' -> Step 2 'Provisioning') accepting the
        pre-selected default version, then returns to the capability page.

        Verified on BOTH bw5ce and bwce: only the entry button differs (captured by
        provision_plugin_button_selector — bw5ce: the in-appPackages
        #buildComp-btn-importAppBuild, bwce: #capPackagesBackToDP); the wizard is
        shared (#provisionPluginUpdt-footBtn-nextStep; completion signalled by
        #btnNavigationToIntegrationDetailsbtnRight).
        """
        ColorLogger.info(f"{self.capability_upper} Provisioning runtime version...")
        # Click the capability's 'Provision (Containers) & Plug-ins' entry button
        # (provision_plugin_button_selector differs per capability; the wizard does not).
        # Re-query the locator on each interaction (do not cache) per project rules.
        if not Util.check_dom_visibility(self.page, self.page.locator(self.provision_plugin_button_selector, has_text="Provision").first, 2, 6):
            Util.exit_error(f"{self.capability_upper} 'Provision (Containers) & Plug-ins' button is not visible.", self.page, f"{self.capability}_provision_version.png")
        self.page.locator(self.provision_plugin_button_selector, has_text="Provision").first.click()
        print(f"Clicked 'Provision {self.capability_upper} (Containers) & Plug-ins' button")

        # Step 1: Select Versions — the default runtime version is pre-selected.
        if not Util.check_dom_visibility(self.page, self.page.locator("#provisionPluginUpdt-footBtn-nextStep"), 2, 10):
            Util.exit_error(f"{self.capability_upper} provision wizard 'Next' button is not visible.", self.page, f"{self.capability}_provision_version-step1.png")
        self.page.wait_for_timeout(1000)
        self.page.locator("#provisionPluginUpdt-footBtn-nextStep").click()
        print(f"Clicked 'Next' on 'Select Versions' step, {self.capability_upper} provisioning started")

        # Step 2: Provisioning — completion shows the 'View Integration Capabilities
        # details' button.
        if not Util.check_dom_visibility(self.page, self.page.locator("#btnNavigationToIntegrationDetailsbtnRight"), 5, 180):
            Util.exit_error(f"{self.capability_upper} version provisioning did not complete in time.", self.page, f"{self.capability}_provision_version-step2.png")
        ColorLogger.success(f"{self.capability_upper} runtime version provisioned successfully.")
        self.page.locator("#btnNavigationToIntegrationDetailsbtnRight").click()
        print("Clicked 'View Integration Capabilities details', back to capability page")
        self.page.wait_for_timeout(3000)

    def bwce_app_build_and_deploy(self, dp_name, app_file_name = None, app_name = None):
        app_file_name = app_file_name or self.app_file_name
        app_name = app_name or self.app_name

        if ReportYaml.get_capability_info(dp_name, self.capability, "appBuild") == "true":
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, '{self.capability}' App Build '{app_name}' is already created in DataPlane '{dp_name}'.")
            return
        ColorLogger.info(f"{self.capability_upper} Creating app build...")

        # if app is created, not need to check capability status
        is_check_status = True
        if ReportYaml.is_app_created(dp_name, self.capability, app_name) or self.is_app_created(self.capability, app_name):
            is_check_status = False
            print(f"'{self.capability}'App '{app_name}' has been created, no need to check '{self.capability}' capability status")
        self.goto_capability(dp_name, self.capability, "#capContainer-cont-appPackages", is_check_status)

        print(f"{self.capability_upper} Checking app build...")
        # self.page.locator("#capContainer-cont-appBuilds").wait_for(state="visible")
        # print(f"{self.capability_upper} capability page loaded, Checking {self.capability_upper} App Builds...")
        # self.page.wait_for_timeout(3000)

        is_app_build_created = Util.refresh_until_success(self.page,
                                                          self.page.locator("#capContainer-cont-appBuilds td", has_text=app_name),
                                                          self.page.locator("#capContainer-cont-appBuilds"),
                                                          f"{self.capability_upper} capability page loaded, Checking {self.capability_upper} App Builds...")

        if is_app_build_created:
            ColorLogger.success(f"{self.capability_upper} app build {app_name} is already created.")
            ReportYaml.set_capability(dp_name, self.capability)
            ReportYaml.set_capability_info(dp_name, self.capability, "appBuild", True)
            return

        print(f"Start Create {self.capability_upper} app build...")

        # On a fresh capability the runtime version is not provisioned, so the
        # 'Create New App Build & Deploy' button is absent (the page shows a
        # 'Provision (Containers) & Plug-ins' button instead). Provision the version
        # first, then the build button appears. (has_text is case-insensitive, so it
        # matches the actual 'Create New APP Build & Deploy' label.)
        if not Util.check_dom_visibility(self.page, self.page.locator(self.create_app_build_button_selector, has_text="Create New App Build & Deploy"), 2, 4):
            ColorLogger.warning(f"{self.capability_upper} 'Create New App Build & Deploy' not visible — runtime version not provisioned yet, provisioning now...")
            self.bwce_provision_version(dp_name)

        # After provisioning the version, the build button can take a few seconds to
        # render — poll for it rather than a bare is_visible().
        if not Util.check_dom_visibility(self.page, self.page.locator(self.create_app_build_button_selector, has_text="Create New App Build & Deploy"), 3, 30):
            Util.exit_error(f"{self.capability_upper} 'Create New App Build & Deploy' button is not visible, check {self.capability_upper} provision page.", self.page, f"{self.capability}_app_build_and_deploy.png")

        self.page.locator(self.create_app_build_button_selector, has_text="Create New App Build & Deploy").click()
        print("Clicked 'Create New App Build & Deploy' button")

        # step1: Upload Files
        self.page.locator("ul.pl-secondarynav__menu .is-active a", has_text="Upload EAR").wait_for(state="visible")
        print(f"{self.capability_upper} 'App Build & Deploy' Step 1: 'Upload EAR' page is loaded")
        file_path = Helper.get_app_file_fullpath(app_file_name)
        self.page.locator('input[type="file"]').evaluate("(input) => input.style.display = 'block'")

        self.page.locator('input[type="file"]').set_input_files(file_path)
        print(f"Selected file: {file_path}")
        self.page.locator('.fileUploaded .file-name', has_text=app_file_name).wait_for(state="visible")
        self.page.locator('#fileUploadBrowseFileBtn').click()
        print("Clicked 'Upload Selected File' button")
        self.page.locator('.file-uploaded .msg strong', has_text="File Uploaded Successfully").wait_for(state="visible")
        print(f"File '{app_file_name}' Uploaded Successfully")
        self.page.locator('#DeployUploadEARNextBtn').click()
        print("Clicked 'Next' button")

        # step2: Select Versions
        self.page.locator("#bldConf-tblBody-txt-appBuildName-text-input").wait_for(state="visible")
        self.page.wait_for_timeout(2000)
        active_title = self.page.locator("ul.pl-secondarynav__menu .is-active a").inner_text()
        print(f"{self.capability_upper} 'App Build & Deploy' Step 2: '{active_title}' page is loaded")
        if self.page.locator("#bldConf-tblBody-btn-refreshProvBWCEList", has_text="Refresh").is_visible():
            self.page.locator("#bldConf-tblBody-btn-refreshProvBWCEList", has_text="Refresh").click()
            print("Clicked 'Refresh' button to refresh BWCE versions list")
            self.page.wait_for_timeout(2000)
        self.page.locator("#bldConf-tblBody-txt-appBuildName-text-input").fill(app_name)
        print(f"Filled App Build Name: {app_name}")

        # click 'Create Build' button in step2
        self.page.locator('#DeployDeployBtn').click()
        print("Clicked 'Create Build' button")

        # step3:
        self.page.wait_for_timeout(2000)
        active_title = self.page.locator("ul.pl-secondarynav__menu .is-active a").inner_text()
        print(f"{self.capability_upper} 'App Build & Deploy' Step 3: '{active_title}' page is loaded")
        # if step3 is "App Build", will deploy app later, it is for 1.5 version
        # click "Deploy App" button will go to "Resource Configurations" step,
        # same as 1.4 version, and then deploy bwce app from "Resource Configurations" step
        if active_title == "App Build":
            if Util.wait_for_success_message(self.page, 5) is False:
                Util.exit_error(f"API return failed message, failed to create {self.capability_upper} {app_name} app build", self.page, f"{self.capability}_app_build_and_deploy.png")

            print("Waiting for 'Successfully created App Build'")
            if Util.check_dom_visibility(self.page, self.page.locator('.stages .step .message', has_text="Successfully created App Build"),3, 60):
                print(f"Successfully created {self.capability_upper} {app_name} app build")
                self.page.locator('#finishDeployViewAppBuildsBtn-1', has_text="Deploy App").wait_for(state="visible")
                self.page.locator('#finishDeployViewAppBuildsBtn-1', has_text="Deploy App").click()
                print("Clicked 'Deploy App' button from Finish tab")
                self.page.locator('#appMngModal-btn-deployBWprov', has_text="Deploy").wait_for(state="visible")
                self.page.locator('#appMngModal-btn-deployBWprov', has_text="Deploy").click()
                print("Clicked 'Deploy' button from Deploy App Dialog")
            else:
                Util.exit_error(f"No success message is seen, Failed to create {self.capability_upper} {app_name} app build", self.page, f"{self.capability}_app_build_and_deploy.png")

            self.bwce_app_build_and_deploy_select_namespace(app_name)

        # below steps is after "Resource Configurations" step
        self.page.locator('#deployComp-btn-ResourceConfigBtn2').click()
        print("Clicked 'Deploy App' button")

        self.page.locator("finished img[src*='success.svg']").wait_for(state="visible")
        ColorLogger.success(f"Created {self.capability_upper} app build '{app_name}' Successfully")
        print(f"Check if {self.capability_upper} app deployed successfully...")

        if Util.check_dom_visibility(self.page, self.page.locator('.stages .step .message', has_text="Successfully Deployed Application"), 5, 60):
            ColorLogger.success(f"{self.capability_upper} app build '{app_name}' is deployed.")
            ReportYaml.set_capability_info(dp_name, self.capability, "appBuild", True)

    def bwce_app_build_and_deploy_select_namespace(self, app_name = None):
        app_name = app_name or self.app_name
        self.page.locator("#nameSpace input").wait_for(state="visible")
        print(f"App Resource Configuration' page loaded")
        self.page.locator("#nameSpace input").click()
        print(f"Clicked 'Namespace' dropdown, and waiting for namespace: {ENV.TP_AUTO_K8S_DP_NAMESPACE}")
        self.page.wait_for_timeout(1000)
        if not self.page.locator("#nameSpace .pl-select-menu li", has_text=ENV.TP_AUTO_K8S_DP_NAMESPACE).is_visible():
            Util.exit_error(f"Namespace '{ENV.TP_AUTO_K8S_DP_NAMESPACE}' is not list in the dropdown.", self.page, f"{self.capability}_app_build_and_deploy.png")

        self.page.locator("#nameSpace .pl-select-menu li", has_text=ENV.TP_AUTO_K8S_DP_NAMESPACE).click()
        print(f"Selected namespace: {ENV.TP_AUTO_K8S_DP_NAMESPACE}")

        if self.page.locator("#app-name-text-input").is_visible():
            self.page.locator("#app-name-text-input").clear()
            self.page.locator("#app-name-text-input").fill(app_name)
            print(f"Filled App Name: {app_name}")

        self.page.locator("label[for='eula-checkbox']").click()
        print("Clicked 'EUA' checkbox")
        self.page.wait_for_timeout(1000)

    def bwce_app_deploy(self, dp_name, app_name = None):
        app_name = app_name or self.app_name

        if ReportYaml.is_app_created(dp_name, self.capability, app_name):
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, '{self.capability}' App '{app_name}' is already created in DataPlane '{dp_name}'.")
            return
        ColorLogger.info(f"{self.capability_upper} Deploying app '{app_name}'...")
        dp_name_space = ENV.TP_AUTO_K8S_DP_NAMESPACE

        self.goto_dataplane(dp_name)
        print(f"Checking if {self.capability_upper} app '{app_name}' is in dataplane {dp_name}.")
        if self.page.locator("apps-list td.app-name a", has_text=app_name).is_visible():
            ColorLogger.success(f"{self.capability_upper} app '{app_name}' in dataplane {dp_name} is already deployed.")
            ReportYaml.set_capability_app(dp_name, self.capability, app_name)
            return

        # if app is created, not need to check capability status
        is_check_status = True
        if ReportYaml.is_app_created(dp_name, self.capability, app_name) or self.is_app_created(self.capability, app_name):
            is_check_status = False
            print(f"'{self.capability}'App '{app_name}' has been created, no need to check '{self.capability}' capability status")
        self.goto_capability(dp_name, self.capability, "#capContainer-cont-appPackages", is_check_status)

        print(f"Waiting for {self.capability_upper} app build {app_name} is deployed...")
        if not Util.check_dom_visibility(self.page, self.page.locator("#bldTbl-table-buildsList tr td", has_text=app_name), 5, 180, True):
            Util.exit_error(f"{self.capability_upper} app {app_name} is not deployed.", self.page, f"{self.capability}_app_deploy.png")

        # if capability appBuild has not been set to true, set it to true
        # in bwce_app_build_and_deploy function, the appBuild has not displayed, but now it is displayed, should set appBuild to true
        if ReportYaml.get_capability_info(dp_name, self.capability, "appBuild") != "true":
            ReportYaml.set_capability_info(dp_name, self.capability, "appBuild", True)

        self.page.locator("#bldTbl-table-buildsList tr", has=self.page.locator("td", has_text=app_name)).nth(0).locator('#builds-menu-dropdown-label').click()
        print(f"Clicked action menu button for {app_name}")
        self.page.locator("#bldTbl-table-buildsList tr", has=self.page.locator("td", has_text=app_name)).nth(0).locator('.pl-dropdown .pl-dropdown-menu__item button', has_text="Deploy").click()
        print(f"Clicked 'Deploy' from action menu list for {app_name}")

        self.page.wait_for_timeout(1000)
        # Deploy App dialog is for 1.4, 1.5 version
        if Util.check_dom_visibility(self.page, self.page.locator('#appMngModal-btn-deployBWprov', has_text="Deploy"), 3, 6):
            print("Deploy App Dialog popup")
            self.page.locator('#appMngModal-btn-deployBWprov', has_text="Deploy").click()
            print("Clicked 'Deploy App' button from Deploy App Dialog")
            self.bwce_app_build_and_deploy_select_namespace(app_name)

            self.page.locator('#deployComp-btn-ResourceConfigBtn2').click()
            print("Clicked 'Deploy App' button")
            print(f"Check if {self.capability_upper} app deployed successfully...")
            if Util.check_dom_visibility(self.page, self.page.locator('.stages .step .message', has_text="Successfully Deployed Application"), 5, 120):
                self.page.locator("#finished-btn-gotoDPDetails-finishDeployViewDeployBuildsBtn-1").click()
                print("Clicked 'View Deployed App' button, go back to Data Plane detail page")
        else:
            # if a case goes here, it means the Deploy App dialog is not popup, CP version maybe is 1.3, it has not been tested
            print("Dialog 'Deploy App Build' does not popup")
            Util.exit_error(f"{self.capability_upper} app {app_name} dialog 'Deploy App Build' does not popup.", self.page, f"{self.capability}_app_deploy.png")

        print(f"Waiting for {self.capability_upper} app '{app_name}' is deployed...")
        if Util.check_dom_visibility(self.page, self.page.locator("apps-list td.app-name a", has_text=app_name), 5, 120):
            ColorLogger.success(f"Deploy {self.capability_upper} app '{app_name}' in namespace {dp_name_space} Successfully")
            ReportYaml.set_capability_app(dp_name, self.capability, app_name)
        else:
            Util.warning_screenshot(f"Deploy {self.capability_upper} app '{app_name}' in namespace {dp_name_space} may failed.", self.page, f"{self.capability}_app_deploy-2.png")

    def bwce_app_config(self, dp_name, app_name = None):
        app_name = app_name or self.app_name

        ColorLogger.info(f"{self.capability_upper} Config app '{app_name}'...")
        self.goto_app_detail(dp_name, app_name, self.selector_header_app_name())

        if ReportYaml.get_capability_app_info(dp_name, self.capability, app_name, "endpointPublic") == "true":
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, '{self.capability}' Endpoints is already Public in DataPlane '{dp_name}'.")
        else:
            if self.page.locator(".no-endpoints", has_text="There are no Endpoints configured for the application").is_visible():
                Util.warning_screenshot(f"There is some error for {self.capability_upper} app '{app_name}', it has no Endpoints configured.", self.page, f"{self.capability}_app_config.png")
                return

            self.page.locator("#tab-endpoints").click()
            print("Clicked 'Endpoints' tab")
            # set Endpoint Visibility to Public
            self.page.locator(".endpoints").wait_for(state="visible")
            print("Endpoint tab is loaded.")
            if Util.check_dom_visibility(self.page, self.page.locator("#endpointV1-btn-openSwagger"), 2, 6):
                ColorLogger.success(f"{self.capability_upper} app '{app_name}' has set Endpoint Visibility to Public.")
                ReportYaml.set_capability_app_info(dp_name, self.capability, app_name, "endpointPublic", True)
            else:
                print("No 'Test' button, will set Endpoint Visibility to Public")
                self.page.locator(self.selector_header_action_menu()).wait_for(state="visible")
                self.page.locator(self.selector_header_action_menu()).click()
                self.page.locator(self.selector_header_action_menu_item(), has_text="Set Endpoint Visibility").wait_for(state="visible")
                self.page.locator(self.selector_header_action_menu_item(), has_text="Set Endpoint Visibility").click()
                print("Clicked 'Set Endpoint Visibility' menu item")
                self.page.locator("#appDtls-appEndPntMod1-btn-saveChanges", has_text="Save Changes").wait_for(state="visible")
                print("Dialog 'Set Endpoint Visibility' popup")
                texts = self.page.locator(".pl-modal__container strong").nth(0).all_inner_texts()
                if any(t in ["Set Endpoint visibility", "Update Endpoint visibility"] for t in texts):
                    route_resource = (ENV.TP_AUTO_GATEWAY_CONTROLLER_BW5CE if self.capability == "bw5ce" else ENV.TP_AUTO_GATEWAY_CONTROLLER_BWCE) if ENV.TP_AUTO_INGRESS_OBJECT == "gateway" else self.ingress_controller
                    if ENV.TP_AUTO_INGRESS_OBJECT == "gateway":
                        gateway_label = self.page.locator('label[for="endpoint-type-gateway"], label[for="gateway"]').first
                        if Util.check_dom_visibility(self.page, gateway_label, 1, 2):
                            gateway_label.click()
                            self.page.wait_for_timeout(2000)
                            print("Selected 'Gateway' resource type in endpoint dialog")
                    if self.page.locator(".pl-table__cell label", has_text=route_resource).is_visible():
                        self.page.locator(".pl-table__cell label", has_text=route_resource).click()
                        print(f"Selected '{route_resource}' from Resource Name column")
                        self.page.locator('label[for="endpoint-radio-0-public"]').click()
                        if self.page.locator("#appDtls-appEndPntMod1-btn-saveChanges", has_text="Save Changes").is_enabled():
                            print("Set Public Endpoint Visibility to 'Public'")
                            self.page.locator("#appDtls-appEndPntMod1-btn-saveChanges", has_text="Save Changes").click()
                            print("Clicked 'Save Changes' button")
                            if Util.wait_for_success_message(self.page, 5) and self.page.locator("#endpointV1-btn-openSwagger").is_visible():
                                ColorLogger.success(f"{self.capability_upper} app '{app_name}' has set Endpoint Visibility to Public.")
                                ReportYaml.set_capability_app_info(dp_name, self.capability, app_name, "endpointPublic", True)
                        else:
                            ColorLogger.warning(f"{self.capability_upper} app '{app_name}' has set Endpoint Visibility to Public.")
                            self.page.locator(".pl-modal__footer-left button", has_text="Cancel").click()
                            print(f"Clicked 'Cancel' button from '{texts}' dialog")
                    else:
                        Util.warning_screenshot(f"Not able to set Endpoint Visibility to Public, '{route_resource}' is not available.", self.page, f"{self.capability}_app_config-endpoint.png")

                # The endpoint dialog auto-closes only on a successful save. If the
                # save produced no success toast (e.g. the endpoint is already Public,
                # so the backend reports no change), the dialog stays open and would
                # intercept the next tab click (Environmental Controls) -> Timeout.
                # Close it explicitly before moving on.
                if Util.check_dom_visibility(self.page, self.page.locator("#appDtls-appEndPntMod1-btn-saveChanges"), 2, 4):
                    # Don't mask a real failure: if Save raised an error toast, surface
                    # it with a screenshot before dismissing the (still-open) dialog.
                    if self.page.locator(".pl-notification--error").is_visible():
                        Util.warning_screenshot(f"{self.capability_upper} app '{app_name}' Set Endpoint Visibility reported an error.", self.page, f"{self.capability}_app_config-endpoint-error.png")
                    if self.page.locator(".pl-modal__footer-left button", has_text="Cancel").first.is_visible():
                        self.page.locator(".pl-modal__footer-left button", has_text="Cancel").first.click()
                        print("Endpoint dialog still open after save — clicked 'Cancel' to close it")
                        self.page.wait_for_timeout(1000)

        if ReportYaml.get_capability_app_info(dp_name, self.capability, app_name, "enableTrace") == "true":
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, '{self.capability}' Trace is already Enabled in DataPlane '{dp_name}'.")
        else:
            # set Engine Variables, BW_OTEL_TRACES_ENABLED to true
            print("Navigating to 'Engine Variables' tab menu")
            self.page.locator(".pl-primarynav__menu .pl-primarynav__item", has_text="Environmental Controls").click()
            print("Clicked 'Environmental Controls' tab menu")
            self.page.wait_for_timeout(1000)
            self.page.locator("#evnCtlEngineVarsTab", has_text="Engine Variables").wait_for(state="visible")
            self.page.locator("#evnCtlEngineVarsTab", has_text="Engine Variables").click()
            self.page.wait_for_timeout(1000)
            print("Clicked 'Engine Variables' left side menu")
            self.page.locator(".engine-variables").wait_for(state="visible")
            print("'Engine Variables' table is loaded.")
            traces_row = self.page.get_by_role("row", name="BW_OTEL_TRACES_ENABLED")
            traces_row.wait_for(state="visible")
            otel_trace_selector = traces_row.locator("#engVars-btn-toggleBoolea")
            if otel_trace_selector.inner_text().lower() == "true":
                ColorLogger.success("BW_OTEL_TRACES_ENABLED is already set to true.")
                ReportYaml.set_capability_app_info(dp_name, self.capability, app_name, "enableTrace", True)
            else:
                otel_trace_selector.click()
                traces_row.locator("#engVars-btn-valTrue").wait_for(state="visible")
                traces_row.locator("#engVars-btn-valTrue").click()
                print("Set BW_OTEL_TRACES_ENABLED to true")
                self.page.wait_for_timeout(1000)
                self.page.locator("#engVars-btn-pushUpdates").click()
                print("Clicked 'Push Updates' button")
                if Util.wait_for_success_message(self.page, 5):
                    ColorLogger.success("Set BW_OTEL_TRACES_ENABLED to true successfully.")
                    ReportYaml.set_capability_app_info(dp_name, self.capability, app_name, "enableTrace", True)

    def bwce_app_start(self, dp_name, app_name = None):
        app_name = app_name or self.app_name

        if ReportYaml.get_capability_app_info(dp_name, self.capability, app_name, "status") == "Running" or self.is_app_running(dp_name, self.capability, app_name):
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, '{self.capability}' App '{app_name}' is Running in DataPlane '{dp_name}'.")
            return
        ColorLogger.info(f"{self.capability_upper} Start app '{app_name}'...")
        self.goto_app_detail(dp_name, app_name, self.selector_header_app_name())

        print("Waiting to see if app status is Running...")
        if self.get_app_instance_number() > 0:
            ColorLogger.success(f"{self.capability_upper} app '{app_name}' is already running.")
            ReportYaml.set_capability_app_info(dp_name, self.capability, app_name, "status", "Running")
        else:
            self.page.locator(self.selector_header_app_action_btn(), has_text="Start").click()
            print("Clicked 'Start' app button")

            print(f"Waiting for app '{app_name}' status is Running...")
            if Util.check_dom_visibility(self.page, self.page.locator(self.selector_header_app_action_btn(), has_text="Stop"), 15, 240, True):
                app_status = self.get_app_status()
                ColorLogger.success(f"{self.capability_upper} app '{app_name}' status is '{app_status}' now.")
                ReportYaml.set_capability_app_info(dp_name, self.capability, app_name, "status", app_status)
            else:
                Util.warning_screenshot(f"Wait too long to scale {self.capability_upper} app '{app_name}'.", self.page, f"{self.capability}_app_start.png")

    def bwce_app_test_endpoint(self, dp_name, app_name = None):
        app_name = app_name or self.app_name

        if self.capability == "bw5ce":
            ColorLogger.warning(f"{self.capability} app does not have 'Test' button in Endpoints tab, skip testing endpoint.")
            return

        if ReportYaml.get_capability_app_info(dp_name, self.capability, app_name, "testedEndpoint") == "true":
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, has tested '{self.capability}' App '{app_name}' endpoint in DataPlane '{dp_name}'.")
            return
        ColorLogger.info(f"{self.capability_upper} Test app endpoint '{app_name}'...")
        self.goto_app_detail(dp_name, app_name, self.selector_header_app_name())

        print("Navigating to 'Endpoints' tab menu")
        self.page.locator("#tab-endpoints").click()
        print("Clicked 'Endpoints' tab")
        self.page.locator(".endpoint-menu-dropdown").wait_for(state="visible")
        print("Endpoint tab is loaded.")
        self.page.wait_for_timeout(1000)

        if self.get_app_instance_number() == 0:
            app_status = self.get_app_status()
            Util.warning_screenshot(f"Current {self.capability_upper} app '{app_name}' status is not Running, it is {app_status}, will skip test app endpoint.", self.page, f"{self.capability}_app_test_endpoint.png")
            return

        print("Check if 'Test' button is visible...")
        test_btn = self.page.locator("#endpointV1-btn-openSwagger")
        if test_btn.is_visible() and test_btn.is_enabled():
            with self.page.context.expect_page() as new_page_info:
                test_btn.click()
                print("Clicked 'Test' button")

            new_page = new_page_info.value
            print("New window detected and captured.")

            print("Waiting for Swagger page loaded.")
            new_page.wait_for_load_state()

            print(f"Waiting for Swagger title '{app_name}' to be displayed.")
            if Util.check_dom_visibility(new_page, new_page.locator("h2.title"), 5, 15, True):
                # new_page.locator("h2.title", has_text=app_name).wait_for(state="visible")
                # print(f"The Swagger title '{app_name}' is displayed.")

                new_page.locator("#operations-Resource-post-resource .opblock-summary-control").click()
                print("Clicked '/resource' path, expand API details")

                new_page.locator("#operations-Resource-post-resource button", has_text="Try it out").click()
                print("Clicked 'Try it out' button")
                new_page.locator("#operations-Resource-post-resource textarea").clear()
                new_page.locator("#operations-Resource-post-resource textarea").fill('{}')
                new_page.locator("#operations-Resource-post-resource button", has_text="Execute").click()
                print("Clicked 'Execute' button")
                new_page.close()
                print("Closed Swagger page")
                ColorLogger.success(f"Test {self.capability_upper} app '{app_name}', endpoint '/resource'")
                ReportYaml.set_capability_app_info(dp_name, self.capability, app_name, "testedEndpoint", True)
            else:
                Util.warning_screenshot(f"Swagger page is not loaded, title '{app_name}' is not displayed.", new_page, f"{self.capability}_app_test_endpoint.png")
        else:
            Util.warning_screenshot(f"'Test' button is not visible in {self.capability_upper} app {app_name}, need to config it and start app.", self.page, f"{self.capability}_app_test_endpoint.png")
