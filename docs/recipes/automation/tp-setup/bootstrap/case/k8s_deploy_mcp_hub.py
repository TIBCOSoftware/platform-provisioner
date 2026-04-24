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

from pathlib import Path
from utils.util import Util
from utils.env import ENV
from utils.color_logger import ColorLogger
from utils.helper import Helper
from page_object.po_auth import PageObjectAuth
from page_object.po_mcp_hub import PageObjectMcpHub

CP_MCP_SERVER_NAME = "cp-mcp-server"


def get_cp_mcp_url():
    """Build CP MCP server URL from environment."""
    host_prefix = ENV.DP_HOST_PREFIX
    dns_domain = ENV.TP_AUTO_CP_SERVICE_DNS_DOMAIN
    return f"https://{host_prefix}.{dns_domain}/cp/mcp"


if __name__ == "__main__":
    if not ENV.TP_AI_ENABLE_MCP_HUB:
        ColorLogger.warning("TP_AI_ENABLE_MCP_HUB is not set, skipping MCP Hub deployment")
        exit(0)

    dp_name = ENV.TP_AUTO_K8S_DP_NAME
    cp_mcp_url = get_cp_mcp_url()
    token = Helper.get_auto_token()

    if not token:
        ColorLogger.warning("OAuth token is empty (kubectl may not be connected). MCP Server auth will not be configured.")

    ColorLogger.info(f"Starting MCP Hub deployment for DP '{dp_name}'...")
    ColorLogger.info(f"CP MCP URL: {cp_mcp_url}")

    page = Util.browser_launch()
    try:
        # Login
        po_auth = PageObjectAuth(page)
        po_auth.login()
        po_auth.login_check()

        # MCP Hub flow
        po_mcp = PageObjectMcpHub(page)
        po_mcp.goto_mcp_hub()
        po_mcp.goto_dataplane(dp_name)

        # Deploy MCP Gateway (skip if already deployed)
        po_mcp.deploy_mcp_gateway(dp_name)

        # Add CP MCP Server (skip if already exists)
        po_mcp.add_mcp_server(
            name=CP_MCP_SERVER_NAME,
            url=cp_mcp_url,
            token=token,
            auth_type="Bearer Token",
        )

        # Push to Gateway and verify
        po_mcp.push_to_gateway()
        tools_count = po_mcp.verify_tools()

        ColorLogger.success(f"MCP Hub deployment complete! {tools_count} tools discovered.")

        po_auth.logout()
    except Exception as e:
        current_filename = Path(__file__).stem
        Util.exit_error(f"Unhandled error: {e}", page, f"unhandled_error_{current_filename}.png")
    Util.browser_close()
