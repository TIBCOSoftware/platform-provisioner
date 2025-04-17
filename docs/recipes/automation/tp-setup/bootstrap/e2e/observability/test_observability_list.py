#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary

from utils.util import Util
from utils.env import ENV
from page_object.po_o11y import PageObjectO11y
from utils.color_logger import ColorLogger
from utils.e2e_util import E2EUtils
from playwright.sync_api import expect
import pytest

@pytest.fixture(scope="function", autouse=True)
def setup_refresh_o11y(logged_in_page):
    page = logged_in_page
    po_o11y = PageObjectO11y(page)
    po_o11y.goto_left_navbar_o11y()
    po_o11y.select_data_plane(ENV.TP_AUTO_K8S_DP_NAME)

    Util.refresh_page(page)
    po_o11y.click_action_menu("Reset Layout")
    return page, po_o11y

@pytest.fixture
def add_custom_card(setup_refresh_o11y):
    def _add_custom_card(level1_menu, level2_menu, middle_menu, chart_type):
        page, po_o11y = setup_refresh_o11y
        po_o11y.add_widget(level1_menu, level2_menu, middle_menu, chart_type)
        po_o11y.click_widget_filter_button(middle_menu)
        page.wait_for_timeout(1000)
        return page, po_o11y
    return _add_custom_card

def test_widget_action_buttons_visibility(setup_refresh_o11y):
    page, _ = setup_refresh_o11y
    expect(page.locator(".dashboard-actions-row button", has_text='Add Widget')).to_be_visible()
    expect(page.locator(".dashboard-actions-row button.test-reset-layout")).to_be_visible()
    page.locator(".dashboard-actions-row button.test-reset-layout").click()
    page.wait_for_timeout(500)
    expect(page.locator(".dashboard-actions-row .p-menuitem-link span", has_text='Save Snapshot')).to_be_visible()
    expect(page.locator(".dashboard-actions-row .p-menuitem-link span", has_text='Revert to Snapshot')).to_be_visible()
    expect(page.locator(".dashboard-actions-row .p-menuitem-link span", has_text='Reset Layout')).to_be_visible()

def test_widget_action_buttons_functionality(setup_refresh_o11y):
    page, po_o11y = setup_refresh_o11y
    po_o11y.add_widget("Integration General", None, "Application CPU Utilization (Kubernetes)", None)
    expect(page.locator('shared-item-chart .highcharts-title', has_text="Application CPU Utilization")).to_be_visible()
    ColorLogger.success(f"Add a Widget, expected widget is visible")

    po_o11y.click_action_menu("Save Snapshot")
    expect(page.locator("p-toast .pl-notification--success", has_text='Dashboard snapshot saved successfully')).to_be_visible()
    ColorLogger.success(f"Clicked 'Save Snapshot' button, expected success message is visible")

    Util.refresh_page(page)
    page.locator(".metrics-root .widget-list-content").wait_for(state="visible")
    print("Observability page is loaded")
    expect(page.locator('shared-item-chart .highcharts-title', has_text="Application CPU Utilization")).to_be_visible()
    ColorLogger.success(f"Refresh page, expected the added widget is still visible")

    po_o11y.click_action_menu("Reset Layout")
    expect(page.locator('shared-item-chart .highcharts-title', has_text="Application CPU Utilization")).not_to_be_visible()
    ColorLogger.success(f"Clicked 'Reset Layout' button, expected the added widget is not visible")

    po_o11y.click_action_menu("Revert to Snapshot")
    expect(page.locator("p-confirmdialog .p-confirm-dialog-message").nth(0)).to_be_visible()
    ColorLogger.success(f"Clicked 'Revert to Snapshot' button, expected the confirmation dialog is visible")

    page.locator("p-confirmdialog button.p-confirm-dialog-accept").click()
    expect(page.locator('shared-item-chart .highcharts-title', has_text="Application CPU Utilization")).to_be_visible()
    ColorLogger.success(f"Clicked 'Yes' button, expected to revert to the last snapshot")


