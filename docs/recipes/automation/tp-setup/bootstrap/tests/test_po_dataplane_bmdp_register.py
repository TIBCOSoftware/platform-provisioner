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
# Regression net for BMDP (Control Tower) registration in k8s_create_bmdp.
#
# The failure these tests exist to prevent is a SILENT one: the registration page
# renders its command list behind a "Display Details & Registration Commands"
# toggle, under an *ngIf whose flag starts false, so the container is absent from
# the DOM until the toggle is clicked AND Angular has re-rendered.
# all_text_contents() is the only call in that flow that does not auto-wait -- with
# zero matches it returns [] immediately, no timeout, no exception. Scraping right
# after the click therefore yields no commands, the execution loop runs zero times,
# nothing is deployed to the cluster, and the task still reports success.
#
# Two further short-circuits then turn that into a green pipeline: a data plane NAME
# in report.yaml, and a data plane CARD in the Control Plane list, were both treated
# as proof of a working data plane. A Control Plane record exists as soon as
# registration is submitted, so it proves only that an attempt was made.
#
# WHAT IS PINNED HERE, and why each case would have passed before the fix:
#   * an empty command list must ABORT, never fall through to "Done" (was: silent skip)
#   * a bare NAME in report.yaml must not short-circuit (was: instant "already created")
#   * a card that is not green must not short-circuit (was: instant "already created")
#   * the health oracle must never consult tunnel state (a disconnected tunnel is not
#     a reason to destroy a data plane)
#   * completion evidence must be written only after the workload is proven, and
#     set_dataplane must precede set_dataplane_info or the write is a silent no-op
#   * titles must reach k8s_run_dataplane_command verbatim -- it keys on the exact
#     strings to apply per-step extras, so a synthesized name skips real work

import time
from unittest.mock import MagicMock, patch

import pytest

import page_object.po_dataplane as po_dataplane_module
from page_object.po_dataplane import (
    BMDP_REGISTER_COMMANDS_CONTAINER,
    BMDP_REGISTER_DETAILS_TOGGLE,
    BMDP_REGISTER_DETAILS_TOGGLE_LEGACY,
    BMDP_REGISTER_FINISHED_CONTENT,
    BMDP_REGISTER_LEGACY_CONTENT,
    BMDP_STATUS_RUNNING,
    PageObjectDataPlane,
)
from utils.env import ENV

DP = "k8s-auto-bmdp1"
TITLES = [
    "1. Helm Repository configuration",
    "2. Namespace creation",
    "3. Service Account creation",
    "4. Cluster Registration",
]
TITLES_SELECTOR = f"{BMDP_REGISTER_COMMANDS_CONTAINER} p.title"
DOWNLOAD_SELECTOR = f"{BMDP_REGISTER_COMMANDS_CONTAINER} #download-commands"


def _make_page():
    """A fake Playwright page whose locators are addressable by selector.

    Every selector resolves to the SAME mock on each call, so a test can set an
    expectation before the code under test runs and assert on it afterwards.
    Defaults are deliberately "absent": not visible, zero matches, no text. That
    makes every optional wizard branch fall through, so a test only has to
    describe the handful of elements it actually cares about.
    `.first` returns the mock itself, which keeps `_sel` (used to route
    check_dom_visibility) intact through the `.first` the production code applies.
    """
    page = MagicMock(name="page")
    registry = {}

    def _locator(selector, **_kwargs):
        if selector not in registry:
            mock = MagicMock(name=f"locator[{selector}]")
            mock._sel = selector
            mock.first = mock
            mock.is_visible.return_value = False
            mock.count.return_value = 0
            mock.get_attribute.return_value = ""
            mock.all_text_contents.return_value = []
            mock.locator.side_effect = lambda sub, **kw: _locator(f"{selector} {sub}")
            registry[selector] = mock
        return registry[selector]

    page.locator.side_effect = _locator
    return page, registry


def _make_po():
    """Build the page object without __init__ (no real Playwright page)."""
    po = object.__new__(PageObjectDataPlane)
    po.page, po._registry = _make_page()
    return po


