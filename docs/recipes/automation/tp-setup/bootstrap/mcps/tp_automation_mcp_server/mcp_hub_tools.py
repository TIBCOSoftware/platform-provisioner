#!/usr/bin/env python3

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

import logging
from typing import Dict, Any

from .automation_executor import run_automation_task, execute_module
from .config import DEFAULT_VALUES

logger = logging.getLogger('tibco-platform-provisioner-mcp-hub')

async def deploy_mcp_hub(dp_name: str = "", chart_version: str = "") -> str:
    """Deploy the MCP Gateway and install MCP servers via the MCP Hub UI.

    This tool runs the browser automation case ``case.k8s_deploy_mcp_hub`` against
    the gateway-centric MCP Hub React UI (PCP-19623). It assumes the MCP Hub chart
    is already installed on the Control Plane (in CP mode, ``MCP_HUB_MODE=cp``).

    The automation drives the UI end-to-end:
    1. Register Gateway -> "Deploy to a TIBCO Data Plane" (auto-provision) onto the
       target Data Plane (POST /api/mcp-hub/gateways/{dpUuid}/deploy)
    2. Installs the catalog MCP servers from the registry (DP pre-selected)
    3. Pushes the configuration to the gateway (Preview Changes -> Push)
    4. Verifies the discovered tools per server (Tools details drawer)

    Args:
        dp_name: Target Data Plane name to deploy the gateway onto
            (maps to TP_AUTO_K8S_DP_NAME).
        chart_version: MCP Hub chart version override (maps to
            CP_PLATFORM_MCP_HUB_VERSION); optional, defaults to the installed version.

    Returns:
        Result of the MCP Hub deployment automation run.

    Examples:
        deploy_mcp_hub()
        deploy_mcp_hub(dp_name="k8s-auto-dp1", chart_version="1.17.0-gateway-centric.4")

    Note:
        Requires an existing CP-mode MCP Hub install and a managed (cp_dp) Data
        Plane to deploy the gateway onto.
    """
    params: Dict[str, Any] = {
        "TP_AI_ENABLE_MCP_HUB": True,
        "HEADLESS": True,
    }

    if dp_name:
        params["TP_AUTO_K8S_DP_NAME"] = dp_name

    if chart_version:
        params["CP_PLATFORM_MCP_HUB_VERSION"] = chart_version

    logger.info("Deploying MCP Hub")

    try:
        return await run_automation_task("case.k8s_deploy_mcp_hub", params)
    except Exception as e:
        logger.error("Failed to run through API, trying direct module execution: %s", e)
        return await execute_module("case.k8s_deploy_mcp_hub", params)
