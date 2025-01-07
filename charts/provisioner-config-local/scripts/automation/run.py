import os
import sys
import time

from color_logger import ColorLogger
from util import Util
from env import EnvConfig

def check_dom_visibility(dom_selector, interval=10, max_wait=180, is_refresh=False):
    total_attempts = max_wait // interval
    timeout = interval if interval < 5 else 5
    print(f"Check dom visibility, wait {timeout} seconds first, then loop to check")
    page.wait_for_timeout(timeout * 1000)
    for attempt in range(total_attempts):
        if dom_selector.is_visible():
            print("Dom is now visible.")
            return True

        print(f"Loop to check, Attempt {attempt + 1}/{total_attempts}: Checking if dom is visible...")
        if attempt < total_attempts - 1:
            if is_refresh:
                print(f"Page reload {attempt + 1}")
                page.reload()
            print(f"Dom not visible. Waiting for {interval} seconds before retrying...")
            page.wait_for_timeout(interval * 1000)

    ColorLogger.error(f"Error: Dom is still not visible after waiting for {max_wait} seconds.")
    return False

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
    page.locator("#user-email").wait_for(state="visible")
    page.fill("#user-email", ENV.CP_ADMIN_EMAIL)
    page.fill("#usr-password", ENV.CP_ADMIN_PASSWORD)
    page.locator("#user-login-btn").click()
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
        login()

        page.wait_for_timeout(500)
        print("Wait to see Welcome page...")
        if page.locator(".title", has_text="Welcome").is_visible():
            logout()
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

def login():
    ColorLogger.info(f"Navigating to login page {ENV.TP_AUTO_LOGIN_URL}...")
    page.goto(ENV.TP_AUTO_LOGIN_URL)
    page.wait_for_timeout(1000)
    if not check_dom_visibility(page.locator("#ta-sign-in-button"), 3, 20, True):
        ColorLogger.error(f"Error: Unable to load login page {ENV.TP_AUTO_LOGIN_URL}")
        return
    page.locator("#ta-sign-in-button", has_text="Sign in with Default IdP").click()

    print("Logging in...")
    page.fill("#user-email", ENV.DP_USER_EMAIL)
    page.fill("#usr-password", ENV.DP_USER_PASSWORD)
    page.click("#user-login-btn")
    if page.locator("#toastr401", has_text="Invalid username or password").is_visible():
        ColorLogger.error(f"User {ENV.DP_USER_EMAIL}, {ENV.DP_USER_PASSWORD} login {ENV.TP_AUTO_LOGIN_URL} failed.")
        return

    if check_dom_visibility(page.locator("#user-profile"), 3, 15, True):
        page.wait_for_selector('#user-profile')
        ColorLogger.success("Login successful!")
        page.wait_for_timeout(1000)
    else:
        ColorLogger.warning(f"Login may successful, but user profile is not visible.")

def logout():
    ColorLogger.info(f"Logging out user {ENV.DP_USER_EMAIL}...")
    page.locator("#nav-bar-menu-list-signout").click()
    # Note: there are 3 buttons has "Sign Out" label, so we need to use nth(2) to click the last one
    page.locator("#confirm-button", has_text="Sign Out").nth(2).wait_for(state="visible")
    page.locator("#confirm-button", has_text="Sign Out").nth(2).click()
    ColorLogger.success(f"Clicked Sign Out button, User {ENV.DP_USER_EMAIL} logout.")
    page.wait_for_timeout(1000)

def grant_permission(permission):
    ColorLogger.info(f"Granting permission for {permission}...")
    page.locator(".policy-description", has_text=permission).click()
    # check if input aria-checked="true" does not exist, then click
    is_selected = page.locator('.dp-selector-container input').get_attribute("aria-checked")
    print(f"Permission {permission} is selected: {is_selected}")
    if is_selected != "true":
        page.locator('.dp-selector-container label').click()
        print("Grant permission for " + permission)

def set_user_permission():
    ColorLogger.info("Setting user permission...")
    page.locator("#nav-bar-menu-list-dataPlanes").wait_for(state="visible")
    page.click("#nav-bar-menu-list-dataPlanes")
    page.locator("#register-dp-button").wait_for(state="visible")
    print("Checking if user has permission...")
    if not page.locator("#register-dp-button").is_disabled():
        ColorLogger.success(f"User {ENV.DP_USER_EMAIL} already has all permissions.")
        return

    print("Start set user permission...")
    page.click("#nav-bar-menu-item-usrMgmt")
    page.click("#users-menu-item")
    page.wait_for_selector(f'.user-name-text[id="go-to-user-details-{ENV.DP_USER_EMAIL}"]')
    print(f"{ENV.DP_USER_EMAIL} is found.")
    # check if user has all permissions
    page.locator(f'.user-name-text[id="go-to-user-details-{ENV.DP_USER_EMAIL}"]').click()
    page.wait_for_timeout(1000)
    print(f"Assign Permissions for {ENV.DP_USER_EMAIL}")
    # if table.permissions has 8 rows, then exit this function
    if page.locator("table.permissions .pl-table__row").count() == 8:
        ColorLogger.success(f"User {ENV.DP_USER_EMAIL} already has all permissions.")
        return

    page.click("#assign-permissions-btn")

    grant_permission("IdP Manager")
    grant_permission("Team Admin")
    grant_permission("Data plane Manager")
    grant_permission("Capability Manager")
    grant_permission("Application Manager")
    grant_permission("Application Viewer")
    grant_permission("View permissions")
    # if button is not disabled, then click
    if not page.locator("#next-assign-permissions").is_disabled():
        page.click("#next-assign-permissions")
        page.click("#assign-permissions-update")
        ColorLogger.success(f"Grant All permission to {ENV.DP_USER_EMAIL}")
    else:
        ColorLogger.success(f"User {ENV.DP_USER_EMAIL} already has all permissions.")

