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
# PCP-24228 - page_o11y honours FORCE_RUN_AUTOMATION.
#
# The env var already existed but was wired only into case/k8s_create_and_start_*_app.py and
# the MCP tools; page_o11y never read it. Combined with the missing delete_dashboard, that made
# a one-way ratchet: once a dashboard existed on an instance, the code that creates it could
# never execute there again. A fix could not be regression-tested, a half-built dashboard could
# not self-heal, and - the expensive one - a re-run that silently skipped the failing step
# looked like a pass and kept a wrong root cause alive.
#
# Default (unset/false) behaviour must stay exactly as it was: an existing dashboard is left
# alone. Only with the switch on does the step delete and rebuild.

import pytest

import page_o11y
from utils.util import Util


class FakeO11y:
    """Records the create/delete traffic; each dashboard method has its own coverage."""

    def __init__(self, existing=(), delete_ok=True, create_ok=True, fail_adds=0):
        self.existing = set(existing)
        self.delete_ok = delete_ok
        self.create_ok = create_ok
        self.fail_adds = fail_adds      # how many add_* calls report failure
        self.deleted = []
        self.created = []
        self.page = object()

    def _add_result(self):
        if self.fail_adds > 0:
            self.fail_adds -= 1
            return False
        return True

    def is_dashboard_exists(self, name):
        return name in self.existing

    def delete_dashboard(self, name):
        self.deleted.append(name)
        if self.delete_ok:
            self.existing.discard(name)
        return self.delete_ok

    def create_dashboard(self, name):
        self.created.append(name)
        if not self.create_ok:
            return False
        self.existing.add(name)
        return True

    # only reached by configure_promql_dashboard's card loop
    def add_promql_widget(self, *_a, **_k):
        return self._add_result()

    def add_promql_instant_widget(self, *_a, **_k):
        return self._add_result()


@pytest.fixture(autouse=True)
def warnings(monkeypatch):
    captured = []
    monkeypatch.setattr(Util, "warning_screenshot",
                        staticmethod(lambda message, page=None, filename="": captured.append(message)))
    return captured


# Both fixtures clear the o11y override as well: it takes PRECEDENCE over FORCE_RUN_AUTOMATION,
# so an ambient value in the developer's shell would invert every assertion below - the tests
# would pass or fail on the environment rather than on the code.
@pytest.fixture
def force_off(monkeypatch):
    monkeypatch.delenv("FORCE_RUN_AUTOMATION", raising=False)
    monkeypatch.delenv("TP_AUTO_O11Y_FORCE_REBUILD_DASHBOARD", raising=False)


@pytest.fixture
def force_on(monkeypatch):
    monkeypatch.setenv("FORCE_RUN_AUTOMATION", "true")
    monkeypatch.delenv("TP_AUTO_O11Y_FORCE_REBUILD_DASHBOARD", raising=False)


class TestDefaultBehaviourIsUnchanged:
    def test_existing_dashboard_is_skipped_and_never_deleted(self, force_off):
        po = FakeO11y(existing=["logs_dashboard"])

        assert page_o11y.should_build_dashboard(po, "logs_dashboard") is False
        assert po.deleted == []

    def test_absent_dashboard_is_built(self, force_off):
        po = FakeO11y()

        assert page_o11y.should_build_dashboard(po, "logs_dashboard") is True
        assert po.deleted == []

    def test_the_flag_is_read_per_call_not_at_import(self, monkeypatch):
        # Reading it at import time would freeze whatever the pipeline's very first run saw.
        monkeypatch.delenv("FORCE_RUN_AUTOMATION", raising=False)
        assert page_o11y.is_force_run() is False
        monkeypatch.setenv("FORCE_RUN_AUTOMATION", "TRUE")
        assert page_o11y.is_force_run() is True