def _visibility_router(visible_selectors):
    """Stand in for Util.check_dom_visibility, routed on the locator's selector.

    A blanket True/False would make every gate agree with every other gate, which
    is exactly how a test can silently exercise the wrong branch.
    """
    def _check(_page, locator, *_args, **_kwargs):
        return getattr(locator, "_sel", None) in visible_selectors
    return _check


@pytest.fixture(autouse=True)
def _no_screenshots(monkeypatch):
    """exit_error still really raises SystemExit; only its side effects are stubbed."""
    monkeypatch.setattr("utils.util.Util.screenshot_page", lambda *a, **k: None)
    monkeypatch.setattr("utils.util.Util.stop_tracing", lambda *a, **k: None)


# --- the render race: expand, WAIT, then scrape -------------------------------------

class TestScrapeRegisterCommands:
    def test_waits_for_container_before_reading_titles(self):
        """The panel is absent at click time and only renders during the wait.

        This is the bug in one test: reading straight after the click yields [].
        """
        po = _make_po()
        container = po.page.locator(BMDP_REGISTER_COMMANDS_CONTAINER)
        titles = po.page.locator(TITLES_SELECTOR)
        toggle = po.page.locator(BMDP_REGISTER_DETAILS_TOGGLE)
        toggle.count.return_value = 1
        # Absent before the wait; the wait is what makes it appear.
        container.count.return_value = 0
        titles.is_visible.return_value = False
        titles.all_text_contents.return_value = []

        def _render(_page, locator, *_a, **_k):
            # The wait must be on the TITLES, not merely on the container: an already-present
            # container is not proof the titles inside it have rendered.
            if getattr(locator, "_sel", None) == TITLES_SELECTOR:
                container.count.return_value = 1
                titles.is_visible.return_value = True
                titles.all_text_contents.return_value = list(TITLES)
                return True
            return False

        with patch("page_object.po_dataplane.Util.check_dom_visibility", side_effect=_render):
            assert po._scrape_register_commands() == TITLES

        toggle.click.assert_called_once()

    def test_does_not_click_toggle_when_panel_already_open(self):
        """The toggle is a plain boolean flip, so a blind click would CLOSE it."""
        po = _make_po()
        po.page.locator(BMDP_REGISTER_COMMANDS_CONTAINER).count.return_value = 1
        titles = po.page.locator(TITLES_SELECTOR)
        titles.is_visible.return_value = True
        titles.all_text_contents.return_value = list(TITLES)
        toggle = po.page.locator(BMDP_REGISTER_DETAILS_TOGGLE)
        toggle.count.return_value = 1

        with patch("page_object.po_dataplane.Util.check_dom_visibility", return_value=True):
            assert po._scrape_register_commands() == TITLES

        toggle.click.assert_not_called()

    def test_expands_a_panel_that_is_present_but_collapsed(self):
        """Presence is not openness. The container class is literally '.expandable', so a
        Control Plane that kept it in the DOM and collapsed it with CSS would make a
        count()-based check say 'already open' and never click the toggle — while
        all_text_contents(), which reads textContent regardless of visibility, still returned
        titles for buttons that cannot be clicked."""
        po = _make_po()
        po.page.locator(BMDP_REGISTER_COMMANDS_CONTAINER).count.return_value = 1  # present
        titles = po.page.locator(TITLES_SELECTOR)
        titles.is_visible.return_value = False                                     # but collapsed
        titles.all_text_contents.return_value = list(TITLES)
        toggle = po.page.locator(BMDP_REGISTER_DETAILS_TOGGLE)
        toggle.count.return_value = 1

        def _expand(_page, locator, *_a, **_k):
            if getattr(locator, "_sel", None) == TITLES_SELECTOR:
                titles.is_visible.return_value = True
                return True
            return False

        with patch("page_object.po_dataplane.Util.check_dom_visibility", side_effect=_expand):
            assert po._scrape_register_commands() == TITLES

        toggle.click.assert_called_once()

    def test_titles_are_trimmed(self):
        """all_text_contents() returns raw textContent with no whitespace normalisation, and
        k8s_run_dataplane_command compares these strings with == to decide whether to apply the
        helm-repo reset and the service-account extras."""
        po = _make_po()
        titles = po.page.locator(TITLES_SELECTOR)
        titles.is_visible.return_value = True
        titles.all_text_contents.return_value = [f"\n  {t}\n" for t in TITLES]

        with patch("page_object.po_dataplane.Util.check_dom_visibility", return_value=True):
            assert po._scrape_register_commands() == TITLES

    def test_reclicks_at_most_once_when_panel_never_renders(self):
        po = _make_po()
        po.page.locator(BMDP_REGISTER_COMMANDS_CONTAINER).count.return_value = 0
        toggle = po.page.locator(BMDP_REGISTER_DETAILS_TOGGLE)
        toggle.count.return_value = 1

        with patch("page_object.po_dataplane.Util.check_dom_visibility", return_value=False):
            assert po._scrape_register_commands() == []

        assert toggle.click.call_count == 2

    def test_falls_back_to_legacy_toggle_selector(self):
        """Older Control Planes only have the generic no-border button."""
        po = _make_po()
        po.page.locator(BMDP_REGISTER_COMMANDS_CONTAINER).count.return_value = 0
        po.page.locator(BMDP_REGISTER_DETAILS_TOGGLE).count.return_value = 0
        legacy = po.page.locator(BMDP_REGISTER_DETAILS_TOGGLE_LEGACY)

        with patch("page_object.po_dataplane.Util.check_dom_visibility", return_value=False):
            po._scrape_register_commands()

        assert legacy.click.call_count == 2


