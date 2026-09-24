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
# Regression net for the CP 1.21 BMDP EMS registration rebuild (PCP-24310), found while
# verifying the GUI path in PCP-24269 and then mapped against the LIVE 1.21 dialog over
# CDP rather than inferred from the diff.
#
# CP 1.21 broke this flow in THREE places, and only the middle one announces itself:
#
#   1. Messaging moved Plexus -> PrimeNG, so '.pl-button__label' matches nothing and the
#      flow timed out for 30s with the button plainly visible.
#   2. The multi-step register wizard became a YAML editor / file-upload dialog.
#   3. The RESULT LIST became a PrimeNG p-datatable. This is the quiet one:
#      'tr.pl-table__row' / 'td.pl-table__cell' match nothing, so the idempotency
#      pre-check answered "not registered" on EVERY run and re-registered, and
#      "td[class*='_healthCell'] svg use" matched nothing, so
#      .get_attribute("href").split() raised AttributeError on None.
#
# THE THEME, inherited from PCP-24237 / PCP-24309: this flow may not report success
# without having actually registered anything. dp_config_ems() writes
# ReportYaml "Added" UNCONDITIONALLY after the register block, so any path that returns
# quietly on failure records an unregistered server group as Added. Several tests below
# exist only to pin that down.
#
# A trap worth naming because it is invisible in a screenshot: the bulk register button's
# accessible name carries the validated count AND changes plurality -
# "Register 0 Server Groups" -> "Register 1 Server Group" - while the per-row action
# button's aria-label becomes exactly "Register" once its row validates. Matching on
# "Register" therefore hits two elements and throws a strict-mode violation. That is why
# the selector keys on "Server Group", and test_register_selector_cannot_match_the_row_button
# exists to stop someone "simplifying" it back.

import os
import re
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import yaml as yaml_lib

from page_object import po_bmdp_config
from page_object.po_bmdp_config import (
    EMS_DONE,
    EMS_HEALTH_ICON,
    EMS_REGISTER_BUTTON_LEGACY,
    EMS_REGISTER_BUTTON_NAME,
    EMS_REGISTER_GROUPS,
    EMS_ROW_STATUS,
    EMS_STATUS_ERROR,
    EMS_STATUS_REGISTERED,
    EMS_STATUS_VALIDATED,
    EMS_VALIDATE_ALL,
    EMS_YAML_EDITOR,
    EMS_YAML_FILE_INPUT,
    PageObjectBMDPConfiguration,
    build_ems_registration_yaml,
)

GROUP = "ems-latest"
CLIENT_URL = "tcp://ems.bw5dm.svc.cluster.local:7222,tcp://ems2.bw5dm.svc.cluster.local:7223"
MONITOR_URL = "http://ems.bw5dm.svc.cluster.local:7220"


# --- the payload ------------------------------------------------------------------------


def test_payload_round_trips_through_yaml():
    """URLs are the reason this is dumped rather than f-string formatted.

    clientUrl is a COMMA-SEPARATED LIST of 'tcp://host:port' - colons, slashes and commas,
    every one of which changes meaning in hand-written YAML. Parsing the output back is
    the only assertion that catches a quoting bug.
    """
    parsed = yaml_lib.safe_load(
        build_ems_registration_yaml(GROUP, CLIENT_URL, MONITOR_URL, "admin", "")
    )

    assert parsed["server_groups"] == [{
        "groupName": GROUP,
        "clientUrl": CLIENT_URL,
        "monitorUrl": MONITOR_URL,
        "registrationUser": "admin",
    }]


def test_empty_password_omits_the_key_rather_than_writing_null():
    """TP_AUTO_K8S_BMDP_BW5_EMS_PASSWORD defaults to '', so this is the DEFAULT path.

    'registrationPass:' with nothing after it parses as None, not '' - an explicit null
    where the dialog's own example marks the field Optional.
    """
    text = build_ems_registration_yaml(GROUP, CLIENT_URL, MONITOR_URL, "admin", "")

    assert "registrationPass" not in text
    assert "registrationPass" not in yaml_lib.safe_load(text)["server_groups"][0]


def test_password_is_included_when_set_and_survives_yaml_metacharacters():
    password = "p@ss: #notacomment"

    group = yaml_lib.safe_load(
        build_ems_registration_yaml(GROUP, CLIENT_URL, MONITOR_URL, "admin", password)
    )["server_groups"][0]

    assert group["registrationPass"] == password


# --- selector shape ----------------------------------------------------------------------


def test_row_lookup_does_not_use_the_dead_plexus_table_classes():
    """Break 3. The 1.21 list is a PrimeNG p-datatable with neither class on its rows.

    Asserted at the LOCATOR CALL, because both callers fail SILENTLY when it is wrong:
    the pre-check re-registers on every run, and the health check crashes on None.
    """
    page = MagicMock()
    po = PageObjectBMDPConfiguration(page)

    po.ems_server_row(GROUP)

    # role=row (not the dead pl-table classes), narrowed by a cell whose text is EXACTLY
    # the group name - so a sibling group that merely contains it cannot match too.
    page.get_by_role.assert_called_once_with("row")
    page.get_by_text.assert_called_once_with(GROUP, exact=True)
    page.locator.assert_not_called()


def test_health_check_survives_a_row_with_no_icon_yet():
    """The old code did .get_attribute("href").split("#") with no guard.

    On 1.21 that selector matched nothing, so get_attribute returned None and the flow
    died with AttributeError instead of reporting "not connected".
    """
    page = MagicMock()
    row = page.get_by_role.return_value.filter.return_value
    row.is_visible.return_value = True
    row.locator.return_value.count.return_value = 0
    po = PageObjectBMDPConfiguration(page)

    po.check_ems_server_status(GROUP)  # must not raise

    row.locator.assert_called_once_with(EMS_HEALTH_ICON)


def test_health_check_survives_get_attribute_returning_none():
    page = MagicMock()
    row = page.get_by_role.return_value.filter.return_value
    row.is_visible.return_value = True
    icon = row.locator.return_value
    icon.count.return_value = 1
    icon.first.get_attribute.return_value = None
    po = PageObjectBMDPConfiguration(page)

    po.check_ems_server_status(GROUP)  # must not raise


