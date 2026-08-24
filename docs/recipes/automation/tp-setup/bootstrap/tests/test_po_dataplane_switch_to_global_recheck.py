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
# PCP-23558 — switch_to_global_config's "Double Check" reported a false negative on the
# fresh-data-plane path ('Use Global Resource' -> 'Link'):
#
#   Clicking Link takes the UI back to the data planes LIST page, where
#   ".o11y-panel-actions .global-resource-name" does not exist. The check polled with
#   is_refresh=True, and Util.refresh_page() reloads whatever page we are on — the list —
#   so all six reloads printed .../data-planes?page=1 and the check could only ever time
#   out, on a link that had in fact succeeded.
#
# Deterministic, not flaky. It turned fatal with PCP-23553's _assert_o11y_recorded, whose
# RuntimeError then skipped the DP activation upload (see test_po_cli_o11y_via_ui.py).
#
# The fix: re-OPEN the DP's Observability panel and poll it (a fresh backend read, since
# the link is applied server-side a few seconds later), never reload the current page.

from unittest.mock import MagicMock

import pytest

from page_object.po_bmdp_config import PageObjectBMDPConfiguration
from page_object.po_dp_config import PageObjectDataPlaneConfiguration
from page_object import po_dataplane
from utils.util import Util

DP_NAME = "k8s-auto-dp1"
LINKED_SELECTOR = ".o11y-panel-actions .global-resource-name"
LEGACY_SWITCH_SELECTOR = ".switch-to-global"
USE_GLOBAL_SELECTOR = ".use-global-resource .o11y-btn"


def _new(cls):
    """Build a page object without running __init__ (no browser needed)."""
    obj = object.__new__(cls)
    obj.page = MagicMock()
    return obj


def _wire(po):
    """Tag every locator mock with the selector it was created from, so the fake
    check_dom_visibility below can answer per selector."""
    mocks = {}

    def _locator(selector, *a, **k):
        mock = mocks.setdefault(selector, MagicMock(name=selector))
        mock.selector_under_test = selector
        return mock

    po.page.locator.side_effect = _locator
    return mocks


def _install_fake_visibility(monkeypatch, linked_from_attempt, legacy_cp=False):
    """Fake Util.check_dom_visibility, with the linked marker appearing only from the
    `linked_from_attempt`-th probe of it (1-based; 0 = never). Records every call so the
    test can assert nothing polled with a reload.

    `legacy_cp=False` models a current CP taking the fresh-DP 'Use Global Resource'
    branch; `legacy_cp=True` models a pre-1.5 CP where '.switch-to-global' is present.
    """
    calls = []
    linked_probes = {"n": 0}

    def fake_check_dom_visibility(page, locator, interval=10, max_wait=180, is_refresh=False):
        selector = getattr(locator, "selector_under_test", None)
        calls.append({"selector": selector, "is_refresh": is_refresh})
        if selector == LINKED_SELECTOR:
            linked_probes["n"] += 1
            return bool(linked_from_attempt) and linked_probes["n"] >= linked_from_attempt
        if selector == LEGACY_SWITCH_SELECTOR:
            return legacy_cp
        if selector == USE_GLOBAL_SELECTOR:
            return not legacy_cp
        return False

    monkeypatch.setattr(Util, "check_dom_visibility", staticmethod(fake_check_dom_visibility))
    return calls


def _arrange(monkeypatch, cls, linked_from_attempt, legacy_cp=False):
    po = _new(cls)
    _wire(po)
    calls = _install_fake_visibility(monkeypatch, linked_from_attempt, legacy_cp)
    report = MagicMock()
    monkeypatch.setattr(po_dataplane, "ReportYaml", report)
    po.goto_dataplane_o11y_config = MagicMock(name="goto_dataplane_o11y_config")
    return po, calls, report


def _assert_never_reloaded(calls):
    reloaded = [c["selector"] for c in calls if c["is_refresh"]]
    assert not reloaded, (
        "the link check must never poll with is_refresh=True: refresh_page() reloads the "
        f"page we are on (the data planes list after 'Link'), not the o11y panel {reloaded}"
    )


