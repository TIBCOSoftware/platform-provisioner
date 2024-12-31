import json
import os
import sys

from playwright.sync_api import sync_playwright
from color_logger import ColorLogger
from util import Util

IS_HEADLESS = Util.is_headless()
GITHUB_TOKEN, HOST_PREFIX, USER_EMAIL, USER_PASSWORD, ADMIN_EMAIL, ADMIN_PASSWORD = Util.get_env_info()

DATAPLANE_NAME = "k8s-auto-dp1"
FLOGO_APP = "flogo.json"
MAX_DATA_PLANES = 8
LOGIN_URL = f"https://{HOST_PREFIX}.cp1-my.localhost.dataplanes.pro/cp/login"
MAIL_URL = "https://mail.localhost.dataplanes.pro/#/"
ADMIN_URL = "https://admin.cp1-my.localhost.dataplanes.pro/admin/login"

playwright = sync_playwright().start()
browser = playwright.chromium.launch(headless=IS_HEADLESS)
context = browser.new_context(
    viewport={"width": 2000, "height": 1080},
    accept_downloads=True
)
page = context.new_page()
def close_browser():
    global browser
    browser.close()
    ColorLogger.success("Browser Closed Successfully.")

def print_env_info():
    str_num = 80
    print("=" * str_num)
    print(f"{'CREDENTIALS':^50}")
    print("=" * str_num)

    print(f"{'Mail URL:':<20}{MAIL_URL}")
    print("-" * str_num)
    print(f"{'Login URL:':<20}{LOGIN_URL}")
    print(f"{'User Email:':<20}{USER_EMAIL}")
    print(f"{'User Password:':<20}{USER_PASSWORD}")
    print("-" * str_num)
    print(f"{'Admin URL:':<20}{ADMIN_URL}")
    print(f"{'Admin Email:':<20}{ADMIN_EMAIL}")
    print(f"{'Admin Password:':<20}{ADMIN_PASSWORD}")
    print("-" * str_num)
    print(f"{'DataPlane:':<20}{DATAPLANE_NAME}")
    print(f"{'App Name:':<20}{get_app_name()}")
    print("=" * str_num)

def check_dom_visibility(dom_selector, interval=20, max_wait=180, is_refresh=False):
    total_attempts = max_wait // interval
    for attempt in range(total_attempts):
        print(f"Attempt {attempt + 1}/{total_attempts}: Checking if dom is visible...")

        if dom_selector.is_visible():
            print("Dom is now visible.")
            return True

        if attempt < total_attempts - 1:
            print(f"Dom not visible. Waiting for {interval} seconds before retrying...")
            page.wait_for_timeout(interval * 1000)
            if is_refresh:
                print(f"Page reload {attempt + 1}")
                page.reload()

    ColorLogger.error(f"Error: Dom is still not visible after waiting for {max_wait} seconds.")
    return False

def active_user_in_mail(email, is_admin=False):
    email_title = "Your TIBCO® Platform subscription has been activated"
    first_name = email.split("@")[0]
    last_name = "Auto"
    password = USER_PASSWORD
    if is_admin:
        ColorLogger.warning(f"Admin user {ADMIN_EMAIL} has not been active, active Admin in mail.")
        email_title = "Your TIBCO® Platform Console subscription has been activated"
        first_name = "Admin"
        last_name = "Test"
        password = ADMIN_PASSWORD

    ColorLogger.info("Check email and active user...")
    try:
        response = page.goto(MAIL_URL, timeout=5000)
        if response and response.status == 200:
            print(f"URL {MAIL_URL} is accessible")
    except Exception as e:
        print(f"An error occurred while accessing {MAIL_URL}: {e}")
        sys.exit(f"Exiting program: An error occurred while accessing {MAIL_URL}")

    page.goto(MAIL_URL)
    print(f"Navigating to mail page {MAIL_URL}...")
    page.reload()

    email_selector = page.locator(".email-list .email-item-link", has_text=email_title).nth(0)
    email_selector.wait_for()
    if not email_selector.locator(".title-subline", has_text=email).is_visible():
        ColorLogger.error(f"Active Email for {email} is not found.")
        sys.exit(f"Exiting program: Active Email for {email} is not found.")

    email_selector.click()
    page.wait_for_timeout(1000)
    iframe = page.frame_locator(".main-container iframe.preview-iframe").nth(0)
    iframe.locator("a.btn-activate", has_text="Sign in").wait_for()

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
        ColorLogger.info(f"User {email} may active.")

    new_page.close()

