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
from page_object.po_user_management import PageObjectUserManagement
from page_object.po_auth import PageObjectAuth
from page_object.po_dp_config import PageObjectDataPlaneConfiguration

if __name__ == "__main__":
    page = Util.browser_launch()
    try:
        po_auth = PageObjectAuth(page)
        po_auth.login()
        po_auth.login_check()

        po_user_management = PageObjectUserManagement(page)
        po_user_management.set_user_permission()

        po_dp_config = PageObjectDataPlaneConfiguration(page)
        # PCP-23553: a data plane always SWITCHES to the Global observability resource.
        # Never o11y_config_dataplane_resource() here - that creates a second, DP-local
        # resource set. o11y_config_switch_to_global() self-navigates to the DP's
        # Observability config.
        po_dp_config.o11y_config_switch_to_global(ENV.TP_AUTO_K8S_DP_NAME)
        po_dp_config.o11y_config_activation(ENV.TP_AUTO_K8S_DP_NAME)

        po_auth.logout()
    except Exception as e:
        current_filename = Path(__file__).stem
        Util.exit_error(f"Unhandled error: {e}", page, f"unhandled_error_{current_filename}.png")
    Util.browser_close()

    Util.set_cp_env()
    Util.print_env_info(False)
