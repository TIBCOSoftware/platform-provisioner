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
# Tests for api_object/o11y_console.py — the Console-API path that creates the Global
# observability configuration and links data planes to it (PCP-21542 workaround).
#
# Every expectation here was measured against a live CP 1.21.0-alpha.129; the cases are
# written around the traps that measurement exposed, because each of them fails SILENTLY
# on the wire (HTTP 200 + wrong state) rather than raising:
#
#   * a pillar template taken from an existing instance carries TP1.<ciphertext> as the
#     password, which the server then encrypts a SECOND time -> a credential that looks
#     valid and cannot authenticate;
#   * METRICS_PRX_PROM / METRICS_EXP_PROM each have TWO subscription-scope instances, so
#     indexing pillars by resource_id points the stack at the wrong prometheus;
#   * the CP allows several O11YV3 stacks at one scope, so a missed idempotency check
#     duplicates the stack instead of erroring;
#   * capabilityType is the link state, so reading it back to decide link state is
#     circular;
#   * the PLATFORM and INFRA capability recipes are different documents.

import json
from unittest.mock import MagicMock

import pytest

from api_object.client import ConsoleApiError
from api_object.o11y_console import (
    O11yConsoleApi,
    O11yConsoleError,
    O11yDataPlaneUnreachable,
)

SCOPE_ID = "sub-1"
STACK_ID = "stack-1"
DP_ID = "dp-1"

# One registry entry, shaped like the real GET /cp/v1/resources rows: the fillable
# leaves are null and the constants are pre-set.
def _registry_entry(resource_id, with_log_index=True):
    fields = [
        {"key": "config.proxy.userApps.elasticSearch.endpoint", "value": None},
        {"key": "config.proxy.userApps.elasticSearch.username", "value": None},
        {"key": "secret.proxy.userApps.elasticSearch.password", "value": None},
        {"key": "secret.proxy.userApps.elasticSearch.headers", "dataType": "map", "value": None},
        {"key": "config.proxy.userApps.enabled", "value": True},
        {"key": "config.proxy.userApps.kind", "value": "elasticSearch"},
    ]
    if with_log_index:
        fields.insert(0, {"key": "config.proxy.userApps.elasticSearch.logIndex", "value": None})
    return {
        "resource_id": resource_id,
        "resource_metadata": {"fields": [
            {"key": "x", "value": {"elasticSearch": {"fields": fields}}}]},
    }


_ES_LOG_TYPES = {"LOGS_PRX_UA_ES", "LOGS_EXP_UA_ES", "LOGS_EXP_SRV_ES",
                 "LOGS_PRX_AS_ES", "LOGS_EXP_AS_ES"}
_ALL_TYPES = _ES_LOG_TYPES | {"METRICS_PRX_PROM", "METRICS_EXP_PROM",
                              "TRACES_PRX_ES", "TRACES_EXP_ES"}


class FakeClient:
    """A ConsoleApiClient stand-in that answers the reads this module makes and records
    every write. Stateful on purpose: `existing` drives the idempotency paths."""

    def __init__(self, existing=None, stacks=(), linked_ids=()):
        self.existing = existing or {}          # resource_id -> [ {name, id}, ... ]
        self.stacks = list(stacks)
        self.linked_ids = list(linked_ids)
        self.posts = []
        self.puts = []
        self.gets = []
        self.next_id = iter(f"new-{i}" for i in range(1, 100))

    # --- reads ---
    def get(self, path, params=None):
        self.gets.append(path)
        if path.startswith("/cp/v1/resources?") or path == "/cp/v1/resources":
            return {"data": [_registry_entry(t, t in _ES_LOG_TYPES) for t in _ALL_TYPES]}
        if path.startswith("/cp/v1/resource-instances-details"):
            rid = path.split("resourceId=")[1]
            if rid == "O11YV3":
                return {"data": [{"resource_instance_id": s, "resource_instance_name": "n"}
                                 for s in self.stacks]}
            return {"data": [{"resource_instance_id": i, "resource_instance_name": n}
                             for n, i in self.existing.get(rid, [])]}
        if path.startswith("/cp/v1/capability-instances?"):
            return {"capabilityInstances": [{"resourceInstanceIds": list(self.linked_ids)}]}
        if path.startswith("/cp/v1/capabilities-metadata"):
            ctype = path.split("capability-type=")[1]
            return {"data": [{
                "version": [1, 21, 0],
                "package": {"package": {
                    "recipe": {"helmCharts": [{"name": f"chart-for-{ctype}"}]},
                    "services": [{"name": "o11y-service"}],
                    "provisioningRoles": ["DEV_OPS"],
                }},
            }]}
        raise AssertionError(f"unexpected GET {path}")

    # --- writes ---
    def post(self, path, payload):
        self.posts.append((path, payload))
        return {"resource_instance_id": next(self.next_id)}

    def put(self, path, payload, timeout=None):
        self.puts.append((path, payload, timeout))
        return {"message": "ok"}

    def whoami_subscription_id(self):
        return SCOPE_ID


