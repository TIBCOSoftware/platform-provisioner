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
# Regression tests for the Data Plane Activation step (dp_config_activation_file and
# dp_config_activation_url) and the shared modal cleanup they run on the way out.
#
# The defect: the step clicked 'Upload' and then decided whether the 'Add New License
# File' dialog had rendered with a single `page.locator('.license-file-drop-zone')
# .is_visible()`. Under install load the dialog was still mounting when that read
# happened, so the entire upload block was skipped - no file was ever attached, the
# failure surfaced as a bare ColorLogger.warning with no screenshot, and the empty
# dialog stayed on screen. A surviving '.pl-modal--open' overlay swallows pointer
# events, so the NEXT navigation died with an "intercepts pointer events" timeout far
# away from the step that actually went wrong. The dp-level branch had the same shape
# with a bare wait_for(state="visible") on the confirmation dialog: on a slow render it
# threw straight out of the method, again leaving the dialog mounted.
#
# The behaviour pinned here:
#   1. the dialog probes are polled through Util.check_dom_visibility with a budget that
#      is at least as generous as the wait_for() default they replaced - cutting it is
#      what makes the slow-render race MORE likely, not less,
#   2. both activation methods run their body in try/finally and close whatever dialog
#      THEY opened, through PageObjectGlobal.close_open_modal(); a dialog this step
#      never opened belongs to the caller and is left alone,
#   3. the cleanup tail never raises - an exception from it would REPLACE the real
#      failure - never warns on a green run, is not fooled by an unrelated exception
#      being handled up the stack, and writes its own screenshot file so the diagnostic
#      screenshot taken moments earlier survives,
#   4. a missed control or dialog does not skip the shared final "is it linked" check:
#      an already-linked license still has to be recorded, or the DP-level link is
#      silently skipped for the whole run,
#   5. a failure is reported with a screenshot and names the sub-cause: a rejected file
#      ('.file-error-message') reads differently from a license that has expired, and
#      scraped dialog text is capped and escaped before it reaches the log,
#   6. a dialog-opening click is marked as having opened one BEFORE it fires, and carries
#      an explicit timeout: a leftover overlay swallows pointer events, so the click
#      itself is what throws, and a cleanup that believed nothing was opened would leave
#      that same overlay for the next navigation - the reported failure all over again,
#   6a. and that timeout is reported, never raised: activation is best-effort by design
#      (o11y_config_activation is called unwrapped), so a blocked opening click that
#      escapes ends the whole create-dp task and blames this step for an overlay an
#      earlier one left behind. Only the block that needed the dialog is skipped, the
#      reason names the control, and the shared check and the cleanup still run,
#   7. the confirmation dialog's 'Link' is the real action, not cleanup, so it keeps the
#      full 30s budget, and a timeout on it is reported and fallen through rather than
#      raised out of the step,
#   8. the 'Upload' option and the drop zone are INDEPENDENT probes: a UI that renders the
#      dialog without the option still has to get the file attached,
#   9. the cleanup re-reads the success condition before it clicks anything: a submit can
#      still be in flight, and 'Cancel' on that dialog would revert the link that had just
#      succeeded.
#
# Browser-free: the page is a MagicMock whose locator() is routed by selector string,
# following the sibling page_object suites.

from unittest.mock import MagicMock

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from page_object.po_dp_config import (
    ACTIVATION_DIALOG_CLICK_TIMEOUT,
    ACTIVATION_DIALOG_SUBMIT_TIMEOUT,
    PageObjectDataPlaneConfiguration,
)
from page_object.po_global import (
    MODAL_CLOSE_CALLER_CLICK_TIMEOUT,
    MODAL_CLOSE_CLICK_TIMEOUT,
    MODAL_CLOSE_MAX_SECONDS,
)
from utils.color_logger import ColorLogger
from utils.env import ENV
from utils.util import Util

DP_NAME = "k8s-auto-dp1"
GLOBAL_DP_NAME = "Global"
ACTIVATION_FILE = "/tmp/upload/tibco-platform-license.zip"
ACTIVATION_URL = "https://activation.example.com"

LINKED_LABEL = "span"                                        # 'Currently linked to the ...' / 'View License'
UPLOAD_OPTION = "#add-global-license-file"
DROP_ZONE = ".license-file-drop-zone"
FILE_INPUT = 'input[type="file"]'
ADD_BTN_ENABLED = "#add-activation-url-btn:not([disabled])"
ADD_BTN = "#add-activation-url-btn"
USE_GLOBAL_FILE = "#use-global-license-file-on-dp"
USE_GLOBAL_URL = "#use-global-activation-on-dp"
ADD_GLOBAL_URL = "#add-global-activation-server"
URL_DIALOG_HEADING = "activation-url-modal .pl-modal__heading"
URL_TEXT_INPUT = "activation-url-modal #activation-url-text-input"
URL_ADD_BTN = "activation-url-modal #add-activation-url-btn"
ACTIVATION_URL_LABEL = ".activation-server-url"
CONFIRM_HEADING = "confirmation-modal .pl-modal__heading"
CONFIRM_BUTTON = "#confirm-button"
# is_modal_open() and the failure-details scrape read the SAME selector.
MODAL = ".pl-modal--open"
FILE_ERROR = ".pl-modal--open .file-error-message"
CLOSE_FOOTER_BTN = ".pl-modal--open #close-activation-url-modal-btn"
CLOSE_HEADER_X = ".pl-modal--open #close-activation-url-modal"
CANCEL_CONFIRM = ".pl-modal--open #cancel-confirm-button"
# The one caller-supplied selector in the codebase, passed by _close_modal().
INGRESS_CANCEL = "#cancel-ingress-configuration, #cancel-route-resource-configuration"

FAILURE_SHOT = "dp_config_activation_file.png"
CLEANUP_SHOT = "dp_config_activation_file-cleanup.png"
URL_FAILURE_SHOT = "dp_config_activation_url.png"
URL_CLEANUP_SHOT = "dp_config_activation_url-cleanup.png"

BLOCKED_BY_OVERLAY = 'Timeout 5000ms exceeded. <div class="pl-modal--open"> intercepts pointer events'


def _new(cls):
    """Build a page object without running __init__ (no browser needed)."""
    obj = object.__new__(cls)
    obj.page = MagicMock()
    return obj


def _child(selector, visible=False, count=0, text=""):
    """One locator result, remembering the selector it was created for.

    count() and is_visible() must answer with a real int / real bool, including for
    selectors a test never named: is_modal_open() evaluates `count() > 0` and then reads
    `nth(i).is_visible()`, and a plain MagicMock returns a MagicMock from count(), which
    makes that comparison raise TypeError - the cleanup path this module is about would
    blow up in the harness instead of returning the boolean the production code reads.
    nth() answers like first(), so a node's visibility is wired in one place.

    element_handle() answers with a node whose is_visible() and click() ARE the ones
    wired on the locator: the close walk resolves a match to a single handle so the node
    it checked is the node it clicks, and a test still wires and asserts one control.
    """
    child = MagicMock()
    child.selector = selector
    child.count.return_value = count
    child.is_visible.return_value = visible
    child.first.is_visible.return_value = visible
    child.last.is_visible.return_value = visible
    child.nth.side_effect = lambda index: child.first
    child.inner_text.return_value = text
    child.first.inner_text.return_value = text
    child.last.inner_text.return_value = text
    child.get_attribute.return_value = ""
    handle = MagicMock()
    handle.is_visible.side_effect = lambda: child.first.is_visible()
    handle.click = child.first.click
    child.first.element_handle.return_value = handle
    child.last.element_handle.return_value = handle
    return child


def _wire_locators(po, overrides=None):
    """Route po.page.locator(selector, ...) to one child mock per selector string, so
    each control can be answered independently and the assertions can name the SELECTOR
    the code used. Unnamed selectors get a child with the safe defaults above."""
    registry = {selector: _child(selector, **spec) for selector, spec in (overrides or {}).items()}

    def _locator(selector, *a, **k):
        if selector not in registry:
            registry[selector] = _child(selector)
        return registry[selector]

    po.page.locator.side_effect = _locator
    return registry


