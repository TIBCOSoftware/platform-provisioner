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
# PCP-23953 — which storage resource the fresco EMS wizard picks.
#
# The Data Plane's storage resource does not have one fixed name: CLI mode creates
# '<dp_name>-storage' (cli_object/orchestrator.py) while GUI mode names it after the
# Kubernetes StorageClass, ENV.TP_AUTO_STORAGE_CLASS ('nfs',
# po_dp_config.dp_config_resources_storage). The fresco wizard was driven with the GUI name
# only, so every TP_AUTO_USE_CLI=true deploy failed EMS provisioning deterministically:
#   'nfs' is not available in EMS 'Message Storage'
# while the row actually rendered was 'k8s-auto-dp1-storage (da94beb9ds6g00dusrg0)'.
#
# These are BEHAVIOUR tests, not source-text assertions: a stub stands in for the wizard's
# resource list, so they pin what the page object SELECTS for a given DOM. The sibling
# tests/test_po_dp_ems.py keeps the selector-shape contracts.

from types import SimpleNamespace

import pytest

from page_object import po_dataplane
from page_object.po_dataplane import PageObjectDataPlane
from page_object.po_dp_activespace import PageObjectDataPlaneActiveSpaces
from page_object.po_dp_ems import PageObjectDataPlaneEMS
from utils import naming
from utils.naming import storage_resource_candidates
from utils.util import Util

DP_NAME = "k8s-auto-dp1"
STORAGE_CLASS = "nfs"
SECTION = "Message Storage"


class _ExitError(Exception):
    """Stands in for Util.exit_error's sys.exit(1), so a test can assert on it."""


class _Radio:
    def __init__(self, row_text, checked):
        self._row_text = row_text
        self._checked = checked

    def check(self, force=False):
        self._checked.append((self._row_text, force))


class _Row:
    """The `.first` of a filtered row list — Playwright's .first counts 0 or 1."""

    def __init__(self, text, checked):
        self.text = text
        self._checked = checked

    def count(self):
        return 1 if self.text is not None else 0

    def inner_text(self):
        return self.text

    def locator(self, selector):
        assert selector == "input.p-radiobutton-input", selector
        return _Radio(self.text, self._checked)


class _Rows:
    def __init__(self, texts, checked):
        self._texts = texts
        self._checked = checked

    def filter(self, has=None, has_text=None):
        # Playwright matches the element's full textContent after WHITESPACE NORMALIZATION,
        # so normalize here too — a '^'-anchored pattern is exactly the kind most sensitive
        # to the difference, and a stub that skipped this would flatter the code under test.
        texts = self._texts if has_text is None else [
            t for t in self._texts if has_text.search(" ".join(t.split()))]
        return _Rows(texts, self._checked)

    def count(self):
        return len(self._texts)

    @property
    def first(self):
        return _Row(self._texts[0] if self._texts else None, self._checked)


class _Section:
    def __init__(self, texts, checked):
        self._texts = texts
        self._checked = checked

    def locator(self, selector):
        assert selector == "li.resources-section__item", selector
        return _Rows(self._texts, self._checked)


class _Sections:
    def __init__(self, sections, checked):
        self._sections = sections
        self._checked = checked

    def filter(self, has=None, has_text=None):
        # The page object scopes by heading: .filter(has=locator("h3...", has_text=title))
        return _Section(self._sections.get(has.has_text, []), self._checked)


class _StubPage:
    """Just enough of the resources widget for fresco_resource_row() to resolve against."""

    def __init__(self, sections):
        self._sections = sections
        self.checked = []

    def locator(self, selector, has_text=None):
        if selector == "section.resources-section":
            return _Sections(self._sections, self.checked)
        if selector == "h3.resources-section__title":
            return SimpleNamespace(has_text=has_text)
        raise AssertionError(f"unexpected selector: {selector}")


