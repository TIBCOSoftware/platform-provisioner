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
import os
import re

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from utils.color_logger import ColorLogger
from utils.util import Util
from utils.helper import Helper, O11Y_LOG_INDEX_PREFIX
from utils.env import ENV
from utils.report import ReportYaml
from page_object.po_dataplane import PageObjectDataPlane

# Text scraped out of an activation dialog is entitlement data going into a warning
# message, so it is capped and flattened onto one line before it is reported.
ACTIVATION_DIALOG_TEXT_LIMIT = 300
ACTIVATION_DIALOG_TEXT_LINES = 2
# Only wording that asserts an expiry counts as one. A valid license also renders an
# 'Expiration Date' line, a section heading can read 'Expired Licenses', and a
# reassurance can read 'has not expired' - reporting any of those declares a perfectly
# good license dead and sends the reader after the wrong problem.
ACTIVATION_EXPIRED_TEXT = re.compile(r"\b(?:has|have|is|are|was|were)\s+expired\b|\bexpired\s+on\b", re.IGNORECASE)
ACTIVATION_NOT_EXPIRED_TEXT = re.compile(r"\b(?:not|never|no)\b[^.]*?\bexpired\b", re.IGNORECASE)
# Explicit short timeout for the dialog reads and the dialog-opening clicks that would
# otherwise run on Playwright's 30s actionability default while the real failure waits to
# be reported. The controls behind them are polled visible first, so a click that cannot
# land inside this budget is blocked by something, not slow.
ACTIVATION_DIALOG_READ_TIMEOUT = 2000
ACTIVATION_DIALOG_CLICK_TIMEOUT = 5000
# The submit clicks ('Link' in a confirmation dialog, 'Add' in the license dialog) are the
# action the whole step exists to perform, so they keep the full 30s budget: cutting it
# turns the slow render this step is being fixed for into a hard failure of the run.
ACTIVATION_DIALOG_SUBMIT_TIMEOUT = 30000
# The 'the license is linked' text, shared by the entry check, the final check and the
# cleanup re-check so all three judge success by exactly the same thing.
ACTIVATION_LINKED_TEXT = re.compile(r"Currently linked to the|View License", re.IGNORECASE)

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
        # WHETHER to configure o11y at all, in the same place as the sibling
        # o11y_config_dataplane_resource that this method replaced for data planes
        # (PCP-23553). Without it, driving case/k8s_config_dp_o11y.py directly with the
        # flag off used to be a no-op and would silently start performing the switch.
        if not ENV.TP_AUTO_IS_CONFIG_O11Y:
            ColorLogger.warning("TP_AUTO_IS_CONFIG_O11Y is false, skip switch to Global Observability Resource.")
            return
        ColorLogger.info(f"Switch dataplane {dp_name} configuration to Global...")
        self.goto_dataplane_o11y_config(dp_name)
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
        self._o11y_enable_toggle_and_add("label[for='userapp-proxy']", "Query Service", "#add-userapp-proxy-btn", dp_name, menu_name, "Query Service")

        # Add or Select Logs -> User Apps -> Exporter configurations
        self._o11y_enable_toggle_and_add("label[for='userapp-exporter']", "Exporter", "#add-userapp-exporter-btn", dp_name, menu_name, "User Apps Exporter")

        # Add or Select Logs -> Services -> Exporter configurations
        self._o11y_enable_toggle_and_add("label[for='services-exporter-toggle']", "Exporter", "#add-services-exporter-btn", dp_name, menu_name, "Services Exporter")

        # Add or Select Logs -> Business Activities -> Query Service configurations
        self._o11y_enable_toggle_and_add("label[for='auditsafe-proxy']", "Query Service", "#add-auditsafe-query-service-btn", dp_name, menu_name, "Business Activities Query Service")

        # Add or Select Logs -> Business Activities -> Exporter configurations
        self._o11y_enable_toggle_and_add("label[for='auditsafe-services-exporter']", "Exporter", "#add-auditsafe-services-exporter-btn", dp_name, menu_name, "Business Activities Exporter")

        self.page.wait_for_timeout(500)
        self.page.locator("#go-to-metrics-server-configuration").click()
        print("Clicked 'Next' button")
        print(f"Data plane '{dp_title}' 'Configure Log Server' Step 1 is configured.")
    
        # Step 2: Configure Metrics Server
        # skip configure step 2 if TP_AUTO_DATA_PLANE_O11Y_SYSTEM_CONFIG is true AND the
        # system-config toggle is present (DP-level resource with an inheritable config).
        # PCP-22537: poll for the Metrics step to render (it can take >30s under peak
        # install load), using the step's Next button as the anchor. NOTE
        # "#go-to-traces-configuration" IS the Metrics step's own Next button (it lives in
        # the metrics-container footer; its id names its destination — the Traces step).
        # PCP-22621: the system-config toggle is *ngIf-hidden when creating the Global
        # (system) resource — there is nothing to inherit — so an absent toggle must take
        # the manual-configure branch instead of hard-failing.
        toggle_present, is_system_toggle_enabled = self._o11y_wait_toggle_system_config(
            "metrics-toggle-system-config", "#go-to-traces-configuration", "Metrics", dp_title)
        if ENV.TP_AUTO_DATA_PLANE_O11Y_SYSTEM_CONFIG and toggle_present:
            if is_system_toggle_enabled:
                print("Use system config for Step 2: Configure Metrics Server")
            else:
                Util.exit_error(f"Data Plane '{dp_title}' Observability system config toggle is present but not enabled for Step 2.", self.page, "o11y_config_dataplane_resource.png")
        else:
            # Manual-configure branch: env flag off, OR the system-config toggle is absent
            # (Global resource creation — nothing to inherit, PCP-22621).
            if not toggle_present:
                # include dp_title so a manual branch taken on an unexpected (non-Global)
                # resource is greppable in the automation logs (review PCP-22621)
                print(f"Data Plane '{dp_title}' Metrics System Config toggle is not present (no inheritable system config) — configuring Metrics manually")
            elif is_system_toggle_enabled:
                print("Metrics System Config is enabled")
                self.page.locator("label[for='metrics-toggle-system-config']").click()
                print("Clicked 'Metrics System Config' toggle button")

            # Add or Select Metrics -> Query Service configurations
            menu_name = "Metrics"
            tab_name = "Query Service"
            self.o11y_config_table_add_or_select_item(dp_name, menu_name, tab_name, "", "#add-metrics-proxy-btn")

            # Add or Select Metrics -> Exporter configurations
            self._o11y_enable_toggle_and_add("label[for='metrics-exporter-toggle']", "Exporter", "#add-metrics-exporter-btn", dp_name, menu_name, "")
        self.page.locator("#go-to-traces-configuration").click()
        print("Clicked 'Next' button")
        print(f"Data plane '{dp_title}' 'Configure Metrics Server' Step 2 is configured.")
    
        # Step 3: Configure Traces Server
        # skip configure step 3 if TP_AUTO_DATA_PLANE_O11Y_SYSTEM_CONFIG is true AND the
        # system-config toggle is present (DP-level resource with an inheritable config).
        # PCP-22537: same load-dependent render race as the Metrics step — poll, using the
        # step's Save button as the anchor.
        # PCP-22621: an absent toggle (Global resource creation) takes the manual-configure
        # branch instead of hard-failing.
        toggle_present, is_system_toggle_enabled = self._o11y_wait_toggle_system_config(
            "traces-toggle-system-config", "#save-observability", "Traces", dp_title)
        if ENV.TP_AUTO_DATA_PLANE_O11Y_SYSTEM_CONFIG and toggle_present:
            if is_system_toggle_enabled:
                print("Use system config for Step 3: Configure Traces Server")
            else:
                Util.exit_error(f"Data Plane '{dp_title}' Observability system config toggle is present but not enabled for Step 3.", self.page, "o11y_config_dataplane_resource.png")
        else:
            # Manual-configure branch: env flag off, OR the system-config toggle is absent
            # (Global resource creation — nothing to inherit, PCP-22621).
            if not toggle_present:
                # include dp_title so a manual branch taken on an unexpected (non-Global)
                # resource is greppable in the automation logs (review PCP-22621)
                print(f"Data Plane '{dp_title}' Traces System Config toggle is not present (no inheritable system config) — configuring Traces manually")
            elif is_system_toggle_enabled:
                print("Traces System Config is enabled")
                self.page.locator("label[for='traces-toggle-system-config']").click()
                print("Clicked 'Traces System Config' toggle button")

            # Add or Select Traces -> Query Service configurations
            menu_name = "Traces"
            self._o11y_enable_toggle_and_add("label[for='traces-proxy']", "Query Service", "#add-traces-proxy-btn", dp_name, menu_name, "")

            # Add or Select Traces -> Exporter configurations
            self._o11y_enable_toggle_and_add("label[for='traces-exporter']", "Exporter", "#add-traces-exporter-btn", dp_name, menu_name, "")
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

    def _o11y_wait_toggle_system_config(self, toggle_id, step_anchor_selector, step_label, dp_title):
        """Wait for an o11y wizard step to render, then report whether its
        (conditionally rendered) system-config toggle is present and enabled.

        Returns a (toggle_present, toggle_enabled) tuple.

        PCP-22537: the Metrics/Traces step can take well over 30s to render when the CP
        web UI is under peak install load (cli-full-automation runs concurrent helm
        installs + create-dp + app deploys). The whole wizard form is
        `*ngIf="observabilityData"`, so nothing in the step exists until that backend
        data resolves. Poll a STEP-LEVEL anchor — the step's Next/Save button, which is
        always present once the step renders regardless of the toggle — with a long,
        logged budget (Util.check_dom_visibility) per CLAUDE.md rule #5, instead of the
        old single-shot 30s wait_for that timed out under load.

        PCP-22621: the system-config toggle is `*ngIf="isMetricsTabHasSystemConfig()"`
        (resp. traces) — it renders only when every metrics/traces service type has an
        inheritable `is_system_config` item. When creating the Global (= system)
        resource itself there is nothing to inherit, so the toggle is hidden BY DESIGN.
        The old code polled for the toggle directly and hard-failed (exit_error) on the
        Global path. Now the step anchor renders in BOTH cases, and an absent toggle is
        a valid state that the caller handles by taking the manual-configure branch.

        Why the toggle probe needs no poll budget of its own (verified against
        observability-add.component.ts, 2026-07): the toggle's `*ngIf` predicate
        isMetricsTabHasSystemConfig() = metricsServiceTypes.every(t =>
        observabilityData[t]?.some(i => i.is_system_config)) is a PURE SYNCHRONOUS read
        of observabilityData — it awaits nothing. observabilityData is loaded in a single
        loadObservabilityData('all') batch that populates every service type at once, and
        the Logs step's Next button is [disabled]="!validateLogsDetails()", so the wizard
        cannot reach the Metrics/Traces step (make its anchor visible) until that batch
        has loaded. Therefore, once the step anchor is visible, observabilityData is fully
        populated and the predicate is at its final value — the toggle's presence is
        deterministic at that point, with no anchor-vs-toggle render race. The real
        load-induced delay (PCP-22537) is the time for that batch to resolve, and it is
        fully covered by the anchor's 120s poll above.
        """
        # 1. Wait for the step to render. The anchor (Next/Save button) is present
        #    whether or not the *ngIf toggle exists. Fast path: skip check_dom_visibility's
        #    up-front sleep if it already rendered; otherwise poll (every 3s up to 120s)
        #    to cover the >30s-under-load render window.
        if not self.page.locator(step_anchor_selector).is_visible():
            if not Util.check_dom_visibility(self.page, self.page.locator(step_anchor_selector), 3, 120):
                Util.exit_error(f"Data Plane '{dp_title}' Observability {step_label} step did not render "
                                f"(anchor '{step_anchor_selector}' not visible after waiting).", self.page, "o11y_config_dataplane_resource.png")
        # 2. Step rendered — probe the conditionally-rendered system-config toggle.
        #    re-query each locator fresh (never cache) per CLAUDE.md rule #4.
        toggle_present = self.page.locator(f"label[for='{toggle_id}']").is_visible()
        toggle_enabled = (
            toggle_present
            and self.page.locator(f"#{toggle_id}").is_visible()
            and self.page.locator(f"#{toggle_id}").get_attribute("aria-checked") == "true"
        )
        return toggle_present, toggle_enabled

    def _o11y_enable_toggle_and_add(self, toggle_selector, tab_name, add_button_selector, dp_name, menu_name, tab_sub_name):
        """Enable an o11y config section toggle (if disabled), auto-wait for the
        'enabled' state to actually render, then unconditionally add/select the item.

        Replaces the previous two-independent-`if` pattern whose second is_visible()
        guard raced the toggle's label re-render and silently skipped the add
        (PCP-22010/PCP-21982: Services Exporter never created -> Next disabled ->
        wizard timeout). The key change is auto-waiting for the 'enabled' label
        (wait_for) in place of that racy is_visible() guard, then adding
        unconditionally.
        """
        # re-query the locator on each use (never cache it) per CLAUDE.md rule #4
        self.page.locator(toggle_selector).wait_for(state="visible")
        # enable the section if it is currently disabled
        if self.page.locator(toggle_selector, has_text=f"{tab_name} disabled").is_visible():
            self.page.locator(toggle_selector).click()
            print(f"Clicked '{tab_name}' toggle button")
        # auto-wait for the section to actually reach the 'enabled' state (fixes the race)
        self.page.locator(toggle_selector, has_text=f"{tab_name} enabled").wait_for(state="visible")
        print(f"{menu_name} '{tab_name} enabled' toggle button is visible.")
        # unconditionally add/select — a real failure now surfaces instead of being silently skipped
        self.o11y_config_table_add_or_select_item(dp_name, menu_name, tab_name, tab_sub_name, add_button_selector)

    # tab_sub_name: this parameter is just for distinction, it will not be used in the UI operation
    def o11y_config_table_add_or_select_item(self, dp_name, menu_name, tab_name, tab_sub_name, add_button_selector):
        ColorLogger.info("O11y start to add or select item...")
        name_input = Helper.get_o11y_sub_name_input(dp_name, menu_name, tab_name, tab_sub_name)
        print(f"Check if name: '{name_input}' is exist in {tab_sub_name} configurations")
        if not Util.check_dom_visibility(self.page, self.page.locator("observability-configurations table tr", has=self.page.locator("td", has_text=name_input)), 3, 6):
            # PCP-22537: the Add button transitions disabled -> enabled with a delay
            # (e.g. right after toggling off "Use CP hosted Prometheus"). Wait for it to
            # be enabled before clicking, instead of relying on a fixed pre-wait.
            Util.click_button_until_enabled(self.page, self.page.locator(add_button_selector))
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
                # prepend the fixed prefix to every log index (shared constant; CLI path in api_object/resources.py uses the same)
                log_index = f"{O11Y_LOG_INDEX_PREFIX}{log_index}"
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

        # Wait for Storage section to render; may take extra time after DP just created
        if not Util.check_dom_visibility(self.page, self.page.locator("#add-storage-resource-btn, #storage-resource-table").first, 5, 60):
            ColorLogger.warning("Storage resource section not loaded after waiting — DP may not be fully ready, skipping.")
            return

        if self.page.locator("#storage-resource-table tr td:first-child", has_text=resource_name).is_visible():
            ColorLogger.success(f"Storage '{resource_name}' is already created.")
            ReportYaml.set_dataplane_info(dp_name, "storage", True)
        else:
            print(f"Adding Storage '{resource_name}', and wait for 'Add Storage Class' button ...")
            self.page.locator("#add-storage-resource-btn").wait_for(state="visible")
            self.page.locator("#add-storage-resource-btn").click()
            print("Clicked 'Add Storage' button")
            # Add Storage dialog popup
            self.add_storage(resource_name)

            if Util.check_dom_visibility(self.page, self.page.locator("#storage-resource-table tr td:first-child", has_text=resource_name), 3, 6):
                ColorLogger.success(f"Add Storage '{resource_name}' successfully.")
                ReportYaml.set_dataplane_info(dp_name, "storage", True)

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

    def _close_modal(self):
        # The Ingress/Route dialog Cancel button is tried first, unconditionally and with
        # the full click budget it had here before, then the shared close controls
        # (activation dialogs, footer Cancel, legacy secondary button, Escape) from
        # PageObjectGlobal.close_open_modal().
        return self.close_open_modal("#cancel-ingress-configuration, #cancel-route-resource-configuration")

    def _detect_ingress_toggle(self):
        """Detect which ingress/route toggle is present on the Resources page.
        CP 1.18+ renamed 'Ingress Controller' to 'Route Resource'.
        Returns 'ingress', 'route', or None if neither is found.
        """
        if self.page.locator("#toggle-ingress-expansion").is_visible():
            return "ingress"
        if self.page.locator("#toggle-route-resource-expansion").is_visible():
            return "route"
        return None

    def dp_config_resources_ingress(self, dp_name, ingress_controller, resource_name, ingress_class_name, fqdn):
        if ReportYaml.get_dataplane_info(dp_name, resource_name) == "true":
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, ingress '{resource_name}' is already created in DataPlane '{dp_name}'.")
            return
        ColorLogger.info("Config Data Plane Resources Ingress...")
        self.page.locator("#resources-menu-item .menu-item-text", has_text="Resources").wait_for(state="visible")
        self.page.locator("#resources-menu-item .menu-item-text", has_text="Resources").click()
        print("Clicked 'Resources' left side menu")
        self.page.wait_for_timeout(5000)

        # CP 1.18+ renamed "Ingress Controller" to "Route Resource".
        # Try both toggle selectors; whichever appears first wins.
        ingress_toggle_sel = "#toggle-ingress-expansion, #toggle-route-resource-expansion"
        if not Util.check_dom_visibility(self.page, self.page.locator(ingress_toggle_sel).first, 5, 60):
            ColorLogger.warning("Ingress/Route resource section not loaded after waiting — DP may not be fully ready, skipping.")
            return

        section_type = self._detect_ingress_toggle()
        if section_type == "ingress":
            toggle_id = "#toggle-ingress-expansion"
            table_selector = "#ingress-resource-table tr td:first-child"
            add_btn_selector = ".ingress .add-resource-btn button"
        elif section_type == "route":
            toggle_id = "#toggle-route-resource-expansion"
            table_selector = ".route-resource table tr td:first-child"
            add_btn_selector = ".route-resource .add-resource-btn button"
        else:
            Util.exit_error("Neither ingress nor route is visible — unknown CP version or page state.", self.page, "dp_config_resources_ingress.png")
            return

        # Expand the section — check if table content is visible (not just the add button)
        if not self.page.locator(table_selector).first.is_visible():
            self.page.locator(toggle_id).click()
            print(f"Clicked toggle {toggle_id} to expand section")
            self.page.wait_for_timeout(3000)

        print(f"Check if Ingress/Route '{resource_name}' exists...")
        if self.page.locator(table_selector, has_text=resource_name).is_visible():
            ColorLogger.success(f"Ingress/Route '{resource_name}' is already created.")
            ReportYaml.set_dataplane_info(dp_name, resource_name, True)
        else:
            print(f"Adding Ingress/Route '{resource_name}'...")
            self.page.locator(add_btn_selector).wait_for(state="visible")
            self.page.locator(add_btn_selector).click()
            print("Clicked 'Add' button")

            self.add_ingress_controller(ingress_controller, resource_name, ingress_class_name, fqdn, section_type)
            self.page.wait_for_timeout(1000)
            if self.page.locator(".pl-notification--error").is_visible():
                error_content = self.page.locator(".pl-notification__message").text_content()
                already_exists = "already in use" in (error_content or "")
                Util.warning_screenshot(f"Config Data Plane Resources Ingress Error: {error_content}", self.page, "dp_config_resources_ingress.png")
                self._close_modal()
                if already_exists:
                    ColorLogger.success(f"Ingress/Route '{resource_name}' already exists, marking as done.")
                    ReportYaml.set_dataplane_info(dp_name, resource_name, True)
                return
            if Util.check_dom_visibility(self.page, self.page.locator(table_selector, has_text=resource_name), 3, 6):
                ColorLogger.success(f"Add Ingress/Route '{resource_name}' successfully.")
                ReportYaml.set_dataplane_info(dp_name, resource_name, True)
            else:
                Util.warning_screenshot(f"Config Data Plane Resources '{resource_name}' Error", self.page, "dp_config_resources_ingress.png")

    def add_ingress_controller(self, ingress_controller, resource_name, ingress_class_name, fqdn, section_type="ingress"):
        ColorLogger.info("Add Ingress/Route Resource in dialog...")

        if section_type == "route":
            # CP 1.18+ "Add Route Resource" dialog
            self.page.locator('.pl-modal__header', has_text="Add Route Resource").wait_for(state="visible")
            print("Dialog 'Add Route Resource' popup")
            # Select "Ingress" radio button (default may already be selected)
            ingress_radio = self.page.locator("#ingress-radio-button")
            if ingress_radio.is_visible() and not ingress_radio.is_checked():
                self.page.locator("label[for='ingress-radio-button']").click()
                print("Selected 'Ingress' radio button")
            # Select ingress controller type (e.g. Traefik) from dropdown
            dropdown_selector = '#ingressController-dropdown input, #ingress-controller-dropdown input'
            option_selector = '#ingressController-dropdown .pl-select__dropdown li, #ingress-controller-dropdown .pl-select__dropdown li'
            self.page.locator(dropdown_selector).first.click()
            print("Clicked 'Ingress Controller' dropdown")
            self.page.locator(option_selector, has_text=ingress_controller).first.wait_for(state="visible")
            print(f"Waiting for '{ingress_controller}' in Ingress Controller dropdown")
            self.page.locator(option_selector, has_text=ingress_controller).first.click()
            print(f"Selected '{ingress_controller}' in Ingress Controller dropdown")
            self.page.fill('#resourceName-input', resource_name)
            print(f"Filled Resource Name: {resource_name}")
            # CP 1.18 uses #ingressClass-input instead of #ingressClassName-input
            self.page.fill('#ingressClass-input', ingress_class_name)
            print(f"Filled Ingress Class Name: {ingress_class_name}")
            self.page.fill('#fqdn-input', fqdn)
            print(f"Filled FQDN: {fqdn}")
            # Save button — try both old and new IDs
            save_btn = self.page.locator("#save-ingress-configuration, #save-route-resource-configuration, .pl-modal button.pl-button--primary", has_text=re.compile(r"Add|Save")).first
            Util.click_button_until_enabled(self.page, save_btn)
            print("Clicked 'Add' button in 'Add Route Resource' dialog")
        else:
            # Legacy "Add Ingress Controller" dialog
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
            Util.click_button_until_enabled(self.page, self.page.locator("#save-ingress-configuration"))
            print("Clicked 'Add' button in 'Add Ingress Controller' dialog")

    def dp_config_resources_gateway(self, dp_name, gateway_controller, resource_name, gateway_name, gateway_namespace, fqdn, gateway_section_name=""):
        """Add a Gateway API controller resource to the DataPlane.

        CP 1.17 and earlier: separate `.gateway-api` section with its own Add button
        and a dedicated "Add Gateway API details" modal.

        CP 1.18+: Ingress and Gateway are unified into a single "Route Resource" section.
        Adding a gateway means opening the "Add Route Resource" modal, switching the
        Ingress/Gateway radio to "Gateway API Controller", and filling renamed fields.
        """
        if ReportYaml.get_dataplane_info(dp_name, resource_name) == "true":
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, gateway '{resource_name}' is already created in DataPlane '{dp_name}'.")
            return
        ColorLogger.info("Config Data Plane Resources GatewayAPI...")
        self.page.locator("#resources-menu-item .menu-item-text", has_text="Resources").wait_for(state="visible")
        self.page.locator("#resources-menu-item .menu-item-text", has_text="Resources").click()
        print("Clicked 'Resources' left side menu")
        self.page.wait_for_timeout(5000)

        # Detect which CP version's UI is rendered. CP 1.17 has the legacy `.gateway-api`
        # section; CP 1.18+ has it merged into the "Route Resource" toggle.
        if self.page.locator(".gateway-api").is_visible():
            self._dp_config_gateway_legacy(
                dp_name, gateway_controller, resource_name,
                gateway_name, gateway_namespace, fqdn, gateway_section_name)
        elif Util.check_dom_visibility(self.page, self.page.locator("#toggle-route-resource-expansion"), 3, 30):
            self._dp_config_gateway_route_resource(
                dp_name, gateway_controller, resource_name,
                gateway_name, gateway_namespace, fqdn, gateway_section_name)
        else:
            ColorLogger.warning("Neither .gateway-api (CP <= 1.17) nor #toggle-route-resource-expansion (CP 1.18+) found — DP may not be ready, OR DP may not support Gateway, skipping.")

    # ---------------------------------------------------------------------
    # CP <= 1.17 path: separate `.gateway-api` section and "Add Gateway API details" modal.
    # Preserved verbatim from the original implementation (just lifted into helpers).
    # ---------------------------------------------------------------------

    def _dp_config_gateway_legacy(self, dp_name, gateway_controller, resource_name, gateway_name, gateway_namespace, fqdn, gateway_section_name=""):
        gateway_section = self.page.locator(".gateway-api")
        gateway_toggle = gateway_section.locator(".toggle-expansion")
        gateway_toggle.wait_for(state="visible")
        expected_icon = 'pl-icon-caret-right'
        if expected_icon in (gateway_toggle.locator("svg use").get_attribute("xlink:href") or ""):
            gateway_toggle.click()
            print("Clicked expand Icon for GatewayAPI section")
            self.page.wait_for_timeout(3000)

        gateway_table = gateway_section.locator("table")
        print(f"Check if GatewayAPI Controller '{resource_name}' exists...")
        if gateway_table.is_visible() and gateway_table.locator("tr td:first-child", has_text=resource_name).is_visible():
            ColorLogger.success(f"GatewayAPI Controller '{resource_name}' is already created.")
            ReportYaml.set_dataplane_info(dp_name, resource_name, True)
        else:
            print(f"GatewayAPI Controller table does not have '{resource_name}'")
            print(f"Adding GatewayAPI Controller '{resource_name}'...")
            self.page.locator("#add-db-config-resource-GATEWAYAPI-btn").wait_for(state="visible")
            self.page.locator("#add-db-config-resource-GATEWAYAPI-btn").click()
            print("Clicked 'Add GatewayAPI Controller' button")

            self._add_gateway_controller_legacy(gateway_controller, resource_name, gateway_name, gateway_namespace, fqdn, gateway_section_name)
            self.page.wait_for_timeout(1000)
            if self.page.locator(".pl-notification--error").is_visible():
                error_content = self.page.locator(".pl-notification__message").text_content()
                Util.warning_screenshot(f"Config Data Plane Resources GatewayAPI Error: {error_content}", self.page, "dp_config_resources_gateway.png")
                self.page.locator("#cancel-database-configuration").click()
                print("Clicked 'Cancel' button")
                return
            if Util.check_dom_visibility(self.page, gateway_section.locator("table tr td:first-child", has_text=resource_name), 3, 6):
                ColorLogger.success(f"Add GatewayAPI Controller '{resource_name}' successfully.")
                ReportYaml.set_dataplane_info(dp_name, resource_name, True)
            else:
                Util.warning_screenshot(f"Config Data Plane Resources GatewayAPI '{resource_name}' Error", self.page, "dp_config_resources_gateway.png")

    def _add_gateway_controller_legacy(self, gateway_controller, resource_name, gateway_name, gateway_namespace, fqdn, gateway_section_name=""):
        ColorLogger.info("Add GatewayAPI Controller in dialog (CP <= 1.17)...")
        self.page.locator('.pl-modal__heading', has_text="Add Gateway API details").wait_for(state="visible")
        print("Dialog 'Add Gateway API details' popup")
        dropdown = self.page.locator('.pl-select', has=self.page.locator('#gatewayAPIControllerName'))
        dropdown.locator('input[type="button"]').click()
        print("Clicked 'Gateway API Controller Name' dropdown")
        dropdown.locator('.pl-select__dropdown li', has_text=gateway_controller).wait_for(state="visible")
        dropdown.locator('.pl-select__dropdown li', has_text=gateway_controller).click()
        print(f"Selected '{gateway_controller}' in Gateway API Controller Name dropdown")
        self.page.fill('#resourceName', resource_name)
        print(f"Filled Resource Name: {resource_name}")
        self.page.fill('#gatewayName', gateway_name)
        print(f"Filled Gateway Name: {gateway_name}")
        self.page.fill('#gatewayNamespace', gateway_namespace)
        print(f"Filled Gateway Namespace: {gateway_namespace}")
        self.page.fill('#gatewayHostOrDomainName', fqdn)
        print(f"Filled Gateway Host or Domain Name: {fqdn}")
        if gateway_section_name:
            self.page.fill('#gatewaySectionName', gateway_section_name)
            print(f"Filled Gateway Section Name: {gateway_section_name}")
        Util.click_button_until_enabled(self.page, self.page.locator("#save-database-configuration"))
        print("Clicked 'Add' button in 'Add Gateway API details' dialog")

    # ---------------------------------------------------------------------
    # CP 1.18+ path: unified "Route Resource" section, "Add Route Resource" modal
    # with Ingress/Gateway radio toggle. Field IDs differ from CP 1.17.
    # ---------------------------------------------------------------------

    def _ensure_route_resource_expanded(self):
        """Make sure the Route Resource section is expanded so its <table> rows are
        actually visible. CP 1.18 collapses the section by default and re-collapses
        it after a successful Save, hiding the table even though the resource exists.
        Caller must invoke this before any `.route-resource table ...` visibility check.
        """
        section_table = self.page.locator(".route-resource table")
        if section_table.is_visible():
            return
        toggle = self.page.locator("#toggle-route-resource-expansion")
        if toggle.is_visible():
            toggle.click()
            print("Expanded Route Resource section")
            self.page.wait_for_timeout(2000)

    def _dp_config_gateway_route_resource(self, dp_name, gateway_controller, resource_name, gateway_name, gateway_namespace, fqdn, gateway_section_name=""):
        # The Add button is visible even when collapsed, but the table rows are NOT
        # — so always expand explicitly before reading the table.
        self._ensure_route_resource_expanded()

        # Existing-resource fast path (CP 1.18 lists rows under .route-resource table)
        existing_row = self.page.locator(".route-resource table tr td:first-child", has_text=resource_name)
        print(f"Check if Gateway resource '{resource_name}' exists in Route Resource table...")
        if existing_row.is_visible():
            ColorLogger.success(f"Gateway resource '{resource_name}' is already created.")
            ReportYaml.set_dataplane_info(dp_name, resource_name, True)
            return

        print(f"Adding Gateway resource '{resource_name}' via 'Add Route Resource' dialog...")
        add_btn_selector = ".route-resource .add-resource-btn button"
        self.page.locator(add_btn_selector).click()
        print("Clicked 'Add' button under Route Resource")
        self.page.wait_for_timeout(1500)

        self._add_gateway_controller_route_resource(gateway_controller, resource_name, gateway_name, gateway_namespace, fqdn, gateway_section_name)
        self.page.wait_for_timeout(1000)

        if self.page.locator(".pl-notification--error").is_visible():
            error_content = self.page.locator(".pl-notification__message").text_content()
            Util.warning_screenshot(f"Config Data Plane Resources Gateway (Route Resource) Error: {error_content}", self.page, "dp_config_resources_gateway.png")
            # No id on Cancel in CP 1.18 — match by text or fall back to Escape
            cancel_btn = self.page.locator(".pl-modal__footer button", has_text="Cancel").first
            if cancel_btn.is_visible():
                cancel_btn.click()
                print("Clicked 'Cancel' button")
            else:
                self.page.keyboard.press("Escape")
                print("Pressed Escape to close modal")
            return

        # CP 1.18 auto-collapses the Route Resource section after Save closes the
        # modal — re-expand before checking the row showed up.
        self._ensure_route_resource_expanded()
        if Util.check_dom_visibility(self.page, existing_row, 3, 6):
            ColorLogger.success(f"Add Gateway resource '{resource_name}' successfully.")
            ReportYaml.set_dataplane_info(dp_name, resource_name, True)
        else:
            Util.warning_screenshot(f"Config Data Plane Resources Gateway '{resource_name}' Error", self.page, "dp_config_resources_gateway.png")

    def _add_gateway_controller_route_resource(self, gateway_controller, resource_name, gateway_name, gateway_namespace, fqdn, gateway_section_name=""):
        ColorLogger.info("Add Gateway Controller in dialog (CP 1.18+ Route Resource)...")
        modal = self.page.locator(".pl-modal", has=self.page.locator(".pl-modal__heading", has_text="Add Route Resource")).first
        modal.wait_for(state="visible")
        print("Dialog 'Add Route Resource' popup")

        # Switch radio from Ingress (default) to Gateway API Controller.
        # Angular form-field radios need force=True (the styled label/wrapper intercepts clicks).
        modal.locator("#gateway-radio-button").click(force=True)
        self.page.wait_for_timeout(1000)
        print("Switched to 'Gateway API Controller' radio")

        # Pick the controller from the gateway-specific dropdown (Nginx / GKE / Istio / Traefik / NetScaler / Other Gateway API Controller)
        modal.locator("#gatewayController-dropdown").click(force=True)
        self.page.wait_for_timeout(800)
        option = self.page.locator(".pl-select__dropdown li", has_text=gateway_controller).first
        option.wait_for(state="visible")
        option.click()
        print(f"Selected '{gateway_controller}' in Gateway Controller dropdown")

        # CP 1.18 input IDs all carry the `-input` suffix and dropped the `description` field.
        modal.locator("#resourceName-input").fill(resource_name)
        print(f"Filled Resource Name: {resource_name}")
        modal.locator("#gatewayName-input").fill(gateway_name)
        print(f"Filled Gateway Name: {gateway_name}")
        modal.locator("#gatewayNamespace-input").fill(gateway_namespace)
        print(f"Filled Gateway Namespace: {gateway_namespace}")
        modal.locator("#gatewayHost-input").fill(fqdn)
        print(f"Filled Gateway Host: {fqdn}")
        if gateway_section_name:
            modal.locator("#sectionName-input").fill(gateway_section_name)
            print(f"Filled Section Name: {gateway_section_name}")

        # CP 1.18 Save button has no id — class + text match.
        save_btn = modal.locator(".pl-modal__footer button.pl-button--primary", has_text="Add Route Resource")
        Util.click_button_until_enabled(self.page, save_btn)
        print("Clicked 'Add Route Resource' button in dialog")

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

    def _activation_modal_text(self, selector):
        """Inner text of the LAST node matching 'selector', '' when there is none.

        Last, not first, to match the close walk: when a confirmation dialog is stacked on
        another dialog, the top-most one is the one being closed and the one being
        reported on, and reading the first match describes the wrong modal.

        Diagnostics only: it must never raise and never widen an existing failure. The
        read is given an explicit timeout because a dialog that is already detaching
        would otherwise hang inner_text() on Playwright's 30s default - twice, on the
        failure path. The bare except turns that timeout into 'no details', which is
        the right answer here.
        """
        try:
            locator = self.page.locator(selector)
            if (locator.count() or 0) == 0:
                return ""
            return (locator.last.inner_text(timeout=ACTIVATION_DIALOG_READ_TIMEOUT) or "").strip()
        except Exception:
            return ""

    def _safe_activation_text(self, text):
        """Flatten and cap a scraped dialog string before it is put in a message.

        It is NOT HTML escaped: this goes into a plain text console log, where escaping
        turns an ordinary apostrophe or ampersand into '&#x27;' / '&amp;' and makes the
        message harder to read than the dialog it was copied from. Newlines and control
        characters are stripped instead, so a multi line dialog error cannot forge log
        lines, and the length cap keeps a whole license listing out of the log.
        """
        text = re.sub(r"[\x00-\x1f\x7f]+", " ", text or "").strip()
        if len(text) > ACTIVATION_DIALOG_TEXT_LIMIT:
            text = f"{text[:ACTIVATION_DIALOG_TEXT_LIMIT]}..."
        return text

    def _activation_failure_details(self, dialog_opened):
        """Say WHY the activation dialog refused the input, while it is still on screen.

        Empty when this step never opened a dialog. It scrapes '.pl-modal--open' off
        whatever happens to be on screen, so on a skip path that modal belongs to the
        CALLER, and folding its text - a stray 'expired' line included - into this step's
        failure message is the exact misdirection 'dialog_opened' exists to prevent.

        With a dialog of its own, two different problems otherwise look identical in the
        log: the dialog rejected the input outright, which it reports in
        '.file-error-message', or the license parsed fine but every entry in it has
        already expired, which it renders as plain text in the dialog body ("Current
        In-product licenses expired on <date>"). An empty error field next to that text
        points at expiry rather than a broken file, but only ever as a hint.
        """
        if not dialog_opened:
            return ""
        details = []
        file_error = self._activation_modal_text(".pl-modal--open .file-error-message")
        if file_error:
            details.append(f"Dialog error message: '{self._safe_activation_text(file_error)}'.")
        modal_text = self._activation_modal_text(".pl-modal--open")
        expiry_lines = [line.strip() for line in modal_text.splitlines()
                        if ACTIVATION_EXPIRED_TEXT.search(line) and not ACTIVATION_NOT_EXPIRED_TEXT.search(line)]
        if expiry_lines:
            expiry_text = " | ".join([self._safe_activation_text(line) for line in expiry_lines[:ACTIVATION_DIALOG_TEXT_LINES]])
            details.append(f"The dialog text mentions an expiry: '{expiry_text}'.")
            if not file_error:
                details.append("No file error was reported; check whether the license has expired.")
        if not details:
            return "The dialog reported no error message and no license details."
        return " ".join(details)

    def _close_activation_modal(self, is_activated, dialog_opened, raised, screenshot_name, success_locator):
        """Cleanup tail for both activation dialogs: nothing may stay mounted.

        Runs from a finally block, so it swallows everything it can hit. An exception
        raised here would REPLACE the one already propagating and demote the real cause
        (say "the confirmation dialog never appeared") to __context__ - exactly the kind
        of misdirection this cleanup exists to prevent.

        'dialog_opened' keeps it off the skip paths that never opened anything: a modal
        found there belongs to the caller, and closing or blaming it would report an
        unrelated leftover as this step's failure. An exception is the one case where that
        ownership cannot be known - the call died part way through, possibly on the very
        click that opened a dialog - so a raising call always cleans up what it can see.
        """
        if not dialog_opened and not raised:
            return
        try:
            # Give a dialog that is already closing time to unmount before judging it.
            self.page.wait_for_timeout(500)
            if not self.is_modal_open():
                return
            # A submit can still be in flight while this runs, and the close walk would then
            # click 'Cancel' on the confirmation dialog it belongs to and revert the link
            # that had just succeeded. So success is read once more, from the same condition
            # the step itself is judged by, and a late success is left alone entirely.
            #
            # Only while this step has NOT already observed success, though. Once it has, the
            # link is recorded server-side and closing the leftover dialog cannot revert it -
            # and this guard would otherwise never let go: is_activated was set *because* that
            # same locator was just visible, and visibility ignores overlays, so the linked
            # text reads visible straight through the backdrop. Returning here on a green run
            # would leave the dialog mounted and hand the next navigation the exact overlay
            # this step exists to clear.
            if not is_activated and Util.check_dom_visibility(self.page, success_locator, 1, 2):
                print("Activation completed while the dialog was still on screen, leaving it alone.")
                return
            if not is_activated or raised:
                # Its own file name: the failure screenshot taken moments ago is the
                # evidence of what went wrong, and must not be overwritten by this one.
                Util.warning_screenshot("Activation dialog is still open after a failed attempt, closing it.", self.page, screenshot_name.replace(".png", "-cleanup.png"))
            else:
                # On a green run the confirmation dialog can still be unmounting right after
                # the Link click; a warning here would fire on every healthy run and poison
                # the very log signal this step is judged on.
                print("Activation dialog is still open after a successful attempt, closing it.")
            self.close_open_modal()
        except Exception as e:
            ColorLogger.warning(f"Failed to close the activation dialog: {str(e)}")

    def _click_activation_control(self, selector, description):
        """Click a control that opens an activation dialog. False when it never landed.

        Reported, never raised, exactly like the 'Link' submit below. Activation is
        best-effort here - o11y_config_activation is called unwrapped - so a timeout
        thrown out of this step ends the whole Data Plane setup, and it does so blaming
        this step for an overlay an earlier one left behind. The caller skips only the
        block that needed the dialog and still runs the shared 'is it linked' check and
        the cleanup.

        The control is polled visible immediately before this, so a click that cannot
        land inside the budget is blocked by something rather than slow, and waiting
        longer would only add that wait to a run that has already gone wrong.
        """
        try:
            self.page.locator(selector).click(timeout=ACTIVATION_DIALOG_CLICK_TIMEOUT)
            print(f"Clicked {description}")
            return True
        except PlaywrightTimeoutError:
            ColorLogger.warning(f"Could not click {description}, it never became clickable.")
            return False

    def _fill_activation_input(self, selector, value, description):
        """Same contract as the click above, for the one dialog field this step types in.

        A field inside a dialog that rendered but is covered, or that is still disabled,
        fails the same way a blocked click does, and must not end the run either.
        """
        try:
            self.page.fill(selector, value, timeout=ACTIVATION_DIALOG_CLICK_TIMEOUT)
            print(f"Filled {description}: {value}")
            return True
        except PlaywrightTimeoutError:
            ColorLogger.warning(f"Could not fill {description}, it never became editable.")
            return False

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

        # From here on a dialog can be opened, so every exit runs through the finally
        # below and leaves no modal behind for the next navigation to trip over.
        is_activated = False
        dialog_opened = False
        raised = False
        skipped_reason = ""
        try:
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
                    is_activated = True
                    return

                print("Waiting for 'Use Global Activation URL' button is visible...")
                if not Util.check_dom_visibility(self.page, self.page.locator("#use-global-activation-on-dp"), 3, 30):
                    skipped_reason = "The 'Use Global Activation URL' button never appeared."
                # if "Use Global Activation URL" button is visible but not enabled, skip config
                elif "pcp-disabled" in (self.page.locator("#use-global-activation-on-dp").get_attribute("class") or ""):
                    ColorLogger.warning("'Use Global Activation URL' button is not enabled, skip config Activation url.")
                    return
                else:
                    # The flag goes up BEFORE the click: a leftover overlay swallows pointer
                    # events, so the click itself is what throws, and a cleanup that believed
                    # nothing was opened would leave that overlay for the next navigation.
                    dialog_opened = True
                    if not self._click_activation_control("#use-global-activation-on-dp", "'Use Global Activation URL' button"):
                        skipped_reason = "The 'Use Global Activation URL' button could not be clicked."
                    else:
                        print("Waiting for 'Use Global Activation URL' modal dialog is visible...")
                        # Polled instead of wait_for(): a throw here would jump straight out of the
                        # method and leave the half rendered confirmation dialog on screen.
                        if not Util.check_dom_visibility(self.page, self.page.locator("confirmation-modal .pl-modal__heading", has_text="Use Global Activation URL"), 3, 30):
                            skipped_reason = "The 'Use Global Activation URL' confirmation dialog never appeared."
                        else:
                            try:
                                self.page.locator("#confirm-button", has_text="Link").click(timeout=ACTIVATION_DIALOG_SUBMIT_TIMEOUT)
                                print("Clicked 'Link' button in 'Use Global Activation URL' modal dialog")
                            except PlaywrightTimeoutError:
                                # A slow 'Link' is reported, not raised: the click may still have
                                # landed, so the shared check below decides, and the cleanup gets
                                # to run instead of the whole Data Plane setup ending here.
                                skipped_reason = "The 'Link' button in the 'Use Global Activation URL' dialog could not be clicked."
            else:
                # for global level
                # for 1.13+ version, need select 'TIBCO Activation Service' option
                if not self.select_tibco_activation_service():
                    ColorLogger.warning("TIBCO Activation Service option is disabled, skip config Activation.")
                    return

                print("Waiting for 'Add Global Activation URL' button is visible...")
                if not Util.check_dom_visibility(self.page, self.page.locator("#add-global-activation-server"), 3, 30):
                    skipped_reason = "The 'Add Global Activation URL' button never appeared."
                else:
                    # The flag goes up BEFORE the click: a leftover overlay swallows pointer
                    # events, so the click itself is what throws, and a cleanup that believed
                    # nothing was opened would leave that overlay for the next navigation.
                    dialog_opened = True
                    if not self._click_activation_control("#add-global-activation-server", "'Add Global Activation URL' button"):
                        skipped_reason = "The 'Add Global Activation URL' button could not be clicked."
                    else:
                        print("Waiting for 'Add New Activation URL' modal dialog is visible...")
                        if not Util.check_dom_visibility(self.page, self.page.locator("activation-url-modal .pl-modal__heading", has_text="Add New Activation URL"), 3, 30):
                            skipped_reason = "The 'Add New Activation URL' dialog never appeared."
                        elif not self._fill_activation_input("activation-url-modal #activation-url-text-input", activation_url, "Activation URL"):
                            # Submitting a dialog whose field was never filled adds an empty
                            # URL, so the 'Add' click below is skipped with it.
                            skipped_reason = "The Activation URL field in the 'Add New Activation URL' dialog could not be filled."
                        else:
                            self.page.locator("activation-url-modal #add-activation-url-btn").click(timeout=ACTIVATION_DIALOG_SUBMIT_TIMEOUT)
                            print("Clicked 'Add' button in 'Add New Activation URL' dialog")

            # A missed control or dialog still falls through to the shared check below: the
            # URL may already be configured, and skipping the report write on that run would
            # leave o11y_config_activation with nothing stored and the DP link silently
            # skipped for the rest of the run.
            if Util.check_dom_visibility(self.page, self.page.locator(".activation-server-url", has_text=activation_url), 3, 6):
                ColorLogger.success(f"Add Activation URL '{activation_url}' successfully.")
                is_activated = True
                if use_global:
                    ReportYaml.set_dataplane_info(dp_name, "activation", "Global")
                else:
                    ReportYaml.set_dataplane_info(dp_name, "activation", "server")
            else:
                # Nothing is written to the report on a failure path: o11y_config_activation
                # skips on any stored value, so a recorded failure would disable activation
                # for good on every later run.
                if use_global:
                    message = f"Link to the Global Activation URL failed for Data Plane '{dp_name}'."
                else:
                    message = f"Add Activation URL '{activation_url}' failed for Data Plane '{dp_name}'."
                if skipped_reason:
                    message = f"{message} {skipped_reason}"
                # Only a dialog this step opened may be scraped for a reason: on a skip
                # path the modal on screen is the caller's, and its text is not evidence
                # about this step.
                details = self._activation_failure_details(dialog_opened)
                if details:
                    message = f"{message} {details}"
                Util.warning_screenshot(message, self.page, "dp_config_activation_url.png")
        except BaseException:
            # Only an exception raised by THIS call may mark the run as failed. sys.exc_info()
            # would also report one being handled further up the stack, and turn a green run
            # into a false warning plus screenshot. BaseException on purpose: a nested
            # Util.exit_error raises SystemExit, which would otherwise sail past.
            raised = True
            raise
        finally:
            self._close_activation_modal(is_activated, dialog_opened, raised, "dp_config_activation_url.png",
                                         self.page.locator(".activation-server-url", has_text=activation_url))

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
        if Util.check_dom_visibility(self.page, self.page.locator("span", has_text=ACTIVATION_LINKED_TEXT), 2, 4):
            ColorLogger.success(f"Activation file is already exist for Data Plane '{dp_name}'.")
            if use_global:
                ReportYaml.set_dataplane_info(dp_name, "activation", "Global")
            else:
                ReportYaml.set_dataplane_info(dp_name, "activation", "file")
            return

        # From here on a dialog can be opened, so every exit runs through the finally
        # below and leaves no modal behind for the next navigation to trip over.
        is_activated = False
        dialog_opened = False
        raised = False
        skipped_reason = ""
        add_button_never_enabled = False
        try:
            if use_global:
                # for dp level
                if not self.select_in_product_activation():
                    ColorLogger.warning("In-Product Activation option is disabled, skip config Activation.")
                    return
                if self.page.locator(".dp-activation-content__license-file-item-details").is_visible():
                    ColorLogger.success(f"In-Product Activation is already exist for Data Plane '{dp_name}'.")
                    ReportYaml.set_dataplane_info(dp_name, "activation", "Global")
                    is_activated = True
                    return

                ColorLogger.info(f"Link to Activation File '{ENV.TP_ACTIVATION_FILENAME}' for Data Plane...")
                # Polled before the click, and the 'pcp-disabled' guard reads the button
                # only once it has rendered: a one-shot is_visible() skips the guard on a
                # late render, and the click behind it then stalls on Playwright's 30s
                # default - the exact shape of failure this step is being fixed for.
                if not Util.check_dom_visibility(self.page, self.page.locator("#use-global-license-file-on-dp"), 3, 30):
                    skipped_reason = "The 'Use Global License File' button never appeared."
                # if "Use Global License File" button is visible but not enabled, skip config
                elif "pcp-disabled" in (self.page.locator("#use-global-license-file-on-dp").get_attribute("class") or ""):
                    ColorLogger.warning("'Use Global License File' button is not enabled, skip config Activation url.")
                    return
                else:
                    # The flag goes up BEFORE the click: a leftover overlay swallows pointer
                    # events, so the click itself is what throws, and a cleanup that believed
                    # nothing was opened would leave that overlay for the next navigation.
                    dialog_opened = True
                    if not self._click_activation_control("#use-global-license-file-on-dp", "'Use Global License File' option"):
                        skipped_reason = "The 'Use Global License File' option could not be clicked."
                    else:
                        print("Waiting for 'Use Global License File' modal dialog is visible...")
                        # Polled instead of wait_for(): a throw here would jump straight out of the
                        # method and leave the half rendered confirmation dialog on screen.
                        if not Util.check_dom_visibility(self.page, self.page.locator("confirmation-modal .pl-modal__heading", has_text="Use Global License File"), 3, 30):
                            skipped_reason = "The 'Use Global License File' confirmation dialog never appeared."
                        else:
                            try:
                                self.page.locator("#confirm-button", has_text="Link").click(timeout=ACTIVATION_DIALOG_SUBMIT_TIMEOUT)
                                print("Clicked 'Link' button in 'Use Global License File' modal dialog")
                            except PlaywrightTimeoutError:
                                # A slow 'Link' is reported, not raised: the click may still have
                                # landed, so the shared check below decides, and the cleanup gets
                                # to run instead of the whole Data Plane setup ending here.
                                skipped_reason = "The 'Link' button in the 'Use Global License File' dialog could not be clicked."
            else:
                # for global level
                if not self.select_in_product_activation():
                    ColorLogger.warning("In-Product Activation option is disabled, skip config Activation.")
                    return
                ColorLogger.info(f"Upload Activation File '{ENV.TP_ACTIVATION_FILENAME}' for Global Data Plane...")
                if not Util.check_dom_visibility(self.page, self.page.locator('#add-global-license-file'), 2, 6):
                    # Told apart from the drop zone below on purpose: nothing was ever
                    # clicked here, so no dialog was ever asked for, and reporting this as
                    # "the dialog never appeared" would name a step that never ran.
                    skipped_reason = "The 'Upload' option '#add-global-license-file' never appeared."
                else:
                    # The flag goes up BEFORE the click: a leftover overlay swallows pointer
                    # events, so the click itself is what throws, and a cleanup that believed
                    # nothing was opened would leave that overlay for the next navigation.
                    dialog_opened = True
                    if not self._click_activation_control("#add-global-license-file", "'Upload' option"):
                        # Told apart from the drop zone below for the same reason as the
                        # missing option above: this names the click, and the guard on that
                        # branch keeps it from being overwritten by a second complaint about
                        # the dialog it was supposed to open.
                        skipped_reason = "The 'Upload' option '#add-global-license-file' could not be clicked."

                # The drop zone is the proof that the 'Add New License File' dialog really
                # rendered. A single is_visible() raced the dialog opening, so the file was
                # never attached and the run went on with an empty, silently open dialog.
                # It is probed independently of the 'Upload' option above: a control plane
                # that shows the dialog without that option still has to get the file.
                if Util.check_dom_visibility(self.page, self.page.locator('.license-file-drop-zone'), 2, 6):
                    # Whatever put the dialog there, the file is being attached to it, so
                    # closing it if this goes wrong is now this step's job.
                    dialog_opened = True
                    print("Popping up 'Add New License File' dialog")

                    self.page.locator('input[type="file"]').evaluate("(input) => input.style.display = 'block'")
                    self.page.locator('input[type="file"]').set_input_files(activation_file_path)
                    print(f"Selected file: {activation_file_path}")

                    # This one waits on server side license validation, not on a client side
                    # mount, so it gets the full budget: the button enables only once the
                    # backend has accepted the file.
                    if Util.check_dom_visibility(self.page, self.page.locator("#add-activation-url-btn:not([disabled])"), 3, 30):
                        self.page.locator('#add-activation-url-btn').click(timeout=ACTIVATION_DIALOG_SUBMIT_TIMEOUT)
                        print("Clicked 'Add' button in 'Add New License File' dialog")
                    else:
                        # Keep the dialog on screen for one more moment: the reason it refused
                        # the file is only readable while it is still mounted, and the shared
                        # tail below turns it into the warning message.
                        add_button_never_enabled = True
                elif not skipped_reason:
                    # Only when the 'Upload' option was there and clicked: its own absence is
                    # already reported above, and naming both would blame two separate steps
                    # for one missing dialog.
                    skipped_reason = "The 'Add New License File' dialog never appeared, so the file was never attached."

            # A missed option or dialog still falls through to the shared check below: the
            # license may already be linked, and skipping the report write on that run would
            # leave o11y_config_activation with nothing stored and the DP link silently
            # skipped for the rest of the run.
            if Util.check_dom_visibility(self.page, self.page.locator("span", has_text=ACTIVATION_LINKED_TEXT), 2, 4):
                ColorLogger.success(f"Upload Activation File '{ENV.TP_ACTIVATION_FILENAME}' successfully for Data Plane '{dp_name}'.")
                is_activated = True
                if use_global:
                    ReportYaml.set_dataplane_info(dp_name, "activation", "Global")
                else:
                    ReportYaml.set_dataplane_info(dp_name, "activation", "file")
            else:
                # Nothing is written to the report on a failure path: o11y_config_activation
                # skips on any stored value, so a recorded failure would disable activation
                # for good on every later run. An unusable license is loud but not fatal,
                # the rest of the Data Plane setup still has to finish.
                if use_global:
                    message = f"Link to the Global license file failed for Data Plane '{dp_name}'."
                else:
                    message = f"Add Activation file '{activation_file_path}' failed for Data Plane '{dp_name}'."
                if skipped_reason:
                    message = f"{message} {skipped_reason}"
                if add_button_never_enabled:
                    message = f"{message} The 'Add' button in the 'Add New License File' dialog never enabled."
                # Only a dialog this step opened may be scraped for a reason: on a skip
                # path the modal on screen is the caller's, and its text is not evidence
                # about this step.
                details = self._activation_failure_details(dialog_opened)
                if details:
                    message = f"{message} {details}"
                Util.warning_screenshot(message, self.page, "dp_config_activation_file.png")
        except BaseException:
            # Only an exception raised by THIS call may mark the run as failed. sys.exc_info()
            # would also report one being handled further up the stack, and turn a green run
            # into a false warning plus screenshot. BaseException on purpose: a nested
            # Util.exit_error raises SystemExit, which would otherwise sail past.
            raised = True
            raise
        finally:
            self._close_activation_modal(is_activated, dialog_opened, raised, "dp_config_activation_file.png",
                                         self.page.locator("span", has_text=ACTIVATION_LINKED_TEXT))
