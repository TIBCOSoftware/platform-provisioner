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
from page_object.po_auth import PageObjectAuth
from page_object.po_dataplane import PageObjectDataPlane
from page_object.po_dp_config import PageObjectDataPlaneConfiguration
from page_object.po_dp_k8s_mcp_server import PageObjectDataPlaneK8sMcpServer

if __name__ == "__main__":
    if not ENV.TP_AUTO_IS_PROVISION_K8S_MCP_SERVER:
        ColorLogger.warning("TP_AUTO_IS_PROVISION_K8S_MCP_SERVER is not set, skipping")
        exit(0)

    page = Util.browser_launch()
    try:
        po_auth = PageObjectAuth(page)
        po_auth.login()

        po_dp = PageObjectDataPlane(page)
        po_dp_config = PageObjectDataPlaneConfiguration(page)
        po_dp.goto_dataplane(ENV.TP_AUTO_K8S_DP_NAME)
        po_dp_config.goto_dataplane_config()
        po_dp_config.dp_config_resources_ingress(
            ENV.TP_AUTO_K8S_DP_NAME,
            ENV.TP_AUTO_INGRESS_CONTROLLER, ENV.TP_AUTO_INGRESS_CONTROLLER_K8S_MCP_SERVER,
            ENV.TP_AUTO_INGRESS_CONTROLLER_CLASS_NAME, ENV.TP_AUTO_FQDN_K8S_MCP_SERVER
        )

        po_k8s_mcp = PageObjectDataPlaneK8sMcpServer(page)
        po_k8s_mcp.goto_left_navbar_dataplane()
        po_k8s_mcp.goto_dataplane(ENV.TP_AUTO_K8S_DP_NAME)
        po_k8s_mcp.k8s_mcp_server_provision_capability(ENV.TP_AUTO_K8S_DP_NAME)

        po_auth.logout()
    except Exception as e:
        current_filename = Path(__file__).stem
        Util.exit_error(f"Unhandled error: {e}", page, f"unhandled_error_{current_filename}.png")
    Util.browser_close()

    Util.set_cp_env()
    Util.print_env_info(False)
