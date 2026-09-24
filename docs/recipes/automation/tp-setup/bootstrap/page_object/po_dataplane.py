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

import json
import re
from urllib.parse import urlparse

from page_object.po_global import PageObjectGlobal
from utils.color_logger import ColorLogger
from utils.util import Util
from utils.helper import Helper
from utils.env import ENV
from utils.report import ReportYaml

# 'Register Data Plane' step of the BMDP wizard. The registration commands sit behind the
# 'Display Details & Registration Commands' toggle: the Control Plane renders the container
# under an *ngIf whose flag starts false, so the container is absent from the DOM — not merely
# hidden — until the toggle is clicked and Angular has re-rendered.
BMDP_REGISTER_FINISHED_CONTENT = ".finished-main-content"
BMDP_REGISTER_DETAILS_TOGGLE = ".finished-main-content .main-actions .pl-button--no-border"
BMDP_REGISTER_DETAILS_TOGGLE_LEGACY = ".pl-button.pl-button--no-border .pl-button__text"
BMDP_REGISTER_COMMANDS_CONTAINER = ".expandable.register-commands-container"
# Legacy (1.4) registration panel, kept so older Control Planes still register.
BMDP_REGISTER_LEGACY_CONTENT = ".install-content"
# Matches a primary button on nearly every wizard page, so it is a diagnostic signal only and
# must never be allowed to decide that the registration step was reached.
BMDP_REGISTER_PRIMARY_BUTTON = ".pl-button.pl-button--primary .pl-button__text"
# The Done button of the registration step. Long-standing and clicked by this flow a few lines
# later, so it is a proven anchor and worth OR-ing into the registration-page gate.
BMDP_REGISTER_FINISHED_BUTTON = "#data-plane-finished-btn"

# Command titles the Control Plane renders on the registration page, in render order.
# k8s_run_dataplane_command keys on these exact strings to apply the per-step extras (helm repo
# reset, network policy / service account settings), so an unrecognised title means those extras
# are silently skipped — worth a loud warning, but not a reason to abort a valid registration.
BMDP_REGISTER_COMMAND_TITLES = (
    "1. Helm Repository configuration",
    "2. Namespace creation",
    "3. Service Account creation",
    "4. Cluster Registration",
)
# The Fresco wizard re-capitalised the first title to '1. Helm Repository Configuration', so the
# titles are compared case-insensitively everywhere. A silent miss here is expensive: the helm-repo
# reset and the network-policy / self-signed-cert extras all key on these exact strings.
BMDP_REGISTER_COMMAND_TITLES_FOLDED = tuple(t.casefold() for t in BMDP_REGISTER_COMMAND_TITLES)
HELM_REPO_COMMAND_TITLE = BMDP_REGISTER_COMMAND_TITLES[0]
SERVICE_ACCOUNT_COMMAND_TITLE = BMDP_REGISTER_COMMAND_TITLES[2]

# --- CP 1.21 Fresco Register-Data-Plane wizard (PCP-24237) ---------------------------------
# CP 1.21 rebuilt BOTH register wizards - 'Register Kubernetes Data Plane' and 'Register Control
# Tower Data Plane' - on the Fresco/PrimeNG dialog shell. The Pulse step nav '.pl-secondarynav
# a.is-active' the flows used to walk is not rendered at all any more, so every step wait timed
# out on the very first step. The legacy selectors are kept in full alongside these: old Control
# Planes are not deprecated on a schedule (bootstrap/CLAUDE.md principle 6).
FRESCO_WIZARD_STEP = ".fw-page-links .wizard-step"
# State is carried by a child div, not by a class on the step itself.
FRESCO_WIZARD_STEP_ACTIVE = "div.wizard-step-selected"
# Legacy step nav, still the anchor on Control Planes that have not migrated.
LEGACY_WIZARD_STEP_ACTIVE = ".pl-secondarynav a.is-active"
# Whichever of the two renders after the 'Start' button. Comma selector, so callers must narrow it
# with .first or Playwright strict mode trips once both are in the DOM (bootstrap/CLAUDE.md).
EITHER_REGISTER_WIZARD = f"{FRESCO_WIZARD_STEP}, {LEGACY_WIZARD_STEP_ACTIVE}"
# Off by default. With it off the wizard is only Basic -> Preview -> Generate Helm Commands, and
# the Control Plane silently defaults the namespace / service account to '<dp-name>-my-ns' /
# '<dp-name>-my-sa' - which is not what this automation registers against.
FRESCO_WIZARD_ADVANCED_TOGGLE = ".p-dialog-header .fw-toggle-container p-toggleswitch"
FRESCO_WIZARD_NEXT = 'tibco-button[data-testid="dp-register-wizard-next-button"] button'
# Labels of the steps this automation fills in, as the rail renders them. The advanced-only ones
# carry an 'ADV' badge on a second line, so labels are compared on their first line only. The
# remaining steps (Container Registry, Helm Chart Repository, Preview) arrive prefilled and are
# passed through by name-less default, so they deliberately have no constant here.
FRESCO_STEP_BASIC = "Basic"
FRESCO_STEP_NAMESPACE_SA = "Namespace & Service Account"
FRESCO_STEP_RESOURCES = "Resources"
FRESCO_STEP_CONFIGURATION = "Configuration"
# Steps that are verified to arrive fully prefilled by the Control Plane, so walking past them
# on its defaults is correct and unremarkable. Anything NOT on this list is passed through too
# - a Control Plane is free to add a step - but is logged as a warning, because the other way
# a step gets passed through is a label that drifted out from under its filler.
FRESCO_PREFILLED_STEPS = ("Container Registry", "Helm Chart Repository", "Preview")
# Final page: the step rail is gone and the registration commands are rendered here.
FRESCO_REGISTER_CONTENT = "helm-commands-list"
FRESCO_REGISTER_COMMAND_BLOCK = f"{FRESCO_REGISTER_CONTENT} .helm-cmd-block"
FRESCO_REGISTER_COMMAND_TITLE = f"{FRESCO_REGISTER_COMMAND_BLOCK} p.helm-cmd-title"
# The container holding each block's two action icons - download first, then copy. Its class is
# literally `copy`, which names the SECOND icon; the download one is reached positionally, as
# `.first` inside it. So this is honestly BOTH class-anchored (on a misleading name) and
# order-dependent - it is used because the icons carry no id, testid or aria-label, and reading
# the icon NAME instead would break bootstrap/CLAUDE.md principle 2. If the component ever swaps
# the order, `expect_download()` times out rather than quietly fetching the wrong thing.
FRESCO_REGISTER_ICON_CONTAINER = ".copy svg"
# Anchored on the visible text, not on being the first button in the footer: a footer that
# later gains a Back or 'Download all' button would otherwise have it clicked, and the flow
# would go on to record the registration as complete.
FRESCO_REGISTER_DONE_BUTTON = ".final-page-footer tibco-button button"
FRESCO_REGISTER_DONE_TEXT = "Done"
# Control Tower 'Resources' step. The two route-resource modes are NOT a relabelling of one
# form: picking Gateway API swaps the controller dropdown's form control AND replaces the whole
# field set (`#ctdp-ingress-*` + `#ctdp-fqdn-input` -> `#ctdp-gateway-*`), with Gateway Name and
# Gateway Namespace required and having no ingress-mode counterpart. Verified against the live
# step in both modes.
FRESCO_INGRESS_CONTROLLER_SELECT = 'tibco-select[formcontrolname="ingressController"]'
FRESCO_GATEWAY_CONTROLLER_SELECT = 'tibco-select[formcontrolname="gatewayApicontrollerName"]'
FRESCO_ROUTE_RESOURCE_GATEWAY_RADIO = "#dp-route-resource-type-radio-input-gateway"
FRESCO_ROUTE_RESOURCE_INGRESS_RADIO = "#dp-route-resource-type-radio-input-ingress"

# Completion marker, written by _mark_bmdp_complete once the cluster workload has been proven.
# A data plane name in report.yaml proves nothing on its own; this status is the only evidence
# that the data plane actually came up.
BMDP_STATUS_RUNNING = "Running successfully"
# The CLI registration path records health under its own key and never writes the status above,
# so a BMDP the CLI already built must still satisfy the guards here — otherwise the browser
# flow re-runs the whole wizard over a data plane that is already in place.
BMDP_HEALTH_STATUS_GREEN = "green"

