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
# Regression tests for PCP-22537 — the Global o11y Metrics/Traces config step was
# flaky under peak install load. Two race fixes are covered:
#
#   1. _o11y_wait_toggle_system_config polls for the step to render via
#      Util.check_dom_visibility (longer, logged budget) instead of a single-shot
#      30s wait_for that timed out when the CP web UI was slow under deploy load —
#      and calls Util.exit_error (graceful screenshot) if it never renders.
#   2. o11y_config_table_add_or_select_item clicks the "Add ... configuration"
#      button via Util.click_button_until_enabled (wait for disabled -> enabled)
#      instead of a bare .click() that could fire before the button was enabled.
#
# PCP-22621 update: _o11y_wait_toggle_system_config now polls a STEP-LEVEL anchor
# (the step's Next/Save button, present whether or not the *ngIf system-config toggle
# renders) and returns a (toggle_present, toggle_enabled) tuple. The step-not-rendered
# exit_error is keyed off that anchor, and an absent toggle is a valid state (see
# test_po_o11y_global_resource_no_system_config_toggle.py for the Global-resource path).

from unittest.mock import MagicMock

import pytest

from page_object.po_dp_config import PageObjectDataPlaneConfiguration
from utils.util import Util
from utils.helper import Helper


def _new(cls):
    """Build a page object without running __init__ (no browser needed)."""
    obj = object.__new__(cls)
    obj.page = MagicMock()
    return obj


def _wire_toggle_locators(po, label_visible, toggle_visible=True, aria="true",
                          anchor_visible=True, anchor_selector="#go-to-traces-configuration"):
    """Route po.page.locator by selector so the step ANCHOR (Next/Save button, the
    render poll target), the toggle LABEL (presence probe) and the "#<toggle_id>"
    (enabled-state read) resolve to distinct mocks we can control independently."""
    anchor_mock = MagicMock(name="anchor")
    anchor_mock.is_visible.return_value = anchor_visible
    label_mock = MagicMock(name="label")
    label_mock.is_visible.return_value = label_visible
    toggle_mock = MagicMock(name="toggle")
    toggle_mock.is_visible.return_value = toggle_visible
    toggle_mock.get_attribute.return_value = aria

    def _locator(selector, *a, **k):
        if selector == anchor_selector:
            return anchor_mock
        if selector.startswith("label[for="):
            return label_mock
        return toggle_mock  # "#<toggle_id>"

    po.page.locator.side_effect = _locator
    return anchor_mock, label_mock, toggle_mock


class TestO11yWaitToggleSystemConfig:
    def test_polls_via_check_dom_visibility_when_not_yet_rendered(self, monkeypatch):
        po = _new(PageObjectDataPlaneConfiguration)

        seen = {}

        def fake_check_dom_visibility(page, locator, interval, max_wait):
            # Record that the polling helper (not a single-shot wait_for) was used,
            # with a budget longer than the old fixed 30s.
            seen["called"] = True
            seen["max_wait"] = max_wait
            return True

        monkeypatch.setattr(Util, "check_dom_visibility", staticmethod(fake_check_dom_visibility))
        # step anchor NOT yet visible -> must fall back to the polling helper (load case).
        # toggle present + checked once rendered.
        _wire_toggle_locators(po, label_visible=True, toggle_visible=True, aria="true",
                              anchor_visible=False)

        result = po._o11y_wait_toggle_system_config(
            "metrics-toggle-system-config", "#go-to-traces-configuration", "Metrics", "Global")

        assert result == (True, True)
        assert seen.get("called") is True
        # budget must exceed the old single-shot 30s that timed out under load
        assert seen["max_wait"] > 30
        # the polling wait must target the STEP ANCHOR selector (present in both cases),
        # not the *ngIf toggle itself.
        po.page.locator.assert_any_call("#go-to-traces-configuration")

    def test_fast_path_skips_polling_when_already_rendered(self, monkeypatch):
        po = _new(PageObjectDataPlaneConfiguration)

        seen = {"called": False}

        def fake_check_dom_visibility(*a, **k):
            seen["called"] = True
            return True

        monkeypatch.setattr(Util, "check_dom_visibility", staticmethod(fake_check_dom_visibility))
        # anchor already visible -> fast path, no up-front check_dom_visibility sleep
        _wire_toggle_locators(po, label_visible=True, toggle_visible=True, aria="true",
                              anchor_visible=True)

        result = po._o11y_wait_toggle_system_config(
            "metrics-toggle-system-config", "#go-to-traces-configuration", "Metrics", "Global")

        assert result == (True, True)
        assert seen["called"] is False  # polling (and its ~3s sleep) was skipped

    def test_returns_false_when_toggle_not_checked(self, monkeypatch):
        po = _new(PageObjectDataPlaneConfiguration)
        monkeypatch.setattr(Util, "check_dom_visibility", staticmethod(lambda *a, **k: True))
        # toggle present but not checked (aria=false) -> (present, not enabled)
        _wire_toggle_locators(po, label_visible=True, toggle_visible=True, aria="false",
                              anchor_visible=True, anchor_selector="#save-observability")

        result = po._o11y_wait_toggle_system_config(
            "traces-toggle-system-config", "#save-observability", "Traces", "Global")

        assert result == (True, False)

    def test_exit_error_when_step_never_renders(self, monkeypatch):
        po = _new(PageObjectDataPlaneConfiguration)
        # Simulate the load-induced race: the step ANCHOR never becomes visible.
        monkeypatch.setattr(Util, "check_dom_visibility", staticmethod(lambda *a, **k: False))
        _wire_toggle_locators(po, label_visible=False, anchor_visible=False)
        exit_calls = {}

        # The real Util.exit_error calls sys.exit(1); mirror that so the test also
        # proves control flow halts (no fall-through to the toggle-state read).
        def fake_exit_error(message, page, screenshot):
            exit_calls["message"] = message
            raise SystemExit(1)

        monkeypatch.setattr(Util, "exit_error", staticmethod(fake_exit_error))

        with pytest.raises(SystemExit):
            po._o11y_wait_toggle_system_config(
                "metrics-toggle-system-config", "#go-to-traces-configuration", "Metrics", "Global")

        # Must fail gracefully via exit_error (screenshot) naming the step, not silently.
        assert "Metrics" in exit_calls.get("message", "")


class TestAddOrSelectWaitsForEnabled:
    def test_add_new_item_clicks_via_click_button_until_enabled(self, monkeypatch):
        po = _new(PageObjectDataPlaneConfiguration)

        monkeypatch.setattr(Helper, "get_o11y_sub_name_input", staticmethod(lambda *a, **k: "metrics-qs"))
        # Item not present in the table -> take the "add" branch.
        monkeypatch.setattr(Util, "check_dom_visibility", staticmethod(lambda *a, **k: False))
        po.o11y_new_resource_fill_form = MagicMock()

        enable_clicks = []

        def fake_click_until_enabled(page, button_locator):
            enable_clicks.append(button_locator)

        monkeypatch.setattr(Util, "click_button_until_enabled", staticmethod(fake_click_until_enabled))

        po.o11y_config_table_add_or_select_item(
            "Global", "Metrics", "Query Service", "", "#add-metrics-proxy-btn"
        )

        # Regression: before the fix the add button was a bare .click(); now it must
        # go through click_button_until_enabled (waits for disabled -> enabled).
        assert len(enable_clicks) == 1
        po.page.locator.assert_any_call("#add-metrics-proxy-btn")
        po.o11y_new_resource_fill_form.assert_called_once()
