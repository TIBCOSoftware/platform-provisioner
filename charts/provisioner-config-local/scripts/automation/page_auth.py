import sys
import time

from color_logger import ColorLogger
from util import Util
from env import EnvConfig

def active_user_in_mail(email, is_admin=False):
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
    try:
        response = page.goto(ENV.TP_AUTO_MAIL_URL, timeout=5000)
        if response and response.status == 200:
            print(f"URL {ENV.TP_AUTO_MAIL_URL} is accessible")
    except Exception as e:
        print(f"An error occurred while accessing {ENV.TP_AUTO_MAIL_URL}: {e}")
        sys.exit(f"Exiting program: An error occurred while accessing {ENV.TP_AUTO_MAIL_URL}")

    page.goto(ENV.TP_AUTO_MAIL_URL)
    print(f"Navigating to mail page {ENV.TP_AUTO_MAIL_URL}...")
    page.reload()

    email_selector = page.locator(".email-list .email-item-link", has_text=email_title).nth(0)
    email_selector.wait_for(state="visible")
    if not email_selector.locator(".title-subline", has_text=email).is_visible():
        ColorLogger.error(f"Active Email for {email} is not found.")
        sys.exit(f"Exiting program: Active Email for {email} is not found.")

    email_selector.click()
    page.wait_for_timeout(1000)
    iframe = page.frame_locator(".main-container iframe.preview-iframe").nth(0)
    iframe.locator("a.btn-activate", has_text="Sign in").wait_for(state="visible")

    with page.context.expect_page() as new_page_info:
        iframe.locator("a.btn-activate", has_text="Sign in").click()
        print("Clicked 'Sign in' button.")

    new_page = new_page_info.value
    print("New window detected and captured.")

    new_page.wait_for_load_state()
    page.wait_for_timeout(2000)

    if new_page.locator("#emailNameInput").is_visible():
        new_page.fill("#firstNameInput", first_name)
        new_page.fill("#lastNameInput", last_name)
        new_page.fill("#passwordInput", password)
        new_page.fill("#confirmPasswordInput", password)
        new_page.locator("#ta-sign-in-button").click()
        ColorLogger.success(f"User {email} has been active in new window completed.")
    else:
        print(f"User {email} may active.")

    new_page.close()

def login_admin_user():
    ColorLogger.info("Login as admin user...")
    page.goto(ENV.TP_AUTO_ADMIN_URL)
    print(f"Navigating to admin page {ENV.TP_AUTO_ADMIN_URL}...")

    page.locator("#ta-sign-in-button", has_text="Sign in with Default IdP").wait_for(state="visible")
    page.locator("#ta-sign-in-button", has_text="Sign in with Default IdP").click()
    print(f"Admin User {ENV.DP_USER_EMAIL} Clicked 'Sign in with Default IdP' button")

    print("Admin User logging in...")
    page.locator("#user-email").wait_for(state="visible")
    page.fill("#user-email", ENV.CP_ADMIN_EMAIL)
    page.fill("#usr-password", ENV.CP_ADMIN_PASSWORD)
    page.locator("#user-login-btn").click()
    print(f"Filled Admin User Email: {ENV.CP_ADMIN_EMAIL}, Password: {ENV.CP_ADMIN_PASSWORD}, then clicked 'Sign in' button")
    if page.locator("#toastr401", has_text="Invalid username or password").is_visible():
        ColorLogger.error(f"Admin user {ENV.CP_ADMIN_EMAIL}, {ENV.CP_ADMIN_PASSWORD} login failed.")
        return

    page.wait_for_timeout(1000)
    if page.locator("#ta-sign-in-button", has_text="Sign in with Default IdP").is_visible():
        page.locator("#ta-sign-in-button", has_text="Sign in with Default IdP").click()

    page.locator(".pcp-page-title", has_text="Welcome").wait_for(state="visible")
    ColorLogger.success(f"Admin user {ENV.CP_ADMIN_EMAIL} login successful.")

