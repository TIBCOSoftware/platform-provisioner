#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary

from utils.color_logger import ColorLogger
from utils.util import Util
from utils.env import ENV
from utils.report import ReportYaml

class PageObjectAuth:
    def __init__(self, page):
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
        if not email_selector.is_visible():
            print(f"No email '{email_title}' for active Admin user.")
            self.reactive_admin()
            print(f"Reactive Admin user '{ENV.CP_ADMIN_EMAIL}' after reset password.")
            return

        email_selector.wait_for(state="visible")
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
                self.reset_admin_password(new_page)
                ColorLogger.info("=== This is the new step to active admin in mail from CP 1.10.0. ===")
            else:
                Util.exit_error(f"Can not active Email for {email}", new_page, "active_user_in_mail_3.png")

        new_page.close()

    def reset_admin_password(self, new_page):
        ColorLogger.info("Reset admin password in new page...")
        self.page.wait_for_timeout(1000)
        if Util.check_dom_visibility(new_page, new_page.locator(".title", has_text="Reset Password"), 3, 6):
            new_page.fill("#passwordInput", ENV.CP_ADMIN_PASSWORD)
            new_page.fill("#confirmPasswordInput", ENV.CP_ADMIN_PASSWORD)
            new_page.locator("#ta-sign-in-button", has_text="Reset Password").click()
            print(f"Changed to new password: {ENV.CP_ADMIN_PASSWORD} and clicked 'Reset Password' button.")
        else:
            Util.exit_error("Reset Password page is not visible.", new_page, "active_user_in_mail_3.png")

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
            self.reset_admin_password(new_page)
            new_page.close()
        else:
            Util.exit_error("Other error occurred while reactive admin user, please check manually.", self.page, "reactive_admin.png")

        self.page.goto(ENV.TP_AUTO_ADMIN_URL)
        print(f"Finish reactive admin user, navigating to admin page {ENV.TP_AUTO_ADMIN_URL}...")

    def login_admin_user(self):
        ColorLogger.info("Login as admin user...")
        self.page.goto(ENV.TP_AUTO_ADMIN_URL)
        print(f"Navigating to admin page {ENV.TP_AUTO_ADMIN_URL}...")
        admin_login_btn_text = "Sign in with Default IdP"

        print(f"Wait for '{admin_login_btn_text}' button is visible and clickable...")
        if not Util.check_dom_visibility(self.page, self.page.locator("#ta-sign-in-button"), 3, 10, True):
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
        ReportYaml.set(".ENV.REPORT_TP_AUTO_ADMIN", True)
        return True

    def logout_admin_user(self):
        ColorLogger.info(f"Loging out admin user...")
        self.page.locator("#changeME-dropdown-label").click()
        self.page.locator(".pl-dropdown-menu .pl-dropdown-menu__link", has_text="Sign Out").click()
        self.page.locator(".pl-modal__container .pl-modal__footer button", has_text="Sign Out").click()
        print(f"Clicked Sign Out button, Admin user {ENV.CP_ADMIN_EMAIL} logout.")
        self.page.wait_for_timeout(1000)

    def admin_provision_user(self, email, host_prefix):
        ColorLogger.info(f"Provision user {email} with Host prefix: {host_prefix}...")
        self.login_admin_user()

        self.page.locator("#nav-bar-menu-list-subscriptions", has_text="Subscriptions").click()
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

    def login(self):
        ColorLogger.info(f"Navigating to login page {ENV.TP_AUTO_LOGIN_URL}...")
        self.page.goto(ENV.TP_AUTO_LOGIN_URL)
        print("Wait for login page is visible...")
        if not Util.check_dom_visibility(self.page, self.page.locator("#ta-sign-in-button"), 3, 10, True):
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

        print(f"Waiting for user profile...")
        if Util.check_dom_visibility(self.page, self.page.locator("#user-profile"), 3, 10, True):
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
        self.page.locator("#nav-bar-menu-list-signout").click()
        # Note: there are 3 buttons has "Sign Out" label, so we need to use nth(2) to click the last one
        self.page.locator("#confirm-button", has_text="Sign Out").nth(2).wait_for(state="visible")
        self.page.locator("#confirm-button", has_text="Sign Out").nth(2).click()
        ColorLogger.success(f"Clicked Sign Out button, User {ENV.DP_USER_EMAIL} logout.")
        self.page.wait_for_timeout(1000)
