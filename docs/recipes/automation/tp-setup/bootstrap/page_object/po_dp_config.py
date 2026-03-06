#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary
import os
import re

from utils.color_logger import ColorLogger
from utils.util import Util
from utils.helper import Helper
from utils.env import ENV
from utils.report import ReportYaml
from page_object.po_dataplane import PageObjectDataPlane

class PageObjectDataPlaneConfiguration(PageObjectDataPlane):
    def __init__(self, page):
        super().__init__(page)

    def goto_dataplane_config(self):
        ColorLogger.info(f"Going to Data plane Configuration page...")
        self.page.locator("button", has_text="Data Plane configuration").wait_for(state="visible")
        self.page.locator("button", has_text="Data Plane configuration").click()
        print("Clicked 'Data Plane configuration' button")
        self.page.wait_for_timeout(500)

    def goto_dataplane_config_sub_menu(self, sub_menu_name, child_menu_name=""):
        ColorLogger.info(f"Going to Data plane config -> '{sub_menu_name}' side menu")
        self.page.locator("#left-sub-menu .menu-item-text", has_text=sub_menu_name).click()
        print(f"Clicked '{sub_menu_name}' left side menu")
        if child_menu_name:
            self.page.locator(".menu-item-list .pl-leftnav-menu__nested .pl-leftnav-menu__link", has_text=child_menu_name).wait_for(state="visible")
            self.page.locator(".menu-item-list .pl-leftnav-menu__nested .pl-leftnav-menu__link", has_text=child_menu_name).click()
            print(f"Clicked '{child_menu_name}' left side menu")
        self.page.wait_for_timeout(500)

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
        if ReportYaml.get_dataplane_info(dp_name, "switchGlobal") == "true":
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, switch to Global is already set in DataPlane '{dp_name}'.")
            return
        ColorLogger.info(f"Switch dataplane {dp_name} configuration to Global...")
        self.goto_left_navbar_dataplane()
        self.goto_dataplane(dp_name)
        self.goto_dataplane_config()
        self.goto_dataplane_config_sub_menu("Observability")
        self.switch_to_global_config(dp_name)

    def o11y_config_activation(self, dp_name):
        ColorLogger.info("Start to config Activation Service...")
        if ReportYaml.get_dataplane_info(dp_name, "activation"):
            ColorLogger.success(f"Activation already set for '{dp_name}', skipping.")
            return

        self.goto_left_navbar_dataplane()
        if dp_name == ENV.TP_AUTO_DP_NAME_GLOBAL:
            self.page.locator("button", has_text="Global configuration").click()
            print("Clicked 'Global configuration' button")

            # This is new for 1.9+ version, to set global activation service
            print("Start to set Global Activation Service...")
            self.dp_config_activation(dp_name)
        else:
            self.goto_dataplane(dp_name)
            self.goto_dataplane_config()
            # This is new for 1.9+ version, link to global activation service
            print("Start to link to Global Activation Service...")
            self.dp_config_activation(dp_name, True)

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
            ReportYaml.set_dataplane(dp_name)
            self.goto_left_navbar_dataplane()
            self.page.locator("button", has_text="Global configuration").click()
            print("Clicked 'Global configuration' button")

            o11y_selector = ".pl-leftnav-layout .pl-leftnav-menu__link"         # for 1.4 version
            if Util.check_dom_visibility(self.page, self.page.locator(".pl-leftnav-layout .pl-tooltip__trigger", has_text="Observability"), 3, 6):
                o11y_selector = ".pl-leftnav-layout .pl-tooltip__trigger"       # for 1.5+ version
            self.page.locator(o11y_selector, has_text="Observability").wait_for(state="visible")
            self.page.locator(o11y_selector, has_text="Observability").click()
            print("Clicked Global configuration -> 'Observability' left side menu")
            o11y_config_page_selector = ".global-configuration-details"         # for global level
        else:
            self.goto_dataplane_config_sub_menu("Observability")

        print("Waiting for Observability config is loaded")
        if not Util.check_dom_visibility(self.page, self.page.locator(o11y_config_page_selector), 3, 6):
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
        if self.page.locator("#resourceName-input").is_visible():    # for 1.3 version
            self.page.fill("#resourceName-input", f"{dp_name}-rs")
            print(f"Input Resource Name: {dp_name}-rs")
        # Add or Select Logs -> User Apps -> Query Service configurations
        menu_name = "Logs"
        tab_name = "Query Service"
        if self.page.locator("label[for='userapp-proxy']", has_text=f"{tab_name} disabled").is_visible():
            self.page.locator("label[for='userapp-proxy']").click()
            print(f"Clicked '{tab_name}' toggle button")
        if self.page.locator("label[for='userapp-proxy']", has_text=f"{tab_name} enabled").is_visible():
            self.o11y_config_table_add_or_select_item(dp_name, menu_name, tab_name, "Query Service", "#add-userapp-proxy-btn")
    
        # Add or Select Logs -> User Apps -> Exporter configurations
        tab_name = "Exporter"
        if self.page.locator("label[for='userapp-exporter']", has_text=f"{tab_name} disabled").is_visible():
            self.page.locator("label[for='userapp-exporter']").click()
            print(f"Clicked '{tab_name}' toggle button")
        if self.page.locator("label[for='userapp-exporter']", has_text=f"{tab_name} enabled").is_visible():
            self.o11y_config_table_add_or_select_item(dp_name, menu_name, tab_name, "User Apps Exporter", "#add-userapp-exporter-btn")
    
        # Add or Select Logs -> Services -> Exporter configurations
        tab_name = "Exporter"
        if self.page.locator("label[for='services-exporter-toggle']", has_text=f"{tab_name} disabled").is_visible():
            self.page.locator("label[for='services-exporter-toggle']").click()
            print(f"Clicked '{tab_name}' toggle button")
        if self.page.locator("label[for='services-exporter-toggle']", has_text=f"{tab_name} enabled").is_visible():
            self.o11y_config_table_add_or_select_item(dp_name, menu_name, tab_name, "Services Exporter", "#add-services-exporter-btn")

        # Add or Select Logs -> Business Activities -> Query Service configurations
        tab_name = "Query Service"
        if self.page.locator("label[for='auditsafe-proxy']", has_text=f"{tab_name} disabled").is_visible():
            self.page.locator("label[for='auditsafe-proxy']").click()
            print(f"Clicked '{tab_name}' toggle button")
        if self.page.locator("label[for='auditsafe-proxy']", has_text=f"{tab_name} enabled").is_visible():
            self.o11y_config_table_add_or_select_item(dp_name, menu_name, tab_name, "Business Activities Query Service", "#add-auditsafe-query-service-btn")

        # Add or Select Logs -> Business Activities -> Exporter configurations
        tab_name = "Exporter"
        if self.page.locator("label[for='auditsafe-services-exporter']", has_text=f"{tab_name} disabled").is_visible():
            self.page.locator("label[for='auditsafe-services-exporter']").click()
            print(f"Clicked '{tab_name}' toggle button")
        if self.page.locator("label[for='auditsafe-services-exporter']", has_text=f"{tab_name} enabled").is_visible():
            self.o11y_config_table_add_or_select_item(dp_name, menu_name, tab_name, "Business Activities Exporter", "#add-auditsafe-services-exporter-btn")

        self.page.wait_for_timeout(500)
        self.page.locator("#go-to-metrics-server-configuration").click()
        print("Clicked 'Next' button")
        print(f"Data plane '{dp_title}' 'Configure Log Server' Step 1 is configured.")
    
        # Step 2: Configure Metrics Server
        # skip configure step 2 if TP_AUTO_DATA_PLANE_O11Y_SYSTEM_CONFIG is true
        system_toggle = self.page.locator("#metrics-toggle-system-config")
        is_system_toggle_enabled = system_toggle.is_visible() and system_toggle.get_attribute("aria-checked") == "true"
        if ENV.TP_AUTO_DATA_PLANE_O11Y_SYSTEM_CONFIG:
            if is_system_toggle_enabled:
                print("Use system config for Step 2: Configure Metrics Server")
            else:
                Util.exit_error(f"Data Plane '{dp_title}' Observability system config is not visible for Step 2.", self.page, "o11y_config_dataplane_resource.png")
        else:
            if is_system_toggle_enabled:
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
        # skip configure step 3 if TP_AUTO_DATA_PLANE_O11Y_SYSTEM_CONFIG is true
        system_toggle = self.page.locator("#traces-toggle-system-config")
        is_system_toggle_enabled = system_toggle.is_visible() and system_toggle.get_attribute("aria-checked") == "true"
        if ENV.TP_AUTO_DATA_PLANE_O11Y_SYSTEM_CONFIG:
            if is_system_toggle_enabled:
                print("Use system config for Step 3: Configure Traces Server")
            else:
                Util.exit_error(f"Data Plane '{dp_title}' Observability system config is not visible for Step 3.", self.page, "o11y_config_dataplane_resource.png")
        else:
            if is_system_toggle_enabled:
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
        self.page.wait_for_timeout(5000)

    # tab_sub_name: this parameter is just for distinction, it will not be used in the UI operation
    def o11y_config_table_add_or_select_item(self, dp_name, menu_name, tab_name, tab_sub_name, add_button_selector):
        ColorLogger.info("O11y start to add or select item...")
        name_input = Helper.get_o11y_sub_name_input(dp_name, menu_name, tab_name, tab_sub_name)
        print(f"Check if name: '{name_input}' is exist in {tab_sub_name} configurations")
        if not Util.check_dom_visibility(self.page, self.page.locator("observability-configurations table tr", has=self.page.locator("td", has_text=name_input)), 3, 6):
            self.page.locator(add_button_selector).click()
            print(f"Clicked 'Add {tab_name} configuration' button in {tab_sub_name} configurations")
            self.o11y_new_resource_fill_form(menu_name, tab_name, tab_sub_name, name_input, dp_name)
    
        print(f"Waiting for '{name_input}' display in {tab_name}")
        self.page.locator("observability-configurations table tr", has=self.page.locator("td", has_text=name_input)).locator("label").wait_for(state="visible")
        self.page.locator("observability-configurations table tr", has=self.page.locator("td", has_text=name_input)).locator("label").click()
        print(f"Selected '{name_input}' in {tab_name} configurations")
    
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
                # for PCP-16998
                elif tab_sub_name == "Business Activities Query Service" or tab_sub_name == "Business Activities Exporter":
                    log_index = f"{dp_title.lower()}-ba-log-index"
                self.page.fill("#log-index-input", log_index)
                print(f"Fill Log Index: {log_index}")

            self.o11y_fill_prometheus_or_elastic("ElasticSearch", ENV.TP_AUTO_ELASTIC_URL, ENV.TP_AUTO_ELASTIC_USER, ENV.TP_AUTO_ELASTIC_PASSWORD)
    
        self.page.locator("configuration-modal .pl-modal__footer-left button.pl-button--primary", has_text="Save").click()
        self.page.wait_for_timeout(1000)
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
    
    def dp_config_resources_storage(self, dp_name):
        resource_name = ENV.TP_AUTO_STORAGE_CLASS
        if ReportYaml.get_dataplane_info(dp_name, "storage") == "true":
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, Resources Storage '{resource_name}' is already created in DataPlane '{dp_name}'.")
            return
    
        ColorLogger.info("Config Data Plane Resources Storage...")
        self.page.locator("#resources-menu-item .menu-item-text", has_text="Resources").wait_for(state="visible")
        self.page.locator("#resources-menu-item .menu-item-text", has_text="Resources").click()
        print("Clicked 'Resources' left side menu")
        print(f"Resource Name: {resource_name}")
        self.page.wait_for_timeout(5000)
        if self.page.locator("#storage-resource-table tr td:first-child", has_text=resource_name).is_visible():
            ColorLogger.success(f"Storage '{resource_name}' is already created.")
            ReportYaml.set_dataplane_info(ENV.TP_AUTO_K8S_DP_NAME, "storage", True)
        else:
            print(f"Adding Storage '{resource_name}', and wait for 'Add Storage Class' button ...")
            self.page.locator("#add-storage-resource-btn").wait_for(state="visible")
            self.page.locator("#add-storage-resource-btn").click()
            print("Clicked 'Add Storage' button")
            # Add Storage dialog popup
            self.add_storage(resource_name)

            if Util.check_dom_visibility(self.page, self.page.locator("#storage-resource-table tr td:first-child", has_text=resource_name), 3, 6):
                ColorLogger.success(f"Add Storage '{resource_name}' successfully.")
                ReportYaml.set_dataplane_info(ENV.TP_AUTO_K8S_DP_NAME, "storage", True)

    def add_storage(self, resource_name):
        ColorLogger.info("Add Storage in dialog...")
        self.page.locator('.pl-modal__header', has_text="Add Storage").wait_for(state="visible")
        print("Dialog 'Add Storage' popup")
        self.page.fill('#resourceName-input', resource_name)
        self.page.fill('#description-input', resource_name)
        self.page.fill('#storageClassName-input', resource_name)
        print(f"Filled Storage Class, {resource_name}")
        Util.click_button_until_enabled(self.page, self.page.locator("#save-storage-configuration"))
        print("Clicked 'Add' button in 'Add Storage' dialog")

    def dp_config_resources_ingress(self, dp_name, ingress_controller, resource_name, ingress_class_name, fqdn):
        if ReportYaml.get_dataplane_info(dp_name, resource_name) == "true":
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, ingress '{resource_name}' is already created in DataPlane '{dp_name}'.")
            return
        ColorLogger.info("Config Data Plane Resources Ingress...")
        self.page.locator("#resources-menu-item .menu-item-text", has_text="Resources").wait_for(state="visible")
        self.page.locator("#resources-menu-item .menu-item-text", has_text="Resources").click()
        print("Clicked 'Resources' left side menu")
        self.page.wait_for_timeout(5000)
        self.page.locator("#toggle-ingress-expansion svg use").wait_for(state="visible")
        expected_icon = 'pl-icon-caret-right'
        if expected_icon in (self.page.query_selector("#toggle-ingress-expansion svg use") or {}).get_attribute("xlink:href"):
            self.page.locator("#toggle-ingress-expansion").click()
            print("Clicked expand Icon, and wait for Ingress Controller table")
            self.page.wait_for_timeout(3000)
    
        print(f"Check if Ingress Controller '{resource_name}' is exist...")
        if self.page.locator("#ingress-resource-table tr td:first-child", has_text=resource_name).is_visible():
            ColorLogger.success(f"Ingress Controller '{resource_name}' is already created.")
            ReportYaml.set_dataplane_info(ENV.TP_AUTO_K8S_DP_NAME, resource_name, True)
        else:
            print(f"Ingress Controller table do not have '{resource_name}'")
            print(f"Adding Ingress Controller '{resource_name}', and wait for 'Add Ingress Controller' button ...")
            self.page.locator(".ingress .add-resource-btn button").wait_for(state="visible")
            self.page.locator(".ingress .add-resource-btn button").click()
            print("Clicked 'Add Ingress Controller' button")
    
            # Add Ingress Controller dialog popup
            self.add_ingress_controller(ingress_controller, resource_name, ingress_class_name, fqdn)
            self.page.wait_for_timeout(1000)
            if self.page.locator(".pl-notification--error").is_visible():
                error_content = self.page.locator(".pl-notification__message").text_content()
                Util.warning_screenshot(f"Config Data Plane Resources Ingress Error: {error_content}", self.page, "dp_config_resources_ingress.png")
                self.page.locator("#cancel-ingress-configuration").click()
                print("Clicked 'Cancel' button")
                return
            if Util.check_dom_visibility(self.page, self.page.locator("#ingress-resource-table tr td:first-child", has_text=resource_name), 3, 6):
                ColorLogger.success(f"Add Ingress Controller '{resource_name}' successfully.")
                ReportYaml.set_dataplane_info(ENV.TP_AUTO_K8S_DP_NAME, resource_name, True)
            else:
                Util.warning_screenshot(f"Config Data Plane Resources '{resource_name}' Error", self.page, "dp_config_resources_ingress.png")

    def add_ingress_controller(self, ingress_controller, resource_name, ingress_class_name, fqdn):
        ColorLogger.info("Add Ingress Controller in dialog...")
        self.page.locator('.pl-modal__header', has_text="Add Ingress Controller").wait_for(state="visible")
        print("Dialog 'Add Ingress Controller' popup")
        self.page.locator('#ingress-controller-dropdown input').click()
        print("Clicked 'Ingress Controller' dropdown")
        self.page.locator('#ingress-controller-dropdown .pl-select__dropdown li', has_text=ingress_controller).wait_for(state="visible")
        print(f"Waiting for '{ingress_controller}' in Ingress Controller dropdown")
        self.page.locator('#ingress-controller-dropdown .pl-select__dropdown li', has_text=ingress_controller).click()
        print(f"Selected '{ingress_controller}' in Ingress Controller dropdown")
        self.page.fill('#resourceName-input', resource_name)
        print(f"Filled Resource Name: {resource_name}")
        self.page.fill('#ingressClassName-input', ingress_class_name)
        print(f"Filled Ingress Class Name: {ingress_class_name}")
        self.page.fill('#fqdn-input', fqdn)
        print(f"Filled FQDN: {fqdn}")

        # for Ingress Key and Value
        # if ENV.TP_AUTO_INGRESS_CONTROLLER_KEYS != "" and ENV.TP_AUTO_INGRESS_CONTROLLER_VALUES != "":
        #     keys = ENV.TP_AUTO_INGRESS_CONTROLLER_KEYS.split(" ")
        #     values = ENV.TP_AUTO_INGRESS_CONTROLLER_VALUES.split(" ")
        #     for i in range(len(keys)):
        #         key = keys[i].strip()
        #         value = values[i].strip()
        #         self.page.fill("#key-input", key)
        #         self.page.fill("#value-textarea", value)
        #         print(f"Filled Ingress Key: {key}, Value: {value}")
        #         self.page.wait_for_timeout(500)
        #         self.page.locator(".olly-header__inputs button", has_text="Save").click()
        #         print("Clicked 'Save' button")
        #         self.page.wait_for_timeout(500)

        Util.click_button_until_enabled(self.page, self.page.locator("#save-ingress-configuration"))
        print("Clicked 'Add' button in 'Add Ingress Controller' dialog")

    def dp_config_activation(self, dp_name, use_global = False):
        activation_menu_item = self.page.locator(".menu-item-list .menu-item-text", has_text="Activation")
        if not Util.check_dom_visibility(self.page, activation_menu_item, 3, 6):
            ColorLogger.warning("Activation menu item is not visible, skip config Activation Service.")
            return
        activation_menu_item.click()
        print("Clicked 'Activation' left side menu")

        if use_global:
            # DP level: read Global report to determine link method
            global_activation = ReportYaml.get_dataplane_info(ENV.TP_AUTO_DP_NAME_GLOBAL, "activation")
            if global_activation == "file":
                print("Global activation is file, linking DP to Global license file...")
                self.dp_config_activation_file(dp_name, use_global, "")
            elif global_activation == "server":
                print("Global activation is server, linking DP to Global activation URL...")
                self.dp_config_activation_url(dp_name, use_global)
            else:
                ColorLogger.warning("No Global activation configured, skipping DP activation link.")
        else:
            # Global level: check file existence to determine upload vs URL
            activation_file_path = Helper.get_file_fullpath_in_upload_folder(ENV.TP_ACTIVATION_FILENAME)
            if os.path.isfile(activation_file_path):
                print("activation file is found, start to upload...")
                self.dp_config_activation_file(dp_name, use_global, activation_file_path)
            else:
                print("activation file is not found, try to config Activation url...")
                self.dp_config_activation_url(dp_name, use_global)

    def dp_config_activation_url(self, dp_name, use_global = False):
        activation_url = ENV.TP_ACTIVATION_URL
        # If not using global activation URL and activation URL is empty, skip config as there is no URL to configure
        if not activation_url and use_global == False:
            ColorLogger.warning("TP_ACTIVATION_URL is not set, skip config Activation url.")
            return

        if activation_url:
            ColorLogger.info(f"Config Data Plane '{dp_name}' Activation Url: {activation_url}")
        else:
            ColorLogger.info(f"Current Activation Url is empty, will link Data Plane '{dp_name}' to use Global Activation Url")

        if activation_url and Util.check_dom_visibility(self.page, self.page.locator(".activation-server-url", has_text=activation_url), 3, 6):
            ColorLogger.success(f"Activation URL '{activation_url}' is already exist for Data Plane '{dp_name}'.")
            if use_global:
                ReportYaml.set_dataplane_info(dp_name, "activation", "Global")
            else:
                ReportYaml.set_dataplane_info(dp_name, "activation", "server")
            return

        if use_global:
            # for dp level
            self.page.locator(".dp-activation").wait_for(state="visible")
            print(f"Checking if dataplane {dp_name} is able to use global activation url...")

            # for 1.13+ version, need select 'TIBCO Activation Service' option
            if not self.select_tibco_activation_service():
                ColorLogger.warning("TIBCO Activation Service option is disabled, skip config Activation.")
                return

            if self.page.locator(".activation-server-url").is_visible():
                current_activation_url = self.page.locator(".activation-server-url").inner_text()
                ColorLogger.success(f"ENV.TP_ACTIVATION_URL is empty, but Activation URL '{current_activation_url}' is already exist for Data Plane '{dp_name}'.")
                ReportYaml.set_dataplane_info(dp_name, "activation", "Global")
                return
            # if "Use Global Activation URL" button is visible but not enabled, skip config
            if self.page.locator("#use-global-activation-on-dp").is_visible() and "pcp-disabled" in (self.page.locator("#use-global-activation-on-dp").get_attribute("class") or ""):
                ColorLogger.warning("'Use Global Activation URL' button is not enabled, skip config Activation url.")
                return

            print("Waiting for 'Use Global Activation URL' button is visible...")
            self.page.locator("#use-global-activation-on-dp").wait_for(state="visible")
            self.page.locator("#use-global-activation-on-dp").click()
            print("Clicked 'Use Global Activation URL' button")

            print("Waiting for 'Use Global Activation URL' modal dialog is visible...")
            self.page.locator("confirmation-modal .pl-modal__heading", has_text="Use Global Activation URL").wait_for(state="visible")
            self.page.locator("#confirm-button", has_text="Link").click()
            print("Clicked 'Link' button in 'Use Global Activation URL' modal dialog")
        else:
            # for global level
            # for 1.13+ version, need select 'TIBCO Activation Service' option
            if not self.select_tibco_activation_service():
                ColorLogger.warning("TIBCO Activation Service option is disabled, skip config Activation.")
                return

            print("Waiting for 'Add Global Activation URL' button is visible...")
            self.page.locator("#add-global-activation-server").wait_for(state="visible")
            self.page.locator("#add-global-activation-server").click()
            print("Clicked 'Add Global Activation URL' button")

            print("Waiting for 'Add New Activation URL' modal dialog is visible...")
            self.page.locator("activation-url-modal .pl-modal__heading", has_text="Add New Activation URL").wait_for(state="visible")
            self.page.fill("activation-url-modal #activation-url-text-input", activation_url)
            self.page.locator("activation-url-modal #add-activation-url-btn").click()
            print(f"Filled Activation URL: {activation_url} and clicked 'Add' button")

        if Util.check_dom_visibility(self.page, self.page.locator(".activation-server-url", has_text=activation_url), 3, 6):
            ColorLogger.success(f"Add Activation URL '{activation_url}' successfully.")
            if use_global:
                ReportYaml.set_dataplane_info(dp_name, "activation", "Global")
            else:
                ReportYaml.set_dataplane_info(dp_name, "activation", "server")
        else:
            ColorLogger.warning(f"Add Activation URL '{activation_url}' failed.")

    def select_in_product_activation(self):
        # global level and dp level are using different label "for" value, so just check by label text
        label_dom = self.page.locator(".pl-form-field--radio-button:has(input:not([disabled]))").locator("label", has_text="In-Product Activation (Recommended)")
        if label_dom.is_visible():
            label_dom.click()
            print("Selected 'In-Product Activation (Recommended)' option")
            return True
        else:
            return False


    def select_tibco_activation_service(self):
        # global level and dp level are using different label "for" value, so just check by label text
        label_dom = self.page.locator(".pl-form-field--radio-button:has(input:not([disabled]))").locator("label", has_text="TIBCO Activation Service")
        if label_dom.is_visible():
            label_dom.click()
            print("Selected 'TIBCO Activation Service' option")
            return True
        else:
            return False

    def dp_config_activation_file(self, dp_name, use_global, activation_file_path):
        # ColorLogger.info(f"Upload Activation File '{ENV.TP_ACTIVATION_FILENAME}' for Global Data Plane...")
        if Util.check_dom_visibility(self.page, self.page.locator("span", has_text=re.compile(r"Currently linked to the|View License", re.IGNORECASE)), 2, 4):
            ColorLogger.success(f"Activation file is already exist for Data Plane '{dp_name}'.")
            if use_global:
                ReportYaml.set_dataplane_info(dp_name, "activation", "Global")
            else:
                ReportYaml.set_dataplane_info(dp_name, "activation", "file")
            return

        if use_global:
            # for dp level
            if not self.select_in_product_activation():
                ColorLogger.warning("In-Product Activation option is disabled, skip config Activation.")
                return
            if self.page.locator(".dp-activation-content__license-file-item-details").is_visible():
                ColorLogger.success(f"In-Product Activation is already exist for Data Plane '{dp_name}'.")
                ReportYaml.set_dataplane_info(dp_name, "activation", "Global")
                return
            # if "Use Global License File" button is visible but not enabled, skip config
            if self.page.locator("#use-global-license-file-on-dp").is_visible() and "pcp-disabled" in (self.page.locator("#use-global-license-file-on-dp").get_attribute("class") or ""):
                ColorLogger.warning("'Use Global License File' button is not enabled, skip config Activation url.")
                return

            ColorLogger.info(f"Link to Activation File '{ENV.TP_ACTIVATION_FILENAME}' for Data Plane...")
            self.page.locator('#use-global-license-file-on-dp').click()
            print("Clicked 'Use Global License File' option")

            print("Waiting for 'Use Global License File' modal dialog is visible...")
            self.page.locator("confirmation-modal .pl-modal__heading", has_text="Use Global License File").wait_for(state="visible")
            self.page.locator("#confirm-button", has_text="Link").click()
            print("Clicked 'Link' button in 'Use Global License File' modal dialog")
        else:
            # for global level
            if not self.select_in_product_activation():
                ColorLogger.warning("In-Product Activation option is disabled, skip config Activation.")
                return
            ColorLogger.info(f"Upload Activation File '{ENV.TP_ACTIVATION_FILENAME}' for Global Data Plane...")
            if self.page.locator('#add-global-license-file').is_visible():
                self.page.locator('#add-global-license-file').click()
                print("Clicked 'Upload' option")

            if self.page.locator('.license-file-drop-zone').is_visible():
                print("Popping up 'Add New License File' dialog")

                self.page.locator('input[type="file"]').evaluate("(input) => input.style.display = 'block'")
                self.page.locator('input[type="file"]').set_input_files(activation_file_path)
                print(f"Selected file: {activation_file_path}")

            if Util.check_dom_visibility(self.page, self.page.locator("#add-activation-url-btn:not([disabled])"), 2, 4):
                self.page.locator('#add-activation-url-btn').click()
                print("Clicked 'Add' button in 'Add New License File' dialog")

        if Util.check_dom_visibility(self.page, self.page.locator("span", has_text=re.compile(r"Currently linked to the|View License", re.IGNORECASE)), 2, 4):
            ColorLogger.success(f"Upload Activation File '{ENV.TP_ACTIVATION_FILENAME}' successfully for Data Plane '{dp_name}'.")
            if use_global:
                ReportYaml.set_dataplane_info(dp_name, "activation", "Global")
            else:
                ReportYaml.set_dataplane_info(dp_name, "activation", "file")
        else:
            ColorLogger.warning(f"Add Activation file '{activation_file_path}' failed.")
