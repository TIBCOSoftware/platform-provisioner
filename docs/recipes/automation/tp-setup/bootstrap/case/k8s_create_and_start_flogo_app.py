import os
from pathlib import Path
from utils.util import Util
from utils.env import ENV
from page_object.po_auth import PageObjectAuth
from page_object.po_dataplane import PageObjectDataPlane
from page_object.po_dp_config import PageObjectDataPlaneConfiguration
from page_object.po_dp_flogo import PageObjectDataPlaneFlogo

if __name__ == "__main__":
    FORCE_RUN_AUTOMATION = os.environ.get("FORCE_RUN_AUTOMATION", "false").lower() == "true"

    page = Util.browser_launch()
    try:
        po_auth = PageObjectAuth(page)
        po_auth.login()

        if FORCE_RUN_AUTOMATION:
            print("FORCE_RUN_AUTOMATION is set to True. Running automation with pre-check and pre-set.")
            po_dp = PageObjectDataPlane(page)
            po_dp_config = PageObjectDataPlaneConfiguration(page)
            po_dp.goto_dataplane(ENV.TP_AUTO_K8S_DP_NAME)
            po_dp_config.goto_dataplane_config()
            po_dp_config.dp_config_resources_storage(ENV.TP_AUTO_K8S_DP_NAME)
            po_dp_config.dp_config_resources_ingress(
                ENV.TP_AUTO_K8S_DP_NAME,
                ENV.TP_AUTO_INGRESS_CONTROLLER, ENV.TP_AUTO_INGRESS_CONTROLLER_FLOGO,
                ENV.TP_AUTO_INGRESS_CONTROLLER_CLASS_NAME, ENV.TP_AUTO_FQDN_FLOGO
            )
            po_dp_config.dp_config_activation(ENV.TP_AUTO_K8S_DP_NAME, True)
            po_dp_config.o11y_config_switch_to_global(ENV.TP_AUTO_K8S_DP_NAME)

        po_dp_flogo = PageObjectDataPlaneFlogo(page)
        po_dp_flogo.goto_left_navbar_dataplane()
        po_dp_flogo.goto_dataplane(ENV.TP_AUTO_K8S_DP_NAME)
        if FORCE_RUN_AUTOMATION:
            po_dp_flogo.flogo_provision_capability(ENV.TP_AUTO_K8S_DP_NAME)
            po_dp_flogo.flogo_provision_connector(ENV.TP_AUTO_K8S_DP_NAME, ENV.FLOGO_APP_NAME)
        po_dp_flogo.flogo_app_build_and_deploy(ENV.TP_AUTO_K8S_DP_NAME, ENV.FLOGO_APP_FILE_NAME, ENV.FLOGO_APP_NAME)
        po_dp_flogo.flogo_app_deploy(ENV.TP_AUTO_K8S_DP_NAME, ENV.FLOGO_APP_NAME)

        po_dp_flogo.flogo_app_config(ENV.TP_AUTO_K8S_DP_NAME, ENV.FLOGO_APP_NAME)
        po_dp_flogo.flogo_app_start(ENV.TP_AUTO_K8S_DP_NAME, ENV.FLOGO_APP_NAME)

        po_auth.logout()
    except Exception as e:
        current_filename = Path(__file__).stem
        Util.exit_error(f"Unhandled error: {e}", page, f"unhandled_error_{current_filename}.png")
    Util.browser_close()

    Util.set_cp_env()
    Util.print_env_info(False)