def login_admin_user():
    ColorLogger.info("Login as admin user...")
    page.goto(ADMIN_URL)
    print(f"Navigating to admin page {ADMIN_URL}...")

    page.locator("#ta-sign-in-button", has_text="Sign in with Default IdP").wait_for()
    page.locator("#ta-sign-in-button", has_text="Sign in with Default IdP").click()
    page.fill("#user-email", ADMIN_EMAIL)
    page.fill("#usr-password", ADMIN_PASSWORD)
    page.locator("#user-login-btn").click()
    if page.locator("#toastr401", has_text="Invalid username or password").is_visible():
        ColorLogger.error(f"Admin user {ADMIN_EMAIL}, {ADMIN_PASSWORD} login failed.")
        return

    page.wait_for_timeout(1000)
    if page.locator("#ta-sign-in-button", has_text="Sign in with Default IdP").is_visible():
        page.locator("#ta-sign-in-button", has_text="Sign in with Default IdP").click()

    page.locator(".pcp-page-title", has_text="Welcome").wait_for()
    ColorLogger.success(f"Admin user {ADMIN_EMAIL} login successful.")

def logout_admin_user():
    page.locator("#changeME-dropdown-label", has_text="Admin Test").click()
    page.locator(".pl-dropdown-menu .pl-dropdown-menu__link", has_text="Sign Out").click()
    page.locator(".pl-modal__container .pl-modal__footer button", has_text="Sign Out").click()
    print(f"Clicked Sign Out button, Admin user {ADMIN_EMAIL} logout.")
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
        page.locator(".footer button", has_text="Ok").wait_for()
        page.locator(".footer button", has_text="Ok").click()
        print("Clicked 'Ok' button")
        if page.locator(".provision-success__subtext", has_text="host_prefix has been used in another account").is_visible():
            ColorLogger.error(f"Host prefix: {host_prefix} has been used in another account.")
            logout_admin_user()
            sys.exit(f"Exiting program: Host prefix: {host_prefix} has been used in another account, use another one or rest database.")
        ColorLogger.success(f"Provision user {email} successful.")

    logout_admin_user()
    ColorLogger.success(f"Admin user {ADMIN_EMAIL} logout successful.")

def is_host_prefix_exist(host_prefix):
    try:
        login()

        page.wait_for_timeout(500)
        if page.locator(".dashboard .title", has_text="Welcome!").is_visible():
            logout()
            ColorLogger.success(f"Host prefix {host_prefix} is already exist.")
            return True
        else:
            return False

    except Exception as e:
        print(f"An error occurred while accessing {LOGIN_URL}: {e}")
        ColorLogger.error(f"An error occurred while verify host prefix in {LOGIN_URL}: {USER_EMAIL}, {USER_PASSWORD}")
        return False

def is_admin_user_exist():
    try:
        login_admin_user()
        if page.locator(".pcp-page-title", has_text="Welcome").is_visible():
            logout_admin_user()
            return True
        else:
            return False
    except Exception as e:
        print(f"An error occurred while accessing {ADMIN_URL}: {e}")
        ColorLogger.error(f"An error occurred while verify admin user in {ADMIN_URL}: {ADMIN_EMAIL}, {ADMIN_PASSWORD}")
        return False

def get_app_name(app_name=FLOGO_APP, is_lower=True):
    file_path = os.path.join(os.path.dirname(__file__), app_name)
    with open(file_path, "r") as f:
        flogo_json = json.load(f)
        app_name = flogo_json["name"]

    if app_name == "":
        ColorLogger.error(f"The app name is empty in file {file_path}.")
        sys.exit(f"Exiting program: The app name is empty in file {file_path}.")
    return app_name.lower() if is_lower else app_name

