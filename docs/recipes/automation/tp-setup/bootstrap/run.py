import os

from color_logger import ColorLogger
from page_auth import login, login_check, logout
from util import Util
from helper import Helper
from env import ENV
from report import ReportYaml

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
    page.locator(f'.user-name-text[id="go-to-user-details-{ENV.DP_USER_EMAIL}"]').wait_for(state="visible")
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
        Util.exit_error("Too many data planes, please delete some data planes first.", page, "k8s_create_dataplane.png")

    if page.locator('.data-plane-name', has_text=dp_name).is_visible():
        ReportYaml.set_dataplane(dp_name)
        ColorLogger.success(f"DataPlane '{dp_name}' is already created.")
        return

    page.click("#register-dp-button")
    page.click("#select-existing-dp-button")
    # step 1 Basic
    page.fill("#data-plane-name-text-input", dp_name)
    print(f"Input Data Plane Name: {dp_name}")
    page.locator('label[for="eua-checkbox"]').click()
    page.click("#data-plane-basics-btn")
    print("Clicked Next button, Finish step 1 Basic")

    # step 2 Namespace & Service account
    page.fill("#namespace-text-input", ENV.TP_AUTO_K8S_DP_NAMESPACE)
    print(f"Input NameSpace: {ENV.TP_AUTO_K8S_DP_NAMESPACE}")
    page.fill("#service-account-text-input", ENV.TP_AUTO_K8S_DP_SERVICE_ACCOUNT)
    print(f"Input Service Account: {ENV.TP_AUTO_K8S_DP_SERVICE_ACCOUNT}")
    page.click("#data-plane-namespace-btn")
    print("Clicked Next button, Finish step 2 Namespace & Service account")

    # step 3 Configuration
    if page.locator('label[for="helm-chart-repo-global"]').is_visible():
        if ENV.GITHUB_TOKEN == "":
            print("GITHUB_TOKEN is empty, choose 'Global Repository'")
            page.locator('label[for="helm-chart-repo-global"]').click()
        else:
            print("GITHUB_TOKEN is set, choose 'Custom Helm Chart Repository'")
            if page.locator('label[for="helm-chart-repo-custom"]').is_visible():
                page.locator('label[for="helm-chart-repo-custom"]').click()
                print("Choose 'Custom Helm Chart Repository'")


            page.fill("#alias-input", f"tp-private-{dp_name}")
            print(f"Input Repository Alias: tp-private-{dp_name}")
            page.fill("#url-input", "https://raw.githubusercontent.com")
            print("Input Registry URL: https://raw.githubusercontent.com")
            page.fill("#repo-input", "tibco/tp-helm-charts/gh-pages")
            print("Input Repository: tibco/tp-helm-charts/gh-pages")
            page.fill("#username-input", "cp-test")
            print("Input Username: cp-test")
            page.fill("#password-input", ENV.GITHUB_TOKEN)
            print(f"Input Password: {ENV.GITHUB_TOKEN}")

    page.click("#data-plane-config-btn")
    print("Clicked Next button, Finish step 3 Configuration")

    # step Preview (for 1.4 and above)
    if page.locator("#data-plane-preview-btn").is_visible():
        page.click("#data-plane-preview-btn")
        print("Clicked Next button, Finish step 4 Preview")

    # step Register Data Plane
    print("Check if create Data Plane is successful...")
    if not Util.check_dom_visibility(page, page.locator("#data-plane-finished-btn"), 3, 30):
        Util.exit_error(f"Data Plane '{dp_name}' creation failed.", page, "k8s_create_dataplane_finish.png")

    download_commands = page.locator("#download-commands")
    # command_count = download_commands.count()
    # commands_title = ["Namespace creation", "Service Account creation", "Cluster Registration"]
    commands_title = page.locator(".register-data-plane p.title").all_text_contents()
    print("commands_title:", commands_title)

    # for different release version: 1.3 => 3 commands, 1.4 and above => 4 commands
    # If the command count is more than 3, add Helm Repository configuration as the first command
    # if command_count > 3:
    #     commands_title.insert(0, "Helm Repository configuration")

    # Execute each command dynamically based on its position
    for index, step_name in enumerate(commands_title):
        # if index < command_count:
        k8s_run_dataplane_command(dp_name, step_name, download_commands.nth(index), index + 1)

    # click Done button
    page.click("#data-plane-finished-btn")
    print("Data Plane create successful, clicked 'Done' button")
    page.locator('#confirm-button', has_text="Yes").wait_for(state="visible")
    page.locator('#confirm-button', has_text="Yes").click()

    # verify data plane is created in the list
    page.wait_for_timeout(2000)
    print(f"Verifying Data Plane {dp_name} is created in the list")
    k8s_wait_tunnel_connected(dp_name)

def k8s_run_dataplane_command(dp_name, step_name, download_selector, step):
    ColorLogger.info(f"Running command for: {step_name}")
    print(f"Download: {step_name}")
    with page.expect_download() as download_info:
        download_selector.click()

    file_name = f"{dp_name}_{step}.sh"
    file_path = Util.download_file(download_info.value, file_name)

    print(f"Run command for: {step_name}")
    Helper.run_shell_file(file_path)
    print(f"Command for step: {step_name} is executed, wait for 3 seconds.")
    page.wait_for_timeout(3000)

def k8s_wait_tunnel_connected(dp_name):
    print(f"Waiting for Data Planes {dp_name} tunnel connected.")
    goto_left_navbar("Data Planes")
    print(f"Navigated to Data Planes list page, and checking for {dp_name} in created and tunnel connected.")
    page.locator('.data-plane-name', has_text=dp_name).wait_for(state="visible")
    if not page.locator('.data-plane-name', has_text=dp_name).is_visible():
        Util.exit_error(f"DataPlane {dp_name} is not created.", page, "k8s_wait_tunnel_connected_1.png")

    ColorLogger.success(f"DataPlane {dp_name} is created, waiting for tunnel connected.")
    ReportYaml.set_dataplane(dp_name)
    data_plane_card = page.locator(".data-plane-card", has=page.locator('.data-plane-name', has_text=dp_name))
    print(f"Waiting for DataPlane {dp_name} tunnel connected...")
    if not Util.check_dom_visibility(page, data_plane_card.locator('.tunnel-status svg.green'), 10, 180):
        Util.exit_error(f"DataPlane {dp_name} tunnel is not connected, exit program and recheck again.", page, "k8s_wait_tunnel_connected_2.png")

    ColorLogger.success(f"DataPlane {dp_name} tunnel is connected.")

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
        Util.exit_error(f"DataPlane {dp_name} does not exist", page, "goto_dataplane.png")

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

def goto_app_detail(dp_name, app_name):
    ColorLogger.info(f"Going to app '{app_name}' detail page")
    goto_dataplane(dp_name)
    if not page.locator("apps-list td.app-name a", has_text=app_name).is_visible():
        Util.exit_error(f"The app '{app_name}' is not deployed yet.", page, "goto_app_detail.png")

    page.locator("apps-list td.app-name a", has_text=app_name).click()
    print(f"Clicked app '{app_name}'")
    page.locator(".app-name-section .name", has_text=app_name).wait_for(state="visible")
    print(f"Navigated to app '{app_name}' detail page")
    page.wait_for_timeout(500)

