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
# Regression net for the CP 1.21 Fresco Register-Data-Plane wizard (PCP-24237).
#
# WHAT WENT WRONG. CP 1.21 rebuilt both register wizards on the Fresco/PrimeNG shell.
# The Pulse step nav '.pl-secondarynav a.is-active' the flows walked is not rendered at
# all any more, so k8s_create_dataplane timed out on its very first step wait and every
# GUI-path (TP_AUTO_USE_CLI=false) deploy failed at create-dp -> deploy-subscription ->
# run.sh -> the whole pipeline, 1h40m in. Nobody noticed because every routine deploy
# runs use_cli=true, which registers the data plane through the tibcop CLI and never
# touches this code.
#
# EVERY CASE HERE IS ABOUT ONE THEME: this flow must never report success without having
# registered. The defect shipped twice over precisely because two different failures both
# looked like success, and the first cut of the FIX reintroduced the same shape a third
# time (a bare `return` on a failed wizard walk, which `case/k8s_create_dp.py` turns into
# exit 0 because it does not check anything afterwards). So:
#   * the wizard is chosen by which one RENDERS - a legacy Control Plane still walks the
#     legacy path (bootstrap/CLAUDE.md principle 6)
#   * the step walk is driven by the rail's own labels and terminates when the rail goes
#   * EVERY failure inside the walk EXITS; there is no quiet return
#   * every filler the caller supplied must actually have FIRED - a step whose label drifts
#     would otherwise read as "nothing to do here" and register on the CP's defaults
#   * label matching is fold-insensitive, so the 'Show Advanced' guard (Playwright has_text,
#     substring + case-insensitive) and the walk cannot disagree about what a step is called
#   * 'Show Advanced' is switched on and PROVEN to have revealed the advanced steps
#   * a registration command that exits non-zero FAILS the step instead of being swallowed
#   * the download must be runnable at all (the missing-shebang bug)
#   * a route controller that is not on offer EXITS rather than registering against
#     whichever one happened to be preselected

from unittest.mock import MagicMock, patch

import pytest

from page_object.po_dataplane import (
    FRESCO_REGISTER_COMMAND_BLOCK,
    FRESCO_REGISTER_COMMAND_TITLE,
    FRESCO_REGISTER_CONTENT,
    FRESCO_REGISTER_DONE_BUTTON,
    FRESCO_REGISTER_DONE_TEXT,
    FRESCO_REGISTER_ICON_CONTAINER,
    FRESCO_GATEWAY_CONTROLLER_SELECT,
    FRESCO_INGRESS_CONTROLLER_SELECT,
    FRESCO_ROUTE_RESOURCE_GATEWAY_RADIO,
    FRESCO_STEP_BASIC,
    FRESCO_STEP_CONFIGURATION,
    FRESCO_STEP_NAMESPACE_SA,
    FRESCO_STEP_RESOURCES,
    FRESCO_WIZARD_ADVANCED_TOGGLE,
    FRESCO_WIZARD_NEXT,
    FRESCO_WIZARD_STEP,
    FRESCO_WIZARD_STEP_ACTIVE,
    HELM_REPO_COMMAND_TITLE,
    LEGACY_WIZARD_STEP_ACTIVE,
    PageObjectDataPlane,
)

DP = "k8s-auto-dp1"
BMDP = "k8s-auto-bmdp1"
NEW_HELM_REPO_TITLE = "1. Helm Repository Configuration"   # 1.21 capitalisation


class StrictModeViolation(Exception):
    """What Playwright raises when a multi-match locator is used without narrowing."""


class _Download:
    def __init__(self):
        self.value = object()

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


class _Locator:
    """A Playwright-shaped locator addressable by selector AND by its filters.

    Two properties of the real thing are modelled deliberately, because the production
    code's correctness turns on them:

    * **`has_text=` / `has=` are part of the identity.** The walk asks for the step rail
      twice with different filters - once unfiltered, once narrowed to the ACTIVE step. A
      registry keyed on the selector alone hands back the same object for both, and a test
      then cannot tell "the rail exists" from "this step is active"; it would pass while the
      code read the wrong one.
    * **`.first` actually narrows.** `is_visible()` raises on a multi-match locator that was
      not narrowed, exactly as Playwright's strict mode does. Without this the `.first` calls
      that this change depends on (the comma-selector wizard gate, the rail probe, the
      per-block download icon) could all be deleted with the suite still green - and strict
      mode is a headline concern of this change, so the harness has to be able to defend it.
    """

    def __init__(self, page, selector, key):
        self.page = page
        self._sel = selector
        self._key = key
        self.matches = 0          # how many elements this selector resolves to
        self.disabled = False
        self.text = ""
        self.text_contents = []
        self.on_click = None

    @property
    def first(self):
        self.page.narrowed.add(self._key)
        return self

    def nth(self, index):
        return self.page.locator(f"{self._sel}[{index}]")

    def count(self):
        return self.matches

    def is_visible(self):
        if self.matches > 1 and self._key not in self.page.narrowed:
            raise StrictModeViolation(
                f"strict mode violation: {self._sel!r} resolved to {self.matches} elements")
        return self.matches > 0

    def is_disabled(self):
        return self.disabled

    def get_attribute(self, name):
        return self.page.attributes.get((self._key, name))

    def inner_text(self):
        return self.text

    def all_text_contents(self):
        return list(self.text_contents)

    def click(self, **_kwargs):
        self.page.clicks.append(self._key)
        if self.on_click is not None:
            self.on_click()

    def check(self, **_kwargs):
        self.page.checked.append(self._key)

    def fill(self, value, **_kwargs):
        self.page.fills[self._sel] = value

    def press(self, key):
        self.page.pressed.append((self._key, key))

    def wait_for(self, **_kwargs):
        self.page.waits.append(self._key)

    def locator(self, sub, **kwargs):
        return self.page.locator(f"{self._sel} {sub}", **kwargs)


class _Page:
    """A Playwright-shaped page. Everything resolves to 0 matches unless a test says so."""

    url = "https://stub/"

    def __init__(self):
        self.registry = {}
        self.narrowed = set()
        self.attributes = {}
        self.element_texts = {}
        self.clicks = []
        self.checked = []
        self.pressed = []
        self.waits = []
        self.fills = {}

    @staticmethod
    def _key(selector, has_text, has):
        has_sel = getattr(has, "_sel", "") if has is not None else ""
        return f"{selector}|has_text={has_text}|has={has_sel}"

    def set_texts(self, selector, texts):
        """Declare the rendered text of every element matching `selector`.

        Only needed where a test cares HOW `has_text=` filters. Filtering is modelled on
        Playwright's real rule so an exact-vs-substring matcher is actually distinguishable:
        a plain string is a whitespace-normalised, case-insensitive **substring**; a compiled
        pattern is `re.search`.
        """
        self.element_texts[selector] = list(texts)
        return self

    def _filtered_count(self, selector, has_text):
        texts = self.element_texts.get(selector)
        if texts is None:
            return None
        if has_text is None:
            return len(texts)
        if hasattr(has_text, "search"):
            return sum(1 for t in texts if has_text.search(t))
        needle = " ".join(str(has_text).split()).casefold()
        return sum(1 for t in texts if needle in " ".join(t.split()).casefold())

    def locator(self, selector, has_text=None, has=None, **_kwargs):
        key = self._key(selector, has_text, has)
        if key not in self.registry:
            loc = _Locator(self, selector, key)
            count = self._filtered_count(selector, has_text)
            if count is not None:
                loc.matches = count
            self.registry[key] = loc
        return self.registry[key]

    def fill(self, selector, value, **_kwargs):
        self.fills[selector] = value

    def click(self, selector, **_kwargs):
        self.clicks.append(f"{selector}|has_text=None|has=")

    def wait_for_timeout(self, _ms):
        pass

    def expect_download(self):
        return _Download()

    def content(self):
        return ""

    def clicked(self, selector):
        return any(c.startswith(f"{selector}|") for c in self.clicks)


