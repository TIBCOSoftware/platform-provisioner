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

import json
import os
import tempfile
import threading
import traceback
import time

from utils.color_logger import ColorLogger
from utils.env import ENV
from utils.helper import Helper
from utils.report import ReportYaml


THREAD_STAGGER_DELAY = 5  # seconds between each thread start


def prepare_deploy_config(deploy_config_file, start_enabled, scratch_dir):
    """Copy a deploy config into a run-scoped file and align it with the 'Start App' toggle.

    GUI mode gates only *_app_start / *_app_test_endpoint on the toggle, so a
    disabled app is still built, deployed and configured — it just never runs.
    CLI mode has no separate start step: `deploy-app` brings the app up with the
    'replicas' from the deploy config (the shipped payloads hardcode 1). Writing
    0 there reproduces the GUI outcome: deployed, not running.

    The mutation lands on a COPY, never on the source. upload/{bwce,bw5ce,flogo}-payload.json
    are checked into the repo and shared by every run, whereas 'replicas' is per-run policy
    read from an env var. Persisting it into the tracked file leaves a dirty working tree,
    invites committing a 'replicas: 0', and makes each run's starting point depend on the
    previous run's toggle. build_and_deploy_app stamps buildId into whatever path it is
    given, so handing it the copy keeps upload/ pristine for the whole flow.

    Args:
        deploy_config_file: Path to the tracked deployment config JSON file (read-only here)
        start_enabled: True when the app should come up running
        scratch_dir: Run-scoped directory the copy is written into

    Returns:
        Path to the run-scoped config, or None if it could not be produced.
    """
    try:
        with open(deploy_config_file, 'r') as f:
            config = json.load(f)
    except (OSError, ValueError) as e:
        ColorLogger.warning(f"Could not read deploy config '{deploy_config_file}': {e}")
        return None

    if not isinstance(config, dict):
        # A deploy config whose JSON root is not an object is unusable anyway; say so
        # here rather than raising an AttributeError out of a function documented to
        # report failure by returning None.
        ColorLogger.warning(f"Deploy config '{deploy_config_file}' is not a JSON object, "
                            f"cannot prepare a deploy config from it")
        return None

    if start_enabled:
        # Only lift a stopped app back to 1; an explicit >1 is kept as-is.
        current = config.get('replicas')
        config['replicas'] = current if isinstance(current, int) and current > 0 else 1
    else:
        config['replicas'] = 0
        # replicas: 0 does not stop an app whose HPA floor is >= 1. The shipped
        # upload/{bwce,bw5ce}-payload-full.json are enableAutoscaling: true with
        # minReplicas: 1, and they are reachable via TP_AUTO_BWCE_APP_PAYLOAD_JSON and the
        # /save-{bwce,flogo}-payload editor endpoints — leaving autoscaling on there lets
        # the HPA scale the stopped app straight back up, turning the toggle into the very
        # no-op PCP-23440 fixed.
        if config.get('enableAutoscaling'):
            config['enableAutoscaling'] = False
            ColorLogger.info("Disabled autoscaling too, so the HPA cannot scale the stopped app back up")

    run_config_file = os.path.join(scratch_dir, os.path.basename(deploy_config_file))
    try:
        with open(run_config_file, 'w') as f:
            json.dump(config, f, indent=2)
    except OSError as e:
        ColorLogger.warning(f"Could not write run-scoped deploy config '{run_config_file}': {e}")
        return None

    ColorLogger.info(f"Prepared a run-scoped '{os.path.basename(deploy_config_file)}' with "
                     f"replicas: {config['replicas']} (the tracked payload is left untouched)")
    return run_config_file


def recorded_bool(recorded):
    """Read back a boolean a previous run recorded in the report.

    ReportYaml round-trips through yq, so a recorded value comes back as the string
    'true'/'false' rather than a bool.

    Returns None when the field is ABSENT, which means UNKNOWN and is deliberately not a
    default. Only a report written before these fields existed lacks them, and it cannot
    say what it did not record — see _deploy_worker for why guessing is wrong in both
    directions. The caller converges by re-deploying once instead.
    """
    if recorded is None:
        return None
    return str(recorded).strip().lower() == "true"


