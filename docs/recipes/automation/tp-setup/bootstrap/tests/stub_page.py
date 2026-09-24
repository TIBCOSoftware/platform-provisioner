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
# A minimal Playwright-shaped stub page, so page objects can be tested on the branch they
# TAKE rather than on the text their source contains (PCP-23946 item 4).
#
# A source grep like `assert "EITHER_WIZARD).first" in src` passes for any code that merely
# mentions the string and fails for a behaviour-preserving rename; a selector that is
# well-formed, scoped, id-free and simply WRONG satisfies it. These stubs answer the only
# question that matters at a branch point: given this DOM, which path did the code take?
#
# Deliberately small. It models just the locator surface the page objects use - visibility,
# clicks, fills, waits, counts - and everything is visible by default so a test states only
# the DOM facts it cares about.

import re


class StubLocator:
    """One locator. `key` is "<selector>|<has_text>", which is what rules match on."""

    def __init__(self, page, selector, has_text=None):
        self.page = page
        self.selector = selector
        self.has_text = has_text
        self.filters = []

    @property
    def key(self):
        return f"{self.selector}|{self.has_text if self.has_text is not None else ''}"

    # Playwright returns a locator from .first/.nth(); narrowing does not change visibility
    # here, but `first_used` records that the caller narrowed - which is what protects an
    # is_visible() call from a strict-mode violation on a multi-match selector.
    @property
    def first(self):
        self.page.first_used.add(self.selector)
        return self

    def nth(self, _i):
        self.page.first_used.add(self.selector)
        return self

    def or_(self, other):
        return OrLocator(self.page, self, other)

    def locator(self, selector, **kwargs):
        return StubLocator(self.page, f"{self.selector} {selector}", kwargs.get("has_text"))

    def filter(self, has=None, has_text=None):
        """Playwright's locator.filter(). COARSE ON PURPOSE: it narrows nothing here.

        This stub keys everything off a selector STRING, so it cannot evaluate a
        `has=`/`has_text=` predicate against real DOM text. Modelling it as a no-op keeps
        the filtered locator answering count()/is_visible() from its parent selector,
        which is what the flow-level tests in this suite actually care about (was the
        legacy path taken, did the Next click happen).

        It deliberately does NOT try to model WHICH row a filter selects — that property
        belongs to tests/test_po_dp_ems_storage_resource_name.py, whose purpose-built
        stubs evaluate the real regex against real row text. Do not add matching logic
        here to make a selection assertion pass; put the assertion in that file instead,
        or this stub will start quietly disagreeing with Playwright.

        It DOES record the inner locator's SELECTOR alongside its text. Recording only
        the text made `has=locator("td:first-child", …)` and `has=locator("td", …)`
        indistinguishable, so a test asserting "the name is matched on the first CELL"
        passed for code that matched the whole row — proven in review on PCP-24348 by
        swapping the two and watching every test stay green.

        Every entry is the SAME shape, `(selector_or_None, text_or_pattern)`, so a caller
        can destructure unconditionally. A `has=` filter recording a tuple while a plain
        `has_text=` recorded a bare string forced readers to type-switch, and the failure
        mode when they forgot was a confusing unpack error inside a test.
        """
        if has is not None:
            self.filters.append((has.selector, getattr(has, "has_text", None)))
        else:
            self.filters.append((None, has_text))
        return self

    def count(self):
        return self.page.counts.get(self.selector, 0)

    def inner_text(self):
        return self.page.texts.get(self.selector, "")

    def all_inner_texts(self):
        return self.page.all_inner_texts.get(self.selector, [])

    def is_visible(self):
        matches = self.page.match_count(self)
        if matches > 1 and self.selector not in self.page.first_used:
            # What Playwright really does, and the whole point of item 3.
            raise StrictModeViolation(
                f"strict mode violation: {self.selector!r} resolved to {matches} elements")
        return self.page.is_visible(self)

    def click(self, **_kwargs):
        if not self.page.is_visible(self):
            raise StubTimeout(f"click on a locator that matches nothing: {self.key}")
        self.page.clicks.append(self.key)

    def check(self, **_kwargs):
        self.page.checked.append(self.key)

    def hover(self, **_kwargs):
        # Through _require_match, so hover is strict like fill/clear: Playwright's hover
        # resolves to exactly one element, and a loose check here would let a test pass where
        # the real hover throws a strict-mode violation.
        self._require_match("hover")
        self.page.hovers.append(self.key)

    def fill(self, value, **_kwargs):
        self._require_match("fill")
        self.page.fills[self.key] = value

    def clear(self, **_kwargs):
        self._require_match("clear")
        self.page.fills[self.key] = ""

    def _require_match(self, action):
        """fill()/clear() wait for an ACTIONABLE element, so on a zero-match locator they burn
        the 30s default and raise - they do not quietly do nothing. Modelling that is the whole
        difference between reproducing PCP-24228 and papering over it: with a permissive fill,
        a test on the broken `input.title-input` selector would have passed.

        Routed through the locator's own is_visible() so it is STRICT the way Playwright's
        fill() is: going through page.is_visible() instead would skip the multi-match check,
        and dropping a `.first` from a fill call site would then be an undetectable regression.
        """
        if not self.is_visible():
            raise StubTimeout(f"{action} on a locator that matches nothing: {self.key}")

    def wait_for(self, **kwargs):
        state = kwargs.get("state", "visible")
        if self.page.wait_for_raises.get((self.selector, state)):
            raise StubTimeout(f"wait_for({state}) timed out on {self.selector}")
        self.page.waits.append((self.selector, state))