def _wire_open_modal(registry, close_selector=CLOSE_FOOTER_BTN):
    """Leave a Pulse modal mounted on the harness page, closable through
    'close_selector' only. Clicking that control unmounts the modal, so
    close_open_modal() walks its candidate list and returns the way it does against a
    real dialog."""
    state = {"open": True, "closed_by": []}

    # The open probe and the diagnostics text scrape read the same '.pl-modal--open',
    # so reuse whatever the test already wired for it (dialog body text) and take over
    # only the open/closed answers - otherwise one wiring silently erases the other.
    modal = registry.get(MODAL) or _child(MODAL)
    modal.count.side_effect = lambda: 1 if state["open"] else 0
    modal.is_visible.side_effect = lambda: state["open"]
    modal.first.is_visible.side_effect = lambda: state["open"]
    modal.last.is_visible.side_effect = lambda: state["open"]
    registry[MODAL] = modal

    control = _child(close_selector, visible=True, count=1)

    def _click(*a, **k):
        state["closed_by"].append(close_selector)
        state["open"] = False

    control.first.click.side_effect = _click
    registry[close_selector] = control
    return state


class _Probe(str):
    """The selector a check_dom_visibility call was handed, remembering the budget it
    was given. It IS the selector string, so the call-order assertions read unchanged,
    and a test can additionally pin the (interval, max_wait) pair - the wait budget is
    the whole point of this fix and was silently cut once already."""
    def __new__(cls, selector, interval, max_wait):
        probe = super().__new__(cls, selector)
        probe.interval = interval
        probe.max_wait = max_wait
        return probe


def _wire_check_dom_visibility(monkeypatch, answers):
    """Answer Util.check_dom_visibility in call order and record which selector each
    answer was handed to, so a test can prove WHICH probe was polled rather than only
    how many probes happened.

    A run that reaches the close walk records ONE probe more than the method body makes:
    the cleanup re-reads the success condition before it touches anything. Answers that
    run out read as False, which is the 'still not linked' case."""
    remaining = list(answers)
    probes = []

    def _fake(page, dom_selector, interval=10, max_wait=180, is_refresh=False):
        probes.append(_Probe(getattr(dom_selector, "selector", "<unwired>"), interval, max_wait))
        return remaining.pop(0) if remaining else False

    monkeypatch.setattr(Util, "check_dom_visibility", staticmethod(_fake))
    return probes


def _wire_warnings(monkeypatch):
    """Keep the two reporting channels apart: Util.warning_screenshot (warning + a
    screenshot of the still-open dialog) versus a bare ColorLogger.warning, which is
    what the old code did and leaves no evidence behind. Screenshot FILE names are
    recorded too: a cleanup capture that reuses the failure file name overwrites the
    evidence the failure screenshot exists to produce."""
    warnings = {"screenshot": [], "log": [], "files": []}

    def _screenshot(message, page=None, filename=""):
        warnings["screenshot"].append(message)
        warnings["files"].append(filename)

    monkeypatch.setattr(Util, "warning_screenshot", staticmethod(_screenshot))
    monkeypatch.setattr(ColorLogger, "warning", staticmethod(
        lambda message: warnings["log"].append(message)))
    return warnings


def _wire_report(monkeypatch):
    """Record ReportYaml writes. A failure path must write nothing: the activation step
    skips on any stored value, so a recorded failure disables activation for good."""
    written = []
    monkeypatch.setattr("page_object.po_dp_config.ReportYaml.set_dataplane_info",
                        lambda *a, **k: written.append(a))
    return written


def _located(po):
    """Every selector string page.locator() was asked for, in call order."""
    return [c.args[0] for c in po.page.locator.call_args_list if c.args]


def _global_upload_po(monkeypatch, overrides=None):
    """Global-level upload harness: the 'In-Product Activation' radio is already
    selected and the 'Upload' option is on screen, which is where the interesting part
    of the step starts."""
    po = _new(PageObjectDataPlaneConfiguration)
    po.select_in_product_activation = MagicMock(return_value=True)
    wiring = {UPLOAD_OPTION: {"visible": True, "count": 1}}
    wiring.update(overrides or {})
    return po, _wire_locators(po, wiring)


class TestDropZoneRaceLeavesNoModalBehind:
    def test_drop_zone_never_renders_skips_upload_and_closes_the_dialog(self, monkeypatch):
        """The reported race: the 'Add New License File' dialog has not rendered by the
        time the drop zone is probed. Nothing may be attached to a dialog that is not
        there, the failure must be screenshotted, and the dialog must not survive into
        the next navigation."""
        po, registry = _global_upload_po(monkeypatch)
        modal = _wire_open_modal(registry)
        warnings = _wire_warnings(monkeypatch)
        written = _wire_report(monkeypatch)
        probes = _wire_check_dom_visibility(monkeypatch, [False, True, False, False])

        po.dp_config_activation_file(GLOBAL_DP_NAME, False, ACTIVATION_FILE)

        # already-linked probe -> 'Upload' option -> drop zone, then the shared final check
        # and the cleanup's re-read of that same check
        assert probes == [LINKED_LABEL, UPLOAD_OPTION, DROP_ZONE, LINKED_LABEL, LINKED_LABEL]
        assert FILE_INPUT not in _located(po)
        assert ADD_BTN not in _located(po)

        # reported with a screenshot of the offending dialog, not as a bare log line
        upload_failure = [m for m in warnings["screenshot"] if "'Add New License File' dialog never appeared" in m]
        assert len(upload_failure) == 1
        assert ACTIVATION_FILE in upload_failure[0]
        assert not any("never appeared" in m for m in warnings["log"])

        # and the leftover dialog is closed before the step returns
        assert modal["closed_by"] == [CLOSE_FOOTER_BTN]
        assert modal["open"] is False
        assert any("still open after a failed attempt" in m for m in warnings["screenshot"])
        assert written == []

        # the cleanup capture must not overwrite the diagnostic one
        assert warnings["files"] == [FAILURE_SHOT, CLEANUP_SHOT]

    def test_drop_zone_is_polled_never_read_once(self, monkeypatch):
        """A single is_visible() read is exactly what lost the race, so the drop zone
        must reach Util.check_dom_visibility and must never be asked directly."""
        po, registry = _global_upload_po(monkeypatch, {DROP_ZONE: {"visible": True, "count": 1}})
        _wire_warnings(monkeypatch)
        _wire_report(monkeypatch)
        probes = _wire_check_dom_visibility(monkeypatch, [False, True, True, True, True])

        po.dp_config_activation_file(GLOBAL_DP_NAME, False, ACTIVATION_FILE)

        assert DROP_ZONE in probes
        assert registry[DROP_ZONE].is_visible.call_count == 0
        assert registry[DROP_ZONE].wait_for.call_count == 0

    def test_a_missing_upload_option_is_not_reported_as_a_missing_dialog(self, monkeypatch):
        """When the 'Upload' option itself never renders, nothing is ever clicked and no
        dialog is ever asked for. Reporting that as "the dialog never appeared" names a
        step that never ran, so the two have to read differently."""
        po, registry = _global_upload_po(monkeypatch, {UPLOAD_OPTION: {}})
        warnings = _wire_warnings(monkeypatch)
        written = _wire_report(monkeypatch)
        probes = _wire_check_dom_visibility(monkeypatch, [False, False, False, False])

        po.dp_config_activation_file(GLOBAL_DP_NAME, False, ACTIVATION_FILE)

        # the drop zone is still probed - it does not depend on the option - but there is
        # nothing to attach to, so no file is selected
        assert probes == [LINKED_LABEL, UPLOAD_OPTION, DROP_ZONE, LINKED_LABEL]
        assert FILE_INPUT not in _located(po)
        message = next(m for m in warnings["screenshot"] if "Add Activation file" in m)
        assert UPLOAD_OPTION in message
        assert "'Add New License File' dialog never appeared" not in message
        assert written == []

    def test_a_missing_upload_option_does_not_stop_the_file_being_attached(self, monkeypatch):
        """The two probes answer different questions and must stay independent. Chaining
        them means a control plane that renders the drop zone WITHOUT the 'Upload' option
        uploads nothing at all: the option is how the dialog is normally asked for, never
        a precondition for using one that is already on screen."""
        po, registry = _global_upload_po(monkeypatch, {
            UPLOAD_OPTION: {},
            DROP_ZONE: {"visible": True, "count": 1},
        })
        warnings = _wire_warnings(monkeypatch)
        written = _wire_report(monkeypatch)
        probes = _wire_check_dom_visibility(monkeypatch, [False, False, True, True, True])

        po.dp_config_activation_file(GLOBAL_DP_NAME, False, ACTIVATION_FILE)

        assert probes == [LINKED_LABEL, UPLOAD_OPTION, DROP_ZONE, ADD_BTN_ENABLED, LINKED_LABEL]
        assert registry[UPLOAD_OPTION].click.call_count == 0
        registry[FILE_INPUT].set_input_files.assert_called_once_with(ACTIVATION_FILE)
        registry[ADD_BTN].click.assert_called_once()
        assert written == [(GLOBAL_DP_NAME, "activation", "file")]
        assert warnings["screenshot"] == []

    def test_an_already_linked_license_is_still_recorded_when_the_dialog_was_missed(self, monkeypatch):
        """The entry probe can lose the same race the drop zone does. Falling out of the
        step on a missed dialog would skip the shared final check, and because
        o11y_config_activation early-returns on any stored value, an unrecorded Global
        license silently skips the DP-level link for the rest of the run."""
        po, registry = _global_upload_po(monkeypatch)
        modal = _wire_open_modal(registry)
        warnings = _wire_warnings(monkeypatch)
        written = _wire_report(monkeypatch)
        probes = _wire_check_dom_visibility(monkeypatch, [False, True, False, True])

        po.dp_config_activation_file(GLOBAL_DP_NAME, False, ACTIVATION_FILE)

        # four probes, not five: the cleanup re-reads the success condition only when the
        # step has NOT already seen it, and this run has - re-reading there would leave a
        # green run's dialog mounted on the strength of a locator that ignores overlays
        assert probes == [LINKED_LABEL, UPLOAD_OPTION, DROP_ZONE, LINKED_LABEL]
        assert written == [(GLOBAL_DP_NAME, "activation", "file")]
        # the license is linked, so the missed dialog is not worth a warning
        assert warnings["screenshot"] == []
        assert warnings["log"] == []
        assert modal["closed_by"] == [CLOSE_FOOTER_BTN]


