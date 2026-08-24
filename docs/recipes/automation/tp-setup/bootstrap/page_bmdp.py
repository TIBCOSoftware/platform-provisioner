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
    ENV.pre_check()

    page = Util.browser_launch()
    try:
        po_auth = PageObjectAuth(page)
        po_dp = PageObjectDataPlane(page)
        po_bmdp_config = PageObjectBMDPConfiguration(page)

        po_auth.login()
        po_auth.login_check()

        po_user_management = PageObjectUserManagement(page)
        po_user_management.set_user_permission()

        # config global dataplane
        po_bmdp_config.o11y_config_dataplane_resource(ENV.TP_AUTO_DP_NAME_GLOBAL)

        if ENV.TP_AUTO_IS_CREATE_BMDP:
            # for create dataplane and config dataplane resources
            po_dp.goto_left_navbar_dataplane()
            # po_dp.k8s_delete_dataplane(ENV.TP_AUTO_K8S_BMDP_NAME)
            po_dp.k8s_create_bmdp(ENV.TP_AUTO_K8S_BMDP_NAME)

            # Grant Product Permission up front, the same way the CLI/API path does it: on a fresh
            # BMDP the CP renders the BW5/BW6 product cards disabled until the user holds the
            # product grant, and the reactive recovery in goto_products() only triggers once we are
            # already deep in the capability flow. Must stay after set_user_permission() above - the
            # base policies it creates are a prerequisite of any product grant.
            po_bmdp_config.ensure_bmdp_product_permissions(ENV.TP_AUTO_K8S_BMDP_NAME)

            # BW5 RVDM config
            if ENV.TP_AUTO_IS_ENABLE_RVDM and not po_bmdp_config.is_app_running("BW5", ENV.TP_AUTO_K8S_BMDP_BW5_RVDM, ENV.TP_AUTO_BW5_APP_NAME):
                po_dp.goto_dataplane(ENV.TP_AUTO_K8S_BMDP_NAME)
                po_bmdp_config.goto_dataplane_config()
                if po_bmdp_config.dp_config_bw5_rvdm(ENV.TP_AUTO_K8S_BMDP_BW5_RVDM):
                    po_dp.goto_dataplane(ENV.TP_AUTO_K8S_BMDP_NAME)
                    if po_bmdp_config.goto_products("BW5"):
                        po_bmdp_config.check_bmdp_app_status_by_app_name("BW5", ENV.TP_AUTO_K8S_BMDP_BW5_RVDM, ENV.TP_AUTO_BW5_APP_NAME)

            # EMS Server config
            if ENV.TP_AUTO_IS_ENABLE_EMSDM and not po_bmdp_config.is_ems_server_connected(ENV.TP_BMDP_IMAGE_TAG_EMS):
                po_dp.goto_dataplane(ENV.TP_AUTO_K8S_BMDP_NAME)
                po_bmdp_config.goto_dataplane_config()
                po_bmdp_config.dp_config_ems(ENV.TP_BMDP_IMAGE_TAG_EMS)

            # BW5 EMSDM config
            if ENV.TP_AUTO_IS_ENABLE_EMSDM and not po_bmdp_config.is_app_running("BW5", ENV.TP_AUTO_K8S_BMDP_BW5_EMSDM, ENV.TP_AUTO_BW5_APP_NAME):
                po_dp.goto_dataplane(ENV.TP_AUTO_K8S_BMDP_NAME)
                po_bmdp_config.goto_dataplane_config()
                if po_bmdp_config.dp_config_bw5_emsdm(ENV.TP_AUTO_K8S_BMDP_BW5_EMSDM):
                    po_dp.goto_dataplane(ENV.TP_AUTO_K8S_BMDP_NAME)
                    if po_bmdp_config.goto_products("BW5"):
                        po_bmdp_config.check_bmdp_app_status_by_app_name("BW5", ENV.TP_AUTO_K8S_BMDP_BW5_EMSDM, ENV.TP_AUTO_BW5_APP_NAME)

            # BW6 Domain config
            if ENV.TP_AUTO_IS_ENABLE_BW6DM and not po_bmdp_config.is_app_running("BW6", ENV.TP_AUTO_K8S_BMDP_BW6DM, "mySleep.application"):
                po_dp.goto_dataplane(ENV.TP_AUTO_K8S_BMDP_NAME)
                po_bmdp_config.goto_dataplane_config()
                if po_bmdp_config.dp_config_bw6(ENV.TP_AUTO_K8S_BMDP_BW6DM):
                    po_dp.goto_dataplane(ENV.TP_AUTO_K8S_BMDP_NAME)
                    if po_bmdp_config.goto_products("BW6"):
                        po_bmdp_config.check_bmdp_app_status_by_app_name("BW6", ENV.TP_AUTO_K8S_BMDP_BW6DM, "mySleep.application")

            po_dp.goto_dataplane(ENV.TP_AUTO_K8S_BMDP_NAME)
            po_bmdp_config.goto_dataplane_config()
            # Note: Will switch to global dataplane configuration, remove config dataplane level o11y
            # po_bmdp_config.o11y_config_dataplane_resource(ENV.TP_AUTO_K8S_BMDP_NAME)
            po_bmdp_config.o11y_config_switch_to_global(ENV.TP_AUTO_K8S_BMDP_NAME)

            # PCP-22771: keep these inside the guard - unguarded they open a BMDP that was never created.
            # Latent today, unlike the page_dp.py twin: utils/env.py defaults TP_AUTO_IS_CREATE_BMDP to "true" (DP:
            # "false"), and tp-automation-o11y.yaml re-exports it inside create-bmdp, the only task running this file.
            po_dp.goto_left_navbar_dataplane()
            po_dp.goto_dataplane(ENV.TP_AUTO_K8S_BMDP_NAME)
            Util.screenshot_page(page, f"success-{ENV.TP_AUTO_K8S_BMDP_NAME}.png")

        # we logged in, so we log out even when there is no BMDP to navigate to.
        po_auth.logout()
    except Exception as e:
        current_filename = Path(__file__).stem
        Util.exit_error(f"Unhandled error: {e}", page, f"unhandled_error_{current_filename}.png")
    Util.browser_close()

    Util.set_cp_env()
    Util.print_env_info(False)
