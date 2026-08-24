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
# Tests for PageObjectBMDPConfiguration.ensure_bmdp_product_permissions — the
# proactive Product Permission grant that makes the browser path behave like the
# CLI/API path.
#
# Before this, the browser path only ever granted REACTIVELY: goto_products found
# a disabled BW5/BW6 card, hovered it for the tooltip, and only then walked the
# Assign Permissions wizard — deep inside the capability flow, on a data plane
# that already had domains registered. The CLI path (page_cli._run_api_bmdp_config)
# grants up front instead. The two paths must leave the same permissions behind.
#
# Three properties carry the risk and are covered here:
#   * the product GATING must match the CLI predicate exactly — BW5 iff
#     (RVDM or EMSDM), BW6 iff BW6DM, nothing else ever;
#   * this is BEST EFFORT: it must never raise, never exit, and never abort the
#     install task, not even on a SystemExit raised by a shared helper;
#   * the in-process memo is a performance optimisation only. Deleting it must
#     change nothing but wall clock, so it may only ever memoise a CONVERGED
#     grant, and it must not suppress the reactive path in goto_products.

from unittest.mock import MagicMock, patch

import pytest

import page_object.po_bmdp_config as po_bmdp_config_module
from page_object.po_bmdp_config import PageObjectBMDPConfiguration
from page_object.po_user_management import (
    GRANT_ALREADY,
    GRANT_DONE,
    GRANT_FAILED,
    GRANT_SKIPPED,
)
from utils.env import ENV

BMDP = "k8s-auto-bmdp1"


@pytest.fixture(autouse=True)
def _clear_run_memo():
    """The memo is module state that outlives a single test by design (one
    process = one automation run), so every test starts from a clean slate."""
    po_bmdp_config_module._GRANTED_IN_RUN.clear()
    yield
    po_bmdp_config_module._GRANTED_IN_RUN.clear()


@pytest.fixture(autouse=True)
def _bw5_and_bw6_enabled(monkeypatch):
    """Default gating for the non-gating tests: both products in play."""
    monkeypatch.setattr(type(ENV), "TP_AUTO_IS_ENABLE_RVDM", True)
    monkeypatch.setattr(type(ENV), "TP_AUTO_IS_ENABLE_EMSDM", False)
    monkeypatch.setattr(type(ENV), "TP_AUTO_IS_ENABLE_BW6DM", True)


def _make_po():
    """Build the page object without __init__ (no real Playwright page)."""
    po = object.__new__(PageObjectBMDPConfiguration)
    po.page = MagicMock()
    return po


def _run_ensure(grant_results, dp_name=BMDP, po=None, nav_error=None, call_twice=False):
    """Drive ensure_bmdp_product_permissions with the wizard stubbed out.

    grant_results is what grant_product_permission does: a single result, a list
    consumed across attempts AND across products, or an exception to raise."""
    po = po or _make_po()
    grant = MagicMock()
    if isinstance(grant_results, (list, BaseException)):
        grant.side_effect = grant_results
    else:
        grant.return_value = grant_results
    nav = MagicMock(side_effect=nav_error)

    with patch("page_object.po_bmdp_config.PageObjectUserManagement") as pum, \
         patch.object(PageObjectBMDPConfiguration, "goto_left_navbar_dataplane", nav), \
         patch.object(PageObjectBMDPConfiguration, "goto_dataplane") as goto_dp:
        pum.return_value.grant_product_permission = grant
        first = po.ensure_bmdp_product_permissions(dp_name)
        second = po.ensure_bmdp_product_permissions(dp_name) if call_twice else None
    return first, second, grant, goto_dp


# --- AC5: the gating predicate must be byte-for-byte the CLI one ---------------------

