#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary

from pathlib import Path
from utils.util import Util
from utils.env import ENV
from page_object.po_auth import PageObjectAuth
from page_object.po_dataplane import PageObjectDataPlane
from page_object.po_dp_config import PageObjectDataPlaneConfiguration
from page_object.po_dp_bwce import PageObjectDataPlaneBWCE
from page_object.po_dp_ems import PageObjectDataPlaneEMS
from page_object.po_dp_flogo import PageObjectDataPlaneFlogo
from page_object.po_dp_pulsar import PageObjectDataPlanePulsar
from page_object.po_dp_tibcohub import PageObjectDataPlaneTibcoHub

if __name__ == "__main__":
    page = Util.browser_launch()
    try:
        po_auth = PageObjectAuth(page)
        po_auth.login()

        po_dp = PageObjectDataPlane(page)
        po_dp_config = PageObjectDataPlaneConfiguration(page)
        po_dp.goto_dataplane(ENV.TP_AUTO_K8S_DP_NAME)
        po_dp_config.goto_dataplane_config()
        po_dp_config.dp_config_resources_storage(ENV.TP_AUTO_K8S_DP_NAME)

        # for provision BWCE/BW5 capability
        if ENV.TP_AUTO_IS_PROVISION_BWCE or ENV.TP_AUTO_IS_PROVISION_BW5CE:
            capability = "bw5ce" if ENV.TP_AUTO_IS_PROVISION_BW5CE else "bwce"

            ingress_controller = ENV.TP_AUTO_INGRESS_CONTROLLER_BW5CE if ENV.TP_AUTO_IS_PROVISION_BW5CE else ENV.TP_AUTO_INGRESS_CONTROLLER_BWCE
            fqdn = ENV.TP_AUTO_FQDN_BW5CE if ENV.TP_AUTO_IS_PROVISION_BW5CE else ENV.TP_AUTO_FQDN_BWCE
            po_dp_config.dp_config_resources_ingress(
                ENV.TP_AUTO_K8S_DP_NAME,
                ENV.TP_AUTO_INGRESS_CONTROLLER, ingress_controller,
                ENV.TP_AUTO_INGRESS_CONTROLLER_CLASS_NAME, fqdn
            )
            po_dp_bwce = PageObjectDataPlaneBWCE(page, capability)
            po_dp_bwce.goto_left_navbar_dataplane()
            po_dp_bwce.goto_dataplane(ENV.TP_AUTO_K8S_DP_NAME)
            po_dp_bwce.bwce_provision_capability(ENV.TP_AUTO_K8S_DP_NAME)
            po_dp_bwce.bwce_provision_connector(ENV.TP_AUTO_K8S_DP_NAME)

        # for provision EMS capability
        if ENV.TP_AUTO_IS_PROVISION_EMS:
            po_dp_ems = PageObjectDataPlaneEMS(page)
            po_dp_ems.goto_left_navbar_dataplane()
            po_dp_ems.goto_dataplane(ENV.TP_AUTO_K8S_DP_NAME)

            po_dp_ems.ems_provision_capability(ENV.TP_AUTO_K8S_DP_NAME, ENV.TP_AUTO_EMS_CAPABILITY_SERVER_NAME)

        # for provision Flogo capability
        if ENV.TP_AUTO_IS_PROVISION_FLOGO:
            po_dp_config.dp_config_resources_ingress(
                ENV.TP_AUTO_K8S_DP_NAME,
                ENV.TP_AUTO_INGRESS_CONTROLLER, ENV.TP_AUTO_INGRESS_CONTROLLER_FLOGO,
                ENV.TP_AUTO_INGRESS_CONTROLLER_CLASS_NAME, ENV.TP_AUTO_FQDN_FLOGO
            )
            po_dp_flogo = PageObjectDataPlaneFlogo(page)
            po_dp_flogo.goto_left_navbar_dataplane()
            po_dp_flogo.goto_dataplane(ENV.TP_AUTO_K8S_DP_NAME)
            po_dp_flogo.flogo_provision_capability(ENV.TP_AUTO_K8S_DP_NAME)
            po_dp_flogo.flogo_provision_connector(ENV.TP_AUTO_K8S_DP_NAME, ENV.FLOGO_APP_NAME)

        # for provision Pulsar capability
        if ENV.TP_AUTO_IS_PROVISION_PULSAR:
            po_dp_pulsar = PageObjectDataPlanePulsar(page)
            po_dp_pulsar.goto_left_navbar_dataplane()
            po_dp_pulsar.goto_dataplane(ENV.TP_AUTO_K8S_DP_NAME)

            po_dp_pulsar.pulsar_provision_capability(ENV.TP_AUTO_K8S_DP_NAME, ENV.TP_AUTO_PULSAR_CAPABILITY_SERVER_NAME)

        # for provision TibcoHub capability
        if ENV.TP_AUTO_IS_PROVISION_TIBCOHUB:
            po_dp_config.dp_config_resources_ingress(
                ENV.TP_AUTO_K8S_DP_NAME,
                ENV.TP_AUTO_INGRESS_CONTROLLER, ENV.TP_AUTO_INGRESS_CONTROLLER_TIBCOHUB,
                ENV.TP_AUTO_INGRESS_CONTROLLER_CLASS_NAME, ENV.TP_AUTO_FQDN_TIBCOHUB
            )
            po_dp_tibcohub = PageObjectDataPlaneTibcoHub(page)
            po_dp_tibcohub.goto_left_navbar_dataplane()
            po_dp_tibcohub.goto_dataplane(ENV.TP_AUTO_K8S_DP_NAME)

            po_dp_tibcohub.tibcohub_provision_capability(ENV.TP_AUTO_K8S_DP_NAME, ENV.TP_AUTO_TIBCOHUB_CAPABILITY_HUB_NAME)

        po_auth.logout()
    except Exception as e:
        current_filename = Path(__file__).stem
        Util.exit_error(f"Unhandled error: {e}", page, f"unhandled_error_{current_filename}.png")
    Util.browser_close()

    Util.set_cp_env()
    Util.print_env_info(False)