def _make_po():
    po = object.__new__(PageObjectDataPlane)
    po.page = _Page()
    po.loc = po.page.locator
    return po


def _present(locator, matches=1):
    locator.matches = matches
    return locator


def _visibility_router(visible_selectors):
    """Stand in for Util.check_dom_visibility, routed on the locator's selector.

    A blanket True/False would make every gate agree with every other gate, which is
    exactly how a test silently exercises the wrong branch.
    """
    def _check(_page, locator, *_a, **_k):
        return getattr(locator, "_sel", None) in visible_selectors
    return _check


@pytest.fixture(autouse=True)
def _no_screenshots(monkeypatch):
    """exit_error still really raises SystemExit; only its side effects are stubbed."""
    monkeypatch.setattr("utils.util.Util.screenshot_page", lambda *a, **k: None)
    monkeypatch.setattr("utils.util.Util.stop_tracing", lambda *a, **k: None)


# --- which wizard is on screen ------------------------------------------------------

class TestWizardDetection:
    def test_fresco_rail_present_selects_the_fresco_path(self):
        po = _make_po()
        _present(po.loc(FRESCO_WIZARD_STEP))
        assert po.is_fresco_register_wizard() is True

    def test_legacy_control_plane_is_not_mistaken_for_fresco(self):
        """A Control Plane that still renders the Pulse nav must keep the legacy path.

        Old Control Planes are not deprecated on a schedule; dropping their branch is what
        this assertion exists to prevent.
        """
        po = _make_po()
        _present(po.loc(LEGACY_WIZARD_STEP_ACTIVE))
        assert po.is_fresco_register_wizard() is False

    def test_the_rail_probe_is_narrowed_for_strict_mode(self):
        """The rail is one node PER STEP, so an un-narrowed is_visible() would throw.

        Delete the `.first` in is_fresco_register_wizard and this raises instead of
        answering - which is what Playwright really does.
        """
        po = _make_po()
        _present(po.loc(FRESCO_WIZARD_STEP), matches=7)
        assert po.is_fresco_register_wizard() is True

    def test_the_harness_really_enforces_strict_mode(self):
        """Control for the test above: without narrowing, a multi-match locator throws."""
        po = _make_po()
        _present(po.loc(FRESCO_WIZARD_STEP), matches=7)
        with pytest.raises(StrictModeViolation):
            po.page.locator(FRESCO_WIZARD_STEP).is_visible()


# --- the step walk ------------------------------------------------------------------

class TestActiveStep:
    def test_reads_the_label_and_drops_the_adv_badge(self):
        """Advanced-only steps render an 'ADV' badge on a second line."""
        po = _make_po()
        active = _present(po.loc(FRESCO_WIZARD_STEP, has=po.loc(FRESCO_WIZARD_STEP_ACTIVE)))
        active.text = f"{FRESCO_STEP_NAMESPACE_SA}\nADV"
        assert po.fresco_wizard_active_step() == FRESCO_STEP_NAMESPACE_SA

    def test_empty_when_the_rail_is_gone(self):
        """The final page drops the rail; that is the walk's terminator, not an error."""
        po = _make_po()
        assert po.fresco_wizard_active_step() == ""

    def test_a_rail_that_is_present_but_unmarked_is_not_read_as_finished(self):
        """The terminator is the rail GOING, not 'no step is marked active'.

        Angular re-renders the rail on each Next, so for a frame the `.wizard-step` nodes are
        on screen with no `.wizard-step-selected` child. `count()` is instantaneous, so landing
        in that frame used to end the walk. It was contained (the missing final page then made
        the run exit loudly) but it turned a transient render into a failed ~98-minute
        pipeline, and if it landed before the last filler the completeness check fired instead
        and blamed a label drift that never happened.
        """
        po = _make_po()
        rail = _present(po.loc(FRESCO_WIZARD_STEP), matches=7)
        active = po.loc(FRESCO_WIZARD_STEP, has=po.loc(FRESCO_WIZARD_STEP_ACTIVE))
        # Rail on screen, nothing marked active, and it never recovers.
        assert active.matches == 0 and rail.matches == 7

        with pytest.raises(SystemExit):
            po.fresco_wizard_active_step()

    def test_an_active_step_that_appears_on_the_re_poll_is_used(self):
        """The one-beat re-poll is what makes the mid-render frame survivable."""
        po = _make_po()
        _present(po.loc(FRESCO_WIZARD_STEP), matches=7)
        active = po.loc(FRESCO_WIZARD_STEP, has=po.loc(FRESCO_WIZARD_STEP_ACTIVE))
        active.text = FRESCO_STEP_NAMESPACE_SA

        # Unmarked on the first read, marked by the time the re-poll runs.
        reads = {"n": 0}

        def _late(_ms, _a=active):
            reads["n"] += 1
            _a.matches = 1

        po.page.wait_for_timeout = _late
        assert po.fresco_wizard_active_step() == FRESCO_STEP_NAMESPACE_SA
        assert reads["n"] == 1, "it must give the rail one beat before giving up"


