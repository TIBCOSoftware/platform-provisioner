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
# Regression net for the CP 1.21 Environmental Controls -> Engine Variables rebuild
# (PCP-24309), found by actually running the pipeline on the GUI path (PCP-24269)
# rather than by reading the diff.
#
# CP 1.21 rebuilt the table
# as an INLINE ROW EDITOR: the value is plain text until the row's Edit button is
# pressed, and the change is only staged once Confirm is pressed. The old flow clicked
# '#engVars-btn-toggleBoolea', which 1.21 does not render at all, so inner_text() timed
# out after 30s. deploy-bwce burned all 10 retries on it, on all three
# deploy-subscription attempts, and because it is ordered ahead of deploy-bw5ce /
# deploy-ems / create-bmdp it blocked every one of them - the single reason that
# pipeline could not reach SUCCEEDED.
#
# THE THEME, inherited from PCP-24237: this flow may not report success without having
# actually changed anything. A row that offers no way to set the value must FAIL LOUDLY
# - not push an unchanged variable and then record it as enabled.
#
# The same 1.21 rebuild also hit the BMDP Messaging page; that one is a full dialog
# redesign (form wizard -> YAML editor) and is tracked separately as PCP-24310.
#
# A trap worth naming, because it is invisible in a screenshot: every per-row id on the
# 1.21 table carries a " <token>" suffix, and that token is separated by a SPACE. A
# space makes the value unusable as a CSS '#id' selector, so even the ids that KEPT
# their name (engVars-btn-valTrue) stopped matching an exact '#...' lookup. That is why
# these selectors are prefix matchers, and test_row_selectors_are_prefix_matchers below
# exists to stop someone "tidying" them back into '#...'.

from unittest.mock import MagicMock

import pytest

from page_object.po_dp_bwce import (
    ENGVARS_LEGACY_BOOL_TOGGLE,
    ENGVARS_LEGACY_VALUE_TRUE,
    ENGVARS_ROW_BOOL_TOGGLER,
    ENGVARS_ROW_CONFIRM,
    ENGVARS_ROW_EDIT,
    ENGVARS_ROW_VALUE_TRUE,
    ENGVARS_VALUE_CELL,
    PageObjectDataPlaneBWCE,
)

set_true = PageObjectDataPlaneBWCE.set_boolean_engine_variable_true
read_value = PageObjectDataPlaneBWCE.engine_variable_value


def make_row(present, texts=None):
    """A row whose child selectors resolve only for the selectors in `present`.

    Records every click as the selector it landed on, in order, so a test can assert
    the 1.21 sequence actually happened rather than just that the call returned True.

    An absent selector raises from wait_for(), the way Playwright does - not merely
    count()==0. That distinction is load-bearing: the first cut of this fix probed
    the post-Edit controls with count(), which does not wait, so a row still being
    re-rendered read as "absent" and the setter gave up. Live, that passed 1 round
    in 3 while every unit test stayed green. A stub where absence only shows up in
    count() cannot tell those two worlds apart.
    """
    clicks = []
    texts = texts or {}

    def locator(selector):
        found = selector in present
        child = MagicMock()
        child.count.return_value = 1 if found else 0
        child.inner_text.return_value = texts.get(selector, "")
        child.click.side_effect = lambda *a, **k: clicks.append(selector)
        if found:
            child.wait_for.return_value = None
        else:
            child.wait_for.side_effect = TimeoutError(f"no element for {selector}")
        child.first = child
        return child

    row = MagicMock()
    row.locator.side_effect = locator
    row.clicks = clicks
    return row


# --- CP 1.21 inline row editor ---------------------------------------------------------

CP121_ROW = (ENGVARS_ROW_EDIT, ENGVARS_ROW_BOOL_TOGGLER, ENGVARS_ROW_VALUE_TRUE, ENGVARS_ROW_CONFIRM)


def test_cp121_row_is_edited_then_confirmed_in_order():
    row = make_row(CP121_ROW)

    assert set_true(row) is True
    # Order matters: the dropdown does not exist until Edit is pressed, and the value
    # is not staged until Confirm is.
    assert row.clicks == [
        ENGVARS_ROW_EDIT,
        ENGVARS_ROW_BOOL_TOGGLER,
        ENGVARS_ROW_VALUE_TRUE,
        ENGVARS_ROW_CONFIRM,
    ]