def k8s_create_dataplane(dp_name):
    ColorLogger.info(f"Creating k8s Data Plane '{dp_name}'...")

    if page.locator(".data-plane-name").count() > ENV.TP_AUTO_MAX_DATA_PLANE:
        ColorLogger.error("Too many data planes, please delete some data planes first.")
        sys.exit("Exiting program: Too many data planes, please delete some data planes first.")

    if page.locator('.data-plane-name', has_text=dp_name).is_visible():
        ColorLogger.success(f"DataPlane '{dp_name}' is already created.")
        return

    page.click("#register-dp-button")
    page.click("#select-existing-dp-button")
    # step 1 Basic
    page.fill("#data-plane-name-text-input", dp_name)
    print(f"Input Data Plane Name: {dp_name}")
    page.locator('label[for="eua-checkbox"]').click()
    page.click("#data-plane-basics-btn")
    print("Finish step 1 Basic")

    # step 2 Namespace & Service account
    page.fill("#namespace-text-input", ENV.TP_AUTO_K8S_DP_NAMESPACE)
    print(f"Input NameSpace: {ENV.TP_AUTO_K8S_DP_NAMESPACE}")
    page.fill("#service-account-text-input", ENV.TP_AUTO_K8S_DP_SERVICE_ACCOUNT)
    print(f"Input Service Account: {ENV.TP_AUTO_K8S_DP_SERVICE_ACCOUNT}")
    page.click("#data-plane-namespace-btn")
    print("Finish step 2 Namespace & Service account")

    # step 3 Configuration
    if page.locator('label[for="helm-chart-repo-global"]').is_visible():
        if ENV.GITHUB_TOKEN == "":
            print("GITHUB_TOKEN is empty, choose 'Global Repository'")
            page.locator('label[for="helm-chart-repo-global"]').click()
        else:
            print("GITHUB_TOKEN is set, choose 'Custom Helm Chart Repository'")
            page.locator('label[for="helm-chart-repo-custom"]').click()

            page.fill("#alias-input", f"tp-private-{dp_name}")
            page.fill("#url-input", "https://raw.githubusercontent.com")
            page.fill("#repo-input", "tibco/tp-helm-charts/gh-pages")
            page.fill("#username-input", "cp-test")
            page.fill("#password-input", ENV.GITHUB_TOKEN)

    page.click("#data-plane-config-btn")
    print("Finish step 3 Configuration")

    # step Preview (for 1.4 and above)
    if page.locator("#data-plane-preview-btn").is_visible():
        page.click("#data-plane-preview-btn")
        print("Finish step 4 Preview")

    # step Register Data Plane
    page.wait_for_selector("#data-plane-finished-btn")

    if ENV.TP_AUTO_CP_VERSION == "1.3":
        k8s_run_dataplane_command(dp_name, "Namespace creation", page.locator(".namespace #download-commands"), 1)
        k8s_run_dataplane_command(dp_name, "Service Account creation", page.locator(".service-account #download-commands"), 2)
        k8s_run_dataplane_command(dp_name, "Cluster Registration", page.locator(".cluster #download-commands"), 3)
    else:
        k8s_run_dataplane_command(dp_name, "Helm Repository configuration", page.locator(".cluster #download-commands").nth(0), 1)
        k8s_run_dataplane_command(dp_name, "Namespace creation", page.locator(".namespace #download-commands"), 2)
        k8s_run_dataplane_command(dp_name, "Service Account creation", page.locator(".service-account #download-commands"), 3)
        k8s_run_dataplane_command(dp_name, "Cluster Registration", page.locator(".cluster #download-commands").nth(1), 4)

    # click Done button
    page.click("#data-plane-finished-btn")
    print("Clicked 'Done' button")
    page.locator('#confirm-button', has_text="Yes").wait_for(state="visible")
    page.locator('#confirm-button', has_text="Yes").click()

    # verify data plane is created in the list
    print(f"Verify Data Plane {dp_name} is created in the list")
    goto_left_navbar("Data Planes")
    print(f"Navigated to Data Planes list page, and wait for {dp_name} is created.")
    page.wait_for_timeout(2000)
    page.locator('.data-plane-name', has_text=dp_name).wait_for(state="visible")
    ColorLogger.success(f"DataPlane {dp_name} is created.")

def k8s_run_dataplane_command(dp_name, step_name, download_selector, step):
    ColorLogger.info(f"Running command for: {step_name}")
    print(f"Download: {step_name}")
    with page.expect_download() as download_info:
        download_selector.click()

    file_name = f"{dp_name}_{step}.sh"
    file_path = Util.download_file(download_info.value, file_name)

    print(f"Run command for: {step_name}")
    Util.run_shell_file(file_path)
    print(f"Command for step: {step_name} is executed, wait for 3 seconds.")
    page.wait_for_timeout(3000)

def goto_left_navbar(item_name):
    ColorLogger.info(f"Going to left side menu ...")
    page.locator(".nav-bar-pointer", has_text=item_name).wait_for(state="visible")
    page.locator(".nav-bar-pointer", has_text=item_name).click()
    print(f"Clicked left side menu '{item_name}'")
    page.wait_for_timeout(500)

def goto_global_dataplane():
    ColorLogger.info(f"Going to Global Data Plane...")
    page.click("#nav-bar-menu-list-dataPlanes")
    # wait for 1 seconds
    page.wait_for_timeout(1000)

    page.locator(".global-configuration button").click()
    print("Clicked 'Global configuration' button")
    page.locator('.global-configuration breadcrumbs a', has_text="Global configuration").wait_for(state="visible")
    print(f"Navigated to Global Data Plane page")

def goto_dataplane(dp_name):
    ColorLogger.info(f"Going to k8s Data Plane '{dp_name}'...")
    page.click("#nav-bar-menu-list-dataPlanes")
    page.wait_for_timeout(2000)

    if not page.locator('.data-plane-name', has_text=dp_name).is_visible():
        ColorLogger.error(f"DataPlane {dp_name} does not exist")
        sys.exit(f"Exiting program: DataPlane {dp_name} does not exist")

    page.locator('data-plane-card', has=page.locator('.data-plane-name', has_text=dp_name)).locator('button', has_text="Go to Data Plane").click()
    print("Clicked 'Go to Data Plane' button")
    page.wait_for_timeout(2000)
    page.locator('.domain-data-title', has_text=dp_name).wait_for(state="visible")
    print(f"Navigated to Data Plane '{dp_name}' page")
    page.wait_for_timeout(1000)

def goto_dataplane_config():
    ColorLogger.info(f"Going to Data plane Configuration page...")
    page.locator("#ct-dp-config-link").wait_for(state="visible")
    page.locator("#ct-dp-config-link").click()
    print("Clicked 'Data Plane configuration' button")
    page.wait_for_timeout(500)

def goto_dataplane_config_sub_menu(sub_menu_name = ""):
    ColorLogger.info(f"Going to Data plane config -> '{sub_menu_name}' side menu")
    page.locator("#left-sub-menu .menu-item-text", has_text=sub_menu_name).click()
    print(f"Clicked '{sub_menu_name}' left side menu")
    page.wait_for_timeout(500)

def goto_dataplane_config_o11y_sub(menu_name):
    ColorLogger.info(f"Going to Data plane config -> o11y -> '{menu_name}' side menu")
    menu_dom_selector = "#left-sub-menu li a"
    page.locator(menu_dom_selector, has_text=menu_name).wait_for(state="visible")
    if not page.locator(menu_dom_selector, has_text=menu_name).is_visible():
        ColorLogger.error(f"Navigate to Data plane Observability page first.")
        return

    page.locator(menu_dom_selector, has_text=menu_name).click()
    print(f"Clicked 'Observability -> {menu_name}' left side menu")
    page.wait_for_timeout(500)