class TestWizardWalk:
    def _walk_over(self, po, steps):
        """Make the rail report `steps` in order, one per Next click."""
        active = po.loc(FRESCO_WIZARD_STEP, has=po.loc(FRESCO_WIZARD_STEP_ACTIVE))
        remaining = list(steps)

        class _Rail:
            @staticmethod
            def sync():
                active.matches = 1 if remaining else 0
                active.text = remaining[0] if remaining else ""

        _Rail.sync()
        nxt = _present(po.loc(FRESCO_WIZARD_NEXT))
        nxt.text = "Next"

        def _advance():
            remaining.pop(0)
            _Rail.sync()

        nxt.on_click = _advance
        return nxt

    def test_runs_each_step_filler_and_stops_when_the_rail_disappears(self):
        po = _make_po()
        nxt = self._walk_over(po, [FRESCO_STEP_BASIC, FRESCO_STEP_NAMESPACE_SA, "Preview"])
        seen = []

        fillers = {
            FRESCO_STEP_BASIC: lambda: seen.append(FRESCO_STEP_BASIC),
            FRESCO_STEP_NAMESPACE_SA: lambda: seen.append(FRESCO_STEP_NAMESPACE_SA),
        }
        po.fresco_wizard_walk(fillers)
        # Every step advanced, including 'Preview', which has no filler.
        assert po.page.clicks.count(nxt._key) == 3
        assert seen == [FRESCO_STEP_BASIC, FRESCO_STEP_NAMESPACE_SA]

    def test_verified_prefilled_steps_pass_through_without_a_warning(self):
        """Container Registry / Helm Chart Repository / Preview arrive prefilled.

        They must NOT warn: three warnings on every healthy run is how the reader learns to
        skip the one line that matters - a step nobody has verified.
        """
        po = _make_po()
        nxt = self._walk_over(po, ["Container Registry", "Helm Chart Repository", "Preview"])

        with patch("page_object.po_dataplane.ColorLogger.warning") as warn:
            po.fresco_wizard_walk({})

        assert po.page.clicks.count(nxt._key) == 3
        warn.assert_not_called()

    def test_an_unverified_new_step_passes_through_but_warns(self):
        """A Control Plane may add a step; do not break the deploy, but say so."""
        po = _make_po()
        nxt = self._walk_over(po, ["Some Brand New Step"])

        with patch("page_object.po_dataplane.ColorLogger.warning") as warn:
            po.fresco_wizard_walk({})

        assert po.page.clicks.count(nxt._key) == 1
        warn.assert_called_once()
        assert "Some Brand New Step" in warn.call_args.args[0]

    def test_a_step_whose_label_drifts_is_not_silently_skipped(self):
        """The one that would put the data plane in the WRONG NAMESPACE.

        The fields on Namespace & Service Account arrive prefilled with the Control Plane's
        '<dp>-my-ns' / '<dp>-my-sa', so a filler that never fires leaves Next enabled and the
        wizard completes happily. Only a post-walk completeness check can catch it.
        """
        po = _make_po()
        self._walk_over(po, [FRESCO_STEP_BASIC, "Namespaces and Service Accounts", "Preview"])
        fired = []
        fillers = {
            FRESCO_STEP_BASIC: lambda: fired.append(FRESCO_STEP_BASIC),
            FRESCO_STEP_NAMESPACE_SA: lambda: fired.append(FRESCO_STEP_NAMESPACE_SA),
        }
        with pytest.raises(SystemExit):
            po.fresco_wizard_walk(fillers)
        assert fired == [FRESCO_STEP_BASIC]

    def test_a_re_capitalised_label_still_matches_its_filler(self):
        """'Namespace & Service account' is the LEGACY spelling of the same step.

        The 'Show Advanced' guard matches with Playwright's has_text (substring,
        case-insensitive), so a spelling that satisfies the guard must also satisfy the walk
        - otherwise the guard says "the step is there" and the walk skips it anyway.
        """
        po = _make_po()
        self._walk_over(po, ["Namespace & Service account", "Preview"])
        fired = []
        po.fresco_wizard_walk({FRESCO_STEP_NAMESPACE_SA: lambda: fired.append("ns")})
        assert fired == ["ns"]

    def test_extra_whitespace_in_the_label_still_matches(self):
        po = _make_po()
        self._walk_over(po, ["  Namespace  &   Service Account  ", "Preview"])
        fired = []
        po.fresco_wizard_walk({FRESCO_STEP_NAMESPACE_SA: lambda: fired.append("ns")})
        assert fired == ["ns"]

    def test_a_step_that_cannot_be_filled_aborts_with_its_own_name(self):
        """A disabled Next means a required field was missed. Say WHICH step."""
        po = _make_po()
        self._walk_over(po, ["Some New Step"])
        po.loc(FRESCO_WIZARD_NEXT).disabled = True

        with pytest.raises(SystemExit):
            po.fresco_wizard_walk({})

    def test_a_missing_next_button_aborts_instead_of_returning_quietly(self):
        """THE regression this ticket's own first fix attempt introduced.

        A bare `return` here propagated all the way out: k8s_create_dataplane returned
        normally, case/k8s_create_dp.py logged out and exited 0, and create-dp went green
        with no data plane, no commands run and no screenshot.

        The assertion is on WHICH error, deliberately. A bare `pytest.raises(SystemExit)`
        passes even with the fix reverted: the walk simply spins to its `max_steps` cap and
        exits on the generic "did not reach its final page" message instead. That is a test
        pinning the wrong contract - green for a reason that has nothing to do with the bug,
        and useless to whoever reads the pipeline log. The operator must be told the Next
        button is missing, and on which step.
        """
        po = _make_po()
        active = _present(po.loc(FRESCO_WIZARD_STEP, has=po.loc(FRESCO_WIZARD_STEP_ACTIVE)))
        active.text = FRESCO_STEP_BASIC
        # Next button absent: matches stays 0.
        errors = []

        def _exit(message, *_a, **_k):
            errors.append(message)
            raise SystemExit(1)

        with patch("page_object.po_dataplane.Util.exit_error", side_effect=_exit):
            with pytest.raises(SystemExit):
                po.fresco_wizard_walk({})

        assert len(errors) == 1, "it must fail on the first pass, not spin to the loop cap"
        assert "no Next button" in errors[0]
        assert FRESCO_STEP_BASIC in errors[0]

    def test_a_wizard_that_never_ends_aborts_instead_of_looping_for_ever(self):
        po = _make_po()
        active = _present(po.loc(FRESCO_WIZARD_STEP, has=po.loc(FRESCO_WIZARD_STEP_ACTIVE)))
        active.text = FRESCO_STEP_BASIC
        nxt = _present(po.loc(FRESCO_WIZARD_NEXT))
        nxt.text = "Next"

        with pytest.raises(SystemExit):
            po.fresco_wizard_walk({}, max_steps=4)
        assert po.page.clicks.count(nxt._key) == 4

    def test_the_next_button_disabled_check_reads_the_live_state(self):
        """is_disabled() covers aria-disabled / p-disabled, which the attribute does not.

        A button disabled that way used to be clicked, do nothing, and burn every remaining
        iteration re-filling the same step before the loop cap finally fired.
        """
        po = _make_po()
        self._walk_over(po, [FRESCO_STEP_BASIC])
        nxt = po.loc(FRESCO_WIZARD_NEXT)
        nxt.disabled = True
        # No `disabled` ATTRIBUTE at all - only the component-level state.
        assert nxt.get_attribute("disabled") is None

        with pytest.raises(SystemExit):
            po.fresco_wizard_walk({})
        assert nxt._key not in po.page.clicks


# --- Show Advanced: the silent-default trap -----------------------------------------