def goto_capability(dp_name, capability, is_check_status=True):
    ColorLogger.info(f"{capability} Going to capability...")
    goto_dataplane(dp_name)
    print(f"Check if {capability} capability is ready...")
    card_id = capability.lower()
    if Util.check_dom_visibility(page, page.locator(f"capability-card #{card_id}"), 10, 120, True):
        print(f"Waiting for {capability} capability status is ready...")
        if not is_check_status:
            page.locator(f"capability-card #{card_id} .image-name").click()
            print(f"Ignore check '{capability}' capability status, get into '{capability}' capability page")
            return
        if Util.check_dom_visibility(page, page.locator(f"capability-card #{card_id} .status .success")):
            print(f"{capability} capability status is ready")
            page.locator(f"capability-card #{card_id} .image-name").click()
            print(f"Clicked '{capability}' capability")
        else:
            Util.exit_error(f"{capability} capability is provisioned, but status is not ready.", page, f"{card_id}_goto_capability.png")
    else:
        Util.exit_error(f"{capability} capability is not provisioned yet.", page, f"{card_id}_goto_capability.png")

def is_capability_provisioned(capability, capability_name=""):
    ColorLogger.info(f"Checking if '{capability}' is provisioned")
    try:
        print(f"Checking if '{capability}' is already provisioned...")
        card_id = capability.lower()
        page.wait_for_timeout(3000)
        if page.locator(f"capability-card #{card_id}").is_visible():
            ColorLogger.success(f"'{capability}' is already provisioned.")
            if capability_name == "":
                return True
            else:
                if page.locator(f"capability-card #{card_id} .pl-tooltip__trigger", has_text=capability_name).is_visible():
                    ColorLogger.success(f"'{capability}' with name '{capability_name}' is provisioned.")
                    return True
                else:
                    ColorLogger.warning(f"'{capability}' with name '{capability_name}' has not been provisioned.")
                    return False
        else:
            ColorLogger.warning(f"'{capability}' has not been provisioned.")
            return False
    except Exception as e:
        ColorLogger.warning(f"An error occurred while Checking capability '{capability}': {e}")
        return False

def o11y_get_new_resource(dp_name=""):
    # For 1.4 version
    add_new_resource_button = page.locator(".add-dp-observability-btn", has_text="Add new resource")
    if page.locator(".o11y-no-config .o11y-config-buttons").is_visible():
        if dp_name == "":
            # For 1.5 Global data plane
            add_new_resource_button = page.locator(".o11y-no-config .o11y-config-buttons .add-global-o11y-icon")
        else:
            # For 1.5 none Global data plane
            add_new_resource_button = page.locator(".o11y-no-config .o11y-config-buttons .add-dp-o11y-icon").nth(0)

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

    print("Waiting for Observability config is loaded")
    if not Util.check_dom_visibility(page, page.locator(".data-plane-observability-content"), 3, 10):
        Util.exit_error(f"Data Plane '{dp_title}' Observability config load failed.", page, "o11y_config_dataplane_resource.png")

    print("Checking if 'Add new resource' button is exist...")
    page.wait_for_timeout(2000)

    add_new_resource_button = o11y_get_new_resource(dp_name)
    if not add_new_resource_button.is_visible():
        print("'Add new resource' button is not exist...")
        ColorLogger.success(f"Data plane '{dp_title}' Observability Resources is already configured.")
        ReportYaml.set_dataplane_info(dp_name, "o11yConfig", True)
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
        o11y_config_table_add_or_select_item(dp_name, menu_name, tab_name, "Query Service", "#add-userapp-proxy-btn")

    # Add or Select Logs -> User Apps -> Exporter configurations
    tab_name = "Exporter"
    if page.locator("label[for='userapp-exporter']", has_text=f"{tab_name} disabled").is_visible():
        page.locator("label[for='userapp-exporter']").click()
        print(f"Clicked '{tab_name}' toggle button")
    if page.locator("label[for='userapp-exporter']", has_text=f"{tab_name} enabled").is_visible():
        o11y_config_table_add_or_select_item(dp_name, menu_name, tab_name, "User Apps Exporter", "#add-userapp-exporter-btn")

    # Add or Select Logs -> Services -> Exporter configurations
    tab_name = "Exporter"
    if page.locator("label[for='services-exporter-toggle']", has_text=f"{tab_name} disabled").is_visible():
        page.locator("label[for='services-exporter-toggle']").click()
        print(f"Clicked '{tab_name}' toggle button")
    if page.locator("label[for='services-exporter-toggle']", has_text=f"{tab_name} enabled").is_visible():
        o11y_config_table_add_or_select_item(dp_name, menu_name, tab_name, "Services Exporter", "#add-services-exporter-btn")

    page.wait_for_timeout(500)
    page.locator("#go-to-metrics-server-configuration").click()
    print("Clicked 'Next' button")
    print(f"Data plane '{dp_title}' 'Configure Log Server' Step 1 is configured.")

    # Step 2: Configure Metrics Server
    system_toggle = page.locator("#metrics-toggle-system-config")
    if system_toggle.is_visible() and system_toggle.get_attribute("aria-checked") == "true":
        print("Metrics System Config is enabled")
        page.locator("label[for='metrics-toggle-system-config']").click()
        print("Clicked 'Metrics System Config' toggle button, then wait for 1 second.")
        page.wait_for_timeout(1000)

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
    system_toggle = page.locator("#traces-toggle-system-config")
    if system_toggle.is_visible() and system_toggle.get_attribute("aria-checked") == "true":
        print("Traces System Config is enabled")
        page.locator("label[for='traces-toggle-system-config']").click()
        print("Clicked 'Traces System Config' toggle button, then wait for 1 second.")
        page.wait_for_timeout(1000)

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
    page.wait_for_timeout(1000)
    if page.locator(".pl-notification--error").is_visible():
        Util.warning_screenshot(f"Data Plane '{dp_title}' Observability Resources configuration failed.", page, "o11y_config_dataplane_resource.png")
        page.locator("#cancel-observability-add-traces").click()
        print("Clicked 'Cancel' button")
        page.locator('#confirm-button', has_text="Yes").wait_for(state="visible")
        page.locator('#confirm-button', has_text="Yes").click()
        return

    ColorLogger.success(f"Data plane '{dp_title}' Observability Resources is configured.")
    ReportYaml.set_dataplane_info(dp_name, "o11yConfig", True)
    print(f"Wait 5 seconds for Data plane '{dp_title}' configuration page redirect.")
    page.wait_for_timeout(5000)

