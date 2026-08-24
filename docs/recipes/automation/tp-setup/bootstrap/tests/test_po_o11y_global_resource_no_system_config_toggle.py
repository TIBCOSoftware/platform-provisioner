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
# Regression tests for PCP-22621 — the DP o11y config automation failed
# deterministically (3/3 attempts) while creating the *Global* observability
# resource, aborting with:
#   [ERROR] Data Plane 'Global' Observability Metrics step did not render
#           (toggle 'metrics-toggle-system-config' not visible after waiting).
#
# Root cause (automation bug, NOT a web-ui bug): the CP web-ui renders the
# "System Config" toggle only `*ngIf="isMetricsTabHasSystemConfig()"` (resp.
# traces) — i.e. only when every metrics/traces service type has an inheritable
# is_system_config item. When creating the Global (= system) resource itself there
# is nothing to inherit, so the toggle is hidden BY DESIGN. The old
# _o11y_wait_toggle_system_config polled for that toggle directly and hard-failed
# (Util.exit_error) on the Global path.
#
# The fix: _o11y_wait_toggle_system_config now polls a STEP-LEVEL anchor (the step's
# Next/Save button, present whether or not the toggle renders) and returns a
# (toggle_present, toggle_enabled) tuple. When the toggle is ABSENT the caller takes
# the manual-configure branch (Query Service + Exporter) instead of aborting — even
# when TP_AUTO_DATA_PLANE_O11Y_SYSTEM_CONFIG is true (there is no system config to
# inherit, so manual is the only correct path).
#
# These tests pin that contract on the deterministic MagicMock-page path (no
# browser), following the sibling suites' object.__new__ + MagicMock pattern.

from unittest.mock import MagicMock, call

import pytest

from page_object.po_dp_config import PageObjectDataPlaneConfiguration
from utils.util import Util
from utils.env import ENV

DP_NAME = "k8s-auto-dp1"

# The Metrics/Traces branch logic is dp_name-independent; the Global-resource
# condition is simulated by an ABSENT system-config toggle (the (present, enabled)
# tuple returned by the stubbed _o11y_wait_toggle_system_config), not by the wizard
# navigation path — mirroring the sibling render-race suite's pragmatic setup.


def _new():
    """Build the page object without running __init__ (no real browser/page)."""
    po = object.__new__(PageObjectDataPlaneConfiguration)
    po.page = MagicMock()
    return po


# --------------------------------------------------------------------------
# Helper-level: an absent toggle is a valid state (no exit_error, no poll).
# --------------------------------------------------------------------------

class TestWaitToggleReportsAbsence:
    def test_absent_toggle_returns_not_present_without_exit_error(self, monkeypatch):
        """Step anchor visible (step rendered) but the *ngIf toggle is absent ->
        returns (False, False) and must NOT call Util.exit_error or poll."""
        po = _new()

        poll_calls = {"count": 0}

        def fake_check_dom_visibility(*a, **k):
            poll_calls["count"] += 1
            return True

        monkeypatch.setattr(Util, "check_dom_visibility", staticmethod(fake_check_dom_visibility))

        def _no_exit(*a, **k):
            raise AssertionError(f"unexpected Util.exit_error: {a}")

        monkeypatch.setattr(Util, "exit_error", staticmethod(_no_exit))

        anchor_mock = MagicMock(name="anchor")
        anchor_mock.is_visible.return_value = True   # step rendered
        label_mock = MagicMock(name="label")
        label_mock.is_visible.return_value = False   # toggle *ngIf-hidden (Global resource)

        def _locator(selector, *a, **k):
            if selector == "#go-to-traces-configuration":
                return anchor_mock
            if selector.startswith("label[for="):
                return label_mock
            return MagicMock()  # "#<toggle_id>" — never reached when absent

        po.page.locator.side_effect = _locator

        result = po._o11y_wait_toggle_system_config(
            "metrics-toggle-system-config", "#go-to-traces-configuration", "Metrics", "Global")

        assert result == (False, False)
        # anchor already visible -> fast path, no polling
        assert poll_calls["count"] == 0


# --------------------------------------------------------------------------
# Call-site: o11y_config_dataplane_resource must take the manual-configure branch
# when the toggle is absent (the Global-resource path), regardless of the env flag.
# --------------------------------------------------------------------------

def _drive_resource(po, monkeypatch, system_config_env, wait_return, exit_error_fn=None):
    """Run o11y_config_dataplane_resource with the Logs-step + toggle-wait helpers
    stubbed, so we can assert only the Metrics/Traces branch behavior. Returns nothing;
    inspect the recorded mocks on `po`. `exit_error_fn` overrides the Util.exit_error
    stub (default: fail the test if exit_error is unexpectedly called)."""
    po.goto_dataplane_config_sub_menu = MagicMock()
    po.o11y_get_new_resource = MagicMock(
        return_value=MagicMock(is_visible=MagicMock(return_value=True)))
    po._o11y_enable_toggle_and_add = MagicMock()          # Logs (5x) + Metrics/Traces exporters
    po.o11y_config_table_add_or_select_item = MagicMock()  # the direct Metrics Query Service add
    po._o11y_wait_toggle_system_config = MagicMock(return_value=wait_return)

    monkeypatch.setattr("page_object.po_dp_config.ReportYaml.get_dataplane_info", lambda *a, **k: "")
    monkeypatch.setattr("page_object.po_dp_config.ReportYaml.set_dataplane_info", lambda *a, **k: None)
    monkeypatch.setattr("page_object.po_dp_config.Util.check_dom_visibility", lambda *a, **k: True)
    monkeypatch.setattr("page_object.po_dp_config.Util.warning_screenshot", lambda *a, **k: None)

    def _no_exit(*a, **k):
        raise AssertionError(f"unexpected Util.exit_error: {a}")

    monkeypatch.setattr("page_object.po_dp_config.Util.exit_error", exit_error_fn or _no_exit)
    monkeypatch.setattr(type(ENV), "TP_AUTO_IS_CONFIG_O11Y", True)
    monkeypatch.setattr(type(ENV), "TP_AUTO_DATA_PLANE_O11Y_SYSTEM_CONFIG", system_config_env)

    po.o11y_config_dataplane_resource(DP_NAME)


