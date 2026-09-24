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
from utils.naming import storage_resource_candidates
from .base import TibcopBase, normalize_gateway_controller


# `--ems-sizing` is a free-text flag: tibcop 1.21 documents it as "EMS sizing (e.g. small,
# medium, large)" and accepts anything. The value is only rejected much later, by the DP-side
# Helm render, which surfaces as a capability that provisions "successfully" and then never
# comes up. Validate in Python so a typo fails before the request is sent.
EMS_SIZINGS = ("small", "medium", "large", "xlarge")


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

    def is_capability_provisioned(self, dp_name, capability, capability_name=""):
        """
        Check if a capability is already provisioned in the DataPlane.

        Args:
            dp_name: Name of the dataplane
            capability: Capability type (BWCE, BW5CE, FLOGO, TIBCOHUB, CONNECTOR, EMS)
            capability_name: Optional instance name that must ALSO match, compared exactly
                against the ``name`` field of the list-capability-instances JSON.

                Mirrors the UI signature (po_dataplane.is_capability_provisioned). Left
                empty, the answer is "is there any instance of this capability type", which
                is what every capability with exactly one instance per Data Plane wants.
                EMS is the exception that motivated the parameter (PCP-24380): a Data Plane
                may legitimately hold several EMS servers, so "some EMS exists" would skip
                provisioning the one that was actually asked for. Exact equality, not the
                anchored-substring matcher the UI side needs - this reads a JSON field, not
                a rendered table cell, so there is no substring hazard to guard against.

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
                if cap_type != capability_upper:
                    continue
                if not capability_name or cap.get('name') == capability_name:
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

    def resolve_storage_resource_id(self, dp_name):
        """The Data Plane's storage resource instance id, creating the resource if needed.

        Distinct from the ``{capability}-{storageclass}-storage`` resource that
        provision_capability auto-creates for BWCE/FLOGO/TIBCOHUB: EMS binds to the Data
        Plane's OWN storage resource, which is what the UI wizard offers and what
        cli_object/orchestrator.py creates as ``{dp_name}-storage``. Getting this wrong is
        not theoretical - it is PCP-23953 with the roles reversed.

        The names are tried in utils.naming.storage_resource_candidates() order, first hit
        wins, and only if NOTHING matches is a resource created - under the CLI convention
        ``{dp_name}-storage``, the same name orchestrator.py uses, so a later run of either
        entry point finds it instead of making a second one.

        Returns the resource id, or None if it could not be found or created. None must
        abort the caller: provisioning EMS against a storage resource that does not exist
        fails on the CP side with a far less obvious message.
        """
        if not self.resource:
            ColorLogger.error("Resource instance not available, cannot resolve the storage resource")
            return None

        candidates = storage_resource_candidates(dp_name)
        for resource_name in candidates:
            existing_id = self.resource.get_resource_id_by_name(dp_name, resource_name)
            if existing_id:
                ColorLogger.info(f"Found existing storage resource '{resource_name}' with ID '{existing_id}'")
                return existing_id

        storage_resource_name = candidates[0]
        storage_class_name = ENV.TP_AUTO_STORAGE_CLASS
        ColorLogger.info(f"None of {candidates} exists, creating storage resource '{storage_resource_name}' with storage class '{storage_class_name}'...")
        result = self.resource.create_storage_resource(
            dp_name=dp_name,
            resource_name=storage_resource_name,
            storage_class_name=storage_class_name,
            description=f"Auto-created storage for DataPlane {dp_name}"
        )
        if result is None:
            ColorLogger.error(f"Failed to create storage resource '{storage_resource_name}'")
            return None

        storage_resource_id = self.resource.get_resource_id_by_name(dp_name, storage_resource_name)
        if not storage_resource_id:
            ColorLogger.error(f"Failed to get resource ID for newly created storage resource '{storage_resource_name}'")
            return None
        ColorLogger.success(f"Storage resource '{storage_resource_name}' created with ID '{storage_resource_id}'")
        return storage_resource_id

    def provision_capability(self, dp_name, capability, storage_resource_id=None, ingress_resource_id=None,
                            gateway_resource_id=None, path_prefix=None, devhub_name=None,
                            k8s_secret=None, other_args=None,
                            msg_data_resource_id=None, log_data_resource_id=None,
                            ems_name=None, ems_sizing=None, ems_use=None):
        """
        Provision a capability (BWCE/BW5CE/FLOGO/TIBCOHUB/CONNECTOR/EMS) in a DataPlane.

        Auto-creates required storage and route (ingress or gateway) resources if IDs not provided.

        Route resource selection:
        - If ``gateway_resource_id`` is given (or auto-created when
          ``ENV.TP_AUTO_INGRESS_OBJECT == "gateway"``), the capability is provisioned
          with ``--gateway-resource-instance-id`` (K8s Gateway API).
        - Otherwise the original ingress path is used. Explicit ``ingress_resource_id``
          always wins over the gateway auto-create branch.

        **EMS takes none of that** (PCP-24380). It binds two DATA resources
        (``--msg-data-resource-instance-id`` / ``--log-data-resource-instance-id``),
        resolved from the Data Plane's OWN storage resource rather than the
        per-capability ``{cap}-{sc}-storage`` this method auto-creates for the others,
        and it has no HTTP route at all - so the whole gateway/ingress block, and the
        ``--path-prefix`` / ``--fluentbit-sidecar-enabled`` catch-all, are skipped for it.
        Any storage/ingress/gateway id a caller passes for EMS is dropped, not forwarded.

        Args:
            dp_name: Name of the dataplane
            capability: Capability type (BWCE, BW5CE, FLOGO, TIBCOHUB, CONNECTOR, EMS)
            storage_resource_id: Storage resource instance ID (auto-creates if not provided)
            ingress_resource_id: Ingress resource instance ID (auto-creates if not provided
                and ``TP_AUTO_INGRESS_OBJECT != "gateway"``)
            gateway_resource_id: Gateway API resource instance ID (auto-creates if not
                provided and ``TP_AUTO_INGRESS_OBJECT == "gateway"``)
            path_prefix: Path prefix (for BWCE/BW5CE/FLOGO), default: /tibco/{capability}/{dataplane_id}
            devhub_name: Developer hub name (for TIBCOHUB only, defaults from ENV.TP_AUTO_TIBCOHUB_CAPABILITY_HUB_NAME)
            k8s_secret: Kubernetes secret object name (for TIBCOHUB only)
            other_args: Additional CLI arguments
            msg_data_resource_id: EMS message-storage resource instance ID (auto-resolved
                from the Data Plane's storage resource if not provided)
            log_data_resource_id: EMS log-storage resource instance ID (same; may be - and
                by default is - the SAME resource as the message one, which is what the UI
                wizard binds too)
            ems_name: EMS server name (for EMS only, defaults from
                ENV.TP_AUTO_EMS_CAPABILITY_SERVER_NAME)
            ems_sizing: EMS sizing (for EMS only, one of EMS_SIZINGS, defaults from
                ENV.TP_AUTO_EMS_CAPABILITY_SIZING)
            ems_use: EMS usage profile (for EMS only, default "dev"; NOT validated - the
                CP blanks it on every path, see the comment at the default below)

        Returns:
            Command output, or "ALREADY_PROVISIONED" if capability exists
        """
        capability_upper = capability.upper()
        is_ems = capability_upper == "EMS"

        if is_ems:
            ems_name = ems_name or ENV.TP_AUTO_EMS_CAPABILITY_SERVER_NAME
            ems_sizing = (ems_sizing or ENV.TP_AUTO_EMS_CAPABILITY_SIZING or "").lower()
            # 'dev' is the wizard's own default. It is hardcoded here rather than exposed as
            # an env var because it does NOT affect the resulting capability name: the CP
            # blanks ems.use on BOTH the UI and the CLI path, the card and
            # /cp/api/v1/data-planes/{dpId}/capabilities/instances both report the bare
            # server name, and po_dp_ems.py used to append '-dev' on the opposite belief and
            # hard-failed verification for it (PCP-24380). Nobody should infer naming from
            # this value. The CP blanking it is MSGDP's call and is out of scope here.
            # No allow-list for --ems-use, deliberately, and it is not an oversight next to
            # the EMS_SIZINGS check below. --ems-sizing is validated because a bad value
            # survives tibcop and then breaks the DP-side Helm render; --ems-use cannot,
            # because the CP never uses the value at all - the chart's escape hatch blanks
            # ems.use to "" on BOTH the CLI and the UI path (verified on tibcop 1.21 against
            # the AWS lab). There is therefore no value that can be "wrong", and an
            # allow-list built from the CLI's own misleading "e.g. dev, prod" help text
            # would only reject values the CP is indifferent to.
            ems_use = ems_use or "dev"
            if ems_sizing not in EMS_SIZINGS:
                ColorLogger.error(
                    f"Unsupported EMS sizing '{ems_sizing}'. Must be one of: {', '.join(EMS_SIZINGS)}")
                return None

        # Check if capability is already provisioned. EMS passes the server name: a Data
        # Plane may hold several EMS servers, so "an EMS exists" is not the same question as
        # "the EMS that was asked for exists", and answering the former would silently skip
        # provisioning the latter.
        if self.is_capability_provisioned(dp_name, capability_upper,
                                          capability_name=ems_name if is_ems else ""):
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

        # EMS resolves its two data resources from the Data Plane's OWN storage resource and
        # takes no route resource at all, so the whole gateway/ingress block below and the
        # per-capability '{cap}-{sc}-storage' auto-create are skipped for it. Any
        # storage/ingress/gateway id a caller passed is dropped rather than forwarded:
        # `--storage-resource-instance-id` on an EMS provision is not a no-op, it is a wrong
        # binding, and the Web UI form does not offer those fields for EMS anyway.
        if is_ems:
            storage_resource_id = ingress_resource_id = gateway_resource_id = None
            if not (msg_data_resource_id and log_data_resource_id):
                resolved_storage_id = self.resolve_storage_resource_id(dp_name)
                if not resolved_storage_id:
                    ColorLogger.error(f"Could not resolve a storage resource, cannot continue provisioning {capability}")
                    return None
                # Both default to the same resource - that is what the UI wizard binds when
                # the Data Plane offers one storage resource, which is the normal case.
                msg_data_resource_id = msg_data_resource_id or resolved_storage_id
                log_data_resource_id = log_data_resource_id or resolved_storage_id

        # Auto-create storage resource if not provided
        if not is_ems and not storage_resource_id and self.resource:
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

        # Decide route kind: Gateway API vs Ingress. EMS is excluded: it has no HTTP route,
        # and provisioning it with one binds a resource the capability cannot use.
        use_gateway = (not is_ems
                       and ENV.TP_AUTO_INGRESS_OBJECT.lower() == "gateway"
                       and not ingress_resource_id)

        # Auto-create gateway API resource if requested and not provided
        if use_gateway and not gateway_resource_id and self.resource:
            gateway_apicontroller = normalize_gateway_controller(ENV.TP_AUTO_GATEWAY_CONTROLLER)
            gw_name_map = {
                "BWCE": ENV.TP_AUTO_GATEWAY_CONTROLLER_BWCE,
                "BW5CE": ENV.TP_AUTO_GATEWAY_CONTROLLER_BW5CE,
                "FLOGO": ENV.TP_AUTO_GATEWAY_CONTROLLER_FLOGO,
                "TIBCOHUB": ENV.TP_AUTO_GATEWAY_CONTROLLER_TIBCOHUB,
            }
            gateway_resource_name = gw_name_map.get(
                capability.upper(),
                f"{ENV.TP_AUTO_GATEWAY_CONTROLLER}-{capability.lower()}",
            )
            ColorLogger.info(f"Gateway resource ID not provided, checking if gateway resource '{gateway_resource_name}' exists...")

            existing_gateway_id = self.resource.get_resource_id_by_name(dp_name, gateway_resource_name)
            if existing_gateway_id:
                ColorLogger.info(f"Found existing gateway resource with ID '{existing_gateway_id}'")
                gateway_resource_id = existing_gateway_id
            else:
                fqdn_map = {
                    "BWCE": ENV.TP_AUTO_FQDN_BWCE,
                    "BW5CE": ENV.TP_AUTO_FQDN_BW5CE,
                    "FLOGO": ENV.TP_AUTO_FQDN_FLOGO,
                    "TIBCOHUB": ENV.TP_AUTO_FQDN_TIBCOHUB,
                }
                fqdn = fqdn_map.get(capability.upper(), ENV.TP_AUTO_FQDN_BWCE)
                ColorLogger.info(f"Creating new gateway API resource '{gateway_resource_name}' with FQDN '{fqdn}', controller '{gateway_apicontroller}', gateway '{ENV.TP_AUTO_GATEWAY_NAME}' in '{ENV.TP_AUTO_GATEWAY_NAMESPACE}'...")
                result = self.resource.create_gateway_api_resource(
                    dp_name=dp_name,
                    resource_name=gateway_resource_name,
                    gateway_name=ENV.TP_AUTO_GATEWAY_NAME,
                    gateway_namespace=ENV.TP_AUTO_GATEWAY_NAMESPACE,
                    fqdn=fqdn,
                    gateway_apicontroller_name=gateway_apicontroller,
                    gateway_section_name=ENV.TP_AUTO_GATEWAY_SECTION_NAME,
                )
                if result is None:
                    ColorLogger.error(f"Failed to create gateway resource, cannot continue provisioning {capability}")
                    return None
                gateway_resource_id = self.resource.get_resource_id_by_name(dp_name, gateway_resource_name)
                if not gateway_resource_id:
                    ColorLogger.error(f"Failed to get resource ID for newly created gateway resource '{gateway_resource_name}'")
                    return None
                ColorLogger.success(f"Gateway resource '{gateway_resource_name}' created with ID '{gateway_resource_id}'")

        # Auto-create ingress resource if not provided (skipped when using gateway, and for
        # EMS, which takes no route resource)
        if not is_ems and not gateway_resource_id and not ingress_resource_id and self.resource:
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

        # Add storage and route resource (gateway preferred over ingress when both set)
        if storage_resource_id:
            command += f'--storage-resource-instance-id "{storage_resource_id}" '
        if gateway_resource_id:
            command += f'--gateway-resource-instance-id "{gateway_resource_id}" '
        elif ingress_resource_id:
            command += f'--ingress-resource-instance-id "{ingress_resource_id}" '

        # Add capability-specific parameters
        if capability.upper() == "TIBCOHUB":
            # TIBCOHUB-specific parameters
            if devhub_name:
                command += f'--developer-hub-name "{devhub_name}" '
            if k8s_secret:
                command += f'--kubernetes-secret-object "{k8s_secret}" '
        elif is_ems:
            # EMS-specific parameters. This arm exists BEFORE the else because the else is a
            # catch-all: without it EMS was provisioned with --path-prefix "None" and
            # --fluentbit-sidecar-enabled, neither of which EMS has any use for and the first
            # of which is a literal "None" string (PCP-24380).
            #
            # EMS takes its own pair of data-resource flags, NOT
            # --storage-resource-instance-id. Verified against the tibcop 1.21 command
            # surface, which documents exactly:
            #   --msg-data-resource-instance-id / --log-data-resource-instance-id
            #   --ems-name / --ems-use / --ems-sizing
            #   --ems-msg-storage-name / --ems-log-storage-name
            command += f'--msg-data-resource-instance-id "{msg_data_resource_id}" '
            command += f'--log-data-resource-instance-id "{log_data_resource_id}" '
            command += f'--ems-name "{ems_name}" '
            command += f'--ems-use "{ems_use}" '
            command += f'--ems-sizing "{ems_sizing}" '
            # The storage NAMES are the Kubernetes StorageClass, which is what
            # ENV.TP_AUTO_STORAGE_CLASS holds; they are deliberately not a parameter of this
            # method and not a field on the Web UI form. A value that disagrees with the
            # resolved resource instance is the PCP-23953 failure class again, and whether
            # the CP even reads these is unverifiable without deliberately passing a wrong
            # one (the resource instance GUI mode creates is itself NAMED after the storage
            # class, so "the CP used our value" and "the CP derived it" look identical).
            # Omitted entirely when the storage class is unknown rather than sent as "".
            storage_class_name = (ENV.TP_AUTO_STORAGE_CLASS or "").strip()
            if storage_class_name:
                command += f'--ems-msg-storage-name "{storage_class_name}" '
                command += f'--ems-log-storage-name "{storage_class_name}" '
            # No health assertion follows this call, deliberately. For roughly three minutes
            # after an EMS provision the CP reports the capability red, "Capability running
            # in DP with Errors" - that is the Prometheus scrape window filling, not a
            # failure. Anything added later that checks EMS health needs a grace period of
            # that order, or it will report a false negative on every successful run.
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
