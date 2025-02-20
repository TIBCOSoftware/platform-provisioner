from pathlib import Path
from utils.util import Util
from utils.env import ENV
from page_object.po_user_management import PageObjectUserManagement
from page_object.po_auth import PageObjectAuth
from page_object.po_dataplane import PageObjectDataPlane
from page_object.po_dp_config import PageObjectDataPlaneConfiguration

if __name__ == "__main__":
    page = Util.browser_launch()
    try:
        po_auth = PageObjectAuth(page)
        po_auth.login()
        po_auth.login_check()

        po_user_management = PageObjectUserManagement(page)
        po_user_management.set_user_permission()

        po_dp = PageObjectDataPlane(page)
        po_dp_config = PageObjectDataPlaneConfiguration(page)
        po_dp.goto_dataplane(ENV.TP_AUTO_K8S_DP_NAME)
        po_dp_config.goto_dataplane_config()
        po_dp_config.o11y_config_dataplane_resource(ENV.TP_AUTO_K8S_DP_NAME)

        po_auth.logout()
    except Exception as e:
        current_filename = Path(__file__).stem
        Util.exit_error(f"Unhandled error: {e}", page, f"unhandled_error_{current_filename}.png")
    Util.browser_close()

    Util.set_cp_env()
    Util.print_env_info(False)