def login():
    ColorLogger.info(f"Navigating to login page {LOGIN_URL}...")
    page.goto(LOGIN_URL)
    page.wait_for_selector('#ta-sign-in-button')
    page.locator("#ta-sign-in-button", has_text="Sign in with Default IdP").click()

    print("Logging in...")
    page.fill("#user-email", USER_EMAIL)
    page.fill("#usr-password", USER_PASSWORD)
    page.click("#user-login-btn")
    if page.locator("#toastr401", has_text="Invalid username or password").is_visible():
        ColorLogger.error(f"User {USER_EMAIL}, {USER_PASSWORD} login {LOGIN_URL} failed.")
        return

    page.wait_for_selector('#user-profile')
    ColorLogger.success("Login successful!")

def logout():
    print(f"Logging out user {USER_EMAIL}...")
    page.locator("#nav-bar-menu-list-signout").click()
    # Note: there are 3 buttons has "Sign Out" label, so we need to use nth(2) to click the last one
    page.locator("#confirm-button", has_text="Sign Out").nth(2).wait_for()
    page.locator("#confirm-button", has_text="Sign Out").nth(2).click()
    ColorLogger.success(f"Clicked Sign Out button, User {USER_EMAIL} logout.")
    page.wait_for_timeout(1000)

def grant_permission(permission):
    page.locator(".policy-description", has_text=permission).click()
    # check if input aria-checked="true" does not exist, then click
    is_selected = page.locator('.dp-selector-container input').get_attribute("aria-checked")
    print(f"Permission {permission} is selected: {is_selected}")
    if is_selected != "true":
        page.locator('.dp-selector-container label').click()
        print("Grant permission for " + permission)

def set_user_permission():
    ColorLogger.info("Checking if user has permission...")
    page.click("#nav-bar-menu-list-dataPlanes")
    page.locator("#register-dp-button").wait_for()
    if not page.locator("#register-dp-button").is_disabled():
        ColorLogger.success(f"User {USER_EMAIL} already has all permissions.")
        return

    ColorLogger.info("Setting user permission...")
    page.click("#nav-bar-menu-item-usrMgmt")
    page.click("#users-menu-item")
    page.wait_for_selector(f'.user-name-text[id="go-to-user-details-{USER_EMAIL}"]')
    print(f"{USER_EMAIL} is found.")
    # check if user has all permissions
    page.locator(f'.user-name-text[id="go-to-user-details-{USER_EMAIL}"]').click()
    page.wait_for_timeout(1000)
    print(f"Assign Permissions for {USER_EMAIL}")
    # if table.permissions has 8 rows, then exit this function
    if page.locator("table.permissions .pl-table__row").count() == 8:
        ColorLogger.success(f"User {USER_EMAIL} already has all permissions.")
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
        ColorLogger.success(f"Grant All permission to {USER_EMAIL}")
    else:
        ColorLogger.success(f"User {USER_EMAIL} already has all permissions.")

def create_k8s_dataplane(dp_name):
    dp_namespace = dp_name + "ns"
    dp_service_account = dp_name + "sa"
    ColorLogger.info(f"Creating k8s data plane '{dp_name}'...")
    page.click("#nav-bar-menu-list-dataPlanes")
    # wait for 1 seconds
    page.wait_for_timeout(500)

    if page.locator(".data-plane-name").count() > MAX_DATA_PLANES:
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
    page.fill("#namespace-text-input", dp_namespace)
    print(f"Input NameSpace: {dp_namespace}")
    page.fill("#service-account-text-input", dp_service_account)
    print(f"Input Service Account: {dp_service_account}")
    page.click("#data-plane-namespace-btn")
    print("Finish step 2 Namespace & Service account")

    # step 3 Configuration

    if GITHUB_TOKEN == "":
        ColorLogger.info("GITHUB_TOKEN is empty, choose 'Global Repository'")
        page.locator('label[for="helm-chart-repo-global"]').click()
    else:
        ColorLogger.info("GITHUB_TOKEN is set, choose 'Custom Helm Chart Repository'")
        page.locator('label[for="helm-chart-repo-custom"]').click()

        page.fill("#alias-input", f"tp-private-{dp_name}")
        page.fill("#url-input", "https://raw.githubusercontent.com")
        page.fill("#repo-input", "tibco/tp-helm-charts/gh-pages")
        page.fill("#username-input", "cp-test")
        page.fill("#password-input", GITHUB_TOKEN)

    page.click("#data-plane-config-btn")
    print("Finish step 3 Configuration")

    # step 4 Preview
    page.click("#data-plane-preview-btn")
    print("Finish step 4 Preview")

    # step 5 Register Data Plane
    page.wait_for_selector("#data-plane-finished-btn")

    print("Download step 1: Helm Repository configuration")
    with page.expect_download() as download_info:
        page.locator(".cluster #download-commands").nth(0).click()

    download = download_info.value
    file_name = Util.dp_step_file(dp_name, 1)
    download.save_as(file_name)
    Util.run_shell_script(file_name)

    print("Download step 2: Namespace creation")
    with page.expect_download() as download_info:
        page.locator(".namespace #download-commands").click()

    download = download_info.value
    file_name = Util.dp_step_file(dp_name, 2)
    download.save_as(file_name)
    Util.run_shell_script(file_name)

    print("Download step 3: Service Account creation")
    with page.expect_download() as download_info:
        page.locator(".service-account #download-commands").click()

    download = download_info.value
    file_name = Util.dp_step_file(dp_name, 3)
    download.save_as(file_name)
    Util.run_shell_script(file_name)

    print("Download step 4: Cluster Registration")
    with page.expect_download() as download_info:
        page.locator(".cluster #download-commands").nth(1).click()

    download = download_info.value
    file_name = Util.dp_step_file(dp_name, 4)
    download.save_as(file_name)
    Util.run_shell_script(file_name)

    # click Done button
    page.click("#data-plane-finished-btn")
    print("Clicked 'Done' button")
    page.locator('#confirm-button', has_text="Yes").wait_for()
    page.locator('#confirm-button', has_text="Yes").click()

    # verify data plane is created in the list
    print(f"Verify data plane {dp_name} is created in the list")
    page.locator('.data-plane-name', has_text=dp_name).wait_for()
    ColorLogger.success(f"DataPlane {dp_name} is created.")

