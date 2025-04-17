#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary

import os
import sys
import pytz
import time
import urllib.request
from urllib.error import URLError, HTTPError
from playwright.sync_api import sync_playwright
from datetime import datetime
from utils.color_logger import ColorLogger
from utils.env import ENV
from utils.helper import Helper
from utils.report import ReportYaml

class Util:
    _page = None
    _browser = None
    _context = None
    _run_start_time = None
    _is_trace = False

    @staticmethod
    def get_dns_ip():
        awk_script = '/^Name:/ {getline; if ($1=="Address:") print $2}'
        return Helper.get_command_output(f"nslookup *.{ENV.TP_AUTO_CP_DNS_DOMAIN} | awk '{awk_script}'", True)

    @staticmethod
    def browser_launch(is_headless=ENV.IS_HEADLESS):
        if Util._browser is None:
            dns_ip = Util.get_dns_ip()
            args = []
            if dns_ip:
                args.append(f"--host-resolver-rules=MAP *.{ENV.TP_AUTO_CP_DNS_DOMAIN} {dns_ip}")
            Util._run_start_time = time.time()
            playwright = sync_playwright().start()
            Util._browser = playwright.chromium.launch(
                headless=is_headless,
                args=args
            )
            ColorLogger.success("Browser Launched Successfully.")

        videos_dir = os.path.join(
            ENV.TP_AUTO_REPORT_PATH,
            str(ENV.RETRY_TIME_FOLDER)
        )
        print(f"Record video to {videos_dir}")
        Util._context = Util._browser.new_context(
            viewport={"width": 2000, "height": 1080},
            record_video_size={"width": 2000, "height": 1080},
            record_video_dir=videos_dir,
            ignore_https_errors=True,
            accept_downloads=True
        )
        if ENV.TP_AUTO_REPORT_TRACE:
            Util._is_trace = True
            ColorLogger.info("Start tracing with screenshots, snapshots, and sources.")
            Util._context.tracing.start(screenshots=True, snapshots=True, sources=True)
        Util._page = Util._context.new_page()
        return Util._page

    @staticmethod
    def browser_close():
        if Util._context is not None:
            Util.stop_tracing()
            Util._context.close()
            if Util._page and Util._page.video:
                video_path = Util._page.video.path()
                ColorLogger.info(f"Video file saved to: {video_path}")

        if Util._browser is not None:
            Util._browser.close()
            Util._browser = None
            ColorLogger.success("Browser Closed Successfully.")

        if Util._run_start_time is not None:
            chicago_time = datetime.now(pytz.timezone("America/Chicago")).strftime('%m/%d/%Y %H:%M:%S')
            total_seconds = time.time() - Util._run_start_time
            minutes = int(total_seconds // 60)
            seconds = total_seconds % 60
            ColorLogger.info(f"Total running time: {minutes} minutes {seconds:.2f} seconds")
            ColorLogger.info(f"Current time: {chicago_time} at America/Chicago")

    @staticmethod
    def stop_tracing():
        if Util._context is not None and Util._is_trace and ENV.TP_AUTO_REPORT_TRACE:
            trace_path = os.path.join(
                ENV.TP_AUTO_REPORT_PATH,
                str(ENV.RETRY_TIME_FOLDER),
                "trace.zip"
            )
            Util._context.tracing.stop(path=trace_path)
            ColorLogger.info(f"Save tracing to file: {trace_path}")

    @staticmethod
    def screenshot_page(page, filename):
        if filename == "":
            ColorLogger.warning(f"Screenshot filename={filename} MUST be set.")
            return
        screenshot_dir = os.path.join(
            ENV.TP_AUTO_REPORT_PATH,
            str(ENV.RETRY_TIME_FOLDER),
            "screenshots"
        )
        # check folder screenshot_dir exist or not, if not create it
        if not os.path.exists(screenshot_dir):
            os.makedirs(screenshot_dir, exist_ok=True)
        file_path = os.path.join(screenshot_dir, filename)
        page.screenshot(path=file_path, full_page=True)
        print(f"Screenshot saved to {file_path}")

    @staticmethod
    def wait_for_success_message(page, timeout=30):
        start_time = time.time()

        while True:
            elapsed_time = time.time() - start_time
            if elapsed_time > timeout:
                print("Timeout: Neither success nor error notification appeared.")
                return None

            try:
                if page.locator(".notification-message").is_visible() or page.locator(".pl-notification--success").is_visible():
                    return True

                if page.locator(".pl-notification--error").is_visible():
                    return False
            except Exception as e:
                print(f"An unexpected error occurred: {e}")
                pass
            time.sleep(0.5)

    @staticmethod
    def download_file(file_obj, filename):
        """
        Downloads a file and saves it to the 'dp_commands' directory.

        Args:
            file_obj: The content of the file to be saved. It should have a `save_as` method.
            filename (str): The name of the file to be saved.

        Returns:
            str: The path to the saved file.
        """
        # Create 'dp_commands' folder if it does not exist
        steps_dir = os.path.join(ENV.TP_AUTO_REPORT_PATH, "dp_commands")
        if not os.path.exists(steps_dir):
            os.makedirs(steps_dir, exist_ok=True)
        # Define the full file path
        file_path = os.path.join(steps_dir, filename)
        # Save the file content to the specified path
        file_obj.save_as(file_path)
        print(f"File saved to {file_path}")
        return file_path

    @staticmethod
    def exit_error(message, page=None, filename=""):
        if page is not None:
            Util.screenshot_page(page, f"error-{filename}")
        Util.stop_tracing()
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
    def set_cp_env():
        ReportYaml.set(".ENV.CP_MAIL_URL", ENV.TP_AUTO_MAIL_URL)
        ReportYaml.set(".ENV.CP_ADMIN_URL", ENV.TP_AUTO_ADMIN_URL)
        ReportYaml.set(".ENV.CP_ADMIN_USER", ENV.CP_ADMIN_EMAIL)
        ReportYaml.set(".ENV.CP_ADMIN_PASSWORD", ENV.CP_ADMIN_PASSWORD)
        ReportYaml.set(".ENV.CP_URL", ENV.TP_AUTO_LOGIN_URL)
        ReportYaml.set(".ENV.CP_USER", ENV.DP_USER_EMAIL)
        ReportYaml.set(".ENV.CP_PASSWORD", ENV.DP_USER_PASSWORD)
        ReportYaml.set(".ENV.ELASTIC_URL", ENV.TP_AUTO_ELASTIC_URL)
        ReportYaml.set(".ENV.KIBANA_URL", ENV.TP_AUTO_KIBANA_URL)
        ReportYaml.set(".ENV.ELASTIC_USER", ENV.TP_AUTO_ELASTIC_USER)
        ReportYaml.set(".ENV.ELASTIC_PASSWORD", ENV.TP_AUTO_ELASTIC_PASSWORD)
        ReportYaml.set(".ENV.PROMETHEUS_URL", ENV.TP_AUTO_PROMETHEUS_URL)
        ReportYaml.set(".ENV.PROMETHEUS_USER", ENV.TP_AUTO_PROMETHEUS_USER)
        ReportYaml.set(".ENV.PROMETHEUS_PASSWORD", ENV.TP_AUTO_PROMETHEUS_PASSWORD)
        # ReportYaml.sort_yaml_order()

    @staticmethod
    def print_cp_info():
        str_num = 90
        print("=" * str_num)
        print(f"{'Control Plane information': ^{str_num}}")
        print("platform-bootstrap: ", Helper.get_command_output(r"helm list --all-namespaces | grep platform-bootstrap | sed -n 's/.*platform-bootstrap-\(.*\)[[:space:]].*/\1/p' | sed 's/[[:space:]].*//'"))
        print("platform-base: ", Helper.get_command_output(r"helm list --all-namespaces | grep platform-base | sed -n 's/.*platform-base-\(.*\)[[:space:]].*/\1/p' | sed 's/[[:space:]].*//'"))

    @staticmethod
    def print_env_info(is_print_auth=True, is_print_dp=True):
        str_num = 90
        col_space = 30
        print("=" * str_num)
        if is_print_auth:
            print("-" * str_num)
            print(f"{'Login Credentials': ^{str_num}}")
            print("-" * str_num)
            print(f"{'Mail URL:':<{col_space}}{ENV.TP_AUTO_MAIL_URL} {'√' if Util.is_url_accessible(ENV.TP_AUTO_MAIL_URL) else 'X'}")
            print("-" * str_num)
            print(f"{'CP Admin URL:':<{col_space}}{ENV.TP_AUTO_ADMIN_URL} {'√' if Util.is_url_accessible(ENV.TP_AUTO_ADMIN_URL) else 'X'}")
            print(f"{'Admin Email:':<{col_space}}{ENV.CP_ADMIN_EMAIL}")
            print(f"{'Admin Password:':<{col_space}}{ENV.CP_ADMIN_PASSWORD}")
            print("-" * str_num)
            print(f"{'CP Login URL:':<{col_space}}{ENV.TP_AUTO_LOGIN_URL} {'√' if Util.is_url_accessible(ENV.TP_AUTO_LOGIN_URL) else 'X'}")
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

            dataplane_fields = [
                ("o11yConfig", "DataPlane O11y Configured", "true"),
                ("storage", "DataPlane storage", ENV.TP_AUTO_STORAGE_CLASS),
                (ENV.TP_AUTO_INGRESS_CONTROLLER_BWCE, "DataPlane ingress", ENV.TP_AUTO_INGRESS_CONTROLLER_BWCE),
                (ENV.TP_AUTO_INGRESS_CONTROLLER_FLOGO, "DataPlane ingress", ENV.TP_AUTO_INGRESS_CONTROLLER_FLOGO),
                (ENV.TP_AUTO_INGRESS_CONTROLLER_TIBCOHUB, "DataPlane ingress", ENV.TP_AUTO_INGRESS_CONTROLLER_TIBCOHUB),
            ]
            capability_fields = [
                ("provisionConnector", "Provision connector"),
                ("appBuild", "Create App Build"),
            ]
            app_fields = [
                ("status", "Status"),
                ("endpointPublic", "Set endpoint to Public"),
                ("enableTrace", "Enabled trace"),
                ("testedEndpoint", "Tested Endpoint"),
            ]
            dp_names = ReportYaml.get_dataplanes()
            if len(dp_names) > 0:
                print(f"{'Data Plane, Capability, App': ^{str_num}}")
                print("-" * str_num)
                for dp_name in dp_names:
                    print(f"{'DataPlane Name':<{col_space}}{dp_name}")

                    for field_key, field_label, field_value in dataplane_fields:
                        if ReportYaml.get_dataplane_info(dp_name, field_key) == "true":
                            print(f"{field_label:<{col_space}}{field_value}")

                    dp_capabilities = ReportYaml.get_capabilities(dp_name)
                    if len(dp_capabilities) > 0:
                        print(f"{'Provisioned capabilities':<{col_space}}"
                              f"{[cap.upper() for cap in dp_capabilities]}"
                              )

                    for dp_capability in dp_capabilities:
                        app_names = ReportYaml.get_capability_apps(dp_name, dp_capability)
                        provision_connector = ReportYaml.get_capability_info(dp_name, dp_capability, "provisionConnector")
                        app_build = ReportYaml.get_capability_info(dp_name, dp_capability, "appBuild")
                        if len(app_names) > 0 or provision_connector or app_build:
                            print(f"{dp_capability.capitalize()}")

                        for field_key, field_label in capability_fields:
                            field_value = ReportYaml.get_capability_info(dp_name, dp_capability, field_key)
                            if field_value:
                                print(f"    {field_label:<{col_space}}{field_value}")

                        for app_name in app_names:
                            print(f"{'  App Name':<{col_space}}{app_name}")
                            for field_key, field_label in app_fields:
                                field_value = ReportYaml.get_capability_app_info(dp_name, dp_capability, app_name, field_key)
                                if field_value:
                                    print(f"    {field_label:<{col_space}}{field_value}")
        print("=" * str_num)

    @staticmethod
    def is_url_accessible(url, timeout=5):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                return response.status < 400
        except (HTTPError, URLError) as e:
            return False

    @staticmethod
    def check_page_url_accessible(page, url, env_key=None, screenshot_name=None):
        is_accessible = False
        try:
            response = page.goto(url, timeout=5000)
            if response and response.status == 200:
                is_accessible = True
                print(f"URL {url} is accessible")
                if env_key:
                    ReportYaml.set(f".ENV.{env_key}", True)
            return is_accessible
        except Exception as e:
            if screenshot_name:
                Util.warning_screenshot(f"An error occurred while accessing {url}: {e}", page, screenshot_name)
            return is_accessible

    @staticmethod
    def check_dom_visibility(page, dom_selector, interval=10, max_wait=180, is_refresh=False):
        total_attempts = max_wait // interval
        timeout = interval if interval < 5 else 5
        print(f"Check dom visibility, wait {timeout} seconds first, then loop to check for {max_wait} seconds.")
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

    @staticmethod
    def refresh_until_success(page, retry_selector, waiting_selector, message="", max_retries=3):
        current_condition = retry_selector.is_visible()
        # Note: check 3 times, because sometimes page cannot be loaded in time
        # if current_condition is empty, reload page, and check again, only check 3 times, if still empty, exit for loop
        for i in range(max_retries):
            if current_condition:
                return current_condition
            Util.refresh_page(page)
            waiting_selector.wait_for(state="visible")
            if message:
                print(message)
            page.wait_for_timeout(3000)
            current_condition = retry_selector.is_visible()

        return current_condition
