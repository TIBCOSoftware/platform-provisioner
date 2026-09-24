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
# PCP-23927 — contract smoke for the EMS provisioning page object.
#
# CP 1.21 rebuilt the Provision EMS wizard on the shared "fresco" modal and gave it a new
# leading 'Server Configuration' step, which pushed '.resources-content' onto the SECOND step.
# The old flow waited for '.resources-content' straight after clicking 'Start' and so timed
# out deterministically. These tests pin what a live run cannot cheaply re-check per commit:
#   1. the flow no longer hard-waits on one wizard's marker — it branches on whichever renders,
#      so pre-1.21 Control Planes keep working;
#   2. the fresco selectors stay off React generated ids and build-hashed CSS-module classes,
#      which change on every UI build;
#   3. the PrimeNG-specific handling this modal family demands (force-checked inputs, the
#      post-close overlay wait) is not quietly dropped — each of those was a live CP failure
#      in a sibling wizard before it was a rule here.
# The selectors themselves were ground-truthed against live CP 1.21.0 (ins-owen-tas-1).
#
# Assert on RESOLVED values (constants, selector-builder return values) rather than on the
# exact source text of a call, so a behaviour-preserving refactor does not false-fail. Source
# inspection is used only where the property under test really is "what the source may contain"
# (e.g. no generated ids anywhere in the selector literals).

import ast
import inspect
import re

from page_object import po_dp_ems
from page_object.po_dataplane import PageObjectDataPlane
from page_object.po_dp_ems import PageObjectDataPlaneEMS


def _selector_literals(module):
    """Every string literal in the module — i.e. the selectors actually used at runtime.

    Asserting against raw source would also match explanatory comments (which legitimately
    name the ids this wizard no longer has), so the checks below inspect literals only.
    """
    tree = ast.parse(inspect.getsource(module))
    return " | ".join(
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    )


class TestBothWizardsSupported:
    """CP 1.21+ fresco wizard and the pre-1.21 wizard must both still be drivable."""

    def test_readiness_gate_covers_both_wizards(self):
        # Resolved value, not source text: the gate must name BOTH markers, so whichever
        # wizard renders after 'Start' satisfies it. Waiting only on '.resources-content'
        # is the PCP-23927 timeout.
        either = PageObjectDataPlaneEMS.EITHER_WIZARD
        assert PageObjectDataPlaneEMS.FRESCO_WIZARD in either
        assert PageObjectDataPlaneEMS.RESOURCES_STEP in either
        assert "," in either, "must be a comma selector matching either wizard"

    def test_readiness_gate_is_narrowed_for_strict_mode(self):
        # bootstrap/CLAUDE.md §3: a comma selector matches ALL of them, so is_visible()/click()
        # throw once both are in the DOM unless the locator is narrowed.
        src = inspect.getsource(PageObjectDataPlaneEMS.ems_provision_capability)
        assert "EITHER_WIZARD).first" in src

    def test_wizard_detection_branches_on_the_fresco_container(self):
        # PCP-23946 item 3: narrowed with .first, so a leftover container from a prior mount
        # raises no strict-mode violation. Behaviour pinned in
        # tests/test_po_ems_o11y_behaviour.py::test_wizard_detection_survives_two_containers_in_the_dom.
        src = inspect.getsource(PageObjectDataPlaneEMS.ems_provision_capability)
        assert "FRESCO_WIZARD).first.is_visible()" in src
        assert "ems_provision_fresco_wizard(" in src

    def test_legacy_wizard_path_is_retained(self):
        # Old Control Planes are not deprecated on a schedule; their selectors must survive.
        src = inspect.getsource(PageObjectDataPlaneEMS.ems_provision_capability)
        for legacy in ("#message-storage-resource-table", "#log-storage-resource-table",
                       "#btnNextCapabilityProvision", "#ems-config-capability-instance",
                       "ems-config-eula", "#btn_next_configuration", "#btn_next_confirmation",
                       "#btn_go_to_dta_pln"):
            assert legacy in src, f"legacy wizard selector {legacy} was dropped"

    def test_both_paths_verify_the_capability_card(self):
        # The fresco branch returns early, so it must call the shared tail ITSELF; the legacy
        # branch falls through to the call at the end. Check each region separately — a single
        # "the string appears somewhere" assertion would pass even if the early return skipped it.
        src = inspect.getsource(PageObjectDataPlaneEMS.ems_provision_capability)
        assert hasattr(PageObjectDataPlaneEMS, "ems_verify_capability")
        fresco_branch, _, legacy_branch = src.partition("Detected the legacy EMS provisioning wizard")
        assert "ems_verify_capability(" in fresco_branch, "fresco branch returns without verifying"
        assert "ems_verify_capability(" in legacy_branch, "legacy branch falls through without verifying"


