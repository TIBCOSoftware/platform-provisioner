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
# Steps that use GUI (Playwright): EMS capability provisioning
#   (BMDP domain configs now use REST via _run_api_bmdp_config; app-level
#    status verification is deferred — only registration-level "Connected"
#    is recorded, pending ct-auth-token sourcing for the BW5 v1 API)
# Steps that use REST API: OAuth token bootstrap (IAT -> client -> token),
#   Global + DP-scoped O11Y resource creation, Global + DP activation file upload,
#   BMDP domain/agent/EMS-server registration, app endpoint testing
# Steps that use CLI (tibcop): DP registration, resource creation,
#   capability provisioning, app build & deploy, BMDP registration
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
import time
import traceback

from api_object import (
    ApiAuth,
    ApiUserPermission,
    BmdpBw5Api,
    BmdpBw6Api,
    BmdpEmsApi,
    ConsoleApiClient,
    LicenseApi,
    OllyApi,
)
from cli_object.facade import TibcopCLI
from cli_object.orchestrator import THREAD_STAGGER_DELAY
from page_object.po_auth import PageObjectAuth
from page_object.po_dp_ems import PageObjectDataPlaneEMS
from utils.color_logger import ColorLogger
from utils.env import ENV
from utils.helper import Helper
from utils.report import ReportYaml
from utils.util import Util

# Serialize all GUI (Playwright) callbacks so concurrent threads
# don't stomp on the shared browser/tracing/video state in Util.
_gui_lock = threading.Lock()

def _run_api_steps():
    """Browser-free replacement for the old GUI bootstrap path.

    Assumes the CP subscription was provisioned via the api-samples flow
    (`userRoles=["*"]`, `generateIAT=true`), so:
      - No UI login needed (Bearer token replaces session cookie).
      - No UI permission grant needed (`*` already grants all roles).

    Steps:
      1. OAuth token: IAT -> client -> token (api-samples steps 8-9).
      2. Global O11Y resources via OllyApi (SUBSCRIPTION scope).
      3. Global activation license file via LicenseApi (SUBSCRIPTION scope).
         Activation server URL handled separately in run() via tibcop CLI.
    """
    ColorLogger.info("=" * 60)
    ColorLogger.info("CLI Mode - API bootstrap (no browser)")
    ColorLogger.info("=" * 60)

    # Step 1: OAuth token
    token = os.environ.get("TIBCOP_CLI_OAUTH_TOKEN") or Helper.get_auto_token()
    if not token:
        ColorLogger.info("Step 1: No OAuth token cached — bootstrapping via IAT -> client -> token")
        _bootstrap_oauth_token_via_iat()
        token = Helper.get_auto_token()
        if not token:
            raise RuntimeError("Token bootstrap completed but auto-token secret read empty")
    else:
        ColorLogger.success("Step 1: OAuth token already available, skipping bootstrap")

    # Step 2: Global O11Y resources
    if not ENV.TP_AUTO_IS_CONFIG_O11Y:
        ColorLogger.info("Step 2/3: TP_AUTO_IS_CONFIG_O11Y=false, skipping Global O11Y + activation")
        return

    cp_url = os.environ.get("TIBCOP_CLI_CPURL", "").rstrip("/") or (ApiAuth.get_subscription_url() or "").rstrip("/")
    if not cp_url:
        raise RuntimeError("TIBCOP_CLI_CPURL or cp-iat subscription-url required for API-based O11Y config")

    client = ConsoleApiClient(cp_url, token)
    ColorLogger.info("Step 2: Creating Global O11Y resources via API")
    OllyApi(client).create_o11y_resources("global")
    ReportYaml.set_dataplane(ENV.TP_AUTO_DP_NAME_GLOBAL)
    ReportYaml.set_dataplane_info(ENV.TP_AUTO_DP_NAME_GLOBAL, "o11yConfig", True)

    # Step 3: Global activation license file (optional)
    license_path = ENV.TP_AUTO_LICENSE_FILE_PATH
    if license_path and os.path.isfile(license_path):
        ColorLogger.info(f"Step 3: Uploading Global activation file via API: {license_path}")
        result = LicenseApi(cp_url, token).upload_license_file(license_path, dp_id=None)
        if result:
            ReportYaml.set_dataplane_info(ENV.TP_AUTO_DP_NAME_GLOBAL, "activation", "uploaded")
            ColorLogger.success("Step 3: Global activation file uploaded")
        else:
            ColorLogger.warning("Step 3: Global activation file upload failed")
    else:
        ColorLogger.info(f"Step 3: license file not found at {license_path}, skipping license file upload")


