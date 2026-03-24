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

import os
import sys
from pathlib import Path
from utils.util import Util
from utils.env import ENV
from page_object.po_auth import PageObjectAuth
from page_object.po_dataplane import PageObjectDataPlane

if __name__ == "__main__":
    CAPABILITY = os.environ.get("CAPABILITY", "").lower()

    if CAPABILITY == "":
        Util.exit_error("CAPABILITY can not be empty.")

    page = Util.browser_launch()
    try:
        po_auth = PageObjectAuth(page)
        po_auth.login()

        po_dp = PageObjectDataPlane(page)
        po_dp.goto_left_navbar_dataplane()
        if CAPABILITY == "bwce":
            po_dp.k8s_delete_app(ENV.TP_AUTO_K8S_DP_NAME, CAPABILITY, ENV.BWCE_APP_NAME)

        if CAPABILITY == "bw5ce":
            po_dp.k8s_delete_app(ENV.TP_AUTO_K8S_DP_NAME, CAPABILITY, ENV.BW5CE_APP_NAME)

        if CAPABILITY == "flogo":
            po_dp.k8s_delete_app(ENV.TP_AUTO_K8S_DP_NAME, CAPABILITY, ENV.FLOGO_APP_NAME)

        po_auth.logout()
    except Exception as e:
        current_filename = Path(__file__).stem
        Util.exit_error(f"Unhandled error: {e}", page, f"unhandled_error_{current_filename}.png")
    Util.browser_close()

    Util.set_cp_env()
    Util.print_env_info(False)