def goto_app_detail(dp_name, app_name):
    ColorLogger.info(f"Going to app '{app_name}' detail page")
    goto_dataplane(dp_name)
    if not page.locator("apps-list td.app-name a", has_text=app_name).is_visible():
        ColorLogger.error(f"The app '{app_name}' is not deployed yet.")
        sys.exit(f"Exiting program: The app '{app_name}' is not deployed yet.")

    page.locator("apps-list td.app-name a", has_text=app_name).click()
    print(f"Clicked app '{app_name}'")
    page.locator(".app-name-section .name", has_text=app_name).wait_for(state="visible")
    print(f"Navigated to app '{app_name}' detail page")
    page.wait_for_timeout(500)

def o11y_get_new_resource(dp_name=""):
    # For 1.4 version
    add_new_resource_button = page.locator(".add-dp-observability-btn", has_text="Add new resource")
    if ENV.TP_AUTO_CP_VERSION == "1.5":
        if dp_name == "":
            # For 1.5 Global data plane
            add_new_resource_button = page.locator(".global-configuration-details .add-global-o11y-icon")
        else:
            # For 1.5 none Global data plane
            add_new_resource_button = page.locator("observability-data-plane .add-dp-o11y-icon")

    return add_new_resource_button

def o11y_config_dataplane_resource(dp_name=""):
    ColorLogger.info("O11y start config dataplane resource...")
    if not ENV.TP_AUTO_IS_CONFIG_O11Y:
        ColorLogger.warning("TP_AUTO_IS_CONFIG_O11Y is false, skip config Observability Resource.")
        return
    dp_title = dp_name
    # dp_name is empty, it means global data plane
    if dp_name == "":
        dp_title = "Global"
        goto_left_navbar("Data Planes")
        page.locator(".global-configuration button", has_text="Global configuration").click()
        print("Clicked 'Global configuration' button")
        page.locator(".pl-leftnav-layout .pl-leftnav-menu__link", has_text="Observability").wait_for(state="visible")
        page.locator(".pl-leftnav-layout .pl-leftnav-menu__link", has_text="Observability").click()
        print("Clicked Global configuration -> 'Observability' left side menu")
    else:
        goto_dataplane_config_sub_menu("Observability")

    print("Checking if 'Add new resource' button is exist...")
    page.wait_for_timeout(5000)

    add_new_resource_button = o11y_get_new_resource(dp_name)
    if not add_new_resource_button.is_visible():
        print("'Add new resource' button is not exist...")
        ColorLogger.success(f"Data plane '{dp_title}' Observability Resources is already configured.")
        return

    add_new_resource_button.click()
    print("Clicked 'Create new Data Plane Resources' button")

    print("Waiting for O11y config o11y page is loaded")
    page.locator(".configuration").wait_for(state="visible")
    print("O11y config o11y page is loaded")

    # Step 1: Configure Log Server
    if page.locator("#resourceName-input").is_visible():    # for 1.3 version
        page.fill("#resourceName-input", f"{dp_name}-rs")
        print(f"Input Resource Name: {dp_name}-rs")
    # Add or Select Logs -> User Apps -> Query Service configurations
    menu_name = "Logs"
    tab_name = "Query Service"
    if page.locator("label[for='userapp-proxy']", has_text=f"{tab_name} disabled").is_visible():
        page.locator("label[for='userapp-proxy']").click()
        print(f"Clicked '{tab_name}' toggle button")
    if page.locator("label[for='userapp-proxy']", has_text=f"{tab_name} enabled").is_visible():
        o11y_config_table_add_or_select_item(dp_name, menu_name, tab_name, "", "#add-userapp-proxy-btn")

    # Add or Select Logs -> User Apps -> Exporter configurations
    tab_name = "Exporter"
    if page.locator("label[for='userapp-exporter']", has_text=f"{tab_name} disabled").is_visible():
        page.locator("label[for='userapp-exporter']").click()
        print(f"Clicked '{tab_name}' toggle button")
    if page.locator("label[for='userapp-exporter']", has_text=f"{tab_name} enabled").is_visible():
        o11y_config_table_add_or_select_item(dp_name, menu_name, tab_name, "User Apps", "#add-userapp-exporter-btn")

    # Add or Select Logs -> Services -> Exporter configurations
    tab_name = "Exporter"
    if page.locator("label[for='services-exporter-toggle']", has_text=f"{tab_name} disabled").is_visible():
        page.locator("label[for='services-exporter-toggle']").click()
        print(f"Clicked '{tab_name}' toggle button")
    if page.locator("label[for='services-exporter-toggle']", has_text=f"{tab_name} enabled").is_visible():
        o11y_config_table_add_or_select_item(dp_name, menu_name, tab_name, "Services", "#add-services-exporter-btn")

    page.wait_for_timeout(500)
    page.locator("#go-to-metrics-server-configuration").click()
    print("Clicked 'Next' button")
    print(f"Data plane '{dp_title}' 'Configure Log Server' Step 1 is configured.")

    # Step 2: Configure Metrics Server
    # Add or Select Metrics -> Query Service configurations
    menu_name = "Metrics"
    tab_name = "Query Service"
    o11y_config_table_add_or_select_item(dp_name, menu_name, tab_name, "", "#add-metrics-proxy-btn")

    # Add or Select Metrics -> Exporter configurations
    tab_name = "Exporter"
    if page.locator("label[for='metrics-exporter-toggle']", has_text=f"{tab_name} disabled").is_visible():
        page.locator("label[for='metrics-exporter-toggle']").click()
        print(f"Clicked '{tab_name}' toggle button")
    if page.locator("label[for='metrics-exporter-toggle']", has_text=f"{tab_name} enabled").is_visible():
        o11y_config_table_add_or_select_item(dp_name, menu_name, tab_name, "", "#add-metrics-exporter-btn")
    page.locator("#go-to-traces-configuration").click()
    print("Clicked 'Next' button")
    print(f"Data plane '{dp_title}' 'Configure Metrics Server' Step 2 is configured.")

    # Step 3: Configure Traces Server
    # Add or Select Traces -> Query Service configurations
    menu_name = "Traces"
    tab_name = "Query Service"
    if page.locator("label[for='traces-proxy']", has_text=f"{tab_name} disabled").is_visible():
        page.locator("label[for='traces-proxy']").click()
        print(f"Clicked '{tab_name}' toggle button")
    if page.locator("label[for='traces-proxy']", has_text=f"{tab_name} enabled").is_visible():
        o11y_config_table_add_or_select_item(dp_name, menu_name, tab_name, "", "#add-traces-proxy-btn")

    # Add or Select Traces -> Exporter configurations
    tab_name = "Exporter"
    if page.locator("label[for='traces-exporter']", has_text=f"{tab_name} disabled").is_visible():
        page.locator("label[for='traces-exporter']").click()
        print(f"Clicked '{tab_name}' toggle button")
    if page.locator("label[for='traces-exporter']", has_text=f"{tab_name} enabled").is_visible():
        o11y_config_table_add_or_select_item(dp_name, menu_name, tab_name, "", "#add-traces-exporter-btn")
    page.locator("#save-observability").click()
    print(f"Data plane '{dp_title}' 'Configure Traces Server' Step 3 is configured.")
    print(f"Wait 3 seconds for Data plane '{dp_title}' configuration page redirect.")
    page.wait_for_timeout(3000)

