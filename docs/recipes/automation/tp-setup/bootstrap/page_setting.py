from pathlib import Path

from utils.util import Util
from utils.env import ENV
from page_object.po_auth import PageObjectAuth
from page_object.po_settings import PageObjectSettings

if __name__ == "__main__":
    ENV.pre_check()

    page = Util.browser_launch()
    try:
        po_auth = PageObjectAuth(page)

        po_auth.login()
        po_auth.login_check()

        po_settings = PageObjectSettings(page)
        po_settings.set_mcp_server()
        po_settings.set_oauth_token()
    except Exception as e:
        current_filename = Path(__file__).stem
        Util.exit_error(f"Unhandled error: {e}", page, f"unhandled_error_{current_filename}.png")

    Util.browser_close()

    Util.set_cp_env()
    Util.print_env_info(True, False)
