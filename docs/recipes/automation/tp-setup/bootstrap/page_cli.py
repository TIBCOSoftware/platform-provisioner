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
# CLI-based DP deployment orchestrator.
#
# This script mirrors the workflow of page_dp.py but uses the tibcop CLI
# for DP operations instead of GUI (Playwright) automation where possible.
#
# Steps that use GUI (Playwright): login, permissions, global O11Y config,
#   BMDP domain configs (BW5 RVDM/EMSDM, BW6, EMS), O11Y switch-to-global
# Steps that use CLI (tibcop): DP registration, resource creation,
#   capability provisioning, app build & deploy, BMDP registration
# Steps that use REST API: app endpoint testing
#
# Usage:
#   export TP_AUTO_USE_CLI=true
#   python -u -m page_cli
#
# Environment variables:
#   TP_AUTO_USE_CLI=true          - Enable CLI mode (required)
#   TP_AUTO_K8S_DP_NAME           - DataPlane name (same as GUI mode)
#   TIBCOP_CLI_CPURL               - CP URL (auto-derived from TP_AUTO_LOGIN_URL if not set)
#   TIBCOP_CLI_OAUTH_TOKEN         - OAuth token (auto-read from k8s secret if not set)

import os
import sys
import threading
import traceback

from cli_object.facade import TibcopCLI
from cli_object.orchestrator import THREAD_STAGGER_DELAY
from page_object.po_auth import PageObjectAuth
from page_object.po_bmdp_config import PageObjectBMDPConfiguration
from page_object.po_dataplane import PageObjectDataPlane
from page_object.po_dp_config import PageObjectDataPlaneConfiguration
from page_object.po_dp_ems import PageObjectDataPlaneEMS
from page_object.po_settings import PageObjectSettings
from page_object.po_user_management import PageObjectUserManagement
from utils.color_logger import ColorLogger
from utils.env import ENV
from utils.helper import Helper
from utils.report import ReportYaml
from utils.util import Util

# Serialize all GUI (Playwright) callbacks so concurrent threads
# don't stomp on the shared browser/tracing/video state in Util.
_gui_lock = threading.Lock()


def _run_gui_steps(page):
    """Run GUI-only steps: login, permissions, global O11Y config."""
    # Step 1: User login and permissions
    ColorLogger.info("=" * 60)
    ColorLogger.info("CLI Mode - Step 1: User login & permissions (GUI)")
    ColorLogger.info("=" * 60)

    po_auth = PageObjectAuth(page)
    po_auth.login()
    po_auth.login_check()

    po_user_management = PageObjectUserManagement(page)
    po_user_management.set_user_permission()

    # Step 2: Global O11Y config
    ColorLogger.info("=" * 60)
    ColorLogger.info("CLI Mode - Step 2: Global O11Y configuration (GUI)")
    ColorLogger.info("=" * 60)

    po_dp_config = PageObjectDataPlaneConfiguration(page)
    po_dp_config.o11y_config_dataplane_resource(ENV.TP_AUTO_DP_NAME_GLOBAL)

    # Configure Global activation (file upload or URL) via GUI
    po_dp_config.o11y_config_activation(ENV.TP_AUTO_DP_NAME_GLOBAL)

    # Step 3: Set OAuth token (if not already available)
    token = os.environ.get("TIBCOP_CLI_OAUTH_TOKEN") or Helper.get_auto_token()
    if not token:
        ColorLogger.info("No OAuth token found, creating via GUI Settings...")
        po_settings = PageObjectSettings(page)
        po_settings.set_oauth_token()

    # Step 4: DP-level O11Y config (switch to global + activation)
    # This must happen via GUI after the DP is created by CLI.
    # Since the DP may not exist yet at this point (CLI creates it later),
    # we return the page objects needed for post-DP O11Y config.
    po_auth.logout()