class TestABlockedOpeningClickIsReportedAndCleanedUpAfter:
    def test_a_blocked_upload_click_is_reported_and_leaves_no_overlay_behind(self, monkeypatch):
        """The reported failure again, on the path polling the dialog probes does not
        cover: a modal left by an earlier step swallows pointer events, the button
        underneath it still reads visible so the probe passes, and it is the CLICK that
        fails.

        Letting that timeout out of the method ends the whole create-dp task over a step
        that is best-effort by design, and blames it for an overlay it was only the
        second victim of. It is reported by name and fallen through instead - and the
        dialog is still marked as opened BEFORE the click, so the cleanup clears that
        overlay rather than leaving it for the next navigation."""
        po, registry = _global_upload_po(monkeypatch)
        registry[UPLOAD_OPTION].click.side_effect = PlaywrightTimeoutError(BLOCKED_BY_OVERLAY)
        modal = _wire_open_modal(registry)
        warnings = _wire_warnings(monkeypatch)
        written = _wire_report(monkeypatch)
        probes = _wire_check_dom_visibility(monkeypatch, [False, True, False, False])

        po.dp_config_activation_file(GLOBAL_DP_NAME, False, ACTIVATION_FILE)

        # bounded, so the step does not spend Playwright's 30s default finding out what
        # the overlay already told it
        registry[UPLOAD_OPTION].click.assert_called_once_with(timeout=ACTIVATION_DIALOG_CLICK_TIMEOUT)
        # only the block that needed the click is skipped: the drop zone is an independent
        # probe, and the shared final check and the cleanup still run
        assert probes == [LINKED_LABEL, UPLOAD_OPTION, DROP_ZONE, LINKED_LABEL, LINKED_LABEL]
        assert FILE_INPUT not in _located(po)

        message = next(m for m in warnings["screenshot"] if "Add Activation file" in m)
        assert "The 'Upload' option '#add-global-license-file' could not be clicked." in message
        # one blocked click, one blamed step: the dialog that click never got to ask for
        # may not be reported as missing on top of it
        assert "'Add New License File' dialog never appeared" not in message
        assert any("Could not click 'Upload' option" in m for m in warnings["log"])

        assert modal["closed_by"] == [CLOSE_FOOTER_BTN]
        assert modal["open"] is False
        # the cleanup capture must not overwrite the diagnostic one
        assert warnings["files"] == [FAILURE_SHOT, CLEANUP_SHOT]
        assert written == []

    def test_a_blocked_upload_click_still_records_an_already_linked_license(self, monkeypatch):
        """Falling through is not only about the cleanup. The license may already be
        linked - the overlay that blocked the click is evidence the run is a re-entry -
        and because o11y_config_activation early-returns on any stored value, dropping
        the shared check here silently skips the DP-level link for the rest of the run."""
        po, registry = _global_upload_po(monkeypatch)
        registry[UPLOAD_OPTION].click.side_effect = PlaywrightTimeoutError(BLOCKED_BY_OVERLAY)
        modal = _wire_open_modal(registry)
        warnings = _wire_warnings(monkeypatch)
        written = _wire_report(monkeypatch)
        probes = _wire_check_dom_visibility(monkeypatch, [False, True, False, True])

        po.dp_config_activation_file(GLOBAL_DP_NAME, False, ACTIVATION_FILE)

        assert probes == [LINKED_LABEL, UPLOAD_OPTION, DROP_ZONE, LINKED_LABEL]
        assert written == [(GLOBAL_DP_NAME, "activation", "file")]
        # the blocked click is still logged, but a linked license is not a failure
        assert any("Could not click 'Upload' option" in m for m in warnings["log"])
        assert warnings["screenshot"] == []
        assert modal["closed_by"] == [CLOSE_FOOTER_BTN]

    def test_a_blocked_use_global_file_click_skips_only_the_confirmation_step(self, monkeypatch):
        """The DP-level twin of the upload path. The confirmation dialog belongs to a
        click that never landed, so polling for it would spend 30s waiting for a dialog
        nothing asked for and then blame it for not appearing."""
        po = _new(PageObjectDataPlaneConfiguration)
        po.select_in_product_activation = MagicMock(return_value=True)
        registry = _wire_locators(po, {USE_GLOBAL_FILE: {"visible": True, "count": 1}})
        registry[USE_GLOBAL_FILE].click.side_effect = PlaywrightTimeoutError(BLOCKED_BY_OVERLAY)
        modal = _wire_open_modal(registry)
        warnings = _wire_warnings(monkeypatch)
        written = _wire_report(monkeypatch)
        probes = _wire_check_dom_visibility(monkeypatch, [False, True, False, False])

        po.dp_config_activation_file(DP_NAME, True, "")

        assert probes == [LINKED_LABEL, USE_GLOBAL_FILE, LINKED_LABEL, LINKED_LABEL]
        assert CONFIRM_HEADING not in probes
        assert CONFIRM_BUTTON not in _located(po)
        registry[USE_GLOBAL_FILE].click.assert_called_once_with(timeout=ACTIVATION_DIALOG_CLICK_TIMEOUT)

        message = next(m for m in warnings["screenshot"] if "Link to the Global license file failed" in m)
        assert "'Use Global License File' option could not be clicked" in message
        assert "confirmation dialog never appeared" not in message
        assert modal["closed_by"] == [CLOSE_FOOTER_BTN]
        assert written == []

    def test_an_exception_before_anything_was_opened_still_clears_the_page(self, monkeypatch):
        """A call that dies part way through cannot know who owns the overlay it can see:
        the click that opened a dialog is exactly the kind of call that throws. Trusting a
        flag that was never set is how the reported failure reached the NEXT navigation,
        so an exception cleans up whatever is on screen."""
        po, registry = _global_upload_po(monkeypatch)
        modal = _wire_open_modal(registry)
        warnings = _wire_warnings(monkeypatch)
        written = _wire_report(monkeypatch)

        # it blows up on the 'Upload' option probe, before anything has been clicked; the
        # cleanup's own re-check still has to work, or this would be proving the
        # except-swallow in the cleanup rather than the cleanup itself
        def _fake(page, dom_selector, interval=10, max_wait=180, is_refresh=False):
            if getattr(dom_selector, "selector", "") == UPLOAD_OPTION:
                raise RuntimeError("Target page, context or browser has been closed")
            return False

        monkeypatch.setattr(Util, "check_dom_visibility", staticmethod(_fake))

        with pytest.raises(RuntimeError):
            po.dp_config_activation_file(GLOBAL_DP_NAME, False, ACTIVATION_FILE)

        assert modal["closed_by"] == [CLOSE_FOOTER_BTN]
        assert modal["open"] is False
        assert warnings["files"] == [CLEANUP_SHOT]
        assert written == []

    def test_a_blocked_use_global_url_click_is_reported_and_leaves_no_overlay_behind(self, monkeypatch):
        """The same guarantee on the activation-URL twin: the dialog-opening controls of
        both methods are reported and cleaned up after, not only the one the bug was
        first seen on."""
        po = _new(PageObjectDataPlaneConfiguration)
        po.select_tibco_activation_service = MagicMock(return_value=True)
        registry = _wire_locators(po, {USE_GLOBAL_URL: {"visible": True, "count": 1}})
        registry[USE_GLOBAL_URL].click.side_effect = PlaywrightTimeoutError(BLOCKED_BY_OVERLAY)
        monkeypatch.setattr(type(ENV), "TP_ACTIVATION_URL", "")
        modal = _wire_open_modal(registry)
        warnings = _wire_warnings(monkeypatch)
        written = _wire_report(monkeypatch)
        probes = _wire_check_dom_visibility(monkeypatch, [True])

        po.dp_config_activation_url(DP_NAME, True)

        registry[USE_GLOBAL_URL].click.assert_called_once_with(timeout=ACTIVATION_DIALOG_CLICK_TIMEOUT)
        assert probes == [USE_GLOBAL_URL, ACTIVATION_URL_LABEL, ACTIVATION_URL_LABEL]
        assert CONFIRM_HEADING not in probes

        message = next(m for m in warnings["screenshot"] if "Link to the Global Activation URL failed" in m)
        assert "'Use Global Activation URL' button could not be clicked" in message
        assert "confirmation dialog never appeared" not in message
        assert any("Could not click 'Use Global Activation URL' button" in m for m in warnings["log"])

        assert modal["closed_by"] == [CLOSE_FOOTER_BTN]
        assert modal["open"] is False
        assert warnings["files"] == [URL_FAILURE_SHOT, URL_CLEANUP_SHOT]
        assert written == []

    def test_a_blocked_add_global_url_click_skips_the_dialog_it_never_opened(self, monkeypatch):
        """Global level, same shape: nothing may be typed into, or submitted in, a dialog
        whose opening click never landed."""
        po = _new(PageObjectDataPlaneConfiguration)
        po.select_tibco_activation_service = MagicMock(return_value=True)
        registry = _wire_locators(po, {ADD_GLOBAL_URL: {"visible": True, "count": 1}})
        registry[ADD_GLOBAL_URL].click.side_effect = PlaywrightTimeoutError(BLOCKED_BY_OVERLAY)
        monkeypatch.setattr(type(ENV), "TP_ACTIVATION_URL", ACTIVATION_URL)
        modal = _wire_open_modal(registry)
        warnings = _wire_warnings(monkeypatch)
        written = _wire_report(monkeypatch)
        probes = _wire_check_dom_visibility(monkeypatch, [False, True, False, False])

        po.dp_config_activation_url(GLOBAL_DP_NAME, False)

        assert probes == [ACTIVATION_URL_LABEL, ADD_GLOBAL_URL, ACTIVATION_URL_LABEL, ACTIVATION_URL_LABEL]
        assert URL_DIALOG_HEADING not in probes
        assert po.page.fill.call_count == 0
        assert URL_ADD_BTN not in _located(po)

        message = next(m for m in warnings["screenshot"] if "Add Activation URL" in m)
        assert "'Add Global Activation URL' button could not be clicked" in message
        assert modal["closed_by"] == [CLOSE_FOOTER_BTN]
        assert written == []

    def test_a_url_field_that_cannot_be_filled_is_not_submitted_empty(self, monkeypatch):
        """The one field this step types into fails the same way a blocked click does -
        covered, or still disabled. Submitting the dialog anyway registers an EMPTY
        activation URL on the control plane, so the 'Add' click goes with it, and the
        run still has to survive to report it."""
        po = _new(PageObjectDataPlaneConfiguration)
        po.select_tibco_activation_service = MagicMock(return_value=True)
        registry = _wire_locators(po, {ADD_GLOBAL_URL: {"visible": True, "count": 1}})
        po.page.fill.side_effect = PlaywrightTimeoutError("Timeout 5000ms exceeded")
        monkeypatch.setattr(type(ENV), "TP_ACTIVATION_URL", ACTIVATION_URL)
        modal = _wire_open_modal(registry)
        warnings = _wire_warnings(monkeypatch)
        written = _wire_report(monkeypatch)
        probes = _wire_check_dom_visibility(monkeypatch, [False, True, True, False, False])

        po.dp_config_activation_url(GLOBAL_DP_NAME, False)

        assert probes == [ACTIVATION_URL_LABEL, ADD_GLOBAL_URL, URL_DIALOG_HEADING,
                          ACTIVATION_URL_LABEL, ACTIVATION_URL_LABEL]
        po.page.fill.assert_called_once_with(URL_TEXT_INPUT, ACTIVATION_URL,
                                             timeout=ACTIVATION_DIALOG_CLICK_TIMEOUT)
        assert URL_ADD_BTN not in _located(po)

        message = next(m for m in warnings["screenshot"] if "Add Activation URL" in m)
        assert "Activation URL field in the 'Add New Activation URL' dialog could not be filled" in message
        assert any("Could not fill Activation URL" in m for m in warnings["log"])
        assert modal["closed_by"] == [CLOSE_FOOTER_BTN]
        assert written == []