widget_test_data = [
    # level1_menu, level2_menu, middle_menu, chart_type, expected_selector, expected_text
    ("Integration General", None, "Application CPU Utilization (Kubernetes)", None, "shared-item-chart .highcharts-title", "Application CPU Utilization"),
    ("Integration General", None, "Application Memory Usage (Kubernetes)", None, "shared-item-chart .highcharts-title", "Application Memory Usage"),
    ("Integration General", None, "Application Request Counts (Kubernetes)", None, "shared-pie-chart .highcharts-title", "Application Request Counts"),

    ("Flogo", "Activity", "Total Activity Executions", "Line Chart", "shared-line-chart .highcharts-title", "Total Activity Executions"),

    ("Flogo", "Engine", "CPU Utilization/Limit Ratio", "Line Chart", "shared-line-chart .highcharts-title", "CPU Utilization/Limit Ratio"),
    ("Flogo", "Engine", "CPU Utilization/Limit Ratio", "Treemap", "shared-treemap-chart .highcharts-title", "CPU Utilization/Limit Ratio"),

    ("Flogo", "Flow", "Total Flow Executions", "Line Chart", "shared-line-chart .highcharts-title", "Total Flow Executions"),
]
@pytest.mark.parametrize(
    "level1_menu, level2_menu, middle_menu, chart_type, selector, expected_text",
    widget_test_data
)
def test_add_widget_variants(setup_refresh_o11y, level1_menu, level2_menu, middle_menu, chart_type, selector, expected_text):
    page, po_o11y = setup_refresh_o11y
    po_o11y.add_widget(level1_menu, level2_menu, middle_menu, chart_type)
    expect(page.locator(selector, has_text=expected_text).nth(0)).to_be_visible()

def test_custom_metrics_filter(add_custom_card):
    card_name = "CPU Utilization/Limit Ratio"
    page, po_o11y = add_custom_card("Flogo", "Engine", card_name, "Line Chart")

    expect(page.locator(".widget-filter-dialog-v2")).to_be_visible()
    ColorLogger.success(f"Clicked 'Filter' button, expected to custom filter dialog is visible")

    po_o11y.click_filter_dialog_button("Cancel")
    expect(page.locator(".widget-filter-dialog-v2")).not_to_be_visible()
    ColorLogger.success(f"Clicked 'Cancel' button, expected to custom filter dialog is not visible")

def test_custom_metrics_switch_chart_type(add_custom_card):
    card_name = "CPU Utilization/Limit Ratio"
    page, po_o11y = add_custom_card("Flogo", "Engine", card_name, "Line Chart")

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
    ColorLogger.success(f"Switch to 'Treemap', expected to see Treemap chart is visible")

def test_custom_metrics_change_card_name(add_custom_card):
    card_name = "CPU Utilization/Limit Ratio"
    page, po_o11y = add_custom_card("Flogo", "Engine", card_name, "Line Chart")

    new_card_name = card_name + " - New"
    po_o11y.input_filter_dialog_card_name(card_name, new_card_name)
    E2EUtils.assert_api_request_and_response(
        page,
        "/o11y/v1/dashboard/profiles",
        lambda: po_o11y.click_filter_dialog_button("Apply"),
        "PUT"
    )
    expect(page.locator('custom-metric-widget .highcharts-title', has_text=new_card_name)).to_be_visible()
    ColorLogger.success(f"Change card name, expected to see new chart title {new_card_name} is visible")

    po_o11y.click_widget_filter_button(new_card_name)
    original_card_name = page.locator(".widget-filter-dialog-v2 .header-right").text_content().strip()
    expect(page.locator(".widget-filter-dialog-v2 .header-right")).to_have_text(original_card_name)
    ColorLogger.success(f"Reopen filter dialog, expected to see the original chart title {new_card_name} is visible too")
    po_o11y.click_filter_dialog_button("Cancel")