def o11y_config_table_add_or_select_item(dp_name, menu_name, tab_name, tab_sub_name, add_button_selector):
    ColorLogger.info("O11y start to add or select item...")
    name_input = Util.get_o11y_sub_name_input(dp_name, menu_name, tab_name, tab_sub_name)
    print(f"Check if name: '{name_input}' is exist in {tab_sub_name} configurations")
    if not page.locator("observability-configurations table tr", has=page.locator("td", has_text=name_input)).is_visible():
        page.locator(add_button_selector).click()
        print(f"Clicked 'Add {tab_name} configuration' button in {tab_sub_name} configurations")
        o11y_new_resource_fill_form(menu_name, tab_name, name_input, dp_name)

    print(f"Waiting for '{name_input}' display in {tab_name}")
    page.locator("observability-configurations table tr", has=page.locator("td", has_text=name_input)).locator("label").wait_for(state="visible")
    page.locator("observability-configurations table tr", has=page.locator("td", has_text=name_input)).locator("label").click()
    print(f"Selected '{name_input}' in {tab_name} configurations")

# when dp_name is empty, it means global data plane
def o11y_new_resource_fill_form(menu_name, tab_name, name_input, dp_name=""):
    ColorLogger.info("O11y start to fill new resource form...")
    dp_title = dp_name if dp_name else "Global"
    print(f"Fill form for Data Plane: {dp_title} -> O11y-> {menu_name} -> {tab_name} ...")
    page.wait_for_selector("configuration-modal .pl-modal")
    page.fill("#config-name-input", name_input)
    page.locator("configuration-modal input.pl-select__control").click()
    print(f"Clicked 'Query Service type' dropdown")
    page.locator("configuration-modal .pl-select-menu__item").nth(0).wait_for(state="visible")

    if menu_name == "Metrics":
        page.locator("configuration-modal .pl-select-menu__item", has_text="Prometheus").click()
        print(f"Selected 'Prometheus' in 'Query Service type' dropdown")
        if tab_name == "Query Service":
            o11y_fill_prometheus_or_elastic("Prometheus", ENV.TP_AUTO_PROMETHEUS_URL, ENV.TP_AUTO_PROMETHEUS_USER, ENV.TP_AUTO_PROMETHEUS_PASSWORD)
    else:
        page.locator("configuration-modal .pl-select-menu__item", has_text="ElasticSearch").click()
        print(f"Selected 'ElasticSearch' in 'Query Service type' dropdown")
        page.locator("#endpoint-input").wait_for(state="visible")
        print(f"Filling ElasticSearch form...")
        if menu_name == "Logs":
            page.fill("#log-index-input", name_input)
            print(f"Fill Log Index: {name_input}")

        o11y_fill_prometheus_or_elastic("ElasticSearch", ENV.TP_AUTO_ELASTIC_URL, ENV.TP_AUTO_ELASTIC_USER, ENV.TP_AUTO_ELASTIC_PASSWORD)

    page.locator("configuration-modal .pl-modal__footer-left button.pl-button--primary", has_text="Save").click()
    page.wait_for_timeout(1000)
    if page.locator(".pl-notification__message").is_visible():
        page.locator("configuration-modal .pl-modal__footer-left button", has_text="Cancel").click()
        ColorLogger.success(f"The {name_input} is already exist.")

    ColorLogger.success(f"Added {name_input} for Data Plane '{dp_title}' Observability -> {menu_name} -> {tab_name}")

def o11y_fill_prometheus_or_elastic(query_service_type, url, username, password):
    ColorLogger.info(f"O11y Filling {query_service_type} form...")
    page.locator("#endpoint-input").wait_for(state="visible")
    if not page.locator("#endpoint-input").is_visible():
        ColorLogger.error(f"Query Service type: {query_service_type} is not visible.")
        sys.exit(f"Exiting program: Query Service type: {query_service_type} is not visible.")

    page.fill("#endpoint-input", url)
    print(f"Fill {query_service_type} URL: {url}")
    if username != "":
        page.fill("#username-input", username)
        print(f"Fill {query_service_type} User: {username}")
    if password != "":
        page.fill("#password-input", password)
        print(f"Fill {query_service_type} Password: {password}")

def o11y_add_query_or_exporter(dp_name, menu_name, tab_name, name_input=""):
    ColorLogger.info("O11y start to add Query or Exporter...")
    dp_title = dp_name if dp_name else "Global"
    print(f"Adding {menu_name} -> {tab_name} for Data Plane '{dp_title}'...")
    page.locator(".stepper a", has_text=tab_name + " configurations").click()
    if name_input == "":
        name_input = Util.get_o11y_sub_name_input(dp_name, menu_name, tab_name, "")

    page.wait_for_timeout(1500)
    if page.locator("proxies-exporters-list table").locator("td", has_text=name_input).is_visible():
        ColorLogger.success(f"The {name_input} is already exist in {menu_name} -> {tab_name}.")
        return

    page.locator("proxies-exporters-list button", has_text="Add").click()
    print(f"Clicked 'Observability -> {menu_name} -> {tab_name} -> Add' button")
    o11y_new_resource_fill_form(menu_name, tab_name, name_input, dp_name)

def o11y_add_log_exporter(dp_name, table_index, name_input=""):
    ColorLogger.info("O11y start to add Log Exporter...")
    dp_title = dp_name if dp_name else "Global"
    tab_name = "Exporter"
    menu_name = "Logs"
    tab_sub_name = "User Apps" if table_index == 0 else "Services"

    print(f"Adding {menu_name} -> {tab_name} -> {tab_sub_name} for Data Plane '{dp_title}'...")
    page.locator(".stepper a", has_text=tab_name + " configurations").click()
    if name_input == "":
        name_input = Util.get_o11y_sub_name_input(dp_name, menu_name, tab_name, tab_sub_name)

    page.wait_for_timeout(1000)
    if page.locator("proxies-exporters-list table").nth(table_index).locator("td", has_text=name_input).is_visible():
        ColorLogger.success(f"The {name_input} is already exist in {menu_name} -> {tab_name} -> {tab_sub_name}.")
        return

    page.locator("proxies-exporters-list button", has_text="Add").nth(table_index).click()
    print(f"Clicked 'Observability -> {menu_name} -> {tab_name} -> Add' button")
    o11y_new_resource_fill_form(menu_name, tab_name, name_input, dp_name)