def test_health_check_reports_connected_on_the_success_icon(monkeypatch):
    recorded = {}
    monkeypatch.setattr(
        po_bmdp_config.ReportYaml, "set_capability_info",
        lambda _dp, _cap, name, state: recorded.update({name: state}),
    )
    page = MagicMock()
    row = page.get_by_role.return_value.filter.return_value
    row.is_visible.return_value = True
    icon = row.locator.return_value
    icon.count.return_value = 1
    icon.first.get_attribute.return_value = "/cp/web-ui-content/assets/uxpl.icons.svg#pl-icon-success"
    po = PageObjectBMDPConfiguration(page)

    po.check_ems_server_status(GROUP)

    assert recorded == {GROUP: "Connected"}


# --- row status reading -------------------------------------------------------------------


def make_dialog_row(statuses):
    """A dialog row whose status cell reads `statuses` in order, repeating the last one."""
    remaining = list(statuses)
    row = MagicMock()
    cell = MagicMock()
    cell.count.return_value = 1

    def next_text():
        return remaining.pop(0) if len(remaining) > 1 else remaining[0]

    cell.first.inner_text.side_effect = next_text
    row.locator.return_value = cell
    row.status_cell = cell
    return row


def test_status_is_read_through_first_so_a_multi_match_cannot_throw():
    row = make_dialog_row(["  Validated  "])

    assert PageObjectBMDPConfiguration.ems_group_status(row) == EMS_STATUS_VALIDATED

    row.locator.assert_called_once_with(EMS_ROW_STATUS)
    row.status_cell.first.inner_text.assert_called_once()


def test_status_is_empty_when_the_cell_has_not_rendered():
    row = MagicMock()
    row.locator.return_value.count.return_value = 0

    assert PageObjectBMDPConfiguration.ems_group_status(row) == ""


def test_wait_returns_as_soon_as_the_target_appears():
    page = MagicMock()
    po = PageObjectBMDPConfiguration(page)
    row = make_dialog_row(["", "", EMS_STATUS_VALIDATED])

    assert po.wait_for_ems_group_status(row, EMS_STATUS_VALIDATED, 120) == EMS_STATUS_VALIDATED
    # Two pending polls slept, the third matched and returned without sleeping again.
    assert page.wait_for_timeout.call_count == 2


def test_wait_gives_up_immediately_on_error_instead_of_burning_the_budget():
    """Error is terminal - watched holding for 40s live, it never became Validated.

    Polling it for the full 120s would turn a clear failure into a two-minute stall in
    the pipeline log.
    """
    page = MagicMock()
    po = PageObjectBMDPConfiguration(page)
    row = make_dialog_row([EMS_STATUS_ERROR])

    assert po.wait_for_ems_group_status(row, EMS_STATUS_VALIDATED, 120) == EMS_STATUS_ERROR
    page.wait_for_timeout.assert_not_called()


def test_wait_returns_the_last_status_after_exhausting_its_budget():
    page = MagicMock()
    po = PageObjectBMDPConfiguration(page)
    row = make_dialog_row([""])

    assert po.wait_for_ems_group_status(row, EMS_STATUS_REGISTERED, 10, interval=5) == ""


# --- the dialog flow ------------------------------------------------------------------------


class StrictModeViolation(Exception):
    """What Playwright raises when a locator used for an action resolves to >1 element."""


class FakeLocator:
    """One locator over FakePage's modelled DOM, STRICT the way Playwright is.

    Strictness is the whole point of this harness, not a detail. This ticket is about
    selectors that quietly match the wrong NUMBER of elements — `.p-button-label` matches
    2, `aria-label='Register'` matches 2, and the live run died on a row lookup that
    matched 2. A harness where `.first` is inert and a 2-match locator clicks happily
    cannot fail on any of that, so every selector guard in the source would be free to
    regress with the suite still green. So here:

      * `.first` genuinely narrows (and is remembered, per-locator);
      * `is_visible()` / `click()` / `set_input_files()` raise StrictModeViolation on a
        multi-match that was not narrowed — Playwright is strict for ALL of these;
      * a zero-match action raises, rather than quietly doing nothing.

    Not `tests/stub_page.py`: that stub models visibility RULES rather than the
    match-count arithmetic these selectors turn on, its `click()` is not strict, and its
    `filter()` is a documented no-op. It also has no `is_enabled()`, `set_input_files()`
    or role-based lookup, all of which this flow needs. Making its `click()` strict would
    change semantics under four existing suites; keeping the count-based model here is
    the smaller blast radius.
    """

    def __init__(self, page, selector, narrowed=False):
        self.page = page
        self.selector = selector
        self.narrowed = narrowed

    @property
    def first(self):
        return FakeLocator(self.page, self.selector, narrowed=True)

    def or_(self, other):
        return OrLocator(self.page, self, other)

    def count(self):
        return sum(self.page.counts.get(part, 0) for part in self.selector.split(" OR "))

    def _resolve(self, action):
        matches = self.count()
        if matches > 1 and not self.narrowed:
            raise StrictModeViolation(
                f"strict mode violation: {self.selector!r} resolved to {matches} elements ({action})")
        return matches

    def is_visible(self):
        matches = self._resolve("is_visible")
        # count() and visibility are DIFFERENT questions - conflating them is what made
        # the presence-vs-visibility bug invisible to this suite in the first place.
        return matches > 0 and self.selector not in self.page.hidden

    def is_enabled(self):
        self._resolve("is_enabled")
        return self.page.enabled.get(self.selector, True)

    def click(self, **_kwargs):
        if self._resolve("click") == 0:
            raise AssertionError(f"click on a locator that matches nothing: {self.selector}")
        self.page.clicks.append(self.selector)

    def set_input_files(self, path):
        if self._resolve("set_input_files") == 0:
            raise AssertionError(f"set_input_files on a locator that matches nothing: {self.selector}")
        with open(path, encoding="utf-8") as handle:
            self.page.uploaded = handle.read()

    def get_by_role(self, role, name=None):
        suffix = f"role={role}[{name}]" if name is not None else f"role={role}"
        return FakeLocator(self.page, f"{self.selector} {suffix}")

    def filter(self, has=None, has_text=None):
        token = has.selector if has is not None else has_text
        return FakeLocator(self.page, f"{self.selector} FILTER[{token}]")

    def locator(self, selector, **_kwargs):
        return FakeLocator(self.page, f"{self.selector} {selector}")

    def inner_text(self):
        self._resolve("inner_text")
        return self.page.texts.get(self.selector, "")

    def wait_for(self, **kwargs):
        state = kwargs.get("state", "visible")
        self.page.waits.append((self.selector, state))
        if (self.selector, state) in self.page.wait_for_raises:
            raise AssertionError(f"wait_for({state}) timed out on {self.selector}")