def o11y_config_table_add_or_select_item(dp_name, menu_name, tab_name, tab_sub_name, add_button_selector):
    ColorLogger.info("O11y start to add or select item...")
    name_input = Helper.get_o11y_sub_name_input(dp_name, menu_name, tab_name, tab_sub_name)
    print(f"Check if name: '{name_input}' is exist in {tab_sub_name} configurations")
    if not page.locator("observability-configurations table tr", has=page.locator("td", has_text=name_input)).is_visible():
        page.locator(add_button_selector).click()
        print(f"Clicked 'Add {tab_name} configuration' button in {tab_sub_name} configurations")
        o11y_new_resource_fill_form(menu_name, tab_name, tab_sub_name, name_input, dp_name)

    print(f"Waiting for '{name_input}' display in {tab_name}")
    page.locator("observability-configurations table tr", has=page.locator("td", has_text=name_input)).locator("label").wait_for(state="visible")
    page.locator("observability-configurations table tr", has=page.locator("td", has_text=name_input)).locator("label").click()
    print(f"Selected '{name_input}' in {tab_name} configurations")

# when dp_name is empty, it means global data plane
def o11y_new_resource_fill_form(menu_name, tab_name, tab_sub_name, name_input, dp_name=""):
    ColorLogger.info("O11y start to fill new resource form...")
    dp_title = dp_name if dp_name else "Global"
    print(f"Fill form for Data Plane: {dp_title} -> O11y-> {menu_name} -> {tab_name} ...")
    page.locator("configuration-modal .pl-modal").wait_for(state="visible")
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
            log_index = name_input
            if tab_sub_name == "Query Service" or tab_sub_name == "User Apps Exporter":
                log_index = f"{dp_title.lower()}-log-index"
            page.fill("#log-index-input", log_index)
            print(f"Fill Log Index: {log_index}")

        o11y_fill_prometheus_or_elastic("ElasticSearch", ENV.TP_AUTO_ELASTIC_URL, ENV.TP_AUTO_ELASTIC_USER, ENV.TP_AUTO_ELASTIC_PASSWORD)

    page.locator("configuration-modal .pl-modal__footer-left button.pl-button--primary", has_text="Save").click()
    page.wait_for_timeout(1000)
    if page.locator(".pl-notification--error").is_visible():
        page.locator("configuration-modal .pl-modal__footer-left button", has_text="Cancel").click()
        ColorLogger.success(f"The {name_input} is already exist.")

    ColorLogger.success(f"Added {name_input} for Data Plane '{dp_title}' Observability -> {menu_name} -> {tab_name}")

def o11y_fill_prometheus_or_elastic(query_service_type, url, username, password):
    ColorLogger.info(f"O11y Filling {query_service_type} form...")
    page.locator("#endpoint-input").wait_for(state="visible")
    if not page.locator("#endpoint-input").is_visible():
        Util.exit_error(f"Query Service type: {query_service_type} is not visible.", page, "o11y_fill_prometheus_or_elastic.png")

    page.fill("#endpoint-input", url)
    print(f"Fill {query_service_type} URL: {url}")
    if username != "":
        page.fill("#username-input", username)
        print(f"Fill {query_service_type} User: {username}")
    if password != "":
        page.fill("#password-input", password)
        print(f"Fill {query_service_type} Password: {password}")

def dp_config_resources_storage():
    ColorLogger.info("Config Data Plane Resources Storage...")
    page.locator("#resources-menu-item .menu-item-text", has_text="Resources").wait_for(state="visible")
    page.locator("#resources-menu-item .menu-item-text", has_text="Resources").click()
    print("Clicked 'Resources' left side menu")
    resource_name = ENV.TP_AUTO_STORAGE_CLASS
    print(f"Resource Name: {resource_name}")
    page.wait_for_timeout(2000)
    if page.locator("#storage-resource-table tr td:first-child", has_text=resource_name).is_visible():
        ColorLogger.success(f"Storage '{resource_name}' is already created.")
        ReportYaml.set_dataplane_info(ENV.TP_AUTO_K8S_DP_NAME, "storage", True)
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
        Util.click_button_until_enabled(page, page.locator("#save-storage-configuration"))
        print("Clicked 'Add' button")
        if Util.check_dom_visibility(page, page.locator("#storage-resource-table tr td:first-child", has_text=resource_name), 3, 6):
            ColorLogger.success(f"Add Storage '{resource_name}' successfully.")
            ReportYaml.set_dataplane_info(ENV.TP_AUTO_K8S_DP_NAME, "storage", True)

def dp_config_resources_ingress(ingress_controller, resource_name, ingress_class_name, fqdn):
    ColorLogger.info("Config Data Plane Resources Ingress...")
    page.locator("#resources-menu-item .menu-item-text", has_text="Resources").wait_for(state="visible")
    page.locator("#resources-menu-item .menu-item-text", has_text="Resources").click()
    print("Clicked 'Resources' left side menu")
    page.locator("#toggle-ingress-expansion svg use").wait_for(state="visible")
    expected_icon = 'pl-icon-caret-right'
    if expected_icon in (page.query_selector("#toggle-ingress-expansion svg use") or {}).get_attribute("xlink:href"):
        page.locator("#toggle-ingress-expansion").click()
        print("Clicked expand Icon, and wait for Ingress Controller table")
        page.wait_for_timeout(3000)

    print(f"Check if Ingress Controller '{resource_name}' is exist...")
    if page.locator("#ingress-resource-table tr td:first-child", has_text=resource_name).is_visible():
        ColorLogger.success(f"Ingress Controller '{resource_name}' is already created.")
        ReportYaml.set_dataplane_info(ENV.TP_AUTO_K8S_DP_NAME, resource_name, True)
    else:
        print(f"Ingress Controller table do not have '{resource_name}'")
        print(f"Adding Ingress Controller '{resource_name}', and wait for 'Add Ingress Controller' button ...")
        page.locator(".ingress .add-resource-btn button").wait_for(state="visible")
        page.locator(".ingress .add-resource-btn button").click()
        print("Clicked 'Add Ingress Controller' button")

        # Add Ingress Controller dialog popup
        page.locator('.pl-modal__header', has_text="Add Ingress Controller").wait_for(state="visible")
        print("Dialog 'Add Ingress Controller' popup")
        page.locator('#ingress-controller-dropdown input').click()
        print("Clicked 'Ingress Controller' dropdown")
        page.locator('#ingress-controller-dropdown .pl-select__dropdown li', has_text=ingress_controller).wait_for(state="visible")
        print(f"Waiting for '{ingress_controller}' in Ingress Controller dropdown")
        page.locator('#ingress-controller-dropdown .pl-select__dropdown li', has_text=ingress_controller).click()
        print(f"Selected '{ingress_controller}' in Ingress Controller dropdown")
        page.fill('#resourceName-input', resource_name)
        print(f"Filled Resource Name: {resource_name}")
        page.fill('#ingressClassName-input', ingress_class_name)
        print(f"Filled Ingress Class Name: {ingress_class_name}")
        page.fill('#fqdn-input', fqdn)
        print(f"Filled FQDN: {fqdn}")

        # for Ingress Key and Value
        # if ENV.TP_AUTO_INGRESS_CONTROLLER_KEYS != "" and ENV.TP_AUTO_INGRESS_CONTROLLER_VALUES != "":
        #     keys = ENV.TP_AUTO_INGRESS_CONTROLLER_KEYS.split(" ")
        #     values = ENV.TP_AUTO_INGRESS_CONTROLLER_VALUES.split(" ")
        #     for i in range(len(keys)):
        #         key = keys[i].strip()
        #         value = values[i].strip()
        #         page.fill("#key-input", key)
        #         page.fill("#value-textarea", value)
        #         print(f"Filled Ingress Key: {key}, Value: {value}")
        #         page.wait_for_timeout(500)
        #         page.locator(".olly-header__inputs button", has_text="Save").click()
        #         print("Clicked 'Save' button")
        #         page.wait_for_timeout(500)

        Util.click_button_until_enabled(page, page.locator("#save-ingress-configuration"))
        print("Clicked 'Add' button")
        page.wait_for_timeout(1000)
        if page.locator(".pl-notification--error").is_visible():
            error_content = page.locator(".pl-notification__message").text_content()
            Util.warning_screenshot(f"Config Data Plane Resources Ingress Error: {error_content}", page, "dp_config_resources_ingress.png")
            page.locator("#cancel-ingress-configuration").click()
            print("Clicked 'Cancel' button")
            return
        if Util.check_dom_visibility(page, page.locator("#ingress-resource-table tr td:first-child", has_text=resource_name), 3, 6):
            ColorLogger.success(f"Add Ingress Controller '{resource_name}' successfully.")
            ReportYaml.set_dataplane_info(ENV.TP_AUTO_K8S_DP_NAME, resource_name, True)

