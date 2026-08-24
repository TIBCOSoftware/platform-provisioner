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
# The first tests for the Assign Permissions "Product Permission" wizard, driven
# through PageObjectUserManagement.grant_product_permission.
#
# What makes this wizard dangerous enough to deserve them:
#   * 'Update' posts the user's ENTIRE permission set (a full replace). A wizard
#     that was misread and then submitted does not just fail to add a grant, it
#     REMOVES the base CP/DP policies the user already had.
#   * The wildcard-domains checkbox publishes aria-checked, but the component
#     pre-seeds it to "false" and writes the real value only inside the
#     resource-instances XHR callback. There is no tri-state, so a read taken
#     before the response settles is indistinguishable from "not granted" — and
#     clicking on it toggles an EXISTING grant off and rewrites it as per-domain
#     rows.
#   * setWildCardDomains() zeroes read/write on EVERY wildcard click, checked or
#     unchecked, so a Write tick made before the wildcard converges is discarded.
#   * A DENIED update persists nothing and leaves the wizard open with a toast;
#     only a successful one routes the SPA to add-user-finished. Success has to
#     be proven, not assumed.
#
# The page is modelled by a small scriptable fake rather than a bare MagicMock:
# these tests are about the ORDER of clicks and about clicks that must NEVER
# happen, which a MagicMock (every attribute truthy, no state) cannot express.

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from page_object.po_user_management import (
    GRANT_ALREADY,
    GRANT_DONE,
    GRANT_FAILED,
    GRANT_SKIPPED,
    PageObjectUserManagement,
)
from utils.env import ENV
from utils.util import Util

USERS_URL = "https://cp.example.com/cp/app/manage/users"
FINISHED_URL = "https://cp.example.com/cp/app/manage/add-user-finished"

# Every click that mutates the wizard. AC4 is largely "none of these fired".
MUTATING_CLICKS = ("wildcard_label", "wildcard_future_label", "wildcard_container",
                   "write_label", "next", "update")
SUBMIT_CLICKS = ("next", "update")


# --- a scriptable stand-in for the wizard DOM ---------------------------------------

class _Seq:
    """A value that can be scripted per read: the last entry is sticky, so
    _Seq(["false", "true"]) reads "false" once and "true" forever after."""

    def __init__(self, value):
        self.values = list(value) if isinstance(value, (list, tuple)) else [value]

    def read(self):
        value = self.values[0]
        if len(self.values) > 1:
            self.values.pop(0)
        return value

    def set(self, value):
        self.values = [value]


def _classify(selector):
    """Map a CP selector onto the logical wizard control it addresses.

    Substring matching (not equality) on purpose: the production selectors may
    gain scoping ancestors or a fallback variant without these tests having to
    be rewritten, which is the point of keeping older selectors as fallbacks."""
    if "green-check-icon" in selector:
        return "green_check"
    if "policy-description" in selector:
        return "policy"
    if "dp-name-text" in selector:
        return "dp_name"
    if "dataplane-selector" in selector:
        return "dp_row"
    if "products-container" in selector:
        return "products"
    if "toggle-area" in selector:
        return "toggle"
    if "product-item" in selector:
        return "product"
    if "allDomainsSelected" in selector:
        return "wildcard_input"
    if "allDomainsWriteSelected" in selector:
        return "write_input"
    if "domain-wildcard-selected-checkbox-" in selector:
        return "wildcard_future_label"
    if "wildcard-domains-checkbox" in selector:
        return "wildcard_label" if selector.rstrip().endswith("label") else "wildcard_container"
    if "pl-table__header" in selector:
        return "write_label"
    if "next-assign-permissions" in selector:
        return "next"
    if "assign-permissions-update" in selector:
        return "update"
    if "cancel-assign-permissions" in selector:
        return "cancel"
    if "pl-notification__message" in selector:
        return "notification"
    return "other:" + selector


