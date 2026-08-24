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
from page_object.po_dataplane import PageObjectDataPlane
from page_object.po_bmdp_config import PageObjectBMDPConfiguration

if __name__ == "__main__":
    page = Util.browser_launch()
    try:
        po_auth = PageObjectAuth(page)
        po_auth.login()
        po_auth.login_check()

        po_user_management = PageObjectUserManagement(page)
        po_user_management.set_user_permission()

        po_dp = PageObjectDataPlane(page)
        po_dp.goto_left_navbar_dataplane()
        po_dp.k8s_create_bmdp(ENV.TP_AUTO_K8S_BMDP_NAME)

        # A fresh BMDP renders its BW5/BW6 product cards disabled until the user holds the product
        # grant, so grant it here as the CLI/API path does, after the base policies are in place.
        po_bmdp_config = PageObjectBMDPConfiguration(page)
        po_bmdp_config.ensure_bmdp_product_permissions(ENV.TP_AUTO_K8S_BMDP_NAME)

        po_auth.logout()
    except Exception as e:
        current_filename = Path(__file__).stem
        Util.exit_error(f"Unhandled error: {e}", page, f"unhandled_error_{current_filename}.png")
    Util.browser_close()

    Util.set_cp_env()
    Util.print_env_info(False)
