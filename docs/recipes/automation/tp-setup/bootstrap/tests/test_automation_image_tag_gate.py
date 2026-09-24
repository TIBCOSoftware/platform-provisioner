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
# PCP-23946 item 5 — the automation image tag is asserted in five places, and merging
# before the GHCR image is pushed puts every on-prem deploy into ImagePullBackOff. Until
# now that was enforced only by a note in a PR description, which disappears on merge.
#
# These tests cover the gate itself: that its declared sites still exist and still match
# (so a rename turns into a failing test rather than a check that quietly matches nothing),
# and that drift is actually reported.

import importlib.util
import re
from pathlib import Path

import pytest

def _repo_root():
    """Walk up to the checkout root rather than counting parents - this file sits six
    levels down and a hard-coded index breaks the moment the tree is reorganised."""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / ".github").is_dir():
            return candidate
    raise RuntimeError("could not locate the repository root")


REPO_ROOT = _repo_root()
SCRIPT = REPO_ROOT / ".github" / "scripts" / "check-automation-image-tag.py"


def _load():
    spec = importlib.util.spec_from_file_location("image_tag_gate", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate():
    assert SCRIPT.is_file(), f"the CI gate script is missing: {SCRIPT}"
    return _load()


@pytest.fixture(scope="module")
def build_workflow():
    """The GHCR build workflow, or a skip.

    `docker-image-ghcr-build-push-public.yml` is one of the paths the repo CLAUDE.md
    lists as NOT synced to the public mirror, while `tests/` is. Asserting on it
    unconditionally turns a green private CI into a red public one.
    """
    path = (REPO_ROOT / ".github" / "workflows"
            / "docker-image-ghcr-build-push-public.yml")
    if not path.is_file():
        pytest.skip("the GHCR build workflow is private-repo only")
    return path.read_text(encoding="utf-8")


def test_every_declared_site_exists_and_matches(gate):
    """A renamed key or moved file must fail here, not silently match nothing in CI."""
    for rel, pattern in gate.TAG_SITES.items():
        path = REPO_ROOT / rel
        assert path.is_file(), f"declared tag site is missing: {rel}"
        assert re.findall(pattern, path.read_text(encoding="utf-8")), \
            f"pattern for {rel} matched nothing - was the key renamed?"


def test_the_repo_is_currently_consistent(gate):
    """The five occurrences agree with version.txt right now."""
    assert gate.check_drift(gate.read_expected_tag(), gate.collect_tags()) is True


def test_drift_is_reported(gate):
    """The check must fail when one site lags - the case a version bump can leave behind."""
    found = gate.collect_tags()
    (first, tags), = list(found.items())[:1]
    drifted = dict(found)
    drifted[first] = ["1.0.0-auto-on-prem-jammy"]
    assert gate.check_drift(gate.read_expected_tag(), drifted) is False


def test_version_txt_is_the_source_of_truth(gate):
    tag = gate.read_expected_tag()
    assert tag.endswith("-auto-on-prem-jammy")
    assert re.match(r"^\d+\.\d+\.\d+-auto-on-prem-jammy$", tag), tag


def test_registry_outage_does_not_fail_the_pr(gate, monkeypatch, capsys):
    """An inconclusive registry answer must warn, not block unrelated work."""
    monkeypatch.setattr(gate, "manifest_exists",
                        lambda _tag: (None, "ConnectionError: registry unreachable", None))
    monkeypatch.setattr(gate.sys, "argv", ["check-automation-image-tag.py"])
    assert gate.main() == 0
    assert "WARN" in capsys.readouterr().out


def test_an_unpublished_tag_fails_the_pr(gate, monkeypatch, capsys):
    monkeypatch.setattr(gate, "manifest_exists",
                        lambda _tag: (False, "HTTP 404", None))
    monkeypatch.setattr(gate.sys, "argv", ["check-automation-image-tag.py"])
    assert gate.main() == 1
    assert "ImagePullBackOff" in capsys.readouterr().out


def test_a_published_tag_passes(gate, monkeypatch):
    monkeypatch.setattr(gate, "manifest_exists",
                        lambda _tag: (True, "HTTP 200", DIGEST))
    monkeypatch.setattr(gate, "check_source_parity",
                        lambda _ref, _head: (True, "same tree"))
    monkeypatch.setattr(gate.sys, "argv", ["check-automation-image-tag.py"])
    assert gate.main() == 0


def _mock_registry(gate, monkeypatch, status, digest=None):
    """Token fetch succeeds; the manifest request answers with `status`.

    `digest` overrides the Docker-Content-Digest the manifest response carries, so a test
    can drive the value manifest_exists() pins on (PCP-24359 item 2).
    """
    import io
    import urllib.error

    class TokenResponse:
        status = 200
        # manifest_exists() reads Docker-Content-Digest to pin the tag (PCP-24359 item 2).
        headers = {"Docker-Content-Digest": DIGEST}

        def read(self):
            return b'{"token": "t"}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class ManifestResponse(TokenResponse):
        def __init__(self):
            self.status = status
            self.headers = {"Docker-Content-Digest": digest or DIGEST}

    def fake_urlopen(req, *a, **k):
        if isinstance(req, str):          # the token endpoint
            return TokenResponse()
        if status == 200:
            return ManifestResponse()
        raise urllib.error.HTTPError(
            "https://ghcr.io/", status, "err", {}, io.BytesIO(b""))

    monkeypatch.setattr(gate.urllib.request, "urlopen", fake_urlopen)


def test_only_404_means_the_tag_is_missing(gate, monkeypatch):
    """A 404 is definitive; 401/403 is not.

    The package pulls anonymously today, so a 401/403 means the environment changed
    (visibility flipped, token flow broke) rather than "this tag was never pushed".
    Reporting that as missing would fail a PR for a reason the PR cannot fix — the
    opposite of the warn-don't-block rule this gate is built on.
    """
    _mock_registry(gate, monkeypatch, 404)
    assert gate.manifest_exists("t")[0] is False

    for code in (401, 403, 500, 502):
        _mock_registry(gate, monkeypatch, code)
        assert gate.manifest_exists("t")[0] is None, f"HTTP {code} must be inconclusive"


def test_a_200_manifest_is_published(gate, monkeypatch):
    _mock_registry(gate, monkeypatch, 200)
    assert gate.manifest_exists("t")[0] is True


def test_the_token_is_actually_sent(gate, monkeypatch):
    """Guards the auth header itself: without a Bearer token every lookup would 401 and the
    gate would fail every PR."""
    sent = {}

    class TokenResponse:
        status = 200
        headers = {"Docker-Content-Digest": DIGEST}

        def read(self):
            return b'{"token": "abc123"}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, *a, **k):
        if isinstance(req, str):
            return TokenResponse()
        sent["auth"] = req.get_header("Authorization")
        return TokenResponse()

    monkeypatch.setattr(gate.urllib.request, "urlopen", fake_urlopen)
    gate.manifest_exists("t")
    assert sent["auth"] == "Bearer abc123"


def test_the_gate_covers_every_file_bump_version_stamps(gate):
    """Bind TAG_SITES to `bump_version.sh` instead of hand-copying its list.

    The gate hard-codes the same files `bump_version.sh` stamps with the automation
    version. Nothing kept the two in step: a sixth `set_version … "${automation_version}"`
    added later would be bumped, shipped and never drift-checked, while the gate happily
    reported "all 5 occurrences agree". Raised in review, and the same failure shape the
    gate itself exists to catch.
    """
    script = (REPO_ROOT / "docs" / "recipes" / "automation" / "tp-setup" / "bootstrap"
              / "bump_version.sh").read_text(encoding="utf-8")

    stamped = set(re.findall(
        r'set_version\s+"([^"]+)"\s+"\$\{automation_version\}"', script))
    # version.txt is stamped through the BUILD_VERSION_FILE variable, not a literal path.
    stamped.discard("$BUILD_VERSION_FILE")
    stamped.add("docs/recipes/automation/tp-setup/bootstrap/version.txt")

    covered = {str(p).replace("\\", "/") for p in gate.TAG_SITES}
    covered.add(str(gate.VERSION_FILE).replace("\\", "/"))

    missing = stamped - covered
    assert not missing, (
        "bump_version.sh stamps files the image-tag gate does not check: "
        f"{sorted(missing)} - add them to TAG_SITES")


def test_the_workflow_wires_the_script_in():
    """The gate is worthless if nothing runs it."""
    workflow = (REPO_ROOT / ".github" / "workflows" / "test.yaml").read_text(encoding="utf-8")
    assert "check-automation-image-tag.py" in workflow
    assert "automation-image-tag:" in workflow


# --------------------------------------------------------------------------
# PCP-24348 item 3 — PUBLISHED is not the same as CURRENT
# --------------------------------------------------------------------------
# 1.7.90-auto-on-prem-jammy was pushed at 19:04:48Z and the review revision it was
# supposed to carry merged at 19:37:59Z. Both existing checks passed - the five sites
# agreed, and the manifest was there - and the image still shipped code that was not the
# code being merged. Neither check ever tied the artifact back to the source.
#
# The parity check compares the GIT TREE HASH of the build context, so it is immune to
# the rebases and squash merges that would make a commit-identity or "is the image newer
# than the commit" comparison cry wolf on main.

BUILT_FROM = "a" * 40
OTHER_REV = "b" * 40
OTHER_TREE = "1" * 40
SAME_TREE = "2" * 40
HEAD_SHA = "c" * 40          # the PR HEAD - NOT the checkout's HEAD, see below
DIGEST = "sha256:" + "d" * 64
DIGEST_2 = "sha256:" + "e" * 64


def _fake_git(gate, monkeypatch, trees, reachable=True, changed=(),
              reachable_after_fetch=None):
    """Script the git questions check_source_parity asks.

    `reachable_after_fetch` models the case the fetch exists for: cat-file fails, the
    fetch rescues it, cat-file then succeeds.
    """
    calls = []
    state = {"reachable": reachable}

    def git(*args):
        calls.append(args)
        if args[0] == "cat-file":
            return state["reachable"], ""
        if args[0] == "fetch":
            if reachable_after_fetch is not None:
                state["reachable"] = reachable_after_fetch
            return True, ""
        if args[0] == "rev-parse":
            rev = args[1].split(":")[0]
            return True, trees[rev]
        if args[0] == "diff":
            return True, "\n".join(f"{gate.BOOTSTRAP_DIR}/{p}" for p in changed)
        return True, ""

    monkeypatch.setattr(gate, "git", git)
    return calls


def test_a_stale_image_blocks_the_merge(gate, monkeypatch):
    """THE regression: same tag, published, built from an older tree."""
    monkeypatch.setattr(gate, "image_revision", lambda _ref: (BUILT_FROM, None))
    _fake_git(gate, monkeypatch, {BUILT_FROM: OTHER_TREE, HEAD_SHA: SAME_TREE},
              changed=["page_object/po_bmdp_config.py"])

    parity, detail = gate.check_source_parity("t", HEAD_SHA)
    assert parity is False
    assert "po_bmdp_config.py" in detail, "name the files, or nobody can act on it"


def test_a_stale_image_fails_the_whole_run(gate, monkeypatch, capsys):
    monkeypatch.setattr(gate, "manifest_exists",
                        lambda _tag: (True, "HTTP 200", DIGEST))
    monkeypatch.setattr(gate, "check_source_parity",
                        lambda _ref, _head: (False, "built from an older tree"))
    monkeypatch.setattr(gate.sys, "argv", ["check-automation-image-tag.py"])

    assert gate.main() == 1
    out = capsys.readouterr().out
    assert "does NOT contain this source" in out
    assert "PARITY=FAIL" in out


def test_an_image_built_from_this_tree_passes(gate, monkeypatch):
    monkeypatch.setattr(gate, "image_revision", lambda _ref: (BUILT_FROM, None))
    _fake_git(gate, monkeypatch, {BUILT_FROM: SAME_TREE, HEAD_SHA: SAME_TREE})

    parity, _ = gate.check_source_parity("t", HEAD_SHA)
    assert parity is True


def test_parity_compares_the_pr_head_not_the_checkout_head(gate, monkeypatch):
    """On a pull_request run the checkout is refs/pull/N/merge, so HEAD is base (+) this
    PR. Comparing against it fails the moment somebody ELSE'S bootstrap change lands on
    main - naming their files, with a remedy (rebuild this branch) that cannot fix it.
    Here the PR head matches the image and the merge ref does not; the gate must pass.
    """
    monkeypatch.setattr(gate, "image_revision", lambda _ref: (BUILT_FROM, None))
    calls = _fake_git(gate, monkeypatch, {
        BUILT_FROM: SAME_TREE,
        HEAD_SHA: SAME_TREE,     # the PR head - identical to the image
        "HEAD": OTHER_TREE,      # the merge ref - carries a concurrent change from base
    })

    assert gate.check_source_parity("t", HEAD_SHA)[0] is True
    assert not any("HEAD:" in a for c in calls for a in c), \
        f"the checkout HEAD must never be the comparison ref: {calls}"


def test_parity_is_skipped_without_a_pr_head(gate, monkeypatch):
    """A push to main has no PR head, and its squashed commit can never match an image
    built before that commit existed - an unfixable red. Parity is a PRE-MERGE check."""
    monkeypatch.setattr(gate, "image_revision",
                        lambda _ref: pytest.fail("must not hit the registry"))

    parity, detail = gate.check_source_parity("t", None)
    assert parity is None
    assert "pre-merge" in detail


def test_a_head_ref_that_looks_like_a_flag_is_refused(gate, monkeypatch):
    """The head ref is CI/operator-supplied rather than registry-supplied, so it is not
    held to a bare sha - `--head HEAD` is legitimate. A leading '-' is not: git would
    read it as a flag."""
    monkeypatch.setattr(gate, "image_revision",
                        lambda _ref: pytest.fail("must not reach the registry"))
    monkeypatch.setattr(gate, "git", lambda *a: pytest.fail(f"git must not be called: {a}"))

    parity, detail = gate.check_source_parity("t", "--output=/tmp/pwned")
    assert parity is None
    assert "refusing" in detail


def test_a_non_runtime_only_difference_warns_instead_of_blocking(gate, monkeypatch):
    """A CHANGELOG line added during a review round, or a new unit test, changes the tree
    but not the runtime. Forcing a version bump plus a hand-triggered image rebuild for
    that is friction with no safety value."""
    monkeypatch.setattr(gate, "image_revision", lambda _ref: (BUILT_FROM, None))
    _fake_git(gate, monkeypatch, {BUILT_FROM: OTHER_TREE, HEAD_SHA: SAME_TREE},
              changed=["CHANGELOG.md", "tests/test_something.py", "e2e/conftest.py"])

    parity, detail = gate.check_source_parity("t", HEAD_SHA)
    assert parity is gate.CARVED_OUT, "benign-and-known, not merely unconfirmed"
    assert parity is not None, "must be distinguishable from 'could not check at all'"
    assert "non-runtime only" in detail


def test_the_file_list_is_taken_with_rename_detection_OFF(gate, monkeypatch):
    """`git diff --name-only` detects renames by default and prints ONLY the destination.
    A runtime file moved into a carved-out path would therefore be itemised solely at its
    carved-out destination, `runtime` would come back empty, and a genuine FAIL would
    degrade to a warning - the silent pass this whole check exists to close. Raised in
    review and reproduced in a scratch repo before being fixed."""
    monkeypatch.setattr(gate, "image_revision", lambda _ref: (BUILT_FROM, None))
    calls = _fake_git(gate, monkeypatch, {BUILT_FROM: OTHER_TREE, HEAD_SHA: SAME_TREE},
                      changed=["CHANGELOG.md"])

    gate.check_source_parity("t", HEAD_SHA)
    diffs = [c for c in calls if c[0] == "diff"]
    assert diffs, calls
    assert "--no-renames" in diffs[0], diffs[0]


def test_a_runtime_file_renamed_into_a_carved_out_path_still_blocks(gate, monkeypatch):
    """With rename detection off, both sides of the move are listed - and the SOURCE side
    is a runtime file, so the gate blocks instead of warning."""
    monkeypatch.setattr(gate, "image_revision", lambda _ref: (BUILT_FROM, None))
    _fake_git(gate, monkeypatch, {BUILT_FROM: OTHER_TREE, HEAD_SHA: SAME_TREE},
              changed=["page_object/po_dp_flogo.py", "tests/po_dp_flogo.py"])

    parity, detail = gate.check_source_parity("t", HEAD_SHA)
    assert parity is False
    assert "page_object/po_dp_flogo.py" in detail


def test_carved_out_is_reported_apart_from_inconclusive_and_does_not_block(gate,
                                                                          monkeypatch,
                                                                          capsys):
    """The two non-blocking verdicts need different responses: 'benign, nothing to do'
    versus 'we learned nothing, somebody should chase this'. One token for both makes the
    second invisible in a log sweep."""
    monkeypatch.setattr(gate, "manifest_exists",
                        lambda _tag: (True, "HTTP 200", DIGEST))
    monkeypatch.setattr(gate, "check_source_parity",
                        lambda _ref, _head: (gate.CARVED_OUT, "docs only"))
    monkeypatch.setattr(gate.sys, "argv", ["check-automation-image-tag.py"])

    assert gate.main() == 0, "a carved-out difference must not block"
    out = capsys.readouterr().out
    assert "PARITY=CARVED_OUT" in out
    assert "PARITY=INCONCLUSIVE" not in out


def test_every_parity_verdict_has_a_token(gate):
    """Guards the identity-keyed lookup: CARVED_OUT is falsy, so an `elif parity:` chain
    would have silently reported it as a FAIL."""
    assert gate.PARITY_TOKENS[True] == "OK"
    assert gate.PARITY_TOKENS[False] == "FAIL"
    assert gate.PARITY_TOKENS[None] == "INCONCLUSIVE"
    assert gate.PARITY_TOKENS[gate.CARVED_OUT] == "CARVED_OUT"
    assert not gate.CARVED_OUT, "stays falsy, so it can never read as a pass"


@pytest.mark.parametrize("verdict, expected_exit", [
    (True, 0),
    ("CARVED_OUT", 0),
    (None, 0),
    (False, 1),
])
def test_main_blocks_exactly_the_verdicts_outside_PARITY_NON_BLOCKING(
        gate, monkeypatch, verdict, expected_exit):
    """`PARITY_NON_BLOCKING` used to be referenced only by a test while `main()`
    re-implemented the same policy inline — so the test pinned a rule nothing enforced,
    which is the very "the test agrees with itself" trap this PR fixes elsewhere. Drive
    `main()` for every verdict instead, so the constant and the behaviour cannot drift.
    """
    parity = gate.CARVED_OUT if verdict == "CARVED_OUT" else verdict

    monkeypatch.setattr(gate, "manifest_exists",
                        lambda _tag: (True, "HTTP 200", DIGEST))
    monkeypatch.setattr(gate, "check_source_parity",
                        lambda _ref, _head: (parity, "d"))
    monkeypatch.setattr(gate.sys, "argv", ["check-automation-image-tag.py"])

    assert gate.main() == expected_exit


def test_one_runtime_file_among_the_carve_out_still_blocks(gate, monkeypatch):
    """The carve-out is about files that cannot change behaviour, not about the ratio."""
    monkeypatch.setattr(gate, "image_revision", lambda _ref: (BUILT_FROM, None))
    _fake_git(gate, monkeypatch, {BUILT_FROM: OTHER_TREE, HEAD_SHA: SAME_TREE},
              changed=["CHANGELOG.md", "page_object/po_dp_flogo.py"])

    assert gate.check_source_parity("t", HEAD_SHA)[0] is False


def test_a_carve_out_named_file_in_a_subdirectory_still_blocks(gate, monkeypatch):
    """The exact set is top-level only. `page_object/README.md` is not the one this gate
    means, and a broad basename match would let a renamed source file through."""
    monkeypatch.setattr(gate, "image_revision", lambda _ref: (BUILT_FROM, None))
    _fake_git(gate, monkeypatch, {BUILT_FROM: OTHER_TREE, HEAD_SHA: SAME_TREE},
              changed=["page_object/README.md"])

    assert gate.check_source_parity("t", HEAD_SHA)[0] is False


def test_a_tree_difference_git_cannot_itemise_still_blocks(gate, monkeypatch):
    """An empty file list is not evidence of innocence - the hashes already disagreed."""
    monkeypatch.setattr(gate, "image_revision", lambda _ref: (BUILT_FROM, None))
    _fake_git(gate, monkeypatch, {BUILT_FROM: OTHER_TREE, HEAD_SHA: SAME_TREE}, changed=[])

    assert gate.check_source_parity("t", HEAD_SHA)[0] is False


def test_an_unreachable_revision_is_inconclusive(gate, monkeypatch):
    """A force-pushed branch can orphan the built-from commit. Unverifiable is not the
    same as wrong, and blocking on it would contradict the warn-don't-block rule."""
    monkeypatch.setattr(gate, "image_revision", lambda _ref: (BUILT_FROM, None))
    _fake_git(gate, monkeypatch, {BUILT_FROM: OTHER_TREE, HEAD_SHA: SAME_TREE},
              reachable=False)

    parity, detail = gate.check_source_parity("t", HEAD_SHA)
    assert parity is None
    assert BUILT_FROM[:12] in detail


def test_a_fetch_rescues_a_revision_the_checkout_did_not_have(gate, monkeypatch):
    """The whole reason the fetch exists: a shallow / merge-ref checkout simply does not
    have the commit yet. An earlier cut asserted only that a fetch was ATTEMPTED, so the
    recovery path itself was never exercised."""
    monkeypatch.setattr(gate, "image_revision", lambda _ref: (BUILT_FROM, None))
    calls = _fake_git(gate, monkeypatch, {BUILT_FROM: SAME_TREE, HEAD_SHA: SAME_TREE},
                      reachable=False, reachable_after_fetch=True)

    assert gate.check_source_parity("t", HEAD_SHA)[0] is True, \
        "the comparison must proceed once the fetch has landed the commit"
    assert any(c[0] == "fetch" for c in calls), calls
    assert len([c for c in calls if c[0] == "cat-file"]) == 2, \
        "reachability must be re-checked AFTER the fetch"


def test_an_image_without_the_revision_label_is_inconclusive(gate, monkeypatch):
    """Images built before the label existed must not fail every PR."""
    monkeypatch.setattr(gate, "image_revision",
                        lambda _ref: (None, "the image carries no label"))
    assert gate.check_source_parity("t", HEAD_SHA)[0] is None


def test_the_build_workflow_stamps_the_label_the_gate_reads(gate, build_workflow):
    """The gate reads a label somebody else has to write. Nothing but this test keeps the
    two names in step, and a silent rename would turn the gate into a permanent WARN."""
    assert f"{gate.REVISION_LABEL}=" in build_workflow


def test_the_parity_check_covers_the_whole_build_context(gate, build_workflow):
    """The compared directory must be the Docker build context, or the comparison is
    about something other than what is in the image."""
    assert f"./{gate.BOOTSTRAP_DIR}" in build_workflow
    assert (REPO_ROOT / gate.BOOTSTRAP_DIR / "Dockerfile").is_file()


def test_the_ci_job_passes_the_pr_head_to_the_gate():
    """The merge-ref trap is only avoided if the workflow actually supplies the head."""
    workflow = (REPO_ROOT / ".github" / "workflows" / "test.yaml").read_text(encoding="utf-8")
    assert "PR_HEAD_SHA:" in workflow
    assert "github.event.pull_request.head.sha" in workflow


# --- image_revision: index -> platform manifests -> config blobs ----------------------

def _config_digest_for(manifest_digest):
    """A well-formed config digest derived from a manifest digest (still 64 hex)."""
    return "sha256:" + manifest_digest[len("sha256:"):][::-1]


def _fake_registry(gate, monkeypatch, index, revisions):
    """Serve an index and a {manifest digest: revision-or-None} map."""
    fetched = []

    def fake_json(path, _token, _accept):
        fetched.append(path)
        if path == "manifests/t":
            return index, None
        if path.startswith("manifests/"):
            return {"config": {"digest": _config_digest_for(path[len("manifests/"):])}}, None
        revision = revisions[path[len("blobs/"):]]
        labels = {gate.REVISION_LABEL: revision} if revision else {}
        return {"config": {"Labels": labels}}, None

    monkeypatch.setattr(gate, "ghcr_token", lambda: ("token", None))
    monkeypatch.setattr(gate, "ghcr_get_json", fake_json)
    return fetched


def test_attestation_manifests_are_not_mistaken_for_the_image(gate, monkeypatch):
    """buildx publishes attestation manifests next to the real ones, tagged
    platform.architecture == "unknown". Reading them would look up a config that carries
    no source labels and report a permanent WARN."""
    index = {"manifests": [
        {"digest": DIGEST, "platform": {"os": "unknown", "architecture": "unknown"}},
        {"digest": DIGEST_2, "platform": {"os": "linux", "architecture": "amd64"}},
    ]}
    fetched = _fake_registry(gate, monkeypatch, index,
                             {_config_digest_for(DIGEST_2): BUILT_FROM})

    assert gate.image_revision("t") == (BUILT_FROM, None)
    assert f"manifests/{DIGEST}" not in fetched, fetched


def test_every_runnable_platform_is_checked_not_just_the_first(gate, monkeypatch):
    """A tag holds an amd64 AND an arm64 manifest. Checking only the first would let a
    stale arm64 - the image half of the on-prem fleet actually pulls on ARM - ship behind
    a green check."""
    index = {"manifests": [
        {"digest": DIGEST, "platform": {"os": "linux", "architecture": "amd64"}},
        {"digest": DIGEST_2, "platform": {"os": "linux", "architecture": "arm64"}},
    ]}
    fetched = _fake_registry(gate, monkeypatch, index, {
        _config_digest_for(DIGEST): BUILT_FROM,
        _config_digest_for(DIGEST_2): OTHER_REV,     # built from a different commit
    })

    revision, detail = gate.image_revision("t")
    assert revision is None
    assert detail.startswith(gate.PLATFORM_MISMATCH), detail
    assert f"manifests/{DIGEST_2}" in fetched, "the second platform must be read"


def test_platform_disagreement_is_a_failure_not_a_warning(gate, monkeypatch):
    """Mismatched artifacts under one tag is a real, actionable defect - the registry is
    answering fine. Treating it as inconclusive would warn-and-pass on a broken image."""
    monkeypatch.setattr(gate, "image_revision",
                        lambda _ref: (None, f"{gate.PLATFORM_MISMATCH}: linux/arm64=beef"))
    assert gate.check_source_parity("t", HEAD_SHA)[0] is False


@pytest.mark.parametrize("revision", [
    "--upload-pack=/bin/sh",   # git option injection: a bare argument starting with '-'
    "not-a-sha",
    "a" * 39,
    "A" * 40,                  # git hashes are lowercase hex
    "",
])
def test_a_malformed_revision_label_is_rejected_before_it_reaches_git(gate, monkeypatch,
                                                                     revision):
    """The label is registry metadata, i.e. untrusted, and it is passed to git as a bare
    argument. subprocess(shell=False) stops shell injection but not OPTION injection."""
    index = {"manifests": [
        {"digest": DIGEST, "platform": {"os": "linux", "architecture": "amd64"}},
    ]}
    _fake_registry(gate, monkeypatch, index, {_config_digest_for(DIGEST): revision})
    monkeypatch.setattr(gate, "git",
                        lambda *a: pytest.fail(f"git must not be called with {a}"))

    assert gate.image_revision("t")[0] is None


def test_a_malformed_index_digest_is_rejected_before_it_reaches_the_registry(gate,
                                                                            monkeypatch):
    """The digest is interpolated straight into a v2 URL path; `../` would redirect the
    request elsewhere in the namespace."""
    index = {"manifests": [
        {"digest": "sha256:../../evil", "platform": {"os": "linux", "architecture": "amd64"}},
    ]}
    _fake_registry(gate, monkeypatch, index, {})

    revision, detail = gate.image_revision("t")
    assert revision is None
    assert "malformed digest" in detail


# --------------------------------------------------------------------------
# PCP-24359 item 2 — the tag is resolved ONCE, to a digest, and re-asserted
# --------------------------------------------------------------------------
# The tag used to be resolved three times: once in manifest_exists(), again in
# image_revision(), and a third time by whatever later pulls it. A tag is mutable, so
# nothing tied those three resolutions to the same bytes - a manifest that passed PARITY
# could be replaced before merge or before pull and every check would still read green.
#
# Not hypothetical: PCP-24348's own review rounds twice rebuilt an already-published
# 1.7.91 in place, which is the very practice that ticket's reasoning rules out.


def test_the_gate_step_has_an_id_so_its_digest_output_is_addressable():
    """Writing to $GITHUB_OUTPUT does nothing unless the STEP can be referenced.

    Caught in review: `emit_step_output("image_digest", ...)` landed the value in the file,
    but GitHub exposes a step output only as `steps.<id>.outputs.<name>` and the invoking
    step had no `id:` - so the write was unaddressable and the helper (plus its OSError
    handler) was dead weight. The half that makes it reachable lives in test.yaml, so it
    is pinned from here.
    """
    yaml = pytest.importorskip("yaml")
    wf = REPO_ROOT / ".github" / "workflows" / "test.yaml"
    assert wf.is_file(), "the CI workflow that runs the gate is missing"
    doc = yaml.safe_load(wf.read_text(encoding="utf-8"))

    steps = [s for job in doc["jobs"].values() for s in job.get("steps", [])]
    gate_steps = [s for s in steps
                  if "check-automation-image-tag.py" in str(s.get("run", ""))]
    assert gate_steps, "no step runs the gate script - this test is now vacuous"
    for step in gate_steps:
        # The CONCRETE id, not merely "some id": the CHANGELOG and the step's own comment
        # both document the handle as steps.image-tag-gate.outputs.image_digest, so a
        # rename would strand both references while a truthiness check stayed green.
        assert step.get("id") == "image-tag-gate", (
            f"the step running the gate ({step.get('name')!r}) needs id: image-tag-gate - "
            "the CHANGELOG and the step comment both document its output as "
            "steps.image-tag-gate.outputs.image_digest, so a rename silently strands them")


def test_the_resolved_digest_is_published_so_a_later_consumer_can_pin_it(gate, monkeypatch,
                                                                         capsys):
    """The whole point of resolving once is that the result is USABLE downstream."""
    monkeypatch.setattr(gate, "manifest_exists",
                        lambda _tag: (True, "HTTP 200", DIGEST))
    monkeypatch.setattr(gate, "check_source_parity",
                        lambda _ref, _head: (True, "same tree"))
    monkeypatch.setattr(gate.sys, "argv", ["check-automation-image-tag.py"])

    assert gate.main() == 0
    assert f"IMAGE_DIGEST={DIGEST}" in capsys.readouterr().out


def test_parity_inspects_the_digest_not_the_mutable_tag(gate, monkeypatch):
    """THE item-2 regression. If parity re-resolves the tag, the bytes it vets need not be
    the bytes whose existence was just confirmed.

    A/B: pass `expected` instead of `digest` at the call site and this goes red.
    """
    seen = {}
    monkeypatch.setattr(gate, "manifest_exists",
                        lambda _tag: (True, "HTTP 200", DIGEST))

    def spy(ref, _head):
        seen["ref"] = ref
        return True, "same tree"

    monkeypatch.setattr(gate, "check_source_parity", spy)
    monkeypatch.setattr(gate.sys, "argv", ["check-automation-image-tag.py"])
    gate.main()

    assert seen["ref"] == DIGEST, "parity must be asked about the pinned digest"


def test_a_tag_that_moves_mid_run_fails_the_check(gate, monkeypatch, capsys):
    """Everything above the re-assert describes the FIRST digest. If the tag no longer
    points at it, those verdicts are about an artifact nobody will pull - and anything
    that already pulled the tag keeps the old digest forever."""
    answers = iter([(True, "HTTP 200", DIGEST), (True, "HTTP 200", DIGEST_2)])
    monkeypatch.setattr(gate, "manifest_exists", lambda _tag: next(answers))
    monkeypatch.setattr(gate, "check_source_parity",
                        lambda _ref, _head: (True, "same tree"))
    monkeypatch.setattr(gate.sys, "argv", ["check-automation-image-tag.py"])

    assert gate.main() == 1, "a tag that moved mid-run must not pass"
    out = capsys.readouterr().out
    assert "MOVED while this check was running" in out
    assert DIGEST_2 in out


def test_the_re_assert_re_resolves_the_TAG_not_the_digest(gate, monkeypatch):
    """The re-assert only means anything if it asks about the MUTABLE name.

    Caught in review: the test above stubs `manifest_exists` with a lambda that ignores
    its first argument, so swapping `check_digest_unchanged(expected, digest)` for
    `check_digest_unchanged(digest, digest)` would re-resolve an immutable digest - which
    can never move, so the check could never fire - and every assertion stayed green.
    That is the same "the test agrees with itself" trap this file is elsewhere about.
    """
    seen = []
    monkeypatch.setattr(gate, "manifest_exists",
                        lambda ref: (seen.append(ref),
                                                  (True, "HTTP 200", DIGEST))[1])
    monkeypatch.setattr(gate, "check_source_parity",
                        lambda _ref, _head: (True, "same tree"))
    monkeypatch.setattr(gate.sys, "argv", ["check-automation-image-tag.py"])
    gate.main()

    expected_tag = gate.read_expected_tag()
    assert seen, "manifest_exists was never called"
    assert seen[-1] == expected_tag, (
        f"the closing re-assert must re-resolve the TAG {expected_tag!r}, not "
        f"{seen[-1]!r} - re-resolving a digest could never detect a move")


def test_a_tag_DELETED_mid_run_fails_rather_than_warns(gate, monkeypatch, capsys):
    """A definitive 404 on the re-assert is not an outage - the tag is gone, so the
    verdicts above describe something the tag no longer names. Lumping it in with the
    inconclusive branch let a deleted tag pass with a warning, while the OPENING probe
    treats the identical 404 as a hard FAIL."""
    answers = iter([(True, "HTTP 200", DIGEST), (False, "HTTP 404", None)])
    monkeypatch.setattr(gate, "manifest_exists", lambda _tag: next(answers))
    monkeypatch.setattr(gate, "check_source_parity",
                        lambda _ref, _head: (True, "same tree"))
    monkeypatch.setattr(gate.sys, "argv", ["check-automation-image-tag.py"])

    assert gate.main() == 1, "a tag deleted mid-run must not pass"
    assert "DELETED while this check was running" in capsys.readouterr().out


def test_an_inconclusive_re_assert_still_passes(gate, monkeypatch, capsys):
    """The fail-open branch, which had no coverage at all. A registry blip on the CLOSING
    lookup must not turn a good PR red - same warn-don't-block rule as the opening probe.
    Pinning it is what stops the item above (404 -> FAIL) from being widened back over
    the inconclusive case."""
    answers = iter([(True, "HTTP 200", DIGEST), (None, "ConnectionError", None)])
    monkeypatch.setattr(gate, "manifest_exists", lambda _tag: next(answers))
    monkeypatch.setattr(gate, "check_source_parity",
                        lambda _ref, _head: (True, "same tree"))
    monkeypatch.setattr(gate.sys, "argv", ["check-automation-image-tag.py"])

    assert gate.main() == 0, "an outage on the re-assert must not block"
    assert "could not re-confirm" in capsys.readouterr().out


def test_a_stable_tag_passes_the_re_assert(gate, monkeypatch, capsys):
    """The control for the test above: same digest twice must stay green, or the re-assert
    would fail every honest PR."""
    monkeypatch.setattr(gate, "manifest_exists",
                        lambda _tag: (True, "HTTP 200", DIGEST))
    monkeypatch.setattr(gate, "check_source_parity",
                        lambda _ref, _head: (True, "same tree"))
    monkeypatch.setattr(gate.sys, "argv", ["check-automation-image-tag.py"])

    assert gate.main() == 0
    assert "still resolves to the digest that was checked" in capsys.readouterr().out


def test_an_unpinnable_digest_does_not_block(gate, monkeypatch, capsys):
    """A registry that omits Docker-Content-Digest means "could not pin", which follows
    the same warn-don't-block rule as a registry outage. Reporting UNKNOWN rather than
    silently passing is what keeps it from being mistaken for a successful pin."""
    monkeypatch.setattr(gate, "manifest_exists",
                        lambda _tag: (True, "HTTP 200", None))
    monkeypatch.setattr(gate, "check_source_parity",
                        lambda _ref, _head: (True, "same tree"))
    monkeypatch.setattr(gate.sys, "argv", ["check-automation-image-tag.py"])

    assert gate.main() == 0
    assert "IMAGE_DIGEST=UNKNOWN" in capsys.readouterr().out


@pytest.mark.parametrize("digest,expected_output", [
    (DIGEST, DIGEST),
    (None, "UNKNOWN"),
])
def test_the_step_output_carries_the_same_token_the_log_prints(gate, monkeypatch, tmp_path,
                                                               digest, expected_output):
    """The log and the step output must publish the same fact in the same shape.

    Raised in review: the log said `IMAGE_DIGEST=UNKNOWN` while the output was an empty
    string, so a consumer branching on the documented `UNKNOWN` sentinel would never see
    it, and an empty value interpolated into `image@${{ ... }}` yields a malformed ref
    rather than an obvious miss. There is no consumer yet, which made it the cheapest
    moment to pick one representation.
    """
    out_file = tmp_path / "github_output"
    out_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    monkeypatch.setattr(gate, "manifest_exists",
                        lambda _tag: (True, "HTTP 200", digest))
    monkeypatch.setattr(gate, "check_source_parity",
                        lambda _ref, _head: (True, "same tree"))
    monkeypatch.setattr(gate.sys, "argv", ["check-automation-image-tag.py"])

    assert gate.main() == 0
    assert f"image_digest={expected_output}" in out_file.read_text(encoding="utf-8")


def test_an_unpinnable_digest_falls_back_to_the_TAG_and_says_so(gate, monkeypatch,
                                                                capsys):
    """`digest or expected` reverts BOTH halves of item 2 at once, so the log has to admit it.

    Raised in review: with no digest, parity re-resolves the mutable tag - the exact
    second resolution image_revision()'s docstring says must not happen - and the closing
    re-assert returns early without asking anything. That is correct under warn-don't-block,
    but a run that silently skipped the pinning otherwise reads exactly like one that did it.
    """
    seen = {}
    monkeypatch.setattr(gate, "manifest_exists",
                        lambda _tag: (True, "HTTP 200", None))

    def spy(ref, _head):
        seen["ref"] = ref
        return True, "same tree"

    monkeypatch.setattr(gate, "check_source_parity", spy)
    monkeypatch.setattr(gate.sys, "argv", ["check-automation-image-tag.py"])

    assert gate.main() == 0
    expected_tag = gate.read_expected_tag()
    assert seen["ref"] == expected_tag, "with no digest, parity falls back to the tag"
    out = capsys.readouterr().out
    assert "no digest to pin" in out, "the degradation must be stated, not silent"
    assert "re-resolve the mutable tag" in out


def test_a_malformed_digest_header_is_not_trusted_as_a_pin(gate, monkeypatch):
    """The digest is fed back into a v2 URL path, so a registry-supplied value that is not
    a bare sha256 must be dropped rather than pinned - the same rule the revision label
    and the index child digests already follow."""
    _mock_registry(gate, monkeypatch, 200, digest="sha256:../../evil")

    exists, _, digest = gate.manifest_exists("t")
    assert exists is True
    assert digest is None, "a malformed digest must not become the pin"


def test_main_makes_NO_network_call_when_the_registry_helpers_are_mocked(gate,
                                                                        monkeypatch):
    """main() must stay hermetic under mocking.

    An earlier cut of this change fetched one token eagerly in main() and threaded it to
    every callee, to collapse the run's repeated token round trips. That put a LIVE
    ghcr.io request into ~9 tests that mock every registry helper and were hermetic
    before - a 30s connect timeout each on a runner with no egress, and a silent walk-back
    of what tests/conftest.py exists to guarantee. Caught in review by reproducing it.

    The optimisation was dropped rather than papered over with more mocks: PCP-24348 had
    already declined it ("two round trips on a job that runs in 9s"), and item 2's real
    content - pinning the tag to a digest - never depended on it.

    A/B: restore `token, _ = ghcr_token()` at the top of main() and this goes red.
    """
    attempted = []

    def no_network(req, *a, **k):
        attempted.append(req if isinstance(req, str) else getattr(req, "full_url", req))
        raise AssertionError(f"main() reached the network: {attempted[-1]}")

    monkeypatch.setattr(gate.urllib.request, "urlopen", no_network)
    monkeypatch.setattr(gate, "manifest_exists",
                        lambda _tag: (True, "HTTP 200", DIGEST))
    monkeypatch.setattr(gate, "check_source_parity",
                        lambda _ref, _head: (True, "same tree"))
    monkeypatch.setattr(gate.sys, "argv", ["check-automation-image-tag.py"])

    assert gate.main() == 0
    assert attempted == [], f"expected no network, got {attempted}"


# --------------------------------------------------------------------------
# PCP-24359 items 3 & 4 — the build workflow
# --------------------------------------------------------------------------


def test_the_build_workflow_refuses_to_overwrite_a_published_tag(build_workflow):
    """Item 3. PCP-24348 argued that rebuilding 1.7.90 in place was not an option, then
    its own review rounds twice rebuilt a published 1.7.91 in place. The gate cannot see
    that - it re-resolves the tag, so a mutated artifact satisfies PARITY - so the refusal
    has to live in the workflow, and it has to be the DEFAULT."""
    assert "forceOverwrite" in build_workflow, "there must be an explicit opt-in"
    assert "Refuse to overwrite an existing tag" in build_workflow
    assert "docker buildx imagetools inspect" in build_workflow, \
        "the guard must actually ask the registry, not just declare an input"
    # Read the PARSED step, not a YAML substring. Pinning the exact text made
    # `if: github.event.inputs.forceOverwrite != 'true'` - valid Actions, behaviourally
    # identical - turn this red, as would a quote-style change. That is the substring-grep
    # shape this same PR replaces elsewhere, so it does not belong here either.
    yaml = pytest.importorskip("yaml")
    guard_step = [s for s in yaml.safe_load(build_workflow)["jobs"]["release-docker"]["steps"]
                  if s.get("name", "").startswith("Refuse to overwrite")][0]
    # The NEGATION is the point. `"forceOverwrite" in ...` alone also passes for
    # `== 'true'` - a guard wired backwards, running ONLY when forced, which is the very
    # failure this message names. Verified in review by running the substring test against
    # the inverted expression.
    guard_if = str(guard_step.get("if", ""))
    assert "forceOverwrite" in guard_if and "!=" in guard_if, \
        "the guard must RUN unless force is set - an unconditional step that only warns " \
        "would leave the default exactly as unsafe as before, and an `==` guard would " \
        f"run it only WHEN forced, which is the same hole inverted (got: {guard_if!r})"


def test_overwriting_is_opt_in_not_opt_out(build_workflow):
    """A `default: true` here would silently restore the behaviour item 3 is about, and
    every other assertion in this file would still pass."""
    guard = build_workflow.split("forceOverwrite:", 1)[1].split("jobs:", 1)[0]
    assert "default: false" in guard, "overwriting must be OFF by default"


IMAGE_BASE_FOR_TESTS = "ghcr.io/example/image"


def _workflow_step(name_prefix):
    """The parsed build-workflow step whose name starts with `name_prefix`."""
    yaml = pytest.importorskip("yaml")
    wf = (REPO_ROOT / ".github" / "workflows"
          / "docker-image-ghcr-build-push-public.yml")
    if not wf.is_file():
        pytest.skip("the GHCR build workflow is private-repo only")
    steps = yaml.safe_load(wf.read_text(encoding="utf-8"))["jobs"]["release-docker"]["steps"]
    match = [s for s in steps if s.get("name", "").startswith(name_prefix)]
    assert match, f"no step named {name_prefix!r} - this test is now vacuous"
    return match[0]


def _run_prepare_tags(tmp_path, tag_name):
    """Execute the REAL `Prepare tags` shell and return (rc, output, TAGS).

    `Prepare tags` is the single parser for `tagName`, and it was executed by no test at
    all - the guard harness hand-rolled its own `TAGS` in Python, which made it a THIRD
    parser for the same input (raised in review). So the empty-entry skip and the
    exit-1-when-nothing-usable path were both behaviour added without an executing test:
    breaking the trim here left every test in this file green.

    Reads `TAGS` back out of a temp $GITHUB_ENV, the way the runner hands it to the next
    step - so the guard below is fed by the step that actually produces its input.
    """
    import shutil
    import subprocess

    bash = shutil.which("bash")
    if not bash:
        pytest.skip("bash not available")

    step = _workflow_step("Prepare tags")
    script_file = tmp_path / "prepare_tags.sh"
    script_file.write_text(step["run"], encoding="utf-8")
    github_env = tmp_path / "github_env"
    github_env.write_text("", encoding="utf-8")

    proc = subprocess.run(
        [bash, str(script_file)], capture_output=True, text=True, timeout=60,
        env={"PATH": "/usr/bin:/bin", "TAG_NAME": tag_name,
             "IMAGE_BASE": IMAGE_BASE_FOR_TESTS, "GITHUB_ENV": str(github_env)})

    tags = ""
    for line in github_env.read_text(encoding="utf-8").splitlines():
        if line.startswith("TAGS="):
            tags = line[len("TAGS="):]
    return proc.returncode, proc.stdout + proc.stderr, tags


def test_prepare_tags_builds_the_refs_that_get_published(tmp_path):
    rc, out, tags = _run_prepare_tags(tmp_path, "1.7.92-auto-on-prem-jammy")
    assert rc == 0, out
    assert tags == f"{IMAGE_BASE_FOR_TESTS}:1.7.92-auto-on-prem-jammy"


def test_prepare_tags_trims_surrounding_whitespace(tmp_path):
    rc, out, tags = _run_prepare_tags(tmp_path, "  1.7.92-auto-on-prem-jammy  , latest ")
    assert rc == 0, out
    assert tags == (f"{IMAGE_BASE_FOR_TESTS}:1.7.92-auto-on-prem-jammy,"
                    f"{IMAGE_BASE_FOR_TESTS}:latest")


def test_prepare_tags_skips_an_empty_entry_instead_of_pushing_a_bare_base(tmp_path):
    """A trailing comma used to produce a bare `${IMAGE_BASE}:` in the push list."""
    rc, out, tags = _run_prepare_tags(tmp_path, "1.7.92-auto-on-prem-jammy,")
    assert rc == 0, out
    assert tags == f"{IMAGE_BASE_FOR_TESTS}:1.7.92-auto-on-prem-jammy"
    assert f"{IMAGE_BASE_FOR_TESTS}:," not in tags


def test_prepare_tags_fails_when_no_usable_tag_remains(tmp_path):
    """Publishing with an empty tag list is never what was meant."""
    rc, out, tags = _run_prepare_tags(tmp_path, "  ,  ")
    assert rc != 0, f"expected a hard failure, got rc=0 with TAGS={tags!r}\n{out}"
    assert "no usable tag" in out.lower()


def _run_overwrite_guard(tmp_path, tag_name, docker_stub):
    """Execute the guard step's REAL shell, with its REAL env:, and a stubbed `docker`.

    Substring assertions on the YAML cannot see the guard's actual behaviour - the
    fail-open version of this step satisfied every one of them (raised independently by
    two reviewers). So run the step body for real and observe what it decides.

    The step's `env:` is read from the workflow too, NOT hard-coded here. An earlier cut
    supplied MUTABLE_TAGS from a literal, so the script was the artifact under test but
    its configuration was a local COPY: adding `automation` (or any versioned prefix) to
    MUTABLE_TAGS in the workflow would have defeated the guard for exactly the tag it
    exists to protect while every test here stayed green. Both reviewers caught it, and
    it is the same self-agreeing-test shape this file is elsewhere about.

    `TAGS` is what "Prepare tags" exports, so it is built here the way that step builds
    it - full refs - because the guard now consumes those rather than re-parsing tagName.

    Returns (returncode, combined output).
    """
    import shutil
    import subprocess

    bash = shutil.which("bash")
    if not bash:
        pytest.skip("bash not available")

    wf = (REPO_ROOT / ".github" / "workflows"
          / "docker-image-ghcr-build-push-public.yml")
    if not wf.is_file():
        pytest.skip("the GHCR build workflow is private-repo only")

    yaml = pytest.importorskip("yaml")
    steps = yaml.safe_load(wf.read_text(encoding="utf-8"))["jobs"]["release-docker"]["steps"]
    guard = [s for s in steps if s.get("name", "").startswith("Refuse to overwrite")]
    assert guard, "the overwrite guard step is gone - this test is now vacuous"
    script = guard[0]["run"]

    # The step's OWN env:, minus the `${{ }}` expressions a runner would resolve.
    step_env = {k: str(v) for k, v in (guard[0].get("env") or {}).items()
                if "${{" not in str(v)}
    assert "MUTABLE_TAGS" in step_env, (
        "the guard's MUTABLE_TAGS carve-out must come from the workflow, not this test - "
        "otherwise widening it there cannot fail anything here")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "docker").write_text(docker_stub, encoding="utf-8")
    (bin_dir / "docker").chmod(0o755)

    script_file = tmp_path / "guard.sh"
    script_file.write_text(script, encoding="utf-8")

    # TAGS comes from the REAL `Prepare tags` step, not a Python re-implementation of it.
    # Hand-rolling it here made this harness a third parser for the same input - the exact
    # "the script is real but its input is a local copy" shape the MUTABLE_TAGS fix above
    # retired, one step upstream. Chaining them tests the whole tagName -> published-refs
    # path in one pass, the way the runner chains the two steps.
    rc, prep_out, refs = _run_prepare_tags(tmp_path, tag_name)
    assert rc == 0, f"Prepare tags failed for {tag_name!r}:\n{prep_out}"
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "TAGS": refs, **step_env}
    proc = subprocess.run([bash, str(script_file)], capture_output=True, text=True,
                          env=env, timeout=60)
    return proc.returncode, proc.stdout + proc.stderr


