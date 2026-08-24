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
# Regression tests for PCP-22010 — create_global_config wizard skipped mandatory
# "Add" steps because of a toggle-guard race.
#
# Root cause: every "toggle a section on, then add its config" block used two
# INDEPENDENT `if`s:
#     if locator(toggle, has_text="X disabled").is_visible():
#         locator(toggle).click()                          # enable the section
#     if locator(toggle, has_text="X enabled").is_visible():  # RACE
#         self.o11y_config_table_add_or_select_item(...)
# `is_visible()` is an instant check (no auto-wait). Right after clicking the
# toggle ON, the label has not re-rendered from "... disabled" to "... enabled"
# yet, so the second `if` read False and the whole add block was silently skipped
# -> Global Resource never assembled -> Next stayed disabled -> wizard timeout.
#
# The fix (_o11y_enable_toggle_and_add): enable the toggle if disabled, then
# AUTO-WAIT for the 'enabled' label to actually render (wait_for, not is_visible),
# then add UNCONDITIONALLY so a real failure surfaces instead of being skipped.
#
# These tests pin that contract on the deterministic MagicMock-page path (no
# browser), following the sibling suites' object.__new__ + MagicMock pattern.

from unittest.mock import MagicMock, call

from page_object.po_dp_config import PageObjectDataPlaneConfiguration
from utils.env import ENV

DP_NAME = "k8s-auto-dp1"


def _new():
    """Build the page object without running __init__ (no real browser/page)."""
    po = object.__new__(PageObjectDataPlaneConfiguration)
    po.page = MagicMock()
    return po


def _install_locator_router(po, disabled_visible, enabled_mock=None):
    """Route self.page.locator(...) to distinct mocks by how the helper queries it:
      - locator(selector)                        -> the toggle element (wait_for/click)
      - locator(selector, has_text="X disabled") -> the 'disabled' label (is_visible)
      - locator(selector, has_text="X enabled")  -> the 'enabled' label  (wait_for)
    """
    toggle_mock = MagicMock(name="toggle")
    disabled_mock = MagicMock(name="disabled-label")
    disabled_mock.is_visible.return_value = disabled_visible
    enabled_mock = enabled_mock or MagicMock(name="enabled-label")

    def router(selector, has_text=None):
        if has_text is None:
            return toggle_mock
        if "disabled" in has_text:
            return disabled_mock
        if "enabled" in has_text:
            return enabled_mock
        return MagicMock()

    po.page.locator.side_effect = router
    return toggle_mock, disabled_mock, enabled_mock


def test_disabled_toggle_is_enabled_then_added():
    """A section that starts disabled: click to enable, wait for the 'enabled'
    label, then add with the exact threaded args."""
    po = _new()
    toggle, _disabled, enabled = _install_locator_router(po, disabled_visible=True)
    po.o11y_config_table_add_or_select_item = MagicMock()

    po._o11y_enable_toggle_and_add(
        "label[for='services-exporter-toggle']", "Exporter",
        "#add-services-exporter-btn", DP_NAME, "Logs", "Services Exporter")

    toggle.wait_for.assert_called_once_with(state="visible")
    toggle.click.assert_called_once()
    enabled.wait_for.assert_called_once_with(state="visible")
    po.o11y_config_table_add_or_select_item.assert_called_once_with(
        DP_NAME, "Logs", "Exporter", "Services Exporter", "#add-services-exporter-btn")


def test_add_called_unconditionally_even_when_enabled_label_races():
    """THE PCP-22010 regression: right after enabling, the 'enabled' label has not
    re-rendered yet (is_visible() would read False — what the OLD racy guard saw).
    The fix auto-waits for it and adds UNCONDITIONALLY, so the add is NEVER skipped
    and is NOT gated on the racy is_visible()."""
    po = _new()
    enabled = MagicMock(name="enabled-label")
    enabled.is_visible.return_value = False  # the race the old guard tripped on
    toggle, _disabled, _ = _install_locator_router(
        po, disabled_visible=True, enabled_mock=enabled)
    po.o11y_config_table_add_or_select_item = MagicMock()

    po._o11y_enable_toggle_and_add(
        "label[for='services-exporter-toggle']", "Exporter",
        "#add-services-exporter-btn", DP_NAME, "Logs", "Services Exporter")

    # The fix waits for the 'enabled' state instead of an instant is_visible() guard...
    enabled.wait_for.assert_called_once_with(state="visible")
    # ...and adds unconditionally despite is_visible() being False (old code skipped here).
    po.o11y_config_table_add_or_select_item.assert_called_once()
    # Regression guard: the add must NOT depend on the 'enabled' label's is_visible().
    enabled.is_visible.assert_not_called()