# --- the "already exists" short-circuits must require evidence ----------------------

class TestAlreadyExistsShortCircuits:
    def test_bare_name_in_report_does_not_short_circuit(self):
        """A name alone is written as soon as any card is seen; it proves nothing."""
        po = _make_po()
        with patch("page_object.po_dataplane.ReportYaml") as report:
            report.is_dataplane_created.return_value = True
            report.get_dataplane_info.return_value = None
            with patch.object(PageObjectDataPlane, "_is_dataplane_status_green", return_value=False) as green, \
                 patch.object(PageObjectDataPlane, "_recover_unhealthy_bmdp") as recover:
                _seed_visible_card(po)
                po.k8s_create_bmdp(DP)

        # Fell through to the Control Plane check instead of returning "already created".
        green.assert_called_once()
        recover.assert_called_once()

    def test_completion_status_short_circuits_when_the_data_plane_still_exists(self):
        po = _make_po()
        _seed_visible_card(po)
        with patch("page_object.po_dataplane.ReportYaml") as report:
            report.is_dataplane_created.return_value = True
            report.get_dataplane_info.return_value = BMDP_STATUS_RUNNING
            po.k8s_create_bmdp(DP)

        # Returned without walking the wizard.
        po.page.click.assert_not_called()

    def test_completion_evidence_for_a_data_plane_that_no_longer_exists_is_discarded(self):
        """report.yaml outlives both the data plane and the process. Deleting a data plane
        leaves its completion markers behind, so trusting them without seeing the card skips
        registration and reports success for something that is no longer there -- observed on a
        live Control Plane straight after a delete."""
        po = _make_po()  # no card seeded: the Control Plane does not have this data plane
        with patch("page_object.po_dataplane.ReportYaml") as report:
            report.is_dataplane_created.return_value = True
            report.get_dataplane_info.return_value = BMDP_STATUS_RUNNING
            # Registration is attempted and aborts later for want of a real wizard, which is
            # enough to prove the short-circuit did NOT fire.
            with patch("page_object.po_dataplane.Util.check_dom_visibility", return_value=False):
                with pytest.raises(SystemExit):
                    po.k8s_create_bmdp(DP)

        report.remove_dataplane.assert_called_once_with(DP)
        po.page.click.assert_any_call("#register-dp-button")

    def test_card_present_but_not_green_takes_recovery_path(self):
        po = _make_po()
        with patch("page_object.po_dataplane.ReportYaml") as report:
            report.is_dataplane_created.return_value = False
            with patch.object(PageObjectDataPlane, "_is_dataplane_status_green", return_value=False), \
                 patch.object(PageObjectDataPlane, "_recover_unhealthy_bmdp") as recover, \
                 patch.object(PageObjectDataPlane, "_mark_bmdp_complete") as mark:
                _seed_visible_card(po)
                po.k8s_create_bmdp(DP)

        recover.assert_called_once()
        mark.assert_not_called()

    def test_card_present_and_green_completes_without_re_registering(self):
        po = _make_po()
        with patch("page_object.po_dataplane.ReportYaml") as report:
            report.is_dataplane_created.return_value = False
            with patch.object(PageObjectDataPlane, "_is_dataplane_status_green", return_value=True), \
                 patch.object(PageObjectDataPlane, "k8s_wait_bmdp_ready") as ready, \
                 patch.object(PageObjectDataPlane, "_assert_bmdp_workload") as workload, \
                 patch.object(PageObjectDataPlane, "_mark_bmdp_complete") as mark:
                _seed_visible_card(po)
                po.k8s_create_bmdp(DP)

        # is_update_report=False: the completion marker must not be written by the readiness
        # wait, only after the workload has been proven.
        ready.assert_called_once_with(DP, False)
        workload.assert_called_once_with(DP)
        mark.assert_called_once_with(DP)
        po.page.click.assert_not_called()

    def test_cli_written_health_status_short_circuits(self):
        """The CLI registration path writes healthStatus, never status. Rejecting it would
        make the browser flow replay a wizard over a data plane the CLI already built."""
        po = _make_po()
        _seed_visible_card(po)
        with patch("page_object.po_dataplane.ReportYaml") as report:
            report.is_dataplane_created.return_value = True
            report.get_dataplane_info.side_effect = (
                lambda _dp, key: "green" if key == "healthStatus" else None
            )
            po.k8s_create_bmdp(DP)

        po.page.click.assert_not_called()

    def test_health_oracle_never_consults_tunnel_state(self):
        """A disconnected tunnel is not a reason to destroy a data plane."""
        po = _make_po()
        with patch("page_object.po_dataplane.Util.check_dom_visibility", return_value=True):
            po._is_dataplane_status_green(DP)

        consulted = [sel for sel in po._registry if "tunnel" in sel]
        assert consulted == [], f"health oracle consulted tunnel selectors: {consulted}"
        assert any("data-plane-status svg.green" in sel for sel in po._registry)