def test_the_guards_mutable_carve_out_is_read_from_the_workflow(tmp_path):
    """Pins the harness's own premise: the carve-out list must be the workflow's.

    A/B: hard-code MUTABLE_TAGS back into _run_overwrite_guard and add `automation` to
    the workflow's list - the guard is then defeated for automation tags in production
    while every other test in this file stays green. That is the exact hole this closes.
    """
    yaml = pytest.importorskip("yaml")
    wf = (REPO_ROOT / ".github" / "workflows"
          / "docker-image-ghcr-build-push-public.yml")
    if not wf.is_file():
        pytest.skip("the GHCR build workflow is private-repo only")
    steps = yaml.safe_load(wf.read_text(encoding="utf-8"))["jobs"]["release-docker"]["steps"]
    guard = [s for s in steps if s.get("name", "").startswith("Refuse to overwrite")][0]
    mutable = (guard.get("env") or {}).get("MUTABLE_TAGS", "")

    assert "latest" in mutable, "latest must stay carved out - it is the runtime image"
    # The automation image line must NOT be carved out, or the guard protects nothing
    # that matters.
    assert "auto-on-prem-jammy" not in mutable
    assert "automation" not in mutable


# A stub that reports the tag exists.
_DOCKER_FOUND = '#!/bin/bash\necho "sha256:abc123"\nexit 0\n'
# A stub that reports the tag genuinely absent, the way the registry words it.
_DOCKER_ABSENT = ('#!/bin/bash\n'
                  'echo "ERROR: docker.io/example/image:x: not found" >&2\nexit 1\n')