def flogo_provision_capability(dp_name):
    ColorLogger.info("Flogo Provisioning capability...")
    goto_dataplane(dp_name)
    if page.locator("capability-card #flogo").is_visible():
        ColorLogger.success("Flogo capability is already provisioned.")
        ReportYaml.set_capability(dp_name, "flogo")
        return

    print("Checking if 'Provision a capability' button is visible.")
    if Util.check_dom_visibility(page, page.locator('button', has_text="Provision a capability"), 10, 100):
        print("'Provision a capability' button is visible.")
        ColorLogger.success(f"Data Plane '{dp_name}' status is running.")
        page.locator('button', has_text="Provision a capability").click()
        print("Clicked 'Provision a capability' button")
        page.wait_for_timeout(2000)
        Util.click_button_until_enabled(page, page.locator('#FLOGO-capability-select-button'))
        print("Clicked 'Provision TIBCO Flogo® Enterprise' -> 'Start' button")

        print("Waiting for Flogo capability page is loaded")
        page.locator(".resources-content").wait_for(state="visible")
        print("Flogo capability page is loaded")
        page.wait_for_timeout(3000)

        if page.locator('#storage-class-resource-table').is_visible():
            page.locator('#storage-class-resource-table tr', has=page.locator('td', has_text=ENV.TP_AUTO_STORAGE_CLASS)).locator('label').wait_for(state="visible")
            page.locator('#storage-class-resource-table tr', has=page.locator('td', has_text=ENV.TP_AUTO_STORAGE_CLASS)).locator('label').click()
            print(f"Selected '{ENV.TP_AUTO_STORAGE_CLASS}' Storage Class for Flogo capability")

        if page.locator('#ingress-resource-table').is_visible():
            page.locator('#ingress-resource-table tr', has=page.locator('td', has_text=ENV.TP_AUTO_INGRESS_CONTROLLER_FLOGO)).locator('label').wait_for(state="visible")
            page.locator('#ingress-resource-table tr', has=page.locator('td', has_text=ENV.TP_AUTO_INGRESS_CONTROLLER_FLOGO)).locator('label').click()
            print(f"Selected '{ENV.TP_AUTO_INGRESS_CONTROLLER_FLOGO}' Ingress Controller for Flogo capability")

        page.locator("#btnNextCapabilityProvision").click()
        print("Clicked Flogo 'Next' button, finished step 1")
        page.locator(".eula-container input").click()
        print("Clicked Flogo 'EUA' checkbox")
        page.locator("#qaProvisionFlogo").click()
        print("Clicked 'Flogo Provision Capability' button, waiting for Flogo Capability Provision Request Completed")
        page.locator(".notification-message", has_text="Successfully provisioned Flogo").wait_for(state="visible")
        ColorLogger.success("Provision Flogo capability successful.")
        page.locator("#qaBackToDP").click()
        print("Clicked 'Go Back To Data Plane Details' button")
    else:
        Util.exit_error("'Provision a capability' button is not visible.", page, "flogo_provision_capability.png")

    print("Reload Data Plane page, and check if Flogo capability is provisioned...")
    Util.refresh_page(page)
    print("Waiting for Flogo capability is in capability list...")
    page.wait_for_timeout(5000)
    if is_capability_provisioned("Flogo"):
        ColorLogger.success("Flogo capability is in capability list")
        ReportYaml.set_capability(dp_name, "flogo")
    else:
        Util.warning_screenshot("Flogo capability is not in capability list", page, "flogo_provision_capability-2.png")

def flogo_provision_connector(dp_name):
    ColorLogger.info("Flogo Provisioning connector...")

    # program will exit if Flogo capability is not provisioned yet
    goto_capability(dp_name, "Flogo")

    page.locator(".capability-connectors-container .total-capability").wait_for(state="visible")
    page.wait_for_timeout(1000)
    print("Flogo capability page loaded, Checking connectors...")
    if page.locator(".capability-connectors-container .total-capability", has_text="(2)").is_visible():
        ColorLogger.success("Flogo connectors are already provisioned.")
        return

    page.wait_for_timeout(2000)
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

    # program will exit if Flogo capability is not provisioned yet
    goto_capability(dp_name, "Flogo")

    print("Flogo Checking app build...")
    if page.locator(".app-build-container td", has_text=app_name).is_visible():
        ColorLogger.success(f"Flogo app build {app_name} is already created.")
        return

    page.wait_for_timeout(2000)
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
    print(f"Clicked 'Namespace' dropdown, and waiting for namespace: {ENV.TP_AUTO_K8S_DP_NAMESPACE}")
    page.wait_for_timeout(1000)
    if not page.locator("flogo-namespace-picker .namespace-dropdown li", has_text=ENV.TP_AUTO_K8S_DP_NAMESPACE).is_visible():
        Util.exit_error(f"Namespace '{ENV.TP_AUTO_K8S_DP_NAMESPACE}' is not list in the dropdown.", page, "flogo_app_build_and_deploy.png")

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
    if Util.check_dom_visibility(page, page.locator('flogo-tp-pl-icon[icon="pl-icon-critical-error"]'),3, 10):
        Util.exit_error(f"Flogo app build '{app_name}' is not deployed.", page, "flogo_app_build_and_deploy_deploy.png")

    print("No deploy error, continue waiting for deploy status...")
    if Util.check_dom_visibility(page, page.locator('.finish-container .step-description', has_text="Successfully deployed App")):
        ColorLogger.success(f"Flogo app build '{app_name}' is deployed.")

