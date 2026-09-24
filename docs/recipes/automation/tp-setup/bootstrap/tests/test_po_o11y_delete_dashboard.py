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
# PCP-24228 - po_o11y.delete_dashboard, the teardown the automation never had.
#
# po_o11y could create dashboards but never remove one, so on an instance that already had a
# dashboard the create path could not run a second time. That is not a convenience gap: a
# re-run SKIPPED the failing step and read as a pass, which is how this ticket's first analysis
# reached a wrong root cause.
#
# The flow was reverse-engineered from the live UI: the dropdown option row carries an
# `.adc-item-delete-icon`, and clicking it opens a confirmation with a Yes button.
#
# WHY A PURPOSE-BUILT FAKE, NOT tests/stub_page.py. This method's whole risk is WHICH ROW it
# acts on, and the shared stub keys everything off a selector string - its filter() narrows
# nothing, so it cannot answer that question (its own docstring says to put row-selection
# assertions in a file like this one instead). The fake below holds real rows with real text
# and evaluates the real regex against them, so `SB_dashboard` vs `SB_dashboard_2` - a prefix
# pair that genuinely ships in o11y_dashboard_config.py:195-196 - is a case the tests can state.

import pytest

from page_object.po_o11y import PageObjectO11y
from utils.util import Util

DASHBOARD = "PromQL_dashboard"
FRESCO_CONFIRM = '[data-testid="o11y-confirm-dialog"] .p-confirmdialog-accept-button'
LEGACY_CONFIRM = "#confirm-button:visible"


class FakeRow:
    """A LAZY locator, like Playwright's: it re-runs the match on every query rather than
    resolving once. Modelling it eagerly is what let a polled read look identical to a single
    read, so the poll could be deleted with every test still green."""

    def __init__(self, page, pattern):
        self.page, self.pattern = page, pattern

    def _resolve(self):
        matched = [r for r in self.page.rows if self.pattern.search(r)]
        # `row_hidden_for_reads` models a row that is slow to RENDER: missing from the first N
        # reads, present afterwards, WITHIN THE SAME open dropdown - the only scenario the polled
        # read exists for.
        if self.page.row_hidden_for_reads > 0:
            self.page.row_hidden_for_reads -= 1
            matched = []
        self.page.filter_matches.append((self.pattern.pattern, list(matched)))
        return matched[0] if matched else None

    def is_visible(self):
        return self._resolve() is not None

    def hover(self):
        name = self._resolve()
        assert name is not None, "hovered a row that does not exist"
        self.page.hovered.append(name)

    def click(self):
        name = self._resolve()
        assert name is not None, "clicked a row that does not exist"
        self.page.row_clicks.append(name)

    def locator(self, selector):
        return FakeIcon(self.page, self._resolve(), selector)


class FakeIcon:
    def __init__(self, page, row_name, selector):
        self.page, self.row_name, self.selector = page, row_name, selector

    def is_visible(self):
        return self.row_name is not None and self.page.icon_visible

    def click(self):
        assert self.row_name is not None, "clicked an icon on a row that does not exist"
        self.page.icon_clicks.append((self.row_name, self.selector))


class FakeConfirm:
    """The PrimeNG accept button, or the legacy Pulse one. `visible_selector` decides which
    markup this page is pretending to render."""

    def __init__(self, page, selector, has_text):
        self.page, self.selector, self.has_text = page, selector, has_text

    @property
    def first(self):
        return self

    def or_(self, other):
        return FakeConfirmUnion(self.page, self, other)

    def is_visible(self):
        return self.page.confirm_visible and self.selector == self.page.visible_confirm_selector

    def click(self):
        if not self.is_visible():
            raise AssertionError(f"clicked a confirm button that is not rendered: {self.selector}")
        self.page.confirm_clicks.append((self.selector, self.has_text))


class FakeConfirmUnion:
    def __init__(self, page, left, right):
        self.page, self.left, self.right = page, left, right

    @property
    def first(self):
        return self

    def is_visible(self):
        return self.left.is_visible() or self.right.is_visible()