def go_to_dataplane_o11y_sub(menu_name):
    menu_dom_selector = "#left-sub-menu li a"
    page.locator(menu_dom_selector, has_text=menu_name).wait_for()
    if not page.locator(menu_dom_selector, has_text=menu_name).is_visible():
        ColorLogger.error(f"Navigate to data plane Observability page first.")
        return

    page.locator(menu_dom_selector, has_text=menu_name).click()
    print(f"Clicked 'Observability -> {menu_name}' left side menu")

def get_name_input(dp_name, menu_name, tab_name, is_system, name_input="", table_index=0):
    if name_input == "":
        tab = tab_name.lower()
        words = tab_name.split()
        if len(words) > 1:
            tab = ''.join(word[0].lower() for word in words)

        if dp_name == "" and is_system:
            name_input = f"_system$GLOBAL_{menu_name.upper()}_{tab.upper()}"
        else:
            index = page.locator("proxies-exporters-list table").nth(table_index).locator("tbody tr").count() + 1
            if dp_name == "":
                name_input = f"GLOBAL_{menu_name}-{tab}".upper()
            else:
                name_input = f"{dp_name}-{menu_name}-{tab}-{index}".lower()

    return name_input

# when dp_name is empty, it means global data plane
def fill_o11y_form(dp_name, menu_name, tab_name, is_system, name_input="", table_index=0):
    name_input = get_name_input(dp_name, menu_name, tab_name, is_system, name_input, table_index)

    # check if proxies-exporters-list first table's any td has name_input, then exit this function
    if page.locator("proxies-exporters-list table").nth(table_index).locator("td", has_text=name_input).is_visible():
        ColorLogger.success(f"The {name_input} is already exist.")
        return

    page.locator("proxies-exporters-list button", has_text="Add").nth(table_index).click()
    print(f"Clicked 'Observability -> {menu_name} -> {tab_name} -> Add' button")

    page.wait_for_selector("configuration-modal .pl-modal")
    page.fill("#config-name-input", name_input)
    page.locator("configuration-modal input.pl-select__control").click()

    if menu_name == "Metrics":
        page.locator("configuration-modal .pl-select-menu__item", has_text="Prometheus").click()
        if tab_name == "Query Service":
            page.fill("#endpoint-input", "https://prometheus-internal.localhost.dataplanes.pro/")
    elif menu_name == "Traces":
        page.locator("configuration-modal .pl-select-menu__item", has_text="ElasticSearch").click()
        page.fill("#endpoint-input", "https://elastic.localhost.dataplanes.pro/")
    else:
        page.locator("configuration-modal .pl-select-menu__item", has_text="ElasticSearch").click()
        page.fill("#log-index-input", name_input)
        page.fill("#endpoint-input", "https://elastic.localhost.dataplanes.pro/")
        page.fill("#username-input", "elastic")
        page.fill("#password-input", Util.get_elastic_password())

    page.locator("configuration-modal .pl-modal__footer-left button.pl-button--primary").click()
    page.wait_for_timeout(1000)
    if page.locator(".pl-notification__message").is_visible():
        page.locator("configuration-modal .pl-modal__footer-left button", has_text="Cancel").click()
        ColorLogger.success(f"The {name_input} is already exist.")

    ColorLogger.success(f"Added {name_input} for data plane '{dp_name}' Observability -> {menu_name} -> {tab_name}")