class TestFrescoWizardSelectors:
    """Ground-truthed against live CP 1.21.0 — see the module docstring."""

    def test_footer_matches_the_shared_fresco_container(self):
        # Same footer container the Infra MCP Server wizard uses; its buttons carry no ids.
        assert PageObjectDataPlaneEMS.FRESCO_WIZARD_FOOTER == ".fresco-wizard-modal-footer-system-actions"

    def test_footer_buttons_matched_by_exact_label(self):
        po = PageObjectDataPlaneEMS(None)
        selector = po.selector_fresco_footer_button("Provision Now")
        assert selector.startswith(PageObjectDataPlaneEMS.FRESCO_WIZARD_FOOTER)
        # :text-is, not a substring match — 'Next' would otherwise also hit 'Next step'.
        assert 'button:text-is("Provision Now")' in selector
        src = inspect.getsource(PageObjectDataPlaneEMS.ems_provision_fresco_wizard)
        assert '"Next"' in src and '"Provision Now"' in src

    def test_summary_confirm_button_is_not_the_legacy_label(self):
        # The legacy wizard confirmed with 'Provision TIBCO Enterprise Message Service'; the
        # fresco Summary step relabelled it, so the fresco path must not reuse the old text.
        src = inspect.getsource(PageObjectDataPlaneEMS.ems_provision_fresco_wizard)
        assert "Provision TIBCO Enterprise Message Service" not in src

    def test_server_name_located_by_stable_name_attribute(self):
        # Its id is React generated (fresco-<hash>-_r_1_) and changes on every mount.
        assert 'input[name="serverName"]' in _selector_literals(po_dp_ems)

    def test_no_react_generated_ids(self):
        # Literals only — a comment may legitimately cite a captured id as an example.
        assert not re.search(r"fresco-[0-9a-f]{6,}-_r_", _selector_literals(po_dp_ems)), (
            "React generated ids change on every mount and must never be used as selectors"
        )

    def test_no_build_hashed_css_module_classes(self):
        # e.g. _serverConfig_1m3yf_50 / _eua_1m3yf_11 / _summaryGrid_1m3yf_87 — the hash
        # changes on every UI build. Literals only, for the same reason as above.
        assert not re.search(r"_[A-Za-z]+_[0-9a-z]{5}_\d+", _selector_literals(po_dp_ems))

    def test_eula_checkbox_scoped_to_the_wizard(self):
        selector = PageObjectDataPlaneEMS(None).selector_fresco_eula_checkbox()
        assert selector.startswith(PageObjectDataPlaneEMS.FRESCO_WIZARD), (
            "an unscoped checkbox selector can match another dialog's checkbox"
        )
        assert "input.p-checkbox-input" in selector

    def test_dialog_close_button_scoped_to_the_wizard_dialog(self):
        # A bare '.p-dialog button.p-dialog-header-close' matches every mounted PrimeNG dialog
        # (a stray toast/confirmation) and trips Playwright strict mode.
        selector = PageObjectDataPlaneEMS(None).selector_fresco_dialog_close_button()
        assert selector.startswith(PageObjectDataPlaneEMS.FRESCO_WIZARD_DIALOG)
        assert "p-dialog-header-close" in selector

    def test_resource_rows_matched_on_name_then_parenthesis(self):
        # Entries read '<name> (<id>)'. A bare substring match would also select a resource
        # whose name merely contains the requested one. The regex now lives on the plural
        # (unnarrowed) builder; fresco_resource_row is the .first wrapper over it.
        src = inspect.getsource(PageObjectDataPlaneEMS.fresco_resource_rows)
        assert "re.escape(resource_name)" in src
        assert r"\s*\(" in src

    def test_resource_locator_is_rebuilt_per_call(self):
        # Project convention: never cache a locator across actions — the wizard re-renders
        # between the visibility poll and the click.
        src = inspect.getsource(PageObjectDataPlaneEMS.fresco_select_resource)
        assert src.count("self.fresco_resource_row(") >= 2

    def test_message_storage_required_log_storage_optional(self):
        # 'Message Storage' is marked required in the UI; 'Log Storage' is not. Assert the
        # required-ness argument per section without pinning the exact call formatting.
        src = inspect.getsource(PageObjectDataPlaneEMS.ems_provision_fresco_wizard)
        calls = dict(re.findall(
            r'fresco_select_resource\(\s*"([^"]+)"[^)]*?,\s*(True|False)\s*\)', src))
        assert calls.get("Message Storage") == "True"
        assert calls.get("Log Storage") == "False"

    def test_returns_to_the_dataplane_before_verifying(self):
        # The fresco final page only offers 'Go to <capability>', so the flow must navigate
        # back itself or ems_verify_capability looks at the wrong page.
        src = inspect.getsource(PageObjectDataPlaneEMS.ems_provision_fresco_wizard)
        assert "self.goto_dataplane(dp_name)" in src