def _seed_visible_card(po):
    """Make the Control Plane list report a card for the data plane.

    `.data-plane-name` is consulted twice with different intent: bare, for the
    "too many data planes" count, and with has_text, for "does this one exist".
    Both resolve to the same mock here, so count stays 0 (under
    TP_AUTO_MAX_DATA_PLANE) while is_visible reports the card as present.
    """
    card = po.page.locator(".data-plane-name")
    card.is_visible.return_value = True
    card.count.return_value = 0
    return card


# --- the workload probe: a green card is not a running data plane -------------------

def _kubectl(namespace_result, pods_result):
    """Route the two kubectl shapes _assert_bmdp_workload issues.

    `--ignore-not-found` is what separates 'absent' from 'failed': a successful lookup of a
    missing namespace exits 0 with EMPTY output, while None means the command itself failed.
    """
    def _output(command, **_kwargs):
        if command.startswith("kubectl get namespace"):
            return namespace_result
        return pods_result
    return _output


class TestAssertBmdpWorkload:
    def test_namespace_missing_aborts(self, monkeypatch):
        po = _make_po()
        monkeypatch.setattr(type(ENV), "IS_CLUSTER_ACCESSIBLE", True)
        with patch("page_object.po_dataplane.Helper.get_command_output", side_effect=_kubectl("", "")):
            with pytest.raises(SystemExit):
                po._assert_bmdp_workload(DP)

    def test_namespace_present_but_no_running_pod_aborts(self, monkeypatch):
        po = _make_po()
        monkeypatch.setattr(type(ENV), "IS_CLUSTER_ACCESSIBLE", True)
        with patch("page_object.po_dataplane.Helper.get_command_output",
                   side_effect=_kubectl("namespace/k8s-auto-bmdp1ns", "")):
            with pytest.raises(SystemExit):
                po._assert_bmdp_workload(DP)

    def test_unqueryable_cluster_aborts_rather_than_recording_success(self, monkeypatch):
        """A failed lookup is 'unknown', never 'absent' and never 'complete'."""
        po = _make_po()
        monkeypatch.setattr(type(ENV), "IS_CLUSTER_ACCESSIBLE", True)
        with patch("page_object.po_dataplane.Helper.get_command_output", side_effect=_kubectl(None, None)):
            with pytest.raises(SystemExit):
                po._assert_bmdp_workload(DP)

    def test_failure_causes_are_distinct(self, monkeypatch):
        """Three different causes must not collapse into one message."""
        po = _make_po()
        monkeypatch.setattr(type(ENV), "IS_CLUSTER_ACCESSIBLE", True)
        messages = []

        def _record(message, *_a, **_k):
            messages.append(message)
            raise SystemExit(1)

        cases = [_kubectl("", ""),
                 _kubectl("namespace/k8s-auto-bmdp1ns", ""),
                 _kubectl(None, None)]
        with patch("page_object.po_dataplane.Util.exit_error", side_effect=_record):
            for case in cases:
                with patch("page_object.po_dataplane.Helper.get_command_output", side_effect=case):
                    with pytest.raises(SystemExit):
                        po._assert_bmdp_workload(DP)

        assert len(messages) == 3
        assert len(set(messages)) == 3
        assert "does not exist" in messages[0]
        assert "no Running pod" in messages[1]
        assert "could not be queried" in messages[2]

    def test_running_pods_pass(self, monkeypatch):
        po = _make_po()
        monkeypatch.setattr(type(ENV), "IS_CLUSTER_ACCESSIBLE", True)
        pods = "pod-a   1/1   Running   0   1m\npod-b   1/1   Running   0   1m"
        with patch("page_object.po_dataplane.Helper.get_command_output",
                   side_effect=_kubectl("namespace/k8s-auto-bmdp1ns", pods)):
            po._assert_bmdp_workload(DP)  # must not raise

    def test_namespace_name_is_validated_before_reaching_a_shell(self, monkeypatch):
        """These names are interpolated into shell commands, so they are validated, not trusted."""
        po = _make_po()
        monkeypatch.setattr(type(ENV), "IS_CLUSTER_ACCESSIBLE", True)
        monkeypatch.setattr(type(ENV), "TP_AUTO_K8S_BMDP_NAMESPACE", "ns; rm -rf /")
        with patch("page_object.po_dataplane.Helper.get_command_output") as run:
            with pytest.raises(ValueError):
                po._assert_bmdp_workload(DP)
        run.assert_not_called()

    def test_probe_skipped_when_cluster_not_accessible(self, monkeypatch):
        po = _make_po()
        monkeypatch.setattr(type(ENV), "IS_CLUSTER_ACCESSIBLE", False)
        with patch("page_object.po_dataplane.Helper.get_command_output") as run:
            po._assert_bmdp_workload(DP)  # must not raise
        run.assert_not_called()