class _WizardState:
    """The mutable state the fake page reads from, and the click side effects
    the CP component would apply."""

    def __init__(self, *, wildcard="false", write="false", green=8, url=USERS_URL,
                 visible=None, counts=None, enabled=None, settle_error=None,
                 wildcard_click_sets="true", write_click_sets="true",
                 write_click_drops_wildcard=False, update_navigates=True,
                 notification_text=""):
        self.attrs = {"wildcard_input": _Seq(wildcard), "write_input": _Seq(write)}
        self.url = _Seq(url)
        self.counts = {k: _Seq(v) for k, v in
                       {"green_check": green, "cancel": 1, "notification": 0, **(counts or {})}.items()}
        self.visible = {k: _Seq(v) for k, v in (visible or {}).items()}
        self.enabled = {k: _Seq(v) for k, v in (enabled or {}).items()}
        self.settle_error = settle_error
        self.wildcard_click_sets = wildcard_click_sets
        self.write_click_sets = write_click_sets
        self.write_click_drops_wildcard = write_click_drops_wildcard
        self.update_navigates = update_navigates
        self.notification_text = notification_text

    def is_visible(self, key):
        return self.visible[key].read() if key in self.visible else True

    def is_enabled(self, key):
        return self.enabled[key].read() if key in self.enabled else True

    def attribute(self, key, name):
        if name != "aria-checked" or key not in self.attrs:
            return None
        return self.attrs[key].read()

    def count_of(self, key):
        return self.counts[key].read() if key in self.counts else 1

    def text_of(self, key):
        return self.notification_text if key == "notification" else ""

    def on_click(self, key):
        if key in ("wildcard_label", "wildcard_future_label", "wildcard_container"):
            if self.wildcard_click_sets is not None:
                self.attrs["wildcard_input"].set(self.wildcard_click_sets)
                # setWildCardDomains() zeroes read/write on EVERY wildcard click.
                self.attrs["write_input"].set("false")
        elif key == "write_label":
            if self.write_click_sets is not None:
                self.attrs["write_input"].set(self.write_click_sets)
            if self.write_click_drops_wildcard:
                self.attrs["wildcard_input"].set("false")
        elif key == "update" and self.update_navigates:
            # A successful update routes the SPA away and destroys the wizard footer.
            self.url.set(FINISHED_URL)
            self.counts["cancel"] = _Seq(0)


class _FakeLocator:
    def __init__(self, page, key, selector):
        self.page = page
        self.key = key
        self.selector = selector

    @property
    def first(self):
        return self

    def locator(self, selector, **kwargs):
        return self.page._resolve(selector, kwargs)

    def count(self):
        self.page.events.append(("count", self.key))
        return self.page.state.count_of(self.key)

    def click(self):
        self.page.events.append(("click", self.key))
        self.page.state.on_click(self.key)

    def is_visible(self):
        return self.page.state.is_visible(self.key)

    def is_enabled(self):
        self.page.events.append(("is_enabled", self.key))
        return self.page.state.is_enabled(self.key)

    def is_disabled(self):
        return not self.page.state.is_enabled(self.key)

    def get_attribute(self, name, timeout=None):
        # timeout is accepted because Util.check_dom_attribute bounds every read: an
        # unbounded get_attribute() falls back to Playwright's 30s default whenever the
        # locator resolves to nothing, which would blow the helper's wall-clock budget.
        self.page.events.append(("get_attribute", self.key))
        return self.page.state.attribute(self.key, name)

    def inner_text(self):
        return self.page.state.text_of(self.key)

    def hover(self):
        return None

    def wait_for(self, **kwargs):
        return None

    def __repr__(self):
        # Util.check_dom_visibility greps repr() for selector='...' to log it.
        return f"<FakeLocator selector='{self.selector}'>"


class _ExpectResponse:
    def __init__(self, page):
        self.page = page

    def __enter__(self):
        return SimpleNamespace(value=None)

    def __exit__(self, exc_type, exc, tb):
        # Playwright raises when the awaited response never arrives — i.e. AFTER
        # the body (the product click) has already run.
        if exc_type is None and self.page.state.settle_error is not None:
            raise self.page.state.settle_error
        return False


class _FakePage:
    def __init__(self, state):
        self.state = state
        self.events = []
        self.locator_calls = []
        self.response_predicates = []

    @property
    def url(self):
        return self.state.url.read()

    def locator(self, selector, **kwargs):
        self.locator_calls.append((selector, kwargs))
        return self._resolve(selector, kwargs)

    def _resolve(self, selector, kwargs):
        return _FakeLocator(self, _classify(selector), selector)

    def click(self, selector):
        self.locator(selector).click()

    def wait_for_timeout(self, milliseconds):
        return None

    def expect_response(self, predicate, **kwargs):
        self.response_predicates.append(predicate)
        return _ExpectResponse(self)