class OrLocator(FakeLocator):
    """Playwright's `a.or_(b)` - and, crucially, what `.first` does to it.

    `.first` narrows the UNION to the DOM-FIRST matching element and then reports THAT
    element's state. It does NOT mean "either side is visible". Modelling it as the
    latter is what let a hidden-first/visible-second regression slip past this suite in
    review round 1: the mutant that reverted the gate to `a.or_(b).first` stayed green.

    APPROXIMATION, stated plainly: this harness has no DOM order, so argument order
    stands in for it - the first side with any match is treated as the DOM-first one.
    That is faithful for the call sites here and is what makes the failure reproducible;
    it is not a general DOM-order model.
    """

    def __init__(self, page, left, right):
        super().__init__(page, f"{left.selector} OR {right.selector}")
        self.left, self.right = left, right

    @property
    def first(self):
        winner = self.left if self.left.count() > 0 else self.right
        return FakeLocator(self.page, winner.selector, narrowed=True)

    def count(self):
        return self.left.count() + self.right.count()

    def is_visible(self):
        self._resolve("is_visible")
        return self.left.is_visible() or self.right.is_visible()


class FakePage:
    """A page whose DOM is a {selector: count} map, plus a click log."""

    url = "https://stub/"

    def __init__(self, counts, enabled=None, texts=None, hidden=()):
        self.counts = counts
        self.enabled = enabled or {}
        self.texts = texts or {}
        self.hidden = set(hidden)
        self.clicks = []
        self.waits = []
        self.wait_for_raises = set()
        self.uploaded = None
        self.fills = {}

    def locator(self, selector, **kwargs):
        has_text = kwargs.get("has_text")
        return FakeLocator(self, f"{selector}|{has_text}" if has_text else selector)

    def get_by_role(self, role, name=None):
        suffix = f"role={role}[{name}]" if name is not None else f"role={role}"
        return FakeLocator(self, suffix)

    def get_by_text(self, text, exact=False):
        return FakeLocator(self, f"text={text}{'!' if exact else ''}")

    def fill(self, selector, value, **_kwargs):
        self.fills[selector] = value

    def wait_for_timeout(self, _ms):
        pass

    def reload(self):
        pass

    def wait_for_load_state(self, *_a, **_k):
        pass


DIALOG_ROW = f"section.gemsModalDialog role=row FILTER[text={GROUP}!]"
BY_NAME = f"role=button[{EMS_REGISTER_BUTTON_NAME}]"
ROW_REGISTER_BUTTON = "section.gemsModalDialog button[aria-label='Register']"

CP121_DOM = {
    EMS_YAML_EDITOR: 1,
    EMS_YAML_FILE_INPUT: 1,
    EMS_VALIDATE_ALL: 1,
    EMS_REGISTER_GROUPS: 1,
    EMS_DONE: 1,
    "section.gemsModalDialog": 1,
    DIALOG_ROW: 1,
    # Break 1, modelled exactly: the class the old code clicked matches NOTHING on 1.21.
    EMS_REGISTER_BUTTON_LEGACY: 0,
    f"role=button[{EMS_REGISTER_BUTTON_NAME}]": 1,
    # Break 2: no step of the old wizard is rendered.
    f"[class*='_modalBody'] span|Enterprise Message Service": 0,
}


@pytest.fixture
def no_side_effects(monkeypatch):
    """Let exit_error still raise SystemExit, without touching disk or a real browser."""
    monkeypatch.setattr(po_bmdp_config.Util, "screenshot_page", lambda *_a, **_k: None)
    monkeypatch.setattr(po_bmdp_config.Util, "stop_tracing", lambda *_a, **_k: None)
    monkeypatch.setattr(po_bmdp_config.Util, "click_button_until_enabled",
                        lambda _page, locator: locator.click())
    # check_dom_visibility/check_dom_enabled sleep 5s before their first poll; the DOM here
    # is static, so read it directly and keep the suite fast.
    monkeypatch.setattr(po_bmdp_config.Util, "check_dom_visibility",
                        lambda _page, locator, *_a, **_k: locator.is_visible())
    monkeypatch.setattr(po_bmdp_config.Util, "check_dom_enabled",
                        lambda _page, locator, *_a, **_k: locator.is_enabled())


def test_cp121_dom_takes_the_yaml_branch(no_side_effects):
    po = PageObjectBMDPConfiguration(FakePage(CP121_DOM))

    assert po.is_yaml_registration_dialog() is True


def test_legacy_dom_takes_the_wizard_branch(no_side_effects):
    legacy = {
        EMS_YAML_EDITOR: 0,
        "[class*='_modalBody'] span|Enterprise Message Service": 1,
    }

    po = PageObjectBMDPConfiguration(FakePage(legacy))

    assert po.is_yaml_registration_dialog() is False


def test_a_dialog_that_is_neither_fails_loudly(no_side_effects):
    """Better a screenshot naming both possibilities than a bare 30s Playwright timeout."""
    po = PageObjectBMDPConfiguration(FakePage({
        EMS_YAML_EDITOR: 0,
        "[class*='_modalBody'] span|Enterprise Message Service": 0,
    }))

    with pytest.raises(SystemExit):
        po.is_yaml_registration_dialog()