def test_controls_that_render_late_are_waited_for_not_snapshotted():
    """The regression this fix itself shipped first time round.

    Clicking Edit re-renders the row, so for a beat the dropdown and Confirm are not
    in the DOM yet. count() has no wait in it, so probing with count() answered 0 and
    the setter reported "this row offers no way to set the value" - on a perfectly
    good CP 1.21 row. Live it passed 1 round in 3; every unit test stayed green,
    because a MagicMock re-renders instantly.

    Here the post-Edit controls report count()==0 but DO become visible. Only an
    implementation that waits can pass.
    """
    clicks = []
    late = {ENGVARS_ROW_BOOL_TOGGLER, ENGVARS_ROW_VALUE_TRUE, ENGVARS_ROW_CONFIRM}

    def locator(selector):
        child = MagicMock()
        # Edit exists in read mode; the rest have not rendered yet at probe time.
        child.count.return_value = 1 if selector == ENGVARS_ROW_EDIT else 0
        child.click.side_effect = lambda *a, **k: clicks.append(selector)
        child.wait_for.return_value = None if selector in late else None
        child.first = child
        return child

    row = MagicMock()
    row.locator.side_effect = locator

    assert set_true(row) is True
    assert clicks == [
        ENGVARS_ROW_EDIT,
        ENGVARS_ROW_BOOL_TOGGLER,
        ENGVARS_ROW_VALUE_TRUE,
        ENGVARS_ROW_CONFIRM,
    ]


def test_cp121_row_never_touches_the_dead_legacy_toggle():
    """The 1.21 selector must not be reached via the legacy branch by accident."""
    row = make_row(CP121_ROW)

    set_true(row)

    assert ENGVARS_LEGACY_BOOL_TOGGLE not in row.clicks
    assert ENGVARS_LEGACY_VALUE_TRUE not in row.clicks


def test_confirm_missing_reports_failure_instead_of_a_staged_nothing():
    """Without Confirm the row stays in edit mode and Push Updates would push nothing.

    Returning True here is exactly the silent success this ticket family exists to
    remove: the caller would go on to record enableTrace=true for a variable still
    sitting at FALSE.
    """
    row = make_row((ENGVARS_ROW_EDIT, ENGVARS_ROW_BOOL_TOGGLER, ENGVARS_ROW_VALUE_TRUE))

    assert set_true(row) is False


@pytest.mark.parametrize(
    "missing",
    [ENGVARS_ROW_EDIT, ENGVARS_ROW_BOOL_TOGGLER, ENGVARS_ROW_VALUE_TRUE, ENGVARS_ROW_CONFIRM],
)
def test_any_missing_control_reports_failure(missing):
    row = make_row(tuple(s for s in CP121_ROW if s != missing))

    assert set_true(row) is False


def test_a_row_offering_nothing_reports_failure():
    """A shell we have never seen must not read as 'already done'."""
    assert set_true(make_row(())) is False


# --- pre-1.21 Plexus table -------------------------------------------------------------


def test_legacy_row_still_toggles_in_place():
    """Old Control Planes are not deprecated on a schedule (bootstrap/CLAUDE.md #6)."""
    row = make_row((ENGVARS_LEGACY_BOOL_TOGGLE, ENGVARS_LEGACY_VALUE_TRUE))

    assert set_true(row) is True
    assert row.clicks == [ENGVARS_LEGACY_BOOL_TOGGLE, ENGVARS_LEGACY_VALUE_TRUE]


def test_legacy_row_does_not_use_the_edit_confirm_wrapper():
    row = make_row((ENGVARS_LEGACY_BOOL_TOGGLE, ENGVARS_LEGACY_VALUE_TRUE) + CP121_ROW)

    set_true(row)

    assert ENGVARS_ROW_EDIT not in row.clicks
    assert ENGVARS_ROW_CONFIRM not in row.clicks


# --- reading the current value ---------------------------------------------------------


def test_value_is_read_from_the_cell_on_cp121():
    row = make_row((ENGVARS_VALUE_CELL,), texts={ENGVARS_VALUE_CELL: " FALSE "})

    assert read_value(row) == "false"


def test_value_is_read_from_the_toggle_on_legacy():
    row = make_row(
        (ENGVARS_LEGACY_BOOL_TOGGLE, ENGVARS_VALUE_CELL),
        texts={ENGVARS_LEGACY_BOOL_TOGGLE: "TRUE", ENGVARS_VALUE_CELL: "FALSE"},
    )

    # The legacy toggle is authoritative where it exists - reading the cell instead
    # would report FALSE for a variable that is already true and re-push it.
    assert read_value(row) == "true"


def test_already_true_is_recognised_so_the_row_is_left_alone():
    row = make_row((ENGVARS_VALUE_CELL,), texts={ENGVARS_VALUE_CELL: "TRUE"})

    assert read_value(row) == "true"