def o11y_config_logs_metrics_traces(dp_name="", is_global=False):
    ColorLogger.info("O11y start to config Logs/Metrics/Traces...")
    dp_title = dp_name if dp_name else "Global"
    print(f"Config {dp_title} Data Plane -> Observability -> Logs/Metrics/Traces ...")
    goto_dataplane_config_sub_menu("Observability")
    add_button_selector = "observability-data-plane .o11y-btn .add-dp-o11y-icon"
    if is_global:
        add_button_selector = ".global-configuration-details .add-global-o11y-icon"
    if not page.locator(add_button_selector).is_visible():
        ColorLogger.warning(f"New UI for Data plane '{dp_title}' Observability is not available.")
        return

    goto_dataplane_config_o11y_sub("Logs")
    o11y_add_query_or_exporter(dp_name, "Logs", "Query Service")
    o11y_add_log_exporter(dp_name, 0)
    o11y_add_log_exporter(dp_name, 1)

    goto_dataplane_config_o11y_sub("Metrics")
    o11y_add_query_or_exporter(dp_name, "Metrics", "Query Service")
    o11y_add_query_or_exporter(dp_name, "Metrics", "Exporter")

    goto_dataplane_config_o11y_sub("Traces")
    o11y_add_query_or_exporter(dp_name, "Traces", "Query Service")
    o11y_add_query_or_exporter(dp_name, "Traces", "Exporter")

def dp_config_resources_storage():
    ColorLogger.info("Config Data Plane Resources Storage...")
    page.locator("#resources-menu-item .menu-item-text", has_text="Resources").wait_for(state="visible")
    page.locator("#resources-menu-item .menu-item-text", has_text="Resources").click()
    print("Clicked 'Resources' left side menu")
    resource_name = ENV.TP_AUTO_STORAGE_CLASS
    print(f"Resource Name: {resource_name}")
    page.wait_for_timeout(500)
    if page.locator("#storage-resource-table tr td:first-child", has_text=resource_name).is_visible():
        ColorLogger.success(f"Storage '{resource_name}' is already created.")
    else:
        print(f"Adding Storage '{resource_name}', and wait for 'Add Storage Class' button ...")
        page.locator("#add-storage-resource-btn").wait_for(state="visible")
        page.locator("#add-storage-resource-btn").click()
        print("Clicked 'Add Storage' button")
        page.locator('.pl-modal__header', has_text="Add Storage").wait_for(state="visible")
        print("Dialog 'Add Storage' popup")
        page.fill('#resourceName-input', resource_name)
        page.fill('#description-input', resource_name)
        page.fill('#storageClassName-input', resource_name)
        print(f"Filled Storage Class, {resource_name}")
        page.wait_for_timeout(1000)
        page.locator("#save-storage-configuration").click()
        print("Clicked 'Add' button")
        page.wait_for_timeout(1000)
        ColorLogger.success(f"Add Storage '{resource_name}' successfully.")

def dp_config_resources_ingress():
    ColorLogger.info("Config Data Plane Resources Ingress...")
    page.locator("#resources-menu-item .menu-item-text", has_text="Resources").wait_for(state="visible")
    page.locator("#resources-menu-item .menu-item-text", has_text="Resources").click()
    print("Clicked 'Resources' left side menu")
    page.locator("#toggle-ingress-expansion").click()
    resource_name = ENV.TP_AUTO_INGRESS_CONTROLLER
    page.wait_for_timeout(500)
    print(f"Check if Ingress Controller '{resource_name}' is exist...")
    if page.locator("#ingress-resource-table tr td:first-child", has_text=resource_name).is_visible():
        ColorLogger.success(f"Ingress Controller '{resource_name}' is already created.")
    else:
        print(f"Adding Ingress Controller '{resource_name}', and wait for 'Add Ingress Controller' button ...")
        page.locator(".ingress .add-resource-btn button").wait_for(state="visible")
        page.locator(".ingress .add-resource-btn button").click()
        print("Clicked 'Add Ingress Controller' button")
        page.locator('.pl-modal__header', has_text="Add Ingress Controller").wait_for(state="visible")
        print("Dialog 'Add Ingress Controller' popup")
        page.fill('#resourceName-input', resource_name)
        page.fill('#ingressClassName-input', resource_name)
        page.fill('#fqdn-input', ENV.TP_AUTO_FLOGO_CAPABILITY_URL)
        print(f"Filled Ingress Controller, {resource_name}, {ENV.TP_AUTO_FLOGO_CAPABILITY_URL}")
        page.wait_for_timeout(1000)
        page.locator("#save-ingress-configuration").click()
        print("Clicked 'Add' button")
        page.wait_for_timeout(1000)
        ColorLogger.success(f"Add Ingress Controller '{resource_name}' successfully.")

def flogo_goto_capability(dp_name, is_check_status=True):
    ColorLogger.info("Flogo Going to capability...")
    is_exit = False
    goto_dataplane(dp_name)
    print("Check if Flogo capability is ready...")
    if check_dom_visibility(page.locator("capability-card #flogo"), 10, 120, True):
        print("Waiting for Flogo capability status is ready...")
        if not is_check_status:
            page.locator("capability-card #flogo .image-name").click()
            print("Ignore check 'Flogo' capability status, get into 'Flogo' capability page")
            return
        if check_dom_visibility(page.locator("capability-card #flogo .status .success")):
            page.locator("capability-card #flogo .image-name").click()
            print("Flogo capability status is ready, get into 'Flogo' capability")
        else:
            ColorLogger.error("Flogo capability is provisioned, but status is not ready.")
            is_exit = True
    else:
        ColorLogger.error("Flogo capability is not provisioned yet.")
        is_exit = True

    if is_exit:
        sys.exit("Exiting program: Flogo capability is not provisioned yet.")

