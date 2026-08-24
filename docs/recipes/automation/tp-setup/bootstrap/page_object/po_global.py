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
import time

from utils.color_logger import ColorLogger
from utils.env import ENV
from utils.util import Util

# close_open_modal() runs from a finally block on the create-dp critical path, so the
# cleanup walk is bounded twice: a wall clock ceiling for the whole walk, and a per click
# timeout. That timeout still has to cover a modal that is animating in under install
# load - the exact condition this cleanup exists for - so it is seconds, not
# milliseconds, and every click and settle is additionally clamped to what is left of the
# ceiling, which is what keeps the ceiling honest.
MODAL_CLOSE_MAX_SECONDS = 15
MODAL_CLOSE_CLICK_TIMEOUT = 5000
# The caller supplied cancel control is a different case: it is the proven close path of
# an existing caller (the Ingress/Route dialog, which clicked it with Playwright's default
# budget), so it keeps that budget and is tried before the ceiling is armed.
MODAL_CLOSE_CALLER_CLICK_TIMEOUT = 30000
# Resolving a node that count() has already matched is immediate; this only stops a
# pathological resolve from eating a whole click budget of its own.
MODAL_CLOSE_RESOLVE_TIMEOUT = 1000
# How long a modal is given to unmount after a close control fired.
MODAL_CLOSE_SETTLE_MS = 500