@pytest.fixture(autouse=True)
def _stub_env_and_util(monkeypatch):
    # ENV is a frozen dataclass instance, so replace the module reference rather than the attr.
    # storage_resource_candidates() lives in utils/naming.py since PCP-24380 (it was on
    # PageObjectDataPlane before), so utils.naming is what to patch - patching po_dataplane
    # would silently stop pinning the storage class and let the ambient cluster value decide.
    monkeypatch.setattr(naming, "ENV", SimpleNamespace(TP_AUTO_STORAGE_CLASS=STORAGE_CLASS))

    # check_dom_visibility would otherwise sleep on the real Playwright clock.
    monkeypatch.setattr(Util, "check_dom_visibility",
                        staticmethod(lambda page, locator, *_a, **_kw: locator.count() > 0))

    warnings = []
    monkeypatch.setattr(Util, "warning_screenshot",
                        staticmethod(lambda message, page=None, filename="": warnings.append(message)))

    def _exit_error(message, page=None, filename=""):
        raise _ExitError(message)

    monkeypatch.setattr(Util, "exit_error", staticmethod(_exit_error))
    return warnings


def _select(sections, section_title=SECTION, is_required=True):
    page = _StubPage(sections)
    PageObjectDataPlaneEMS(page).fresco_select_resource(section_title, DP_NAME, is_required)
    return page.checked


class TestStorageResourceNameResolution:
    def test_the_gui_name_alone_never_matches_a_cli_named_resource(self):
        # The defect itself, isolated: looking up ONLY ENV.TP_AUTO_STORAGE_CLASS — what the
        # wizard used to do — finds nothing against a CLI-provisioned Data Plane, which is
        # why 'nfs is not available in EMS Message Storage' was reached every single run.
        # Anchoring the fix on this keeps a future "simplify it back to one name" honest.
        page = _StubPage({SECTION: [f"{DP_NAME}-storage (da94beb9ds6g00dusrg0)"]})
        assert PageObjectDataPlaneEMS(page).fresco_resource_row(SECTION, [STORAGE_CLASS]).count() == 0

    def test_cli_named_resource_is_selected(self):
        # The PCP-23953 regression: CLI mode's '<dp>-storage' used to match nothing at all.
        checked = _select({SECTION: [f"{DP_NAME}-storage (da94beb9ds6g00dusrg0)"]})
        assert checked == [(f"{DP_NAME}-storage (da94beb9ds6g00dusrg0)", True)]

    def test_gui_named_resource_is_still_selected(self):
        # GUI mode names the resource after the StorageClass; that path must not regress.
        checked = _select({SECTION: [f"{STORAGE_CLASS} (abc123)"]})
        assert checked == [(f"{STORAGE_CLASS} (abc123)", True)]

    def test_dp_named_resource_wins_when_both_are_offered(self):
        checked = _select({SECTION: [f"{STORAGE_CLASS} (abc123)", f"{DP_NAME}-storage (def456)"]})
        assert checked == [(f"{DP_NAME}-storage (def456)", True)]

    def test_a_longer_dp_name_is_not_matched(self):
        # has_text is a substring match, so 'k8s-auto-dp1' would otherwise also hit
        # 'k8s-auto-dp10-storage'. The name must be followed by ' (' to count.
        checked = _select({SECTION: ["k8s-auto-dp10-storage (def456)", f"{STORAGE_CLASS} (abc123)"]})
        assert checked == [(f"{STORAGE_CLASS} (abc123)", True)]

    def test_radio_is_force_checked(self):
        # PrimeNG renders the real <input> as a transparent overlay; a plain check() hangs.
        checked = _select({SECTION: [f"{DP_NAME}-storage (def456)"]})
        assert checked[0][1] is True