def _run_gui_dp_o11y(dp_name):
    """Run GUI-based DP-level O11Y configuration after DP is created via CLI.

    Opens a new browser session to configure O11Y switch-to-global and activation
    on the DataPlane. This is required because there is no CLI equivalent for
    O11Y configuration.

    Acquires _gui_lock to prevent concurrent browser sessions.
    """
    if not ENV.TP_AUTO_IS_CONFIG_O11Y:
        ColorLogger.info("TP_AUTO_IS_CONFIG_O11Y is false, skipping DP-level O11Y config")
        return

    # Check report: skip if switchGlobal and activation already configured
    switch_global = ReportYaml.get_dataplane_info(dp_name, "switchGlobal")
    activation = ReportYaml.get_dataplane_info(dp_name, "activation")
    if str(switch_global).lower() == "true" and activation:
        ColorLogger.success(f"DP '{dp_name}' O11Y already configured (from report: switchGlobal={switch_global}, activation={activation}), skipping")
        return

    with _gui_lock:
        ColorLogger.info("=" * 60)
        ColorLogger.info(f"CLI Mode - DP O11Y configuration for '{dp_name}' (GUI)")
        ColorLogger.info("=" * 60)

        page = Util.browser_launch()
        try:
            po_auth = PageObjectAuth(page)
            po_auth.login()
            po_auth.login_check()

            po_dp_config = PageObjectDataPlaneConfiguration(page)
            po_dp_config.o11y_config_switch_to_global(dp_name)
            po_dp_config.o11y_config_activation(dp_name)

            po_auth.logout()
            ColorLogger.success(f"DP-level O11Y configured for '{dp_name}'")
        except Exception as e:
            ColorLogger.error(f"DP-level O11Y config failed: {e}")
            traceback.print_exc()
        finally:
            Util.browser_close()


def _run_gui_ems_provision(dp_name):
    """Run GUI-based EMS capability provisioning.

    Opens a new browser session to provision EMS capability on the DataPlane.
    EMS provisioning has no CLI equivalent.

    Acquires _gui_lock to prevent concurrent browser sessions.
    """
    with _gui_lock:
        ColorLogger.info("=" * 60)
        ColorLogger.info(f"CLI Mode - Provision EMS for '{dp_name}' (GUI)")
        ColorLogger.info("=" * 60)

        page = Util.browser_launch()
        try:
            po_auth = PageObjectAuth(page)
            po_auth.login()
            po_auth.login_check()

            po_dp_ems = PageObjectDataPlaneEMS(page)
            po_dp_ems.goto_left_navbar_dataplane()
            po_dp_ems.goto_dataplane(dp_name)
            po_dp_ems.ems_provision_capability(dp_name, ENV.TP_AUTO_EMS_CAPABILITY_SERVER_NAME)

            ReportYaml.set_capability(dp_name, "ems")
            po_auth.logout()
            ColorLogger.success(f"EMS capability provisioned for '{dp_name}'")
        except Exception as e:
            ColorLogger.error(f"EMS provisioning failed: {e}")
            traceback.print_exc()
        finally:
            Util.browser_close()