def _run_grant(state, dp_name="k8s-auto-bmdp1", app_name="BW5"):
    """Drive grant_product_permission against the fake wizard.

    goto_assign_permissions is stubbed (it is pure navigation); everything the
    assertions care about — Util.check_dom_visibility / check_dom_enabled /
    check_dom_attribute — runs for real against the fake DOM."""
    po = object.__new__(PageObjectUserManagement)
    page = _FakePage(state)
    po.page = page
    po.env = ENV
    warnings = []

    def _warn(message, page=None, filename=""):
        warnings.append(message)

    with patch.object(PageObjectUserManagement, "goto_assign_permissions"), \
         patch.object(Util, "warning_screenshot", staticmethod(_warn)), \
         patch("page_object.po_user_management.ReportYaml") as report:
        result = po.grant_product_permission(dp_name, app_name)
    return SimpleNamespace(result=result, page=page, warnings=warnings, report=report,
                           clicked=[key for kind, key in page.events if kind == "click"])


def _assert_no_unexpected_error(run):
    # The whole method sits in a try/except that turns ANY exception into
    # GRANT_FAILED, so a broken harness would otherwise look like a real result.
    assert not [w for w in run.warnings if "Unexpected error" in w], run.warnings


# --- AC4-A: an existing grant is a pure no-op ---------------------------------------

class TestIdempotentNoOp:
    def test_already_granted_returns_already_and_clicks_nothing_mutating(self):
        """Post-settle the wildcard AND Write both read "true": the grant is already
        in place, so the wizard must be left exactly as found. Any click here would
        toggle the live grant off (setWildCardDomains) or re-post the whole
        permission set."""
        run = _run_grant(_WizardState(wildcard="true", write="true"))

        _assert_no_unexpected_error(run)
        assert run.result == GRANT_ALREADY
        for key in MUTATING_CLICKS:
            assert key not in run.clicked, f"{key} must never be clicked for an existing grant"
        # ... and it left the wizard through Cancel, which posts nothing.
        assert "cancel" in run.clicked


# --- AC4-B: fail closed, never submit a wizard that does not read back clean --------

class TestFailClosedGuard:
    def test_pre_update_reread_false_refuses_to_submit(self):
        """The most important guard in the feature. The wildcard converges, then the
        Write click re-renders the domain table and drops it again. The final re-read
        sees wildcard=false, so nothing may be submitted: an Update here would replace
        the user's entire permission set with the half-built wizard."""
        run = _run_grant(_WizardState(write_click_drops_wildcard=True))

        _assert_no_unexpected_error(run)
        assert run.result == GRANT_FAILED
        for key in SUBMIT_CLICKS:
            assert key not in run.clicked, f"{key} must never be clicked once the re-read fails"
        assert any("Refusing to submit" in w for w in run.warnings), run.warnings

    def test_green_check_count_drop_refuses_to_submit(self):
        """Same guard, other trigger: the wizard reads back fully converged, but the
        granted-policy count dropped below the baseline snapshot taken on entry — the
        signature of a wizard that silently lost the user's existing policies."""
        run = _run_grant(_WizardState(green=[8, 7]))

        _assert_no_unexpected_error(run)
        assert run.result == GRANT_FAILED
        for key in SUBMIT_CLICKS:
            assert key not in run.clicked
        assert any("Refusing to submit" in w for w in run.warnings), run.warnings

    def test_baseline_and_final_policy_counts_are_both_read(self):
        """The guard is only real if the count is sampled twice — once before any
        interaction, once immediately before submitting."""
        run = _run_grant(_WizardState())

        counted = [key for kind, key in run.page.events
                   if kind == "count" and key == "green_check"]
        assert len(counted) >= 2


# --- AC4-C: an unsettled wizard is inert --------------------------------------------

