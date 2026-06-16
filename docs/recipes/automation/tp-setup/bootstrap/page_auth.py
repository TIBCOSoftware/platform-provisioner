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
"""Init-user dispatcher.

Two paths:
- TP_AUTO_USE_CLI=true  -> pure-API path (api_object.ApiAuth, no browser).
                           Requires CP installed with
                           global.external.enable_api_based_initialization=true.
- otherwise             -> legacy GUI path (page_object.PageObjectAuth), unchanged.
"""
from pathlib import Path

from utils.color_logger import ColorLogger
from utils.env import ENV
from utils.util import Util


def _run_api_path():
    from api_object import ApiAuth, ApiAuthError
    ColorLogger.info("Init-user via API (TP_AUTO_USE_CLI=true)")
    try:
        ApiAuth().init_cp_user(ENV.DP_USER_EMAIL, ENV.DP_HOST_PREFIX, ENV.DP_USER_PASSWORD)
    except ApiAuthError as e:
        ColorLogger.error(str(e))
        raise


def _run_gui_path():
    from page_object.po_auth import PageObjectAuth
    page = Util.browser_launch()
    po_auth = PageObjectAuth(page)
    try:
        if not po_auth.is_host_prefix_exist(ENV.DP_HOST_PREFIX):
            if ENV.TP_AUTO_IS_PROVISION_USER_WITHOUT_EMAIL:
                # No-email path (default): admin pre-bootstrapped via chart adminInitialPassword;
                # regular user via Console API + initialPassword. login_admin_user / login
                # transparently handle CP's forced first-login password reset.
                if not po_auth.is_admin_user_exist():
                    Util.exit_error("Admin login failed (even after first-login reset attempt).",
                                    page, "no-email-admin-login.png")
                po_auth.admin_provision_user_via_api(ENV.DP_USER_EMAIL, ENV.DP_HOST_PREFIX, ENV.DP_USER_PASSWORD)
                if po_auth.login():
                    po_auth.logout()
                else:
                    # CP 1.18+: initialPassword no longer registers the user in the IdP.
                    # Fall back to email-based activation via maildev.
                    ColorLogger.warning("initialPassword login failed, activating user via maildev email...")
                    po_auth.active_user_in_mail(ENV.DP_USER_EMAIL)
            else:
                # Legacy email-based path
                if not po_auth.is_admin_user_exist():
                    po_auth.active_user_in_mail(ENV.CP_ADMIN_EMAIL, True)
                po_auth.admin_provision_user(ENV.DP_USER_EMAIL, ENV.DP_HOST_PREFIX)
                po_auth.active_user_in_mail(ENV.DP_USER_EMAIL)
    except Exception as e:
        current_filename = Path(__file__).stem
        Util.exit_error(f"Unhandled error: {e}", page, f"unhandled_error_{current_filename}.png")
    Util.browser_close()


if __name__ == "__main__":
    ENV.pre_check()
    if ENV.TP_AUTO_USE_CLI:
        _run_api_path()
    else:
        _run_gui_path()
    Util.set_cp_env()
    Util.print_env_info(True, False)
