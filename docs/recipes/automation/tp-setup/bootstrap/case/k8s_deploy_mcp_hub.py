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

# MCP servers to install from the registry (short keys; mapped to registry
# display names in PageObjectMcpHub.MCP_SERVER_CATALOG).
MCP_SERVERS_TO_INSTALL = [
    "cp-mcp-server",
    "o11y-mcp-server",
    "flogo-mcp-server",
    "bw-mcp-server",
]


if __name__ == "__main__":
    if not ENV.TP_AI_ENABLE_MCP_HUB:
        ColorLogger.warning("TP_AI_ENABLE_MCP_HUB is not set, skipping MCP Hub deployment")
        exit(0)

    dp_name = ENV.TP_AUTO_K8S_DP_NAME
    token = Helper.get_auto_token()

    if not token:
        ColorLogger.warning("OAuth token is empty (kubectl may not be connected). MCP Server auth will not be configured.")

    ColorLogger.info(f"Starting MCP Hub deployment for DP '{dp_name}'...")

    page = Util.browser_launch()
    try:
        po_auth = PageObjectAuth(page)
        po_auth.login()
        po_auth.login_check()

        # Gateway-centric React UI (PCP-19623): Register Gateway ->
        # "Deploy to a TIBCO Data Plane" (auto-provision), install servers from the
        # registry (DP pre-selected), push to the gateway, then verify tools.
        po_mcp = PageObjectMcpHub(page)
        po_mcp.goto_mcp_hub()

        gateway_id = po_mcp.deploy_mcp_gateway(dp_name, skip_online_wait=True)

        # Wait until the gateway is deployed (deterministic Hub API mcpgatewayDeployed
        # + detail view operable) so the servers tab renders before installing servers.
        # Pass dp_name so an empty/unresolved gateway_id can still resolve by name.
        # PCP-19765: the deploy POST returns a PLACEHOLDER gateway id the backend re-keys
        # (supersedes) after async provision; wait_for_gateway_deployed re-resolves the
        # CURRENT id and returns it, so reassign gateway_id here to stop propagating the
        # stale placeholder to add_mcp_server / push_to_gateway / verify_tools.
        gateway_id = po_mcp.wait_for_gateway_deployed(gateway_id, dp_name=dp_name) or gateway_id

        for server_name in MCP_SERVERS_TO_INSTALL:
            po_mcp.add_mcp_server(name=server_name, token=token, gateway_id=gateway_id)

        # min_tools=1 = "the gateway discovered at least something" (the alpha.49 guard).
        # push_to_gateway owns the hard gate via /sync/refresh; verify_tools is confirmatory.
        # dp_name lets push recover a late supersede of the gateway id (PCP-19765).
        po_mcp.push_to_gateway(gateway_id=gateway_id, min_tools=1, dp_name=dp_name)
        tools_count = po_mcp.verify_tools(gateway_id=gateway_id, min_tools=1)
        ColorLogger.success(f"MCP Hub deployment complete! {tools_count} tools discovered.")

        po_auth.logout()
    except Exception as e:
        current_filename = Path(__file__).stem
        Util.exit_error(f"Unhandled error: {e}", page, f"unhandled_error_{current_filename}.png")
    Util.browser_close()
