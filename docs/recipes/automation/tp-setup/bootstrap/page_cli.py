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
# Steps that use GUI (Playwright): EMS capability provisioning, all O11Y resource
#   configuration — Global resource creation plus switching the k8s DP and the BMDP to
#   it (see O11Y_CONFIG_VIA_UI)
#   (BMDP domain configs use REST via _run_api_bmdp_config; app-level
#    status verification is deferred — only registration-level "Connected"
#    is recorded, pending ct-auth-token sourcing for the BW5 v1 API)
# Steps that use REST API: OAuth token bootstrap (IAT -> client -> token),
#   Global + DP activation file upload, BMDP domain/agent/EMS-server registration,
#   app endpoint testing
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
from page_object.po_bmdp_config import PageObjectBMDPConfiguration
from page_object.po_dp_config import PageObjectDataPlaneConfiguration
from page_object.po_dp_ems import PageObjectDataPlaneEMS
from utils.color_logger import ColorLogger
from utils.env import ENV
from utils.helper import Helper
from utils.report import ReportYaml
from utils.util import Util

# Serialize all GUI (Playwright) callbacks so concurrent threads
# don't stomp on the shared browser/tracing/video state in Util.
_gui_lock = threading.Lock()

# O11Y configuration goes through the UI BY DESIGN (PCP-22010, pinned by PCP-23553).
#
# The contract a deploy must satisfy is: create ONE Global observability resource, then
# switch every data plane (k8s DP and BMDP) TO that global resource. Only the UI can do
# the second half — OllyApi exposes create_o11y_resources() and nothing that links a data
# plane to the global resource. Taking the API path for a data plane therefore cannot
# satisfy the contract; it can only create a second, DP-local resource set (the silent
# degradation PCP-23553 was raised for).
#
# This is a code constant on purpose: it is deliberately NOT exposed as a recipe/guiEnv
# key or an env var, so it cannot be misconfigured from the provisioner UI. It answers
# HOW o11y is configured; GUI_TP_AUTO_ENABLE_CONFIG_O11Y (-> TP_AUTO_IS_CONFIG_O11Y)
# answers WHETHER to configure it at all.
#
# The API branches below are kept (not deleted) so the structure is ready when the API
# gains a switch-to-global operation. Do NOT flip this constant to False before that
# operation exists — the data-plane API branches raise NotImplementedError rather than
# silently falling back to create-local.
O11Y_CONFIG_VIA_UI = True


def _assert_dataplane_o11y_via_ui(dp_name):
    """Guard the retained data-plane API branch (PCP-23553).

    Fail loudly instead of falling back to create-local. `OllyApi` only exposes
    `create_o11y_resources()`; for a data plane that creates a SECOND, DP-local resource
    set rather than linking it to the Global one — the regression this ticket pins down.
    Delete this guard only together with a real API switch-to-global implementation.

    The Global subject is unaffected: creating the Global resource over the API is
    correct and stays functional (see `_run_api_steps` Step 2).
    """
    if O11Y_CONFIG_VIA_UI:
        return
    raise NotImplementedError(
        f"PCP-23553: cannot configure o11y for data plane '{dp_name}' over the API - "
        "OllyApi has no switch-to-global operation, only create_o11y_resources(), which "
        "would create a second DP-local resource set instead of linking the data plane "
        "to the Global resource. Keep O11Y_CONFIG_VIA_UI = True until the API supports it."
    )


