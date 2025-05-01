#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary

from utils.util import Util
from utils.color_logger import ColorLogger
from utils.e2e_util import E2EUtils
from playwright.sync_api import expect
from datetime import datetime, timedelta
import pytest

def test_widget_action_buttons_visibility(setup_refresh_o11y):
    page, _ = setup_refresh_o11y(False)
    expect(page.locator(".dashboard-actions-row button", has_text='Add Card')).to_be_visible()
    expect(page.locator(".dashboard-actions-row button.test-reset-layout")).to_be_visible()
    page.locator(".dashboard-actions-row button.test-reset-layout").click()
    page.wait_for_timeout(500)
    expect(page.locator(".dashboard-actions-row .p-menuitem-link span", has_text='Save Snapshot')).to_be_visible()
    expect(page.locator(".dashboard-actions-row .p-menuitem-link span", has_text='Revert to Snapshot')).to_be_visible()
    expect(page.locator(".dashboard-actions-row .p-menuitem-link span", has_text='Reset Layout')).to_be_visible()

def test_widget_action_buttons_functionality(setup_refresh_o11y):
    card_name = "Application CPU Utilization"
    page, po_o11y = setup_refresh_o11y()
    po_o11y.add_widget("Integration General", None, f"{card_name}", "Kubernetes")
    expect(page.locator('shared-item-chart .highcharts-title', has_text=card_name)).to_be_visible()
    ColorLogger.success(f"Add a Widget, expected widget is visible")

    po_o11y.click_action_menu("Save Snapshot")
    expect(page.locator("p-toast .pl-notification--success", has_text='Dashboard snapshot saved successfully')).to_be_visible()
    ColorLogger.success(f"Clicked 'Save Snapshot' button, expected success message is visible")

    Util.refresh_page(page)
    page.locator(".metrics-root .widget-list-content").wait_for(state="visible")
    print("Observability page is loaded")
    expect(page.locator('shared-item-chart .highcharts-title', has_text=card_name)).to_be_visible()
    ColorLogger.success(f"Refresh page, expected the added widget is still visible")

    po_o11y.click_action_menu("Reset Layout", True)
    expect(page.locator('shared-item-chart .highcharts-title', has_text=card_name)).not_to_be_visible()
    ColorLogger.success(f"Clicked 'Reset Layout' button, expected the added widget is not visible")

    po_o11y.click_action_menu("Revert to Snapshot")
    expect(page.locator("p-confirmdialog .p-confirm-dialog-message").nth(0)).to_be_visible()
    ColorLogger.success(f"Clicked 'Revert to Snapshot' button, expected the confirmation dialog is visible")

    page.locator("p-confirmdialog button", has_text="Yes").click()
    expect(page.locator('shared-item-chart .highcharts-title', has_text=card_name)).to_be_visible()
    ColorLogger.success(f"Clicked 'Yes' button, expected to revert to the last snapshot")

def test_custom_metrics_filter(add_custom_card):
    card_name = "CPU Utilization/Limit Percentage"
    page, po_o11y = add_custom_card("Flogo", "Engine", card_name)

    expect(page.locator(".widget-filter-dialog-v2")).to_be_visible()
    ColorLogger.success(f"Click 'Filter' button, expect to custom filter dialog is visible")

    po_o11y.click_filter_dialog_button("Cancel")
    expect(page.locator(".widget-filter-dialog-v2")).not_to_be_visible()
    ColorLogger.success(f"Click 'Cancel' button, expect to custom filter dialog is not visible")

    expect(po_o11y.get_chart_card(card_name).locator("custom-metrics-filter-aggr-info button")).to_be_visible()
    po_o11y.get_chart_card(card_name).locator("custom-metrics-filter-aggr-info button").hover()
    print(f"Mouse hover to the 'i' icon button")

    expect(po_o11y.get_chart_card(card_name).locator("custom-metrics-filter-aggr-info .tooltip-content", has_text=f"avg({card_name})")).to_be_visible()
    ColorLogger.success(f"Expect the 'i' icon is visible, mouseover to see the tooltip successfully")

    now = datetime.now()
    one_hour_ago = now - timedelta(hours=1)
    time_hour_ago = one_hour_ago.strftime("Since %b %d %Y %H:%M")
    expect(po_o11y.get_chart_card(card_name).locator(".widget-filter-label", has_text=time_hour_ago)).to_be_visible()
    ColorLogger.success(f"Expect to see the default time range is '{time_hour_ago}'")

    expect(po_o11y.get_chart_card(card_name).locator(".widget-dp-workload-type", has_text="Kubernetes")).to_be_visible()
    ColorLogger.success(f"Expect to see the 'Kubernetes' tag is visible")

    expect(po_o11y.get_chart_card(card_name).locator(".widget-card-bottom-app-types .ci-flogo")).to_be_visible()
    ColorLogger.success(f"Expect to see the Flogo icon is visible")

    expect(po_o11y.get_chart_card(card_name).locator('.widget-card-bottom button[title="Remove Card"]')).to_be_visible()
    po_o11y.get_chart_card(card_name).locator('.widget-card-bottom button[title="Remove Card"]').click()
    print(f"Click the 'delete' icon button")

    expect(page.locator('shared-card-remove-confirmation')).to_be_visible()
    ColorLogger.success(f"Click remove card icon button, expect to see Delete card confirmation dialog is visible")

    page.locator('shared-card-remove-confirmation button', has_text="Delete card").click()
    print(f"Click 'Delete card' confirmation button")
    expect(po_o11y.get_chart_card(card_name)).not_to_be_visible()
    ColorLogger.success(f"Expect to see {card_name} card is removed")

