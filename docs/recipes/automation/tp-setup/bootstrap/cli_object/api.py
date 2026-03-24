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
CP REST API module.

Handles Control Plane REST API operations:
- Generic REST API calls
- Get capability versions
- Get apps, builds, and other resources
"""

import json
import os
import re
import time
import traceback
from utils.color_logger import ColorLogger
from utils.env import ENV
from utils.report import ReportYaml
from .base import TibcopBase


class TibcopAPI:
    """
    Control Plane REST API operations.

    Provides methods for calling CP REST API endpoints for BWCE, BW5CE, and FLOGO.
    """

    def __init__(self, base: TibcopBase, dataplane=None):
        """
        Initialize API handler.

        Args:
            base: TibcopBase instance for command execution
            dataplane: TibcopDataPlane instance for dataplane operations (optional)
        """
        self.base = base
        self.dataplane = dataplane

    def call_cp_rest_api(self, capability, dp_name, api_path, method='GET', data=None, headers=None):
        """
        Generic method to call CP REST API for any capability endpoint.

        This is a flexible method that can call any CP REST API endpoint for BWCE/BW5CE/FLOGO.

        Args:
            capability: Capability type (BWCE, BW5CE, FLOGO)
            dp_name: Name of the dataplane
            api_path: API path after /tibco/{capability_path}/{dataplane_id}/
                     Example: 'public/v1/cp/bwceversions'
                              'public/v1/apps'
                              'api/v1/builds'
            method: HTTP method (GET, POST, PUT, DELETE). Default: GET
            data: Request body for POST/PUT (dict). Will be JSON-encoded.
            headers: Additional HTTP headers (dict). Authorization header is auto-added.

        Returns:
            Response data (parsed JSON) or None if failed

        Example:
            # Get versions
            result = api.call_cp_rest_api('BWCE', 'dp1', 'public/v1/cp/bwceversions')

            # Get apps
            result = api.call_cp_rest_api('FLOGO', 'dp1', 'public/v1/apps')

            # Create build (POST with data)
            result = api.call_cp_rest_api('BWCE', 'dp1', 'api/v1/builds',
                                         method='POST', data={'version': '2.9.0'})
        """
        capability_upper = capability.upper()
        if capability_upper not in ['BWCE', 'BW5CE', 'FLOGO']:
            ColorLogger.error(f"Unsupported capability: {capability}. Must be BWCE, BW5CE, or FLOGO.")
            return None

        # Step 1: Get dataplane ID
        if self.dataplane:
            dataplane_id = self.dataplane.get_dataplane_id(dp_name)
        else:
            ColorLogger.error("DataPlane instance not available, cannot get dataplane ID")
            return None

        if not dataplane_id:
            return None

        # Step 2: Construct REST API URL
        # BWCE uses 'bw' instead of 'bwce' in path
        capability_path = "bw" if capability_upper == "BWCE" else capability_upper.lower()

        # Get FQDN from ENV based on capability
        fqdn_map = {
            'BWCE': ENV.TP_AUTO_FQDN_BWCE,
            'BW5CE': ENV.TP_AUTO_FQDN_BW5CE,
            'FLOGO': ENV.TP_AUTO_FQDN_FLOGO
        }
        base_url = f"https://{fqdn_map[capability_upper]}"

        # Remove leading slash from api_path if present
        api_path = api_path.lstrip('/')
        api_url = f"{base_url}/tibco/{capability_path}/{dataplane_id}/{api_path}"

        # Step 3: Get OAuth token
        token = None
        if self.base.CUSTOM_ENV and 'TIBCOP_CLI_OAUTH_TOKEN' in self.base.CUSTOM_ENV:
            token = self.base.CUSTOM_ENV['TIBCOP_CLI_OAUTH_TOKEN']
        else:
            token = os.environ.get('TIBCOP_CLI_OAUTH_TOKEN')

        if not token:
            ColorLogger.error("Failed to get CLI OAuth token (TIBCOP_CLI_OAUTH_TOKEN)")
            return None

        # Step 4: Build curl command
        # Build headers
        all_headers = {
            'accept': 'application/json',
            'Authorization': f'Bearer {token}'
        }
        if headers:
            all_headers.update(headers)

        # Build curl command (-k for self-signed certificates)
        insecure_flag = '-k ' if ENV.TP_IS_CERT_SELF_SIGNED else ''
        curl_cmd = f'curl -s {insecure_flag}-X {method} "{api_url}"'

        # Add Content-Type for POST/PUT before building header flags
        if data and method in ['POST', 'PUT']:
            all_headers['Content-Type'] = 'application/json'

        # Add headers
        for header_name, header_value in all_headers.items():
            curl_cmd += f' -H "{header_name}: {header_value}"'

        # Add data for POST/PUT
        if data and method in ['POST', 'PUT']:
            json_data = json.dumps(data)
            curl_cmd += f" -d '{json_data}'"

        # Step 5: Make REST API call
        try:
            # Only print curl output in debug mode
            api_result = self.base.run_command(curl_cmd, verbose=False)

            if api_result is None or not api_result.strip():
                ColorLogger.error("Failed to call CP REST API - empty response")
                return None

            # Step 6: Parse JSON response
            api_data = json.loads(api_result)

            return api_data

        except json.JSONDecodeError as e:
            ColorLogger.error(f"Failed to parse REST API JSON response: {e}")
            return None
        except Exception as e:
            ColorLogger.error(f"Error calling CP REST API: {e}")
            return None

    def get_connector_version_from_cp_api(self, dp_name, connector_id='General'):
        """
        Get connector version from CP REST API.

        Calls public/v1/cp/connectors on the FLOGO capability endpoint
        and returns the tag for the specified connector.

        Args:
            dp_name: Name of the dataplane
            connector_id: Connector ID to look up (default: 'General')

        Returns:
            Version string (tag) if found, None otherwise
        """
        ColorLogger.info(f"Getting connector '{connector_id}' version from CP REST API for DataPlane '{dp_name}'...")

        api_data = self.call_cp_rest_api('FLOGO', dp_name, 'public/v1/cp/connectors')

        if not api_data or not isinstance(api_data, list):
            ColorLogger.warning("Could not get connectors from CP API")
            return None

        for connector in api_data:
            if connector.get('id') == connector_id:
                tag = connector.get('tag')
                if tag:
                    ColorLogger.info(f"Available connector '{connector_id}' from CP REST API:")
                    print(json.dumps([{"id": connector_id, "version": tag}], indent=2))
                    ColorLogger.success(f"Selected connector '{connector_id}' version: {tag}")
                    return tag

        available_ids = [c.get('id') for c in api_data]
        ColorLogger.warning(f"Connector '{connector_id}' not found. Available: {available_ids}")
        return None

    def get_capability_version_from_cp_api(self, capability, dp_name, select_last=False,
                                            max_retries=6, retry_interval=10):
        """
        Get capability version from CP REST API (generic method for BWCE/BW5CE/FLOGO).

        Args:
            capability: Capability type (BWCE, BW5CE, FLOGO)
            dp_name: Name of the dataplane
            select_last: If True, select the last version from the list (default: False, selects first)
            max_retries: Maximum number of retries if API is not ready (default: 6)
            retry_interval: Seconds between retries (default: 10)

        Returns:
            version (string) or None if failed
        """
        import time
        capability_upper = capability.upper()
        ColorLogger.info(f"Getting {capability_upper} version from CP REST API for DataPlane '{dp_name}'...")

        # Construct API path based on capability
        # BWCE/BW5CE/FLOGO all use similar patterns: public/v1/cp/{capability}versions
        api_path = f"public/v1/cp/{capability_upper.lower()}versions"

        # Retry loop - capability API may not be ready immediately after provisioning
        api_data = None
        for attempt in range(1, max_retries + 1):
            api_data = self.call_cp_rest_api(capability, dp_name, api_path)
            if api_data is not None and isinstance(api_data, list) and len(api_data) > 0:
                break
            if attempt < max_retries:
                ColorLogger.info(f"{capability_upper} version API not ready, retrying ({attempt}/{max_retries})...")
                time.sleep(retry_interval)

        if api_data is None:
            return None

        # Parse the response to extract version
        # Expected format: [{"version": "2.9.0-V35", ...}, ...]
        try:
            if isinstance(api_data, list) and len(api_data) > 0:
                # Display all available versions
                versions = [item.get('version') for item in api_data if item.get('version')]
                if versions:
                    ColorLogger.info(f"Available {capability_upper} versions from CP REST API:")
                    print(json.dumps([{"version": v} for v in versions], indent=2))

                    # Select version based on select_last parameter
                    if select_last:
                        version = versions[-1]
                        ColorLogger.success(f"Selected last {capability_upper} version: {version}")
                    else:
                        version = versions[0]
                        ColorLogger.success(f"Selected first {capability_upper} version: {version}")
                    return version
                else:
                    ColorLogger.warning("No version found in API response")
                    return None
            else:
                ColorLogger.warning("API returned empty or invalid response")
                return None
        except Exception as e:
            ColorLogger.error(f"Error parsing version from response: {e}")
            return None

    def test_app_endpoint(self, dp_name, capability, app_name, endpoint_path, method='GET', data=None):
        """
        Test an app endpoint via REST API.

        Steps:
        1. GET /v1/dp/apps - find the app, get appId
        2. GET /v1/dp/apps/{appId}/instances - verify instances running
        3. POST /v1/dp/apps/{appId}/endpoints/public - make public
        4. curl the actual endpoint

        Args:
            dp_name: Name of the dataplane
            capability: Capability type (BWCE, BW5CE, FLOGO)
            app_name: Name of the app to test
            endpoint_path: Path to test (e.g. '/flogo')
            method: HTTP method (default: GET)
            data: Request body for POST/PUT (dict or None)

        Returns:
            True if endpoint test succeeded, False otherwise
        """
        ColorLogger.info(f"Testing {capability} app '{app_name}' endpoint '{endpoint_path}' via REST API...")

        try:
            # Step 1: List apps to find appId
            apps_data = self.call_cp_rest_api(capability, dp_name, 'public/v1/dp/apps')
            if not apps_data or not isinstance(apps_data, list):
                ColorLogger.warning(f"Could not list apps for {capability}, skipping endpoint test")
                return False

            app_id = None
            actual_app_name = app_name
            for app in apps_data:
                if app.get('name') == app_name or app.get('appName') == app_name:
                    app_id = app.get('id') or app.get('appId')
                    actual_app_name = app.get('name') or app.get('appName') or app_name
                    break

            # Fallback: if exact name not found, use the first app for this capability
            if not app_id and len(apps_data) > 0:
                first_app = apps_data[0]
                app_id = first_app.get('id') or first_app.get('appId')
                actual_app_name = first_app.get('name') or first_app.get('appName') or app_name
                ColorLogger.info(f"App '{app_name}' not found, using first available app '{actual_app_name}'")

            if not app_id:
                ColorLogger.warning(f"No apps found for {capability}, skipping endpoint test")
                return False

            # Step 2: Check instances are running
            instances_data = self.call_cp_rest_api(capability, dp_name, f'public/v1/dp/apps/{app_id}/instances')
            if not instances_data or (isinstance(instances_data, list) and len(instances_data) == 0):
                ColorLogger.warning(f"No running instances for app '{app_name}', skipping endpoint test")
                return False

            ColorLogger.info(f"App '{app_name}' has {len(instances_data) if isinstance(instances_data, list) else 'unknown'} instance(s)")

            # Step 3: Get endpoints info and make endpoint public
            ColorLogger.info(f"Making endpoint public for app '{app_name}'...")

            fqdn_map = {
                'BWCE': ENV.TP_AUTO_FQDN_BWCE,
                'BW5CE': ENV.TP_AUTO_FQDN_BW5CE,
                'FLOGO': ENV.TP_AUTO_FQDN_FLOGO
            }
            fqdn = fqdn_map.get(capability.upper())
            if not fqdn:
                ColorLogger.warning(f"No FQDN configured for {capability}")
                return False

            # 3a: GET endpoints to discover port info and public status
            endpoints_data = self.call_cp_rest_api(
                capability, dp_name, f'public/v1/dp/apps/{app_id}/endpoints'
            )

            # Parse endpoints response: {endpointsInfo: [{targetSvcPort, pathPrefix, ...}], isPublicEndpointenabled}
            is_already_public = False
            public_endpoint_url = None
            port_mappings = []
            if endpoints_data and isinstance(endpoints_data, dict):
                is_already_public = endpoints_data.get('isPublicEndpointenabled', False)
                for ep in endpoints_data.get('endpointsInfo', []):
                    port = ep.get('targetSvcPort') or ep.get('port')
                    service_path = ep.get('pathPrefix') or '/'
                    if port:
                        port_mappings.append({
                            'port': port,
                            'servicePath': service_path,
                            'isPublic': True
                        })
                    # Capture publicEndpoint URL if already public
                    if ep.get('publicEndpoint'):
                        public_endpoint_url = ep.get('publicEndpoint')

            if not port_mappings:
                ColorLogger.info(f"No endpoint port info found, using default port 9999")
                port_mappings = [{'port': 9999, 'servicePath': '/', 'isPublic': True}]

            # 3b: Make endpoint public (skip if already public)
            if is_already_public:
                ColorLogger.success(f"Endpoint already public for app '{app_name}'")
                ReportYaml.set_capability_app_info(dp_name, capability.lower(), app_name, "endpointPublic", True)
            else:
                make_public_payload = {
                    'ingressClassName': ENV.TP_AUTO_INGRESS_CONTROLLER_CLASS_NAME,
                    'ingressControllerName': ENV.TP_AUTO_INGRESS_CONTROLLER,
                    'ingressHostName': fqdn,
                    'portServicePathMappings': port_mappings
                }
                ColorLogger.info(f"Make-public payload: {json.dumps(make_public_payload, indent=2)}")
                public_result = self.call_cp_rest_api(
                    capability, dp_name, f'public/v1/dp/apps/{app_id}/endpoints/public',
                    method='POST', data=make_public_payload
                )
                if public_result is not None:
                    message = public_result.get('message', '') if isinstance(public_result, dict) else str(public_result)
                    ColorLogger.success(f"Made endpoint public for app '{app_name}': {message}")
                    ReportYaml.set_capability_app_info(dp_name, capability.lower(), app_name, "endpointPublic", True)
                else:
                    ColorLogger.warning(f"Make endpoint public API returned no data for '{app_name}', continuing anyway...")

            # Step 4: Call the app endpoint directly (with retry)
            # Public endpoint URL: https://{fqdn}{endpoint_path}
            if public_endpoint_url:
                endpoint_url = public_endpoint_url.rstrip('/') + endpoint_path
            else:
                endpoint_url = f"https://{fqdn}{endpoint_path}"
            ColorLogger.info(f"Testing endpoint URL: {endpoint_url}")

            # Get token for auth
            token = self.base.CUSTOM_ENV.get('TIBCOP_CLI_OAUTH_TOKEN') or os.environ.get('TIBCOP_CLI_OAUTH_TOKEN')

            insecure_flag = '-k ' if ENV.TP_IS_CERT_SELF_SIGNED else ''
            curl_cmd = f'curl -s {insecure_flag}-o /dev/stdout -w "\\n%{{http_code}}" -X {method} "{endpoint_url}" -H "Authorization: Bearer {token}" -H "accept: application/json"'
            if data is not None and method in ['POST', 'PUT']:
                json_data = json.dumps(data)
                curl_cmd += f" -H \"Content-Type: application/json\" -d '{json_data}'"

            # Retry endpoint test (app may need time after becoming public)
            max_retries = 3
            retry_interval = 10
            for attempt in range(1, max_retries + 1):
                result = self.base.run_command(curl_cmd)
                if not result:
                    ColorLogger.warning(f"Endpoint test for '{app_name}' returned empty response")
                    if attempt < max_retries:
                        ColorLogger.info(f"Retrying in {retry_interval}s... (attempt {attempt}/{max_retries})")
                        time.sleep(retry_interval)
                        continue
                    return False

                # Parse HTTP status code from last line (curl -w appends it)
                # Format: body + \n + http_code, but body may be empty (e.g. 302 redirect)
                lines = result.strip().rsplit('\n', 1)
                if len(lines) > 1:
                    body = lines[0]
                    http_code = lines[-1].strip()
                else:
                    # Single line: could be just the http_code when body is empty
                    token = lines[0].strip()
                    if re.match(r'^\d{3}$', token):
                        http_code = token
                        body = ''
                    else:
                        http_code = ''
                        body = token

                if http_code.startswith('2'):
                    ColorLogger.success(f"Endpoint test for '{app_name}' {method} {endpoint_path}: HTTP {http_code} OK")
                    ColorLogger.success(f"Public endpoint reachable: {endpoint_url}")
                    ReportYaml.set_capability_app_info(dp_name, capability.lower(), app_name, "testedEndpoint", True)
                    return True
                else:
                    ColorLogger.warning(f"Endpoint test for '{app_name}' {method} {endpoint_path}: HTTP {http_code} FAILED")
                    ColorLogger.warning(f"Response body: {body[:200]}")
                    if attempt < max_retries:
                        ColorLogger.info(f"Retrying in {retry_interval}s... (attempt {attempt}/{max_retries})")
                        time.sleep(retry_interval)
                    else:
                        return False

            return False

        except Exception as e:
            ColorLogger.warning(f"Endpoint test failed for '{app_name}': {e}")
            traceback.print_exc()
            return False
