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
# Selector pins for the Assign Permissions "Product Permission" wizard.
#
# Browser-free on purpose: these are the few selector DECISIONS that are correct
# for a reason the CP markup does not make obvious, so an innocent-looking
# "tidy-up" reintroduces a bug that only reproduces on a freshly created BMDP —
# the exact case no reviewer has in front of them. Each pin below records the
# CP-side mechanism that forces the choice.

import os
import re

BOOTSTRAP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PO_USER_MANAGEMENT = os.path.join(BOOTSTRAP_DIR, "page_object", "po_user_management.py")


def _source():
    with open(PO_USER_MANAGEMENT, encoding="utf-8") as f:
        return f.read()


SRC = _source()


class TestWildcardLabelMatcher:
    def test_the_text_matcher_stays_the_bare_prefix(self):
        """The CP renders TWO mutually exclusive wildcard labels and the wording
        depends on the capability AND on whether the data plane has any domains yet:
        "All current and future domains" / "...agents" once domains exist, but
        "All future domains" / "...agents" while there are none. Tightening the
        matcher to any full phrase makes it unmatchable for one of those states —
        and the zero-domain state is exactly the freshly created BMDP this feature
        exists for."""
        matchers = re.findall(r"""has_text=["'](All current and future[^"']*)["']""", SRC)

        assert matchers, "the wildcard label must still be matched by its text prefix"
        for matcher in matchers:
            assert matcher == "All current and future", (
                f"wildcard text matcher was tightened to {matcher!r}; it must stay the "
                "prefix shared by the domains and agents wording"
            )

    def test_the_zero_domain_fallback_keys_on_the_for_attribute_prefix(self):
        """Both label variants are rendered by the same template and share one for
        attribute, for="domain-wildcard-selected-checkbox-{{dp_id}}". That prefix is
        therefore the only selector that matches a BMDP with zero domains, where the
        "All current and future" wording does not exist at all."""
        assert re.search(r"""label\[for\^=["']domain-wildcard-selected-checkbox-["']\]""", SRC), (
            "the zero-domain wildcard label fallback must key on the for-attribute prefix"
        )


class TestSettleSignal:
    def test_the_product_click_is_wrapped_in_the_resource_instances_wait(self):
        """Selecting a product fires GET /resource-instances-details, and ONLY its
        response tells the wizard about the existing domains and flips the wildcard
        checkbox on for an existing grant. aria-checked is pre-seeded to "false", so
        there is no tri-state to distinguish "not granted" from "not loaded yet":
        reading before that response settles and then clicking toggles a live grant
        OFF and rewrites it as per-domain rows."""
        assert "expect_response" in SRC, "the product click must be wrapped in a response wait"
        start = SRC.index("expect_response")
        assert "/resource-instances-details" in SRC[start:start + 400], (
            "the settle predicate must key on the /resource-instances-details GET"
        )


class TestCheckboxInputs:
    def test_the_state_is_read_from_the_named_inputs(self):
        """State is read from the inputs the CP binds its model to
        ([name]='allDomainsSelected' / [name]='allDomainsWriteSelected'), not from
        the label or the container that carries the click handler."""
        assert re.search(r"""name=["']allDomainsSelected["']""", SRC)
        assert re.search(r"""name=["']allDomainsWriteSelected["']""", SRC)

    def test_read_is_never_clicked_separately(self):
        """allReadPermissionsSelected FOLLOWS allWritePermissionsSelected in the CP
        component and the Read input is [disabled] while Write is on, so ticking
        Write already grants read. A separate Read click can only fight the
        component."""
        assert not re.search(r"""has_text=["']Read["']""", SRC), (
            "read access comes for free with Write; a separate Read click must not be added"
        )


class TestUsersTableRowMenu:
    """goto_assign_permissions is the door to the whole wizard, so if its selectors
    miss, every product grant fails before it starts.

    Measured live on a 1.20 control plane: the legacy row-action id
    button#changeME-dropdown-label resolves to ZERO elements and so does
    .pl-dropdown-menu__action - that table moved to PrimeNG and the row action button
    now carries no id at all. The bug stayed hidden for so long because
    set_user_permission() short-circuits before reaching this method; a proactive
    product grant is the first caller that always enters the wizard.
    """

    def test_the_row_menu_trigger_keeps_the_legacy_id_and_gains_a_generic_fallback(self):
        assert "button#changeME-dropdown-label" in SRC, (
            "keep the legacy id first so older control planes behave exactly as before"
        )
        assert re.search(r"""locator\(["']dropdown-button button["']\)""", SRC), (
            "newer control planes render the row action button with no id; the generic "
            "dropdown-button button fallback is what makes the wizard reachable there"
        )

    def test_the_menu_entry_keeps_the_legacy_class_and_gains_the_role_fallback(self):
        assert ".pl-dropdown-menu__action" in SRC, (
            "keep the legacy menu class first; never remove a working selector"
        )
        assert re.search(r"""\[role=['"]menuitem['"]\]""", SRC), (
            "the PrimeNG menu exposes entries as role=menuitem, not .pl-dropdown-menu__action"
        )