class TestUnsettledIsInert:
    def test_no_response_and_no_wildcard_settle_clicks_nothing(self):
        """The resource-instances response never arrives AND the fallback attribute
        poll never sees the wildcard settle. State is unknown, not "not granted":
        aria-checked reads "false" both when there is no grant and when the XHR has
        not landed yet. Clicking on that guess is what corrupts an existing grant, so
        the run must stay inert and fail closed for the caller to retry."""
        run = _run_grant(_WizardState(settle_error=PlaywrightTimeoutError("timeout 30000ms exceeded")))

        assert run.result == GRANT_FAILED
        for key in MUTATING_CLICKS:
            assert key not in run.clicked, f"{key} was clicked on unsettled wizard state"

    def test_a_missing_response_still_settles_on_the_wildcard_itself(self):
        """The fail-closed branch above keys on the POLL, not on the missing response:
        a wizard that renders an existing grant has settled by definition, whatever
        happened to the XHR we were listening for. Losing that would turn every
        response we fail to observe into a failed grant."""
        run = _run_grant(_WizardState(settle_error=PlaywrightTimeoutError("timeout 30000ms exceeded"),
                                      wildcard="true", write="true"))

        _assert_no_unexpected_error(run)
        assert run.result == GRANT_ALREADY
        for key in MUTATING_CLICKS:
            assert key not in run.clicked

    def test_settle_predicate_matches_only_the_resource_instances_get(self):
        """The settle signal is the GET that fills the domain table; it is the only
        caller of that URL on this page, so it is a safe deterministic oracle."""
        run = _run_grant(_WizardState(wildcard="true", write="true"))

        assert run.page.response_predicates, "the product click must be wrapped in a response wait"
        predicate = run.page.response_predicates[0]
        matching = SimpleNamespace(url="https://cp.example.com/api/v1/resource-instances-details?dp=1",
                                   request=SimpleNamespace(method="GET"))
        other = SimpleNamespace(url="https://cp.example.com/api/v1/dataplanes",
                                request=SimpleNamespace(method="GET"))
        assert predicate(matching)
        assert not predicate(other)


# --- AC4-D: the product grant owns no shared idempotency flag -----------------------

class TestNoSharedFlagWrite:
    # Factories, not instances: a _WizardState carries consumed-on-read sequences,
    # so a shared instance would be dirty on a rerun (pytest-rerunfailures is on).
    @pytest.mark.parametrize("make_state", [
        lambda: _WizardState(wildcard="true", write="true"),               # already
        lambda: _WizardState(),                                            # granted
        lambda: _WizardState(write_click_drops_wildcard=True),             # failed
        lambda: _WizardState(visible={"product": False}),                  # skipped
    ], ids=["already", "granted", "failed", "skipped"])
    def test_never_writes_the_user_permission_report_flag(self, make_state):
        """REPORT_USER_PERMISSION means "the base CP/DP policies are in place" and is
        owned by set_user_permission. A per-product grant writing it would make a
        later set_user_permission short-circuit on evidence it never gathered."""
        run = _run_grant(make_state())

        written = [call.args[0] for call in run.report.set.call_args_list if call.args]
        assert ".ENV.REPORT_USER_PERMISSION" not in written, written

    def test_set_user_permission_still_writes_the_flag(self):
        """Companion assertion, so the test above cannot pass by the flag having been
        dropped everywhere."""
        po = object.__new__(PageObjectUserManagement)
        po.page = _FakePage(_WizardState())     # #register-dp-button enabled -> already granted
        po.env = ENV
        with patch.object(PageObjectUserManagement, "goto_left_navbar"), \
             patch("page_object.po_user_management.ReportYaml") as report:
            report.get.return_value = ""
            po.set_user_permission()

        written = [call.args for call in report.set.call_args_list if call.args]
        assert (".ENV.REPORT_USER_PERMISSION", True) in written, written


# --- success has to be proven by the SPA navigating away ----------------------------

class TestSuccessPathNavigation:
    def test_navigation_to_add_user_finished_is_the_success_oracle(self):
        run = _run_grant(_WizardState())

        _assert_no_unexpected_error(run)
        assert run.result == GRANT_DONE
        assert "update" in run.clicked
        # The wizard is gone after a successful update; clicking Cancel there would
        # auto-wait 30s on a detached node and then throw.
        assert "cancel" not in run.clicked

    def test_wizard_still_open_after_the_budget_is_a_failure_not_a_success(self):
        """A denied grant leaves the wizard mounted with a 'not allowed to assign'
        toast and persists nothing. Reporting that as success would let the caller
        march into a capability flow whose product cards are still disabled."""
        run = _run_grant(_WizardState(update_navigates=False,
                                      counts={"notification": 1},
                                      notification_text="You are not allowed to assign this permission"))

        _assert_no_unexpected_error(run)
        assert run.result == GRANT_FAILED
        assert "update" in run.clicked
        assert any("not applied" in w for w in run.warnings), run.warnings