def test_open_button_is_clicked_even_though_the_legacy_class_is_gone(no_side_effects):
    """Break 1's regression test: on this DOM the old code clicked nothing for 30s."""
    page = FakePage(CP121_DOM)

    PageObjectBMDPConfiguration(page).click_register_new_instances()

    assert page.clicks == [f"role=button[{EMS_REGISTER_BUTTON_NAME}]"]


def test_open_button_falls_back_to_the_legacy_class_when_the_name_is_absent(no_side_effects):
    page = FakePage({
        f"role=button[{EMS_REGISTER_BUTTON_NAME}]": 0,
        EMS_REGISTER_BUTTON_LEGACY: 1,
    })

    PageObjectBMDPConfiguration(page).click_register_new_instances()

    assert page.clicks == [EMS_REGISTER_BUTTON_LEGACY]


def test_open_button_that_never_appears_fails_loudly(no_side_effects):
    page = FakePage({f"role=button[{EMS_REGISTER_BUTTON_NAME}]": 0, EMS_REGISTER_BUTTON_LEGACY: 0})

    with pytest.raises(SystemExit):
        PageObjectBMDPConfiguration(page).click_register_new_instances()

    assert page.clicks == []


def register_page(**overrides):
    counts = dict(CP121_DOM)
    counts.update(overrides.pop("counts", {}))
    return FakePage(counts, enabled=overrides.pop("enabled", None))


def drive_registration(page, monkeypatch, statuses):
    """Run ems_register_by_yaml with the dialog row reporting `statuses` in order."""
    po = PageObjectBMDPConfiguration(page)
    remaining = list(statuses)
    monkeypatch.setattr(
        PageObjectBMDPConfiguration, "ems_group_status",
        staticmethod(lambda _row: remaining.pop(0) if len(remaining) > 1 else remaining[0]),
    )
    # ENV is a FROZEN dataclass, so its fields cannot be set - swap the module reference.
    monkeypatch.setattr(po_bmdp_config, "ENV", SimpleNamespace(
        TP_AUTO_K8S_BMDP_BW5_EMS_SERVER_URL=CLIENT_URL,
        TP_AUTO_K8S_BMDP_BW5_EMS_MONITOR_URL=MONITOR_URL,
        TP_AUTO_K8S_BMDP_BW5_EMS_USERNAME="admin",
        TP_AUTO_K8S_BMDP_BW5_EMS_PASSWORD="",
    ))
    return po.ems_register_by_yaml(GROUP)


def test_happy_path_uploads_validates_registers_then_done(no_side_effects, monkeypatch):
    page = register_page()

    drive_registration(page, monkeypatch, [EMS_STATUS_VALIDATED, EMS_STATUS_REGISTERED])

    # Order matters: Register only enables once something has validated, and Done only
    # once something has registered.
    assert page.clicks == [EMS_VALIDATE_ALL, EMS_REGISTER_GROUPS, EMS_DONE]
    assert yaml_lib.safe_load(page.uploaded)["server_groups"][0]["groupName"] == GROUP


def test_the_uploaded_payload_is_what_reaches_the_file_input(no_side_effects, monkeypatch):
    """The upload is the whole point of the 1.21 path - assert the bytes, not the call."""
    page = register_page()

    drive_registration(page, monkeypatch, [EMS_STATUS_VALIDATED, EMS_STATUS_REGISTERED])

    group = yaml_lib.safe_load(page.uploaded)["server_groups"][0]
    assert group == {
        "groupName": GROUP,
        "clientUrl": CLIENT_URL,
        "monitorUrl": MONITOR_URL,
        "registrationUser": "admin",
    }


def test_validation_error_aborts_without_registering(no_side_effects, monkeypatch):
    """No silent success. dp_config_ems writes ReportYaml 'Added' unconditionally after
    this call returns, so returning quietly here would record an EMS server group that
    was never registered as Added."""
    page = register_page()

    with pytest.raises(SystemExit):
        drive_registration(page, monkeypatch, [EMS_STATUS_ERROR])

    assert page.clicks == [EMS_VALIDATE_ALL]


def test_register_button_stuck_disabled_aborts_without_clicking(no_side_effects, monkeypatch):
    """'Register 0 Server Groups' stays disabled when nothing staged.

    Clicking it anyway spends Playwright's 30s auto-wait and then reports a bare click
    timeout that says nothing about the real problem.
    """
    page = register_page(enabled={EMS_REGISTER_GROUPS: False})

    with pytest.raises(SystemExit):
        drive_registration(page, monkeypatch, [EMS_STATUS_VALIDATED])

    assert page.clicks == [EMS_VALIDATE_ALL]


def test_a_register_that_never_reaches_registered_aborts_before_done(no_side_effects, monkeypatch):
    page = register_page()

    with pytest.raises(SystemExit):
        drive_registration(page, monkeypatch, [EMS_STATUS_VALIDATED, EMS_STATUS_VALIDATED])

    assert page.clicks == [EMS_VALIDATE_ALL, EMS_REGISTER_GROUPS]
    assert EMS_DONE not in page.clicks


def test_success_does_not_depend_on_a_toast(no_side_effects, monkeypatch):
    """CP 1.21 raises NO success notification for this flow.

    div[role='alert'][aria-label='success'], .pl-notification__message and the selectors
    behind Util.wait_for_success_message() all stayed empty for 24s after a registration
    that demonstrably succeeded. A flow that waits for one can never pass on 1.21, so this
    DOM deliberately contains no notification element at all.
    """
    page = register_page()
    assert not any("notification" in selector or "alert" in selector for selector in page.counts)

    drive_registration(page, monkeypatch, [EMS_STATUS_VALIDATED, EMS_STATUS_REGISTERED])

    assert page.clicks == [EMS_VALIDATE_ALL, EMS_REGISTER_GROUPS, EMS_DONE]