class FakeOptions:
    """page.locator(<option selector>) - narrowed by .filter(has_text=<pattern>).first."""

    def __init__(self, page):
        self.page = page

    def filter(self, has_text=None):
        # Nothing is resolved here - the match runs on each query, as Playwright's does.
        return FakeMatches(self.page, has_text)


class FakeMatches:
    def __init__(self, page, pattern):
        self.page, self.pattern = page, pattern

    @property
    def first(self):
        return FakeRow(self.page, self.pattern)


class FakeContent:
    """`.widget-list-content` - the dashboard body goto_dashboard waits on after clicking."""

    def __init__(self, page):
        self.page = page

    def wait_for(self, **_kwargs):
        self.page.content_waits += 1


class FakeKeyboard:
    def __init__(self, page):
        self.page = page

    def press(self, key):
        self.page.key_presses.append(key)


class FakePage:
    """Rows are real strings; the code's real regex is matched against them."""

    def __init__(self, rows, icon_visible=True, confirm_visible=True,
                 visible_confirm_selector=FRESCO_CONFIRM, row_hidden_for_reads=0):
        self.rows = list(rows)
        self.row_hidden_for_reads = row_hidden_for_reads
        self.icon_visible = icon_visible
        self.confirm_visible = confirm_visible
        self.visible_confirm_selector = visible_confirm_selector
        self.hovered, self.icon_clicks, self.confirm_clicks, self.row_clicks = [], [], [], []
        self.key_presses, self.filter_matches = [], []
        self.content_waits = 0
        self.keyboard = FakeKeyboard(self)

    def locator(self, selector, has_text=None):
        if selector.startswith("#confirm-button") or "confirmdialog-accept-button" in selector:
            return FakeConfirm(self, selector, has_text)
        if selector == ".widget-list-content":
            return FakeContent(self)
        return FakeOptions(self)

    def wait_for_timeout(self, _ms):
        pass


@pytest.fixture
def warnings(monkeypatch):
    captured = []
    monkeypatch.setattr(Util, "warning_screenshot",
                        staticmethod(lambda message, page=None, filename="": captured.append(message)))
    return captured


def _po(page, dropdown_opens=True, name_reads=None):
    """`name_reads` is the sequence get_dashboard_names() returns on successive calls, so a
    test can model the removal landing asynchronously. The last entry repeats."""
    po = object.__new__(PageObjectO11y)
    po.page = page
    po.open_dashboard_dropdown = lambda: dropdown_opens
    reads = list(name_reads if name_reads is not None else [["Default"]])
    po.get_dashboard_names = lambda: reads.pop(0) if len(reads) > 1 else list(reads[0])
    return po


class TestPicksTheRightRow:
    def test_a_name_that_is_a_prefix_of_another_deletes_only_its_own_row(self, warnings):
        """The case that makes a substring match dangerous: SB_dashboard and SB_dashboard_2
        BOTH ship (o11y_dashboard_config.py:195-196). Playwright's has_text is a substring
        match, so the naive locator resolves to both rows and .first silently picks whichever
        the DOM ordered first - destroying a dashboard nobody asked about, while the exact
        verify then blames the intended one for still existing."""
        page = FakePage(rows=["Default", "SB_dashboard", "SB_dashboard_2"])
        po = _po(page, name_reads=[["Default", "SB_dashboard_2"]])

        assert po.delete_dashboard("SB_dashboard") is True

        assert [n for n, _ in page.icon_clicks] == ["SB_dashboard"]
        assert page.hovered == ["SB_dashboard"]
        _pattern, matched = page.filter_matches[0]
        assert matched == ["SB_dashboard"], "the row filter must resolve to exactly one row"

    def test_the_longer_name_is_still_reachable(self, warnings):
        page = FakePage(rows=["Default", "SB_dashboard", "SB_dashboard_2"])
        po = _po(page, name_reads=[["Default", "SB_dashboard"]])

        assert po.delete_dashboard("SB_dashboard_2") is True
        assert [n for n, _ in page.icon_clicks] == ["SB_dashboard_2"]

    def test_surrounding_whitespace_in_the_row_still_matches(self, warnings):
        # get_dashboard_names() strips, so is_dashboard_exists matches a padded row; the delete
        # must agree with it or the two disagree about what exists.
        page = FakePage(rows=["Default", f"  {DASHBOARD}  "])
        po = _po(page, name_reads=[["Default"]])

        assert po.delete_dashboard(DASHBOARD) is True
        assert page.icon_clicks