class TestDoubleCheckReopensTheO11yPanel:
    def test_link_confirmed_after_reopening_the_panel(self, monkeypatch):
        # PreCheck (probe 1) misses — the DP is not linked yet. The double check then
        # re-opens the panel and finds the marker on its first probe there (probe 2).
        po, calls, report = _arrange(monkeypatch, PageObjectDataPlaneConfiguration, linked_from_attempt=2)

        po.switch_to_global_config(DP_NAME)

        po.goto_dataplane_o11y_config.assert_called_once_with(DP_NAME)
        report.set_dataplane_info.assert_called_once_with(DP_NAME, "switchGlobal", True)
        _assert_never_reloaded(calls)

    def test_precheck_short_circuits_without_navigating(self, monkeypatch):
        # Already linked (re-run): the panel is open, the marker is right there.
        po, calls, report = _arrange(monkeypatch, PageObjectDataPlaneConfiguration, linked_from_attempt=1)

        po.switch_to_global_config(DP_NAME)

        po.goto_dataplane_o11y_config.assert_not_called()
        report.set_dataplane_info.assert_called_once_with(DP_NAME, "switchGlobal", True)
        _assert_never_reloaded(calls)

    def test_retries_the_reopen_while_the_backend_catches_up(self, monkeypatch):
        # Linking is applied server-side a few seconds later, so a stale panel would keep
        # saying "not linked" however long we polled it — each retry must re-navigate.
        po, calls, report = _arrange(monkeypatch, PageObjectDataPlaneConfiguration, linked_from_attempt=3)

        po.switch_to_global_config(DP_NAME)

        assert po.goto_dataplane_o11y_config.call_count == 2
        report.set_dataplane_info.assert_called_once_with(DP_NAME, "switchGlobal", True)
        _assert_never_reloaded(calls)

    def test_genuine_failure_is_still_reported_as_failure(self, monkeypatch):
        po, calls, report = _arrange(monkeypatch, PageObjectDataPlaneConfiguration, linked_from_attempt=0)

        po.switch_to_global_config(DP_NAME)

        assert po.goto_dataplane_o11y_config.call_count == 3      # all rounds exhausted
        report.set_dataplane_info.assert_not_called()             # nothing claimed
        _assert_never_reloaded(calls)

    def test_legacy_switch_to_global_branch_still_confirms(self, monkeypatch):
        """Old CP versions render '.switch-to-global' instead of 'Use Global Resource'
        (CLAUDE.md: never drop support for an old selector). The re-check is shared by
        both branches, so it must confirm the legacy one too."""
        po, calls, report = _arrange(monkeypatch, PageObjectDataPlaneConfiguration,
                                     linked_from_attempt=2, legacy_cp=True)

        po.switch_to_global_config(DP_NAME)

        po.page.locator.assert_any_call(LEGACY_SWITCH_SELECTOR)      # legacy branch taken
        po.goto_dataplane_o11y_config.assert_called_once_with(DP_NAME)
        report.set_dataplane_info.assert_called_once_with(DP_NAME, "switchGlobal", True)
        _assert_never_reloaded(calls)

    def test_bmdp_shares_the_same_recheck(self, monkeypatch):
        """BMDP inherits switch_to_global_config, and its o11y panel is reached the same
        way — the fix must cover it without a second implementation."""
        po, calls, report = _arrange(monkeypatch, PageObjectBMDPConfiguration, linked_from_attempt=2)

        po.switch_to_global_config(DP_NAME)

        po.goto_dataplane_o11y_config.assert_called_once_with(DP_NAME)
        report.set_dataplane_info.assert_called_once_with(DP_NAME, "switchGlobal", True)
        _assert_never_reloaded(calls)


class TestRecheckIsolatesNavigationFailures:
    """Re-navigating is a far bigger failure surface than the page.reload() it replaced
    (raised by all three cross-reviewers). A bad round must cost one round, not the run."""

    @pytest.mark.parametrize("boom", [SystemExit(1), RuntimeError("playwright timeout")])
    def test_a_failed_round_does_not_cancel_the_remaining_rounds(self, monkeypatch, boom):
        po, calls, report = _arrange(monkeypatch, PageObjectDataPlaneConfiguration, linked_from_attempt=2)
        # Round 1's navigation blows up; rounds 2-3 must still run, and round 2 confirms.
        po.goto_dataplane_o11y_config = MagicMock(side_effect=[boom, None, None])

        po.switch_to_global_config(DP_NAME)

        assert po.goto_dataplane_o11y_config.call_count == 2
        report.set_dataplane_info.assert_called_once_with(DP_NAME, "switchGlobal", True)

    @pytest.mark.parametrize("boom", [SystemExit(1), RuntimeError("playwright timeout")])
    def test_navigation_that_never_recovers_warns_instead_of_aborting_the_run(self, monkeypatch, boom):
        """Util.exit_error() -> sys.exit(1) is a BaseException. Unisolated it would abort
        the whole browser-mode run, where the pre-PCP-23558 check merely warned."""
        po, calls, report = _arrange(monkeypatch, PageObjectDataPlaneConfiguration, linked_from_attempt=0)
        po.goto_dataplane_o11y_config = MagicMock(side_effect=boom)

        po.switch_to_global_config(DP_NAME)          # must not propagate

        assert po.goto_dataplane_o11y_config.call_count == 3
        report.set_dataplane_info.assert_not_called()

    def test_keyboardinterrupt_is_still_fatal(self, monkeypatch):
        """Isolation must not widen to BaseException — Ctrl-C still stops everything."""
        po, calls, report = _arrange(monkeypatch, PageObjectDataPlaneConfiguration, linked_from_attempt=0)
        po.goto_dataplane_o11y_config = MagicMock(side_effect=KeyboardInterrupt)

        with pytest.raises(KeyboardInterrupt):
            po.switch_to_global_config(DP_NAME)


class TestGotoDataplaneO11yConfig:
    def test_base_class_declares_the_contract_instead_of_attributeerror(self):
        """switch_to_global_config lives on PageObjectDataPlane but the navigation hooks
        are subclass-only. Calling it on a bare base instance must say so, not raise a
        bare AttributeError three frames deep inside the retry loop."""
        po = _new(po_dataplane.PageObjectDataPlane)
        po.goto_left_navbar_dataplane = MagicMock()
        po.goto_dataplane = MagicMock()

        with pytest.raises(NotImplementedError, match="goto_dataplane_config"):
            po.goto_dataplane_o11y_config(DP_NAME)


    @pytest.mark.parametrize("cls", [PageObjectDataPlaneConfiguration, PageObjectBMDPConfiguration])
    def test_navigates_list_dp_config_observability(self, cls):
        """The one navigation path to the panel, shared by o11y_config_switch_to_global and
        the double-check retry — both configuration page objects must satisfy it."""
        po = _new(cls)
        po.goto_left_navbar_dataplane = MagicMock()
        po.goto_dataplane = MagicMock()
        po.goto_dataplane_config = MagicMock()
        po.goto_dataplane_config_sub_menu = MagicMock()

        po.goto_dataplane_o11y_config(DP_NAME)

        po.goto_left_navbar_dataplane.assert_called_once_with()
        po.goto_dataplane.assert_called_once_with(DP_NAME)
        po.goto_dataplane_config.assert_called_once_with()
        po.goto_dataplane_config_sub_menu.assert_called_once_with("Observability")
