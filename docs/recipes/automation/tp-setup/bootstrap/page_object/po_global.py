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
from utils.env import ENV
from utils.util import Util

class PageObjectGlobal:
    def __init__(self, page):
        self.page = page
        self.env = ENV
        self.is_fresco = False

    def goto_left_navbar(self, item_name):
        ColorLogger.info(f"Going to left side menu ...")
        self.page.locator(".nav-bar-pointer", has_text=item_name).wait_for(state="visible")
        self.page.locator(".nav-bar-pointer", has_text=item_name).click()
        print(f"Clicked left side menu '{item_name}'")
        self.page.wait_for_timeout(500)

    def detect_fresco_ui(self):
        ColorLogger.info("Detecting if the UI is using Fresco header...")
        if Util.check_dom_visibility(self.page, self.page.locator("tibco-header"), 1, 2):
            self.is_fresco = True
            ColorLogger.info("Fresco header UI detected.")
        else:
            ColorLogger.info("Fresco header UI not detected.")

    def selector_header_dp_name(self):
        return "tibco-header tibco-breadcrumbs .p-breadcrumb-item"

    def selector_header_app_name(self):
        return "tibco-header .header-title-readonly-text"

    def selector_header_action_menu(self):
        selector = "#app-details-menu-dropdown-label"
        if self.is_fresco:
            selector = "tibco-header .tibco-header-action-btn .pi-ellipsis-v"
        return selector

    def selector_header_action_menu_item(self):
        selector = ".pl-dropdown-menu__action"
        if self.is_fresco:
            selector = ".p-menu-item-label"
        return selector

    def selector_header_app_status_tooltip(self):
        selector = ".pl-tooltip__content:visible"
        if self.is_fresco:
            selector = ".p-tooltip-text:visible"
        return selector

    def selector_header_app_scale_input(self):
        return "tibco-header .tibco-header-scaling-field-group input.p-inputtext"

    def selector_header_app_action_btn(self):
        return "tibco-header .tibco-header-scaling-field-group .p-button:not([disabled])"

    def get_app_instance_number(self):
        input_value = 0
        try:
            self.page.locator(self.selector_header_app_scale_input()).wait_for(state="visible")
            input_value = self.page.locator(self.selector_header_app_scale_input()).input_value().strip()
            print(f"Get app instance number: {input_value}")
        except Exception as e:
            Util.warning_screenshot(f"Failed to get app instance number: {str(e)}", self.page, "get_app_instance_number.png")
        return int(input_value)

    def get_app_status(self):
        app_status = ""
        try:
            print(f"Wait for tooltip from Dom {self.selector_header_app_scale_input()}...")
            self.page.locator(self.selector_header_app_scale_input()).wait_for(state="visible")
            print(f"Mouseover to Dom {self.selector_header_app_scale_input()}...")
            self.page.locator(self.selector_header_app_scale_input()).focus()
            self.page.locator(self.selector_header_app_scale_input()).hover(force=True)
            self.page.locator(self.selector_header_app_scale_input()).dispatch_event("pointerover")
            self.page.locator(self.selector_header_app_scale_input()).dispatch_event("mouseover")
            self.page.wait_for_timeout(200)
            app_status = self.page.locator(self.selector_header_app_status_tooltip()).inner_text().split("\n")[0]
            app_status = re.sub("Status:", "", app_status, flags=re.IGNORECASE).strip()
            if app_status:
                print(f"Get app status: {app_status}")
        except Exception as e:
            Util.warning_screenshot(f"Failed to get app status: {str(e)}", self.page, "get_app_status.png")
        return app_status