class TestGreenRunStaysQuiet:
    def test_successful_upload_produces_no_warning(self, monkeypatch):
        """Dialog rendered, file attached, 'Add' enabled, license linked: the step must
        record the result and say nothing else."""
        po, registry = _global_upload_po(monkeypatch, {DROP_ZONE: {"visible": True, "count": 1}})
        warnings = _wire_warnings(monkeypatch)
        written = _wire_report(monkeypatch)
        probes = _wire_check_dom_visibility(monkeypatch, [False, True, True, True, True])

        po.dp_config_activation_file(GLOBAL_DP_NAME, False, ACTIVATION_FILE)

        assert probes == [LINKED_LABEL, UPLOAD_OPTION, DROP_ZONE, ADD_BTN_ENABLED, LINKED_LABEL]
        registry[FILE_INPUT].set_input_files.assert_called_once_with(ACTIVATION_FILE)
        registry[ADD_BTN].click.assert_called_once()
        assert written == [(GLOBAL_DP_NAME, "activation", "file")]
        assert warnings["screenshot"] == []
        assert warnings["log"] == []

    def test_dialog_still_unmounting_on_success_is_closed_silently(self, monkeypatch):
        """A green run can reach the cleanup while the dialog is still animating out.
        It has to be closed, but quietly: a warning here fires on every healthy run and
        poisons the very log signal this step is judged on."""
        po, registry = _global_upload_po(monkeypatch, {DROP_ZONE: {"visible": True, "count": 1}})
        modal = _wire_open_modal(registry)
        warnings = _wire_warnings(monkeypatch)
        written = _wire_report(monkeypatch)
        _wire_check_dom_visibility(monkeypatch, [False, True, True, True, True])

        po.dp_config_activation_file(GLOBAL_DP_NAME, False, ACTIVATION_FILE)

        assert written == [(GLOBAL_DP_NAME, "activation", "file")]
        assert modal["closed_by"] == [CLOSE_FOOTER_BTN]
        assert warnings["screenshot"] == []
        assert warnings["log"] == []

    def test_an_unrelated_exception_up_the_stack_does_not_fake_a_failure(self, monkeypatch):
        """The cleanup must judge only what THIS call did. sys.exc_info() reports any
        exception being handled anywhere up the stack, so a caller that is already
        inside an except block would turn this green run into a warning and a
        screenshot."""
        po, registry = _global_upload_po(monkeypatch, {DROP_ZONE: {"visible": True, "count": 1}})
        modal = _wire_open_modal(registry)
        warnings = _wire_warnings(monkeypatch)
        written = _wire_report(monkeypatch)
        _wire_check_dom_visibility(monkeypatch, [False, True, True, True, True])

        try:
            raise RuntimeError("an unrelated failure the caller is already handling")
        except RuntimeError:
            po.dp_config_activation_file(GLOBAL_DP_NAME, False, ACTIVATION_FILE)

        assert written == [(GLOBAL_DP_NAME, "activation", "file")]
        assert modal["closed_by"] == [CLOSE_FOOTER_BTN]
        assert warnings["screenshot"] == []
        assert warnings["log"] == []

    def test_a_step_that_opened_no_dialog_leaves_the_page_alone(self, monkeypatch):
        """The skip paths never open anything, so a modal found on the page belongs to
        the CALLER. Closing it, or blaming this step for it, reports an unrelated
        leftover as this step's failure."""
        po = _new(PageObjectDataPlaneConfiguration)
        po.select_in_product_activation = MagicMock(return_value=False)
        registry = _wire_locators(po)
        modal = _wire_open_modal(registry)
        warnings = _wire_warnings(monkeypatch)
        written = _wire_report(monkeypatch)
        _wire_check_dom_visibility(monkeypatch, [False])

        po.dp_config_activation_file(DP_NAME, True, "")

        assert warnings["screenshot"] == []
        assert modal["closed_by"] == []
        assert modal["open"] is True
        assert written == []
        assert warnings["log"] == ["In-Product Activation option is disabled, skip config Activation."]


