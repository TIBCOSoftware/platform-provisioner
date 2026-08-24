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

"""Pure-logic unit tests for the Observability dashboard/card definitions
(PCP-20053, PCP-20424, PCP-21284). These run without a browser or cluster and guard
the per-dashboard 15-card limit (no card-limit errors), the Spring Boot dashboard
split, the Integration General / Messaging General bulk-add card sets, and the CP
1.20 Messaging / Data Grid reorganisation that carries the ActiveSpaces Health card."""

import pytest

from o11y_dashboard_config import (
    MAX_CARD_COUNT,
    CAPABILITY_DASHBOARDS,
    SB_GROUPS_1,
    SB_GROUPS_2,
    BW_GROUPS,
    FLOGO_GROUPS,
    INTEGRATION_GENERAL_GROUPS,
    MESSAGING_GENERAL_GROUPS,
    MESSAGING_DATA_GRID_CAPABILITY,
    MESSAGING_DATA_GRID_GROUPS,
    ACTIVESPACES_HEALTH_CARD,
    PROMQL_DASHBOARD,
    PROMQL_INSTANT_CHART_TYPES,
)


def _dashboard_cards(spec):
    return [card for _level2, cards in spec["groups"] for card in cards]


def _spec_by_name(name):
    return next(s for s in CAPABILITY_DASHBOARDS if s["name"] == name)


def test_every_capability_dashboard_within_card_limit():
    for spec in CAPABILITY_DASHBOARDS:
        count = len(_dashboard_cards(spec))
        assert count <= MAX_CARD_COUNT, f"{spec['name']} has {count} cards (> {MAX_CARD_COUNT})"


def test_no_duplicate_cards_within_a_submenu():
    # add_widget locates a card by has-text WITHIN a single sub-menu (level2) panel,
    # so titles must be unique per sub-menu to avoid ambiguous matches. The same
    # title may legitimately repeat across different sub-menus (e.g. Integration
    # General exposes "Application Instances" under both Kubernetes and Control
    # Tower), so uniqueness is enforced per sub-menu, not per whole dashboard.
    for spec in CAPABILITY_DASHBOARDS:
        for level2, cards in spec["groups"]:
            assert len(cards) == len(set(cards)), f"{spec['name']} -> {level2} has duplicate cards: {cards}"


def test_spring_boot_split_counts():
    # 23 SB cards exceed the 15-card limit, so they are split 14 + 9.
    assert sum(len(c) for _l, c in SB_GROUPS_1) == 14
    assert sum(len(c) for _l, c in SB_GROUPS_2) == 9


def test_expected_dashboard_names_and_capabilities():
    by_name = {s["name"]: s["capability"] for s in CAPABILITY_DASHBOARDS}
    assert by_name == {
        "BW6_dashboard": "BW6 (Containers)",
        "Flogo_dashboard": "Flogo",
        "BW5_dashboard": "BW5 (Containers)",
        "SB_dashboard": "Spring Boot",
        "SB_dashboard_2": "Spring Boot",
        "Integration_General": "Integration General",
        "Messaging_General": "Messaging General",
        "Messaging_Data_Grid": MESSAGING_DATA_GRID_CAPABILITY,
    }


def test_bw_and_flogo_group_sizes():
    # BW6/BW5 = Engine/Process/Activity x3 = 9; Flogo = Engine 3 + Flow 1 + Activity 1 = 5
    assert sum(len(c) for _l, c in BW_GROUPS) == 9
    assert sum(len(c) for _l, c in FLOGO_GROUPS) == 5


def test_integration_general_dashboard_card_split():
    # PCP-20424: Integration General = 8 = 4 (Kubernetes) + 4 (Control Tower).
    # PromQL moved to its own PROMQL_DASHBOARD.
    by_submenu = {level2: cards for level2, cards in INTEGRATION_GENERAL_GROUPS}
    assert len(by_submenu["Kubernetes"]) == 4
    assert len(by_submenu["Control Tower"]) == 4
    assert len(_dashboard_cards(_spec_by_name("Integration_General"))) == 8


def test_messaging_general_dashboard_card_count():
    # PCP-20424: all 4 EMS cards directly under the Messaging General node (no sub-menu).
    assert [level2 for level2, _cards in MESSAGING_GENERAL_GROUPS] == [None]
    assert len(_dashboard_cards(_spec_by_name("Messaging_General"))) == 4