def flogo_provision_capability(dp_name):
    ColorLogger.info("Flogo Provisioning capability...")
    goto_dataplane(dp_name)
    if page.locator("capability-card #flogo").is_visible():
        ColorLogger.success("Flogo capability is already provisioned.")
        return

    print("Checking if 'Provision a capability' button is visible.")
    if check_dom_visibility(page.locator('button', has_text="Provision a capability"), 10, 100):
        print("'Provision a capability' button is visible.")
        ColorLogger.success(f"Data Plane '{dp_name}' status is running.")
        page.locator('button', has_text="Provision a capability").click()
        print("Clicked 'Provision a capability' button")
        button = page.locator('#FLOGO-capability-select-button')
        button.wait_for(state="visible")
        page.wait_for_function(
            """
            (button) => !button.disabled
            """,
            arg=button.element_handle()
        )
        button.click()
        print("Clicked 'Provision TIBCO Flogo® Enterprise' -> 'Start' button")

        print("Waiting for Flogo capability page is loaded")
        page.locator(".resources-content").wait_for(state="visible")
        print("Flogo capability page is loaded")

        page.locator('#storage-class-resource-table tr', has=page.locator('td', has_text=ENV.TP_AUTO_STORAGE_CLASS)).locator('label').click()
        print(f"Selected '{ENV.TP_AUTO_STORAGE_CLASS}' Storage Class")
        page.locator('#ingress-resource-table tr', has=page.locator('td', has_text=ENV.TP_AUTO_INGRESS_CONTROLLER)).locator('label').click()
        print(f"Selected '{ENV.TP_AUTO_INGRESS_CONTROLLER}' Ingress Controller")

        page.locator("#btnNextCapabilityProvision").click()
        page.locator(".eula-container input").click()
        page.locator("#qaProvisionFlogo").click()
        print("Selected 'EUA', then clicked 'Provision Flogo Version' button")
        page.locator("flogo-tp-pl-icon svg.complete").wait_for(state="visible")
        ColorLogger.success("Provision Flogo capability successful.")
        page.locator("#qaBackToDP").click()
        print("Clicked 'Go Back To Data Plane Details' button")
    else:
        ColorLogger.error("'Provision a capability' button is not visible.")
        sys.exit("Exiting program: Flogo capability is not provisioned yet.")

def flogo_provision_connector(dp_name):
    ColorLogger.info("Flogo Provisioning connector...")

    flogo_goto_capability(dp_name, False)
    page.wait_for_timeout(1000)
    print("Before flogo provision connector, Check if Flogo have API error...")
    if page.locator(".notification-message", has_text="Could not get custom extension provisioned in the Data plane").is_visible():
        ColorLogger.error("Flogo capability page API error: Could not get custom extension provisioned in the Data plane.")
        return

    print("Flogo Checking connectors...")
    if page.locator(".capability-connectors-container .total-capability", has_text="(2)").is_visible():
        ColorLogger.success("Flogo connectors are already provisioned.")
        return

    # program will exit if Flogo capability is not provisioned yet
    flogo_goto_capability(dp_name)
    print("Start Create Flogo app connector...")

    page.locator(".capability-buttons", has_text="Provision Flogo & Connectors").wait_for(state="visible")
    page.locator(".capability-buttons", has_text="Provision Flogo & Connectors").click()
    print("Clicked 'Provision Flogo & Connectors' button")
    # page.locator(".versions-container label", has_text="HTTP").wait_for(state="visible")
    # page.locator(".versions-container label", has_text="HTTP").click()
    # page.locator(".versions-container label", has_text="Websocket").scroll_into_view_if_needed()
    # page.locator(".versions-container label", has_text="Websocket").click()
    # print("Selected 'HTTP' and 'Websocket' connectors")
    page.locator("#qaPluginProvision").click()
    print("Clicked 'Provision' button")
    page.locator("flogo-plugins-provision-finish .complete").wait_for(state="visible")
    ColorLogger.success("Provision Flogo & Connectors successful.")
    page.locator(".finish-buttons-container button", has_text="Go back to Data Plane details").click()
    print("Clicked 'Go back to Data Plane details' button")

def flogo_app_build_and_deploy(dp_name, app_file_name, app_name):
    ColorLogger.info("Flogo Creating app build...")

    flogo_goto_capability(dp_name, False)
    page.wait_for_timeout(1000)
    print("Before flogo app build and deploy, Check if Flogo have API error...")
    if page.locator(".notification-message", has_text="Could not get custom extension provisioned in the Data plane").is_visible():
        ColorLogger.error("Flogo capability page API error: Could not get custom extension provisioned in the Data plane.")
        return

    print("Flogo Checking app build...")
    if page.locator(".app-build-container td", has_text=app_name).is_visible():
        ColorLogger.success(f"Flogo app build {app_name} is already created.")
        return

    # program will exit if Flogo capability is not provisioned yet
    flogo_goto_capability(dp_name)
    page.wait_for_timeout(1000)
    print("Start Create Flogo app build...")

    page.locator(".capability-buttons", has_text="Create New App Build And Deploy").click()
    print("Clicked 'Create New App Build And Deploy' button")

    # step1: Upload Files
    file_path = os.path.join(os.path.dirname(__file__), app_file_name)
    page.locator('input[type="file"]').evaluate("(input) => input.style.display = 'block'")

    page.locator('input[type="file"]').set_input_files(file_path)
    print(f"Selected file: {file_path}")
    page.locator('app-upload-file .dropzone-file-name', has_text=app_file_name).wait_for(state="visible")
    page.locator('#qaUploadApp').click()
    print("Clicked 'Upload' button")
    page.locator('flogo-deploy-upload-app .upload-main-title', has_text="File Uploaded Successfully").wait_for(state="visible")
    print(f"File '{app_file_name}' Uploaded Successfully")
    page.locator('#qaNextAppDeploy').click()
    print("Clicked 'Next' button")

    # step2: Select Versions
    if page.locator(".version-field-container .rovision-link", has_text="Provision Flogo in another tab").is_visible():
        with page.context.expect_page() as new_page_info:
            page.locator(".version-field-container .rovision-link", has_text="Provision Flogo in another tab").click()
            print("Clicked 'Provision Flogo in another tab' link")

        new_page = new_page_info.value
        ColorLogger.success("New window detected and captured.")
        new_page.locator(".versions-container label", has_text="HTTP").click()
        new_page.locator(".versions-container label", has_text="Websocket").scroll_into_view_if_needed()
        new_page.locator(".versions-container label", has_text="Websocket").click()
        print("Selected 'HTTP' and 'Websocket' connectors")
        new_page.locator("#qaPluginProvision").click()
        new_page.close()
        ColorLogger.success("Provision Flogo & Connectors successful.")
        page.locator(".refresh-link", has_text="Refresh List").click()
        page.wait_for_timeout(1000)

    page.locator("flogo-namespace-picker input").click()
    if not page.locator("flogo-namespace-picker .namespace-dropdown li", has_text=ENV.TP_AUTO_K8S_DP_NAMESPACE).is_visible():
        ColorLogger.error(f"Namespace '{ENV.TP_AUTO_K8S_DP_NAMESPACE}' is not list in the dropdown.")
        sys.exit(f"Exiting program: Namespace '{ENV.TP_AUTO_K8S_DP_NAMESPACE}' is not list in the dropdown.")

    page.locator("flogo-namespace-picker .namespace-dropdown li", has_text=ENV.TP_AUTO_K8S_DP_NAMESPACE).click()
    print(f"Selected namespace: {ENV.TP_AUTO_K8S_DP_NAMESPACE}")
    page.locator(".eula-container").click()
    print("Clicked 'EUA' checkbox")
    page.locator('#qaNextAppDeploy').click()
    print("Clicked 'Next' button")

    # step3: Resource Configuration
    page.locator('#qaResourceAppDeploy').click()
    print("Clicked 'Deploy App' button")

    # step4: Finished
    page.locator('.finish-container .deploy-banner-icon').wait_for(state="visible")
    ColorLogger.success(f"Created Flogo app build '{app_name}' Successfully")
    page.locator('.finish-container .step-description', has_text="Building the app...").wait_for(state="visible")
    print("Waiting for 'Building the app...'")
    print("Check if Flogo app deployed successfully...")
    if check_dom_visibility(page.locator('.finish-container .step-description', has_text="Successfully deployed App")):
        ColorLogger.success(f"Flogo app build '{app_name}' is deployed.")

