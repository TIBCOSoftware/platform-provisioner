#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary

from utils.color_logger import ColorLogger
from utils.util import Util
from utils.helper import Helper
from utils.env import ENV
from utils.report import ReportYaml
from page_object.po_dataplane import PageObjectDataPlane

class PageObjectBMDPConfiguration(PageObjectDataPlane):
    capability = "BW5"
    def __init__(self, page):
        super().__init__(page)

    def goto_dataplane_config(self):
        ColorLogger.info(f"Going to Data plane Configuration page...")
        self.page.locator("#ct-dp-config-link").wait_for(state="visible")
        self.page.locator("#ct-dp-config-link").click()
        print("Clicked 'BMDP configuration' button")
        self.page.wait_for_timeout(500)

    def goto_dataplane_config_sub_menu(self, sub_menu_name = ""):
        ColorLogger.info(f"Going to Data plane config -> '{sub_menu_name}' side menu")
        self.page.locator("#left-sub-menu .menu-item-text", has_text=sub_menu_name).click()
        print(f"Clicked '{sub_menu_name}' left side menu")
        self.page.wait_for_timeout(500)

    def goto_products(self, product_name):
        ColorLogger.info("Going to Products page...")
        # "BW5 Adapters" for BW5, "BE" for be, "BW6" for BW6
        print(f"Checking if {product_name} Card is Available.")
        if Util.check_dom_visibility(self.page, self.page.locator(f".product-card:not(.disabled-card):has-text('{product_name}')"), 10, 120, True):
            self.page.locator(f".product-card:not(.disabled-card):has-text('{product_name}')").click()
            print(f"Clicked '{product_name}' Card")
        else:
            Util.exit_error(f"{product_name} Card is not visible.", self.page, "goto_Products.png")

    def dp_config_bw5_rvdm(self, domain_name):

        ColorLogger.info("Config BW5 RV domain...")
        if not Util.check_dom_visibility(self.page, self.page.locator(f"td.pl-table__cell:text('{domain_name}')"), 3, 10, True):
            # add domain
            self.page.locator("#add-domain-button").wait_for(state="visible")
            self.page.locator("#add-domain-button").click()
            print("Clicked 'Add Domain' button, to configure BW5 RV domain")
            self.page.fill("#domainName-input", ENV.TP_AUTO_K8S_BMDP_BW5_RVDM)
            print(f"Filled Domain Name: {ENV.TP_AUTO_K8S_BMDP_BW5_RVDM}")

            # select message transport from dropdown
            self.page.locator(".pl-select__toggle").click()
            self.page.locator("li.pl-select-menu__item", has_text="RV").click()
            print("Selected 'RV' from dropdown")
            self.page.fill("#rvService-input", ENV.TP_AUTO_K8S_BMDP_BW5_RVDM_RV_SERVICE)
            self.page.fill("#rvNetwork-input", ENV.TP_AUTO_K8S_BMDP_BW5_RVDM_RV_NETWORK)
            self.page.fill("#rvDaemon-input", ENV.TP_AUTO_K8S_BMDP_BW5_RVDM_RV_DAEMON)
            print(f"Filled RV Service: {ENV.TP_AUTO_K8S_BMDP_BW5_RVDM_RV_SERVICE}, RV Network: {ENV.TP_AUTO_K8S_BMDP_BW5_RVDM_RV_NETWORK}, RV Daemon: {ENV.TP_AUTO_K8S_BMDP_BW5_RVDM_RV_DAEMON}")
            self.page.locator(".pl-button.pl-button--primary", has_text="Add Domain").click()
            self.page.wait_for_timeout(5000)
            domain_banner = self.page.locator(".pl-notification__message").inner_text()
            if self.page.locator(".pl-notification__message", has_text="successfully").is_visible():
                ColorLogger.success(domain_banner)
            else:
                Util.warning_screenshot(f"May faild to regiter RV domain due to: {domain_banner}", self.page, "dp_config_bw5_rvdm.png")
        self.check_bw5_domain_status(domain_name)

    def dp_config_bw5_emsdm(self, domain_name):

        ColorLogger.info("Config BW5 EMS domain...")
        if not Util.check_dom_visibility(self.page, self.page.locator(f"td.pl-table__cell:text('{domain_name}')"), 3, 10, True):
            # add domain
            self.page.locator("#add-domain-button").wait_for(state="visible")
            self.page.locator("#add-domain-button").click()
            print("Clicked 'Add Domain' button, to configure BW5 EMS domain")
            self.page.fill("#domainName-input", ENV.TP_AUTO_K8S_BMDP_BW5_EMSDM)
            print(f"Filled Domain Name: {ENV.TP_AUTO_K8S_BMDP_BW5_EMSDM}")

            # select message transport from dropdown
            self.page.locator(".pl-select__toggle").click()
            self.page.locator("li.pl-select-menu__item", has_text="EMS").click()
            print("Selected 'EMS' from dropdown")
            self.page.fill("#emsServerUrl-input", ENV.TP_AUTO_K8S_BMDP_BW5_EMS_SERVER_URL)
            self.page.fill("#emsUserName-input", ENV.TP_AUTO_K8S_BMDP_BW5_EMS_USERNAME)
            self.page.fill("#emsPassword-input", ENV.TP_AUTO_K8S_BMDP_BW5_EMS_PASSWORD)
            print(f"Filled EMS Server URL: {ENV.TP_AUTO_K8S_BMDP_BW5_EMS_SERVER_URL}, EMS User: {ENV.TP_AUTO_K8S_BMDP_BW5_EMS_USERNAME}, EMS Password: {ENV.TP_AUTO_K8S_BMDP_BW5_EMS_PASSWORD}")
            self.page.locator(".pl-button.pl-button--primary", has_text="Add Domain").click()
            self.page.wait_for_timeout(5000)
            domain_banner = self.page.locator(".pl-notification__message").inner_text()
            if self.page.locator(".pl-notification__message", has_text="successfully").is_visible():
                ColorLogger.success(domain_banner)
            else:
                Util.warning_screenshot(f"May faild to regiter RV domain due to: {domain_banner}", self.page, "dp_config_bw5_emsdm.png")
        else:
            ColorLogger.info(f"Domain '{domain_name}' is already added.")
        self.check_bw5_domain_status(domain_name)

    def check_bw5_domain_status(self, domain_name, max_retries=180):
        ColorLogger.info(f"Checking domain status for '{domain_name}'")
        domain_row = self.page.locator("tr.pl-table__row", has=self.page.locator('td.pl-table__cell', has_text=domain_name))
        if domain_row.is_visible():
            if Util.check_dom_visibility(self.page, domain_row.locator("td.pl-table__cell img[src*='/connected.svg']"), 10, max_retries):
                ColorLogger.success(f"Domain '{domain_name}' is connected.")
                ReportYaml.set_capability(ENV.TP_AUTO_K8S_BMDP_NAME, self.capability)
                ReportYaml.set_capability_info(ENV.TP_AUTO_K8S_BMDP_NAME, self.capability, domain_name, "Connected")
                return
            Util.exit_error(f"Domain '{domain_name}' status is disconnected.", self.page, "check_bw5_domain_status.png")
        else:
            Util.exit_error(f"Domain '{domain_name}' is not found.", self.page, "check_domain_status.png")


    def check_bmdp_app_status_by_app_name(self, product_name, domain_name, app_name):
        ColorLogger.info(f"Checking {product_name} application - {app_name} status in '{domain_name}'")
        self.page.wait_for_timeout(1000)
        app_row = self.page.locator("tr.pl-table__row", has=self.page.locator('td.pl-table__cell', has_text=domain_name))
        if Util.check_dom_visibility(self.page, app_row.locator("td.pl-table__cell img[src*='/pl-icon-success.svg']"), 5, 120, True):
            app_row.locator('td.pl-table__cell .text', has_text=app_name).click()
            print(f"'{app_name}' is deployed and checking service instance status.")
            ReportYaml.set_capability_app(ENV.TP_AUTO_K8S_BMDP_NAME, self.capability, f"{domain_name}.{app_name}")
        else:
            Util.exit_error(f"'{app_name}' is not deployed successfully or cannot be discovered by CT in domain '{domain_name}'.", self.page, "check_bmdp_app_status_by_app_name.png")
        service_instance_row = self.page.locator("tr.pl-table__row")
        if Util.check_dom_visibility(self.page, service_instance_row.locator("td.pl-table__cell img[src*='/pl-icon-success.svg']"), 5, 120, True):
            ColorLogger.success(f"'{app_name}' in domain '{domain_name}' instance is running.")
            ReportYaml.set_capability_app_info(ENV.TP_AUTO_K8S_BMDP_NAME, self.capability, f"{domain_name}.{app_name}", "Status", "Running")
        else:
            Util.exit_error(f"'{app_name}' in domain '{domain_name}' instance is not running.", self.page, "check_bmdp_app_status_by_app_name.png")

        print("Clicked 'ElasticSearch' left side menu")
        self.page.wait_for_timeout(500)
        if Util.check_dom_visibility(self.page, self.page.locator(".pl-button.pl-button--primary", has_text="Add ElasticSearch"), 1, 3):
            self.page.locator(".pl-button.pl-button--primary", has_text="Add ElasticSearch").click()
            print("Clicked 'Add ElasticSearch' button")
            self.page.fill("#esUrl-input", ENV.TP_AUTO_ELASTIC_URL)
            self.page.fill("#esUser-input", ENV.TP_AUTO_ELASTIC_USER)
            self.page.fill("#esPassword-input", ENV.TP_AUTO_ELASTIC_PASSWORD)
            print(f"Filled ElasticSearch URL: {ENV.TP_AUTO_ELASTIC_URL}, User: {ENV.TP_AUTO_ELASTIC_USER}, Password: {ENV.TP_AUTO_ELASTIC_PASSWORD}")
            self.page.locator(".pl-button.pl-button--primary", has_text="Add").click()
            self.page.wait_for_timeout(5000)
            if self.page.locator(".pl-notification__message", has_text="successfully").is_visible():
                ColorLogger.success("ElasticSearch is added successfully.")
            else:
                Util.warning_screenshot("May faild to add ElasticSearch.", self.page, "o11y_prepare_es.png")
        else:
            ColorLogger.info("ElasticSearch is already added.")

    def o11y_get_new_resource(self, dp_name):
        # For 1.4 version
        add_new_resource_button = self.page.locator(".add-dp-observability-btn", has_text="Add new resource")
        if self.page.locator(".o11y-no-config .o11y-config-buttons").is_visible():
            if dp_name == ENV.TP_AUTO_DP_NAME_GLOBAL:
                # For 1.5 Global data plane
                add_new_resource_button = self.page.locator(".o11y-no-config .o11y-config-buttons .add-global-o11y-icon")
            else:
                # For 1.5 none Global data plane
                add_new_resource_button = self.page.locator(".o11y-no-config .o11y-config-buttons .add-dp-o11y-icon").nth(0)

        return add_new_resource_button

    def o11y_config_switch_to_global(self, dp_name):
        ColorLogger.info(f"Switch dataplane {dp_name} configuration to Global...")
        self.goto_left_navbar_dataplane()
        self.goto_dataplane(dp_name)
        self.goto_dataplane_config()
        self.goto_dataplane_config_sub_menu("Observability")
        self.switch_to_global_config(dp_name)

    def o11y_config_dataplane_resource(self, dp_name):
        if ReportYaml.get_dataplane_info(dp_name, "o11yConfig") == "true":
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, o11yConfig is already created in DataPlane '{dp_name}'.")
            return

        ColorLogger.info(f"O11y start config {dp_name} dataplane resource...")
        if not ENV.TP_AUTO_IS_CONFIG_O11Y:
            ColorLogger.warning("TP_AUTO_IS_CONFIG_O11Y is false, skip config Observability Resource.")
            return
        dp_title = dp_name
        o11y_config_page_selector = ".data-plane-observability-content"         # for dp level
        # dp_name is 'Global', it means global data plane
        if dp_name == ENV.TP_AUTO_DP_NAME_GLOBAL:
            self.goto_left_navbar_dataplane()
            self.page.locator(".global-configuration button", has_text="Global configuration").click()
            print("Clicked 'Global configuration' button")
            o11y_selector = ".pl-leftnav-layout .pl-leftnav-menu__link"         # for 1.4 version
            if Util.check_dom_visibility(self.page, self.page.locator(".pl-leftnav-layout .pl-tooltip__trigger", has_text="Observability"), 3, 6):
                o11y_selector = ".pl-leftnav-layout .pl-tooltip__trigger"       # for 1.5+ version
            self.page.locator(o11y_selector, has_text="Observability").wait_for(state="visible")
            self.page.locator(o11y_selector, has_text="Observability").click()
            print("Clicked Global configuration -> 'Observability' left side menu")
            o11y_config_page_selector = ".global-configuration-details"         # for global level
            ReportYaml.set_dataplane(dp_name)
        else:
            self.goto_dataplane_config_sub_menu("Observability")

        print("Waiting for Observability config is loaded")
        if not Util.check_dom_visibility(self.page, self.page.locator(o11y_config_page_selector), 3, 10):
            Util.exit_error(f"Data Plane '{dp_title}' Observability config load failed.", self.page, "o11y_config_dataplane_resource.png")

        print("Checking if 'Add new resource' button is exist...")
        self.page.wait_for_timeout(2000)

        add_new_resource_button = self.o11y_get_new_resource(dp_name)
        if not add_new_resource_button.is_visible():
            print("'Add new resource' button is not exist...")
            ColorLogger.success(f"Data plane '{dp_title}' Observability Resources is already configured.")
            ReportYaml.set_dataplane_info(dp_name, "o11yConfig", True)
            return

        add_new_resource_button.click()
        print("Clicked 'Create new Data Plane Resources' button")

        print("Waiting for O11y config o11y page is loaded")
        self.page.locator(".configuration").wait_for(state="visible")
        self.page.wait_for_timeout(2000)
        print("O11y config o11y page is loaded")

        # Step 1: Configure Log Server
        if self.page.locator("#resourceName-input").is_visible():    # for 1.3,1.4 version
            self.page.fill("#resourceName-input", f"{dp_name}-rs")
            print(f"Input Resource Name: {dp_name}-rs")
        self.page.locator("#go-to-metrics-server-configuration").click()
        print("Clicked 'Next' button, move to 'Configure Metrics Server' Step 2")

        # Step 2: Configure Metrics Server
        system_toggle = self.page.locator("#metrics-toggle-system-config")
        if system_toggle.is_visible() and system_toggle.get_attribute("aria-checked") == "true":
            print("Metrics System Config is enabled")
            self.page.locator("label[for='metrics-toggle-system-config']").click()
            print("Clicked 'Metrics System Config' toggle button, then wait for 1 second.")
            self.page.wait_for_timeout(1000)

        # Add or Select Metrics -> Query Service configurations
        menu_name = "Metrics"
        tab_name = "Query Service"
        self.o11y_config_table_add_or_select_item(dp_name, menu_name, tab_name, "", "#add-metrics-proxy-btn")

        # Add or Select Metrics -> Exporter configurations
        tab_name = "Exporter"
        if self.page.locator("label[for='metrics-exporter-toggle']", has_text=f"{tab_name} disabled").is_visible():
            self.page.locator("label[for='metrics-exporter-toggle']").click()
            print(f"Clicked '{tab_name}' toggle button")
        if self.page.locator("label[for='metrics-exporter-toggle']", has_text=f"{tab_name} enabled").is_visible():
            self.o11y_config_table_add_or_select_item(dp_name, menu_name, tab_name, "", "#add-metrics-exporter-btn")
        self.page.locator("#go-to-traces-configuration").click()
        print("Clicked 'Next' button")
        print(f"Data plane '{dp_title}' 'Configure Metrics Server' Step 2 is configured.")

        # Step 3: Configure Traces Server
        system_toggle = self.page.locator("#traces-toggle-system-config")
        if system_toggle.is_visible() and system_toggle.get_attribute("aria-checked") == "true":
            print("Traces System Config is enabled")
            self.page.locator("label[for='traces-toggle-system-config']").click()
            print("Clicked 'Traces System Config' toggle button, then wait for 1 second.")
            self.page.wait_for_timeout(1000)

        # Add or Select Traces -> Query Service configurations
        menu_name = "Traces"
        tab_name = "Query Service"
        if self.page.locator("label[for='traces-proxy']", has_text=f"{tab_name} disabled").is_visible():
            self.page.locator("label[for='traces-proxy']").click()
            print(f"Clicked '{tab_name}' toggle button")
        if self.page.locator("label[for='traces-proxy']", has_text=f"{tab_name} enabled").is_visible():
            self.o11y_config_table_add_or_select_item(dp_name, menu_name, tab_name, "", "#add-traces-proxy-btn")

        # Add or Select Traces -> Exporter configurations
        tab_name = "Exporter"
        if self.page.locator("label[for='traces-exporter']", has_text=f"{tab_name} disabled").is_visible():
            self.page.locator("label[for='traces-exporter']").click()
            print(f"Clicked '{tab_name}' toggle button")
        if self.page.locator("label[for='traces-exporter']", has_text=f"{tab_name} enabled").is_visible():
            self.o11y_config_table_add_or_select_item(dp_name, menu_name, tab_name, "", "#add-traces-exporter-btn")
        self.page.locator("#save-observability").click()
        print(f"Data plane '{dp_title}' 'Configure Traces Server' Step 3 is configured.")
        self.page.wait_for_timeout(1000)
        if self.page.locator(".pl-notification--error").is_visible():
            Util.warning_screenshot(f"Data Plane '{dp_title}' Observability Resources configuration failed.", self.page, "o11y_config_dataplane_resource.png")
            self.page.locator("#cancel-observability-add-traces").click()
            print("Clicked 'Cancel' button")
            self.page.locator('#confirm-button', has_text="Yes").wait_for(state="visible")
            self.page.locator('#confirm-button', has_text="Yes").click()
            return

        ColorLogger.success(f"Data plane '{dp_title}' Observability Resources is configured.")
        ReportYaml.set_dataplane_info(dp_name, "o11yConfig", True)
        print(f"Wait 5 seconds for Data plane '{dp_title}' configuration page redirect.")
        self.page.wait_for_timeout(15000)

    def o11y_config_table_add_or_select_item(self, dp_name, menu_name, tab_name, tab_sub_name, add_button_selector):
        ColorLogger.info("O11y start to add or select item...")
        name_input = Helper.get_o11y_sub_name_input(dp_name, menu_name, tab_name, tab_sub_name)
        print(f"Check if name: '{name_input}' is exist in {tab_sub_name} configurations")
        if not Util.check_dom_visibility(self.page, self.page.locator("observability-configurations table tr", has=self.page.locator("td", has_text=name_input)), 3, 10):
            self.page.locator(add_button_selector).click()
            print(f"Clicked 'Add {tab_name} configuration' button in {tab_sub_name} configurations")
            self.o11y_new_resource_fill_form(menu_name, tab_name, tab_sub_name, name_input, dp_name)

        print(f"Waiting for '{name_input}' display in {tab_name}")
        self.page.locator("observability-configurations table tr", has=self.page.locator("td", has_text=name_input)).locator("label").wait_for(state="visible")
        self.page.locator("observability-configurations table tr", has=self.page.locator("td", has_text=name_input)).locator("label").click()
        print(f"Selected '{name_input}' in {tab_name} configurations")

    # when dp_name is empty, it means global data plane
    def o11y_new_resource_fill_form(self, menu_name, tab_name, tab_sub_name, name_input, dp_name):
        ColorLogger.info("O11y start to fill new resource form...")
        dp_title = dp_name
        print(f"Fill form for Data Plane: {dp_title} -> O11y-> {menu_name} -> {tab_name} ...")
        self.page.locator("configuration-modal .pl-modal").wait_for(state="visible")
        self.page.fill("#config-name-input", name_input)
        self.page.locator("configuration-modal input.pl-select__control").click()
        print(f"Clicked 'Query Service type' dropdown")
        self.page.locator("configuration-modal .pl-select-menu__item").nth(0).wait_for(state="visible")

        if menu_name == "Metrics":
            self.page.locator("configuration-modal .pl-select-menu__item", has_text="Prometheus").click()
            print(f"Selected 'Prometheus' in 'Query Service type' dropdown")
            if tab_name == "Query Service":
                self.o11y_fill_prometheus_or_elastic("Prometheus", ENV.TP_AUTO_PROMETHEUS_URL, ENV.TP_AUTO_PROMETHEUS_USER, ENV.TP_AUTO_PROMETHEUS_PASSWORD)
        else:
            self.page.locator("configuration-modal .pl-select-menu__item", has_text="ElasticSearch").click()
            print(f"Selected 'ElasticSearch' in 'Query Service type' dropdown")
            self.page.locator("#endpoint-input").wait_for(state="visible")
            print(f"Filling ElasticSearch form...")
            if menu_name == "Logs":
                log_index = name_input
                if tab_sub_name == "Query Service" or tab_sub_name == "User Apps Exporter":
                    log_index = f"{dp_title.lower()}-log-index"
                self.page.fill("#log-index-input", log_index)
                print(f"Fill Log Index: {log_index}")

            self.o11y_fill_prometheus_or_elastic("ElasticSearch", ENV.TP_AUTO_ELASTIC_URL, ENV.TP_AUTO_ELASTIC_USER, ENV.TP_AUTO_ELASTIC_PASSWORD)

        self.page.locator("configuration-modal .pl-modal__footer-left button.pl-button--primary", has_text="Save").click()
        self.page.wait_for_timeout(10000)
        if self.page.locator(".pl-notification--error").is_visible():
            Util.exit_error(f"Add {name_input} for Data Plane '{dp_title}' Observability -> {menu_name} -> {tab_name} failed.", self.page, f"o11y_new_resource_fill_form-{name_input}.png")

        if Util.check_dom_visibility(self.page, self.page.locator("observability-configurations table tr", has=self.page.locator("td", has_text=name_input)), 2, 6):
            ColorLogger.success(f"Added {name_input} for Data Plane '{dp_title}' Observability -> {menu_name} -> {tab_name}")

    def o11y_fill_prometheus_or_elastic(self, query_service_type, url, username, password):
        ColorLogger.info(f"O11y Filling {query_service_type} form...")
        self.page.locator("#endpoint-input").wait_for(state="visible")
        if not self.page.locator("#endpoint-input").is_visible():
            Util.exit_error(f"Query Service type: {query_service_type} is not visible.", self.page, "o11y_fill_prometheus_or_elastic.png")

        self.page.fill("#endpoint-input", url)
        print(f"Fill {query_service_type} URL: {url}")
        if username != "":
            self.page.fill("#username-input", username)
            print(f"Fill {query_service_type} User: {username}")
        if password != "":
            self.page.fill("#password-input", password)
            print(f"Fill {query_service_type} Password: {password}")
