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
from utils.helper import Helper
from utils.env import ENV
from utils.report import ReportYaml
from page_object.po_dataplane import PageObjectDataPlane
from page_object.po_dp_config import PageObjectDataPlaneConfiguration

class PageObjectDataPlaneSpringBoot(PageObjectDataPlane):
    po_dp_config = None
    capability = "sb"
    def __init__(self, page):
        self.po_dp_config = PageObjectDataPlaneConfiguration(page)
        super().__init__(page)

    def springboot_provision_capability(self, dp_name):
        capability = self.capability
        if ReportYaml.is_capability_for_dataplane_created(dp_name, capability):
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, capability '{capability}' is already created in DataPlane '{dp_name}'.")
            return
        ColorLogger.info("SpringBoot Provisioning capability...")
        self.goto_dataplane(dp_name)
        if self.page.locator(f"capability-card #{capability}").is_visible():
            ColorLogger.success("SpringBoot capability is already provisioned.")
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
            Util.click_button_until_enabled(self.page, self.page.locator('#SB-capability-select-button'))
            print("Clicked 'Provision SpringBoot' -> 'Start' button")

            print("Waiting for SpringBoot capability page is loaded")
            self.page.locator(".resources-content").wait_for(state="visible")
            print("SpringBoot capability page is loaded")
            self.page.wait_for_timeout(3000)

            if self.page.locator('#storage-class-resource-table').is_visible():
                storage_row_locator = self.page.locator('#storage-class-resource-table tr', has=self.page.locator('td:nth-child(2)', has_text=ENV.TP_AUTO_STORAGE_CLASS))
                print(f"Checking Storage Class table has '{ENV.TP_AUTO_STORAGE_CLASS}' visible...")
                if not Util.check_dom_visibility(self.page, storage_row_locator, 2, 4):
                    ColorLogger.info(f"Adding Storage Class: {ENV.TP_AUTO_STORAGE_CLASS} for {self.capability} capability")
                    if self.page.locator("#add-storage-resource-storage-class-btn").is_visible():
                        self.page.locator("#add-storage-resource-storage-class-btn").click()
                        print("Clicked 'Adding Storage Class' button")
                        self.po_dp_config.add_storage(ENV.TP_AUTO_STORAGE_CLASS)

                if Util.check_dom_visibility(self.page, storage_row_locator, 3, 6):
                    storage_row_locator.locator('label').click()
                    print(f"Selected '{ENV.TP_AUTO_STORAGE_CLASS}' Storage Class for {self.capability} capability")
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
                route_resource_name = ENV.TP_AUTO_GATEWAY_CONTROLLER_SPRINGBOOT
            else:
                route_resource_name = ENV.TP_AUTO_INGRESS_CONTROLLER_SPRINGBOOT

            # CP 1.18+ renamed #ingress-resource-table to #route-resource-table
            ingress_table_sel = "#ingress-resource-table, #route-resource-table"
            if self.page.locator(ingress_table_sel).first.is_visible():
                print(f"Checking Ingress/Route table has '{route_resource_name}' visible...")
                if not Util.check_dom_visibility(self.page, self.page.locator(ingress_table_sel).first.locator('tr', has=self.page.locator('td', has_text=route_resource_name)), 2, 4):
                    if ENV.TP_AUTO_INGRESS_OBJECT != "gateway":
                        ColorLogger.info(f"Adding Ingress/Route: {route_resource_name} for SpringBoot capability")
                        add_btn_sel = "#add-ingress-resource-ingress-controller-btn, #add-route-resource-btn"
                        if self.page.locator(add_btn_sel).first.is_visible():
                            self.page.locator(add_btn_sel).first.click()
                            print("Clicked 'Add Ingress/Route Resource' button")
                            self.po_dp_config.add_ingress_controller(
                                ENV.TP_AUTO_INGRESS_CONTROLLER, route_resource_name,
                                ENV.TP_AUTO_INGRESS_CONTROLLER_CLASS_NAME, ENV.TP_AUTO_FQDN_SPRINGBOOT,
                                "route" if self.page.locator('#route-resource-table').is_visible() else "ingress"
                            )

                if Util.check_dom_visibility(self.page, self.page.locator(ingress_table_sel).first.locator('tr', has=self.page.locator('td', has_text=route_resource_name)), 3, 6):
                    self.page.locator(ingress_table_sel).first.locator('tr', has=self.page.locator('td', has_text=route_resource_name)).locator('label').click()
                    print(f"Selected '{route_resource_name}' Ingress/Route for SpringBoot capability")
                else:
                    Util.exit_error(f"'{route_resource_name}' Ingress/Route is still not available, please check if it is provisioned in Data Plane '{dp_name}'", self.page, f"{self.capability}_provision_capability.png")

            self.page.locator("#btnNextCapabilityProvision", has_text="Next").click()
            print("Clicked SpringBoot 'Next' button, finished step 1")
            self.page.wait_for_timeout(3000)
            # CP 1.18+ removed the EULA checkbox
            if self.page.locator(".resource-agree label").is_visible():
                self.page.locator(".resource-agree label").click()
                print("Clicked SpringBoot 'EUA' checkbox")
                self.page.wait_for_timeout(500)
            else:
                print("No EULA checkbox (CP 1.18+), skipping")
            self.page.locator("#btnNextCapabilityProvision").click()
            self.page.wait_for_timeout(3000)

            # Step 3: Preview/Customize Recipe — click the actual provision button
            if Util.check_dom_visibility(self.page, self.page.locator("#btnCapabilityProvision"), 2, 4):
                self.page.locator("#btnCapabilityProvision").click()
                print("Preview/Customize Recipe page is loaded, clicked 'SpringBoot Provision Capability' button")

            print("Waiting for SpringBoot Capability Provision Request Completed")
            if Util.check_dom_visibility(self.page, self.page.locator(".resource-success .title", has_text="Capability Provision Request Completed"), 5, 120):
                ColorLogger.success("Provision SpringBoot capability successful.")
            else:
                ColorLogger.warning("Provision SpringBoot capability successful message is not displayed, the Provision may not succeed.")
            if self.page.locator("#capProvBackToDPBtn").is_visible():
                self.page.locator("#capProvBackToDPBtn").click()
                print("Clicked 'Go Back To Data Plane Details' button")
            else:
                ColorLogger.warning("Can not find 'Go Back To Data Plane Details' button, navigating via menu")
                self.goto_dataplane(dp_name)
        else:
            Util.exit_error("'Provision a capability' button is not visible.", self.page, "springboot_provision_capability.png")

        print("Reload Data Plane page, and check if SpringBoot capability is provisioned...")
        Util.refresh_page(self.page)
        print("Waiting for SpringBoot capability is in capability list...")
        is_dataplane_container_available = Util.check_dom_visibility(self.page, self.page.locator(".data-plane-container"), 5, 20, True)
        if is_dataplane_container_available and self.is_capability_provisioned(capability):
            ColorLogger.success("SpringBoot capability is in capability list")
            ReportYaml.set_capability(dp_name, capability)
        else:
            Util.warning_screenshot("SpringBoot capability is not in capability list", self.page, "springboot_provision_capability-2.png")

    def springboot_provision_connector(self, dp_name, app_name=None):
        app_name = app_name or ENV.SPRINGBOOT_APP_NAME
        capability = self.capability
        if ReportYaml.get_capability_info(dp_name, capability, "provisionConnector") == "true":
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, '{capability}' Connector is already created in DataPlane '{dp_name}'.")
            return
        ColorLogger.info("SpringBoot Provisioning connector...")

        # if app is created, no need to check capability status
        is_check_status = True
        if ReportYaml.is_app_created(dp_name, capability, app_name) or self.is_app_created(capability, app_name):
            is_check_status = False
            print(f"'{capability}' App '{app_name}' has been created, no need to check '{capability}' capability status")

        capability_selector_path = "#capContainer-cont-appPackages"
        self.goto_capability(dp_name, capability, capability_selector_path, is_check_status)

        self.page.locator(capability_selector_path).wait_for(state="visible")
        print("SpringBoot capability page loaded, Checking buildpack versions...")
        self.page.wait_for_timeout(3000)

        connectors = [text.strip() for text in self.page.locator("#pkgsTbl-table-listPkg td:first-child").all_inner_texts()]
        # Note: check 2 times, because sometimes buildpack versions cannot be loaded in time
        for i in range(2):
            if connectors:
                break
            Util.refresh_page(self.page)
            self.page.locator(capability_selector_path).wait_for(state="visible")
            print("SpringBoot capability page loaded, Checking buildpack versions...")
            self.page.wait_for_timeout(3000)
            connectors = [text.strip() for text in self.page.locator("#pkgsTbl-table-listPkg td:first-child").all_inner_texts()]

        print(f"SpringBoot Buildpack Versions: {connectors}")
        required_connectors = {"SB"}
        mapped_name = "Spring Boot"
        if required_connectors.issubset(set(connectors)) or {mapped_name}.issubset(set(connectors)):
            ColorLogger.success("SpringBoot buildpack versions are already provisioned.")
            ReportYaml.set_capability_info(dp_name, capability, "provisionConnector", True)
            self.page.locator(self.selector_header_dp_name(), has_text=dp_name).click()
            print(f"Clicked menu navigator Data Plane '{dp_name}', go back to Data Plane detail page")
            return

        print("Start to Provision SpringBoot buildpack versions...")

        self.page.locator("#capPackagesBackToDP", has_text="Provision").wait_for(state="visible")
        self.page.locator("#capPackagesBackToDP", has_text="Provision").click()
        print("Clicked 'Provision' button")
        self.page.locator("#provisionPluginUpdt-footBtn-nextStep").click()
        print("Clicked 'Next' button")
        self.page.locator("#FinishedProvisionPlugin img[src*='success.svg']").wait_for(state="visible")
        self.page.locator("#btnNavigationToIntegrationDetailsbtnRight", has_text="View Integration Capabilities details").click()
        print("Clicked 'View Integration Capabilities details' button")

        # re-check connectors after provisioning
        connectors = [text.strip() for text in self.page.locator("#pkgsTbl-table-listPkg td:first-child").all_inner_texts()]
        if required_connectors.issubset(set(connectors)) or {mapped_name}.issubset(set(connectors)):
            ColorLogger.success("Provision SpringBoot buildpack versions successful.")
            ReportYaml.set_capability_info(dp_name, capability, "provisionConnector", True)
        self.page.locator(self.selector_header_dp_name(), has_text=dp_name).click()
        print(f"Clicked menu navigator Data Plane '{dp_name}', go back to Data Plane detail page")

    def springboot_app_build_and_deploy(self, dp_name, app_file_name=None, app_name=None):
        app_file_name = app_file_name or ENV.SPRINGBOOT_APP_FILE_NAME
        app_name = app_name or ENV.SPRINGBOOT_APP_NAME
        capability = self.capability

        if ReportYaml.get_capability_info(dp_name, capability, "appBuild") == "true":
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, '{capability}' App Build '{app_name}' is already created in DataPlane '{dp_name}'.")
            return
        ColorLogger.info("SpringBoot Creating app build...")

        # if app is created, no need to check capability status
        is_check_status = True
        if ReportYaml.is_app_created(dp_name, capability, app_name) or self.is_app_created(capability, app_name):
            is_check_status = False
            print(f"'{capability}' App '{app_name}' has been created, no need to check '{capability}' capability status")
        self.goto_capability(dp_name, capability, "#capContainer-cont-appPackages", is_check_status)

        print("SpringBoot Checking app build...")

        is_app_build_created = Util.refresh_until_success(self.page,
                                                          self.page.locator("#capContainer-cont-appBuilds td", has_text=app_name),
                                                          self.page.locator("#capContainer-cont-appBuilds"),
                                                          "SpringBoot capability page loaded, Checking SpringBoot App Builds...")

        if is_app_build_created:
            ColorLogger.success(f"SpringBoot app build {app_name} is already created.")
            ReportYaml.set_capability(dp_name, capability)
            ReportYaml.set_capability_info(dp_name, capability, "appBuild", True)
            return

        print("Start Create SpringBoot app build...")

        if not self.page.locator("#capBuildsCreateNewBuildBtn", has_text="Create New App Build & Deploy").is_visible():
            Util.exit_error(f"SpringBoot 'Create New App Build & Deploy' button is not visible, check SpringBoot provision page.", self.page, "springboot_app_build_and_deploy.png")

        self.page.locator("#capBuildsCreateNewBuildBtn", has_text="Create New App Build & Deploy").click()
        print("Clicked 'Create New App Build & Deploy' button")

        # step1: Upload JAR
        self.page.locator("ul.pl-secondarynav__menu .is-active a", has_text="Upload").wait_for(state="visible")
        print("SpringBoot 'App Build & Deploy' Step 1: 'Upload' page is loaded")
        file_path = Helper.get_app_file_fullpath(app_file_name, ENV.TP_AUTO_APP_RELEASE_REPO, ENV.TP_AUTO_APP_RELEASE_TAG)
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

        # step2: Build Configuration
        self.page.locator("#bldConf-tblBody-txt-appBuildName-text-input").wait_for(state="visible")
        self.page.wait_for_timeout(2000)
        active_title = self.page.locator("ul.pl-secondarynav__menu .is-active a").inner_text()
        print(f"SpringBoot 'App Build & Deploy' Step 2: '{active_title}' page is loaded")
        if self.page.locator("#bldConf-tblBody-btn-refreshProvBWCEList", has_text="Refresh").is_visible():
            self.page.locator("#bldConf-tblBody-btn-refreshProvBWCEList", has_text="Refresh").click()
            print("Clicked 'Refresh' button to refresh buildpack versions list")
            self.page.wait_for_timeout(2000)
        self.page.locator("#bldConf-tblBody-txt-appBuildName-text-input").fill(app_name)
        print(f"Filled App Build Name: {app_name}")

        # click 'Create Build' button in step2
        self.page.locator('#DeployDeployBtn').click()
        print("Clicked 'Create Build' button")

        # step3: App Build
        self.page.wait_for_timeout(2000)
        active_title = self.page.locator("ul.pl-secondarynav__menu .is-active a").inner_text()
        print(f"SpringBoot 'App Build & Deploy' Step 3: '{active_title}' page is loaded")
        if active_title == "App Build":
            if Util.wait_for_success_message(self.page, 5) is False:
                Util.exit_error(f"API return failed message, failed to create SpringBoot {app_name} app build", self.page, "springboot_app_build_and_deploy.png")

            print("Waiting for 'Successfully created App Build'")
            if Util.check_dom_visibility(self.page, self.page.locator('.stages .step .message', has_text="Successfully created App Build"), 3, 60):
                print(f"Successfully created SpringBoot {app_name} app build")
                self.page.locator('#finishDeployViewAppBuildsBtn-1', has_text="Deploy App").wait_for(state="visible")
                self.page.locator('#finishDeployViewAppBuildsBtn-1', has_text="Deploy App").click()
                print("Clicked 'Deploy App' button from Finish tab")
                self.page.locator('#appMngModal-btn-deployHelm', has_text="Deploy").wait_for(state="visible")
                self.page.locator('#appMngModal-btn-deployHelm', has_text="Deploy").click()
                print("Clicked 'Deploy' button from Deploy App Dialog")
            else:
                Util.exit_error(f"No success message is seen, Failed to create SpringBoot {app_name} app build", self.page, "springboot_app_build_and_deploy.png")

            self.springboot_app_build_and_deploy_select_namespace(app_name)

        # below steps is after "Resource Configurations" & "YAML Editor" step
        self.page.locator('#deployComp-btn-DeployBtn', has_text="Deploy App").click()
        print("Clicked 'Deploy App' button")

        print("Check if SpringBoot app deployed successfully...")

        if Util.check_dom_visibility(self.page, self.page.locator('.stages .step .message', has_text="Successfully Deployed Application"), 5, 60):
            ColorLogger.success(f"SpringBoot app build '{app_name}' is deployed.")
            ReportYaml.set_capability_info(dp_name, capability, "appBuild", True)

    def springboot_app_build_and_deploy_select_namespace(self, app_name=None):
        app_name = app_name or ENV.SPRINGBOOT_APP_NAME
        self.page.locator("#nameSpace input").wait_for(state="visible")
        print("App Resource Configuration page loaded")
        self.page.locator("#nameSpace input").click()
        print(f"Clicked 'Namespace' dropdown, and waiting for namespace: {ENV.TP_AUTO_K8S_DP_NAMESPACE}")
        self.page.wait_for_timeout(1000)
        if not self.page.locator("#nameSpace .pl-select-menu li", has_text=ENV.TP_AUTO_K8S_DP_NAMESPACE).is_visible():
            Util.exit_error(f"Namespace '{ENV.TP_AUTO_K8S_DP_NAMESPACE}' is not list in the dropdown.", self.page, "springboot_app_build_and_deploy.png")

        self.page.locator("#nameSpace .pl-select-menu li", has_text=ENV.TP_AUTO_K8S_DP_NAMESPACE).click()
        print(f"Selected namespace: {ENV.TP_AUTO_K8S_DP_NAMESPACE}")

        if self.page.locator("#app-name-text-input").is_visible():
            self.page.locator("#app-name-text-input").clear()
            self.page.locator("#app-name-text-input").fill(app_name)
            print(f"Filled App Name: {app_name}")

        self.page.locator('#deployComp-btn-ResourceConfigBtn1', has_text="Next").click()
        print("Clicked 'Next' button")

        self.page.locator("label[for='eula-checkbox']").click()
        print("Clicked 'EUA' checkbox")
        self.page.wait_for_timeout(1000)

    def springboot_app_deploy(self, dp_name, app_name=None):
        app_name = app_name or ENV.SPRINGBOOT_APP_NAME
        capability = self.capability

        if ReportYaml.is_app_created(dp_name, capability, app_name):
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, '{capability}' App '{app_name}' is already created in DataPlane '{dp_name}'.")
            return
        ColorLogger.info(f"SpringBoot Deploying app '{app_name}'...")
        dp_name_space = ENV.TP_AUTO_K8S_DP_NAMESPACE

        self.goto_dataplane(dp_name)
        print(f"Checking if SpringBoot app '{app_name}' is in dataplane {dp_name}.")
        if self.page.locator("apps-list td.app-name a", has_text=app_name).is_visible():
            ColorLogger.success(f"SpringBoot app '{app_name}' in dataplane {dp_name} is already deployed.")
            ReportYaml.set_capability_app(dp_name, capability, app_name)
            return

        # if app is created, no need to check capability status
        is_check_status = True
        if ReportYaml.is_app_created(dp_name, capability, app_name) or self.is_app_created(capability, app_name):
            is_check_status = False
            print(f"'{capability}' App '{app_name}' has been created, no need to check '{capability}' capability status")
        self.goto_capability(dp_name, capability, "#capContainer-cont-appPackages", is_check_status)

        print(f"Waiting for SpringBoot app build {app_name} is deployed...")
        if not Util.check_dom_visibility(self.page, self.page.locator("#bldTbl-table-buildsList tr td", has_text=app_name), 5, 180, True):
            Util.exit_error(f"SpringBoot app {app_name} is not deployed.", self.page, "springboot_app_deploy.png")

        # if capability appBuild has not been set to true, set it to true
        if ReportYaml.get_capability_info(dp_name, capability, "appBuild") != "true":
            ReportYaml.set_capability_info(dp_name, capability, "appBuild", True)

        self.page.locator("#bldTbl-table-buildsList tr", has=self.page.locator("td", has_text=app_name)).nth(0).locator('#builds-menu-dropdown-label').click()
        print(f"Clicked action menu button for {app_name}")
        self.page.locator("#bldTbl-table-buildsList tr", has=self.page.locator("td", has_text=app_name)).nth(0).locator('.pl-dropdown .pl-dropdown-menu__item button', has_text="Deploy").click()
        print(f"Clicked 'Deploy' from action menu list for {app_name}")

        self.page.wait_for_timeout(1000)
        if Util.check_dom_visibility(self.page, self.page.locator('#appMngModal-btn-deployHelm', has_text="Deploy"), 3, 6):
            print("Deploy App Dialog popup")
            self.page.locator('#appMngModal-btn-deployHelm', has_text="Deploy").click()
            print("Clicked 'Deploy App' button from Deploy App Dialog")
            self.springboot_app_build_and_deploy_select_namespace(app_name)

            # below steps is after "Resource Configurations" & "YAML Editor" step
            self.page.locator('#deployComp-btn-DeployBtn', has_text="Deploy App").click()
            print("Clicked 'Deploy App' button")

            print("Check if SpringBoot app deployed successfully...")

            if Util.check_dom_visibility(self.page, self.page.locator('.stages .step .message', has_text="Successfully Deployed Application"), 5, 120):
                self.page.locator("#finished-btn-gotoDPDetails-finishDeployViewDeployBuildsBtn-1").click()
                print("Clicked 'View Deployed App' button, go back to Data Plane detail page")
        else:
            print("Dialog 'Deploy App Build' does not popup")
            Util.exit_error(f"SpringBoot app {app_name} dialog 'Deploy App Build' does not popup.", self.page, "springboot_app_deploy.png")

        print(f"Waiting for SpringBoot app '{app_name}' is deployed...")
        if Util.check_dom_visibility(self.page, self.page.locator("apps-list td.app-name a", has_text=app_name), 5, 120):
            ColorLogger.success(f"Deploy SpringBoot app '{app_name}' in namespace {dp_name_space} Successfully")
            ReportYaml.set_capability_app(dp_name, capability, app_name)
        else:
            Util.warning_screenshot(f"Deploy SpringBoot app '{app_name}' in namespace {dp_name_space} may failed.", self.page, "springboot_app_deploy-2.png")

    def springboot_app_config(self, dp_name, app_name=None):
        app_name = app_name or ENV.SPRINGBOOT_APP_NAME
        capability = self.capability

        ColorLogger.info(f"SpringBoot Config app '{app_name}'...")
        self.goto_app_detail(dp_name, app_name, self.selector_header_app_name())

        if ReportYaml.get_capability_app_info(dp_name, capability, app_name, "endpointPublic") == "true":
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, '{capability}' Endpoints is already Public in DataPlane '{dp_name}'.")
            return

        self.page.locator("#tab-endpoints").click()
        print("Clicked 'Endpoints' tab")
        self.page.locator(".endpoints").wait_for(state="visible")
        print("Endpoint tab is loaded.")
        if Util.check_dom_visibility(self.page, self.page.locator(".endpoints .header h4", has_text="Public"), 2, 6):
            ColorLogger.success(f"SpringBoot app '{app_name}' has set Endpoint Visibility to Public.")
            ReportYaml.set_capability_app_info(dp_name, capability, app_name, "endpointPublic", True)
        else:
            print("Endpoints is not public, will set Endpoint Visibility to Public")
            self.page.locator(self.selector_header_action_menu()).wait_for(state="visible")
            self.page.locator(self.selector_header_action_menu()).click()
            self.page.locator(self.selector_header_action_menu_item(), has_text="Set Endpoint Visibility").wait_for(state="visible")
            self.page.locator(self.selector_header_action_menu_item(), has_text="Set Endpoint Visibility").click()
            print("Clicked 'Set Endpoint Visibility' menu item")
            self.page.locator("#appDtls-appEndPntMod1-btn-saveChanges", has_text="Save Changes").wait_for(state="visible")
            print("Dialog 'Set Endpoint Visibility' popup")
            texts = self.page.locator(".pl-modal__container strong").nth(0).all_inner_texts()
            if any(t in ["Set Endpoint visibility", "Update Endpoint visibility"] for t in texts):
                if self.page.locator(".pl-table__cell label", has_text=ENV.TP_AUTO_INGRESS_CONTROLLER_SPRINGBOOT).is_visible():
                    self.page.locator(".pl-table__cell label", has_text=ENV.TP_AUTO_INGRESS_CONTROLLER_SPRINGBOOT).click()
                    print(f"Selected '{ENV.TP_AUTO_INGRESS_CONTROLLER_SPRINGBOOT}' from Resource Name column")
                    self.page.locator('label[for="endpoint-radio-0-public"]').click()
                    if self.page.locator("#appDtls-appEndPntMod1-btn-saveChanges", has_text="Save Changes").is_enabled():
                        print("Set Public Endpoint Visibility to 'Public'")
                        self.page.locator("#appDtls-appEndPntMod1-btn-saveChanges", has_text="Save Changes").click()
                        print("Clicked 'Save Changes' button")
                        if Util.wait_for_success_message(self.page, 5) and self.page.locator(".endpoints .header h4", has_text="Public").is_visible():
                            ColorLogger.success(f"SpringBoot app '{app_name}' has set Endpoint Visibility to Public.")
                            ReportYaml.set_capability_app_info(dp_name, capability, app_name, "endpointPublic", True)
                    else:
                        ColorLogger.warning(f"'Save Changes' button is not enabled, did NOT set Endpoint Visibility to Public for SpringBoot app '{app_name}'.")
                        self.page.locator(".pl-modal__footer-left button", has_text="Cancel").click()
                        print(f"Clicked 'Cancel' button from '{texts}' dialog")
                else:
                    Util.warning_screenshot(f"Not able to set Endpoint Visibility to Public, '{ENV.TP_AUTO_INGRESS_CONTROLLER_SPRINGBOOT}' is not available.", self.page, "springboot_app_config-endpoint.png")

    def springboot_app_start(self, dp_name, app_name=None):
        app_name = app_name or ENV.SPRINGBOOT_APP_NAME
        capability = self.capability

        if ReportYaml.get_capability_app_info(dp_name, capability, app_name, "status") == "Running" or self.is_app_running(dp_name, capability, app_name):
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, '{capability}' App '{app_name}' is Running in DataPlane '{dp_name}'.")
            return
        ColorLogger.info(f"SpringBoot Start app '{app_name}'...")
        self.goto_app_detail(dp_name, app_name, self.selector_header_app_name())

        print("Waiting to see if app status is Running...")
        if self.get_app_instance_number() > 0:
            ColorLogger.success(f"SpringBoot app '{app_name}' is already running.")
            ReportYaml.set_capability_app_info(dp_name, capability, app_name, "status", "Running")
        else:
            self.page.locator(self.selector_header_app_action_btn(), has_text="Start").click()
            print("Clicked 'Start' app button")

            print(f"Waiting for app '{app_name}' status is Running...")
            if Util.check_dom_visibility(self.page, self.page.locator(self.selector_header_app_action_btn(), has_text="Stop"), 15, 240, True):
                app_status = self.get_app_status()
                ColorLogger.success(f"SpringBoot app '{app_name}' status is '{app_status}' now.")
                ReportYaml.set_capability_app_info(dp_name, capability, app_name, "status", app_status)
            else:
                Util.warning_screenshot(f"Wait too long to scale SpringBoot app '{app_name}'.", self.page, "springboot_app_start.png")
