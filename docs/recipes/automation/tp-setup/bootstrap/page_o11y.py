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

import os
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


def is_force_run():
    """Whether an existing dashboard should be DELETED and rebuilt.

    Honours FORCE_RUN_AUTOMATION (AC10), but reads TP_AUTO_O11Y_FORCE_REBUILD_DASHBOARD first
    when it is set, so the destructive behaviour can be steered on its own.
    FORCE_RUN_AUTOMATION is a GLOBAL switch - a checkbox in the Hub UI, an MCP tool parameter,
    and the app-rebuild flag in three case/k8s_create_and_start_*_app.py - whose meaning so far
    has been 'redo the app create/start'. Someone ticking it to force a Flogo rebuild should
    have a way to say 'but leave my dashboards alone'.

    Read at call time, not import time, so a caller can set it per run.
    """
    override = os.environ.get("TP_AUTO_O11Y_FORCE_REBUILD_DASHBOARD", "").strip().lower()
    if override:
        # Accept the usual truthy spellings here, not just "true". This flag can CANCEL a
        # rebuild, so reading an intended-yes value like "1" as false would do the opposite of
        # what the person setting it asked for - silently.
        return override in ("true", "1", "yes", "on")
    return os.environ.get("FORCE_RUN_AUTOMATION", "false").strip().lower() == "true"


def should_build_dashboard(po_o11y, name, existed=None):
    """Whether the caller should go on to create `name`.

    `existed` lets a caller that has already read the dropdown pass the answer in; opening it
    is the flakiest and slowest control in this flow, so it is not worth reading twice.

    Default: an existing dashboard is left alone (unchanged behaviour). Under the force flag it
    is deleted first so the create path runs again - without that switch, once a dashboard
    existed on an instance the code that builds it could never execute there again, which is
    what let a wrong root cause survive a 'passing' re-run and left a half-built dashboard with
    no way to self-heal (PCP-24228).

    A delete that fails skips the rebuild rather than calling create_dashboard on a name that is
    still taken (which only re-opens the dialog with an inline error).
    """
    if existed is None:
        existed = po_o11y.is_dashboard_exists(name)
    if not existed:
        return True
    if not is_force_run():
        ColorLogger.warning(f"Dashboard '{name}' already exists; skip creation")
        return False
    print(f"Force rebuild is on; deleting existing dashboard '{name}' to rebuild it")
    if not po_o11y.delete_dashboard(name):
        # delete_dashboard already logged the specific reason and took the screenshot.
        ColorLogger.warning(f"Could not delete existing dashboard '{name}'; skip rebuilding it")
        return False
    return True


def ensure_dashboard(po_o11y, name):
    """Gate + create, shared by every step that builds a dashboard. Returns True when `name`
    exists and is ready for cards.

    Exists so the create-failure message can tell the two cases apart. Under a force rebuild the
    dashboard is DELETED first, so a create that then fails leaves the instance with no `name`
    dashboard at all - a materially worse outcome than the 'skip and leave alone' default, and
    one the generic 'Failed to create' line gave no hint of.
    """
    existed = po_o11y.is_dashboard_exists(name)
    if not should_build_dashboard(po_o11y, name, existed):
        return False
    if po_o11y.create_dashboard(name):
        return True
    if existed:
        Util.warning_screenshot(
            f"Dashboard '{name}' was DELETED for a force rebuild and could not be recreated - "
            f"this instance now has NO '{name}' dashboard. Re-run to rebuild it.",
            po_o11y.page, f"o11y-rebuild-lost-{name}.png")
    else:
        Util.warning_screenshot(f"Failed to create dashboard '{name}'", po_o11y.page, f"o11y-create-{name}.png")
    return False


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
    if not ensure_dashboard(po_o11y, LOG_DASHBOARD_NAME):
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
        if not ensure_dashboard(po_o11y, name):
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
    if not ensure_dashboard(po_o11y, name):
        return
    # Tally what actually landed. This is the dashboard the defect emptied out, and the run
    # exits 0 either way, so without a count at the end a future selector hop is just a green
    # pipeline and 5 missing cards that only a screenshot would reveal.
    # "complete" rather than "added" on purpose: an instant card that was applied but could not
    # be RENAMED is physically on the dashboard, so calling it not-added would misreport what is
    # there. It is still a failure - every instant card comes from the same catalog entry, so
    # without the rename the dashboard shows five identical titles and the one thing it exists
    # to show is gone.
    expected, complete = 0, 0
    for card_name, query in spec["range_cards"]:
        expected += 1
        complete += 1 if po_o11y.add_promql_widget(capability, submenu, card_name, query) else 0
    for card_name, query, chart_type, title in spec["instant_cards"]:
        expected += 1
        complete += 1 if po_o11y.add_promql_instant_widget(capability, submenu, card_name, query, chart_type, title) else 0
    if complete < expected:
        Util.warning_screenshot(
            f"Dashboard '{name}': only {complete} of {expected} cards are complete "
            f"(added and correctly named)", po_o11y.page, f"o11y-{name}-incomplete.png")
    else:
        ColorLogger.success(f"Dashboard '{name}': all {expected} cards complete (added and correctly named)")


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