class TestCleanupNeverMasksTheRealFailure:
    def test_a_failing_close_does_not_replace_the_original_exception(self, monkeypatch):
        """The cleanup runs from a finally block. If it raises, its own error becomes
        the one that propagates and demotes the real cause to __context__ - the exact
        misdirection this cleanup exists to prevent."""
        po, registry = _global_upload_po(monkeypatch, {
            DROP_ZONE: {"visible": True, "count": 1},
            FILE_INPUT: {},
        })
        registry[FILE_INPUT].set_input_files.side_effect = RuntimeError(
            "Timeout 30000ms exceeded setting input files")
        _wire_open_modal(registry)
        po.close_open_modal = MagicMock(side_effect=RuntimeError("close control click was intercepted"))
        warnings = _wire_warnings(monkeypatch)
        _wire_report(monkeypatch)
        _wire_check_dom_visibility(monkeypatch, [False, True, True])

        with pytest.raises(RuntimeError) as excinfo:
            po.dp_config_activation_file(GLOBAL_DP_NAME, False, ACTIVATION_FILE)

        assert "setting input files" in str(excinfo.value)
        assert "close control" not in str(excinfo.value)
        # the finally really ran and really failed - the assertion above is not vacuous
        po.close_open_modal.assert_called_once()
        assert any("Failed to close the activation dialog" in m for m in warnings["log"])

    def test_cleanup_warns_when_an_exception_is_in_flight_after_a_successful_upload(self, monkeypatch):
        """A recorded success is not enough on its own: when something threw after the
        upload was confirmed, the dialog left behind belongs to a broken run and must be
        screenshotted rather than closed in silence."""
        po, registry = _global_upload_po(monkeypatch, {DROP_ZONE: {"visible": True, "count": 1}})
        modal = _wire_open_modal(registry)
        warnings = _wire_warnings(monkeypatch)
        monkeypatch.setattr("page_object.po_dp_config.ReportYaml.set_dataplane_info",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("report write failed")))
        _wire_check_dom_visibility(monkeypatch, [False, True, True, True, True])

        with pytest.raises(RuntimeError) as excinfo:
            po.dp_config_activation_file(GLOBAL_DP_NAME, False, ACTIVATION_FILE)

        assert "report write failed" in str(excinfo.value)
        assert any("still open after a failed attempt" in m for m in warnings["screenshot"])
        assert warnings["files"] == [CLEANUP_SHOT]
        assert modal["closed_by"] == [CLOSE_FOOTER_BTN]


class TestCleanupNeverUndoesASuccess:
    def test_a_link_that_lands_while_the_cleanup_settles_is_not_cancelled(self, monkeypatch):
        """The submit can still be in flight when the finally runs: the shared check saw
        nothing yet, but the link lands a moment later. The close walk would then click
        'Cancel' on the confirmation dialog it belongs to and revert a link that had
        succeeded, so success is read once more and a late one is left completely
        alone - nothing closed, nothing warned about."""
        po = _new(PageObjectDataPlaneConfiguration)
        po.select_in_product_activation = MagicMock(return_value=True)
        registry = _wire_locators(po, {USE_GLOBAL_FILE: {"visible": True, "count": 1}})
        modal = _wire_open_modal(registry, CANCEL_CONFIRM)
        warnings = _wire_warnings(monkeypatch)
        written = _wire_report(monkeypatch)
        # entry / button / confirmation dialog / shared check (not linked yet) / cleanup
        # re-check (the submit has landed by now)
        probes = _wire_check_dom_visibility(monkeypatch, [False, True, True, False, True])

        po.dp_config_activation_file(DP_NAME, True, "")

        assert probes == [LINKED_LABEL, USE_GLOBAL_FILE, CONFIRM_HEADING, LINKED_LABEL, LINKED_LABEL]
        assert modal["closed_by"] == []
        assert modal["open"] is True
        assert registry[CANCEL_CONFIRM].first.click.call_count == 0
        # the shared check already reported the failure it saw; the cleanup adds no second
        # warning and no second screenshot on top of a link that is in fact there
        assert warnings["files"] == [FAILURE_SHOT]
        assert not any("still open" in m for m in warnings["screenshot"])
        assert written == []


