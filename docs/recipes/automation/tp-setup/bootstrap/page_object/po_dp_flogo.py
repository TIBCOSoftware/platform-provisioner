from utils.color_logger import ColorLogger
from utils.util import Util
from utils.helper import Helper
from utils.env import ENV
from utils.report import ReportYaml
from page_object.po_dataplane import PageObjectDataPlane

class PageObjectDataPlaneFlogo(PageObjectDataPlane):
    def __init__(self, page):
        super().__init__(page)

    def flogo_provision_capability(self, dp_name):
        capability = "flogo"
        if ReportYaml.is_capability_for_dataplane_created(dp_name, capability):
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, capability '{capability}' is already created in DataPlane '{dp_name}'.")
            return
        ColorLogger.info("Flogo Provisioning capability...")
        self.goto_dataplane(dp_name)
        if self.page.locator("capability-card #flogo").is_visible():
            ColorLogger.success("Flogo capability is already provisioned.")
            ReportYaml.set_capability(dp_name, capability)
            return

        print("Checking if 'Provision a capability' button is visible.")
        if Util.check_dom_visibility(self.page, self.page.locator('button', has_text="Provision a capability"), 10, 100):
            print("'Provision a capability' button is visible.")
            ColorLogger.success(f"Data Plane '{dp_name}' status is running.")
            self.page.locator('button', has_text="Provision a capability").click()
            print("Clicked 'Provision a capability' button")
            self.page.wait_for_timeout(2000)
            Util.click_button_until_enabled(self.page, self.page.locator('#FLOGO-capability-select-button'))
            print("Clicked 'Provision TIBCO Flogo® Enterprise' -> 'Start' button")

            print("Waiting for Flogo capability page is loaded")
            self.page.locator(".resources-content").wait_for(state="visible")
            print("Flogo capability page is loaded")
            self.page.wait_for_timeout(3000)

            if self.page.locator('#storage-class-resource-table').is_visible():
                self.page.locator('#storage-class-resource-table tr', has=self.page.locator('td', has_text=ENV.TP_AUTO_STORAGE_CLASS)).locator('label').wait_for(state="visible")
                self.page.locator('#storage-class-resource-table tr', has=self.page.locator('td', has_text=ENV.TP_AUTO_STORAGE_CLASS)).locator('label').click()
                print(f"Selected '{ENV.TP_AUTO_STORAGE_CLASS}' Storage Class for Flogo capability")

            if self.page.locator('#ingress-resource-table').is_visible():
                self.page.locator('#ingress-resource-table tr', has=self.page.locator('td', has_text=ENV.TP_AUTO_INGRESS_CONTROLLER_FLOGO)).locator('label').wait_for(state="visible")
                self.page.locator('#ingress-resource-table tr', has=self.page.locator('td', has_text=ENV.TP_AUTO_INGRESS_CONTROLLER_FLOGO)).locator('label').click()
                print(f"Selected '{ENV.TP_AUTO_INGRESS_CONTROLLER_FLOGO}' Ingress Controller for Flogo capability")

            self.page.locator("#btnNextCapabilityProvision").click()
            print("Clicked Flogo 'Next' button, finished step 1")
            is_eula_loaded = Util.refresh_until_success(self.page,
                                                        self.page.locator(".eula-container input"),
                                                        self.page.locator(".eula-container input"),
                                                        "Flogo Capability step 2 is loaded.")
            if is_eula_loaded:
                self.page.locator(".eula-container input").click()
                print("Clicked Flogo 'EUA' checkbox")
                self.page.locator("#qaProvisionFlogo").click()
                print("Clicked 'Flogo Provision Capability' button, waiting for Flogo Capability Provision Request Completed")
                # TODO: success message may not pop up, need to handle this case
                if Util.check_dom_visibility(self.page, self.page.locator(".notification-message", has_text="Successfully provisioned Flogo"), 5, 30):
                    ColorLogger.success("Provision Flogo capability successful.")
                else:
                    ColorLogger.warning("Provision Flogo capability successful message is not displayed, the Provision flogo may not succeed.")
                self.page.locator("#qaBackToDP").click()
                print("Clicked 'Go Back To Data Plane Details' button")
            else:
                Util.exit_error("Flogo Capability step 2 is not loaded.", self.page, "flogo_provision_capability.png")
        else:
            Util.exit_error("'Provision a capability' button is not visible.", self.page, "flogo_provision_capability.png")

        print("Reload Data Plane page, and check if Flogo capability is provisioned...")
        Util.refresh_page(self.page)
        print("Waiting for Flogo capability is in capability list...")
        self.page.locator(".data-plane-container").wait_for(state="visible")
        if self.is_capability_provisioned(capability):
            ColorLogger.success("Flogo capability is in capability list")
            ReportYaml.set_capability(dp_name, capability)
        else:
            Util.warning_screenshot("Flogo capability is not in capability list", self.page, "flogo_provision_capability-2.png")

    def flogo_provision_connector(self, dp_name, app_name):
        capability = "flogo"
        if ReportYaml.get_capability_info(dp_name, capability, "provisionConnector") == "true":
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, '{capability}' Connector is already created in DataPlane '{dp_name}'.")
            return
        ColorLogger.info("Flogo Provisioning connector...")
    
        # if app is created, not need to check capability status
        is_check_status = True
        if ReportYaml.is_app_created(dp_name, capability, app_name) or self.flogo_is_app_created(app_name):
            is_check_status = False
            print(f"'{capability}'App '{app_name}' has been created, no need to check '{capability}' capability status")
        self.goto_capability(dp_name, capability, is_check_status)
    
        self.page.locator(".capability-connectors-container .total-capability").wait_for(state="visible")
        print("Flogo capability page loaded, Checking connectors...")
        self.page.wait_for_timeout(3000)
    
        connectors = [text.strip() for text in self.page.locator(".capability-connectors-container td:first-child").all_inner_texts()]
        # Note: check 3 times, because sometimes Flogo connectors can not be loaded in time
        # if connectors is empty, reload page, and check again, only check 3 times, if still empty, exit for loop
        for i in range(3):
            if connectors:
                break
            Util.refresh_page(self.page)
            self.page.locator(".capability-connectors-container .total-capability").wait_for(state="visible")
            print("Flogo capability page loaded, Checking connectors...")
            self.page.wait_for_timeout(3000)
            connectors = [text.strip() for text in self.page.locator(".capability-connectors-container td:first-child").all_inner_texts()]
    
        # connectors = Util.refresh_until_success(page,
        #                            [text.strip() for text in self.page.locator(".capability-connectors-container td:first-child").all_inner_texts()],
        #                            self.page.locator(".capability-connectors-container .total-capability"),
        #                            "Flogo capability page loaded, Checking connectors...")
    
        print(f"Flogo Connectors: {connectors}")
        required_connectors = {"Flogo", "General"}
        if required_connectors.issubset(set(connectors)):
            ColorLogger.success("Flogo connectors are already provisioned.")
            ReportYaml.set_capability_info(dp_name, capability, "provisionConnector", True)
            self.page.locator("flogo-capability-header .dp-sec-name", has_text=dp_name).click()
            print(f"Clicked menu navigator Data Plane '{dp_name}', go back to Data Plane detail page")
            return
    
        print("Start Create Flogo app connector...")
    
        self.page.locator(".capability-buttons", has_text="Provision Flogo & Connectors").wait_for(state="visible")
        self.page.locator(".capability-buttons", has_text="Provision Flogo & Connectors").click()
        print("Clicked 'Provision Flogo & Connectors' button")
        # self.page.locator(".versions-container label", has_text="HTTP").wait_for(state="visible")
        # self.page.locator(".versions-container label", has_text="HTTP").click()
        # self.page.locator(".versions-container label", has_text="Websocket").scroll_into_view_if_needed()
        # self.page.locator(".versions-container label", has_text="Websocket").click()
        # print("Selected 'HTTP' and 'Websocket' connectors")
        self.page.locator("#qaPluginProvision").click()
        print("Clicked 'Provision' button")
        self.page.locator("flogo-plugins-provision-finish .complete").wait_for(state="visible")
        ColorLogger.success("Provision Flogo & Connectors successful.")
        ReportYaml.set_capability_info(dp_name, capability, "provisionConnector", True)
        self.page.locator(".finish-buttons-container button", has_text="Go back to Data Plane details").click()
        print("Clicked 'Go back to Data Plane details' button")
    
    def flogo_app_build_and_deploy(self, dp_name, app_file_name, app_name):
        capability = "flogo"
        if ReportYaml.get_capability_info(dp_name, capability, "appBuild") == "true":
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, '{capability}' App Build '{app_name}' is already created in DataPlane '{dp_name}'.")
            return
        ColorLogger.info("Flogo Creating app build...")
    
        # if app is created, not need to check capability status
        is_check_status = True
        if ReportYaml.is_app_created(dp_name, capability, app_name) or self.flogo_is_app_created(app_name):
            is_check_status = False
            print(f"'{capability}'App '{app_name}' has been created, no need to check '{capability}' capability status")
        self.goto_capability(dp_name, capability, is_check_status)
    
        print("Flogo Checking app build...")
        self.page.locator(".app-build-container").wait_for(state="visible")
        print("Flogo capability page loaded, Checking Flogo App Builds...")
        self.page.wait_for_timeout(3000)
        # is_app_build_created = self.page.locator(".app-build-container td", has_text=app_name).is_visible()
        # # Note: check 3 times, because sometimes Flogo App Builds can not be loaded in time
        # # if not Flogo App Builds, reload page, and check again, only check 3 times, if still empty, exit for loop
        # for i in range(3):
        #     if is_app_build_created:
        #         break
        #     Util.refresh_page(page)
        #     self.page.locator(".app-build-container").wait_for(state="visible")
        #     print("Flogo capability page loaded, Checking Flogo App Builds...")
        #     self.page.wait_for_timeout(3000)
        #     is_app_build_created = self.page.locator(".app-build-container td", has_text=app_name).is_visible()
    
        is_app_build_created = Util.refresh_until_success(self.page,
                                                          self.page.locator(".app-build-container td", has_text=app_name),
                                                          self.page.locator(".app-build-container"),
                                                          "Flogo capability page loaded, Checking Flogo App Builds...")
    
        if is_app_build_created:
            ColorLogger.success(f"Flogo app build {app_name} is already created.")
            ReportYaml.set_capability_info(dp_name, capability, "appBuild", True)
            return
    
        print("Start Create Flogo app build...")
    
        self.page.locator(".capability-buttons", has_text="Create New App Build And Deploy").click()
        print("Clicked 'Create New App Build And Deploy' button")
    
        # step1: Upload Files
        self.page.locator("ul.items .is-active .step-text", has_text="Upload Files").wait_for(state="visible")
        print("Flogo 'App Build & Deploy' Step 1: 'Upload Files' page is loaded")
        file_path = Helper.get_app_file_fullpath(app_file_name)
        self.page.locator('input[type="file"]').evaluate("(input) => input.style.display = 'block'")
    
        self.page.locator('input[type="file"]').set_input_files(file_path)
        print(f"Selected file: {file_path}")
        self.page.locator('app-upload-file .dropzone-file-name', has_text=app_file_name).wait_for(state="visible")
        self.page.locator('#qaUploadApp').click()
        print("Clicked 'Upload Selected File' button")
        self.page.locator('.upload-main-title', has_text="File Uploaded Successfully").wait_for(state="visible")
        print(f"File '{app_file_name}' Uploaded Successfully")
        self.page.locator('#qaNextAppDeploy').click()
        print("Clicked 'Next' button")
    
        # step2: Select Versions
        self.page.locator("#build-name").wait_for(state="visible")
        self.page.wait_for_timeout(2000)
        active_title = self.page.locator("ul.items .is-active .step-text").inner_text()
        print(f"Flogo 'App Build & Deploy' Step 2: '{active_title}' page is loaded")
        if self.page.locator(".version-field-container .rovision-link", has_text="Provision Flogo in another tab").is_visible():
            with self.page.context.expect_page() as new_page_info:
                self.page.locator(".version-field-container .rovision-link", has_text="Provision Flogo in another tab").click()
                print("Clicked 'Provision Flogo in another tab' link")
    
            new_page = new_page_info.value
            ColorLogger.success("New window detected and captured.")
            new_page.locator(".versions-container label", has_text="HTTP").click()
            new_page.locator(".versions-container label", has_text="Websocket").scroll_into_view_if_needed()
            new_page.locator(".versions-container label", has_text="Websocket").click()
            print("Selected 'HTTP' and 'Websocket' connectors")
            new_page.locator("#qaPluginProvision").click()
            new_page.close()
            ColorLogger.success("Provision Flogo & Connectors successful.")
            self.page.locator(".refresh-link", has_text="Refresh List").click()
            self.page.wait_for_timeout(1000)
    
        # namespace picker is for 1.4 and 1.3
        if self.page.locator("flogo-namespace-picker input").is_visible():
            self.flogo_app_build_and_deploy_select_namespace()
    
        # click 'Next' button in step2
        self.page.locator('#qaNextAppDeploy').click()
        print("Clicked 'Next' button")
    
        # step3:
        self.page.wait_for_timeout(2000)
        active_title = self.page.locator("ul.items .is-active .step-text").inner_text()
        print(f"Flogo 'App Build & Deploy' Step 3: '{active_title}' page is loaded")
        # if step3 is "Finished", will deploy app later, it is for 1.5 version
        # click "Deploy App" button will go to "Resource Configurations" step,
        # same as 1.4 version, and then deploy flogo app from "Resource Configurations" step
        if active_title == "Finished":
            if Util.wait_for_success_message(self.page, 5) is False:
                Util.exit_error(f"API return failed message, failed to create Flogo {app_name} app build", self.page, "flogo_app_build_and_deploy.png")

            print("Waiting for 'Creating new app build...'")
            self.page.locator('.finish-container .step-description', has_text="Creating new app build...").wait_for(state="visible")
            print("Waiting for 'Successfully created app build'")
            if Util.check_dom_visibility(self.page, self.page.locator('.finish-container .step-description', has_text="Successfully created app build"),3, 60):
                print(f"Successfully created Flogo {app_name} app build")
                self.page.locator('.finish-buttons-container button', has_text="Deploy App").wait_for(state="visible")
                self.page.locator('.finish-buttons-container button', has_text="Deploy App").click()
                print("Clicked 'Deploy App' button from Finish tab")
                self.page.locator('.app-managed-container .deploy-app button', has_text="Deploy App").nth(0).wait_for(state="visible")
                self.page.locator('.app-managed-container .deploy-app button', has_text="Deploy App").nth(0).click()
                print("Clicked 'Deploy App' button from Deploy App Dialog")
            else:
                Util.exit_error(f"No success message is seen, Failed to create Flogo {app_name} app build", self.page, "flogo_app_build_and_deploy.png")
    
            self.page.fill("#app-name", app_name)
            print(f"Filled Application Name: {app_name}")
            self.flogo_app_build_and_deploy_select_namespace()
    
        # below steps is after "Resource Configurations" step
        self.page.locator('#qaResourceAppDeploy').click()
        print("Clicked 'Deploy App' button")
    
        self.page.locator('.finish-container .deploy-banner-icon').wait_for(state="visible")
        ColorLogger.success(f"Created Flogo app build '{app_name}' Successfully")
        print("Check if Flogo app deployed successfully...")
        if Util.check_dom_visibility(self.page, self.page.locator('flogo-tp-pl-icon[icon="pl-icon-critical-error"]'),3, 10):
            Util.exit_error(f"Flogo app build '{app_name}' is not deployed.", self.page, "flogo_app_build_and_deploy_deploy.png")
    
        print("No deploy error, continue waiting for deploy status...")
        if Util.check_dom_visibility(self.page, self.page.locator('.finish-container .step-description', has_text="Successfully deployed App"), 15, 300):
            ColorLogger.success(f"Flogo app build '{app_name}' is deployed.")
            ReportYaml.set_capability_info(dp_name, capability, "appBuild", True)
    
    def flogo_app_build_and_deploy_select_namespace(self):
        self.page.locator("flogo-namespace-picker input").click()
        print(f"Clicked 'Namespace' dropdown, and waiting for namespace: {ENV.TP_AUTO_K8S_DP_NAMESPACE}")
        self.page.wait_for_timeout(1000)
        if not self.page.locator("flogo-namespace-picker .namespace-dropdown li", has_text=ENV.TP_AUTO_K8S_DP_NAMESPACE).is_visible():
            Util.exit_error(f"Namespace '{ENV.TP_AUTO_K8S_DP_NAMESPACE}' is not list in the dropdown.", self.page, "flogo_app_build_and_deploy.png")
    
        self.page.locator("flogo-namespace-picker .namespace-dropdown li", has_text=ENV.TP_AUTO_K8S_DP_NAMESPACE).click()
        print(f"Selected namespace: {ENV.TP_AUTO_K8S_DP_NAMESPACE}")
        self.page.locator(".eula-container").click()
        print("Clicked 'EUA' checkbox")
    
    def flogo_app_deploy(self, dp_name, app_name):
        capability = "flogo"
        if ReportYaml.is_app_created(dp_name, capability, app_name):
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, '{capability}' App '{app_name}' is already created in DataPlane '{dp_name}'.")
            return
        ColorLogger.info(f"Flogo Deploying app '{app_name}'...")
        dp_name_space = ENV.TP_AUTO_K8S_DP_NAMESPACE

        self.goto_dataplane(dp_name)
        if self.page.locator("apps-list td.app-name a", has_text=app_name).is_visible():
            ColorLogger.success(f"Flogo app '{app_name}' in namespace {dp_name_space} is already deployed.")
            ReportYaml.set_capability_app(dp_name, capability, app_name)
            return
    
        # if app is created, not need to check capability status
        is_check_status = True
        if ReportYaml.is_app_created(dp_name, capability, app_name) or self.flogo_is_app_created(app_name):
            is_check_status = False
            print(f"'{capability}'App '{app_name}' has been created, no need to check '{capability}' capability status")
        self.goto_capability(dp_name, capability, is_check_status)
    
        print(f"Waiting for Flogo app build {app_name} is deployed...")
        if not Util.check_dom_visibility(self.page, self.page.locator(".app-build-container td:first-child", has_text=app_name), 20, 180, True):
            Util.exit_error(f"Flogo app {app_name} is not deployed.", self.page, "flogo_app_deploy.png")
    
        # if capability appBuild has not been set to true, set it to true
        # in flogo_app_build_and_deploy function, the appBuild has not displayed, but now it is displayed, should set appBuild to true
        if ReportYaml.get_capability_info(dp_name, capability, "appBuild") != "true":
            ReportYaml.set_capability_info(dp_name, capability, "appBuild", True)
    
        self.page.locator(".app-build-container tr", has=self.page.locator("td", has_text=app_name)).nth(0).locator('flogo-app-build-actions button[data-pl-dropdown-role="toggler"]').click()
        print(f"Clicked action menu button for {app_name}")
        self.page.locator(".app-build-container tr", has=self.page.locator("td", has_text=app_name)).nth(0).locator('flogo-app-build-actions .action-menu button', has_text="Deploy").click()
        print(f"Clicked 'Deploy' from action menu list for {app_name}")
    
        self.page.wait_for_timeout(1000)
        # .app-managed-container is for 1.5 version
        if Util.check_dom_visibility(self.page, self.page.locator('.app-managed-container .deploy-app button', has_text="Deploy App").nth(0), 3, 6):
            print("Deploy App Dialog popup")
            self.page.locator('.app-managed-container .deploy-app button', has_text="Deploy App").nth(0).click()
            print("Clicked 'Deploy App' button from Deploy App Dialog")
            self.flogo_app_build_and_deploy_select_namespace()
    
            self.page.locator('#qaResourceAppDeploy').click()
            print("Clicked 'Deploy App' button")
            print("Check if Flogo app deployed successfully...")
            if Util.check_dom_visibility(self.page, self.page.locator('flogo-tp-pl-icon[icon="pl-icon-critical-error"]'),3, 10):
                Util.exit_error(f"Flogo app '{app_name}' is not deployed.", self.page, "flogo_app_deploy.png")
    
            print("No deploy error, continue waiting for deploy status...")
            if Util.check_dom_visibility(self.page, self.page.locator('.finish-container .step-description', has_text="Successfully deployed App"), 10, 120):
                self.page.locator("#qaDeployedApps").click()
                print("Clicked 'View Deployed App' button, go back to Data Plane detail page")
        else:
            self.page.locator(".pl-modal__footer-right button", has_text="Deploy App Build").wait_for(state="visible")
            print("Dialog 'Deploy App Build' popup")
            self.page.locator("flogo-namespace-picker input").click()
    
            self.page.locator("flogo-namespace-picker .namespace-dropdown li", has_text=dp_name_space).click()
            print(f"Selected Namespace '{dp_name_space}' for {dp_name}")
    
            self.page.locator("#deployName").clear()
            self.page.fill("#deployName", app_name)
            print(f"Clear previous deploy name and Input lower case Deploy Name: {app_name}")
    
            self.page.locator(".pl-modal__footer-right button", has_text="Deploy App Build").click()
            print("Clicked 'Deploy App Build' button")
            self.page.wait_for_timeout(1000)
    
            self.page.locator("flogo-capability-header .dp-sec-name", has_text=dp_name).click()
            print(f"Clicked menu navigator Data Plane '{dp_name}', go back to Data Plane detail page")
    
        print(f"Waiting for Flogo app '{app_name}' is deployed...")
        if Util.check_dom_visibility(self.page, self.page.locator("apps-list td.app-name a", has_text=app_name), 10, 120):
            ColorLogger.success(f"Deploy Flogo app '{app_name}' in namespace {dp_name_space} Successfully")
            ReportYaml.set_capability_app(dp_name, capability, app_name)
        else:
            Util.warning_screenshot(f"Deploy Flogo app '{app_name}' in namespace {dp_name_space} may failed.", self.page, "flogo_app_deploy-2.png")
    
    def flogo_app_config(self, dp_name, app_name):
        capability = "flogo"
        ColorLogger.info(f"Flogo Config app '{app_name}'...")
        self.goto_app_detail(dp_name, app_name)
    
        if ReportYaml.get_capability_app_info(dp_name, capability, app_name, "endpointPublic") == "true":
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, '{capability}' Endpoints is already Public in DataPlane '{dp_name}'.")
        else:
            if self.page.locator(".no-endpoints", has_text="There are no Endpoints configured for the application").is_visible():
                Util.warning_screenshot(f"There is some error for Flogo app '{app_name}', it has no Endpoints configured.", self.page, "flogo_app_config.png")
                return
    
            # set Endpoint Visibility to Public
            self.page.locator(".endpoints-container td.action-button").wait_for(state="visible")
            print("Endpoint action button is loaded.")
            if self.page.locator(".endpoints-container td.action-button button", has_text="Public URL").is_visible():
                ColorLogger.success(f"Flogo app '{app_name}' has set Endpoint Visibility to Public.")
                ReportYaml.set_capability_app_info(dp_name, capability, app_name, "endpointPublic", True)
            else:
                print("No 'Public URL' button, will set Endpoint Visibility to Public")
                self.page.locator("#app-details-menu-dropdown-label").wait_for(state="visible")
                self.page.locator("#app-details-menu-dropdown-label").click()
                self.page.locator(".pl-dropdown-menu__action", has_text="Set Endpoint Visibility").wait_for(state="visible")
                self.page.locator(".pl-dropdown-menu__action", has_text="Set Endpoint Visibility").click()
                print("Clicked 'Set Endpoint Visibility' menu item")
                self.page.locator(".pl-modal__footer-right button", has_text="Cancel").wait_for(state="visible")
                print("Dialog 'Set Endpoint Visibility' popup")
                if self.page.locator(".modal-header", has_text="Update Endpoint visibility to Public").is_visible():
                    if self.page.locator(".capability-table-row-details label", has_text=ENV.TP_AUTO_INGRESS_CONTROLLER_FLOGO).is_visible():
                        self.page.locator(".capability-table-row-details label", has_text=ENV.TP_AUTO_INGRESS_CONTROLLER_FLOGO).click()
                        print(f"Selected '{ENV.TP_AUTO_INGRESS_CONTROLLER_FLOGO}' from Resource Name column")
                        self.page.locator("button", has_text="Update Endpoint visibility to Public").click()
                        print("Clicked 'Update Endpoint visibility to Public' button")
                        if Util.wait_for_success_message(self.page, 5) and self.page.locator(".endpoints-container td.action-button button", has_text="Public URL").is_visible():
                            ColorLogger.success(f"Flogo app '{app_name}' has set Endpoint Visibility to Public.")
                            ReportYaml.set_capability_app_info(dp_name, capability, app_name, "endpointPublic", True)
                    else:
                        Util.warning_screenshot(f"Not able to set Endpoint Visibility to Public, '{ENV.TP_AUTO_INGRESS_CONTROLLER_FLOGO}' is not available.", self.page, "flogo_app_config-endpoint.png")
    
        if ReportYaml.get_capability_app_info(dp_name, capability, app_name, "enableTrace") == "true":
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, '{capability}' Trace is already Enabled in DataPlane '{dp_name}'.")
        else:
            # set Engine Variables, FLOGO_OTEL_TRACE to true
            print("Navigating to 'Engine Variables' tab menu")
            self.page.locator(".pl-primarynav__menu .pl-primarynav__item", has_text="Environmental Controls").click()
            print("Clicked 'Environmental Controls' tab menu")
            self.page.locator(".environment-container .left-navigation li a", has_text="Engine Variables").wait_for(state="visible")
            self.page.locator(".environment-container .left-navigation li a", has_text="Engine Variables").click()
            print("Clicked 'Engine Variables' left side menu")
            self.page.locator(".appVars-table tr.pl-table__row", has=self.page.locator("td", has_text="FLOGO_OTEL_TRACE")).wait_for(state="visible")
            flogo_otel_trace_selector = self.page.locator(".appVars-table tr.pl-table__row", has=self.page.locator("td", has_text="FLOGO_OTEL_TRACE")).locator("select")
            if flogo_otel_trace_selector.input_value() == "true":
                ColorLogger.success("FLOGO_OTEL_TRACE is already set to true.")
                ReportYaml.set_capability_app_info(dp_name, capability, app_name, "enableTrace", True)
            else:
                flogo_otel_trace_selector.select_option(label="true")
                print("Set FLOGO_OTEL_TRACE to true")
                self.page.locator("button.update-button", has_text="Push Updates").click()
                print("Clicked 'Push Updates' button")
                if Util.wait_for_success_message(self.page, 5):
                    ColorLogger.success("Set FLOGO_OTEL_TRACE to true successfully.")
                    ReportYaml.set_capability_app_info(dp_name, capability, app_name, "enableTrace", True)
    
    def flogo_app_start(self, dp_name, app_name):
        capability = "flogo"
        if ReportYaml.get_capability_app_info(dp_name, capability, app_name, "status") == "Running":
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, '{capability}' App '{app_name}' is Running in DataPlane '{dp_name}'.")
            return
        ColorLogger.info(f"Flogo Start app '{app_name}'...")
        self.goto_app_detail(dp_name, app_name)
    
        print("Waiting to see if app status is Running...")
        self.page.locator("flogo-app-run-status .scale-status-text").wait_for(state="visible")
        # when app status is Running, or the action button is 'Stop', it means app is already running
        is_app_running = self.page.locator("flogo-app-run-status .scale-status-text", has_text="Running").is_visible() or self.page.locator("flogo-app-run-status button", has_text="Stop").is_visible()
        if is_app_running:
            ColorLogger.success(f"Flogo app '{app_name}' is already running.")
            ReportYaml.set_capability_app_info(dp_name, capability, app_name, "status", "Running")
        else:
            self.page.locator("flogo-app-run-status button", has_text="Start").click()
            print("Clicked 'Start' app button")
    
            print(f"Waiting for app '{app_name}' status is Running...")
            if Util.check_dom_visibility(self.page, self.page.locator("flogo-app-run-status .scale-status-text", has_not_text="Scaling"), 15, 180, True):
                app_status = self.page.locator("flogo-app-run-status .scale-status-text").inner_text()
                ColorLogger.success(f"Flogo app '{app_name}' status is '{app_status}' now.")
                ReportYaml.set_capability_app_info(dp_name, capability, app_name, "status", app_status)
            else:
                Util.warning_screenshot(f"Wait too long to scale Flogo app '{app_name}'.", self.page, "flogo_app_start.png")
    
    def flogo_app_test_endpoint(self, dp_name, app_name):
        capability = "flogo"
        if ReportYaml.get_capability_app_info(dp_name, capability, app_name, "testedEndpoint") == "true":
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, has tested '{capability}' App '{app_name}' endpoint in DataPlane '{dp_name}'.")
            return
        ColorLogger.info(f"Flogo Test app endpoint '{app_name}'...")
        self.goto_app_detail(dp_name, app_name)
    
        print("Navigating to 'Endpoints' tab menu")
        self.page.locator(".pl-primarynav__menu .pl-primarynav__item", has_text="Endpoints").click()
    
        print("Check if 'Test' button is visible...")
        self.page.locator(".endpoints-container td.action-button").wait_for(state="visible")
        print("Endpoint action button is loaded.")
        if self.page.locator(".endpoints-container td.action-button a", has_text="Test").is_visible():
            with self.page.context.expect_page() as new_page_info:
                self.page.locator(".endpoints-container td.action-button a", has_text="Test").click()
                print("Clicked 'Test' button")
    
            new_page = new_page_info.value
            print("New window detected and captured.")
    
            print("Waiting for Swagger page loaded.")
            new_page.wait_for_load_state()
    
            print(f"Waiting for Swagger title '{app_name}' to be displayed.")
            if Util.check_dom_visibility(new_page, new_page.locator("#swagger-editor h2.title", has_text=app_name), 5, 15, True):
                new_page.locator("#swagger-editor h2.title", has_text=app_name).wait_for(state="visible")
                print(f"The Swagger title '{app_name}' is displayed.")
    
                new_page.locator("#operations-default-get_flogo .opblock-summary-control").click()
                print("Clicked '/flogo' path, expand API details")
    
                new_page.locator("#operations-default-get_flogo button", has_text="Try it out").click()
                print("Clicked 'Try it out' button")
                new_page.locator("#operations-default-get_flogo button", has_text="Execute").click()
                print("Clicked 'Execute' button")
                new_page.close()
                print("Closed Swagger page")
                ColorLogger.success(f"Test Flogo app '{app_name}', endpoint '/flogo'")
                ReportYaml.set_capability_app_info(dp_name, capability, app_name, "testedEndpoint", True)
            else:
                Util.warning_screenshot(f"Swagger page is not loaded, title '{app_name}' is not displayed.", new_page, "flogo_app_test_endpoint.png")
        else:
            Util.warning_screenshot(f"'Test' button is not visible in Flogo app {app_name}, need to config it and start app.", self.page, "flogo_app_test_endpoint.png")
    
    def flogo_is_app_created(self, app_name):
        ColorLogger.info(f"Checking if Flogo app '{app_name}' is created")
        try:
            print(f"Checking if Flogo app '{app_name}' is already created...")
            self.page.locator("apps-list").wait_for(state="visible")
            self.page.wait_for_timeout(3000)
            if self.page.locator("#app-list-table tr.pl-table__row td.app-name", has_text=app_name).is_visible():
                ColorLogger.success(f"Flogo app '{app_name}' is already created.")
                return True
            else:
                print(f"Flogo app '{app_name}' has not been created.")
                return False
        except Exception as e:
            ColorLogger.warning(f"An error occurred while Checking Flogo app '{app_name}': {e}")
            return False
    
    def flogo_is_app_running(self, app_name):
        ColorLogger.info(f"Checking if Flogo app '{app_name}' is running")
        try:
            print(f"Checking if Flogo app '{app_name}' is already running...")
            self.page.wait_for_timeout(3000)
            if self.page.locator("#app-list-table tr.FLOGO", has=self.page.locator("td.app-name", has_text=app_name)).locator("td", has_text="Running").is_visible():
                ColorLogger.success(f"Flogo app '{app_name}' is already running.")
                return True
            else:
                print(f"Flogo app '{app_name}' has not been running.")
                return False
        except Exception as e:
            ColorLogger.warning(f"An error occurred while Checking Flogo app '{app_name}': {e}")
            return False
