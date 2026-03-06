#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary
"""
BW5CE technology module.

Handles BW5CE-specific operations:
- List BW5CE versions
- Provision BW5CE version
- Create BW5CE build
- Deploy BW5CE app
- Build and deploy BW5CE app (all steps)
"""

import json
import re
from utils.color_logger import ColorLogger
from utils.util import Util
from .base import TibcopBase


class TibcopBW5CE:
    """
    BW5CE-specific operations.

    Provides methods for BW5CE application lifecycle management.
    """

    def __init__(self, base: TibcopBase, api=None, capability=None, app=None):
        """
        Initialize BW5CE handler.

        Args:
            base: TibcopBase instance for command execution
            api: TibcopAPI instance for REST API operations (optional)
            capability: TibcopCapability instance for capability operations (optional)
            app: TibcopApp instance for app operations (optional)
        """
        self.base = base
        self.api = api
        self.capability = capability
        self.app = app

    def list_versions(self, dp_name, other_args=None):
        """
        List BW5CE versions from both Control Plane and DataPlane.

        Args:
            dp_name: Name of the dataplane
            other_args: Additional CLI arguments

        Returns:
            Tuple of (buildtypeTag, imageTag) or (None, None) if failed
        """
        print("\n" + "="*60)
        print("BW5CE Version Information")
        print("="*60 + "\n")

        # 1. Get BW5CE version from Control Plane (select last version)
        ColorLogger.info("1. Getting BW5CE version from Control Plane...")
        cp_version = None
        if self.api:
            # BW5CE uses select_last=True to get the latest version
            cp_version = self.api.get_capability_version_from_cp_api('BW5CE', dp_name, select_last=True)

        if cp_version:
            print()
            Util.print_box(f"BW5CE Selected Version on Control Plane: {cp_version}", width=60)
            print()

        # 2. Get BW5CE versions from DataPlane
        ColorLogger.info("2. Getting BW5CE versions from DataPlane...")
        command = (
            f'{self.base.TIBCOP_CLI_PATH} bw5ce:list-bw5ceversions '
            f'--dataplane-name "{dp_name}" '
            f'--json '
        )
        command += f'{other_args or ""}'

        result = self.base.run_command(command, verbose=False)

        if not result or not result.strip():
            ColorLogger.error("Failed to list BW5CE versions on DataPlane")
            return None, None

        try:
            data = json.loads(result)
            buildtype_catalog = Util.extract_response_array(data, 'buildtypeCatalog')

            if not buildtype_catalog:
                ColorLogger.warning("No BW5CE versions found on DataPlane")
                return None, None

            buildtype = buildtype_catalog[0]
            buildtype_tag = buildtype.get('buildtypeTag')
            base_images = buildtype.get('baseImages', [])
            image_tag = base_images[0].get('imageTag') if base_images else None

            print()
            Util.print_box([
                "BW5CE Versions on DataPlane:",
                f"  - BuildType Tag: {buildtype_tag}",
                f"  - Base Image Tag: {image_tag}"
            ], width=60)
            print()

            ColorLogger.success(f"Found BW5CE version: {buildtype_tag}, Image: {image_tag}")
            return buildtype_tag, image_tag

        except Exception as e:
            ColorLogger.error(f"Error processing BW5CE versions: {e}")
            return None, None

    def provision_version(self, dp_name, bw5ce_version, other_args=None):
        """
        Provision a BW5CE version.

        Args:
            dp_name: Name of the dataplane
            bw5ce_version: BW5CE version tag (buildtypeTag)
            other_args: Additional CLI arguments

        Returns:
            Command output
        """
        if self.capability:
            return self.capability.provision_version('BW5CE', dp_name, bw5ce_version, other_args)
        else:
            ColorLogger.error("Capability instance not available")
            return None

    def create_build(self, dp_name, ear_file_path, bw5ce_version=None, base_image_tag=None, other_args=None):
        """
        Create a BW5CE build from an EAR file.

        Args:
            dp_name: Name of the dataplane
            ear_file_path: Path to the BW5CE EAR file
            bw5ce_version: BW5CE version tag (auto-fetched if None)
            base_image_tag: Base image tag (auto-fetched if None)
            other_args: Additional CLI arguments

        Returns:
            Build ID if successful, None otherwise
        """
        ear_file_path = Util.convert_to_absolute_path(ear_file_path)

        # Auto-fetch version and tag if not provided
        if not bw5ce_version or not base_image_tag:
            ColorLogger.info("Fetching latest BW5CE version and base image tag...")
            bw5ce_version, base_image_tag = self.list_versions(dp_name, other_args)

            if not bw5ce_version or not base_image_tag:
                ColorLogger.error("Failed to get BW5CE version information")
                return None

        ColorLogger.info(f"Creating BW5CE build from '{ear_file_path}'...")
        ColorLogger.info(f"Using version: {bw5ce_version}, Image tag: {base_image_tag}")

        command = (
            f'{self.base.TIBCOP_CLI_PATH} bw5ce:create-build '
            f'--bw5ce-version "{bw5ce_version}" '
            f'--base-image-tag "{base_image_tag}" '
            f'--auto-provision "{ear_file_path}" '
            f'--dataplane-name "{dp_name}" '
            '--json '
        )
        command += f'{other_args or ""}'

        result = self.base.run_command(command)

        # Check for CLI error indicators
        if self.base.is_cli_error(result):
            error_msg = result if result else "Command failed"
            ColorLogger.error(f"Failed to create BW5CE build: {error_msg}")
            return None

        # Check for empty response
        if not result or not result.strip():
            ColorLogger.error("Failed to create BW5CE build - command returned empty response")
            ColorLogger.error("This usually means the tibcop command failed silently or had an error")
            ColorLogger.error("Try running the command with --debug flag to see more details")
            return None

        # Log the actual response for debugging
        ColorLogger.info(f"Build command response: {result[:500]}")  # First 500 chars

        # Extract build ID from result
        try:
            data = json.loads(result)
            if isinstance(data, dict):
                build_id = data.get('buildId')
                if build_id:
                    ColorLogger.success(f"BW5CE build created. Build ID: {build_id}")
                    return build_id
                else:
                    # Log what keys are available
                    ColorLogger.warning(f"Response is JSON but no 'buildId' found. Available keys: {list(data.keys())}")
            elif isinstance(data, str):
                # Response is a JSON-encoded string, check if it's a valid build ID
                if re.match(r'^[a-f0-9]{32}$', data, re.IGNORECASE):
                    ColorLogger.success(f"BW5CE build created. Build ID: {data}")
                    return data
                else:
                    ColorLogger.warning(f"Response is a string but not a valid build ID format: {data}")
        except json.JSONDecodeError as e:
            ColorLogger.warning(f"Response is not valid JSON: {e}")

        # Try regex extraction with multiple patterns
        patterns = [
            r'"id"\s*:\s*"([a-f0-9]{32})"',  # Try "id" field first
            r"buildId['\"]?\s*[:=]\s*['\"]?([a-f0-9]{32})['\"]?",
            r"\b([a-f0-9]{32})\b"
        ]

        for pattern in patterns:
            match = re.search(pattern, result, re.IGNORECASE)
            if match:
                build_id = match.group(1)
                ColorLogger.success(f"BW5CE build created. Build ID: {build_id}")
                return build_id

        ColorLogger.error("Failed to extract build ID from response")
        ColorLogger.error(f"Full response was: {result}")
        return None

    def deploy_app(self, dp_name, dp_namespace, deploy_config_file, other_args=None):
        """
        Deploy a BW5CE app using a deployment configuration file.

        Args:
            dp_name: Name of the dataplane
            dp_namespace: Namespace of the dataplane
            deploy_config_file: Path to the deployment config JSON file
            other_args: Additional CLI arguments

        Returns:
            Command output
        """
        deploy_config_file = Util.convert_to_absolute_path(deploy_config_file)

        ColorLogger.info(f"Deploying BW5CE app to '{dp_name}' using config '{deploy_config_file}'...")
        command = (
            f'{self.base.TIBCOP_CLI_PATH} bw5ce:deploy-app '
            f'--dataplane-name "{dp_name}" '
            f'--namespace "{dp_namespace}" '
            f'"{deploy_config_file}" '
        )
        command += f'{other_args or ""}'

        result = self.base.run_command(command)

        if self.base.is_cli_error(result):
            error_msg = result if result else "Command failed"
            ColorLogger.error(f"Failed to deploy BW5CE app: {error_msg}")
            return None

        ColorLogger.success("BW5CE app deployed successfully")
        if self.app:
            print("\n" + "="*60)
            print("Updated app list:")
            print("="*60 + "\n")
            self.app.list_apps(dp_name, print_result=True)
        return result

    def build_and_deploy_app(self, dp_name, ear_file_path, deploy_config_file, dp_namespace=None, other_args=None):
        """
        Build and deploy a BW5CE app (all steps).

        Orchestrates the complete workflow:
        1. Get BW5CE version from CP
        2. Provision BW5CE version
        3. List versions to get image tag
        4. Create build
        5. Deploy app

        Args:
            dp_name: Name of the dataplane
            ear_file_path: Path to the BW5CE EAR file
            deploy_config_file: Path to the deployment config JSON file
            dp_namespace: Namespace (defaults to {dp_name}ns)
            other_args: Additional CLI arguments

        Returns:
            True if successful, False otherwise
        """
        ColorLogger.info(f"Starting BW5CE app build and deployment for '{dp_name}'...")

        # Pre-check: Verify BW5CE capability is provisioned
        ColorLogger.info("Pre-check: Verifying BW5CE capability is provisioned...")
        if self.capability and not self.capability.is_capability_provisioned(dp_name, 'BW5CE'):
            ColorLogger.error("BW5CE capability is not provisioned in this DataPlane.")
            ColorLogger.warning("Please provision BW5CE capability first and wait for it to be ready, then come back here to build and deploy.")
            ColorLogger.info("You can use 'provision_bw5ce' or 'provision-capability' with capability=BW5CE to provision.")
            return False
        ColorLogger.success("BW5CE capability is provisioned and ready")

        ear_file_path = Util.convert_to_absolute_path(ear_file_path)
        deploy_config_file = Util.convert_to_absolute_path(deploy_config_file)

        if not dp_namespace:
            dp_namespace = f"{dp_name}ns"

        # Step 1: Get version from CP (select last version for BW5CE)
        ColorLogger.info("Step 1/5: Getting BW5CE version from CP...")
        bw5ce_version = None
        if self.api:
            bw5ce_version = self.api.get_capability_version_from_cp_api('BW5CE', dp_name, select_last=True)

        if not bw5ce_version:
            ColorLogger.error("Failed to get BW5CE version")
            return False

        # Step 2: Provision version
        ColorLogger.info(f"Step 2/5: Provisioning BW5CE version '{bw5ce_version}'...")
        result = self.provision_version(dp_name, bw5ce_version, other_args)
        if self.base.is_cli_error(result):
            ColorLogger.error("Failed to provision BW5CE version")
            return False

        # Step 3: List versions to get image tag
        ColorLogger.info("Step 3/5: Getting base image tag...")
        _, base_image_tag = self.list_versions(dp_name, other_args)
        if not base_image_tag:
            ColorLogger.error("Failed to get base image tag")
            return False

        # Step 4: Create build
        ColorLogger.info(f"Step 4/5: Creating build from '{ear_file_path}'...")
        build_id = self.create_build(dp_name, ear_file_path, bw5ce_version, base_image_tag, other_args)
        if not build_id:
            ColorLogger.error("Failed to create build")
            return False

        # Update deployment config with build ID
        try:
            with open(deploy_config_file, 'r') as f:
                config = json.load(f)
            config['buildId'] = build_id
            with open(deploy_config_file, 'w') as f:
                json.dump(config, f, indent=2)
            ColorLogger.success(f"Updated config with buildId: {build_id}")
        except Exception as e:
            ColorLogger.error(f"Failed to update config: {e}")
            return False

        # Step 5: Deploy app
        ColorLogger.info("Step 5/5: Deploying app...")
        result = self.deploy_app(dp_name, dp_namespace, deploy_config_file, other_args)
        if self.base.is_cli_error(result):
            ColorLogger.error("Failed to deploy app")
            return False

        ColorLogger.success("BW5CE app build and deployment completed!")
        return True