# A stub that fails for a reason that is NOT "absent" - a network/auth/rate-limit blip.
_DOCKER_BROKEN = ('#!/bin/bash\n'
                  'echo "error during connect: dial tcp: i/o timeout" >&2\nexit 1\n')


def test_the_guard_blocks_when_the_tag_already_exists(tmp_path):
    rc, out = _run_overwrite_guard(tmp_path, "1.7.92-auto-on-prem-jammy", _DOCKER_FOUND)
    assert rc == 1, out
    assert "refusing to overwrite" in out.lower()


def test_the_guard_allows_a_genuinely_absent_tag(tmp_path):
    """The control: if this went red the guard would block every legitimate build."""
    rc, out = _run_overwrite_guard(tmp_path, "1.7.92-auto-on-prem-jammy", _DOCKER_ABSENT)
    assert rc == 0, out
    assert "safe to publish" in out.lower()


def test_a_registry_ERROR_does_not_read_as_absent(tmp_path):
    """THE fail-open regression, found independently by two reviewers.

    `imagetools inspect` exits non-zero for a missing tag AND for DNS/TLS/5xx/429/auth
    failures alike. The first cut used it as a bare `if`, so any blip landed in the
    "no existing tag - safe to publish" branch and let through the very overwrite this
    step exists to prevent - worst precisely when the registry is flaky, which is the
    likeliest reason someone re-dispatches a build.

    A/B: restore `if docker buildx imagetools inspect ... >/dev/null 2>&1` and this goes
    red (rc 0, "safe to publish") while every substring assertion in this file stays green.
    """
    rc, out = _run_overwrite_guard(tmp_path, "1.7.92-auto-on-prem-jammy", _DOCKER_BROKEN)
    assert rc == 1, f"an indeterminate registry answer must NOT permit the publish:\n{out}"
    assert "could not determine" in out.lower()
    assert "safe to publish" not in out.lower()