def flogo_app_deploy(dp_name, app_name):
    ColorLogger.info(f"Flogo Deploying app '{app_name}'...")
    dp_name_space = ENV.TP_AUTO_K8S_DP_NAMESPACE

    goto_dataplane(dp_name)
    if page.locator("apps-list td.app-name a", has_text=app_name).is_visible():
        ColorLogger.success(f"Flogo app '{app_name}' in namespace {dp_name_space} is already deployed.")
        return

    # program will exit if Flogo capability is not provisioned yet
    goto_capability(dp_name, "Flogo")

    print(f"Waiting for Flogo app build {app_name} is deployed...")
    if not Util.check_dom_visibility(page, page.locator(".app-build-container td:first-child", has_text=app_name), 20, 180, True):
        Util.exit_error(f"Flogo app {app_name} is not deployed.", page, "flogo_app_deploy.png")

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

    print(f"Waiting for Flogo app '{app_name}' is deployed...")
    if Util.check_dom_visibility(page, page.locator("apps-list td.app-name a", has_text=app_name), 10, 120):
        ColorLogger.success(f"Deploy Flogo app '{app_name}' in namespace {dp_name_space} Successfully")
    else:
        Util.warning_screenshot(f"Deploy Flogo app '{app_name}' in namespace {dp_name_space} may failed.", page, "flogo_app_deploy-2.png")

def flogo_app_config(dp_name, app_name):
    ColorLogger.info(f"Flogo Config app '{app_name}'...")
    goto_app_detail(dp_name, app_name)

    if page.locator(".no-endpoints", has_text="There are no Endpoints configured for the application").is_visible():
        Util.warning_screenshot(f"There is some error for Flogo app '{app_name}', it has no Endpoints configured.", page, "flogo_app_config.png")
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
        if page.locator(".capability-table-row-details label", has_text=ENV.TP_AUTO_INGRESS_CONTROLLER_FLOGO).is_visible():
            page.locator(".capability-table-row-details label", has_text=ENV.TP_AUTO_INGRESS_CONTROLLER_FLOGO).click()
            print(f"Selected '{ENV.TP_AUTO_INGRESS_CONTROLLER_FLOGO}' from Resource Name column")
            page.locator("button", has_text="Update Endpoint visibility to Public").click()
            print("Clicked 'Update Endpoint visibility to Public' button")
        else:
            Util.warning_screenshot(f"Not able to set Endpoint Visibility to Public, '{ENV.TP_AUTO_INGRESS_CONTROLLER_FLOGO}' is not available.", page, "flogo_app_config-endpoint.png")
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
    # when app status is Running, or the action button is 'Stop', it means app is already running
    is_app_running = page.locator("flogo-app-run-status .scale-status-text", has_text="Running").is_visible() or page.locator("flogo-app-run-status button", has_text="Stop").is_visible()
    if is_app_running:
        ColorLogger.success(f"Flogo app '{app_name}' is already running.")
        ReportYaml.set_capability_app_info(ENV.TP_AUTO_K8S_DP_NAME, "flogo", app_name, "status", "Running")
    else:
        page.locator("flogo-app-run-status button", has_text="Start").click()
        print("Clicked 'Start' app button")

        print(f"Waiting for app '{app_name}' status is Running...")
        if Util.check_dom_visibility(page, page.locator("flogo-app-run-status .scale-status-text", has_not_text="Scaling"), 15, 180, True):
            app_status = page.locator("flogo-app-run-status .scale-status-text").inner_text()
            ColorLogger.success(f"Flogo app '{app_name}' status is '{app_status}' now.")
            ReportYaml.set_capability_app_info(ENV.TP_AUTO_K8S_DP_NAME, "flogo", app_name, "status", app_status)
        else:
            Util.warning_screenshot(f"Wait too long to scale Flogo app '{app_name}'.", page, "flogo_app_start.png")

def flogo_app_test_endpoint(dp_name, app_name):
    ColorLogger.info(f"Flogo Test app endpoint '{app_name}'...")
    goto_app_detail(dp_name, app_name)

    print("Navigating to 'Endpoints' tab menu")
    page.locator(".pl-primarynav__menu .pl-primarynav__item", has_text="Endpoints").click()

    print("Check if 'Test' button is visible...")
    page.wait_for_timeout(2000)
    if page.locator(".endpoints-container .action-button a", has_text="Test").is_visible():
        with page.context.expect_page() as new_page_info:
            page.locator(".endpoints-container .action-button a", has_text="Test").click()
            print("Clicked 'Test' button")

        new_page = new_page_info.value
        print("New window detected and captured.")

        print("Waiting for Swagger page loaded.")
        new_page.wait_for_load_state()

        print(f"Waiting for Swagger title '{app_name}' to be displayed.")
        if Util.check_dom_visibility(new_page, new_page.locator("#swagger-editor h2.title", has_text=app_name), 5, 15, True):
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
            Util.warning_screenshot(f"Swagger page is not loaded, title '{app_name}' is not displayed.", new_page, "flogo_app_test_endpoint.png")
    else:
        Util.warning_screenshot(f"'Test' button is not visible in Flogo app {app_name}, need to config it and start app.", page, "flogo_app_test_endpoint.png")

def flogo_is_app_created(app_name):
    ColorLogger.info(f"Checking if Flogo app '{app_name}' is created")
    try:
        print(f"Checking if Flogo app '{app_name}' is already created...")
        page.wait_for_timeout(3000)
        if page.locator("#app-list-table tr.pl-table__row td.app-name", has_text=app_name).is_visible():
            ColorLogger.success(f"Flogo app '{app_name}' is already created.")
            ReportYaml.set_capability(ENV.TP_AUTO_K8S_DP_NAME, "flogo")
            ReportYaml.set_capability_app(ENV.TP_AUTO_K8S_DP_NAME, "flogo", app_name)
            return True
        else:
            print(f"Flogo app '{app_name}' has not been created.")
            return False
    except Exception as e:
        ColorLogger.warning(f"An error occurred while Checking Flogo app '{app_name}': {e}")
        return False

def flogo_is_app_running(app_name):
    ColorLogger.info(f"Checking if Flogo app '{app_name}' is running")
    try:
        print(f"Checking if Flogo app '{app_name}' is already running...")
        page.wait_for_timeout(3000)
        if page.locator("#app-list-table tr.FLOGO", has=page.locator("td.app-name", has_text=app_name)).locator("td", has_text="Running").is_visible():
            ColorLogger.success(f"Flogo app '{app_name}' is already running.")
            ReportYaml.set_capability_app_info(ENV.TP_AUTO_K8S_DP_NAME, "flogo", app_name, "status", "Running")
            return True
        else:
            print(f"Flogo app '{app_name}' has not been running.")
            return False
    except Exception as e:
        ColorLogger.warning(f"An error occurred while Checking Flogo app '{app_name}': {e}")
        return False

