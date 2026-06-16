#
# Copyright 2025 Cloud Software Group, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""App-endpoint test workflow: list apps → check instances → make public → curl."""

import json
import os
import re
import time
import traceback

from api_object.call_cp_rest_api import CpRestApi
from utils.color_logger import ColorLogger
from utils.env import ENV
from utils.report import ReportYaml


class AppEndpointApi:
    """Make an app endpoint public and verify reachability."""

    def __init__(self, rest: CpRestApi):
        self.rest = rest

    def test_app_endpoint(self, dp_name, capability, app_name, endpoint_path, method='GET', data=None):
        """Test an app endpoint via REST API.

        Steps:
        1. GET /v1/dp/apps - find the app, get appId
        2. GET /v1/dp/apps/{appId}/instances - verify instances running
        3. POST /v1/dp/apps/{appId}/endpoints/public - make public
        4. curl the actual endpoint
        """
        ColorLogger.info(f"Testing {capability} app '{app_name}' endpoint '{endpoint_path}' via REST API...")

        try:
            apps_data = self.rest.call_cp_rest_api(capability, dp_name, 'public/v1/dp/apps')
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

            if not app_id and len(apps_data) > 0:
                first_app = apps_data[0]
                app_id = first_app.get('id') or first_app.get('appId')
                actual_app_name = first_app.get('name') or first_app.get('appName') or app_name
                ColorLogger.info(f"App '{app_name}' not found, using first available app '{actual_app_name}'")

            if not app_id:
                ColorLogger.warning(f"No apps found for {capability}, skipping endpoint test")
                return False

            instances_data = self.rest.call_cp_rest_api(capability, dp_name, f'public/v1/dp/apps/{app_id}/instances')
            if not instances_data or (isinstance(instances_data, list) and len(instances_data) == 0):
                ColorLogger.warning(f"No running instances for app '{app_name}', skipping endpoint test")
                return False

            ColorLogger.info(f"App '{app_name}' has {len(instances_data) if isinstance(instances_data, list) else 'unknown'} instance(s)")

            ColorLogger.info(f"Making endpoint public for app '{app_name}'...")

            fqdn_map = {
                'BWCE': ENV.TP_AUTO_FQDN_BWCE,
                'BW5CE': ENV.TP_AUTO_FQDN_BW5CE,
                'FLOGO': ENV.TP_AUTO_FQDN_FLOGO,
            }
            fqdn = fqdn_map.get(capability.upper())
            if not fqdn:
                ColorLogger.warning(f"No FQDN configured for {capability}")
                return False

            endpoints_data = self.rest.call_cp_rest_api(
                capability, dp_name, f'public/v1/dp/apps/{app_id}/endpoints'
            )

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
                            'isPublic': True,
                        })
                    if ep.get('publicEndpoint'):
                        public_endpoint_url = ep.get('publicEndpoint')

            if not port_mappings:
                ColorLogger.info(f"No endpoint port info found, using default port 9999")
                port_mappings = [{'port': 9999, 'servicePath': '/', 'isPublic': True}]

            if is_already_public:
                ColorLogger.success(f"Endpoint already public for app '{app_name}'")
                ReportYaml.set_capability_app_info(dp_name, capability.lower(), app_name, "endpointPublic", True)
            else:
                if ENV.TP_AUTO_INGRESS_OBJECT == "gateway":
                    make_public_payload = {
                        'gatewayControllerName': ENV.TP_AUTO_GATEWAY_CONTROLLER,
                        'gatewayName': ENV.TP_AUTO_GATEWAY_NAME,
                        'gatewayNamespace': ENV.TP_AUTO_GATEWAY_NAMESPACE,
                        'gatewayHostName': fqdn,
                        'portServicePathMappings': port_mappings,
                    }
                    if ENV.TP_AUTO_GATEWAY_SECTION_NAME:
                        make_public_payload['gatewaySectionName'] = ENV.TP_AUTO_GATEWAY_SECTION_NAME
                else:
                    make_public_payload = {
                        'ingressClassName': ENV.TP_AUTO_INGRESS_CONTROLLER_CLASS_NAME,
                        'ingressControllerName': ENV.TP_AUTO_INGRESS_CONTROLLER,
                        'ingressHostName': fqdn,
                        'portServicePathMappings': port_mappings,
                    }
                ColorLogger.info(f"Make-public payload: {json.dumps(make_public_payload, indent=2)}")
                public_result = self.rest.call_cp_rest_api(
                    capability, dp_name, f'public/v1/dp/apps/{app_id}/endpoints/public',
                    method='POST', data=make_public_payload
                )
                if public_result is not None:
                    message = public_result.get('message', '') if isinstance(public_result, dict) else str(public_result)
                    ColorLogger.success(f"Made endpoint public for app '{app_name}': {message}")
                    ReportYaml.set_capability_app_info(dp_name, capability.lower(), app_name, "endpointPublic", True)
                else:
                    ColorLogger.warning(f"Make endpoint public API returned no data for '{app_name}', continuing anyway...")

            if public_endpoint_url:
                endpoint_url = public_endpoint_url.rstrip('/') + endpoint_path
            else:
                endpoint_url = f"https://{fqdn}{endpoint_path}"
            ColorLogger.info(f"Testing endpoint URL: {endpoint_url}")

            token = self.rest.base.CUSTOM_ENV.get('TIBCOP_CLI_OAUTH_TOKEN') or os.environ.get('TIBCOP_CLI_OAUTH_TOKEN')

            insecure_flag = '-k ' if ENV.TP_IS_CERT_SELF_SIGNED else ''
            curl_cmd = f'curl -s {insecure_flag}-o /dev/stdout -w "\\n%{{http_code}}" -X {method} "{endpoint_url}" -H "Authorization: Bearer {token}" -H "accept: application/json"'
            if data is not None and method in ['POST', 'PUT']:
                json_data = json.dumps(data)
                curl_cmd += f" -H \"Content-Type: application/json\" -d '{json_data}'"

            max_retries = 3
            retry_interval = 10
            for attempt in range(1, max_retries + 1):
                result = self.rest.base.run_command(curl_cmd)
                if not result:
                    ColorLogger.warning(f"Endpoint test for '{app_name}' returned empty response")
                    if attempt < max_retries:
                        ColorLogger.info(f"Retrying in {retry_interval}s... (attempt {attempt}/{max_retries})")
                        time.sleep(retry_interval)
                        continue
                    return False

                lines = result.strip().rsplit('\n', 1)
                if len(lines) > 1:
                    body = lines[0]
                    http_code = lines[-1].strip()
                else:
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
