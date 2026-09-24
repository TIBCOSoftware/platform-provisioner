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
# PCP-24379: the tester-on-prem image pinned tibcop 1.9.0-alpha.2046 while the automation
# targets the 1.21 command surface. 1.9 -> 1.21 added ~150 commands and removed none, so
# an out-of-date CLI never fails at startup — it fails deep inside a run with "command not
# found" on the first 1.21-only subcommand, which reads like a platform bug and gets
# triaged as one.
#
# The failure mode this guards is specifically a stale BASE image: the Automation Hub
# Dockerfile installs no tibcop of its own, it inherits whatever the
# <ver>-tester-on-prem-jammy base shipped. Bumping TIBCOP_TAG without rebuilding and
# re-pointing that FROM leaves the Hub on the old CLI with nothing to say so.
#
# These tests pin the startup assertion: version is parsed from the real `--version`
# banner shape, an older CLI aborts before any command runs, and a missing binary is
# reported as a missing binary rather than as an unparseable version.
#
# Pure subprocess-boundary logic — no cluster, no browser, no real tibcop needed.

import re
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cli_object.base import TIBCOP_MIN_VERSION, TibcopBase


BANNER = "@tibco/tp-cli/1.21.0 linux-x64 node-v20.11.1"


@pytest.fixture(autouse=True)
def _clear_version_cache():
    """get_version caches on the class, so leakage between tests is a real hazard.

    The cache is a dict keyed by cli_path since PCP-24380 (it used to be a single
    `_version` slot, which answered a question about binary A with the version of
    binary B once facade.py started passing an explicit path).
    """
    TibcopBase._versions.clear()
    yield
    TibcopBase._versions.clear()


def _run_result(stdout="", stderr=""):
    return MagicMock(stdout=stdout, stderr=stderr, returncode=0)


def test_version_parsed_from_the_real_banner():
    with patch("cli_object.base.subprocess.run", return_value=_run_result(BANNER)):
        assert TibcopBase.get_version() == "1.21.0"


def test_version_read_from_stderr_too():
    """oclif has shipped the banner on both streams; neither placement is an error."""
    with patch("cli_object.base.subprocess.run", return_value=_run_result(stderr=BANNER)):
        assert TibcopBase.get_version() == "1.21.0"


def test_version_probed_only_once():
    run = MagicMock(return_value=_run_result(BANNER))
    with patch("cli_object.base.subprocess.run", run):
        TibcopBase.get_version()
        TibcopBase.get_version()
    run.assert_called_once()


def test_alpha_suffix_survives_parsing():
    """A pre-release build must still satisfy the check, not trip the int() parse."""
    banner = "@tibco/tp-cli/1.21.0-alpha.1080 linux-x64 node-v20.11.1"
    with patch("cli_object.base.subprocess.run", return_value=_run_result(banner)):
        assert TibcopBase.assert_min_version() == "1.21.0-alpha.1080"


def test_current_minimum_is_satisfied_by_121():
    with patch("cli_object.base.subprocess.run", return_value=_run_result(BANNER)):
        assert TibcopBase.assert_min_version(minimum=TIBCOP_MIN_VERSION) == "1.21.0"


def test_older_cli_aborts_before_any_command_runs():
    """The 1.9.0 the on-prem image used to pin. Must fail here, not mid-run."""
    banner = "@tibco/tp-cli/1.9.0 linux-x64 node-v20.11.1"
    with patch("cli_object.base.subprocess.run", return_value=_run_result(banner)):
        with pytest.raises(RuntimeError, match="found 1.9.0"):
            TibcopBase.assert_min_version()


def test_minor_version_compared_numerically_not_lexically():
    """'1.9' > '1.21' as strings — the exact trap this bump walks into."""
    banner = "@tibco/tp-cli/1.9.0 linux-x64 node-v20.11.1"
    with patch("cli_object.base.subprocess.run", return_value=_run_result(banner)):
        assert TibcopBase.get_version() == "1.9.0"
    TibcopBase._versions.clear()
    with patch("cli_object.base.subprocess.run", return_value=_run_result(banner)):
        with pytest.raises(RuntimeError):
            TibcopBase.assert_min_version(minimum=(1, 21))


def test_missing_binary_reported_as_missing():
    with patch("cli_object.base.subprocess.run", side_effect=FileNotFoundError("nope")):
        assert TibcopBase.get_version() is None
    with patch("cli_object.base.subprocess.run", side_effect=FileNotFoundError("nope")):
        with pytest.raises(RuntimeError, match="could not be determined"):
            TibcopBase.assert_min_version()


def test_probe_timeout_does_not_hang_the_run():
    err = subprocess.TimeoutExpired(cmd="tibcop", timeout=120)
    with patch("cli_object.base.subprocess.run", side_effect=err):
        with pytest.raises(RuntimeError, match="could not be determined"):
            TibcopBase.assert_min_version()


def test_unparseable_output_is_not_treated_as_a_pass():
    with patch("cli_object.base.subprocess.run", return_value=_run_result("garbage")):
        with pytest.raises(RuntimeError, match="could not be determined"):
            TibcopBase.assert_min_version()


def test_failed_probe_is_not_cached():
    """A transient failure must not poison every later call in the process."""
    with patch("cli_object.base.subprocess.run", side_effect=OSError("transient")):
        assert TibcopBase.get_version() is None
    with patch("cli_object.base.subprocess.run", return_value=_run_result(BANNER)):
        assert TibcopBase.get_version() == "1.21.0"