class TestShowAdvanced:
    def _toggle(self, po, checked):
        toggle = _present(po.loc(FRESCO_WIZARD_ADVANCED_TOGGLE))
        po.page.attributes[(toggle._key, "data-p-checked")] = checked
        return toggle

    def test_turns_the_toggle_on_when_it_is_off(self):
        po = _make_po()
        toggle = self._toggle(po, "false")

        with patch("page_object.po_dataplane.Util.check_dom_visibility", return_value=True):
            po.fresco_wizard_enable_advanced()

        assert po.page.clicks.count(toggle._key) == 1

    def test_does_not_flip_a_toggle_that_is_already_on(self):
        """It is a plain boolean flip, so a blind click would turn Advanced back OFF."""
        po = _make_po()
        toggle = self._toggle(po, "true")

        with patch("page_object.po_dataplane.Util.check_dom_visibility", return_value=True):
            po.fresco_wizard_enable_advanced()

        assert toggle._key not in po.page.clicks

    def test_aborts_when_the_advanced_steps_never_appear(self):
        """Without this the run continues into the Control Plane's default namespace.

        That is the whole reason this check exists: nothing else in the flow would notice,
        and the data plane would register into '<dp-name>-my-ns'.
        """
        po = _make_po()
        self._toggle(po, "false")

        with patch("page_object.po_dataplane.Util.check_dom_visibility", return_value=False):
            with pytest.raises(SystemExit):
                po.fresco_wizard_enable_advanced()

    def test_aborts_when_there_is_no_toggle_at_all(self):
        """Routed, not blanket-False: the toggle gate and the advanced-step gate are different
        questions, and a blanket answer lets a test pass through the branch it is not about."""
        po = _make_po()
        with patch("page_object.po_dataplane.Util.check_dom_visibility",
                   side_effect=_visibility_router(set())):
            with pytest.raises(SystemExit):
                po.fresco_wizard_enable_advanced()

    def test_a_toggle_that_paints_late_is_waited_for_rather_than_counted(self):
        """`count()` does not auto-wait, and this fires while the dialog is still mounting.

        A header that paints a beat after the step rail would kill a ~98-minute deploy with
        "has no 'Show Advanced' toggle". The only way a test can tell the wait apart from an
        instantaneous count is to make the element absent at first look and present during the
        poll — with a bare `count()` this run exits, with `check_dom_visibility` it proceeds.
        """
        po = _make_po()
        toggle = po.loc(FRESCO_WIZARD_ADVANCED_TOGGLE)   # not on screen yet: matches == 0
        po.page.attributes[(toggle._key, "data-p-checked")] = "false"

        def _paints_during_the_poll(_page, locator, *_a, **_k):
            if getattr(locator, "_sel", None) == FRESCO_WIZARD_ADVANCED_TOGGLE:
                toggle.matches = 1
            return True

        with patch("page_object.po_dataplane.Util.check_dom_visibility",
                   side_effect=_paints_during_the_poll):
            po.fresco_wizard_enable_advanced()

        assert po.page.clicks.count(toggle._key) == 1

    def test_a_missing_data_p_checked_attribute_is_caught_by_the_assertion_below_it(self):
        """`data-p-checked` is the ONLY signal separating 'already on' from 'off'.

        `get_attribute` returns None for an attribute that is absent or renamed, which falls
        into the click branch — so if PrimeNG ever moves that state onto the inner input, a
        toggle that was already ON gets clicked OFF and the wizard silently collapses to
        Basic -> Preview -> Generate Helm Commands, registering on the Control Plane's default
        namespace. That is the exact trap this method exists to close.

        It stays closed, but by the layer below: the advanced-step assertion then fails and the
        run exits loudly. This pins BOTH halves — the mis-read (the click happens) and the net
        that catches it (the run exits) — because either alone would be misleading.
        """
        po = _make_po()
        toggle = _present(po.loc(FRESCO_WIZARD_ADVANCED_TOGGLE))
        # No data-p-checked at all: page.attributes has no entry, so get_attribute -> None.
        assert toggle.get_attribute("data-p-checked") is None

        # The toggle itself IS there; only the advanced steps never appear. Routing the two
        # gates separately is what makes this test about the attribute rather than the toggle.
        with patch("page_object.po_dataplane.Util.check_dom_visibility",
                   side_effect=_visibility_router({FRESCO_WIZARD_ADVANCED_TOGGLE})):
            with pytest.raises(SystemExit):
                po.fresco_wizard_enable_advanced()

        assert po.page.clicks.count(toggle._key) == 1, "an unreadable toggle must still be clicked"


# --- the fields the automation actually cares about ---------------------------------

class TestStepFillers:
    def test_namespace_and_service_account_overwrite_the_control_plane_defaults(self):
        po = _make_po()
        po.fresco_fill_namespace_sa_step("k8s-auto-dp1ns", "k8s-auto-dp1-sa")

        assert po.page.fills["#dp-namespace-input"] == "k8s-auto-dp1ns"
        assert po.page.fills["#dp-service-account-input"] == "k8s-auto-dp1-sa"

    def test_basic_step_skips_the_control_tower_only_fields_for_a_k8s_data_plane(self):
        po = _make_po()
        po.fresco_fill_basic_step(DP)

        assert po.page.fills == {"#dp-name-input": DP}
        assert po.page.checked  # the EUA box was ticked

    def test_basic_step_fills_the_control_tower_fields(self):
        po = _make_po()
        po.fresco_fill_basic_step(BMDP, is_control_tower=True, machine_host_name="bmdp.example.com")

        assert po.page.fills["#dp-name-input"] == BMDP
        assert po.page.fills["#machine-host-name-input"] == "bmdp.example.com"
        # Asserted on `checked`, not "checked OR clicked". The production code uses
        # .check(force=True) specifically - a plain click on a PrimeNG radio label behaves
        # differently - and an or-joined assertion cannot tell the two apart, so it would stay
        # green through exactly the behaviour change it is supposed to catch.
        assert "#ct-flavor-radio-k8s|has_text=None|has=" in po.page.checked

    def test_the_control_tower_wizard_ticks_the_SAME_eula_control_as_the_k8s_one(self):
        """The legacy wizards did NOT share this control, so the Fresco one sharing it is a claim.

        Legacy `k8s_create_dataplane` clicked `label[for="eua-checkbox"]` while
        `k8s_create_bmdp` clicked `label[for="terms-checkbox"]`. The Fresco flows both go
        through `fresco_check_eula`, i.e. both assert `formcontrolname="eula"`. Asserting only
        that *something* was checked would stay green if the CT wizard bound a different
        control, so this pins the exact locator on the Control Tower path.

        Not inferred: the CT Basic step was mapped over CDP on ins-owen-o11y-10 and reports
        `formcontrolname="eula"`, and `case.bmdp_create_dp` has since run green end to end
        three times, which it cannot do without this box being ticked.
        """
        eula_key = 'tibco-checkbox[formcontrolname="eula"] input.p-checkbox-input|has_text=None|has='

        po = _make_po()
        po.fresco_fill_basic_step(BMDP, is_control_tower=True, machine_host_name="bmdp.example.com")
        assert eula_key in po.page.checked

        # ...and the Kubernetes flow ticks that same control, which is what "shared" means.
        po = _make_po()
        po.fresco_fill_basic_step(DP)
        assert eula_key in po.page.checked

    def test_control_tower_without_a_host_name_aborts_instead_of_taking_the_preselected_type(self):
        """An empty TP_AUTO_FQDN_BMDP used to skip the flavour radio too.

        The flavour and the host name were both keyed off `machine_host_name`, so an unset env
        var silently left the Control Tower type at whatever the Control Plane preselected -
        and 'Native' is a completely different data plane with no cheap way back. Same
        silent-wrong-registration shape the rest of this flow exits over.
        """
        po = _make_po()
        with pytest.raises(SystemExit):
            po.fresco_fill_basic_step(BMDP, is_control_tower=True, machine_host_name="")

        assert po.page.fills == {}
        assert po.page.checked == []

    def test_reachable_url_is_filled_only_when_the_control_plane_renders_it(self):
        """Hybrid connectivity is on by default, and then there is no URL field at all."""
        po = _make_po()
        with patch("page_object.po_dataplane.Util.check_dom_visibility", return_value=False), \
             patch("page_object.po_dataplane.ENV") as env:
            env.TP_IS_CERT_SELF_SIGNED = False
            po.fresco_fill_configuration_step("https://dp.example.com")
        assert po.page.fills == {}

        po = _make_po()
        with patch("page_object.po_dataplane.Util.check_dom_visibility",
                   side_effect=_visibility_router({"#dp-url-input"})), \
             patch("page_object.po_dataplane.ENV") as env:
            env.TP_IS_CERT_SELF_SIGNED = False
            po.fresco_fill_configuration_step("https://dp.example.com")
        assert po.page.fills["#dp-url-input"] == "https://dp.example.com"


