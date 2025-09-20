#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary

from pathlib import Path
from utils.util import Util
from utils.env import ENV
from page_object.po_auth import PageObjectAuth
from page_object.po_dataplane import PageObjectDataPlane
from page_object.po_dp_config import PageObjectDataPlaneConfiguration
from page_object.po_bmdp_config import PageObjectBMDPConfiguration

if __name__ == "__main__":
    page = Util.browser_launch()
    try:
        po_auth = PageObjectAuth(page)
        po_auth.login()
        po_dp = PageObjectDataPlane(page)
        po_bmdp_config = PageObjectBMDPConfiguration(page)
        # for provision RVDM capability
        if ENV.TP_AUTO_IS_ENABLE_RVDM:
            po_dp.goto_dataplane(ENV.TP_AUTO_K8S_BMDP_NAME)
            po_bmdp_config.goto_dataplane_config()
            po_bmdp_config.dp_config_bw5_rvdm(ENV.TP_AUTO_K8S_BMDP_BW5_RVDM)
            po_dp.goto_dataplane(ENV.TP_AUTO_K8S_BMDP_NAME)
            po_bmdp_config.goto_products("BW5") # "BW5" for BW5, "BE" for be, "BW6" for BW6
            po_bmdp_config.check_bmdp_app_status_by_app_name("BW5", ENV.TP_AUTO_K8S_BMDP_BW5_RVDM, "mySleep")
        if ENV.TP_AUTO_IS_ENABLE_EMSDM:
            po_dp.goto_dataplane(ENV.TP_AUTO_K8S_BMDP_NAME)
            po_bmdp_config.goto_dataplane_config()
            po_bmdp_config.dp_config_ems(ENV.TP_BMDP_IMAGE_TAG_EMS)
        if ENV.TP_AUTO_IS_ENABLE_EMSDM:
            po_dp.goto_dataplane(ENV.TP_AUTO_K8S_BMDP_NAME)
            po_bmdp_config.goto_dataplane_config()
            po_bmdp_config.dp_config_bw5_emsdm(ENV.TP_AUTO_K8S_BMDP_BW5_EMSDM)
            po_dp.goto_dataplane(ENV.TP_AUTO_K8S_BMDP_NAME)
            po_bmdp_config.goto_products("BW5")
            po_bmdp_config.check_bmdp_app_status_by_app_name("BW5", ENV.TP_AUTO_K8S_BMDP_BW5_EMSDM, "mySleep")
        if ENV.TP_AUTO_IS_ENABLE_BW6DM:
            po_dp.goto_dataplane(ENV.TP_AUTO_K8S_BMDP_NAME)
            po_bmdp_config.goto_dataplane_config()
            po_bmdp_config.dp_config_bw6(ENV.TP_AUTO_K8S_BMDP_BW6DM)
            po_dp.goto_dataplane(ENV.TP_AUTO_K8S_BMDP_NAME)
            po_bmdp_config.goto_products("BW6")
            po_bmdp_config.check_bmdp_app_status_by_app_name("BW6", ENV.TP_AUTO_K8S_BMDP_BW6DM, "mySleep.application")

        po_auth.logout()
    except Exception as e:
        current_filename = Path(__file__).stem
        Util.exit_error(f"Unhandled error: {e}", page, f"unhandled_error_{current_filename}.png")
    Util.browser_close()

    Util.set_cp_env()
    Util.print_env_info(False)