def _bootstrap_oauth_token_via_iat():
    """Back-compat wrapper around ApiAuth.bootstrap_tenant_token()."""
    ApiAuth.bootstrap_tenant_token()


def _run_dp_o11y(cli, dp_name):
    """DP-level O11Y configuration after DP is created via CLI.

    Two API calls (no GUI needed):
      1. O11Y resources: POST /cp/api/v1/data-planes/{dpId}/resources/instances/{type}
      2. Activation file: PUT /cp/api/v1/data-planes/{dpId}/license
    """
    if not ENV.TP_AUTO_IS_CONFIG_O11Y:
        ColorLogger.info("TP_AUTO_IS_CONFIG_O11Y is false, skipping DP-level O11Y config")
        return

    activation = ReportYaml.get_dataplane_info(dp_name, "activation")
    o11y_done = ReportYaml.get_dataplane_info(dp_name, "o11yResources")
    if str(o11y_done).lower() == "true" and activation:
        ColorLogger.success(f"DP '{dp_name}' O11Y already configured (report: o11yResources={o11y_done}, activation={activation}), skipping")
        return

    ColorLogger.info("=" * 60)
    ColorLogger.info(f"CLI Mode - DP O11Y resources for '{dp_name}' (REST via cli.resource)")
    ColorLogger.info("=" * 60)
    try:
        report_lock = getattr(getattr(cli, "orchestrator", None), "report_lock", None)
        if cli.resource.create_o11y_resources(dp_name) is None:
            raise RuntimeError("create_o11y_resources returned None")
        if report_lock:
            with report_lock:
                ReportYaml.set_dataplane_info(dp_name, "o11yResources", True)
        else:
            ReportYaml.set_dataplane_info(dp_name, "o11yResources", True)
    except Exception as e:
        ColorLogger.error(f"DP-level O11Y resource create failed: {e}")
        traceback.print_exc()
        return

    # Upload activation file via REST API (if available)
    license_path = ENV.TP_AUTO_LICENSE_FILE_PATH
    if license_path and os.path.isfile(license_path):
        ColorLogger.info("=" * 60)
        ColorLogger.info(f"CLI Mode - DP activation file upload for '{dp_name}' (REST API)")
        ColorLogger.info("=" * 60)
        try:
            # Resolve DP ID for the upload endpoint
            dp_id = cli.dataplane.get_dataplane_id(dp_name)
            if not dp_id:
                ColorLogger.warning(f"Could not resolve DP ID for '{dp_name}', skipping activation file upload")
            else:
                # Build CP URL and token from CLI environment
                cp_url = (getattr(cli.base, "CUSTOM_ENV", {}) or {}).get("TIBCOP_CLI_CPURL") or os.environ.get("TIBCOP_CLI_CPURL", "").rstrip("/")
                token = (getattr(cli.base, "CUSTOM_ENV", {}) or {}).get("TIBCOP_CLI_OAUTH_TOKEN") or os.environ.get("TIBCOP_CLI_OAUTH_TOKEN", "") or Helper.get_auto_token()
                if not (cp_url and token):
                    ColorLogger.warning("CP URL or token missing, skipping activation file upload")
                else:
                    result = LicenseApi(cp_url, token).upload_license_file(license_path, dp_id)
                    if result:
                        if report_lock:
                            with report_lock:
                                ReportYaml.set_dataplane_info(dp_name, "activation", "uploaded")
                        else:
                            ReportYaml.set_dataplane_info(dp_name, "activation", "uploaded")
                        ColorLogger.success(f"DP-level O11Y activation configured for '{dp_name}'")
                    else:
                        ColorLogger.warning(f"License file upload failed for '{dp_name}'")
        except Exception as e:
            ColorLogger.error(f"DP-level O11Y activation upload failed: {e}")
            traceback.print_exc()
    else:
        ColorLogger.info(f"license file not found at {license_path}, skipping DP activation file upload")


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