# --- click ORDER: the wildcard invalidates Write, so it can only go first -----------

class TestClickOrder:
    def test_wildcard_is_clicked_before_write_and_write_enablement_is_checked_between(self):
        """setWildCardDomains() unconditionally zeroes allRead/allWrite on every
        wildcard click, and the Write header input stays [disabled] while the
        dataplane has no domains and no wildcard. So: wildcard, then the
        enabled-check, then Write."""
        run = _run_grant(_WizardState())

        order = list(run.page.events)
        wildcard_click = order.index(("click", "wildcard_label"))
        write_enabled_check = order.index(("is_enabled", "write_input"))
        write_click = order.index(("click", "write_label"))
        assert wildcard_click < write_enabled_check < write_click

    def test_write_is_not_clicked_while_its_input_stays_disabled(self):
        """Write is [disabled] until the wildcard is on for a domain-less dataplane;
        clicking a disabled control just burns the Playwright auto-wait budget."""
        run = _run_grant(_WizardState(enabled={"write_input": False}))

        assert "write_label" not in run.clicked
        assert run.result == GRANT_FAILED     # never converged -> never submitted
        for key in SUBMIT_CLICKS:
            assert key not in run.clicked


# --- the zero-domain BMDP: the wildcard label has DIFFERENT text --------------------

class TestZeroDomainWildcardLabel:
    def test_falls_back_to_the_for_attribute_label_when_the_prefix_label_is_absent(self):
        """A freshly created BMDP has zero registered domains, so the CP renders the
        OTHER wildcard label ("All future domains"/"All future agents") — the
        "All current and future" variant only exists once domains are present. Keying
        solely on that text can therefore NEVER match a fresh BMDP. Both variants
        share the for attribute, so that is the fallback."""
        run = _run_grant(_WizardState(counts={"wildcard_label": 0}))

        _assert_no_unexpected_error(run)
        assert "wildcard_future_label" in run.clicked
        assert run.result == GRANT_DONE

    def test_the_text_label_is_attempted_first(self):
        """Order matters for older CPs: the text label stays the primary matcher, the
        for-attribute label is the added fallback, never a replacement."""
        run = _run_grant(_WizardState(counts={"wildcard_label": 0}))

        counted = [key for kind, key in run.page.events
                   if kind == "count" and key in ("wildcard_label", "wildcard_future_label")]
        assert counted[0] == "wildcard_label"
        assert "wildcard_future_label" in counted

    def test_container_click_is_the_last_resort_when_no_label_matches(self):
        """The container owns the real (click) handler and it preventDefault()s, so
        clicking it cannot double-toggle through the label's for-forwarding."""
        run = _run_grant(_WizardState(counts={"wildcard_label": 0, "wildcard_future_label": 0}))

        _assert_no_unexpected_error(run)
        assert "wildcard_container" in run.clicked
        assert run.result == GRANT_DONE


# --- strict mode: "k8s-auto-bmdp1" must not resolve two rows ------------------------

class TestDataplaneMatcherStrictMode:
    def test_dp_name_matcher_is_anchored_and_excludes_a_longer_sibling(self):
        """Locator.click() is strict-mode: a loose has_text also matches
        "k8s-auto-bmdp1" inside "k8s-auto-bmdp10", and two resolved nodes throw."""
        run = _run_grant(_WizardState(wildcard="true", write="true"))

        name_matchers = [kwargs.get("has_text") for selector, kwargs in run.page.locator_calls
                         if "dp-name-text" in selector]
        assert name_matchers, "the dataplane row must be anchored on its name element"
        pattern = name_matchers[0]
        assert hasattr(pattern, "search"), "the primary dp matcher must be a regex, not a bare string"
        assert pattern.search("k8s-auto-bmdp1")
        assert pattern.search("  k8s-auto-bmdp1 ")          # the row text carries whitespace
        assert not pattern.search("k8s-auto-bmdp10")

    def test_loose_name_fallback_still_resolves_on_older_cp_markup(self):
        """The anchored matcher is an ADDITION; the loose one it replaced stays as a
        fallback so a CP whose row text is not exactly the dp name still works."""
        # 2 attempts against the anchored locator, then the loose one resolves.
        run = _run_grant(_WizardState(visible={"dp_row": [False, False, True]},
                                      wildcard="true", write="true"))

        _assert_no_unexpected_error(run)
        assert run.result == GRANT_ALREADY
        loose = [kwargs.get("has_text") for selector, kwargs in run.page.locator_calls
                 if "dp-name-text" in selector and isinstance(kwargs.get("has_text"), str)]
        assert loose == ["k8s-auto-bmdp1"]