def logout_admin_user():
    ColorLogger.info(f"Loging out admin user...")
    page.locator("#changeME-dropdown-label", has_text="Admin Test").click()
    page.locator(".pl-dropdown-menu .pl-dropdown-menu__link", has_text="Sign Out").click()
    page.locator(".pl-modal__container .pl-modal__footer button", has_text="Sign Out").click()
    print(f"Clicked Sign Out button, Admin user {ENV.CP_ADMIN_EMAIL} logout.")
    page.wait_for_timeout(1000)

def admin_provision_user(email, host_prefix):
    ColorLogger.info(f"Provision user {email} with Host prefix: {host_prefix}...")
    login_admin_user()

    page.locator("#nav-bar-menu-list-subscriptions", has_text="Subscriptions").click()
    page.wait_for_timeout(200)
    if page.locator(".subscription-card-header .name", has_text=host_prefix).is_visible():
        ColorLogger.success(f"Subscription for {email} with Host prefix: {host_prefix} is already created.")
    else:
        first_name = email.split("@")[0]
        last_name = "Auto"
        country = "United States"
        state = "Texas"

        page.locator("button", has_text="Provision via Wizard").click()
        # step 1: User Details
        page.fill("#email", email)
        page.fill("#firstName", first_name)
        page.fill("#lastName", last_name)
        page.locator("input#country").click()
        page.locator("div#country .pl-select-menu li", has_text=country).nth(0).click()
        page.locator("input#state").click()
        page.locator("div#state .pl-select-menu li", has_text=state).click()
        page.locator(".footer button", has_text="Next").click()
        print(f"Filled User Details: {email}, {first_name}, {last_name}, {country}, {state}")

        # step 2: Subscriptions Details
        company_name = f"Tibco-{first_name}"
        page.fill("#companyName", company_name)
        page.fill("#hostPrefix", host_prefix)
        page.locator(".footer button", has_text="Next").click()
        print(f"Filled Subscriptions Details: {company_name}, {host_prefix}")

        # step 3: Preview
        page.locator(".footer button", has_text="Ok").wait_for(state="visible")
        page.locator(".footer button", has_text="Ok").click()
        print("Clicked 'Ok' button")
        if page.locator(".provision-success__subtext", has_text="host_prefix has been used in another account").is_visible():
            ColorLogger.error(f"Host prefix: {host_prefix} has been used in another account.")
            logout_admin_user()
            sys.exit(f"Exiting program: Host prefix: {host_prefix} has been used in another account, use another one or rest database.")
        ColorLogger.success(f"Provision user {email} successful.")

    logout_admin_user()
    ColorLogger.success(f"Admin user {ENV.CP_ADMIN_EMAIL} logout successful.")

def is_host_prefix_exist(host_prefix):
    ColorLogger.info(f"Checking if {host_prefix} is exist...")
    try:
        login(page)

        page.wait_for_timeout(500)
        print("Wait to see Welcome page...")
        if page.locator(".title", has_text="Welcome").is_visible():
            logout(page)
            ColorLogger.success(f"Host prefix {host_prefix} is already exist.")
            return True
        else:
            return False

    except Exception as e:
        print(f"An error occurred while accessing {ENV.TP_AUTO_LOGIN_URL}: {e}")
        ColorLogger.error(f"An error occurred while verify host prefix in {ENV.TP_AUTO_LOGIN_URL}: {ENV.DP_USER_EMAIL}, {ENV.DP_USER_PASSWORD}")
        return False

def is_admin_user_exist():
    ColorLogger.info(f"Checking if admin user {ENV.CP_ADMIN_EMAIL} is exist...")
    try:
        login_admin_user()
        print("Wait to see Admin Welcome page...")
        if page.locator(".pcp-page-title", has_text="Welcome").is_visible():
            logout_admin_user()
            return True
        else:
            return False
    except Exception as e:
        print(f"An error occurred while accessing {ENV.TP_AUTO_ADMIN_URL}: {e}")
        ColorLogger.error(f"An error occurred while verify admin user in {ENV.TP_AUTO_ADMIN_URL}: {ENV.CP_ADMIN_EMAIL}, {ENV.CP_ADMIN_PASSWORD}")
        return False

