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

# Observability auto-configuration (gated by TP_AUTO_ENABLE_O11Y_WIDGET).
# On CP versions that expose the "Add dashboard" button, create per-capability
# dashboards and bulk-add cards (PCP-20053). On older CP versions without it,
# fall back to the legacy widget flow (add a few cards to the Default dashboard).

from pathlib import Path

from utils.report import ReportYaml
from utils.util import Util
from utils.env import ENV
from utils.color_logger import ColorLogger
from page_object.po_auth import PageObjectAuth
from page_object.po_o11y import PageObjectO11y
from o11y_dashboard_config import (
    LOG_CARDS,
    LOG_DASHBOARD_NAME,
    CAPABILITY_DASHBOARDS,
    PROMQL_DASHBOARD,
)


def configure_default_dashboard(po_o11y):
    """Step 1: reset the Default dashboard. Reset Layout restores the system-default
    Default dashboard, which is already populated with all Integration General
    (Kubernetes + Control Tower) and Messaging General cards. Re-adding them would
    duplicate cards and hit the 15-card limit, so a reset is all that is needed."""
    print("===== Step 1: configure 'Default' dashboard =====")
    po_o11y.click_action_menu("Reset Layout", True)


def configure_logs_dashboard(po_o11y):
    """Step 2: create logs_dashboard and add the log cards."""
    print(f"===== Step 2: configure '{LOG_DASHBOARD_NAME}' dashboard =====")
    if po_o11y.is_dashboard_exists(LOG_DASHBOARD_NAME):
        ColorLogger.warning(f"Dashboard '{LOG_DASHBOARD_NAME}' already exists; skip creation")
        return
    if not po_o11y.create_dashboard(LOG_DASHBOARD_NAME):
        Util.warning_screenshot(f"Failed to create '{LOG_DASHBOARD_NAME}'", po_o11y.page, f"o11y-create-{LOG_DASHBOARD_NAME}.png")
        return
    log_cards = list(LOG_CARDS)
    if po_o11y.is_catalog_card_available("Logs", None, "Audit History"):
        log_cards.append("Audit History")
    else:
        ColorLogger.warning("'Audit History' not available (Audit Trail not installed); skip it")
    po_o11y.add_widgets("Logs", None, log_cards, None)


def configure_capability_dashboards(po_o11y, labels):
    """Step 3: create one dashboard per installed capability and add its cards.
    Uninstalled capabilities are skipped with a clear log line."""
    print("===== Step 3: configure per-capability dashboards =====")
    for spec in CAPABILITY_DASHBOARDS:
        name, capability = spec["name"], spec["capability"]
        if capability not in labels:
            ColorLogger.warning(f"Capability '{capability}' not installed; skip dashboard '{name}'")
            continue
        if po_o11y.is_dashboard_exists(name):
            ColorLogger.warning(f"Dashboard '{name}' already exists; skip creation")
            continue
        if not po_o11y.create_dashboard(name):
            Util.warning_screenshot(f"Failed to create dashboard '{name}'", po_o11y.page, f"o11y-create-{name}.png")
            continue
        for level2_menu, cards in spec["groups"]:
            po_o11y.add_widgets(capability, level2_menu, cards)


def configure_promql_dashboard(po_o11y, labels):
    """Step 4 (PCP-20424): create the dedicated PromQL dashboard. One Range card plus
    one Instant card per concrete chart type (renamed so they're distinguishable).
    PromQL cards auto-open a query editor, so they go through add_promql_*widget."""
    spec = PROMQL_DASHBOARD
    name, capability, submenu = spec["name"], spec["capability"], spec["submenu"]
    print(f"===== Step 4: configure '{name}' dashboard =====")
    if capability not in labels:
        ColorLogger.warning(f"Capability '{capability}' not installed; skip dashboard '{name}'")
        return
    if po_o11y.is_dashboard_exists(name):
        ColorLogger.warning(f"Dashboard '{name}' already exists; skip creation")
        return
    if not po_o11y.create_dashboard(name):
        Util.warning_screenshot(f"Failed to create dashboard '{name}'", po_o11y.page, f"o11y-create-{name}.png")
        return
    for card_name, query in spec["range_cards"]:
        po_o11y.add_promql_widget(capability, submenu, card_name, query)
    for card_name, query, chart_type, title in spec["instant_cards"]:
        po_o11y.add_promql_instant_widget(capability, submenu, card_name, query, chart_type, title)


