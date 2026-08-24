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

"""Regression tests for the Add Card catalog left-menu selectors (PCP-21284).

CP 1.20 wrapped the catalog tree in root category nodes, which made level-2 labels
ambiguous: 'General' is both a root node AND a leaf under 'Messaging / Data Grid',
and it is a substring of 'Integration General'. The previous code matched a level-2
node with an unscoped `has_text` over the whole tree, so on CP 1.20 that resolves to
three nodes and trips Playwright strict mode.

These run without a browser or cluster: the selector builders are driven through a
stub page and the produced CSS is asserted to express the parent-scoping rule.
"""

import re

import pytest

from o11y_dashboard_config import MESSAGING_DATA_GRID_CAPABILITY, MESSAGING_DATA_GRID_GROUPS
from page_object.po_o11y import PageObjectO11y

MODERN_LABEL = ".p-tree-node-label"
LEGACY_LABEL = ".p-treenode-label"


class _StubLocator:
    def __init__(self, count):
        self._count = count

    def count(self):
        return self._count


class _StubPage:
    """Minimal page double: the selector builders only ask how many elements a
    selector matches, to choose between the PrimeNG 18 and the legacy class names."""

    def __init__(self, primeng18=True):
        self.primeng18 = primeng18

    def locator(self, selector):
        is_modern_selector = MODERN_LABEL in selector
        return _StubLocator(1 if is_modern_selector == self.primeng18 else 0)


def _po(primeng18=True):
    return PageObjectO11y(_StubPage(primeng18))


def test_sub_menu_selector_is_scoped_to_its_parent():
    # The level-2 lookup must start from the parent <li>, so a leaf label is only ever
    # searched inside its own branch of the tree.
    css = _po().selector_dialog_left_sub_menu(MESSAGING_DATA_GRID_CAPABILITY)
    assert css.startswith(".categories-menu-panel li:has(")
    assert f'> div :text-is("{MESSAGING_DATA_GRID_CAPABILITY}")' in css
    assert css.endswith(f"ul {MODERN_LABEL}")


def test_sub_menu_selector_matches_text_below_the_node_header_not_on_the_label():
    # Playwright's :text-is resolves to the SMALLEST element holding the text. A root
    # category renders its title in an inner <div class="tree-node-root">, so pinning
    # :text-is onto the label element itself matches ZERO nodes on CP 1.20 (verified
    # live). The selector must therefore search descendants of the node header.
    css = _po().selector_dialog_left_sub_menu(MESSAGING_DATA_GRID_CAPABILITY)
    assert f'{MODERN_LABEL}:text-is(' not in css, "must not anchor :text-is on the label element"
    assert "> div :text-is(" in css


def test_sub_menu_selector_pins_the_parent_with_exact_text():
    # A substring match on the parent would let the ambiguous 'General' leaf also
    # anchor on 'Integration General'; :text-is is an exact match, has-text is not.
    css = _po().selector_dialog_left_sub_menu("General")
    assert ':text-is("General")' in css
    assert ":has-text" not in css


def test_sub_menu_selector_only_descends_into_the_child_group():
    # `ul <label>` restricts the match to nodes inside the parent's children group;
    # without the `ul` the parent's OWN label would match too.
    css = _po().selector_dialog_left_sub_menu("Flogo")
    parent_part, _, child_part = css.partition(") ")
    assert child_part == f"ul {MODERN_LABEL}"
    assert 'Flogo' in parent_part


def test_sub_menu_selector_pins_the_parent_header_with_a_direct_child_combinator():
    # `> div` keeps the parent match on the node's OWN header row. Without it, an
    # ancestor <li> would also match through its descendants and the level-2 lookup
    # would escape the branch again.
    css = _po().selector_dialog_left_sub_menu("Flogo")
    assert "li:has(> div " in css


def test_sub_menu_selector_falls_back_to_legacy_primeng_classes():
    # Older control planes render .p-treenode-label; backward compatibility is a hard
    # requirement (the automation supports every still-supported CP version).
    css = _po(primeng18=False).selector_dialog_left_sub_menu("Flogo")
    assert LEGACY_LABEL in css
    assert MODERN_LABEL not in css


@pytest.mark.parametrize("level2", [level2 for level2, _cards in MESSAGING_DATA_GRID_GROUPS])
def test_messaging_sub_menus_are_reached_through_the_scoped_selector(level2):
    # Every Messaging / Data Grid group is a level-2 node, so add_widget always takes
    # the scoped path. 'General' in particular MUST NOT be looked up unscoped.
    assert level2
    css = _po().selector_dialog_left_sub_menu(MESSAGING_DATA_GRID_CAPABILITY)
    assert MESSAGING_DATA_GRID_CAPABILITY in css
    # The leaf text is applied by the caller via has_text ON TOP of this selector, so
    # the selector itself must not anchor on a leaf. Assert the anchored form
    # unconditionally: a plain `level2 not in css` check is vacuous for 'Data Grid',
    # which is a substring of the parent label 'Messaging / Data Grid' and so is
    # always present in css regardless of what the builder does.
    assert f':text-is("{level2}")' not in css
    # ...and the ONLY anchored text in the selector is the parent label.
    assert re.findall(r':text-is\("([^"]*)"\)', css) == [MESSAGING_DATA_GRID_CAPABILITY]
