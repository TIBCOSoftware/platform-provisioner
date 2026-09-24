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
# PCP-23927 case 3 — contract smoke for the o11y filter-dialog left nav.
#
# CP 1.21 rebuilt this nav as a PrimeNG p-menu. The row class went from `.menu-item` to
# `.p-menu-item` — a DIFFERENT CSS token, so the old selector matched NOTHING and clicking
# "Chart Presentation" timed out after 30s while the item sat plainly visible on screen.
# The label also moved into a `.p-menu-item-label` span, so text matching alone would have
# hit the span rather than a clickable row.
#
# Selectors ground-truthed against live CP 1.21.0 (ins-owen-tas-1), read out of the failing
# run's own Playwright trace and then re-confirmed by driving the live dialog:
#
#   <li role="menuitem" class="p-menu-item" aria-label="Chart Presentation" id="pn_id_1156_1">
#     <div class="p-menu-item-content">
#       <a class="p-ripple p-menu-item-link">
#         <span class="p-menu-item-label">Chart Presentation</span>
#
# The <li>'s role + aria-label are the stable hook; the id is generated per mount.

import inspect
import re

from page_object.po_o11y import PageObjectO11y


class TestFilterDialogMenuSelector:
    def test_selector_targets_the_menuitem_row_by_aria_label(self):
        selector = PageObjectO11y(None).selector_filter_dialog_menu_item("Chart Presentation")
        assert selector.startswith(PageObjectO11y.FILTER_DIALOG), "must be scoped to the dialog"
        assert 'li[role="menuitem"]' in selector, "target the clickable row, not the label span"
        assert 'aria-label="Chart Presentation"' in selector

    def test_selector_does_not_use_the_generated_id(self):
        # ids look like pn_id_1156_1 and change on every mount.
        selector = PageObjectO11y(None).selector_filter_dialog_menu_item("Chart Presentation")
        assert not re.search(r"pn_id_\d+", selector)

    def test_legacy_menu_item_markup_is_still_supported(self):
        # Older CPs keep the pre-PrimeNG `.menu-item` nav; per the project's
        # backward-compatibility rule the old selector must not be dropped.
        src = inspect.getsource(PageObjectO11y.click_filter_dialog_menu_item)
        assert ".menu-item" in src
        assert "has_text=label" in src, "the legacy row carries no aria-label, so match on text"

    def test_waits_for_either_nav_then_branches(self):
        # Which nav renders is version-dependent, so poll for whichever appears and branch
        # once — the same shape as the EMS wizard fix in this ticket.
        #
        # PCP-23946: the gate is built with `.or_()` over the fresco selector and the
        # LABEL-SCOPED legacy row, replacing the `f"{fresco}, {legacy}"` comma selector whose
        # legacy half was unlabelled. Behaviour is pinned in
        # tests/test_po_ems_o11y_behaviour.py::test_legacy_nav_without_the_requested_label_fails_visibly;
        # this only holds the shape.
        src = inspect.getsource(PageObjectO11y.click_filter_dialog_menu_item)
        assert ".or_(" in src, "gate must cover both navs"
        assert "legacy, has_text=label" in src, "the legacy half of the gate must be labelled"
        assert ".first" in src, "the gate must be narrowed or strict mode trips"

    def test_branches_on_visibility_and_narrows_before_clicking(self):
        # The gate polls VISIBILITY, so the branch must too: selecting on mere presence
        # (count() > 0) would take the fresco branch for a hidden — or detached-from-a-prior-
        # mount — node and click something invisible, reproducing the opaque 30s timeout this
        # fix removes. Every click must also be narrowed, or a two-node match trips strict mode.
        src = inspect.getsource(PageObjectO11y.click_filter_dialog_menu_item)
        assert "count() > 0" not in src, "branch on visibility, not presence"
        assert "locator(fresco).first.is_visible()" in src
        for line in src.splitlines():
            code = line.split("#", 1)[0]  # a comment mentioning .click() is not a call site
            if ".click()" in code:
                assert ".first.click()" in code, f"unnarrowed click: {line.strip()}"

    def test_failure_is_observable(self):
        src = inspect.getsource(PageObjectO11y.click_filter_dialog_menu_item)
        assert "Util.check_dom_visibility(" in src
        assert "Util.exit_error(" in src


class TestCallersUseTheSharedHelper:
    def test_chart_presentation_tab_goes_through_the_helper(self):
        src = inspect.getsource(PageObjectO11y.select_instant_chart_type)
        assert "click_filter_dialog_menu_item(" in src
        assert ".menu-item" not in src, "must not re-introduce the broken selector inline"

    def test_custom_filter_menu_goes_through_the_helper(self):
        # click_filter_dialog_menu is the e2e-suite entry point; it had the same broken
        # selector, so both callers must share one implementation.
        src = inspect.getsource(PageObjectO11y.click_filter_dialog_menu)
        assert "click_filter_dialog_menu_item(" in src
        assert ".menu-item" not in src
