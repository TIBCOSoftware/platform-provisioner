#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary

from pathlib import Path
from utils.util import Util
from utils.env import ENV
from page_object.po_auth import PageObjectAuth
from page_object.po_o11y import PageObjectO11y

import pytest
from utils.helper import Helper

# TODO: this code should be moved when feature is released.
def pytest_collection_modifyitems(config, items):
    platform_base_version = Helper.get_cp_platform_base_version()

    for item in items:
        if "test_o11y_" in item.nodeid and "-custom-o11y" not in platform_base_version:
                item.add_marker(pytest.mark.skip(reason=f"Skipped due to CP platform version ({platform_base_version}) not containing '-custom-o11y'"))

@pytest.fixture(scope="session")
def browser_page():
    """
    Launches the browser once for the entire pytest session.
    All test functions will share the same browser instance.
    Suitable for test suites that don't require browser restarts.
    """
    page = Util.browser_launch()
    yield page
    Util.browser_close()

@pytest.fixture(scope="session")
def logged_in_page(browser_page):
    """
    Provides a logged-in page for each test function.

    1. Launches the app and performs login using PageObjectAuth.
    2. Ensures login succeeded using login_check().
    3. Automatically logs out after the test finishes.
    4. Captures a screenshot and raises an exception if login fails.
    """
    page = browser_page
    po_auth = PageObjectAuth(page)
    try:
        po_auth.login()
        po_auth.login_check()
        yield page
        po_auth.logout()
    except Exception as e:
        pytest.fail(f"Login failed: {e}", pytrace=True)
        current_filename = Path(__file__).stem
        Util.exit_error(f"Login failed: {e}", page, f"unhandled_error_{current_filename}.png")
        raise

@pytest.fixture(scope="function")
def setup_refresh_o11y(logged_in_page):
    def _setup_refresh_o11y(is_reset_layout=True):
        page = logged_in_page
        po_o11y = PageObjectO11y(page)
        po_o11y.goto_left_navbar_o11y()
        po_o11y.select_data_plane(ENV.TP_AUTO_K8S_DP_NAME)

        if is_reset_layout:
            Util.refresh_page(page)
            po_o11y.click_action_menu("Reset Layout")
        return page, po_o11y
    return _setup_refresh_o11y

@pytest.fixture
def add_custom_card(setup_refresh_o11y):
    def _add_custom_card(level1_menu, level2_menu, middle_menu, data_plane_type=None, is_click_filter=True, is_reset_layout=True):
        page, po_o11y = setup_refresh_o11y(is_reset_layout)
        po_o11y.add_widget(level1_menu, level2_menu, middle_menu, data_plane_type)
        if is_click_filter:
            po_o11y.click_widget_card_button(middle_menu, "Filters")
        page.wait_for_timeout(1000)
        return page, po_o11y
    return _add_custom_card
