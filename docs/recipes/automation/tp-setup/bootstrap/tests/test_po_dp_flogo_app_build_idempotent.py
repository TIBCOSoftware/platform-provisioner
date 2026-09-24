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
# PCP-24348 defect B — the Flogo app-build step could not survive the state its own
# retry created.
#
# A deploy-flogo attempt died after the build had already been accepted, the retry
# created a SECOND build with the same name, and from then on every retry failed
# identically and immediately:
#
#   Locator.is_visible: Error: strict mode violation:
#   locator(".app-build-container td:first-child").filter(has_text="rest-flogo-1")
#   resolved to 2 elements
#
# The cruel part is WHICH line raised: the "is a build already there? then skip creating
# one" guard. The check that exists to make the step idempotent was the one that could
# not answer once the step had been run twice, so the run never self-healed - retries 2
# through 5 failed at the same selector and everything downstream was blocked.
#
# These are behaviour tests on a stub DOM (see tests/stub_page.py): they describe a Data
# Plane whose app-build table holds two rows for one app and assert which branch the page
# object takes. Against the pre-fix code they fail with StrictModeViolation, which is the
# whole point - a source grep for ".first" could not tell the difference.

import contextlib
import inspect

import pytest

from page_object.po_dp_flogo import PageObjectDataPlaneFlogo
from utils.naming import app_build_name_pattern
from utils.report import ReportYaml
from utils.util import Util
from tests.stub_page import StubPage, StrictModeViolation

APP = "rest-flogo-1"
DP = "k8s-auto-dp1"
ROWS = ".app-build-container tr"
# Both spellings the page object has ever used to find a build row. A test that only
# described one of them would let the other quietly stay un-narrowed.
NAME_CELLS = (".app-build-container td", ".app-build-container td:first-child")
CREATE_BUTTON = "Create New App Build And Deploy"


@pytest.fixture(autouse=True)
def no_side_effects(monkeypatch):
    """Screenshots/tracing are not the subject; record the calls instead."""
    recorded = {"warnings": [], "errors": []}

    def warn(message, page=None, filename=""):
        recorded["warnings"].append((message, filename))

    def die(message, page=None, filename=""):
        recorded["errors"].append((message, filename))
        raise SystemExit(1)

    monkeypatch.setattr(Util, "warning_screenshot", staticmethod(warn))
    monkeypatch.setattr(Util, "exit_error", staticmethod(die))
    monkeypatch.setattr(Util, "screenshot_page", staticmethod(lambda *a, **k: None))
    return recorded


