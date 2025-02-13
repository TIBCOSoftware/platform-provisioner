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
        Util.exit_error(f"Unhandled error: {e}", page, "unhandled_error_auth.png")

    Util.browser_close()

    Util.set_cp_env()
    Util.print_env_info(True, False)