def _run_gui_bmdp_config(bmdp_name):
    """Run GUI-based BMDP domain configuration after BMDP is created via CLI.

    Opens a new browser session to configure:
    - BW5 RV Domain Manager (RVDM)
    - EMS Server registration
    - BW5 EMS Domain Manager (EMSDM)
    - BW6 Domain Manager
    - O11Y switch-to-global
    These operations have no CLI equivalent.

    Acquires _gui_lock to prevent concurrent browser sessions.
    """
    with _gui_lock:
        ColorLogger.info("=" * 60)
        ColorLogger.info(f"CLI Mode - BMDP domain configuration for '{bmdp_name}' (GUI)")
        ColorLogger.info("=" * 60)

        page = Util.browser_launch()
        try:
            po_auth = PageObjectAuth(page)
            po_auth.login()
            po_auth.login_check()

            po_dp = PageObjectDataPlane(page)
            po_bmdp_config = PageObjectBMDPConfiguration(page)

            # BW5 RVDM config
            if ENV.TP_AUTO_IS_ENABLE_RVDM and not po_bmdp_config.is_app_running("BW5", ENV.TP_AUTO_K8S_BMDP_BW5_RVDM, ENV.TP_AUTO_BW5_APP_NAME):
                po_dp.goto_dataplane(bmdp_name)
                po_bmdp_config.goto_dataplane_config()
                if po_bmdp_config.dp_config_bw5_rvdm(ENV.TP_AUTO_K8S_BMDP_BW5_RVDM):
                    po_dp.goto_dataplane(bmdp_name)
                    if po_bmdp_config.goto_products("BW5"):
                        po_bmdp_config.check_bmdp_app_status_by_app_name("BW5", ENV.TP_AUTO_K8S_BMDP_BW5_RVDM, ENV.TP_AUTO_BW5_APP_NAME)

            # EMS Server config
            if ENV.TP_AUTO_IS_ENABLE_EMSDM and not po_bmdp_config.is_ems_server_connected(ENV.TP_BMDP_IMAGE_TAG_EMS):
                po_dp.goto_dataplane(bmdp_name)
                po_bmdp_config.goto_dataplane_config()
                po_bmdp_config.dp_config_ems(ENV.TP_BMDP_IMAGE_TAG_EMS)

            # BW5 EMSDM config
            if ENV.TP_AUTO_IS_ENABLE_EMSDM and not po_bmdp_config.is_app_running("BW5", ENV.TP_AUTO_K8S_BMDP_BW5_EMSDM, ENV.TP_AUTO_BW5_APP_NAME):
                po_dp.goto_dataplane(bmdp_name)
                po_bmdp_config.goto_dataplane_config()
                if po_bmdp_config.dp_config_bw5_emsdm(ENV.TP_AUTO_K8S_BMDP_BW5_EMSDM):
                    po_dp.goto_dataplane(bmdp_name)
                    if po_bmdp_config.goto_products("BW5"):
                        po_bmdp_config.check_bmdp_app_status_by_app_name("BW5", ENV.TP_AUTO_K8S_BMDP_BW5_EMSDM, ENV.TP_AUTO_BW5_APP_NAME)

            # BW6 Domain config
            if ENV.TP_AUTO_IS_ENABLE_BW6DM and not po_bmdp_config.is_app_running("BW6", ENV.TP_AUTO_K8S_BMDP_BW6DM, "mySleep.application"):
                po_dp.goto_dataplane(bmdp_name)
                po_bmdp_config.goto_dataplane_config()
                if po_bmdp_config.dp_config_bw6(ENV.TP_AUTO_K8S_BMDP_BW6DM):
                    po_dp.goto_dataplane(bmdp_name)
                    if po_bmdp_config.goto_products("BW6"):
                        po_bmdp_config.check_bmdp_app_status_by_app_name("BW6", ENV.TP_AUTO_K8S_BMDP_BW6DM, "mySleep.application")

            # O11Y switch to global + activation
            if ENV.TP_AUTO_IS_CONFIG_O11Y:
                po_dp.goto_dataplane(bmdp_name)
                po_bmdp_config.goto_dataplane_config()
                po_bmdp_config.o11y_config_switch_to_global(bmdp_name)

                po_dp_config = PageObjectDataPlaneConfiguration(page)
                

            # Take screenshot and logout
            po_dp.goto_left_navbar_dataplane()
            po_dp.goto_dataplane(bmdp_name)
            Util.screenshot_page(page, f"success-{bmdp_name}.png")
            po_auth.logout()
            ColorLogger.success(f"BMDP domain configuration completed for '{bmdp_name}'")
        except Exception as e:
            ColorLogger.error(f"BMDP domain configuration failed: {e}")
            traceback.print_exc()
        finally:
            Util.browser_close()