def test_the_guard_skips_deliberately_mutable_tags(tmp_path):
    """`latest` is this workflow's DEFAULT input and the repo's documented runtime image
    (README.md, docs/design/README.md, dev/platform-provisioner.sh). Guarding it would
    hard-fail every routine publish and train an automatic forceOverwrite reflex - which
    would then be ticked on the automation tag too."""
    rc, out = _run_overwrite_guard(tmp_path, "latest", _DOCKER_FOUND)
    assert rc == 0, out
    assert "mutable" in out.lower()


def test_every_tag_in_a_comma_separated_list_is_checked(tmp_path):
    """The input accepts multiple tags; checking only the first would leave a hole."""
    rc, out = _run_overwrite_guard(tmp_path, "latest, 1.7.92-auto-on-prem-jammy",
                                   _DOCKER_FOUND)
    assert rc == 1, out
    assert "1.7.92-auto-on-prem-jammy" in out


def test_no_dispatch_input_is_interpolated_into_any_run_script(build_workflow):
    """Actions substitutes `${{ }}` BEFORE bash parses, so an inlined dispatch input is a
    command-injection sink in a runner holding the registry push credential.

    Asserted across EVERY `run:` in the workflow, not just the guard. A reviewer pointed
    out that the first cut fixed the new step while `Prepare tags` two steps above still
    inlined the same `tagName` - so the PR that establishes the rule left the
    counter-example next to it, which is what the next person copies. Values reach a
    script through `env:` instead.
    """
    yaml = pytest.importorskip("yaml")
    jobs = yaml.safe_load(build_workflow)["jobs"]

    offenders = []
    # EVERY job, not just release-docker: hardcoding the job name silently exempts any
    # job added later from the rule this test is the only thing enforcing.
    for job_name, job in jobs.items():
        for step in job.get("steps", []):
            script = step.get("run")
            if not script:
                continue
            for line in script.splitlines():
                # Search INSIDE `${{ }}` only - that is the substitution sink. Matching the
                # raw line flagged a comment that merely NAMES an input, so a comment
                # explaining this rule would have broken it.
                #
                # `\binputs\s*(\.|\[)` covers every spelling that expands before bash: the
                # long `github.event.inputs.x` and the short `inputs.x` (the form GitHub's
                # current docs favour), dotted or bracket-indexed - `inputs['x']` is the
                # same sink and a bare `\binputs\.` missed it. The long form needs no
                # separate check: the `.` before `inputs` is a word boundary.
                for expr in re.findall(r"\$\{\{(.*?)\}\}", line):
                    if re.search(r"\binputs\s*(\.|\[)", expr):
                        offenders.append(
                            f"{job_name} / {step.get('name', '?')}: {line.strip()}")

    assert not offenders, (
        "dispatch inputs must reach a run: script via env:, not `${{ }}`:\n  "
        + "\n  ".join(offenders))


def test_the_build_workflow_records_what_it_published(build_workflow):
    """Item 4. Nothing interlocks the dispatch against a later push, so the build cannot
    guarantee ordering - but it can make the outcome answerable without a gate re-run,
    which is the step that was skipped on PR #443."""
    assert "Record what was published" in build_workflow
    assert "GITHUB_STEP_SUMMARY" in build_workflow
    assert "Built from commit" in build_workflow, \
        "the summary must name the COMMIT - the tag alone is what was already ambiguous"