# --- the Control Tower wizard (AC3) -------------------------------------------------

class TestControlTowerWizard:
    def test_it_fills_the_same_shared_steps_plus_resources(self):
        """The CT wizard is the k8s one plus a Resources step; the fillers must say so."""
        po = _make_po()
        captured = {}
        po.fresco_wizard_enable_advanced = MagicMock()
        po.fresco_wizard_walk = MagicMock(side_effect=lambda f, **k: captured.update(f))
        po.fresco_run_register_commands = MagicMock(return_value=False)

        with patch("page_object.po_dataplane.ENV") as env:
            env.TP_AUTO_FQDN_BMDP = "bmdp.example.com"
            env.TP_AUTO_K8S_BMDP_NAMESPACE = "k8s-auto-bmdp1ns"
            env.TP_AUTO_K8S_BMDP_SERVICE_ACCOUNT = "k8s-auto-bmdp1-sa"
            env.TP_AUTO_REACHABLE_BMDP_URL = "https://bmdp.example.com"
            with pytest.raises(SystemExit):
                po.k8s_create_bmdp_fresco(BMDP)

        assert set(captured) == {FRESCO_STEP_BASIC, FRESCO_STEP_NAMESPACE_SA,
                                 FRESCO_STEP_RESOURCES, FRESCO_STEP_CONFIGURATION}
        po.fresco_wizard_enable_advanced.assert_called_once()

    def test_a_failed_registration_never_deletes_the_control_tower_data_plane(self):
        """By this point 'Save' has already registered it; deleting on a DOM timeout is worse."""
        po = _make_po()
        po.fresco_wizard_enable_advanced = MagicMock()
        po.fresco_wizard_walk = MagicMock()
        po.fresco_run_register_commands = MagicMock(return_value=False)
        po.k8s_delete_dataplane = MagicMock()

        with patch("page_object.po_dataplane.ENV"):
            with pytest.raises(SystemExit):
                po.k8s_create_bmdp_fresco(BMDP)
        po.k8s_delete_dataplane.assert_not_called()

    def test_resources_step_uses_the_ingress_branch_by_default(self):
        po = _make_po()
        po.fresco_select_route_controller = MagicMock()

        with patch("page_object.po_dataplane.ENV") as env:
            env.TP_AUTO_INGRESS_OBJECT = "ingress"
            env.TP_AUTO_INGRESS_CONTROLLER = "nginx"
            env.TP_AUTO_INGRESS_CONTROLLER_CLASS_NAME = "nginx"
            env.TP_AUTO_FQDN_BMDP = "bmdp.example.com"
            po.fresco_fill_ctdp_resources_step()

        assert po.page.fills["#ctdp-storage-class-name-input"] == "nfs"
        assert po.page.fills["#ctdp-ingress-resource-name-input"] == "nginx"
        assert po.page.fills["#ctdp-ingress-class-name-input"] == "nginx"
        assert po.page.fills["#ctdp-fqdn-input"] == "bmdp.example.com"
        po.fresco_select_route_controller.assert_called_once_with(
            FRESCO_INGRESS_CONTROLLER_SELECT, "nginx")

    def test_gateway_mode_fills_the_whole_gateway_field_set(self):
        """Gateway is a DIFFERENT form, not a relabelled ingress one.

        Picking Gateway API swaps the controller dropdown's form control and replaces the field
        set: `#ctdp-gateway-*` instead of `#ctdp-ingress-*` + `#ctdp-fqdn-input`, with Gateway
        Name and Gateway Namespace required and having no ingress counterpart. Filling the
        ingress ids here would leave three required fields empty and the wizard stuck.
        """
        po = _make_po()
        po.fresco_select_route_controller = MagicMock()
        _present(po.loc(FRESCO_ROUTE_RESOURCE_GATEWAY_RADIO))

        with patch("page_object.po_dataplane.Util.check_dom_visibility", return_value=True), \
             patch("page_object.po_dataplane.ENV") as env:
            env.TP_AUTO_INGRESS_OBJECT = "gateway"
            env.TP_AUTO_GATEWAY_CONTROLLER = "istio"
            env.TP_AUTO_GATEWAY_NAME = "nginx-gateway"
            env.TP_AUTO_GATEWAY_NAMESPACE = "ingress-system"
            env.TP_AUTO_FQDN_BMDP = "bmdp.example.com"
            po.fresco_fill_ctdp_resources_step()

        assert po.page.fills["#ctdp-gateway-resource-name-input"] == "istio"
        assert po.page.fills["#ctdp-gateway-name-input"] == "nginx-gateway"
        assert po.page.fills["#ctdp-gateway-namespace-input"] == "ingress-system"
        assert po.page.fills["#ctdp-gateway-host-input"] == "bmdp.example.com"
        # None of the ingress-mode ids exist on this form.
        assert "#ctdp-ingress-resource-name-input" not in po.page.fills
        assert "#ctdp-ingress-class-name-input" not in po.page.fills
        assert "#ctdp-fqdn-input" not in po.page.fills
        po.fresco_select_route_controller.assert_called_once_with(
            FRESCO_GATEWAY_CONTROLLER_SELECT, "istio")

    def test_gateway_mode_aborts_when_the_radio_never_appears(self):
        """An instantaneous is_visible() right after a Next click races Angular's render.

        Falling through to Ingress there would register the wrong route-resource type and still
        report success. TP_AUTO_INGRESS_OBJECT='gateway' is an explicit operator request, so a
        missing radio is an error rather than an older-Control-Plane fallback.
        """
        po = _make_po()
        po.fresco_select_route_controller = MagicMock()

        with patch("page_object.po_dataplane.Util.check_dom_visibility", return_value=False), \
             patch("page_object.po_dataplane.ENV") as env:
            env.TP_AUTO_INGRESS_OBJECT = "gateway"
            with pytest.raises(SystemExit):
                po.fresco_fill_ctdp_resources_step()

        po.fresco_select_route_controller.assert_not_called()
        assert "#ctdp-ingress-resource-name-input" not in po.page.fills

    def _selected_option(self, po, controller, offered):
        """Drive the dropdown over a declared option list; return how many options matched."""
        po.page.set_texts("li.p-select-option", offered)
        seen = {}
        real_locator = po.page.locator

        def _spy(selector, **kwargs):
            found = real_locator(selector, **kwargs)
            if selector == "li.p-select-option":
                seen["matches"] = found.matches
            return found

        po.page.locator = _spy
        with patch("page_object.po_dataplane.Util.check_dom_visibility", return_value=True):
            po.fresco_select_route_controller(FRESCO_INGRESS_CONTROLLER_SELECT, controller)
        return seen["matches"]

    def test_the_route_controller_is_matched_on_its_whole_text(self):
        """`nginx` must not select `Nginx Gateway Fabric`.

        Playwright's `has_text=` is a case-insensitive SUBSTRING, so with `.first` a controller
        whose name prefixes another offered option would silently bind the wrong one and report
        success - the exact outcome the abort in this method exists to prevent. Same anchoring
        lesson as the `nfs` vs `nfs-backup` storage matcher in PCP-23953.
        """
        matched = self._selected_option(
            _make_po(), "nginx", ["Nginx", "Nginx Gateway Fabric", "Traefik"])
        assert matched == 1, "the matcher resolved more than one option; .first would guess"

    def test_the_route_controller_match_is_case_insensitive(self):
        """The env var is lowercase (`nginx`); the dropdown renders `Nginx`."""
        assert self._selected_option(_make_po(), "nginx", ["Nginx", "Traefik"]) == 1

    def test_a_multi_word_route_controller_still_matches(self):
        """`.capitalize()` used to mangle these into `Nginx gateway fabric`."""
        assert self._selected_option(
            _make_po(), "nginx gateway fabric", ["Nginx", "Nginx Gateway Fabric"]) == 1

    def test_a_route_controller_that_is_not_offered_aborts(self):
        """Weaker than the legacy code it replaces is not acceptable.

        The legacy dropdown clicked the option and threw when it was missing. Warning and
        keeping the preselected controller would register the data plane against the wrong
        ingress controller and still report success.
        """
        po = _make_po()
        _present(po.loc(FRESCO_INGRESS_CONTROLLER_SELECT))

        with patch("page_object.po_dataplane.Util.check_dom_visibility", return_value=False):
            with pytest.raises(SystemExit):
                po.fresco_select_route_controller(FRESCO_INGRESS_CONTROLLER_SELECT, "nginx")


