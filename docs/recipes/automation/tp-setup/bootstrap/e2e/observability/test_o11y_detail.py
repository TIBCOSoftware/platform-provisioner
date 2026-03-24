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

import re
from utils.color_logger import ColorLogger
from playwright.sync_api import expect

# this must be the first test in the file, and other tests should not depend on it
# all other tests is for the detail page
def test_custom_metrics_url(add_custom_card):
    card_name = "CPU Utilization/Request Percentage"
    # do not reset layout, To avoid affecting the refresh of action_buttons.py
    page, po_o11y = add_custom_card("Flogo", "Engine", card_name, None, False, False)

    po_o11y.click_widget_card_button(card_name, "Expand")
    detail_page_path = "/cp/metrics/custom_metrics"
    page.wait_for_url(f"**{detail_page_path}*")
    expect(page).to_have_url(re.compile(f".*{detail_page_path}.*"))
    ColorLogger.success(f"Click 'Expand' button, expect to see the custom metrics detail page")

    expect(page.locator('custom-metric-widget-detail .wdc-sub-header', has_text=card_name)).to_be_visible()
    ColorLogger.success(f"Expect to see header {card_name} on detail page")

def test_custom_metrics_page(browser_page):
    page = browser_page

    expect(page.locator('custom-metric-widget-detail highcharts-chart')).to_be_visible()
    expect(page.locator("custom-metric-widget-detail custom-metric-widget-detail-table table tbody .wdc-table-row")).to_have_count(1)
    ColorLogger.success(f"Expect to see Stock chart and Table list with data on detail page")
