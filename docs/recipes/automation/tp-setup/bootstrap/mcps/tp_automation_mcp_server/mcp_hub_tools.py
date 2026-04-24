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
    """Deploy MCP Hub

    This tool deploys the TIBCO MCP Hub to the Control Plane namespace.
    MCP Hub provides a centralized management interface for MCP (Model Context Protocol)
    servers and recipes within the TIBCO Platform.

    The tool automates the following process:
    1. Extracts configuration from the existing CP installation (helm get values)
    2. Builds the MCP Hub chart values (container registry, DNS domain, etc.)
    3. Adds the TIBCO Platform helm repo
    4. Runs helm upgrade --install for tibco-cp-mcp-hub chart

    Args:
        dp_name: Name of the Data Plane (used for context, MCP Hub deploys to CP namespace).
        chart_version: Specific chart version to deploy (optional, defaults to latest).

    Returns:
        Result of the MCP Hub deployment process

    Examples:
        deploy_mcp_hub()
        deploy_mcp_hub(chart_version="~1.17.0-0")

    Note:
        Requires an existing CP installation with platform-base deployed.
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