def test_row_selectors_are_prefix_matchers():
    """The 1.21 ids end in ' <token>' - a SPACE - so '#id' cannot match them.

    This is the whole reason the fix is not a one-word rename, and it is invisible
    unless you dump the DOM. Keep it pinned.
    """
    for selector in CP121_ROW:
        assert selector.startswith("[id^="), selector
        assert not selector.startswith("#"), selector


# --- legacy Control Plane, driven against a MODELLED DOM -------------------------------
#
# The cases above use MagicMock, which answers every call truthily and never raises - so
# they prove the branching logic but NOT that the legacy path survives contact with a DOM
# that behaves like Playwright's. StubPage does: count() defaults to 0, click() raises on a
# locator that matches nothing, wait_for() raises when the element is absent, and a
# multi-match is_visible() is a strict-mode violation.
#
# This is the same standard PCP-24237 held its own legacy path to (a legacy DOM driven
# end-to-end to prove it still walks the legacy ids), and it is the standard this fix has
# to meet too: CP 1.21 is not a cutover, old Control Planes keep working
# (bootstrap/CLAUDE.md principle 6).

from tests.stub_page import StubLocator, StubPage, StubTimeout

ROW = "tr.engvar-row"


def build_row(page, present, texts=None):
    """A modelled Engine Variables row exposing exactly the controls in `present`.

    Absent controls get count 0 AND a timing-out wait_for - both, because those are two
    different ways Playwright reports "not there" and the code under test uses both.
    """
    texts = texts or {}
    every = (
        ENGVARS_LEGACY_BOOL_TOGGLE, ENGVARS_LEGACY_VALUE_TRUE, ENGVARS_VALUE_CELL,
        ENGVARS_ROW_EDIT, ENGVARS_ROW_BOOL_TOGGLER, ENGVARS_ROW_VALUE_TRUE, ENGVARS_ROW_CONFIRM,
    )
    for sel in every:
        key = f"{ROW} {sel}"
        if sel in present:
            page.set_count(key, 1)
            page.texts[key] = texts.get(sel, "")
        else:
            page.set_count(key, 0)
            page.time_out_wait_for(key, "visible")
    return StubLocator(page, ROW)


LEGACY_CONTROLS = (ENGVARS_LEGACY_BOOL_TOGGLE, ENGVARS_LEGACY_VALUE_TRUE)
CP121_CONTROLS = (ENGVARS_ROW_EDIT, ENGVARS_ROW_BOOL_TOGGLER, ENGVARS_ROW_VALUE_TRUE, ENGVARS_ROW_CONFIRM)


def test_legacy_dom_end_to_end_walks_only_the_legacy_ids():
    page = StubPage()
    row = build_row(page, LEGACY_CONTROLS, texts={ENGVARS_LEGACY_BOOL_TOGGLE: "FALSE"})

    assert set_true(row) is True
    assert page.clicks == [f"{ROW} {ENGVARS_LEGACY_BOOL_TOGGLE}|", f"{ROW} {ENGVARS_LEGACY_VALUE_TRUE}|"]
    # Not one 1.21 control was touched - on a legacy CP they do not exist, so reaching for
    # them would raise here rather than silently no-op.
    for sel in CP121_CONTROLS:
        assert not page.clicked(sel), sel


def test_legacy_dom_value_is_read_from_the_toggle_not_the_cell():
    """On a legacy CP there is no plain-text value cell to fall back to."""
    page = StubPage()
    row = build_row(page, LEGACY_CONTROLS, texts={ENGVARS_LEGACY_BOOL_TOGGLE: "TRUE"})

    assert read_value(row) == "true"


def test_cp121_dom_end_to_end_walks_only_the_new_ids():
    """Mirror of the legacy case, so both branches are held to the same DOM standard."""
    page = StubPage()
    row = build_row(page, CP121_CONTROLS + (ENGVARS_VALUE_CELL,), texts={ENGVARS_VALUE_CELL: "FALSE"})

    assert read_value(row) == "false"
    assert set_true(row) is True
    assert page.clicks == [f"{ROW} {sel}|" for sel in CP121_CONTROLS]
    for sel in LEGACY_CONTROLS:
        assert not page.clicked(sel), sel


def test_a_dom_offering_neither_shell_fails_instead_of_clicking_nothing():
    """The failure must be a reported False, not a click into the void."""
    page = StubPage()
    row = build_row(page, ())

    assert set_true(row) is False
    assert page.clicks == []


def test_the_modelled_dom_really_punishes_a_wrong_selector():
    """Control for the tests above: this harness is strict, unlike MagicMock.

    Without this, a permissive stub could make every assertion above pass vacuously.
    """
    page = StubPage()
    build_row(page, LEGACY_CONTROLS)

    with pytest.raises(StubTimeout):
        StubLocator(page, ROW).locator(ENGVARS_ROW_EDIT).click()
