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

"""Unit tests for the ActiveSpaces provisioning page object (PCP-21284).

The ActiveSpaces dialog is a React ("fresco") modal with hashed CSS-module class
names and no element ids, so the whole page object hinges on picking selectors that
survive a re-render: container classes, input `name`s, aria-labels and visible text.
These tests run without a browser or cluster: they exercise the selector builders and
the storage-resource preference logic through a stub page.
"""

import re
from types import SimpleNamespace

import pytest

from page_object import po_dp_activespace as po_activespace_module
from page_object.po_dp_activespace import PageObjectDataPlaneActiveSpaces

DP_NAME = "k8s-auto-dp1"
MESSAGE_STORAGE = "section-messageStorage"
LOG_STORAGE = "section-logStorage"


class _StubLocator:
    def __init__(self, count, recorder=None, selector="", visible=True, visibility=None):
        self._count = count
        self._recorder = recorder
        self._selector = selector
        self._visible = visible
        # per-index visibility, for the multi-mask overlay case
        self._visibility = visibility

    def count(self):
        return self._count

    @property
    def first(self):
        return self

    def nth(self, index):
        if self._visibility is not None:
            return _StubLocator(1, self._recorder, self._selector, self._visibility[index])
        return self

    def is_visible(self):
        return self._visible

    def check(self, force=False):
        if self._recorder is not None:
            self._recorder.append((self._selector, force))


class _StubPage:
    """Page double whose `locator()` returns a match count driven by `matches`, a
    mapping of substring -> count. Any `check()` call is recorded so the tests can
    assert WHICH resource row was selected."""

    def __init__(self, matches=None, visible=True):
        self.matches = matches or {}
        self.visible = visible
        self.checked = []
        self.waits = []

    def locator(self, selector):
        # A `:has-text('X')` filter narrows the match, so when one is present the count
        # is looked up by that filter (absent key => 0 rows matched). Only an unfiltered
        # selector falls back to the plain substring keys. Without this, the generic
        # "li.resources-section__item" key would also answer for filtered selectors and
        # every candidate would look like a hit.
        filter_match = re.search(r":has-text\('([^']*)'\)", selector)
        if filter_match:
            return _StubLocator(self.matches.get(f":has-text('{filter_match.group(1)}')", 0),
                                self.checked, selector, self.visible)
        count = 0
        for fragment, value in self.matches.items():
            if ":has-text(" not in fragment and fragment in selector:
                count = value
        return _StubLocator(count, self.checked, selector, self.visible)

    def wait_for_timeout(self, ms):
        self.waits.append(ms)

    def screenshot(self, **_kwargs):
        # no-op double: the real one writes a PNG under the report dir
        self.screenshots = getattr(self, "screenshots", 0) + 1


class _VanishingOverlayLocator(_StubLocator):
    """Reports the overlay as present until the owning page has slept `linger` times."""

    def __init__(self, page, linger, selector):
        super().__init__(0, page.checked, selector)
        self._page = page
        self._linger = linger

    def _gone(self):
        return len(self._page.waits) >= self._linger

    def count(self):
        return 0 if self._gone() else 1

    def is_visible(self):
        return not self._gone()


class _VanishingOverlayPage(_StubPage):
    """The overlay clears after `linger` poll sleeps."""

    def __init__(self, linger):
        super().__init__()
        self.linger = linger

    def locator(self, selector):
        if ".p-dialog-mask" in selector:
            return _VanishingOverlayLocator(self, self.linger, selector)
        return super().locator(selector)


def _po(matches=None):
    return PageObjectDataPlaneActiveSpaces(_StubPage(matches))


def _pin_storage_class(monkeypatch, value):
    """Swap the module-level ENV reference. ENV itself is a FROZEN dataclass, so its
    attributes cannot be monkeypatched in place; replacing the name the page object
    resolves is the way to pin it without touching real configuration."""
    monkeypatch.setattr(
        po_activespace_module, "ENV",
        SimpleNamespace(TP_AUTO_STORAGE_CLASS=value,
                        TP_AUTO_REPORT_YAML_FILE=po_activespace_module.ENV.TP_AUTO_REPORT_YAML_FILE),
    )
    return value


@pytest.fixture
def storage_class(monkeypatch):
    """Pin ENV.TP_AUTO_STORAGE_CLASS. It is auto-detected from the live cluster, so
    reading the ambient value would make these tests depend on the machine they run on
    (it is 'hostpath' on one box and '' with no cluster reachable)."""
    return _pin_storage_class(monkeypatch, "test-storage-class")


