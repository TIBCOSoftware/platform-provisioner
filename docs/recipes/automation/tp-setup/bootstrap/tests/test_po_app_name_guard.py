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
# Regression tests for PCP-20157 — springboot_provision_connector passed
# app_name=None to is_app_created, causing a Playwright strict-mode violation
# (has_text=None applies no filter -> locator resolves to every app row ->
# is_visible() throws when >=2 rows exist).
#
# Two fixes are covered:
#   1. po_dataplane.is_app_created defensively returns False on a falsy app_name
#      without ever touching the page locator (so any future None caller is safe).
#   2. po_dp_springboot.springboot_provision_connector defaults the name to
#      ENV.SPRINGBOOT_APP_NAME (the root cause), so the existence check downstream
#      receives the real app name instead of None.

from unittest.mock import MagicMock

import pytest

from page_object.po_dataplane import PageObjectDataPlane
from page_object.po_dp_springboot import PageObjectDataPlaneSpringBoot
from utils.env import ENV
from utils.report import ReportYaml


def _new(cls):
    """Build a page object without running __init__ (no browser needed)."""
    obj = object.__new__(cls)
    obj.page = MagicMock()
    return obj


class TestIsAppCreatedGuard:
    def test_none_app_name_returns_false_without_locator(self):
        po = _new(PageObjectDataPlane)
        assert po.is_app_created("sb", None) is False
        # The guard must short-circuit before any locator query, otherwise
        # has_text=None would trigger the strict-mode violation.
        po.page.locator.assert_not_called()

    def test_empty_app_name_returns_false_without_locator(self):
        po = _new(PageObjectDataPlane)
        assert po.is_app_created("sb", "") is False
        po.page.locator.assert_not_called()


class _Stop(Exception):
    """Sentinel to halt the method right after the app-existence check."""


class TestSpringbootProvisionConnectorDefault:
    def test_defaults_app_name_to_env(self, monkeypatch):
        po = _new(PageObjectDataPlaneSpringBoot)  # capability = "sb" (class attr)

        # Not previously provisioned -> no early return.
        monkeypatch.setattr(ReportYaml, "get_capability_info", lambda *a, **k: "")

        captured = {}

        def fake_report_is_app_created(dp_name, capability, app_name):
            captured["report_app"] = app_name
            return False

        monkeypatch.setattr(ReportYaml, "is_app_created", fake_report_is_app_created)
        po.is_app_created = MagicMock(return_value=False)
        # Stop execution once both existence checks have run with the resolved name.
        po.goto_capability = MagicMock(side_effect=_Stop())

        with pytest.raises(_Stop):
            po.springboot_provision_connector("k8s-auto-dp1")  # no app_name passed

        # Both existence checks must receive the defaulted name, never None.
        assert captured["report_app"] == ENV.SPRINGBOOT_APP_NAME
        po.is_app_created.assert_called_once_with("sb", ENV.SPRINGBOOT_APP_NAME)