class TestDegradation:
    """What to do when NO known naming convention matched.

    Cross-review pushed back hard on the first cut, which degraded to "click the first row"
    in every such case. Two of that behaviour's three branches were wrong: with several
    unrecognised rows it binds EMS to a resource nobody chose, and on the OPTIONAL section
    "leave it unset" is strictly safer than "guess". Only the single-row case is genuinely
    unambiguous, and that is the one the degradation exists for.
    """

    def test_one_unrecognised_row_is_selected(self, _stub_env_and_util):
        # No ambiguity: the section offers exactly one resource, so a naming change must
        # not fail the deploy.
        checked = _select({SECTION: ["renamed-storage-thing (def456)"]})
        assert checked == [("renamed-storage-thing (def456)", True)]
        assert any("exactly one resource" in w for w in _stub_env_and_util)

    def test_several_unrecognised_rows_do_NOT_get_a_coin_flip(self):
        # Picking arbitrarily here binds EMS to a storage resource nobody chose, and that
        # surfaces much later and far more confusingly than an error naming what was on
        # screen. Required section => fail, and say how many were offered.
        with pytest.raises(_ExitError, match="no safe one to pick"):
            _select({SECTION: ["mystery-a (id1)", "mystery-b (id2)"]})

    def test_several_unrecognised_rows_leave_an_OPTIONAL_section_unset(self, _stub_env_and_util):
        checked = _select({"Log Storage": ["mystery-a (id1)", "mystery-b (id2)"]},
                          section_title="Log Storage", is_required=False)
        assert checked == [], "an optional section must be left unset, not bound to a guess"
        assert any("leaving it unset" in w for w in _stub_env_and_util)

    def test_required_section_with_no_resource_at_all_exits(self):
        with pytest.raises(_ExitError, match="No storage resource is available"):
            _select({SECTION: []})

    def test_optional_section_with_no_resource_only_warns(self, _stub_env_and_util):
        checked = _select({"Log Storage": []}, section_title="Log Storage", is_required=False)
        assert checked == []
        assert any("No storage resource is available" in w for w in _stub_env_and_util)


class TestVisibilityDoesNotOverrideThePresentRow:
    """The poll buys time; count() decides which row to click.

    An earlier cut gated the candidate resolution on check_dom_visibility, so a candidate
    row that was in the DOM but not yet is_visible() (mid fade-in, collapsed section, a
    zero-box parent) fell into the degradation branch and clicked a DIFFERENT resource —
    a wrong-config selection reported as a warning. No test could catch that while the
    fixture defined visibility AS presence, so these drive the real distinction.
    """

    def test_an_invisible_but_present_candidate_row_is_still_the_one_clicked(self, monkeypatch):
        monkeypatch.setattr(Util, "check_dom_visibility",
                            staticmethod(lambda *_a, **_kw: False))  # never becomes visible
        checked = _select({SECTION: [f"{STORAGE_CLASS} (abc123)", f"{DP_NAME}-storage (def456)"]})
        assert checked == [(f"{DP_NAME}-storage (def456)", True)], (
            "a failed visibility poll must not demote the correct row to the fallback")

    def test_the_same_holds_on_the_legacy_table(self, monkeypatch):
        monkeypatch.setattr(Util, "check_dom_visibility",
                            staticmethod(lambda *_a, **_kw: False))
        page = _LegacyStubPage([STORAGE_CLASS, f"{DP_NAME}-storage"])
        PageObjectDataPlaneEMS(page).legacy_select_storage(TABLE, SECTION, DP_NAME, True)
        assert page.clicked == [f"{DP_NAME}-storage"]


class TestCandidateOrder:
    def test_candidates_prefer_the_dataplane_named_resource(self):
        candidates = storage_resource_candidates(DP_NAME)
        assert candidates == [f"{DP_NAME}-storage", STORAGE_CLASS]

    def test_blank_storage_class_is_not_offered_as_a_candidate(self, monkeypatch):
        # An empty StorageClass would compile to '^(?:...|\s*\()' and match every row.
        monkeypatch.setattr(naming, "ENV", SimpleNamespace(TP_AUTO_STORAGE_CLASS=""))
        assert storage_resource_candidates(DP_NAME) == [f"{DP_NAME}-storage"]

    def test_every_candidate_is_anchored_on_its_opening_parenthesis(self):
        # One union regex is used for the visibility poll, so EACH alternative — not just the
        # first — has to carry the ' (' anchor, or the union re-opens the substring hole.
        rows = {SECTION: ["nfs-extra (id1)", "a-storage-legacy (id2)", "nfs (id3)"]}
        page = _StubPage(rows)
        row = PageObjectDataPlaneEMS(page).fresco_resource_row(SECTION, ["a-storage", "nfs"])
        assert row.text == "nfs (id3)", "an anchored union must skip 'nfs-extra' and 'a-storage-legacy'"

    def test_no_names_matches_any_row_the_section_offers(self):
        page = _StubPage({SECTION: ["renamed-storage-thing (id1)"]})
        row = PageObjectDataPlaneEMS(page).fresco_resource_row(SECTION)
        assert row.text == "renamed-storage-thing (id1)"