def _run_api_bmdp_config(bmdp_name, report_lock):
    """API-based BMDP configuration. Sequential, browser-free.

    Writes domain-/server-level ReportYaml entries (`capability` +
    `capability_info` with value "Connected") only when the underlying API
    confirms registration succeeded (HAWKDOMAIN status == "REGISTERED" or
    MSGSERVER successfully created). Does NOT write app-level
    `set_capability_app_info("Status", "Running")` — that requires the BW5
    v1 API (ct-auth-token), which is not yet accessible outside the browser.

    `report_lock` serializes ReportYaml writes against concurrent DP-thread
    writes; reuse `cli.orchestrator.report_lock`.
    """
    ColorLogger.info("=" * 60)
    ColorLogger.info(f"CLI Mode - BMDP API configuration for '{bmdp_name}' (no browser)")
    ColorLogger.info("=" * 60)

    client = ConsoleApiClient.from_auto_token()
    dp_id = client.resolve_dataplane_id(bmdp_name)
    bw5 = BmdpBw5Api(client)
    bw6 = BmdpBw6Api(client)
    ems = BmdpEmsApi(client)

    # ReportYaml capability/info writers require the dataplane entry to exist;
    # set_dataplane is idempotent. Orchestrator flow already calls this before
    # invoking us, but standalone callers may not — be defensive.
    with report_lock:
        ReportYaml.set_dataplane(bmdp_name)

    # Grant the user Product Permission via API (replaces the GUI "Assign
    # Permissions" wizard). Without it the product cards are disabled and the
    # capability/domain config below is rejected. BW5 and BW6 are the products
    # gated behind product permission (see po_bmdp_config.goto_products); EMS
    # server registration is not. Idempotent — a present grant is left as-is.
    perm = ApiUserPermission(client)
    if ENV.TP_AUTO_IS_ENABLE_RVDM or ENV.TP_AUTO_IS_ENABLE_EMSDM:
        perm.grant_product_permission(bmdp_name, "BW5")
    if ENV.TP_AUTO_IS_ENABLE_BW6DM:
        perm.grant_product_permission(bmdp_name, "BW6")

    def _hawkdomain_registered(name):
        d = bw5.find_domain(dp_id, name)
        if not d:
            return False
        meta = d.get("resource_instance_metadata") or {}
        domains = meta.get("domains") or [{}]
        return (domains[0] or {}).get("status") == "REGISTERED"

    # --- BW5 RVDM ---
    if ENV.TP_AUTO_IS_ENABLE_RVDM:
        try:
            bw5.add_rv_domain(
                dp_id, ENV.TP_AUTO_K8S_BMDP_BW5_RVDM,
                ENV.TP_AUTO_K8S_BMDP_BW5_RVDM_RV_SERVICE,
                ENV.TP_AUTO_K8S_BMDP_BW5_RVDM_RV_NETWORK,
                ENV.TP_AUTO_K8S_BMDP_BW5_RVDM_RV_DAEMON,
            )
            if _hawkdomain_registered(ENV.TP_AUTO_K8S_BMDP_BW5_RVDM):
                with report_lock:
                    ReportYaml.set_capability(bmdp_name, "BW5")
                    ReportYaml.set_capability_info(bmdp_name, "BW5",
                        ENV.TP_AUTO_K8S_BMDP_BW5_RVDM, "Connected")
        except Exception as e:
            ColorLogger.error(f"BW5 RVDM registration failed: {e}")
            traceback.print_exc()

    # --- EMS Server + BW5 EMSDM ---
    if ENV.TP_AUTO_IS_ENABLE_EMSDM:
        try:
            ems.register_ems(
                dp_id, ENV.TP_BMDP_IMAGE_TAG_EMS,
                ENV.TP_AUTO_K8S_BMDP_BW5_EMS_SERVER_URL,
                ENV.TP_AUTO_K8S_BMDP_BW5_EMS_MONITOR_URL,
                ENV.TP_AUTO_K8S_BMDP_BW5_EMS_USERNAME,
                ENV.TP_AUTO_K8S_BMDP_BW5_EMS_PASSWORD,
            )
            with report_lock:
                ReportYaml.set_capability(bmdp_name, "EMSServer")
                ReportYaml.set_capability_info(bmdp_name, "EMSServer",
                    ENV.TP_BMDP_IMAGE_TAG_EMS, "Connected")
        except Exception as e:
            ColorLogger.error(f"EMS Server registration failed: {e}")
            traceback.print_exc()

        try:
            bw5.add_ems_domain(
                dp_id, ENV.TP_AUTO_K8S_BMDP_BW5_EMSDM,
                ENV.TP_AUTO_K8S_BMDP_BW5_EMS_SERVER_URL,
                ENV.TP_AUTO_K8S_BMDP_BW5_EMS_USERNAME,
                ENV.TP_AUTO_K8S_BMDP_BW5_EMS_PASSWORD,
            )
            if _hawkdomain_registered(ENV.TP_AUTO_K8S_BMDP_BW5_EMSDM):
                with report_lock:
                    ReportYaml.set_capability(bmdp_name, "BW5")
                    ReportYaml.set_capability_info(bmdp_name, "BW5",
                        ENV.TP_AUTO_K8S_BMDP_BW5_EMSDM, "Connected")
        except Exception as e:
            ColorLogger.error(f"BW5 EMSDM registration failed: {e}")
            traceback.print_exc()

    # --- BW6 Agent ---
    if ENV.TP_AUTO_IS_ENABLE_BW6DM:
        try:
            bw6.add_agent(
                dp_id, ENV.TP_AUTO_K8S_BMDP_BW6DM,
                ENV.TP_AUTO_K8S_BMDP_BW6DM_URL,
            )
            with report_lock:
                ReportYaml.set_capability(bmdp_name, "BW6")
                ReportYaml.set_capability_info(bmdp_name, "BW6",
                    ENV.TP_AUTO_K8S_BMDP_BW6DM, "Connected")
        except Exception as e:
            ColorLogger.error(f"BW6 Agent registration failed: {e}")
            traceback.print_exc()

    # --- O11Y — mirror DP: dataplane-scope create + activation upload ---
    if ENV.TP_AUTO_IS_CONFIG_O11Y:
        try:
            OllyApi(client).create_o11y_resources(bmdp_name)
            with report_lock:
                ReportYaml.set_dataplane_info(bmdp_name, "o11yResources", True)

            license_path = ENV.TP_AUTO_LICENSE_FILE_PATH
            if license_path and os.path.isfile(license_path):
                token = Helper.get_auto_token()
                if LicenseApi(client.base_url, token).upload_license_file(license_path, dp_id):
                    with report_lock:
                        ReportYaml.set_dataplane_info(bmdp_name, "activation", "uploaded")
                    ColorLogger.success(f"BMDP activation file uploaded for '{bmdp_name}'")
                else:
                    ColorLogger.warning(f"License file upload failed for '{bmdp_name}'")
            else:
                ColorLogger.info(f"License file not found at {license_path}, skipping BMDP activation upload")
        except Exception as e:
            ColorLogger.error(f"BMDP O11Y configuration failed: {e}")
            traceback.print_exc()

    ColorLogger.success(f"BMDP API configuration completed for '{bmdp_name}'")


def _run_dp_setup(cli, errors):
    """Thread target: run K8S DataPlane setup."""
    try:
        cli.orchestrator.run_dataplane_setup(
            ENV.TP_AUTO_K8S_DP_NAME,
            ENV.TP_AUTO_K8S_DP_NAMESPACE,
            on_o11y_needed=lambda dp: _run_dp_o11y(cli, dp),
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
            on_config_needed=lambda name: _run_api_bmdp_config(
                name, cli.orchestrator.report_lock),
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

    # Phase 1: API bootstrap (no browser; permissions baked into subscription via userRoles=["*"])
    try:
        _run_api_steps()
    except Exception as e:
        ColorLogger.error(f"API bootstrap failed: {e}")
        traceback.print_exc()
        return

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