# --- the registration commands ------------------------------------------------------

class TestRegisterCommands:
    def _final_page(self, po, titles):
        po.loc(FRESCO_REGISTER_COMMAND_TITLE).text_contents = list(titles)
        _present(po.loc(FRESCO_REGISTER_COMMAND_BLOCK), matches=len(titles))

    def test_each_command_is_paired_with_its_own_block(self):
        """A page-wide icon match could shift the pairing and run the wrong script."""
        po = _make_po()
        titles = [NEW_HELM_REPO_TITLE, "2. Namespace creation"]
        self._final_page(po, titles)
        po.k8s_run_dataplane_command = MagicMock()

        with patch("page_object.po_dataplane.Util.check_dom_visibility", return_value=True):
            assert po.fresco_run_register_commands(DP) is True

        calls = po.k8s_run_dataplane_command.call_args_list
        assert [c.args[1] for c in calls] == titles
        assert [c.args[3] for c in calls] == [1, 2]
        # Block-scoped, so the n-th title's icon comes from the n-th block.
        for index in (0, 1):
            assert calls[index].args[2]._sel == (
                f"{FRESCO_REGISTER_COMMAND_BLOCK}[{index}] {FRESCO_REGISTER_ICON_CONTAINER}")

    def test_an_empty_command_list_aborts_instead_of_reporting_success(self):
        po = _make_po()
        self._final_page(po, [])
        po.k8s_run_dataplane_command = MagicMock()

        with patch("page_object.po_dataplane.Util.check_dom_visibility", return_value=True):
            with pytest.raises(SystemExit):
                po.fresco_run_register_commands(DP)
        po.k8s_run_dataplane_command.assert_not_called()

    def test_a_title_block_mismatch_refuses_to_run_anything(self):
        po = _make_po()
        po.loc(FRESCO_REGISTER_COMMAND_TITLE).text_contents = ["1. a", "2. b", "3. c"]
        _present(po.loc(FRESCO_REGISTER_COMMAND_BLOCK), matches=2)
        po.k8s_run_dataplane_command = MagicMock()

        with patch("page_object.po_dataplane.Util.check_dom_visibility", return_value=True):
            with pytest.raises(SystemExit):
                po.fresco_run_register_commands(DP)
        po.k8s_run_dataplane_command.assert_not_called()

    def test_returns_false_when_the_final_page_never_renders(self):
        """The caller turns this into a named exit; it must not be swallowed."""
        po = _make_po()
        with patch("page_object.po_dataplane.Util.check_dom_visibility",
                   side_effect=_visibility_router(set())):
            assert po.fresco_run_register_commands(DP) is False

    def test_done_is_anchored_on_its_text_not_on_being_the_first_button(self):
        """A footer that later gains a Back button must not have IT clicked instead."""
        po = _make_po()
        po.wait_for_overlay_to_clear = MagicMock()
        po.fresco_register_click_done()

        expected = f"{FRESCO_REGISTER_DONE_BUTTON}|has_text={FRESCO_REGISTER_DONE_TEXT}|has="
        assert expected in po.page.clicks

    def test_done_does_not_wait_for_a_confirmation_that_no_longer_exists(self):
        """The legacy '#confirm-button' -> 'Yes' dialog is gone in 1.21; waiting hangs."""
        po = _make_po()
        po.wait_for_overlay_to_clear = MagicMock()
        po.fresco_register_click_done()

        assert not any("#confirm-button" in key for key in po.page.registry)


# --- a registration command that FAILS must fail the step ---------------------------

