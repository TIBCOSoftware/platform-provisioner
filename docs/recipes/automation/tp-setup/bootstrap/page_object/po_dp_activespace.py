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
from utils.env import ENV
from utils.report import ReportYaml
from page_object.po_dataplane import PageObjectDataPlane

class PageObjectDataPlaneActiveSpaces(PageObjectDataPlane):
    """Provision the TIBCO ActiveSpaces (AS) capability on a Data Plane.

    Unlike EMS/Flogo, which use the multi-step Angular wizard (Resources -> Config ->
    Custom Config -> Confirm, all with stable element ids), ActiveSpaces provisions
    through a SINGLE-PAGE React ("fresco") modal: environment type + End User
    Agreement + the resources widget, then one 'Provision Now' button. That modal has
    no element ids and uses hashed CSS-module class names, so every selector below is
    anchored on a stable container class, an input `name`, an aria-label or visible
    text - never on a hashed class.
    """
    capability = "as"
    # The provisioned card shows the product name as its instance name (EMS instead
    # shows the server name the user typed), so it is a constant, not a parameter.
    capability_name = "ActiveSpaces"

    # Containers of the React provisioning modal. The dialog does NOT close on submit:
    # it swaps the form (`modal`) for a final success page (`modal_final_page`) and
    # stays up until dismissed, so all three are needed.
    modal_dialog = ".fresco-wizard-modal"
    modal = ".fresco-wizard-modal-content"
    modal_footer = ".fresco-wizard-modal-footer"
    modal_final_page = ".fresco-wizard-modal-final-page"

    def __init__(self, page):
        super().__init__(page)

    def selector_environment_radio(self, environment):
        # aria-label reads e.g. "Development Environment (best effort Kubernetes node
        # scheduling)"; match on the prefix so the parenthetical can change freely.
        return f"{self.modal} input.p-radiobutton-input[aria-label^='{environment} Environment']"

    def selector_storage_item(self, resource_name=""):
        # Each resource row is an <li> whose text is "<resource-name> (<resource-id>)".
        # NOTE: this matches one row PER SECTION (Message Storage, Log Storage), so any
        # caller doing is_visible()/click() on it must narrow it first (.first or a
        # control-name filter) to avoid a Playwright strict-mode violation.
        item = f"{self.modal} li.resources-section__item"
        if resource_name:
            item += f":has-text('{resource_name}')"
        return item

    def selector_storage_radio(self, control_name, resource_name=""):
        # The radio itself carries no text, so filter on the row and drill into it.
        return f"{self.selector_storage_item(resource_name)} input[name='{control_name}']"

    def selector_eua_checkbox(self):
        return f"{self.modal} .fresco-check-box-container input.p-checkbox-input"

    def selector_footer_button(self, button_text):
        return f"{self.modal_footer} button:text-is('{button_text}')"

    def selector_dialog_close_button(self):
        # The final page offers "Go to TIBCO ActiveSpaces®" (navigates to the
        # capability detail page) and the header close icon. Close is used so this
        # page object keeps control of where it navigates next.
        return f"{self.modal_dialog} button.p-dialog-header-close"

    def wait_for_overlay_to_clear(self, max_wait=30):
        """Wait until no dialog mask is covering the page.

        PrimeNG keeps the `.p-dialog-mask` on top of the page through the dialog's
        leave animation. The overlay swallows pointer events, so navigating too soon
        (the left nav click inside goto_dataplane) fails with a click timeout
        complaining that the mask "intercepts pointer events" - and by then
        provisioning has already succeeded, which makes it a particularly misleading
        failure. Observed live on CP 1.20.
        """
        overlay = ".p-dialog-mask"
        for _attempt in range(max_wait * 2):
            count = self.page.locator(overlay).count()
            if count == 0:
                return True
            # Check EVERY mask, not just the first: a hidden leftover stacked under a
            # still-visible one would otherwise read as "cleared" while clicks are
            # actually still being swallowed - the very bug this method exists to avoid.
            if not any(self.page.locator(overlay).nth(i).is_visible() for i in range(count)):
                return True
            self.page.wait_for_timeout(500)
        Util.warning_screenshot("A dialog overlay is still covering the page; navigation may be blocked.", self.page, "as_provision_capability-overlay.png")
        return False

    def select_storage_resource(self, section_title, control_name, dp_name):
        """Pick a storage resource for one section of the resources widget.

        Two storage-resource naming conventions exist in the wild, so both are tried
        before falling back to whatever is offered first:
          1. '<dp_name>-storage' - resources provisioned with the Data Plane itself
             (observed live on CP 1.20: "k8s-auto-dp1-storage (<id>)").
          2. ENV.TP_AUTO_STORAGE_CLASS - what this automation names the resource it
             creates in dp_config_resources_storage(), and what EMS filters on.
        Matching whole tokens matters: has-text is a SUBSTRING match, so filtering on a
        bare DP name 'k8s-auto-dp1' would also match a 'k8s-auto-dp10-storage' row.
        Returns False when the section offers no resource at all.
        """
        candidates = [f"{dp_name}-storage"]
        if ENV.TP_AUTO_STORAGE_CLASS:
            candidates.append(ENV.TP_AUTO_STORAGE_CLASS)

        selector = ""
        for resource_name in candidates:
            candidate = self.selector_storage_radio(control_name, resource_name)
            if self.page.locator(candidate).count() > 0:
                selector = candidate
                break
        if not selector:
            # Nothing matched a known naming convention - take the first row offered.
            selector = self.selector_storage_radio(control_name)
        if self.page.locator(selector).count() == 0:
            ColorLogger.warning(f"No resource available to select for '{section_title}'.")
            return False
        # PrimeNG renders the real <input> as a transparent overlay on the styled box,
        # so it fails Playwright's default visibility check; force the click and let
        # check() assert the resulting state.
        self.page.locator(selector).first.check(force=True)
        print(f"Selected '{section_title}' resource for ActiveSpaces")
        return True

    def accept_end_user_agreement(self):
        """Tick the mandatory EUA checkbox. Guarded like every other control in this
        flow: an unguarded check() on a zero-match locator raises a bare TimeoutError
        instead of the warn+screenshot+return the rest of the flow degrades with.
        Returns False when the checkbox is absent."""
        eua_checkbox = self.selector_eua_checkbox()
        if self.page.locator(eua_checkbox).count() == 0:
            return False
        self.page.locator(eua_checkbox).first.check(force=True)
        return True

    def as_provision_capability(self, dp_name, environment="Development"):
        capability = self.capability
        if ReportYaml.is_capability_for_dataplane_created(dp_name, capability):
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, capability '{capability}' is already created in DataPlane '{dp_name}'.")
            return

        ColorLogger.info("ActiveSpaces Provisioning capability...")
        self.goto_dataplane(dp_name)
        if self.page.locator(f"capability-card #{capability} .pl-tooltip__trigger", has_text=self.capability_name).is_visible():
            ColorLogger.success("ActiveSpaces capability is already provisioned.")
            ReportYaml.set_capability(dp_name, capability)
            return

        print("Checking if 'Provision a capability' button is visible.")
        if not Util.check_dom_visibility(self.page, self.page.locator('button', has_text="Provision a capability"), 10, 100):
            Util.exit_error("'Provision a capability' button is not visible.", self.page, "as_provision_capability.png")

        print("'Provision a capability' button is visible.")
        ColorLogger.success(f"Data Plane '{dp_name}' status is running.")
        self.page.locator('button', has_text="Provision a capability").click()
        print("Clicked 'Provision a capability' button")
        self.page.wait_for_timeout(2000)
        print("Waiting for capability list is loaded")
        self.page.locator(".capability-select-container").wait_for(state="visible")
        if not Util.check_dom_visibility(self.page, self.page.locator('#AS-capability-select-button'), 5, 5):
            Util.exit_error("ActiveSpaces capability 'Start' button is not visible.", self.page, "as_provision_capability-1.png")
        Util.click_button_until_enabled(self.page, self.page.locator('#AS-capability-select-button'))
        print("Clicked 'Provision TIBCO ActiveSpaces®' -> 'Start' button")

        # On control planes running an older tibco-cp-messaging (< 1.19.15) the AS tile
        # is listed but its dialog is not wired up, so nothing opens. Warn and skip
        # rather than time out deeper in the flow with a confusing error.
        if not Util.check_dom_visibility(self.page, self.page.locator(self.modal), 2, 30):
            Util.warning_screenshot("ActiveSpaces provisioning dialog did not open.", self.page, "as_provision_capability-2.png")
            return
        print("ActiveSpaces provisioning dialog is loaded")

        # The resources widget fetches the Data Plane's resources AFTER the dialog
        # renders. Every read below uses locator.count(), which is a point-in-time DOM
        # read with NO auto-waiting - without this poll a slow fetch would look like
        # "no storage resource" and silently abort a perfectly good provisioning run.
        # .first is REQUIRED: the widget renders one row per section (Message Storage,
        # Log Storage), so an unqualified locator resolves to several elements and
        # is_visible() inside check_dom_visibility raises a strict-mode violation.
        if not Util.check_dom_visibility(self.page, self.page.locator(self.selector_storage_item()).first, 3, 60):
            Util.exit_error("ActiveSpaces resources widget did not load any resource.", self.page, "as_provision_capability-3.png")

        # Environment type: 'Development' is preselected by the UI, but set it
        # explicitly so a change of default cannot silently alter what we provision.
        environment_radio = self.selector_environment_radio(environment)
        if self.page.locator(environment_radio).count() > 0:
            self.page.locator(environment_radio).first.check(force=True)
            print(f"Selected ActiveSpaces '{environment} Environment'")
        else:
            ColorLogger.warning(f"ActiveSpaces '{environment} Environment' option not found; keeping the UI default.")

        # Message Storage is mandatory, Log Storage is optional.
        if not self.select_storage_resource("Message Storage", "section-messageStorage", dp_name):
            Util.exit_error("ActiveSpaces 'Message Storage' has no resource to select.", self.page, "as_provision_capability-4.png")
        self.select_storage_resource("Log Storage", "section-logStorage", dp_name)

        if not self.accept_end_user_agreement():
            Util.exit_error("ActiveSpaces 'End User Agreement' checkbox not found; cannot accept the agreement.", self.page, "as_provision_capability-5.png")
        print("Checked ActiveSpaces 'End User Agreement' checkbox")

        Util.click_button_until_enabled(self.page, self.page.locator(self.selector_footer_button("Provision Now")))
        print("Clicked ActiveSpaces 'Provision Now' button, waiting for the provision request to complete")

        # The wizard does not close on submit - it swaps the form for a final page
        # reading "TIBCO ActiveSpaces(R) provisioned successfully." THAT is the
        # completion signal; the form detaching only means the request was sent.
        # Match on the plain-English part: the product name carries a (R) (U+00AE).
        if not Util.check_dom_visibility(self.page, self.page.locator(self.modal_final_page, has_text="provisioned successfully"), 5, 180):
            Util.exit_error("ActiveSpaces provisioning did not report success.", self.page, "as_provision_capability-6.png")
        ColorLogger.success("Provision ActiveSpaces capability successful.")

        # The success page stays up as a modal until dismissed, and its overlay
        # swallows pointer events - leaving it open makes the very next navigation
        # fail with a misleading "mask intercepts pointer events" click timeout,
        # AFTER provisioning has already succeeded.
        self.page.locator(self.selector_dialog_close_button()).click()
        print("Closed the ActiveSpaces provisioning dialog")
        self.page.locator(self.modal_dialog).wait_for(state="detached")
        self.wait_for_overlay_to_clear()

        print("Go to Data Plane page, and check if ActiveSpaces capability is provisioned...")
        self.goto_dataplane(dp_name)
        print("Waiting for ActiveSpaces capability is in capability list...")
        is_dataplane_container_available = Util.check_dom_visibility(self.page, self.page.locator(".data-plane-container"), 5, 20, True)
        # The card is created by the backend a little after the request is accepted, so
        # poll (with page refreshes) instead of asserting once.
        if is_dataplane_container_available and Util.check_dom_visibility(self.page, self.page.locator(f"capability-card #{capability}"), 10, 180, True):
            ColorLogger.success(f"ActiveSpaces capability {self.capability_name} is in capability list")
            ReportYaml.set_capability(dp_name, capability)
        else:
            # Not a warning: the pipeline's retryCount can only act on a non-zero exit,
            # and a retry is safe here - the entry-point card check makes the whole
            # method idempotent, so a re-run short-circuits once the card does appear.
            Util.exit_error(f"ActiveSpaces capability {self.capability_name} is not in capability list", self.page, "as_provision_capability-7.png")