def flogo_app_deploy(dp_name, app_name):
    ColorLogger.info(f"Flogo Deploying app '{app_name}'...")
    dp_name_space = ENV.TP_AUTO_K8S_DP_NAMESPACE

    goto_dataplane(dp_name)
    if page.locator("apps-list td.app-name a", has_text=app_name).is_visible():
        ColorLogger.success(f"Flogo app '{app_name}' in namespace {dp_name_space} is already deployed.")
        return

    # program will exit if Flogo capability is not provisioned yet
    flogo_goto_capability(dp_name)

    print(f"Waiting for Flogo app build {app_name} is deployed...")
    if not check_dom_visibility(page.locator(".app-build-container td:first-child", has_text=app_name), 20, 180, True):
        ColorLogger.error(f"Flogo app {app_name} is not deployed.")
        sys.exit(f"Exiting program: Flogo app {app_name} is not deployed.")

    page.locator(".app-build-container tr", has=page.locator("td", has_text=app_name)).nth(0).locator('flogo-app-build-actions button[data-pl-dropdown-role="toggler"]').click()
    print(f"Clicked action menu button for {app_name}")
    page.locator(".app-build-container tr", has=page.locator("td", has_text=app_name)).nth(0).locator('flogo-app-build-actions .action-menu button', has_text="Deploy").click()
    print(f"Clicked 'Deploy' from action menu list for {app_name}")

    page.locator(".pl-modal__footer-right button", has_text="Deploy App Build").wait_for(state="visible")
    print("Dialog 'Deploy App Build' popup")
    page.locator("flogo-namespace-picker input").click()

    page.locator("flogo-namespace-picker .namespace-dropdown li", has_text=dp_name_space).click()
    print(f"Selected Namespace '{dp_name_space}' for {dp_name}")

    page.locator("#deployName").clear()
    page.fill("#deployName", app_name)
    print(f"Clear previous deploy name and Input lower case Deploy Name: {app_name}")

    page.locator(".pl-modal__footer-right button", has_text="Deploy App Build").click()
    print("Clicked 'Deploy App Build' button")

    page.locator("flogo-capability-header .dp-sec-name", has_text=dp_name).click()
    print(f"Clicked menu navigator Data Plane '{dp_name}'")

    if check_dom_visibility(page.locator("apps-list td.app-name a", has_text=app_name), 10, 120):
        ColorLogger.success(f"Deploy Flogo app '{app_name}' in namespace {dp_name_space} Successfully")
    else:
        ColorLogger.error(f"Deploy Flogo app '{app_name}' in namespace {dp_name_space} failed.")

def flogo_app_config(dp_name, app_name):
    ColorLogger.info(f"Flogo Config app '{app_name}'...")
    goto_app_detail(dp_name, app_name)

    if page.locator(".no-endpoints", has_text="There are no Endpoints configured for the application").is_visible():
        ColorLogger.error(f"There is some error for Flogo app '{app_name}', it has no Endpoints configured.")
        return

    # set Endpoint Visibility to Public
    print("Set Endpoint Visibility to Public")
    page.locator("#app-details-menu-dropdown-label").wait_for(state="visible")
    page.locator("#app-details-menu-dropdown-label").click()
    page.locator(".pl-dropdown-menu__action", has_text="Set Endpoint Visibility").wait_for(state="visible")
    page.locator(".pl-dropdown-menu__action", has_text="Set Endpoint Visibility").click()
    print("Clicked 'Set Endpoint Visibility' menu item")
    page.locator(".pl-modal__footer-right button", has_text="Cancel").wait_for(state="visible")
    print("Dialog 'Set Endpoint Visibility' popup")
    if page.locator(".modal-header", has_text="Update Endpoint visibility to Public").is_visible():
        if page.locator(".capability-table-row-details label[for='ingress-radio-button-0']", has_text=ENV.TP_AUTO_INGRESS_CONTROLLER).is_visible():
            page.locator(".capability-table-row-details label[for='ingress-radio-button-0']", has_text=ENV.TP_AUTO_INGRESS_CONTROLLER).click()
            print(f"Selected '{ENV.TP_AUTO_INGRESS_CONTROLLER}' from Resource Name column")
            page.locator("button", has_text="Update Endpoint visibility to Public").click()
            print("Clicked 'Update Endpoint visibility to Public' button")
        else:
            ColorLogger.warning(f"Not able to set Endpoint Visibility to Public, '{ENV.TP_AUTO_INGRESS_CONTROLLER}' is not available.")
    else:
        if page.locator(".modal-header", has_text="Update Endpoint visibility to Private").is_visible():
            page.locator(".pl-modal__footer-right button", has_text="Cancel").click()
            print("Clicked 'Cancel' button")
            ColorLogger.success(f"Flogo app '{app_name}' has set Endpoint Visibility to Public.")

    # set Engine Variables, FLOGO_OTEL_TRACE to true
    print("Navigating to 'Engine Variables' tab menu")
    page.locator(".pl-primarynav__menu .pl-primarynav__item", has_text="Environmental Controls").click()
    print("Clicked 'Environmental Controls' tab menu")
    page.locator(".environment-container .left-navigation li a", has_text="Engine Variables").wait_for(state="visible")
    page.locator(".environment-container .left-navigation li a", has_text="Engine Variables").click()
    print("Clicked 'Engine Variables' left side menu")
    page.locator(".appVars-table tr.pl-table__row", has=page.locator("td", has_text="FLOGO_OTEL_TRACE")).wait_for(state="visible")
    flogo_otel_trace_selector = page.locator(".appVars-table tr.pl-table__row", has=page.locator("td", has_text="FLOGO_OTEL_TRACE")).locator("select")
    if flogo_otel_trace_selector.input_value() == "true":
        ColorLogger.success("FLOGO_OTEL_TRACE is already set to true.")
    else:
        flogo_otel_trace_selector.select_option(label="true")
        print("Set FLOGO_OTEL_TRACE to true")
        page.locator("button.update-button", has_text="Push Updates").click()
        print("Clicked 'Push Updates' button")