def o11y_add_query(dp_name, menu_name, is_system=False, name_input=""):
    tab_name = "Query Service"
    page.locator(".stepper a", has_text=tab_name + " configurations").click()
    fill_o11y_form(dp_name, menu_name, tab_name, is_system, name_input, 0)

def o11y_add_exporter(dp_name, menu_name, is_system=False, name_input=""):
    tab_name = "Exporter"
    page.locator(".stepper a", has_text=tab_name + " configurations").click()
    fill_o11y_form(dp_name, menu_name, tab_name, is_system, name_input, 0)

def o11y_log_add_exporter_ua(dp_name, is_system=False, name_input=""):
    tab_name = "Exporter"
    page.locator(".stepper a", has_text=tab_name + " configurations").click()
    fill_o11y_form(dp_name, "Logs", tab_name + ' User Apps', is_system, name_input, 0)

def o11y_log_add_exporter_service(dp_name, is_system=False, name_input=""):
    tab_name = "Exporter"
    page.locator(".stepper a", has_text=tab_name + " configurations").click()
    fill_o11y_form(dp_name, "Logs", tab_name + ' Services', is_system, name_input, 1)

def goto_dataplane(dp_name):
    ColorLogger.info(f"Config k8s data plane '{dp_name}'...")
    page.click("#nav-bar-menu-list-dataPlanes")
    # wait for 1 seconds
    page.wait_for_timeout(1000)

    if not page.locator('.data-plane-name', has_text=dp_name).is_visible():
        ColorLogger.error(f"DataPlane {dp_name} does not exist")
        sys.exit(f"Exiting program: DataPlane {dp_name} does not exist")

    page.locator('data-plane-card', has=page.locator('.data-plane-name', has_text=dp_name)).locator('button', has_text="Go to Data Plane").click()
    print("Clicked 'Go to Data Plane' button")
    page.locator('.domain-data-title', has_text=dp_name).wait_for()
    ColorLogger.info(f"Navigate to data plane '{dp_name}' page")
    page.wait_for_timeout(1000)

def goto_dataplane_config():
    page.locator("#ct-dp-config-link").click()
    print("Clicked 'Data Plane configuration' button")
    page.wait_for_timeout(500)

def config_system_dataplane_o11y():
    goto_global_dataplane()
    config_dataplane_o11y("", True)

def config_global_dataplane_o11y():
    goto_global_dataplane()
    config_dataplane_o11y("", False)

def config_dataplane_o11y(dp_name="", is_system=False):
    page.locator("#left-sub-menu .menu-item-text", has_text="Observability").click()
    print("Clicked 'Observability' left side menu")
    # no system config for Logs if is_system is True
    if not is_system:
        go_to_dataplane_o11y_sub("Logs")
        o11y_add_query(dp_name, "Logs", is_system)
        o11y_log_add_exporter_ua(dp_name, is_system)
        o11y_log_add_exporter_service(dp_name, is_system)

    go_to_dataplane_o11y_sub("Metrics")
    o11y_add_query(dp_name, "Metrics", is_system)
    o11y_add_exporter(dp_name, "Metrics", is_system)

    go_to_dataplane_o11y_sub("Traces")
    o11y_add_query(dp_name, "Traces", is_system)
    o11y_add_exporter(dp_name, "Traces", is_system)