@pytest.fixture(autouse=True)
def no_report_yaml(monkeypatch):
    """ReportYaml writes to disk and short-circuits the very guards under test."""
    written = {}
    monkeypatch.setattr(ReportYaml, "get_capability_info",
                        staticmethod(lambda *a, **k: written.get("appBuild", "false")))
    monkeypatch.setattr(ReportYaml, "is_app_created", staticmethod(lambda *a, **k: False))
    monkeypatch.setattr(ReportYaml, "set_capability", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(
        ReportYaml, "set_capability_info",
        staticmethod(lambda dp, cap, key, value: written.__setitem__(key, str(value).lower())))
    monkeypatch.setattr(ReportYaml, "set_capability_app", staticmethod(lambda *a, **k: None))
    return written


def _flogo(page):
    """A Flogo page object wired to the stub, with navigation neutralised.

    goto_capability/goto_dataplane are pure navigation - they are covered elsewhere and
    would drag half the Data Plane UI into a test about one table.
    """
    po = PageObjectDataPlaneFlogo.__new__(PageObjectDataPlaneFlogo)
    po.page = page
    po.capability = "flogo"
    po.goto_capability = lambda *a, **k: None
    po.goto_dataplane = lambda *a, **k: None
    po.is_app_created = lambda *a, **k: False
    return po


def _page_with_builds(count):
    """A capability page whose app-build table holds `count` rows for APP."""
    page = StubPage()
    page.set_count(ROWS, count)
    for cell in NAME_CELLS:
        page.set_count(cell, count)
    return page


# --------------------------------------------------------------------------
# app_build_rows - the shared locator every caller must go through
# --------------------------------------------------------------------------

def test_the_row_locator_is_not_narrowed_so_callers_can_count():
    """It must return ALL matching rows: `.first` can never exceed 1, and the duplicate
    warning needs the real number."""
    page = _page_with_builds(2)
    assert _flogo(page).app_build_rows(APP).count() == 2


def test_the_unnarrowed_row_locator_still_trips_strict_mode():
    """Guards the stub as much as the code: if two rows did NOT raise here, every
    assertion below would pass for the pre-fix implementation too."""
    page = _page_with_builds(2)
    with pytest.raises(StrictModeViolation):
        _flogo(page).app_build_rows(APP).is_visible()


def test_the_row_locator_anchors_on_the_name_cell():
    """Filtering on the row's whole text would let a build id or a date column satisfy
    the match - the substring trap PCP-24310 closed for EMS server groups.

    The assertion is on the inner locator's SELECTOR, not just its text. An earlier cut
    checked only the text and was therefore vacuous: swapping `td:first-child` for `td`
    - the exact un-hardened variant this test forbids - left all 11 tests green. Caught
    in review by someone who ran that swap.
    """
    rows = _flogo(StubPage()).app_build_rows(APP)
    assert rows.selector == ROWS

    (cell_selector, pattern), = rows.filters
    assert cell_selector == "td:first-child", "the name must be matched on the name CELL"
    assert pattern.search(APP), "the filter must actually match the app it was built for"


@pytest.mark.parametrize("cell", [
    "rest-flogo-1",
    "  rest-flogo-1  ",            # the cell is padded
    "rest-flogo-1 (9b16a21ff035)",  # ... or carries the build id, as the EMS list does
])
def test_the_name_matcher_accepts_the_real_cell_renderings(cell):
    assert app_build_name_pattern(APP).search(cell)


@pytest.mark.parametrize("cell", ["REST-FLOGO-1", "Rest-Flogo-1", "rest-Flogo-1 (abc)"])
def test_the_name_matcher_stays_case_insensitive(cell):
    """A *string* `has_text` is case-INSENSITIVE; a compiled pattern uses its own flags.
    Without `re.IGNORECASE` this change would have silently narrowed the match as well as
    anchoring it — a different behaviour change from the one intended, in the one function
    whose whole job is to find the right row. Anchoring is deliberate; case is not.
    """
    assert app_build_name_pattern(APP).search(cell)


@pytest.mark.parametrize("cell", [
    "rest-flogo-10",       # THE one that matters: the default app name is rest-flogo-1
    "rest-flogo-12",
    "rest-flogo-1-backup",
    "rest-flogo-1_v2",
    "my-rest-flogo-1",     # ... and it must be anchored at the start, not merely bounded
    "REST-FLOGO-10",       # case-insensitivity must not re-open the prefix hole
])
def test_the_name_matcher_rejects_a_different_app_whose_name_extends_it(cell):
    """`has_text` is a SUBSTRING match. Left bare, a Data Plane holding `rest-flogo-10`
    would make the guard report `rest-flogo-1` as already built, warn about a duplicate
    that does not exist, and let `.first` deploy the wrong build."""
    assert not app_build_name_pattern(APP).search(cell)


@pytest.mark.parametrize("cell", [
    "rest-flogo-1.2",      # the exact row created on a live CP to settle this
    "rest-flogo-1.v2",
    "rest-flogo-1.0.1",
    "REST-FLOGO-1.2",      # case-insensitivity must not re-open the dot hole either
])
def test_the_name_matcher_rejects_a_different_app_whose_name_continues_with_a_dot(cell):
    """PCP-24359 item 5. `(?![\\w-])` bounded the name against word chars and hyphens but
    NOT a dot, so `rest-flogo-1` matched `rest-flogo-1.2` - the `-1` vs `-10` bug one
    character over.

    Not settled by reading the regex. Whether a dot can legally follow the name is a
    question about the live CP, and PCP-24348 deliberately left the end of the name
    unanchored on the strength of PCP-23953, so narrowing it again needed evidence. On a
    real Data Plane (CP 1.21) an app whose Flogo JSON `name` is `rest-flogo-1.2` uploads
    cleanly, `#build-name` accepts it with no `pattern`/`maxlength` and
    `checkValidity() == true`, the build is created, and the App Builds table renders
    `rest-flogo-1.2` ABOVE `rest-flogo-1`. Against the shipped matcher the live table
    matched 2 rows for `rest-flogo-1`; against this one it matches 1.

    A/B: revert the pattern to `(?![\\w-])` and every case here goes red.
    """
    assert not app_build_name_pattern(APP).search(cell)


def test_widening_the_boundary_did_not_break_the_accepted_renderings():
    """The dot exclusion must not narrow what the matcher already accepts. Every known
    real rendering continues with a space or end-of-string, never a dot - so pinning them
    here is what makes the PCP-23953 walk-back impossible to repeat by accident."""
    pattern = app_build_name_pattern(APP)
    for cell in ["rest-flogo-1", "  rest-flogo-1  ", "rest-flogo-1 (9b16a21ff035)"]:
        assert pattern.search(cell), cell


def test_a_dotted_sibling_no_longer_looks_like_a_duplicate():
    """The consequence, not just the regex.

    Applied to the row texts the LIVE App Builds table returned, in the order it returned
    them: `rest-flogo-1.2` sorted ABOVE `rest-flogo-1`. The old matcher selected both, so
    the count()-based guard warned about a duplicate that did not exist and `.first` -
    which flogo_app_deploy drives the action menu off - resolved to `rest-flogo-1.2`, the
    WRONG build to deploy. The matcher now selects exactly the one row that is the app.

    Evaluated against the real pattern and real cell text rather than through StubPage:
    its filter() is a deliberate no-op that models no row selection, and its docstring
    says to put selection assertions here instead of teaching it to match.
    """
    live_rows = ["rest-flogo-1.2", "rest-flogo-1"]
    pattern = app_build_name_pattern(APP)

    selected = [cell for cell in live_rows if pattern.search(cell)]

    assert selected == ["rest-flogo-1"], (
        "a dotted sibling is a different app, not a duplicate - and must not be the row "
        f"that .first hands to flogo_app_deploy (got {selected})")


# --------------------------------------------------------------------------
# flogo_app_build_and_deploy - the idempotency guard
# --------------------------------------------------------------------------

def test_an_existing_build_short_circuits_before_creating_another():
    page = _page_with_builds(1)
    _flogo(page).flogo_app_build_and_deploy(DP, "rest-flogo-1.json", APP)

    assert not page.clicked(CREATE_BUTTON), "a build already exists; nothing to create"


def test_a_duplicated_build_is_answered_not_raised(no_report_yaml):
    """THE regression. Two rows for one app is exactly the state a failed attempt leaves
    behind, and the guard has to say "yes, it exists" so the retry can succeed.

    A/B: against the pre-fix guard - an un-narrowed is_visible() on the name cell - this
    test fails with StrictModeViolation, which is what the pipeline saw on retries 2..5.
    """
    page = _page_with_builds(2)
    _flogo(page).flogo_app_build_and_deploy(DP, "rest-flogo-1.json", APP)

    assert not page.clicked(CREATE_BUTTON), "must not create a THIRD build"
    assert no_report_yaml.get("appBuild") == "true", "the step must report success"


def test_a_duplicated_build_is_reported_rather_than_silently_tolerated(no_side_effects):
    """Recovering is not the same as being fine: the extra build is real, it stays in the
    CP UI, and only a retry can have made it."""
    page = _page_with_builds(2)
    _flogo(page).flogo_app_build_and_deploy(DP, "rest-flogo-1.json", APP)

    warnings = [m for m, _ in no_side_effects["warnings"]]
    assert any(APP in m and "2" in m for m in warnings), warnings


def test_a_single_build_is_not_reported_as_a_duplicate(no_side_effects):
    page = _page_with_builds(1)
    _flogo(page).flogo_app_build_and_deploy(DP, "rest-flogo-1.json", APP)

    assert no_side_effects["warnings"] == []


def test_no_build_at_all_goes_on_to_create_one(no_side_effects):
    """The guard must not become a blanket skip - a Data Plane with no build still needs
    one, and that is the path every clean run takes.

    The run is allowed to fall over once it is inside the 5-step upload wizard: the stub
    models the app-build TABLE, not file uploads. Reaching the wizard at all is the
    assertion - it means the guard did not short-circuit.
    """
    page = StubPage()
    for selector in (ROWS,) + NAME_CELLS:
        page.set_count(selector, 0)
        page.hide(selector)

    with contextlib.suppress(Exception):
        _flogo(page).flogo_app_build_and_deploy(DP, "rest-flogo-1.json", APP)

    assert page.clicked(CREATE_BUTTON)


# --------------------------------------------------------------------------
# flogo_app_deploy - the second table reader
# --------------------------------------------------------------------------

def _deployable_page(count):
    page = _page_with_builds(count)
    page.hide("apps-list td.app-name a")                          # app not deployed yet
    page.hide('flogo-tp-pl-icon[icon="pl-icon-critical-error"]')  # deploy does not error
    return page


def test_deploy_survives_a_duplicated_build_and_acts_on_one_row(no_report_yaml):
    """The other half of the outage: the deploy step polls the same table, and its poll
    was un-narrowed too, so it raised instead of proceeding.

    A/B: against the pre-fix poll this fails with StrictModeViolation.
    """
    page = _deployable_page(2)
    _flogo(page).flogo_app_deploy(DP, APP)

    assert page.clicked('button[data-pl-dropdown-role="toggler"]'), page.clicks
    assert page.clicked("Deploy"), page.clicks


def test_deploy_works_unchanged_with_a_single_build():
    page = _deployable_page(1)
    _flogo(page).flogo_app_deploy(DP, APP)
    assert page.clicked('button[data-pl-dropdown-role="toggler"]')


# --------------------------------------------------------------------------
# the trigger: the transient progress line must not be a hard gate
# --------------------------------------------------------------------------

def test_the_transient_progress_line_is_not_waited_on():
    """'Creating new app build...' is a PROGRESS line, not a state.

    The run that produced the duplicate died here:

        Flogo 'App Build & Deploy' Step 3: 'Finished' page is loaded
        [ERROR] Locator.wait_for: Timeout 30000ms exceeded.

    i.e. the build had already moved past 'Creating...' before the wait started, so a
    build that SUCCEEDED was reported as a failure - and the retry that followed is what
    created the second build. Only the terminal 'Successfully created app build' is worth
    gating on.

    Source-based on purpose, and the limits are real: it pins that the hard wait does not
    come back, not what the method does. Driving the whole 5-step wizard on a stub to
    reach line ~390 would test the file-upload plumbing far more than this one line.
    """
    source = inspect.getsource(PageObjectDataPlaneFlogo.flogo_app_build_and_deploy)
    for line in source.splitlines():
        code = line.split("#", 1)[0]
        if "Creating new app build" in code:
            assert ".wait_for(" not in code, (
                "the transient progress line is a hard gate again: " + line.strip())

    # ... and the terminal state IS still polled. Without this half, deleting the wait
    # outright would satisfy the assertion above.
    assert "Successfully created app build" in source
    assert "check_dom_visibility" in source


# --------------------------------------------------------------------------
# The matcher has one owner, and it is not this page object (PCP-24380)
# --------------------------------------------------------------------------

def test_the_name_matcher_lives_in_the_shared_naming_module():
    """It moved out of PageObjectDataPlaneFlogo when the EMS capability card turned out to
    need exactly the same anchored matcher: a Data Plane can hold both `ems-sn` and
    `ems-sn-2`, so a bare substring accepts the wrong card.

    The anchor does not make the EMS GUI path multi-server-safe, and this docstring used to
    imply it did. `is_capability_provisioned` raises strict-mode on its un-narrowed OUTER
    `capability-card #ems` locator before the pattern is applied, swallows the error and
    returns False - so with two or more EMS servers the GUI verification path fails
    (one card -> True, three -> False on a live CP 1.21). Pre-existing, out of scope for
    PCP-24380; the detail lives on po_dataplane.is_capability_provisioned.

    po_dp_ems importing po_dp_flogo to borrow it would be a sideways dependency between
    two unrelated capability wizards, and copying it would be the PCP-23953 mistake in a
    new place - this file's whole subject is what happens when the matcher is wrong in one
    of two copies.
    """
    from utils import naming

    assert naming.app_build_name_pattern is naming.capability_instance_name_pattern
    assert "app_build_name_pattern" not in vars(PageObjectDataPlaneFlogo), (
        "the matcher must be called from utils.naming, not redefined on the page object")
    # ... and the call site really does use the shared one.
    source = inspect.getsource(PageObjectDataPlaneFlogo.app_build_rows)
    assert "self.app_build_name_pattern(" not in source, source
    assert "app_build_name_pattern(app_name)" in source, source
