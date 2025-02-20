from utils.color_logger import ColorLogger
from utils.util import Util
from utils.helper import Helper
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
            if Util.check_dom_visibility(self.page, self.page.locator(".resource-success .title", has_text="Capability Provision Request Completed"), 5, 120):
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

    def bwce_provision_connector(self, dp_name, app_name):
        capability = self.capability
        if ReportYaml.get_capability_info(dp_name, capability, "provisionConnector") == "true":
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, '{capability}' Connector is already created in DataPlane '{dp_name}'.")
            return
        ColorLogger.info("BWCE Provisioning connector...")

        # if app is created, not need to check capability status
        is_check_status = True
        if ReportYaml.is_app_created(dp_name, capability, app_name) or self.is_app_created(capability, app_name):
            is_check_status = False
            print(f"'{capability}'App '{app_name}' has been created, no need to check '{capability}' capability status")

        capability_selector_path = "#capContainer-cont-appPackages"
        self.goto_capability(dp_name, capability, capability_selector_path, is_check_status)

        self.page.locator(capability_selector_path).wait_for(state="visible")
        print("BWCE capability page loaded, Checking Plugins...")
        self.page.wait_for_timeout(3000)

        plugins = [text.strip() for text in self.page.locator("#pkgsTbl-table-listPkg td:first-child").all_inner_texts()]
        # Note: check 3 times, because sometimes BWCE Plugins can not be loaded in time
        # if plugins is empty, reload page, and check again, only check 3 times, if still empty, exit for loop
        for i in range(3):
            if plugins:
                break
            Util.refresh_page(self.page)
            self.page.locator(capability_selector_path).wait_for(state="visible")
            print("BWCE capability page loaded, Checking Plugins...")
            self.page.wait_for_timeout(3000)
            plugins = [text.strip() for text in self.page.locator("#pkgsTbl-table-listPkg td:first-child").all_inner_texts()]

        print(f"BWCE Plugins: {plugins}")
        required_connectors = {"BWCE"}
        if required_connectors.issubset(set(plugins)):
            ColorLogger.success("BWCE Plugins are already provisioned.")
            ReportYaml.set_capability_info(dp_name, capability, "provisionConnector", True)
            self.page.locator("#capabilityHeader-lbl-dpname", has_text=dp_name).click()
            print(f"Clicked menu navigator Data Plane '{dp_name}', go back to Data Plane detail page")
            return

        print("Start to Provision BWCE Plugins...")

        self.page.locator("#capPackagesBackToDP", has_text="Provision BWCE & Plug-ins").wait_for(state="visible")
        self.page.locator("#capPackagesBackToDP", has_text="Provision BWCE & Plug-ins").click()
        print("Clicked 'Provision BWCE & Plug-ins' button")
        self.page.locator("#provisionPluginUpdt-footBtn-nextStep").click()
        print("Clicked 'Next' button")
        self.page.locator("#FinishedProvisionPlugin img[src*='success.svg']").wait_for(state="visible")
        ColorLogger.success("Provision BWCE & Plug-ins successful.")
        ReportYaml.set_capability_info(dp_name, capability, "provisionConnector", True)
        self.page.locator("#btnNavigationToDPDetails", has_text="Go back to Data Plane details").click()
        print("Clicked 'Go back to Data Plane details' button")

    def bwce_app_build_and_deploy(self, dp_name, app_file_name, app_name):
        capability = self.capability
        if ReportYaml.get_capability_info(dp_name, capability, "appBuild") == "true":
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, '{capability}' App Build '{app_name}' is already created in DataPlane '{dp_name}'.")
            return
        ColorLogger.info("BWCE Creating app build...")

        # if app is created, not need to check capability status
        is_check_status = True
        if ReportYaml.is_app_created(dp_name, capability, app_name) or self.is_app_created(capability, app_name):
            is_check_status = False
            print(f"'{capability}'App '{app_name}' has been created, no need to check '{capability}' capability status")
        self.goto_capability(dp_name, capability, "#capContainer-cont-appPackages", is_check_status)

        print("BWCE Checking app build...")
        self.page.locator("#capContainer-cont-appBuilds").wait_for(state="visible")
        print("BWCE capability page loaded, Checking BWCE App Builds...")
        self.page.wait_for_timeout(3000)

        is_app_build_created = Util.refresh_until_success(self.page,
                                                          self.page.locator("#capContainer-cont-appBuilds td", has_text=app_name),
                                                          self.page.locator("#capContainer-cont-appBuilds"),
                                                          "BWCE capability page loaded, Checking BWCE App Builds...")

        if is_app_build_created:
            ColorLogger.success(f"BWCE app build {app_name} is already created.")
            ReportYaml.set_capability_info(dp_name, capability, "appBuild", True)
            return

        print("Start Create BWCE app build...")

        self.page.locator("#capBuildsCreateNewBuildBtn", has_text="Create New App Build & Deploy").click()
        print("Clicked 'Create New App Build & Deploy' button")

        # step1: Upload Files
        self.page.locator("ul.pl-secondarynav__menu .is-active a", has_text="Upload EAR").wait_for(state="visible")
        print("BWCE 'App Build & Deploy' Step 1: 'Upload EAR' page is loaded")
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
        print(f"BWCE 'App Build & Deploy' Step 2: '{active_title}' page is loaded")
        # self.page.locator("#bldConf-tblBody-txt-appBuildName-text-input").fill(app_name)

        # click 'Create Build' button in step2
        self.page.locator('#DeployDeployBtn').click()
        print("Clicked 'Create Build' button")

        # step3:
        self.page.wait_for_timeout(2000)
        active_title = self.page.locator("ul.pl-secondarynav__menu .is-active a").inner_text()
        print(f"BWCE 'App Build & Deploy' Step 3: '{active_title}' page is loaded")
        # if step3 is "App Build", will deploy app later, it is for 1.5 version
        # click "Deploy App" button will go to "Resource Configurations" step,
        # same as 1.4 version, and then deploy bwce app from "Resource Configurations" step
        if active_title == "App Build":
            if Util.wait_for_success_message(self.page, 5) is False:
                Util.exit_error(f"API return failed message, failed to create BWCE {app_name} app build", self.page, "bwce_app_build_and_deploy.png")

            print("Waiting for 'Successfully created App Build'")
            if Util.check_dom_visibility(self.page, self.page.locator('.stages .step .message', has_text="Successfully created App Build"),3, 60):
                print(f"Successfully created BWCE {app_name} app build")
                self.page.locator('#finishDeployViewAppBuildsBtn-1', has_text="Deploy App").wait_for(state="visible")
                self.page.locator('#finishDeployViewAppBuildsBtn-1', has_text="Deploy App").click()
                print("Clicked 'Deploy App' button from Finish tab")
                self.page.locator('#appMngModal-btn-deployBWprov', has_text="Deploy").wait_for(state="visible")
                self.page.locator('#appMngModal-btn-deployBWprov', has_text="Deploy").click()
                print("Clicked 'Deploy' button from Deploy App Dialog")
            else:
                Util.exit_error(f"No success message is seen, Failed to create BWCE {app_name} app build", self.page, "bwce_app_build_and_deploy.png")

            self.page.fill("#app-name-text-input", app_name)
            print(f"Filled App Name: {app_name}")
            self.bwce_app_build_and_deploy_select_namespace()

        # below steps is after "Resource Configurations" step
        self.page.locator('#deployComp-btn-ResourceConfigBtn2').click()
        print("Clicked 'Deploy App' button")

        self.page.locator("finished img[src*='success.svg']").wait_for(state="visible")
        ColorLogger.success(f"Created BWCE app build '{app_name}' Successfully")
        print("Check if BWCE app deployed successfully...")

        if Util.check_dom_visibility(self.page, self.page.locator('.stages .step .message', has_text="Successfully Deployed Application"), 5, 60):
            ColorLogger.success(f"BWCE app build '{app_name}' is deployed.")
            ReportYaml.set_capability_info(dp_name, capability, "appBuild", True)

    def bwce_app_build_and_deploy_select_namespace(self):
        self.page.locator("#nameSpace input").click()
        print(f"Clicked 'Namespace' dropdown, and waiting for namespace: {ENV.TP_AUTO_K8S_DP_NAMESPACE}")
        self.page.wait_for_timeout(1000)
        if not self.page.locator("#nameSpace .pl-select-menu li", has_text=ENV.TP_AUTO_K8S_DP_NAMESPACE).is_visible():
            Util.exit_error(f"Namespace '{ENV.TP_AUTO_K8S_DP_NAMESPACE}' is not list in the dropdown.", self.page, "bwce_app_build_and_deploy.png")

        self.page.locator("#nameSpace .pl-select-menu li", has_text=ENV.TP_AUTO_K8S_DP_NAMESPACE).click()
        print(f"Selected namespace: {ENV.TP_AUTO_K8S_DP_NAMESPACE}")
        self.page.locator("label[for='eula-checkbox']").click()
        print("Clicked 'EUA' checkbox")

    def bwce_app_deploy(self, dp_name, app_name):
        capability = self.capability
        if ReportYaml.is_app_created(dp_name, capability, app_name):
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, '{capability}' App '{app_name}' is already created in DataPlane '{dp_name}'.")
            return
        ColorLogger.info(f"BWCE Deploying app '{app_name}'...")
        dp_name_space = ENV.TP_AUTO_K8S_DP_NAMESPACE

        self.goto_dataplane(dp_name)
        if self.page.locator("apps-list td.app-name a", has_text=app_name).is_visible():
            ColorLogger.success(f"BWCE app '{app_name}' in namespace {dp_name_space} is already deployed.")
            ReportYaml.set_capability_app(dp_name, capability, app_name)
            return

        # if app is created, not need to check capability status
        is_check_status = True
        if ReportYaml.is_app_created(dp_name, capability, app_name) or self.is_app_created(capability, app_name):
            is_check_status = False
            print(f"'{capability}'App '{app_name}' has been created, no need to check '{capability}' capability status")
        self.goto_capability(dp_name, capability, "#capContainer-cont-appPackages", is_check_status)

        print(f"Waiting for BWCE app build {app_name} is deployed...")
        if not Util.check_dom_visibility(self.page, self.page.locator("#bldTbl-table-buildsList td:first-child", has_text=app_name), 5, 180, True):
            Util.exit_error(f"BWCE app {app_name} is not deployed.", self.page, "bwce_app_deploy.png")

        # if capability appBuild has not been set to true, set it to true
        # in bwce_app_build_and_deploy function, the appBuild has not displayed, but now it is displayed, should set appBuild to true
        if ReportYaml.get_capability_info(dp_name, capability, "appBuild") != "true":
            ReportYaml.set_capability_info(dp_name, capability, "appBuild", True)

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
            self.bwce_app_build_and_deploy_select_namespace()

            self.page.locator('#deployComp-btn-ResourceConfigBtn2').click()
            print("Clicked 'Deploy App' button")
            print("Check if BWCE app deployed successfully...")
            if Util.check_dom_visibility(self.page, self.page.locator('.stages .step .message', has_text="Successfully Deployed Application"), 5, 120):
                self.page.locator("#finished-btn-gotoDPDetails-finishDeployViewDeployBuildsBtn-1").click()
                print("Clicked 'View Deployed App' button, go back to Data Plane detail page")
        else:
            # if case goes here, it means the Deploy App dialog is not popup, CP version maybe is 1.3, it has not been tested
            print("Dialog 'Deploy App Build' does not popup")
            Util.exit_error(f"BWCE app {app_name} dialog 'Deploy App Build' does not popup.", self.page, "bwce_app_deploy.png")

        print(f"Waiting for BWCE app '{app_name}' is deployed...")
        if Util.check_dom_visibility(self.page, self.page.locator("apps-list td.app-name a", has_text=app_name), 5, 120):
            ColorLogger.success(f"Deploy BWCE app '{app_name}' in namespace {dp_name_space} Successfully")
            ReportYaml.set_capability_app(dp_name, capability, app_name)
        else:
            Util.warning_screenshot(f"Deploy BWCE app '{app_name}' in namespace {dp_name_space} may failed.", self.page, "bwce_app_deploy-2.png")

    def bwce_app_config(self, dp_name, app_name):
        capability = self.capability
        ColorLogger.info(f"BWCE Config app '{app_name}'...")
        self.goto_app_detail(dp_name, app_name, ".app-name")

        if ReportYaml.get_capability_app_info(dp_name, capability, app_name, "endpointPublic") == "true":
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, '{capability}' Endpoints is already Public in DataPlane '{dp_name}'.")
        else:
            if self.page.locator(".no-endpoints", has_text="There are no Endpoints configured for the application").is_visible():
                Util.warning_screenshot(f"There is some error for BWCE app '{app_name}', it has no Endpoints configured.", self.page, "bwce_app_config.png")
                return

            self.page.locator("#tab-endpoints").click()
            print("Clicked 'Endpoints' tab")
            # set Endpoint Visibility to Public
            self.page.locator(".endpoints").wait_for(state="visible")
            print("Endpoint tab is loaded.")
            if Util.check_dom_visibility(self.page, self.page.locator("#endpointV1-btn-openSwagger"), 2, 6):
                ColorLogger.success(f"BWCE app '{app_name}' has set Endpoint Visibility to Public.")
                ReportYaml.set_capability_app_info(dp_name, capability, app_name, "endpointPublic", True)
            else:
                print("No 'Test' button, will set Endpoint Visibility to Public")
                self.page.locator("#app-details-menu-dropdown-label").wait_for(state="visible")
                self.page.locator("#app-details-menu-dropdown-label").click()
                self.page.locator(".pl-dropdown-menu__action", has_text="Set Endpoint Visibility").wait_for(state="visible")
                self.page.locator(".pl-dropdown-menu__action", has_text="Set Endpoint Visibility").click()
                print("Clicked 'Set Endpoint Visibility' menu item")
                self.page.locator("#appDtls-appEndPntMod1-btn-saveChanges", has_text="Save Changes").wait_for(state="visible")
                print("Dialog 'Set Endpoint Visibility' popup")
                if self.page.locator(".pl-modal__container strong", has_text="Update Endpoint visibility").is_visible():
                    if self.page.locator(".pl-table__cell label", has_text=ENV.TP_AUTO_INGRESS_CONTROLLER_BWCE).is_visible():
                        self.page.locator(".pl-table__cell label", has_text=ENV.TP_AUTO_INGRESS_CONTROLLER_BWCE).click()
                        print(f"Selected '{ENV.TP_AUTO_INGRESS_CONTROLLER_BWCE}' from Resource Name column")
                        self.page.locator('label[for="endpoint-radio-0-public"]').click()
                        print("Set Public Endpoint Visibility to 'Public'")
                        self.page.locator("#appDtls-appEndPntMod1-btn-saveChanges", has_text="Save Changes").click()
                        print("Clicked 'Save Changes' button")
                        if Util.wait_for_success_message(self.page, 5) and self.page.locator("#endpointV1-btn-openSwagger").is_visible():
                            ColorLogger.success(f"BWCE app '{app_name}' has set Endpoint Visibility to Public.")
                            ReportYaml.set_capability_app_info(dp_name, capability, app_name, "endpointPublic", True)
                    else:
                        Util.warning_screenshot(f"Not able to set Endpoint Visibility to Public, '{ENV.TP_AUTO_INGRESS_CONTROLLER_BWCE}' is not available.", self.page, "bwce_app_config-endpoint.png")

        if ReportYaml.get_capability_app_info(dp_name, capability, app_name, "enableTrace") == "true":
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, '{capability}' Trace is already Enabled in DataPlane '{dp_name}'.")
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
            bwce_otel_trace_selector = traces_row.locator("#engVars-btn-toggleBoolea")
            if bwce_otel_trace_selector.inner_text().lower() == "true":
                ColorLogger.success("BW_OTEL_TRACES_ENABLED is already set to true.")
                ReportYaml.set_capability_app_info(dp_name, capability, app_name, "enableTrace", True)
            else:
                bwce_otel_trace_selector.click()
                self.page.locator("#engVars-btn-valTrue").wait_for(state="visible")
                self.page.locator("#engVars-btn-valTrue").click()
                print("Set BW_OTEL_TRACES_ENABLED to true")
                self.page.wait_for_timeout(1000)
                self.page.locator("#engVars-btn-pushUpdates").click()
                print("Clicked 'Push Updates' button")
                if Util.wait_for_success_message(self.page, 5):
                    ColorLogger.success("Set BW_OTEL_TRACES_ENABLED to true successfully.")
                    ReportYaml.set_capability_app_info(dp_name, capability, app_name, "enableTrace", True)

    def bwce_app_start(self, dp_name, app_name):
        capability = self.capability
        if ReportYaml.get_capability_app_info(dp_name, capability, app_name, "status") == "Running" or self.is_app_running(dp_name, capability, app_name):
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, '{capability}' App '{app_name}' is Running in DataPlane '{dp_name}'.")
            return
        ColorLogger.info(f"BWCE Start app '{app_name}'...")
        self.goto_app_detail(dp_name, app_name, ".app-name")

        print("Waiting to see if app status is Running...")
        self.page.locator("#appDtls-appName-cont .status_label").wait_for(state="visible")
        # when app status is Running, or the action button is 'Stop', it means app is already running
        is_app_running = self.page.locator("#appDtls-appName-cont .status_label", has_text="Running").is_visible() or self.page.locator(".start_stop", has_text="Stop").is_visible()
        if is_app_running:
            ColorLogger.success(f"BWCE app '{app_name}' is already running.")
            ReportYaml.set_capability_app_info(dp_name, capability, app_name, "status", "Running")
        else:
            self.page.locator(".start_stop", has_text="Start").click()
            print("Clicked 'Start' app button")

            print(f"Waiting for app '{app_name}' status is Running...")
            if Util.check_dom_visibility(self.page, self.page.locator("#appDtls-appName-cont .status_label", has_not_text="Scaling"), 15, 240, True):
                app_status = self.page.locator("#appDtls-appName-cont .status_label").inner_text()
                ColorLogger.success(f"BWCE app '{app_name}' status is '{app_status}' now.")
                ReportYaml.set_capability_app_info(dp_name, capability, app_name, "status", app_status)
            else:
                Util.warning_screenshot(f"Wait too long to scale BWCE app '{app_name}'.", self.page, "flogo_app_start.png")

    def bwce_app_test_endpoint(self, dp_name, app_name):
        capability = self.capability
        if ReportYaml.get_capability_app_info(dp_name, capability, app_name, "testedEndpoint") == "true":
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, has tested '{capability}' App '{app_name}' endpoint in DataPlane '{dp_name}'.")
            return
        ColorLogger.info(f"BWCE Test app endpoint '{app_name}'...")
        self.goto_app_detail(dp_name, app_name, ".app-name")

        print("Navigating to 'Endpoints' tab menu")
        self.page.locator("#tab-endpoints").click()
        print("Clicked 'Endpoints' tab")
        self.page.locator(".endpoint-menu-dropdown").wait_for(state="visible")
        print("Endpoint tab is loaded.")
        self.page.wait_for_timeout(1000)
        print("Check if 'Test' button is visible...")
        if self.page.locator("#endpointV1-btn-openSwagger").is_visible():
            with self.page.context.expect_page() as new_page_info:
                self.page.locator("#endpointV1-btn-openSwagger").click()
                print("Clicked 'Test' button")

            new_page = new_page_info.value
            print("New window detected and captured.")

            print("Waiting for Swagger page loaded.")
            new_page.wait_for_load_state()

            print(f"Waiting for Swagger title '{app_name}' to be displayed.")
            if Util.check_dom_visibility(new_page, new_page.locator("#swagger-ui h2.title", has_text=app_name), 5, 15, True):
                new_page.locator("#swagger-ui h2.title", has_text=app_name).wait_for(state="visible")
                print(f"The Swagger title '{app_name}' is displayed.")

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
                ColorLogger.success(f"Test BWCE app '{app_name}', endpoint '/resource'")
                ReportYaml.set_capability_app_info(dp_name, capability, app_name, "testedEndpoint", True)
            else:
                Util.warning_screenshot(f"Swagger page is not loaded, title '{app_name}' is not displayed.", new_page, "bwce_app_test_endpoint.png")
        else:
            Util.warning_screenshot(f"'Test' button is not visible in BWCE app {app_name}, need to config it and start app.", self.page, "bwce_app_test_endpoint.png")