def test_already_enabled_toggle_not_clicked_but_still_added():
    """A section enabled by default (e.g. User Apps): no toggle click, but the add
    still runs (the old code happened to work here — this pins it stays working)."""
    po = _new()
    toggle, _disabled, enabled = _install_locator_router(po, disabled_visible=False)
    po.o11y_config_table_add_or_select_item = MagicMock()

    po._o11y_enable_toggle_and_add(
        "label[for='userapp-proxy']", "Query Service",
        "#add-userapp-proxy-btn", DP_NAME, "Logs", "Query Service")

    toggle.click.assert_not_called()
    enabled.wait_for.assert_called_once_with(state="visible")
    po.o11y_config_table_add_or_select_item.assert_called_once_with(
        DP_NAME, "Logs", "Query Service", "Query Service", "#add-userapp-proxy-btn")


def test_create_global_config_wraps_all_eight_toggle_sections(monkeypatch):
    """Call-site matrix regression: o11y_config_dataplane_resource must route ALL 8
    toggle+add sections through the helper, in order, with the EXACT
    (toggle_selector, tab_name, add_button_selector, dp_name, menu_name, tab_sub_name)
    tuple each one had before the refactor. Guards against a swapped selector / sub-name
    / add-button at any single site — the whole value of the fix is that every section
    gets assembled. Drives the method with a MagicMock page (no browser); the helper and
    the direct (non-toggle) Metrics Query Service add are stubbed to record calls."""
    po = _new()
    po.goto_dataplane_config_sub_menu = MagicMock()
    # 'Add new resource' button present -> proceed past the "already configured" return.
    po.o11y_get_new_resource = MagicMock(
        return_value=MagicMock(is_visible=MagicMock(return_value=True)))
    po._o11y_enable_toggle_and_add = MagicMock()          # record every toggle+add call
    po.o11y_config_table_add_or_select_item = MagicMock()  # the direct Metrics Query Service add

    monkeypatch.setattr("page_object.po_dp_config.ReportYaml.get_dataplane_info", lambda *a, **k: "")
    monkeypatch.setattr("page_object.po_dp_config.ReportYaml.set_dataplane_info", lambda *a, **k: None)
    monkeypatch.setattr("page_object.po_dp_config.Util.check_dom_visibility", lambda *a, **k: True)
    monkeypatch.setattr("page_object.po_dp_config.Util.warning_screenshot", lambda *a, **k: None)

    def _no_exit(*a, **k):
        raise AssertionError(f"unexpected Util.exit_error: {a}")

    monkeypatch.setattr("page_object.po_dp_config.Util.exit_error", _no_exit)
    # class-level attributes (no dataclass annotation) — patch on the class so ENV sees it.
    monkeypatch.setattr(type(ENV), "TP_AUTO_IS_CONFIG_O11Y", True)
    monkeypatch.setattr(type(ENV), "TP_AUTO_DATA_PLANE_O11Y_SYSTEM_CONFIG", False)

    po.o11y_config_dataplane_resource(DP_NAME)

    expected = [
        call("label[for='userapp-proxy']", "Query Service", "#add-userapp-proxy-btn", DP_NAME, "Logs", "Query Service"),
        call("label[for='userapp-exporter']", "Exporter", "#add-userapp-exporter-btn", DP_NAME, "Logs", "User Apps Exporter"),
        call("label[for='services-exporter-toggle']", "Exporter", "#add-services-exporter-btn", DP_NAME, "Logs", "Services Exporter"),
        call("label[for='auditsafe-proxy']", "Query Service", "#add-auditsafe-query-service-btn", DP_NAME, "Logs", "Business Activities Query Service"),
        call("label[for='auditsafe-services-exporter']", "Exporter", "#add-auditsafe-services-exporter-btn", DP_NAME, "Logs", "Business Activities Exporter"),
        call("label[for='metrics-exporter-toggle']", "Exporter", "#add-metrics-exporter-btn", DP_NAME, "Metrics", ""),
        call("label[for='traces-proxy']", "Query Service", "#add-traces-proxy-btn", DP_NAME, "Traces", ""),
        call("label[for='traces-exporter']", "Exporter", "#add-traces-exporter-btn", DP_NAME, "Traces", ""),
    ]
    assert po._o11y_enable_toggle_and_add.call_count == 8
    assert po._o11y_enable_toggle_and_add.call_args_list == expected