class TestProductGating:
    @pytest.mark.parametrize("rvdm,emsdm,bw6dm,expected", [
        (False, False, False, []),
        (True,  False, False, ["BW5"]),
        (False, True,  False, ["BW5"]),
        (True,  True,  False, ["BW5"]),
        (False, False, True,  ["BW6"]),
        (True,  False, True,  ["BW5", "BW6"]),
        (False, True,  True,  ["BW5", "BW6"]),
        (True,  True,  True,  ["BW5", "BW6"]),
    ])
    def test_matches_the_cli_predicate(self, monkeypatch, rvdm, emsdm, bw6dm, expected):
        """BW5 is the product behind BOTH RV and EMS domains, so either flag pulls it
        in exactly once. EMS server registration, BE and Messaging are not gated by
        Product Permission at all and must never reach the wizard."""
        monkeypatch.setattr(type(ENV), "TP_AUTO_IS_ENABLE_RVDM", rvdm)
        monkeypatch.setattr(type(ENV), "TP_AUTO_IS_ENABLE_EMSDM", emsdm)
        monkeypatch.setattr(type(ENV), "TP_AUTO_IS_ENABLE_BW6DM", bw6dm)

        results, _, grant, _ = _run_ensure(GRANT_DONE)

        assert list(results) == expected
        requested = [call.args[1] for call in grant.call_args_list]
        assert requested == expected

    def test_nothing_enabled_never_opens_the_wizard(self, monkeypatch):
        monkeypatch.setattr(type(ENV), "TP_AUTO_IS_ENABLE_RVDM", False)
        monkeypatch.setattr(type(ENV), "TP_AUTO_IS_ENABLE_EMSDM", False)
        monkeypatch.setattr(type(ENV), "TP_AUTO_IS_ENABLE_BW6DM", False)

        results, _, grant, _ = _run_ensure(GRANT_DONE)

        assert results == {}
        grant.assert_not_called()

    def test_ems_be_and_messaging_are_never_requested(self, monkeypatch):
        monkeypatch.setattr(type(ENV), "TP_AUTO_IS_ENABLE_RVDM", True)
        monkeypatch.setattr(type(ENV), "TP_AUTO_IS_ENABLE_EMSDM", True)
        monkeypatch.setattr(type(ENV), "TP_AUTO_IS_ENABLE_BW6DM", True)

        results, _, grant, _ = _run_ensure(GRANT_DONE)

        requested = {call.args[1] for call in grant.call_args_list}
        assert requested == {"BW5", "BW6"}
        assert not requested & {"EMS", "BE", "Messaging", "MSGSERVER"}


# --- the contract of the return value and of the one greppable log line -------------

class TestResultContract:
    def test_returns_a_result_per_product_using_the_shared_constants(self):
        results, _, _, _ = _run_ensure([GRANT_DONE, GRANT_ALREADY])

        assert results == {"BW5": GRANT_DONE, "BW6": GRANT_ALREADY}
        for value in results.values():
            assert value in (GRANT_DONE, GRANT_ALREADY, GRANT_SKIPPED, GRANT_FAILED)

    def test_emits_exactly_one_greppable_line_per_product(self, capsys):
        """This single line is how a support engineer answers "did the grant happen"
        from a pipeline log, so its shape is a contract."""
        _run_ensure([GRANT_DONE, GRANT_ALREADY])

        out = capsys.readouterr().out
        assert out.count(f"Product permission {BMDP} => BW5: {GRANT_DONE}") == 1
        assert out.count(f"Product permission {BMDP} => BW6: {GRANT_ALREADY}") == 1

    def test_defaults_the_dataplane_to_the_bmdp_from_env(self):
        results, _, grant, _ = _run_ensure(GRANT_DONE, dp_name=None)

        assert [call.args[0] for call in grant.call_args_list] == \
               [ENV.TP_AUTO_K8S_BMDP_NAME, ENV.TP_AUTO_K8S_BMDP_NAME]
        assert set(results) == {"BW5", "BW6"}


# --- exactly one retry, and the retry's answer is the answer -------------------------

class TestRetry:
    def test_a_failure_is_retried_once_and_the_second_result_wins(self):
        """In the pipeline this grant gets ONE chance per instance lifetime: the
        create-bmdp task exits 0 as soon as the BMDP appears in .dataPlane[], so
        there is no "it will self-heal next run"."""
        results, _, grant, _ = _run_ensure([GRANT_FAILED, GRANT_DONE,      # BW5: retried
                                            GRANT_ALREADY])                # BW6: first try
        assert results == {"BW5": GRANT_DONE, "BW6": GRANT_ALREADY}
        assert grant.call_count == 3

    def test_it_retries_once_and_no_more(self):
        # A third element would be consumed only by a second (forbidden) retry.
        results, _, grant, _ = _run_ensure([GRANT_FAILED, GRANT_FAILED, GRANT_DONE,   # BW5
                                            GRANT_DONE])                              # BW6
        assert results["BW5"] == GRANT_FAILED
        assert results["BW6"] == GRANT_DONE
        assert grant.call_count == 3      # 2 for BW5 + 1 for BW6

    def test_a_converged_result_is_not_retried(self):
        _, _, grant, _ = _run_ensure([GRANT_DONE, GRANT_ALREADY])
        assert grant.call_count == 2

    def test_a_skip_is_not_retried(self):
        """A product the CP does not offer will not start being offered on attempt 2."""
        results, _, grant, _ = _run_ensure([GRANT_SKIPPED, GRANT_SKIPPED])
        assert results == {"BW5": GRANT_SKIPPED, "BW6": GRANT_SKIPPED}
        assert grant.call_count == 2


# --- AC4-E: the memo is an optimisation, never a correctness mechanism ---------------

