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
"""
Orchestrator module for CLI-based DataPlane deployment.

Extracts CLI orchestration logic from page_cli.py:
- DataPlane setup (registration, resources, capabilities, apps)
- BMDP (Control Tower) setup
- Concurrent provision and deploy with staggered threads
- App endpoint testing via REST API

GUI-dependent steps use callbacks so this module has no Playwright dependency.
"""

import os
import threading
import traceback
import time

from utils.color_logger import ColorLogger
from utils.env import ENV
from utils.helper import Helper
from utils.report import ReportYaml


THREAD_STAGGER_DELAY = 5  # seconds between each thread start


class TibcopOrchestrator:
    """
    Orchestrates CLI-based DataPlane deployment workflows.

    Coordinates capability provisioning, app deployment, and endpoint
    testing using TibcopCLI modules. GUI-dependent steps are handled
    through callbacks.
    """

    def __init__(self, cli):
        """
        Initialize orchestrator.

        Args:
            cli: TibcopCLI instance with all sub-modules
        """
        self.cli = cli
        self.report_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_dataplane_setup(self, dp_name, dp_namespace, on_o11y_needed=None, on_ems_needed=None):
        """Run CLI-based DP setup: registration, resources, O11Y, capabilities, apps.

        Args:
            dp_name: DataPlane name
            dp_namespace: DataPlane namespace
            on_o11y_needed: Optional callback(dp_name) for GUI O11Y configuration.
                           Called after resources are created and before capability provisioning,
                           so that activation is linked before capabilities need it.
            on_ems_needed: Optional callback(dp_name) for GUI EMS provisioning.
                          Called after capability provisioning phase.
        """
        if not ENV.TP_AUTO_IS_CREATE_DP:
            ColorLogger.warning("TP_AUTO_IS_CREATE_DP is false, skipping all DP operations")
            return

        # Step 3: Register K8S DataPlane
        ColorLogger.info("=" * 60)
        ColorLogger.info("CLI Mode - Step 3: Register K8S DataPlane (CLI)")
        ColorLogger.info("=" * 60)

        result = self.cli.dataplane.register_k8s_dataplane(
            dp_name,
            dp_namespace,
            ENV.TP_AUTO_K8S_DP_SERVICE_ACCOUNT
        )
        if result is None:
            ColorLogger.error(f"DataPlane '{dp_name}' registration failed, aborting remaining steps")
            return
        ReportYaml.set_dataplane(dp_name)
        ReportYaml.set_dataplane_info(dp_name, "namespace", dp_namespace)
        ReportYaml.set_dataplane_info(dp_name, "serviceAccount", ENV.TP_AUTO_K8S_DP_SERVICE_ACCOUNT)
        ColorLogger.success(f"DataPlane '{dp_name}' registered via CLI")

        # Wait for DataPlane to be green before proceeding
        health = ReportYaml.get_dataplane_info(dp_name, "healthStatus")
        if str(health).lower() == "green":
            ColorLogger.success(f"DataPlane '{dp_name}' already green (from report), skipping wait")
        else:
            if not self.cli.dataplane.wait_for_dataplane_green(dp_name):
                raise RuntimeError(f"DataPlane '{dp_name}' is not green after timeout, aborting")
            ReportYaml.set_dataplane_info(dp_name, "healthStatus", "green")

        # Step 4: Create storage resource and collect its ID
        ColorLogger.info("=" * 60)
        ColorLogger.info("CLI Mode - Step 4: Create storage resource (CLI)")
        ColorLogger.info("=" * 60)

        storage_resource_name = f"{dp_name}-storage"
        storage_resource_id = self.cli.resource.get_resource_id_by_name(dp_name, storage_resource_name)
        if storage_resource_id:
            ColorLogger.success(f"Storage resource '{storage_resource_name}' already exists (ID: {storage_resource_id}), skipping creation")
        else:
            self.cli.resource.create_storage_resource(
                dp_name,
                storage_resource_name,
                ENV.TP_AUTO_STORAGE_CLASS
            )
            storage_resource_id = self.cli.resource.get_resource_id_by_name(dp_name, storage_resource_name)
        ReportYaml.set_dataplane_info(dp_name, "storage", ENV.TP_AUTO_STORAGE_CLASS)

        # Step 5: Create ingress resources and collect their IDs per capability
        ColorLogger.info("=" * 60)
        ColorLogger.info("CLI Mode - Step 5: Create ingress resources (CLI)")
        ColorLogger.info("=" * 60)

        # Map: (capability_key, ingress_name, fqdn)
        ingress_configs = []
        if ENV.TP_AUTO_IS_PROVISION_FLOGO:
            ingress_configs.append(('FLOGO', ENV.TP_AUTO_INGRESS_CONTROLLER_FLOGO, ENV.TP_AUTO_FQDN_FLOGO))
        if ENV.TP_AUTO_IS_PROVISION_BWCE:
            ingress_configs.append(('BWCE', ENV.TP_AUTO_INGRESS_CONTROLLER_BWCE, ENV.TP_AUTO_FQDN_BWCE))
        if ENV.TP_AUTO_IS_PROVISION_BW5CE:
            ingress_configs.append(('BW5CE', ENV.TP_AUTO_INGRESS_CONTROLLER_BW5CE, ENV.TP_AUTO_FQDN_BW5CE))
        if ENV.TP_AUTO_IS_PROVISION_TIBCOHUB:
            ingress_configs.append(('TIBCOHUB', ENV.TP_AUTO_INGRESS_CONTROLLER_TIBCOHUB, ENV.TP_AUTO_FQDN_TIBCOHUB))

        ingress_ids = {}  # capability_key -> resource_id
        for cap_key, ingress_name, fqdn in ingress_configs:
            resource_id = self.cli.resource.get_resource_id_by_name(dp_name, ingress_name)
            if resource_id:
                ColorLogger.success(f"Ingress resource '{ingress_name}' already exists (ID: {resource_id}), skipping creation")
            else:
                self.cli.resource.create_ingress_resource(
                    dp_name,
                    ingress_name,
                    fqdn
                )
                resource_id = self.cli.resource.get_resource_id_by_name(dp_name, ingress_name)
            if resource_id:
                ingress_ids[cap_key] = resource_id

        # Step 6: DP-level O11Y config and activation link (requires GUI)
        if on_o11y_needed:
            on_o11y_needed(dp_name)

        # Step 7: Provision capabilities and build/deploy apps
        self._provision_and_deploy(dp_name, dp_namespace, storage_resource_id, ingress_ids, on_ems_needed)


    def run_bmdp_setup(self, bmdp_name, namespace, service_account, fqdn,
                       on_config_needed=None):
        """Register Control Tower (BMDP) DataPlane via CLI.

        Args:
            bmdp_name: BMDP DataPlane name
            namespace: BMDP namespace
            service_account: BMDP service account
            fqdn: BMDP FQDN
            on_config_needed: Optional callback(bmdp_name) for GUI domain configuration.
                             Called after BMDP is green.
        """
        if not ENV.TP_AUTO_IS_CREATE_BMDP:
            ColorLogger.warning("TP_AUTO_IS_CREATE_BMDP is false, skipping BMDP operations")
            return

        ColorLogger.info("=" * 60)
        ColorLogger.info("CLI Mode - Register Control Tower DataPlane (CLI)")
        ColorLogger.info("=" * 60)

        result = self.cli.dataplane.register_control_tower_dataplane(
            bmdp_name,
            dp_namespace=namespace,
            dp_service_account_name=service_account,
            fqdn=fqdn
        )
        if result is None:
            ColorLogger.error(f"Control Tower DataPlane '{bmdp_name}' registration failed, aborting remaining steps")
            return
        ReportYaml.set_dataplane(bmdp_name)
        ReportYaml.set_dataplane_info(bmdp_name, "namespace", namespace)
        ReportYaml.set_dataplane_info(bmdp_name, "serviceAccount", service_account)
        ColorLogger.success(f"Control Tower DataPlane '{bmdp_name}' registered via CLI")

        # Wait for BMDP to be green before domain configuration
        health = ReportYaml.get_dataplane_info(bmdp_name, "healthStatus")
        if str(health).lower() == "green":
            ColorLogger.success(f"BMDP '{bmdp_name}' already green (from report), skipping wait")
        else:
            if not self.cli.dataplane.wait_for_dataplane_green(bmdp_name):
                raise RuntimeError(f"BMDP '{bmdp_name}' is not green after timeout, aborting")
            ReportYaml.set_dataplane_info(bmdp_name, "healthStatus", "green")

        # Domain configs and O11Y require GUI - invoke callback
        if on_config_needed:
            on_config_needed(bmdp_name)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _provision_and_deploy(self, dp_name, dp_namespace, storage_resource_id=None, ingress_ids=None,
                              on_ems_needed=None):
        """Provision capabilities and build/deploy apps concurrently via CLI.

        Phase 1: Provision all enabled capabilities in parallel threads (staggered start)
        Phase 2: Build and deploy all apps in parallel threads (staggered start)
        Phase 3: Test app endpoints sequentially

        Args:
            dp_name: DataPlane name
            dp_namespace: DataPlane namespace
            storage_resource_id: Pre-created storage resource ID (passed to provision_capability)
            ingress_ids: Dict mapping capability key -> pre-created ingress resource ID
        """
        ingress_ids = ingress_ids or {}

        # Build capability task list based on enabled flags
        cap_tasks = []
        if ENV.TP_AUTO_IS_PROVISION_FLOGO:
            cap_tasks.append({
                'key': 'FLOGO', 'report_name': 'flogo',
                'app_file': ENV.FLOGO_APP_FILE_NAME,
                'deploy_config': 'flogo-payload.json',
                'app_name': ENV.FLOGO_APP_NAME,
                'deploy_func': self.cli.flogo.build_and_deploy_app,
                'start_enabled': ENV.TP_AUTO_START_FLOGO_APP,
                'endpoint_path': '/', 'endpoint_method': 'GET', 'endpoint_data': None,
                'storage_resource_id': storage_resource_id,
                'ingress_resource_id': ingress_ids.get('FLOGO'),
            })
        if ENV.TP_AUTO_IS_PROVISION_BWCE:
            cap_tasks.append({
                'key': 'BWCE', 'report_name': 'bwce',
                'app_file': ENV.BWCE_APP_FILE_NAME,
                'deploy_config': ENV.BWCE_APP_PAYLOAD_JSON,
                'app_name': ENV.BWCE_APP_NAME,
                'deploy_func': self.cli.bwce.build_and_deploy_app,
                'start_enabled': ENV.TP_AUTO_START_BWCE_APP,
                'endpoint_path': '/swagger/', 'endpoint_method': 'GET', 'endpoint_data': None,
                'storage_resource_id': storage_resource_id,
                'ingress_resource_id': ingress_ids.get('BWCE'),
            })
        if ENV.TP_AUTO_IS_PROVISION_BW5CE:
            cap_tasks.append({
                'key': 'BW5CE', 'report_name': 'bw5ce',
                'app_file': ENV.BW5CE_APP_FILE_NAME,
                'deploy_config': 'bw5ce-payload.json',
                'app_name': ENV.BW5CE_APP_NAME,
                'deploy_func': self.cli.bw5ce.build_and_deploy_app,
                'start_enabled': ENV.TP_AUTO_START_BW5CE_APP,
                'endpoint_path': '/', 'endpoint_method': 'GET', 'endpoint_data': None,
                'storage_resource_id': storage_resource_id,
                'ingress_resource_id': ingress_ids.get('BW5CE'),
            })

        # Phase 1-3: Provision, build/deploy, test (for BWCE/BW5CE/FLOGO)
        if cap_tasks:
            # Phase 1: Concurrent provision (staggered start)
            ColorLogger.info("=" * 60)
            ColorLogger.info("CLI Mode - Step 7a: Provision capabilities (concurrent)")
            ColorLogger.info("=" * 60)

            provision_results = {}
            threads = []
            for task in cap_tasks:
                t = threading.Thread(
                    target=self._provision_worker,
                    args=(dp_name, task, provision_results),
                    name=f"Prov-{task['key']}"
                )
                threads.append(t)
            _start_staggered_threads(threads)

            # Wait for provisioner pods to be Running before deploying
            if not self.cli.kubectl.wait_for_provisioner_pods(dp_namespace):
                ColorLogger.error("Provisioner pods not ready, aborting app deployment")
                return

            # Phase 2: Concurrent build & deploy (staggered start)
            ColorLogger.info("=" * 60)
            ColorLogger.info("CLI Mode - Step 7b: Build & deploy apps (concurrent)")
            ColorLogger.info("=" * 60)

            deploy_results = {}
            threads = []
            for task in cap_tasks:
                if not provision_results.get(task['key']):
                    ColorLogger.warning(f"{task['key']} provision failed, skipping deploy")
                    continue
                t = threading.Thread(
                    target=self._deploy_worker,
                    args=(dp_name, dp_namespace, task, deploy_results),
                    name=f"Deploy-{task['key']}"
                )
                threads.append(t)
            _start_staggered_threads(threads)

            # Phase 3: Wait for app pods, then test endpoints
            # Check activation: without activation, apps cannot become running/ready
            dp_activation = ReportYaml.get_dataplane_info(dp_name, "activation")
            if not dp_activation:
                ColorLogger.warning(f"No activation found for DataPlane '{dp_name}', skipping endpoint testing")
            else:
                for task in cap_tasks:
                    if deploy_results.get(task['key']) and task.get('endpoint_path'):
                        # Check report: skip if endpoint already public and tested
                        ep_public = ReportYaml.get_capability_app_info(
                            dp_name, task['report_name'], task['app_name'], "endpointPublic")
                        ep_tested = ReportYaml.get_capability_app_info(
                            dp_name, task['report_name'], task['app_name'], "testedEndpoint")
                        if str(ep_public).lower() == "true" and str(ep_tested).lower() == "true":
                            ColorLogger.success(
                                f"[{task['key']}] App '{task['app_name']}' endpoint already public and tested (from report), skipping")
                            continue

                        if self.cli.kubectl.wait_for_app_pods(dp_namespace, task['app_name']):
                            with self.report_lock:
                                ReportYaml.set_capability_app_info(
                                    dp_name, task['report_name'], task['app_name'], "status", "Running")
                            ColorLogger.info(f"[{task['key']}] App '{task['app_name']}' status updated: Running")
                            self.cli.api.test_app_endpoint(
                                dp_name, task['key'], task['app_name'],
                                task['endpoint_path'], task['endpoint_method'], task.get('endpoint_data')
                            )
                        else:
                            ColorLogger.warning(f"[{task['key']}] App pods not ready, skipping endpoint test")

        # TibcoHub / DevHub (provision only, CLI)
        if ENV.TP_AUTO_IS_PROVISION_TIBCOHUB:
            if ReportYaml.is_capability_for_dataplane_created(dp_name, "tibcohub"):
                ColorLogger.success("TibcoHub already provisioned (from report), skipping")
            else:
                ColorLogger.info("=" * 60)
                ColorLogger.info("CLI Mode - Provision TibcoHub (CLI)")
                ColorLogger.info("=" * 60)
                result = self.cli.capability.provision_capability(
                    dp_name, 'TIBCOHUB',
                    storage_resource_id=storage_resource_id,
                    ingress_resource_id=ingress_ids.get('TIBCOHUB')
                )
                if result:
                    with self.report_lock:
                        ReportYaml.set_capability(dp_name, "tibcohub")
                    ColorLogger.success("TibcoHub provisioned via CLI")

        # EMS (provision only, requires GUI)
        if ENV.TP_AUTO_IS_PROVISION_EMS and on_ems_needed:
            if ReportYaml.is_capability_for_dataplane_created(dp_name, "ems"):
                ColorLogger.success("EMS already provisioned (from report), skipping")
            else:
                on_ems_needed(dp_name)


    def _provision_worker(self, dp_name, task, results):
        """Provision a single capability in a thread."""
        key = task['key']
        report_name = task['report_name']
        try:
            # Check report: skip if capability already provisioned
            if ReportYaml.is_capability_for_dataplane_created(dp_name, report_name):
                ColorLogger.success(f"[{key}] Capability already provisioned (from report), skipping")
                results[key] = True
                return

            ColorLogger.info(f"[{key}] Provisioning capability...")
            success = self.cli.capability.provision_capability(
                dp_name, key,
                storage_resource_id=task.get('storage_resource_id'),
                ingress_resource_id=task.get('ingress_resource_id')
            )
            if success:
                with self.report_lock:
                    ReportYaml.set_capability(dp_name, report_name)
                ColorLogger.success(f"[{key}] Capability provisioned")
                results[key] = True
            else:
                ColorLogger.error(f"[{key}] Capability provision failed")
                results[key] = False
        except Exception as e:
            ColorLogger.error(f"[{key}] Provision error: {e}")
            traceback.print_exc()
            results[key] = False

    def _deploy_worker(self, dp_name, dp_namespace, task, results):
        """Build and deploy a single app in a thread."""
        key = task['key']
        report_name = task['report_name']
        app_name = task['app_name']
        try:
            # Check report: skip if status already recorded
            app_status = ReportYaml.get_capability_app_info(dp_name, report_name, app_name, "status")
            if app_status:
                ColorLogger.success(f"[{key}] App '{app_name}' status already recorded: '{app_status}' (from report), skipping")
                results[key] = True
                return

            app_file = Helper.get_file_fullpath_in_upload_folder(task['app_file'])
            deploy_config = Helper.get_file_fullpath_in_upload_folder(task['deploy_config'])

            if not os.path.isfile(app_file) or not os.path.isfile(deploy_config):
                ColorLogger.warning(f"[{key}] App file or deploy config not found, skipping")
                results[key] = False
                return

            ColorLogger.info(f"[{key}] Building and deploying app...")
            success = task['deploy_func'](dp_name, app_file, deploy_config, dp_namespace)
            if success:
                # Query actual app state from platform
                app_state = self._get_app_state(dp_name, key, app_name)
                with self.report_lock:
                    ReportYaml.set_capability_app(dp_name, report_name, app_name)
                    ReportYaml.set_capability_app_info(dp_name, report_name, app_name, "status", app_state or "Deployed")
                ColorLogger.success(f"[{key}] App '{app_name}' built and deployed, status: {app_state or 'Deployed'}")
                results[key] = True
            else:
                with self.report_lock:
                    ReportYaml.set_capability_app(dp_name, report_name, app_name)
                    ReportYaml.set_capability_app_info(dp_name, report_name, app_name, "status", "Failure")
                ColorLogger.error(f"[{key}] App build and deploy failed")
                results[key] = False
        except Exception as e:
            ColorLogger.error(f"[{key}] Deploy error: {e}")
            traceback.print_exc()
            results[key] = False

    def _get_app_state(self, dp_name, capability_key, app_name):
        """Query app state from platform via CLI.

        Returns:
            App state string (e.g., 'Running', 'Deploying') or None
        """
        try:
            apps = self.cli.app._get_apps_data(dp_name)
            for app in apps:
                if app.get('app_name') == app_name and app.get('capability_id') == capability_key:
                    return app.get('app_state')
        except Exception:
            pass
        return None


def _start_staggered_threads(threads, delay=THREAD_STAGGER_DELAY):
    """Start threads with a staggered delay, then join all.

    Args:
        threads: List of Thread objects
        delay: Seconds between each thread start (default: THREAD_STAGGER_DELAY)
    """
    for i, t in enumerate(threads):
        t.start()
        if delay > 0 and i < len(threads) - 1:
            time.sleep(delay)
    for t in threads:
        t.join()