def configure_dashboards(po_o11y):
    """PCP-20053 + PCP-20424 flow: populate Default + logs_dashboard + per-capability
    dashboards + the dedicated PromQL dashboard."""
    labels = po_o11y.get_catalog_menu_labels()
    configure_default_dashboard(po_o11y)
    configure_logs_dashboard(po_o11y)
    configure_capability_dashboards(po_o11y, labels)
    configure_promql_dashboard(po_o11y, labels)


def configure_legacy_widgets(po_o11y):
    """Backward-compatible minimal flow for older CP versions that do not expose
    the 'Add dashboard' button: reset the Default dashboard and add a few cards."""
    ColorLogger.warning("Add dashboard not supported; running legacy widget flow on the Default dashboard")
    po_o11y.click_action_menu("Reset Layout", True)
    if po_o11y.is_data_plane_in_list(ENV.TP_AUTO_K8S_DP_NAME):
        widget_card_data = [
            # level1_menu, level2_menu, middle_menu, data_plane_type
            ("Integration General", None, "Application Instances", "Kubernetes"),
            ("BW6 (Containers)", "Engine", "Active Thread Count", None),
            ("Flogo", "Engine", "CPU Utilization/Limit Percentage", None),
        ]
        for level1_menu, level2_menu, middle_menu, data_plane_type in widget_card_data:
            po_o11y.add_widget(level1_menu, level2_menu, middle_menu, data_plane_type)
        ReportYaml.set_dataplane_info(ENV.TP_AUTO_K8S_DP_NAME, "o11yWidget", True)

    if po_o11y.is_data_plane_in_list(ENV.TP_AUTO_K8S_BMDP_NAME):
        widget_card_data = [
            # level1_menu, level2_menu, middle_menu, data_plane_type
            ("Integration General", None, "Application Instances", "Control Tower"),
            ("BW5 (Containers)", "Engine", "CPU Percent", None),
        ]
        for level1_menu, level2_menu, middle_menu, data_plane_type in widget_card_data:
            po_o11y.add_widget(level1_menu, level2_menu, middle_menu, data_plane_type)
        ReportYaml.set_dataplane_info(ENV.TP_AUTO_K8S_BMDP_NAME, "o11yWidget", True)


if __name__ == "__main__":
    ENV.pre_check()

    page = Util.browser_launch()
    try:
        po_auth = PageObjectAuth(page)
        po_o11y = PageObjectO11y(page)

        po_auth.login()
        po_auth.login_check()

        po_o11y.goto_left_navbar_o11y()
        if not po_o11y.is_support_add_widget():
            Util.warning_screenshot("'Add Card' is not available; skip Observability configuration", page, "o11y-add-card-unsupported.png")
        elif po_o11y.has_add_dashboard_button():
            configure_dashboards(po_o11y)
            ReportYaml.set_dataplane_info(ENV.TP_AUTO_K8S_DP_NAME, "o11yWidget", True)
        else:
            configure_legacy_widgets(po_o11y)

        Util.screenshot_page(page, f"success-o11y-widgets.png")
        po_auth.logout()
    except Exception as e:
        current_filename = Path(__file__).stem
        Util.exit_error(f"Unhandled error: {e}", page, f"unhandled_error_{current_filename}.png")
    Util.browser_close()

    Util.set_cp_env()
    Util.print_env_info(False)