class TestDataPlaneLevelLink:
    def test_confirmation_dialog_never_appears_warns_and_cancels(self, monkeypatch):
        """DP level 'Use Global License File': when the confirmation dialog never
        renders the step must report and carry on instead of throwing out of a 30s
        wait_for, and the half-rendered dialog must be closed through its own Cancel
        control - the activation-url close buttons do not exist on it."""
        po = _new(PageObjectDataPlaneConfiguration)
        po.select_in_product_activation = MagicMock(return_value=True)
        registry = _wire_locators(po, {
            USE_GLOBAL_FILE: {"visible": True, "count": 1},
            CONFIRM_HEADING: {},
        })
        modal = _wire_open_modal(registry, CANCEL_CONFIRM)
        warnings = _wire_warnings(monkeypatch)
        written = _wire_report(monkeypatch)
        probes = _wire_check_dom_visibility(monkeypatch, [False, True, False, False])

        po.dp_config_activation_file(DP_NAME, True, "")

        assert probes == [LINKED_LABEL, USE_GLOBAL_FILE, CONFIRM_HEADING, LINKED_LABEL, LINKED_LABEL]
        assert registry[CONFIRM_HEADING].wait_for.call_count == 0
        link_failure = [m for m in warnings["screenshot"]
                        if "'Use Global License File' confirmation dialog never appeared" in m]
        assert len(link_failure) == 1
        assert DP_NAME in link_failure[0]
        assert written == []

        # closed through the confirmation dialog's Cancel, not an activation-url control
        assert modal["closed_by"] == [CANCEL_CONFIRM]
        assert registry[CLOSE_FOOTER_BTN].first.click.call_count == 0
        assert registry[CLOSE_HEADER_X].first.click.call_count == 0

    def test_a_link_click_that_times_out_is_reported_not_raised(self, monkeypatch):
        """'Link' is the action the whole step exists to perform, and it renders on the
        same loaded control plane every probe here is polled against. A timeout on it is
        re-raised and ends create-dp, so it keeps the full budget and, if it still runs
        out, falls through to the shared check - the link may well have gone through -
        and to the cleanup, instead of throwing out of the step."""
        po = _new(PageObjectDataPlaneConfiguration)
        po.select_in_product_activation = MagicMock(return_value=True)
        registry = _wire_locators(po, {
            USE_GLOBAL_FILE: {"visible": True, "count": 1},
            CONFIRM_BUTTON: {},
        })
        registry[CONFIRM_BUTTON].click.side_effect = PlaywrightTimeoutError("Timeout 30000ms exceeded")
        modal = _wire_open_modal(registry, CANCEL_CONFIRM)
        warnings = _wire_warnings(monkeypatch)
        written = _wire_report(monkeypatch)
        probes = _wire_check_dom_visibility(monkeypatch, [False, True, True, False])

        po.dp_config_activation_file(DP_NAME, True, "")

        assert ACTIVATION_DIALOG_SUBMIT_TIMEOUT >= 30000
        registry[CONFIRM_BUTTON].click.assert_called_once_with(timeout=ACTIVATION_DIALOG_SUBMIT_TIMEOUT)
        assert probes == [LINKED_LABEL, USE_GLOBAL_FILE, CONFIRM_HEADING, LINKED_LABEL, LINKED_LABEL]
        message = next(m for m in warnings["screenshot"] if "Link to the Global license file failed" in m)
        assert "'Link' button" in message
        assert modal["closed_by"] == [CANCEL_CONFIRM]
        assert written == []

    def test_the_use_global_button_is_polled_before_it_is_clicked(self, monkeypatch):
        """A one-shot is_visible() on the button skipped the 'pcp-disabled' guard on a
        late render and then let a bare click() stall on Playwright's 30s default. The
        button is polled first, and the guard reads it only once it has rendered."""
        po = _new(PageObjectDataPlaneConfiguration)
        po.select_in_product_activation = MagicMock(return_value=True)
        registry = _wire_locators(po, {USE_GLOBAL_FILE: {}})
        warnings = _wire_warnings(monkeypatch)
        written = _wire_report(monkeypatch)
        probes = _wire_check_dom_visibility(monkeypatch, [False, False, False])

        po.dp_config_activation_file(DP_NAME, True, "")

        assert probes == [LINKED_LABEL, USE_GLOBAL_FILE, LINKED_LABEL]
        assert registry[USE_GLOBAL_FILE].click.call_count == 0
        assert registry[USE_GLOBAL_FILE].get_attribute.call_count == 0
        message = next(m for m in warnings["screenshot"] if "Link to the Global license file failed" in m)
        assert "'Use Global License File' button never appeared" in message
        assert written == []


class TestActivationUrlTwin:
    def test_dp_level_failure_names_the_link_action_not_the_add_action(self, monkeypatch):
        """The DP-level path links to the Global URL, it does not add one. Composing the
        message from the truthiness of the (empty) activation URL named the wrong
        action, so it is composed from 'use_global' instead."""
        po = _new(PageObjectDataPlaneConfiguration)
        po.select_tibco_activation_service = MagicMock(return_value=True)
        registry = _wire_locators(po, {USE_GLOBAL_URL: {"visible": True, "count": 1}})
        monkeypatch.setattr(type(ENV), "TP_ACTIVATION_URL", "")
        warnings = _wire_warnings(monkeypatch)
        written = _wire_report(monkeypatch)
        probes = _wire_check_dom_visibility(monkeypatch, [True, False, False])

        po.dp_config_activation_url(DP_NAME, True)

        assert probes == [USE_GLOBAL_URL, CONFIRM_HEADING, ACTIVATION_URL_LABEL]
        message = next(m for m in warnings["screenshot"] if "failed for Data Plane" in m)
        assert "Link to the Global Activation URL failed" in message
        assert "Add Activation URL" not in message
        assert "'Use Global Activation URL' confirmation dialog never appeared" in message
        assert written == []

    def test_the_cleanup_re_check_reads_the_activation_url_label(self, monkeypatch):
        """This twin is judged by '.activation-server-url', not by the license text, so
        that is the condition its cleanup has to re-read before closing anything -
        otherwise a URL that lands late is cancelled straight back off again."""
        po = _new(PageObjectDataPlaneConfiguration)
        po.select_tibco_activation_service = MagicMock(return_value=True)
        registry = _wire_locators(po, {USE_GLOBAL_URL: {"visible": True, "count": 1}})
        monkeypatch.setattr(type(ENV), "TP_ACTIVATION_URL", "")
        modal = _wire_open_modal(registry, CANCEL_CONFIRM)
        warnings = _wire_warnings(monkeypatch)
        written = _wire_report(monkeypatch)
        probes = _wire_check_dom_visibility(monkeypatch, [True, True, False, True])

        po.dp_config_activation_url(DP_NAME, True)

        assert probes == [USE_GLOBAL_URL, CONFIRM_HEADING, ACTIVATION_URL_LABEL, ACTIVATION_URL_LABEL]
        assert modal["closed_by"] == []
        assert modal["open"] is True
        assert warnings["files"] == [URL_FAILURE_SHOT]
        assert written == []


class TestIsModalOpen:
    def test_no_modal_on_a_page_that_has_none(self):
        """count() first, then a per node is_visible(): a confirmation dialog stacked on
        another dialog makes the selector resolve two nodes, and Playwright strict mode
        would then make a bare is_visible() throw from inside the cleanup path."""
        po = _new(PageObjectDataPlaneConfiguration)
        registry = _wire_locators(po)

        assert po.is_modal_open() is False

        assert registry[MODAL].count.call_count == 1
        assert registry[MODAL].is_visible.call_count == 0
        assert registry[MODAL].nth.call_count == 0

    def test_open_modal_is_detected(self):
        po = _new(PageObjectDataPlaneConfiguration)
        registry = _wire_locators(po)
        _wire_open_modal(registry)

        assert po.is_modal_open() is True

    def test_a_mounted_but_hidden_modal_does_not_count_as_open(self):
        """A hidden '.pl-modal--open' node blocks nothing. Reading presence alone would
        keep it 'open' for ever: the close loop could never converge, and every healthy
        run would collect a spurious warning and screenshot."""
        po = _new(PageObjectDataPlaneConfiguration)
        _wire_locators(po, {MODAL: {"count": 1, "visible": False}})

        assert po.is_modal_open() is False

    def test_a_detached_page_answers_false_instead_of_raising(self):
        """It is called from a finally block, so it may not raise there either."""
        po = _new(PageObjectDataPlaneConfiguration)
        po.page.locator.side_effect = RuntimeError("Target page, context or browser has been closed")

        assert po.is_modal_open() is False


