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
Flogo technology module.

Handles Flogo-specific operations:
- List Flogo versions
- Provision Flogo version and connectors
- Create Flogo build
- Deploy Flogo app
- Build and deploy Flogo app (all steps)
"""

import json
import re
import time
from utils.color_logger import ColorLogger
from utils.util import Util
from .base import TibcopBase


class TibcopFlogo:
    """
    Flogo-specific operations.

    Provides methods for Flogo application lifecycle management.
    """

    # The DataPlane itself caps a build at 600s queued + 300s building, so past 900s
    # the build has already given up on its own side and waiting longer is pointless.
    BUILD_WAIT_TIMEOUT = 900
    BUILD_WAIT_INTERVAL = 10

    # How many consecutive unreadable status polls to tolerate before giving up. A
    # permanent failure (bad dataplane, expired token) then surfaces in seconds rather
    # than after the full timeout, while a transient blip is still ridden out.
    BUILD_STATUS_MAX_FAILURES = 3

    # States reported by `flogo:get-build-status`; its --no-loop flag is documented as
    # "Do not loop till the build status is Success or Failure". All matched
    # case-insensitively.
    #
    # Only Queued / Building / Success were observed on a live DataPlane, so the
    # failure vocabulary is NOT exhaustively verified. Success is therefore an exact
    # allow-list (never guess a build is usable), while failure is matched by
    # SUBSTRING: an unrecognized terminal failure must fail fast rather than look like
    # "still running" and burn the whole timeout. A status matching neither list is
    # treated as still-running, but warned about if it is not a known in-progress one.
    #
    # INVARIANT: BUILD_IN_PROGRESS_STATUSES must stay disjoint from
    # BUILD_FAILURE_MARKERS. The failure check is a substring match and runs first, so
    # adding an in-progress state whose name contains one of those markers (say
    # "post-error-cleanup") would silently make it read as a terminal failure.
    BUILD_SUCCESS_STATUSES = ("success", "successful", "succeeded")
    BUILD_FAILURE_MARKERS = ("fail", "error", "cancel", "abort", "reject", "denied",
                             "timeout", "timed out", "expire")
    BUILD_IN_PROGRESS_STATUSES = ("queued", "building", "pending", "running",
                                  "inprogress", "in progress", "started")

    def __init__(self, base: TibcopBase, version_api=None, capability=None, app=None):
        """
        Initialize Flogo handler.

        Args:
            base: TibcopBase instance for command execution
            version_api: CapabilityVersionApi instance (optional)
            capability: TibcopCapability instance for capability operations (optional)
            app: TibcopApp instance for app operations (optional)
        """
        self.base = base
        self.version_api = version_api
        self.capability = capability
        self.app = app

    def list_versions(self, dp_name, other_args=None):
        """
        List Flogo versions from both Control Plane and DataPlane.

        Args:
            dp_name: Name of the dataplane
            other_args: Additional CLI arguments

        Returns:
            Version string (buildtypeTag) if found, None otherwise
        """
        print("\n" + "="*60)
        print("Flogo Version Information")
        print("="*60 + "\n")

        # 1. Get Flogo version from Control Plane (select last version)
        ColorLogger.info("1. Getting Flogo version from Control Plane...")
        cp_version = None
        if self.version_api:
            cp_version = self.version_api.get_capability_version('FLOGO', dp_name, select_last=True)

        if cp_version:
            print()
            Util.print_box(f"Flogo Selected Version on Control Plane: {cp_version}", width=60)
            print()

        # 2. Get Flogo versions from DataPlane
        ColorLogger.info("2. Getting Flogo versions from DataPlane...")
        command = (
            f'{self.base.TIBCOP_CLI_PATH} flogo:list-flogo-versions '
            f'--dataplane-name "{dp_name}" '
            f'--json '
        )
        command += f'{other_args or ""}'

        result = self.base.run_command(command, verbose=False)

        if not result or not result.strip():
            ColorLogger.error("Failed to list Flogo versions on DataPlane")
            return None

        try:
            # Handle potential debug output before JSON
            json_str = result
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError:
                # Try to find JSON from last line backwards
                lines = result.split('\n')
                for i in range(len(lines) - 1, -1, -1):
                    if lines[i].strip().startswith('{'):
                        json_str = '\n'.join(lines[i:])
                        data = json.loads(json_str)
                        break

            buildtype_catalog = Util.extract_response_array(data, 'buildtypeCatalog')

            if not buildtype_catalog:
                ColorLogger.warning("No Flogo versions found on DataPlane")
                return None

            buildtype = buildtype_catalog[0]
            buildtype_tag = buildtype.get('buildtypeTag')
            base_images = buildtype.get('baseImages', [])
            image_tag = base_images[0].get('imageTag') if base_images else None

            print()
            Util.print_box([
                "Flogo Versions on DataPlane:",
                f"  - BuildType Tag: {buildtype_tag}",
                f"  - Base Image Tag: {image_tag}"
            ], width=60)
            print()

            ColorLogger.success(f"Found Flogo version: {buildtype_tag}")
            return buildtype_tag

        except Exception as e:
            ColorLogger.error(f"Error processing Flogo versions: {e}")
            return None

    def provision_version(self, dp_name, flogo_version, other_args=None):
        """
        Provision Flogo version and connector versions.

        Args:
            dp_name: Name of the dataplane
            flogo_version: Flogo version tag (buildtypeTag)
            other_args: Additional CLI arguments

        Returns:
            Command output
        """
        if not self.capability:
            ColorLogger.error("Capability instance not available")
            return None

        # Provision connector: get version from CP API
        connector_version = None
        if self.version_api:
            connector_version = self.version_api.get_connector_version(dp_name, 'General')
        if not connector_version:
            ColorLogger.warning("Could not get connector version from CP API, skipping connector provisioning")
        else:
            self.capability.provision_version('CONNECTOR', dp_name, connector_version,
                                             other_args='--connector-id "General"')

        # Provision Flogo version
        return self.capability.provision_version('FLOGO', dp_name, flogo_version, other_args)

    def create_build(self, dp_name, app_file_path, flogo_version=None, os_type="linux", arch="amd64", other_args=None):
        """
        Create a Flogo build from an app file.

        Args:
            dp_name: Name of the dataplane
            app_file_path: Path to the Flogo app file (.flogo or .json)
            flogo_version: Flogo version (auto-fetched if None)
            os_type: Operating system (default: linux)
            arch: Architecture (default: amd64)
            other_args: Additional CLI arguments

        Returns:
            Build ID if successful, None otherwise
        """
        app_file_path = Util.convert_to_absolute_path(app_file_path)

        # Auto-fetch version if not provided
        if not flogo_version:
            ColorLogger.info("Fetching latest Flogo version...")
            flogo_version = self.list_versions(dp_name, other_args)

            if not flogo_version:
                ColorLogger.error("Cannot proceed without Flogo version")
                return None

        ColorLogger.info(f"Creating Flogo build from '{app_file_path}'...")
        ColorLogger.info(f"Using version: {flogo_version}, OS: {os_type}, Arch: {arch}")

        command = (
            f'{self.base.TIBCOP_CLI_PATH} flogo:create-build '
            f'--flogo-version "{flogo_version}" '
            # f'--os {os_type} '   #FLOGO-17040
            # f'--arch {arch} '
            f'--dataplane-name "{dp_name}" '
            f'"{app_file_path}" '
            f'--json '
        )
        command += f'{other_args or ""}'

        result = self.base.run_command(command)

        # Check for CLI error indicators
        if self.base.is_cli_error(result):
            error_msg = result if result else "Command failed"
            ColorLogger.error(f"Failed to create Flogo build: {error_msg}")
            return None

        # Check for empty response
        if not result or not result.strip():
            ColorLogger.error("Failed to create Flogo build - command returned empty response")
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
                    ColorLogger.success(f"Flogo build created. Build ID: {build_id}")
                    return build_id
                else:
                    # Log what keys are available
                    ColorLogger.warning(f"Response is JSON but no 'buildId' found. Available keys: {list(data.keys())}")
            elif isinstance(data, str):
                if re.match(r'^[a-f0-9]{32}$', data, re.IGNORECASE):
                    ColorLogger.success(f"Flogo build created. Build ID: {data}")
                    return data
        except json.JSONDecodeError as e:
            ColorLogger.warning(f"Response is not valid JSON: {e}")

        # Try regex extraction with multiple patterns
        patterns = [
            r'"id"\s*:\s*"([a-f0-9]{32})"',  # Try "id" field first
            r"['\"]([a-f0-9]{32})['\"]",
            r"buildId['\"]?\s*[:=]\s*['\"]?([a-f0-9]{32})['\"]?",
            r"\b([a-f0-9]{32})\b"
        ]

        for pattern in patterns:
            match = re.search(pattern, result, re.IGNORECASE)
            if match:
                build_id = match.group(1)
                ColorLogger.success(f"Flogo build created. Build ID: {build_id}")
                return build_id

        ColorLogger.error("Failed to extract build ID from response")
        ColorLogger.error(f"Full response was: {result}")
        return None

    def get_build_status(self, build_id, dp_name):
        """
        Get the current status of a Flogo build.

        Uses `flogo:get-build-status --no-loop` so a single call returns the status
        as it is right now; the polling loop and its timeout live in wait_for_build,
        where they can be logged and bounded by this code rather than by the CLI.

        The caller's `other_args` is deliberately NOT forwarded: it is the operator's
        free-form "Additional Command Flags" box, aimed at the operation they picked
        (create-build / deploy-app). A flag that subcommand accepts but this one does
        not would make the poll fail — and wait_for_build aborts on a CLI error — so
        this call keeps a fixed, minimal argv. Credentials come from the environment
        (TIBCOP_CLI_CPURL / TIBCOP_CLI_OAUTH_TOKEN), not from other_args.

        Args:
            build_id: Build ID returned by create_build
            dp_name: Name of the dataplane

        Returns:
            (status, error):
              ("Success", None)  a status was read
              (None, "<text>")   no status; the CLI reported this error text
              (None, None)       no status and no error text to report
        """
        command = (
            f'{self.base.TIBCOP_CLI_PATH} flogo:get-build-status '
            f'--build-id "{build_id}" '
            f'--dataplane-name "{dp_name}" '
            f'--json '
            f'--no-loop '
        )

        result = self.base.run_command(command, verbose=False)

        if result is None:
            # Non-zero exit; run_command already logged the stdout/stderr.
            return None, "command failed"
        if not result.strip():
            return None, None

        # Same tolerance as list_versions: the CLI may emit debug output before the JSON
        data = None
        try:
            data = json.loads(result)
        except json.JSONDecodeError:
            lines = result.split('\n')
            for i in range(len(lines) - 1, -1, -1):
                if lines[i].strip().startswith('{'):
                    try:
                        data = json.loads('\n'.join(lines[i:]))
                    except json.JSONDecodeError:
                        data = None
                    break

        if isinstance(data, dict):
            status = data.get('status')
            if isinstance(status, str) and status.strip():
                return status.strip(), None

        # Parse FIRST, classify second: is_cli_error() matches the substring 'failed',
        # so running it on a valid `{"status": "Failed"}` payload would misread a failed
        # BUILD as a failed COMMAND. Only output that yielded no status gets classified.
        if self.base.is_cli_error(result):
            return None, result.strip()

        return None, None

    def wait_for_build(self, build_id, dp_name, timeout=BUILD_WAIT_TIMEOUT,
                       interval=BUILD_WAIT_INTERVAL):
        """
        Wait until a Flogo build reaches a terminal state.

        `flogo:create-build` is ASYNCHRONOUS: it returns as soon as the build is
        accepted, with status 'Queued'. Deploying that build id right away makes
        `flogo:deploy-app` fail with "Build status is not successful for buildID:
        <id>, buildStatus: Queued" (PCP-23045).

        Polls until a real (monotonic) deadline and logs every attempt, so a stuck
        build shows progress in the pipeline log instead of a silent wait. The clock
        is wall-clock, not a count of intervals, because each poll spawns a tibcop
        subprocess that takes seconds of its own.

        Args:
            build_id: Build ID returned by create_build
            dp_name: Name of the dataplane
            timeout: Maximum wait time in seconds (default: BUILD_WAIT_TIMEOUT)
            interval: Polling interval in seconds (default: BUILD_WAIT_INTERVAL)

        Returns:
            True when the build succeeded; False if it failed, could not be read, or
            timed out.
        """
        interval = max(1, interval)
        ColorLogger.info(f"Waiting for Flogo build '{build_id}' to complete (timeout: {timeout}s)...")

        started = time.monotonic()
        deadline = started + timeout
        unreadable_streak = 0
        while time.monotonic() < deadline:
            status, error = self.get_build_status(build_id, dp_name)
            elapsed = int(time.monotonic() - started)

            if status is None:
                # A read can fail transiently (the status API lags a freshly accepted
                # build) or permanently (bad dataplane, expired token). Rather than
                # guess, tolerate a few in a row and then give up — a permanent error
                # surfaces in seconds instead of hiding behind a misleading
                # "did not complete within {timeout}s".
                unreadable_streak += 1
                detail = f": {error}" if error else ""
                if unreadable_streak >= self.BUILD_STATUS_MAX_FAILURES:
                    ColorLogger.error(
                        f"Giving up on Flogo build '{build_id}': status unreadable "
                        f"{unreadable_streak} times in a row{detail}")
                    return False
                ColorLogger.warning(
                    f"Status of Flogo build '{build_id}' unreadable "
                    f"({unreadable_streak}/{self.BUILD_STATUS_MAX_FAILURES}, {elapsed}s elapsed)"
                    f"{detail}, retrying...")
            else:
                unreadable_streak = 0
                lowered = status.lower()
                if lowered in self.BUILD_SUCCESS_STATUSES:
                    ColorLogger.success(f"Flogo build '{build_id}' finished: {status} (after {elapsed}s)")
                    return True
                if any(marker in lowered for marker in self.BUILD_FAILURE_MARKERS):
                    ColorLogger.error(f"Flogo build '{build_id}' ended in a failed state: {status}")
                    return False
                if lowered in self.BUILD_IN_PROGRESS_STATUSES:
                    ColorLogger.info(f"Flogo build '{build_id}' status: '{status}' ({elapsed}s elapsed), waiting...")
                else:
                    ColorLogger.warning(
                        f"Flogo build '{build_id}' reported an unrecognized status '{status}' "
                        f"({elapsed}s elapsed); treating it as in progress")

            # Never sleep past the deadline, so the reported timeout is the real one.
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(interval, remaining))

        ColorLogger.error(f"Flogo build '{build_id}' did not complete within {timeout}s")
        return False

    def deploy_app(self, dp_name, dp_namespace, deploy_config_file, build_id=None, other_args=None):
        """
        Deploy a Flogo app using a deployment configuration file.

        Args:
            dp_name: Name of the dataplane
            dp_namespace: Namespace of the dataplane
            deploy_config_file: Path to the deployment config JSON file
            build_id: Build ID (optional, read from config if not provided)
            other_args: Additional CLI arguments

        Returns:
            Command output
        """
        deploy_config_file = Util.convert_to_absolute_path(deploy_config_file)

        # Read/update config file with build ID
        try:
            with open(deploy_config_file, 'r') as f:
                config = json.load(f)

            if build_id:
                config['buildId'] = build_id
                with open(deploy_config_file, 'w') as f:
                    json.dump(config, f, indent=4)
                ColorLogger.info(f"Updated buildId in config: {build_id}")
            else:
                build_id = config.get('buildId')
                if not build_id or build_id == 'string':
                    ColorLogger.error("No valid buildId found in config file")
                    return None
                ColorLogger.info(f"Using buildId from config: {build_id}")

        except Exception as e:
            ColorLogger.error(f"Failed to read/update config file: {e}")
            return None

        ColorLogger.info(f"Deploying Flogo app to '{dp_name}'...")

        command = (
            f'{self.base.TIBCOP_CLI_PATH} flogo:deploy-app '
            f'--dataplane-name "{dp_name}" '
            f'--namespace "{dp_namespace}" '
            f'"{deploy_config_file}" '
        )

        if build_id:
            command += f'--build-id "{build_id}" '

        command += f'{other_args or ""}'

        result = self.base.run_command(command)

        if self.base.is_cli_error(result):
            error_msg = result if result else "Command failed"
            ColorLogger.error(f"Failed to deploy Flogo app: {error_msg}")
            return None

        ColorLogger.success("Flogo app deployed successfully")
        if self.app:
            print("\n" + "="*60)
            print("Updated app list:")
            print("="*60 + "\n")
            self.app.list_apps(dp_name, print_result=True)
        return result

    def build_and_deploy_app(self, dp_name, app_file_path, deploy_config_file, dp_namespace=None, other_args=None):
        """
        Build and deploy a Flogo app (all steps).

        Orchestrates the complete workflow:
        1. Get Flogo version from CP
        2. Provision Flogo version and connectors
        3. List versions
        4. Create build
        5. Deploy app

        Args:
            dp_name: Name of the dataplane
            app_file_path: Path to the Flogo app JSON file
            deploy_config_file: Path to the deployment config JSON file
            dp_namespace: Namespace (defaults to {dp_name}ns)
            other_args: Additional CLI arguments

        Returns:
            True if successful, False otherwise
        """
        ColorLogger.info(f"Starting Flogo app build and deployment for '{dp_name}'...")

        # Pre-check: Verify Flogo capability is provisioned
        ColorLogger.info("Pre-check: Verifying Flogo capability is provisioned...")
        if self.capability and not self.capability.is_capability_provisioned(dp_name, 'FLOGO'):
            ColorLogger.error("Flogo capability is not provisioned in this DataPlane.")
            ColorLogger.warning("Please provision Flogo capability first and wait for it to be ready, then come back here to build and deploy.")
            ColorLogger.info("You can use 'provision_flogo' or 'provision-capability' with capability=FLOGO to provision.")
            return False
        ColorLogger.success("Flogo capability is provisioned and ready")

        app_file_path = Util.convert_to_absolute_path(app_file_path)
        deploy_config_file = Util.convert_to_absolute_path(deploy_config_file)

        if not dp_namespace:
            dp_namespace = f"{dp_name}ns"

        # Step 1: Get version from CP (select last version)
        ColorLogger.info("Step 1/5: Getting Flogo version from CP...")
        flogo_version = None
        if self.version_api:
            flogo_version = self.version_api.get_capability_version('FLOGO', dp_name, select_last=True)

        if not flogo_version:
            ColorLogger.error("Failed to get Flogo version")
            return False

        # Step 2: Provision version
        ColorLogger.info(f"Step 2/5: Provisioning Flogo version '{flogo_version}'...")
        result = self.provision_version(dp_name, flogo_version, other_args)
        if self.base.is_cli_error(result):
            ColorLogger.error("Failed to provision Flogo version")
            return False

        # Step 3: List versions (confirmation)
        ColorLogger.info("Step 3/5: Listing versions...")
        self.list_versions(dp_name, other_args)

        # Step 4: Create build
        ColorLogger.info(f"Step 4/5: Creating build from '{app_file_path}'...")
        build_id = self.create_build(dp_name, app_file_path, flogo_version, other_args=other_args)
        if not build_id:
            ColorLogger.error("Failed to create build")
            return False

        # create-build is asynchronous — it returns while the build is still 'Queued'.
        # Deploying before it reaches 'Success' fails every time (PCP-23045).
        if not self.wait_for_build(build_id, dp_name):
            ColorLogger.error(f"Build '{build_id}' is not usable, skipping deploy")
            return False

        # Step 5: Deploy app
        ColorLogger.info("Step 5/5: Deploying app...")
        result = self.deploy_app(dp_name, dp_namespace, deploy_config_file, build_id, other_args)
        if self.base.is_cli_error(result):
            ColorLogger.error("Failed to deploy app")
            return False

        ColorLogger.success("Flogo app build and deployment completed!")
        return True