def bwce_provision_capability(dp_name):
    ColorLogger.info("BWCE Provisioning capability...")
    goto_dataplane(dp_name)
    if page.locator("capability-card #bwce").is_visible():
        ColorLogger.success("BWCE capability is already provisioned.")
        ReportYaml.set_capability(dp_name, "bwce")
        return

    print("Checking if 'Provision a capability' button is visible.")
    if Util.check_dom_visibility(page, page.locator('button', has_text="Provision a capability"), 10, 100):
        print("'Provision a capability' button is visible.")
        ColorLogger.success(f"Data Plane '{dp_name}' status is running.")
        page.locator('button', has_text="Provision a capability").click()
        print("Clicked 'Provision a capability' button")
        page.wait_for_timeout(2000)
        Util.click_button_until_enabled(page, page.locator('#BWCE-capability-select-button'))
        print("Clicked 'Provision TIBCO BusinessWorks™ Container Edition' -> 'Start' button")

        print("Waiting for BWCE capability page is loaded")
        page.locator(".resources-content").wait_for(state="visible")
        print("BWCE capability page is loaded")
        page.wait_for_timeout(3000)

        if page.locator('#storage-class-resource-table').is_visible():
            page.locator('#storage-class-resource-table tr', has=page.locator('td', has_text=ENV.TP_AUTO_STORAGE_CLASS)).locator('label').wait_for(state="visible")
            page.locator('#storage-class-resource-table tr', has=page.locator('td', has_text=ENV.TP_AUTO_STORAGE_CLASS)).locator('label').click()
            print(f"Selected '{ENV.TP_AUTO_STORAGE_CLASS}' Storage Class for BWCE capability")

        if page.locator('#ingress-resource-table').is_visible():
            page.locator('#ingress-resource-table tr', has=page.locator('td', has_text=ENV.TP_AUTO_INGRESS_CONTROLLER_BWCE)).locator('label').wait_for(state="visible")
            page.locator('#ingress-resource-table tr', has=page.locator('td', has_text=ENV.TP_AUTO_INGRESS_CONTROLLER_BWCE)).locator('label').click()
            print(f"Selected '{ENV.TP_AUTO_INGRESS_CONTROLLER_BWCE}' Ingress Controller for BWCE capability")

        page.locator("#btnNextCapabilityProvision", has_text="Next").click()
        print("Clicked BWCE 'Next' button, finished step 1")
        page.locator(".resource-agree label").click()
        print("Clicked BWCE 'EUA' checkbox")
        page.locator("#btnNextCapabilityProvision", has_text="BWCE Provision Capability").click()
        print("Clicked 'BWCE Provision Capability' button, waiting for BWCE Capability Provision Request Completed")
        if Util.check_dom_visibility(page, page.locator(".resource-success .title", has_text="Capability Provision Request Completed"), 5, 60):
            ColorLogger.success("Provision Flogo capability successful.")
        page.locator("#capProvBackToDPBtn").click()
        print("Clicked 'Go Back To Data Plane Details' button")
    else:
        Util.exit_error("'Provision a capability' button is not visible.", page, "bwce_provision_capability.png")

    print("Reload Data Plane page, and check if BWCE capability is provisioned...")
    Util.refresh_page(page)
    print("Waiting for BWCE capability is in capability list...")
    page.wait_for_timeout(5000)
    if is_capability_provisioned("BWCE"):
        ColorLogger.success("BWCE capability is in capability list")
        ReportYaml.set_capability(dp_name, "bwce")
    else:
        Util.warning_screenshot("BWCE capability is not in capability list", page, "bwce_provision_capability-2.png")

def ems_provision_capability(dp_name, ems_server_name):
    capability_name = f"{ems_server_name}-dev"
    ColorLogger.info("EMS Provisioning capability...")
    goto_dataplane(dp_name)
    if page.locator("capability-card #ems .pl-tooltip__trigger", has_text=capability_name).is_visible():
        ColorLogger.success("EMS capability is already provisioned.")
        ReportYaml.set_capability(dp_name, "ems")
        return

    print("Checking if 'Provision a capability' button is visible.")
    if Util.check_dom_visibility(page, page.locator('button', has_text="Provision a capability"), 10, 100):
        print("'Provision a capability' button is visible.")
        ColorLogger.success(f"Data Plane '{dp_name}' status is running.")
        page.locator('button', has_text="Provision a capability").click()
        print("Clicked 'Provision a capability' button")
        page.wait_for_timeout(2000)
        Util.click_button_until_enabled(page, page.locator('#EMS-capability-select-button'))
        print("Clicked 'Provision TIBCO Enterprise Message Service™' -> 'Start' button")

        print("Waiting for EMS capability page is loaded")
        page.locator(".resources-content").wait_for(state="visible")
        print("EMS capability page is loaded")
        page.wait_for_timeout(3000)

        # step1: Resources
        if page.locator('#message-storage-resource-table').is_visible():
            page.locator('#message-storage-resource-table tr', has=page.locator('td', has_text=ENV.TP_AUTO_STORAGE_CLASS)).locator('label').wait_for(state="visible")
            page.locator('#message-storage-resource-table tr', has=page.locator('td', has_text=ENV.TP_AUTO_STORAGE_CLASS)).locator('label').click()
            print(f"Selected '{ENV.TP_AUTO_STORAGE_CLASS}' Message Storage")

        if page.locator('#log-storage-resource-table').is_visible():
            page.locator('#log-storage-resource-table tr', has=page.locator('td', has_text=ENV.TP_AUTO_STORAGE_CLASS)).locator('label').wait_for(state="visible")
            page.locator('#log-storage-resource-table tr', has=page.locator('td', has_text=ENV.TP_AUTO_STORAGE_CLASS)).locator('label').click()
            print(f"Selected '{ENV.TP_AUTO_STORAGE_CLASS}' Log Storage")

        page.locator("#btnNextCapabilityProvision", has_text="Next").click()
        print("Clicked EMS step 1 'Next' button")

        # step2: Configuration
        page.locator("#ems-config-capability-instance").wait_for(state="visible")
        print("Waiting for EMS configuration step 2 is loaded")
        page.fill("#ems-config-capability-instance", ems_server_name)
        print(f"Filled EMS 'Server Name' with '{ems_server_name}'")
        page.locator("label[for='ems-config-eula']").click()
        print("Clicked EMS 'EUA' checkbox")
        page.locator("#btn_next_configuration", has_text="Next").click()
        print("Clicked EMS step 2 'Next' button")

        # step3: Custom Config
        print("Skipped EMS step 3")

        # step4: Configuration
        page.locator("#btn_next_confirmation", has_text="Provision TIBCO Enterprise Message Service").click()
        print("Clicked EMS step 4 'Provision TIBCO Enterprise Message Service' button, waiting for EMS Capability Provision Request Completed")

        if Util.check_dom_visibility(page, page.get_by_text("EMS server is provisioned and ready to use!"), 5, 60):
            ColorLogger.success("Provision EMS capability successful.")
        page.locator("#btn_go_to_dta_pln").click()
        print("Clicked 'Go Back To Data Plane Details' button")
    else:
        Util.exit_error("'Provision a capability' button is not visible.", page, "ems_provision_capability.png")

    print("Reload Data Plane page, and check if EMS capability is provisioned...")
    Util.refresh_page(page)
    print("Waiting for EMS capability is in capability list...")
    page.wait_for_timeout(5000)
    if is_capability_provisioned("EMS", capability_name):
        ColorLogger.success(f"EMS capability {capability_name} is in capability list")
        ReportYaml.set_capability(dp_name, "ems")
    else:
        Util.warning_screenshot(f"EMS capability {capability_name} is not in capability list", page, "ems_provision_capability-2.png")