def test_messaging_data_grid_dashboard_structure():
    # PCP-21284: on CP 1.20 the flat "Messaging General" node became a
    # "Messaging / Data Grid" root with three leaves. 1 EMS health + 1 ActiveSpaces
    # health + 3 EMS server metric cards = 5.
    by_submenu = {level2: cards for level2, cards in MESSAGING_DATA_GRID_GROUPS}
    assert set(by_submenu) == {"Messaging", "Data Grid", "General"}
    assert by_submenu["Data Grid"] == [ACTIVESPACES_HEALTH_CARD]
    assert len(_dashboard_cards(_spec_by_name("Messaging_Data_Grid"))) == 5
    # Every group must be reachable via a level-2 menu; a None level2 would make the
    # add_widget call fall back to the (ambiguous) root node.
    assert all(level2 for level2, _cards in MESSAGING_DATA_GRID_GROUPS)


def test_activespaces_card_title_is_plural():
    # PCP-21323 renamed the card from "ActiveSpace Health" to "ActiveSpaces Health";
    # the automation must assert the final title, and has-text is a substring match,
    # so the singular form would silently keep matching if it ever came back.
    assert ACTIVESPACES_HEALTH_CARD == "ActiveSpaces Health"


def test_legacy_and_new_messaging_dashboards_are_mutually_exclusive():
    # Both specs live in CAPABILITY_DASHBOARDS; only one can ever fire because a
    # given CP renders either the old flat label or the new root label, never both.
    # Guard that they are gated on DIFFERENT labels, so no CP gets two messaging
    # dashboards holding the same EMS cards.
    legacy = _spec_by_name("Messaging_General")["capability"]
    current = _spec_by_name("Messaging_Data_Grid")["capability"]
    assert legacy != current
    # The legacy label must not be a substring of the new one (the catalog gate is an
    # exact list membership test, but keeping them disjoint avoids future confusion).
    assert legacy not in current and current not in legacy
    # The EMS server metric cards moved sub-menu but kept their titles.
    legacy_cards = set(_dashboard_cards(_spec_by_name("Messaging_General")))
    current_cards = set(_dashboard_cards(_spec_by_name("Messaging_Data_Grid")))
    assert legacy_cards < current_cards, "the new dashboard must still cover every legacy EMS card"


def test_promql_dashboard_structure():
    # PCP-20424: dedicated PromQL dashboard = 1 Range card + 1 Instant card per
    # concrete chart type (5), total 6, within the 15-card limit.
    spec = PROMQL_DASHBOARD
    assert spec["submenu"] == "PromQL"
    assert len(spec["range_cards"]) == 1
    assert len(spec["instant_cards"]) == len(PROMQL_INSTANT_CHART_TYPES) == 5
    total = len(spec["range_cards"]) + len(spec["instant_cards"])
    assert total == 6 <= MAX_CARD_COUNT


def test_promql_instant_chart_types_concrete():
    # The five concrete chart types, in the catalog's order; "Auto" is excluded.
    assert PROMQL_INSTANT_CHART_TYPES == ["Single Stat", "Bar", "Gauge", "Pie", "Table"]
    assert "Auto" not in PROMQL_INSTANT_CHART_TYPES
    # Each instant card pairs a chart type with a matching, unique dashboard title.
    chart_types = [ct for _name, _q, ct, _title in PROMQL_DASHBOARD["instant_cards"]]
    titles = [title for _name, _q, _ct, title in PROMQL_DASHBOARD["instant_cards"]]
    assert chart_types == PROMQL_INSTANT_CHART_TYPES
    assert len(titles) == len(set(titles)), f"duplicate instant titles: {titles}"
    for _name, _q, ct, title in PROMQL_DASHBOARD["instant_cards"]:
        assert ct in title, f"title '{title}' should mention its chart type '{ct}'"


def test_promql_queries_non_empty_and_shaped():
    # Range card needs a range vector ([...]); instant card a plain selector.
    range_query = PROMQL_DASHBOARD["range_cards"][0][1]
    assert range_query.strip().endswith("]"), "range query must be a range vector"
    for _name, query, _ct, _title in PROMQL_DASHBOARD["instant_cards"]:
        assert query.strip(), "instant query must be non-empty"
        assert "]" not in query, "instant query must not be a range vector"


@pytest.mark.parametrize("spec", CAPABILITY_DASHBOARDS, ids=lambda s: s["name"])
def test_groups_are_non_empty(spec):
    for level2, cards in spec["groups"]:
        assert cards, f"{spec['name']} -> {level2} has no cards"