def flogo_app_start(dp_name, app_name):
    ColorLogger.info(f"Flogo Start app '{app_name}'...")
    goto_app_detail(dp_name, app_name)

    print("Waiting to see if app status is Running...")
    page.locator("flogo-app-run-status .scale-status-text").wait_for(state="visible")
    if page.locator("flogo-app-run-status .scale-status-text", has_text="Running").is_visible():
        ColorLogger.success(f"Flogo app '{app_name}' is already running.")
    else:
        page.locator("flogo-app-run-status button", has_text="Start").click()
        print("Clicked 'Start' app button")

        print(f"Waiting for app '{app_name}' status is Running...")
        if check_dom_visibility(page.locator("flogo-app-run-status .scale-status-text", has_not_text="Scaling"), 15, 180, True):
            app_status = page.locator("flogo-app-run-status .scale-status-text").inner_text()
            ColorLogger.success(f"Flogo app '{app_name}' status is '{app_status}' now.")
        else:
            ColorLogger.error(f"Wait too long to scale Flogo app '{app_name}'.")

def flogo_app_test_endpoint(dp_name, app_name):
    ColorLogger.info(f"Flogo Test app endpoint '{app_name}'...")
    goto_app_detail(dp_name, app_name)

    print("Navigating to 'Endpoints' tab menu")
    page.locator(".pl-primarynav__menu .pl-primarynav__item", has_text="Endpoints").click()

    print("Check if 'Test' button is visible...")
    if page.locator(".endpoints-container .action-button a", has_text="Test").is_visible():
        with page.context.expect_page() as new_page_info:
            page.locator(".endpoints-container .action-button a", has_text="Test").click()
            print("Clicked 'Test' button")

        new_page = new_page_info.value
        print("New window detected and captured.")

        print("Waiting for Swagger page loaded.")
        new_page.wait_for_load_state()

        print(f"Waiting for Swagger title '{app_name}' to be displayed.")
        if check_dom_visibility(new_page.locator("#swagger-editor h2.title", has_text=app_name), 5, 20, True):
            new_page.locator("#swagger-editor h2.title", has_text=app_name).wait_for(state="visible")
            print(f"The Swagger title '{app_name}' is displayed.")

            new_page.locator("#operations-default-get_flogo .opblock-summary-control").click()
            print("Clicked '/flogo' path, expand API details")

            new_page.locator("#operations-default-get_flogo button", has_text="Try it out").click()
            print("Clicked 'Try it out' button")
            new_page.locator("#operations-default-get_flogo button", has_text="Execute").click()
            print("Clicked 'Execute' button")
            new_page.close()
            print("Closed Swagger page")
            ColorLogger.success(f"Test Flogo app '{app_name}', endpoint '/flogo'")
        else:
            ColorLogger.error(f"Swagger page is not loaded, title '{app_name}' is not displayed.")
    else:
        ColorLogger.error(f"'Test' button is not visible in Flogo app {app_name}, need to config it and start app.")

def flogo_is_app_created(dp_name, app_name):
    ColorLogger.info(f"Checking if Flogo app '{app_name}' is created")
    goto_dataplane(dp_name)
    try:
        print(f"Checking if Flogo app '{app_name}' is already created...")
        page.wait_for_timeout(3000)
        if page.locator("#app-list-table tr.pl-table__row td.app-name", has_text=app_name).is_visible():
            ColorLogger.success(f"Flogo app '{app_name}' is already created.")
            return True
        else:
            print(f"Flogo app '{app_name}' has not been created.")
            return False
    except Exception as e:
        print(f"An error occurred while Checking Flogo app '{app_name}': {e}")
        ColorLogger.error(f"An error occurred while Checking Flogo app '{app_name}': {e}")
        return False

if __name__ == "__main__":
    ENV = EnvConfig()
    START_TIME = time.time()

    browser = Util.browser_launch(ENV.IS_HEADLESS)
    page = Util.browser_page(browser)

    if not is_host_prefix_exist(ENV.DP_HOST_PREFIX):
        if not is_admin_user_exist():
            active_user_in_mail(ENV.CP_ADMIN_EMAIL, True)
        admin_provision_user(ENV.DP_USER_EMAIL, ENV.DP_HOST_PREFIX)
        active_user_in_mail(ENV.DP_USER_EMAIL)

    login()
    set_user_permission()

    # config global dataplane
    # o11y_config_dataplane_resource()

    goto_left_navbar("Data Planes")
    k8s_create_dataplane(ENV.TP_AUTO_K8S_DP_NAME)
    goto_dataplane(ENV.TP_AUTO_K8S_DP_NAME)
    goto_dataplane_config()
    dp_config_resources_storage()
    dp_config_resources_ingress()
    flogo_provision_capability(ENV.TP_AUTO_K8S_DP_NAME)

    goto_dataplane_config()
    o11y_config_dataplane_resource(ENV.TP_AUTO_K8S_DP_NAME)

    if not flogo_is_app_created(ENV.TP_AUTO_K8S_DP_NAME, ENV.FLOGO_APP_NAME):
        flogo_provision_connector(ENV.TP_AUTO_K8S_DP_NAME)
        flogo_app_build_and_deploy(ENV.TP_AUTO_K8S_DP_NAME, ENV.FLOGO_APP_FILE_NAME, ENV.FLOGO_APP_NAME)
        flogo_app_deploy(ENV.TP_AUTO_K8S_DP_NAME, ENV.FLOGO_APP_NAME)
        flogo_app_config(ENV.TP_AUTO_K8S_DP_NAME, ENV.FLOGO_APP_NAME)
    flogo_app_start(ENV.TP_AUTO_K8S_DP_NAME, ENV.FLOGO_APP_NAME)
    flogo_app_test_endpoint(ENV.TP_AUTO_K8S_DP_NAME, ENV.FLOGO_APP_NAME)
    logout()
    Util.print_env_info(ENV)

    Util.browser_close(browser)
    END_TIME = time.time()
    print(f"Program running time: {END_TIME - START_TIME:.2f} seconds")