class TestProbeBudgets:
    def test_slow_render_probes_keep_the_full_wait_budget(self, monkeypatch):
        """These probes replaced wait_for(state='visible'), which carried Playwright's
        30s default. Polling costs nothing when the element is already there, and
        shrinking the ceiling makes the slow-render race this fix is about MORE likely
        to be lost - and turns losing it into a silent skip."""
        po = _new(PageObjectDataPlaneConfiguration)
        po.select_in_product_activation = MagicMock(return_value=True)
        _wire_locators(po, {USE_GLOBAL_FILE: {"visible": True, "count": 1}})
        _wire_warnings(monkeypatch)
        _wire_report(monkeypatch)
        probes = _wire_check_dom_visibility(monkeypatch, [False, True, False, False])

        po.dp_config_activation_file(DP_NAME, True, "")

        budgets = {probe: (probe.interval, probe.max_wait) for probe in probes}
        assert budgets[USE_GLOBAL_FILE] == (3, 30)
        assert budgets[CONFIRM_HEADING] == (3, 30)

    def test_the_add_button_probe_waits_on_server_side_validation(self, monkeypatch):
        """'Add' enables only after the backend has accepted the file, so it gets the
        full budget, while the two client-side mounts around it keep the short one."""
        po, _ = _global_upload_po(monkeypatch, {DROP_ZONE: {"visible": True, "count": 1}})
        _wire_warnings(monkeypatch)
        _wire_report(monkeypatch)
        probes = _wire_check_dom_visibility(monkeypatch, [False, True, True, True, True])

        po.dp_config_activation_file(GLOBAL_DP_NAME, False, ACTIVATION_FILE)

        budgets = {probe: (probe.interval, probe.max_wait) for probe in probes}
        assert budgets[ADD_BTN_ENABLED] == (3, 30)
        assert budgets[UPLOAD_OPTION] == (2, 6)
        assert budgets[DROP_ZONE] == (2, 6)


class TestCloseControlsStayBoundedAndScoped:
    def test_no_close_candidate_reaches_outside_the_open_modal(self, monkeypatch):
        """'--secondary' is not necessarily Cancel in this UI - po_bmdp_config uses that
        class for 'Validate Server' - so the unscoped legacy candidate could fire a real
        action on an unrelated modal, three passes in a row. It is kept for older
        control planes, but scoped to the open modal footer and to Cancel/Close."""
        po = _new(PageObjectDataPlaneConfiguration)
        _wire_locators(po, {MODAL: {"count": 1, "visible": True}})
        _wire_warnings(monkeypatch)

        assert po.close_open_modal() is False

        used = [selector for selector in _located(po) if selector != MODAL]
        assert used, "the candidate list has to be walked for this to prove anything"
        for selector in used:
            for part in selector.split(","):
                assert part.strip().startswith(".pl-modal--open"), part
        legacy = next(selector for selector in used if "pl-button--secondary" in selector)
        assert "Cancel" in legacy and "Close" in legacy

    def test_the_close_walk_is_bounded_by_a_wall_clock_deadline(self, monkeypatch):
        """Three passes of click timeouts over the whole candidate list is a minute of
        wall clock, spent inside a finally on the create-dp critical path, on top of the
        failure that is already being reported."""
        po = _new(PageObjectDataPlaneConfiguration)
        _wire_locators(po, {MODAL: {"count": 1, "visible": True}})
        _wire_warnings(monkeypatch)

        # every reading is 10 seconds later than the last, so the 15s ceiling is passed
        # part way through the first pass
        ticks = iter(range(0, 10000, 10))
        clock = MagicMock()
        clock.monotonic.side_effect = lambda: next(ticks)
        monkeypatch.setattr("page_object.po_global.time", clock)

        assert po.close_open_modal() is False
        assert po.page.keyboard.press.call_count == 0
        assert len([selector for selector in _located(po) if selector != MODAL]) < 6

    def test_close_clicks_carry_an_explicit_but_workable_timeout(self, monkeypatch):
        """Every second spent here is added to a run that has already gone wrong, so the
        click is bounded rather than left on Playwright's 30s default - but the modal it
        is closing is one that renders slowly under install load, which is the whole
        reason this cleanup exists, so the bound is seconds and not milliseconds."""
        po = _new(PageObjectDataPlaneConfiguration)
        registry = _wire_locators(po)
        _wire_open_modal(registry)
        _wire_warnings(monkeypatch)

        assert po.close_open_modal() is True

        registry[CLOSE_FOOTER_BTN].first.click.assert_called_once_with(timeout=MODAL_CLOSE_CLICK_TIMEOUT)
        assert 5000 <= MODAL_CLOSE_CLICK_TIMEOUT < 30000

    def test_a_caller_supplied_cancel_keeps_the_full_click_budget(self, monkeypatch):
        """The Ingress/Route caller clicked its own Cancel with Playwright's default
        budget before this helper existed. Handing it the cleanup budget instead would
        make the shared helper worse than the code it replaced on a path that worked."""
        po = _new(PageObjectDataPlaneConfiguration)
        registry = _wire_locators(po)
        modal = _wire_open_modal(registry, INGRESS_CANCEL)
        _wire_warnings(monkeypatch)

        assert po._close_modal() is True

        assert modal["closed_by"] == [INGRESS_CANCEL]
        registry[INGRESS_CANCEL].first.click.assert_called_once_with(
            timeout=MODAL_CLOSE_CALLER_CLICK_TIMEOUT)
        assert MODAL_CLOSE_CALLER_CLICK_TIMEOUT > MODAL_CLOSE_CLICK_TIMEOUT

    def test_the_footer_candidates_cover_both_footer_variants(self, monkeypatch):
        """This UI writes the modal footer as '.pl-modal__footer' and just as often as
        '.pl-modal__footer-left' / '.pl-modal__footer-right' (po_dp_bwce, po_dp_flogo,
        po_bmdp_config, po_dp_springboot). A footer candidate that knows only the first
        spelling matches almost nothing and quietly stops being a fallback at all."""
        po = _new(PageObjectDataPlaneConfiguration)
        _wire_locators(po, {MODAL: {"count": 1, "visible": True}})
        _wire_warnings(monkeypatch)

        po.close_open_modal()

        footer_candidates = [selector for selector in _located(po) if "pl-modal__footer" in selector]
        assert footer_candidates
        for variant in (".pl-modal__footer ", ".pl-modal__footer-left ", ".pl-modal__footer-right "):
            assert any(variant in selector for selector in footer_candidates), variant

    def test_a_deadline_cut_walk_does_not_claim_every_control_was_tried(self, monkeypatch):
        """The ceiling can end the walk half way through the candidate list. Reporting
        that as "after trying every close control" sends the reader looking for a dialog
        with no working close button, when the controls were simply never reached."""
        po = _new(PageObjectDataPlaneConfiguration)
        _wire_locators(po, {MODAL: {"count": 1, "visible": True}})
        warnings = _wire_warnings(monkeypatch)

        ticks = iter(range(0, 10000, 10))
        clock = MagicMock()
        clock.monotonic.side_effect = lambda: next(ticks)
        monkeypatch.setattr("page_object.po_global.time", clock)

        assert po.close_open_modal() is False

        assert any("close budget ran out" in m for m in warnings["log"])
        assert not any("every close control" in m for m in warnings["log"])

    def test_a_modal_that_closed_on_the_deadline_is_not_warned_about(self, monkeypatch):
        """The deadline is a reason to stop walking, not a verdict: the dialog may well
        have unmounted while the walk was being cut short, and warning without looking
        again reports a blocked navigation that is not blocked."""
        po = _new(PageObjectDataPlaneConfiguration)
        registry = _wire_locators(po, {MODAL: {"count": 1, "visible": True}})
        warnings = _wire_warnings(monkeypatch)

        ticks = iter(range(0, 10000, 10))
        now = {"seconds": 0}

        def _monotonic():
            now["seconds"] = next(ticks)
            return now["seconds"]

        clock = MagicMock()
        clock.monotonic.side_effect = _monotonic
        monkeypatch.setattr("page_object.po_global.time", clock)
        # open while the walk runs, gone by the time the 15s ceiling cuts it short
        registry[MODAL].count.side_effect = lambda: 1 if now["seconds"] <= MODAL_CLOSE_MAX_SECONDS else 0

        assert po.close_open_modal() is True
        assert warnings["log"] == []

    def test_escape_is_not_pressed_when_no_modal_is_open(self, monkeypatch):
        """Escape is not a no-op on a page with no dialog: it reaches whatever else is
        listening for it. Nothing open means nothing to close."""
        po = _new(PageObjectDataPlaneConfiguration)
        _wire_locators(po)
        _wire_warnings(monkeypatch)

        assert po.close_open_modal() is True
        assert po.page.keyboard.press.call_count == 0

    def test_the_checked_node_is_the_node_that_gets_clicked(self, monkeypatch):
        """A locator re-queries the page on every call, so on a page where dialogs are
        unmounting underneath the walk, the node that answered is_visible() need not be
        the node that receives the click. The match is resolved to one handle instead."""
        po = _new(PageObjectDataPlaneConfiguration)
        registry = _wire_locators(po)
        _wire_open_modal(registry)
        _wire_warnings(monkeypatch)

        assert po.close_open_modal() is True

        control = registry[CLOSE_FOOTER_BTN]
        handle = control.first.element_handle.return_value
        assert control.first.element_handle.call_count == 1
        assert handle.is_visible.call_count == 1
        assert handle.click.call_count == 1


