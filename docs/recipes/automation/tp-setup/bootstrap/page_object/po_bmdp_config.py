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
import shutil
import tempfile

import yaml

from page_object.po_user_management import PageObjectUserManagement, GRANT_DONE, GRANT_ALREADY, GRANT_FAILED
from utils.color_logger import ColorLogger
from utils.util import Util
from utils.helper import (
    Helper,
    O11Y_LOG_INDEX_BUSINESS_ACTIVITIES,
    O11Y_LOG_INDEX_DEFAULT,
    O11Y_LOG_INDEX_USER_APPS,
    o11y_log_index,
)
from utils.env import ENV
from utils.report import ReportYaml
from page_object.po_dataplane import PageObjectDataPlane

# Data plane config -> Messaging: registering an EMS server group.
#
# CP 1.21 changed this page in three separate places, and only the middle one is a
# redesign - the other two are quiet selector breaks that do not raise where they break:
#
#   1. the page moved from Plexus to PrimeNG, so the '.pl-button__label' the flow clicked
#      to OPEN registration matches nothing and it timed out for 30s with the button
#      plainly visible;
#   2. the multi-step form wizard (pick capability -> pick "Register a Server" -> fill six
#      inputs) became a single YAML editor / file-upload dialog. None of the intermediate
#      steps or inputs exist any more;
#   3. the RESULT LIST became a PrimeNG p-datatable, so 'tr.pl-table__row',
#      'td.pl-table__cell' and "td[class*='_healthCell']" all match nothing. That one is
#      the dangerous one: the idempotency pre-check silently decided "not registered yet"
#      on every run, and check_ems_server_status() called .get_attribute() on None.
#
# Every legacy selector below is kept and the branch is taken on which dialog the Control
# Plane actually rendered, not on a version number (bootstrap/CLAUDE.md principle 6).
EMS_REGISTER_BUTTON_NAME = "Register New Instances"
# Pre-1.21 fallback for the same button. NOT swapped for '.p-button-label': that class
# matches 2 elements on the 1.21 Messaging page ('More' and this one), so it would turn a
# 30s timeout into a strict-mode violation. The accessible name is unique on both.
EMS_REGISTER_BUTTON_LEGACY = ".pl-button__label"

EMS_DIALOG = "section.gemsModalDialog"
# Present only in the 1.21 dialog - this is what the branch is taken on.
EMS_YAML_EDITOR = f"{EMS_DIALOG} #yaml-editor"
# Hidden (0x0, class _hidden_*) behind a <label for="yaml-input">Upload YAML</label>.
# set_input_files() drives it anyway, which is why this flow uploads a generated file
# rather than typing into the ace editor - ace is a canvas-ish editor that fill() cannot
# drive reliably.
EMS_YAML_FILE_INPUT = f"{EMS_DIALOG} #yaml-input"
EMS_YAML_FILENAME = "ems-server-groups.yaml"
EMS_VALIDATE_ALL = f"{EMS_DIALOG} button[aria-label='Validate All']"
# The bulk register button's accessible name is DYNAMIC and carries the validated count,
# with a singular/plural swap: "Register 0 Server Groups" -> "Register 1 Server Group".
# Matching on "Register" alone would also match the per-row action button, whose
# aria-label becomes exactly "Register" once its row validates - two matches, strict-mode
# violation. "Server Group" appears only on the bulk button.
EMS_REGISTER_GROUPS = f"{EMS_DIALOG} button[aria-label*='Server Group']"
EMS_DONE = f"{EMS_DIALOG} button[aria-label='Done']"
EMS_ROW_STATUS = "[class*='_tableStatusCell']"

# Per-row status vocabulary, read live on CP 1.21.0:
#   '' / 'Registering...' -> transient; parsed out of the YAML, or mid-register
#   Validated / Registered -> the two states this flow drives towards
#   Error -> terminal; it held Error for 40s and never recovered into Validated
EMS_STATUS_VALIDATED = "Validated"
EMS_STATUS_REGISTERED = "Registered"
EMS_STATUS_ERROR = "Error"

# 'Done' closes the modal, and the Messaging list underneath must not be read until it
# has: the dialog's own result table ALSO holds a row named after the server group, so
# while both are mounted get_by_role("row", name=...) resolves to 2 elements and
# check_ems_server_status() dies on a strict-mode violation. Seen for real on 1.21 - the
# registration had fully succeeded and the flow still failed, one line later.
EMS_DIALOG_CLOSE_TIMEOUT_MS = 30000

# First step of the pre-1.21 wizard, kept as the "legacy dialog opened" signal.
EMS_WIZARD_STEP = "[class*='_modalBody'] span"
EMS_WIZARD_CAPABILITY = "Enterprise Message Service"
EMS_WIZARD_REGISTER_SERVER = "Register a Server"

# Health is conveyed ONLY by an icon here - no text, no aria-label, no title (checked on
# the live 1.21 row). bootstrap/CLAUDE.md principle 2 says not to read SVG internals for
# state, but there is no other signal to read, and the code being replaced already read
# exactly this href. Legacy wraps the icon in td[class*='_healthCell'], 1.21 in
# div[class*='_healthContainer_'] - one prefix covers both.
EMS_HEALTH_ICON = "[class*='_health'] svg use"
EMS_HEALTH_OK = "pl-icon-success"


def build_ems_registration_yaml(server_group_name, client_url, monitor_url, username, password):
    """The CP 1.21 `server_groups` registration payload, as YAML text.

    Dumped through PyYAML rather than an f-string on purpose: clientUrl and monitorUrl are
    comma-separated URL lists full of ':' and '//', and the password is arbitrary text, so
    hand-formatting breaks on the first value that needs quoting.

    An empty password omits the key entirely. `registrationPass:` with nothing after it is
    YAML null rather than an empty string, and the dialog's own example marks the field
    Optional - TP_AUTO_K8S_BMDP_BW5_EMS_PASSWORD defaults to '', so this is the normal
    case, not an edge case.
    """
    server_group = {
        "groupName": server_group_name,
        "clientUrl": client_url,
        "monitorUrl": monitor_url,
        "registrationUser": username,
    }
    if password:
        server_group["registrationPass"] = password
    return yaml.safe_dump({"server_groups": [server_group]}, default_flow_style=False, sort_keys=False)