def config_dataplane_o11y_resource(dp_name=""):
    page.locator("#left-sub-menu .menu-item-text", has_text="Observability").click()
    print("Clicked 'Observability' left side menu")
    page.wait_for_timeout(500)
    if not page.locator("observability-data-plane .o11y-btn .add-dp-o11y-icon").is_visible():
        ColorLogger.success(f"Data plane '{dp_name}' Observability has been configured.")
        return

    page.locator("observability-data-plane .o11y-btn .add-dp-o11y-icon").click()
    print("Clicked 'Create new Data Plane Resources' button")
    page.locator('.configuration').wait_for()
    print("Config o11y page is loaded")
    page.locator("#go-to-metrics-server-configuration").click()
    page.locator("#go-to-traces-configuration").click()
    page.locator("#save-observability").click()
    ColorLogger.success(f"Data plane '{dp_name}' Observability is configured.")

def config_resources_storage():
    ColorLogger.info("Config Resources Storage...")
    page.locator("#resources-menu-item .menu-item-text", has_text="Resources").click()
    print("Clicked 'Resources' left side menu")
    resource_name = Util.get_resource_name()
    print(f"Resource Name: {resource_name}")
    if page.locator("#storage-resource-table tr td", has_text=resource_name).count() > 0:
        ColorLogger.success(f"Storage '{resource_name}' is already created.")
    else:
        page.locator("#add-storage-resource-btn").click()
        page.locator('.pl-modal__header', has_text="Add Storage").wait_for()
        page.fill('#resourceName-input', resource_name)
        page.fill('#description-input', resource_name)
        page.fill('#storageClassName-input', resource_name)
        page.locator("#save-storage-configuration").click()
        ColorLogger.success(f"Add Storage '{resource_name}' successfully.")

def config_resources_ingress():
    ColorLogger.info("Config Resources Ingress...")
    page.locator("#resources-menu-item .menu-item-text", has_text="Resources").click()
    print("Clicked 'Resources' left side menu")
    page.locator("#toggle-ingress-expansion").click()
    resource_name = "nginx"
    if page.locator("#ingress-resource-table tr td", has_text=resource_name).count() > 0:
        ColorLogger.success(f"Ingress Controller '{resource_name}' is already created.")
    else:
        page.locator(".ingress .add-resource-btn button").click()
        page.locator('.pl-modal__header', has_text="Add Ingress Controller").wait_for()
        page.fill('#resourceName-input', resource_name)
        page.fill('#ingressClassName-input', resource_name)
        page.fill('#fqdn-input', "flogo.localhost.dataplanes.pro")
        page.locator("#save-ingress-configuration").click()
        ColorLogger.success(f"Add Ingress Controller '{resource_name}' successfully.")

def goto_global_dataplane():
    ColorLogger.info(f"Config Global data plane...")
    page.click("#nav-bar-menu-list-dataPlanes")
    # wait for 1 seconds
    page.wait_for_timeout(1000)

    page.locator(".global-configuration button").click()
    print("Clicked 'Global configuration' button")
    page.locator('.global-configuration breadcrumbs a', has_text="Global configuration").wait_for()
    ColorLogger.info(f"Navigate to Global data plane page")

def goto_flogo_capability(dp_name):
    is_exit = False
    goto_dataplane(dp_name)
    ColorLogger.info("Check if Flogo capability is ready...")
    if check_dom_visibility(page.locator("capability-card #flogo"), 10, 120, True):
        ColorLogger.info("Waiting for Flogo capability status is ready...")
        if check_dom_visibility(page.locator("capability-card #flogo .status .success")):
            page.locator("capability-card #flogo .image-name").click()
            print("Flogo capability status is ready, get into 'Flogo' capability")
            page.wait_for_timeout(1000)
        else:
            ColorLogger.error("Flogo capability is provisioned, but status is not ready.")
            is_exit = True
    else:
        ColorLogger.error("Flogo capability is not provisioned yet.")
        is_exit = True

    if is_exit:
        sys.exit("Exiting program: Flogo capability is not provisioned yet.")

def goto_app_detail(dp_name, app_name):
    app_name = app_name if app_name else get_app_name()

    goto_dataplane(dp_name)
    if not page.locator("apps-list td.app-name a", has_text=app_name).is_visible():
        ColorLogger.error(f"The app '{app_name}' is not deployed yet.")
        sys.exit(f"Exiting program: The app '{app_name}' is not deployed yet.")

    page.locator("apps-list td.app-name a", has_text=app_name).click()
    print(f"Clicked app '{app_name}'")
    page.locator(".app-name-section .name", has_text=app_name).wait_for()
    ColorLogger.info(f"Navigate to app '{app_name}' detail page")