def select_endpoint_test_tasks(cap_tasks, deploy_results):
    """Pick the tasks whose app pods should be waited on and endpoint tested.

    Skips tasks that failed to deploy, tasks without an endpoint (provision-only
    capabilities such as TIBCOHUB) and tasks whose 'Start <capability> App'
    toggle is off — a stopped app has no pods to wait for, so testing it would
    only burn the wait_for_app_pods timeout and log a misleading warning.
    """
    return [
        task for task in cap_tasks
        if deploy_results.get(task['key'])
        and task.get('endpoint_path')
        and task.get('start_enabled', True)
    ]


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

        # Step 5: Create route resources (ingress or gateway) and collect their IDs per capability
        use_gateway = ENV.TP_AUTO_INGRESS_OBJECT.lower() == "gateway"
        route_kind = "gateway" if use_gateway else "ingress"
        ColorLogger.info("=" * 60)
        ColorLogger.info(f"CLI Mode - Step 5: Create {route_kind} resources (CLI)")
        ColorLogger.info("=" * 60)

        # Map: (capability_key, resource_name, fqdn). Resource name varies by route kind
        # so it matches the names used by the Playwright wizards (page_dp.py + po_dp_*.py).
        route_configs = []
        if ENV.TP_AUTO_IS_PROVISION_FLOGO:
            name = ENV.TP_AUTO_GATEWAY_CONTROLLER_FLOGO if use_gateway else ENV.TP_AUTO_INGRESS_CONTROLLER_FLOGO
            route_configs.append(('FLOGO', name, ENV.TP_AUTO_FQDN_FLOGO))
        if ENV.TP_AUTO_IS_PROVISION_BWCE:
            name = ENV.TP_AUTO_GATEWAY_CONTROLLER_BWCE if use_gateway else ENV.TP_AUTO_INGRESS_CONTROLLER_BWCE
            route_configs.append(('BWCE', name, ENV.TP_AUTO_FQDN_BWCE))
        if ENV.TP_AUTO_IS_PROVISION_BW5CE:
            name = ENV.TP_AUTO_GATEWAY_CONTROLLER_BW5CE if use_gateway else ENV.TP_AUTO_INGRESS_CONTROLLER_BW5CE
            route_configs.append(('BW5CE', name, ENV.TP_AUTO_FQDN_BW5CE))
        if ENV.TP_AUTO_IS_PROVISION_TIBCOHUB:
            name = ENV.TP_AUTO_GATEWAY_CONTROLLER_TIBCOHUB if use_gateway else ENV.TP_AUTO_INGRESS_CONTROLLER_TIBCOHUB
            route_configs.append(('TIBCOHUB', name, ENV.TP_AUTO_FQDN_TIBCOHUB))

        route_ids = {}  # capability_key -> resource_id
        for cap_key, resource_name, fqdn in route_configs:
            resource_id = self.cli.resource.get_resource_id_by_name(dp_name, resource_name)
            if resource_id:
                ColorLogger.success(f"{route_kind.title()} resource '{resource_name}' already exists (ID: {resource_id}), skipping creation")
            else:
                if use_gateway:
                    self.cli.resource.create_gateway_api_resource(
                        dp_name=dp_name,
                        resource_name=resource_name,
                        gateway_name=ENV.TP_AUTO_GATEWAY_NAME,
                        gateway_namespace=ENV.TP_AUTO_GATEWAY_NAMESPACE,
                        fqdn=fqdn,
                        gateway_section_name=ENV.TP_AUTO_GATEWAY_SECTION_NAME,
                    )
                else:
                    self.cli.resource.create_ingress_resource(
                        dp_name,
                        resource_name,
                        fqdn
                    )
                resource_id = self.cli.resource.get_resource_id_by_name(dp_name, resource_name)
            if resource_id:
                route_ids[cap_key] = resource_id

        # Step 6: DP-level O11Y config and activation link (requires GUI)
        if on_o11y_needed:
            on_o11y_needed(dp_name)

        # Step 7: Provision capabilities and build/deploy apps
        self._provision_and_deploy(dp_name, dp_namespace, storage_resource_id, route_ids, use_gateway, on_ems_needed)


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

    def _provision_and_deploy(self, dp_name, dp_namespace, storage_resource_id=None, route_ids=None,
                              use_gateway=False, on_ems_needed=None):
        """Provision capabilities and build/deploy apps concurrently via CLI.

        Phase 1: Provision all enabled capabilities in parallel threads (staggered start)
        Phase 2: Build and deploy all apps in parallel threads (staggered start)
        Phase 3: Wait for app pods and test endpoints in parallel threads (staggered start)

        Args:
            dp_name: DataPlane name
            dp_namespace: DataPlane namespace
            storage_resource_id: Pre-created storage resource ID (passed to provision_capability)
            route_ids: Dict mapping capability key -> pre-created route (ingress or gateway) resource ID
            use_gateway: If True, route_ids are gateway resource IDs; else ingress resource IDs
        """
        route_ids = route_ids or {}
        route_key = 'gateway_resource_id' if use_gateway else 'ingress_resource_id'

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
                route_key: route_ids.get('FLOGO'),
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
                route_key: route_ids.get('BWCE'),
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
                route_key: route_ids.get('BW5CE'),
            })
        if ENV.TP_AUTO_IS_PROVISION_TIBCOHUB:
            cap_tasks.append({
                'key': 'TIBCOHUB', 'report_name': 'tibcohub',
                'deploy_func': None,
                'endpoint_path': None,
                'storage_resource_id': storage_resource_id,
                route_key: route_ids.get('TIBCOHUB'),
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

            # Phase 2: Concurrent build & deploy (staggered start)
            # Only run for capabilities that have a deploy_func (skip provision-only like TIBCOHUB)
            deploy_tasks = [t for t in cap_tasks if t.get('deploy_func')]
            deploy_results = {}
            if deploy_tasks:
                # Wait for provisioner pods to be Running before deploying
                if not self.cli.kubectl.wait_for_provisioner_pods(dp_namespace):
                    ColorLogger.error("Provisioner pods not ready, aborting app deployment")
                    return

                ColorLogger.info("=" * 60)
                ColorLogger.info("CLI Mode - Step 7b: Build & deploy apps (concurrent)")
                ColorLogger.info("=" * 60)

                threads = []
                for task in deploy_tasks:
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

            # Phase 3: Wait for app pods, then test endpoints (concurrent)
            # Check activation: without activation, apps cannot become running/ready
            dp_activation = ReportYaml.get_dataplane_info(dp_name, "activation")
            if not dp_activation:
                ColorLogger.warning(f"No activation found for DataPlane '{dp_name}', skipping endpoint testing")
            else:
                # Reading the live toggle here is safe: _deploy_worker re-deploys whenever
                # the report's recorded startEnabled disagrees with it, so by this point
                # the deployed replicas and this filter always agree. No "skipped because
                # stopped" log — _deploy_worker already logs the skip where the toggle is
                # actually applied.
                test_tasks = select_endpoint_test_tasks(cap_tasks, deploy_results)
                if test_tasks:
                    ColorLogger.info("=" * 60)
                    ColorLogger.info("CLI Mode - Step 7c: Wait for app pods & test endpoints (concurrent)")
                    ColorLogger.info("=" * 60)
                    threads = [
                        threading.Thread(
                            target=self._wait_and_test_worker,
                            args=(dp_name, dp_namespace, task),
                            name=f"Test-{task['key']}"
                        )
                        for task in test_tasks
                    ]
                    _start_staggered_threads(threads)

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
                ingress_resource_id=task.get('ingress_resource_id'),
                gateway_resource_id=task.get('gateway_resource_id'),
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
        start_enabled = task.get('start_enabled', True)
        try:
            # Skip ONLY if the last run deployed this app SUCCESSFULLY and with THIS SAME
            # toggle. Both come from fields this code writes; 'status' is the platform's
            # own wording (an unbounded _get_app_state string) and is deliberately NOT a
            # decision input — keying on it made a 'Failure' read as done, and any other
            # failure spelling would read as success. See the PCP-23459 CHANGELOG entry for
            # why a healthy-state whitelist is worse than either.
            #
            # The reads take report_lock because report.yaml is one document mutated through
            # yq: a sibling capability's worker can be mid-write to the same FILE. Per-key
            # ownership makes the VALUE uncontended, which is a different thing. Holding it
            # across all three also makes them a consistent snapshot, which matters because
            # the condition below compares two of them.
            with self.report_lock:
                app_status = ReportYaml.get_capability_app_info(dp_name, report_name, app_name, "status")
                deploy_ok = recorded_bool(
                    ReportYaml.get_capability_app_info(dp_name, report_name, app_name, "deploySucceeded"))
                recorded = recorded_bool(
                    ReportYaml.get_capability_app_info(dp_name, report_name, app_name, "startEnabled"))
            if app_status and deploy_ok is True and recorded == start_enabled:
                ColorLogger.success(f"[{key}] App '{app_name}' status already recorded: '{app_status}' (from report), skipping")
                results[key] = True
                return
            if app_status:
                if deploy_ok is False:
                    reason = "its last deploy failed"
                elif deploy_ok is None or recorded is None:
                    # A report written before these fields existed cannot say what it did
                    # not record, and neither direction is safe to assume: a pre-PCP-23440
                    # run ignored the toggle and always deployed the app running, but a
                    # PCP-23440 run (release 1.7.80) already honoured it and could have left
                    # the app at replicas: 0 without recording why. Guessing 'was running'
                    # would leave exactly that app stopped on a toggle-ON run — the defect
                    # this change exists to fix. Converge once instead; the re-deploy writes
                    # both fields, so it costs one run per report, not one per run.
                    reason = "it predates the report's 'deploySucceeded'/'startEnabled' fields, so what the last run did is unknown"
                else:
                    reason = f"it was deployed with 'Start app' {recorded} but that is now {start_enabled}"
                ColorLogger.info(f"[{key}] Re-deploying app '{app_name}' to converge: {reason}")

            app_file = Helper.get_file_fullpath_in_upload_folder(task['app_file'])
            deploy_config = Helper.get_file_fullpath_in_upload_folder(task['deploy_config'])

            if not os.path.isfile(app_file) or not os.path.isfile(deploy_config):
                ColorLogger.warning(f"[{key}] App file or deploy config not found, skipping")
                results[key] = False
                return

            # Honour the 'Start <capability> App' toggle: CLI mode has no separate start
            # step, so a stopped app must be deployed with replicas: 0. The toggle is
            # applied to a run-scoped copy that lives only for this deploy, so the tracked
            # payload under upload/ is never written to — not by us, and not by the buildId
            # stamp inside deploy_func either.
            # ignore_cleanup_errors: the deploy is done by the time __exit__ runs, so a
            # lingering handle (Windows/VDI local dev, AV scanner) must not turn a
            # successful deploy into a PermissionError out of the temp-dir teardown.
            with tempfile.TemporaryDirectory(prefix=f"tp-auto-{key.lower()}-",
                                             ignore_cleanup_errors=True) as scratch_dir:
                run_config = prepare_deploy_config(deploy_config, start_enabled, scratch_dir)
                if run_config is None:
                    # There is no config to deploy with; deploying the tracked payload
                    # instead would run the app at whatever replicas it happens to hold,
                    # which is the silent no-op this whole path exists to prevent.
                    ColorLogger.error(f"[{key}] Could not prepare the deploy config, skipping deploy")
                    results[key] = False
                    return

                if not start_enabled:
                    ColorLogger.info(f"[{key}] Start app is disabled, deploying with replicas: 0 (not running)")

                ColorLogger.info(f"[{key}] Building and deploying app...")
                success = task['deploy_func'](dp_name, app_file, run_config, dp_namespace)

            if success:
                # Query actual app state from platform
                app_state = self._get_app_state(dp_name, key, app_name)
                with self.report_lock:
                    ReportYaml.set_capability_app(dp_name, report_name, app_name)
                    # status is the platform's word, for a human reading the report;
                    # deploySucceeded is this run's own verdict, and is what the resume
                    # short-circuit keys on. Keeping them separate is what stops the skip
                    # from depending on the platform's failure vocabulary.
                    ReportYaml.set_capability_app_info(dp_name, report_name, app_name, "status", app_state or "Deployed")
                    ReportYaml.set_capability_app_info(dp_name, report_name, app_name, "deploySucceeded", True)
                    ReportYaml.set_capability_app_info(dp_name, report_name, app_name, "startEnabled", start_enabled)
                ColorLogger.success(f"[{key}] App '{app_name}' built and deployed, status: {app_state or 'Deployed'}")
                results[key] = True
            else:
                with self.report_lock:
                    ReportYaml.set_capability_app(dp_name, report_name, app_name)
                    ReportYaml.set_capability_app_info(dp_name, report_name, app_name, "status", "Failure")
                    ReportYaml.set_capability_app_info(dp_name, report_name, app_name, "deploySucceeded", False)
                    ReportYaml.set_capability_app_info(dp_name, report_name, app_name, "startEnabled", start_enabled)
                ColorLogger.error(f"[{key}] App build and deploy failed")
                results[key] = False
        except Exception as e:
            ColorLogger.error(f"[{key}] Deploy error: {e}")
            traceback.print_exc()
            results[key] = False

    def _wait_and_test_worker(self, dp_name, dp_namespace, task):
        """Wait for an app's pods to be Running, then test its endpoint, in a thread."""
        key = task['key']
        report_name = task['report_name']
        app_name = task['app_name']
        try:
            # Check report: skip if endpoint already public and tested
            ep_public = ReportYaml.get_capability_app_info(dp_name, report_name, app_name, "endpointPublic")
            ep_tested = ReportYaml.get_capability_app_info(dp_name, report_name, app_name, "testedEndpoint")
            if str(ep_public).lower() == "true" and str(ep_tested).lower() == "true":
                ColorLogger.success(
                    f"[{key}] App '{app_name}' endpoint already public and tested (from report), skipping")
                return

            if self.cli.kubectl.wait_for_app_pods(dp_namespace, app_name):
                with self.report_lock:
                    ReportYaml.set_capability_app_info(dp_name, report_name, app_name, "status", "Running")
                ColorLogger.info(f"[{key}] App '{app_name}' status updated: Running")
                with self.report_lock:
                    self.cli.endpoint_api.test_app_endpoint(
                        dp_name, key, app_name,
                        task['endpoint_path'], task['endpoint_method'], task.get('endpoint_data')
                    )
            else:
                ColorLogger.warning(f"[{key}] App pods not ready, skipping endpoint test")
        except Exception as e:
            ColorLogger.error(f"[{key}] Wait/test error: {e}")
            traceback.print_exc()

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
