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

from page_object.po_global import PageObjectGlobal
from utils.color_logger import ColorLogger
from utils.env import ENV
from utils.report import ReportYaml
from utils.util import Util

# Outcome of a single product-permission grant. All four are TRUTHY, so callers must
# compare against the constant ("if result == GRANT_FAILED"), never use it as a boolean.
GRANT_DONE = "granted"
GRANT_ALREADY = "already"
GRANT_SKIPPED = "skipped"
GRANT_FAILED = "failed"

class PageObjectUserManagement(PageObjectGlobal):
    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.env = ENV

    def grant_permission(self, permission, checked="true"):
        ColorLogger.info(f"Granting permission for {permission}...")
        self.page.locator(".policy-description", has_text=permission).click()
        input_selectors = self.page.locator('.dp-selector-container input[type="checkbox"]').all()
        if len(input_selectors) == 1:
            input_selector = input_selectors[0]
            # check if input aria-checked="true" does not exist, then click
            is_selected = input_selector.get_attribute("aria-checked")
            if is_selected != checked:
                input_selector.locator("xpath=..").locator("label").click()
                print("Granted permission for " + permission)
        else:
            selectors = self.page.locator('label', has_text="All current and future").all()
            for selector in selectors:
                is_selected = self.page.locator(f"#{selector.get_attribute("for")}").get_attribute("aria-checked")
                if is_selected != checked:
                    selector.click()
                    print(f"Granted permission for {permission} -> {selector.inner_text()}")

    def goto_assign_permissions(self):
        print("Start set user permission...")
        self.page.click("#nav-bar-menu-item-usrMgmt")
        self.page.click("#users-menu-item")
        self.page.locator(f'.user-name-text[id="go-to-user-details-{ENV.DP_USER_EMAIL}"]').wait_for(state="visible")
        print(f"{ENV.DP_USER_EMAIL} is found.")

        # Newer control planes render this table with PrimeNG and the row action button
        # carries no id at all, so the legacy id resolves to nothing. Try it first so older
        # control planes keep their exact behaviour, then fall back to the generic button.
        user_row = self.page.locator("team-members tr", has=self.page.locator(f'.user-name-text[id="go-to-user-details-{ENV.DP_USER_EMAIL}"]'))
        row_menu_trigger = user_row.locator("dropdown-button button#changeME-dropdown-label")
        if row_menu_trigger.count() == 0:
            row_menu_trigger = user_row.locator("dropdown-button button")
        row_menu_trigger.first.click()
        print(f"Click on dropdown button for user {ENV.DP_USER_EMAIL}")

        # Same migration renames the menu entries: .pl-dropdown-menu__action becomes a
        # role-based menuitem. Keep both so either markup resolves.
        update_permissions = self.page.locator(".pl-dropdown-menu__action", has_text="Update permissions")
        if not Util.check_dom_visibility(self.page, update_permissions, 1, 3):
            update_permissions = self.page.locator("[role='menuitem']", has_text="Update permissions")
            update_permissions.first.wait_for(state="visible")
        update_permissions.first.click()
        print(f"Clicked 'Update permissions' from dropdown list")

        self.page.locator(".policy-selector-container").wait_for(state="visible")
        print("Assign permissions page is loaded.")

    def set_user_permission(self):
        if ReportYaml.get(".ENV.REPORT_USER_PERMISSION") == "true":
            ColorLogger.success(f"In {ENV.TP_AUTO_REPORT_YAML_FILE} file, user permission is already set.")
            return
        ColorLogger.info("Setting user permission...")
        self.goto_left_navbar("Data Planes")
        self.page.locator("#register-dp-button").wait_for(state="visible")
        print("Checking if user has permission...")
        if not self.page.locator("#register-dp-button").is_disabled():
            ColorLogger.success(f"User {ENV.DP_USER_EMAIL} already has all permissions.")
            ReportYaml.set(".ENV.REPORT_USER_PERMISSION", True)
            return

        self.goto_assign_permissions()
        print(f"Assign Permissions for {ENV.DP_USER_EMAIL}")
        # if it has 8 green icons, then exit this function
        if self.page.locator(".policy-selector-container .green-check-icon").count() >= 8:
            ColorLogger.success(f"User {ENV.DP_USER_EMAIL} already has all permissions.")
            ReportYaml.set(".ENV.REPORT_USER_PERMISSION", True)
            return

        self.grant_permission("IdP Manager")
        self.grant_permission("Team Admin")
        self.grant_permission("Data plane Manager")
        self.grant_permission("Capability Manager")
        self.grant_permission("Application Manager")
        self.grant_permission("Application Viewer")
        self.grant_permission("View permissions")
        # if button is not disabled, then click
        if not self.page.locator("#next-assign-permissions").is_disabled():
            self.page.click("#next-assign-permissions")
            self.page.click("#assign-permissions-update")
            ColorLogger.success(f"Grant All permission to {ENV.DP_USER_EMAIL}")
            ReportYaml.set(".ENV.REPORT_USER_PERMISSION", True)
        else:
            ColorLogger.success(f"User {ENV.DP_USER_EMAIL} already has all permissions.")
            ReportYaml.set(".ENV.REPORT_USER_PERMISSION", True)

    def grant_product_permission(self, dp_name, app_name) -> str:
        """Converge the 'Product Permission' grant of one product on one dataplane.

        Idempotent: an existing "all domains + Write" grant is left untouched (no click,
        no POST). Always returns exactly one of GRANT_DONE / GRANT_ALREADY /
        GRANT_SKIPPED / GRANT_FAILED - all truthy, so compare against the constant.
        """
        permission = "Product Permission"
        ColorLogger.info(f"Granting  {permission} for "+ dp_name + " => " + app_name)
        try:
            self.goto_assign_permissions()

            # The container paints at a fixed height from the first frame, so its
            # visibility says nothing about the policy rows: those arrive at the end of a
            # serial chain of dataplane/user/policy requests. Wait for the row itself
            # before reading anything, or a merely slow CP is misread as one that does not
            # offer the policy at all.
            print("Checking if product permission is visible...")
            policy_selector = self.page.locator(".policy-description", has_text=permission)
            if not Util.check_dom_visibility(self.page, policy_selector, 2, 20):
                ColorLogger.warning(f"'{permission}' did not render within 20s - either this CP does not offer it or the page is slow. Skipping {dp_name} => {app_name}.")
                self._cancel_assign_permissions()
                return GRANT_SKIPPED

            # 'Update' posts the user's ENTIRE permission set (a full replace), so a
            # mis-read wizard could drop the base CP/DP policies the user already has.
            # Snapshot the granted count and refuse to submit if it ever drops. Taken only
            # now that the policy list has demonstrably rendered - a count read against an
            # unpopulated list would be 0 and silently disarm the guard.
            baseline_policies = self.page.locator(".policy-selector-container .green-check-icon").count()
            print(f"Currently granted policies: {baseline_policies}")
            if baseline_policies == 0:
                # every caller runs set_user_permission() first, so at least one is expected
                ColorLogger.warning("No granted policies were visible, so the drop guard is disarmed for this attempt.")

            print("Product permission is visible.")
            policy_selector.click()
            print("Checking product permission for " + dp_name + " => " + app_name)

            # Locator.click() is strict-mode: a loose has_text also matches "k8s-auto-bmdp1"
            # inside "k8s-auto-bmdp10" and two resolved nodes throw. Anchor on the whole row
            # text, keeping the loose form as a fallback so older CP markup still resolves.
            dataplane_selector = self.page.locator('.dataplane-selector', has=self.page.locator('.dp-name-text', has_text=re.compile(rf"^\s*{re.escape(dp_name)}\s*$"))).first
            if not Util.check_dom_visibility(self.page, dataplane_selector, 2, 4):
                dataplane_selector = self.page.locator('.dataplane-selector', has=self.page.locator('.dp-name-text', has_text=dp_name)).first
                if not Util.check_dom_visibility(self.page, dataplane_selector, 2, 4):
                    Util.warning_screenshot(f"Dataplane {dp_name} is not found in product permission list.", self.page, "grant_product_permission_dp.png")
                    self._cancel_assign_permissions()
                    return GRANT_SKIPPED
                print("Dataplane " + dp_name + " matched by name fallback.")

            print("Dataplane " + dp_name + " is found in product permission list.")
            dataplane_selector.click()
            print("Clicked on dataplane " + dp_name)

            # The products list renders only while the row is expanded, so it is the
            # expansion oracle. The click above lands by bounding-box geometry; the real
            # (click) handler sits on .toggle-area, so only fall back to it while the row is
            # demonstrably collapsed - clicking it on an expanded row would collapse it.
            products_container = dataplane_selector.locator(".products-container")
            if not Util.check_dom_visibility(self.page, products_container, 1, 6):
                toggle_area = dataplane_selector.locator(".toggle-area")
                if toggle_area.count() > 0:
                    print("Dataplane " + dp_name + " row is still collapsed, clicking its toggle area.")
                    toggle_area.first.click()
                if not Util.check_dom_visibility(self.page, products_container, 1, 6):
                    Util.warning_screenshot(f"Dataplane {dp_name} row did not expand, cannot reach product {app_name}.", self.page, "grant_product_permission_expand.png")
                    self._cancel_assign_permissions()
                    return GRANT_SKIPPED

            app_selector = products_container.locator(".product-item", has_text=re.compile(rf"^\s*{re.escape(app_name)}\s*$")).first
            if not Util.check_dom_visibility(self.page, app_selector, 2, 4):
                app_selector = products_container.locator(".product-item", has_text=app_name).first
                if not Util.check_dom_visibility(self.page, app_selector, 2, 4):
                    ColorLogger.warning(f"Product '{app_name}' is NOT offered by this CP for dataplane {dp_name}; its capability cards will stay disabled. Skipping {permission} for {dp_name} => {app_name}.")
                    self._cancel_assign_permissions()
                    return GRANT_SKIPPED

            print("Product " + dp_name + " => " + app_name + " is found in product permission list.")

            wildcard_input = self.page.locator(".domain-selector-container .wildcard-domains-checkbox input[name='allDomainsSelected']")
            write_input = self.page.locator(".domains-table-container .pl-table__header input[name='allDomainsWriteSelected']")

            # Selecting a product fires GET /resource-instances-details, and only its
            # response tells the wizard about the existing domains and flips the wildcard
            # checkbox on for an existing grant. Until then aria-checked is already present
            # and reads "false" (there is no tri-state), so reading too early and clicking
            # would toggle an existing grant OFF and rewrite it as per-domain rows. Arm the
            # response wait before the click so every read below is on settled state.
            degraded_wildcard_on = None
            is_clicked = False
            try:
                with self.page.expect_response(lambda r: "/resource-instances-details" in r.url and r.request.method == "GET", timeout=30000):
                    app_selector.click()
                    is_clicked = True
                print("Clicked on product " + dp_name + " => " + app_name + ", domain details loaded.")
                # give Angular change detection time to render the loaded domains
                self.page.wait_for_timeout(500)
            except Exception as e:
                if is_clicked:
                    ColorLogger.warning(f"Domain details response was not observed after clicking {dp_name} => {app_name}: {e}")
                else:
                    ColorLogger.warning(f"Could not click product {dp_name} => {app_name}: {e}")
                    try:
                        app_selector.click()
                        print("Retried click on product " + dp_name + " => " + app_name)
                    except Exception as click_error:
                        ColorLogger.warning(f"Retry click on product {dp_name} => {app_name} also failed: {click_error}")
                # No response to key on: poll the wildcard instead, which both bounds the
                # wait and settles as soon as an existing grant renders.
                degraded_wildcard_on = Util.check_dom_attribute(self.page, wildcard_input, "aria-checked", "true", 1, 10)
                if not degraded_wildcard_on:
                    # Neither oracle answered, so the wizard state is UNKNOWN, not "not
                    # granted": aria-checked reads "false" both for a missing grant and for
                    # one whose XHR has not landed. setProductDomains subscribes
                    # unconditionally and settles the table on the error branch too, so a
                    # response that never arrives means the page is broken, not slow.
                    # Guessing here is what toggles a live grant off, so stay inert and let
                    # the caller re-enter a fresh wizard.
                    Util.warning_screenshot(f"Domain details never settled for {dp_name} => {app_name}, leaving the wizard untouched.", self.page, "grant_product_permission_unsettled.png")
                    self._cancel_assign_permissions()
                    return GRANT_FAILED

            is_wildcard_on = degraded_wildcard_on if degraded_wildcard_on is not None else Util.check_dom_attribute(self.page, wildcard_input, "aria-checked", "true", 1, 3)
            is_write_on = Util.check_dom_attribute(self.page, write_input, "aria-checked", "true", 1, 3) if is_wildcard_on else False
            print(f"All current and future domains: {is_wildcard_on}")
            print(f"Write permission: {is_write_on}")

            if is_wildcard_on and is_write_on:
                ColorLogger.success(f"{permission} for {dp_name} => {app_name} is already granted, nothing to update.")
                self._cancel_assign_permissions()
                return GRANT_ALREADY

            # setWildCardDomains() clears read/write on EVERY wildcard click, checked or
            # unchecked, so the wildcard must be converged BEFORE Write, never the reverse.
            if not is_wildcard_on:
                # The wildcard label text differs per capability ("All current and future
                # domains" for BW5/domain-based products, "...agents" for BW6). The checkbox
                # markup is otherwise identical, so match on the shared prefix to stay
                # capability-agnostic and avoid a strict-mode/timeout miss.
                wildcard_label = self.page.locator(".domain-selector-container .wildcard-domains-checkbox label", has_text="All current and future")
                # A dataplane with zero registered domains renders the other label variant
                # ("All future domains"/"...agents") instead; both share this for attribute.
                wildcard_future_label = self.page.locator(".domain-selector-container label[for^='domain-wildcard-selected-checkbox-']")
                wildcard_checkbox = self.page.locator(".domain-selector-container .wildcard-domains-checkbox")
                for attempt in range(1, 3):
                    if wildcard_label.count() > 0:
                        wildcard_label.first.click()
                        print("Clicked on 'All current and future' for " + dp_name + " => " + app_name)
                    elif wildcard_future_label.count() > 0:
                        wildcard_future_label.first.click()
                        print("Clicked on the wildcard domains label for " + dp_name + " => " + app_name)
                    else:
                        # the container owns the real (click) handler and it preventDefault()s,
                        # so this cannot double-toggle through the label's for-forwarding
                        wildcard_checkbox.first.click()
                        print("Clicked on the wildcard domains checkbox for " + dp_name + " => " + app_name)

                    is_wildcard_on = Util.check_dom_attribute(self.page, wildcard_input, "aria-checked", "true", 1, 3)
                    if is_wildcard_on:
                        break
                    ColorLogger.warning(f"Wildcard domains is still off after attempt {attempt}/2 for {dp_name} => {app_name}.")

            # Ticking Write also ticks Read (allReadPermissionsSelected follows
            # allWritePermissionsSelected), so there is nothing else to click for read access.
            if is_wildcard_on and not is_write_on:
                # Write stays [disabled] until the wildcard is on for a domain-less dataplane
                if Util.check_dom_enabled(self.page, write_input, 1, 6):
                    self.page.locator(".domains-table-container .pl-table__header label", has_text="Write").first.click()
                    print("Clicked on 'Write' permission for " + dp_name + " => " + app_name)
                    is_write_on = Util.check_dom_attribute(self.page, write_input, "aria-checked", "true", 1, 3)
                else:
                    ColorLogger.warning(f"'Write' permission checkbox stayed disabled for {dp_name} => {app_name}.")

            # Fail closed: nothing reaches the wire without 'Update', so a half-converged
            # wizard is harmless as long as it is never submitted. Re-read everything.
            is_wildcard_on = Util.check_dom_attribute(self.page, wildcard_input, "aria-checked", "true", 1, 3)
            is_write_on = Util.check_dom_attribute(self.page, write_input, "aria-checked", "true", 1, 3)
            granted_policies = self.page.locator(".policy-selector-container .green-check-icon").count()
            if not is_wildcard_on or not is_write_on or granted_policies < baseline_policies:
                Util.warning_screenshot(
                    f"Refusing to submit {permission} for {dp_name} => {app_name}: all domains={is_wildcard_on}, "
                    f"write={is_write_on}, granted policies={granted_policies} (was {baseline_policies}).",
                    self.page, "grant_product_permission_guard.png")
                self._cancel_assign_permissions()
                return GRANT_FAILED

            if self.page.locator("#next-assign-permissions").is_disabled():
                ColorLogger.success(f"{permission} for {dp_name} => {app_name} needs no update.")
                self._cancel_assign_permissions()
                return GRANT_ALREADY

            self.page.click("#next-assign-permissions")
            update_button = self.page.locator("#assign-permissions-update")
            if not Util.check_dom_visibility(self.page, update_button, 1, 6):
                Util.warning_screenshot(f"'Update' button did not appear on the preview step for {dp_name} => {app_name}.", self.page, "grant_product_permission_update.png")
                self._cancel_assign_permissions()
                return GRANT_FAILED

            update_button.click()

            # A denied grant persists nothing and leaves the wizard open with an error
            # toast, so success has to be proven: only a successful update routes the SPA to
            # add-user-finished, which destroys the wizard footer.
            is_granted = False
            for _ in range(30):
                if "/manage/add-user-finished" in self.page.url:
                    is_granted = True
                    break
                try:
                    # the wizard footer is destroyed together with the wizard on success
                    if self.page.locator("#cancel-assign-permissions").count() == 0:
                        is_granted = True
                        break
                except Exception as e:
                    # a DOM read during the route change must not be mistaken for a failure
                    print(f"Wizard footer is not readable yet: {e}")
                self.page.wait_for_timeout(500)

            if is_granted:
                ColorLogger.success(f"Granted {permission} to {ENV.DP_USER_EMAIL} for {dp_name} => {app_name}")
                return GRANT_DONE

            try:
                notification = self.page.locator(".pl-notification__message")
                if notification.count() > 0:
                    ColorLogger.warning(f"Wizard notification: {notification.first.inner_text().strip()}")
            except Exception as e:
                print(f"Could not read the wizard notification: {e}")

            Util.warning_screenshot(f"{permission} for {dp_name} => {app_name} was not applied, the wizard is still open.", self.page, "grant_product_permission_not_applied.png")
            self._cancel_assign_permissions()
            return GRANT_FAILED
        except Exception as e:
            Util.warning_screenshot(f"Unexpected error while granting {permission} for {dp_name} => {app_name}: {e}", self.page, "grant_product_permission_error.png")
            self._cancel_assign_permissions()
            return GRANT_FAILED

    def _cancel_assign_permissions(self):
        """Leave the Assign Permissions wizard without submitting anything.

        Only when the wizard is still mounted: after a successful update the SPA has
        already navigated away and the footer is gone, where a click would auto-wait for
        30 seconds and then throw.
        """
        try:
            cancel_button = self.page.locator("#cancel-assign-permissions")
            if cancel_button.count() > 0 and cancel_button.first.is_visible():
                cancel_button.first.click()
                print("Left the Assign Permissions page without updating.")
        except Exception as e:
            print(f"Could not leave the Assign Permissions page: {e}")