class TestCommandFailureIsNotSwallowed:
    def _run(self, po, title, run_shell_file):
        with patch("page_object.po_dataplane.Util.download_file", return_value=_write_temp("echo hi\n")), \
             patch("page_object.po_dataplane.Helper.get_command_output", return_value=""), \
             patch("page_object.po_dataplane.Helper.run_shell_file", side_effect=run_shell_file), \
             patch("page_object.po_dataplane.ENV") as env:
            env.TP_CREATE_NETWORK_POLICIES = "false"
            env.TP_AUTO_K8S_DP_SERVICE_ACCOUNT_CREATION_ADDITIONAL_SETTINGS = ""
            env.TP_IS_CERT_SELF_SIGNED = False
            po.k8s_run_dataplane_command(DP, title, MagicMock(), 2)

    def test_a_non_zero_registration_command_aborts_the_step(self):
        """The general form of the bug the shebang fix only closed one instance of.

        Helper.run_shell_file swallowed every failure and returned "", and this caller
        ignored the result - so a failing helm/kubectl read exactly like a successful one,
        the loop moved on, Done was clicked, and the task went green.
        """
        po = _make_po()

        def _boom(*_a, **_k):
            raise RuntimeError("helm upgrade exited 1")

        with pytest.raises(SystemExit):
            self._run(po, "2. Namespace creation", _boom)

    def test_it_asks_the_runner_to_raise_rather_than_swallow(self):
        po = _make_po()
        seen = {}

        def _ok(path, *_a, **kwargs):
            seen.update(kwargs)
            return ""

        self._run(po, "2. Namespace creation", _ok)
        assert seen.get("raise_on_failure") is True

    def test_a_failing_TEARDOWN_command_does_not_abort_the_delete(self):
        """Delete is best-effort; aborting there leaves the data plane half torn down.

        The abort added for registration reached delete-data-plane too, which was wrong twice:
        the run would exit before clicking the delete dialog's confirm button and before
        `ReportYaml.remove_dataplane`, and teardown scripts exit non-zero for entirely benign
        reasons — a `helm uninstall` of a release already gone, a `kubectl delete` on a missing
        namespace. A partially-installed data plane, which is exactly what this ticket's defect
        produced, is the input most likely to cause one.
        """
        po = _make_po()

        def _boom(*_a, **kwargs):
            assert not kwargs.get("raise_on_failure"), "teardown must not ask the runner to raise"
            return ""

        with patch("page_object.po_dataplane.Util.download_file", return_value=_write_temp("helm uninstall x\n")), \
             patch("page_object.po_dataplane.Helper.run_shell_file", side_effect=_boom), \
             patch("page_object.po_dataplane.ENV") as env:
            env.TP_CREATE_NETWORK_POLICIES = "false"
            env.TP_AUTO_K8S_DP_SERVICE_ACCOUNT_CREATION_ADDITIONAL_SETTINGS = ""
            env.TP_IS_CERT_SELF_SIGNED = False
            # No SystemExit: the caller must survive to finish the teardown.
            po.k8s_run_dataplane_command(DP, "Delete Data Plane", MagicMock(), 0,
                                         abort_on_failure=False)

    def test_the_delete_flow_passes_abort_on_failure_false(self):
        """Pins the call site, not just the parameter: delete must opt out."""
        po = _make_po()
        po.k8s_run_dataplane_command = MagicMock()
        po._dataplane_name_locator = MagicMock(return_value=_present(po.loc(".dp")))
        po.goto_left_navbar_dataplane = MagicMock()

        with patch("page_object.po_dataplane.Util.refresh_until_success", return_value=True), \
             patch("page_object.po_dataplane.Util.check_dom_visibility", return_value=True), \
             patch("page_object.po_dataplane.Util.wait_for_success_message", return_value=False), \
             patch("page_object.po_dataplane.ReportYaml.remove_dataplane"), \
             patch("page_object.po_dataplane.ENV"):
            po.page.evaluate = MagicMock()
            po.k8s_delete_dataplane(DP)

        assert po.k8s_run_dataplane_command.call_args is not None, "the delete command must run"
        assert po.k8s_run_dataplane_command.call_args.kwargs.get("abort_on_failure") is False

    def test_the_legacy_flow_runs_its_commands_through_the_same_aborting_sink(self):
        """`k8s_run_dataplane_command` is shared, so this is a LEGACY behaviour change too.

        The PR describes the legacy path as frozen, and for the wizard walk it is. But the
        command sink is shared by four flows — Fresco register, legacy k8s register, legacy
        BMDP register, and delete-data-plane — so `raise_on_failure=True` reaches CP 1.20 as
        well: a registration helm/kubectl that exits non-zero used to be logged and walked
        past, and now aborts. That is intended (a swallowed exit code is the failure class
        this ticket closes), but "intended" needs pinning, and the legacy routing test mocks
        the sink out entirely, so nothing else covers it.

        This asserts the legacy loop really does reach the shared sink, which is what makes
        the behaviour change apply there at all.
        """
        po = _make_po()
        po.k8s_create_dataplane_fresco = MagicMock()
        po.k8s_run_dataplane_command = MagicMock()
        po.k8s_setup_dp_reachability = MagicMock()
        po.k8s_wait_tunnel_connected = MagicMock()
        _present(po.loc(LEGACY_WIZARD_STEP_ACTIVE))
        po.loc(".register-data-plane p.title").text_contents = [
            NEW_HELM_REPO_TITLE, "2. Namespace creation"]

        with patch("page_object.po_dataplane.ReportYaml.is_dataplane_created", return_value=False), \
             patch("page_object.po_dataplane.ReportYaml.set_dataplane_info"), \
             patch("page_object.po_dataplane.Util.check_dom_visibility", return_value=True), \
             patch("page_object.po_dataplane.ENV") as env:
            env.TP_AUTO_MAX_DATA_PLANE = 10
            env.TP_AUTO_K8S_DP_NAMESPACE = "k8s-auto-dp1ns"
            env.TP_AUTO_K8S_DP_SERVICE_ACCOUNT = "k8s-auto-dp1-sa"
            env.TP_AUTO_REACHABLE_DP_URL = "https://dp.example.com"
            env.TP_IS_CERT_SELF_SIGNED = False
            po.k8s_create_dataplane(DP)

        titles = [c.args[1] for c in po.k8s_run_dataplane_command.call_args_list]
        assert titles == [NEW_HELM_REPO_TITLE, "2. Namespace creation"], (
            "the legacy loop must route its commands through the shared sink, which is what "
            "makes raise_on_failure apply to CP 1.20 as well")


# --- the downloaded script must be runnable -----------------------------------------

_TEMP_FILES = []


def _write_temp(content):
    import tempfile

    handle = tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False, encoding="utf-8")
    handle.write(content)
    handle.close()
    _TEMP_FILES.append(handle.name)
    return handle.name


@pytest.fixture(autouse=True)
def _clean_temp_files():
    yield
    import os

    while _TEMP_FILES:
        try:
            os.unlink(_TEMP_FILES.pop())
        except OSError:
            pass


class TestPreparingTheFileHonoursTheSameContract:
    """Review finding (PR #439, adhanshe-tibco): _ensure_shebang sat OUTSIDE the guard.

    `abort_on_failure=False` is a documented best-effort contract, and `k8s_delete_dataplane`
    relies on it: anything that raises out of `k8s_run_dataplane_command` skips the delete
    dialog's confirm click and `ReportYaml.remove_dataplane`, leaving the data plane half torn
    down. Running the file was guarded; PREPARING it was not - `_ensure_shebang` reads and
    rewrites the download, so a file that is not valid UTF-8 (or a download that raced to
    disk) raised straight past the guard. A partially-installed data plane, which is exactly
    what this ticket's defect produced, is the input most likely to cause one.
    """

    @staticmethod
    def _run(po, abort_on_failure, exc):
        with patch("page_object.po_dataplane.Util.download_file", return_value="/tmp/whatever.sh"),              patch.object(PageObjectDataPlane, "_ensure_shebang", side_effect=exc),              patch("page_object.po_dataplane.Helper.run_shell_file", return_value=""),              patch("page_object.po_dataplane.ENV") as env:
            env.TP_CREATE_NETWORK_POLICIES = "false"
            env.TP_AUTO_K8S_DP_SERVICE_ACCOUNT_CREATION_ADDITIONAL_SETTINGS = ""
            env.TP_IS_CERT_SELF_SIGNED = False
            po.k8s_run_dataplane_command(DP, "Delete Data Plane", MagicMock(), 0,
                                         abort_on_failure=abort_on_failure)

    @pytest.mark.parametrize("exc", [
        UnicodeDecodeError("utf-8", bytes([0xFF]), 0, 1, "invalid start byte"),
        OSError("download not on disk yet"),
    ])
    def test_teardown_survives_an_unreadable_download(self, exc):
        """No raise: the caller must live to click confirm and clear the report entry."""
        po = _make_po()
        self._run(po, abort_on_failure=False, exc=exc)

    def test_the_registration_path_still_fails_loudly(self):
        """The other half of the contract - abort_on_failure=True must NOT swallow it.

        A registration whose script could not be prepared is the silent-success this whole
        ticket exists to remove, so it has to exit, not warn.
        """
        po = _make_po()
        with pytest.raises(SystemExit):
            self._run(po, abort_on_failure=True, exc=OSError("boom"))


