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
Resource instance management module.

Handles all resource-related operations:
- List resource instances
- Get resource ID by name
- Create storage resources
- Create ingress resources
- Create activation server resources
- Create O11Y wizard resources (via REST API — no tibcop CLI equivalent)
- Delete resources
"""

import json
import os
from utils.color_logger import ColorLogger
from utils.env import ENV
from utils.helper import Helper
from api_object import ConsoleApiClient, OllyApi
from .base import TibcopBase, normalize_ingress_controller, normalize_gateway_controller


class TibcopResource:
    """
    Resource instance management operations.

    Provides methods for managing TIBCO Platform resource instances including
    storage, ingress, and activation server resources.
    """

    def __init__(self, base: TibcopBase):
        """
        Initialize Resource handler.

        Args:
            base: TibcopBase instance for command execution
        """
        self.base = base

    def list_resource_instances(self, dp_name, other_args=None, print_result=False):
        """
        List all resource instances in a DataPlane.

        Returns table format output directly from tibcop CLI.

        Args:
            dp_name: Name of the dataplane
            other_args: Additional CLI arguments
            print_result: Whether to print the result during execution

        Returns:
            Table string from tibcop CLI
        """
        ColorLogger.info(f"Listing resource instances in DataPlane '{dp_name}'...")
        command = (
            f'{self.base.TIBCOP_CLI_PATH} tplatform:list-resource-instances '
            f'--dataplane-name="{dp_name}" '
        )
        command += f'{other_args or ""}'
        result = self.base.run_command(command, verbose=False)

        # Check for CLI error indicators
        if self.base.is_cli_error(result):
            error_msg = result if result else "Command failed"
            ColorLogger.error(f"Failed to list resource instances: {error_msg}")
            return None

        # Check for empty result warning (not an error)
        if self.base.is_empty_warning(result):
            ColorLogger.warning(f"No resource instances found in DataPlane '{dp_name}'")
            if print_result:
                print("\n" + "="*80)
                print("Resource Instances in DataPlane:")
                print("="*80)
                print("(No resource instances found)")
                print("="*80 + "\n")
            return result

        if print_result:
            print("\n" + "="*80)
            print("Resource Instances in DataPlane:")
            print("="*80)
            print(result)
            print("="*80 + "\n")
        ColorLogger.success("Resource instances listed successfully")
        return result

    def get_resource_id_by_name(self, dp_name, resource_name):
        """
        Get resource instance ID by resource name using JSON output.

        Args:
            dp_name: Name of the dataplane
            resource_name: Name of the resource instance to search for

        Returns:
            Resource instance ID (string) or None if not found
        """
        ColorLogger.info(f"Looking up resource ID for resource name '{resource_name}' in DataPlane '{dp_name}'...")
        command = (
            f'{self.base.TIBCOP_CLI_PATH} tplatform:list-resource-instances '
            f'--dataplane-name="{dp_name}" '
            f'--json '
        )
        # Don't print command output for internal ID lookup
        result = self.base.run_command(command, verbose=False)

        # Check for CLI error indicators
        if self.base.is_cli_error(result):
            error_msg = result if result else "Command failed"
            ColorLogger.error(f"Failed to list resource instances: {error_msg}")
            return None

        try:
            # Parse JSON output
            resources = json.loads(result)

            # Search for matching resource by name
            for resource in resources:
                if resource.get('name') == resource_name:
                    resource_id = resource.get('id')
                    ColorLogger.success(f"Found resource ID '{resource_id}' for resource name '{resource_name}'")
                    return resource_id

            ColorLogger.warning(f"Resource with name '{resource_name}' not found")
            return None

        except json.JSONDecodeError as e:
            ColorLogger.error(f"Failed to parse JSON output: {e}")
            ColorLogger.debug(f"Raw output: {result}")
            return None
        except Exception as e:
            ColorLogger.error(f"Error processing resource list: {e}")
            return None

    def create_storage_resource(self, dp_name, resource_name, storage_class_name=None,
                                description="Storage_For_Integration", other_args=None):
        """
        Create a storage resource instance in a DataPlane.

        Args:
            dp_name: Name of the dataplane
            resource_name: Name for the storage resource instance
            storage_class_name: Storage class name (defaults from ENV.TP_AUTO_STORAGE_CLASS)
            description: Description for the storage resource
            other_args: Additional CLI arguments

        Returns:
            Command output
        """
        ColorLogger.info(f"Creating storage resource instance '{resource_name}' in DataPlane '{dp_name}'...")

        # Set default storage class from ENV if not provided
        if not storage_class_name:
            storage_class_name = ENV.TP_AUTO_STORAGE_CLASS
            ColorLogger.info(f"Using default storage class from ENV: {storage_class_name}")

        command = (
            f'{self.base.TIBCOP_CLI_PATH} tplatform:create-storage-resource-instance '
            f'--dataplane-name "{dp_name}" '
            f'--name "{resource_name}" '
            f'--storage-class-name "{storage_class_name}" '
            f'--description "{description}" '
        )
        command += f'{other_args or ""}'
        result = self.base.run_command(command)

        if self.base.is_cli_error(result):
            error_msg = result if result else "Command failed"
            ColorLogger.error(f"Failed to create storage resource instance '{resource_name}': {error_msg}")
            return None

        ColorLogger.success(f"Storage resource instance '{resource_name}' created successfully")
        print("\n" + "="*60)
        print("Updated resource instance list:")
        print("="*60 + "\n")
        self.list_resource_instances(dp_name, print_result=True)
        return result

    def create_ingress_resource(self, dp_name, resource_name, fqdn, ingress_class_name=None,
                                ingress_controller=None, other_args=None):
        """
        Create an ingress resource instance in a DataPlane.

        Args:
            dp_name: Name of the dataplane
            resource_name: Name for the ingress resource instance
            fqdn: Fully qualified domain name
            ingress_class_name: Ingress class name (defaults from ENV)
            ingress_controller: Ingress controller (defaults from ENV)
            other_args: Additional CLI arguments

        Returns:
            Command output
        """
        ColorLogger.info(f"Creating ingress resource instance '{resource_name}' in DataPlane '{dp_name}'...")

        # Set default values from ENV if not provided
        if not ingress_class_name:
            ingress_class_name = ENV.TP_AUTO_INGRESS_CONTROLLER_CLASS_NAME
            ColorLogger.info(f"Using default ingress class name from ENV: {ingress_class_name}")

        if not ingress_controller:
            ingress_controller = ENV.TP_AUTO_INGRESS_CONTROLLER
            ColorLogger.info(f"Using default ingress controller from ENV: {ingress_controller}")

        ingress_controller = normalize_ingress_controller(ingress_controller)

        command = (
            f'{self.base.TIBCOP_CLI_PATH} tplatform:create-ingress-resource-instance '
            f'--dataplane-name "{dp_name}" '
            f'--name "{resource_name}" '
            f'--ingress-class-name "{ingress_class_name}" '
            f'--ingress-controller "{ingress_controller}" '
            f'--fqdn "{fqdn}" '
        )
        command += f'{other_args or ""}'
        result = self.base.run_command(command)

        if self.base.is_cli_error(result):
            error_msg = result if result else "Command failed"
            ColorLogger.error(f"Failed to create ingress resource instance '{resource_name}': {error_msg}")
            return None

        ColorLogger.success(f"Ingress resource instance '{resource_name}' created successfully")
        print("\n" + "="*60)
        print("Updated resource instance list:")
        print("="*60 + "\n")
        self.list_resource_instances(dp_name, print_result=True)
        return result

    def create_gateway_api_resource(self, dp_name, resource_name, gateway_name, gateway_namespace,
                                    fqdn, gateway_apicontroller_name=None, gateway_section_name=None,
                                    other_args=None):
        """
        Create a Gateway API resource instance in a DataPlane (tibcop 1.9.0+).

        Args:
            dp_name: Name of the dataplane
            resource_name: Name for the gateway API resource instance
            gateway_name: K8s Gateway resource name (e.g. "nginx-gateway")
            gateway_namespace: Namespace of the K8s Gateway (e.g. "ingress-system")
            fqdn: Host/domain name served by the Gateway
            gateway_apicontroller_name: Controller type (e.g. "Nginx", "Traefik").
                Defaults to ENV.TP_AUTO_GATEWAY_CONTROLLER (title-cased).
            gateway_section_name: Optional Gateway Listener section name (parentRefs.sectionName).
                Only passed when truthy — matches UI behavior where the field is optional.
            other_args: Additional CLI arguments

        Returns:
            Command output
        """
        ColorLogger.info(f"Creating gateway API resource instance '{resource_name}' in DataPlane '{dp_name}'...")

        if not gateway_apicontroller_name:
            gateway_apicontroller_name = normalize_gateway_controller(ENV.TP_AUTO_GATEWAY_CONTROLLER)
            ColorLogger.info(f"Using default gateway controller from ENV: {gateway_apicontroller_name}")

        command = (
            f'{self.base.TIBCOP_CLI_PATH} tplatform:create-gateway-api-resource-instance '
            f'--dataplane-name "{dp_name}" '
            f'--name "{resource_name}" '
            f'--gateway-apicontroller-name "{gateway_apicontroller_name}" '
            f'--gateway-name "{gateway_name}" '
            f'--gateway-namespace "{gateway_namespace}" '
            f'--gateway-host-or-domain-name "{fqdn}" '
        )
        if gateway_section_name:
            command += f'--gateway-section-name "{gateway_section_name}" '
        command += f'{other_args or ""}'
        result = self.base.run_command(command)

        if self.base.is_cli_error(result):
            error_msg = result if result else "Command failed"
            ColorLogger.error(f"Failed to create gateway API resource instance '{resource_name}': {error_msg}")
            return None

        ColorLogger.success(f"Gateway API resource instance '{resource_name}' created successfully")
        print("\n" + "="*60)
        print("Updated resource instance list:")
        print("="*60 + "\n")
        self.list_resource_instances(dp_name, print_result=True)
        return result

    def delete_resource(self, dp_name, resource_instance_id, other_args=None):
        """
        Delete a resource instance in a DataPlane.

        Args:
            dp_name: Name of the dataplane
            resource_instance_id: Resource instance ID to delete
            other_args: Additional CLI arguments

        Returns:
            Command output
        """
        ColorLogger.info(f"Deleting resource instance '{resource_instance_id}' from DataPlane '{dp_name}'...")
        command = (
            f'{self.base.TIBCOP_CLI_PATH} tplatform:delete-resource-instance '
            f'--dataplane-name "{dp_name}" '
            f'--id "{resource_instance_id}" '
        )
        command += f'{other_args or ""}'
        result = self.base.run_command(command)

        if self.base.is_cli_error(result):
            error_msg = result if result else "Command failed"
            ColorLogger.error(f"Failed to delete resource instance: {error_msg}")
            return None

        ColorLogger.success("Resource instance deleted successfully")
        print("\n" + "="*60)
        print("Updated resource instance list:")
        print("="*60 + "\n")
        self.list_resource_instances(dp_name, print_result=True)
        return result

    def _find_resource_id_by_name(self, name, dp_name=None):
        """Look up a resource instance id by name. dp_name=None → SUBSCRIPTION scope.

        Returns the id string, or None if not found / on error. Idempotency helper.
        """
        scope_label = "SUBSCRIPTION" if dp_name is None else f"DataPlane '{dp_name}'"
        command = f'{self.base.TIBCOP_CLI_PATH} tplatform:list-resource-instances --json '
        if dp_name:
            command += f'--dataplane-name="{dp_name}" '
        result = self.base.run_command(command, verbose=False)
        if self.base.is_cli_error(result) or not result:
            return None
        try:
            for item in json.loads(result):
                if item.get("name") == name:
                    return item.get("id")
        except (json.JSONDecodeError, TypeError):
            ColorLogger.warning(f"Could not parse resource list for {scope_label}")
        return None

    def create_activation_server(self, dp_name=None, name=None, url=None, scope=None,
                                 description=None, version=None, other_args=None):
        """
        Create activation server resource instance (CASRI). Idempotent.

        Scope is inferred from dp_name: pass dp_name → DATAPLANE scope,
        omit dp_name (or pass None) → SUBSCRIPTION (global) scope. The
        explicit `scope` kwarg overrides this inference when set.

        URL is constructed from TP_ACTIVATION_SERVER_* env vars if not provided.
        If a resource with the same `name` already exists in the target scope,
        the create is skipped and the existing id is returned.

        Returns:
            Command output (create result), existing-id string (skip), or None on error.
        """
        # Use default name if not provided
        if not name:
            name = "ActivationServer"

        # Infer scope from dp_name unless caller forced it
        if scope is None:
            scope = "DATAPLANE" if dp_name else "SUBSCRIPTION"

        # Construct URL from ENV variables if not provided
        if url:
            ColorLogger.info(f"Using activation server URL from user input: {url}")
        else:
            if ENV.TP_ACTIVATION_SERVER_CERT_HOSTNAME and ENV.TP_ACTIVATION_SERVER_FINGER_PRINT:
                url = ENV.TP_ACTIVATION_URL
                ColorLogger.info(f"Using activation server URL from ENV variables: {url}")
            else:
                ColorLogger.error("No activation server URL provided and ENV variables not set")
                ColorLogger.error("Required ENV variables:")
                ColorLogger.error("  - TP_ACTIVATION_SERVER_CERT_HOSTNAME")
                ColorLogger.error("  - TP_ACTIVATION_SERVER_FINGER_PRINT")
                ColorLogger.error("  - TP_ACTIVATION_SERVER_PORT (optional, default: 7070)")
                return None

        scope_label = "SUBSCRIPTION (global)" if scope == "SUBSCRIPTION" else f"DataPlane '{dp_name}'"

        # Idempotency: skip if name already exists in target scope
        existing_id = self._find_resource_id_by_name(name, dp_name if scope == "DATAPLANE" else None)
        if existing_id:
            ColorLogger.success(f"Activation server '{name}' already exists in {scope_label} (id={existing_id}), skipping")
            return existing_id

        ColorLogger.info(f"Creating activation server resource instance '{name}' in {scope_label}...")
        ColorLogger.info(f"  URL: {url}")
        ColorLogger.info(f"  Scope: {scope}")

        command = f'{self.base.TIBCOP_CLI_PATH} tplatform:casri '
        if scope == "DATAPLANE" and dp_name:
            command += f'--dataplane-name "{dp_name}" '
        command += (
            f'--name "{name}" '
            f'--url "{url}" '
            f'--scope {scope} '
        )

        if description:
            command += f'--description "{description}" '

        if version:
            command += f'--version "{version}" '

        command += '--json '
        command += f'{other_args or ""}'

        result = self.base.run_command(command)

        if self.base.is_cli_error(result):
            error_msg = result if result else "Command failed"
            ColorLogger.error(f"Failed to create activation server resource instance: {error_msg}")
            return None

        ColorLogger.success(f"Activation server resource instance '{name}' created successfully in {scope_label}")
        return result

    def create_o11y_resources(self, target="global"):
        """Create the 9 O11Y wizard resources via the flat resource REST API.

        tibcop CLI has no equivalent (no `create-o11y-*` commands), so this
        method wraps the REST client (`api_object.OllyApi`) and is exposed
        here so callers can use the unified `cli.resource.*` namespace.

        Args:
            target: 'global' for SUBSCRIPTION-scope, or a DataPlane id/name
                    for DP-scoped creation.

        Returns:
            Result dict from OllyApi.create_o11y_resources, or None on error.
        """
        env = getattr(self.base, "CUSTOM_ENV", {}) or {}
        cp_url = (env.get("TIBCOP_CLI_CPURL") or os.environ.get("TIBCOP_CLI_CPURL", "")).rstrip("/")
        token = env.get("TIBCOP_CLI_OAUTH_TOKEN") or os.environ.get("TIBCOP_CLI_OAUTH_TOKEN") or Helper.get_auto_token()
        if not (cp_url and token):
            ColorLogger.error("TIBCOP_CLI_CPURL or OAuth token missing — cannot create O11Y resources")
            return None
        return OllyApi(ConsoleApiClient(cp_url, token)).create_o11y_resources(target)