class TestHappyPath:
    def test_deletes_through_the_row_trash_icon_and_the_visible_confirmation(self, warnings):
        page = FakePage(rows=["Default", DASHBOARD])
        po = _po(page, name_reads=[["Default"]])

        assert po.delete_dashboard(DASHBOARD) is True

        assert page.hovered == [DASHBOARD], "the row is hovered first, as a user must to reveal the icon"
        assert [sel for _, sel in page.icon_clicks] == [".adc-item-delete-icon"]
        assert [sel for sel, _ in page.confirm_clicks] == [FRESCO_CONFIRM]
        assert warnings == []

    def test_the_delete_icon_selector_is_not_tag_pinned(self):
        """A tag-pinned `i.adc-item-delete-icon` is the exact shape that broke this ticket: it
        stops matching the moment the class hops onto a wrapper host. A bare class follows it."""
        assert PageObjectO11y(None).selector_dashboard_delete_icon() == ".adc-item-delete-icon"


class TestTheConfirmationIsThePrimeNGDialog:
    """Ground-truthed on the live CP after the first AC7 run failed here: the o11y
    confirmation is a PrimeNG p-confirmdialog whose accept button has no id and no testid.
    Every `#confirm-button` on the page belongs to the HIDDEN 'Confirm Sign Out' modal -
    measured: `#confirm-button` -> 3 nodes, `#confirm-button:visible` -> 0."""

    def test_the_primeng_accept_button_is_clicked_when_it_is_the_one_rendered(self, warnings):
        page = FakePage(rows=["Default", DASHBOARD], visible_confirm_selector=FRESCO_CONFIRM)
        po = _po(page, name_reads=[["Default"]])

        assert po.delete_dashboard(DASHBOARD) is True
        assert [sel for sel, _ in page.confirm_clicks] == [FRESCO_CONFIRM]

    def test_the_legacy_pulse_modal_is_still_supported(self, warnings):
        # Older CP per backward-compat principle 6 - and it stays :visible-scoped so it can
        # never resolve to the hidden sign-out button.
        page = FakePage(rows=["Default", DASHBOARD], visible_confirm_selector=LEGACY_CONFIRM)
        po = _po(page, name_reads=[["Default"]])

        assert po.delete_dashboard(DASHBOARD) is True
        assert page.confirm_clicks == [(LEGACY_CONFIRM, "Yes")]

    def test_the_legacy_selector_can_never_reach_the_hidden_sign_out_button(self):
        _fresco, legacy = PageObjectO11y(None).selector_dashboard_delete_confirm_button()
        assert ":visible" in legacy

    def test_the_primary_selector_is_scoped_to_the_dialog(self):
        fresco, _legacy = PageObjectO11y(None).selector_dashboard_delete_confirm_button()
        assert fresco.startswith('[data-testid="o11y-confirm-dialog"]')
        assert "p-confirmdialog-accept-button" in fresco
        assert "reject" not in fresco, "the accept button, not No"