# --- the return contract -------------------------------------------------------------

class TestReturnContract:
    def test_the_four_results_are_distinct_and_all_truthy(self):
        """All four are non-empty strings, so `if po.grant_product_permission(...)`
        is ALWAYS true — including for a failure. Callers must compare against the
        constant."""
        results = (GRANT_DONE, GRANT_ALREADY, GRANT_SKIPPED, GRANT_FAILED)
        assert len(set(results)) == 4
        for result in results:
            assert isinstance(result, str)
            assert result, "a falsy result would make `if grant(...)` silently work"

    def test_missing_product_row_is_skipped_not_failed(self):
        """The product is simply not offered by this CP/dataplane. That is a
        configuration fact, not a defect, and must not burn the caller's retry."""
        run = _run_grant(_WizardState(visible={"product": False}))

        assert run.result == GRANT_SKIPPED
        for key in MUTATING_CLICKS:
            assert key not in run.clicked

    def test_missing_dataplane_row_is_skipped_not_failed(self):
        run = _run_grant(_WizardState(visible={"dp_row": False}))

        assert run.result == GRANT_SKIPPED
        for key in MUTATING_CLICKS:
            assert key not in run.clicked

    def test_product_permission_absent_from_this_cp_is_skipped(self):
        """An older CP does not offer the 'Product Permission' policy at all."""
        run = _run_grant(_WizardState(visible={"policy": False}))

        assert run.result == GRANT_SKIPPED
        for key in MUTATING_CLICKS:
            assert key not in run.clicked

    @pytest.mark.parametrize("make_state,expected", [
        (lambda: _WizardState(wildcard="true", write="true"), GRANT_ALREADY),
        (lambda: _WizardState(), GRANT_DONE),
        (lambda: _WizardState(write_click_drops_wildcard=True), GRANT_FAILED),
        (lambda: _WizardState(visible={"product": False}), GRANT_SKIPPED),
        (lambda: _WizardState(settle_error=PlaywrightTimeoutError("timeout")), GRANT_FAILED),
    ], ids=["already", "granted", "guard", "skipped", "unsettled"])
    def test_every_path_returns_one_of_the_four_constants(self, make_state, expected):
        run = _run_grant(make_state())
        assert run.result in (GRANT_DONE, GRANT_ALREADY, GRANT_SKIPPED, GRANT_FAILED)
        assert run.result == expected

    def test_an_unexpected_error_is_reported_as_failed_not_raised(self):
        """The wizard runs inside best-effort callers; a page that blows up must not
        take the install task with it."""
        po = object.__new__(PageObjectUserManagement)
        po.page = _FakePage(_WizardState())
        po.env = ENV
        warnings = []
        with patch.object(PageObjectUserManagement, "goto_assign_permissions",
                          side_effect=RuntimeError("navigation exploded")), \
             patch.object(Util, "warning_screenshot",
                          staticmethod(lambda message, page=None, filename="": warnings.append(message))), \
             patch("page_object.po_user_management.ReportYaml"):
            assert po.grant_product_permission("k8s-auto-bmdp1", "BW5") == GRANT_FAILED
        assert any("navigation exploded" in w for w in warnings), warnings


# --- AC3 is satisfied by Write alone --------------------------------------------------

class TestReadIsImpliedByWrite:
    def test_no_separate_read_click_is_issued(self):
        """allReadPermissionsSelected FOLLOWS allWritePermissionsSelected in the CP
        component, and the Read input is [disabled] while Write is on. A separate
        Read click would either no-op or fight the component."""
        run = _run_grant(_WizardState())

        read_locators = [selector for selector, kwargs in run.page.locator_calls
                         if kwargs.get("has_text") == "Read"]
        assert not read_locators, read_locators
        assert "write_label" in run.clicked