class TestPrimeNgQuirksHandled:
    """Each of these was a real live-CP failure in a sibling fresco wizard before it was a rule."""

    def test_primeng_inputs_are_force_checked(self):
        # The real <input> is a transparent overlay on the styled box and fails Playwright's
        # default actionability check (po_dp_activespace.py, CHANGELOG 1.7.7x). A plain
        # .check() hangs the full timeout and throws an UNGUARDED error.
        src = inspect.getsource(po_dp_ems)
        checks = re.findall(r"\.check\(([^)]*)\)", src)
        assert checks, "expected the fresco flow to check the EUA box and a resource radio"
        for args in checks:
            assert "force=True" in args, f".check({args}) must pass force=True for PrimeNG inputs"

    def test_overlay_is_awaited_before_navigating_away(self):
        # PrimeNG keeps .p-dialog-mask up through the close animation; it swallows the left-nav
        # click inside goto_dataplane and fails AFTER provisioning already succeeded.
        # Index into the CODE only: a comment naming one of these calls would otherwise be
        # found first and scramble the ordering this test is about (PCP-23946).
        src = "\n".join(
            line.split("#", 1)[0]
            for line in inspect.getsource(PageObjectDataPlaneEMS.ems_provision_fresco_wizard).splitlines()
        )
        assert "self.wait_for_overlay_to_clear()" in src
        close_at = src.index("selector_fresco_dialog_close_button")
        # PCP-23946 item 2: the detach wait now carries an explicit timeout and is non-fatal,
        # matching wait_for_overlay_to_clear on the next line — both fire after provisioning
        # has already succeeded. Ordering is still what this test is about.
        detach_at = src.index('wait_for(state="detached", timeout=')
        overlay_at = src.index("self.wait_for_overlay_to_clear()")
        goto_at = src.index("self.goto_dataplane(dp_name)")
        # Same order as po_dp_activespace: close -> dialog detached -> mask cleared -> navigate.
        # A slow close animation can leave the modal attached while the mask is already
        # clearing, and either one still swallows the next navigation click.
        assert close_at < detach_at < overlay_at < goto_at

    def test_overlay_helper_is_shared_not_duplicated(self):
        # Lives on the common base so the ActiveSpaces and EMS fresco wizards share one
        # implementation (and its regression tests) instead of drifting apart.
        #
        # Asked of the CLASS, not of the source text. The old form stripped the one known
        # call and then forbade the string anywhere else, so a prose comment that merely
        # NAMED the method failed a test about redefinition — it could not fail for the
        # reason it was written for. PCP-23946 and PCP-23953 hit this independently and
        # fixed it independently; this is the merge of the two.
        #
        # vars() is kept over `"def wait_for_overlay_to_clear" not in getsource(...)`
        # because it answers the real question — is this name bound on THIS class — and so
        # also catches a rebinding that is not a `def` (an assignment, a decorator's return,
        # a name pulled in by a mixin). A source grep only catches the literal `def`.
        assert hasattr(PageObjectDataPlane, "wait_for_overlay_to_clear")
        assert "wait_for_overlay_to_clear" not in vars(PageObjectDataPlaneEMS), (
            "EMS must inherit it, not redefine it")

    def test_resource_visibility_polls_the_row_not_the_transparent_radio(self):
        # Polling is_visible() on the transparent input can read False while the row renders
        # fine, which would report a present resource as missing and hard-fail the run.
        src = inspect.getsource(PageObjectDataPlaneEMS.fresco_select_resource)
        poll_line = next(line for line in src.splitlines() if "check_dom_visibility" in line)
        assert "fresco_resource_row(" in poll_line
        assert "p-radiobutton-input" not in poll_line