class PageObjectDataPlane(PageObjectGlobal):
    def __init__(self, page):
        super().__init__(page)

    def goto_left_navbar_dataplane(self):
        self.goto_left_navbar("Data Planes")
        self.page.locator(".data-planes-content").wait_for(state="visible")
        print(f"Waiting for Data Planes page is loaded")
        self.detect_fresco_ui()

    def goto_global_dataplane(self):
        ColorLogger.info(f"Going to Global Data Plane...")
        self.goto_left_navbar_dataplane()
        # wait for 1 second
        self.page.wait_for_timeout(1000)

        self.page.locator("button", has_text="Global configuration").click()
        print("Clicked 'Global configuration' button")
        self.page.locator('breadcrumbs a', has_text="Global configuration").wait_for(state="visible")
        print(f"Navigated to Global Data Plane page")

    def goto_dataplane(self, dp_name):
        ColorLogger.info(f"Going to k8s Data Plane '{dp_name}'...")
        self.goto_left_navbar_dataplane()
        is_dataplane_visible = Util.refresh_until_success(self.page,
                                                          self.page.locator('.data-plane-name', has_text=dp_name),
                                                          self.page.locator(".data-planes-content"),
                                                          "DataPlane list page is load.")

        if is_dataplane_visible:
            self.page.locator('data-plane-card', has=self.page.locator('.data-plane-name', has_text=dp_name)).locator('button', has_text="Go to Data Plane").click()
            print("Clicked 'Go to Data Plane' button")
            self.page.wait_for_timeout(2000)
            nav_dp_selector = ".domain-data-title"
            if self.is_fresco:
                nav_dp_selector = "tibco-header .header-title-readonly-text"

            # waiting_selector must be the page CONTAINER, not the element being retried for
            # (PCP-24228): refresh_until_success does waiting_selector.wait_for(state="visible")
            # after each reload, so passing the retry target here made the inner retry cancel
            # itself out - it threw at the 30s default instead of returning False. Same shape as
            # the '.data-planes-content' container used for the list page above.
            is_dataplane_detail_visible = Util.refresh_until_success(self.page,
                                                                     self.page.locator(nav_dp_selector, has_text=dp_name),
                                                                     self.page.locator(".data-plane-container"),
                                                                     f"DataPlane '{dp_name}' detail page is load.")
            if is_dataplane_detail_visible:
                print(f"Navigated to Data Plane '{dp_name}' detail page")
                ReportYaml.set_dataplane(dp_name)
                self.page.wait_for_timeout(1000)
            else:
                Util.exit_error(f"DataPlane {dp_name} detail page is not load.", self.page, "goto_dataplane.png")

        else:
            Util.exit_error(f"DataPlane {dp_name} does not exist", self.page, "goto_dataplane.png")

    def goto_capability(self, dp_name, capability, capability_selector_path, is_check_status=True):
        ColorLogger.info(f"{capability} Going to capability...")
        self.goto_dataplane(dp_name)
        print(f"Check if {capability} capability is ready...")
        card_id = capability.lower()
        if Util.check_dom_visibility(self.page, self.page.locator(f"capability-card #{card_id}"), 10, 120, True):
            ColorLogger.success(f"{capability} capability is already provisioned.")
            ReportYaml.set_capability(dp_name, capability)
            print(f"Waiting for {capability} capability status is ready...")
            is_capability_success = Util.check_dom_visibility(self.page, self.page.locator(f"capability-card #{card_id} .status .success"))
            if not is_check_status or is_capability_success:
                self.page.locator(f"capability-card #{card_id} .image-name").click()
                print(f"Clicked '{capability}' capability")
                self.page.wait_for_timeout(3000)
                if not is_check_status:
                    print(f"Ignore check '{capability}' capability status, get into '{capability}' capability page")
                if is_capability_success:
                    print(f"{capability} capability status is ready")

                is_capability_loaded = Util.refresh_until_success(self.page,
                                                                  self.page.locator(capability_selector_path),
                                                                  self.page.locator(capability_selector_path),
                                                                  f"{capability} capability detail page is loaded")
                if is_capability_loaded:
                    print(f"Navigated to {capability} capability detail page")
                    self.page.wait_for_timeout(1000)
                else:
                    Util.exit_error(f"{capability} capability page is not loaded.", self.page, f"{card_id}_goto_capability.png")
            else:
                Util.exit_error(f"{capability} capability is provisioned, but status is not ready.", self.page, f"{card_id}_goto_capability.png")
        else:
            Util.exit_error(f"{capability} capability is not provisioned yet.", self.page, f"{card_id}_goto_capability.png")

    def goto_app_detail(self, dp_name, app_name, app_selector_path):
        ColorLogger.info(f"Going to app '{app_name}' detail page")
        self.goto_dataplane(dp_name)
        is_app_visible = Util.refresh_until_success(self.page,
                                                    self.page.locator("apps-list td.app-name a", has_text=app_name),
                                                    self.page.locator("apps-list td.app-name a", has_text=app_name),
                                                    "App detail page is load.")
        if is_app_visible:
            self.page.locator("apps-list td.app-name a", has_text=app_name).click()
            print(f"Clicked app '{app_name}'")
            self.page.locator(app_selector_path, has_text=app_name).wait_for(state="visible")
            print(f"Navigated to app '{app_name}' detail page")
            self.page.wait_for_timeout(500)
        else:
            Util.exit_error(f"The app '{app_name}' is not deployed yet.", self.page, "goto_app_detail.png")

    # storage_resource_candidates() used to live here, so the EMS and ActiveSpaces wizards
    # could not disagree about the name (PCP-23953). It has moved one layer down, to
    # utils/naming.py, because the CLI EMS arm added in PCP-24380 must ask the same
    # question and cli_object cannot import a page object without importing Playwright
    # with it. Both wizards now call the shared function directly.

    def wait_for_overlay_to_clear(self, max_wait=30):
        """Wait until no dialog mask is covering the page.

        PrimeNG keeps the `.p-dialog-mask` on top of the page through the dialog's
        leave animation. The overlay swallows pointer events, so navigating too soon
        (the left nav click inside goto_dataplane) fails with a click timeout
        complaining that the mask "intercepts pointer events" - and by then
        provisioning has already succeeded, which makes it a particularly misleading
        failure. Observed live on CP 1.20.

        Shared by every fresco/PrimeNG wizard that dismisses a dialog and then
        navigates: ActiveSpaces (PCP-21284) and EMS (PCP-23927).
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
        Util.warning_screenshot("A dialog overlay is still covering the page; navigation may be blocked.", self.page, "provision_capability-overlay.png")
        return False

    # --- Fresco Register-Data-Plane wizard (CP 1.21+, PCP-24237) ----------------------------
    # Shared by the Kubernetes and the Control Tower flows: the two differ only in which steps
    # the rail shows and what each step asks for, so the walk itself is written once here and
    # each flow supplies a {step label -> filler} map.

    def is_fresco_register_wizard(self):
        """Is the open register wizard the CP 1.21+ Fresco one?

        `.first` for the reason the EMS gate has it: is_visible() on a locator that matches
        several elements raises a strict-mode violation instead of answering the question, and
        the rail is a multi-element selector by construction (one node per step).
        """
        return self.page.locator(FRESCO_WIZARD_STEP).first.is_visible()

    def fresco_wizard_enable_advanced(self):
        """Switch 'Show Advanced' on and prove the advanced steps appeared.

        Failing loudly here matters more than it looks: with the toggle off the wizard still
        completes, but against the Control Plane's own default namespace and service account.
        The registration would 'succeed' into the wrong namespace and only surface much later,
        as a data plane that never connects.
        """
        # Waited for, not counted. `count()` does not auto-wait, and this fires as the dialog
        # is still mounting - a header that paints a beat after the step rail would otherwise
        # kill a ~98-minute deploy on a transient render (principle 5). Re-queried on every
        # line rather than cached across the count / attribute read / click, because the wait
        # in between is exactly where a live-re-rendering node goes stale (principle 4).
        if not Util.check_dom_visibility(self.page, self.page.locator(FRESCO_WIZARD_ADVANCED_TOGGLE).first, 2, 10):
            Util.exit_error("Fresco register wizard has no 'Show Advanced' toggle; the namespace and service account cannot be set.",
                            self.page, "fresco_register_advanced_missing.png")
            return

        if self.page.locator(FRESCO_WIZARD_ADVANCED_TOGGLE).first.get_attribute("data-p-checked") == "true":
            print("'Show Advanced' is already on")
        else:
            self.page.locator(FRESCO_WIZARD_ADVANCED_TOGGLE).first.click()
            print("Turned on 'Show Advanced', to reveal the namespace / service account / configuration steps")

        advanced_step = self.page.locator(FRESCO_WIZARD_STEP, has_text=FRESCO_STEP_NAMESPACE_SA)
        if not Util.check_dom_visibility(self.page, advanced_step.first, 2, 10):
            Util.exit_error(
                f"'Show Advanced' did not reveal the '{FRESCO_STEP_NAMESPACE_SA}' step; the data plane would be "
                f"registered against the Control Plane's default namespace and service account.",
                self.page, "fresco_register_advanced_no_steps.png")

    def fresco_wizard_active_step(self):
        """Label of the step the rail currently marks active, or '' once the rail is GONE.

        The terminator is the rail disappearing, not merely "no step is marked active" - those
        are different conditions and conflating them ends the walk early. Angular re-renders
        the rail on each Next, so for a frame the `.wizard-step` nodes exist with no
        `div.wizard-step-selected` child; `count()` is an instantaneous poll, so landing in
        that frame used to read as "the wizard finished".

        It was contained rather than silent - the walk would return, `fresco_run_register_commands`
        would find no final page and exit loudly - but it turned a transient render into a
        failed ~98-minute pipeline, and if it landed before the last filler the completeness
        check fired instead, sending the reader after a label drift that never happened.

        So: rail gone -> ''. Rail present but unmarked -> give it one more beat, and only then
        conclude. Still present and still unmarked after that is a wizard in a state this flow
        does not understand, which is worth saying rather than guessing.
        """
        active = self.page.locator(FRESCO_WIZARD_STEP, has=self.page.locator(FRESCO_WIZARD_STEP_ACTIVE))
        if active.count() == 0:
            if self.page.locator(FRESCO_WIZARD_STEP).count() == 0:
                return ""
            self.page.wait_for_timeout(1000)
            if self.page.locator(FRESCO_WIZARD_STEP).count() == 0:
                return ""
            if self.page.locator(
                    FRESCO_WIZARD_STEP, has=self.page.locator(FRESCO_WIZARD_STEP_ACTIVE)).count() == 0:
                Util.exit_error(
                    "Fresco register wizard still shows its step rail but marks no step active; "
                    "the wizard did not finish and the walk cannot tell which step it is on.",
                    self.page, "fresco_register_no_active_step.png")
                return ""
        # Advanced-only steps render an 'ADV' badge on a second line; the label is the first.
        return self.page.locator(
            FRESCO_WIZARD_STEP,
            has=self.page.locator(FRESCO_WIZARD_STEP_ACTIVE)).first.inner_text().strip().split("\n", 1)[0].strip()

    def fresco_wizard_next(self, step_label):
        """Advance one step. The button reads 'Next' throughout and 'Save' on Preview.

        Every failure here exits: a wizard that cannot be advanced has not registered
        anything, and returning quietly would let the caller fall through to a clean logout
        and an exit code of 0 - the exact silent success this ticket exists to remove.

        The locator is re-queried on every line (bootstrap/CLAUDE.md principle 4): the
        disabled check and the click must not be able to straddle an Angular re-render and
        act on different elements.
        """
        if self.page.locator(FRESCO_WIZARD_NEXT).count() == 0:
            Util.exit_error(f"Fresco register wizard has no Next button on step '{step_label}'; it cannot be advanced.",
                            self.page, "fresco_register_next_missing.png")
            return

        # is_disabled() rather than get_attribute("disabled"): PrimeNG also disables through
        # `aria-disabled` / a `p-disabled` class, and a button disabled that way would be
        # clicked, do nothing, and burn every remaining iteration on the same step.
        if self.page.locator(FRESCO_WIZARD_NEXT).first.is_disabled():
            Util.exit_error(f"Fresco register wizard is stuck on step '{step_label}': its Next button is disabled, so a required field was not filled.",
                            self.page, "fresco_register_next_disabled.png")
            return

        label = self.page.locator(FRESCO_WIZARD_NEXT).first.inner_text().strip()
        self.page.locator(FRESCO_WIZARD_NEXT).first.click()
        print(f"Clicked '{label}', finished step '{step_label}'")
        self.page.wait_for_timeout(3000)

    @staticmethod
    def _normalise_step_label(label):
        """Fold a step label so the rail's spelling cannot decide whether a step is filled.

        The 'Show Advanced' guard matches with Playwright's `has_text`, which is a
        case-insensitive substring; the walk used to match with `==`. That gap was enough for
        a re-capitalised label - 'Namespace & Service account', the spelling the LEGACY wizard
        uses - to satisfy the guard and then silently skip its filler, registering the data
        plane against the Control Plane's own default namespace. Both now compare folded.
        """
        return " ".join(label.split()).casefold()

    @classmethod
    def _prefilled_step_keys(cls):
        return {cls._normalise_step_label(name) for name in FRESCO_PREFILLED_STEPS}

    def fresco_wizard_walk(self, fillers, max_steps=15):
        """Walk the wizard to its final page, running `fillers[step]` on each step that has one.

        Keyed on the rail's own labels rather than on a fixed order, so a Control Plane that
        adds, removes or reorders a step still walks through: an unknown step is passed through
        untouched, and if it actually needed input the disabled Next button stops the run with
        that step's name instead of a bare timeout.

        Passing an unknown step through is only safe because of the completeness check at the
        end: every filler the caller supplied must have fired. Without it, a step whose label
        drifts reads as 'nothing to do here' and the wizard completes on the Control Plane's
        defaults - which is precisely how this defect would come back.

        `max_steps` only bounds the loop; the real terminator is the rail disappearing.
        """
        wanted = {self._normalise_step_label(name): fn for name, fn in fillers.items()}
        # Folded once, not per iteration. It stays a method rather than a module constant so
        # the folding rule has exactly one home (`_normalise_step_label`), which matters more
        # than where the set literal lives.
        prefilled = self._prefilled_step_keys()
        fired = set()

        for _ in range(max_steps):
            step = self.fresco_wizard_active_step()
            if step == "":
                self._assert_every_filler_fired(fillers, fired)
                return

            key = self._normalise_step_label(step)
            filler = wanted.get(key)
            if filler is None:
                if key in prefilled:
                    print(f"Step '{step}' arrives prefilled by the Control Plane, passing through")
                else:
                    # Warn only for a step nobody has verified. Warning on the three known
                    # prefilled ones every single run would train the reader to skip the line
                    # that matters - the one naming a step that should not be there.
                    ColorLogger.warning(f"Fresco register wizard step '{step}' is not one this automation fills or has verified as prefilled; passing through on the Control Plane's defaults.")
            else:
                print(f"Filling step '{step}'")
                fired.add(key)
                filler()

            self.fresco_wizard_next(step)

        Util.exit_error(f"Fresco register wizard did not reach its final page within {max_steps} steps.",
                        self.page, "fresco_register_too_many_steps.png")

    def _assert_every_filler_fired(self, fillers, fired):
        """Fail if the wizard finished without ever presenting a step this flow must fill."""
        missing = sorted(name for name in fillers if self._normalise_step_label(name) not in fired)
        if missing:
            Util.exit_error(
                f"Fresco register wizard finished without presenting step(s) {missing}; the data plane "
                f"would be registered against the Control Plane's defaults.",
                self.page, "fresco_register_step_missing.png")

    def fresco_check_eula(self):
        """Tick the End User Agreement box.

        The checkbox id is generated per mount (`tibco-checkbox-<uuid>-3`), and so is the `for`
        of its label, so neither can be selected by id. The form control name is the stable
        handle the Control Plane binds it under.

        A plain `.check()`, unlike the `.check(force=True)` the Control Tower flavour radio
        needs. That is deliberate, not an oversight: this checkbox passes Playwright's
        actionability checks on the live wizard, so keeping them is worth more than matching
        its neighbour. `force=True` would skip exactly the check that would tell us the box had
        become unclickable.
        """
        self.page.locator('tibco-checkbox[formcontrolname="eula"] input.p-checkbox-input').check()
        print("Accepted the End User Agreement")

    def fresco_fill_by_form_control(self, form_control, value, label):
        """Fill an input whose id is generated per mount, via its stable formcontrolname."""
        self.page.locator(f'tibco-inputtext[formcontrolname="{form_control}"] input').fill(value)
        print(f"Input {label}: {value}")

    def fresco_register_command_titles(self):
        """Titles of the command blocks on the final page, in render order."""
        return [t.strip() for t in self.page.locator(FRESCO_REGISTER_COMMAND_TITLE).all_text_contents()]

    def fresco_register_download_locator(self, index):
        """Download icon of the index-th command block.

        Scoped to its own block so the title -> button pairing cannot drift, which would run the
        wrong script for a step. The download icon is the FIRST of the block's two icons; the
        second is Copy.
        """
        return self.page.locator(FRESCO_REGISTER_COMMAND_BLOCK).nth(index).locator(FRESCO_REGISTER_ICON_CONTAINER).first

    def fresco_run_register_commands(self, dp_name):
        """Run every command the final page renders, each under its own real title."""
        if not Util.check_dom_visibility(self.page, self.page.locator(FRESCO_REGISTER_CONTENT).first, 3, 60):
            return False

        commands_title = self.fresco_register_command_titles()
        print("commands_title:", commands_title)
        if not commands_title:
            Util.exit_error(f"Data Plane '{dp_name}' registration page produced no commands to run.",
                            self.page, "fresco_register_commands_empty.png")
            return False

        block_count = self.page.locator(FRESCO_REGISTER_COMMAND_BLOCK).count()
        if block_count != len(commands_title):
            Util.exit_error(
                f"Data Plane '{dp_name}' registration page has {len(commands_title)} command title(s) but "
                f"{block_count} command block(s); refusing to run mismatched commands.",
                self.page, "fresco_register_commands_mismatch.png")
            return False

        for index, step_name in enumerate(commands_title):
            if step_name.casefold() not in BMDP_REGISTER_COMMAND_TITLES_FOLDED:
                ColorLogger.warning(f"Unrecognised registration command title '{step_name}'; running it as-is, but no per-step extras will be applied to it.")
            self.k8s_run_dataplane_command(dp_name, step_name, self.fresco_register_download_locator(index), index + 1)

        print(f"Executed {len(commands_title)} registration command(s) for Data Plane '{dp_name}'")
        return True

    def fresco_register_click_done(self):
        """Close the final page. Unlike the legacy wizard there is no 'Yes' confirmation after it."""
        self.page.locator(FRESCO_REGISTER_DONE_BUTTON, has_text=FRESCO_REGISTER_DONE_TEXT).first.click()
        print("Data Plane create successful, clicked 'Done' button")
        self.wait_for_overlay_to_clear()

    def is_capability_provisioned(self, capability, capability_name=""):
        ColorLogger.info(f"Checking if '{capability}' is provisioned")
        # `capability_name` may be a compiled pattern as well as a plain string. EMS passes
        # one (PCP-24380): has_text is a case-insensitive SUBSTRING match and a Data Plane
        # may legitimately hold both `ems-sn` and `ems-sn-2`, so a bare name would let the
        # tooltip check below accept the wrong card. Only the log lines care which form it
        # is, hence the one-line unwrap rather than two code paths.
        #
        # KNOWN DEFECT, pre-existing and deliberately NOT fixed here. That pattern guards
        # only the INNER tooltip locator. The OUTER `capability-card #{card_id}` check below
        # has no `.first` and no name filter, so on a Data Plane holding two or more
        # instances of one capability - EMS is the capability that can have them -
        # is_visible() raises a Playwright strict-mode violation, the `except Exception` at
        # the bottom of this method swallows it, and the answer comes back False. For EMS
        # that False reaches po_dp_ems.ems_verify_capability(), which calls
        # Util.exit_error() -> sys.exit(1). Measured by QA against a live CP 1.21: one EMS
        # card -> True, three EMS cards -> False with the strict-mode error in the log. So
        # the GUI verification path does not work with several EMS servers on one Data
        # Plane. Narrowing this locator would change behaviour for every capability that
        # calls this method, which is why it belongs to its own ticket rather than to
        # PCP-24380.
        display_name = getattr(capability_name, "pattern", capability_name)
        try:
            print(f"Checking if '{capability}' is already provisioned...")
            card_id = capability.lower()
            self.page.wait_for_timeout(3000)
            if self.page.locator(f"capability-card #{card_id}").is_visible():
                ColorLogger.success(f"'{capability}' is already provisioned.")
                if capability_name == "":
                    return True
                else:
                    if self.page.locator(f"capability-card #{card_id} .pl-tooltip__trigger", has_text=capability_name).is_visible():
                        ColorLogger.success(f"'{capability}' with name '{display_name}' is provisioned.")
                        return True
                    else:
                        ColorLogger.warning(f"'{capability}' with name '{display_name}' has not been provisioned.")
                        return False
            else:
                ColorLogger.warning(f"'{capability}' has not been provisioned.")
                return False
        except Exception as e:
            ColorLogger.warning(f"An error occurred while Checking capability '{capability}': {e}")
            return False

    def is_app_created(self, capability, app_name):
        ColorLogger.info(f"Checking if {capability} app '{app_name}' is created")
        # Guard against a missing app_name: with has_text=None Playwright applies no text
        # filter, so the locator matches every app row and is_visible() raises a strict-mode
        # violation ("resolved to N elements"). No app name => nothing to check => not created.
        if not app_name:
            print(f"No app_name provided for capability '{capability}', treating as not created.")
            return False
        try:
            print(f"Checking if {capability} app '{app_name}' is already created...")
            self.page.locator("apps-list").wait_for(state="visible")
            self.page.wait_for_timeout(3000)
            if self.page.locator("#app-list-table tr.pl-table__row td.app-name", has_text=app_name).is_visible():
                ColorLogger.success(f"{capability} app '{app_name}' is already created.")
                return True
            else:
                print(f"{capability} app '{app_name}' has not been created.")
                return False
        except Exception as e:
            ColorLogger.warning(f"An error occurred while Checking {capability} app '{app_name}': {e}")
            return False

    def is_app_running(self, dp_name, capability, app_name):
        ColorLogger.info(f"Checking if {capability} app '{app_name}' is running")
        try:
            self.goto_dataplane(dp_name)
            print(f"Checking if {capability} app '{app_name}' is already running...")
            self.page.wait_for_timeout(3000)
            if self.page.locator(f"#app-list-table tr.{capability.upper()}", has=self.page.locator("td.app-name", has_text=app_name)).locator("td", has_text="Running").is_visible():
                ColorLogger.success(f"{capability} app '{app_name}' is already running.")
                ReportYaml.set_capability_app_info(dp_name, capability, app_name, "status", "Running")
                return True
            else:
                print(f"{capability} app '{app_name}' has not been running.")
                return False
        except Exception as e:
            ColorLogger.warning(f"An error occurred while Checking {capability} app '{app_name}': {e}")
            return False

    def k8s_delete_dataplane(self, dp_name):
        ColorLogger.info(f"Deleting Data Plane '{dp_name}'")
        self.goto_left_navbar_dataplane()

        is_dataplane_visible = Util.refresh_until_success(self.page,
                                                          self.page.locator('.data-plane-name', has_text=dp_name),
                                                          self.page.locator(".data-planes-content"),
                                                          "DataPlane list page is load.")

        if is_dataplane_visible:
            self.page.locator('data-plane-card', has=self.page.locator('.data-plane-name', has_text=dp_name)).locator('.delete-dp-dropdown button').nth(0).click()
            print(f"Clicked '...' icon in Data Plane {dp_name} card")
            self.page.locator(".is-shown .pl-dropdown-menu__action", has_text="Delete Data Plane").nth(0).wait_for(state="visible")
            # check if 'Force Delete Data Plane' is visible, use Force Delete Data Plane as first choice
            if self.page.locator(".is-shown .pl-dropdown-menu__action", has_text="Force Delete Data Plane").is_visible():
                self.page.locator(".is-shown .pl-dropdown-menu__action", has_text="Force Delete Data Plane").click()
            else:
                self.page.locator(".is-shown .pl-dropdown-menu__action", has_text="Delete Data Plane").nth(0).click()
            print(f"Clicked 'Delete Data Plane' menu item")
            self.page.locator(".delete-dp-modal").wait_for(state="visible")
            print("'Delete Data Plane' dialog popup.")
            if Util.check_dom_visibility(self.page, self.page.locator(".delete-dp-modal #download-commands"), 2, 4):
                print("Delete Data Plane command is displayed.")
                # Note: the label height is too small, need to adjust it to trigger click event
                self.page.evaluate("""
                    document.querySelector(".delete-dp-modal label[for='agree-delete-btn']").style.minHeight = '20px';
                    document.querySelector(".delete-dp-modal label[for='agree-delete-btn']").style.width = '100%';
                """)
                self.page.locator(".delete-dp-modal label[for='agree-delete-btn']").click()
                print("Clicked confirm checkbox")
                # Teardown: a failing delete script must not stop the flow before it clicks
                # confirm and clears the report entry. See k8s_run_dataplane_command's docstring.
                self.k8s_run_dataplane_command(dp_name, "Delete Data Plane", self.page.locator(".delete-dp-modal #download-commands"), 0,
                                               abort_on_failure=False)

            self.page.locator(".delete-dp-modal #confirm-button").click()
            print("Clicked 'Delete' button in Delete Data Plane dialog")
            if Util.wait_for_success_message(self.page, 5):
                print("'Delete Data Plane' success message is displayed.")
                self.page.locator('.data-plane-name', has_text=dp_name).wait_for(state="detached")
                ColorLogger.success(f"Deleted Data Plane '{dp_name}'")
                ReportYaml.remove_dataplane(dp_name)
        else:
            ColorLogger.warning(f"Data Plane '{dp_name}' does not exist.")
            return

    def k8s_create_dataplane(self, dp_name, retry=0):
        if ReportYaml.is_dataplane_created(dp_name):
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, DataPlane '{dp_name}' is already created.")
            return

        ColorLogger.info(f"Creating k8s Data Plane '{dp_name}'...")
        self.page.wait_for_timeout(2000)

        if self.page.locator(".data-plane-name").count() > ENV.TP_AUTO_MAX_DATA_PLANE:
            Util.exit_error("Too many data planes, please delete some data planes first.", self.page, "k8s_create_dataplane.png")

        if self.page.locator('.data-plane-name', has_text=dp_name).is_visible():
            ReportYaml.set_dataplane(dp_name)
            ColorLogger.success(f"DataPlane '{dp_name}' is already created.")
            return

        self.page.click("#register-dp-button")
        if not Util.check_dom_visibility(self.page, self.page.locator("#select-existing-dp-button"), 10, 60, True):
            Util.exit_error("DP registration modal did not load within 60s", self.page, "k8s_create_dataplane.png")
        self.page.locator("#select-existing-dp-button").click()

        # CP 1.21 rebuilt this wizard on the Fresco shell (PCP-24237). Wait for whichever one
        # renders, then branch once; the legacy path below is unchanged.
        if not Util.check_dom_visibility(self.page, self.page.locator(EITHER_REGISTER_WIZARD).first, 3, 60):
            Util.exit_error("Register Data Plane wizard did not open.", self.page, "k8s_create_dataplane.png")
        if self.is_fresco_register_wizard():
            print("Detected the CP 1.21+ Fresco Register Kubernetes Data Plane wizard")
            self.k8s_create_dataplane_fresco(dp_name)
            return

        print("Detected the legacy Register Kubernetes Data Plane wizard")
        # step 1 Basic
        print("Waiting for Step 1: 'Basic' page is loaded")
        self.page.locator(LEGACY_WIZARD_STEP_ACTIVE, has_text="Basic").wait_for(state="visible")
        self.page.fill("#data-plane-name-text-input", dp_name)
        print(f"Input Data Plane Name: {dp_name}")
        self.page.locator('label[for="eua-checkbox"]').click()
        self.page.click("#data-plane-basics-btn")
        print("Clicked Next button, Finish step 1 Basic")

        # step 2 Namespace & Service account
        print("Waiting for Step 2: 'Namespace & Service account' page is loaded")
        self.page.locator(LEGACY_WIZARD_STEP_ACTIVE, has_text="Namespace & Service account").wait_for(state="visible")
        self.page.fill("#namespace-text-input", ENV.TP_AUTO_K8S_DP_NAMESPACE)
        print(f"Input NameSpace: {ENV.TP_AUTO_K8S_DP_NAMESPACE}")
        self.page.fill("#service-account-text-input", ENV.TP_AUTO_K8S_DP_SERVICE_ACCOUNT)
        print(f"Input Service Account: {ENV.TP_AUTO_K8S_DP_SERVICE_ACCOUNT}")
        self.page.click("#data-plane-namespace-btn")
        print("Clicked Next button, Finish step 2 Namespace & Service account")

        # step 3 Configuration
        print("Waiting for Step 3: 'Configuration' page is loaded")
        self.page.locator(LEGACY_WIZARD_STEP_ACTIVE, has_text="Configuration").wait_for(state="visible")

        # Handle non-hybrid connectivity: fill the Reachable DP URL when hybrid is disabled
        if Util.check_dom_visibility(self.page, self.page.locator("#hybrid-conn-url-host-input"), 2, 4):
            reachable_dp_url = ENV.TP_AUTO_REACHABLE_DP_URL
            self.page.fill("#hybrid-conn-url-host-input", reachable_dp_url)
            self.page.locator("#hybrid-conn-url-host-input").press("Tab")
            print(f"Hybrid connectivity disabled, Input Reachable DP URL: {reachable_dp_url}")

        if ENV.TP_IS_CERT_SELF_SIGNED:
            self.page.fill("#custom-certificate-secret-name-text-input", "self-signed-cert")
            print("Input Custom Certificate Secret Name: self-signed-cert")

        self.page.click("#data-plane-config-btn")
        print("Clicked Next button, Finish step 3 Configuration")

        # step Preview (for 1.4 and above)
        if Util.check_dom_visibility(self.page, self.page.locator(LEGACY_WIZARD_STEP_ACTIVE, has_text="Preview"), 3, 9):
            print("Step 4: 'Preview' page is loaded")
            self.page.wait_for_timeout(1000)
            if self.page.locator("#data-plane-preview-btn").is_visible():
                self.page.click("#data-plane-preview-btn")
                print("Clicked Next button, Finish step 4 Preview")

        # step Register Data Plane
        print("Check if create Data Plane is successful...")
        if not Util.check_dom_visibility(self.page, self.page.locator(".register-data-plane-content"), 3, 45):
            self.k8s_delete_dataplane(dp_name)
            if retry >= 3:
                Util.exit_error(f"Data Plane '{dp_name}' creation failed.", self.page, "k8s_create_dataplane_finish.png")

            ColorLogger.warning(f"Data Plane '{dp_name}' creation failed, retry {retry + 1} times.")
            self.k8s_create_dataplane(dp_name, retry + 1)
            # The retry owns the rest of the flow. Without this return the outer call fell
            # through into the command loop below against a stale page, on top of whatever the
            # retry had just done.
            return

        download_commands = self.page.locator("#download-commands")
        commands_title = self.page.locator(".register-data-plane p.title").all_text_contents()
        print("commands_title:", commands_title)

        # Execute each command dynamically based on its position
        for index, step_name in enumerate(commands_title):
            self.k8s_run_dataplane_command(dp_name, step_name, download_commands.nth(index), index + 1)

        # click Done button
        self.page.click("#data-plane-finished-btn")
        print("Data Plane create successful, clicked 'Done' button")
        ReportYaml.set_dataplane_info(dp_name, "runCommands", True)
        self.page.locator('#confirm-button', has_text="Yes").wait_for(state="visible")
        self.page.locator('#confirm-button', has_text="Yes").click()

        # verify data plane is created in the list
        self.page.wait_for_timeout(2000)
        print(f"Verifying Data Plane {dp_name} is created in the list")
        # No-tibtunnel mode: make the registered Reachable DP URL reachable (ingress or netpol labels).
        self.k8s_setup_dp_reachability(dp_name, ENV.TP_AUTO_K8S_DP_NAMESPACE, ENV.TP_AUTO_REACHABLE_DP_URL)
        self.k8s_wait_tunnel_connected(dp_name)

    def k8s_create_dataplane_fresco(self, dp_name):
        """Register a Kubernetes Data Plane through the CP 1.21+ Fresco wizard (PCP-24237).

        Called with the wizard already open on its Basic step. The step order is left to the
        Control Plane: only the steps this automation has something to say about get a filler,
        and everything else (Container Registry, Helm Chart Repository, Preview) is passed
        through on the Control Plane's own defaults, which is what a human registering a data
        plane would do.
        """
        self.fresco_wizard_enable_advanced()

        fillers = {
            FRESCO_STEP_BASIC: lambda: self.fresco_fill_basic_step(dp_name),
            FRESCO_STEP_NAMESPACE_SA: lambda: self.fresco_fill_namespace_sa_step(
                ENV.TP_AUTO_K8S_DP_NAMESPACE, ENV.TP_AUTO_K8S_DP_SERVICE_ACCOUNT),
            FRESCO_STEP_CONFIGURATION: lambda: self.fresco_fill_configuration_step(ENV.TP_AUTO_REACHABLE_DP_URL),
        }
        self.fresco_wizard_walk(fillers)

        # step Register Data Plane
        print("Check if create Data Plane is successful...")
        if not self.fresco_run_register_commands(dp_name):
            # Deliberately no delete-and-retry here, unlike the legacy wizard. By this point the
            # Preview step's 'Save' has already registered the data plane, so the legacy branch
            # would DELETE a real registration on nothing more than a DOM timeout - including one
            # that merely rendered slowly - and then recurse into k8s_create_dataplane, which
            # reports 'already created' the moment the delete does not take. That is how a failed
            # registration becomes a green task. Fail loudly and leave the decision to a human,
            # exactly as k8s_create_bmdp already does.
            Util.exit_error(
                f"Data Plane '{dp_name}' did not reach the registration step of the wizard. Nothing was deleted; "
                f"check the Control Plane for a partially registered data plane and remove it before re-running.",
                self.page, "k8s_create_dataplane_finish.png")
            return

        self.fresco_register_click_done()
        ReportYaml.set_dataplane_info(dp_name, "runCommands", True)

        # verify data plane is created in the list
        self.page.wait_for_timeout(2000)
        print(f"Verifying Data Plane {dp_name} is created in the list")
        # No-tibtunnel mode: make the registered Reachable DP URL reachable (ingress or netpol labels).
        self.k8s_setup_dp_reachability(dp_name, ENV.TP_AUTO_K8S_DP_NAMESPACE, ENV.TP_AUTO_REACHABLE_DP_URL)
        self.k8s_wait_tunnel_connected(dp_name)

    def fresco_fill_basic_step(self, dp_name, is_control_tower=False, machine_host_name=""):
        """Basic step, shared by the Kubernetes and the Control Tower wizards.

        The Control Tower one additionally asks for a Control Tower type and a machine host
        name. Which wizard this is comes from `is_control_tower`, NOT from whether a host name
        happened to be supplied: keying both off the host name meant an empty
        `TP_AUTO_FQDN_BMDP` skipped the flavour radio too, and the run then registered against
        whichever type the Control Plane had preselected - the same silent-wrong-registration
        shape the rest of this flow exits over, and one with no cheap way back, since 'Native'
        is a completely different data plane.
        """
        if is_control_tower:
            if not machine_host_name:
                Util.exit_error(
                    "Control Tower registration needs a machine host name, but TP_AUTO_FQDN_BMDP is empty. "
                    "Refusing to register against whichever Control Tower type the Control Plane preselected.",
                    self.page, "fresco_register_missing_host_name.png")
                return

            # Kubernetes is the default flavour, but say so explicitly.
            self.page.locator("#ct-flavor-radio-k8s").check(force=True)
            print("Selected Control Tower type: Kubernetes")

        self.page.fill("#dp-name-input", dp_name)
        print(f"Input Data Plane Name: {dp_name}")

        if is_control_tower:
            self.page.fill("#machine-host-name-input", machine_host_name)
            print(f"Input Machine Host Name: {machine_host_name}")

        self.fresco_check_eula()

    def fresco_fill_namespace_sa_step(self, namespace, service_account):
        """Namespace & Service Account step.

        Both fields arrive prefilled with the Control Plane's '<dp-name>-my-ns' /
        '<dp-name>-my-sa' defaults, so they are overwritten rather than merely typed into.
        """
        self.page.fill("#dp-namespace-input", namespace)
        print(f"Input NameSpace: {namespace}")
        self.page.fill("#dp-service-account-input", service_account)
        print(f"Input Service Account: {service_account}")

    def fresco_fill_configuration_step(self, reachable_dp_url):
        """Configuration step.

        Hybrid connectivity is on by default and the Reachable DP URL is only rendered when it
        is off, so - exactly as the legacy flow did - the field is filled if and only if the
        Control Plane shows it. The automation does not flip the toggle itself: which mode the
        data plane registers in is the Control Plane's decision, not the test's.
        """
        if Util.check_dom_visibility(self.page, self.page.locator("#dp-url-input"), 2, 4):
            self.page.fill("#dp-url-input", reachable_dp_url)
            self.page.locator("#dp-url-input").press("Tab")
            print(f"Hybrid connectivity disabled, Input Reachable DP URL: {reachable_dp_url}")

        if ENV.TP_IS_CERT_SELF_SIGNED:
            self.fresco_fill_by_form_control("customCertificateSecretName", "self-signed-cert",
                                             "Custom Certificate Secret Name")

    def k8s_create_bmdp(self, dp_name, retry=0):
        ColorLogger.info(f"Creating k8s Data Plane '{dp_name}'...")
        # Validate the namespace once, up front. Several steps below hand it to commands that run
        # through a shell, and it arrives from the environment, so check it before the first of
        # them rather than at each sink — a later sink added without the check would otherwise
        # reopen the hole quietly.
        self._safe_k8s_name(ENV.TP_AUTO_K8S_BMDP_NAMESPACE)
        self.page.wait_for_timeout(2000)

        if self.page.locator(".data-plane-name").count() > ENV.TP_AUTO_MAX_DATA_PLANE:
            Util.exit_error("Too many data planes, please delete some data planes first.", self.page, "k8s_create_dataplane.png")

        # The Control Plane is the source of truth for whether this data plane exists at all.
        # report.yaml is only a record of what a previous run believed, and it outlives both the
        # data plane and the process: a data plane deleted afterwards leaves its completion
        # markers behind, so trusting the report on its own skips the registration entirely and
        # reports success for a data plane that is no longer there.
        if self._dataplane_name_locator(dp_name).is_visible():
            print(f"DataPlane '{dp_name}' already exists in the Control Plane, checking whether it is healthy...")
            # A card only proves a record exists; it may be a leftover from a half-finished
            # registration. Completion evidence recorded earlier counts, but only now that the
            # data plane has been seen; otherwise fall back to the live health check.
            if self._is_bmdp_complete(dp_name):
                ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, DataPlane '{dp_name}' is already created.")
                return

            if self._is_dataplane_status_green(dp_name):
                ColorLogger.success(f"DataPlane '{dp_name}' is already created and healthy.")
                self.k8s_wait_bmdp_ready(dp_name, False)
                self._assert_bmdp_workload(dp_name)
                self._mark_bmdp_complete(dp_name)
                return

            ColorLogger.warning(f"DataPlane '{dp_name}' exists in the Control Plane, but is not healthy.")
            self._recover_unhealthy_bmdp(dp_name, retry)
            return

        # No card: whatever the report says about this data plane describes something that no
        # longer exists. Drop it so the entry cannot short-circuit a later task, and register.
        if ReportYaml.is_dataplane_created(dp_name):
            ColorLogger.warning(f"DataPlane '{dp_name}' is recorded in {ENV.TP_AUTO_REPORT_YAML_FILE} but is not in the Control Plane; discarding the stale record and registering it again.")
            ReportYaml.remove_dataplane(dp_name)

        self.page.click("#register-dp-button")
        self.page.locator("#select-control-tower-dp-button").wait_for(state="visible")
        self.page.locator(".pl-primary-spinner").wait_for(state="hidden", timeout=60000)
        self.page.wait_for_timeout(2000)

        # check if #select-control-tower-dp-button is disabled, if it's disabled, should return error, and exit.
        start_btn = self.page.locator("#select-control-tower-dp-button")
        if "pcp-disabled" in (start_btn.get_attribute("class") or ""):
            tooltip = self.page.locator("#control-tower-dp-register-button-tooltip")
            hint = tooltip.text_content(timeout=3000) if tooltip.is_visible(timeout=2000) else "unknown prerequisite"
            Util.exit_error(
                f"Control Tower DP 'Start' button is disabled: {hint}",
                self.page, "bmdp_button_disabled.png"
            )

        start_btn.click()

        # CP 1.21 rebuilt this wizard on the same Fresco shell as the Kubernetes one
        # (PCP-24237): every id below is gone there, so branch before touching any of them.
        # Wait on EITHER wizard rather than on the Fresco rail alone: polling only for Fresco
        # made every LEGACY registration pay the full timeout before falling through, and a
        # Fresco rail that rendered slower than that would drop into the legacy path and
        # reproduce the very timeout this fixes.
        if not Util.check_dom_visibility(self.page, self.page.locator(EITHER_REGISTER_WIZARD).first, 3, 60):
            Util.exit_error("Register Control Tower Data Plane wizard did not open.", self.page, "bmdp_register_wizard_missing.png")
        if self.is_fresco_register_wizard():
            print("Detected the CP 1.21+ Fresco Register Control Tower Data Plane wizard")
            self.k8s_create_bmdp_fresco(dp_name)
            return

        print("Detected the legacy Register Control Tower Data Plane wizard")
        print("Waiting for Step 1: 'Pre-Requisites' page is loaded")
        if Util.check_dom_visibility(self.page, self.page.locator("#data-plane-pre-requisites-btn"), 2, 4):
            tp_version = 1.4
            # step 1 Pre-Requisites
            print("configure for 1.4")
            self.page.click("#data-plane-pre-requisites-btn")
            print("Clicked Next button, Finish Pre-Requisites")
            # step 2 Basic
            self.page.locator(LEGACY_WIZARD_STEP_ACTIVE, has_text="Basic").wait_for(state="visible")
            self.page.fill("#data-plane-name-text-input", dp_name)
            print(f"Input Data Plane Name: {dp_name}")
            self.page.locator('label[for="terms-checkbox"]').click()
            self.page.click("#data-plane-basics-btn")
            print("Clicked Next button, Finish Basic")
        else:
            tp_version = 1.5
            self.page.fill("#data-plane-name-text-input", dp_name)
            print(f"Input Data Plane Name: {dp_name}")
            self.page.fill("#data-plane-machine-host-name-text-input", ENV.TP_AUTO_FQDN_BMDP)
            print(f"Input Machine Host Name: {ENV.TP_AUTO_FQDN_BMDP}")

            # Reachable DP URL is always required for BMDP registration (TP 1.15+)
            reachable_url_field = self.page.locator("#reachable-dp-url-text-input")
            if reachable_url_field.is_visible():
                reachable_dp_url = ENV.TP_AUTO_REACHABLE_BMDP_URL
                reachable_url_field.fill(reachable_dp_url)
                print(f"Input Reachable DP URL: {reachable_dp_url}")

            self.page.locator('label[for="terms-checkbox"]').click()
            self.page.locator(".pl-button.pl-button--no-border.big-button.big-button-secondary").click()
            print("Clicked Advanced Configuration button. Go with Advanced Configuration")

        # step 3 Namespace & Service account
        print("Waiting for 'Namespace & Service account' page is loaded")
        self.page.locator(LEGACY_WIZARD_STEP_ACTIVE, has_text="Namespace & Service account").wait_for(state="visible")
        self.page.fill("#namespace-text-input", ENV.TP_AUTO_K8S_BMDP_NAMESPACE)
        print(f"Input NameSpace: {ENV.TP_AUTO_K8S_BMDP_NAMESPACE}")
        self.page.fill("#service-account-text-input", ENV.TP_AUTO_K8S_BMDP_SERVICE_ACCOUNT)
        print(f"Input Service Account: {ENV.TP_AUTO_K8S_BMDP_SERVICE_ACCOUNT}")
        self.page.click("#data-plane-namespace-btn")
        print("Clicked Next button, Finish Namespace & Service account")

        # step 4 Configure resources - storage class
        print("Waiting for 'Configure resources' page is loaded")
        self.page.locator(LEGACY_WIZARD_STEP_ACTIVE, has_text="Resources").wait_for(state="visible")
        self.page.fill("#storage-resource-name-text-input", "storageclass")
        print(f"Input Storage Resource Name: storageclass")
        self.page.fill("#storage-description-text-input", "storageclass")
        print(f"Input Storage Description: storageclass")
        # set the storage class to nfs for now, due to a known issue with hawkconsole
        # self.page.fill("#storage-class-name-text-input", "{ENV.TP_AUTO_STORAGE_CLASS}")
        self.page.fill("#storage-class-name-text-input", "nfs")
        print(f"Input Storage Class Name: nfs")

        # step 4 Configure resources - ingress / gateway controller
        # CP 1.18 added a Gateway API Controller radio next to the Ingress Controller
        # radio. Switching to Gateway exposes a different dropdown (Nginx / GKE / Istio /
        # Traefik / NetScaler / Other) and a different field set with `gateway-*` IDs
        # instead of `ingress-*`. Earlier CPs (≤1.17) only have the ingress flow.
        gateway_radio = self.page.locator('#gateway-radio-button')
        if ENV.TP_AUTO_INGRESS_OBJECT == "gateway" and gateway_radio.is_visible():
            # CP 1.18+ gateway path
            gateway_radio.click(force=True)
            print("Switched to 'Gateway API Controller' radio (CP 1.18 BMDP wizard)")
            self.page.wait_for_timeout(1500)

            # Same `.ingress pcp-dropdown` container; in gateway mode the inner div is
            # #gatewayController and options are Nginx/GKE/Istio/Traefik/NetScaler/Other.
            self.page.locator('.ingress pcp-dropdown input[type="button"]').click()
            print("Clicked Gateway Controller dropdown")
            select_gateway_controller = ENV.TP_AUTO_GATEWAY_CONTROLLER.capitalize()
            opt = self.page.locator('.ingress pcp-dropdown li', has_text=select_gateway_controller).first
            opt.wait_for(state="visible")
            opt.click()
            print(f"Selected Gateway Controller: {select_gateway_controller}")

            self.page.fill("#gateway-resource-name-text-input", ENV.TP_AUTO_GATEWAY_CONTROLLER)
            print(f"Input Gateway Resource Name: {ENV.TP_AUTO_GATEWAY_CONTROLLER}")
            self.page.fill("#gateway-name-text-input", ENV.TP_AUTO_GATEWAY_NAME)
            print(f"Input Gateway Name: {ENV.TP_AUTO_GATEWAY_NAME}")
            self.page.fill("#gateway-namespace-text-input", ENV.TP_AUTO_GATEWAY_NAMESPACE)
            print(f"Input Gateway Namespace: {ENV.TP_AUTO_GATEWAY_NAMESPACE}")
            self.page.fill("#gateway-hostname-text-input", ENV.TP_AUTO_FQDN_BMDP)
            print(f"Input Gateway Hostname (FQDN): {ENV.TP_AUTO_FQDN_BMDP}")
        else:
            # Ingress path (CP <= 1.17 always; CP 1.18 when TP_AUTO_INGRESS_OBJECT != "gateway")
            # For 1.13 and above, the ingress controller changed to dropdown selection from a readonly input box
            if not self.page.locator("ingress-controller-text-input").is_visible():
                # click dropdown and select ENV.TP_AUTO_INGRESS_CONTROLLER
                print("For 1.13 and above, the ingress controller changed to dropdown selection from a readonly input box")
                if self.page.locator('.ingress pcp-dropdown').is_visible():
                    print("Selecting Ingress Controller from dropdown")
                    self.page.locator('.ingress pcp-dropdown input[type="button"]').click()
                    print("Clicked Ingress Controller dropdown")
                    self.page.locator('.ingress pcp-dropdown div#ingressController').wait_for(state="visible")
                    print("Ingress Controller options are visible")
                    select_ingress_controller = ENV.TP_AUTO_INGRESS_CONTROLLER.capitalize()
                    self.page.locator('.ingress pcp-dropdown div#ingressController li', has_text=select_ingress_controller).click()
                    print(f"Selected Ingress Controller: {select_ingress_controller}")

            self.page.fill("#ingress-resource-name-text-input", ENV.TP_AUTO_INGRESS_CONTROLLER)
            print(f"Input Ingress Resource Name: {ENV.TP_AUTO_INGRESS_CONTROLLER}")
            self.page.fill("#ingress-class-name-text-input", ENV.TP_AUTO_INGRESS_CONTROLLER_CLASS_NAME)
            print(f"Input Ingress Class Name: {ENV.TP_AUTO_INGRESS_CONTROLLER_CLASS_NAME}")
            self.page.fill("#ingress-fqdn-text-input", ENV.TP_AUTO_FQDN_BMDP)
            print(f"Input Ingress FQDN: {ENV.TP_AUTO_FQDN_BMDP}")

        self.page.click("#data-plane-resources-btn")
        print("Clicked Next button, Finish Configure resources")

        # step 5 Configuration
        print("Waiting for 'Configuration' page is loaded")
        self.page.locator(LEGACY_WIZARD_STEP_ACTIVE, has_text="Configuration").wait_for(state="visible")

        if ENV.TP_IS_CERT_SELF_SIGNED:
            self.page.fill("#custom-certificate-secret-name-text-input", "self-signed-cert")
            print("Input Custom Certificate Secret Name: self-signed-cert")

        self.page.click("#data-plane-preview-next-btn")
        print("Clicked Next button, Finish Configuration")

        # step 6 Preview (for 1.4 and above)
        if Util.check_dom_visibility(self.page, self.page.locator(LEGACY_WIZARD_STEP_ACTIVE, has_text="Preview"), 3, 9):
            print("'Preview' page is loaded")
            self.page.wait_for_timeout(1000)
            if self.page.locator("#data-plane-preview-create-btn").is_visible():
                self.page.click("#data-plane-preview-create-btn")
                print("Clicked Next button, Finish Preview")
            elif self.page.locator("#data-plane-config-prev-btn").is_visible():
                self.page.click("#data-plane-config-prev-btn")
                print("Clicked  'Register on Control Plane now', Finish Preview")

        # step 7 Register Data Plane
        print("Check if create Data Plane is successful...")
        # Only a page-specific anchor proves the wizard reached the registration step: the legacy
        # '.install-content' panel (1.4), '.finished-main-content' (1.5 and above), or the Done
        # button the flow goes on to click. Several anchors rather than one, so the gate cannot
        # hinge on a single class that a future Control Plane might rename.
        is_register_page = Util.check_dom_visibility(self.page, self.page.locator(BMDP_REGISTER_LEGACY_CONTENT).first, 2, 10) \
            or Util.check_dom_visibility(self.page, self.page.locator(BMDP_REGISTER_FINISHED_CONTENT).first, 3, 45) \
            or self.page.locator(BMDP_REGISTER_FINISHED_BUTTON).first.is_visible()
        if not is_register_page:
            # Diagnostic only: a visible primary button says the wizard is alive but on the wrong
            # page, it is never enough on its own to treat the registration as successful.
            if self.page.locator(BMDP_REGISTER_PRIMARY_BUTTON).first.is_visible():
                ColorLogger.warning("Registration page anchors are absent while a primary button is visible; the wizard is on an unexpected page.")
            # Deliberately no delete-and-retry here. The old code deleted the data plane on this
            # branch, but the branch was unreachable, so that behaviour has never actually run;
            # making it live would mean destroying a data plane on nothing more than a DOM
            # timeout — including a registration that merely rendered slowly. Fail loudly and
            # leave the decision to a human instead.
            Util.exit_error(
                f"BMDP '{dp_name}' did not reach the registration step of the wizard. Nothing was deleted; "
                f"check the Control Plane for a partially registered data plane and remove it before re-running.",
                self.page, "bmdp_register_page_missing.png")

        if tp_version == 1.4:
            download_commands = self.page.locator("#download-commands")
            commands_title = self.page.locator(f"{BMDP_REGISTER_LEGACY_CONTENT} p.title").all_text_contents()
            commands_title.pop(0)
        else:
            commands_title = self._scrape_register_commands()
            # The Control Plane renders one svg#download-commands per command block, in title
            # order. Scope the buttons to the same container so a page-wide match cannot shift the
            # title -> button pairing and download the wrong script for a step.
            download_commands = self.page.locator(f"{BMDP_REGISTER_COMMANDS_CONTAINER} #download-commands")

        print("commands_title:", commands_title)

        if not commands_title:
            self._log_register_commands_diagnostics()
            Util.exit_error(f"BMDP '{dp_name}' registration page produced no commands to run.", self.page, "bmdp_register_commands_empty.png")

        # The 1.4 layout drops its first title (see pop above), so only the container-scoped path
        # can be compared; a mismatch there means the pairing is off and running the commands would
        # execute the wrong script for a step.
        if tp_version != 1.4 and download_commands.count() != len(commands_title):
            Util.exit_error(
                f"BMDP '{dp_name}' registration page has {len(commands_title)} command title(s) but "
                f"{download_commands.count()} download button(s); refusing to run mismatched commands.",
                self.page, "bmdp_register_commands_mismatch.png")

        # Execute each command dynamically based on its position, always under its real title:
        # k8s_run_dataplane_command keys on the title to apply the per-step extras, so a synthesized
        # name would silently skip them.
        for index, step_name in enumerate(commands_title):
            if step_name.casefold() not in BMDP_REGISTER_COMMAND_TITLES_FOLDED:
                ColorLogger.warning(f"Unrecognised registration command title '{step_name}'; running it as-is, but no per-step extras will be applied to it.")
            self.k8s_run_dataplane_command(dp_name, step_name, download_commands.nth(index), index + 1)

        print(f"Executed {len(commands_title)} registration command(s) for BMDP '{dp_name}'")

        # click Done button
        self.page.click("#data-plane-finished-btn")
        print("BMDP create successful, clicked 'Done' button")
        self.page.locator('#confirm-button', has_text="Yes").wait_for(state="visible")
        self.page.locator('#confirm-button', has_text="Yes").click()

        # verify data plane is created in the list
        self.page.wait_for_timeout(2000)
        print(f"Verifying Data Plane {dp_name} is created in the list")
        # No-tibtunnel mode: make the registered Reachable BMDP URL reachable (ingress or netpol labels).
        self.k8s_setup_dp_reachability(dp_name, ENV.TP_AUTO_K8S_BMDP_NAMESPACE, ENV.TP_AUTO_REACHABLE_BMDP_URL, is_bmdp=True)
        self.k8s_wait_tunnel_connected(dp_name, False)
        self.k8s_wait_bmdp_ready(dp_name, False)
        self._assert_bmdp_workload(dp_name)
        self._mark_bmdp_complete(dp_name)

    def k8s_create_bmdp_fresco(self, dp_name):
        """Register a Control Tower Data Plane through the CP 1.21+ Fresco wizard (PCP-24237).

        The Control Tower wizard is the Kubernetes one plus a 'Resources' step, so it reuses
        the same walk and the same Basic / Namespace & Service Account / Configuration fillers.
        """
        self.fresco_wizard_enable_advanced()

        fillers = {
            FRESCO_STEP_BASIC: lambda: self.fresco_fill_basic_step(
                dp_name, is_control_tower=True, machine_host_name=ENV.TP_AUTO_FQDN_BMDP),
            FRESCO_STEP_NAMESPACE_SA: lambda: self.fresco_fill_namespace_sa_step(
                ENV.TP_AUTO_K8S_BMDP_NAMESPACE, ENV.TP_AUTO_K8S_BMDP_SERVICE_ACCOUNT),
            FRESCO_STEP_RESOURCES: self.fresco_fill_ctdp_resources_step,
            FRESCO_STEP_CONFIGURATION: lambda: self.fresco_fill_configuration_step(ENV.TP_AUTO_REACHABLE_BMDP_URL),
        }
        self.fresco_wizard_walk(fillers)

        # step Register Data Plane
        print("Check if create BMDP is successful...")
        if not self.fresco_run_register_commands(dp_name):
            # Deliberately no delete-and-retry, for the same reason the legacy path has none:
            # destroying a data plane on nothing more than a DOM timeout - including a
            # registration that merely rendered slowly - is worse than stopping for a human.
            Util.exit_error(
                f"BMDP '{dp_name}' did not reach the registration step of the wizard. Nothing was deleted; "
                f"check the Control Plane for a partially registered data plane and remove it before re-running.",
                self.page, "bmdp_register_page_missing.png")
            return

        self.fresco_register_click_done()

        # verify data plane is created in the list
        self.page.wait_for_timeout(2000)
        print(f"Verifying Data Plane {dp_name} is created in the list")
        # No-tibtunnel mode: make the registered Reachable BMDP URL reachable (ingress or netpol labels).
        self.k8s_setup_dp_reachability(dp_name, ENV.TP_AUTO_K8S_BMDP_NAMESPACE, ENV.TP_AUTO_REACHABLE_BMDP_URL, is_bmdp=True)
        self.k8s_wait_tunnel_connected(dp_name, False)
        self.k8s_wait_bmdp_ready(dp_name, False)
        self._assert_bmdp_workload(dp_name)
        self._mark_bmdp_complete(dp_name)

    def fresco_fill_ctdp_resources_step(self):
        """Control Tower 'Resources' step: storage class, then ingress or gateway.

        The two route-resource modes render DIFFERENT forms, not a relabelled one - the
        controller dropdown binds a different form control and the whole field set changes
        (`#ctdp-ingress-*` + `#ctdp-fqdn-input` vs `#ctdp-gateway-*`), with Gateway Name and
        Gateway Namespace required and having no ingress-mode counterpart. So each branch fills
        its own fields end to end; there is no shared tail.
        """
        self.page.fill("#ctdp-storage-name-input", "storageclass")
        print("Input Storage Resource Name: storageclass")
        self.fresco_fill_by_form_control("description", "storageclass", "Storage Description")
        # set the storage class to nfs for now, due to a known issue with hawkconsole
        self.page.fill("#ctdp-storage-class-name-input", "nfs")
        print("Input Storage Class Name: nfs")

        if ENV.TP_AUTO_INGRESS_OBJECT == "gateway":
            self.fresco_fill_ctdp_gateway_route()
        else:
            self.fresco_fill_ctdp_ingress_route()

    def fresco_fill_ctdp_gateway_route(self):
        """Gateway API route resource on the Control Tower Resources step.

        The radio is waited for rather than probed with a bare `is_visible()`. An instantaneous
        poll right after a Next click races Angular's render, and falling through to the Ingress
        branch would register the data plane with the wrong route-resource type and still report
        success - which is the shape this whole change exists to remove. `TP_AUTO_INGRESS_OBJECT
        == "gateway"` is an explicit operator request, so a missing radio here is an error, not
        a fall back to an older Control Plane.
        """
        gateway_radio = self.page.locator(FRESCO_ROUTE_RESOURCE_GATEWAY_RADIO)
        if not Util.check_dom_visibility(self.page, gateway_radio, 2, 10):
            Util.exit_error(
                "TP_AUTO_INGRESS_OBJECT is 'gateway' but the Control Tower Resources step offers no "
                "Gateway API radio; refusing to register with an Ingress route resource instead.",
                self.page, "fresco_route_resource_gateway_missing.png")
            return

        self.page.locator(FRESCO_ROUTE_RESOURCE_GATEWAY_RADIO).check(force=True)
        print("Selected Route Resource: 'Gateway API Controller'")
        self.page.wait_for_timeout(1500)

        self.fresco_select_route_controller(FRESCO_GATEWAY_CONTROLLER_SELECT, ENV.TP_AUTO_GATEWAY_CONTROLLER)
        self.page.fill("#ctdp-gateway-resource-name-input", ENV.TP_AUTO_GATEWAY_CONTROLLER)
        print(f"Input Gateway Resource Name: {ENV.TP_AUTO_GATEWAY_CONTROLLER}")
        self.page.fill("#ctdp-gateway-name-input", ENV.TP_AUTO_GATEWAY_NAME)
        print(f"Input Gateway Name: {ENV.TP_AUTO_GATEWAY_NAME}")
        self.page.fill("#ctdp-gateway-namespace-input", ENV.TP_AUTO_GATEWAY_NAMESPACE)
        print(f"Input Gateway Namespace: {ENV.TP_AUTO_GATEWAY_NAMESPACE}")
        self.page.fill("#ctdp-gateway-host-input", ENV.TP_AUTO_FQDN_BMDP)
        print(f"Input Gateway Host/Domain name: {ENV.TP_AUTO_FQDN_BMDP}")

    def fresco_fill_ctdp_ingress_route(self):
        """Ingress Controller route resource on the Control Tower Resources step."""
        self.page.locator(FRESCO_ROUTE_RESOURCE_INGRESS_RADIO).check(force=True)
        print("Selected Route Resource: 'Ingress Controller'")
        self.page.wait_for_timeout(1500)

        self.fresco_select_route_controller(FRESCO_INGRESS_CONTROLLER_SELECT, ENV.TP_AUTO_INGRESS_CONTROLLER)
        self.page.fill("#ctdp-ingress-resource-name-input", ENV.TP_AUTO_INGRESS_CONTROLLER)
        print(f"Input Ingress Resource Name: {ENV.TP_AUTO_INGRESS_CONTROLLER}")
        self.page.fill("#ctdp-ingress-class-name-input", ENV.TP_AUTO_INGRESS_CONTROLLER_CLASS_NAME)
        print(f"Input Ingress Class Name: {ENV.TP_AUTO_INGRESS_CONTROLLER_CLASS_NAME}")
        self.page.fill("#ctdp-fqdn-input", ENV.TP_AUTO_FQDN_BMDP)
        print(f"Input FQDN: {ENV.TP_AUTO_FQDN_BMDP}")

    def fresco_select_route_controller(self, select_selector, controller):
        """Pick a controller from the Fresco route-resource dropdown.

        `select_selector` differs by mode - the Ingress form binds `ingressController`, the
        Gateway API form binds `gatewayApicontrollerName` - so the caller passes the one its
        branch is looking at rather than this method assuming either.

        The PrimeNG select renders its options into an overlay outside the dialog, so the
        option is looked up page-wide once the list is open, not under the select.

        A missing option EXITS rather than keeping whatever was preselected. The legacy
        dropdown clicked the option and threw when it was absent, so degrading to a warning
        here would be strictly weaker than the code it replaces: the data plane would register
        against the wrong ingress controller and still report success.

        The option is matched on its WHOLE text, anchored. Playwright's `has_text` is a
        case-insensitive substring, so with `.first` a controller whose name prefixes another
        offered option - `nginx` against a list holding `nginx-gateway-fabric` - would select
        whichever renders first and report success, which is the exact outcome the exit above
        exists to prevent. Anchoring also removes the need for `.capitalize()`, which was only
        papering over the case difference and mangled multi-word names on the way.
        """
        self.page.locator(select_selector).click()
        print("Clicked the route controller dropdown")
        # Re-queried rather than held across the wait (principle 4). The PrimeNG options live
        # in a page-level overlay that re-renders while the poll runs, which is the single most
        # likely place in this method for a cached handle to go stale.
        exact = re.compile(rf"^\s*{re.escape(controller)}\s*$", re.IGNORECASE)
        if not Util.check_dom_visibility(
                self.page, self.page.locator("li.p-select-option", has_text=exact).first, 2, 10):
            Util.exit_error(f"Route controller '{controller}' is not offered by the dropdown; refusing to register against whichever one happened to be preselected.",
                            self.page, "fresco_route_controller_missing.png")
            return
        self.page.locator("li.p-select-option", has_text=exact).first.click()
        print(f"Selected route controller: {controller}")

    def _scrape_register_commands(self):
        """Expand the registration-commands panel and return the command titles it renders.

        all_text_contents() is the only call in this flow that does not auto-wait: with zero
        matches it returns [] immediately, with no timeout and no exception. Scraping right after
        clicking the toggle therefore races Angular's re-render and silently yields no commands, so
        wait for the container first and only then read the titles.
        """
        titles_selector = f"{BMDP_REGISTER_COMMANDS_CONTAINER} p.title"

        # Click only when the panel is closed: the toggle is a plain boolean flip, so a blind click
        # on an already-open panel would close it again. Decide on VISIBILITY, not presence: the
        # container is *ngIf-gated today, but the class is literally '.expandable', and a Control
        # Plane that instead kept it in the DOM and collapsed it with CSS would make a presence
        # check say 'already open' so the toggle never fired — while all_text_contents(), which
        # reads textContent regardless of visibility, still returned titles for buttons that
        # cannot be clicked.
        if not self.page.locator(titles_selector).first.is_visible():
            self._click_register_details_toggle()

        # Always settle on the TITLES, never on the container alone, and never skip this wait:
        # the read below does not auto-wait, so any path that reaches it without having waited
        # is the original race. An already-present container is not proof the titles inside it
        # have rendered.
        Util.check_dom_visibility(self.page, self.page.locator(titles_selector).first, 3, 45)

        # Re-evaluate the DOM (not the wait's return value) immediately before deciding to click
        # again, and click at most one extra time for the same reason.
        if not self.page.locator(titles_selector).first.is_visible():
            ColorLogger.warning("Registration commands panel did not render, clicking the details toggle once more.")
            self._click_register_details_toggle()
            Util.check_dom_visibility(self.page, self.page.locator(titles_selector).first, 3, 45)

        # all_text_contents() returns raw textContent with no whitespace normalisation, and
        # k8s_run_dataplane_command compares these strings with == to decide whether to apply the
        # helm-repo reset and the service-account extras. An untrimmed title would match nothing
        # and silently skip that work — the very failure mode this change exists to remove.
        return [title.strip() for title in self.page.locator(titles_selector).all_text_contents()]

    def _click_register_details_toggle(self):
        # 'Display Details & Registration Commands' toggle. Prefer the selector anchored on the
        # registration panel; older Control Planes only have the generic no-border button.
        if self.page.locator(BMDP_REGISTER_DETAILS_TOGGLE).count() > 0:
            self.page.locator(BMDP_REGISTER_DETAILS_TOGGLE).first.click()
            print("Clicked 'Display Details & Registration Commands' toggle")
            return

        self.page.locator(BMDP_REGISTER_DETAILS_TOGGLE_LEGACY).first.click()
        print("Clicked 'Display Details & Registration Commands' toggle (legacy selector)")

    def _log_register_commands_diagnostics(self):
        # Print what each candidate selector actually matched, so a future layout change is obvious
        # from the pipeline log instead of needing a trace replay.
        for description, selector in (
            ("commands container", BMDP_REGISTER_COMMANDS_CONTAINER),
            ("command titles", f"{BMDP_REGISTER_COMMANDS_CONTAINER} p.title"),
            ("details toggle", BMDP_REGISTER_DETAILS_TOGGLE),
            ("details toggle (legacy)", BMDP_REGISTER_DETAILS_TOGGLE_LEGACY),
        ):
            ColorLogger.warning(f"No registration command scraped, {description} selector '{selector}' matched {self.page.locator(selector).count()} element(s).")

    @staticmethod
    def _is_bmdp_complete(dp_name):
        """True only when report.yaml carries positive evidence that the BMDP came up.

        Two registration paths write two different markers, and both are genuine: the browser
        flow writes the status once the workload is proven, while the CLI flow writes
        healthStatus only after wait_for_dataplane_green has returned. Accepting just one of
        them would make the other path re-run a registration that already succeeded.
        A bare name is NOT evidence — it is written as soon as any card with that name is seen.
        """
        if not ReportYaml.is_dataplane_created(dp_name):
            return False

        if ReportYaml.get_dataplane_info(dp_name, "status") == BMDP_STATUS_RUNNING:
            return True

        health_status = ReportYaml.get_dataplane_info(dp_name, "healthStatus")
        return str(health_status).lower() == BMDP_HEALTH_STATUS_GREEN

    @staticmethod
    def _exact_name_pattern(dp_name):
        # Exact (whitespace-trimmed) match: a substring match on 'k8s-auto-bmdp1' also selects
        # 'k8s-auto-bmdp10', and two matches make is_visible() / click() raise a strict-mode error.
        return re.compile(rf"^\s*{re.escape(dp_name)}\s*$")

    def _dataplane_name_locator(self, dp_name):
        return self.page.locator('.data-plane-name', has_text=self._exact_name_pattern(dp_name)).first

    def _is_dataplane_status_green(self, dp_name):
        """Health oracle for one data plane card in the Data Planes list.

        Only the card-level data plane status icon counts. Tunnel state is deliberately ignored: a
        disconnected tunnel is never a reason to destroy a data plane. The icon turns green only
        after a page reload, hence is_refresh=True — the same shape k8s_wait_bmdp_ready uses.
        """
        data_plane_card = self.page.locator(".data-plane-card", has=self.page.locator('.data-plane-name', has_text=self._exact_name_pattern(dp_name))).first
        return Util.check_dom_visibility(self.page, data_plane_card.locator('.data-plane-status svg.green').first, 20, 300, True)

    def _assert_bmdp_workload(self, dp_name):
        """Prove the BMDP has a real workload in the cluster, not just a green card in the UI."""
        if not ENV.IS_CLUSTER_ACCESSIBLE:
            ColorLogger.warning(f"Cluster is not accessible, skipping BMDP '{dp_name}' workload check.")
            return

        # The namespace the data plane was actually registered with, not whatever the current
        # environment happens to default to: judging an existing data plane against a namespace
        # it never used would report a perfectly healthy one as broken.
        namespace = self._bmdp_namespace(dp_name)
        namespace_state = self._namespace_state(namespace)
        if namespace_state == "absent":
            Util.exit_error(f"BMDP '{dp_name}' is registered, but its namespace '{namespace}' does not exist in the cluster.", self.page, "bmdp_namespace_missing.png")
        if namespace_state == "unknown":
            Util.exit_error(f"BMDP '{dp_name}' is registered, but the cluster could not be queried to confirm namespace '{namespace}'; refusing to record it as complete.", self.page, "bmdp_namespace_unknown.png")

        running_pods = self._count_namespace_pods(namespace, "--field-selector=status.phase=Running")
        if running_pods is None:
            Util.exit_error(f"BMDP '{dp_name}' namespace '{namespace}' could not be queried for pods; refusing to record it as complete.", self.page, "bmdp_pods_unknown.png")
        if running_pods == 0:
            Util.exit_error(f"BMDP '{dp_name}' namespace '{namespace}' has no Running pod; the registration commands did not deploy a workload.", self.page, "bmdp_pods_not_ready.png")

        ColorLogger.success(f"BMDP '{dp_name}' workload check passed: {running_pods} Running pod(s) in namespace '{namespace}'.")

    def _mark_bmdp_complete(self, dp_name):
        """Record completion evidence for a BMDP.

        This is the ONLY place the completion status is written, and it must stay that way:
        both the report guard above and the recipe's create-bmdp pre-check treat that status
        as proof the data plane really came up, and the report file outlives the process on a
        host mount. Writing it any earlier — while the workload is still unproven — is what
        lets a later task retry short-circuit to green on a data plane that deployed nothing.

        set_dataplane_info only mutates an entry that already exists, so set_dataplane must run
        first or the write is a silent no-op. Call this only once the data plane is proven up.
        """
        ReportYaml.set_dataplane(dp_name)
        ReportYaml.set_dataplane_info(dp_name, "status", BMDP_STATUS_RUNNING)
        ReportYaml.set_dataplane_info(dp_name, "runCommands", True)

    def _recover_unhealthy_bmdp(self, dp_name, retry):
        """Report a Control Plane record for a BMDP that exists but is not healthy.

        This deliberately does NOT delete anything. An automatic delete-and-re-register was
        considered and rejected: the only evidence available here is a namespace name taken
        from the environment, which is never read back from the record being deleted, so the
        proof and the victim are decoupled. The same entry point is reachable from the
        unauthenticated local script endpoint with a caller-supplied data plane name and
        namespace, which would turn any mistake into a remote force-delete of someone else's
        data plane — and a force delete drops the Control Plane record while orphaning the
        real workload. The acceptance criterion is satisfied either way: the short-circuit no
        longer fires on an unhealthy data plane, and the task fails instead of reporting green.

        Cluster state is still gathered, but only to make the failure message actionable.
        """
        del retry  # recovery is not retried; a human decides what to do with the record.

        namespace = self._bmdp_namespace(dp_name)
        evidence = f"namespace '{namespace}'"
        if ENV.IS_CLUSTER_ACCESSIBLE:
            namespace_state = self._namespace_state(namespace)
            if namespace_state == "absent":
                evidence = f"{evidence} does not exist, so the registration commands never ran"
            elif namespace_state == "unknown":
                evidence = f"{evidence} could not be queried"
            else:
                pod_count = self._count_namespace_pods(namespace)
                if pod_count is None:
                    evidence = f"{evidence} exists but could not be queried for pods"
                elif pod_count == 0:
                    evidence = f"{evidence} exists but has no pod, so the registration commands never ran"
                else:
                    evidence = f"{evidence} has {pod_count} pod(s), so the data plane is deployed but has not gone healthy"
        else:
            evidence = f"{evidence} could not be checked because the cluster is not accessible"

        Util.exit_error(
            f"BMDP '{dp_name}' already exists in the Control Plane but is not healthy: {evidence}. "
            f"Refusing to treat it as created. Delete the data plane in the Control Plane (and remove "
            f"{namespace} if it is left behind), then re-run.",
            self.page, "bmdp_unhealthy_existing.png")

    @staticmethod
    def _bmdp_namespace(dp_name):
        """The namespace a BMDP was actually registered with.

        The environment default is only a fallback: a data plane registered by the CLI path, by
        hand, or by an earlier run with a different setting can have a different namespace, and
        judging it against the current environment would report a healthy data plane as broken.
        """
        recorded = ReportYaml.get_dataplane_info(dp_name, "namespace")
        if recorded and str(recorded).strip() and str(recorded).strip() != "null":
            return str(recorded).strip()
        return ENV.TP_AUTO_K8S_BMDP_NAMESPACE


    @staticmethod
    def _safe_k8s_name(name):
        """Reject anything that is not a plain Kubernetes object name.

        These names are interpolated into commands that run through a shell, and they come
        from the environment, so validate rather than trust. A DNS-1123 label cannot contain
        a shell metacharacter, which makes this both the correctness check and the safety one.
        """
        if not name or not re.fullmatch(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?", name):
            raise ValueError(f"Refusing to use '{name}' as a Kubernetes name: not a DNS-1123 label.")
        return name

    def _namespace_state(self, namespace):
        """Return 'present', 'absent' or 'unknown' for a namespace.

        'unknown' is the important one. get_command_output returns None on ANY non-zero exit
        — an expired kubeconfig, an API-server blip, kubectl missing from PATH — so treating
        None as 'absent' would let a transient failure classify a live data plane as a
        leftover and delete a real workload. --ignore-not-found separates the two: a
        successful lookup of a missing namespace exits 0 with empty output.
        """
        output = Helper.get_command_output(
            f"kubectl get namespace {self._safe_k8s_name(namespace)} --ignore-not-found -o name",
            is_print_cmd=True)
        if output is None:
            return "unknown"
        return "present" if output.strip() else "absent"

    def _count_namespace_pods(self, namespace, extra_args=""):
        """Count pods in a namespace, or return None when the count cannot be established.

        None and 0 must stay distinct: get_command_output returns None on any non-zero exit,
        and callers here decide whether to DELETE a data plane, so 'kubectl failed' must never
        be read as 'there are no pods'.
        """
        command = f"kubectl get pods -n {self._safe_k8s_name(namespace)} --no-headers"
        if extra_args:
            command = f"{command} {extra_args}"
        output = Helper.get_command_output(command, is_print_cmd=True)
        if output is None:
            return None
        return len([line for line in output.splitlines() if line.strip()])

    @staticmethod
    def _ensure_shebang(file_path):
        """Give a downloaded registration script an interpreter line if it has none.

        Helper.run_shell_file exec's the file directly on Linux, so a script without a
        shebang dies with 'Exec format error'. The Fresco wizard downloads the raw command
        text with no interpreter line, and the failure is SILENT in the worst way: every
        command no-ops, the flow still clicks Done, and the Control Plane still shows a data
        plane - one that has nothing installed behind it and never connects. Observed on
        CP 1.21 (PCP-24237); the legacy wizard's downloads already carried a shebang, which
        is why this only surfaced now.

        Prepending is safe for both: a file that already starts with '#!' is left alone.
        """
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        if content.startswith("#!"):
            return False

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"#!/bin/bash\n{content}")
        print(f"Added a '#!/bin/bash' interpreter line to {file_path}")
        return True

    def k8s_run_dataplane_command(self, dp_name, step_name, download_selector, step,
                                  abort_on_failure=True):
        """Download one registration command, apply the per-step extras, and RUN it.

        SHARED BY FOUR FLOWS, not just the Fresco one: the Fresco register loop, the legacy
        k8s register loop, the legacy BMDP register loop, and delete-data-plane. So the two
        changes made here for PCP-24237 reach the legacy paths too, and that is deliberate:

        * `_ensure_shebang` is inert on legacy downloads - they already carry an interpreter
          line - so it only ever fires for Fresco's raw command text.
        * aborting on a non-zero exit is NOT inert. On a CP 1.20 Control Plane a registration
          helm/kubectl that exited non-zero used to be logged and walked past; it now aborts
          the run. That is a real behaviour change to a path this ticket otherwise freezes,
          and it is the point: a swallowed exit code is the same failure class the missing
          shebang was one instance of, and leaving legacy able to report success over a
          half-installed data plane would be keeping the bug on purpose.

        `abort_on_failure=False` is for TEARDOWN, and delete-data-plane passes it. Aborting
        there is wrong twice over: the run would exit before clicking the delete dialog's
        confirm button and before `ReportYaml.remove_dataplane`, leaving the data plane half
        torn down and the rest of the teardown skipped - and teardown scripts exit non-zero
        for entirely benign reasons (a `helm uninstall` of a release that is already gone, a
        `kubectl delete` on a missing namespace). A partially-installed data plane, which is
        exactly what this ticket's defect produced, is the input most likely to cause one.
        """
        ColorLogger.info(f"Running command for: {step_name}")
        print(f"Download: {step_name}")
        with self.page.expect_download() as download_info:
            download_selector.click()

        file_name = f"{dp_name}_{step}.sh"
        file_path = Util.download_file(download_info.value, file_name)
        # Preparing the file must honour the SAME best-effort contract as running it.
        # _ensure_shebang reads and rewrites the download, so a file that is not valid
        # UTF-8 (or a download that raced to disk) raises straight out of this method -
        # past the abort_on_failure branch below and past k8s_delete_dataplane's confirm
        # click and ReportYaml.remove_dataplane, which is precisely the half-torn-down
        # teardown that abort_on_failure=False exists to prevent.
        try:
            self._ensure_shebang(file_path)
        except (OSError, UnicodeDecodeError) as e:
            if abort_on_failure:
                Util.exit_error(f"Registration command '{step_name}' for Data Plane '{dp_name}' could not be prepared: {e}.",
                                self.page, "k8s_run_dataplane_command_failed.png")
                return
            ColorLogger.warning(f"Could not add an interpreter line to {file_path}: {e}; running it as-is.")
        # Compared case-insensitively: CP 1.21 re-capitalised the title to
        # '1. Helm Repository Configuration', and an exact match would have skipped the repo
        # reset silently, leaving a stale helm repo to serve the registration charts.
        if step_name.casefold() == HELM_REPO_COMMAND_TITLE.casefold():
            # read the file content
            with open(file_path, "r", encoding="utf-8") as f:
                file_content = f.read()
                # get name "tibco-platform-public" from "helm repo add tibco-platform-public https://"
                repo_name = file_content.split("helm repo add ")[1].split(" ")[0]
                if repo_name:
                    # remove the repo first
                    print(f"Removing existing helm repo: {repo_name}")
                    Helper.get_command_output(f"helm repo remove {repo_name}", True)

        # add network_policies if ENV.TP_CREATE_NETWORK_POLICIES is true
        if step_name.casefold() == SERVICE_ACCOUNT_COMMAND_TITLE.casefold():
            if ENV.TP_CREATE_NETWORK_POLICIES == "true":
                # add network_policies at the end of the file
                network_policies = f" --set networkPolicy.create=true --set networkPolicy.createDeprecatedPolicies=true --set networkPolicy.createInternetScopePolicies=true --set networkPolicy.createClusterScopePolicies=true --set networkPolicy.createDeprecatedPolicies=false  --set networkPolicy.nodeCidrIpBlock={ENV.TP_CLUSTER_NODE_CIDR} --set networkPolicy.podCidrIpBlock={ENV.TP_CLUSTER_POD_CIDR} --set networkPolicy.serviceCidrIpBlock={ENV.TP_CLUSTER_SERVICE_CIDR}"
                with open(file_path, "a", encoding="utf-8") as f:
                    f.write(network_policies)
                    ColorLogger.info(f"Adding Network Policies: {network_policies} for {step_name} to {file_name}")

            if ENV.TP_AUTO_K8S_DP_SERVICE_ACCOUNT_CREATION_ADDITIONAL_SETTINGS:
                # add namespace to the file
                other_settings = f" {ENV.TP_AUTO_K8S_DP_SERVICE_ACCOUNT_CREATION_ADDITIONAL_SETTINGS}"
                with open(file_path, "a", encoding="utf-8") as f:
                    f.write(other_settings)
                    ColorLogger.info(f"Adding additional settings: {other_settings} for {step_name} to {file_name}")

        if ENV.TP_IS_CERT_SELF_SIGNED:
            with open(file_path, "r", encoding="utf-8") as f:
                file_content = f.read()
            if 'helm upgrade' in file_content:
                modified = False
                dp_namespace = f"{dp_name}ns"
                if 'dp-configure-namespace' in file_content:
                    # Create cert secret before the namespace configuration step
                    # cert_path is the form handed to the native kubectl: on Windows (Git Bash)
                    # MSYS path conversion is disabled (PCP-20701), so convert /tmp to a Windows
                    # path with `cygpath -w`; on Linux cygpath is absent and we keep /tmp as-is.
                    secret_cmd = (
                        f'cert_file=/tmp/cp-cert.pem\n'
                        f'cert_path="$(cygpath -w "$cert_file" 2>/dev/null || echo "$cert_file")"\n'
                        f'kubectl get secret default-certificate -n ingress-system -o jsonpath="{{.data.tls\\.crt}}" | base64 --decode > "$cert_file"\n'
                        f'kubectl create secret generic self-signed-cert -n "{dp_namespace}" --from-file=cert="$cert_path"\n'
                        f'rm -f "$cert_file"\n'
                    )
                    ColorLogger.info("Self-signed certificate detected, inserting cert secret creation...")
                    file_content = file_content.replace('helm upgrade', secret_cmd + 'helm upgrade', 1)
                    modified = True
                if modified:
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(file_content)

        print(f"Run command for: {step_name}")
        if not abort_on_failure:
            # Teardown is best-effort by design - see the docstring. Failures are logged by
            # run_shell_file and the caller carries on to finish the delete.
            Helper.run_shell_file(file_path)
            print(f"Command for step: {step_name} is executed, wait for 3 seconds.")
            self.page.wait_for_timeout(3000)
            return

        # raise_on_failure: a registration command that exits non-zero has not registered
        # anything, and the default swallow-and-return-"" made that indistinguishable from
        # success - the loop went on to the next command, Done was clicked, and the task went
        # green over a data plane with nothing behind it. The missing shebang was one cause of
        # that; a failing helm/kubectl is another, and this closes the class rather than the
        # instance (PCP-24237).
        try:
            Helper.run_shell_file(file_path, raise_on_failure=True)
        except Exception as e:
            Util.exit_error(f"Registration command '{step_name}' for Data Plane '{dp_name}' failed: {e}. "
                            f"The data plane is registered in the Control Plane but its cluster side is incomplete.",
                            self.page, "k8s_run_dataplane_command_failed.png")
            return
        print(f"Command for step: {step_name} is executed, wait for 3 seconds.")
        self.page.wait_for_timeout(3000)

    def k8s_wait_bmdp_ready(self, dp_name, is_update_report=True):
        """Wait for the data plane card to report ready.

        `is_update_report=False` withholds the completion marker. A green card only says
        the Control Plane is happy; it is not proof that the registration commands ran, so
        the BMDP flow defers the marker until the cluster workload has been checked too.
        Writing it here would leave the marker on disk when that later check aborts, and
        the report path outlives the process — the next task retry would then short-circuit
        to green on a data plane that deployed nothing.
        """
        ColorLogger.info(f"Wait for '{dp_name}' getting ready...")
        data_plane_card = self.page.locator(".data-plane-card", has=self.page.locator('.data-plane-name', has_text=dp_name))
        if not Util.check_dom_visibility(self.page, data_plane_card.locator('.data-plane-status svg.green'), 20, 300, True):
            Util.exit_error(f"Data Plane '{dp_name}' is not ready.", self.page, "dp_config_bmdp_status.png")

        ColorLogger.success(f"Data Plane '{dp_name}' is ready.")
        if is_update_report:
            ReportYaml.set_dataplane(dp_name)
            ReportYaml.set_dataplane_info(dp_name, "status", BMDP_STATUS_RUNNING)

    def k8s_wait_tunnel_connected(self, dp_name, is_update_report=True):
        print(f"Waiting for Data Plane {dp_name} to be created and ready.")
        self.goto_left_navbar_dataplane()
        print(f"Navigated to Data Planes list page, and checking for {dp_name} is created.")
        self.page.locator('.data-plane-name', has_text=dp_name).wait_for(state="visible")
        if not self.page.locator('.data-plane-name', has_text=dp_name).is_visible():
            Util.exit_error(f"DataPlane {dp_name} is not created.", self.page, "k8s_wait_tunnel_connected_1.png")

        if is_update_report:
            ReportYaml.set_dataplane(dp_name)
        data_plane_card = self.page.locator(".data-plane-card", has=self.page.locator('.data-plane-name', has_text=dp_name))

        # No-tibtunnel mode (hybrid connectivity disabled): there is no tibtunnel to
        # wait for — the CP reaches the DP over the configured Reachable DP URL. Skip
        # the tunnel-status wait and instead confirm DP readiness via the card-level
        # DP status icon (the same signal k8s_wait_bmdp_ready uses).
        if not ENV.TP_AUTO_ENABLE_HYBRID_CONNECTIVITY:
            ColorLogger.success(f"DataPlane {dp_name} is created. Hybrid connectivity disabled, skipping tunnel-connected wait.")
            print(f"Waiting for DataPlane {dp_name} to be ready (no-tibtunnel mode)...")
            # Match k8s_wait_bmdp_ready: poll every 20s up to 300s and refresh the DP list page
            # between polls (is_refresh=True) — the DP status icon only turns green after a reload.
            if not Util.check_dom_visibility(self.page, data_plane_card.locator('.data-plane-status svg.green'), 20, 300, True):
                Util.exit_error(f"DataPlane {dp_name} is not ready, exit program and recheck again.", self.page, "k8s_wait_dp_ready.png")
            ColorLogger.success(f"DataPlane {dp_name} is ready.")
            ReportYaml.set_dataplane_info(dp_name, "tunnelConnected", False)
            return

        ColorLogger.success(f"DataPlane {dp_name} is created, waiting for tunnel connected.")
        print(f"Waiting for DataPlane {dp_name} tunnel connected...")
        if not Util.check_dom_visibility(self.page, data_plane_card.locator('.tunnel-status svg.green'), 10, 180):
            Util.exit_error(f"DataPlane {dp_name} tunnel is not connected, exit program and recheck again.", self.page, "k8s_wait_tunnel_connected_2.png")

        ColorLogger.success(f"DataPlane {dp_name} tunnel is connected.")
        ReportYaml.set_dataplane_info(dp_name, "tunnelConnected", True)

    def k8s_setup_dp_reachability(self, dp_name, namespace, reachable_url, is_bmdp=False):
        # No-tibtunnel (hybrid disabled) reachability: make the registered Reachable DP URL actually
        # reachable from the CP. Option A (default): create a controller-adaptive ingress in the DP
        # namespace pointing at the cpdpproxy service. Option B (TP_AUTO_DP_APPLY_NETPOL_LABELS=true):
        # label the cpdpproxy (DP) and tp-dp-proxy (CP) deployments so tp-dp-proxy can reach the
        # cpdpproxy ClusterIP directly through the namespace deny-all NetworkPolicies.
        if ENV.TP_AUTO_ENABLE_HYBRID_CONNECTIVITY:
            return
        if not ENV.TP_AUTO_DP_MANAGE_REACHABILITY:
            ColorLogger.info("TP_AUTO_DP_MANAGE_REACHABILITY is false, skipping no-tibtunnel reachability setup.")
            return
        if not ENV.IS_CLUSTER_ACCESSIBLE:
            ColorLogger.warning("Cluster is not accessible, skipping no-tibtunnel reachability setup.")
            return

        dp_type = "BMDP" if is_bmdp else "DataPlane"
        if ENV.TP_AUTO_DP_APPLY_NETPOL_LABELS:
            ColorLogger.info(f"No-tibtunnel {dp_type} '{dp_name}': applying private-reachability NetworkPolicy labels (Option B).")
            self._apply_dp_reachability_netpol_labels(namespace)
        else:
            ColorLogger.info(f"No-tibtunnel {dp_type} '{dp_name}': creating public cpdpproxy {ENV.TP_AUTO_INGRESS_OBJECT} (Option A).")
            self._apply_cpdpproxy_public_ingress(namespace, reachable_url)

        # Cross-cutting: dp-proxy (CP side) caches DP connection-details and keeps dialing the
        # previous (stale) address until the cache expires. Restart it so it re-reads the
        # registered reachable URL and uses the now-in-place ingress/labels immediately.
        self._restart_dp_proxy()

    def _restart_dp_proxy(self):
        cp_ns = ENV.TP_AUTO_CP_NAMESPACE
        deploy = ENV.TP_AUTO_CP_DP_PROXY_DEPLOYMENT
        ColorLogger.info(f"Restarting {deploy} in {cp_ns} to invalidate the no-tibtunnel connection-details cache.")
        out = Helper.get_command_output(f"kubectl rollout restart deployment {deploy} -n {cp_ns}", is_print_cmd=True)
        if out is None:
            ColorLogger.warning(f"Could not restart {deploy} in {cp_ns}; the CP may keep using the cached DP address.")
            return
        print(out)
        # Best-effort wait so the refreshed dp-proxy is ready before we verify DP readiness.
        Helper.get_command_output(f"kubectl rollout status deployment {deploy} -n {cp_ns} --timeout=150s", is_print_cmd=True)

    def _apply_cpdpproxy_public_ingress(self, namespace, reachable_url):
        host = urlparse(reachable_url).hostname or reachable_url.split("://")[-1].split("/")[0]
        controller = ENV.TP_AUTO_GATEWAY_CONTROLLER if ENV.TP_AUTO_INGRESS_OBJECT == "gateway" else ENV.TP_AUTO_INGRESS_CONTROLLER
        manifest = self._build_cpdpproxy_ingress_manifest(host, namespace)
        ColorLogger.info(f"Applying cpdpproxy public {ENV.TP_AUTO_INGRESS_OBJECT} (controller: {controller}) for host '{host}' in namespace '{namespace}'.")
        print(f"Manifest:\n{manifest}")
        cmd = "cat <<'EOF' | kubectl apply -f -\n" + manifest + "EOF\n"
        output = Helper.get_command_output(cmd, is_print_cmd=True)
        if output is None:
            ColorLogger.warning(f"Failed to apply cpdpproxy public {ENV.TP_AUTO_INGRESS_OBJECT} for host '{host}'; the CP may not be able to reach the DP.")
        else:
            ColorLogger.success(f"cpdpproxy public {ENV.TP_AUTO_INGRESS_OBJECT} applied for host '{host}'.")
            print(output)

    def _apply_dp_reachability_netpol_labels(self, dp_namespace):
        # cpdpproxy (DP side) must accept cross-namespace ingress; tp-dp-proxy (CP side) must be allowed
        # to egress to the DP namespace. Label both the Deployment object and its pod template so the
        # pods carry the label (NetworkPolicy selects on pod labels) and it survives restarts.
        self._label_deployment_and_template(ENV.TP_AUTO_DP_PROXY_SERVICE_NAME, dp_namespace,
                                            "networking.platform.tibco.com/cluster-ingress", "enable")
        self._label_deployment_and_template(ENV.TP_AUTO_CP_DP_PROXY_DEPLOYMENT, ENV.TP_AUTO_CP_NAMESPACE,
                                            "networking.platform.tibco.com/cluster-egress", "enable")

    @staticmethod
    def _label_deployment_and_template(deployment, namespace, label_key, label_value):
        labels = {label_key: label_value}
        patch = json.dumps({"metadata": {"labels": labels}, "spec": {"template": {"metadata": {"labels": labels}}}})
        cmd = f"kubectl patch deployment {deployment} -n {namespace} --type=merge -p '{patch}'"
        output = Helper.get_command_output(cmd, is_print_cmd=True)
        if output is None:
            ColorLogger.warning(f"Could not label deployment '{deployment}' in '{namespace}' ({label_key}={label_value}); it may not exist.")
        else:
            ColorLogger.success(f"Labeled deployment '{deployment}' in '{namespace}': {label_key}={label_value}")
            print(output)

    def _build_cpdpproxy_ingress_manifest(self, host, namespace):
        # Mirror the capability charts' controller-adaptive ingress pattern (dp-flogo-app / dp-bwce-app):
        # one shape per deployed controller, selected from the same ENV the automation feeds the CP
        # "Add Ingress/Route" wizard. cpdpproxy needs a plain host -> service route (no prefix strip).
        svc = ENV.TP_AUTO_DP_PROXY_SERVICE_NAME
        port = ENV.TP_AUTO_DP_PROXY_SERVICE_PORT
        name = "cpdpproxy-public"

        if ENV.TP_AUTO_INGRESS_OBJECT == "gateway":
            section_name = f"\n    sectionName: {ENV.TP_AUTO_GATEWAY_SECTION_NAME}" if ENV.TP_AUTO_GATEWAY_SECTION_NAME else ""
            return (
                "apiVersion: gateway.networking.k8s.io/v1\n"
                "kind: HTTPRoute\n"
                "metadata:\n"
                f"  name: {name}\n"
                f"  namespace: {namespace}\n"
                "  annotations:\n"
                f"    platform.tibco.com/controller-name: \"{ENV.TP_AUTO_GATEWAY_CONTROLLER}\"\n"
                "spec:\n"
                "  parentRefs:\n"
                f"  - name: {ENV.TP_AUTO_GATEWAY_NAME}\n"
                f"    namespace: {ENV.TP_AUTO_GATEWAY_NAMESPACE}{section_name}\n"
                "  hostnames:\n"
                f"  - \"{host}\"\n"
                "  rules:\n"
                "  - matches:\n"
                "    - path:\n"
                "        type: PathPrefix\n"
                "        value: /\n"
                "    backendRefs:\n"
                f"    - name: {svc}\n"
                f"      port: {port}\n"
                "      weight: 100\n"
            )

        controller = ENV.TP_AUTO_INGRESS_CONTROLLER
        if controller == "openshiftRouter":
            return (
                "apiVersion: route.openshift.io/v1\n"
                "kind: Route\n"
                "metadata:\n"
                f"  name: {name}\n"
                f"  namespace: {namespace}\n"
                "  annotations:\n"
                f"    platform.tibco.com/controller-name: \"{controller}\"\n"
                "spec:\n"
                f"  host: {host}\n"
                "  path: /\n"
                "  to:\n"
                "    kind: Service\n"
                f"    name: {svc}\n"
                "    weight: 100\n"
                "  port:\n"
                f"    targetPort: {port}\n"
                "  wildcardPolicy: None\n"
            )

        # Classic Ingress (traefik / nginx / haProxy / kong) — controller chosen via ingressClassName.
        annotations = f"    platform.tibco.com/controller-name: \"{controller}\"\n"
        if controller == "nginx":
            annotations += "    nginx.ingress.kubernetes.io/proxy-body-size: \"0\"\n"
        return (
            "apiVersion: networking.k8s.io/v1\n"
            "kind: Ingress\n"
            "metadata:\n"
            f"  name: {name}\n"
            f"  namespace: {namespace}\n"
            "  annotations:\n"
            f"{annotations}"
            "spec:\n"
            f"  ingressClassName: {ENV.TP_AUTO_INGRESS_CONTROLLER_CLASS_NAME}\n"
            "  rules:\n"
            f"  - host: {host}\n"
            "    http:\n"
            "      paths:\n"
            "      - path: /\n"
            "        pathType: Prefix\n"
            "        backend:\n"
            "          service:\n"
            f"            name: {svc}\n"
            "            port:\n"
            f"              number: {port}\n"
        )

    def k8s_delete_app(self, dp_name, capability, app_name):
        ColorLogger.info(f"Deleting {capability} app '{app_name}' in DataPlane {dp_name}")
        self.goto_dataplane(dp_name)
        self.page.wait_for_timeout(3000)
        app_row = self.page.locator(f"#app-list-table tr.{capability.upper()}", has=self.page.locator("td.app-name", has_text=app_name))
        if app_row.is_visible():
            app_row.locator(".actions a:has(svg[id^='delete'])").click()
            print(f"Clicked 'Delete' icon in app '{app_name}' row")
            self.page.locator(".confirmation .pl-modal__container").wait_for(state="visible")
            print(f"Delete confirmation dialog is displayed.")
            self.page.locator(".confirmation #confirm-button", has_text="Yes").click()
            print("Clicked 'Yes' button in confirmation dialog")
            self.page.wait_for_timeout(2000)
            if not self.page.locator(f"#app-list-table tr.{capability.upper()}", has=self.page.locator("td.app-name", has_text=app_name)).is_visible():
                ColorLogger.success(f"Deleted {capability} app '{app_name}' in DataPlane {dp_name}")
                ReportYaml.remove_capability_app(dp_name, capability, app_name)
        else:
            ColorLogger.warning(f"{capability} app '{app_name}' does not exist.")

    # --- template-method contract for the o11y navigation below ---------------------
    # goto_dataplane_o11y_config() (and therefore switch_to_global_config(), which now
    # re-navigates to confirm the link) depends on these two. They are implemented by the
    # configuration subclasses - PageObjectDataPlaneConfiguration and
    # PageObjectBMDPConfiguration - because the selectors differ per data plane kind.
    # Declared here so the dependency is an explicit contract with a clear message
    # instead of an AttributeError raised three frames deep inside a retry loop.

    def goto_dataplane_config(self):
        raise NotImplementedError(
            f"{type(self).__name__} must implement goto_dataplane_config() to use the o11y "
            "navigation - it is provided by PageObjectDataPlaneConfiguration / "
            "PageObjectBMDPConfiguration, not by PageObjectDataPlane itself.")

    def goto_dataplane_config_sub_menu(self, sub_menu_name, *args, **kwargs):
        raise NotImplementedError(
            f"{type(self).__name__} must implement goto_dataplane_config_sub_menu() to use the "
            "o11y navigation - it is provided by PageObjectDataPlaneConfiguration / "
            "PageObjectBMDPConfiguration, not by PageObjectDataPlane itself.")

    def goto_dataplane_o11y_config(self, dp_name):
        """Open '<dp_name>' -> Data Plane configuration -> Observability.

        The one navigation path to the o11y panel, shared by o11y_config_switch_to_global
        and by switch_to_global_config's post-link re-check. Template method over the two
        hooks above.
        """
        self.goto_left_navbar_dataplane()
        self.goto_dataplane(dp_name)
        self.goto_dataplane_config()
        self.goto_dataplane_config_sub_menu("Observability")

    def is_linked_to_global_config(self, interval=5, max_wait=10):
        """True once the o11y panel shows the DP is linked to the Global resource.

        Polls the CURRENT page without reloading, so it is only meaningful while the
        Observability panel is open (see switch_to_global_config).
        """
        return Util.check_dom_visibility(
            self.page,
            self.page.locator(".o11y-panel-actions .global-resource-name", has_text="View in Global Configuration"),
            interval, max_wait)

    def recheck_linked_to_global_config(self, dp_name, attempts=3, interval=5, max_wait=10):
        """Confirm the link by RE-OPENING the Observability panel, up to `attempts` times.

        Clicking 'Link' / 'Yes' takes the UI back to the data planes LIST page, where
        ".o11y-panel-actions .global-resource-name" does not exist. Polling there - with or
        without a reload - can only ever time out, because Util.refresh_page() reloads
        whatever page we are on, i.e. the list (PCP-23558: the resulting false "link failed"
        became fatal once PCP-23553 started asserting on the report key, which skipped the
        DP activation upload and left every Flogo app CrashLooping on license validation).

        Linking is also applied on the backend a few seconds later, so the confirmation
        needs a FRESH read of the panel rather than a longer poll of a stale one - hence
        re-navigating each round instead of passing is_refresh=True.

        Cost, stated honestly: the SUCCESS path is one navigation plus a ~5s probe, which
        is cheaper than the 30s + 6 reloads it replaces. Only a genuine failure pays all
        three rounds - each is a full navigation plus ~15s of polling (check_dom_visibility
        waits `interval` up front and again after every attempt), so ~1-2 minutes before a
        data plane is declared unlinked. That is the deliberate trade: a false negative
        here is what PCP-23558 cost us, so the confirmation is allowed to be slow when it
        is about to report failure.

        Each round's navigation is isolated: re-navigating is a much larger failure
        surface than the plain page.reload() it replaces (a whole list -> DP -> config ->
        Observability walk, whose helpers raise PlaywrightTimeoutError or call
        Util.exit_error -> sys.exit(1) on a miss). Unisolated, a transient list-render
        race on round 1 would (a) cancel the other two rounds this retry exists to
        provide and (b) abort the entire run where the old check merely warned - a worse
        failure mode than the one being fixed. A navigation failure is therefore just
        "not confirmed this round"; only an exhausted budget reports failure, through the
        same non-fatal warning as before. The two are logged distinctly so a pipeline-log
        triage can tell "still not linked" from "could not get back to the panel" - that
        distinction is how PCP-23558 itself was diagnosed.
        """
        for attempt in range(1, attempts + 1):
            print(f"Re-open '{dp_name}' Observability panel to verify the link (attempt {attempt}/{attempts})")
            try:
                self.goto_dataplane_o11y_config(dp_name)
            except (Exception, SystemExit) as e:
                # SystemExit explicitly: Util.exit_error() calls sys.exit(1) and that is a
                # BaseException, invisible to "except Exception" (same trap as
                # po_bmdp_config.py:124/150). NOT BaseException - KeyboardInterrupt must
                # still abort the run.
                ColorLogger.warning(f"Round {attempt}/{attempts}: could not re-open the Observability panel for '{dp_name}': {e}")
                continue
            if self.is_linked_to_global_config(interval, max_wait):
                return True
            print(f"Round {attempt}/{attempts}: '{dp_name}' is not linked to the Global resource yet")
        return False

    def switch_to_global_config(self, dp_name):
        ColorLogger.info(f"Switch to Global Observability Resource")
        # NOTE on waits: the o11y panel is an Angular component that can take several seconds
        # to (re-)render. The checks below poll without reloading the page (is_refresh=False)
        # so a transient slow render does not get reset mid-flow. Previously these were
        # single-shot checks with is_refresh=True, where a miss on the legacy ".switch-to-global"
        # selector reloaded the page and the following ".use-global-resource" check then raced
        # the freshly re-rendering panel -> a false "link failed".
        print("PreCheck if Data Plane is already linked to Global Observability Resource...")
        if self.is_linked_to_global_config(5, 10):
            ColorLogger.success(f"Linked {dp_name} to Global Observability Resource successfully.")
            ReportYaml.set_dataplane_info(dp_name, "switchGlobal", True)
            return

        print("Check if 'Switch to Global' or 'Use Global Resource' button is visible...")
        # ".switch-to-global" is the legacy (pre-1.5) selector; absent on newer CP versions.
        if Util.check_dom_visibility(self.page, self.page.locator(".switch-to-global"), 5, 5) and self.page.locator(".switch-to-global").is_enabled():
            ColorLogger.info(f"Switching current Data Plane '{dp_name}' configuration to Global Observability Resource")
            self.page.locator(".switch-to-global").click()
            print("Clicked 'Switch to Global' button")
            self.page.locator(".confirmation .pl-modal__heading", has_text="Switch to Global Observability Resource?").wait_for(state="visible")
            print("Confirmation dialog is visible")
            self.page.locator("#confirm-button", has_text="Yes").click()
            print("Clicked 'Yes' button in confirmation dialog")
        elif Util.check_dom_visibility(self.page, self.page.locator(".use-global-resource .o11y-btn"), 3, 30) and self.page.locator(".use-global-resource .o11y-btn").is_enabled():
            ColorLogger.info(f"Data Plane '{dp_name}' does not have configuration, Use Global Resource")
            self.page.locator(".use-global-resource .o11y-btn").click()
            print("Clicked 'Use Global Resource' button")
            self.page.locator(".confirmation .pl-modal__heading", has_text="Link Data plane to this resource ?").wait_for(state="visible")
            print("Confirmation dialog is visible")
            self.page.locator("#confirm-button", has_text="Link").click()
            print("Clicked 'Link' button in confirmation dialog")

        print("Double Check if Data Plane is already linked to Global Observability Resource...")
        # Linking applies global o11y config on the backend, so the confirmation can lag a few
        # seconds; re-open the panel and poll it, up to 3 rounds, before declaring failure.
        if self.recheck_linked_to_global_config(dp_name):
            ColorLogger.success(f"Linked {dp_name} to Global Observability Resource successfully.")
            ReportYaml.set_dataplane_info(dp_name, "switchGlobal", True)
        else:
            ColorLogger.warning(f"Linked {dp_name} to Global Observability Resource failed.")