def login(page):
    ColorLogger.info(f"Navigating to login page {ENV.TP_AUTO_LOGIN_URL}...")
    page.goto(ENV.TP_AUTO_LOGIN_URL)
    if not Util.check_dom_visibility(page, page.locator("#ta-sign-in-button"), 5, 10, True):
        ColorLogger.error(f"Error: Unable to load login page {ENV.TP_AUTO_LOGIN_URL}")
        return

    print(f"Will click 'Sign in with Default IdP' button")
    page.locator("#ta-sign-in-button", has_text="Sign in with Default IdP").click()
    print(f"User {ENV.DP_USER_EMAIL} Clicked 'Sign in with Default IdP' button")

    print("User logging in...")
    page.fill("#user-email", ENV.DP_USER_EMAIL)
    page.fill("#usr-password", ENV.DP_USER_PASSWORD)
    page.click("#user-login-btn")
    print(f"Filled User Email: {ENV.DP_USER_EMAIL}, Password: {ENV.DP_USER_PASSWORD}, then clicked 'Sign in' button")
    if page.locator("#toastr401", has_text="Invalid username or password").is_visible():
        ColorLogger.error(f"User {ENV.DP_USER_EMAIL}, {ENV.DP_USER_PASSWORD} login {ENV.TP_AUTO_LOGIN_URL} failed.")
        return

    print(f"Waiting for user profile...")
    if Util.check_dom_visibility(page, page.locator("#user-profile"), 5, 10, True):
        page.wait_for_selector('#user-profile')
        print(f"User {ENV.DP_USER_EMAIL} profile is displayed...")
        ColorLogger.success("Login successful!")
        page.wait_for_timeout(1000)
    else:
        ColorLogger.warning(f"Login may successful, but user profile is not visible.")

def login_check(page):
    ColorLogger.info(f"Checking if user {ENV.DP_USER_EMAIL} is login...")
    try:
        if page.locator("#user-profile").is_visible():
            ColorLogger.success(f"User {ENV.DP_USER_EMAIL} is already login.")
        else:
            sys.exit(f"Exiting program: User {ENV.DP_USER_EMAIL} is not login.")
    except Exception as e:
        print(f"An error occurred while accessing {ENV.TP_AUTO_LOGIN_URL}: {e}")
        ColorLogger.error(f"An error occurred while verify login in {ENV.TP_AUTO_LOGIN_URL}: {ENV.DP_USER_EMAIL}, {ENV.DP_USER_PASSWORD}")
        sys.exit(f"Exiting program: An error occurred while verify login in {ENV.TP_AUTO_LOGIN_URL}")

def logout(page):
    ColorLogger.info(f"Logging out user {ENV.DP_USER_EMAIL}...")
    page.locator("#nav-bar-menu-list-signout").click()
    # Note: there are 3 buttons has "Sign Out" label, so we need to use nth(2) to click the last one
    page.locator("#confirm-button", has_text="Sign Out").nth(2).wait_for(state="visible")
    page.locator("#confirm-button", has_text="Sign Out").nth(2).click()
    ColorLogger.success(f"Clicked Sign Out button, User {ENV.DP_USER_EMAIL} logout.")
    page.wait_for_timeout(1000)

ENV = EnvConfig()
if __name__ == "__main__":
    ENV.pre_check()
    START_TIME = time.time()

    browser = Util.browser_launch(ENV.IS_HEADLESS)
    page = Util.browser_page(browser)

    if not is_host_prefix_exist(ENV.DP_HOST_PREFIX):
        if not is_admin_user_exist():
            active_user_in_mail(ENV.CP_ADMIN_EMAIL, True)
        admin_provision_user(ENV.DP_USER_EMAIL, ENV.DP_HOST_PREFIX)
        active_user_in_mail(ENV.DP_USER_EMAIL)

    Util.browser_close(browser)

    Util.print_env_info(ENV, True, False)
    END_TIME = time.time()
    ColorLogger.info(f"Page auth running time: {END_TIME - START_TIME:.2f} seconds")