@pytest.mark.parametrize("system_config_env", [True, False])
def test_absent_toggle_takes_manual_branch(monkeypatch, system_config_env):
    """THE PCP-22621 regression: with the system-config toggle ABSENT (Global
    resource), the Metrics + Traces steps must configure manually and must NOT call
    exit_error — even when TP_AUTO_DATA_PLANE_O11Y_SYSTEM_CONFIG is true.

    This pins the CORRECTED call-site truth table (it stubs the toggle-wait helper to
    report the toggle absent, so it does not itself re-run the old helper's poll). The
    real helper's no-exit-on-absent-toggle behavior — the actual root-cause fix — is
    exercised by TestWaitToggleReportsAbsence below with the un-stubbed helper."""
    po = _new()
    _drive_resource(po, monkeypatch, system_config_env, wait_return=(False, False))

    # anchor selectors threaded into both step waits
    assert po._o11y_wait_toggle_system_config.call_args_list == [
        call("metrics-toggle-system-config", "#go-to-traces-configuration", "Metrics", DP_NAME),
        call("traces-toggle-system-config", "#save-observability", "Traces", DP_NAME),
    ]

    # Metrics -> Query Service configured directly (manual branch entered)
    po.o11y_config_table_add_or_select_item.assert_any_call(
        DP_NAME, "Metrics", "Query Service", "", "#add-metrics-proxy-btn")

    # Manual exporters added: Logs (5) + Metrics exporter (1) + Traces proxy/exporter (2) = 8
    assert po._o11y_enable_toggle_and_add.call_count == 8
    manual_metrics_traces = [
        call("label[for='metrics-exporter-toggle']", "Exporter", "#add-metrics-exporter-btn", DP_NAME, "Metrics", ""),
        call("label[for='traces-proxy']", "Query Service", "#add-traces-proxy-btn", DP_NAME, "Traces", ""),
        call("label[for='traces-exporter']", "Exporter", "#add-traces-exporter-btn", DP_NAME, "Traces", ""),
    ]
    for expected in manual_metrics_traces:
        assert expected in po._o11y_enable_toggle_and_add.call_args_list


def test_present_enabled_toggle_uses_system_config_no_manual_add(monkeypatch):
    """Backward compat: when the toggle IS present and enabled and the env flag is
    true (DP-level resource with an inheritable system config), the Metrics/Traces
    steps use the system config — no direct Metrics Query Service add, and only the
    5 Logs-step toggle+add calls run (metrics exporter + 2 traces calls are skipped)."""
    po = _new()
    _drive_resource(po, monkeypatch, system_config_env=True, wait_return=(True, True))

    # System-config path taken -> the direct Metrics Query Service add never runs.
    po.o11y_config_table_add_or_select_item.assert_not_called()
    # Only the 5 Logs-step sections go through the toggle+add helper.
    assert po._o11y_enable_toggle_and_add.call_count == 5


def test_present_but_not_enabled_env_true_exits(monkeypatch):
    """Backward compat: env flag true + toggle PRESENT but NOT enabled (DP-level
    resource where the system config exists but the toggle is off) -> the Metrics step
    must exit_error (it cannot silently manual-configure a resource that is supposed to
    inherit). Pins the `env=true, present, not-enabled` branch the reviewers flagged as
    untested."""
    po = _new()
    exits = {}

    def _exit(message, page, screenshot):
        exits["message"] = message
        raise SystemExit(1)

    with pytest.raises(SystemExit):
        _drive_resource(po, monkeypatch, system_config_env=True,
                        wait_return=(True, False), exit_error_fn=_exit)

    # Halted at the Metrics step's exit_error (present-but-not-enabled), not silently manual.
    assert "Step 2" in exits.get("message", "")
    po.o11y_config_table_add_or_select_item.assert_not_called()


def test_present_enabled_env_false_clicks_toggle_off_then_manual(monkeypatch):
    """Backward compat: env flag false + toggle PRESENT and enabled -> the code must
    turn the system-config toggle OFF (click its label) and then manual-configure.
    Pins the `env=false, present, enabled -> toggle-off` branch the reviewers flagged
    as untested."""
    po = _new()
    _drive_resource(po, monkeypatch, system_config_env=False, wait_return=(True, True))

    # Toggle-off clicks issued for both Metrics and Traces system-config labels.
    po.page.locator.assert_any_call("label[for='metrics-toggle-system-config']")
    po.page.locator.assert_any_call("label[for='traces-toggle-system-config']")
    # Manual path fully taken: Logs (5) + Metrics exporter (1) + Traces proxy/exporter (2) = 8.
    assert po._o11y_enable_toggle_and_add.call_count == 8
    po.o11y_config_table_add_or_select_item.assert_any_call(
        DP_NAME, "Metrics", "Query Service", "", "#add-metrics-proxy-btn")