class TestEnsureShebang:
    """The second silent failure this ticket uncovered, and the more dangerous one.

    Helper.run_shell_file exec's the file directly on Linux. The Fresco wizard downloads the
    raw command text with no interpreter line, so every command died with 'Exec format error'
    -- and NOTHING noticed: the loop still ran to completion, Done was still clicked, and the
    Control Plane still listed a data plane. Observed live on ins-owen-o11y-10: 4 commands
    'executed', 0 namespaces created.
    """

    def test_a_script_without_a_shebang_gets_one(self):
        path = _write_temp("helm repo add tibco-platform-public https://example.invalid/repo\n")
        assert PageObjectDataPlane._ensure_shebang(path) is True

        with open(path, encoding="utf-8") as f:
            content = f.read()
        assert content.startswith("#!/bin/bash\n")
        # The command itself must survive untouched -- it is about to be run.
        assert content.endswith("helm repo add tibco-platform-public https://example.invalid/repo\n")

    def test_a_script_that_already_has_one_is_left_alone(self):
        original = "#!/bin/sh\necho hello\n"
        path = _write_temp(original)
        assert PageObjectDataPlane._ensure_shebang(path) is False

        with open(path, encoding="utf-8") as f:
            assert f.read() == original

    def test_the_download_is_made_runnable_before_it_is_run(self):
        """Ordering matters: the shebang has to be in place by the time bash sees it."""
        po = _make_po()
        path = _write_temp("kubectl apply -f -\n")
        seen = {}

        with patch("page_object.po_dataplane.Util.download_file", return_value=path), \
             patch("page_object.po_dataplane.Helper.run_shell_file",
                   side_effect=lambda p, *a, **k: seen.update(head=open(p, encoding="utf-8").read(11))), \
             patch("page_object.po_dataplane.ENV") as env:
            env.TP_CREATE_NETWORK_POLICIES = "false"
            env.TP_AUTO_K8S_DP_SERVICE_ACCOUNT_CREATION_ADDITIONAL_SETTINGS = ""
            env.TP_IS_CERT_SELF_SIGNED = False
            po.k8s_run_dataplane_command(DP, "2. Namespace creation", MagicMock(), 2)

        assert seen["head"] == "#!/bin/bash"


class TestCommandTitleCapitalisation:
    def _repo_reset_calls(self, po, title):
        recorded = []
        script = "helm repo add tibco-platform-public https://example.invalid/repo\n"

        with patch("page_object.po_dataplane.Util.download_file", return_value=_write_temp(script)), \
             patch("page_object.po_dataplane.Helper.get_command_output",
                   side_effect=lambda cmd, *a, **k: recorded.append(cmd)), \
             patch("page_object.po_dataplane.Helper.run_shell_file", return_value=""), \
             patch("page_object.po_dataplane.ENV") as env:
            env.TP_CREATE_NETWORK_POLICIES = "false"
            env.TP_AUTO_K8S_DP_SERVICE_ACCOUNT_CREATION_ADDITIONAL_SETTINGS = ""
            env.TP_IS_CERT_SELF_SIGNED = False
            po.k8s_run_dataplane_command(DP, title, MagicMock(), 1)
        return recorded

    def test_the_1_21_helm_repo_title_still_triggers_the_repo_reset(self):
        """1.21 renamed 'configuration' -> 'Configuration'.

        The old exact-match compared against the 1.20 spelling, so the reset was skipped
        without a word and a stale helm repo served the registration charts.
        """
        assert self._repo_reset_calls(_make_po(), NEW_HELM_REPO_TITLE) == [
            "helm repo remove tibco-platform-public"]

    def test_the_1_20_spelling_still_works(self):
        """Backward compatibility: the older Control Planes send the lowercase title."""
        assert self._repo_reset_calls(_make_po(), HELM_REPO_COMMAND_TITLE) == [
            "helm repo remove tibco-platform-public"]


# --- the branch point in k8s_create_dataplane ---------------------------------------

class TestCreateDataPlaneRouting:
    def test_fresco_control_plane_takes_the_fresco_path(self):
        po = _make_po()
        po.k8s_create_dataplane_fresco = MagicMock()
        _present(po.loc(FRESCO_WIZARD_STEP), matches=7)

        with patch("page_object.po_dataplane.ReportYaml.is_dataplane_created", return_value=False), \
             patch("page_object.po_dataplane.Util.check_dom_visibility", return_value=True), \
             patch("page_object.po_dataplane.ENV") as env:
            env.TP_AUTO_MAX_DATA_PLANE = 10
            po.k8s_create_dataplane(DP)

        po.k8s_create_dataplane_fresco.assert_called_once_with(DP)
        # The legacy wizard must not be touched at all on a 1.21 Control Plane.
        assert po.page.fills == {}

    def test_legacy_control_plane_still_walks_the_legacy_wizard(self):
        po = _make_po()
        po.k8s_create_dataplane_fresco = MagicMock()
        po.k8s_run_dataplane_command = MagicMock()
        po.k8s_setup_dp_reachability = MagicMock()
        po.k8s_wait_tunnel_connected = MagicMock()
        _present(po.loc(LEGACY_WIZARD_STEP_ACTIVE))

        with patch("page_object.po_dataplane.ReportYaml.is_dataplane_created", return_value=False), \
             patch("page_object.po_dataplane.ReportYaml.set_dataplane_info"), \
             patch("page_object.po_dataplane.Util.check_dom_visibility", return_value=True), \
             patch("page_object.po_dataplane.ENV") as env:
            env.TP_AUTO_MAX_DATA_PLANE = 10
            env.TP_AUTO_K8S_DP_NAMESPACE = "k8s-auto-dp1ns"
            env.TP_AUTO_K8S_DP_SERVICE_ACCOUNT = "k8s-auto-dp1-sa"
            env.TP_AUTO_REACHABLE_DP_URL = "https://dp.example.com"
            env.TP_IS_CERT_SELF_SIGNED = False
            po.k8s_create_dataplane(DP)

        po.k8s_create_dataplane_fresco.assert_not_called()
        assert po.page.fills["#data-plane-name-text-input"] == DP
        assert po.page.clicked("#data-plane-basics-btn")

    def test_a_failed_registration_never_deletes_the_data_plane(self):
        """'Save' on Preview has already registered it, so delete-and-retry is destructive.

        The legacy branch deleted on a DOM timeout and recursed into k8s_create_dataplane,
        which reports 'already created' the moment the delete does not take - turning a
        failed registration into a green task. The Fresco path fails loudly instead.
        """
        po = _make_po()
        po.fresco_wizard_enable_advanced = MagicMock()
        po.fresco_wizard_walk = MagicMock()
        po.fresco_run_register_commands = MagicMock(return_value=False)
        po.k8s_delete_dataplane = MagicMock()

        with patch("page_object.po_dataplane.ENV"):
            with pytest.raises(SystemExit):
                po.k8s_create_dataplane_fresco(DP)
        po.k8s_delete_dataplane.assert_not_called()