# --- completion evidence --------------------------------------------------------------

class TestMarkBmdpComplete:
    def test_creates_the_entry_before_writing_into_it(self):
        """set_dataplane_info only mutates an EXISTING entry, so order is load-bearing:
        writing the marker first is a silent no-op."""
        po = _make_po()
        calls = []
        with patch("page_object.po_dataplane.ReportYaml") as report:
            report.set_dataplane.side_effect = lambda *a, **k: calls.append("set_dataplane")
            report.set_dataplane_info.side_effect = lambda dp, key, value: calls.append(key)
            with patch("os.path.exists", return_value=False):
                po._mark_bmdp_complete(DP)

        assert calls[0] == "set_dataplane"
        assert set(calls[1:]) == {"status", "runCommands"}

    def test_completion_status_is_written_only_here(self):
        """The guards treat this status as proof the data plane came up, and the report file
        outlives the process on a host mount. Any earlier write means an aborted run leaves
        the marker behind and the next task retry short-circuits to green on nothing."""
        po = _make_po()
        with patch("page_object.po_dataplane.ReportYaml") as report:
            with patch("os.path.exists", return_value=False):
                po._mark_bmdp_complete(DP)

        written = {c.args[1]: c.args[2] for c in report.set_dataplane_info.call_args_list}
        assert written.get("status") == BMDP_STATUS_RUNNING

    def test_readiness_wait_does_not_write_the_marker_when_deferred(self):
        """k8s_wait_bmdp_ready runs BEFORE the workload probe, so it must stay silent."""
        po = _make_po()
        with patch("page_object.po_dataplane.Util.check_dom_visibility", return_value=True):
            with patch("page_object.po_dataplane.ReportYaml") as report:
                po.k8s_wait_bmdp_ready(DP, False)

        report.set_dataplane.assert_not_called()
        report.set_dataplane_info.assert_not_called()


