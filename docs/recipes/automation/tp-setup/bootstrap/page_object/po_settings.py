#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary

import json, base64

from utils.color_logger import ColorLogger
from utils.env import ENV
from utils.helper import Helper
from utils.report import ReportYaml
from utils.util import Util

class PageObjectSettings:
    def __init__(self, page):
        self.page = page
        self.env = ENV

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
        token_row = self.page.locator("oauth-token table tr", has=self.page.locator("td:first-child", has_text=ENV.TP_AUTO_TOKEN_NAME))
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
            if self.page.locator("oauth-token table tr", has=self.page.locator("td:first-child", has_text=ENV.TP_AUTO_TOKEN_NAME)).is_visible():
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

        copy_token_dialog = self.page.locator(".pl-modal__container", has=self.page.locator('#copy-oauth2-token-btn'))
        copy_token_dialog.wait_for(state="visible")
        print("Dialog 'Copy OAuth Token' is visible")
        copy_token_dialog.locator("#view-token-btn").click()
        print("Clicked 'View' button to reveal the token")

        token_value = self.page.locator(".pl-modal__container .form-field", has=self.page.locator(".label", has_text="Access token")).locator(".value").text_content().strip()
        copy_token_dialog.locator("#close-oauth2-token-btn").click()
        print("Clicked 'Close' button on dialog")

        if not token_value:
            ColorLogger.error("Failed to get the OAuth token value from the dialog.")
            ReportYaml.set(".ENV.REPORT_OAUTH_TOKEN", False)
            return

        ColorLogger.info(f"Creating kubernetes secret '{ENV.TP_AUTO_TOKEN_NAME}' for OAuth token...")
        self.print_oauth_token_info(token_value)
        Helper.get_command_output(f"kubectl create secret generic {ENV.TP_AUTO_TOKEN_NAME} --from-literal=\"{ENV.TP_AUTO_TOKEN_NAME}={token_value}\" -n {ENV.TP_AUTO_TOKEN_NAMESPACE}", True)
        if self.is_created_oauth_token():
            ColorLogger.success(f"OAuth Token '{ENV.TP_AUTO_TOKEN_NAME}' is set in kubernetes successfully.")
            ReportYaml.set(".ENV.REPORT_OAUTH_TOKEN", True)
            if self.page.locator("oauth-token table tr", has=self.page.locator("td:first-child", has_text=ENV.TP_AUTO_TOKEN_NAME)).is_visible():
                ColorLogger.success(f"New OAuth Token '{ENV.TP_AUTO_TOKEN_NAME}' is created successfully.")
        else:
            ColorLogger.error(f"Failed to create kubernetes secret {ENV.TP_AUTO_TOKEN_NAME} in namespace {ENV.TP_AUTO_TOKEN_NAMESPACE}.")
            ReportYaml.set(".ENV.REPORT_OAUTH_TOKEN", False)