def _api(**kw):
    client = FakeClient(**kw)
    return O11yConsoleApi(client, scope_id=SCOPE_ID), client


def _leaf(payload, suffix):
    for field in payload["payload"]["resourceInstanceMetadata"]["fields"]:
        for _kind, body in field["value"].items():
            for leaf in body["fields"]:
                if leaf["key"].endswith(suffix):
                    return leaf["value"]
    return "<absent>"


# ---------------------------------------------------------------------------
# Pillar creation
# ---------------------------------------------------------------------------

def test_pillar_template_comes_from_the_registry_not_from_an_existing_instance():
    """The whole reason this module exists is that a stored instance reads its password
    back as TP1.<ciphertext>; posting that back double-encrypts it into a credential that
    silently fails to authenticate. Only /cp/v1/resources may be the template source."""
    api, client = _api()
    api.ensure_pillars()
    template_reads = [g for g in client.gets if g.startswith("/cp/v1/resources")]
    assert template_reads, "the registry was never read"
    # -details is used for idempotency lookups only, never as a template.
    assert all("resource-instances-details" not in g for g in template_reads)


def test_pillar_payload_fills_the_registry_nulls():
    api, client = _api()
    api.ensure_pillars()
    _path, payload = next(p for p in client.posts
                          if p[1]["resourceId"] == "LOGS_PRX_UA_ES")
    assert _leaf(payload, ".logIndex") == "user-app-global-log-index"
    assert _leaf(payload, ".endpoint")
    # The map-typed field is null in the registry; the UI sends {} and so must we —
    # null and {} render differently into the helm values.
    assert _leaf(payload, ".headers") == {}
    assert payload["payload"]["scope"] == "SUBSCRIPTION"
    assert payload["payload"]["scopeId"] == SCOPE_ID


def test_business_activities_pillars_get_the_ba_index():
    api, client = _api()
    api.ensure_pillars()
    for rid in ("LOGS_PRX_AS_ES", "LOGS_EXP_AS_ES"):
        payload = next(p[1] for p in client.posts if p[1]["resourceId"] == rid)
        assert _leaf(payload, ".logIndex") == "user-app-global-ba-log-index"


def test_non_logs_pillars_carry_no_log_index():
    api, client = _api()
    api.ensure_pillars()
    for rid in ("METRICS_PRX_PROM", "TRACES_PRX_ES"):
        payload = next(p[1] for p in client.posts if p[1]["resourceId"] == rid)
        assert _leaf(payload, ".logIndex") == "<absent>"


def test_existing_pillars_are_reused_not_recreated():
    api, client = _api(existing={"LOGS_PRX_UA_ES": [("global-logs-qsqs-1", "old-1")]})
    ids = api.ensure_pillars()
    assert ids["logs-qsqs-1"] == "old-1"
    assert all(p[1]["resourceId"] != "LOGS_PRX_UA_ES" for p in client.posts)


# ---------------------------------------------------------------------------
# Stack assembly
# ---------------------------------------------------------------------------