class TestTheDestructivePathHasItsOwnSwitch:
    """FORCE_RUN_AUTOMATION is a GLOBAL flag - a Hub UI checkbox, an MCP parameter, and the
    app-rebuild flag in three cases - and until now it only meant 'redo the app create/start'.
    Someone ticking it to force a Flogo rebuild needs a way to keep their dashboards."""

    def test_the_override_can_switch_the_destructive_path_off(self, monkeypatch):
        monkeypatch.setenv("FORCE_RUN_AUTOMATION", "true")
        monkeypatch.setenv("TP_AUTO_O11Y_FORCE_REBUILD_DASHBOARD", "false")
        po = FakeO11y(existing=["logs_dashboard"])

        assert page_o11y.should_build_dashboard(po, "logs_dashboard") is False
        assert po.deleted == []

    def test_the_override_can_switch_it_on_by_itself(self, monkeypatch):
        monkeypatch.delenv("FORCE_RUN_AUTOMATION", raising=False)
        monkeypatch.setenv("TP_AUTO_O11Y_FORCE_REBUILD_DASHBOARD", "true")
        po = FakeO11y(existing=["logs_dashboard"])

        assert page_o11y.should_build_dashboard(po, "logs_dashboard") is True
        assert po.deleted == ["logs_dashboard"]

    def test_an_unset_or_blank_override_falls_back_to_force_run_automation(self, monkeypatch):
        # AC10: FORCE_RUN_AUTOMATION alone must still drive the rebuild.
        monkeypatch.setenv("FORCE_RUN_AUTOMATION", "true")
        monkeypatch.setenv("TP_AUTO_O11Y_FORCE_REBUILD_DASHBOARD", "   ")
        assert page_o11y.is_force_run() is True

    def test_an_intended_yes_spelling_is_not_read_as_a_cancellation(self, monkeypatch):
        """This flag can CANCEL a rebuild, so reading an intended-yes value as false does the
        opposite of what the person setting it asked for — silently."""
        monkeypatch.setenv("FORCE_RUN_AUTOMATION", "true")
        for spelling in ("1", "yes", "on", "TRUE", "True"):
            monkeypatch.setenv("TP_AUTO_O11Y_FORCE_REBUILD_DASHBOARD", spelling)
            assert page_o11y.is_force_run() is True, f"{spelling!r} must not cancel the rebuild"

    def test_an_explicit_no_still_cancels(self, monkeypatch):
        monkeypatch.setenv("FORCE_RUN_AUTOMATION", "true")
        for spelling in ("false", "False", "0", "no", "off"):
            monkeypatch.setenv("TP_AUTO_O11Y_FORCE_REBUILD_DASHBOARD", spelling)
            assert page_o11y.is_force_run() is False, f"{spelling!r} must cancel the rebuild"

    def test_a_whitespace_padded_value_is_not_silently_read_as_false(self, monkeypatch):
        """Raised by Copilot: the blank guard stripped but the comparison did not, so ' TRUE '
        passed the guard and then returned False - the flag set, and quietly ignored."""
        monkeypatch.delenv("FORCE_RUN_AUTOMATION", raising=False)
        monkeypatch.setenv("TP_AUTO_O11Y_FORCE_REBUILD_DASHBOARD", " TRUE ")
        assert page_o11y.is_force_run() is True

        monkeypatch.delenv("TP_AUTO_O11Y_FORCE_REBUILD_DASHBOARD", raising=False)
        monkeypatch.setenv("FORCE_RUN_AUTOMATION", " true ")
        assert page_o11y.is_force_run() is True


class TestForceRunRebuilds:
    def test_existing_dashboard_is_deleted_then_rebuilt(self, force_on):
        po = FakeO11y(existing=["logs_dashboard"])

        assert page_o11y.should_build_dashboard(po, "logs_dashboard") is True
        assert po.deleted == ["logs_dashboard"]

    def test_a_failed_delete_does_not_attempt_a_duplicate_create(self, force_on):
        # create_dashboard on a taken name only re-opens the dialog with an inline error.
        po = FakeO11y(existing=["logs_dashboard"], delete_ok=False)

        assert page_o11y.should_build_dashboard(po, "logs_dashboard") is False
        assert po.deleted == ["logs_dashboard"]