class OrLocator(StubLocator):
    """Playwright's locator.or_(): matches the UNION of both sides.

    The union is what strict mode is evaluated against, and `.first` narrows the whole
    thing - not either side individually. Getting that wrong made `.first` a no-op here:
    with an inert `first` and an is_visible() that skipped the strict check, deleting
    `.first` from the o11y gate left every behavioural test passing. Caught in review.

    KNOWN DIVERGENCE: real `.or_(...).first` resolves to the DOM-FIRST element of the union and
    reports that element's visibility; this stub has no DOM order, so it reports "either side is
    visible". The two differ only when both markups are present at once and the earlier one is
    hidden - a transitional CP shipping fresco AND legacy together. Do not read a pass here as
    proof of behaviour in that case.
    """

    def __init__(self, page, left, right):
        super().__init__(page, f"{left.selector} OR {right.selector}")
        self.left, self.right = left, right

    @property
    def first(self):
        self.page.first_used.add(self.selector)
        return self

    def _union_count(self):
        return self.page.match_count(self.left) + self.page.match_count(self.right)

    def is_visible(self):
        matches = self._union_count()
        if matches > 1 and self.selector not in self.page.first_used:
            raise StrictModeViolation(
                f"strict mode violation: or_({self.left.selector!r}, "
                f"{self.right.selector!r}) resolved to {matches} elements")
        # Read the sides directly: strict mode was already evaluated on the union above,
        # and Playwright does not re-apply it per side.
        return self.page.is_visible(self.left) or self.page.is_visible(self.right)

    def click(self, **kwargs):
        (self.left if self.page.is_visible(self.left) else self.right).click(**kwargs)


class StubKeyboard:
    """page.keyboard. Records presses; the page objects use it to dismiss overlays."""

    def __init__(self, page):
        self.page = page

    def press(self, key):
        self.page.key_presses.append(key)

    def insert_text(self, text):
        self.page.inserted_text.append(text)


class StrictModeViolation(Exception):
    pass


class StubTimeout(Exception):
    pass


class StubPage:
    """A Playwright-shaped page whose DOM is described by visibility rules.

    Everything is visible unless a rule says otherwise, so a test declares only what it
    is actually about:

        page = StubPage()
        page.hide(".fresco-wizard-modal-container")   # legacy CP
    """

    url = "https://stub/"

    def __init__(self):
        self.rules = []          # [(compiled_pattern, visible)] - first match wins
        self.counts = {}         # selector -> number of matching elements
        self.texts = {}          # selector -> inner_text(), for log-line assertions
        self.wait_for_raises = {}  # (selector, state) -> True to time out
        self.clicks = []
        self.checked = []
        self.hovers = []
        self.fills = {}
        self.waits = []
        self.first_used = set()
        self.reloads = 0
        self.default_visible = True
        self.key_presses = []
        self.inserted_text = []
        self.all_inner_texts = {}   # selector -> list of row texts, for dropdown reads
        self.keyboard = StubKeyboard(self)

    # --- DOM description -------------------------------------------------------------

    def hide(self, pattern):
        self.rules.append((re.compile(re.escape(pattern)), False))
        return self

    def show(self, pattern):
        self.rules.append((re.compile(re.escape(pattern)), True))
        return self

    def hide_all_but(self, *patterns):
        for p in patterns:
            self.show(p)
        self.default_visible = False
        return self

    def set_count(self, selector, n):
        self.counts[selector] = n
        return self

    def time_out_wait_for(self, selector, state="detached"):
        self.wait_for_raises[(selector, state)] = True
        return self

    # --- queries used by StubLocator --------------------------------------------------

    def match_count(self, locator):
        if locator.selector in self.counts:
            return self.counts[locator.selector]
        return sum(1 for k in self._keys(locator) if self._visible_key(k))

    def is_visible(self, locator):
        # A ZERO count wins: set_count(sel, 0) means the selector resolves to NOTHING, and
        # nothing cannot be visible. Reading only the visibility rules here made match_count()
        # and is_visible() disagree, so a zero-count selector still answered "visible" and the
        # stub's own zero-match model did not hold for the one query that matters.
        # A non-zero count does NOT force visible, though: counts model HOW MANY nodes match,
        # hide()/show() model whether they are shown, and letting the former override the latter
        # would silently undo an explicit hide() in any test that also set a count.
        if self.counts.get(locator.selector) == 0:
            return False
        # A comma selector matches EITHER side, so it is visible when any part is - the same
        # rule Playwright applies, and the reason such a locator needs .first before
        # is_visible(). Modelling it as one opaque string would let `hide(".resources-content")`
        # silently hide `".fresco-…, .resources-content"` too.
        return any(self._visible_key(k) for k in self._keys(locator))

    def _keys(self, locator):
        has_text = locator.has_text if locator.has_text is not None else ""
        return [f"{part.strip()}|{has_text}" for part in locator.selector.split(",")]

    def _visible_key(self, key):
        for pattern, visible in self.rules:
            if pattern.search(key):
                return visible
        return self.default_visible

    # --- Playwright page surface ------------------------------------------------------

    def locator(self, selector, **kwargs):
        return StubLocator(self, selector, kwargs.get("has_text"))

    def get_by_text(self, text, **_kwargs):
        return StubLocator(self, f"text={text}")

    def fill(self, selector, value, **_kwargs):
        self.fills[f"{selector}|"] = value

    def wait_for_timeout(self, _ms):
        pass

    def wait_for_load_state(self, *_a, **_k):
        pass

    def reload(self, *_a, **_k):
        self.reloads += 1

    def content(self):
        return ""

    def clicked(self, fragment):
        """Did any click land on a key containing this fragment?"""
        return any(fragment in c for c in self.clicks)