def provision_flogo_capability(dp_name):
    goto_dataplane(dp_name)
    ColorLogger.info("Provisioning Flogo capability...")
    if page.locator("capability-card #flogo").is_visible():
        ColorLogger.success("Flogo capability is already provisioned.")
        return

    if check_dom_visibility(page.locator('button', has_text="Provision a capability")):
        page.locator('button', has_text="Provision a capability").click()
        print("Clicked 'Provision a capability' button")
        page.locator('#FLOGO-capability-select-button').wait_for()
        page.locator('#FLOGO-capability-select-button').click()
        print("Clicked 'Provision TIBCO Flogo® Enterprise' -> 'Start' button")

        page.locator('#storage-class-resource-table tr', has=page.locator('td', has_text="hostpath")).locator('label').click()
        print("Selected 'hostpath' Storage Class")
        page.locator('#ingress-resource-table tr', has=page.locator('td', has_text="nginx")).locator('label').click()
        print("Selected 'nginx' Ingress Controller")

        page.locator("#btnNextCapabilityProvision").click()
        page.locator(".eula-container input").click()
        page.locator("#qaProvisionFlogo").click()
        ColorLogger.success("Provision Flogo capability successful.")
    else:
        ColorLogger.error("'Provision a capability' button is not visible.")
        sys.exit("Exiting program: Flogo capability is not provisioned yet.")

def provision_flogo_connector(dp_name):
    # program will exit if Flogo capability is not provisioned yet
    goto_flogo_capability(dp_name)
    ColorLogger.info("Provisioning Flogo connectors...")

    if page.locator(".capability-connectors-container .total-capability", has_text="(4)").is_visible():
        ColorLogger.success("Flogo connectors are already provisioned.")
        return

    page.locator(".capability-buttons", has_text="Provision Flogo & Connectors").click()
    print("Clicked 'Provision Flogo & Connectors' button")
    page.locator(".versions-container label", has_text="HTTP").wait_for()
    page.locator(".versions-container label", has_text="HTTP").click()
    page.locator(".versions-container label", has_text="Websocket").scroll_into_view_if_needed()
    page.locator(".versions-container label", has_text="Websocket").click()
    print("Selected 'HTTP' and 'Websocket' connectors")
    page.locator("#qaPluginProvision").click()
    print("Clicked 'Provision' button")
    page.locator("flogo-plugins-provision-finish .complete").wait_for()
    ColorLogger.success("Provision Flogo & Connectors successful.")
    page.locator(".finish-buttons-container button", has_text="Go back to Data Plane details").click()
    print("Clicked 'Go back to Data Plane details' button")

def flogo_app_build_and_deploy(dp_name):
    # program will exit if Flogo capability is not provisioned yet
    goto_flogo_capability(dp_name)
    ColorLogger.info("Start Create Flogo app build...")
    app_original_name = get_app_name(FLOGO_APP, False)

    if page.locator(".app-build-container td", has_text=app_original_name).is_visible():
        ColorLogger.success(f"Flogo app build {app_original_name} is already created.")
        return

    ColorLogger.info("Creating Flogo app build...")
    page.locator(".capability-buttons", has_text="Create New App Build And Deploy").click()
    print("Clicked 'Create New App Build And Deploy' button")

    # step1: Upload Files
    file_path = os.path.join(os.path.dirname(__file__), FLOGO_APP)
    page.locator('input[type="file"]').evaluate("(input) => input.style.display = 'block'")

    page.locator('input[type="file"]').set_input_files(file_path)
    print(f"Selected file: {file_path}")
    page.locator('app-upload-file .dropzone-file-name', has_text=FLOGO_APP).wait_for()
    page.locator('#qaUploadApp').click()
    print("Clicked 'Upload' button")
    page.locator('flogo-deploy-upload-app .upload-main-title', has_text="File Uploaded Successfully").wait_for()
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
    page.locator("flogo-namespace-picker .namespace-dropdown li", has_text=f"{dp_name}ns").click()
    print(f"Selected namespace: {dp_name}ns")
    page.locator(".eula-container").click()
    print("Clicked 'EUA' checkbox")
    page.locator('#qaNextAppDeploy').click()
    print("Clicked 'Next' button")

    # step3: Resource Configuration
    page.locator('#qaResourceAppDeploy').click()
    print("Clicked 'Deploy App' button")

    # step4: Finished
    page.locator('.finish-container .deploy-banner-icon').wait_for()
    ColorLogger.success(f"Created Flogo app build '{app_original_name}' Successfully")

