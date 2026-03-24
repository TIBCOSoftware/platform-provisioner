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
Application management module.

Handles all application-related operations:
- List applications
- Get app ID by capability and name
- Delete applications
"""

import json
from utils.color_logger import ColorLogger
from .base import TibcopBase


class TibcopApp:
    """
    Application management operations.

    Provides methods for managing TIBCO Platform applications including
    listing, querying, and deleting apps by capability type.
    """

    def __init__(self, base: TibcopBase):
        """
        Initialize App handler.

        Args:
            base: TibcopBase instance for command execution
        """
        self.base = base

    def _get_apps_data(self, dp_name, other_args=None):
        """
        Internal method to get apps data as list of dicts.

        Args:
            dp_name: Name of the dataplane
            other_args: Additional CLI arguments

        Returns:
            List of app dictionaries with filtered fields
        """
        command = (
            f'{self.base.TIBCOP_CLI_PATH} tplatform:list-apps '
            f'--dataplane-name="{dp_name}" '
            f'--json '
            f'{other_args or ""}'
        )
        # Don't print command output for internal data retrieval
        result = self.base.run_command(command, verbose=False)

        # Check for CLI error indicators
        if self.base.is_cli_error(result):
            error_msg = result if result else "Command failed"
            ColorLogger.error(f"Failed to get apps data: {error_msg}")
            return []

        try:
            # Parse the full response
            data = json.loads(result)
            filtered_apps = []

            # Extract only useful fields
            for app in data.get('response', []):
                filtered_apps.append({
                    'app_id': app.get('app_id'),
                    'app_name': app.get('app_name'),
                    'app_state': app.get('app_state'),
                    'capability_id': app.get('capability_id'),
                    'app_namespace': app.get('app_namespace')
                })

            return filtered_apps

        except json.JSONDecodeError as e:
            ColorLogger.error(f"Failed to parse JSON response: {e}")
            return []

    def list_apps(self, dp_name, other_args=None, print_result=False):
        """
        List all apps in a DataPlane.

        Returns table format output directly from tibcop CLI.

        Args:
            dp_name: Name of the dataplane
            other_args: Additional CLI arguments
            print_result: Whether to print the result during execution

        Returns:
            Table string from tibcop CLI
        """
        ColorLogger.info(f"Listing apps in DataPlane '{dp_name}'...")
        command = (
            f'{self.base.TIBCOP_CLI_PATH} tplatform:list-apps '
            f'--dataplane-name="{dp_name}" '
        )
        command += f'{other_args or ""}'
        result = self.base.run_command(command, verbose=False)

        # Check for CLI error indicators
        if self.base.is_cli_error(result):
            error_msg = result if result else "Command failed"
            ColorLogger.error(f"Failed to list apps: {error_msg}")
            return None

        if print_result:
            print("\n" + "="*80)
            print("Apps in DataPlane:")
            print("="*80)
            print(result)
            print("="*80 + "\n")
        ColorLogger.success("Apps listed successfully")
        return result

    def get_app_id(self, dp_name, capability_id, app_name=None):
        """
        Get app_id for a specific capability and optionally app name.

        Args:
            dp_name: Name of the dataplane
            capability_id: Capability type (BWCE, BW5CE, FLOGO)
            app_name: Optional app name to filter by

        Returns:
            app_id string if single match, list of app_ids if multiple, None if not found
        """
        ColorLogger.info(f"Looking for {capability_id} app(s) in DataPlane '{dp_name}'...")

        apps = self._get_apps_data(dp_name)

        if not apps:
            ColorLogger.warning("No apps found or command failed")
            return None

        # Filter by capability_id
        matching_apps = [app for app in apps if app.get('capability_id') == capability_id]

        # Further filter by app_name if provided
        if app_name:
            matching_apps = [app for app in matching_apps if app.get('app_name') == app_name]

        if not matching_apps:
            ColorLogger.warning(f"No {capability_id} app found with name '{app_name}'" if app_name else f"No {capability_id} app found")
            return None

        # Extract app_ids
        app_ids = [app.get('app_id') for app in matching_apps]

        if len(app_ids) == 1:
            ColorLogger.success(f"Found app_id: {app_ids[0]}")
            return app_ids[0]
        else:
            ColorLogger.info(f"Found {len(app_ids)} matching apps")
            return app_ids

    def delete_app(self, dp_name, capability_id, app_id, other_args=None):
        """
        Delete an app by capability_id and app_id.

        Args:
            dp_name: Name of the dataplane
            capability_id: Capability type (BWCE, BW5CE, FLOGO)
            app_id: App ID to delete
            other_args: Additional CLI arguments

        Returns:
            Command output
        """
        capability_lower = capability_id.lower()
        ColorLogger.info(f"Deleting {capability_id} app '{app_id}' from DataPlane '{dp_name}'...")
        command = (
            f'{self.base.TIBCOP_CLI_PATH} {capability_lower}:delete-app '
            f'--dataplane-name "{dp_name}" '
            f'--app-id "{app_id}" '
        )
        command += f'{other_args or ""}'
        result = self.base.run_command(command)

        if self.base.is_cli_error(result):
            error_msg = result if result else "Command failed"
            ColorLogger.error(f"Failed to delete {capability_id} app: {error_msg}")
            return None

        ColorLogger.success("App deleted successfully")
        print("\n" + "="*60)
        print("Updated app list:")
        print("="*60 + "\n")
        self.list_apps(dp_name, print_result=True)
        return result
