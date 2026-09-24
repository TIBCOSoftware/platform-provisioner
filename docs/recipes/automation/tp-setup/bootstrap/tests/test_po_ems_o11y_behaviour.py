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
# PCP-23946 — behavioural coverage for the PCP-23927 (PR #428) EMS/o11y changes, and
# regression tests for the three legacy-path gaps that review left open.
#
# Why a new file: tests/test_po_dp_ems.py and tests/test_po_o11y_filter_menu.py are almost
# entirely `inspect.getsource()` greps and `ast` walks. That is the right technique for the
# properties those modules declare (no React-generated ids, no build-hashed classes), but as
# the primary coverage for a 186-line behavioural change it cannot fail for the reason that
# matters: `assert "EITHER_WIZARD).first" in src` passes for any code that merely mentions the
# string and fails for a behaviour-preserving rename. These drive the page objects against a
# stub DOM instead and assert which branch was taken.

import pytest

from page_object.po_dp_ems import PageObjectDataPlaneEMS
from page_object.po_o11y import PageObjectO11y
from utils.util import Util
from tests.stub_page import StubPage, StubTimeout, StrictModeViolation

FRESCO = ".fresco-wizard-modal-container"
FRESCO_DIALOG = ".fresco-wizard-modal"
LEGACY_STEP = ".resources-content"
FILTER_DIALOG = ".widget-filter-dialog-v2"


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


def _o11y(page):
    po = PageObjectO11y.__new__(PageObjectO11y)
    po.page = page
    return po


def _ems(page):
    po = PageObjectDataPlaneEMS.__new__(PageObjectDataPlaneEMS)
    po.page = page
    return po


# --- o11y filter-dialog nav: which row does it actually click? -----------------------

def test_fresco_nav_clicks_the_aria_labelled_row():
    page = StubPage().hide(f"{FILTER_DIALOG} .menu-item")
    _o11y(page).click_filter_dialog_menu_item("Chart Presentation")
    assert page.clicked('aria-label="Chart Presentation"')


def test_legacy_nav_clicks_the_labelled_row():
    """Pre-1.21 CP: no p-menu, so the labelled `.menu-item` is what must be clicked."""
    page = StubPage().hide('li[role="menuitem"]')
    _o11y(page).click_filter_dialog_menu_item("Chart Presentation")
    assert page.clicked(".menu-item|Chart Presentation")


def test_legacy_nav_without_the_requested_label_fails_visibly(no_side_effects):
    """PCP-23946 item 1 — the regression.

    The gate used to poll the UNLABELLED `.menu-item`, so on a legacy CP any visible nav row
    satisfied it. With the requested section renamed or absent, the code then fell through to
    `.click()` on a zero-match locator: a bare 30s Playwright timeout with no screenshot — the
    exact opaque failure PCP-23927 exists to remove, relocated onto the compatibility path.

    A/B: against the pre-fix gate this test fails with StubTimeout from the click.
    """
    page = (StubPage()
            .hide('li[role="menuitem"]')                       # not 1.21
            .hide(f"{FILTER_DIALOG} .menu-item|Chart Presentation")  # section renamed away
            .show(f"{FILTER_DIALOG} .menu-item"))              # other rows still there

    with pytest.raises(SystemExit):
        _o11y(page).click_filter_dialog_menu_item("Chart Presentation")

    assert no_side_effects["errors"], "must fail through exit_error, with a screenshot"
    assert "Chart Presentation" in no_side_effects["errors"][0][0]
    assert page.clicks == [], "must not click a locator that matches nothing"


def test_the_gate_is_narrowed_when_both_navs_match(no_side_effects):
    """The `.first` on the o11y gate must be load-bearing.

    Both nav markups present (a CP mid-migration, or simply two matching rows) makes the
    `or_()` union resolve to more than one element, which is when real Playwright raises
    a strict-mode violation on an un-narrowed locator.

    A/B: delete `.first` from the gate in po_o11y.py and this test fails with
    StrictModeViolation. Before review, deleting it left the whole suite green — the stub's
    OrLocator.first was inert, so the one assertion that pins this was missing.
    """
    page = StubPage()  # everything visible: fresco row AND labelled legacy row both match

    _o11y(page).click_filter_dialog_menu_item("Chart Presentation")

    assert page.clicked('aria-label="Chart Presentation"'), "narrowing picks the fresco row"
    assert not no_side_effects["errors"]


def test_no_nav_at_all_fails_visibly(no_side_effects):
    page = StubPage().hide('li[role="menuitem"]').hide(f"{FILTER_DIALOG} .menu-item")
    with pytest.raises(SystemExit):
        _o11y(page).click_filter_dialog_menu_item("Chart Presentation")
    assert no_side_effects["errors"]


# --- EMS wizard dispatch: fresco vs legacy -------------------------------------------

def test_fresco_container_dispatches_to_the_fresco_wizard(monkeypatch):
    page = StubPage().hide(LEGACY_STEP)
    po = _ems(page)
    taken = []
    monkeypatch.setattr(po, "ems_provision_fresco_wizard",
                        lambda dp, name: taken.append(("fresco", dp, name)))
    monkeypatch.setattr(po, "ems_verify_capability", lambda *a: None)
    monkeypatch.setattr(po, "goto_dataplane", lambda *a: None)
    monkeypatch.setattr(Util, "click_button_until_enabled", staticmethod(lambda *a, **k: None))
    # the entry-point "already provisioned" card must not short-circuit the dispatch
    page.hide("capability-card #ems .pl-tooltip__trigger")

    po.ems_provision_capability("dp1", "ems1")

    assert taken == [("fresco", "dp1", "ems1")]


