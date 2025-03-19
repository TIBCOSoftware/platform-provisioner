from pathlib import Path
from utils.util import Util
from utils.env import ENV
from page_object.po_auth import PageObjectAuth
from page_object.po_dataplane import PageObjectDataPlane
from page_object.po_dp_config import PageObjectDataPlaneConfiguration
import pytest
from playwright.sync_api import expect

@pytest.fixture(scope="session")
def setup_browser():
    page = Util.browser_launch()
    try:
        po_auth = PageObjectAuth(page)
        po_auth.login()
        po_auth.login_check()

        po_dp = PageObjectDataPlane(page)
        po_dp_config = PageObjectDataPlaneConfiguration(page)
        po_dp.goto_dataplane(ENV.TP_AUTO_K8S_DP_NAME)
        po_dp_config.goto_dataplane_config()
        po_dp_config.goto_dataplane_config_sub_menu("Observability", "Logs")

        page.locator(".proxies-exporters-list .pl-secondarynav__menu .pl-secondarynav__link", has_text="Exporter configurations").wait_for(state="visible")
        page.locator(".proxies-exporters-list .pl-secondarynav__menu .pl-secondarynav__link", has_text="Exporter configurations").click()
        print(f"Clicked 'Exporter configurations' tab menu")

        yield page, po_dp_config, po_auth
        po_auth.logout()
    except Exception as e:
        pytest.fail(f"Unhandled error: {e}", pytrace=True)
        current_filename = Path(__file__).stem
        Util.exit_error(f"Unhandled error: {e}", page, f"unhandled_error_{current_filename}.png")
    Util.browser_close()

@pytest.fixture(scope="function", autouse=True)
def setup_exporter_configuration(setup_browser):
    page, po_dp_config, _ = setup_browser

    print(f"Setup 'Exporter configurations' dialog")
    page.locator("#exporter-configurations .configuration-btn", has_text="Add").nth(0).wait_for(state="visible")
    page.locator("#exporter-configurations .configuration-btn", has_text="Add").nth(0).click()
    print(f"Clicked 'User Apps' Add button")

    print(f"Waiting for 'Logs server' dialog popup")
    page.locator("configuration-modal .pl-modal").wait_for(state="visible")
    print(f"'Logs server' dialog popup")

    page.locator("configuration-modal input.pl-select__control").click()
    print(f"Clicked 'Exporter type' dropdown")
    page.locator("configuration-modal .pl-select-menu__item", has_text="ElasticSearch").wait_for(state="visible")
    page.locator("configuration-modal .pl-select-menu__item", has_text="ElasticSearch").click()
    print(f"Selected 'ElasticSearch' in 'Exporter type' dropdown")
    page.locator("#endpoint-input").wait_for(state="visible")
    expect(page.locator("configuration-modal .test-connection button")).to_be_visible()
    print(f"'Test Connection' button is visible")

    return page, po_dp_config

def test_connection_success(setup_exporter_configuration):
    page, po_dp_config = setup_exporter_configuration
    print(f"Filling ElasticSearch form...")
    po_dp_config.o11y_fill_prometheus_or_elastic("ElasticSearch", ENV.TP_AUTO_ELASTIC_URL, ENV.TP_AUTO_ELASTIC_USER, ENV.TP_AUTO_ELASTIC_PASSWORD)
    page.locator("configuration-modal .test-connection button").click()
    print(f"Clicked 'Test Connection' button")
    expect(page.locator("configuration-modal .test-connection-success")).to_be_visible()
    page.locator("configuration-modal .pl-modal__footer-left button", has_text="Cancel").click()
    print(f"Clicked 'Cancel' button")

def test_connection_failure(setup_exporter_configuration):
    page, po_dp_config= setup_exporter_configuration
    print(f"Filling ElasticSearch form...")
    po_dp_config.o11y_fill_prometheus_or_elastic("ElasticSearch", ENV.TP_AUTO_ELASTIC_URL, ENV.TP_AUTO_ELASTIC_USER, "wrong password")
    page.locator("configuration-modal .test-connection button").click()
    print(f"Clicked 'Test Connection' button")
    expect(page.locator("configuration-modal .test-connection-failure")).to_be_visible()
    page.locator("configuration-modal .pl-modal__footer-left button", has_text="Cancel").click()
    print(f"Clicked 'Cancel' button")