class TestALostRebuildIsReportedAsSuchNotAsAGenericCreateFailure:
    """A force rebuild deletes FIRST, so a create that then fails leaves the instance with no
    dashboard where one existed — materially worse than the default 'skip and leave alone', and
    the generic 'Failed to create' line gave no hint of it."""

    def test_a_delete_then_failed_create_says_the_dashboard_is_now_gone(self, force_on, warnings):
        po = FakeO11y(existing=["logs_dashboard"], create_ok=False)

        assert page_o11y.ensure_dashboard(po, "logs_dashboard") is False

        assert po.deleted == ["logs_dashboard"]
        assert any("was DELETED for a force rebuild" in w and "NO 'logs_dashboard' dashboard" in w
                   for w in warnings)

    def test_a_failed_create_on_a_fresh_name_stays_the_plain_message(self, force_off, warnings):
        # Nothing was destroyed here, so it must not claim anything was.
        po = FakeO11y(create_ok=False)

        assert page_o11y.ensure_dashboard(po, "logs_dashboard") is False

        assert po.deleted == []
        assert any(w == "Failed to create dashboard 'logs_dashboard'" for w in warnings)
        assert not any("DELETED" in w for w in warnings)

    def test_the_dropdown_is_only_read_once_per_dashboard(self, force_off):
        """Opening it is the flakiest and slowest control in this flow, and the force path
        already pays for it twice more (delete + verify)."""
        po = FakeO11y()
        reads = []
        po.is_dashboard_exists = lambda name: reads.append(name) or False

        page_o11y.ensure_dashboard(po, "logs_dashboard")

        assert reads == ["logs_dashboard"]


class TestEveryCreateStepGoesThroughTheGate:
    """AC7 needs the PromQL step specifically to be re-runnable, but a half-honoured switch
    would be worse than none - each step that has an exists-check must use the same gate."""

    def test_promql_step_rebuilds_under_force_run(self, force_on):
        po = FakeO11y(existing=[page_o11y.PROMQL_DASHBOARD["name"]])

        page_o11y.configure_promql_dashboard(po, [page_o11y.PROMQL_DASHBOARD["capability"]])

        assert po.deleted == [page_o11y.PROMQL_DASHBOARD["name"]]
        assert po.created == [page_o11y.PROMQL_DASHBOARD["name"]]

    def test_promql_step_still_skips_by_default(self, force_off):
        po = FakeO11y(existing=[page_o11y.PROMQL_DASHBOARD["name"]])

        page_o11y.configure_promql_dashboard(po, [page_o11y.PROMQL_DASHBOARD["capability"]])

        assert po.deleted == []
        assert po.created == []

    def test_logs_step_rebuilds_under_force_run(self, force_on, monkeypatch):
        po = FakeO11y(existing=[page_o11y.LOG_DASHBOARD_NAME])
        po.is_catalog_card_available = lambda *_a: False
        po.add_widgets = lambda *_a, **_k: None

        page_o11y.configure_logs_dashboard(po)

        assert po.deleted == [page_o11y.LOG_DASHBOARD_NAME]
        assert po.created == [page_o11y.LOG_DASHBOARD_NAME]

    def test_promql_step_reports_when_it_did_not_add_every_card(self, force_off, warnings):
        """The tally is the guard against the NEXT PCP-24228: the run exits 0 either way, so
        without it a future selector hop is a green pipeline and 5 missing cards. Deleting the
        `added < expected` branch must not leave the suite green."""
        po = FakeO11y(fail_adds=2)

        page_o11y.configure_promql_dashboard(po, [page_o11y.PROMQL_DASHBOARD["capability"]])

        expected = len(page_o11y.PROMQL_DASHBOARD["range_cards"]) + len(page_o11y.PROMQL_DASHBOARD["instant_cards"])
        assert any(f"only {expected - 2} of {expected} cards are complete" in w for w in warnings)

    def test_a_complete_promql_dashboard_warns_about_nothing(self, force_off, warnings):
        po = FakeO11y()

        page_o11y.configure_promql_dashboard(po, [page_o11y.PROMQL_DASHBOARD["capability"]])

        assert warnings == []

    def test_capability_step_rebuilds_under_force_run(self, force_on):
        spec = page_o11y.CAPABILITY_DASHBOARDS[0]
        po = FakeO11y(existing=[spec["name"]])
        po.add_widgets = lambda *_a, **_k: None

        page_o11y.configure_capability_dashboards(po, [spec["capability"]])

        assert po.deleted == [spec["name"]]
        assert po.created == [spec["name"]]