def test_done_waits_for_the_modal_to_close_before_the_list_is_read(no_side_effects, monkeypatch):
    """Caught on the LIVE 1.21 run, not by any of the tests above it.

    The registration had fully succeeded - Validated, Registering..., Registered, Done -
    and the very next line died:

        strict mode violation: get_by_role("row", name="ems-latest") resolved to 2 elements
          1) <tr> aka "ems-latest tcp://ems.bw5dm."          <- the Messaging list
          2) <tr> aka "Expand ems-latest ems-latest"          <- the dialog, still mounted

    The dialog's own result table names its rows after the server group too, so reading
    the list while the modal is unmounting matches both. A DOM-level unit test cannot see
    this: it only appears when two tables are mounted at once.
    """
    page = register_page()

    drive_registration(page, monkeypatch, [EMS_STATUS_VALIDATED, EMS_STATUS_REGISTERED])

    assert ("section.gemsModalDialog", "hidden") in page.waits, \
        "the list must not be read until the modal is gone"


def test_a_modal_that_never_closes_fails_loudly(no_side_effects, monkeypatch):
    """Better than letting the caller hit an unexplained strict-mode violation."""
    page = register_page()
    page.wait_for_raises.add(("section.gemsModalDialog", "hidden"))

    with pytest.raises(SystemExit):
        drive_registration(page, monkeypatch, [EMS_STATUS_VALIDATED, EMS_STATUS_REGISTERED])


def test_transient_registering_status_is_polled_through_not_treated_as_failure():
    """'Registering...' is a real 1.21 status, seen live between Register and Registered.

    It is neither the target nor Error, so it must keep polling - a stricter reading that
    only tolerated '' would abort on a registration that was working.
    """
    page = MagicMock()
    po = PageObjectBMDPConfiguration(page)
    row = make_dialog_row(["Registering...", EMS_STATUS_REGISTERED])

    assert po.wait_for_ems_group_status(row, EMS_STATUS_REGISTERED, 120) == EMS_STATUS_REGISTERED


def test_the_generated_payload_file_does_not_outlive_the_upload(no_side_effects, monkeypatch):
    """It carries registrationPass; it must not linger on disk or in a report artifact."""
    seen = {}
    original = FakeLocator.set_input_files

    def capture(self, path):
        seen["path"] = path
        return original(self, path)

    monkeypatch.setattr(FakeLocator, "set_input_files", capture)
    page = register_page()

    drive_registration(page, monkeypatch, [EMS_STATUS_VALIDATED, EMS_STATUS_REGISTERED])

    assert not os.path.exists(seen["path"])


# --- strict-mode: the defect class this whole ticket is about ------------------------------
#
# Added after a 3-model cross-review pointed out that the first version of this harness had
# an inert `.first` and a click() that never raised on a multi-match - i.e. on a ticket whose
# selectors are chosen SPECIFICALLY to avoid matching 2 elements, nothing here could have
# failed if they started to. The live run had already proved the point the hard way: it died
# on a row lookup that resolved to 2 rows while every unit test stayed green.


def test_the_harness_itself_is_strict():
    """Control case. If this passes trivially, every test below it is worthless.

    Same reasoning as PCP-24309's control case: a harness asserted to be strict has to be
    shown to be strict, or a later refactor can quietly make it permissive again and take
    the whole multi-match section down with it.
    """
    page = FakePage({"#two": 2})

    with pytest.raises(StrictModeViolation):
        page.locator("#two").click()
    with pytest.raises(StrictModeViolation):
        page.locator("#two").is_visible()
    # ...and .first is the escape hatch, exactly as in Playwright.
    page.locator("#two").first.click()
    assert page.clicks == ["#two"]


def test_open_button_survives_a_page_where_the_name_matches_twice(no_side_effects):
    """`.first` on the open button is load-bearing, not decoration.

    A Messaging page that renders the button twice (or a stale copy during a re-render)
    would otherwise throw a strict-mode violation instead of clicking.
    """
    page = FakePage({BY_NAME: 2, EMS_REGISTER_BUTTON_LEGACY: 0})

    PageObjectBMDPConfiguration(page).click_register_new_instances()

    assert page.clicks == [BY_NAME]


def test_legacy_open_button_is_narrowed_too(no_side_effects):
    """The legacy click had no `.first` before review; a 2-match legacy page threw."""
    page = FakePage({BY_NAME: 0, EMS_REGISTER_BUTTON_LEGACY: 2})

    PageObjectBMDPConfiguration(page).click_register_new_instances()

    assert page.clicks == [EMS_REGISTER_BUTTON_LEGACY]


def test_open_button_is_chosen_by_visibility_not_mere_presence(no_side_effects):
    """count() counts HIDDEN nodes; is_visible() does not.

    A shell holding a hidden 'Register New Instances' node while the visible control is
    the legacy one would, under a count()-based decision, send the click at the hidden
    node and then burn Playwright's actionability auto-wait on it.
    """
    page = FakePage({BY_NAME: 0, EMS_REGISTER_BUTTON_LEGACY: 1})

    PageObjectBMDPConfiguration(page).click_register_new_instances()

    assert page.clicks == [EMS_REGISTER_BUTTON_LEGACY]


def attribute_selector_matches(selector, attribute, values):
    """Which of `values` a CSS attribute selector would match. Mirrors the CSS rules for
    the two forms these constants use: [attr='v'] (exact) and [attr*='v'] (substring).

    Deliberately NOT routed through FakePage: its DOM is a {selector-string: count} map,
    so it cannot represent "two DIFFERENT selectors matching overlapping elements" - the
    exact property at stake here. A test that pretended otherwise would pass even after
    the selector was changed back to the broken form, which is worse than no test.
    """
    exact = re.search(re.escape(attribute) + r"='([^']*)'\]", selector)
    substring = re.search(re.escape(attribute) + r"\*='([^']*)'\]", selector)
    if substring:
        return [v for v in values if substring.group(1) in v]
    if exact:
        return [v for v in values if v == exact.group(1)]
    raise AssertionError(f"no {attribute} clause in {selector!r}")