# --- an unhealthy existing data plane: report it, never destroy it ---------------------

class TestUnhealthyExistingBmdp:
    """The acceptance criterion allows the task to FAIL rather than re-register, and that is
    what this does. An automatic delete was considered and rejected: the only evidence
    available is a namespace name from the environment, which is never read back from the
    record being deleted, and the same entry point is reachable from the unauthenticated
    local script endpoint with a caller-supplied name and namespace."""

    def test_never_deletes_the_data_plane(self, monkeypatch):
        po = _make_po()
        monkeypatch.setattr(type(ENV), "IS_CLUSTER_ACCESSIBLE", True)
        with patch("page_object.po_dataplane.ReportYaml") as report,              patch("page_object.po_dataplane.Helper.get_command_output", side_effect=_kubectl("", "")),              patch.object(PageObjectDataPlane, "k8s_delete_dataplane") as delete:
            report.get_dataplane_info.return_value = None
            with pytest.raises(SystemExit):
                po._recover_unhealthy_bmdp(DP, 0)

        delete.assert_not_called()

    def test_never_records_completion(self, monkeypatch):
        """The whole point is that an unhealthy data plane must not look finished."""
        po = _make_po()
        monkeypatch.setattr(type(ENV), "IS_CLUSTER_ACCESSIBLE", True)
        with patch("page_object.po_dataplane.ReportYaml") as report,              patch("page_object.po_dataplane.Helper.get_command_output", side_effect=_kubectl("", "")):
            report.get_dataplane_info.return_value = None
            with pytest.raises(SystemExit):
                po._recover_unhealthy_bmdp(DP, 0)

        report.set_dataplane_info.assert_not_called()

    def test_message_names_the_cluster_evidence(self, monkeypatch):
        """A bare 'not healthy' is not actionable; say which state was observed."""
        po = _make_po()
        monkeypatch.setattr(type(ENV), "IS_CLUSTER_ACCESSIBLE", True)
        messages = []

        def _record(message, *_a, **_k):
            messages.append(message)
            raise SystemExit(1)

        pods = "pod-a   1/1   Running   0   1m"
        cases = [(_kubectl("", ""), "never ran"),
                 (_kubectl("namespace/k8s-auto-bmdp1ns", pods), "has not gone healthy"),
                 (_kubectl(None, None), "could not be queried")]
        with patch("page_object.po_dataplane.Util.exit_error", side_effect=_record),              patch("page_object.po_dataplane.ReportYaml") as report:
            report.get_dataplane_info.return_value = None
            for case, expected in cases:
                with patch("page_object.po_dataplane.Helper.get_command_output", side_effect=case):
                    with pytest.raises(SystemExit):
                        po._recover_unhealthy_bmdp(DP, 0)
                assert expected in messages[-1], messages[-1]

    def test_uses_the_namespace_the_data_plane_was_registered_with(self, monkeypatch):
        """An existing data plane may predate the current environment default; judging it
        against the wrong namespace would call a healthy data plane broken."""
        po = _make_po()
        monkeypatch.setattr(type(ENV), "IS_CLUSTER_ACCESSIBLE", True)
        monkeypatch.setattr(type(ENV), "TP_AUTO_K8S_BMDP_NAMESPACE", "env-default-ns")
        seen = []

        def _record_ns(command, **_kwargs):
            seen.append(command)
            return ""

        with patch("page_object.po_dataplane.ReportYaml") as report,              patch("page_object.po_dataplane.Helper.get_command_output", side_effect=_record_ns):
            report.get_dataplane_info.side_effect = (
                lambda _dp, key: "recorded-ns" if key == "namespace" else None
            )
            with pytest.raises(SystemExit):
                po._recover_unhealthy_bmdp(DP, 0)

        assert any("recorded-ns" in c for c in seen)
        assert not any("env-default-ns" in c for c in seen)