class TestRunMemo:
    @pytest.mark.parametrize("first_result", [GRANT_DONE, GRANT_ALREADY])
    def test_a_converged_grant_is_not_walked_twice_in_one_process(self, first_result):
        first, second, grant, _ = _run_ensure(first_result, call_twice=True)

        assert grant.call_count == 2                       # BW5 + BW6, once each
        assert second == {"BW5": GRANT_ALREADY, "BW6": GRANT_ALREADY}
        assert set(first) == set(second)

    def test_a_failure_is_re_attempted_by_the_next_caller(self):
        """The memo must not turn a transient wizard failure into a permanent skip:
        a later caller in the same process has to try again."""
        po = _make_po()
        grant = MagicMock(return_value=GRANT_FAILED)
        with patch("page_object.po_bmdp_config.PageObjectUserManagement") as pum, \
             patch.object(PageObjectBMDPConfiguration, "goto_left_navbar_dataplane"), \
             patch.object(PageObjectBMDPConfiguration, "goto_dataplane"):
            pum.return_value.grant_product_permission = grant
            po.ensure_bmdp_product_permissions(BMDP)
            after_first = grant.call_count
            second = po.ensure_bmdp_product_permissions(BMDP)

        assert second == {"BW5": GRANT_FAILED, "BW6": GRANT_FAILED}
        assert grant.call_count > after_first, "the second call must re-enter the wizard"

    def test_a_skip_is_re_attempted_by_the_next_caller(self):
        first, second, grant, _ = _run_ensure(GRANT_SKIPPED, call_twice=True)

        assert first == second == {"BW5": GRANT_SKIPPED, "BW6": GRANT_SKIPPED}
        assert grant.call_count == 4      # nothing memoised

    def test_the_memo_is_keyed_on_the_dataplane_too(self):
        po = _make_po()
        grant = MagicMock(return_value=GRANT_DONE)
        with patch("page_object.po_bmdp_config.PageObjectUserManagement") as pum, \
             patch.object(PageObjectBMDPConfiguration, "goto_left_navbar_dataplane"), \
             patch.object(PageObjectBMDPConfiguration, "goto_dataplane"):
            pum.return_value.grant_product_permission = grant
            po.ensure_bmdp_product_permissions(BMDP)
            po.ensure_bmdp_product_permissions("k8s-auto-bmdp2")

        granted_on = {call.args[0] for call in grant.call_args_list}
        assert granted_on == {BMDP, "k8s-auto-bmdp2"}

    def test_the_memo_does_not_suppress_the_reactive_grant_in_goto_products(self):
        """goto_products only grants when it has SEEN a disabled card plus the
        "You need Product permission" tooltip — hard evidence that the grant is
        missing right now, which beats anything the memo believes. If the memo
        gated that path, a grant lost between the two (or made against the wrong
        user session) could never be recovered."""
        po = _make_po()
        po_bmdp_config_module._GRANTED_IN_RUN.add((ENV.TP_AUTO_K8S_BMDP_NAME, "BW5"))
        grant = MagicMock(return_value=GRANT_DONE)

        with patch("page_object.po_bmdp_config.PageObjectUserManagement") as pum, \
             patch("page_object.po_bmdp_config.Util.check_dom_visibility", return_value=True), \
             patch.object(PageObjectBMDPConfiguration, "goto_left_navbar_dataplane"), \
             patch.object(PageObjectBMDPConfiguration, "goto_dataplane"):
            pum.return_value.grant_product_permission = grant
            assert po.goto_products("BW5") is True

        grant.assert_called_once_with(ENV.TP_AUTO_K8S_BMDP_NAME, "BW5")


# --- best effort: nothing here may abort the caller ----------------------------------

class TestNeverAbortsTheCaller:
    def test_an_exception_from_the_wizard_becomes_a_failed_result(self):
        results, _, grant, _ = _run_ensure(RuntimeError("the wizard exploded"))

        assert results == {"BW5": GRANT_FAILED, "BW6": GRANT_FAILED}
        assert grant.call_count == 4      # both products, both attempts

    def test_a_systemexit_from_the_wizard_is_trapped(self):
        """Util.exit_error deep in a shared helper raises SystemExit, a BaseException
        that sails straight past `except Exception`. A best-effort grant may not kill
        the install task, so it has to be caught explicitly."""
        results, _, _, _ = _run_ensure(SystemExit(1))

        assert results == {"BW5": GRANT_FAILED, "BW6": GRANT_FAILED}

    def test_a_systemexit_from_the_navigation_restore_is_trapped(self):
        """The wizard lives under User Management, so the method navigates back to the
        data plane on the way out. A hiccup there must still return the results — the
        caller navigates for itself anyway."""
        results, _, _, _ = _run_ensure(GRANT_DONE, nav_error=SystemExit(1))

        assert results == {"BW5": GRANT_DONE, "BW6": GRANT_DONE}

    def test_an_exception_from_the_navigation_restore_is_trapped(self):
        results, _, _, _ = _run_ensure(GRANT_DONE, nav_error=RuntimeError("no left nav"))

        assert results == {"BW5": GRANT_DONE, "BW6": GRANT_DONE}

    def test_it_navigates_back_to_the_dataplane_the_caller_expects(self):
        _, _, _, goto_dp = _run_ensure(GRANT_DONE)

        goto_dp.assert_called_once_with(BMDP)
