#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary

from pathlib import Path

from utils.report import ReportYaml
from utils.util import Util
from utils.env import ENV
from page_object.po_auth import PageObjectAuth
from page_object.po_o11y import PageObjectO11y

if __name__ == "__main__":
    ENV.pre_check()

    page = Util.browser_launch()
    try:
        po_auth = PageObjectAuth(page)
        po_o11y = PageObjectO11y(page)

        po_auth.login()
        po_auth.login_check()

        po_o11y.goto_left_navbar_o11y()
        if po_o11y.is_support_add_widget():
            po_o11y.click_action_menu("Reset Layout", True)
            if po_o11y.is_data_plane_in_list(ENV.TP_AUTO_K8S_DP_NAME):
                widget_card_data = [
                    # level1_menu, level2_menu, middle_menu, data_plane_type
                    ("Integration General", None, "Application CPU Utilization", "Kubernetes"),
                    ("Integration General", None, "Application Memory Usage", "Kubernetes"),
                    ("Integration General", None, "Application Instances", "Kubernetes"),
                    ("Integration General", None, "Application Request Counts", "Kubernetes"),

                    ("BWCE", "Engine", "Active Thread Count", None),
                    ("BWCE", "Process", "Process Max Elapsed Time", None),
                    ("BWCE", "Activity", "Activity Max Elapsed Time", None),

                    ("Flogo", "Engine", "CPU Utilization/Limit Percentage", None),
                    ("Flogo", "Flow", "Total Flow Executions", None),
                    ("Flogo", "Activity", "Total Activity Executions", None),
                ]
                for level1_menu, level2_menu, middle_menu, data_plane_type in widget_card_data:
                    po_o11y.add_widget(level1_menu, level2_menu, middle_menu, data_plane_type)
                ReportYaml.set_dataplane_info(ENV.TP_AUTO_K8S_DP_NAME, "o11yWidget", True)

            if po_o11y.is_data_plane_in_list(ENV.TP_AUTO_K8S_BMDP_NAME):
                widget_card_data = [
                    # level1_menu, level2_menu, middle_menu, data_plane_type
                    ("Integration General", None, "Application CPU Utilization", "Control Tower"),
                    ("Integration General", None, "Application Memory Usage", "Control Tower"),
                    ("Integration General", None, "Application Instances", "Control Tower"),
                    ("Integration General", None, "Application Request Counts", "Control Tower"),

                    ("BW5", "Engine", "CPU Percent", None),
                    ("BW5", "Process", "Process Definitions Aborted", None),
                ]
                for level1_menu, level2_menu, middle_menu, data_plane_type in widget_card_data:
                    po_o11y.add_widget(level1_menu, level2_menu, middle_menu, data_plane_type)
                ReportYaml.set_dataplane_info(ENV.TP_AUTO_K8S_BMDP_NAME, "o11yWidget", True)

        Util.screenshot_page(page, f"success-o11y-widgets.png")
        po_auth.logout()
    except Exception as e:
        current_filename = Path(__file__).stem
        Util.exit_error(f"Unhandled error: {e}", page, f"unhandled_error_{current_filename}.png")
    Util.browser_close()

    Util.set_cp_env()
    Util.print_env_info(False)
