from utils.util import Util
from utils.env import ENV
from page_object.po_o11y import PageObjectO11y
from playwright.sync_api import expect
import pytest

@pytest.fixture(scope="function", autouse=True)
def setup_refresh_o11y(logged_in_page):
    page = logged_in_page
    po_o11y = PageObjectO11y(page)
    po_o11y.goto_left_navbar_o11y()
    po_o11y.select_data_plane(ENV.TP_AUTO_K8S_DP_NAME)

    Util.refresh_page(page)
    po_o11y.reset_layout()
    return page, po_o11y

def test_widget_action_buttons(setup_refresh_o11y):
    page, _ = setup_refresh_o11y
    expect(page.locator(".dashboard-actions-row button", has_text='Add Widget')).to_be_visible()
    expect(page.locator(".dashboard-actions-row button", has_text='Save Changes')).to_be_visible()
    expect(page.locator(".dashboard-actions-row button.test-reset-layout")).to_be_visible()

def test_save_changes_and_reset_layout_button(setup_refresh_o11y):
    page, po_o11y = setup_refresh_o11y
    po_o11y.add_widget("Integration General", None, "Application CPU Utilization (Kubernetes)", None)
    expect(page.locator(".widget-card-chart highcharts-chart text", has_text="Application CPU Utilization").nth(0)).to_be_visible()
    expect(page.locator(".dashboard-actions-row button", has_text='Save Changes')).to_be_enabled()
    page.locator(".dashboard-actions-row button", has_text='Save Changes').click()
    print(f"Clicked 'Save Changes' button")
    expect(page.locator(".dashboard-actions-row button", has_text='Save Changes')).to_be_disabled()
    Util.refresh_page(page)
    expect(page.locator(".widget-card-chart highcharts-chart text", has_text="Application CPU Utilization").nth(0)).to_be_visible()
    po_o11y.reset_layout()
    expect(page.locator(".widget-card-chart highcharts-chart text", has_text="Application CPU Utilization").nth(0)).not_to_be_visible()

widget_test_data = [
    # level1_menu, level2_menu, middle_menu, chart_type, expected_selector, expected_text
    ("Integration General", None, "Application CPU Utilization (Kubernetes)", None, ".widget-card-chart highcharts-chart text", "Application CPU Utilization"),
    ("Integration General", None, "Application Memory Usage (Kubernetes)", None, ".widget-card-chart highcharts-chart text", "Application Memory Usage"),
    ("Integration General", None, "Application Request Counts (Kubernetes)", None, ".widget-card-chart highcharts-chart text", "Application Request Counts"),

    ("Flogo", "Activity", "Total Activity Executions", "Line Chart", ".widget-card-chart shared-line-chart highcharts-chart text", "Total Activity Executions"),

    ("Flogo", "Engine", "CPU Utilization/Limit Ratio", "Line Chart", ".widget-card-chart shared-line-chart highcharts-chart text", "CPU Utilization/Limit Ratio"),
    ("Flogo", "Engine", "CPU Utilization/Limit Ratio", "Treemap", ".widget-card-chart shared-treemap-chart highcharts-chart text", "CPU Utilization/Limit Ratio"),

    ("Flogo", "Flow", "Total Flow Executions", "Line Chart", ".widget-card-chart shared-line-chart highcharts-chart text", "Total Flow Executions"),
]
@pytest.mark.parametrize(
    "level1_menu, level2_menu, middle_menu, chart_type, selector, expected_text",
    widget_test_data
)
def test_add_widget_variants(setup_refresh_o11y, level1_menu, level2_menu, middle_menu, chart_type, selector, expected_text):
    page, po_o11y = setup_refresh_o11y
    po_o11y.add_widget(level1_menu, level2_menu, middle_menu, chart_type)
    expect(page.locator(selector, has_text=expected_text).nth(0)).to_be_visible()
