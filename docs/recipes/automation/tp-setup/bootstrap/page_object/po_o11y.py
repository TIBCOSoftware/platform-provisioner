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

import re

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from page_object.po_global import PageObjectGlobal
from utils.color_logger import ColorLogger
from utils.e2e_util import E2EUtils
from utils.util import Util

class PageObjectO11y(PageObjectGlobal):
    FILTER_DIALOG = ".widget-filter-dialog-v2"

    def __init__(self, page):
        super().__init__(page)

    def selector_filter_dialog_menu_item(self, label):
        """Stable selector for one section in the filter dialog's left nav (CP 1.21+).

        CP 1.21 rebuilt this nav as a PrimeNG p-menu. The row class went from `.menu-item`
        to `.p-menu-item` — a DIFFERENT class token, so the old selector matches nothing at
        all — and the label moved into a `.p-menu-item-label` span. The <li> carries
        role="menuitem" and aria-label="<section>", which is the stable hook. See PCP-23927.
        """
        return f'{self.FILTER_DIALOG} li[role="menuitem"][aria-label="{label}"]'

    def click_filter_dialog_menu_item(self, label):
        """Open a section of the filter dialog's left nav, on either nav markup.

        Waits for whichever nav rendered, then branches once — the pre-1.21 `.menu-item`
        markup stays supported.
        """
        fresco = self.selector_filter_dialog_menu_item(label)
        legacy = f"{self.FILTER_DIALOG} .menu-item"
        # Gate on the LABELLED legacy row, not on `.menu-item` at large (PCP-23946). The fresco
        # selector already embeds the label; an unlabelled legacy half meant any visible nav row
        # satisfied the gate, so on a pre-1.21 CP whose section had been renamed the code fell
        # through to `.click()` on a zero-match locator - a bare 30s timeout with no screenshot,
        # i.e. the exact failure PCP-23927 exists to remove, relocated onto the legacy path.
        legacy_labelled = self.page.locator(legacy, has_text=label)
        gate = self.page.locator(fresco).or_(legacy_labelled).first
        if not Util.check_dom_visibility(self.page, gate, 2, 30):
            Util.exit_error(f"Filter dialog '{label}' menu item is not visible.", self.page, "o11y-filter-dialog-menu.png")
            return
        # Branch on VISIBILITY, not mere presence, and narrow before clicking. The gate above
        # is satisfied by whichever nav is visible; selecting on count() would take the fresco
        # branch for a hidden-but-present (or detached-from-a-prior-mount) node and click
        # something invisible — reproducing the opaque 30s timeout this fix exists to remove.
        if self.page.locator(fresco).first.is_visible():
            self.page.locator(fresco).first.click()
        else:
            self.page.locator(legacy, has_text=label).first.click()
        print(f"Clicked filter dialog '{label}' menu")

    def goto_left_navbar_o11y(self):
        self.goto_left_navbar("Observability")
        # Gate on the always-present dashboard action row (Add card / Add dashboard / "..." menu).
        # Newer CP renders the header via 'tibco-header' (.header-title) instead of the old
        # '.widget-list-header h1', so waiting on the title text breaks on those versions.
        if not Util.check_dom_visibility(self.page, self.page.locator(".dashboard-actions-row"), 5, 60):
            Util.warning_screenshot("Observability dashboard action row did not appear", self.page, "o11y-not-loaded.png")
        print("Observability page is loaded")

    def get_add_card_button(self):
        return self.page.locator(".dashboard-actions-row button", has_text="Add Card")

    def is_support_add_widget(self):
        try:
            self.get_add_card_button().wait_for(state="visible", timeout=3000)
            is_visible = self.get_add_card_button().is_visible()
            is_enabled = self.get_add_card_button().is_enabled()
            if not is_enabled:
                ColorLogger.warning("Add Card button is visible but disabled")
            return is_visible and is_enabled

        except PlaywrightTimeoutError:
            # wait_for raises Playwright's TimeoutError (not the builtin TimeoutError).
            ColorLogger.warning("Add Card button not found or not visible")
            return False

    def selector_data_plane_dropdown(self):
        # after dataplane dropdown list changed to autocomplete, the dataplane selector also need to be updated
        selector = ".widget-list-header .dataplane-list p-autocomplete .p-autocomplete-dropdown"
        if not self.page.locator(selector).is_visible():
            # if not found, use old selector, for CP 1.14 and earlier versions
            selector = ".widget-list-header p-dropdown"
        return selector

    def selector_none_disabled_data_plane(self, dp_name):
        # after dataplane dropdown list changed to autocomplete, the none disabled item selector also need to be updated
        selector = ".widget-list-header .dataplane-list .dd-item:not(.dd-item-disabled) .dd-item-label span"
        if not self.page.locator(selector, has_text=dp_name).is_visible():
            # if not found, use old selector, for CP 1.14 and earlier versions
            selector = ".p-dropdown-item .dp-item:not(.dp-item-disabled)"
        return selector

    def selector_data_plane_item(self, dp_name):
        # after dataplane dropdown list changed to autocomplete, the none disabled item selector also need to be updated
        selector = ".widget-list-header .dataplane-list .dd-item-label span"
        if not self.page.locator(selector, has_text=dp_name).is_visible():
            # if not found, use old selector, for CP 1.14 and earlier versions
            selector = ".p-dropdown-item .dp-item-label span"
        return selector

    def selector_dialog_footer_btn(self, btn_text):
        selector = ".p-dialog-footer button"
        if not self.page.locator(selector, has_text=btn_text).is_visible():
            # if not found, use old selector, before upgrade to PrimeNG 18
            selector = "p-confirmdialog button"
        return selector

    def selector_dialog_left_menu(self, menu_text):
        # Pick the tree-label class by which one the tree renders, NOT by whether
        # this specific menu_text is currently visible: a level-2 node (e.g. Engine)
        # is not rendered until its parent capability node is expanded, which would
        # otherwise make this fall back to the old class and time out on PrimeNG 18.
        selector = ".categories-menu-panel .p-tree-node-label"
        if self.page.locator(selector).count() == 0:
            # if not found, use old selector, before upgrade to PrimeNG 18
            selector = ".categories-menu-panel .p-treenode-label"
        return selector

    def selector_dialog_left_sub_menu(self, level1_menu):
        """Level-2 tree nodes SCOPED to their level-1 parent.

        CP 1.20 added root category nodes ('Integration Applications',
        'Messaging / Data Grid') whose leaf labels are no longer unique across the
        tree: 'General' is BOTH a root node and a leaf under 'Messaging / Data Grid',
        and it is also a substring of 'Integration General'. An unscoped has_text
        match therefore resolves to several nodes and trips Playwright strict mode.
        Scoping to the parent node makes each level-2 label unambiguous, and is a
        no-op on the older, flat trees.
        """
        label_class = self.selector_dialog_left_menu(level1_menu).rsplit(" ", 1)[-1]
        # A node renders as <li><div class="...-content"> … <span class="...-label">,
        # so `> div` pins the match to the node's OWN header (its children live in a
        # sibling <ul>) and the trailing `ul <label>` then yields only its level-2
        # nodes. The text is matched on a DESCENDANT of that header rather than on the
        # label element itself: Playwright's :text-is resolves to the SMALLEST element
        # holding the text, which for a root category is an inner <div class=
        # "tree-node-root">, not the label span - anchoring on the label directly
        # matches nothing. Searching the header covers both shapes, including older
        # control planes whose label carries the text as a direct child.
        return f'.categories-menu-panel li:has(> div :text-is("{level1_menu}")) ul {label_class}'

    def is_data_plane_in_list(self, dp_name):
        self.page.locator(self.selector_data_plane_dropdown()).click()
        is_available = self.page.locator(self.selector_none_disabled_data_plane(dp_name), has_text=dp_name).count() > 0
        print(f"Check 'Data Plane' dropdown '{dp_name}' is is_available: {is_available}")
        if is_available:
            self.page.locator(self.selector_data_plane_item(dp_name), has_text=dp_name).click()
            print(f"Selected '{dp_name}' in 'Data Plane' dropdown")
        return is_available

    def select_data_plane(self, dp_name):
        self.page.locator(self.selector_data_plane_dropdown()).click()
        print(f"Clicked 'Data Plane' dropdown")
        self.page.locator(self.selector_data_plane_item(dp_name), has_text=dp_name).wait_for(state="visible")
        self.page.locator(self.selector_data_plane_item(dp_name), has_text=dp_name).click()
        print(f"Selected '{dp_name}' in 'Data Plane' dropdown")

    def get_chart_card(self, card_name):
        return self.page.locator(".widget-card", has=self.page.locator('.highcharts-title', has_text=card_name))

    # action menu: "Save Snapshot", "Revert to Snapshot", "Reset Layout"
    def click_action_menu(self, action_item, confirmation=False):
        # tp-o11y-service PCP-21299 (Fresco) wraps this button in a <tibco-button> host,
        # so the .test-reset-layout class moved onto that host and no longer identifies
        # the real <button>. data-testid="widget-more-option-button" is unchanged across
        # the migration (present on both the old <button> and the new <tibco-button>),
        # matching this file's own convention for the sibling Add/Save dashboard buttons
        # (selector_add_dashboard_button / widget-save-dashboard-button below). Scoped to
        # .dashboard-actions-row (its real parent) + .first as a strict-mode safety net,
        # in case any other widget-level control ever reuses the same test-id.
        selector = '.dashboard-actions-row [data-testid="widget-more-option-button"]'
        self.page.locator(selector).first.wait_for(state="visible")
        self.page.locator(selector).first.click()
        print(f"Clicked '...' icon")
        self.page.locator(".p-menu-list li span", has_text=action_item).wait_for(state="visible")
        self.page.locator(".p-menu-list li span", has_text=action_item).click()
        print(f"Clicked '{action_item}' Button")
        if confirmation:
            self.page.locator(self.selector_dialog_footer_btn("Yes"), has_text="Yes").click()
            print(f"Clicked 'Yes' button in '{action_item}' confirmation dialog")
        self.page.wait_for_timeout(500)

    def click_add_widget_button(self):
        self.get_add_card_button().click()
        print(f"Clicked 'Add Card' Button")
        self.page.locator("card-catalog-modal").wait_for(state="visible")
        print(f"'Select card to add' dialog is visible")

    def click_widget_dialog_left_menu(self, level1_menu, level2_menu=None):
        """Navigate the Add Card catalog left tree. Returns True when the requested
        node(s) were found and clicked, False when a node is absent (e.g. the
        'Control Tower' sub-node on a cluster without HAWKCONSOLE/BMDP installed) so
        callers can skip + log gracefully instead of aborting the whole flow. The
        node appears as part of normal page flow, so a bounded wait_for is fine; a
        missing node is the graceful-skip case we catch."""
        # Keep the selector STRING (not the locator object) and re-query each line,
        # per the project's locator convention (CLAUDE.md: never cache a locator).
        sel1 = self.selector_dialog_left_menu(level1_menu)
        try:
            self.page.locator(sel1, has_text=level1_menu).wait_for(state="visible", timeout=15000)
        except PlaywrightTimeoutError:
            # Only a timeout means the node is genuinely absent (graceful skip). Other
            # errors (page closed, bad selector) must surface, not be swallowed as a skip.
            ColorLogger.warning(f"Left menu '{level1_menu}' not found in catalog; skip")
            return False
        self.page.locator(sel1, has_text=level1_menu).click()
        print(f"Clicked 'Left side bar' -> '{level1_menu}' menu")

        if level2_menu:
            sel2 = self.selector_dialog_left_sub_menu(level1_menu)
            try:
                self.page.locator(sel2, has_text=level2_menu).wait_for(state="visible", timeout=10000)
            except PlaywrightTimeoutError:
                # Timeout = sub-node absent (capability not installed) -> graceful skip.
                ColorLogger.warning(f"Left sub-menu '{level1_menu}' -> '{level2_menu}' not found (capability not installed?); skip")
                return False
            self.page.locator(sel2, has_text=level2_menu).click()
            print(f"Clicked 'Left side bar' -> '{level1_menu}' -> '{level2_menu}' menu")
        return True

    def click_widget_dialog_middle_menu(self, middle_menu, data_plane_type=None):
        item_selector = f"li.widget-list-item:has-text('{middle_menu}')"
        if data_plane_type:
            item_selector = f".widgets-menu-panel li.widget-list-item-category:has-text('{data_plane_type}') ~ {item_selector}"

        item = self.page.locator(item_selector).first
        item.hover()
        item.locator(".widget-list-btn-add").click()
        print(f"Clicked '{middle_menu}' menu")

    def select_chart_type_toggle_button(self, chart_type=""):
        self.page.locator(".pl-text-toggle .pl-text-toggle__label", has_text=chart_type).click()
        print(f"Selected '{chart_type}' toggle button")

    def click_add_card_to_dashboard_button(self):
        self.page.locator(".selected-widget-panel-btn-add").click()
        print(f"Clicked 'Add to Dashboard' button")

    def add_widget(self, level1_menu, level2_menu, middle_menu, data_plane_type=None):
        """Add a single catalog card. Returns True on success, False when the card
        can't be added: the 'Add Card' button is disabled (per-dashboard 15-card
        limit) or the requested left-menu node is absent (capability not installed)."""
        if self.get_add_card_button().is_disabled():
            ColorLogger.warning("Add Card button is disabled, cannot add widget")
            return False
        self.click_add_widget_button()
        if not self.click_widget_dialog_left_menu(level1_menu, level2_menu):
            self.close_add_widget_dialog()
            return False
        self.click_widget_dialog_middle_menu(middle_menu, data_plane_type)
        self.page.locator("card-catalog-modal").wait_for(state="detached")
        print(f"'Select card to add' dialog is hidden")
        ColorLogger.success(
            f"Add '{level1_menu}'"
            + (f" -> '{level2_menu}'" if level2_menu else "")
            + f" -> '{middle_menu}'"
            + (f" -> '{data_plane_type}'" if data_plane_type else "")
            + " Card successfully"
        )
        return True

    def add_widgets(self, level1_menu, level2_menu, cards, data_plane_type=None):
        """Batch wrapper over add_widget() for a list of cards sharing the same
        left-menu path. Stops early on the first failure: a disabled 'Add Card'
        button (15-card limit) or a missing left-menu node (e.g. 'Control Tower'
        absent on a non-BMDP cluster) applies to every remaining card in the group,
        so the rest are skipped with a single clear log line instead of retrying."""
        for index, middle_menu in enumerate(cards):
            if not self.add_widget(level1_menu, level2_menu, middle_menu, data_plane_type):
                # The failed card plus every card after it won't be added.
                not_added = len(cards) - index
                ColorLogger.warning(
                    f"Cannot add under '{level1_menu}'"
                    + (f" -> '{level2_menu}'" if level2_menu else "")
                    + f"; {not_added} card(s) in this group were not added"
                )
                return

    def _open_promql_editor(self, level1_menu, level2_menu, card_name, query):
        """Add a PromQL catalog card and fill its auto-opened query editor. A PromQL
        card auto-opens the custom-metrics-filter dialog because it can't be saved
        without a query. Returns True with the editor open (ready for Apply / further
        config), False if the card couldn't be added or the editor didn't open."""
        if self.get_add_card_button().is_disabled():
            ColorLogger.warning("Add Card button is disabled, cannot add PromQL widget")
            return False
        self.click_add_widget_button()
        if not self.click_widget_dialog_left_menu(level1_menu, level2_menu):
            self.close_add_widget_dialog()
            return False
        self.click_widget_dialog_middle_menu(card_name)
        self.page.locator("card-catalog-modal").wait_for(state="detached")

        # The freshly added PromQL card auto-opens its query editor on the next tick.
        filter_dialog = ".widget-filter-dialog-v2"
        if not Util.check_dom_visibility(self.page, self.page.locator(filter_dialog), 2, 15):
            Util.warning_screenshot(f"PromQL query editor did not open for '{card_name}'", self.page, f"o11y-promql-{card_name}.png")
            return False

        # The editor is a CodeMirror instance; type into its contenteditable content.
        # insert_text inserts the whole string in one input event (like a paste), which
        # avoids triggering the per-keystroke autocomplete dropdown that could overlap Apply.
        editor = f"{filter_dialog} .cm-content"
        self.page.locator(editor).click()
        self.page.locator(editor).fill("")
        self.page.keyboard.insert_text(query)
        print(f"Filled PromQL query for '{card_name}': {query}")
        return True

    def apply_filter_dialog(self, label):
        """Wait for the filter dialog's 'Apply' to be ENABLED (it enables only once a
        non-empty query is present, so this also confirms the query landed), click it,
        and wait for the dialog to close. Returns True on success. Re-query + .first
        each poll (avoids stale locators / a strict-mode match on any other 'Apply')."""
        filter_dialog = ".widget-filter-dialog-v2"
        apply_locator = lambda: self.page.locator(f"{filter_dialog} button", has_text="Apply").first
        for _ in range(16):
            btn = apply_locator()
            if btn.is_visible() and btn.is_enabled():
                apply_locator().click()
                self.page.locator(filter_dialog).wait_for(state="detached")
                ColorLogger.success(f"Applied PromQL card '{label}'")
                return True
            self.page.wait_for_timeout(500)
        Util.warning_screenshot(f"PromQL 'Apply' did not enable for '{label}' (query not accepted?)", self.page, f"o11y-promql-apply-{label}.png")
        self.page.keyboard.press("Escape")  # close the editor so it doesn't block the next card
        return False

    def select_instant_chart_type(self, chart_type):
        """On the open PromQL Instant editor, switch to the 'Chart Presentation' tab
        and pick the given Chart Type (Single Stat / Bar / Gauge / Pie / Table). The
        p-select renders its options in an overlay appended to <body>."""
        filter_dialog = self.FILTER_DIALOG
        self.click_filter_dialog_menu_item("Chart Presentation")
        chart_select = f"{filter_dialog} .instant-chart-type-section p-select"
        self.page.locator(chart_select).wait_for(state="visible")
        self.page.locator(chart_select).click()
        option = self.page.locator(
            ".p-select-overlay .p-select-option, .p-dropdown-panel .p-dropdown-item, [role='option']",
            has_text=chart_type,
        ).first
        option.wait_for(state="visible")
        option.click()
        print(f"Selected Chart Type '{chart_type}'")

    def add_promql_widget(self, level1_menu, level2_menu, card_name, query):
        """Add a PromQL Range card (PCP-20424): fill the auto-opened query editor and
        Apply. Initialises the card to a valid, runnable query."""
        if not self._open_promql_editor(level1_menu, level2_menu, card_name, query):
            return False
        return self.apply_filter_dialog(card_name)

    def add_promql_instant_widget(self, level1_menu, level2_menu, card_name, query, chart_type, title):
        """Add a PromQL Instant card (PCP-20424) set to a specific Chart Type and
        renamed to `title`, so multiple instant cards (one per chart type) are
        distinguishable on the dashboard.

        Returns True only when the card is BOTH applied and renamed. The rename is not
        cosmetic here: every instant card comes from the same catalog entry, so without it the
        dashboard carries five cards all reading 'PromQL Instant Query' and the one thing this
        dashboard exists to show - one card per chart type - is gone. Reporting a misnamed card
        as added would let the caller's tally print 'all 6 cards added' on the next rename-
        selector hop, i.e. miss the exact regression the tally was added to catch.
        """
        if not self._open_promql_editor(level1_menu, level2_menu, card_name, query):
            return False
        # A failed rename keeps the catalog name; carry that forward so the Apply log and the
        # screenshot name say what is actually on the card, and keep adding the rest (PCP-24228).
        renamed = self.input_filter_dialog_card_name(card_name, title)
        self.select_instant_chart_type(chart_type)
        applied = self.apply_filter_dialog(title if renamed else card_name)
        if applied and not renamed:
            ColorLogger.warning(f"Card '{card_name}' was added but could not be renamed to '{title}'; "
                                f"it is indistinguishable from the other instant cards")
        return applied and renamed

    # ---------------------------------------------------------------------------
    # Dashboard management (PCP-20053)
    # ---------------------------------------------------------------------------
    def selector_add_dashboard_button(self):
        return '[data-testid="widget-add-dashboard-button"]'

    def has_add_dashboard_button(self):
        """Pre-gate: the per-capability dashboard flow is only supported on CP
        versions that expose the 'Add dashboard' button. Older versions skip it."""
        is_visible = Util.check_dom_visibility(self.page, self.page.locator(self.selector_add_dashboard_button()), 2, 8)
        if not is_visible:
            ColorLogger.warning("'Add dashboard' button not found; this CP version does not support the dashboard flow")
        return is_visible

    def selector_catalog_menu_label(self):
        selector = ".categories-menu-panel .p-tree-node-label"
        if self.page.locator(selector).count() == 0:
            # fallback for versions before the PrimeNG 18 upgrade
            selector = ".categories-menu-panel .p-treenode-label"
        return selector

    def close_add_widget_dialog(self):
        close_button = "card-catalog-modal [data-testid='widget-catalog-modal-close']"
        if self.page.locator(close_button).is_visible():
            self.page.locator(close_button).click()
        else:
            self.page.keyboard.press("Escape")
        self.page.locator("card-catalog-modal").wait_for(state="detached")
        print("Closed 'Select card to add' dialog")

    def get_catalog_menu_labels(self):
        """Open the Add Card catalog once, collect the left-tree node labels
        (root + capability/category labels), then close. Used to decide which
        capability dashboards to create and whether Messaging cards exist."""
        if self.get_add_card_button().is_disabled():
            ColorLogger.warning("Add Card button is disabled, cannot read catalog menu labels")
            return []
        self.click_add_widget_button()
        label_selector = self.selector_catalog_menu_label()
        self.page.locator(label_selector).first.wait_for(state="visible")
        labels = [text.strip() for text in self.page.locator(label_selector).all_inner_texts() if text.strip()]
        self.close_add_widget_dialog()
        print(f"Catalog menu labels: {labels}")
        return labels

    def is_catalog_card_available(self, level1_menu, level2_menu, card_name):
        """Whether a specific card is available under the given left-menu path."""
        if self.get_add_card_button().is_disabled():
            return False
        self.click_add_widget_button()
        # If the left-menu path is absent the card cannot exist under it; honor the
        # nav return value rather than counting cards under whatever panel is showing.
        if not self.click_widget_dialog_left_menu(level1_menu, level2_menu):
            self.close_add_widget_dialog()
            print(f"Card '{card_name}' under '{level1_menu}' available: False (menu not found)")
            return False
        present = self.page.locator("li.widget-list-item", has_text=card_name).count() > 0
        self.close_add_widget_dialog()
        print(f"Card '{card_name}' under '{level1_menu}' available: {present}")
        return present

    def selector_dashboard_option(self):
        return ".p-select-option, .p-dropdown-item, [role='option']"

    def dashboard_option_row(self, name):
        """The ONE dropdown row whose whole text is `name`, matched exactly.

        Playwright's `has_text="<str>"` is a SUBSTRING match, and the shipped dashboard
        set contains a prefix pair - `SB_dashboard` and `SB_dashboard_2`
        (o11y_dashboard_config.py:195-196). A substring match on `SB_dashboard` resolves to
        both rows and `.first` then picks whichever the DOM happens to order first, which for
        a DESTRUCTIVE action means deleting a dashboard nobody asked about. It is also
        asymmetric with is_dashboard_exists, which compares row text for EQUALITY - so the
        wrong row gets deleted and the verify then blames the right one for still existing.
        Anchoring the pattern makes the row match the same rule the existence check uses.
        """
        pattern = re.compile(rf"^\s*{re.escape(name)}\s*$")
        return self.page.locator(self.selector_dashboard_option()).filter(has_text=pattern).first

    def open_dashboard_dropdown(self):
        """Open the header dashboard dropdown (the one listing dashboards, which
        always contains the built-in 'Default'). The Observability header renders
        two dropdowns (data plane + dashboard); pick the one whose panel lists
        'Default'."""
        trigger_selectors = ["shared-header p-select", "shared-header p-dropdown", ".widget-list-header p-dropdown"]
        option_selector = self.selector_dashboard_option()
        overlay = self.page.locator(".p-select-overlay, .p-dropdown-panel")
        for _attempt in range(3):
            # clear any stray overlay so a previous open does not block the trigger click
            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(300)
            for selector in trigger_selectors:
                triggers = self.page.locator(selector)
                count = triggers.count()
                # iterate from last to first: the dashboard dropdown is rendered after the data plane one
                for i in range(count - 1, -1, -1):
                    try:
                        triggers.nth(i).click()
                    except Exception:
                        continue
                    if Util.check_dom_visibility(self.page, overlay.first, 1, 3):
                        if self.page.locator(option_selector, has_text="Default").count() > 0:
                            return True
                    # not the dashboard dropdown, close and try the next one
                    self.page.keyboard.press("Escape")
                    self.page.wait_for_timeout(200)
        ColorLogger.warning("Could not open the dashboard dropdown")
        return False

    def get_dashboard_names(self):
        if not self.open_dashboard_dropdown():
            return []
        names = [text.strip() for text in self.page.locator(self.selector_dashboard_option()).all_inner_texts() if text.strip()]
        self.page.keyboard.press("Escape")
        return names

    def is_dashboard_exists(self, name):
        exists = name in self.get_dashboard_names()
        print(f"Dashboard '{name}' exists: {exists}")
        return exists

    def goto_dashboard(self, name=""):
        """Navigate to a dashboard via the header dashboard dropdown. Empty name
        means the built-in 'Default' dashboard."""
        target = name if name else "Default"
        if not self.open_dashboard_dropdown():
            Util.warning_screenshot(f"Cannot open dashboard dropdown to go to '{target}'", self.page, "o11y-dashboard-dropdown.png")
            return False
        # Exact row, for the same reason delete_dashboard needs one: 'SB_dashboard' is a
        # substring of 'SB_dashboard_2', so a substring match navigates to the wrong dashboard.
        # Guarded, because tightening the match also made a near-miss resolve to ZERO rows where
        # the old substring selector would have found something: an unguarded click would then
        # burn Playwright's 30s default and raise out of a method that promises a bool.
        if not Util.check_dom_visibility(self.page, self.dashboard_option_row(target), 1, 10):
            self.page.keyboard.press("Escape")
            Util.warning_screenshot(f"Dashboard '{target}' is not in the dropdown", self.page, "o11y-dashboard-goto.png")
            return False
        self.dashboard_option_row(target).click()
        self.page.locator(".widget-list-content").wait_for(state="visible")
        print(f"Navigated to dashboard '{target}'")
        return True

    def selector_dashboard_delete_icon(self):
        # Bare class, no `i` tag qualifier: a tag-pinned `i.adc-item-delete-icon` is exactly the
        # shape that broke this ticket - it stops matching the moment the class hops onto a
        # wrapper host, while a bare class follows it.
        return ".adc-item-delete-icon"

    def selector_dashboard_delete_confirm_button(self):
        """The accept ('Yes') button of the delete-dashboard confirmation, on either markup.

        Returns (fresco, legacy). Ground-truthed live on CP 1.21 (ins-owen-o11y-7): the o11y
        confirmation is a PrimeNG confirm dialog, NOT the Pulse `#confirm-button` modal -

            <tibco-confirm-dialog testid="o11y-confirm-dialog">
              <p-confirmdialog> <div class="p-confirmdialog p-dialog"
                                     data-testid="o11y-confirm-dialog" role="alertdialog">
                ... <button class="... p-confirmdialog-accept-button">Yes</button>

        and its accept button carries no id and no data-testid, only the PrimeNG class. Every
        `#confirm-button` on the page belongs to the always-present but HIDDEN 'Confirm Sign
        Out' modal: measured on the live page, `#confirm-button` resolves to 3 nodes and
        `#confirm-button:visible` to 0. The Pulse selector is kept as the legacy branch for
        older CP; `:visible` stays on it so it can never reach the sign-out button.
        """
        fresco = '[data-testid="o11y-confirm-dialog"] .p-confirmdialog-accept-button'
        legacy = "#confirm-button:visible"
        return fresco, legacy

    def delete_dashboard(self, name):
        """Delete a dashboard from the header dropdown. Returns True once the name is free.

        The automation could create dashboards but never remove one (PCP-24228), so on any
        instance that already had a dashboard the create path could not run a second time:
        a fix could not be regression-tested, a half-built dashboard could not self-heal, and
        a re-run that silently SKIPPED the failing step read as a pass.

        Nothing in here may raise. The caller deletes in order to REBUILD, so an exception
        escaping a teardown helper would abort the whole page_o11y run through Util.exit_error
        - the same failure class this ticket exists to remove - and would do it after the
        dashboard was already gone.
        """
        try:
            return self._delete_dashboard(name)
        except Exception as e:
            try:
                # The screenshot is a diagnostic, not the contract. On a dead or navigating page
                # it can raise too, and letting it do so from here would break the one promise
                # this method makes.
                Util.warning_screenshot(f"Deleting dashboard '{name}' failed: {e}", self.page, "o11y-dashboard-delete.png")
            except Exception as screenshot_error:
                ColorLogger.warning(f"Deleting dashboard '{name}' failed: {e} (screenshot also failed: {screenshot_error})")
            return False

    def _delete_dashboard(self, name):
        if not self.open_dashboard_dropdown():
            Util.warning_screenshot(f"Cannot open dashboard dropdown to delete '{name}'", self.page, "o11y-dashboard-dropdown.png")
            return False
        # POLLED, like every other gate here. The caller saw this dashboard EXIST one call ago,
        # so a miss is more likely a half-rendered dropdown than a real absence - and treating it
        # as absent hands the caller a create on a name that is still taken, which fails with an
        # inline duplicate-name error instead of retrying. A single is_visible() would have been
        # the one unpolled read in a method that elsewhere assumes this very read is flaky.
        row_visible = Util.check_dom_visibility(self.page, self.dashboard_option_row(name), 1, 5)
        if not row_visible:
            # The dropdown itself may have closed under us; re-open once and poll again.
            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(1000)
            if not self.open_dashboard_dropdown():
                # A dropdown that will not re-open is a FAILED READ, not an absence - the same
                # conflation as reading `[]` from get_dashboard_names() as a successful delete.
                # Claiming "nothing to delete" here would send the caller off to create a name
                # that may well still be taken.
                Util.warning_screenshot(f"Cannot re-open the dashboard dropdown to confirm '{name}' is gone",
                                        self.page, "o11y-dashboard-dropdown.png")
                return False
            row_visible = Util.check_dom_visibility(self.page, self.dashboard_option_row(name), 1, 5)
        if not row_visible:
            self.page.keyboard.press("Escape")
            # A row the LOCATOR could not match is not the same thing as an absent dashboard - it
            # is the silent zero-match this ticket exists to remove. dashboard_option_row() asks
            # the question a different way than is_dashboard_exists did one call ago (an anchored
            # regex through filter(has_text=...) vs equality over stripped all_inner_texts()), so
            # cross-check the authoritative read before claiming the name is free. An EMPTY read
            # is a failed read, not an absence, exactly as in the verify poll below.
            names = self.get_dashboard_names()
            if not names or name in names:
                Util.warning_screenshot(
                    f"Dashboard '{name}' could not be matched in the dropdown but is still listed; "
                    f"not deleting, and not reporting the name as free",
                    self.page, "o11y-dashboard-delete-row.png")
                return False
            # Genuinely absent IS the postcondition this method promises, so it is a success.
            # Returning False would tell should_build_dashboard to skip the rebuild and leave
            # the instance with no dashboard at all.
            ColorLogger.warning(f"Dashboard '{name}' is not in the dropdown; nothing to delete")
            return True

        # The trash icon sits on the option row and reveals on hover, as it does for a user.
        self.dashboard_option_row(name).hover()
        if not Util.check_dom_visibility(self.page, self.dashboard_option_row(name).locator(self.selector_dashboard_delete_icon()), 1, 5):
            self.page.keyboard.press("Escape")
            Util.warning_screenshot(f"Delete icon not found on the '{name}' dashboard row", self.page, "o11y-dashboard-delete-icon.png")
            return False
        self.dashboard_option_row(name).locator(self.selector_dashboard_delete_icon()).click()
        print(f"Clicked the delete icon for dashboard '{name}'")

        fresco_confirm, legacy_confirm = self.selector_dashboard_delete_confirm_button()
        gate = self.page.locator(fresco_confirm).or_(self.page.locator(legacy_confirm, has_text="Yes")).first
        if not Util.check_dom_visibility(self.page, gate, 1, 10):
            Util.warning_screenshot(f"Delete confirmation did not appear for dashboard '{name}'", self.page, "o11y-dashboard-delete-confirm.png")
            # Every other failure return here leaves the page closed; an overlay left open would
            # block whatever the caller does next.
            self.page.keyboard.press("Escape")
            return False
        # Branch on visibility, matching what the gate polled for - only one markup exists.
        if self.page.locator(fresco_confirm).first.is_visible():
            self.page.locator(fresco_confirm).first.click()
        else:
            self.page.locator(legacy_confirm, has_text="Yes").first.click()
        print(f"Confirmed deletion of dashboard '{name}'")

        # Verify against the dropdown rather than a toast: the delete is only useful here if the
        # name is free for create_dashboard to reuse. POLL it - the removal is asynchronous, and
        # a single stale read would report a completed delete as a failure, which skips the
        # rebuild and leaves the dashboard destroyed. (Waiting on '.widget-list-content' is no
        # barrier at all: it is already visible and stays visible through the delete.)
        # 10 attempts, matching the `check_dom_visibility(page, loc, 1, 10)` budget every other
        # wait in this file uses. A tighter cap would reach the very outcome the poll exists to
        # prevent from the other side: on a slow CP the delete lands AFTER the budget, the caller
        # skips the rebuild, and the dashboard is gone for good. Costs nothing on the happy path -
        # the loop returns on the first clean read.
        attempts = 10
        for attempt in range(attempts):
            self.page.wait_for_timeout(1000)
            # A FAILED read must not read as a successful delete. get_dashboard_names() returns
            # [] when the dropdown would not open, and `name not in []` is True - so without this
            # guard a dropdown that stopped opening would report every delete as a success and
            # the caller would go on to create a name that is still taken. A real read is never
            # empty: the dropdown always carries the built-in 'Default'.
            names = self.get_dashboard_names()
            if names and name not in names:
                ColorLogger.success(f"Deleted dashboard '{name}'")
                return True
            reason = "the dropdown could not be read" if not names else f"dashboard '{name}' is still listed"
            print(f"--- Attempt {attempt + 1}/{attempts}: {reason}, waiting for the delete to land...")
        Util.warning_screenshot(f"Dashboard '{name}' is still listed after deleting it", self.page, "o11y-dashboard-delete-verify.png")
        return False

    def close_add_dashboard_dialog(self):
        close_button = ".add-dashboard-dialog [data-testid='widget-catalog-modal-close']"
        if self.page.locator(close_button).is_visible():
            self.page.locator(close_button).click()
        else:
            self.page.keyboard.press("Escape")

    def create_dashboard(self, name):
        """Add dashboard -> fill name -> Save -> wait for navigation to the new
        (empty) dashboard. Returns True on success. A duplicate/invalid name keeps
        the dialog open with an inline error; in that case it logs and returns False."""
        self.page.locator(self.selector_add_dashboard_button()).click()
        print("Clicked 'Add dashboard' button")
        self.page.locator("#dashboard-name").wait_for(state="visible")
        self.page.locator("#dashboard-name").fill(name)
        print(f"Filled dashboard name '{name}'")
        self.page.locator('[data-testid="widget-save-dashboard-button"]').click()
        print("Clicked 'Save' dashboard button")

        error_locator = self.page.locator(".add-dashboard-dialog .error-message")
        if Util.check_dom_visibility(self.page, error_locator, 1, 3):
            ColorLogger.warning(f"Create dashboard '{name}' failed: {error_locator.inner_text().strip()}")
            self.close_add_dashboard_dialog()
            return False

        # success: the dialog closes and the app navigates to the new empty dashboard
        self.page.locator("#dashboard-name").wait_for(state="hidden")
        self.page.locator(".widget-list-content").wait_for(state="visible")
        ColorLogger.success(f"Created dashboard '{name}'")
        return True

    def click_widget_card_button(self, widget_title, icon_name):
        widget_dom = self.page.locator('custom-metric-widget', has=self.page.locator('.highcharts-title', has_text=widget_title))
        widget_dom.locator(f'custom-metrics-filter .widget-filter-button[title="{icon_name}"]').wait_for(state="visible")
        widget_dom.locator(f'custom-metrics-filter .widget-filter-button[title="{icon_name}"]').click()
        print(f"Clicked '{widget_title}' -> '{icon_name}' button")

    def click_filter_dialog_button(self, label):
        self.page.locator(".widget-filter-dialog-v2 button", has_text=label).click()
        print(f"Clicked Custom Filter -> '{label}' button")

    def click_filter_dialog_menu(self, label):
        self.click_filter_dialog_menu_item(label)

    def selector_filter_dialog_card_name_input(self):
        """The card-title field in the open filter dialog, on either markup (PCP-24228).

        Returns (fresco, legacy). The Fresco migration moved the `title-input` class off the
        <input> and onto the <tibco-inputtext> host, so `input.title-input` matches NOTHING on
        any CP carrying Fresco:

            <tibco-inputtext class="title-input" testid="widget-filter-title-input">
              ... <input data-testid="widget-filter-title-input" class="p-inputtext ...">

        `data-testid` survives the migration - the same trap, in this same file, that
        click_action_menu already hit and fixed (PCP-23371). The legacy class-based selector is
        kept for pre-Fresco CP, as a separate branch rather than a comma selector (which would
        match both and trip strict mode).
        """
        fresco = f'{self.FILTER_DIALOG} input[data-testid="widget-filter-title-input"]'
        legacy = f"{self.FILTER_DIALOG} input.title-input"
        return fresco, legacy

    def input_filter_dialog_card_name(self, current_card_name, new_card_name):
        """Rename the card in the open filter dialog. Returns True when it was renamed.

        A field that is MISSING no longer raises: one unhandled 30s Locator timeout here used
        to abort the entire page_o11y run, which is how every o11y deploy shipped a
        PromQL_dashboard with 1 of 6 cards (PCP-24228). A DOM change that removes the field now
        costs one card's name - a logged warning and a screenshot - instead of the five cards
        that come after it. (A field that is present but un-actionable - disabled, readonly,
        covered - can still raise out of click/fill; that is Playwright's actionability wait,
        and it is a different failure than the one this fix is about.)
        """
        # `.first` for the same reason the input gate below has it: an unnarrowed locator that
        # matches more than one node trips strict mode on is_visible() and on click().
        title_button = f"{self.FILTER_DIALOG} .title-button"
        if not Util.check_dom_visibility(self.page, self.page.locator(title_button).first, 1, 5):
            Util.warning_screenshot(f"Card name edit button is not visible; keep card name '{current_card_name}'",
                                    self.page, "o11y-filter-title-button.png")
            return False
        self.page.locator(title_button).first.click()

        fresco, legacy = self.selector_filter_dialog_card_name_input()
        gate = self.page.locator(fresco).or_(self.page.locator(legacy)).first
        if not Util.check_dom_visibility(self.page, gate, 1, 10):
            Util.warning_screenshot(f"Card name input is not visible; keep card name '{current_card_name}'",
                                    self.page, "o11y-filter-title-input.png")
            return False
        # Branch on VISIBILITY, matching what the gate polled for: only one of the two markups
        # exists on a given CP. fill() clears the field first, so no separate .clear() call.
        selector = fresco if self.page.locator(fresco).first.is_visible() else legacy
        self.page.locator(selector).first.fill(new_card_name)
        print(f"Change Custom Filter -> Card Name From '{current_card_name}' to '{new_card_name}'")
        return True

    def click_filter_dialog_chart_type(self, label):
        self.page.locator('.widget-filter-dialog-v2 label.pl-text-toggle__label[for^="chart-type-"]', has_text=label).click()
        print(f"Clicked Custom Filter -> Chart Type: '{label}'")

    def assert_after_custom_metrics_apply_filter(self, expected_query_params: dict):
        """
        After click 'Apply' button in the filter dialog,
        Wait and verify if the api url request contains the expected query parameters
        :param expected_query_params: need to match query parameters (in dictionary form)
        """
        E2EUtils.assert_api_request_and_response(
            self.page,
            "/o11y/v2/metrics",
            lambda: self.click_filter_dialog_button("Apply"),
            'GET',
            200,
            expected_query_params
        )
