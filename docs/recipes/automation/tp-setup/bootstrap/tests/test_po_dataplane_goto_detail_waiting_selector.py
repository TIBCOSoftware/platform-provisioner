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
# PCP-24228 (secondary defect) - goto_dataplane's detail-page retry cancelled itself out.
#
# Util.refresh_until_success(page, retry_selector, waiting_selector) reloads the page and then
# does waiting_selector.wait_for(state="visible"): the waiting selector is meant to be the page
# CONTAINER, i.e. the proof that the reload finished, while retry_selector is the thing being
# looked for. goto_dataplane passed the SAME locator as both, so the helper waited - at the 30s
# Playwright default - on the very element whose absence triggered the retry, and THREW instead
# of returning False. The list-page call 13 lines earlier had it right all along
# (retry '.data-plane-name', wait '.data-planes-content').

from unittest.mock import MagicMock

import pytest

from page_object.po_dataplane import PageObjectDataPlane
from utils.util import Util

DP = "k8s-auto-dp1"
DETAIL_CONTAINER = ".data-plane-container"
LIST_CONTAINER = ".data-planes-content"


class Loc:
    """A locator that remembers how it was created, so a call can be identified by selector."""

    def __init__(self, selector, has_text=None):
        self.selector = selector
        self.has_text = has_text

    def __getattr__(self, _name):
        return MagicMock()


@pytest.fixture(autouse=True)
def hermetic_report(monkeypatch):
    """goto_dataplane reaches ReportYaml.set_dataplane on the success path, which shells out to
    `yq` and writes report/report.yaml. Left unpatched these tests mutate the working tree and
    ERROR on any machine without yq on PATH - utils/report.py only catches CalledProcessError,
    not FileNotFoundError. Every other suite here patches it; tests/conftest.py exists for
    exactly this reason."""
    monkeypatch.setattr("page_object.po_dataplane.ReportYaml", MagicMock())


@pytest.fixture
def calls(monkeypatch):
    recorded = []

    def fake_refresh_until_success(page, retry_selector, waiting_selector, message="", max_retries=3):
        recorded.append((retry_selector, waiting_selector))
        return True

    monkeypatch.setattr(Util, "refresh_until_success", staticmethod(fake_refresh_until_success))
    monkeypatch.setattr(Util, "exit_error",
                        staticmethod(lambda message, page=None, filename="": pytest.fail(message)))
    return recorded


def _po():
    po = object.__new__(PageObjectDataPlane)
    po.page = MagicMock()
    po.page.locator.side_effect = lambda selector, **kwargs: Loc(selector, kwargs.get("has_text"))
    po.is_fresco = True
    po.goto_left_navbar_dataplane = lambda: None
    return po


class TestDetailPageRetry:
    def test_waiting_selector_is_a_container_distinct_from_the_retry_target(self, calls):
        po = _po()
        po.page.locator.side_effect = lambda selector, **kwargs: Loc(selector, kwargs.get("has_text"))

        po.goto_dataplane(DP)

        assert len(calls) == 2, "list page then detail page"
        retry, waiting = calls[1]
        assert retry.selector != waiting.selector, \
            "waiting on the retry target makes the retry wait for what it is retrying for"
        assert waiting.selector == DETAIL_CONTAINER
        assert waiting.has_text is None, "a container proves the reload finished; it is not name-scoped"

    def test_retry_target_still_identifies_the_named_data_plane(self, calls):
        po = _po()

        po.goto_dataplane(DP)

        retry, _ = calls[1]
        assert retry.has_text == DP

    def test_list_page_call_keeps_its_own_container(self, calls):
        # The correct usage this fix copies - it must not be disturbed.
        po = _po()

        po.goto_dataplane(DP)

        retry, waiting = calls[0]
        assert waiting.selector == LIST_CONTAINER
        assert retry.selector != waiting.selector