def test_capability_identity_matches_the_provisioned_card():
    # The DP page renders the card as `capability-card #as`, and its instance name is
    # the product name (EMS instead shows the server name the user typed).
    assert PageObjectDataPlaneActiveSpaces.capability == "as"
    assert PageObjectDataPlaneActiveSpaces.capability_name == "ActiveSpaces"


def test_selectors_are_scoped_to_the_modal():
    po = _po()
    modal = PageObjectDataPlaneActiveSpaces.modal
    assert po.selector_environment_radio("Development").startswith(modal)
    assert po.selector_storage_radio(MESSAGE_STORAGE).startswith(modal)
    assert po.selector_eua_checkbox().startswith(modal)
    # The footer lives outside the content container, so it has its own root.
    assert po.selector_footer_button("Provision Now").startswith(PageObjectDataPlaneActiveSpaces.modal_footer)


def test_no_selector_relies_on_a_hashed_css_module_class():
    # The modal's own styling uses CSS-module classes like `_basicConfig_aygax_1`,
    # emitted by the bundler with a hash that changes on every rebuild. Those are
    # recognisable by a LEADING underscore (plain BEM classes such as
    # `resources-section__item` are stable and fine).
    po = _po()
    selectors = [
        po.selector_environment_radio("Development"),
        po.selector_storage_radio(MESSAGE_STORAGE, DP_NAME),
        po.selector_eua_checkbox(),
        po.selector_footer_button("Provision Now"),
    ]
    hashed = re.compile(r"\._[A-Za-z]")
    for selector in selectors:
        assert not hashed.search(selector), f"hashed class name leaked into: {selector}"


def test_environment_radio_matches_the_aria_label_prefix():
    # aria-label is "Development Environment (best effort Kubernetes node scheduling)";
    # anchoring on the prefix keeps the parenthetical free to change.
    css = _po().selector_environment_radio("Development")
    assert "input.p-radiobutton-input" in css
    assert "[aria-label^='Development Environment']" in css


def test_footer_button_uses_exact_text():
    # has-text would also match a future "Provision Now and Configure"-style button.
    assert ":text-is('Provision Now')" in _po().selector_footer_button("Provision Now")


def test_storage_radio_filters_by_resource_row_not_by_the_input():
    # The radio input carries no text; the resource name lives on the <li> row.
    po = _po()
    unfiltered = po.selector_storage_radio(MESSAGE_STORAGE)
    filtered = po.selector_storage_radio(MESSAGE_STORAGE, DP_NAME)
    assert "li.resources-section__item" in unfiltered
    assert f"input[name='{MESSAGE_STORAGE}']" in unfiltered
    assert f":has-text('{DP_NAME}')" in filtered
    assert filtered.index(f":has-text('{DP_NAME}')") < filtered.index("input[name=")


def test_resources_readiness_poll_is_narrowed_to_one_element():
    # The resources widget renders one row PER SECTION (Message Storage, Log Storage),
    # so the readiness poll must narrow to .first — check_dom_visibility calls
    # is_visible(), which raises a strict-mode violation on a multi-match locator.
    # (Regression: this exact violation aborted a live CP 1.20 provisioning run.)
    import inspect
    src = inspect.getsource(PageObjectDataPlaneActiveSpaces.as_provision_capability)
    poll_lines = [ln for ln in src.splitlines() if "check_dom_visibility" in ln and "selector_storage_item" in ln]
    assert poll_lines, "the resources widget readiness poll is missing"
    for line in poll_lines:
        assert ".first" in line, f"readiness poll must narrow to one element: {line.strip()}"


def test_storage_item_selector_is_shared_by_the_poll_and_the_radio():
    # One definition of the row selector, so the poll and the click can never drift.
    po = _po()
    assert po.selector_storage_radio(MESSAGE_STORAGE).startswith(po.selector_storage_item())
    assert po.selector_storage_radio(MESSAGE_STORAGE, DP_NAME).startswith(po.selector_storage_item(DP_NAME))


def test_message_and_log_storage_use_distinct_control_names():
    po = _po()
    assert po.selector_storage_radio(MESSAGE_STORAGE) != po.selector_storage_radio(LOG_STORAGE)


def test_select_storage_prefers_the_data_plane_own_resource():
    # Several storage resources can be offered; the DP's own "<dp>-storage" is the
    # deterministic choice, so a shared/global resource cannot be picked by accident.
    page = _StubPage({"li.resources-section__item": 3, f":has-text('{DP_NAME}-storage')": 1})
    po = PageObjectDataPlaneActiveSpaces(page)
    assert po.select_storage_resource("Message Storage", MESSAGE_STORAGE, DP_NAME) is True
    assert len(page.checked) == 1
    selector, force = page.checked[0]
    assert f":has-text('{DP_NAME}-storage')" in selector
    assert force is True, "PrimeNG hides the real input behind the styled box"