def test_stack_slots_reference_pillars_by_name_not_by_resource_id():
    """METRICS_PRX_PROM has TWO subscription-scope instances on a real CP —
    'global-metrics-qs-1' and '_system$metricsServer'. The UI-built stack references the
    'global-' one. Indexing by resource_id picks whichever came back last and silently
    points the stack at the wrong prometheus."""
    api, client = _api(existing={
        "METRICS_PRX_PROM": [("global-metrics-qs-1", "right-1"),
                             ("_system$metricsServer", "wrong-1")],
    })
    api.ensure_global_config()
    stack = next(p[1] for p in client.posts if p[1]["resourceId"] == "O11YV3")
    value = stack["payload"]["resourceInstanceMetadata"]["fields"][0]["value"]
    assert value["proxies"]["metricsServer"]["instanceId"] == "right-1"


def test_stack_shape_matches_the_wizard():
    api, client = _api()
    api.ensure_global_config()
    stack = next(p[1] for p in client.posts if p[1]["resourceId"] == "O11YV3")
    value = stack["payload"]["resourceInstanceMetadata"]["fields"][0]["value"]
    assert set(value["proxies"]) == {
        "logsServerUserApps", "logsServerAuditSafe", "metricsServer", "tracesServer"}
    enabled = {k for k, v in value["exporters"].items() if v["enabled"]}
    assert enabled == {"logsServerUserApps", "logsServerServices",
                       "logsServerAuditSafe", "metricsServer", "tracesServer"}
    # Four secondaries, present but disabled. There is deliberately no auditSafe secondary.
    disabled = {k for k, v in value["exporters"].items() if not v["enabled"]}
    assert disabled == {"logsServerUserAppsSecondary", "logsServerServicesSecondary",
                        "metricsServerSecondary", "tracesServerSecondary"}
    assert all(v["scope"] == "SUBSCRIPTION" for v in value["proxies"].values())
    assert value["proxies"]["metricsServer"]["kind"] == "prometheus"
    assert value["proxies"]["tracesServer"]["kind"] == "elasticSearch"


def test_create_uses_the_wrapped_envelope():
    """POST wraps ({resourceId, payload}); the UPDATE path is flat with the target in the
    query string. Copying one shape onto the other fails on the wire."""
    api, client = _api()
    api.ensure_global_config()
    path, payload = next(p for p in client.posts if p[1]["resourceId"] == "O11YV3")
    assert path == "/cp/v1/resource-instances"
    assert set(payload) == {"resourceId", "payload"}


def test_existing_stack_is_reused():
    api, client = _api(stacks=[STACK_ID])
    assert api.ensure_global_config() == STACK_ID
    assert client.posts == []


def test_more_than_one_stack_is_refused():
    """The CP really does allow duplicates at one scope (verified), so this is a state we
    can reach, not a theoretical one. Picking [0] is how data planes end up linked to
    different stacks."""
    api, _client = _api(stacks=["a", "b"])
    with pytest.raises(O11yConsoleError, match="refusing to guess"):
        api.global_stack_id()


def test_a_failed_lookup_is_never_read_as_absent():
    """A wrong scopeId answers 403. Swallowing that into an empty list reads as 'no stack
    exists' and creates a duplicate."""
    api, client = _api()
    client.get = MagicMock(side_effect=ConsoleApiError("GET", "u", 403, "denied"))
    with pytest.raises(ConsoleApiError):
        api.global_stack_id()


# ---------------------------------------------------------------------------
# Link / unlink
# ---------------------------------------------------------------------------

def test_link_sends_the_stack_pointer_and_platform_type():
    api, client = _api(stacks=[STACK_ID], linked_ids=[])
    client.linked_ids = []

    def put(path, payload, timeout=None):
        client.puts.append((path, payload, timeout))
        client.linked_ids = [STACK_ID]          # the switch takes effect
        return {"message": "ok"}
    client.put = put

    assert api.link_to_global(DP_ID) is True
    path, body, timeout = client.puts[0]
    assert "type=PLATFORM" in path and "operation=UPDATE" in path
    assert body["capabilityType"] == "PLATFORM"
    assert body["resourceInstanceDetails"] == {"scope": "SUBSCRIPTION", "instanceId": STACK_ID}
    assert body["dataPlaneId"] == DP_ID
    assert body["recipe"]["helmChartsCommon"] == {}
    assert timeout == 90


