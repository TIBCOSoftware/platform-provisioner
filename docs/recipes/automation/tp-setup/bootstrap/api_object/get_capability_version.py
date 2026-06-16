#
# Copyright 2025 Cloud Software Group, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Capability/connector version lookup via CP REST API."""

import json
import time

from api_object.call_cp_rest_api import CpRestApi
from utils.color_logger import ColorLogger


class CapabilityVersionApi:
    """Fetch BWCE/BW5CE/FLOGO versions and Flogo connector versions."""

    def __init__(self, rest: CpRestApi):
        self.rest = rest

    def get_connector_version(self, dp_name, connector_id='General'):
        """Look up a Flogo connector's tag via `public/v1/cp/connectors`."""
        ColorLogger.info(f"Getting connector '{connector_id}' version from CP REST API for DataPlane '{dp_name}'...")

        api_data = self.rest.call_cp_rest_api('FLOGO', dp_name, 'public/v1/cp/connectors')
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

    def get_capability_version(self, capability, dp_name, select_last=False,
                                max_retries=6, retry_interval=10):
        """Get a capability version from `public/v1/cp/{capability}versions` with retry.

        Args:
            capability: BWCE, BW5CE, or FLOGO
            dp_name: DataPlane name
            select_last: choose the last version in the list (default: first)
            max_retries / retry_interval: capability API may not be ready right after provisioning
        """
        capability_upper = capability.upper()
        ColorLogger.info(f"Getting {capability_upper} version from CP REST API for DataPlane '{dp_name}'...")

        api_path = f"public/v1/cp/{capability_upper.lower()}versions"

        api_data = None
        for attempt in range(1, max_retries + 1):
            api_data = self.rest.call_cp_rest_api(capability, dp_name, api_path)
            if api_data is not None and isinstance(api_data, list) and len(api_data) > 0:
                break
            if attempt < max_retries:
                ColorLogger.info(f"{capability_upper} version API not ready, retrying ({attempt}/{max_retries})...")
                time.sleep(retry_interval)

        if api_data is None:
            return None

        try:
            if isinstance(api_data, list) and len(api_data) > 0:
                versions = [item.get('version') for item in api_data if item.get('version')]
                if versions:
                    ColorLogger.info(f"Available {capability_upper} versions from CP REST API:")
                    print(json.dumps([{"version": v} for v in versions], indent=2))

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