def _assert_o11y_recorded(dp_name, report_key, failure_message):
    """Fail unless the o11y wizard recorded `report_key` for `dp_name` (PCP-23553).

    The page-object wizards signal failure with a warning + screenshot and then simply
    return; only a confirmed success writes its report key. So the key is the outcome,
    and "no exception was raised" is not.
    """
    if str(ReportYaml.get_dataplane_info(dp_name, report_key)).lower() == "true":
        return
    raise RuntimeError(f"{failure_message} ({report_key} not recorded)")


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

    # cp_url is still needed by Step 3 (activation) regardless of the o11y path.
    cp_url = os.environ.get("TIBCOP_CLI_CPURL", "").rstrip("/") or (ApiAuth.get_subscription_url() or "").rstrip("/")

    if O11Y_CONFIG_VIA_UI:
        # Assemble Global o11y through the UI wizard, not the API (O11Y_CONFIG_VIA_UI).
        # The wizard (o11y_config_dataplane_resource) writes ReportYaml o11yConfig itself.
        ColorLogger.info("Step 2: Creating Global O11Y resources via UI (O11Y_CONFIG_VIA_UI)")
        # Raise on failure: every data plane later SWITCHES to this resource, so
        # continuing without it guarantees the PCP-23553 failure mode (each DP falling
        # back to, or being reported as, something that is not the Global resource).
        if not _run_gui_o11y(ENV.TP_AUTO_DP_NAME_GLOBAL):
            raise RuntimeError("Global o11y UI configuration failed; data planes have nothing to switch to")
    else:
        if not cp_url:
            raise RuntimeError("TIBCOP_CLI_CPURL or cp-iat subscription-url required for API-based O11Y config")
        client = ConsoleApiClient(cp_url, token)
        ColorLogger.info("Step 2: Creating Global O11Y resources via API")
        OllyApi(client).create_o11y_resources("global")
        ReportYaml.set_dataplane(ENV.TP_AUTO_DP_NAME_GLOBAL)
        ReportYaml.set_dataplane_info(ENV.TP_AUTO_DP_NAME_GLOBAL, "o11yConfig", True)

    # Step 3: Global activation license file (optional)
    license_path = ENV.TP_AUTO_LICENSE_FILE_PATH
    if license_path and os.path.isfile(license_path) and not cp_url:
        # Surface the skip: a configured license file is present but no cp_url was
        # resolved (e.g. o11y went via UI so cp_url was never required) — the upload
        # is skipped rather than silently dropped.
        ColorLogger.warning(f"Step 3: license file {license_path} present but no cp_url resolved; skipping Global activation upload")
    if license_path and os.path.isfile(license_path) and cp_url:
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

    O11Y resources: the DP is switched to the Global observability resource through the
    UI (see O11Y_CONFIG_VIA_UI). Activation file: PUT /cp/api/v1/data-planes/{dpId}/license
    over REST.

    The two are INDEPENDENT and are sequenced, not nested: a failed o11y switch must never
    skip the activation upload (PCP-23558).
    """
    if not ENV.TP_AUTO_IS_CONFIG_O11Y:
        ColorLogger.info("TP_AUTO_IS_CONFIG_O11Y is false, skipping DP-level O11Y config")
        return

    activation = ReportYaml.get_dataplane_info(dp_name, "activation")
    o11y_done = ReportYaml.get_dataplane_info(dp_name, "o11yResources")
    if str(o11y_done).lower() == "true" and activation:
        ColorLogger.success(f"DP '{dp_name}' O11Y already configured (report: o11yResources={o11y_done}, activation={activation}), skipping")
        return

    # Raised outside the try below on purpose: a misconfigured path must abort the DP
    # thread, not be logged as one more recoverable o11y warning.
    _assert_dataplane_o11y_via_ui(dp_name)

    report_lock = getattr(getattr(cli, "orchestrator", None), "report_lock", None)
    try:
        ColorLogger.info("=" * 60)
        ColorLogger.info(f"CLI Mode - DP O11Y switch to Global for '{dp_name}' (UI, O11Y_CONFIG_VIA_UI)")
        ColorLogger.info("=" * 60)
        if not _run_gui_o11y(dp_name):
            raise RuntimeError("o11y UI config returned False")
        # Record o11yResources so the idempotency guard above short-circuits on re-run,
        # regardless of which path (API or UI) configured it.
        if report_lock:
            with report_lock:
                ReportYaml.set_dataplane_info(dp_name, "o11yResources", True)
        else:
            ReportYaml.set_dataplane_info(dp_name, "o11yResources", True)
    except (Exception, SystemExit) as e:
        # SystemExit is caught EXPLICITLY, same trap as po_bmdp_config.py:124/150.
        # Util.exit_error() deep in a shared navigation helper (goto_dataplane ->
        # refresh_until_success miss) calls sys.exit(1), and SystemExit is a
        # BaseException that sails straight past "except Exception" - it would exit this
        # function without ever reaching the activation upload, which is exactly the
        # PCP-23558 failure mode arriving through a second door. Reachable from the o11y
        # step both on the way in (o11y_config_switch_to_global navigates) and now on the
        # way out (recheck_linked_to_global_config re-navigates). Deliberately NOT
        # BaseException: KeyboardInterrupt must still abort the run.
        #
        # DELIBERATELY non-fatal, unlike the Global path in _run_api_steps (PCP-23553,
        # reviewed decision). A missing Global resource means every data plane has
        # nothing to switch to, so the whole deploy is void; one data plane failing to
        # link is a localised o11y gap on an otherwise working deploy, and the
        # pre-existing behaviour is to keep going. What PCP-23553 fixed here is the
        # lying report: o11yResources is only written on the success path above, so a
        # failed link is no longer recorded as configured and no longer short-circuits
        # the next run. The exit code still does not reflect it - if that should change,
        # append to the caller's `errors` list rather than widening this except.
        #
        # It must NOT `return`: the activation upload below is a separate concern that a
        # localised o11y gap has no business skipping (PCP-23558 - it left the DP with no
        # tp-dp-license-file, so every Flogo app CrashLooped on license validation while
        # the pipeline still reported SUCCESS).
        ColorLogger.error(f"DP-level O11Y resource create failed: {e}")
        traceback.print_exc()

    _run_dp_activation_upload(cli, dp_name, report_lock)


def _run_dp_activation_upload(cli, dp_name, report_lock):
    """Upload the DP activation (license) file via PUT /cp/api/v1/data-planes/{dpId}/license.

    Split out of _run_dp_o11y so it runs whatever the o11y step did (PCP-23558). Without
    the license file the DP never gets the tp-dp-license-file capability and every Flogo
    app fails to start with "does not have entitlement to TIBCO_FLOGO_CCS".
    """
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


def _run_gui_o11y(dp_name, is_bmdp=False):
    """Configure o11y for dp_name through the UI (browser).

    The contract (PCP-23553), identical to the browser-mode paths page_dp.py /
    page_bmdp.py already implement:
      - Global  -> CREATE the one observability resource set (o11y_config_dataplane_resource)
      - any DP  -> SWITCH that data plane to the Global resource (o11y_config_switch_to_global)

    A non-Global subject must NEVER go through o11y_config_dataplane_resource: that
    creates a second, DP-local resource set instead of linking to the Global one.

    `is_bmdp` selects the BMDP page object, whose config pages differ from a k8s DP's.
    Both switch helpers self-navigate (data plane list -> DP -> Configuration ->
    Observability), so no navigation prelude is needed here.

    Mirrors _run_gui_ems_provision (browser_launch + login + page object + logout) and
    drives the same page objects as the standalone cases (case/create_global_config.py,
    case/k8s_config_dp_o11y.py, case/bmdp_config_dp_o11y.py).

    Acquires _gui_lock to prevent concurrent browser sessions. Returns True on
    success, False on failure (caller decides how to record/report).
    """
    with _gui_lock:
        ColorLogger.info("=" * 60)
        ColorLogger.info(f"CLI Mode - Configure o11y for '{dp_name}' (GUI, O11Y_CONFIG_VIA_UI)")
        ColorLogger.info("=" * 60)

        page = Util.browser_launch()
        try:
            po_auth = PageObjectAuth(page)
            po_auth.login()
            po_auth.login_check()

            # Both wizards report failure by warning + returning, NOT by raising, so
            # "nothing threw" does not mean "it worked". Each records its own report key
            # ONLY on a confirmed success, so that key - not the absence of an exception
            # - is what this function keys on. Without it a data plane that never got
            # linked is still written down as o11yResources: true, which is the
            # silent-green half of PCP-23553.
            po_config = PageObjectBMDPConfiguration(page) if is_bmdp else PageObjectDataPlaneConfiguration(page)
            if dp_name == ENV.TP_AUTO_DP_NAME_GLOBAL:
                # Global: the wizard self-navigates (Global configuration -> Observability),
                # mirroring case/create_global_config.py. o11yConfig is written only after
                # the wizard saves without a .pl-notification--error.
                po_config.o11y_config_dataplane_resource(dp_name)
                _assert_o11y_recorded(dp_name, "o11yConfig", "the Global observability resource was not created")
            else:
                # switchGlobal is written only once "View in Global Configuration" is
                # visible, i.e. the data plane really is linked to the Global resource.
                po_config.o11y_config_switch_to_global(dp_name)
                _assert_o11y_recorded(dp_name, "switchGlobal",
                                      f"'{dp_name}' was not linked to the Global observability resource")

            po_auth.logout()
            ColorLogger.success(f"o11y configured via UI for '{dp_name}'")
            return True
        except Exception as e:
            ColorLogger.error(f"o11y UI config failed for '{dp_name}': {e}")
            traceback.print_exc()
            return False
        finally:
            Util.browser_close()


def _run_api_bmdp_config(bmdp_name, report_lock):
    """API-based BMDP configuration. Sequential.

    Browser-free except for the o11y step, which switches the BMDP to the Global
    observability resource through the UI (PCP-23553 — the API cannot link a data plane
    to the Global resource, only create a BMDP-local set).

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

    # --- O11Y — mirror DP: switch to the Global resource (UI) + activation upload ---
    if ENV.TP_AUTO_IS_CONFIG_O11Y:
        # PCP-23553: the BMDP used to create its own resource set over REST, bypassing the
        # UI detour entirely and leaving a third, BMDP-local set. Same guard as the DP —
        # raised outside the try so a misconfigured path aborts instead of being logged.
        _assert_dataplane_o11y_via_ui(bmdp_name)
        try:
            if not _run_gui_o11y(bmdp_name, is_bmdp=True):
                raise RuntimeError("o11y UI config returned False")
            with report_lock:
                ReportYaml.set_dataplane_info(bmdp_name, "o11yResources", True)
        except (Exception, SystemExit) as e:
            # Same shape, same reasoning as _run_dp_o11y (PCP-23558): the activation
            # upload used to live INSIDE this try, after the raise above, so a failed
            # BMDP switch skipped the BMDP's license file exactly the way it skipped the
            # k8s DP's. It is now sequenced after this block instead of nested in it.
            # SystemExit is caught explicitly for the same reason as there
            # (Util.exit_error -> sys.exit(1) is a BaseException); KeyboardInterrupt is
            # deliberately still fatal.
            ColorLogger.error(f"BMDP O11Y configuration failed: {e}")
            traceback.print_exc()

        _run_bmdp_activation_upload(client, bmdp_name, dp_id, report_lock)

    ColorLogger.success(f"BMDP API configuration completed for '{bmdp_name}'")


