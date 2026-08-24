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
import sys
import re

import pytz
import html
import time
import urllib.request
from urllib.error import URLError, HTTPError
from playwright.sync_api import sync_playwright
from datetime import datetime
from utils.color_logger import ColorLogger
from utils.env import ENV
from utils.helper import Helper
from utils.report import ReportYaml
from playwright.sync_api import ViewportSize

class Util:
    _page = None
    _browser = None
    _context = None
    _playwright = None
    _run_start_time = None
    _is_trace = False

    @staticmethod
    def get_upload_folder():
        """
        Get the absolute path to the upload folder.
        This method returns the upload folder path relative to the bootstrap directory,
        so it works regardless of where the server is running.

        :return: Absolute path to the upload folder
        """
        return os.path.join(os.path.dirname(os.path.dirname(__file__)), "upload")

    @staticmethod
    def convert_to_absolute_path(file_path):
        """
        Convert relative path to absolute path, handling upload folder paths.

        :param file_path: File path (can be relative or absolute)
        :return: Absolute file path
        """
        if not file_path or os.path.isabs(file_path):
            return file_path

        # If path starts with 'upload/', extract filename and get full path
        if file_path.startswith('upload/'):
            filename = file_path.replace('upload/', '')
            return Helper.get_file_fullpath_in_upload_folder(filename)
        else:
            # Otherwise, assume it's already in upload folder
            return Helper.get_file_fullpath_in_upload_folder(file_path)

    @staticmethod
    def extract_response_array(json_data, key='response'):
        """
        Extract array from JSON response, handling both dict and list formats.

        :param json_data: Parsed JSON data (dict or list)
        :param key: Key to extract from dict (default: 'response')
        :return: Array extracted from the data
        """
        if isinstance(json_data, dict):
            return json_data.get(key, [])
        elif isinstance(json_data, list):
            return json_data
        else:
            return []

    @staticmethod
    def append_common_args(command, debug=False, other_args=None):
        """
        Append common command arguments (debug flag and other_args).

        :param command: Base command string
        :param debug: Enable debug mode
        :param other_args: Additional CLI arguments
        :return: Command with appended arguments
        """
        if debug:
            command += '--debug '
        command += f'{other_args or ""}'
        return command

    @staticmethod
    def print_box(content, width=60, style='single'):
        """
        Print content in a complete box with borders.

        :param content: Content to display (can be string or list of strings)
        :param width: Width of the box (default: 60)
        :param style: Box style - 'single', 'double', or 'bold' (default: 'single')
        """
        # Box drawing characters
        if style == 'double':
            chars = {'tl': '╔', 'tr': '╗', 'bl': '╚', 'br': '╝', 'h': '═', 'v': '║'}
        elif style == 'bold':
            chars = {'tl': '┏', 'tr': '┓', 'bl': '┗', 'br': '┛', 'h': '━', 'v': '┃'}
        else:  # single
            chars = {'tl': '┌', 'tr': '┐', 'bl': '└', 'br': '┘', 'h': '─', 'v': '│'}

        # Convert content to list if it's a string
        if isinstance(content, str):
            content_lines = [content]
        else:
            content_lines = content

        # Print top border
        print(f"{chars['tl']}{chars['h'] * width}{chars['tr']}")

        # Print content lines
        for line in content_lines:
            # Pad line to width
            padded_line = line.ljust(width - 2)
            print(f"{chars['v']} {padded_line} {chars['v']}")

        # Print bottom border
        print(f"{chars['bl']}{chars['h'] * width}{chars['br']}")

    @staticmethod
    def get_dns_ip():
        awk_script = '/^Name:/ {getline; if ($1=="Address:") print $2}'
        result = Helper.get_command_output(f"nslookup *.{ENV.TP_AUTO_CP_DNS_DOMAIN} | awk '{awk_script}'", True)
        # Only return the first IP address if multiple are found
        return result.strip().split('\n')[0] if result else ""

    @staticmethod
    def browser_launch(is_headless=ENV.IS_HEADLESS):
        if Util._browser is None:
            dns_ip = Util.get_dns_ip()
            # PCP-15474: Fix browser launch failure due to --single-process issue in windows VDI environment
            args = [
            ]
            if dns_ip:
                args.append(f"--host-resolver-rules=MAP *.{ENV.TP_AUTO_CP_DNS_DOMAIN} {dns_ip}")
            Util._run_start_time = time.time()
            Util._playwright = sync_playwright().start()
            Util._browser = Util._playwright.chromium.launch(
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
            viewport=ViewportSize(width=2000, height=1080),
            record_video_size=ViewportSize(width=2000, height=1080),
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

        if Util._playwright is not None:
            Util._playwright.stop()
            Util._playwright = None

        if Util._run_start_time is not None:
            chicago_time = datetime.now(pytz.timezone(ENV.TIME_ZONE)).strftime('%m/%d/%Y %H:%M:%S')
            total_seconds = time.time() - Util._run_start_time
            minutes = int(total_seconds // 60)
            seconds = total_seconds % 60
            ColorLogger.info(f"Total running time: {minutes} minutes {seconds:.2f} seconds")
            ColorLogger.info(f"Current time: {chicago_time} at {ENV.TIME_ZONE}")

    @staticmethod
    def stop_tracing():
        if Util._context is not None and Util._is_trace and ENV.TP_AUTO_REPORT_TRACE:
            trace_path = os.path.join(
                ENV.TP_AUTO_REPORT_PATH,
                str(ENV.RETRY_TIME_FOLDER),
                "trace.zip"
            )
            Util._context.tracing.stop(path=trace_path)
            Util._is_trace = False
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
        page.screenshot(path=file_path, full_page=True, animations="disabled")
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
    def save_command_to_file(command, filename):
        """
        Saves a command string to a temporary file in the 'dp_commands' directory.

        Args:
            command (str): The command string to be saved.
            filename (str): The name of the file to be created.

        Returns:
            str: The path to the created file.
        """
        # Create 'dp_commands' folder if it does not exist
        steps_dir = os.path.join(ENV.TP_AUTO_REPORT_PATH, "dp_commands")
        if not os.path.exists(steps_dir):
            os.makedirs(steps_dir, exist_ok=True)
        # Define the full file path
        file_path = os.path.join(steps_dir, filename)
        ColorLogger.info(f"Saving command script to file: {file_path}")
        ColorLogger.info("Command:\n" + html.escape(command))
        with open(file_path, 'w') as temp_script:
            temp_script.write(f"#!/bin/bash\n{command}\n")
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
        space_nums = 45
        print("=" * str_num)
        print(f"{'Control Plane information': ^{str_num}}")
        print("Is cluster accessible:", "√" if ENV.IS_CLUSTER_ACCESSIBLE else "X")
        node_name = Helper.get_node_name()
        ip = Helper.get_node_ip()
        if ENV.TP_AUTO_KUBECONFIG:
            # get ip from KUBECONFIG file name
            kubeconfig_file = os.path.basename(ENV.TP_AUTO_KUBECONFIG)
            ip_match = re.search(r'(\d{1,3}(?:\.\d{1,3}){3})', kubeconfig_file)
            if ip_match:
                ip = ip_match.group(1)
        if node_name:
            print("{:<{}} {}".format("Node name", space_nums, "IP"))
            print("{:<{}} {}".format(node_name, space_nums, ip))
            print("-" * str_num)

        cp_platform_bootstrap_version = Helper.get_cp_platform_bootstrap_version()
        if cp_platform_bootstrap_version:
            print("platform-bootstrap: ", cp_platform_bootstrap_version)

        cp_platform_base_version = Helper.get_cp_platform_base_version()
        if cp_platform_base_version:
            print("platform-base: ", cp_platform_bootstrap_version)

        all_tibco_cp_version = Helper.get_all_tibco_cp_version()
        if all_tibco_cp_version:
            print(f"All TIBCO CP versions:\n{all_tibco_cp_version}")
            print("-" * str_num)

        deployment_images = Helper.get_deployment_images(f"{ENV.TP_AUTO_CP_NAMESPACE}")
        if deployment_images:
            print(f"All Deployment images:")
            images = deployment_images.splitlines()
            print("{:<{}} {}".format("Image name", space_nums, "Version"))
            for image in images:
                if ":" in image:
                    name, version = image.split(":", 1)
                else:
                    name, version = image, ""
                print("{:<{}} {}".format(name, space_nums, version))
            print("-" * str_num)

        if ENV.TP_AUTO_KUBECONFIG:
            print("KUBECONFIG: ", ENV.TP_AUTO_KUBECONFIG)

    @staticmethod
    def print_env_info(is_print_auth=True, is_print_dp=True):
        str_num = 90
        col_space = 30
        print("=" * str_num)
        if is_print_auth:
            print("-" * str_num)
            print(f"{'Login Credentials': ^{str_num}}")
            auto_token = Helper.get_auto_token()
            if auto_token:
                tibco_cp_installation_time = Helper.get_auto_token_creation().split("T")
                print("-" * str_num)
                print(
                    f"{'OAuth Token:':<{col_space}}{auto_token}",
                    " " * 5,
                    ENV.TP_AUTO_TOKEN_DURATION,
                    ENV.TP_AUTO_TOKEN_DURATION_UNIT,
                    f"since {tibco_cp_installation_time[0]}" if len(tibco_cp_installation_time) else ""
                )
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

            # Label overrides for known dataplane fields (key -> (label, display_value))
            dp_field_labels = {
                "o11yConfig": ("DataPlane O11y Configured", "true"),
                "o11yWidget": ("Observability Widget", "true"),
                "ActivationFile": ("Activation Service", "true"),
                "ActivationUrl": ("Activation Service", "true"),
                "storage": ("DataPlane storage", ENV.TP_AUTO_STORAGE_CLASS),
            }
            # Label overrides for known capability fields
            cap_field_labels = {
                "provisionConnector": "Provision connector",
                "appBuild": "Create App Build",
            }
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

                    for field_key in ReportYaml.get_dataplane_field_keys(dp_name):
                        stored_value = ReportYaml.get_dataplane_info(dp_name, field_key)
                        if not stored_value:
                            continue
                        if field_key in dp_field_labels:
                            if stored_value == "true":
                                label, display_value = dp_field_labels[field_key]
                                print(f"{label:<{col_space}}{display_value}")
                        else:
                            print(f"{field_key:<{col_space}}{stored_value}")

                    dp_capabilities = ReportYaml.get_capabilities(dp_name)
                    if len(dp_capabilities) > 0:
                        print(f"{'Provisioned capabilities':<{col_space}}"
                              f"{[cap.upper() for cap in dp_capabilities]}"
                              )

                    for dp_capability in dp_capabilities:
                        app_names = ReportYaml.get_capability_apps(dp_name, dp_capability)
                        cap_keys = ReportYaml.get_capability_field_keys(dp_name, dp_capability)
                        if len(app_names) > 0 or len(cap_keys) > 0:
                            print(f"{dp_capability.capitalize()}")

                        for field_key in cap_keys:
                            field_value = ReportYaml.get_capability_info(dp_name, dp_capability, field_key)
                            if field_value:
                                label = cap_field_labels.get(field_key, field_key)
                                print(f"    {label:<{col_space}}{field_value}")

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
        except (HTTPError, URLError):
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
        selector = None
        try:
            m = re.search(r"selector=(['\"])(.*?)\1", repr(dom_selector))
            selector = m.group(2) if m else None
        except Exception as e:
            print(f"Error extracting selector: {e}")

        for attempt in range(total_attempts):
            if selector: print(f"Checking dom: {selector}")

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
    def check_dom_enabled(page, dom_selector, interval=2, max_wait=60):
        """Poll until a (present/visible) DOM element becomes ENABLED — mirrors
        check_dom_visibility's logged-polling contract but keys on is_enabled().

        For fields that render visible-but-disabled while the UI awaits async
        readiness — e.g. the Register-Gateway wizard's gateway-name input, which
        stays disabled with aria-describedby="register-name-awaiting-dp" until the
        wizard's target-DP list resolves (PCP-21482). Playwright's .fill()/.click()
        auto-wait for editability and blow the default 30s timeout on a field that
        is still disabled; polling is_enabled() first lets the caller screenshot and
        exit gracefully instead. Call only AFTER the element is visible (is_enabled()
        needs the element to exist). Returns True as soon as it is enabled, False
        after max_wait.
        """
        total_attempts = max_wait // interval
        timeout = interval if interval < 5 else 5
        print(f"Check dom enabled, wait {timeout} seconds first, then loop to check for {max_wait} seconds.")
        page.wait_for_timeout(timeout * 1000)
        selector = None
        try:
            m = re.search(r"selector=(['\"])(.*?)\1", repr(dom_selector))
            selector = m.group(2) if m else None
        except Exception as e:
            print(f"Error extracting selector: {e}")

        for attempt in range(total_attempts):
            if selector: print(f"Checking dom enabled: {selector}")

            # is_enabled() RAISES when the locator resolves to no element (unlike
            # is_visible(), which returns False) — e.g. a transient *ngIf detach at
            # poll time. Swallow it and keep polling so this helper honours its
            # boolean contract (never raises) and the caller's graceful
            # screenshot/exit path still runs.
            try:
                if dom_selector.is_enabled():
                    print("Dom is now enabled.")
                    return True
            except Exception as e:
                print(f"is_enabled() not resolvable yet ({e}); will retry...")

            print(f"--- Attempt {attempt + 1}/{total_attempts}, Loop to check: Checking if dom is enabled...")
            if attempt < total_attempts - 1:  # no need to sleep after the final check
                print(f"Dom not enabled. Waiting for {interval} seconds before retrying...")
                page.wait_for_timeout(interval * 1000)

        ColorLogger.warning(f"Dom is still not enabled after waiting for {max_wait} seconds.")
        return False

    @staticmethod
    def check_dom_attribute(page, dom_selector, attribute, expected, interval=1, max_wait=6) -> bool:
        """Poll until a DOM element's ATTRIBUTE equals expected — mirrors
        check_dom_visibility / check_dom_enabled's logged-polling contract but keys
        on get_attribute().

        For state the UI publishes through an attribute that is written
        asynchronously. The Assign-Permissions wizard is the motivating case: the
        wildcard-domains checkbox exposes its state via aria-checked, but the
        component pre-seeds that to "false" and only writes the real value inside
        the resource-instances XHR callback. The attribute is therefore PRESENT and
        wrong for a short window, so a zero-wait get_attribute() — how the existing
        bug reads it — sees stale state and makes the caller click a checkbox that
        was already ticked, toggling an existing grant back OFF.

        DELIBERATE DEVIATION from both siblings: this does an IMMEDIATE first read
        BEFORE any wait, and only then sleeps interval between attempts.
        check_dom_visibility opens with a blind min(interval, 5)s sleep; here the
        caller has already deterministically settled on the XHR, so a leading blind
        wait buys nothing and is pure cost on an install task that already carries
        retryCount:10.

        Returns True as soon as the attribute equals expected, False after max_wait.
        Never raises.
        """
        # Read at least once even when max_wait < interval, so the "immediate first
        # read" contract holds for every caller-supplied timing. Round the attempt
        # count UP so max_wait stays a true upper bound rather than being truncated
        # away when it is not an exact multiple of interval, and floor interval at 1
        # so a caller passing 0 gets a busy-free poll instead of ZeroDivisionError -
        # this helper's whole contract is that it never raises.
        interval = max(1, interval)
        total_attempts = max(1, -(-max_wait // interval))
        print(f"Check dom attribute '{attribute}' == '{expected}', check immediately, then loop to check for {max_wait} seconds.")
        selector = None
        try:
            m = re.search(r"selector=(['\"])(.*?)\1", repr(dom_selector))
            selector = m.group(2) if m else None
        except Exception as e:
            print(f"Error extracting selector: {e}")

        for attempt in range(total_attempts):
            if selector: print(f"Checking dom attribute: {selector}")

            # get_attribute() RAISES when the locator resolves to no element (a
            # transient *ngIf detach while the wizard re-renders). Swallow it and
            # keep polling so this helper honours its boolean contract.
            try:
                # Bound the read explicitly: get_attribute() forwards Playwright's 30s
                # default when the locator resolves to nothing, so an unbounded call would
                # make max_wait a per-attempt budget instead of the wall-clock cap callers
                # rely on to stay inert quickly.
                actual = dom_selector.get_attribute(attribute, timeout=interval * 1000)
                if actual == expected:
                    print(f"Dom attribute '{attribute}' is now '{expected}'.")
                    return True
                print(f"Dom attribute '{attribute}' is '{actual}', expected '{expected}'.")
            except Exception as e:
                print(f"get_attribute() not resolvable yet ({e}); will retry...")

            print(f"--- Attempt {attempt + 1}/{total_attempts}, Loop to check: Checking dom attribute...")
            if attempt < total_attempts - 1:  # no need to sleep after the final check
                print(f"Dom attribute not matched. Waiting for {interval} seconds before retrying...")
                try:
                    page.wait_for_timeout(interval * 1000)
                except Exception as e:
                    # a torn-down page/context raises here; stop polling and report the
                    # miss rather than break the never-raises contract on the way out
                    print(f"Page is no longer waitable ({e}); stopping the poll.")
                    break

        ColorLogger.warning(f"Dom attribute '{attribute}' is still not '{expected}' after waiting for {max_wait} seconds.")
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

    @staticmethod
    def parse_json_result(result_str):
        if not result_str or result_str.strip() == "":
            print("Error: Empty JSON output.")
            return None
        try:
            return json.loads(result_str)
        except json.JSONDecodeError:
            print("Error: Invalid JSON output.")
            print(result_str)
            return None

    @staticmethod
    def clean_ansi_escape(line, is_bytes=True):
        ansi_escape = re.compile(r'\x1B[@-_][0-?]*[ -/]*[@-~]')
        if is_bytes:
            line = line.decode("utf-8", errors="replace")
        line = ansi_escape.sub('', line)
        return line.strip()