def pulsar_provision_capability(dp_name, pulsar_server_name):
    capability_name = f"{pulsar_server_name}-dev"
    ColorLogger.info("Pulsar Provisioning capability...")
    goto_dataplane(dp_name)
    if page.locator("capability-card #pulsar .pl-tooltip__trigger", has_text=capability_name).is_visible():
        ColorLogger.success("Pulsar capability is already provisioned.")
        ReportYaml.set_capability(dp_name, "pulsar")
        return

    print("Checking if 'Provision a capability' button is visible.")
    if Util.check_dom_visibility(page, page.locator('button', has_text="Provision a capability"), 10, 100):
        print("'Provision a capability' button is visible.")
        ColorLogger.success(f"Data Plane '{dp_name}' status is running.")
        page.locator('button', has_text="Provision a capability").click()
        print("Clicked 'Provision a capability' button")
        page.wait_for_timeout(2000)
        Util.click_button_until_enabled(page, page.locator('#PULSAR-capability-select-button'))
        print("Clicked 'Provision TIBCO® Messaging Quasar - Powered by Apache Pulsar™' -> 'Start' button")

        print("Waiting for Pulsar capability page is loaded")
        page.locator(".resources-content").wait_for(state="visible")
        print("Pulsar capability page is loaded")
        page.wait_for_timeout(3000)

        # step1: Resources
        if page.locator('#message-storage-resource-table').is_visible():
            page.locator('#message-storage-resource-table tr', has=page.locator('td', has_text=ENV.TP_AUTO_STORAGE_CLASS)).locator('label').wait_for(state="visible")
            page.locator('#message-storage-resource-table tr', has=page.locator('td', has_text=ENV.TP_AUTO_STORAGE_CLASS)).locator('label').click()
            print(f"Selected '{ENV.TP_AUTO_STORAGE_CLASS}' Message Storage")

        if page.locator('#journal-storage-resource-table').is_visible():
            page.locator('#journal-storage-resource-table tr', has=page.locator('td', has_text=ENV.TP_AUTO_STORAGE_CLASS)).locator('label').wait_for(state="visible")
            page.locator('#journal-storage-resource-table tr', has=page.locator('td', has_text=ENV.TP_AUTO_STORAGE_CLASS)).locator('label').click()
            print(f"Selected '{ENV.TP_AUTO_STORAGE_CLASS}' Journal Storage")

        if page.locator('#log-storage-resource-table').is_visible():
            page.locator('#log-storage-resource-table tr', has=page.locator('td', has_text=ENV.TP_AUTO_STORAGE_CLASS)).locator('label').wait_for(state="visible")
            page.locator('#log-storage-resource-table tr', has=page.locator('td', has_text=ENV.TP_AUTO_STORAGE_CLASS)).locator('label').click()
            print(f"Selected '{ENV.TP_AUTO_STORAGE_CLASS}' Log Storage")

        page.locator("#btnNextCapabilityProvision", has_text="Next").click()
        print("Clicked Pulsar step 1 'Next' button")

        # step2: Configuration
        page.locator("#cap-config-capability-instance").wait_for(state="visible")
        print("Waiting for Pulsar configuration step 2 is loaded")
        page.fill("#cap-config-capability-instance", pulsar_server_name)
        print(f"Filled Pulsar 'Server Name' with '{pulsar_server_name}'")
        page.locator("label[for='cap-config-eula']").click()
        print("Clicked Pulsar 'EUA' checkbox")
        page.locator("#btn_next_configuration", has_text="Next").click()
        print("Clicked Pulsar step 2 'Next' button")

        # step3: Custom Config
        print("Skipped Pulsar step 3")

        # step4: Configuration
        page.locator("#btn_next_confirmation", has_text="Provision TIBCO® Messaging Quasar - Powered by Apache Pulsar™").click()
        print("Clicked Pulsar step 4 'Provision TIBCO® Messaging Quasar - Powered by Apache Pulsar™' button, waiting for Pulsar Capability Provision Request Completed")

        if Util.check_dom_visibility(page, page.get_by_text("Pulsar server is provisioned and ready to use!"), 5, 60):
            ColorLogger.success("Provision Pulsar capability successful.")
            ReportYaml.set_capability(dp_name, "pulsar")
        page.locator("#btn_go_to_dta_pln").click()
        print("Clicked 'Go Back To Data Plane Details' button")
    else:
        Util.exit_error("'Provision a capability' button is not visible.", page, "pulsar_provision_capability.png")

    print("Reload Data Plane page, and check if Pulsar capability is provisioned...")
    Util.refresh_page(page)
    print("Waiting for Pulsar capability is in capability list...")
    page.wait_for_timeout(5000)
    if is_capability_provisioned("Pulsar", capability_name):
        ColorLogger.success(f"Pulsar capability {capability_name} is in capability list")
    else:
        Util.warning_screenshot(f"Pulsar capability {capability_name} is not in capability list", page, "pulsar_provision_capability-2.png")

def tibcohub_provision_capability(dp_name, hub_name):
    capability_name = f"{hub_name}"
    ColorLogger.info("TibcoHub Provisioning capability...")
    goto_dataplane(dp_name)
    if page.locator("capability-card #tibcohub .pl-tooltip__trigger", has_text=capability_name).is_visible():
        ColorLogger.success("TibcoHub capability is already provisioned.")
        ReportYaml.set_capability(dp_name, "tibcohub")
        return

    print("Checking if 'Provision a capability' button is visible.")
    if Util.check_dom_visibility(page, page.locator('button', has_text="Provision a capability"), 10, 100):
        print("'Provision a capability' button is visible.")
        ColorLogger.success(f"Data Plane '{dp_name}' status is running.")
        page.locator('button', has_text="Provision a capability").click()
        print("Clicked 'Provision a capability' button")
        page.wait_for_timeout(2000)
        Util.click_button_until_enabled(page, page.locator('#TIBCOHUB-capability-select-button'))
        print("Clicked 'Provision TIBCO® Developer Hub' -> 'Start' button")

        print("Waiting for TibcoHub capability page is loaded")
        page.locator(".resources-content").wait_for(state="visible")
        print("TibcoHub capability page is loaded")
        page.wait_for_timeout(3000)

        # step1: Resources for TibcoHub capability
        if page.locator('#storage-class-resource-table').is_visible():
            page.locator('#storage-class-resource-table tr', has=page.locator('td', has_text=ENV.TP_AUTO_STORAGE_CLASS)).locator('label').wait_for(state="visible")
            page.locator('#storage-class-resource-table tr', has=page.locator('td', has_text=ENV.TP_AUTO_STORAGE_CLASS)).locator('label').click()
            print(f"Selected '{ENV.TP_AUTO_STORAGE_CLASS}' Storage Class for TibcoHub capability")

        if page.locator('#ingress-resource-table').is_visible():
            page.locator('#ingress-resource-table tr', has=page.locator('td', has_text=ENV.TP_AUTO_INGRESS_CONTROLLER_TIBCOHUB)).locator('label').wait_for(state="visible")
            page.locator('#ingress-resource-table tr', has=page.locator('td', has_text=ENV.TP_AUTO_INGRESS_CONTROLLER_TIBCOHUB)).locator('label').click()
            print(f"Selected '{ENV.TP_AUTO_INGRESS_CONTROLLER_TIBCOHUB}' Ingress Controller for TibcoHub capability")

        page.locator("#btnNextCapabilityProvision", has_text="Next").click()
        print("Clicked TibcoHub step 1 'Next' button")

        # step2: Configuration
        page.locator("#thub-config-capability-instance").wait_for(state="visible")
        print("Waiting for TibcoHub configuration step 2 is loaded")
        page.fill("#thub-config-capability-instance", hub_name)
        print(f"Filled TibcoHub 'Developer Hub Name' with '{hub_name}'")
        page.locator("label[for='thub-config-eula']").click()
        print("Clicked TibcoHub 'EUA' checkbox")
        page.locator("#btn_next_configuration", has_text="Next").click()
        print("Clicked TibcoHub step 2 'Next' button")

        # step3: Custom Configuration
        page.locator("#btn_next_custom_configuration", has_text="Next").click()
        print("Clicked TibcoHub step 3 'Next' button")

        # step4: Confirmation
        page.locator("#btn_next_confirmation", has_text="Next").click()
        print("Clicked TibcoHub step 4 'Next' button, waiting for TibcoHub Capability Provision Request Completed")

        if Util.check_dom_visibility(page, page.get_by_text("Sit back while we provision your capability"), 5, 60):
            ColorLogger.success("Provision TibcoHub capability successful.")
        page.locator("#btn_go_to_dta_pln").click()
        print("Clicked 'Go Back To Data Plane Details' button")
    else:
        Util.exit_error("'Provision a capability' button is not visible.", page, "tibcohub_provision_capability.png")

    print("Reload Data Plane page, and check if TibcoHub capability is provisioned...")
    Util.refresh_page(page)
    print("Waiting for TibcoHub capability is in capability list...")
    page.wait_for_timeout(5000)
    if is_capability_provisioned("TibcoHub", capability_name):
        ColorLogger.success(f"TibcoHub capability {capability_name} is in capability list")
        ReportYaml.set_capability(dp_name, "tibcohub")
    else:
        ColorLogger.warning(f"TibcoHub capability {capability_name} is not in capability list")

