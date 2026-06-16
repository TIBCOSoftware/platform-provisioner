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
DataPlane management module.

Handles all DataPlane-related operations:
- List dataplanes
- Check if dataplane exists
- Register K8s dataplane
- Unregister dataplane
- Get dataplane ID
"""

import inspect
import json
import os
from utils.color_logger import ColorLogger
from utils.env import ENV
from utils.helper import Helper
from utils.util import Util
from .base import TibcopBase, normalize_gateway_controller


class TibcopDataPlane:
    """
    DataPlane management operations.

    Provides methods for managing TIBCO Platform DataPlanes including
    registration, unregistration, and querying dataplane information.
    """

    def __init__(self, base: TibcopBase):
        """
        Initialize DataPlane handler.

        Args:
            base: TibcopBase instance for command execution
        """
        self.base = base
        self._dp_id_cache = {}  # dp_name -> dataplane_id cache

    def list_dataplanes(self, other_args=None):
        """
        List all dataplanes.

        Args:
            other_args: Additional CLI arguments

        Returns:
            Command output as string, or None if failed
        """
        command = (
            f'{self.base.TIBCOP_CLI_PATH} tplatform:list-dataplanes '
            f'{other_args or ""}'
        )
        return self.base.run_command(command, verbose=False)

    def is_dataplane_created(self, dp_name):
        """
        Check if a dataplane with the specified name exists.

        Args:
            dp_name: Name of the dataplane to check

        Returns:
            True if the dataplane exists, False otherwise
        """
        command = (
            f'--name="{dp_name}" '
            f'--json '
        )
        result = self.list_dataplanes(command)
        if self.base.is_cli_error(result):
            ColorLogger.info(f"Dataplane '{dp_name}' not found.")
            return False
        data = Util.parse_json_result(result)
        return data is not None

    def wait_for_dataplane_green(self, dp_name, timeout=480, interval=10):
        """
        Wait until the dataplane status becomes 'green'.

        Polls the dataplane status at regular intervals until it is green
        or the timeout is reached.

        Args:
            dp_name: Name of the dataplane to check
            timeout: Maximum wait time in seconds (default: 480)
            interval: Polling interval in seconds (default: 10)

        Returns:
            True if dataplane is green, False if timed out
        """
        import time
        elapsed = 0
        ColorLogger.info(f"Waiting for DataPlane '{dp_name}' to become green (timeout: {timeout}s)...")
        while elapsed < timeout:
            command = f'--name="{dp_name}" --json '
            result = self.list_dataplanes(command)
            if not self.base.is_cli_error(result):
                data = Util.parse_json_result(result)
                if data and isinstance(data, list) and len(data) > 0:
                    status = data[0].get("status", "")
                    if status == "green":
                        ColorLogger.success(f"DataPlane '{dp_name}' is green")
                        return True
                    ColorLogger.info(f"DataPlane '{dp_name}' status: '{status}', waiting...")
            time.sleep(interval)
            elapsed += interval
        ColorLogger.error(f"DataPlane '{dp_name}' did not become green within {timeout}s")
        return False

    def register_k8s_dataplane(self,
                              dp_name,
                              dp_namespace=None,
                              dp_service_account_name=None,
                              other_args=None):
        """
        Register a Kubernetes dataplane.

        Runs the registration command in a shell script file.

        Args:
            dp_name: Name of the dataplane
            dp_namespace: Namespace for the dataplane (defaults to {dp_name}ns)
            dp_service_account_name: Service account name (defaults to {dp_name}sa)
            other_args: Additional CLI arguments

        Returns:
            Command output, or empty string if dataplane already exists
        """
        if self.is_dataplane_created(dp_name):
            ColorLogger.success(f"Dataplane '{dp_name}' already exists. Skip registration.")
            return ""

        ColorLogger.info(f"Dataplane '{dp_name}' does not exist. Starting registration...")
        dp_namespace = dp_namespace or f"{dp_name}ns"
        dp_service_account_name = dp_service_account_name or f"{dp_name}sa"

        cert_arg = '--custom-certificate-secret-name self-signed-cert ' if ENV.TP_IS_CERT_SELF_SIGNED else ''
        command = (
            f'{self.base.TIBCOP_CLI_PATH} tplatform:register-k8s-dataplane --onlyPrintScripts '
            f'--name="{dp_name}" '
            f'--namespace="{dp_namespace}" '
            f'--service-account-name="{dp_service_account_name}" '
            f'{cert_arg}'
            f'{other_args or ""}'
        )

        script_path = os.path.join(ENV.TP_AUTO_REPORT_PATH, f"{inspect.currentframe().f_code.co_name}.sh")
        return self._run_dp_registration_script(command, script_path, dp_namespace)

    def register_control_tower_dataplane(self,
                                         dp_name,
                                         dp_namespace=None,
                                         dp_service_account_name=None,
                                         storage_resource_name=None,
                                         storage_class_name=None,
                                         storage_resource_description=None,
                                         ingress_resource_name=None,
                                         ingress_controller_name=None,
                                         ingress_class_name=None,
                                         ingress_resource_description=None,
                                         fqdn=None,
                                         use_gateway=None,
                                         gatewayapi_resource_name=None,
                                         gateway_apicontroller_name=None,
                                         gateway_name=None,
                                         gateway_namespace=None,
                                         gateway_section=None,
                                         other_args=None):
        """
        Register a Control Tower (Business Monitoring) DataPlane.

        Runs the registration command in a shell script file.

        Args:
            dp_name: Name of the dataplane
            dp_namespace: Namespace for the dataplane (defaults to {dp_name}ns)
            dp_service_account_name: Service account name (defaults to {dp_name}sa)
            storage_resource_name: Name for storage resource (defaults to 'ctdp-nfs')
            storage_class_name: Storage class name (defaults to ENV.TP_AUTO_STORAGE_CLASS)
            storage_resource_description: Description for storage resource
            ingress_resource_name: Name for ingress resource (defaults to 'ctdp-ingress')
            ingress_controller_name: Ingress controller name (defaults to ENV.TP_AUTO_INGRESS_CONTROLLER)
            ingress_class_name: Ingress class name (defaults to ENV.TP_AUTO_INGRESS_CONTROLLER_CLASS_NAME)
            ingress_resource_description: Description for ingress resource
            fqdn: FQDN for ingress/gateway (defaults to ENV.TP_AUTO_FQDN_BMDP)
            use_gateway: When True, register with Gateway API resource instead of ingress.
                Defaults to (ENV.TP_AUTO_INGRESS_OBJECT == "gateway").
            gatewayapi_resource_name: Name for the gateway API resource (defaults to 'ctdp-gateway')
            gateway_apicontroller_name: Controller type, title-cased (defaults to ENV.TP_AUTO_GATEWAY_CONTROLLER)
            gateway_name: K8s Gateway resource name (defaults to ENV.TP_AUTO_GATEWAY_NAME)
            gateway_namespace: K8s Gateway namespace (defaults to ENV.TP_AUTO_GATEWAY_NAMESPACE)
            gateway_section: Optional Gateway Listener section name (defaults to ENV.TP_AUTO_GATEWAY_SECTION_NAME)
            other_args: Additional CLI arguments

        Returns:
            Command output, or empty string if dataplane already exists
        """
        if self.is_dataplane_created(dp_name):
            ColorLogger.success(f"Control Tower DataPlane '{dp_name}' already exists. Skip registration.")
            return ""

        ColorLogger.info(f"Control Tower DataPlane '{dp_name}' does not exist. Starting registration...")

        # Set defaults
        dp_namespace = dp_namespace or f"{dp_name}ns"
        dp_service_account_name = dp_service_account_name or f"{dp_name}sa"
        storage_resource_name = storage_resource_name or "ctdp-nfs"
        storage_class_name = storage_class_name or ENV.TP_AUTO_STORAGE_CLASS
        storage_resource_description = storage_resource_description or "storage for bmdp"
        fqdn = fqdn or ENV.TP_AUTO_FQDN_BMDP

        if use_gateway is None:
            use_gateway = (ENV.TP_AUTO_INGRESS_OBJECT == "gateway")

        if use_gateway:
            gatewayapi_resource_name = gatewayapi_resource_name or "ctdp-gateway"
            gateway_apicontroller_name = normalize_gateway_controller(gateway_apicontroller_name or ENV.TP_AUTO_GATEWAY_CONTROLLER)
            gateway_name = gateway_name or ENV.TP_AUTO_GATEWAY_NAME
            gateway_namespace = gateway_namespace or ENV.TP_AUTO_GATEWAY_NAMESPACE
            if gateway_section is None:
                gateway_section = ENV.TP_AUTO_GATEWAY_SECTION_NAME
            route_args = (
                f'--gatewayapi-resource-name="{gatewayapi_resource_name}" '
                f'--gateway-apicontroller-name="{gateway_apicontroller_name}" '
                f'--gateway-name="{gateway_name}" '
                f'--gateway-namespace="{gateway_namespace}" '
                f'--gateway-host-or-domain-name="{fqdn}" '
            )
            if gateway_section:
                route_args += f'--gateway-section="{gateway_section}" '
        else:
            ingress_resource_name = ingress_resource_name or "ctdp-ingress"
            ingress_controller_name = ingress_controller_name or ENV.TP_AUTO_INGRESS_CONTROLLER
            ingress_class_name = ingress_class_name or ENV.TP_AUTO_INGRESS_CONTROLLER_CLASS_NAME
            ingress_resource_description = ingress_resource_description or "ingress for bmdp"
            route_args = (
                f'--ingress-resource-name="{ingress_resource_name}" '
                f'--ingress-controller-name="{ingress_controller_name}" '
                f'--ingress-class-name="{ingress_class_name}" '
                f'--ingress-resource-description="{ingress_resource_description}" '
                f'--fqdn="{fqdn}" '
            )

        cert_arg = '--custom-certificate-secret-name self-signed-cert ' if ENV.TP_IS_CERT_SELF_SIGNED else ''
        command = (
            f'{self.base.TIBCOP_CLI_PATH} tplatform:register-control-tower-dataplane --onlyPrintScripts '
            f'--name="{dp_name}" '
            f'--namespace="{dp_namespace}" '
            f'--service-account-name="{dp_service_account_name}" '
            f'--storage-resource-name="{storage_resource_name}" '
            f'--storage-class-name="{storage_class_name}" '
            f'--storage-resource-description="{storage_resource_description}" '
            f'{route_args}'
            f'{cert_arg}'
            f'{other_args or ""}'
        )

        script_path = os.path.join(ENV.TP_AUTO_REPORT_PATH, f"{inspect.currentframe().f_code.co_name}.sh")
        return self._run_dp_registration_script(command, script_path, dp_namespace)

    def _run_dp_registration_script(self, command, script_path, dp_namespace):
        """
        Run a DP registration command, optionally creating a cert secret for self-signed certs.

        When TP_IS_CERT_SELF_SIGNED is true, inserts a kubectl command to create the
        certificate secret before the first helm upgrade command. The helm --set for
        cpCertificateSecret is handled by the CLI via --custom-certificate-secret-name flag.

        Args:
            command: The tibcop CLI command to run
            script_path: Path to save the generated script
            dp_namespace: Namespace for the dataplane

        Returns:
            Command output, or empty string on failure
        """
        script_content = self.base.run_command(command)
        if not script_content or self.base.is_cli_error(script_content):
            ColorLogger.error(f"Failed to generate registration script")
            return None

        script_content = self.base.format_command(script_content)

        if ENV.TP_IS_CERT_SELF_SIGNED:
            ColorLogger.info("Self-signed certificate detected, inserting cert secret creation...")
            secret_cmd = (
                f'kubectl get secret default-certificate -n ingress-system -o jsonpath="{{.data.tls\\.crt}}" | base64 --decode > /tmp/cp-cert.pem\n'
                f'kubectl create secret generic self-signed-cert -n {dp_namespace} --from-file=cert=/tmp/cp-cert.pem\n'
                f'rm -f /tmp/cp-cert.pem\n'
            )
            script_content = script_content.replace('helm upgrade', secret_cmd + 'helm upgrade', 1)

        with open(script_path, "w") as f:
            f.write(script_content)
        return Helper.run_shell_file(script_path)

    def unregister_dataplane(self, dp_name, other_args=None):
        """
        Unregister a dataplane.

        Runs the unregistration command in a shell script file.

        Args:
            dp_name: Name of the dataplane
            other_args: Additional CLI arguments

        Returns:
            Command output, or empty string if dataplane doesn't exist
        """
        if not self.is_dataplane_created(dp_name):
            ColorLogger.success(f"Dataplane '{dp_name}' does not exist. Skip unregistration.")
            return ""

        ColorLogger.info(f"Dataplane '{dp_name}' exists. Starting unregistration...")
        command = (
            f'{self.base.TIBCOP_CLI_PATH} tplatform:unregister-dataplane --onlyPrintScripts --force '
            f'--name="{dp_name}" '
            f'{other_args or ""}'
        )

        script_path = os.path.join(ENV.TP_AUTO_REPORT_PATH, f"{inspect.currentframe().f_code.co_name}.sh")
        return self.base.run_command_result_from_file(command, script_path)

    def get_dataplane_id(self, dp_name):
        """
        Get dataplane ID by dataplane name using list-dataplanes API.

        Results are cached per dp_name to avoid redundant API calls.

        Args:
            dp_name: Name of the dataplane

        Returns:
            Dataplane ID (string) or None if not found
        """
        # Return cached result if available
        if dp_name in self._dp_id_cache:
            cached_id = self._dp_id_cache[dp_name]
            ColorLogger.info(f"Using cached dataplane ID for '{dp_name}': {cached_id}")
            return cached_id

        ColorLogger.info(f"Getting dataplane ID for '{dp_name}'...")

        get_dp_cmd = f'{self.base.TIBCOP_CLI_PATH} tplatform:list-dataplanes --json'
        # Don't print command output for internal ID lookup
        dp_result = self.base.run_command(get_dp_cmd, verbose=False)

        # Check for CLI error indicators
        if self.base.is_cli_error(dp_result):
            error_msg = dp_result if dp_result else "Command failed"
            ColorLogger.error(f"Failed to list dataplanes: {error_msg}")
            return None

        dataplane_id = None
        try:
            if dp_result:
                dp_data = json.loads(dp_result)
                dataplanes = Util.extract_response_array(dp_data, 'response')

                for dp in dataplanes:
                    if dp.get('name') == dp_name:
                        dataplane_id = dp.get('id')
                        ColorLogger.success(f"Found dataplane '{dp_name}' with ID: {dataplane_id}")
                        break

                if not dataplane_id:
                    ColorLogger.error(f"DataPlane '{dp_name}' not found in the list")
                    return None
        except Exception as e:
            ColorLogger.error(f"Error processing dataplane list: {e}")
            return None

        # Cache the result
        if dataplane_id:
            self._dp_id_cache[dp_name] = dataplane_id

        return dataplane_id