def test_the_cache_is_keyed_by_path(monkeypatch):
    """PCP-24380 ride-along. The cache used to be a single `_version` slot while the probe
    takes a cli_path, so once facade.py started passing self.base.TIBCOP_CLI_PATH one
    binary's version could answer a question about another - silently, and only on a
    machine where the two differ, which is the machine the assertion exists for."""
    banners = {"/opt/old/tibcop": "@tibco/tp-cli/1.9.0 linux-x64",
               "/opt/new/tibcop": "@tibco/tp-cli/1.21.0 linux-x64"}

    def fake_run(argv, *_a, **_kw):
        return _run_result(banners[argv[0]])

    with patch("cli_object.base.subprocess.run", fake_run):
        assert TibcopBase.get_version("/opt/old/tibcop") == "1.9.0"
        assert TibcopBase.get_version("/opt/new/tibcop") == "1.21.0"
        # ... and each is still cached, i.e. keying by path did not disable caching.
        assert TibcopBase.get_version("/opt/old/tibcop") == "1.9.0"


def test_the_facade_probes_the_binary_it_will_actually_run():
    """assert_min_version() defaults cli_path to the literal "tibcop" while every command
    is built from self.base.TIBCOP_CLI_PATH. Passing the path explicitly is what stops the
    assertion vouching for a binary nobody runs."""
    import inspect

    from cli_object.facade import TibcopCLI

    src = inspect.getsource(TibcopCLI.__init__)
    assert "assert_min_version(cli_path=self.base.TIBCOP_CLI_PATH)" in src, (
        "the version assertion must probe self.base.TIBCOP_CLI_PATH, not the default")


# ---------------------------------------------------------------------------
# TIBCOP_MIN_VERSION vs the Dockerfile that installs the binary
# ---------------------------------------------------------------------------
# PCP-24380 ride-along (PR #446 review item b). Two pins, in two repos-worth of file
# tree, with nothing between them: `TIBCOP_MIN_VERSION` here and `ARG TIBCOP_TAG` in
# docker/Dockerfile-tester-on-prem. They drift SILENTLY in both directions - an image
# built with an older tibcop fails every run at startup (loud, but only after the image
# is published), and raising the ARG without raising the floor means the automation can
# start using newer commands with no assertion protecting the people still on the old
# base. The whole point of PCP-24379's startup assertion was that this chain had no
# guard; leaving its own two ends ungraded would be the same mistake one level up.


def _repo_root():
    """Walk up to the checkout root rather than counting parents - this file sits six
    levels down and a hard-coded index breaks the moment the tree is reorganised."""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / ".github").is_dir():
            return candidate
    raise RuntimeError("could not locate the repository root")


def _tibcop_tag():
    """The tibcop version the on-prem tester image installs, or a skip.

    Skipped rather than failed when the file is absent: `tests/` is synced to the public
    mirror and runs inside the automation image, neither of which necessarily carries the
    repository's `docker/` directory. A test that cannot see its subject must say so, not
    pass quietly - but it must not turn a green private CI red elsewhere either.
    """
    dockerfile = _repo_root() / "docker" / "Dockerfile-tester-on-prem"
    if not dockerfile.is_file():
        pytest.skip(f"{dockerfile} is not present in this checkout")
    match = re.search(r'^ARG\s+TIBCOP_TAG="([^"]+)"',
                      dockerfile.read_text(encoding="utf-8"), re.MULTILINE)
    assert match, f"no `ARG TIBCOP_TAG=\"...\"` in {dockerfile} - the pin was renamed or removed"
    return match.group(1)


def test_the_image_installs_a_tibcop_that_satisfies_the_floor():
    """The direction that breaks a deploy: an image whose tibcop is below the floor fails
    TibcopCLI.__init__ on every entry point, in a container nobody can edit."""
    tag = _tibcop_tag()
    installed = tuple(int(part) for part in tag.split(".")[:2])
    assert installed >= tuple(TIBCOP_MIN_VERSION), (
        f"docker/Dockerfile-tester-on-prem installs tibcop {tag}, below the "
        f"TIBCOP_MIN_VERSION floor of {'.'.join(str(p) for p in TIBCOP_MIN_VERSION)}. "
        "Every run in that image would abort at startup.")


def test_the_floor_is_not_left_behind_by_the_image():
    """The quieter direction. Raising TIBCOP_TAG without raising the floor lets the
    automation adopt newer commands while the assertion still passes for anyone on an
    older base - which is precisely the 'fails deep inside a run with command not found'
    failure PCP-24379 added the assertion to prevent.

    Major.minor only: an alpha build of the same minor is the same command surface, and
    demanding an exact match would make every routine alpha bump a two-file edit for no
    safety gain.
    """
    tag = _tibcop_tag()
    installed = tuple(int(part) for part in tag.split(".")[:2])
    assert installed == tuple(TIBCOP_MIN_VERSION), (
        f"docker/Dockerfile-tester-on-prem installs tibcop {tag} but TIBCOP_MIN_VERSION is "
        f"{'.'.join(str(p) for p in TIBCOP_MIN_VERSION)}. Raise the floor in "
        "cli_object/base.py in the same change, or the assertion guards nothing for anyone "
        "still on the older base image.")