class TestVerification:
    def test_an_asynchronous_removal_is_polled_not_read_once(self, warnings):
        """The removal is async. A single read right after the confirm click still lists the
        dashboard - and reporting that as failure skips the rebuild, leaving the instance with
        the dashboard destroyed and never rebuilt: strictly worse than not deleting at all."""
        page = FakePage(rows=["Default", DASHBOARD])
        po = _po(page, name_reads=[["Default", DASHBOARD], ["Default", DASHBOARD], ["Default"]])

        assert po.delete_dashboard(DASHBOARD) is True
        assert warnings == []

    def test_a_dropdown_that_will_not_open_is_not_read_as_a_successful_delete(self, warnings):
        """`get_dashboard_names()` returns [] when the dropdown would not open, and
        `name not in []` is True — so without a guard a dropdown that stopped opening reports
        every delete as a success, and the caller then creates a name that is still taken.
        A real read is never empty: the dropdown always carries the built-in 'Default'."""
        page = FakePage(rows=["Default", DASHBOARD])
        po = _po(page, name_reads=[[]])          # every read fails

        assert po.delete_dashboard(DASHBOARD) is False
        assert any("still listed" in w for w in warnings)

    def test_a_transient_read_failure_still_converges(self, warnings):
        page = FakePage(rows=["Default", DASHBOARD])
        po = _po(page, name_reads=[[], [], ["Default"]])

        assert po.delete_dashboard(DASHBOARD) is True
        assert warnings == []

    def test_a_dashboard_that_never_disappears_is_reported(self, warnings):
        page = FakePage(rows=["Default", DASHBOARD])
        po = _po(page, name_reads=[["Default", DASHBOARD]])

        assert po.delete_dashboard(DASHBOARD) is False
        assert any("still listed" in w for w in warnings)


class TestGotoDashboardUsesTheSameExactRow:
    """`goto_dashboard` is on the hot path of every o11y run and had the identical substring
    bug. Tightening it also introduced a new way to fail - an exact match that misses resolves
    to ZERO rows where the substring one found something - so the click needs a guard."""

    def test_it_navigates_to_the_exact_row_not_a_prefix_match(self, warnings):
        page = FakePage(rows=["Default", "SB_dashboard", "SB_dashboard_2"])
        po = _po(page)
        po.page.locator = page.locator

        assert po.goto_dashboard("SB_dashboard") is True
        assert page.row_clicks == ["SB_dashboard"], "must not land on SB_dashboard_2"
        _pattern, matched = page.filter_matches[0]
        assert matched == ["SB_dashboard"]

    def test_a_missing_dashboard_returns_false_instead_of_burning_the_30s_default(self, warnings):
        page = FakePage(rows=["Default"])
        po = _po(page)

        assert po.goto_dashboard("PromQL_dashboard") is False
        assert any("not in the dropdown" in w for w in warnings)