# The accessible names the 1.21 dialog really holds once a row has validated, read off the
# live CP: the per-row action button, and the bulk button carrying the validated count.
POST_VALIDATION_BUTTON_LABELS = ["Register", "Upload YAML", "Validate All", "Register 1 Server Group", "Done"]


def test_bulk_register_selector_matches_exactly_one_live_button():
    """The behavioural half of the selector-shape test above, against the REAL labels.

    'Register' matches the row button AND 'Register 1 Server Group' would too under a
    substring match - two elements, strict-mode violation. The shipped selector must
    pick out exactly the bulk button.
    """
    matched = attribute_selector_matches(EMS_REGISTER_GROUPS, "aria-label", POST_VALIDATION_BUTTON_LABELS)

    assert matched == ["Register 1 Server Group"]


def test_the_naive_register_selector_really_would_match_two():
    """Control: proves the test above is not vacuously true.

    If a substring match on 'Register' did NOT collide, the shipped selector's whole
    justification - and the comment at the constant - would be wrong.
    """
    naive = "button[aria-label*='Register']"

    assert len(attribute_selector_matches(naive, "aria-label", POST_VALIDATION_BUTTON_LABELS)) == 2


def test_bulk_register_selector_tracks_the_plural_form_too():
    """The label is 'Register 0 Server Groups' before anything validates - the count and
    the plural both move, which is why this cannot be an exact match."""
    matched = attribute_selector_matches(
        EMS_REGISTER_GROUPS, "aria-label", ["Register", "Register 0 Server Groups"])

    assert matched == ["Register 0 Server Groups"]


# --- dp_config_ems: the report must not outrun the registration ----------------------------


@pytest.fixture
def captured_report(monkeypatch):
    """Capture ReportYaml writes so 'was it recorded as Added?' is directly assertable."""
    written = []
    monkeypatch.setattr(po_bmdp_config.ReportYaml, "get_capability_info", lambda *_a: None)
    monkeypatch.setattr(po_bmdp_config.ReportYaml, "set_capability", lambda *_a: None)
    monkeypatch.setattr(po_bmdp_config.ReportYaml, "set_capability_info",
                        lambda _dp, _cap, name, state: written.append((name, state)))
    return written


def drive_dp_config_ems(page, monkeypatch, wizard_result):
    """dp_config_ems() with the row absent, forced down the legacy wizard branch."""
    po = PageObjectBMDPConfiguration(page)
    checked = []
    monkeypatch.setattr(PageObjectBMDPConfiguration, "ems_server_row",
                        lambda _self, _n: FakeLocator(page, "absent-row"))
    monkeypatch.setattr(PageObjectBMDPConfiguration, "goto_dataplane_config_sub_menu", lambda *_a, **_k: None)
    monkeypatch.setattr(PageObjectBMDPConfiguration, "click_register_new_instances", lambda _self: None)
    monkeypatch.setattr(PageObjectBMDPConfiguration, "is_yaml_registration_dialog", lambda _self: False)
    monkeypatch.setattr(PageObjectBMDPConfiguration, "ems_register_by_wizard",
                        lambda _self, _n: wizard_result)
    monkeypatch.setattr(PageObjectBMDPConfiguration, "check_ems_server_status",
                        lambda _self, n: checked.append(n))
    po.dp_config_ems(GROUP)
    return checked


def test_legacy_registration_failure_is_not_recorded_as_added(no_side_effects, captured_report, monkeypatch):
    """The pre-existing lie this review surfaced.

    ems_register_by_wizard() warns and RETURNS on a failed validation, and dp_config_ems
    used to write "Added" regardless. Worse, "Added" short-circuits the check at the top
    of dp_config_ems, so the wrong answer is sticky: every later run skips the flow and
    the server group is never actually registered.
    """
    checked = drive_dp_config_ems(FakePage({"absent-row": 0}), monkeypatch, wizard_result=False)

    assert captured_report == [], "a failed legacy registration must not be recorded as Added"
    assert checked == [], "and must not go on to report a health status either"


def test_legacy_registration_success_is_recorded_as_added(no_side_effects, captured_report, monkeypatch):
    """The other half - the return-value change must not break the working path."""
    checked = drive_dp_config_ems(FakePage({"absent-row": 0}), monkeypatch, wizard_result=True)

    assert captured_report == [(GROUP, "Added")]
    assert checked == [GROUP]


# --- secret hygiene -------------------------------------------------------------------------


def ems_env(password):
    return SimpleNamespace(
        TP_BMDP_IMAGE_TAG_EMS=GROUP,
        TP_AUTO_K8S_BMDP_BW5_EMS_SERVER_URL=CLIENT_URL,
        TP_AUTO_K8S_BMDP_BW5_EMS_MONITOR_URL=MONITOR_URL,
        TP_AUTO_K8S_BMDP_BW5_EMS_USERNAME="admin",
        TP_AUTO_K8S_BMDP_BW5_EMS_PASSWORD=password,
    )


def test_payload_is_deleted_even_when_the_upload_raises(no_side_effects, monkeypatch):
    """The `finally` branch - the one that actually matters for the secret.

    A failed upload is precisely when a credential-bearing temp file would be forgotten.
    """
    seen = {}

    def exploding_upload(self, path):
        seen["path"] = path
        raise RuntimeError("upload blew up")

    monkeypatch.setattr(FakeLocator, "set_input_files", exploding_upload)
    monkeypatch.setattr(po_bmdp_config, "ENV", ems_env("s3cret"))
    po = PageObjectBMDPConfiguration(register_page())

    with pytest.raises(RuntimeError):
        po.upload_ems_registration_yaml(GROUP)

    assert not os.path.exists(seen["path"])


def test_the_password_is_never_printed(no_side_effects, monkeypatch, capsys):
    """The legacy wizard printed it in clear text (`Filled EMS Password: <pw>`).

    That line is still on the legacy path, which is kept verbatim; the 1.21 path must not
    reintroduce it - the payload is uploaded, never logged.
    """
    password = "sup3rs3cret-pw"
    monkeypatch.setattr(po_bmdp_config, "ENV", ems_env(password))
    page = register_page()

    PageObjectBMDPConfiguration(page).upload_ems_registration_yaml(GROUP)

    out = capsys.readouterr()
    assert password not in out.out
    assert password not in out.err
    # ...but it DID reach the browser, which is why the operator is warned the report
    # artefacts will contain it.
    assert password in page.uploaded