def _run_dp_setup(cli, errors):
    """Thread target: run K8S DataPlane setup."""
    try:
        cli.orchestrator.run_dataplane_setup(
            ENV.TP_AUTO_K8S_DP_NAME,
            ENV.TP_AUTO_K8S_DP_NAMESPACE,
            on_o11y_needed=_run_gui_dp_o11y,
            on_ems_needed=_run_gui_ems_provision
        )
    except Exception as e:
        ColorLogger.error(f"[DP] Setup failed: {e}")
        traceback.print_exc()
        errors.append(e)


def _run_bmdp_setup(cli, errors):
    """Thread target: run BMDP (Control Tower) setup."""
    try:
        cli.orchestrator.run_bmdp_setup(
            ENV.TP_AUTO_K8S_BMDP_NAME,
            ENV.TP_AUTO_K8S_BMDP_NAMESPACE,
            ENV.TP_AUTO_K8S_BMDP_SERVICE_ACCOUNT,
            ENV.TP_AUTO_FQDN_BMDP,
            on_config_needed=_run_gui_bmdp_config
        )
    except Exception as e:
        ColorLogger.error(f"[BMDP] Setup failed: {e}")
        traceback.print_exc()
        errors.append(e)


def run():
    """Main entry point for CLI-based DP deployment."""
    ColorLogger.info("=" * 60)
    ColorLogger.info("Starting CLI-based DP deployment workflow")
    ColorLogger.info("=" * 60)

    ENV.pre_check()

    # Write CP environment info to report
    Util.set_cp_env()

    # Phase 1: GUI steps (login, permissions, O11Y)
    page = None
    try:
        page = Util.browser_launch()
        _run_gui_steps(page)
    except Exception as e:
        ColorLogger.error(f"GUI steps failed: {e}")
        traceback.print_exc()
        return
    finally:
        # Always close browser - no longer needed for CLI steps
        if page:
            ColorLogger.info("Closing browser - remaining steps use CLI")
            Util.browser_close()
            page = None

    # Phase 2: CLI steps
    cli = TibcopCLI.from_env()
    if not cli:
        ColorLogger.error("Failed to build CLI environment. Aborting.")
        return

    # Global Activation Server (CLI fallback — only if GUI didn't configure)
    if ReportYaml.get_dataplane_info("Global", "activation"):
        ColorLogger.success("Global activation already configured, skipping CLI")
    elif ENV.TP_ACTIVATION_URL:
        ColorLogger.info("Creating Global Activation Server resource via CLI...")
        result = cli.resource.create_activation_server("Global", scope="SUBSCRIPTION")
        if result:
            ReportYaml.set_dataplane_info("Global", "activation", "server")

    # Phase 2: Create DP and BMDP concurrently
    threads = []
    errors = []

    if ENV.TP_AUTO_IS_CREATE_DP:
        t = threading.Thread(
            target=_run_dp_setup,
            args=(cli, errors),
            name="DP-Setup"
        )
        threads.append(t)

    if ENV.TP_AUTO_IS_CREATE_BMDP:
        t = threading.Thread(
            target=_run_bmdp_setup,
            args=(cli, errors),
            name="BMDP-Setup"
        )
        threads.append(t)

    for i, t in enumerate(threads):
        t.start()
        if i < len(threads) - 1:
            import time
            time.sleep(THREAD_STAGGER_DELAY)
    for t in threads:
        t.join()

    # Phase 3: Print environment info
    Util.print_env_info(is_print_auth=False)

    if errors:
        ColorLogger.error("=" * 60)
        ColorLogger.error(f"CLI-based DP deployment failed with {len(errors)} error(s)")
        ColorLogger.error("=" * 60)
        sys.exit(1)

    ColorLogger.info("=" * 60)
    ColorLogger.success("CLI-based DP deployment workflow completed")
    ColorLogger.info("=" * 60)


if __name__ == "__main__":
    run()
