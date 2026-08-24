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
# Tests for the CLI/API o11y resource creation log index (api_object/resources.py).
#
# Requirement: every log index created by the CLI path must carry the fixed
# "user-app-" prefix (kept in sync with the UI path in
# page_object/po_dp_config.py / po_bmdp_config.py). Only the ElasticSearch
# "es-log" resources (the 5 Logs query-service / exporter resources) carry a
# logIndex; Metrics (prometheus / es-no-log) and Traces (es-no-headers) must not.

from unittest.mock import MagicMock, patch

import pytest

from api_object.resources import OllyApi, _build_payload
from page_object.po_dp_config import PageObjectDataPlaneConfiguration
from page_object.po_bmdp_config import PageObjectBMDPConfiguration


def _client_no_existing():
    """A ConsoleApiClient stub where nothing exists yet (so every resource is
    created) and POST records the payloads it was called with."""
    client = MagicMock()
    client.get.return_value = {"response": []}          # existing_by_name -> {}
    client.list_dataplanes.return_value = [{"id": "dp-1", "name": "k8s-auto-dp1"}]
    posted = []

    def fake_post(path, payload):
        posted.append((path, payload))
        return {"response": {"id": f"id-{len(posted)}"}}

    client.post.side_effect = fake_post
    return client, posted


def test_build_payload_es_log_uses_given_log_index():
    body = _build_payload("user-app-global-logs-qsqs-1", "es-log", "elastic",
                          "user-app-global-log-index")
    assert body["logIndex"] == "user-app-global-log-index"


def test_build_payload_non_es_log_has_no_log_index():
    for kind in ("es-no-log", "es-no-headers", "prom-exporter"):
        body = _build_payload("n", kind, "elastic", "user-app-global-log-index")
        assert "logIndex" not in body, f"{kind} must not carry a logIndex"


def test_global_scope_prefixes_log_index_with_user_app():
    client, posted = _client_no_existing()
    OllyApi(client).create_o11y_resources("global")
    log_indexes = [p["logIndex"] for _, p in posted if "logIndex" in p]
    # the 5 es-log Logs resources each carry the prefixed index
    assert len(log_indexes) == 5
    assert all(li == "user-app-global-log-index" for li in log_indexes), log_indexes


def test_dp_scope_prefixes_log_index_with_user_app():
    client, posted = _client_no_existing()
    OllyApi(client).create_o11y_resources("k8s-auto-dp1")
    log_indexes = [p["logIndex"] for _, p in posted if "logIndex" in p]
    assert len(log_indexes) == 5
    assert all(li == "user-app-k8s-auto-dp1-log-index" for li in log_indexes), log_indexes


def test_metrics_and_traces_carry_no_log_index():
    client, posted = _client_no_existing()
    OllyApi(client).create_o11y_resources("global")
    # 9 wizard resources posted; exactly 5 (the es-log Logs ones) carry logIndex.
    assert len(posted) == 9
    with_index = [p for _, p in posted if "logIndex" in p]
    assert len(with_index) == 5


# ---------------------------------------------------------------------------
# UI-wizard path: o11y_new_resource_fill_form must also apply the user-app- prefix
# to the value filled into #log-index-input (parity with the CLI/API path above).
# Covers both po_dp_config and the identical method in po_bmdp_config.
# ---------------------------------------------------------------------------

def _ui_log_index(cls, util_module, menu, tab, sub, name, dp):
    """Drive o11y_new_resource_fill_form with a MagicMock page and return the value
    passed to page.fill('#log-index-input', ...) (None if it was never filled)."""
    po = object.__new__(cls)
    po.page = MagicMock()
    po.o11y_fill_prometheus_or_elastic = MagicMock()   # stub the endpoint/cred fill
    with patch(util_module, MagicMock()):              # Util.exit_error / check_dom_visibility no-op
        po.o11y_new_resource_fill_form(menu, tab, sub, name, dp)
    for c in po.page.fill.call_args_list:
        if c.args and c.args[0] == "#log-index-input":
            return c.args[1]
    return None


@pytest.mark.parametrize("cls,util_mod", [
    (PageObjectDataPlaneConfiguration, "page_object.po_dp_config.Util"),
    (PageObjectBMDPConfiguration, "page_object.po_bmdp_config.Util"),
])
class TestUiLogIndexPrefix:
    def test_user_apps_query_service_prefixed(self, cls, util_mod):
        li = _ui_log_index(cls, util_mod, "Logs", "Query Service", "Query Service",
                           "global-logs-qsqs-1", "Global")
        assert li == "user-app-global-log-index"

    def test_business_activities_prefixed(self, cls, util_mod):
        li = _ui_log_index(cls, util_mod, "Logs", "Query Service",
                           "Business Activities Query Service", "x", "Global")
        assert li == "user-app-global-ba-log-index"

    def test_default_name_still_prefixed(self, cls, util_mod):
        # Services Exporter matches neither the User-Apps nor the BA branch, so
        # log_index defaults to name_input — the prefix must still be applied.
        li = _ui_log_index(cls, util_mod, "Logs", "Exporter", "Services Exporter",
                           "global-logs-ese-1", "Global")
        assert li == "user-app-global-logs-ese-1"