def test_done_that_never_enables_fails_with_a_screenshot(no_side_effects, monkeypatch):
    """Before review this was the one exit with no artefact - a bare Playwright timeout."""
    page = register_page(enabled={EMS_DONE: False})

    with pytest.raises(SystemExit):
        drive_registration(page, monkeypatch, [EMS_STATUS_VALIDATED, EMS_STATUS_REGISTERED])

    assert EMS_DONE not in page.clicks


def test_open_button_ignores_a_present_but_hidden_named_button(no_side_effects):
    """The presence-vs-visibility fix, with a DOM that can actually tell them apart.

    count() counts hidden nodes. A shell that keeps a hidden 'Register New Instances'
    node while the visible control is the legacy one would, under the count()-based
    decision this replaced, click the hidden node and then spend Playwright's whole
    actionability auto-wait on an element that can never be clicked.
    """
    page = FakePage({BY_NAME: 1, EMS_REGISTER_BUTTON_LEGACY: 1}, hidden={BY_NAME})

    PageObjectBMDPConfiguration(page).click_register_new_instances()

    assert page.clicks == [EMS_REGISTER_BUTTON_LEGACY]


SUCCESS_ALERT = "div[role='alert'][aria-label='success']"
# The pre-1.21 wizard's own DOM, as its (unchanged) selectors ask for it.
LEGACY_WIZARD_DOM = {
    "[class*='_modalBody'] span|Enterprise Message Service": 1,
    "[class*='_modalBody'] span|Register a Server": 1,
    "button.pl-button.pl-button--secondary.gemsButton|Validate Server": 1,
    "button.pl-button.pl-button--primary.gemsButton|Register Server": 1,
    "button.pl-button.pl-button--primary.gemsButton|Done": 1,
}


def legacy_wizard_page(success_alerts):
    counts = dict(LEGACY_WIZARD_DOM)
    counts[SUCCESS_ALERT] = success_alerts
    return FakePage(counts)


def drive_legacy_wizard(page, monkeypatch):
    monkeypatch.setattr(po_bmdp_config, "ENV", ems_env(""))
    monkeypatch.setattr(po_bmdp_config.Util, "check_dom_visibility",
                        lambda _p, locator, *_a, **_k: locator.is_visible())
    monkeypatch.setattr(po_bmdp_config.Util, "click_button_until_enabled",
                        lambda _p, locator: locator.click())
    return PageObjectBMDPConfiguration(page).ems_register_by_wizard(GROUP)


def test_legacy_wizard_reports_failure_when_validation_never_succeeds(no_side_effects, monkeypatch):
    """Drives the REAL ems_register_by_wizard, not a stub of it.

    The sibling test asserts dp_config_ems honours a False; this one asserts the wizard
    actually RETURNS False when the CP never shows the success notification. Without it,
    the wizard could return True unconditionally and the report would go back to lying
    while every other test stayed green.
    """
    page = legacy_wizard_page(success_alerts=0)

    assert drive_legacy_wizard(page, monkeypatch) is False
    # ...and it never got as far as clicking Register Server.
    assert not any("Register Server" in click for click in page.clicks)


def test_legacy_wizard_reports_success_only_after_confirmation(no_side_effects, monkeypatch):
    """The working legacy path must still return True - the return value is the ONLY
    thing this change touched on that path, so a regression here is a real one."""
    page = legacy_wizard_page(success_alerts=1)

    assert drive_legacy_wizard(page, monkeypatch) is True
    assert any("Register Server" in click for click in page.clicks)


def test_legacy_wizard_still_fills_every_field_it_always_did(no_side_effects, monkeypatch):
    """Guards the 'kept verbatim' claim: the browser interactions must be untouched."""
    page = legacy_wizard_page(success_alerts=1)

    drive_legacy_wizard(page, monkeypatch)

    assert set(page.fills) == {
        "input[name='groupName']", "input[name='clientUrl']", "input[name='monitorUrl']",
        "input[name='registrationUser']", "input[name='registrationPass']",
    }


# --- the union-visibility gate (from PR-review round 1) -------------------------------------


def test_a_hidden_first_match_does_not_mask_a_visible_second(no_side_effects):
    """`a.or_(b).first` narrows the UNION to the DOM-first match, then reports THAT
    element's visibility - so a hidden earlier match hides a visible later one and the
    gate fails on a page that is perfectly actionable. Exactly the failure mode this
    change exists to remove, so it must not be reintroduced by the gate itself.
    """
    page = FakePage({BY_NAME: 1, EMS_REGISTER_BUTTON_LEGACY: 1}, hidden={BY_NAME})

    PageObjectBMDPConfiguration(page).click_register_new_instances()

    assert page.clicks == [EMS_REGISTER_BUTTON_LEGACY]


def test_gate_is_true_when_only_the_second_variant_is_visible(no_side_effects):
    po = PageObjectBMDPConfiguration(FakePage({"#a": 1, "#b": 1}, hidden={"#a"}))

    assert po.wait_for_either_visible(
        po.page.locator("#a"), po.page.locator("#b"), 1, 3) is True


def test_gate_is_true_when_only_the_first_variant_is_visible(no_side_effects):
    po = PageObjectBMDPConfiguration(FakePage({"#a": 1, "#b": 1}, hidden={"#b"}))

    assert po.wait_for_either_visible(
        po.page.locator("#a"), po.page.locator("#b"), 1, 3) is True


def test_gate_is_false_only_when_neither_is_visible(no_side_effects):
    po = PageObjectBMDPConfiguration(FakePage({"#a": 1, "#b": 1}, hidden={"#a", "#b"}))

    assert po.wait_for_either_visible(
        po.page.locator("#a"), po.page.locator("#b"), 1, 3) is False