if __name__ == "__main__":
    ENV.pre_check()

    page = Util.browser_launch()
    try:
        login(page)
        login_check(page)

        set_user_permission()

        # config global dataplane
        # o11y_config_dataplane_resource()

        if ENV.TP_AUTO_IS_CREATE_DP:
            # for create dataplane and config dataplane resources
            goto_left_navbar("Data Planes")
            k8s_create_dataplane(ENV.TP_AUTO_K8S_DP_NAME)
            goto_dataplane(ENV.TP_AUTO_K8S_DP_NAME)
            goto_dataplane_config()
            dp_config_resources_storage()
            if ENV.TP_AUTO_IS_PROVISION_BWCE:
                dp_config_resources_ingress(
                    ENV.TP_AUTO_INGRESS_CONTROLLER, ENV.TP_AUTO_INGRESS_CONTROLLER_BWCE,
                    ENV.TP_AUTO_INGRESS_CONTROLLER_CLASS_NAME, ENV.TP_AUTO_FQDN_BWCE
                )
            if ENV.TP_AUTO_IS_PROVISION_FLOGO:
                dp_config_resources_ingress(
                    ENV.TP_AUTO_INGRESS_CONTROLLER, ENV.TP_AUTO_INGRESS_CONTROLLER_FLOGO,
                    ENV.TP_AUTO_INGRESS_CONTROLLER_CLASS_NAME, ENV.TP_AUTO_FQDN_FLOGO
                )
            if ENV.TP_AUTO_IS_PROVISION_TIBCOHUB:
                dp_config_resources_ingress(
                    ENV.TP_AUTO_INGRESS_CONTROLLER, ENV.TP_AUTO_INGRESS_CONTROLLER_TIBCOHUB,
                    ENV.TP_AUTO_INGRESS_CONTROLLER_CLASS_NAME, ENV.TP_AUTO_FQDN_TIBCOHUB
                )
            o11y_config_dataplane_resource(ENV.TP_AUTO_K8S_DP_NAME)

            # for provision BWCE capability
            if ENV.TP_AUTO_IS_PROVISION_BWCE:
                goto_left_navbar("Data Planes")
                goto_dataplane(ENV.TP_AUTO_K8S_DP_NAME)

                bwce_provision_capability(ENV.TP_AUTO_K8S_DP_NAME)

            # for provision EMS capability
            if ENV.TP_AUTO_IS_PROVISION_EMS:
                goto_left_navbar("Data Planes")
                goto_dataplane(ENV.TP_AUTO_K8S_DP_NAME)

                ems_provision_capability(ENV.TP_AUTO_K8S_DP_NAME, ENV.TP_AUTO_EMS_CAPABILITY_SERVER_NAME)

            # for provision Flogo capability, connector, app, and start app
            if ENV.TP_AUTO_IS_PROVISION_FLOGO:
                goto_left_navbar("Data Planes")
                goto_dataplane(ENV.TP_AUTO_K8S_DP_NAME)
                # check if Flogo app is created, if not, create it
                if not flogo_is_app_created(ENV.FLOGO_APP_NAME):
                    flogo_provision_capability(ENV.TP_AUTO_K8S_DP_NAME)
                    flogo_provision_connector(ENV.TP_AUTO_K8S_DP_NAME)
                    flogo_app_build_and_deploy(ENV.TP_AUTO_K8S_DP_NAME, ENV.FLOGO_APP_FILE_NAME, ENV.FLOGO_APP_NAME)
                    flogo_app_deploy(ENV.TP_AUTO_K8S_DP_NAME, ENV.FLOGO_APP_NAME)

                # check if Flogo app is created and running, if not, start it
                if flogo_is_app_created(ENV.FLOGO_APP_NAME) and not flogo_is_app_running(ENV.FLOGO_APP_NAME):
                    flogo_app_config(ENV.TP_AUTO_K8S_DP_NAME, ENV.FLOGO_APP_NAME)
                    flogo_app_start(ENV.TP_AUTO_K8S_DP_NAME, ENV.FLOGO_APP_NAME)
                    flogo_app_test_endpoint(ENV.TP_AUTO_K8S_DP_NAME, ENV.FLOGO_APP_NAME)

            # for provision Pulsar capability
            if ENV.TP_AUTO_IS_PROVISION_PULSAR:
                goto_left_navbar("Data Planes")
                goto_dataplane(ENV.TP_AUTO_K8S_DP_NAME)

                pulsar_provision_capability(ENV.TP_AUTO_K8S_DP_NAME, ENV.TP_AUTO_PULSAR_CAPABILITY_SERVER_NAME)

            # for provision TibcoHub capability
            if ENV.TP_AUTO_IS_PROVISION_TIBCOHUB:
                goto_left_navbar("Data Planes")
                goto_dataplane(ENV.TP_AUTO_K8S_DP_NAME)

                tibcohub_provision_capability(ENV.TP_AUTO_K8S_DP_NAME, ENV.TP_AUTO_TIBCOHUB_CAPABILITY_HUB_NAME)
        logout(page)
    except Exception as e:
        Util.exit_error(f"Unhandled error: {e}", page, "unhandled_error_run.png")
    Util.browser_close()

    Util.print_env_info(False)
