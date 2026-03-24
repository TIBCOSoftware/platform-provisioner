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
Capability management module.

Handles all capability-related operations:
- List capabilities
- Provision capabilities
- Provision versions
"""

import json
from utils.color_logger import ColorLogger
from utils.env import ENV
from .base import TibcopBase


class TibcopCapability:
    """
    Capability management operations.

    Provides methods for managing TIBCO Platform capabilities including
    BWCE, BW5CE, FLOGO, TIBCOHUB, and CONNECTOR.
    """

    def __init__(self, base: TibcopBase, dataplane=None, resource=None):
        """
        Initialize Capability handler.

        Args:
            base: TibcopBase instance for command execution
            dataplane: TibcopDataPlane instance for dataplane operations (optional)
            resource: TibcopResource instance for resource operations (optional)
        """
        self.base = base
        self.dataplane = dataplane
        self.resource = resource

    def list_capabilities(self, dp_name, other_args=None, print_result=False, silent=False):
        """
        List all capability instances in a DataPlane.

        Returns table format output directly from tibcop CLI.

        Args:
            dp_name: Name of the dataplane
            other_args: Additional CLI arguments
            print_result: Whether to print the result during execution
            silent: Suppress log messages (for internal use)

        Returns:
            Table string from tibcop CLI
        """
        if not silent:
            ColorLogger.info(f"Listing capabilities in DataPlane '{dp_name}'...")
        command = (
            f'{self.base.TIBCOP_CLI_PATH} tplatform:list-capability-instances '
            f'--dataplane-name="{dp_name}" '
        )
        command += f'{other_args or ""}'
        # Only print command output in debug mode (result will be printed later if print_result=True)
        result = self.base.run_command(command, verbose=False)

        # Check for CLI error indicators
        if self.base.is_cli_error(result):
            error_msg = result if result else "Command failed"
            if not silent:
                ColorLogger.error(f"Failed to list capabilities: {error_msg}")
            return None

        # Check for empty result warning (not an error)
        if self.base.is_empty_warning(result):
            if not silent:
                ColorLogger.warning(f"No capability instances found in DataPlane '{dp_name}'")
            if print_result:
                print("\n" + "="*80)
                print("Capabilities in DataPlane:")
                print("="*80)
                print("(No capability instances found)")
                print("="*80 + "\n")
            return result

        if print_result:
            print("\n" + "="*80)
            print("Capabilities in DataPlane:")
            print("="*80)
            print(result)
            print("="*80 + "\n")
        if not silent:
            ColorLogger.success("Capabilities listed successfully")
        return result

    def is_capability_provisioned(self, dp_name, capability):
        """
        Check if a capability is already provisioned in the DataPlane.

        Args:
            dp_name: Name of the dataplane
            capability: Capability type (BWCE, BW5CE, FLOGO, TIBCOHUB, CONNECTOR)

        Returns:
            True if capability is already provisioned, False otherwise
        """
        capability_upper = capability.upper()
        ColorLogger.info(f"Checking if {capability_upper} capability is already provisioned...")

        # Reuse list_capabilities with --json flag and silent mode
        result = self.list_capabilities(dp_name, other_args='--json', silent=True)

        if not result:
            return False

        if self.base.is_cli_error(result):
            return False

        # Check for empty warning (no capabilities)
        if self.base.is_empty_warning(result):
            return False

        try:
            # Try to extract JSON from the result (may contain CLI messages before JSON)
            json_str = result
            # Look for JSON array or object start
            json_start = -1
            for i, char in enumerate(result):
                if char in '[{':
                    json_start = i
                    break

            if json_start > 0:
                json_str = result[json_start:]

            data = json.loads(json_str)
            # Extract capabilities array from response
            # The response can be a direct array or wrapped in a 'response' object
            if isinstance(data, list):
                capabilities = data
            elif isinstance(data, dict):
                capabilities = data.get('response', [])
            else:
                capabilities = []

            # Check if the capability exists in the list
            # The JSON structure is: {"id": "xxx", "name": "BW6(Containers)", "capability": "BWCE"}
            for cap in capabilities:
                # The field name is "capability" (e.g., "BWCE", "BW5CE", "FLOGO")
                cap_type = cap.get('capability', '').upper()
                if cap_type == capability_upper:
                    return True

            return False

        except (json.JSONDecodeError, Exception) as e:
            return False

    def provision_version(self, capability, dp_name, version, other_args=None):
        """
        Provision a capability version (generic method for BWCE/BW5CE/FLOGO/CONNECTOR).

        Args:
            capability: Capability type (BWCE, BW5CE, FLOGO, CONNECTOR)
            dp_name: Name of the dataplane
            version: Version tag (buildtypeTag)
            other_args: Additional CLI arguments (for CONNECTOR: '--connector-id "General"')

        Returns:
            Command output
        """
        capability_upper = capability.upper()
        if capability_upper not in ['BWCE', 'BW5CE', 'FLOGO', 'CONNECTOR']:
            ColorLogger.error(f"Unsupported capability: {capability}. Must be BWCE, BW5CE, FLOGO, or CONNECTOR.")
            return None

        ColorLogger.info(f"Provisioning {capability_upper} version '{version}' in DataPlane '{dp_name}'...")

        # Command mapping for each capability
        command_map = {
            'BWCE': 'bwce:provision-bwceversion',
            'BW5CE': 'bw5ce:provision-bw5ceversion',
            'FLOGO': 'flogo:provision-flogo-version',
            'CONNECTOR': 'flogo:provision-connector'
        }

        command = (
            f'{self.base.TIBCOP_CLI_PATH} {command_map[capability_upper]} '
            f'--dataplane-name "{dp_name}" '
            f'--version "{version}" '
        )
        command += f'{other_args or ""}'

        result = self.base.run_command(command)

        # Check if already provisioned (run_command returns "ALREADY_PROVISIONED" in this case)
        if result == "ALREADY_PROVISIONED":
            ColorLogger.info(f"{capability_upper} version '{version}' is already provisioned, skipping...")
            return "ALREADY_PROVISIONED"

        if self.base.is_cli_error(result):
            error_msg = result if result else "Command failed"
            ColorLogger.error(f"Failed to provision {capability_upper} version '{version}': {error_msg}")
            return None

        ColorLogger.success(f"{capability_upper} version '{version}' provisioned successfully")
        return result

    def provision_capability(self, dp_name, capability, storage_resource_id=None, ingress_resource_id=None,
                            path_prefix=None, devhub_name=None, k8s_secret=None, other_args=None):
        """
        Provision a capability (BWCE/BW5CE/FLOGO/TIBCOHUB/CONNECTOR) in a DataPlane.

        Auto-creates required storage and ingress resources if IDs not provided.

        Args:
            dp_name: Name of the dataplane
            capability: Capability type (BWCE, BW5CE, FLOGO, TIBCOHUB, CONNECTOR)
            storage_resource_id: Storage resource instance ID (auto-creates if not provided)
            ingress_resource_id: Ingress resource instance ID (auto-creates if not provided)
            path_prefix: Path prefix (for BWCE/BW5CE/FLOGO), default: /tibco/{capability}/{dataplane_id}
            devhub_name: Developer hub name (for TIBCOHUB only, defaults from ENV.TP_AUTO_TIBCOHUB_CAPABILITY_HUB_NAME)
            k8s_secret: Kubernetes secret object name (for TIBCOHUB only)
            other_args: Additional CLI arguments

        Returns:
            Command output, or "ALREADY_PROVISIONED" if capability exists
        """
        capability_upper = capability.upper()

        # Check if capability is already provisioned
        if self.is_capability_provisioned(dp_name, capability_upper):
            ColorLogger.info(f"{capability_upper} capability is already provisioned in DataPlane '{dp_name}', skipping...")
            return "ALREADY_PROVISIONED"

        ColorLogger.info(f"Provisioning {capability} capability in DataPlane '{dp_name}'...")

        # Get dataplane_id (needed for multiple operations)
        if self.dataplane:
            dataplane_id = self.dataplane.get_dataplane_id(dp_name)
        else:
            ColorLogger.error("DataPlane instance not available, cannot get dataplane ID")
            return None

        if not dataplane_id:
            ColorLogger.error(f"Failed to get dataplane ID for '{dp_name}'")
            return None

        # Auto-create storage resource if not provided
        if not storage_resource_id and self.resource:
            # Get storage class from ENV
            storage_class_name = ENV.TP_AUTO_STORAGE_CLASS
            # Build resource name with storage class info: {capability}-{storageclass}-storage
            storage_resource_name = f"{capability.lower()}-{storage_class_name}-storage"
            ColorLogger.info(f"Storage resource ID not provided, checking if storage resource '{storage_resource_name}' exists...")

            # First check if resource already exists
            existing_storage_id = self.resource.get_resource_id_by_name(dp_name, storage_resource_name)

            if existing_storage_id:
                ColorLogger.info(f"Found existing storage resource with ID '{existing_storage_id}'")
                storage_resource_id = existing_storage_id
            else:
                # Create new storage resource
                ColorLogger.info(f"Creating new storage resource '{storage_resource_name}' with storage class '{storage_class_name}'...")
                result = self.resource.create_storage_resource(
                    dp_name=dp_name,
                    resource_name=storage_resource_name,
                    storage_class_name=storage_class_name,
                    description=f"Auto-created storage for {capability}"
                )
                if result is None:
                    ColorLogger.error(f"Failed to create storage resource, cannot continue provisioning {capability}")
                    return None

                # Get the resource ID of the newly created resource
                storage_resource_id = self.resource.get_resource_id_by_name(dp_name, storage_resource_name)
                if not storage_resource_id:
                    ColorLogger.error(f"Failed to get resource ID for newly created storage resource '{storage_resource_name}'")
                    return None
                ColorLogger.success(f"Storage resource '{storage_resource_name}' created with ID '{storage_resource_id}'")

        # Auto-create ingress resource if not provided
        if not ingress_resource_id and self.resource:
            # Get ingress settings from ENV
            ingress_class_name = ENV.TP_AUTO_INGRESS_CONTROLLER_CLASS_NAME
            ingress_controller = ENV.TP_AUTO_INGRESS_CONTROLLER
            # Build resource name with ingress controller info: {capability}-{ingresscontroller}-ingress
            ingress_resource_name = f"{capability.lower()}-{ingress_controller}-ingress"

            ColorLogger.info(f"Ingress resource ID not provided, checking if ingress resource '{ingress_resource_name}' exists...")

            # First check if resource already exists
            existing_ingress_id = self.resource.get_resource_id_by_name(dp_name, ingress_resource_name)

            if existing_ingress_id:
                ColorLogger.info(f"Found existing ingress resource with ID '{existing_ingress_id}'")
                ingress_resource_id = existing_ingress_id
            else:
                # Determine FQDN based on capability type
                fqdn_map = {
                    "BWCE": ENV.TP_AUTO_FQDN_BWCE,
                    "BW5CE": ENV.TP_AUTO_FQDN_BW5CE,
                    "FLOGO": ENV.TP_AUTO_FQDN_FLOGO,
                    "TIBCOHUB": ENV.TP_AUTO_FQDN_TIBCOHUB
                }
                fqdn = fqdn_map.get(capability.upper(), ENV.TP_AUTO_FQDN_BWCE)

                # Create new ingress resource
                ColorLogger.info(f"Creating new ingress resource '{ingress_resource_name}' with FQDN '{fqdn}', class '{ingress_class_name}', controller '{ingress_controller}'...")
                result = self.resource.create_ingress_resource(
                    dp_name=dp_name,
                    resource_name=ingress_resource_name,
                    fqdn=fqdn,
                    ingress_class_name=ingress_class_name,
                    ingress_controller=ingress_controller
                )
                if result is None:
                    ColorLogger.error(f"Failed to create ingress resource, cannot continue provisioning {capability}")
                    return None

                # Get the resource ID of the newly created resource
                ingress_resource_id = self.resource.get_resource_id_by_name(dp_name, ingress_resource_name)
                if not ingress_resource_id:
                    ColorLogger.error(f"Failed to get resource ID for newly created ingress resource '{ingress_resource_name}'")
                    return None
                ColorLogger.success(f"Ingress resource '{ingress_resource_name}' created with ID '{ingress_resource_id}'")

        if capability.upper() == "TIBCOHUB" and not devhub_name:
            devhub_name = ENV.TP_AUTO_TIBCOHUB_CAPABILITY_HUB_NAME
            ColorLogger.info(f"Using default devhub name from ENV: {devhub_name}")

        # Calculate default path_prefix if not provided (for BWCE/BW5CE/FLOGO)
        if capability.upper() in ["BWCE", "BW5CE", "FLOGO"]:
            if not path_prefix:
                # BWCE uses 'bw' instead of 'bwce' in path prefix
                capability_path = "bw" if capability.upper() == "BWCE" else capability.lower()
                path_prefix = f"/tibco/{capability_path}/{dataplane_id}"
                ColorLogger.success(f"Using default path_prefix: {path_prefix}")

        # Build base command
        command = (
            f'{self.base.TIBCOP_CLI_PATH} tplatform:provision-capability '
            f'--dataplane-name "{dp_name}" '
            f'--capability {capability} '
        )

        # Add storage and ingress (common for all capabilities)
        if storage_resource_id:
            command += f'--storage-resource-instance-id "{storage_resource_id}" '
        if ingress_resource_id:
            command += f'--ingress-resource-instance-id "{ingress_resource_id}" '

        # Add capability-specific parameters
        if capability.upper() == "TIBCOHUB":
            # TIBCOHUB-specific parameters
            if devhub_name:
                command += f'--developer-hub-name "{devhub_name}" '
            if k8s_secret:
                command += f'--kubernetes-secret-object "{k8s_secret}" '
        else:
            # BWCE/BW5CE/FLOGO parameters
            command += f'--path-prefix "{path_prefix}" '
            command += '--fluentbit-sidecar-enabled '

        # Add other args
        if other_args:
            command += other_args

        result = self.base.run_command(command)

        if self.base.is_cli_error(result):
            error_msg = result if result else "Command failed"
            ColorLogger.error(f"Failed to provision {capability} capability: {error_msg}")
            return None

        ColorLogger.success(f"{capability} capability provisioned successfully")
        print("\n" + "="*60)
        print("Updated capability list:")
        print("="*60 + "\n")
        self.list_capabilities(dp_name, print_result=True)
        return result

    def delete_capability_instance(self, dp_name, capability, other_args=None):
        """
        Delete a capability instance from a DataPlane.

        Args:
            dp_name: Name of the dataplane
            capability: Capability type to delete (BWCE, BW5CE, FLOGO, TIBCOHUB, EMS)
            other_args: Additional CLI arguments

        Returns:
            Command output, or None if failed
        """
        capability_upper = capability.upper()
        valid_capabilities = ['BWCE', 'BW5CE', 'FLOGO', 'TIBCOHUB', 'EMS']

        if capability_upper not in valid_capabilities:
            ColorLogger.error(f"Unsupported capability: {capability}. Must be one of: {', '.join(valid_capabilities)}")
            return None

        ColorLogger.info(f"Deleting {capability_upper} capability instance from DataPlane '{dp_name}'...")

        command = (
            f'{self.base.TIBCOP_CLI_PATH} tplatform:delete-capability-instance '
            f'--dataplane-name "{dp_name}" '
            f'--id {capability_upper} '
        )

        command += f'{other_args or ""}'

        result = self.base.run_command(command)

        if self.base.is_cli_error(result):
            error_msg = result if result else "Command failed"
            ColorLogger.error(f"Failed to delete {capability_upper} capability instance: {error_msg}")
            return None

        ColorLogger.success(f"{capability_upper} capability instance deleted successfully from DataPlane '{dp_name}'")
        print("\n" + "="*60)
        print("Updated capability list:")
        print("="*60 + "\n")
        self.list_capabilities(dp_name, print_result=True)
        return result