class TestTheFallbackNamesWhatItBound(object):
    """The fallback used to log `Selected 'first available'`.

    That made the ONE case where the resource name matters most — the case where nobody
    chose it — the vaguest line in the run, for a fix whose whole thesis is "the error was
    lying". Nothing pinned this line, which is how it drifted.
    """

    def test_fresco_fallback_logs_the_resource_it_actually_bound(self, capsys):
        _select({SECTION: ["renamed-storage-thing (def456)"]})
        assert "Selected 'renamed-storage-thing' Message Storage" in capsys.readouterr().out

    def test_legacy_fallback_logs_the_resource_it_actually_bound(self, capsys):
        page = _LegacyStubPage(["renamed-storage-thing"])
        PageObjectDataPlaneEMS(page).legacy_select_storage(TABLE, SECTION, DP_NAME, is_required=True)
        assert "Selected 'renamed-storage-thing' Message Storage" in capsys.readouterr().out

    def test_a_direct_match_still_logs_the_candidate_name(self, capsys):
        _select({SECTION: [f"{DP_NAME}-storage (def456)"]})
        assert f"Selected '{DP_NAME}-storage' Message Storage" in capsys.readouterr().out

    def test_naming_the_row_can_never_fail_the_step(self):
        # A logging aid must not be able to break the provisioning it describes.
        class _Exploding:
            def inner_text(self):
                raise RuntimeError("detached")
        assert PageObjectDataPlaneEMS(None).storage_row_name(_Exploding()) == "first available"


class TestTheConventionHasOneOwner:
    """This defect WAS two copies of one fact, and only one of them was right.

    po_dp_activespace already tried both naming conventions; the EMS wizard knew only the
    GUI one. Keeping the list in ONE place is the part of the fix that stops the next
    capability wizard from repeating it — same reasoning as wait_for_overlay_to_clear.

    That one place moved in PCP-24380, from PageObjectDataPlane down to utils/naming.py,
    because the CLI EMS arm has to ask the same question and cli_object cannot import a
    page object without importing Playwright with it. The guard therefore has to say
    "nobody redefines it" AND "it is reachable without a browser" — the second half is
    the new one, and it is the one that would let the list get copied back up.
    """

    def test_the_candidate_list_lives_in_the_shared_naming_module(self):
        assert callable(naming.storage_resource_candidates)

    @pytest.mark.parametrize("page_object_class",
                             [PageObjectDataPlane, PageObjectDataPlaneEMS,
                              PageObjectDataPlaneActiveSpaces])
    def test_no_page_object_keeps_its_own_copy(self, page_object_class):
        assert "storage_resource_candidates" not in vars(page_object_class), (
            f"{page_object_class.__name__} must call utils.naming, not keep its own copy")

    @pytest.mark.parametrize("module", ["page_object.po_dp_ems", "page_object.po_dp_activespace"])
    def test_both_wizards_call_the_shared_function(self, module):
        """Not `self.storage_resource_candidates(...)`. An inherited-method call would
        still work today — nothing stops someone re-adding the method to the base — and
        would look identical at every call site, which is how the two copies diverged in
        the first place."""
        import importlib
        import inspect

        source = inspect.getsource(importlib.import_module(module))
        assert "self.storage_resource_candidates(" not in source, (
            f"{module} must call utils.naming.storage_resource_candidates() directly")
        assert "storage_resource_candidates(dp_name)" in source, (
            f"{module} no longer resolves the candidate list at all")

    def test_the_shared_module_pulls_in_no_browser(self):
        """The whole reason for the move. utils/naming.py must stay importable from
        cli_object, which means it must not (transitively) import Playwright — so it
        cannot grow a `from utils.util import Util` for convenience later."""
        import ast
        from pathlib import Path

        source = Path(naming.__file__).read_text(encoding="utf-8")
        imported = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)

        offenders = sorted(m for m in imported
                           if m.split(".")[0] in {"playwright", "page_object"}
                           or m == "utils.util")
        assert not offenders, (
            "utils/naming.py must stay browser-free so cli_object can import it; "
            f"these imports break that: {offenders}")


