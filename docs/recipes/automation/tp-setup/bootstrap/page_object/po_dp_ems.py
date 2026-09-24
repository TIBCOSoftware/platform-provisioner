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

import re

from utils.color_logger import ColorLogger
from utils.naming import capability_instance_name_pattern, storage_resource_candidates
from utils.util import Util
from utils.env import ENV
from utils.report import ReportYaml
from page_object.po_dataplane import PageObjectDataPlane

class PageObjectDataPlaneEMS(PageObjectDataPlane):
    capability = "ems"
    # CP 1.21 rebuilt the EMS provisioning wizard on the shared "fresco" modal (the one the Infra
    # MCP Server capability already uses). It opens on a new leading 'Server Configuration' step,
    # so '.resources-content' — the legacy wizard's first step, and what this flow used to wait on
    # — now only appears on its SECOND step. Both wizards stay supported: the flow waits for
    # whichever one renders and branches once. See PCP-23927.
    FRESCO_WIZARD_DIALOG = ".fresco-wizard-modal"
    FRESCO_WIZARD = ".fresco-wizard-modal-container"
    FRESCO_WIZARD_FOOTER = ".fresco-wizard-modal-footer-system-actions"
    FRESCO_WIZARD_FINAL_PAGE = ".fresco-wizard-modal-final-page"
    # Also the legacy wizard's first step, hence the shared name.
    RESOURCES_STEP = ".resources-content"
    # Whichever of the two renders after 'Start'. Comma selector, so callers must narrow it
    # with .first or Playwright strict mode trips once both are in the DOM (bootstrap/CLAUDE.md).
    EITHER_WIZARD = f"{FRESCO_WIZARD}, {RESOURCES_STEP}"

    def __init__(self, page):
        super().__init__(page)

    def ems_provision_capability(self, dp_name, ems_server_name):
        capability = self.capability
        if ReportYaml.is_capability_for_dataplane_created(dp_name, capability):
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, capability '{capability}' is already created in DataPlane '{dp_name}'.")
            return
        # The card is named for the EMS SERVER, with nothing appended (PCP-24380). This
        # used to read f"{ems_server_name}-dev", on the belief that the wizard's 'dev'
        # Server Use became part of the capability name. It does not: verified against a
        # live CP 1.21 Data Plane, the card reads `ems-sn` and
        # /cp/api/v1/data-planes/{dpId}/capabilities/instances returns
        # {"name":"ems-sn","capability":"EMS"} - no suffix, no separate display field.
        # Because has_text is a case-insensitive SUBSTRING match, "ems-sn-dev" is simply
        # not a substring of "ems-sn", so the gate below never fired and - worse -
        # ems_verify_capability() reached Util.exit_error() on every single run. The
        # ReportYaml short-circuit at the top of this method masked the first symptom;
        # it could not mask the second.
        capability_name = ems_server_name
        # Anchored, not bare: a Data Plane may legitimately hold `ems-sn` AND `ems-sn-2`,
        # and the gate below calls is_visible() unguarded, so a bare substring would match
        # both cards' tooltip triggers and raise a strict-mode violation instead of
        # answering.
        #
        # The anchor fixes THIS locator and nothing beyond it. It does not make the EMS GUI
        # path work with more than one EMS server on a Data Plane: is_capability_provisioned()
        # tests the OUTER `capability-card #ems` locator - no `.first`, no name filter -
        # before the pattern is ever applied, so two or more cards raise strict-mode there,
        # its `except Exception` swallows the error, and it answers False; the caller
        # (ems_verify_capability) then exits non-zero. Proven by A/B on a live CP 1.21: one
        # EMS card -> True, three EMS cards -> False with a strict-mode error in the log.
        # Pre-existing and deliberately out of scope for PCP-24380 - do not read the
        # anchoring as multi-EMS support.
        capability_name_pattern = capability_instance_name_pattern(capability_name)
        ColorLogger.info("EMS Provisioning capability...")
        self.goto_dataplane(dp_name)
        if self.page.locator("capability-card #ems .pl-tooltip__trigger", has_text=capability_name_pattern).is_visible():
            ColorLogger.success("EMS capability is already provisioned.")
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
            if not Util.check_dom_visibility(self.page, self.page.locator('#EMS-capability-select-button'), 5, 5):
                Util.warning_screenshot("EMS capability 'Start' button is not visible.", self.page, "ems_provision_capability-1.png")
                return
            Util.click_button_until_enabled(self.page, self.page.locator('#EMS-capability-select-button'))
            print("Clicked 'Provision TIBCO Enterprise Message Service™' -> 'Start' button")

            print("Waiting for EMS capability page is loaded")
            if not Util.check_dom_visibility(self.page, self.page.locator(self.EITHER_WIZARD).first, 3, 60):
                Util.exit_error("EMS provisioning wizard did not open.", self.page, "ems_provision_capability-3.png")
                return
            print("EMS capability page is loaded")
            self.page.wait_for_timeout(3000)

            # .first for the same reason the gate above has it: is_visible() on a multi-match
            # locator raises a strict-mode violation instead of answering the question, and a
            # leftover container from a prior mount is exactly what motivated scoping the
            # close button (PCP-23946).
            if self.page.locator(self.FRESCO_WIZARD).first.is_visible():
                print("Detected the CP 1.21+ Fresco EMS provisioning wizard")
                # ems_provision_fresco_wizard navigates back to the Data Plane detail page,
                # which is what ems_verify_capability expects.
                self.ems_provision_fresco_wizard(dp_name, ems_server_name)
                self.ems_verify_capability(dp_name, capability_name)
                return

            print("Detected the legacy EMS provisioning wizard")
            # step1: Resources
            if self.page.locator('#message-storage-resource-table').is_visible():
                self.legacy_select_storage('#message-storage-resource-table', "Message Storage", dp_name, is_required=True)

            if self.page.locator('#log-storage-resource-table').is_visible():
                self.legacy_select_storage('#log-storage-resource-table', "Log Storage", dp_name, is_required=False)

            self.page.locator("#btnNextCapabilityProvision", has_text="Next").click()
            print("Clicked EMS step 1 'Next' button")

            # step2: Configuration
            self.page.locator("#ems-config-capability-instance").wait_for(state="visible")
            print("Waiting for EMS configuration step 2 is loaded")
            self.page.fill("#ems-config-capability-instance", ems_server_name)
            print(f"Filled EMS 'Server Name' with '{ems_server_name}'")
            self.page.locator("label[for='ems-config-eula']").click()
            print("Clicked EMS 'EUA' checkbox")
            self.page.locator("#btn_next_configuration", has_text="Next").click()
            print("Clicked EMS step 2 'Next' button")

            # step3: Custom Config
            print("Skipped EMS step 3")

            # step4: Configuration
            self.page.locator("#btn_next_confirmation", has_text="Provision TIBCO Enterprise Message Service").click()
            print("Clicked EMS step 4 'Provision TIBCO Enterprise Message Service' button, waiting for EMS Capability Provision Request Completed")

            if Util.check_dom_visibility(self.page, self.page.get_by_text("EMS server is provisioned and ready to use!"), 5, 60):
                ColorLogger.success("Provision EMS capability successful.")
            self.page.locator("#btn_go_to_dta_pln").click()
            print("Clicked 'Go Back To Data Plane Details' button")
        else:
            Util.exit_error("'Provision a capability' button is not visible.", self.page, "ems_provision_capability.png")

        self.ems_verify_capability(dp_name, capability_name)

    def ems_verify_capability(self, dp_name, capability_name):
        print("Reload Data Plane page, and check if EMS capability is provisioned...")
        Util.refresh_page(self.page)
        print("Waiting for EMS capability is in capability list...")
        is_dataplane_container_available = Util.check_dom_visibility(self.page, self.page.locator(".data-plane-container"), 5, 20, True)
        # The card is created by the backend a little after the request is accepted, so poll
        # (with page refreshes) instead of asserting once — a single read here would report a
        # perfectly healthy provision as missing. Same budget as po_dp_activespace.py.
        # .first because a Data Plane may legitimately hold SEVERAL EMS servers, and
        # check_dom_visibility calls is_visible() unguarded — a multi-match locator would raise
        # a strict-mode violation instead of answering "is any EMS card present yet?"
        # (observed live with two EMS instances). The name-specific check follows below.
        is_capability_carded = is_dataplane_container_available and Util.check_dom_visibility(
            self.page, self.page.locator(f"capability-card #{self.capability}").first, 10, 180, True)
        # Anchored matcher, so the name check does not accept an `ems-sn-2` card as a match
        # for `ems-sn`. Built here rather than taken as an argument so both call sites keep
        # passing the plain name and the log lines keep reading it (PCP-24380).
        #
        # It does NOT make this path survive two or more EMS servers on one Data Plane. The
        # `.first` above gets the poll as far as "a card exists", but is_capability_provisioned()
        # then calls is_visible() on the un-narrowed OUTER `capability-card #ems` locator
        # before applying this pattern: that raises strict-mode, its `except Exception`
        # swallows the error, and it returns False - so the else branch below takes
        # Util.exit_error() and the run dies. Measured on a live CP 1.21: one card -> True,
        # three cards -> False. Pre-existing defect in the shared page object, left as-is
        # here on purpose; fixing it would change behaviour for every capability.
        if is_capability_carded and self.is_capability_provisioned(
                self.capability, capability_instance_name_pattern(capability_name)):
            ColorLogger.success(f"EMS capability {capability_name} is in capability list")
            ReportYaml.set_capability(dp_name, self.capability)
        else:
            # Not a warning: page_cli records the capability as provisioned as soon as this
            # returns, so warning here reports a green run for a Data Plane with no EMS. The
            # pipeline's retryCount can only act on a non-zero exit, and a retry is safe —
            # the entry-point card check at the top of ems_provision_capability makes the whole
            # method idempotent, so a re-run short-circuits once the card does appear.
            Util.exit_error(f"EMS capability {capability_name} is not in capability list", self.page, "ems_provision_capability-2.png")

    def ems_provision_fresco_wizard(self, dp_name, ems_server_name):
        """Drive the CP 1.21+ fresco EMS wizard: Server Configuration -> Resource Selection -> Summary.

        Every control on the 'Server Configuration' step carries a React generated id
        (fresco-<build hash>-_r_1_), so the form fields are located by their stable `name`
        attribute and the footer buttons by their exact label, as the Infra MCP Server
        wizard already does.
        """
        # Step 1: Server Configuration. 'Server Use' (dev), 'Server Sizing' (Small) and the
        # 'Development Environment' radio are pre-selected by the wizard, so this flow only
        # fills the server name. 'Server Use' does NOT feed the capability name - the card
        # and the CP API both report the bare server name; see the note in
        # ems_provision_capability() for how that was established (PCP-24380).
        print("Waiting for EMS 'Server Configuration' step is loaded")
        if not Util.check_dom_visibility(self.page, self.page.locator('input[name="serverName"]'), 3, 60):
            Util.exit_error("EMS 'Server Configuration' step is not loaded.", self.page, "ems_provision_capability-fresco-config.png")
            return
        self.page.fill('input[name="serverName"]', ems_server_name)
        print(f"Filled EMS 'Server Name' with '{ems_server_name}'")

        eula_checkbox = self.selector_fresco_eula_checkbox()
        if not Util.check_dom_visibility(self.page, self.page.locator(eula_checkbox), 2, 20):
            Util.exit_error("EMS 'End User Agreement' checkbox is not visible.", self.page, "ems_provision_capability-fresco-eula.png")
            return
        # PrimeNG renders the real <input> as a transparent overlay on the styled box, so it
        # fails Playwright's default actionability check; force the click and let check()
        # assert the resulting state (same reason as po_dp_activespace.py).
        self.page.locator(eula_checkbox).first.check(force=True)
        print("Checked EMS 'End User Agreement' checkbox")

        # Until the EUA is accepted 'Next' stays soft-disabled via CSS (pointer-events: none)
        # while still reporting disabled == false, so a wait keyed on the disabled property
        # passes and the click is then intercepted. Playwright's actionability auto-wait covers
        # the gap; give it room. Same quirk documented in po_dp_infra_mcp_server.py.
        self.fresco_click_footer_button("Next", "Server Configuration")

        # Step 2: Resource Selection. The Data Plane resources widget is embedded here, but it
        # renders its entries as radio lists ('<resource name> (<resource id>)') instead of the
        # #message-storage-resource-table / #log-storage-resource-table the legacy wizard shows.
        print("Waiting for EMS 'Resource Selection' step is loaded")
        if not Util.check_dom_visibility(self.page, self.page.locator(self.RESOURCES_STEP), 3, 60):
            Util.exit_error("EMS 'Resource Selection' step is not loaded.", self.page, "ems_provision_capability-fresco-resources.png")
            return
        self.fresco_select_resource("Message Storage", dp_name, True)
        self.fresco_select_resource("Log Storage", dp_name, False)
        self.fresco_click_footer_button("Next", "Resource Selection")

        # Step 3: Summary — the footer's confirm button is relabelled 'Provision Now'.
        print("Waiting for EMS 'Summary' step is loaded")
        self.fresco_click_footer_button("Provision Now", "Summary")
        print("Waiting for EMS Capability Provision Request Completed")

        # The final page shows 'Submitting provisioning request...' first, then
        # '<capability> provisioned successfully.' — matched on the stable half of that sentence.
        #
        # WARN, not fatal, and generous: this banner is a CONVENIENCE signal, not the
        # authority. The authority is the capability card, which ems_verify_capability polls
        # with refreshes and DOES fail on. Measured on a real deploy-subscription run
        # (2026-08-28): under concurrent capability provisioning the banner had not appeared
        # after 120s even though EMS provisioned fine — the next attempt found it already
        # there. Failing here therefore reported failure on a success, burned a ~5-minute
        # retry, and pointed at the wrong thing. An idle instance shows the banner in ~10s,
        # so the wide budget only ever costs time on a run that is genuinely in trouble.
        if Util.check_dom_visibility(self.page, self.page.locator(self.FRESCO_WIZARD_FINAL_PAGE, has_text="provisioned successfully"), 5, 240):
            ColorLogger.success("Provision EMS capability successful.")
        else:
            Util.warning_screenshot("EMS provisioning did not report success within 240s; deferring to the capability-card check.", self.page, "ems_provision_capability-fresco-final.png")

        # The final page only offers 'Go to TIBCO Enterprise Message Service™', which opens the
        # capability rather than going back, so close the wizard and return to the Data Plane
        # explicitly before the capability card is verified.
        self.page.locator(self.selector_fresco_dialog_close_button()).first.click()
        print("Closed EMS provisioning wizard")
        # Wait for the dialog to detach AND for its mask to clear, in that order — the same
        # sequence po_dp_activespace.py uses. A slow close animation can leave the modal
        # attached while the mask is already clearing, and either one still swallows the
        # left-nav click inside goto_dataplane — failing AFTER provisioning already succeeded.
        #
        # Non-fatal, matching wait_for_overlay_to_clear() on the very next line (PCP-23946):
        # both fire after provisioning has already succeeded and both are about a cosmetic
        # teardown, so a bare TimeoutError here would fail a run whose real work is done. The
        # capability-card check downstream stays the authority either way.
        try:
            self.page.locator(self.FRESCO_WIZARD_DIALOG).wait_for(state="detached", timeout=30000)
        except Exception:
            Util.warning_screenshot(
                "EMS wizard dialog did not detach after close; navigation may be blocked.",
                self.page, "ems_provision_capability-fresco-close.png")
        self.wait_for_overlay_to_clear()
        self.goto_dataplane(dp_name)

    def legacy_storage_row(self, table_id, resource_names=None):
        """Fresh locator for a row of the legacy wizard's storage table.

        Anchored at the START, and terminated by either the end of the cell or the ' ('
        that precedes a resource id. Anchoring is not optional: has_text is a SUBSTRING
        match, so an unanchored 'nfs' also matches an 'nfs-backup' row — and because the
        click re-runs this same filter and takes .first, that is a click on the WRONG
        resource, not merely a loose lookup. Every alternative carries its own anchors,
        for the same reason the fresco union does.

        Accepting BOTH terminators is deliberate. The pre-1.21 table is not available to
        inspect (no such Control Plane to test against) and the code it replaced used a
        bare substring match, which works for either rendering and so is no evidence of
        which one it is. Anchoring the END too would have been a TIGHTENING on an
        unverifiable path: a cell reading 'nfs (abc123)' — the shape the fresco list uses
        two screens over — matched before and would stop matching, turning a cosmetic DOM
        difference into a failed deploy on a legacy GUI-mode Data Plane that works today.
        This form keeps the 'nfs' vs 'nfs-backup' protection without betting on a
        rendering nobody here can check.
        With no names given, matches any row the table offers.
        """
        rows = self.page.locator(f'{table_id} tr')
        if resource_names:
            alternatives = "|".join(re.escape(name) for name in resource_names)
            rows = rows.filter(has=self.page.locator(
                'td', has_text=re.compile(rf"^\s*(?:{alternatives})\s*(?:\(|$)")))
        return rows

    def legacy_select_storage(self, table_id, section_title, dp_name, is_required):
        """Pick the Data Plane's storage resource in the legacy wizard's table.

        Same two-convention ambiguity as the fresco path, and the same fix (PCP-23953):
        the row is called '<dp>-storage' when CLI mode — or the Data Plane itself —
        provisioned the resource, and ENV.TP_AUTO_STORAGE_CLASS when GUI mode did.
        Matching only the latter left the locator with ZERO matches under
        TP_AUTO_USE_CLI=true, which turned the old unguarded wait_for(state="visible")
        into a bare 30s timeout with no screenshot.

        `is_required` mirrors the fresco path and is NOT optional: 'Message Storage' is a
        required field, and an earlier cut of this method warned for both sections. That
        let a missing required resource fall through to the '#btnNextCapabilityProvision'
        click below it — an unguarded timeout at best, and at worst EMS provisioned with
        no message storage, which the capability-card check cannot detect.

        Not live-verifiable: this branch only runs on pre-1.21 Control Planes and none is
        available to test against, so it is held to the fresco path's shape by tests.
        """
        candidates = storage_resource_candidates(dp_name)

        # Wait on the candidates as one union first — the table fills in asynchronously, so
        # resolving with count() straight away would race the render and report "missing".
        # Result deliberately ignored; see the fresco path for why count() decides, not the poll.
        Util.check_dom_visibility(self.page, self.legacy_storage_row(table_id, candidates).first, 2, 30)
        selected = next((name for name in candidates
                         if self.legacy_storage_row(table_id, [name]).count() > 0), None)

        if selected is None:
            # Same decision table as the fresco path, via the shared helper. The row count is
            # taken over `label` rather than `tr`, because `#tbl tr` also matches the header
            # row, which carries no selectable control.
            if not self.storage_degrade_or_fail(section_title, dp_name, is_required=is_required,
                                                candidates=candidates,
                                                rows=self.legacy_storage_row(table_id).locator('label'),
                                                kind="legacy"):
                return

        row = self.legacy_storage_row(table_id, [selected] if selected else None)
        bound = selected or self.storage_row_name(row.first)
        row.locator('label').first.click()
        print(f"Selected '{bound}' {section_title}")

    def fresco_click_footer_button(self, button_text, step_name):
        """Click a fresco wizard footer button, failing with a screenshot instead of a raw timeout.

        The footer buttons carry no ids, so they are matched by exact label. The generous
        click timeout absorbs the CSS soft-disable window described at the call sites.
        """
        selector = self.selector_fresco_footer_button(button_text)
        if not Util.check_dom_visibility(self.page, self.page.locator(selector), 3, 60):
            Util.exit_error(f"EMS '{step_name}' step '{button_text}' button is not visible.", self.page, "ems_provision_capability-fresco-footer.png")
            return
        self.page.locator(selector).click(timeout=60000)
        print(f"Clicked EMS '{step_name}' step '{button_text}' button")

    # storage_resource_candidates() lives in utils/naming.py so this wizard, the
    # ActiveSpaces one and the CLI EMS arm cannot drift apart over what the resource is
    # called (PCP-23953, PCP-24380). It used to be inherited from PageObjectDataPlane,
    # like wait_for_overlay_to_clear() still is; it moved down a layer when cli_object
    # needed it, because cli_object cannot import a page object without importing
    # Playwright with it.

    def fresco_select_resource(self, section_title, dp_name, is_required):
        """Select the Data Plane's storage resource in the named Resource Selection section."""
        candidates = storage_resource_candidates(dp_name)

        # Poll the ROW, not the radio: the radio is the transparent input under the styled box,
        # so an is_visible() poll on it can read false while the row is perfectly well rendered.
        # Wait on the candidates as one union so a slow-rendering list is waited out once.
        #
        # The poll's RESULT IS DELIBERATELY IGNORED and the resolution below re-reads with
        # count(). Gating on it would mean a candidate row that is present but not yet
        # is_visible() (mid fade-in, a collapsed section, a zero-box parent) drops into the
        # degradation branch and clicks a DIFFERENT resource — a wrong-config selection
        # dressed up as a warning. count() answers "is the right row in the DOM", which is
        # the question that decides which row to click; the poll only buys time for it.
        Util.check_dom_visibility(self.page, self.fresco_resource_row(section_title, candidates), 3, 30)
        selected = next((name for name in candidates
                         if self.fresco_resource_row(section_title, [name]).count() > 0), None)

        if selected is None:
            if not self.storage_degrade_or_fail(section_title, dp_name, is_required=is_required,
                                                candidates=candidates,
                                                rows=self.fresco_resource_rows(section_title),
                                                kind="fresco"):
                return

        row = self.fresco_resource_row(section_title, [selected] if selected else None)
        # Name the row BEFORE clicking it. On the fallback branch `selected` is None, and the
        # bound resource is precisely the thing nobody chose — logging 'first available' there
        # made the one case where the name matters most the vaguest line in the run.
        bound = selected or self.storage_row_name(row)
        # force=True for the same transparent-overlay reason as the EUA checkbox above.
        row.locator("input.p-radiobutton-input").check(force=True)
        print(f"Selected '{bound}' {section_title}")

    def storage_row_name(self, row):
        """Best-effort name of the row about to be selected, for the log line.

        Entries read '<name> (<id>)', so the id is trimmed. Never raises: this exists to
        make a fallback self-describing, and a logging aid must not be able to fail the
        provisioning step it is describing.
        """
        try:
            text = (row.inner_text() or "").strip()
        except Exception:
            return "first available"
        return text.split(" (")[0].strip() or "first available"

    def storage_degrade_or_fail(self, section_title, dp_name, is_required, candidates, rows, kind):
        """Decide what to do when no known naming convention matched. Returns True to fall
        through to "click the first row", False to give up on this section.

        Shared by both wizard paths so they cannot disagree about it. Three cases:

        1. **Nothing offered at all.** Required -> exit_error (a missing Message Storage is
           a real, reportable problem, and letting it through leaves the wizard blocked on a
           required field or — worse — provisions EMS with no message storage, which the
           capability-card check cannot detect). Optional -> warn and skip.
        2. **Exactly one row, unrecognised name.** Select it. There is no ambiguity to get
           wrong, and this is the case the degradation exists for: a naming change should
           not fail a deploy.
        3. **Several rows, none recognised.** Do NOT guess. Picking arbitrarily binds EMS to
           a storage resource nobody chose, and that surfaces far later and far more
           confusingly than an error naming what was actually on screen. Required -> fail
           with the offered names in the message; optional -> warn and skip. Leaving an
           OPTIONAL section unset is strictly safer than binding it to a guess.
        """
        rows_count = rows.count()
        screenshot = f"ems_provision_capability-{kind}-{section_title.lower().replace(' ', '-')}.png"

        if rows_count == 0:
            message = f"No storage resource is available in EMS '{section_title}', please check if one is provisioned in Data Plane '{dp_name}'"
        elif rows_count == 1:
            Util.warning_screenshot(f"None of {candidates} is offered in EMS '{section_title}'; it lists exactly one resource, selecting that.", self.page, screenshot)
            return True
        else:
            message = f"None of {candidates} is offered in EMS '{section_title}', and it lists {rows_count} resources, so there is no safe one to pick. Check the storage resource naming in Data Plane '{dp_name}'"

        if is_required:
            Util.exit_error(message, self.page, screenshot)
            return False
        Util.warning_screenshot(f"{message}. '{section_title}' is optional — leaving it unset rather than guessing.", self.page, screenshot)
        return False

    def fresco_resource_rows(self, section_title, resource_names=None):
        """Fresh locator for ALL matching resource rows, scoped to the section heading.

        Entries read '<resource name> (<resource id>)', so a row is matched on the name
        followed by the opening parenthesis — a bare substring would also match a resource
        that merely contains this one's name ('k8s-auto-dp1' would also hit
        'k8s-auto-dp10-storage'). Every alternative carries its own anchor: anchoring only
        the first one re-opens exactly that hole for the rest.
        With no names given, matches any row the section offers.

        Unnarrowed on purpose — the caller decides. `fresco_resource_row()` takes .first for
        polling and clicking (Playwright strict mode), while the degradation path needs the
        real count() to tell "one unambiguous row" from "several, none of them recognised".
        """
        rows = (self.page.locator("section.resources-section")
                .filter(has=self.page.locator("h3.resources-section__title", has_text=section_title))
                .locator("li.resources-section__item"))
        if resource_names:
            alternatives = "|".join(rf"{re.escape(resource_name)}\s*\(" for resource_name in resource_names)
            rows = rows.filter(has_text=re.compile(rf"^(?:{alternatives})"))
        return rows

    def fresco_resource_row(self, section_title, resource_names=None):
        """The single row to act on — .first, so a multi-match cannot trip strict mode."""
        return self.fresco_resource_rows(section_title, resource_names).first

    def selector_fresco_footer_button(self, button_text):
        # The wizard's footer buttons carry no ids, so they are matched by exact label
        # (:text-is, not a substring) scoped to the footer's action container.
        return f'{self.FRESCO_WIZARD_FOOTER} button:text-is("{button_text}")'

    def selector_fresco_eula_checkbox(self):
        # The checkbox carries no id, name or aria-label and its wrapper's CSS-module class is
        # build-hashed, so it is located by the stable library class inside the wizard. The
        # 'Server Configuration' step renders exactly one checkbox (the agreement).
        return f"{self.FRESCO_WIZARD} .fresco-check-box-container input.p-checkbox-input"

    def selector_fresco_dialog_close_button(self):
        # Scoped to the wizard's own dialog: a stray toast/confirmation elsewhere in the DOM
        # would otherwise make a bare '.p-dialog ...' match several nodes and trip strict mode.
        return f"{self.FRESCO_WIZARD_DIALOG} button.p-dialog-header-close"