def _run_bmdp_activation_upload(client, bmdp_name, dp_id, report_lock):
    """Upload the BMDP activation (license) file. The BMDP mirror of
    _run_dp_activation_upload — runs whatever the o11y step did (PCP-23558)."""
    license_path = ENV.TP_AUTO_LICENSE_FILE_PATH
    if not (license_path and os.path.isfile(license_path)):
        ColorLogger.info(f"License file not found at {license_path}, skipping BMDP activation upload")
        return
    try:
        token = Helper.get_auto_token()
        if LicenseApi(client.base_url, token).upload_license_file(license_path, dp_id):
            with report_lock:
                ReportYaml.set_dataplane_info(bmdp_name, "activation", "uploaded")
            ColorLogger.success(f"BMDP activation file uploaded for '{bmdp_name}'")
        else:
            ColorLogger.warning(f"License file upload failed for '{bmdp_name}'")
    except (Exception, SystemExit) as e:
        ColorLogger.error(f"BMDP activation upload failed: {e}")
        traceback.print_exc()


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
        # Exit non-zero, matching the errors branch at the end of this function. A
        # bootstrap failure means no OAuth token and/or no Global o11y resource, so
        # nothing below can run and no data plane is created - returning 0 here reported
        # a green pipeline for a deploy that did nothing (PCP-23553).
        ColorLogger.error(f"API bootstrap failed: {e}")
        traceback.print_exc()
        sys.exit(1)

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