def test_select_storage_matches_the_whole_storage_token_not_the_bare_dp_name():
    # has-text is a SUBSTRING match: filtering on the bare DP name would let
    # 'k8s-auto-dp1' also match a 'k8s-auto-dp10-storage' row and pick the wrong one.
    page = _StubPage({"li.resources-section__item": 2, f":has-text('{DP_NAME}-storage')": 1})
    po = PageObjectDataPlaneActiveSpaces(page)
    po.select_storage_resource("Message Storage", MESSAGE_STORAGE, DP_NAME)
    selector, _force = page.checked[0]
    assert f":has-text('{DP_NAME}-storage')" in selector
    assert f":has-text('{DP_NAME}')" not in selector, "must not filter on the bare DP name"


def test_select_storage_falls_back_to_the_storage_class_naming_convention(storage_class):
    # dp_config_resources_storage() names the resource it creates after
    # ENV.TP_AUTO_STORAGE_CLASS (and EMS filters on exactly that), so a DP whose
    # storage was created by this automation has NO '<dp>-storage' row — the
    # storage-class name must still be preferred over "just take the first".
    page = _StubPage({
        "li.resources-section__item": 3,
        f":has-text('{DP_NAME}-storage')": 0,
        f":has-text('{storage_class}')": 1,
    })
    po = PageObjectDataPlaneActiveSpaces(page)
    assert po.select_storage_resource("Message Storage", MESSAGE_STORAGE, DP_NAME) is True
    selector, _force = page.checked[0]
    assert f":has-text('{storage_class}')" in selector


def test_select_storage_falls_back_to_the_first_offered_resource(storage_class):
    # Neither naming convention matches (e.g. a hand-named storage resource), so the
    # first row must still be selected rather than the section left blank.
    page = _StubPage({
        "li.resources-section__item": 2,
        f":has-text('{DP_NAME}-storage')": 0,
        f":has-text('{storage_class}')": 0,
    })
    po = PageObjectDataPlaneActiveSpaces(page)
    assert po.select_storage_resource("Message Storage", MESSAGE_STORAGE, DP_NAME) is True
    selector, _force = page.checked[0]
    assert ":has-text(" not in selector


def test_select_storage_skips_the_storage_class_tier_when_it_is_unset(monkeypatch):
    # ENV.TP_AUTO_STORAGE_CLASS is auto-detected from the cluster and can legitimately
    # be empty; an empty candidate would build ":has-text('')", which matches EVERY row.
    _pin_storage_class(monkeypatch, "")
    page = _StubPage({"li.resources-section__item": 2, f":has-text('{DP_NAME}-storage')": 0})
    po = PageObjectDataPlaneActiveSpaces(page)
    assert po.select_storage_resource("Message Storage", MESSAGE_STORAGE, DP_NAME) is True
    selector, _force = page.checked[0]
    assert ":has-text('')" not in selector
    assert ":has-text(" not in selector


def test_accept_eua_ticks_the_checkbox_with_force():
    page = _StubPage({".fresco-check-box-container input.p-checkbox-input": 1})
    po = PageObjectDataPlaneActiveSpaces(page)
    assert po.accept_end_user_agreement() is True
    selector, force = page.checked[0]
    assert "p-checkbox-input" in selector
    assert force is True


def test_accept_eua_reports_a_missing_checkbox_instead_of_raising():
    # The EUA is mandatory, so a missing checkbox must abort the flow the same way the
    # other controls do (warn + screenshot + return) rather than letting an unguarded
    # check() blow up with a bare Playwright TimeoutError.
    page = _StubPage({".fresco-check-box-container input.p-checkbox-input": 0})
    po = PageObjectDataPlaneActiveSpaces(page)
    assert po.accept_end_user_agreement() is False
    assert page.checked == [], "must not attempt to tick a checkbox that isn't there"


def test_select_storage_reports_when_no_resource_is_available():
    # Message Storage is mandatory; the caller aborts on False instead of submitting
    # an invalid form and waiting out a provisioning timeout.
    page = _StubPage({"li.resources-section__item": 0})
    po = PageObjectDataPlaneActiveSpaces(page)
    assert po.select_storage_resource("Message Storage", MESSAGE_STORAGE, DP_NAME) is False
    assert page.checked == []


@pytest.mark.parametrize("environment", ["Development", "Production"])
def test_environment_is_parameterised(environment):
    assert f"'{environment} Environment'" in _po().selector_environment_radio(environment)


