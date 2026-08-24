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
import os

from page_object.po_global import PageObjectGlobal
from utils.color_logger import ColorLogger
from utils.helper import Helper
from utils.util import Util
from utils.env import ENV
from utils.report import ReportYaml

class PageObjectAuth(PageObjectGlobal):
    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.env = ENV

    def active_user_in_mail(self, email, is_admin=False):
        ColorLogger.info(f"Active user {email} in mail...")
        email_title = "Your TIBCO® Platform subscription has been activated"
        first_name = email.split("@")[0]
        last_name = "Auto"
        password = ENV.DP_USER_PASSWORD
        if is_admin:
            ColorLogger.warning(f"Admin user {ENV.CP_ADMIN_EMAIL} has not been active, active Admin in mail.")
            email_title = "Your TIBCO® Platform Console subscription has been activated"
            first_name = "Admin"
            last_name = "Test"
            password = ENV.CP_ADMIN_PASSWORD

        print("Check email and active user...")
        if not Util.check_page_url_accessible(self.page, ENV.TP_AUTO_MAIL_URL, "REPORT_TP_AUTO_MAIL"):
            Util.exit_error(f"Unable to access mail page {ENV.TP_AUTO_MAIL_URL}", self.page, "active_user_in_mail.png")

        self.page.goto(ENV.TP_AUTO_MAIL_URL)
        print(f"Navigating to mail page {ENV.TP_AUTO_MAIL_URL}...")
        Util.refresh_page(self.page)

        email_selector = self.page.locator(".email-list .email-item-link", has_text=email_title).nth(0)
        if not Util.check_dom_visibility(self.page, email_selector, interval=10, max_wait=60, is_refresh=True):
            if is_admin:
                print(f"No email '{email_title}' for active Admin user.")
                self.reactive_admin()
                print(f"Reactive Admin user '{ENV.CP_ADMIN_EMAIL}' after reset password.")
                return
            Util.exit_error(f"Active Email for {email} is not found.", self.page, "active_user_in_mail.png")
        print(f"Page {ENV.TP_AUTO_MAIL_URL} has been loaded...")
        if not email_selector.locator(".title-subline", has_text=email).is_visible():
            Util.exit_error(f"Active Email for {email} is not found.", self.page, "active_user_in_mail.png")

        email_selector.click()
        self.page.wait_for_timeout(1000)
        iframe = self.page.frame_locator(".main-container iframe.preview-iframe").nth(0)
        iframe.locator("a.btn-activate", has_text="Sign in").wait_for(state="visible")

        with self.page.context.expect_page() as new_page_info:
            iframe.locator("a.btn-activate", has_text="Sign in").click()
            print(f"Clicked 'Sign in' button from email title '{email_title}'.")

        new_page = new_page_info.value
        print("New window detected and captured.")

        new_page.wait_for_load_state()
        new_page.wait_for_timeout(5000)
        is_email_input_visible = Util.refresh_until_success(new_page,
                                                            new_page.locator("#emailNameInput"),
                                                            new_page.locator("#emailNameInput"),
                                                            "Email input is visible in 'Sign in' page.")

        if is_email_input_visible:
            new_page.fill("#firstNameInput", first_name)
            new_page.fill("#lastNameInput", last_name)
            new_page.fill("#passwordInput", password)
            new_page.fill("#confirmPasswordInput", password)
            new_page.locator("#ta-sign-in-button").click()
            ColorLogger.success(f"User {email} has been active in new window completed.")
        else:
            if new_page.locator("#ta-sign-in-button").is_visible():
                ColorLogger.info("=== This is the new step to active admin in mail from CP 1.10.0. ===")
                new_page.locator("#ta-sign-in-button").click()
                print("Clicked 'Sign in with Default IdP'.")
                # Temporary password for admin user from email
                temp_admin_password = "admin"
                new_page.fill("#user-email", ENV.CP_ADMIN_EMAIL)
                new_page.fill("#user-password", temp_admin_password)
                new_page.locator("#user-login-btn").click()
                print(f"Filled Admin User Email: {ENV.CP_ADMIN_EMAIL}, Password: {temp_admin_password}, then clicked 'Sign in' button")
                if not self.reset_password_on_first_login(new_page, ENV.CP_ADMIN_PASSWORD, label="admin"):
                    Util.exit_error("Reset Password page is not visible.", new_page, "active_user_in_mail_3.png")
                ColorLogger.info("=== This is the new step to active admin in mail from CP 1.10.0. ===")
            else:
                Util.exit_error(f"Can not active Email for {email}", new_page, "active_user_in_mail_3.png")

        new_page.close()

    @staticmethod
    def _reset_form_present(page):
        """True if the 'Reset Password' form (its two password fields) is on screen.
        This form appears on an account's FIRST login (forced reset) and on the
        email-based reset flow; the same #passwordInput/#confirmPasswordInput IDs are
        also reused by other flows (e.g. the email activation form in
        active_user_in_mail). It never shows on a normal username/password login, so
        this guard keeps the patient poll below from waiting on an ordinary login."""
        try:
            return (page.query_selector("#passwordInput") is not None
                    and page.query_selector("#confirmPasswordInput") is not None)
        except Exception:
            return False

    def reset_password_on_first_login(self, page, password, label="user"):
        """Handle the 'Reset Password' page CP shows on an account's FIRST login
        (admin via chart adminInitialPassword; DP user via API initialPassword) and on
        the email-based reset flow (the /forgot-password/reset URL opened from
        reactive_admin). Detected either by the reset form being present or by a
        /forgot-password/reset URL. The new password is set to the SAME value (e.g.
        Tibco@123 in / Tibco@123 out) so the credential stays stable, then submitted;
        CP redirects back to the /sso login form so the caller re-authenticates.

        The reset flow is SLOW (each redirect can take ~15s). Poll patiently for the
        reset form to appear instead of giving up after a few seconds — the previous
        short wait was why admin first-login resets were missed and login never reached
        the welcome page. Returns True if a reset was performed, False if it wasn't shown
        (already-active account). DOM: #passwordInput, #confirmPasswordInput,
        #ta-sign-in-button (text 'Reset Password', disabled until both pass the policy).
        """
        reset_present = self._reset_form_present(page)
        for _ in range(80):  # poll up to ~40s for the slow forced-reset redirect
            if reset_present:
                break
            try:
                url = page.url or ""
            except Exception:
                url = ""
            if "/forgot-password/reset" in url:
                reset_present = True
                break
            # Already authenticated (admin/DP user landed on its app) -> no reset needed.
            if "/admin/app" in url or "/cp/app" in url:
                return False
            page.wait_for_timeout(500)
            reset_present = self._reset_form_present(page)
        if not reset_present:
            return False
        page.fill("#passwordInput", password)
        page.fill("#confirmPasswordInput", password)
        Util.click_button_until_enabled(page, page.locator("#ta-sign-in-button", has_text="Reset Password"))
        print(f"Reset {label} password (reusing the same password) and clicked 'Reset Password' button.")
        # The reset redirects back to the /sso login form (slow) — wait for it so the
        # caller's re-login finds the form rather than a mid-redirect page.
        try:
            page.wait_for_selector("#user-email", state="visible", timeout=45000)
        except Exception:
            print(f"Login form (#user-email) did not appear within 45s after {label} reset; continuing.")
        return True

    def reactive_admin(self):
        ColorLogger.info("No email for active Admin user, start to reactive Admin.")
        self.page.goto(ENV.TP_AUTO_ADMIN_URL)
        print(f"Navigating to admin page {ENV.TP_AUTO_ADMIN_URL}...")
        admin_login_btn_text = "Sign in with Default IdP"
        Util.click_button_until_enabled(self.page, self.page.locator("#ta-sign-in-button", has_text=admin_login_btn_text))
        print(f"Clicked '{admin_login_btn_text}' button")
        self.page.wait_for_timeout(1000)
        Util.click_button_until_enabled(self.page, self.page.locator(".forgot-password"))
        print(f"Clicked 'Forgot password?' link button")
        self.page.wait_for_timeout(2000)
        self.page.locator(".reset-link-title", has_text="Forgot your password?").wait_for(state="visible")
        self.page.fill("#emailNameInput", ENV.CP_ADMIN_EMAIL)
        request_reset_link_btn_text = "Request Reset Link"
        Util.click_button_until_enabled(self.page, self.page.locator("#ta-sign-in-button", has_text=request_reset_link_btn_text))
        print(f"Fill '{ENV.CP_ADMIN_EMAIL}', then clicked '{request_reset_link_btn_text}' button")
        reset_error_description = "An email with subject TIBCO Platform password reset was already sent."
        if Util.check_dom_visibility(self.page, self.page.locator(".pl-notification__message", has_text=reset_error_description), 2, 6):
            ColorLogger.warning(f"Admin user {ENV.CP_ADMIN_EMAIL} reset password failed, {reset_error_description}")

        elif Util.check_dom_visibility(self.page, self.page.locator(".email-sent-title", has_text="Reset Password Email Sent"), 2, 4):
            ColorLogger.success(f"Reset Password Email Sent, check mail.")

        self.page.goto(ENV.TP_AUTO_MAIL_URL)
        print(f"Navigating to mail page {ENV.TP_AUTO_MAIL_URL}...")

        reset_password_email_title = "TIBCO Platform password reset"
        reset_password_email_selector = self.page.locator(".email-list .email-item-link", has_text=reset_password_email_title).nth(0)
        if reset_password_email_selector.is_visible():
            reset_password_email_selector.click()
            self.page.wait_for_timeout(1000)

            iframe = self.page.frame_locator(".main-container iframe.preview-iframe").nth(0)
            iframe.locator("a.btn-activate", has_text="Reset password").wait_for(state="visible")

            with self.page.context.expect_page() as new_page_info:
                iframe.locator("a.btn-activate", has_text="Reset password").click()
                print(f"Clicked 'Reset password' button from email title '{reset_password_email_title}'.")

            new_page = new_page_info.value
            if not self.reset_password_on_first_login(new_page, ENV.CP_ADMIN_PASSWORD, label="admin"):
                Util.exit_error("Reset Password page is not visible.", new_page, "active_user_in_mail_3.png")
            new_page.close()
        else:
            Util.exit_error("Other error occurred while reactive admin user, please check manually.", self.page, "reactive_admin.png")

        self.page.goto(ENV.TP_AUTO_ADMIN_URL)
        print(f"Finish reactive admin user, navigating to admin page {ENV.TP_AUTO_ADMIN_URL}...")

    def login_admin_user(self, _retry_after_reset=False):
        ColorLogger.info("Login as admin user...")
        self.page.goto(ENV.TP_AUTO_ADMIN_URL)
        print(f"Navigating to admin page {ENV.TP_AUTO_ADMIN_URL}...")
        admin_login_btn_text = "Sign in with Default IdP"

        print(f"Wait for '{admin_login_btn_text}' button is visible and clickable...")
        if not Util.check_dom_visibility(self.page, self.page.locator("#ta-sign-in-button"), 3, 9, True):
            ColorLogger.warning(f"Unable to load Admin login page {ENV.TP_AUTO_ADMIN_URL}")
            return False
        Util.click_button_until_enabled(self.page, self.page.locator("#ta-sign-in-button"))
        print(f"Admin User {ENV.DP_USER_EMAIL} Clicked '{admin_login_btn_text}' button")

        print("Admin User logging in...")
        self.page.locator("#user-email").wait_for(state="visible")
        self.page.fill("#user-email", ENV.CP_ADMIN_EMAIL)
        self.page.fill("#usr-password", ENV.CP_ADMIN_PASSWORD)
        self.page.locator("#user-login-btn").click()
        print(f"Filled Admin User Email: {ENV.CP_ADMIN_EMAIL}, Password: {ENV.CP_ADMIN_PASSWORD}, then clicked 'Sign in' button")
        if self.page.locator("#toastr401", has_text="Invalid username or password").is_visible():
            ColorLogger.warning(f"Admin user {ENV.CP_ADMIN_EMAIL}, {ENV.CP_ADMIN_PASSWORD} login failed.")
            return False

        # Handle the forced first-login password reset (used with chart adminInitialPassword).
        # Recurse once with the new password set; the guard prevents an infinite loop.
        if not _retry_after_reset and self.reset_password_on_first_login(self.page, ENV.CP_ADMIN_PASSWORD, label="admin"):
            self.page.wait_for_timeout(2000)
            return self.login_admin_user(_retry_after_reset=True)

        self.page.wait_for_timeout(1000)
        # Note: if the "Sign in with Default IdP" button is still visible, click it again
        # It is a bug when admin login path is "/admin/login"
        # If login path is "/admin", it will not show the "Sign in with Default IdP" button again
        if self.page.locator("#ta-sign-in-button").is_visible():
            print(f"Click '{admin_login_btn_text}' button again...")
            self.page.locator("#ta-sign-in-button").click()

        print(f"Waiting for admin {ENV.CP_ADMIN_EMAIL} welcome page.")
        if not Util.check_dom_visibility(self.page, self.page.locator(".pcp-page-title", has_text="Welcome"), 3, 6):
            ColorLogger.warning(f"Admin user {ENV.CP_ADMIN_EMAIL}, {ENV.CP_ADMIN_PASSWORD} login failed, did not see welcome page.")
            return False

        self.page.locator(".pcp-page-title", has_text="Welcome").wait_for(state="visible")
        ColorLogger.success(f"Admin user {ENV.CP_ADMIN_EMAIL} login successful.")
        ReportYaml.set(".ENV.REPORT_AUTO_ACTIVE_ADMIN", True)
        return True

    def logout_admin_user(self):
        ColorLogger.info(f"Loging out admin user...")
        self.page.locator("#changeME-dropdown-label", has_text="admin").click()
        self.page.locator(".pl-dropdown-menu .pl-dropdown-menu__link", has_text="Sign Out").click()
        self.page.locator(".pl-modal__container .pl-modal__footer button", has_text="Sign Out").click()
        print(f"Clicked Sign Out button, Admin user {ENV.CP_ADMIN_EMAIL} logout.")
        self.page.wait_for_timeout(1000)

    def admin_provision_user(self, email, host_prefix):
        ColorLogger.info(f"Provision user {email} with Host prefix: {host_prefix}...")
        self.login_admin_user()

        self.goto_left_navbar("Subscriptions")
        print("Clicked 'Subscriptions' left sidebar menu")
        self.page.wait_for_timeout(200)
        if self.page.locator(".subscription-card-header .name", has_text=host_prefix).is_visible():
            ColorLogger.success(f"Subscription for {email} with Host prefix: {host_prefix} is already created.")
        else:
            first_name = email.split("@")[0]
            last_name = "Auto"
            country = "United States"
            state = "Texas"

            self.page.locator("button", has_text="Provision via Wizard").click()
            print("Clicked 'Provision via Wizard' button")
            # step 1: User Details
            self.page.fill("#email", email)
            self.page.fill("#firstName", first_name)
            self.page.fill("#lastName", last_name)
            self.page.locator("input#country").click()
            self.page.locator(".pl-select-menu li", has_text=country).nth(0).click()
            self.page.wait_for_timeout(500)
            if not self.page.locator("input#state").input_value():
                self.page.locator("input#state").clear()
                self.page.locator("input#state").click()
                self.page.locator(".pl-select-menu li", has_text=state).click()
            self.page.locator(".footer button", has_text="Next").click()
            print(f"Filled User Details: {email}, {first_name}, {last_name}, {country}, {state}")

            # step 2: Subscriptions Details
            company_name = f"Tibco-{first_name}"
            self.page.fill("#companyName", company_name)
            self.page.fill("#hostPrefix", host_prefix)
            self.page.locator(".footer button", has_text="Next").click()
            print(f"Filled Subscriptions Details: {company_name}, {host_prefix}")

            # step 3: Preview
            self.page.locator(".footer button", has_text="Ok").wait_for(state="visible")
            self.page.locator(".footer button", has_text="Ok").click()
            self.page.wait_for_timeout(2000)
            print("Clicked 'Ok' button")
            if self.page.locator(".provision-success__subtext", has_text="host_prefix has been used in another account").is_visible():
                print("Error: host_prefix has been used in another account")
                self.page.locator(".provision-success__actions button", has_text="Cancel").wait_for(state="visible")
                self.page.locator(".provision-success__actions button", has_text="Cancel").click()
                print("Clicked 'Cancel' button")
                Util.screenshot_page(self.page, "admin-provision-user.png")
                self.logout_admin_user()
                Util.warning_screenshot(f"Host prefix: {host_prefix} has been used in another account, use another one or rest database.")
                return
            ColorLogger.success(f"Provision user {email} successful.")

        self.logout_admin_user()
        ColorLogger.success(f"Admin user {ENV.CP_ADMIN_EMAIL} logout successful.")

    def admin_provision_user_via_api(self, email, host_prefix, password):
        """Provision a regular TP subscription via the Console API.
        Uses the admin browser session cookie for auth — admin must be logged in.
        Endpoint: POST https://admin.<DOMAIN>/platform-console/api/v1/subscriptions

        Always sets `generateIAT=true` and persists the IAT + subscription URL to
        k8s secret `cp-iat` (namespace `automation`). The IAT is cheap (24h TTL,
        single-bootstrap-use) and harmless to GUI flows that ignore it; downstream
        API/CLI flows use it to register a long-lived OAuth2 client via
        /idm/v1/oauth2/clients without ever opening a browser.

        CP >= 1.18 still falls back to maildev activation because initialPassword
        no longer registers the user in the IdP. On CP <= 1.17, initialPassword
        also works for direct login.
        """
        ColorLogger.info(f"Provision user {email} (host_prefix={host_prefix}) via Console API...")
        if not self.login_admin_user():
            Util.exit_error("Admin login failed before API provisioning",
                            self.page, "api-provision-login.png")

        api_url = f"https://admin.{ENV.TP_AUTO_CP_SERVICE_DNS_DOMAIN}/platform-console/api/v1/subscriptions"
        first_name = email.split("@")[0]
        payload = {
            "userDetails": {
                "firstName": first_name,
                "lastName": "Auto",
                "email": email,
                "initialPassword": password,
                "country": "US",
                "state": "TX",
            },
            "accountDetails": {
                "companyName": f"Tibco-{first_name}",
                "ownerLimit": 10,
                "hostPrefix": host_prefix,
                "comment": "Provisioned by automation via Console API (no email)",
            },
            "generateIAT": True,
            "copyAdminIdP": False,
            "userRoles": ["*"],
            "useDefaultIDP": True,
            "customContainerRegistry": False,
        }
        resp = self.page.context.request.post(
            api_url,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )
        body = resp.text()[:4000]
        # CP returns HTTP 200 even for application errors (status:"error" in body),
        # so HTTP code alone is not enough — must also check the parsed body.
        try:
            parsed = json.loads(body)
        except ValueError:
            parsed = {}
        if resp.status in (200, 201) and parsed.get("status") != "error":
            ColorLogger.success(f"Provisioned {email} via API (subscription created).")
            self._persist_iat_from_response(parsed, host_prefix)
        elif "already exists" in body.lower() or "duplicate" in body.lower():
            ColorLogger.warning(f"Subscription for {host_prefix} already exists — continuing.")
        else:
            Util.exit_error(f"API provisioning failed status={resp.status} body={body}",
                            self.page, "api-provision.png")
        self.logout_admin_user()

    @staticmethod
    def _persist_iat_from_response(parsed, host_prefix):
        """Extract IAT + subscription URL from subscription response and store
        in k8s secret `cp-iat` (namespace TP_AUTO_TOKEN_NAMESPACE). Idempotent."""
        try:
            inner = parsed.get("response", {})
            iat = inner.get("iat", {}).get("accessToken")
            sub_url = inner.get("details", {}).get("provisioningDetails", {}).get("subscriptionUrl") or ""
        except AttributeError:
            iat, sub_url = None, ""
        if not iat:
            ColorLogger.warning("generateIAT=True but no IAT found in response; downstream CLI bootstrap will fail")
            return
        if sub_url and not sub_url.startswith("http"):
            sub_url = f"https://{sub_url}"
        ns = ENV.TP_AUTO_TOKEN_NAMESPACE
        Helper.get_command_output(f"kubectl create namespace {ns} 2>/dev/null || true")
        Helper.get_command_output(f"kubectl delete secret cp-iat -n {ns} 2>/dev/null || true")
        Helper.get_command_output(
            f"kubectl create secret generic cp-iat -n {ns} "
            f"--from-literal=iat='{iat}' --from-literal=subscription-url='{sub_url}' "
            f"--from-literal=host-prefix='{host_prefix}'"
        )
        ColorLogger.success(f"IAT stored in secret {ns}/cp-iat (sub_url={sub_url})")

    def is_host_prefix_exist(self, host_prefix):
        ColorLogger.info(f"Checking if host_prefix: {host_prefix} is exist...")
        try:
            if not self.login():
                return False

            print("Wait to see Welcome page...")
            self.page.wait_for_timeout(500)
            if self.page.locator(".title", has_text="Welcome").is_visible():
                self.logout()
                ColorLogger.success(f"Host prefix {host_prefix} is already exist.")
                return True
            else:
                return False

        except Exception as e:
            ColorLogger.warning(f"An error occurred while accessing: {e}")
            ColorLogger.warning(f"An error occurred while verify host prefix in {ENV.TP_AUTO_LOGIN_URL}: {ENV.DP_USER_EMAIL}, {ENV.DP_USER_PASSWORD}")
            return False

    def is_admin_user_exist(self):
        ColorLogger.info(f"Checking if admin user {ENV.CP_ADMIN_EMAIL} is exist...")
        try:
            if not self.login_admin_user():
                return False

            print("Wait to see Admin Welcome page...")
            self.page.wait_for_timeout(500)
            if self.page.locator(".pcp-page-title", has_text="Welcome").is_visible():
                self.logout_admin_user()
                return True
            else:
                return False
        except Exception as e:
            ColorLogger.warning(f"An error occurred while accessing: {e}")
            ColorLogger.warning(f"An error occurred while verify admin user in {ENV.TP_AUTO_ADMIN_URL}: {ENV.CP_ADMIN_EMAIL}, {ENV.CP_ADMIN_PASSWORD}")
            return False

    def login(self, _retry_after_reset=False):
        ColorLogger.info(f"Navigating to login page {ENV.TP_AUTO_LOGIN_URL}...")
        self.page.goto(ENV.TP_AUTO_LOGIN_URL)
        print("Wait for login page is visible...")
        if not Util.check_dom_visibility(self.page, self.page.locator("#ta-sign-in-button"), 3, 9, True):
            ColorLogger.warning(f"Unable to load login page {ENV.TP_AUTO_LOGIN_URL}")
            return False

        print("Login page loaded, Wait for 'Sign in with ...' button is visible and clickable...")
        Util.click_button_until_enabled(self.page, self.page.locator("#ta-sign-in-button"))
        print(f"User {ENV.DP_USER_EMAIL} Clicked 'Sign in with ...' button")

        print("User logging in...")
        self.page.fill("#user-email", ENV.DP_USER_EMAIL)
        self.page.fill("#usr-password", ENV.DP_USER_PASSWORD)
        self.page.click("#user-login-btn")
        print(f"Filled User Email: {ENV.DP_USER_EMAIL}, Password: {ENV.DP_USER_PASSWORD}, then clicked 'Sign in' button")
        if self.page.locator("#toastr401", has_text="Invalid username or password").is_visible():
            ColorLogger.warning(f"User {ENV.DP_USER_EMAIL}, {ENV.DP_USER_PASSWORD} login {ENV.TP_AUTO_LOGIN_URL} failed.")
            return False

        # Handle the forced first-login password reset (used with API initialPassword).
        # Recurse once with the new password set; the guard prevents an infinite loop.
        if not _retry_after_reset and self.reset_password_on_first_login(self.page, ENV.DP_USER_PASSWORD, label=ENV.DP_USER_EMAIL):
            self.page.wait_for_timeout(2000)
            return self.login(_retry_after_reset=True)

        print(f"Waiting for user profile...")
        if Util.check_dom_visibility(self.page, self.page.locator("#user-profile"), 3, 9, True):
            self.page.wait_for_selector('#user-profile')
            print(f"User {ENV.DP_USER_EMAIL} profile is displayed...")
            ReportYaml.set(".ENV.REPORT_AUTO_ACTIVE_USER", True)
            ColorLogger.success("Login successful!")
            self.page.wait_for_timeout(1000)
        else:
            ColorLogger.warning(f"Login may successful, but user profile is not visible.")
        return True

    def login_check(self):
        ColorLogger.info(f"Checking if user {ENV.DP_USER_EMAIL} is login...")
        try:
            if self.page.locator("#user-profile").is_visible():
                ColorLogger.success(f"User {ENV.DP_USER_EMAIL} is already login.")
            else:
                Util.exit_error(f"User {ENV.DP_USER_EMAIL} is not login.", self.page, "login_check.png")
        except Exception as e:
            print(f"An error occurred while accessing {ENV.TP_AUTO_LOGIN_URL}: {e}")
            Util.exit_error(f"An error occurred while verify login in {ENV.TP_AUTO_LOGIN_URL}: {ENV.DP_USER_EMAIL}, {ENV.DP_USER_PASSWORD}", self.page, "login_check_e.png")

    def logout(self):
        ColorLogger.info(f"Logging out user {ENV.DP_USER_EMAIL}...")
        # Logout is a best-effort TEARDOWN: every case calls it LAST, after its real work has
        # already succeeded, so a logout failure must NEVER abort the run — turning a green case
        # RED and triggering full re-deploy retries (PCP-20999). It must also be robust to WHERE
        # the flow ended: post-#372 the MCP Hub deploy ends on the gateway detail MFE
        # (/cp/mcphub/gateways/{id}), whose React view/overlay leaves the CP-shell left-nav
        # "Sign Out" present-but-unclickable (a 30s Locator.click timeout that used to crash the
        # case). So first re-navigate to the CP entry: when a session exists this re-mounts the
        # shell + left-nav and drops any lingering MFE dialog/overlay (if it instead shows the
        # login form, the poll below simply warn-returns — the non-fatal wrapper, not the
        # redirect, is the guarantee). The nav interaction is INLINED (not via goto_left_navbar)
        # so no Util.exit_error/SystemExit is reachable here, and the whole body — re-nav
        # included — is wrapped so ANY failure warns instead of aborting the caller.
        try:
            self.page.goto(ENV.TP_AUTO_LOGIN_URL, wait_until="domcontentloaded")
            self.page.wait_for_timeout(1000)
            if not Util.check_dom_visibility(self.page, self.page.locator(".nav-bar-pointer", has_text="Sign Out"), 3, 30):
                Util.warning_screenshot(
                    f"'Sign Out' left-nav not reachable; skipping logout for {ENV.DP_USER_EMAIL} (non-fatal teardown).",
                    self.page, "logout.png")
                return
            self.page.locator(".nav-bar-pointer", has_text="Sign Out").click()
            self.page.wait_for_timeout(500)
            self.page.locator(".nav-bar-display-block #confirm-button", has_text="Sign Out").wait_for(state="visible")
            self.page.locator(".nav-bar-display-block #confirm-button", has_text="Sign Out").click()
            ColorLogger.success(f"Clicked Sign Out button, User {ENV.DP_USER_EMAIL} logout.")
            self.page.wait_for_timeout(1000)
        except Exception as e:
            Util.warning_screenshot(
                f"Logout did not complete for {ENV.DP_USER_EMAIL} (non-fatal teardown): {e}",
                self.page, "logout.png")