def test_unlink_omits_the_pointer_and_uses_infra_type():
    api, client = _api(stacks=[STACK_ID], linked_ids=[STACK_ID])

    def put(path, payload, timeout=None):
        client.puts.append((path, payload, timeout))
        client.linked_ids = []
        return {"message": "ok"}
    client.put = put

    assert api.unlink_from_global(DP_ID) is True
    path, body, _t = client.puts[0]
    assert "type=INFRA" in path
    assert body["capabilityType"] == "INFRA"
    assert "resourceInstanceDetails" not in body


def test_each_direction_fetches_its_own_capability_metadata():
    """The PLATFORM and INFRA recipes are DIFFERENT documents — PLATFORM carries the
    configured exporter switches, INFRA is the bare variant. Reusing one cached fetch for
    both pushes the wrong configuration."""
    api, client = _api(stacks=[STACK_ID], linked_ids=[])

    def put(path, payload, timeout=None):
        client.puts.append((path, payload, timeout))
        client.linked_ids = [STACK_ID] if "PLATFORM" in path else []
        return {"message": "ok"}
    client.put = put

    api.link_to_global(DP_ID)
    api.unlink_from_global(DP_ID)

    meta = [g for g in client.gets if g.startswith("/cp/v1/capabilities-metadata")]
    assert any("capability-type=PLATFORM" in g for g in meta)
    assert any("capability-type=INFRA" in g for g in meta)
    assert client.puts[0][1]["recipe"] != client.puts[1][1]["recipe"]


def test_link_returns_the_read_back_not_the_http_status():
    """A 200 that did not change the state is a failure. Reporting the call instead of
    the outcome is exactly how this area regressed three times."""
    api, client = _api(stacks=[STACK_ID], linked_ids=[])   # switch never takes effect
    assert api.link_to_global(DP_ID) is False
    assert client.puts, "the switch was attempted"


def test_link_is_skipped_when_already_linked():
    api, client = _api(stacks=[STACK_ID], linked_ids=[STACK_ID])
    assert api.link_to_global(DP_ID) is True
    assert client.puts == [], "a no-op link must not re-run the helm reconcile (~12 s)"


def test_unlink_is_skipped_when_already_unlinked():
    api, client = _api(stacks=[STACK_ID], linked_ids=[])
    assert api.unlink_from_global(DP_ID) is True
    assert client.puts == []


def test_link_without_a_global_stack_is_refused():
    api, _client = _api(stacks=[])
    with pytest.raises(O11yConsoleError, match="no Global observability stack"):
        api.link_to_global(DP_ID)


def test_link_state_is_not_read_from_capability_type():
    """capabilityType IS the link state (PLATFORM when linked, INFRA when not), so
    querying capability-instances-details with a fixed type to decide link state is
    circular — it returns 0 for every unlinked DP and reads as 'no O11Y capability'."""
    api, client = _api(stacks=[STACK_ID], linked_ids=[STACK_ID])
    api.is_linked_to_global(DP_ID)
    assert not any("capability-instances-details" in g for g in client.gets)
    assert not any("/o11y/v1/dataplanes" in g for g in client.gets), (
        "/o11y/v1/dataplanes is cached ~120 s and lies in both directions")


def test_a_severed_tunnel_is_its_own_exception():
    """503 ATMOSPHERE-11002 is infrastructure, not a rejected payload; the caller has to
    be able to tell them apart to triage in the right order."""
    api, client = _api(stacks=[STACK_ID], linked_ids=[])
    client.put = MagicMock(side_effect=ConsoleApiError(
        "PUT", "u", 503, json.dumps({"errorCode": "ATMOSPHERE-11002"})))
    with pytest.raises(O11yDataPlaneUnreachable):
        api.link_to_global(DP_ID)


# ---------------------------------------------------------------------------
# Containment: the back door must stay behind the seam
# ---------------------------------------------------------------------------

def test_the_workaround_is_greppable_by_ticket():
    """A future maintainer must be able to find every line to delete from the ticket
    number alone. The Jira link is the real mechanism; this keeps the code side honest."""
    from pathlib import Path

    import api_object.o11y_console as module
    src = Path(module.__file__).read_text()
    assert module.WORKAROUND_TICKET == "PCP-21542"
    for method in ("_create_pillar_via_console", "_create_stack_via_console",
                   "_reprovision_o11y_capability"):
        assert f"def {method}" in src
    assert src.count("PCP-21542") >= 3