# --- final success page (regression: PCP-21284, caught on a live CP 1.20 run) -----
# The wizard does NOT close on submit: it swaps the form for a final page reading
# "TIBCO ActiveSpaces(R) provisioned successfully." and stays up until dismissed.

def test_final_page_is_a_distinct_container_from_the_form():
    # Treating "the form detached" as "provisioning finished" is what made the first
    # live run mis-sequence: the form detaches the moment the request is submitted.
    cls = PageObjectDataPlaneActiveSpaces
    assert cls.modal_final_page != cls.modal
    assert cls.modal_final_page.startswith(".fresco-wizard-modal")


def test_close_button_is_scoped_to_the_dialog_and_uses_the_stable_primeng_class():
    css = _po().selector_dialog_close_button()
    assert css.startswith(PageObjectDataPlaneActiveSpaces.modal_dialog)
    assert "button.p-dialog-header-close" in css


def test_success_text_match_avoids_the_trademark_character():
    # The live text is "TIBCO ActiveSpaces® provisioned successfully." Matching the
    # product name would drag U+00AE into a DOM matcher; the page object matches only
    # the plain-English tail. (A ® in a log string is fine - EMS logs one too.)
    import inspect
    src = inspect.getsource(PageObjectDataPlaneActiveSpaces.as_provision_capability)
    matcher_lines = [ln for ln in src.splitlines() if "has_text=" in ln]
    assert any('has_text="provisioned successfully"' in ln for ln in matcher_lines)
    for line in matcher_lines:
        assert "®" not in line, f"trademark char used in a DOM matcher: {line.strip()}"


# --- post-submit overlay (regression: PCP-21284, caught on a live CP 1.20 run) ----
# After 'Provision Now' the modal detaches but a `.p-dialog-mask` overlay lingers and
# swallows pointer events, so navigating straight to the DP page failed with a click
# timeout ("mask intercepts pointer events") AFTER provisioning had already succeeded.

def test_overlay_wait_returns_immediately_when_nothing_is_covering_the_page():
    page = _StubPage({".p-dialog-mask": 0})
    po = PageObjectDataPlaneActiveSpaces(page)
    assert po.wait_for_overlay_to_clear() is True
    assert page.waits == [], "must not sleep when no overlay is present"


def test_overlay_wait_polls_until_the_mask_disappears():
    page = _VanishingOverlayPage(linger=4)
    po = PageObjectDataPlaneActiveSpaces(page)
    assert po.wait_for_overlay_to_clear() is True
    assert len(page.waits) == 4, "should poll exactly until the overlay clears"


def test_overlay_wait_treats_a_hidden_mask_as_cleared():
    # PrimeNG can leave the mask element in the DOM once hidden; presence alone must
    # not be read as "still blocking", or every run would burn the full timeout.
    page = _StubPage({".p-dialog-mask": 1}, visible=False)
    po = PageObjectDataPlaneActiveSpaces(page)
    assert po.wait_for_overlay_to_clear() is True
    assert page.waits == []


def test_overlay_wait_checks_every_mask_not_just_the_first():
    # A hidden leftover mask stacked under a still-visible one must NOT read as
    # "cleared" - that would re-introduce the swallowed-click bug this method fixes.
    page = _StubPage()
    page.locator = lambda selector: _StubLocator(
        2, page.checked, selector, visibility=[False, True]
    ) if ".p-dialog-mask" in selector else _StubLocator(0, page.checked, selector)
    po = PageObjectDataPlaneActiveSpaces(page)
    assert po.wait_for_overlay_to_clear(max_wait=1) is False, "a visible second mask must still block"


def test_overlay_wait_clears_when_all_masks_are_hidden():
    page = _StubPage()
    page.locator = lambda selector: _StubLocator(
        2, page.checked, selector, visibility=[False, False]
    ) if ".p-dialog-mask" in selector else _StubLocator(0, page.checked, selector)
    po = PageObjectDataPlaneActiveSpaces(page)
    assert po.wait_for_overlay_to_clear(max_wait=1) is True


def test_overlay_wait_is_bounded_and_does_not_raise():
    # Provisioning has already been accepted by this point, so a stuck overlay must
    # degrade to a warning + screenshot, never abort the run.
    page = _StubPage({".p-dialog-mask": 1}, visible=True)
    po = PageObjectDataPlaneActiveSpaces(page)
    assert po.wait_for_overlay_to_clear(max_wait=2) is False
    assert len(page.waits) == 4, "max_wait seconds at a 500ms poll interval"
    assert getattr(page, "screenshots", 0) == 1, "a stuck overlay must leave a screenshot"