class TestFailuresAreObservable:
    def test_fresco_step_transitions_use_check_dom_visibility(self):
        # Project convention: poll with logged progress + a screenshot on failure rather than
        # a silent wait_for(), which is exactly what made PCP-23927 an opaque 30s timeout.
        src = inspect.getsource(PageObjectDataPlaneEMS.ems_provision_fresco_wizard)
        # A silent wait_for(state="visible") on a variable-latency element is what made this
        # an opaque 30s timeout. wait_for(state="detached") on a dialog we just closed is a
        # different thing — bounded, normal page flow — and is allowed.
        assert 'wait_for(state="visible"' not in src
        assert src.count("Util.check_dom_visibility(") >= 3

    def test_every_footer_click_is_guarded(self):
        # A bare .click() on a stuck/soft-disabled button throws an unhandled Playwright
        # timeout with no screenshot. The shared helper guards, then clicks.
        src = inspect.getsource(PageObjectDataPlaneEMS.fresco_click_footer_button)
        assert "Util.check_dom_visibility(" in src
        assert "Util.exit_error(" in src
        wizard_src = inspect.getsource(PageObjectDataPlaneEMS.ems_provision_fresco_wizard)
        assert 'button:text-is' not in wizard_src, "footer clicks must go through the guarded helper"

    def test_missing_capability_card_is_fatal_and_polled(self):
        # page_cli records the capability as provisioned as soon as ems_verify_capability
        # returns, so warning here reports a green run for a Data Plane with no EMS. Fatal is
        # only safe because the card is polled WITH refreshes first (the backend creates it a
        # little after the request is accepted) and because the entry-point check makes a
        # retry idempotent.
        src = inspect.getsource(PageObjectDataPlaneEMS.ems_verify_capability)
        assert "capability-card #" in src, "the card must be polled, not read once"
        assert re.search(r"check_dom_visibility\([^)]*?capability-card", src, re.S) or \
               "capability-card #{self.capability}" in src
        assert "180, True" in src, "poll with refreshes on a real budget before failing"
        assert "Util.exit_error(" in src
        assert "Util.warning_screenshot(" not in src

    def test_capability_card_poll_is_narrowed_for_strict_mode(self):
        # A Data Plane may hold several EMS servers, and check_dom_visibility calls
        # is_visible() unguarded — an un-narrowed 'capability-card #ems' would raise a
        # strict-mode violation (observed live with two instances) instead of answering
        # "is any EMS card present yet?".
        src = inspect.getsource(PageObjectDataPlaneEMS.ems_verify_capability)
        poll_line = next(line for line in src.splitlines() if "capability-card #" in line)
        assert ".first" in poll_line

    def test_success_banner_is_advisory_and_generously_waited(self):
        # The final-page banner is a CONVENIENCE signal, not the authority — the capability
        # card is (see test_missing_capability_card_is_fatal_and_polled). Measured on a real
        # deploy-subscription run: under concurrent provisioning the banner had not appeared
        # after 120s even though EMS provisioned fine, so failing here reported failure on a
        # success and burned a ~5-minute retry. It must warn, not abort, and wait generously.
        src = inspect.getsource(PageObjectDataPlaneEMS.ems_provision_fresco_wizard)
        final_check = src[src.index("FRESCO_WIZARD_FINAL_PAGE"):]
        head = final_check.split("selector_fresco_dialog_close_button")[0]
        assert "Util.exit_error(" not in head, (
            "the banner must not abort the run — the capability-card check is the authority"
        )
        assert "Util.warning_screenshot(" in head
        budget = re.search(r"FRESCO_WIZARD_FINAL_PAGE[^)]*\),\s*\d+,\s*(\d+)\)", src)
        assert budget and int(budget.group(1)) >= 240, (
            "an idle instance shows the banner in ~10s; a loaded one needed >120s"
        )

    def test_the_card_check_is_still_the_fatal_authority(self):
        # Downgrading the banner is only safe BECAUSE this one aborts. Pinning both together
        # so a future edit cannot quietly leave neither of them fatal (silent-green again).
        assert "Util.exit_error(" in inspect.getsource(PageObjectDataPlaneEMS.ems_verify_capability)

    def test_fresco_failures_use_distinct_screenshots(self):
        # Two different failures writing the same file makes triage ambiguous. The ONE
        # legitimate reuse is the resource-row shot: it is the same step on both the
        # required and the optional branch.
        names = re.findall(r'"(ems_provision_capability-fresco-[^"]+\.png)"',
                           inspect.getsource(po_dp_ems))
        duplicated = {n for n in set(names) if names.count(n) > 1}
        assert duplicated <= {"ems_provision_capability-fresco-resource-row.png"}, (
            f"distinct failures must use distinct screenshots; reused: {sorted(duplicated)}")
        assert len(set(names)) >= 4


