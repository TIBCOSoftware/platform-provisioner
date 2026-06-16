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
(PCP-20053). These run without a browser or cluster and guard the per-dashboard
15-card limit (no card-limit errors) and the Spring Boot dashboard split."""

import pytest

from o11y_dashboard_config import (
    MAX_CARD_COUNT,
    CAPABILITY_DASHBOARDS,
    SB_GROUPS_1,
    SB_GROUPS_2,
    BW_GROUPS,
    FLOGO_GROUPS,
)


def _dashboard_cards(spec):
    return [card for _level2, cards in spec["groups"] for card in cards]


def test_every_capability_dashboard_within_card_limit():
    for spec in CAPABILITY_DASHBOARDS:
        count = len(_dashboard_cards(spec))
        assert count <= MAX_CARD_COUNT, f"{spec['name']} has {count} cards (> {MAX_CARD_COUNT})"


def test_no_duplicate_cards_within_a_dashboard():
    # add_widget locates cards by has-text; duplicate titles in one dashboard would
    # cause ambiguous matches and inflate the card count.
    for spec in CAPABILITY_DASHBOARDS:
        cards = _dashboard_cards(spec)
        assert len(cards) == len(set(cards)), f"{spec['name']} has duplicate cards: {cards}"


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
    }


def test_bw_and_flogo_group_sizes():
    # BW6/BW5 = Engine/Process/Activity x3 = 9; Flogo = Engine 3 + Flow 1 + Activity 1 = 5
    assert sum(len(c) for _l, c in BW_GROUPS) == 9
    assert sum(len(c) for _l, c in FLOGO_GROUPS) == 5


@pytest.mark.parametrize("spec", CAPABILITY_DASHBOARDS, ids=lambda s: s["name"])
def test_groups_are_non_empty(spec):
    for level2, cards in spec["groups"]:
        assert cards, f"{spec['name']} -> {level2} has no cards"