class TestFailurePaths:
    def test_returns_false_without_clicking_when_the_dropdown_will_not_open(self, warnings):
        page = FakePage(rows=["Default", DASHBOARD])
        po = _po(page, dropdown_opens=False)

        assert po.delete_dashboard(DASHBOARD) is False
        assert page.icon_clicks == []
        assert any("Cannot open dashboard dropdown" in w for w in warnings)

    def test_a_row_the_locator_cannot_match_is_not_reported_as_a_free_name(self, warnings):
        """The third read/absence conflation, and the one with the worst message. The row locator
        matching zero rows is a silent zero-match, not an absence — and the authoritative read
        still lists the dashboard. Reporting "nothing to delete" here sends the caller into
        create_dashboard on a taken name, which fails, and the operator is then told the
        dashboard WAS DELETED and to re-run — about a dashboard that is perfectly intact."""
        page = FakePage(rows=["Default"])                    # locator can never match the row
        po = _po(page, name_reads=[["Default", DASHBOARD]])  # ...but it IS still listed

        assert po.delete_dashboard(DASHBOARD) is False

        assert page.icon_clicks == []
        assert any("still listed" in w and "not reporting the name as free" in w for w in warnings)

    def test_absent_dashboard_is_a_no_op_AND_a_success(self, warnings):
        """'Already gone' satisfies the postcondition this method promises - the name is free
        for create_dashboard. Returning False would tell should_build_dashboard to skip the
        rebuild, so a benign race would leave the dashboard unbuilt."""
        page = FakePage(rows=["Default"])
        po = _po(page)

        assert po.delete_dashboard(DASHBOARD) is True
        assert page.icon_clicks == []
        assert "Escape" in page.key_presses, "the open dropdown must be dismissed again"

    def test_a_slow_rendering_row_is_polled_for_within_the_same_open_dropdown(self, warnings):
        """The reason the row read is POLLED rather than read once. Reverting both polls back to
        a single `is_visible()` must turn this red: with one read the first miss falls straight
        through to the re-open branch, so `opens` would be 2.

        The sibling test below covers the re-open path, which a bare `is_visible()` also
        satisfies — which is exactly how this change was left unpinned."""
        page = FakePage(rows=["Default", DASHBOARD], row_hidden_for_reads=2)
        po = _po(page, name_reads=[["Default"]])
        opens = {"n": 0}
        po.open_dashboard_dropdown = lambda: (opens.__setitem__("n", opens["n"] + 1), True)[1]

        assert po.delete_dashboard(DASHBOARD) is True

        assert [n for n, _ in page.icon_clicks] == [DASHBOARD]
        assert opens["n"] == 1, "the poll must find the row without needing a re-open"
        assert warnings == []

    def test_a_row_that_appears_only_after_the_reopen_is_still_deleted(self, warnings):
        """The RECOVERY half of the re-read guard: the guard exists because the first read is
        flaky, so the case that matters is the one where re-reading finds the row and the delete
        proceeds normally. Testing only the failure branch would leave the guard's whole reason
        for existing unpinned."""
        page = FakePage(rows=["Default"])            # first look misses the row
        po = _po(page, name_reads=[["Default"]])
        opens = {"n": 0}

        def open_dropdown():
            opens["n"] += 1
            if opens["n"] == 2:
                page.rows.append(DASHBOARD)          # the re-opened dropdown renders it
            return True

        po.open_dashboard_dropdown = open_dropdown

        assert po.delete_dashboard(DASHBOARD) is True
        assert [n for n, _ in page.icon_clicks] == [DASHBOARD]
        assert opens["n"] == 2, "the initial open, then exactly one re-open - not a retry loop"
        assert warnings == []

    def test_a_dropdown_that_will_not_reopen_is_not_reported_as_nothing_to_delete(self, warnings):
        """Sibling of the empty-read conflation: if the re-check cannot re-open the dropdown
        that is a FAILED READ, not an absence. Calling it 'nothing to delete' would send the
        caller off to create a name that may well still be taken."""
        page = FakePage(rows=["Default"])            # first look misses the row
        po = _po(page)
        opens = iter([True, False])                  # ...and the re-open fails
        po.open_dashboard_dropdown = lambda: next(opens, False)

        assert po.delete_dashboard(DASHBOARD) is False
        assert any("Cannot re-open the dashboard dropdown" in w for w in warnings)

    def test_missing_delete_icon_stops_before_any_confirmation(self, warnings):
        page = FakePage(rows=["Default", DASHBOARD], icon_visible=False)
        po = _po(page)

        assert po.delete_dashboard(DASHBOARD) is False
        assert page.icon_clicks == []
        assert page.confirm_clicks == []
        assert any("Delete icon not found" in w for w in warnings)

    def test_missing_confirmation_does_not_leave_a_click_unconfirmed(self, warnings):
        page = FakePage(rows=["Default", DASHBOARD], confirm_visible=False)
        po = _po(page)

        assert po.delete_dashboard(DASHBOARD) is False
        assert page.confirm_clicks == []
        assert any("confirmation did not appear" in w for w in warnings)

    def test_an_unexpected_error_is_contained_not_propagated(self, warnings):
        """A teardown helper must never abort the run: an exception escaping here would reach
        page_o11y's catch-all and Util.exit_error - the same failure class this ticket removes -
        and it would do so after the dashboard was already deleted."""
        page = FakePage(rows=["Default", DASHBOARD])
        po = _po(page)
        po.open_dashboard_dropdown = lambda: (_ for _ in ()).throw(RuntimeError("boom"))

        assert po.delete_dashboard(DASHBOARD) is False
        assert any("boom" in w for w in warnings)