class PageObjectGlobal:
    def __init__(self, page):
        self.page = page
        self.env = ENV
        self.is_fresco = False

    def goto_left_navbar(self, item_name):
        ColorLogger.info(f"Going to left side menu ...")
        # Poll with logged progress instead of a silent wait_for() so a slow/abnormal
        # left-nav re-render (e.g. right after a heavy DP config operation) fails with a
        # screenshot and clear logs rather than an opaque "Timeout 30000ms exceeded".
        if not Util.check_dom_visibility(self.page, self.page.locator(".nav-bar-pointer", has_text=item_name), 3, 30):
            Util.exit_error(f"Left side menu '{item_name}' is not visible.", self.page, "goto_left_navbar.png")
        self.page.locator(".nav-bar-pointer", has_text=item_name).click()
        print(f"Clicked left side menu '{item_name}'")
        self.page.wait_for_timeout(500)

    def is_modal_open(self):
        """Whether a Pulse modal is mounted AND visible on the page.

        Visibility is what matters: a mounted but hidden '.pl-modal--open' node would
        otherwise read as open for ever, so the close loop could never converge and a
        perfectly healthy run would collect a warning and a screenshot.

        It is read per node instead of straight off the locator, because a confirmation
        dialog stacked on another dialog makes the selector resolve two elements, and
        Playwright strict mode then makes a bare is_visible() throw - from inside a
        cleanup path, which is the one place an exception must not come from. The whole
        body is guarded for the same reason.

        Scope is the Pulse (pl-*) modal family only. The PrimeNG dialog family has its
        own waiter, PageObjectDataPlaneActiveSpaces.wait_for_overlay_to_clear(), which
        polls '.p-dialog-mask' through its leave animation.
        """
        try:
            modals = self.page.locator(".pl-modal--open")
            count = modals.count() or 0
            return count > 0 and any(modals.nth(i).is_visible() for i in range(count))
        except Exception as e:
            print(f"Could not tell whether a modal is open: {str(e)}")
            return False

    def _click_modal_control(self, selector, prefer_last=False, timeout=MODAL_CLOSE_CLICK_TIMEOUT):
        """Click one visible node matching 'selector'; True only if a click fired.

        The count guard keeps the attempt from being reported as a success when nothing
        matches, and the visibility guard keeps a hidden leftover node from swallowing
        it. 'prefer_last' takes the last match in DOM order, which is what the class
        based candidates want: when dialogs stack, the one holding the blocking overlay
        is the top-most.

        The match is resolved to a single element handle and that same handle is both
        checked and clicked. A locator re-queries the page on every call, so on a page
        where dialogs are unmounting underneath the walk the node that answered
        is_visible() is not necessarily the node that gets the click. The handle is used
        immediately and thrown away - nothing is polled through it, which is what makes a
        frozen handle a problem elsewhere (see po_mcp_hub).

        The click carries an explicit timeout because this runs on a cleanup path: a
        control that cannot be clicked inside it is blocked by something, and sitting on
        Playwright's 30s default only delays the real failure being reported.
        """
        try:
            locator = self.page.locator(selector)
            if (locator.count() or 0) == 0:
                return False
            match = locator.last if prefer_last else locator.first
            control = match.element_handle(timeout=min(timeout, MODAL_CLOSE_RESOLVE_TIMEOUT))
            if control is None or not control.is_visible():
                return False
            control.click(timeout=timeout)
            return True
        except Exception as e:
            print(f"Could not click '{selector}' to close the modal: {str(e)}")
            return False

    def _modal_close_remaining_ms(self, deadline):
        """Milliseconds left of the cleanup ceiling; <= 0 once it is spent."""
        return int((deadline - time.monotonic()) * 1000)

    def _modal_close_settle(self, deadline):
        """Let a modal unmount after a close control fired, without outliving the ceiling."""
        self.page.wait_for_timeout(max(min(MODAL_CLOSE_SETTLE_MS, self._modal_close_remaining_ms(deadline)), 0))

    def close_open_modal(self, extra_cancel_selector=""):
        """Best effort close of whatever Pulse modal is left on screen. Never raises.

        A surviving '.pl-modal--open' overlay swallows pointer events, so the next
        navigation fails with an "intercepts pointer events" timeout far away from the
        step that actually went wrong.

        A caller supplied cancel control is tried first, unconditionally and with the full
        click budget the Ingress/Route caller gave it before this helper existed: it is
        that caller's proven close path, so it is neither gated behind a modal probe nor
        narrowed by the cleanup budget the rest of the walk runs on. Once, and before the
        ceiling is armed: when that control is on the page the click already auto-waits
        actionability for its whole budget, and when it is not, a second attempt at it
        would add nothing the shared candidates and Escape behind it do not. What that
        caller gains is the rest of the walk - those candidates, and a re-read of what is
        actually still on screen - in place of two blind Escape presses.

        Each shared candidate is (selector, prefer_last), and that walk is bounded by
        MODAL_CLOSE_MAX_SECONDS: it runs from a finally block on the create-dp critical
        path, and three passes of click timeouts must not be allowed to add up to a minute
        on top of the failure that is already being reported. Every click and every settle
        inside the walk is clamped to what is left of that ceiling.
        """
        try:
            if extra_cancel_selector and self._click_modal_control(extra_cancel_selector, False, MODAL_CLOSE_CALLER_CLICK_TIMEOUT):
                print(f"Clicked '{extra_cancel_selector}' to close the open modal")
                self.page.wait_for_timeout(MODAL_CLOSE_SETTLE_MS)
                if not self.is_modal_open():
                    return True

            # Pulse renders the modal footer as '.pl-modal__footer' and, at least as often
            # in this UI, as '.pl-modal__footer-left' / '.pl-modal__footer-right' (see
            # po_dp_bwce, po_dp_flogo, po_bmdp_config, po_dp_springboot), so a candidate
            # scoped to the first alone would match almost nothing.
            footers = (
                ".pl-modal--open .pl-modal__footer",
                ".pl-modal--open .pl-modal__footer-left",
                ".pl-modal--open .pl-modal__footer-right",
            )
            candidates = [
                (".pl-modal--open #close-activation-url-modal-btn", False),  # footer close, add-license-modal and activation-url-modal
                (".pl-modal--open #close-activation-url-modal", False),      # header X
                (".pl-modal--open #cancel-confirm-button", False),           # confirmation-modal, e.g. 'Use Global License File'
                (".pl-modal--open .pl-modal__close", True),
                (", ".join(f'{footer} button:has-text("Cancel")' for footer in footers), True),
                # Older CP versions, kept last for backward compatibility. Scoped to the open
                # modal footer and to Cancel/Close text on purpose: '--secondary' is not
                # necessarily Cancel in this UI (po_bmdp_config uses it for 'Validate Server'),
                # so an unscoped match could fire a real action on an unrelated dialog.
                (", ".join(f'{footer} button.pl-button--secondary:has-text("{label}")'
                           for footer in footers for label in ("Cancel", "Close")), True),
            ]
            deadline = time.monotonic() + MODAL_CLOSE_MAX_SECONDS
            deadline_reached = False
            for attempt in range(3):
                # A modal that went away between passes ends it here rather than paying
                # for another walk of the whole candidate list.
                if attempt > 0 and not self.is_modal_open():
                    return True
                for selector, prefer_last in candidates:
                    budget = self._modal_close_remaining_ms(deadline)
                    # Starting a click that cannot finish inside the ceiling only buys a
                    # "Timeout 3ms exceeded" line in a log that is already reporting a
                    # real failure.
                    if budget <= MODAL_CLOSE_RESOLVE_TIMEOUT:
                        deadline_reached = True
                        break
                    if not self._click_modal_control(selector, prefer_last, min(MODAL_CLOSE_CLICK_TIMEOUT, budget)):
                        continue
                    print(f"Clicked '{selector}' to close the open modal")
                    self._modal_close_settle(deadline)
                    if not self.is_modal_open():
                        return True
                if deadline_reached or self._modal_close_remaining_ms(deadline) <= MODAL_CLOSE_SETTLE_MS:
                    deadline_reached = True
                    break
                # Escape is vestigial for the activation dialogs - they declare onKeyDown
                # but register no keydown listener - and is kept only for the other CP
                # dialogs that do close on it. It is pressed only while something is
                # actually open: on a page with no modal it is not a no-op, it reaches
                # whatever else on the page listens for it. keyboard.press takes no timeout
                # because it dispatches straight away, with none of the actionability
                # waiting that makes a click on a detaching node hang.
                if not self.is_modal_open():
                    return True
                self.page.keyboard.press("Escape")
                self._modal_close_settle(deadline)
                print(f"Pressed Escape to close the modal, attempt {attempt + 1}")
                if not self.is_modal_open():
                    return True
        except Exception as e:
            ColorLogger.warning(f"Failed to close the open modal: {str(e)}")
            return False

        # The walk can end because the ceiling cut it short, so what is on screen NOW
        # decides, and the warning may not claim every control was tried when it was not.
        if not self.is_modal_open():
            return True
        if deadline_reached:
            ColorLogger.warning(f"A modal is still open after the {MODAL_CLOSE_MAX_SECONDS}s close budget ran out; the next navigation may be blocked.")
        else:
            ColorLogger.warning("A modal is still open after trying every close control; the next navigation may be blocked.")
        return False

    def detect_fresco_ui(self):
        ColorLogger.info("Detecting if the UI is using Fresco header...")
        if Util.check_dom_visibility(self.page, self.page.locator("tibco-header"), 1, 2):
            self.is_fresco = True
            ColorLogger.info("Fresco header UI detected.")
        else:
            ColorLogger.info("Fresco header UI not detected.")

    def selector_header_dp_name(self):
        return "tibco-header tibco-breadcrumbs .p-breadcrumb-item"

    def selector_header_app_name(self):
        return "tibco-header .header-title-readonly-text"

    def selector_header_action_menu(self):
        selector = "#app-details-menu-dropdown-label"
        if self.is_fresco:
            selector = "tibco-header .tibco-header-action-btn .pi-ellipsis-v"
        return selector

    def selector_header_action_menu_item(self):
        selector = ".pl-dropdown-menu__action"
        if self.is_fresco:
            selector = ".p-menu-item-label"
        return selector

    def selector_header_app_status_tooltip(self):
        selector = ".pl-tooltip__content:visible"
        if self.is_fresco:
            selector = ".p-tooltip-text:visible"
        return selector

    def selector_header_app_scale_input(self):
        return "tibco-header .tibco-header-scaling-field-group input.p-inputtext"

    def selector_header_app_action_btn(self):
        return "tibco-header .tibco-header-scaling-field-group .p-button:not([disabled])"

    def get_app_instance_number(self):
        input_value = 0
        try:
            self.page.locator(self.selector_header_app_scale_input()).wait_for(state="visible")
            input_value = self.page.locator(self.selector_header_app_scale_input()).input_value().strip()
            print(f"Get app instance number: {input_value}")
        except Exception as e:
            Util.warning_screenshot(f"Failed to get app instance number: {str(e)}", self.page, "get_app_instance_number.png")
        return int(input_value)

    def get_app_status(self):
        app_status = ""
        try:
            print(f"Wait for tooltip from Dom {self.selector_header_app_scale_input()}...")
            self.page.locator(self.selector_header_app_scale_input()).wait_for(state="visible")
            print(f"Mouseover to Dom {self.selector_header_app_scale_input()}...")
            self.page.locator(self.selector_header_app_scale_input()).focus()
            self.page.locator(self.selector_header_app_scale_input()).hover(force=True)
            self.page.locator(self.selector_header_app_scale_input()).dispatch_event("pointerover")
            self.page.locator(self.selector_header_app_scale_input()).dispatch_event("mouseover")
            self.page.wait_for_timeout(200)
            app_status = self.page.locator(self.selector_header_app_status_tooltip()).inner_text().split("\n")[0]
            app_status = re.sub("Status:", "", app_status, flags=re.IGNORECASE).strip()
            if app_status:
                print(f"Get app status: {app_status}")
        except Exception as e:
            Util.warning_screenshot(f"Failed to get app status: {str(e)}", self.page, "get_app_status.png")
        return app_status