def test_gate_survives_either_side_matching_twice(no_side_effects):
    """Each side keeps its own `.first`, so a multi-match cannot raise strict mode."""
    po = PageObjectBMDPConfiguration(FakePage({"#a": 2, "#b": 2}))

    assert po.wait_for_either_visible(
        po.page.locator("#a"), po.page.locator("#b"), 1, 3) is True


def test_branch_detection_ignores_a_present_but_hidden_editor(no_side_effects):
    """A 1.21 editor node that exists but is not shown must NOT win the branch over a
    visible legacy wizard."""
    page = FakePage(
        {EMS_YAML_EDITOR: 1, "[class*='_modalBody'] span|Enterprise Message Service": 1},
        hidden={EMS_YAML_EDITOR},
    )

    assert PageObjectBMDPConfiguration(page).is_yaml_registration_dialog() is False


def test_legacy_wizard_no_longer_prints_the_password(no_side_effects, monkeypatch, capsys):
    """The legacy path kept every browser interaction, but not the clear-text log line:
    it went straight into the pipeline log and any support bundle built from it."""
    page = legacy_wizard_page(success_alerts=1)
    monkeypatch.setattr(po_bmdp_config, "ENV", ems_env("legacy-cleartext-pw"))
    monkeypatch.setattr(po_bmdp_config.Util, "check_dom_visibility",
                        lambda _p, locator, *_a, **_k: locator.is_visible())
    monkeypatch.setattr(po_bmdp_config.Util, "click_button_until_enabled",
                        lambda _p, locator: locator.click())

    PageObjectBMDPConfiguration(page).ems_register_by_wizard(GROUP)

    out = capsys.readouterr().out
    assert "legacy-cleartext-pw" not in out
    # ...but it still reaches the form, so the wizard itself is unchanged.
    assert page.fills["input[name='registrationPass']"] == "legacy-cleartext-pw"


def test_the_harness_reproduces_the_or_first_trap():
    """Control for the OrLocator model. If `.or_().first` looks fine here, the three
    mutants that revert the gate to it would stay green and this section is worthless.
    """
    page = FakePage({"#hidden-first": 1, "#visible-second": 1}, hidden={"#hidden-first"})
    union = page.locator("#hidden-first").or_(page.locator("#visible-second"))

    # `.first` picks the DOM-first match and reports ITS visibility - so it says False...
    assert union.first.is_visible() is False
    # ...even though one of the two really is visible.
    assert page.locator("#visible-second").is_visible() is True


def test_branch_detection_narrows_the_editor_before_reading_it(no_side_effects):
    """`editor.first.is_visible()`: a Messaging shell that renders two #yaml-editor nodes
    (a stale one mid-swap) would otherwise throw strict mode instead of branching."""
    page = FakePage({EMS_YAML_EDITOR: 2,
                     "[class*='_modalBody'] span|Enterprise Message Service": 0})

    assert PageObjectBMDPConfiguration(page).is_yaml_registration_dialog() is True


# --- row lookup: the sibling-group collision (from PR review) --------------------------------
#
# Raised by four independent reviewers before it was fixed. `get_by_role("row", name=X)`
# matches the accessible name by SUBSTRING, and a row's accessible name is its WHOLE text,
# so a second group whose name merely contains the first makes both rows match - and
# is_visible() then throws a strict-mode violation. Same defect class this PR removes,
# relocated from the dialog to the list.

# Two rows as CP 1.21 really renders them: (accessible name, [cell texts]).
TWO_GROUP_LIST = [
    ("ems-latest tcp://ems.bw5dm.svc.cluster.local:7222", ["ems-latest", "tcp://ems.bw5dm.svc.cluster.local:7222"]),
    ("ems-latest-2 tcp://ems2.bw5dm.svc.cluster.local:7223", ["ems-latest-2", "tcp://ems2.bw5dm.svc.cluster.local:7223"]),
]


def rows_matched_by_accessible_name(rows, group):
    """Playwright's `get_by_role("row", name=group)` - case-insensitive SUBSTRING."""
    return [name for name, _cells in rows if group.lower() in name.lower()]


def rows_matched_by_exact_name_cell(rows, group):
    """The shipped form: a row containing a descendant whose text is EXACTLY the group."""
    return [name for name, cells in rows if any(cell == group for cell in cells)]


def test_the_old_row_lookup_really_would_have_matched_two():
    """Control. If the substring form did not collide, the fix below would be pointless."""
    assert len(rows_matched_by_accessible_name(TWO_GROUP_LIST, "ems-latest")) == 2


def test_exact_name_cell_anchoring_picks_exactly_one_row():
    matched = rows_matched_by_exact_name_cell(TWO_GROUP_LIST, "ems-latest")

    assert matched == ["ems-latest tcp://ems.bw5dm.svc.cluster.local:7222"]


def test_exact_name_cell_anchoring_still_finds_the_longer_sibling():
    """...and does not over-correct: the longer name must still be findable on its own."""
    matched = rows_matched_by_exact_name_cell(TWO_GROUP_LIST, "ems-latest-2")

    assert matched == ["ems-latest-2 tcp://ems2.bw5dm.svc.cluster.local:7223"]


def test_exact_row_name_would_match_nothing_at_all():
    """Why `exact=True` on the ROW name was rejected, recorded so it is not "fixed" back.

    A row's accessible name is its whole text, so an exact match on the group name alone
    matches zero rows - it would silently turn every lookup into "not registered".
    """
    assert [n for n, _c in TWO_GROUP_LIST if n == "ems-latest"] == []


def test_health_icon_selector_matches_both_table_generations():
    """Behavioural replacement for the old string-shape assertion.

    Legacy wraps the icon in td[class*='_healthCell'], 1.21 in div[class*='_healthContainer_'];
    the shipped prefix has to hit both, and pinning either full class name breaks the other.
    """
    prefix = re.search(r"\[class\*='([^']*)'\]", EMS_HEALTH_ICON).group(1)

    assert prefix in "_healthCell", "must match the legacy Plexus wrapper"
    assert prefix in "_healthContainer_10zmy_1", "must match the CP 1.21 wrapper"
