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
# log index; Metrics (prometheus / es-no-log) and Traces (es-no-headers) must not.
#
# PCP-21434: the wire key is the HYPHENATED "log-index". Both paths now build the
# value through utils.helper.o11y_log_index so the three-way branch rule lives in
# one place instead of being spelled out twice in two different vocabularies.

from unittest.mock import MagicMock, patch

import pytest

from api_object.resources import OllyApi, _WIZARD_RESOURCES, _build_payload
from utils.helper import (
    O11Y_LOG_INDEX_BUSINESS_ACTIVITIES,
    O11Y_LOG_INDEX_DEFAULT,
    O11Y_LOG_INDEX_USER_APPS,
    o11y_log_index,
)
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


def test_build_payload_es_log_uses_the_hyphenated_key():
    """PCP-21434: the CP elasticSearchSchema property is 'log-index', not 'logIndex'.

    A/B against a live CP 1.21: posting 'log-index' persists the value, posting
    'logIndex' is silently dropped (HTTP 201, stored index None). The camelCase
    spelling must never come back.
    """
    body = _build_payload("user-app-global-logs-qsqs-1", "es-log", "elastic",
                          "user-app-global-log-index")
    assert body["log-index"] == "user-app-global-log-index"
    assert "logIndex" not in body


def test_build_payload_non_es_log_has_no_log_index():
    for kind in ("es-no-log", "es-no-headers", "prom-exporter"):
        body = _build_payload("n", kind, "elastic", "user-app-global-log-index")
        assert "log-index" not in body, f"{kind} must not carry a log index"
        assert "logIndex" not in body, f"{kind} must not carry a log index"


def test_global_scope_log_indexes_match_the_ui_wizard():
    """The three-way rule, verified against a CP 1.21 subscription whose resources
    were created by the UI wizard. Services Exporter genuinely falls through to the
    resource name — a wizard quirk that is mirrored, not fixed."""
    client, posted = _client_no_existing()
    OllyApi(client).create_o11y_resources("global")
    by_type = {path.rsplit("/", 1)[-1]: p for path, p in posted}
    assert by_type["LOGS_PRX_UA_ES"]["log-index"] == "user-app-global-log-index"
    assert by_type["LOGS_EXP_UA_ES"]["log-index"] == "user-app-global-log-index"
    assert by_type["LOGS_PRX_AS_ES"]["log-index"] == "user-app-global-ba-log-index"
    assert by_type["LOGS_EXP_AS_ES"]["log-index"] == "user-app-global-ba-log-index"
    assert by_type["LOGS_EXP_SRV_ES"]["log-index"] == "user-app-global-logs-ese-1"


def test_dp_scope_is_refused():
    """PCP-23553 regression guard, at the only layer that can still reach it.

    A data plane must be SWITCHED to the Global resource, never given its own set.
    The old DP-scoped branch is deleted rather than guarded, and this pins that it
    stays deleted: `create_o11y_resources` used to accept a DP name and happily
    create a second, DP-local set — the exact silent degradation that has regressed
    three times.
    """
    client, posted = _client_no_existing()
    with pytest.raises(ValueError, match="Global scope"):
        OllyApi(client).create_o11y_resources("k8s-auto-dp1")
    assert posted == [], "nothing may be POSTed on the refused path"


def test_metrics_and_traces_carry_no_log_index():
    client, posted = _client_no_existing()
    OllyApi(client).create_o11y_resources("global")
    # 9 wizard resources posted; exactly 5 (the es-log Logs ones) carry a log index.
    assert len(posted) == 9
    with_index = [p for _, p in posted if "log-index" in p]
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


# ---------------------------------------------------------------------------
# The shared rule itself. Both paths above delegate here, so this is the one
# place the three branches are pinned as a table.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("branch,dp_title,name,expected", [
    (O11Y_LOG_INDEX_USER_APPS,           "Global",        "x", "user-app-global-log-index"),
    (O11Y_LOG_INDEX_BUSINESS_ACTIVITIES, "Global",        "x", "user-app-global-ba-log-index"),
    (O11Y_LOG_INDEX_DEFAULT,             "Global",        "global-logs-ese-1", "user-app-global-logs-ese-1"),
    (O11Y_LOG_INDEX_USER_APPS,           "k8s-auto-dp1",  "x", "user-app-k8s-auto-dp1-log-index"),
    (O11Y_LOG_INDEX_BUSINESS_ACTIVITIES, "K8s-Auto-DP1",  "x", "user-app-k8s-auto-dp1-ba-log-index"),
])
def test_o11y_log_index_rule(branch, dp_title, name, expected):
    assert o11y_log_index(branch, dp_title, name) == expected


def test_ui_and_api_agree_on_every_logs_resource():
    """Parity guard. The UI keys the branch off the sub-tab name and the API off the
    resource type; if either mapping drifts, the two paths silently produce different
    indexes for the same resource. Assert the two tables agree, resource by resource."""
    ui_subtab_for_type = {
        "LOGS_PRX_UA_ES":  "Query Service",
        "LOGS_EXP_UA_ES":  "User Apps Exporter",
        "LOGS_EXP_SRV_ES": "Services Exporter",
        "LOGS_PRX_AS_ES":  "Business Activities Query Service",
        "LOGS_EXP_AS_ES":  "Business Activities Exporter",
    }
    for rtype, suffix, kind, _backend, branch in _WIZARD_RESOURCES:
        if kind != "es-log":
            assert branch is None, f"{rtype} carries no log index but declares branch {branch!r}"
            continue
        name = "global-" + suffix
        api_value = o11y_log_index(branch, "Global", name)
        ui_value = _ui_log_index(
            PageObjectDataPlaneConfiguration, "page_object.po_dp_config.Util",
            "Logs", "Query Service", ui_subtab_for_type[rtype], name, "Global")
        assert api_value == ui_value, f"{rtype}: API {api_value!r} != UI {ui_value!r}"