class TestFailureNamesTheSubCause:
    def test_rejected_file_reports_the_dialog_error_message(self, monkeypatch):
        """'Add' never enables and the dialog says why: the message must carry the
        dialog's own error text and must not blame expiry."""
        po, registry = _global_upload_po(monkeypatch, {
            DROP_ZONE: {"visible": True, "count": 1},
            FILE_ERROR: {"count": 1, "text": "The selected file is not a valid license file."},
            MODAL: {"count": 1, "text": "Add New License File\nThe selected file is not a valid license file."},
        })
        _wire_open_modal(registry)
        warnings = _wire_warnings(monkeypatch)
        written = _wire_report(monkeypatch)
        probes = _wire_check_dom_visibility(monkeypatch, [False, True, True, False, False])

        po.dp_config_activation_file(GLOBAL_DP_NAME, False, ACTIVATION_FILE)

        assert probes == [LINKED_LABEL, UPLOAD_OPTION, DROP_ZONE, ADD_BTN_ENABLED, LINKED_LABEL, LINKED_LABEL]
        message = next(m for m in warnings["screenshot"] if "Add Activation file" in m)
        assert "The 'Add' button in the 'Add New License File' dialog never enabled." in message
        assert "The selected file is not a valid license file." in message
        assert "has expired" not in message
        assert written == []

    def test_expired_license_without_an_error_message_is_reported_as_expired(self, monkeypatch):
        """Same symptom, different cause: the file parsed fine but every entry in it has
        expired, which the dialog only renders as body text. An empty error field next
        to that text has to point at expiry rather than at a broken file."""
        po, registry = _global_upload_po(monkeypatch, {
            DROP_ZONE: {"visible": True, "count": 1},
            MODAL: {"count": 1, "text":
                    "Add New License File\nCurrent In-product licenses expired on 12 Jan 2026\nUpload a new license file"},
        })
        _wire_open_modal(registry)
        warnings = _wire_warnings(monkeypatch)
        written = _wire_report(monkeypatch)
        _wire_check_dom_visibility(monkeypatch, [False, True, True, False, False])

        po.dp_config_activation_file(GLOBAL_DP_NAME, False, ACTIVATION_FILE)

        message = next(m for m in warnings["screenshot"] if "Add Activation file" in m)
        assert "The 'Add' button in the 'Add New License File' dialog never enabled." in message
        assert "Current In-product licenses expired on 12 Jan 2026" in message
        assert "check whether the license has expired" in message
        assert "Dialog error message" not in message
        assert written == []

    def test_an_expiration_date_on_a_valid_license_is_not_called_expired(self, monkeypatch):
        """Every valid license renders an 'Expiration Date' line, so a bare /expir/i
        match declares a perfectly good license expired and sends the reader chasing a
        licence that is not the problem."""
        po, registry = _global_upload_po(monkeypatch, {
            DROP_ZONE: {"visible": True, "count": 1},
            MODAL: {"count": 1, "text":
                    "Add New License File\nExpiration Date: 12 Jan 2030\nEdition: Enterprise"},
        })
        _wire_open_modal(registry)
        warnings = _wire_warnings(monkeypatch)
        _wire_report(monkeypatch)
        _wire_check_dom_visibility(monkeypatch, [False, True, True, False, False])

        po.dp_config_activation_file(GLOBAL_DP_NAME, False, ACTIVATION_FILE)

        message = next(m for m in warnings["screenshot"] if "Add Activation file" in m)
        assert "expired" not in message
        assert "Expiration Date: 12 Jan 2030" not in message

    def test_scraped_dialog_text_is_capped_and_kept_on_one_line(self, monkeypatch):
        """The message goes to a plain text console log, so the scraped text is capped -
        a whole license listing may not be poured into the log - and flattened, so a
        multi line dialog error cannot forge log lines of its own. It is deliberately
        NOT html escaped: that turns every apostrophe in an ordinary dialog message into
        '&#x27;' and makes the log harder to read than the dialog it came from."""
        po, registry = _global_upload_po(monkeypatch, {
            DROP_ZONE: {"visible": True, "count": 1},
            FILE_ERROR: {"count": 1, "text":
                         "The file's format isn't valid & was rejected.\n[ERROR] forged log line\n"
                         + "A" * 400 + "TAIL_MARKER"},
        })
        _wire_open_modal(registry)
        warnings = _wire_warnings(monkeypatch)
        _wire_report(monkeypatch)
        _wire_check_dom_visibility(monkeypatch, [False, True, True, False, False])

        po.dp_config_activation_file(GLOBAL_DP_NAME, False, ACTIVATION_FILE)

        message = next(m for m in warnings["screenshot"] if "Add Activation file" in m)
        assert "The file's format isn't valid & was rejected." in message
        assert "&#x27;" not in message and "&amp;" not in message
        assert "\n" not in message
        assert "TAIL_MARKER" not in message
        assert "..." in message

    def test_a_line_saying_a_license_has_not_expired_is_not_reported_as_an_expiry(self, monkeypatch):
        """A negation carries the word too. Matching it turns a dialog that says the
        license is fine into a report that it is dead."""
        po, registry = _global_upload_po(monkeypatch, {
            DROP_ZONE: {"visible": True, "count": 1},
            MODAL: {"count": 1, "text":
                    "Add New License File\nExpired Licenses\nThe current license has not expired."},
        })
        _wire_open_modal(registry)
        warnings = _wire_warnings(monkeypatch)
        _wire_report(monkeypatch)
        _wire_check_dom_visibility(monkeypatch, [False, True, True, False, False])

        po.dp_config_activation_file(GLOBAL_DP_NAME, False, ACTIVATION_FILE)

        message = next(m for m in warnings["screenshot"] if "Add Activation file" in m)
        assert "mentions an expiry" not in message
        assert "check whether the license has expired" not in message

    def test_no_dialog_of_our_own_means_no_dialog_text_is_scraped(self, monkeypatch):
        """The scrape reads '.pl-modal--open' off whatever is on screen. On a skip path
        this step opened nothing, so that modal - and any 'expired' line in it - belongs
        to the CALLER, and folding its text into this step's failure blames this step for
        someone else's dialog. Nor may the message claim a dialog reported nothing when
        there was no dialog of ours to report anything."""
        po, registry = _global_upload_po(monkeypatch, {
            UPLOAD_OPTION: {},
            MODAL: {"count": 1, "text": "Some other dialog\nCurrent In-product licenses expired on 12 Jan 2026"},
        })
        warnings = _wire_warnings(monkeypatch)
        _wire_report(monkeypatch)
        _wire_check_dom_visibility(monkeypatch, [False, False, False, False])

        po.dp_config_activation_file(GLOBAL_DP_NAME, False, ACTIVATION_FILE)

        message = next(m for m in warnings["screenshot"] if "Add Activation file" in m)
        assert "expired" not in message
        assert "The dialog reported no error message" not in message
        assert registry[MODAL].last.inner_text.call_count == 0
