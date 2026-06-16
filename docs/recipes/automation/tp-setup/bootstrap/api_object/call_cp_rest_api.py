#
# Copyright 2025 Cloud Software Group, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Low-level REST caller for capability FQDN endpoints (BWCE/BW5CE/FLOGO)."""

import json
import os
from typing import TYPE_CHECKING

from utils.color_logger import ColorLogger
from utils.env import ENV

if TYPE_CHECKING:
    from cli_object.base import TibcopBase


class CpRestApi:
    """Generic curl-based REST client for `/tibco/{capability}/{dataplaneId}/...` paths."""

    def __init__(self, base: "TibcopBase", dataplane=None):
        self.base = base
        self.dataplane = dataplane

    def call_cp_rest_api(self, capability, dp_name, api_path, method='GET', data=None, headers=None):
        """Generic method to call CP REST API for any capability endpoint.

        Args:
            capability: BWCE, BW5CE, or FLOGO
            dp_name: DataPlane name (resolved to dataplane id via TibcopDataPlane)
            api_path: Path under `/tibco/{capability_path}/{dataplaneId}/`
            method: HTTP method (default GET)
            data: dict for POST/PUT body (JSON-encoded)
            headers: extra headers (Authorization auto-added)

        Returns:
            Parsed JSON response, or None on failure.
        """
        capability_upper = capability.upper()
        if capability_upper not in ['BWCE', 'BW5CE', 'FLOGO']:
            ColorLogger.error(f"Unsupported capability: {capability}. Must be BWCE, BW5CE, or FLOGO.")
            return None

        if self.dataplane:
            dataplane_id = self.dataplane.get_dataplane_id(dp_name)
        else:
            ColorLogger.error("DataPlane instance not available, cannot get dataplane ID")
            return None

        if not dataplane_id:
            return None

        # BWCE uses 'bw' instead of 'bwce' in path
        capability_path = "bw" if capability_upper == "BWCE" else capability_upper.lower()

        fqdn_map = {
            'BWCE': ENV.TP_AUTO_FQDN_BWCE,
            'BW5CE': ENV.TP_AUTO_FQDN_BW5CE,
            'FLOGO': ENV.TP_AUTO_FQDN_FLOGO,
        }
        base_url = f"https://{fqdn_map[capability_upper]}"
        api_path = api_path.lstrip('/')
        api_url = f"{base_url}/tibco/{capability_path}/{dataplane_id}/{api_path}"

        token = None
        if self.base.CUSTOM_ENV and 'TIBCOP_CLI_OAUTH_TOKEN' in self.base.CUSTOM_ENV:
            token = self.base.CUSTOM_ENV['TIBCOP_CLI_OAUTH_TOKEN']
        else:
            token = os.environ.get('TIBCOP_CLI_OAUTH_TOKEN')

        if not token:
            ColorLogger.error("Failed to get CLI OAuth token (TIBCOP_CLI_OAUTH_TOKEN)")
            return None

        all_headers = {
            'accept': 'application/json',
            'Authorization': f'Bearer {token}',
        }
        if headers:
            all_headers.update(headers)

        insecure_flag = '-k ' if ENV.TP_IS_CERT_SELF_SIGNED else ''
        curl_cmd = f'curl -s {insecure_flag}-X {method} "{api_url}"'

        if data and method in ['POST', 'PUT']:
            all_headers['Content-Type'] = 'application/json'

        for header_name, header_value in all_headers.items():
            curl_cmd += f' -H "{header_name}: {header_value}"'

        if data and method in ['POST', 'PUT']:
            json_data = json.dumps(data)
            curl_cmd += f" -d '{json_data}'"

        try:
            api_result = self.base.run_command(curl_cmd, verbose=False)
            if api_result is None or not api_result.strip():
                ColorLogger.error("Failed to call CP REST API - empty response")
                return None
            return json.loads(api_result)
        except json.JSONDecodeError as e:
            ColorLogger.error(f"Failed to parse REST API JSON response: {e}")
            return None
        except Exception as e:
            ColorLogger.error(f"Error calling CP REST API: {e}")
            return None