TABLE = "#message-storage-resource-table"


class _Labels:
    def __init__(self, texts, clicked):
        self._texts = texts
        self._clicked = clicked

    def count(self):
        return len(self._texts)

    @property
    def first(self):
        return SimpleNamespace(click=lambda: self._clicked.append(self._texts[0]))


class _LegacyRows:
    """The legacy wizard's <tr> list. The real rendering is UNKNOWN (no pre-1.21 Control
    Plane to inspect), so tests drive both plausible shapes: a bare name, and the
    '<name> (<id>)' form the fresco list uses."""

    def __init__(self, texts, clicked):
        self._texts = texts
        self._clicked = clicked

    def filter(self, has=None):
        # Whitespace-normalized like _Rows.filter, and for the same reason: Playwright
        # matches textContent after normalization, and an anchored pattern is exactly the
        # kind most sensitive to the difference.
        return _LegacyRows([t for t in self._texts if has.has_text.search(" ".join(t.split()))],
                           self._clicked)

    def count(self):
        return len(self._texts)

    def inner_text(self):
        return self._texts[0] if self._texts else None

    @property
    def first(self):
        return _LegacyRows(self._texts[:1], self._clicked)

    def locator(self, selector):
        assert selector == "label", selector
        return _Labels(self._texts, self._clicked)


class _LegacyStubPage:
    def __init__(self, texts):
        self._texts = texts
        self.clicked = []

    def locator(self, selector, has_text=None):
        if selector == f"{TABLE} tr":
            return _LegacyRows(self._texts, self.clicked)
        if selector == "td":
            return SimpleNamespace(has_text=has_text)
        raise AssertionError(f"unexpected selector: {selector}")