def flogo_app_deploy(dp_name):
    dp_name_space = dp_name + "ns"
    app_original_name = get_app_name(FLOGO_APP, False)
    app_name = app_original_name.lower()

    goto_dataplane(dp_name)
    if page.locator("apps-list td.app-name a", has_text=app_name).is_visible():
        ColorLogger.success(f"Flogo app '{app_name}' in namespace {dp_name_space} is already deployed.")
        return

    # program will exit if Flogo capability is not provisioned yet
    goto_flogo_capability(dp_name)
    ColorLogger.info("Deploying Flogo app ...")

    print(f"Waiting for Flogo app build {app_original_name} is deployed...")
    if not check_dom_visibility(page.locator(".app-build-container td", has_text=app_original_name), 20, 180, True):
        ColorLogger.error(f"Flogo app {app_original_name} is not deployed.")
        sys.exit(f"Exiting program: Flogo app {app_original_name} is not deployed.")

    page.locator(".app-build-container tr", has=page.locator("td", has_text=app_original_name)).nth(0).locator('flogo-app-build-actions button[data-pl-dropdown-role="toggler"]').click()
    print(f"Clicked action menu button for {app_original_name}")
    page.locator(".app-build-container tr", has=page.locator("td", has_text=app_original_name)).nth(0).locator('flogo-app-build-actions .action-menu button', has_text="Deploy").click()
    print(f"Clicked 'Deploy' from action menu list for {app_original_name}")

    page.locator(".pl-modal__footer-right button", has_text="Deploy App Build").wait_for()
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
    print(f"Clicked menu navigator data plane '{dp_name}'")

    if check_dom_visibility(page.locator("apps-list td.app-name a", has_text=app_name), 10, 60):
        ColorLogger.success(f"Deploy Flogo app '{app_name}' in namespace {dp_name_space} Successfully")
    else:
        ColorLogger.error(f"Deploy Flogo app '{app_name}' in namespace {dp_name_space} failed.")

def start_flogo_app(dp_name, app_name):
    goto_app_detail(dp_name, app_name)

    if page.locator("flogo-app-run-status .scale-status-text", has_text="Stopped").is_visible():
        page.locator("flogo-app-run-status button", has_text="Start").click()
        print("Clicked 'Start' app button")

        print(f"Waiting for app '{app_name}' status is Running...")
        if check_dom_visibility(page.locator("flogo-app-run-status .scale-status-text", has_text="Running")):
            ColorLogger.success(f"Flogo app '{app_name}' is started successfully.")
        else:
            ColorLogger.error(f"Failed to start Flogo app '{app_name}'.")
    else:
        ColorLogger.success(f"Flogo app '{app_name}' is already running.")

if __name__ == "__main__":
    if not is_host_prefix_exist(HOST_PREFIX):
        if not is_admin_user_exist():
            active_user_in_mail(ADMIN_EMAIL, True)
        admin_provision_user(USER_EMAIL, HOST_PREFIX)
        active_user_in_mail(USER_EMAIL)

    login()
    set_user_permission()

    create_k8s_dataplane(DATAPLANE_NAME)

    # config_system_dataplane_o11y()
    # config_global_dataplane_o11y()
    #
    goto_dataplane(DATAPLANE_NAME)
    goto_dataplane_config()
    # config_dataplane_o11y(DATAPLANE_NAME)
    #
    # config_dataplane_o11y_resource(DATAPLANE_NAME)
    config_resources_storage()
    config_resources_ingress()
    provision_flogo_capability(DATAPLANE_NAME)
    provision_flogo_connector(DATAPLANE_NAME)
    flogo_app_build_and_deploy(DATAPLANE_NAME)
    flogo_app_deploy(DATAPLANE_NAME)
    start_flogo_app(DATAPLANE_NAME, get_app_name())
    logout()
    print_env_info()

close_browser()
