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

import json, base64, re

from utils.color_logger import ColorLogger
from utils.env import ENV
from utils.helper import Helper
from utils.report import ReportYaml
from utils.util import Util

class PageObjectSettings:
    def __init__(self, page):
        self.page = page
        self.env = ENV

    def _token_row_locator(self, token_name):
        # Match an OAuth token table row by its name cell. The name lives in the
        # <span id="token-name-{index}"> cell, which is present in BOTH the old
        # table layout (name in the first <td>) and the redesigned one (PCP-16529
        # added checkbox + type columns, moving the name to the 3rd <td>). Keying
        # on the #token-name- id (exact text) therefore works across CP versions,
        # unlike the previous `td:first-child` selector which silently matched
        # zero rows on the redesigned table (root cause of PCP-20425).
        return self.page.locator(
            "oauth-token table tr",
            has=self.page.locator("[id^='token-name-']",
                                  has_text=re.compile(rf"^{re.escape(token_name)}$")),
        )

    def _result_dialog_locator(self):
        # The success result modal that exposes the generated token.
        return self.page.locator(".pl-modal__container", has=self.page.locator('#copy-oauth2-token-btn'))

    def _error_notification_locator(self):
        # The CP error toast (e.g. "Invalid request: Duplicate AccessToken name.",
        # rate-limit) shown when token generation is rejected by the backend.
        return self.page.locator(".pl-notification--error .pl-notification__message")

    def _wait_for_generate_result(self, interval=2, max_wait=30):
        # After clicking Generate, either the success result modal appears, or an
        # error notification appears and the result modal never renders. Wait (with
        # Util.check_dom_visibility's logged polling, per the project's wait
        # convention) for EITHER to show, then report which, so a backend rejection
        # is surfaced as a clear, logged error instead of an opaque `wait_for`
        # timeout (PCP-20425). Returns a tuple:
        #   ("success", None) | ("error", "<message>") | ("timeout", None)
        #
        # NOTE: pass `.or_(...).first` — a bare `.or_()` raises a strict-mode
        # violation in check_dom_visibility's is_visible() when BOTH the success
        # modal and an error toast are present at once; `.first` narrows to one.
        appeared = Util.check_dom_visibility(
            self.page,
            self._result_dialog_locator().or_(self._error_notification_locator()).first,
            interval, max_wait,
        )
        if not appeared:
            return "timeout", None
        # Discriminate; success wins over a co-existing error toast.
        if self._result_dialog_locator().is_visible():
            return "success", None
        error_notification = self._error_notification_locator()
        if error_notification.count() > 0 and error_notification.first.is_visible():
            # text_content() may be None (empty/detached toast); coerce so a missing
            # message never crashes here and re-masks the backend error.
            return "error", (error_notification.first.text_content() or "").strip()
        return "timeout", None

    @staticmethod
    def delete_oauth_token():
        print(f"Delete kubectl secret '{ENV.TP_AUTO_TOKEN_NAME}' if exists...")
        Helper.get_command_output(f"kubectl delete secret {ENV.TP_AUTO_TOKEN_NAME} -n {ENV.TP_AUTO_TOKEN_NAMESPACE}", True)

    @staticmethod
    def print_oauth_token_info(token_value):
        print("-" * 50)
        print(f"{ENV.TP_AUTO_TOKEN_NAME}{":":5}{token_value}")
        print("-" * 50)

    def get_oauth_token(self):
        print(f"Check if kubectl secret '{ENV.TP_AUTO_TOKEN_NAME}' exists...")
        out = Helper.get_command_output(f"kubectl get secret {ENV.TP_AUTO_TOKEN_NAME} -n {ENV.TP_AUTO_TOKEN_NAMESPACE} -o json 2>/dev/null || echo ''", True).strip()
        if not out:
            return False

        try:
            secret = json.loads(out)
            data = secret.get("data", {})
            token_b64 = data.get(ENV.TP_AUTO_TOKEN_NAME, "")
            if not token_b64:
                print(f"Found base64 encoded token in secret, but it is empty after decoding, will delete '{ENV.TP_AUTO_TOKEN_NAME}' from kubernetes.")
                self.delete_oauth_token()
                return False
            token_value = base64.b64decode(token_b64).decode("utf-8").strip()
            if token_value == "********":
                # PCP-21482: a previously-stored masked placeholder is NOT a real
                # token. Treat it like empty — delete it so set_oauth_token's
                # idempotent early-exit doesn't keep reusing the poisoned value and
                # instead regenerates through the fixed (reveal-race-safe) path.
                print(f"Secret '{ENV.TP_AUTO_TOKEN_NAME}' holds a masked placeholder ('********'); deleting so it is regenerated.")
                self.delete_oauth_token()
                return False
            return token_value
        except Exception as e:
            ColorLogger.error(f"base64 decode token error: {e}")
            return False

    def is_created_oauth_token(self):
        return bool(self.get_oauth_token())

    def set_oauth_token(self):
        print("Start set OAuth Token...")
        self.page.click("#nav-bar-menu-item-settings")
        print("Clicked left navbar 'Settings' menu")
        self.page.click("#oauth-token-menu-item")
        print("Clicked 'OAuth Token' submenu")

        self.page.locator("#generate-token-btn").wait_for(state="visible")
        print("'OAuth Token' page is visible")
        self.page.wait_for_timeout(1000)
        token_row = self._token_row_locator(ENV.TP_AUTO_TOKEN_NAME)
        if token_row.is_visible():
            ColorLogger.success(f"OAuth Token '{ENV.TP_AUTO_TOKEN_NAME}' exists in table.")
            # check kubectl secret
            oath_token = self.get_oauth_token()
            if oath_token != False:
                self.print_oauth_token_info(oath_token)
                ColorLogger.success(f"Secret {ENV.TP_AUTO_TOKEN_NAME} OAuth Token is already set in kubernetes namespace {ENV.TP_AUTO_TOKEN_NAMESPACE}.")
                ReportYaml.set(".ENV.REPORT_OAUTH_TOKEN", True)
                return

            ColorLogger.warning(f"Secret '{ENV.TP_AUTO_TOKEN_NAME}' value is not stored in kubernetes, will re-generate it.")
            token_row.locator("button[id^='delete-token-btn-']").click()
            print(f"Clicked 'Delete' button for existing token '{ENV.TP_AUTO_TOKEN_NAME}'")
            delete_token_confirmation_dialog = self.page.locator(".pl-modal__container", has=self.page.locator('.pl-modal__heading', has_text="Delete OAuth token"))
            delete_token_confirmation_dialog.wait_for(state="visible")
            print("Dialog 'Delete OAuth token' is visible")
            delete_token_confirmation_dialog.locator("#confirm-button", has_text="Yes").click()
            print("Clicked 'Yes' button on confirmation dialog")
            Util.refresh_page(self.page)
            self.page.locator("#generate-token-btn").wait_for(state="visible")
            print("Refreshed page and 'OAuth Token' page is visible again")
            if self._token_row_locator(ENV.TP_AUTO_TOKEN_NAME).is_visible():
                ColorLogger.warning(f"Failed to delete existing OAuth Token '{ENV.TP_AUTO_TOKEN_NAME}'")
                ReportYaml.set(".ENV.REPORT_OAUTH_TOKEN", False)
                return
            else:
                ColorLogger.success(f"Existing OAuth Token '{ENV.TP_AUTO_TOKEN_NAME}' is deleted.")
        else:
            print(f"'{ENV.TP_AUTO_TOKEN_NAME}' does not exist, delete existing kubernetes secret if exists...")
            self.delete_oauth_token()

        print(f"Creating new OAuth Token '{ENV.TP_AUTO_TOKEN_NAME}'...")
        self.page.locator("#generate-token-btn").click()
        print("Clicked 'Generate OAuth Token' button")
        create_token_dialog = self.page.locator(".pl-modal__container", has=self.page.locator('.pl-modal__heading', has_text="Generate OAuth Token"))
        create_token_dialog.wait_for(state="visible")
        print("Dialog 'Generate OAuth Token' is visible")
        create_token_dialog.locator("#oauth-token-name").fill(ENV.TP_AUTO_TOKEN_NAME)
        print(f"Filled token name: {ENV.TP_AUTO_TOKEN_NAME}")
        create_token_dialog.locator("#oauth-token-duration").clear()
        create_token_dialog.locator("#oauth-token-duration").fill(ENV.TP_AUTO_TOKEN_DURATION)
        print(f"Filled token duration ({ENV.TP_AUTO_TOKEN_DURATION_UNIT}): {ENV.TP_AUTO_TOKEN_DURATION}")
        create_token_dialog.locator("#cp-select-period-dropdown").click()
        create_token_dialog.locator("#cp-select-period-dropdown-listbox").wait_for(state="visible")
        create_token_dialog.locator("#cp-select-period-dropdown-listbox li", has_text=ENV.TP_AUTO_TOKEN_DURATION_UNIT).click()
        print(f"Selected token duration unit: {ENV.TP_AUTO_TOKEN_DURATION_UNIT}")
        create_token_dialog.locator("#generate-oauth2-token-btn").click()
        print("Clicked 'Generate' button on dialog")

        # On success the result modal (#copy-oauth2-token-btn) renders; on a backend
        # rejection (e.g. "Invalid request: Duplicate AccessToken name.", rate limit)
        # an error notification is shown and the modal never appears. Detect both so
        # the real error surfaces in the log + a screenshot, instead of an opaque
        # `wait_for` timeout (PCP-20425).
        status, message = self._wait_for_generate_result()
        if status == "error":
            Util.warning_screenshot(f"OAuth Token generation was rejected by Control Plane: {message}", self.page, "oauth_token_generate_error")
            ColorLogger.error(f"Failed to generate OAuth Token '{ENV.TP_AUTO_TOKEN_NAME}': {message}")
            ReportYaml.set(".ENV.REPORT_OAUTH_TOKEN", False)
            return
        if status == "timeout":
            Util.warning_screenshot("OAuth Token result dialog did not appear and no error notification was shown.", self.page, "oauth_token_generate_timeout")
            ColorLogger.error(f"Failed to generate OAuth Token '{ENV.TP_AUTO_TOKEN_NAME}': result dialog not visible.")
            ReportYaml.set(".ENV.REPORT_OAUTH_TOKEN", False)
            return

        copy_token_dialog = self._result_dialog_locator()
        print("Dialog 'Copy OAuth Token' is visible")
        copy_token_dialog.locator("#view-token-btn").click()
        print("Clicked 'View' button to reveal the token")

        # PCP-21482: clicking "View" flips isTokenVisible, which the template renders
        # via *ngIf — swapping the masked "********" span for the real-token span. Under
        # Angular 21 (cp/web-ui, base 1.19.0-alpha.160+) that DOM swap is async, so
        # reading .value immediately races the re-render and returns "********" (an 8-byte
        # non-token). That masked value then gets stored in the auto-token secret, so every
        # downstream CLI/API call 401s (and the provision-tenant token-fetch yields a
        # 12-byte body). Wait for the reveal to complete before reading: #hide-token-btn
        # renders only once isTokenVisible=true, so its visibility is the "real token now
        # shown" signal.
        if not Util.check_dom_visibility(self.page, self.page.locator("#hide-token-btn"), 1, 15):
            Util.warning_screenshot("OAuth token did not reveal after clicking 'View' (field still masked).", self.page, "oauth_token_view_timeout")

        token_value = (self.page.locator(".pl-modal__container .form-field", has=self.page.locator(".label", has_text="Access token")).locator(".value").text_content() or "").strip()
        copy_token_dialog.locator("#close-oauth2-token-btn").click()
        print("Clicked 'Close' button on dialog")

        # Reject the masked placeholder as well as empty — storing "********" would poison
        # the auto-token secret and 401 every downstream call (PCP-21482).
        if not token_value or token_value == "********":
            ColorLogger.error("Failed to get the OAuth token value from the dialog (still masked).")
            ReportYaml.set(".ENV.REPORT_OAUTH_TOKEN", False)
            return

        ColorLogger.info(f"Creating kubernetes secret '{ENV.TP_AUTO_TOKEN_NAME}' for OAuth token...")
        self.print_oauth_token_info(token_value)
        print(f"Create namespace '{ENV.TP_AUTO_TOKEN_NAMESPACE}' if not exists...")
        Helper.get_command_output(f"kubectl get ns {ENV.TP_AUTO_TOKEN_NAMESPACE} >/dev/null 2>&1 || kubectl create ns {ENV.TP_AUTO_TOKEN_NAMESPACE}", True)
        print(f"Created secret generic '{ENV.TP_AUTO_TOKEN_NAME}' in namespace '{ENV.TP_AUTO_TOKEN_NAMESPACE}'")
        Helper.get_command_output(f"kubectl create secret generic {ENV.TP_AUTO_TOKEN_NAME} --from-literal=\"{ENV.TP_AUTO_TOKEN_NAME}={token_value}\" -n {ENV.TP_AUTO_TOKEN_NAMESPACE}", True)
        if self.is_created_oauth_token():
            ColorLogger.success(f"OAuth Token '{ENV.TP_AUTO_TOKEN_NAME}' is set in kubernetes successfully.")
            ReportYaml.set(".ENV.REPORT_OAUTH_TOKEN", True)
            ReportYaml.set(".ENV.REPORT_OAUTH_TOKEN_SECRET", f"{ENV.TP_AUTO_TOKEN_NAMESPACE}/{ENV.TP_AUTO_TOKEN_NAME}")
            if self._token_row_locator(ENV.TP_AUTO_TOKEN_NAME).is_visible():
                ColorLogger.success(f"New OAuth Token '{ENV.TP_AUTO_TOKEN_NAME}' is created successfully.")
        else:
            ColorLogger.error(f"Failed to create kubernetes secret {ENV.TP_AUTO_TOKEN_NAME} in namespace {ENV.TP_AUTO_TOKEN_NAMESPACE}.")
            ReportYaml.set(".ENV.REPORT_OAUTH_TOKEN", False)

    def set_mcp_server(self):
        print("Start set MCP Server...")
        self.page.locator("#nav-bar-menu-item-settings").click()
        print("Clicked left navbar 'Settings' menu")
        self.page.locator(".left-sub-menu ul.menu-items").wait_for(state="visible")
        print("'Sub-menu' page is visible")

        if Util.check_dom_visibility(self.page, self.page.locator("#mcp-servers-menu-item"), 2, 2):
            self.page.locator("#mcp-servers-menu-item").click()
            print("Clicked 'MCP Server' submenu")

            self.page.locator(".settings-mcp-servers").wait_for(state="visible")
            print("'MCP Server' page is visible")

            self.page.locator(".mcp-header-row .select-button", has_text="Select all").wait_for(state="visible")
            self.page.locator(".mcp-header-row .select-button", has_text="Select all").click()
            print("Clicked 'Select all' button to select all MCP servers")
            self.page.wait_for_timeout(1000)

            if self.page.locator(".settings-mcp-servers .mcp-footer button", has_text="Save").is_disabled():
                ColorLogger.info(f"'Save' button is disabled, no changes to save for MCP server settings.")
                ColorLogger.success(f"'MCP Server' has been enabled.")
                ReportYaml.set(".ENV.ENABLE_MCP_SERVER", True)
                return

            self.page.locator(".settings-mcp-servers .mcp-footer button", has_text="Save").click()
            print("Clicked 'Save' button to save MCP server settings")
            self.page.wait_for_timeout(1000)

            if self.page.locator(".pl-modal__heading", has_text="Update MCP Servers Configuration").is_visible():
                ColorLogger.success(f"'Update MCP Server' confirmation dialog is visible")
                self.page.locator(".pl-modal__container #confirm-button", has_text="Update").click()
                print("Clicked 'Update' button on confirmation dialog")

                if Util.check_dom_visibility(self.page, self.page.locator(".pl-notification__message", has_text="MCP servers updated successfully"), 2, 6):
                    ColorLogger.success(f"'MCP Server' settings are updated successfully.")
                    ReportYaml.set(".ENV.ENABLE_MCP_SERVER", True)
                else:
                    ColorLogger.warning(f"Failed to update MCP Server settings.")
            else:
                ColorLogger.warning(f"Failed to load 'MCP Server' page.")
        else:
            ColorLogger.warning(f"'MCP Server' submenu is not available in 'Settings' page.")