def test_custom_metrics_switch_chart_type(add_custom_card):
    card_name = "CPU Utilization/Limit Percentage"
    page, po_o11y = add_custom_card("Flogo", "Engine", card_name)

    po_o11y.click_filter_dialog_menu("Chart Presentation")
    po_o11y.click_filter_dialog_chart_type("Treemap")
    po_o11y.assert_after_custom_metrics_apply_filter(
        {
            "aggrOp": "avg",
            "appTypes": "flogo",
            "chartType": "treemap",
            "requestType": "custom_metrics_summary",
            "metrics": "k8s_container_cpu_limit_utilization_ratio"
        }
    )
    expect(page.locator('shared-treemap-chart .highcharts-title', has_text=card_name)).to_be_visible()
    ColorLogger.success(f"Switch to 'Treemap', expect to see Treemap chart is visible")

def test_custom_metrics_change_card_name(add_custom_card):
    card_name = "CPU Utilization/Limit Percentage"
    page, po_o11y = add_custom_card("Flogo", "Engine", card_name)

    new_card_name = card_name + " - New"
    po_o11y.input_filter_dialog_card_name(card_name, new_card_name)
    E2EUtils.assert_api_request_and_response(
        page,
        "/o11y/v1/dashboard/profiles",
        lambda: po_o11y.click_filter_dialog_button("Apply"),
        "PUT"
    )
    expect(page.locator('custom-metric-widget .highcharts-title', has_text=new_card_name)).to_be_visible()
    ColorLogger.success(f"Change card name, expect to see new chart title {new_card_name} is visible")

    po_o11y.click_widget_card_button(new_card_name, "Filters")
    original_card_name = page.locator(".widget-filter-dialog-v2 .header-right").text_content().strip()
    expect(page.locator(".widget-filter-dialog-v2 .header-right")).to_have_text(original_card_name)
    ColorLogger.success(f"Reopen filter dialog, expect to see the original chart title {new_card_name} is visible too")
    po_o11y.click_filter_dialog_button("Cancel")

widget_test_data = [
    # level1_menu, level2_menu, middle_menu, data_plane_type, expected_selector, expected_text
    ("Integration General", None, "Application CPU Utilization", "Kubernetes", "shared-item-chart .highcharts-title", "Application CPU Utilization"),
    ("Integration General", None, "Application Memory Usage", "Kubernetes", "shared-item-chart .highcharts-title", "Application Memory Usage"),
    ("Integration General", None, "Application Instances", "Kubernetes", "shared-pie-chart .highcharts-title", "Application Instances"),
    ("Integration General", None, "Application Request Counts", "Kubernetes", "shared-pie-chart .highcharts-title", "Application Request Counts"),

    ("BWCE", "Engine", "Active Thread Count", None, "shared-line-chart .highcharts-title", "Active Thread Count"),
    ("BWCE", "Process", "Process Max Elapsed Time", None, "shared-line-chart .highcharts-title", "Process Max Elapsed Time"),
    ("BWCE", "Activity", "Activity Max Elapsed Time", None, "shared-line-chart .highcharts-title", "Activity Max Elapsed Time"),

    ("Flogo", "Engine", "CPU Utilization/Limit Percentage", None, "shared-line-chart .highcharts-title", "CPU Utilization/Limit Percentage"),
    ("Flogo", "Flow", "Total Flow Executions", None, "shared-line-chart .highcharts-title", "Total Flow Executions"),
    ("Flogo", "Activity", "Total Activity Executions", None, "shared-line-chart .highcharts-title", "Total Activity Executions"),
]
@pytest.mark.parametrize(
    "level1_menu, level2_menu, middle_menu, data_plane_type, selector, expected_text",
    widget_test_data
)
def test_add_widget_variants(setup_refresh_o11y, level1_menu, level2_menu, middle_menu, data_plane_type, selector, expected_text):
    page, po_o11y = setup_refresh_o11y()
    po_o11y.add_widget(level1_menu, level2_menu, middle_menu, data_plane_type)
    if page.locator(".widget-card-content h3", has_text=expected_text).nth(0).is_visible():
        expect(page.locator(".widget-card-content h3", has_text=expected_text).nth(0)).to_be_visible()
        ColorLogger.success(f"Add widget card successfully, but no data available")
    else:
        expect(page.locator(selector, has_text=expected_text).nth(0)).to_be_visible()
        ColorLogger.success(f"Add widget card successfully, and data is available")