# (dp_name, product) pairs whose Product Permission already converged in THIS process.
# Purely a performance optimisation - deleting it must never change correctness, only
# make a later caller walk the Assign Permissions wizard again for a grant that is
# already in place. Deliberately NOT persisted to report.yaml: that file has three
# different lifecycles (pipeline / Automation Hub / run-case-in-gcp), so a persisted
# marker would make an idempotency re-run skip the very code it is meant to verify.
_GRANTED_IN_RUN: set[tuple[str, str]] = set()

class PageObjectBMDPConfiguration(PageObjectDataPlane):

    def __init__(self, page):
        super().__init__(page)

    def goto_dataplane_config(self):
        ColorLogger.info(f"Going to Data plane Configuration page...")
        self.page.locator("button", has_text="Data Plane configuration").wait_for(state="visible")
        self.page.locator("button", has_text="Data Plane configuration").click()
        print("Clicked 'BMDP configuration' button")
        self.page.wait_for_timeout(500)

    def goto_dataplane_config_sub_menu(self, sub_menu_name = ""):
        ColorLogger.info(f"Going to Data plane config -> '{sub_menu_name}' side menu")
        self.page.locator("#left-sub-menu .menu-item-text", has_text=sub_menu_name).click()
        print(f"Clicked '{sub_menu_name}' left side menu")
        self.page.wait_for_timeout(500)

    def goto_products(self, product_name):
        ColorLogger.info("Going to Products page...")
        # "BW5" for BW5, "BE" for be, "BW6" for BW6
        print(f"Checking if {product_name} Card is Available.")

        if self.page.locator(f".product-card.disabled-card", has=self.page.locator(f".product-card__title", has_text=product_name)).is_visible():
            print(f"{product_name} Card is Disabled, need to set user permission first.")
            self.page.locator(f".product-card.disabled-card", has=self.page.locator(f".product-card__title", has_text=product_name)).hover()
            print(f"Hovered on Disabled {product_name} Card to check tooltip message.")
            if self.page.locator(".pl-tooltip__content:visible", has_text="You need Product permission to perform this action.").is_visible():
                print("Tooltip message is visible, proceed to set user permission.")
                po_user_management = PageObjectUserManagement(self.page)
                po_user_management.grant_product_permission(ENV.TP_AUTO_K8S_BMDP_NAME, product_name)

                print("Go back to Dataplane Products page after setting user permission.")
                self.goto_left_navbar_dataplane()
                self.goto_dataplane(ENV.TP_AUTO_K8S_BMDP_NAME)

        if Util.check_dom_visibility(self.page, self.page.locator(f".product-card:not(.disabled-card)", has=self.page.locator(f".product-card__title", has_text=product_name)), 30, 180, True):
            self.page.locator(f".product-card:not(.disabled-card)", has=self.page.locator(f".product-card__title", has_text=product_name)).click()
            print(f"Clicked '{product_name}' Card")
            return True
        else:
            Util.warning_screenshot(f"{product_name} Card is not visible.", self.page, "goto_Products.png")
            return False

    def ensure_bmdp_product_permissions(self, dp_name=None) -> dict[str, str]:
        """Grant the user Product Permission on the BMDP for every product this run
        will configure, before anything needs it.

        The browser path only ever granted reactively, once goto_products found a
        disabled product card; the CLI path grants up front (page_cli._run_api_bmdp_config).
        Doing it here makes both paths leave the same permissions behind, and gets the
        grant in while the BMDP is still fresh instead of mid capability config.

        Returns {product: result}, result being one of the GRANT_* strings. This method
        never raises and never calls Util.exit_error - a grant that could not be made is
        reported and the caller carries on.
        """
        dp_name = dp_name or ENV.TP_AUTO_K8S_BMDP_NAME

        # Same gating as the CLI path: BW5 and BW6 are the only products behind Product
        # Permission, and only the ones whose domains this run registers are worth a
        # wizard round trip. EMS / BE / Messaging are not gated by it at all.
        products = []
        if ENV.TP_AUTO_IS_ENABLE_RVDM or ENV.TP_AUTO_IS_ENABLE_EMSDM:
            products.append("BW5")
        if ENV.TP_AUTO_IS_ENABLE_BW6DM:
            products.append("BW6")
        if not products:
            print("No BW5 or BW6 domain is enabled, no Product Permission is needed.")
            return {}

        ColorLogger.info(f"Ensuring Product Permission on '{dp_name}' for: {', '.join(products)}")
        results = {}
        for product in products:
            if (dp_name, product) in _GRANTED_IN_RUN:
                results[product] = GRANT_ALREADY
                print(f"Product permission {dp_name} => {product}: {GRANT_ALREADY}")
                continue

            result = GRANT_FAILED
            # Two attempts, no more. In the pipeline this grant gets exactly ONE chance per
            # instance lifetime: the create-bmdp task exits 0 as soon as the BMDP shows up
            # in .dataPlane[], so there is no "it will self-heal on the next run".
            # grant_product_permission cancels out of the wizard before it reports a
            # failure and goto_assign_permissions re-enters from scratch, so attempt 2
            # never inherits a half ticked wizard.
            for attempt in range(2):
                try:
                    po_user_management = PageObjectUserManagement(self.page)
                    result = po_user_management.grant_product_permission(dp_name, product)
                except (Exception, SystemExit) as e:
                    # Util.exit_error deep in a shared helper raises SystemExit, a
                    # BaseException that sails straight past "except Exception". Nothing in
                    # a best effort grant may abort the caller, so catch it explicitly.
                    # No screenshot here on purpose: Util.warning_screenshot itself raises
                    # when the page is already gone, which would break the no-raise contract.
                    ColorLogger.warning(f"Product Permission attempt {attempt + 1} for '{product}' on '{dp_name}' raised: {e}")
                    result = GRANT_FAILED
                if result != GRANT_FAILED:
                    break

            results[product] = result
            # Memoise a converged grant only. A skip or a failure has to stay retryable for
            # a later caller in the same process.
            if result in (GRANT_DONE, GRANT_ALREADY):
                _GRANTED_IN_RUN.add((dp_name, product))
            print(f"Product permission {dp_name} => {product}: {result}")
            if result == GRANT_FAILED:
                ColorLogger.warning(f"Could not grant Product Permission '{product}' on '{dp_name}', will continue with remaining tasks.")

        # The wizard lives under User Management, so put the browser back on the data plane
        # page the caller expects, the same way goto_products does after its reactive grant.
        try:
            print(f"Go back to Data Plane '{dp_name}' page after setting user permission.")
            self.goto_left_navbar_dataplane()
            self.goto_dataplane(dp_name)
        except (Exception, SystemExit) as e:
            # Same SystemExit trap as above: a navigation hiccup on the way out must not
            # kill an install task, the caller navigates for itself anyway.
            ColorLogger.warning(f"Could not navigate back to Data Plane '{dp_name}' after setting Product Permission: {e}")

        return results

    def dp_config_bw5_rvdm(self, domain_name):
        if ReportYaml.get_capability_info(ENV.TP_AUTO_K8S_BMDP_NAME, "BW5", domain_name) in ("Added", "Connected"):
            ColorLogger.success(f"Dataplane '{ENV.TP_AUTO_K8S_BMDP_NAME}' capability 'BW5' domain '{domain_name}' is already added.")
            return self.check_domain_status(domain_name, "BW5")

        ColorLogger.info("Config BW5 RV domain...")
        if not Util.check_dom_visibility(self.page, self.page.locator(f"td.pl-table__cell:text('{domain_name}')"), 3, 9, True):
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
            #add domain to report no matter success or failed
            ReportYaml.set_capability(ENV.TP_AUTO_K8S_BMDP_NAME, "BW5")
            ReportYaml.set_capability_info(ENV.TP_AUTO_K8S_BMDP_NAME, "BW5", domain_name, "Added")
            if self.page.locator(".pl-notification__message", has_text="successfully").is_visible():
                ColorLogger.success(domain_banner)
            else:
                Util.warning_screenshot(f"May faild to regiter RV domain due to: {domain_banner}", self.page, "dp_config_bw5_rvdm.png")
                return False
        return self.check_domain_status(domain_name, "BW5")

    def dp_config_bw5_emsdm(self, domain_name):
        if ReportYaml.get_capability_info(ENV.TP_AUTO_K8S_BMDP_NAME, "BW5", domain_name) in ("Added", "Connected"):
            ColorLogger.success(f"Dataplane '{ENV.TP_AUTO_K8S_BMDP_NAME}' capability 'BW5' domain '{domain_name}' is already added.")
            return self.check_domain_status(domain_name, "BW5")

        ColorLogger.info("Config BW5 EMS domain...")
        if not Util.check_dom_visibility(self.page, self.page.locator(f"td.pl-table__cell:text('{domain_name}')"), 3, 9, True):
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
            #add domain to report no matter success or failed
            ReportYaml.set_capability(ENV.TP_AUTO_K8S_BMDP_NAME, "BW5")
            ReportYaml.set_capability_info(ENV.TP_AUTO_K8S_BMDP_NAME, "BW5", domain_name, "Added")
            if self.page.locator(".pl-notification__message", has_text="successfully").is_visible():
                ColorLogger.success(domain_banner)
            else:
                Util.warning_screenshot(f"May faild to regiter RV domain due to: {domain_banner}", self.page, "dp_config_bw5_emsdm.png")
                return False
        else:
            ColorLogger.info(f"Domain '{domain_name}' is already added.")
        return self.check_domain_status(domain_name, "BW5")

    def check_domain_status(self, domain_name, capability, max_retries=180):
        ColorLogger.info(f"Checking domain status for '{domain_name}'")
        domain_row = self.page.locator("tr.pl-table__row", has=self.page.locator('td.pl-table__cell', has_text=domain_name))
        if domain_row.is_visible():
            if Util.check_dom_visibility(self.page, domain_row.locator("td.pl-table__cell img[src*='/connected.svg']"), 10, max_retries):
                ColorLogger.success(f"Domain '{domain_name}' is connected.")
                ReportYaml.set_capability_info(ENV.TP_AUTO_K8S_BMDP_NAME, capability, domain_name, "Connected")
                return True
            Util.warning_screenshot(f"Domain '{domain_name}' status is disconnected, will continue with remaining tasks.", self.page, "check_domain_status.png")
            return False
        else:
            Util.warning_screenshot(f"Domain '{domain_name}' is not found, will continue with remaining tasks.", self.page, "check_domain_status.png")
            return False


    def check_bmdp_app_status_by_app_name(self, product_name, domain_name, app_name):
        ColorLogger.info(f"Checking {product_name} application - {app_name} status in '{domain_name}'")
        self.page.wait_for_timeout(1000)
        # check bw5 application status
        if product_name == "BW5":
            print("Checking if new domain card layout is available...")
            if Util.check_dom_visibility(self.page, self.page.locator(".domains-grid"), 2, 4):
                print("New domain card layout detected.")
                domain_card = self.page.locator(".domain-card", has=self.page.locator('.pl-card__header', has_text=domain_name))
                if domain_card.is_visible():
                    dom_go_to_domain = domain_card.locator(".pl-card__footer", has_text=re.compile(r"Go (into|to) Domain"))
                    if dom_go_to_domain.is_visible():
                        # for 1.16 or earlier version
                        dom_go_to_domain.click()
                    else:
                        domain_card.click()
                    print(f"'{domain_name}' is deployed and checking application instance status.")
                    app_row = self.page.locator("tr.pl-table__row", has=self.page.locator('td.pl-table__cell', has_text=app_name))
                    if Util.check_dom_visibility(self.page, app_row.locator("td.pl-table__cell img[src*='/pl-icon-success.svg']"), 5, 120, True):
                        print(f"'{app_name}' is deployed and checking service instance status.")
                        ReportYaml.set_capability_app(ENV.TP_AUTO_K8S_BMDP_NAME, "BW5", f"{domain_name}.{app_name}")
                        ReportYaml.set_capability_app_info(ENV.TP_AUTO_K8S_BMDP_NAME, "BW5", f"{domain_name}.{app_name}", "Status", "Running")
                    else:
                        ColorLogger.warning(f"'{app_name}' is not deployed successfully or cannot be discovered by CT in domain '{domain_name}'.")
            else:
                app_row = self.page.locator("tr.pl-table__row", has=self.page.locator('td.pl-table__cell', has_text=domain_name))
                if Util.check_dom_visibility(self.page, app_row.locator("td.pl-table__cell img[src*='/pl-icon-success.svg']"), 5, 120, True):
                    app_row.locator('td.pl-table__cell .text', has_text=app_name).click()
                    print(f"'{app_name}' is deployed and checking service instance status.")
                    ReportYaml.set_capability_app(ENV.TP_AUTO_K8S_BMDP_NAME, "BW5", f"{domain_name}.{app_name}")
                else:
                    ColorLogger.warning(f"'{app_name}' is not deployed successfully or cannot be discovered by CT in domain '{domain_name}'.")
                service_instance_row = self.page.locator("tr.pl-table__row")
                if Util.check_dom_visibility(self.page, service_instance_row.locator("td.pl-table__cell img[src*='/pl-icon-success.svg']"), 5, 120, True):
                    ColorLogger.success(f"'{app_name}' in domain '{domain_name}' instance is running.")
                    ReportYaml.set_capability_app_info(ENV.TP_AUTO_K8S_BMDP_NAME, "BW5", f"{domain_name}.{app_name}", "Status", "Running")
                else:
                    ColorLogger.warning(f"'{app_name}' in domain '{domain_name}' instance is not running.")
        # check bw6 application status
        if product_name == "BW6":
            if Util.check_dom_visibility(self.page, self.page.locator(".pl-card--standard"), 2, 10):
                if not self.is_fresco:
                    self.page.locator(".pl-card--standard").click()
                print(f"'{domain_name}' is deployed and checking application instance status.")
            else:
                Util.warning_screenshot(f"'{domain_name}' is not deployed successfully or cannot be discovered by CT.", self.page, "check_bmdp_bw6_app_status.png")

            if Util.check_dom_visibility(self.page, self.page.locator(f".pl-card__body-content img[src*='/machines.svg']"), 2, 6):
                print(f"'{domain_name} -> {product_name}' application card layout detected.")
                self.page.locator(f".pl-card__body-content img[src*='/machines.svg']").click()
                self.check_bw6_app_status(domain_name, "Machines", "bw6-node")
                self.check_bw6_app_status(domain_name, "AppSpaces", "test_as")
                self.check_bw6_app_status(domain_name, "AppNodes", "test_an")
                self.check_bw6_app_status(domain_name, "Applications", "mySleep.application")

    def is_app_running(self, product_name, domain_name, app_name):
        # BW5 stores app as "{domain}.{app}", BW6 stores app as "{app}" (no domain prefix)
        report_app_name = app_name if product_name == "BW6" else f"{domain_name}.{app_name}"
        if ReportYaml.get_capability_app_info(ENV.TP_AUTO_K8S_BMDP_NAME, product_name, report_app_name, "Status"):
            ColorLogger.success(f"Dataplane '{ENV.TP_AUTO_K8S_BMDP_NAME}' capability '{product_name}' app '{report_app_name}' is already running.")
            return True
        return False

    def is_ems_server_connected(self, server_group_name):
        if ReportYaml.get_capability_info(ENV.TP_AUTO_K8S_BMDP_NAME, "EMSServer", server_group_name):
            ColorLogger.success(f"Dataplane '{ENV.TP_AUTO_K8S_BMDP_NAME}' '{server_group_name}' is Connected.")
            return True
        return False

    def check_bw6_app_status(self, domain_name, app_type, app_name):
        ColorLogger.info(f"Checking BW6 application - {app_type} status")
        # hover over the app type icon to click it
        if self.is_fresco:
            self.page.locator(f"#tab-{app_type.lower()}").click()
        else:
            self.page.locator(f".bw6-icons .pl-tooltip__trigger", has=self.page.locator(f"img[alt='{app_type}']")).hover()
            self.page.wait_for_timeout(500)
            self.page.locator(f".bw6-icons .pl-tooltip__trigger", has=self.page.locator(f"img[alt='{app_type}']")).click()
        app_row = self.page.locator("tr.pl-table__row", has=self.page.locator('td.pl-table__cell', has_text=app_name))
        if Util.check_dom_visibility(self.page, app_row.locator("td.pl-table__cell img[src*='/running.svg']"), 2, 5):
            ColorLogger.success(f"'{app_type}':'{app_name}' in domain '{domain_name}' is running.")
            ReportYaml.set_capability_app(ENV.TP_AUTO_K8S_BMDP_NAME, "BW6", f"{app_name}")
            ReportYaml.set_capability_app_info(ENV.TP_AUTO_K8S_BMDP_NAME, "BW6", f"{app_name}", "Status", "Running")
        else:
            Util.warning_screenshot(f"'{app_name}' in domain '{domain_name}' instance is not running.", self.page, "check_bw6_app_status_by_app_name.png")

    def dp_config_bw6(self, agent_name):
        if ReportYaml.get_capability_info(ENV.TP_AUTO_K8S_BMDP_NAME, "BW6", agent_name) in ("Added", "Connected"):
            ColorLogger.success(f"Dataplane '{ENV.TP_AUTO_K8S_BMDP_NAME}' capability 'BW6' domain '{agent_name}' is already added.")
            return self.check_domain_status(agent_name, "BW6")

        ColorLogger.info("Config BW6 domain...")
        # switch to BW6 Agents config page
        self.goto_dataplane_config_sub_menu("Agents")
        if not Util.check_dom_visibility(self.page, self.page.locator(f"td.pl-table__cell:text('{agent_name}')"), 3, 9, True):
            # add domain
            self.page.locator("#add-proxy").wait_for(state="visible")
            self.page.locator("#add-proxy").click()
            print("Clicked 'Add Agent' button, to configure BW6 domain")
            self.page.fill("#agentName-text-input", ENV.TP_AUTO_K8S_BMDP_BW6DM)
            print(f"Filled Agent Name: {ENV.TP_AUTO_K8S_BMDP_BW6DM}")

            # add bw6 agent url
            self.page.fill("#agentUrl-text-input", ENV.TP_AUTO_K8S_BMDP_BW6DM_URL)
            print(f"Filled BW6Agent URL: {ENV.TP_AUTO_K8S_BMDP_BW6DM_URL}")
            # test connection and register bw6 agent
            if Util.check_dom_visibility(self.page, self.page.locator("button", has_text="Test Connection"), 2, 4):
                self.page.locator("button", has_text="Test Connection").click()
                print("Clicked 'Test Connection' button")
                if Util.check_dom_visibility(self.page, self.page.locator(".test-connection-success"), 2, 6):
                    ColorLogger.success("BW6Agent connection is successful.")
                    self.page.locator("agent-config-modal button", has_text="Register").click()
                    ReportYaml.set_capability(ENV.TP_AUTO_K8S_BMDP_NAME, "BW6")
                    ReportYaml.set_capability_info(ENV.TP_AUTO_K8S_BMDP_NAME, "BW6", agent_name, "Added")
                    print("Clicked 'Register' button")
                    self.page.wait_for_timeout(3000)
                    if self.page.locator(".pl-notification__message", has_text="successfully").is_visible():
                        agent_banner = self.page.locator(".pl-notification__message").inner_text()
                        ColorLogger.success(agent_banner)
                    else:
                        Util.warning_screenshot(f"May failed to register BW6 domain", self.page, "dp_config_bw6dm.png")
                        return False
                else:
                    Util.warning_screenshot(f"'{agent_name}' connection test failed.", self.page, "test_connection_bw6agent_error.png")
                    self.page.locator("agent-config-modal button", has_text="Cancel").click()
                    return False
            else:
                Util.warning_screenshot(f"'{agent_name}' is not deployed successfully or cannot be discovered by CT", self.page, "test_connection_bw6agent.png")
                return False

        else:
            ColorLogger.info(f"Domain '{agent_name}' is already registered.")
        return self.check_domain_status(agent_name, "BW6")

    def dp_config_ems(self, server_group_name):
        if ReportYaml.get_capability_info(ENV.TP_AUTO_K8S_BMDP_NAME, "EMSServer", server_group_name) in ("Added", "Connected"):
            ColorLogger.success(f"Dataplane '{ENV.TP_AUTO_K8S_BMDP_NAME}' capability EMSServer '{server_group_name}' is already added.")
            return
        ColorLogger.info("Config EMS Instance...")
        # switch to EMS Agents config page
        self.goto_dataplane_config_sub_menu("Messaging")
        if not Util.check_dom_visibility(self.page, self.ems_server_row(server_group_name), 3, 9, True):
            # add EMS Server
            self.click_register_new_instances()
            if self.is_yaml_registration_dialog():
                self.ems_register_by_yaml(server_group_name)
            else:
                # The legacy wizard warns and returns instead of exiting, so its outcome
                # has to be carried out here. Writing "Added" regardless - which is what
                # this method did before - records a server group that failed validation
                # as registered, and because "Added" short-circuits the check at the top
                # of this method, that lie is sticky across every later run.
                if not self.ems_register_by_wizard(server_group_name):
                    return
        else:
            ColorLogger.info(f"Domain '{server_group_name}' is already registered.")
        ReportYaml.set_capability(ENV.TP_AUTO_K8S_BMDP_NAME, "EMSServer")
        ReportYaml.set_capability_info(ENV.TP_AUTO_K8S_BMDP_NAME, "EMSServer", server_group_name, "Added")
        self.check_ems_server_status(server_group_name)

    def ems_server_row(self, server_group_name):
        """The row for one EMS server group in the Messaging list.

        Version-agnostic on purpose. CP 1.21 replaced the Plexus table with a PrimeNG
        p-datatable whose rows carry neither 'pl-table__row' nor 'pl-table__cell', so the
        old locator matched nothing and BOTH its callers failed quietly: the idempotency
        pre-check decided "not registered" on every run and re-registered, and
        check_ems_server_status() called .get_attribute() on None. `role=row` is the one
        thing the two tables agree on - <tr> carries it implicitly, and 1.21 also sets it
        explicitly - so one locator serves both.

        Anchored on the NAME CELL, not on the row's accessible name. `get_by_role("row",
        name=...)` matches that name by SUBSTRING, and a row's accessible name is its whole
        text - so a second group called `ems-latest-2` makes both rows match, and
        is_visible() then throws a strict-mode violation. That is the very defect class
        this change exists to remove, just moved from the dialog to the list. `exact=True`
        on the row name cannot fix it (the name is "ems-latest tcp://..." - exact would
        match nothing); matching a cell whose text is exactly the group name can, and works
        on both table generations: 1.21 puts it in an <a>, the Plexus table in a
        td.pl-table__cell, and either is a descendant of the row.
        """
        return self.page.get_by_role("row").filter(
            has=self.page.get_by_text(server_group_name, exact=True))

    def click_register_new_instances(self):
        """Open the EMS registration dialog.

        The accessible name is the primary hook because it is the one thing that survived
        the Plexus -> PrimeNG move: 1.21 renders
        button[aria-label='Register New Instances'], pre-1.21 renders a pl-button whose
        span gives the button the same name. The legacy class is kept as the fallback for
        any older shell whose button is named differently.
        """
        by_name = self.page.get_by_role("button", name=EMS_REGISTER_BUTTON_NAME)
        legacy = self.page.locator(EMS_REGISTER_BUTTON_LEGACY)
        if not self.wait_for_either_visible(by_name, legacy, 2, 30):
            Util.exit_error(
                f"'{EMS_REGISTER_BUTTON_NAME}' button never became visible on the Messaging page.",
                self.page, "ems_register_button.png"
            )
        # Decided on VISIBILITY, not presence: count() counts hidden nodes too, so a shell
        # that keeps a detached/hidden copy of either control would send the click at the
        # wrong one and then burn Playwright's actionability auto-wait on it.
        if by_name.first.is_visible():
            by_name.first.click()
        else:
            legacy.first.click()
        print("Clicked 'Register New Instances' button, to add a EMS Server instance")

    def is_yaml_registration_dialog(self):
        """Which registration UI did this Control Plane open - 1.21 YAML, or legacy wizard?

        Waits for WHICHEVER arrives rather than probing one and then the other: a
        sequential probe would spend the first probe's entire budget on every legacy run,
        and count() alone has no wait in it, so it would answer 0 while the dialog was
        still rendering (the mistake PCP-24309 shipped first time round).
        """
        editor = self.page.locator(EMS_YAML_EDITOR)
        wizard = self.page.locator(EMS_WIZARD_STEP, has_text=EMS_WIZARD_CAPABILITY)
        if not self.wait_for_either_visible(editor, wizard, 2, 30):
            Util.exit_error(
                "The EMS registration dialog opened neither the CP 1.21 YAML editor nor the legacy wizard.",
                self.page, "ems_register_dialog.png"
            )
        return editor.first.is_visible()

    def wait_for_either_visible(self, first, second, interval, max_wait):
        """True as soon as EITHER locator is visible, each checked independently.

        Deliberately NOT `first.or_(second).first`, which is what this replaced.
        `.or_()` builds the UNION and `.first` then narrows it to the DOM-FIRST match and
        reports that one element's visibility - so a hidden earlier match masks a visible
        later one and the wait fails on a page that is perfectly actionable, which is the
        exact failure mode this whole change exists to remove. Each side keeps its own
        `.first` so a multi-match on either cannot raise a strict-mode violation.

        Mirrors Util.check_dom_visibility's contract: polls, logs progress, returns a
        boolean so the caller can screenshot and exit gracefully.
        """
        attempts = max(1, max_wait // interval)
        for attempt in range(attempts):
            if first.first.is_visible() or second.first.is_visible():
                print("Dom is now visible.")
                return True
            print(f"--- Attempt {attempt + 1}/{attempts}: neither variant visible yet...")
            if attempt < attempts - 1:
                self.page.wait_for_timeout(interval * 1000)
        ColorLogger.warning(f"Neither variant became visible within {max_wait} seconds.")
        return False

    def ems_register_by_yaml(self, server_group_name):
        """CP 1.21: upload a generated payload, Validate, Register, Done.

        No step here keys on a success toast. CP 1.21 raises NONE for this flow -
        div[role='alert'][aria-label='success'], .pl-notification__message and the
        selectors behind Util.wait_for_success_message() all stayed empty for 24s after a
        registration that demonstrably succeeded. The row's own status text is the signal,
        and every step that cannot reach its expected status fails with a screenshot
        rather than falling through to the ReportYaml write that would record an
        unregistered server group as Added.
        """
        self.upload_ems_registration_yaml(server_group_name)

        # Anchored on the name cell for the same reason as ems_server_row(): a second
        # group whose name merely CONTAINS this one would otherwise match two rows here too.
        dialog_row = self.page.locator(EMS_DIALOG).get_by_role("row").filter(
            has=self.page.get_by_text(server_group_name, exact=True))
        if not Util.check_dom_visibility(self.page, dialog_row, 2, 30):
            Util.exit_error(
                f"The uploaded YAML did not parse into a '{server_group_name}' row in the registration dialog.",
                self.page, "ems_register_yaml.png"
            )

        self.page.locator(EMS_VALIDATE_ALL).click()
        print("Clicked 'Validate All' button")
        status = self.wait_for_ems_group_status(dialog_row, EMS_STATUS_VALIDATED, 120)
        if status != EMS_STATUS_VALIDATED:
            Util.exit_error(
                f"EMS server group '{server_group_name}' did not validate "
                f"(status: '{status or 'pending'}'); it is not reachable from the data plane.",
                self.page, "ems_validate_error.png"
            )

        # 'Register N Server Group(s)' only enables once something is validated. Clicking
        # it while it still reads 'Register 0 Server Groups' spends Playwright's whole
        # 30s auto-wait and then reports a bare click timeout, which says nothing about
        # the real problem.
        if not Util.check_dom_enabled(self.page, self.page.locator(EMS_REGISTER_GROUPS), 2, 30):
            Util.exit_error(
                f"The register button stayed disabled after '{server_group_name}' validated, "
                f"so there is nothing staged to register.",
                self.page, "ems_register_disabled.png"
            )
        self.page.locator(EMS_REGISTER_GROUPS).click()
        print("Clicked 'Register Server Groups' button")

        status = self.wait_for_ems_group_status(dialog_row, EMS_STATUS_REGISTERED, 120)
        if status != EMS_STATUS_REGISTERED:
            Util.exit_error(
                f"EMS server group '{server_group_name}' was not registered (status: '{status or 'pending'}').",
                self.page, "ems_register_error.png"
            )
        ColorLogger.success("EMS Server registration is successful.")

        # Guarded the same way the register button is, three lines up. The bare
        # click_button_until_enabled() this replaced raises a raw Playwright timeout with
        # NO screenshot, which was the one failure path in this method that produced no
        # artefact - directly contradicting the docstring above.
        if not Util.check_dom_enabled(self.page, self.page.locator(EMS_DONE), 2, 30):
            Util.exit_error(
                f"'Done' stayed disabled after '{server_group_name}' registered.",
                self.page, "ems_done_disabled.png"
            )
        self.page.locator(EMS_DONE).click()
        print("Clicked 'Done' button")
        self.wait_for_registration_dialog_closed()

    def wait_for_registration_dialog_closed(self):
        """Block until the registration modal is gone, before anyone reads the list.

        Not cosmetic. The dialog's result table holds a row named after the server group
        too, so for as long as it stays mounted the Messaging list lookup resolves to two
        rows and throws a strict-mode violation - which is how a registration that had
        completely succeeded still failed the run.
        """
        try:
            self.page.locator(EMS_DIALOG).wait_for(state="hidden", timeout=EMS_DIALOG_CLOSE_TIMEOUT_MS)
        except Exception:
            Util.exit_error(
                "The EMS registration dialog stayed open after 'Done'.",
                self.page, "ems_register_dialog_open.png"
            )

    def upload_ems_registration_yaml(self, server_group_name):
        """Write the generated payload to a temp file and hand it to the hidden file input."""
        payload = build_ems_registration_yaml(
            server_group_name,
            ENV.TP_AUTO_K8S_BMDP_BW5_EMS_SERVER_URL,
            ENV.TP_AUTO_K8S_BMDP_BW5_EMS_MONITOR_URL,
            ENV.TP_AUTO_K8S_BMDP_BW5_EMS_USERNAME,
            ENV.TP_AUTO_K8S_BMDP_BW5_EMS_PASSWORD,
        )
        if ENV.TP_AUTO_K8S_BMDP_BW5_EMS_PASSWORD:
            # Unlike the legacy wizard's input[type=password], the 1.21 dialog renders the
            # uploaded payload as plain text in the ace editor - so the always-on video,
            # the trace snapshots and any failure screenshot taken while the dialog is up
            # will contain this password. Say so rather than letting it be a surprise.
            # (Nothing leaks on the default path: the password defaults to empty and the
            # key is then omitted from the payload entirely.)
            ColorLogger.warning(
                "EMS registrationPass is set: CP 1.21 shows the uploaded YAML as plain text "
                "in the editor, so report video/trace/screenshots will contain it."
            )
        temp_dir = tempfile.mkdtemp(prefix="tp-auto-ems-")
        yaml_path = os.path.join(temp_dir, EMS_YAML_FILENAME)
        try:
            with open(yaml_path, "w", encoding="utf-8") as payload_file:
                payload_file.write(payload)
            self.page.locator(EMS_YAML_FILE_INPUT).set_input_files(yaml_path)
        finally:
            # The payload carries registrationPass, so it must not outlive the upload or
            # end up in a report artifact. set_input_files() has read the file by the time
            # it returns, so removing it here is safe.
            shutil.rmtree(temp_dir, ignore_errors=True)
            # ignore_errors swallows a failed delete, and a silently-undeleted credential
            # file is exactly the thing worth hearing about. Say it, don't fail the run:
            # the registration itself is fine, and aborting here would be worse.
            if os.path.exists(temp_dir):
                ColorLogger.warning(f"Could not delete the EMS registration payload: {yaml_path}")
        print(f"Uploaded EMS registration YAML for server group: {server_group_name}")
        print(f"Filled EMS Client URL: {ENV.TP_AUTO_K8S_BMDP_BW5_EMS_SERVER_URL}")
        print(f"Filled EMS Monitor URL: {ENV.TP_AUTO_K8S_BMDP_BW5_EMS_MONITOR_URL}")
        print(f"Filled EMS User Name: {ENV.TP_AUTO_K8S_BMDP_BW5_EMS_USERNAME}")

    def wait_for_ems_group_status(self, dialog_row, target, max_wait, interval=5):
        """Poll one dialog row until it reads `target`; return the status it settled on.

        Returns as soon as the row reads Error instead of burning the rest of the budget:
        Error is terminal, it does not recover into Validated (watched for 40s live). The
        caller turns a non-target status into a screenshot and a hard exit.
        """
        attempts = max(1, max_wait // interval)
        for attempt in range(attempts):
            status = self.ems_group_status(dialog_row)
            if status == target:
                print(f"EMS server group status: '{status}'")
                return status
            if status == EMS_STATUS_ERROR:
                ColorLogger.warning(f"EMS server group status: '{status}'")
                return status
            print(f"--- Attempt {attempt + 1}/{attempts}: EMS server group status is "
                  f"'{status or 'pending'}', waiting for '{target}'...")
            if attempt < attempts - 1:  # no point sleeping after the final read
                self.page.wait_for_timeout(interval * 1000)
        return self.ems_group_status(dialog_row)

    @staticmethod
    def ems_group_status(dialog_row):
        """Status text of one server-group row in the registration dialog, '' when blank."""
        status_cell = dialog_row.locator(EMS_ROW_STATUS)
        if status_cell.count() == 0:
            return ""
        return status_cell.first.inner_text().strip()

    def ems_register_by_wizard(self, server_group_name):
        """Pre-1.21: the multi-step form wizard. Returns True only on confirmed success.

        Every browser interaction is unchanged on purpose, down to the
        warning-instead-of-exit on failure: there is no pre-1.21 Control Plane on hand to
        re-verify it against, so the only safe edit is no edit, and the 1.21 path's hard
        exits are not retrofitted here.

        The ONE thing that changed is the return value, which touches no UI at all. The
        caller used to write ReportYaml "Added" whether or not this returned after a
        warning, so a failed legacy registration was recorded as registered - and since
        "Added" short-circuits dp_config_ems, it stayed wrong forever.
        """
        self.page.locator(EMS_WIZARD_STEP, has_text=EMS_WIZARD_CAPABILITY).wait_for(state="visible")
        self.page.locator(EMS_WIZARD_STEP, has_text=EMS_WIZARD_CAPABILITY).click()
        print("Clicked 'Enterprise Message Service' button")
        self.page.locator(EMS_WIZARD_STEP, has_text=EMS_WIZARD_REGISTER_SERVER).wait_for(state="visible")
        self.page.locator(EMS_WIZARD_STEP, has_text=EMS_WIZARD_REGISTER_SERVER).click()
        print("Clicked 'Register a Server' button")

        self.page.fill("input[name='groupName']", ENV.TP_BMDP_IMAGE_TAG_EMS)
        print(f"Filled EMS Server Name: {ENV.TP_BMDP_IMAGE_TAG_EMS}")

        # add EMS client url
        self.page.fill("input[name='clientUrl']", ENV.TP_AUTO_K8S_BMDP_BW5_EMS_SERVER_URL)
        print(f"Filled EMS Client URL: {ENV.TP_AUTO_K8S_BMDP_BW5_EMS_SERVER_URL}")
        # add EMS Monitor url
        self.page.fill("input[name='monitorUrl']", ENV.TP_AUTO_K8S_BMDP_BW5_EMS_MONITOR_URL)
        print(f"Filled EMS Monitor URL: {ENV.TP_AUTO_K8S_BMDP_BW5_EMS_MONITOR_URL}")
        # add EMS user
        self.page.fill("input[name='registrationUser']", ENV.TP_AUTO_K8S_BMDP_BW5_EMS_USERNAME)
        print(f"Filled EMS User Name: {ENV.TP_AUTO_K8S_BMDP_BW5_EMS_USERNAME}")
        # add EMS password
        self.page.fill("input[name='registrationPass']", ENV.TP_AUTO_K8S_BMDP_BW5_EMS_PASSWORD)
        # Redacted (from PR review). The value used to be printed in clear text, straight
        # into the pipeline log and any support bundle built from it. A log line is not a
        # browser interaction, so this is the one edit to the legacy path that carries no
        # behavioural risk at all - "keep the wizard verbatim" was never a reason to keep
        # leaking the password.
        print("Filled EMS Password: ***")

        # Validate Server
        self.page.locator("button.pl-button.pl-button--secondary.gemsButton", has_text="Validate Server").wait_for(state="visible")
        self.page.locator("button.pl-button.pl-button--secondary.gemsButton", has_text="Validate Server").click()
        print("Clicked 'Validate Server' button")

        if Util.check_dom_visibility(self.page, self.page.locator("div[role='alert'][aria-label='success']").first, 1, 10):
            self.page.locator("button.pl-button.pl-button--primary.gemsButton", has_text="Register Server").click()
            print("Clicked 'Register Server' button")
            if Util.check_dom_visibility(self.page, self.page.locator("div[role='alert'][aria-label='success']").first, 1, 10):
                ColorLogger.success("EMS Server registration is successful.")
                Util.click_button_until_enabled(self.page, self.page.locator("button.pl-button.pl-button--primary.gemsButton", has_text="Done"))
                print("Clicked 'Done' button")
                return True
            # Registered but never acknowledged - the same "not confirmed" bucket as a
            # failed validation, so it must not be reported as Added either.
            Util.warning_screenshot(f"'{server_group_name}' registration was not confirmed", self.page, "ems_register_error.png")
            return False
        Util.warning_screenshot(f"'{server_group_name}' is not registered successfully or not reachable", self.page, "ems_register_error.png")
        return False

    def check_ems_server_status(self, server_group_name):
        # Check the status of the EMS server
        ColorLogger.info(f"Checking EMS Server '{server_group_name}' status")
        ems_server_row = self.ems_server_row(server_group_name)
        if not ems_server_row.is_visible():
            ColorLogger.warning(f"EMS Server '{server_group_name}' is not connected.")
            return
        # Guarded because 1.21 renders no health icon at all while the row is still
        # settling; the old unguarded .get_attribute("href").split() turned that moment
        # into an AttributeError on None instead of a "not connected" warning.
        health_icon = ems_server_row.locator(EMS_HEALTH_ICON)
        if health_icon.count() == 0:
            ColorLogger.warning(f"EMS Server '{server_group_name}' is not connected.")
            return
        ems_health_svg = (health_icon.first.get_attribute("href") or "").split("#")[-1]
        if ems_health_svg == EMS_HEALTH_OK:
            ColorLogger.success(f"EMS Server '{server_group_name}' is connected.")
            ReportYaml.set_capability_info(ENV.TP_AUTO_K8S_BMDP_NAME, "EMSServer", server_group_name, "Connected")
            return
        ColorLogger.warning(f"EMS Server '{server_group_name}' is not connected.")

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
        # (PCP-23553). Without it, driving case/bmdp_config_dp_o11y.py directly with the
        # flag off used to be a no-op and would silently start performing the switch.
        if not ENV.TP_AUTO_IS_CONFIG_O11Y:
            ColorLogger.warning("TP_AUTO_IS_CONFIG_O11Y is false, skip switch to Global Observability Resource.")
            return
        ColorLogger.info(f"Switch dataplane {dp_name} configuration to Global...")
        self.goto_dataplane_o11y_config(dp_name)
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
            self.page.locator("button", has_text="Global configuration").click()
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
        if not Util.check_dom_visibility(self.page, self.page.locator(o11y_config_page_selector), 3, 9):
            Util.warning_screenshot(f"Data Plane '{dp_title}' Observability config load failed.", self.page, "o11y_config_dataplane_resource.png")

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
        if not Util.check_dom_visibility(self.page, self.page.locator("observability-configurations table tr", has=self.page.locator("td", has_text=name_input)), 3, 9):
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
                # Which of the three branches this sub-tab is; the value itself is built by
                # the shared helper so this wizard and the CLI/API path in
                # api_object/resources.py cannot drift apart (PCP-21434).
                if tab_sub_name == "Query Service" or tab_sub_name == "User Apps Exporter":
                    log_index_branch = O11Y_LOG_INDEX_USER_APPS
                # for PCP-16998
                elif tab_sub_name == "Business Activities Query Service" or tab_sub_name == "Business Activities Exporter":
                    log_index_branch = O11Y_LOG_INDEX_BUSINESS_ACTIVITIES
                else:
                    log_index_branch = O11Y_LOG_INDEX_DEFAULT
                log_index = o11y_log_index(log_index_branch, dp_title, name_input)
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