class TestCallerSurvivesExitError:
    """Util.exit_error() raises SystemExit, which `except Exception` does NOT catch.

    The caller is `page_cli._run_cli_ems_provision` since PCP-24380 — it was
    `_run_gui_ems_provision`, which drove the wizard in a browser. Nothing on the CLI
    path calls Util.exit_error() any more, so the trap now guards against RE-introducing
    a sys.exit() rather than against one that is there today. Kept, and kept pointed at
    the current function name, because the consequence has not changed: a SystemExit
    escaping here kills the DP setup THREAD, leaves `errors` empty, and the run exits 0
    with no EMS.
    """

    def test_ems_caller_traps_systemexit(self):
        from page_cli import _run_cli_ems_provision
        src = inspect.getsource(_run_cli_ems_provision)
        assert "except (Exception, SystemExit)" in src, (
            "neither orchestrator.on_ems_needed() nor _run_dp_setup's `except Exception` "
            "catches SystemExit, so a sys.exit(1) silently kills the DP thread"
        )
        assert "except BaseException" not in src, "KeyboardInterrupt must still abort the run"

    def test_ems_caller_reraises_so_the_run_fails(self):
        # Trapping SystemExit must not DOWNGRADE the failure: _run_dp_setup collects normal
        # exceptions into `errors`, and only a non-empty `errors` makes the workflow exit 1.
        # Logging and returning would report a green run for a data plane with no EMS.
        from page_cli import _run_cli_ems_provision
        src = inspect.getsource(_run_cli_ems_provision)
        handler = src[src.index("except (Exception, SystemExit)"):]
        assert re.search(r"\braise\b", handler), (
            "the handler must re-raise a normal exception, or the failure never reaches `errors`"
        )

    def test_dp_setup_turns_exceptions_into_a_nonzero_exit(self):
        # The other half of the contract above — pinned so a refactor of the thread target
        # cannot quietly break the path that makes an EMS failure visible.
        from page_cli import _run_dp_setup
        src = inspect.getsource(_run_dp_setup)
        assert "errors.append(e)" in src
