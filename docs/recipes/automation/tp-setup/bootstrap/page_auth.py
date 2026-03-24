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
from page_object.po_auth import PageObjectAuth

if __name__ == "__main__":
    ENV.pre_check()

    page = Util.browser_launch()
    po_auth = PageObjectAuth(page)
    try:
        if not po_auth.is_host_prefix_exist(ENV.DP_HOST_PREFIX):
            if not po_auth.is_admin_user_exist():
                po_auth.active_user_in_mail(ENV.CP_ADMIN_EMAIL, True)
            po_auth.admin_provision_user(ENV.DP_USER_EMAIL, ENV.DP_HOST_PREFIX)
            po_auth.active_user_in_mail(ENV.DP_USER_EMAIL)
    except Exception as e:
        current_filename = Path(__file__).stem
        Util.exit_error(f"Unhandled error: {e}", page, f"unhandled_error_{current_filename}.png")

    Util.browser_close()

    Util.set_cp_env()
    Util.print_env_info(True, False)
