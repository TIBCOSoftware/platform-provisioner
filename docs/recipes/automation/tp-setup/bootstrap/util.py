import os
import sys

from playwright.sync_api import sync_playwright
from color_logger import ColorLogger
from env import ENV
import time

class Util:
    _browser = None
    _run_start_time = None

    @staticmethod
    def browser_launch(is_headless=ENV.IS_HEADLESS):
        if Util._browser is None:
            Util._run_start_time = time.time()
            playwright = sync_playwright().start()
            Util._browser = playwright.chromium.launch(headless=is_headless)
            ColorLogger.success("Browser Launched Successfully.")

        context = Util._browser.new_context(
            viewport={"width": 2000, "height": 1080},
            ignore_https_errors=True,
            accept_downloads=True
        )

        return context.new_page()

    @staticmethod
    def browser_close():
        if Util._browser is not None:
            Util._browser.close()
            Util._browser = None
            ColorLogger.success("Browser Closed Successfully.")

        if Util._run_start_time is not None:
            ColorLogger.info(f"Total running time: {time.time() - Util._run_start_time:.2f} seconds")

    @staticmethod
    def screenshot_page(page, filename):
        if filename == "":
            ColorLogger.warning(f"Screenshot filename={filename} MUST be set.")
            return
        screenshot_dir = ENV.TP_AUTO_SCREENSHOT_PATH
        # check folder screenshot_dir exist or not, if not create it
        if not os.path.exists(screenshot_dir):
            os.makedirs(screenshot_dir, exist_ok=True)
        file_path = os.path.join(screenshot_dir, filename)
        page.screenshot(path=file_path, full_page=True)
        print(f"Screenshot saved to {file_path}")

    @staticmethod
    def exit_error(message, page=None, filename=""):
        if page is not None:
            Util.screenshot_page(page, f"error-{filename}")
        ColorLogger.error(f"Exiting program: {message}")
        sys.exit(1)

    @staticmethod
    def warning_screenshot(message, page=None, filename=""):
        ColorLogger.warning(message)
        if page is not None:
            Util.screenshot_page(page, f"warning-{filename}")

    @staticmethod
    def refresh_page(page):
        print("Page reload for: ", page.url)
        page.reload()
        page.wait_for_load_state()

    @staticmethod
    def print_env_info(is_print_auth=True, is_print_dp=True):
        str_num = 90
        col_space = 28
        print("=" * str_num)
        if is_print_auth:
            print("-" * str_num)
            print(f"{'Login Credentials': ^{str_num}}")
            print("-" * str_num)
            print(f"{'Mail URL:':<{col_space}}{ENV.TP_AUTO_MAIL_URL}")
            print("-" * str_num)
            print(f"{'Admin URL:':<{col_space}}{ENV.TP_AUTO_ADMIN_URL}")
            print(f"{'Admin Email:':<{col_space}}{ENV.CP_ADMIN_EMAIL}")
            print(f"{'Admin Password:':<{col_space}}{ENV.CP_ADMIN_PASSWORD}")
            print("-" * str_num)
            print(f"{'Login URL:':<{col_space}}{ENV.TP_AUTO_LOGIN_URL}")
            print(f"{'User Email:':<{col_space}}{ENV.DP_USER_EMAIL}")
            print(f"{'User Password:':<{col_space}}{ENV.DP_USER_PASSWORD}")
        if is_print_dp:
            print("-" * str_num)
            print(f"{'Elastic/Kibana/Prometheus Credentials': ^{str_num}}")
            print("-" * str_num)
            print(f"{'Elastic URL:':<{col_space}}{ENV.TP_AUTO_ELASTIC_URL}")
            print(f"{'Kibana URL:':<{col_space}}{ENV.TP_AUTO_KIBANA_URL}")
            print(f"{'User Name:':<{col_space}}{ENV.TP_AUTO_ELASTIC_USER}")
            print(f"{'User Password:':<{col_space}}{ENV.TP_AUTO_ELASTIC_PASSWORD}")
            print("-" * str_num)
            print(f"{'Prometheus URL:':<{col_space}}{ENV.TP_AUTO_PROMETHEUS_URL}")
            if ENV.TP_AUTO_PROMETHEUS_USER != "":
                print(f"{'User Name:':<{col_space}}{ENV.TP_AUTO_PROMETHEUS_USER}")
            if ENV.TP_AUTO_PROMETHEUS_PASSWORD != "":
                print(f"{'User Password:':<{col_space}}{ENV.TP_AUTO_PROMETHEUS_PASSWORD}")
            print("-" * str_num)
            if ENV.TP_AUTO_IS_CREATE_DP:
                print(f"{'Data Plane, App': ^{str_num}}")
                print("-" * str_num)
                print(f"{'DataPlane Name:':<{col_space}}{ENV.TP_AUTO_K8S_DP_NAME}")
                if ENV.TP_AUTO_IS_CONFIG_O11Y:
                    print(f"{'DataPlane Configured:':<{col_space}}{ENV.TP_AUTO_IS_CONFIG_O11Y}")

                print(f"{'Provisioned capabilities:':<{col_space}}"
                      f"{'BWCE ' if ENV.TP_AUTO_IS_PROVISION_BWCE else ''}"
                      f"{'EMS ' if ENV.TP_AUTO_IS_PROVISION_EMS else ''}"
                      f"{'Flogo ' if ENV.TP_AUTO_IS_PROVISION_FLOGO else ''}"
                      f"{'Pulsar ' if ENV.TP_AUTO_IS_PROVISION_PULSAR else ''}"
                      f"{'TibcoHub' if ENV.TP_AUTO_IS_PROVISION_TIBCOHUB else ''}"
                      )

                if ENV.TP_AUTO_IS_PROVISION_FLOGO:
                    print(f"{'Flogo App Name:':<{col_space}}{ENV.FLOGO_APP_NAME}")
                    if ENV.FLOGO_APP_STATUS != "":
                        print(f"{'Flogo App Status:':<{col_space}}{ENV.FLOGO_APP_STATUS}")
        print("=" * str_num)

    @staticmethod
    def check_dom_visibility(page, dom_selector, interval=10, max_wait=180, is_refresh=False):
        total_attempts = max_wait // interval
        timeout = interval if interval < 5 else 5
        print(f"Check dom visibility, wait {timeout} seconds first, then loop to check")
        page.wait_for_timeout(timeout * 1000)
        for attempt in range(total_attempts):
            if dom_selector.is_visible():
                print("Dom is now visible.")
                return True

            print(f"--- Attempt {attempt + 1}/{total_attempts}, Loop to check: Checking if dom is visible...")
            if attempt <= total_attempts - 1:
                if is_refresh:
                    print(f"Page reload {attempt + 1}")
                    Util.refresh_page(page)
                print(f"Dom not visible. Waiting for {interval} seconds before retrying...")
                page.wait_for_timeout(interval * 1000)

        ColorLogger.warning(f"Dom is still not visible after waiting for {max_wait} seconds.")
        return False

    @staticmethod
    def click_button_until_enabled(page, button_selector):
        button_selector.wait_for(state="visible")
        page.wait_for_function(
            """
            (button) => !button.disabled
            """,
            arg=button_selector.element_handle()
        )
        button_selector.click()
