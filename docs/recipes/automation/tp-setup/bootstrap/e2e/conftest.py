import pytest
from pathlib import Path
from utils.util import Util
from page_object.po_auth import PageObjectAuth

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
