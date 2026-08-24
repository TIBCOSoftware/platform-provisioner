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
# Tests for Util.check_dom_attribute — the attribute-polling sibling of
# check_dom_visibility / check_dom_enabled, added for the Assign Permissions
# wizard.
#
# Why an attribute poll at all: the wildcard-domains checkbox publishes its
# state through aria-checked, but the CP component pre-seeds that attribute to
# "false" and only writes the real value inside the resource-instances XHR
# callback. The attribute is therefore PRESENT and WRONG for a short window, so
# a zero-wait get_attribute() reads stale state and makes the caller click a
# checkbox that was already ticked — which toggles an existing grant OFF.
#
# Three properties are load-bearing for that caller and pinned here:
#   1. the FIRST read happens immediately (no leading blind sleep, unlike
#      check_dom_visibility) — the caller has already settled on the XHR, so a
#      blind wait is pure cost on every install task;
#   2. it is bounded and returns False rather than hanging;
#   3. it never raises, so the caller's fail-closed branch (not an exception
#      handler) is what decides.

import inspect
from unittest.mock import MagicMock

from utils.util import Util


def _page_and_locator(attribute_value):
    """A page whose wait_for_timeout is observable, plus a locator whose
    get_attribute is driven by `attribute_value` (a value or a side_effect)."""
    page = MagicMock()
    locator = MagicMock()
    if isinstance(attribute_value, (list, tuple)) or callable(attribute_value) or isinstance(attribute_value, BaseException):
        locator.get_attribute.side_effect = attribute_value
    else:
        locator.get_attribute.return_value = attribute_value
    return page, locator


class TestSignature:
    def test_is_a_staticmethod_with_the_agreed_defaults(self):
        # The caller relies on the short default budget (a settled wizard answers
        # immediately; an unsettled one must not stall the whole install).
        assert isinstance(inspect.getattr_static(Util, "check_dom_attribute"), staticmethod)
        params = inspect.signature(Util.check_dom_attribute).parameters
        assert list(params) == ["page", "dom_selector", "attribute", "expected", "interval", "max_wait"]
        assert params["interval"].default == 1
        assert params["max_wait"].default == 6


class TestImmediateFirstRead:
    def test_returns_true_on_immediate_match_without_sleeping_first(self):
        page, locator = _page_and_locator("true")

        assert Util.check_dom_attribute(page, locator, "aria-checked", "true") is True

        # The read is bounded by the poll interval: unbounded, get_attribute() falls back
        # to Playwright's 30s default whenever the locator resolves to nothing, so a
        # missing element would blow max_wait many times over instead of failing fast.
        locator.get_attribute.assert_called_once_with("aria-checked", timeout=1000)
        # The deliberate deviation from check_dom_visibility: no leading blind wait.
        page.wait_for_timeout.assert_not_called()

    def test_reads_once_even_when_max_wait_is_shorter_than_interval(self):
        # max_wait // interval == 0; the "always read at least once" floor keeps the
        # helper usable for callers that pass a very short budget.
        page, locator = _page_and_locator("true")

        assert Util.check_dom_attribute(page, locator, "aria-checked", "true", 10, 6) is True

        assert locator.get_attribute.call_count == 1
        page.wait_for_timeout.assert_not_called()


class TestPolling:
    def test_returns_true_once_the_attribute_flips(self):
        # The real race: aria-checked is "false" until the XHR callback lands.
        page, locator = _page_and_locator(["false", "false", "true"])

        assert Util.check_dom_attribute(page, locator, "aria-checked", "true", 1, 6) is True

        assert locator.get_attribute.call_count == 3
        assert page.wait_for_timeout.call_count == 2  # one sleep between each retry

    def test_returns_false_after_max_wait(self):
        page, locator = _page_and_locator("false")

        assert Util.check_dom_attribute(page, locator, "aria-checked", "true", 1, 6) is False

        assert locator.get_attribute.call_count == 6            # max_wait // interval
        assert page.wait_for_timeout.call_count == 5            # no sleep after the final read

    def test_max_wait_is_an_upper_bound_not_a_truncated_multiple(self):
        """A floor division would silently shorten the budget whenever max_wait is
        not an exact multiple of interval (4/6 -> a single read), so the caller would
        get far less patience than it asked for. Round up instead."""
        page, locator = _page_and_locator("false")

        assert Util.check_dom_attribute(page, locator, "aria-checked", "true", 4, 6) is False

        assert locator.get_attribute.call_count == 2

    def test_a_zero_interval_does_not_raise(self):
        """The helper's entire contract is that it never raises - callers use it to
        stay inert rather than to fail. A floor-divide by a caller-supplied 0 would
        break that with a ZeroDivisionError before a single read happened."""
        page, locator = _page_and_locator("true")

        assert Util.check_dom_attribute(page, locator, "aria-checked", "true", 0, 6) is True

    def test_a_torn_down_page_stops_the_poll_instead_of_raising(self):
        """wait_for_timeout raises once the page/context is gone. That must end the
        poll with a False, not propagate - the sleep sits outside the get_attribute
        try block, so it was the one unguarded call left in a "never raises" helper."""
        page, locator = _page_and_locator("false")
        page.wait_for_timeout.side_effect = RuntimeError("Target page closed")

        assert Util.check_dom_attribute(page, locator, "aria-checked", "true", 1, 6) is False

        assert locator.get_attribute.call_count == 1            # stopped at the first sleep

    def test_missing_attribute_is_not_a_match(self):
        # get_attribute returns None for an absent attribute; that must poll out to
        # False rather than compare equal to anything.
        page, locator = _page_and_locator(None)

        assert Util.check_dom_attribute(page, locator, "aria-checked", "true", 1, 3) is False


class TestNeverRaises:
    def test_swallows_get_attribute_errors_and_returns_false(self):
        # A locator that resolves to no element (transient *ngIf detach while the
        # wizard re-renders) makes get_attribute RAISE. The caller's fail-closed
        # guard must be the thing that decides, so this stays a boolean.
        page, locator = _page_and_locator(Exception("locator resolved to no element"))

        assert Util.check_dom_attribute(page, locator, "aria-checked", "true", 1, 3) is False

    def test_recovers_when_the_element_reattaches_mid_poll(self):
        page, locator = _page_and_locator([Exception("not resolvable yet"), "true"])

        assert Util.check_dom_attribute(page, locator, "aria-checked", "true", 1, 3) is True