class TestLegacyWizardHasTheSameBug:
    """The pre-1.21 table branch matched on ENV.TP_AUTO_STORAGE_CLASS only, exactly like the
    fresco path did — so CLI mode against an older Control Plane hit the identical failure,
    just as an unguarded 30s wait_for() instead of a screenshot. No pre-1.21 Control Plane is
    available to verify on, so this branch is held to the fresco path's shape by tests."""

    def _select(self, texts, section_title=SECTION, is_required=True):
        page = _LegacyStubPage(texts)
        PageObjectDataPlaneEMS(page).legacy_select_storage(TABLE, section_title, DP_NAME, is_required)
        return page.clicked

    def test_cli_named_resource_is_selected(self):
        assert self._select([f"{DP_NAME}-storage"]) == [f"{DP_NAME}-storage"]

    def test_gui_named_resource_is_still_selected(self):
        # The only behaviour the legacy path had before; it must not regress.
        assert self._select([STORAGE_CLASS]) == [STORAGE_CLASS]

    def test_dp_named_resource_wins_when_both_are_offered(self):
        assert self._select([STORAGE_CLASS, f"{DP_NAME}-storage"]) == [f"{DP_NAME}-storage"]

    def test_one_unrecognised_row_is_selected(self, _stub_env_and_util):
        assert self._select(["renamed-storage-thing"]) == ["renamed-storage-thing"]
        assert any("exactly one resource" in w for w in _stub_env_and_util)

    def test_several_unrecognised_rows_do_NOT_get_a_coin_flip(self):
        with pytest.raises(_ExitError, match="no safe one to pick"):
            self._select(["mystery-a", "mystery-b"])

    def test_a_missing_REQUIRED_resource_is_fatal(self):
        # The regression cross-review caught: an earlier cut warned for BOTH sections, so a
        # missing Message Storage fell through to the '#btnNextCapabilityProvision' click —
        # an unguarded timeout at best, EMS with no message storage at worst.
        with pytest.raises(_ExitError, match="No storage resource is available"):
            self._select([])

    def test_a_missing_OPTIONAL_resource_only_warns(self, _stub_env_and_util):
        assert self._select([], section_title="Log Storage", is_required=False) == []
        assert any("No storage resource is available" in w for w in _stub_env_and_util)

    def test_the_click_is_narrowed_for_strict_mode(self):
        # Two matching rows must not raise a strict-mode violation the way an un-narrowed
        # .locator('label').click() would.
        assert self._select([f"{DP_NAME}-storage", f"{DP_NAME}-storage"]) == [f"{DP_NAME}-storage"]

    # -- anchoring -------------------------------------------------------------------
    # has_text is a SUBSTRING match and the legacy cell holds the BARE name (no ' (<id>)'
    # to anchor on), so the pattern must be anchored at BOTH ends. Cross-review caught
    # this: the first cut of legacy_storage_row() built a bare alternation, which made
    # 'nfs' match an 'nfs-backup' row — and since the click re-runs the same filter and
    # takes .first, that is a click on the WRONG storage resource, not just a bad lookup.

    def test_a_candidate_does_not_match_a_longer_row_that_contains_it(self):
        # 'nfs' must not select 'nfs-backup'; the exact 'nfs' row is the only valid hit.
        assert self._select(["nfs-backup", STORAGE_CLASS]) == [STORAGE_CLASS]

    def test_a_candidate_does_not_match_a_row_that_ends_with_it(self):
        assert self._select(["prod-nfs", STORAGE_CLASS]) == [STORAGE_CLASS]

    def test_a_longer_dp_name_is_not_matched(self):
        # The fresco path's substring guard, restated for the legacy table.
        assert self._select([f"{DP_NAME}0-storage", STORAGE_CLASS]) == [STORAGE_CLASS]

    def test_surrounding_whitespace_in_the_cell_still_matches(self):
        # Table cells routinely render padded; the anchors allow \s* on both sides so a
        # legitimate row is not missed by the very guard that blocks the wrong ones.
        assert self._select([f"  {DP_NAME}-storage  "]) == [f"  {DP_NAME}-storage  "]

    def test_only_substring_rows_present_degrades_rather_than_clicking_one(self):
        # Nothing matches exactly, so this is the fallback's job — but the point is that
        # 'nfs-backup' was NOT treated as a candidate match.
        checked = self._select(["nfs-backup"])
        assert checked == ["nfs-backup"], "fallback still selects the only row offered"

    # -- the terminator ---------------------------------------------------------------
    # Human review caught that anchoring the END too was a TIGHTENING on a path with no
    # verification environment: the legacy table's rendering is unknown, and the code this
    # replaced used a bare substring match, which is evidence for neither shape. If the
    # table renders '<name> (<id>)' like the fresco list, a both-ends anchor would find
    # ZERO rows and break a legacy GUI-mode deploy that works today. So the pattern is
    # anchored at the start and terminated by end-of-cell OR ' ('.

    def test_a_cell_rendered_as_name_then_id_still_matches(self):
        assert self._select([f"{DP_NAME}-storage (da94beb9ds6g00dusrg0)"]) == [
            f"{DP_NAME}-storage (da94beb9ds6g00dusrg0)"]

    def test_the_id_form_does_not_reopen_the_substring_hole(self):
        # 'nfs-backup (id)' must still lose to the exact 'nfs (id)' row.
        assert self._select(["nfs-backup (id1)", f"{STORAGE_CLASS} (id2)"]) == [f"{STORAGE_CLASS} (id2)"]

    def test_a_longer_dp_name_in_the_id_form_is_not_matched(self):
        assert self._select([f"{DP_NAME}0-storage (id1)", f"{STORAGE_CLASS} (id2)"]) == [f"{STORAGE_CLASS} (id2)"]
