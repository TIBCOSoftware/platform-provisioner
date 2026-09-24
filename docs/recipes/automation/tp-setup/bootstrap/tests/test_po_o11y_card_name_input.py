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
# PCP-24228 - the card-title field in the o11y filter dialog.
#
# The Fresco migration moved the `title-input` class off the <input> and onto the
# <tibco-inputtext> host, so `input.title-input` matched NOTHING on current CP:
#
#   <tibco-inputtext class="title-input" testid="widget-filter-title-input">
#     <div class="fc-container"><div class="fc-component">
#       <input data-testid="widget-filter-title-input" class="p-inputtext ...">
#
# Counted live against the CP: `input.title-input` -> 0 elements,
# `input[data-testid="widget-filter-title-input"]` -> 1, fill() verified on it.
#
# The old code called `.clear()` on that 0-match locator, so it burned the 30s default and
# raised - killing the whole page_o11y run and losing 5 of the 6 PromQL cards on EVERY o11y
# deploy. These tests run the real method against tests/stub_page.py and assert on the branch
# it TAKES, so both halves matter: that the fresco DOM is filled, and that a DOM where neither
# markup exists returns False instead of exploding.

import pytest

from page_object.po_o11y import PageObjectO11y
from tests.stub_page import StubPage
from utils.util import Util

FRESCO = '.widget-filter-dialog-v2 input[data-testid="widget-filter-title-input"]'
LEGACY = ".widget-filter-dialog-v2 input.title-input"
TITLE_BUTTON = ".widget-filter-dialog-v2 .title-button"


@pytest.fixture(autouse=True)
def never_exits(monkeypatch):
    """Every case in this file enforces the headline property: nothing on the card-rename path
    may end the run. Util.exit_error calls sys.exit, and one of those here is what cost 5 of the
    6 cards - so it fails the test outright rather than being grepped for in the source, which
    would stay green if it were renamed or reached through a helper."""
    monkeypatch.setattr(Util, "exit_error",
                        staticmethod(lambda message, page=None, filename="": pytest.fail(
                            f"exit_error reached from the card-rename path: {message}")))


@pytest.fixture
def warnings(monkeypatch):
    """Capture Util.warning_screenshot - it would otherwise drive a real Playwright screenshot."""
    captured = []
    monkeypatch.setattr(Util, "warning_screenshot",
                        staticmethod(lambda message, page=None, filename="": captured.append(message)))
    return captured


def _po(page):
    po = object.__new__(PageObjectO11y)
    po.page = page
    return po


class TestSelectorContract:
    def test_the_two_selectors_are_separate_not_one_comma_selector(self):
        # A comma selector matches both and trips Playwright strict mode; the code must branch.
        # (That the selectors resolve on a live CP is proven by the DOM counts recorded on the
        # ticket and by the AC7 run, not by this file - a well-formed selector can still be
        # wrong, which is precisely how this defect shipped.)
        fresco, legacy = PageObjectO11y(None).selector_filter_dialog_card_name_input()
        assert "," not in fresco and "," not in legacy
        assert fresco != legacy


class TestFoundBranch:
    def test_fresco_dom_is_filled_through_the_data_testid_input(self, warnings):
        page = StubPage().hide(LEGACY)          # current CP: the class-based input does not exist
        po = _po(page)

        assert po.input_filter_dialog_card_name("PromQL Instant Query", "Instant Single Stat") is True

        assert page.fills.get(f"{FRESCO}|") == "Instant Single Stat"
        assert page.clicked(TITLE_BUTTON), "the title must be put into edit mode first"
        assert warnings == []

    def test_legacy_dom_still_renames_through_the_class_selector(self, warnings):
        page = StubPage().hide(FRESCO)          # pre-Fresco CP: no data-testid input
        po = _po(page)

        assert po.input_filter_dialog_card_name("Old", "New") is True

        assert page.fills.get(f"{LEGACY}|") == "New"
        assert warnings == []


class TestNotFoundBranch:
    def test_missing_input_warns_and_returns_false_instead_of_raising(self, warnings):
        """The regression that cost 5 of 6 cards: an unhandled Locator timeout here aborted the
        run. A DOM the code cannot drive must now cost this ONE card's name, nothing else."""
        page = StubPage().hide(FRESCO).hide(LEGACY)
        po = _po(page)

        assert po.input_filter_dialog_card_name("PromQL Instant Query", "Instant Bar") is False

        assert page.fills == {}, "nothing may be typed into an element that does not exist"
        assert any("Card name input is not visible" in w for w in warnings)

    def test_missing_title_button_warns_and_returns_false(self, warnings):
        page = StubPage().hide(TITLE_BUTTON)
        po = _po(page)

        assert po.input_filter_dialog_card_name("Old", "New") is False

        assert not page.clicked(TITLE_BUTTON)
        assert any("Card name edit button is not visible" in w for w in warnings)


class TestCallerKeepsGoing:
    """The acceptance criterion - a card-rename failure must not abort the run - driven, not
    grepped. These run the real add_promql_instant_widget with only its neighbours stubbed."""

    def _instrumented(self, page):
        po = _po(page)
        applied = []
        po._open_promql_editor = lambda *_a, **_k: True
        po.select_instant_chart_type = lambda _chart_type: None
        po.apply_filter_dialog = lambda label: applied.append(label) or True
        return po, applied

    def test_the_card_is_still_applied_when_the_rename_fails(self, warnings):
        """AC4: one unreachable field costs that card's NAME, not the cards after it."""
        page = StubPage().hide(FRESCO).hide(LEGACY)     # neither markup: the rename cannot work
        po, applied = self._instrumented(page)

        po.add_promql_instant_widget("Kubernetes", "PromQL", "PromQL Instant Query",
                                     "up", "Bar", "Instant Bar")

        assert applied == ["PromQL Instant Query"], \
            "the card must still be applied, under the name it actually carries"

    def test_a_card_that_could_not_be_renamed_is_not_reported_as_added(self, warnings):
        """Every instant card comes from the same catalog entry, so an unrenamed one is
        indistinguishable from the other four - which is the defect, not a cosmetic loss.
        Reporting it as added would let configure_promql_dashboard's tally print
        'all 6 cards added' on the very rename-selector hop the tally exists to catch."""
        page = StubPage().hide(FRESCO).hide(LEGACY)
        po, _applied = self._instrumented(page)

        assert po.add_promql_instant_widget("Kubernetes", "PromQL", "PromQL Instant Query",
                                            "up", "Bar", "Instant Bar") is False

    def test_a_successful_rename_applies_under_the_new_title(self, warnings):
        page = StubPage().hide(LEGACY)                  # current CP
        po, applied = self._instrumented(page)

        assert po.add_promql_instant_widget("Kubernetes", "PromQL", "PromQL Instant Query",
                                            "up", "Bar", "Instant Bar") is True
        assert applied == ["Instant Bar"]
        assert page.fills.get(f"{FRESCO}|") == "Instant Bar"