def test_only_the_legacy_step_takes_the_legacy_path(monkeypatch):
    """The pre-1.21 path is the least-verified one, so pin that it is still reachable."""
    page = (StubPage().hide(FRESCO).hide("capability-card #ems .pl-tooltip__trigger")
            # Legacy step 1 offers storage rows. Required 'Message Storage' with ZERO rows is
            # now a hard failure (PCP-23953), so a table modelled as empty would abort the run
            # before reaching the step-2/3/4 assertions below — this test is about reaching
            # them, not about storage selection, which tests/test_po_dp_ems_storage_resource_name.py
            # covers against stubs that evaluate the real row-matching regex.
            .set_count("#message-storage-resource-table tr", 1)
            .set_count("#log-storage-resource-table tr", 1))
    po = _ems(page)
    monkeypatch.setattr(po, "ems_provision_fresco_wizard",
                        lambda *a: pytest.fail("must not take the fresco path"))
    monkeypatch.setattr(po, "ems_verify_capability", lambda *a: None)
    monkeypatch.setattr(po, "goto_dataplane", lambda *a: None)
    monkeypatch.setattr(Util, "click_button_until_enabled", staticmethod(lambda *a, **k: None))

    po.ems_provision_capability("dp1", "ems1")

    assert page.clicked("#btnNextCapabilityProvision"), "legacy step 1 Next"
    assert page.clicked("#btn_go_to_dta_pln"), "legacy return to Data Plane"
    assert page.fills.get("#ems-config-capability-instance|") == "ems1"


def test_wizard_detection_survives_two_containers_in_the_dom(monkeypatch):
    """PCP-23946 item 3 — a leftover container from a prior mount must not abort the run.

    A/B: without `.first` the stub raises StrictModeViolation, exactly as Playwright would.
    """
    page = StubPage().hide(LEGACY_STEP).hide("capability-card #ems .pl-tooltip__trigger")
    page.set_count(FRESCO, 2)
    po = _ems(page)
    monkeypatch.setattr(po, "ems_provision_fresco_wizard", lambda *a: None)
    monkeypatch.setattr(po, "ems_verify_capability", lambda *a: None)
    monkeypatch.setattr(po, "goto_dataplane", lambda *a: None)
    monkeypatch.setattr(Util, "click_button_until_enabled", staticmethod(lambda *a, **k: None))

    po.ems_provision_capability("dp1", "ems1")  # must not raise StrictModeViolation


# --- EMS wizard close: a stuck dialog must not fail an already-successful provision ----

def _drive_fresco_wizard(page, monkeypatch, po):
    monkeypatch.setattr(po, "fresco_select_resource", lambda *a, **k: None)
    monkeypatch.setattr(po, "fresco_click_footer_button", lambda *a, **k: None)
    monkeypatch.setattr(po, "goto_dataplane", lambda *a: page.__setattr__("navigated", True))
    monkeypatch.setattr(po, "wait_for_overlay_to_clear", lambda *a, **k: True)


def test_a_stuck_close_dialog_warns_instead_of_failing(monkeypatch, no_side_effects):
    """PCP-23946 item 2.

    The close click and this detach wait are the two waits in the method that are not
    polled/logged/screenshotted, and both fire AFTER provisioning has already succeeded —
    the "particularly misleading failure" wait_for_overlay_to_clear's own docstring warns
    about one line below. It now behaves the same way that helper does.

    A/B: against the pre-fix bare `wait_for(state="detached")` this test fails with StubTimeout.
    """
    page = StubPage().time_out_wait_for(FRESCO_DIALOG, "detached")
    po = _ems(page)
    _drive_fresco_wizard(page, monkeypatch, po)

    po.ems_provision_fresco_wizard("dp1", "ems1")

    assert any("did not detach" in m for m, _ in no_side_effects["warnings"])
    assert getattr(page, "navigated", False), "must still return to the Data Plane"


def test_a_clean_close_warns_about_nothing(monkeypatch, no_side_effects):
    page = StubPage()
    po = _ems(page)
    _drive_fresco_wizard(page, monkeypatch, po)

    po.ems_provision_fresco_wizard("dp1", "ems1")

    assert (FRESCO_DIALOG, "detached") in page.waits
    assert not [m for m, _ in no_side_effects["warnings"] if "did not detach" in m]


# --- EMS verification: a missing card is fatal ----------------------------------------

def test_a_card_that_never_appears_is_fatal(monkeypatch, no_side_effects):
    """page_cli records the capability as provisioned as soon as this returns, so a warning
    here would report a green run for a Data Plane with no EMS."""
    page = StubPage().hide("capability-card #ems")
    po = _ems(page)
    monkeypatch.setattr(po, "is_capability_provisioned", lambda *a, **k: False)

    with pytest.raises(SystemExit):
        po.ems_verify_capability("dp1", "ems1")

    assert no_side_effects["errors"]


def test_a_card_that_appears_is_recorded(monkeypatch):
    page = StubPage()
    po = _ems(page)
    recorded = []
    monkeypatch.setattr(po, "is_capability_provisioned", lambda *a, **k: True)
    monkeypatch.setattr("page_object.po_dp_ems.ReportYaml.set_capability",
                        staticmethod(lambda dp, cap: recorded.append((dp, cap))))

    po.ems_verify_capability("dp1", "ems1")

    assert recorded == [("dp1", "ems")]
