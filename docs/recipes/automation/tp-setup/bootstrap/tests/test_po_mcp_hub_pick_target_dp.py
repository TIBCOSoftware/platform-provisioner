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
# Regression tests for PCP-20127 — the deploy-mcp-hub DP-readiness race.
#
# Root cause (see docs/plan/PCP-20127-plan.md): the Register Gateway wizard's
# target-DP list is fetched ONCE at page mount (useGateways, staleTime:0, no
# refetchInterval), so it never refreshes mid-wizard. The fix waits for the
# target DP to report status=='online' BEFORE entering the wizard, via the same
# Hub /gateways API the wizard reads. These tests pin that gate:
#   * it polls until the cp_dp DP is online, then returns (does not abort);
#   * it fails fast & loud on an API error (never a silent 15-min burn);
#   * it times out -> exit_error if the DP never comes online;
#   * it keys on origin=='cp_dp' (a 'direct' row with the same name must not satisfy it);
#   * deploy_mcp_gateway invokes the gate BEFORE navigating to /gateways/register.
#
# Faithful to the contract (tp-mcp-hub contracts/gateway.ts): status enum is
# online|offline|unknown (never 'degraded'); origin defaults to 'cp_dp'.

from unittest.mock import MagicMock, patch

import pytest

from page_object.po_mcp_hub import PageObjectMcpHub
from utils.util import Util

DP_NAME = "k8s-auto-dp1"
# PCP-21143: the registered gateway name is prefixed 'gateway-<dp>' (see
# PageObjectMcpHub._gateway_name); name-based gateway lookups match THIS, not the
# bare DP name. Target-DP selection still keys on DP_NAME.
GW_NAME = f"gateway-{DP_NAME}"
# PCP-21173: the current Data Plane's id. Gateway reuse/status lookups also bind to it
# (gateway.dataPlaneId == current dpId), so an orphan row left by a same-named DP
# delete/recreate (stale dataPlaneId) is rejected.
DP_ID = "dp-id-current"
API_URL = "https://cp-sub1.example.com/cp/mcp-hub/api/mcp-hub/gateways"


def _make_po():
    """Build a PageObjectMcpHub without running __init__ (which would need a real
    Playwright page). Inject a MagicMock page and a pre-captured gateways API URL."""
    po = PageObjectMcpHub.__new__(PageObjectMcpHub)
    po.page = MagicMock()
    po.gateway_id = None
    po._gateways_api_url = API_URL
    # page.wait_for_timeout is a no-op MagicMock, so the poll loop never really sleeps.
    return po


def _api_response(payload, ok=True, status=200, text=""):
    resp = MagicMock()
    resp.ok = ok
    resp.status = status
    resp.json.return_value = payload
    resp.text.return_value = text
    return resp


def _dp(name=DP_NAME, status="online", origin="cp_dp", dp_id=DP_ID):
    return {"name": name, "status": status, "origin": origin, "dpId": dp_id}


def _route_get(gateways=None, data_planes=None, gw_ok=True, gw_status=200):
    """A ``request.get`` side_effect that routes by URL: the ``/data-planes`` endpoint
    (the PCP-21173 identity resolve) vs the ``/gateways`` endpoint. Reusable across any
    number of calls (a function, not a one-shot list). ``data_planes`` defaults to a
    single online DP (name=DP_NAME, dpId=DP_ID) so identity resolution succeeds; pass
    ``data_planes=[]`` to simulate the DP not being listed (dpId unresolvable)."""
    if data_planes is None:
        data_planes = [_dp()]

    def _get(url, *a, **k):
        if str(url).endswith("/data-planes"):
            return _api_response(data_planes)
        return _api_response(gateways or [], ok=gw_ok, status=gw_status)

    return _get


def test_wait_polls_until_dp_online_then_returns():
    """Degraded (unknown/offline) for two polls, then online -> returns without aborting."""
    po = _make_po()
    po.page.context.request.get.side_effect = [
        _api_response([_dp(status="unknown")]),
        _api_response([_dp(status="offline")]),
        _api_response([_dp(status="online")]),
    ]
    with patch("page_object.po_mcp_hub.Util.exit_error",
               side_effect=AssertionError("must not abort when the DP comes online")):
        po._wait_for_target_dp_online(DP_NAME, max_minutes=5)
    assert po.page.context.request.get.call_count == 3
    # It must have waited between polls (not busy-looped).
    assert po.page.wait_for_timeout.call_count >= 2


def test_wait_returns_immediately_when_already_online():
    """Happy path: DP already online on the first poll -> single GET, no wait."""
    po = _make_po()
    po.page.context.request.get.return_value = _api_response([_dp(status="online")])
    with patch("page_object.po_mcp_hub.Util.exit_error",
               side_effect=AssertionError("must not abort")):
        po._wait_for_target_dp_online(DP_NAME, max_minutes=5)
    assert po.page.context.request.get.call_count == 1
    po.page.wait_for_timeout.assert_not_called()


def test_wait_fails_loud_on_api_error():
    """A 404/401 on the readiness GET aborts immediately — never a silent long loop."""
    po = _make_po()
    po.page.context.request.get.return_value = _api_response([], ok=False, status=404)
    with patch("page_object.po_mcp_hub.Util.exit_error",
               side_effect=SystemExit(1)) as exit_error:
        with pytest.raises(SystemExit):
            po._wait_for_target_dp_online(DP_NAME, max_minutes=5)
    assert po.page.context.request.get.call_count == 1  # aborted on the first poll
    assert exit_error.called


def test_wait_times_out_when_dp_never_online():
    """Never online within the budget -> exit_error (timeout fallback)."""
    po = _make_po()
    po.page.context.request.get.return_value = _api_response([_dp(status="unknown")])
    with patch("page_object.po_mcp_hub.Util.exit_error",
               side_effect=SystemExit(1)) as exit_error:
        with pytest.raises(SystemExit):
            po._wait_for_target_dp_online(DP_NAME, max_minutes=1)
    assert exit_error.called


def test_wait_ignores_direct_row_with_same_name():
    """A 'direct' gateway with the same name (origin!='cp_dp') must NOT satisfy the gate."""
    po = _make_po()
    po.page.context.request.get.return_value = _api_response(
        [_dp(status="online", origin="direct")]
    )
    with patch("page_object.po_mcp_hub.Util.exit_error",
               side_effect=SystemExit(1)) as exit_error:
        with pytest.raises(SystemExit):
            po._wait_for_target_dp_online(DP_NAME, max_minutes=1)
    assert exit_error.called  # times out because no cp_dp row is online


def test_deploy_waits_for_dp_online_before_entering_wizard():
    """deploy_mcp_gateway must call the readiness gate BEFORE navigating to the
    Register wizard page, so the wizard's one-time DP-list fetch sees it online."""
    po = _make_po()
    calls = []
    po._open_gateway_from_home = MagicMock(return_value=None)  # not idempotent path
    po._hub_url = lambda route="": f"https://cp-sub1.example.com/cp/mcphub{route}"

    def _goto(url, *a, **k):
        calls.append(("goto", url))
    po.page.goto.side_effect = _goto

    with patch.object(PageObjectMcpHub, "_wait_for_target_dp_online",
                      side_effect=lambda *a, **k: calls.append(("gate", a[0] if a else None))), \
         patch.object(PageObjectMcpHub, "_register_continue"), \
         patch.object(PageObjectMcpHub, "_register_fill_identity"), \
         patch.object(PageObjectMcpHub, "_register_pick_target_dp"), \
         patch.object(PageObjectMcpHub, "_register_select_or_create_resource"), \
         patch.object(PageObjectMcpHub, "_register_review_and_deploy", return_value="gw-id"), \
         patch.object(PageObjectMcpHub, "_wait_for_gateway_online"), \
         patch("page_object.po_mcp_hub.Util.check_dom_visibility", return_value=True):
        po.deploy_mcp_gateway(DP_NAME, skip_online_wait=True)

    gate_idx = next(i for i, c in enumerate(calls) if c[0] == "gate")
    register_idx = next(
        i for i, c in enumerate(calls)
        if c[0] == "goto" and c[1].endswith("/gateways/register")
    )
    assert gate_idx < register_idx, f"gate must run before the register goto; calls={calls}"


# --- _capture_gateways_api_url: latch only the Hub's own gateways-list URL --------

HUB_ORIGIN = "https://cp-sub1.example.com"


def _response_event(url, method="GET", resource_type="xhr"):
    ev = MagicMock()
    ev.url = url
    ev.request.method = method
    ev.request.resource_type = resource_type
    return ev


def _capture_po():
    po = PageObjectMcpHub.__new__(PageObjectMcpHub)
    po.page = MagicMock()
    po.gateway_id = None
    po._gateways_api_url = None
    po._hub_origin = lambda: HUB_ORIGIN
    return po


def test_capture_latches_hub_gateways_url_and_strips_query():
    po = _capture_po()
    po._capture_gateways_api_url(
        _response_event(f"{HUB_ORIGIN}/cp/mcp-hub/api/mcp-hub/gateways?foo=1"))
    assert po._gateways_api_url == f"{HUB_ORIGIN}/cp/mcp-hub/api/mcp-hub/gateways"


def test_capture_is_one_shot():
    po = _capture_po()
    first = f"{HUB_ORIGIN}/cp/mcp-hub/api/mcp-hub/gateways"
    po._capture_gateways_api_url(_response_event(first))
    po._capture_gateways_api_url(
        _response_event(f"{HUB_ORIGIN}/cp/mcp-hub/api/mcp-hub/gateways?page=2"))
    assert po._gateways_api_url == first  # capture-once: not overwritten


def test_capture_ignores_non_matching_requests():
    po = _capture_po()
    for ev in (
        _response_event(f"{HUB_ORIGIN}/cp/mcphub/gateways/register"),                       # UI route, not /gateways
        _response_event(f"{HUB_ORIGIN}/cp/mcp-hub/api/mcp-hub/gateways/x/deploy", method="POST"),  # deploy POST
        _response_event(f"{HUB_ORIGIN}/cp/mcp-hub/api/mcp-hub/gateways/x", method="PUT"),   # single-gateway PUT
        _response_event(f"{HUB_ORIGIN}/some/api/other/gateways"),                            # non-mcp /api/.../gateways
        _response_event("https://evil.example.com/cp/mcp-hub/api/mcp-hub/gateways"),         # different origin
        _response_event(f"{HUB_ORIGIN}/cp/mcp-hub/api/mcp-hub/gateways", resource_type="document"),  # navigation
    ):
        po._capture_gateways_api_url(ev)
    assert po._gateways_api_url is None  # none of the above latched


def test_wait_accepts_missing_origin_as_cp_dp():
    """A row with no 'origin' key is treated as cp_dp (mirrors the contract's zod default)."""
    po = _make_po()
    po.page.context.request.get.return_value = _api_response([{"name": DP_NAME, "status": "online"}])
    with patch("page_object.po_mcp_hub.Util.exit_error",
               side_effect=AssertionError("a missing-origin online row must satisfy the gate as cp_dp")):
        po._wait_for_target_dp_online(DP_NAME, max_minutes=5)
    assert po.page.context.request.get.call_count == 1


def test_wait_dp_online_polls_dataplanes_endpoint():
    """The DP-readiness gate must poll /data-planes (not /gateways) — the endpoint the
    wizard's target-DP list reads (PCP-19802 design-B)."""
    po = _make_po()
    po.page.context.request.get.return_value = _api_response([_dp(status="online")])
    with patch("page_object.po_mcp_hub.Util.exit_error",
               side_effect=AssertionError("online row must satisfy the gate")):
        po._wait_for_target_dp_online(DP_NAME, max_minutes=5)
    assert po.page.context.request.get.call_args[0][0].endswith("/data-planes")


# === PCP-20336: deterministic gateways-API readiness =============================
#
# The deploy-mcp-hub flow's deployed/online readiness now uses deterministic Hub API
# signals instead of brittle UI-flag polling: _api_get_gateway (GET .../gateways row
# by id, name-fallback origin-cp_dp + fail-on-duplicate); _wait_for_gateway_online
# (POST .../gateways/{id}/health-check, accept status=='online'); wait_for_gateway_deployed
# (poll mcpgatewayDeployed, then confirm the UI Push action operable). Backend contract
# (tp-mcp-hub gateways.ts rowToJson): {id,name,status(online|offline|unknown),
# mcpgatewayDeployed,origin}; health-check is synchronous and returns {status}.

GW_ID = "gw-uuid-1"


def _gw(id=GW_ID, name=DP_NAME, status="online", origin="cp_dp", deployed=True,
        data_plane_id=DP_ID):
    return {"id": id, "name": name, "status": status, "origin": origin,
            "mcpgatewayDeployed": deployed, "dataPlaneId": data_plane_id}


def test_api_get_gateway_matches_by_id_primary():
    """When a gateway_id is known, match on it (not name) — the reliable key."""
    po = _make_po()
    po.page.context.request.get.return_value = _api_response(
        [_gw(id="other", name=DP_NAME), _gw(id=GW_ID, name=DP_NAME, status="offline")])
    row = po._api_get_gateway(gateway_id=GW_ID)
    assert row is not None and row["id"] == GW_ID and row["status"] == "offline"


def test_api_get_gateway_name_fallback_filters_origin_cp_dp():
    """No id -> name fallback, but a 'direct' row with the same name is ignored."""
    po = _make_po()
    po.page.context.request.get.side_effect = _route_get(
        gateways=[_gw(id="d1", name=GW_NAME, origin="direct"), _gw(id="c1", name=GW_NAME, origin="cp_dp")])
    row = po._api_get_gateway(dp_name=DP_NAME)
    assert row is not None and row["id"] == "c1"


def test_api_get_gateway_name_fallback_fails_loud_on_duplicate():
    """Two cp_dp gateways with the same name and no id -> exit_error (ambiguous;
    multi-gateway-per-dp). Never silently pick the first."""
    po = _make_po()
    po.page.context.request.get.side_effect = _route_get(
        gateways=[_gw(id="a", name=GW_NAME), _gw(id="b", name=GW_NAME)])
    with patch("page_object.po_mcp_hub.Util.exit_error", side_effect=SystemExit(1)) as exit_error:
        with pytest.raises(SystemExit):
            po._api_get_gateway(dp_name=DP_NAME)
    assert exit_error.called


def test_api_get_gateway_returns_none_when_absent():
    """A known id with no matching row -> None (caller decides; not an error)."""
    po = _make_po()
    po.page.context.request.get.return_value = _api_response([_gw(id="other")])
    assert po._api_get_gateway(gateway_id=GW_ID) is None


def test_api_get_gateway_fails_loud_on_api_error():
    """A non-OK gateways GET -> exit_error (report, never read a wrong status)."""
    po = _make_po()
    po.page.context.request.get.return_value = _api_response([], ok=False, status=500)
    with patch("page_object.po_mcp_hub.Util.exit_error", side_effect=SystemExit(1)) as exit_error:
        with pytest.raises(SystemExit):
            po._api_get_gateway(gateway_id=GW_ID)
    assert exit_error.called


def test_api_get_gateway_handles_dict_wrapped_payload():
    """The list endpoint may wrap rows as {"gateways": [...]} — handle both shapes."""
    po = _make_po()
    po.page.context.request.get.return_value = _api_response({"gateways": [_gw(id=GW_ID)]})
    row = po._api_get_gateway(gateway_id=GW_ID)
    assert row is not None and row["id"] == GW_ID


def test_api_get_gateway_skips_rows_without_id():
    """A row missing 'id' must not crash the id match; the real target is still found."""
    po = _make_po()
    po.page.context.request.get.return_value = _api_response(
        [{"name": "x", "status": "online"}, _gw(id=GW_ID)])
    assert po._api_get_gateway(gateway_id=GW_ID)["id"] == GW_ID


def test_wait_online_succeeds_on_healthcheck_online():
    """A health-check returning status=='online' -> returns without aborting."""
    po = _make_po()
    po.gateway_id = GW_ID
    po.page.context.request.post.return_value = _api_response({"connected": True, "status": "online"})
    with patch("page_object.po_mcp_hub.Util.exit_error",
               side_effect=AssertionError("must not abort when the gateway is online")):
        po._wait_for_gateway_online(GW_ID, max_minutes=5)
    assert po.page.context.request.post.call_count == 1
    assert "/health-check" in po.page.context.request.post.call_args[0][0]
    assert GW_ID in po.page.context.request.post.call_args[0][0]


def test_wait_online_times_out_when_never_online():
    """Never online within the budget -> loud exit_error (a real offline is reported)."""
    po = _make_po()
    po.gateway_id = GW_ID
    po.page.context.request.post.return_value = _api_response({"connected": False, "status": "offline"})
    with patch("page_object.po_mcp_hub.Util.exit_error", side_effect=SystemExit(1)) as exit_error:
        with pytest.raises(SystemExit):
            po._wait_for_gateway_online(GW_ID, max_minutes=1)
    assert exit_error.called


def test_wait_online_fails_fast_on_persistent_api_error():
    """A persistent non-404 hard error (401) -> fail fast after 3 consecutive, NOT the
    full 15-min budget."""
    po = _make_po()
    po.gateway_id = GW_ID
    po.page.context.request.post.return_value = _api_response({}, ok=False, status=401)
    with patch("page_object.po_mcp_hub.Util.exit_error", side_effect=SystemExit(1)) as exit_error:
        with pytest.raises(SystemExit):
            po._wait_for_gateway_online(GW_ID, max_minutes=15)
    assert po.page.context.request.post.call_count == 3
    assert exit_error.called


def test_wait_online_404_falls_back_to_ui_once():
    """A generic 404 (legacy variant, endpoint absent) -> single UI fallback (one POST,
    then the UI online check), NOT a per-iteration nested deployed-wait."""
    po = _make_po()
    po.gateway_id = GW_ID
    po.page.context.request.post.return_value = _api_response({}, ok=False, status=404)
    with patch.object(PageObjectMcpHub, "wait_for_gateway_deployed"), \
         patch.object(PageObjectMcpHub, "is_gateway_online", return_value=True), \
         patch("page_object.po_mcp_hub.Util.exit_error",
               side_effect=AssertionError("must not abort when the UI reports online")):
        po._wait_for_gateway_online(GW_ID, max_minutes=5)
    assert po.page.context.request.post.call_count == 1


def test_wait_online_404_gateway_not_found_fails_loud():
    """A 404 whose body is 'Gateway not found' = a WRONG id (endpoint exists) -> fail
    loud, NOT a legacy UI fallback that would time out confusingly."""
    po = _make_po()
    po.gateway_id = GW_ID
    po.page.context.request.post.return_value = _api_response(
        {"error": "Gateway not found"}, ok=False, status=404, text='{"error":"Gateway not found"}')
    with patch.object(PageObjectMcpHub, "_wait_for_gateway_online_ui",
                      side_effect=AssertionError("a wrong-id 404 must not UI-fallback")), \
         patch("page_object.po_mcp_hub.Util.exit_error", side_effect=SystemExit(1)) as exit_error:
        with pytest.raises(SystemExit):
            po._wait_for_gateway_online(GW_ID, max_minutes=5)
    assert exit_error.called
    assert po.page.context.request.post.call_count == 1


def test_wait_deployed_succeeds_on_api_flag_and_ui_operable():
    """API row with mcpgatewayDeployed + the detail Push action visible -> deployed."""
    po = _make_po()
    po.page.context.request.get.return_value = _api_response([_gw(id=GW_ID, deployed=True)])
    with patch.object(PageObjectMcpHub, "goto_gateway"), \
         patch.object(PageObjectMcpHub, "_detail_push_button", return_value=MagicMock()), \
         patch("page_object.po_mcp_hub.Util.check_dom_visibility", return_value=True), \
         patch("page_object.po_mcp_hub.Util.exit_error",
               side_effect=AssertionError("must not abort when deployed + UI operable")):
        po.wait_for_gateway_deployed(GW_ID, max_minutes=5)


def test_wait_deployed_flags_ui_lag_when_api_deployed_but_no_push_button():
    """API says deployed but the detail view never renders the Push action -> loud
    PCP-20127 UI-lag error (NOT a blind timeout)."""
    po = _make_po()
    po.page.context.request.get.return_value = _api_response([_gw(id=GW_ID, deployed=True)])
    with patch.object(PageObjectMcpHub, "goto_gateway"), \
         patch.object(PageObjectMcpHub, "_detail_push_button", return_value=MagicMock()), \
         patch("page_object.po_mcp_hub.Util.check_dom_visibility", return_value=False), \
         patch("page_object.po_mcp_hub.Util.exit_error", side_effect=SystemExit(1)) as exit_error:
        with pytest.raises(SystemExit):
            po.wait_for_gateway_deployed(GW_ID, max_minutes=1)
    assert exit_error.called
    assert "lagging" in exit_error.call_args[0][0] or "PCP-20127" in exit_error.call_args[0][0]


def test_wait_deployed_times_out_when_api_never_deployed():
    """mcpgatewayDeployed never true -> loud timeout (the deploy may have failed)."""
    po = _make_po()
    po.page.context.request.get.return_value = _api_response([_gw(id=GW_ID, deployed=False)])
    with patch("page_object.po_mcp_hub.Util.exit_error", side_effect=SystemExit(1)) as exit_error:
        with pytest.raises(SystemExit):
            po.wait_for_gateway_deployed(GW_ID, max_minutes=1)
    assert exit_error.called


# === PCP-20336 (1.17.1 minor line): Browse-Registry button drift + API idempotency ===
#
# Two regressions on the new 1.17.1 line, same Fresco-drops-data-testid family:
#   1. The MCP Servers tab action buttons became Fresco <Button label> with NO
#      data-testid, so add_mcp_server's get_by_test_id("servers-registry-button")
#      never resolved -> 30s click timeout (the #11 failure). _servers_registry_button
#      then resolved "Browse Registry" by role+name (unanchored), testid as fallback.
#      (PCP-22620 later re-flipped it to test-id-first once PCP-22619 restored the hook —
#      see the PCP-22620 tests below.)
#   2. deploy_mcp_gateway's idempotency used the UI dashboard (_open_gateway_from_home),
#      which on the multi-gateway-per-dp dashboard stopped resolving an existing gateway
#      (the row click no longer lands on /gateways/<id>) -> every re-run re-deployed and
#      piled up duplicate gateways until the DP node ran out of schedulable CPU.
#      _find_existing_gateway_id now reuses an existing cp_dp gateway (deployed OR still
#      provisioning, PCP-20573) via the deterministic gateways API (reuse-first), so
#      re-runs don't pile up.


# PCP-22620: _servers_registry_button was flipped to test-id-FIRST — PCP-22619 re-added
# the stable `servers-registry-button` hook (Fresco alpha.87 passthrough / PLTUX-1299), so
# the automation prefers it and only falls back to the 'Browse Registry' label by role+name
# on older Hub builds. These pin the new ordering (was role+name-first under PCP-20336).


def test_servers_registry_button_prefers_test_id():
    """PCP-22620: resolve 'Browse Registry' by the servers-registry-button test-id FIRST;
    when it is visible the role+name locator is never even built."""
    po = _make_po()
    with patch("page_object.po_mcp_hub.Util.check_dom_visibility", return_value=True):
        result = po._servers_registry_button()
    po.page.get_by_test_id.assert_called_with("servers-registry-button")
    assert result is po.page.get_by_test_id.return_value.first
    po.page.get_by_role.assert_not_called()  # test-id hit -> role+name never consulted


def test_servers_registry_button_falls_back_to_role_name():
    """Older build: test-id absent -> fall back to role+name 'Browse Registry' (unanchored,
    for the PrimeReact icon-glyph-in-accessible-name caveat)."""
    po = _make_po()
    # first check (test-id) False, second (role+name) True
    with patch("page_object.po_mcp_hub.Util.check_dom_visibility", side_effect=[False, True]):
        result = po._servers_registry_button()
    po.page.get_by_test_id.assert_called_with("servers-registry-button")
    args, kwargs = po.page.get_by_role.call_args
    assert args[0] == "button"
    assert kwargs["name"].pattern == "Browse Registry"
    assert result is po.page.get_by_role.return_value.first


def test_servers_registry_button_defaults_to_test_id_when_none_visible():
    """Neither visible yet -> return the durable test-id locator (a current Hub renders the
    test-id, not the label), so the caller polls the right hook."""
    po = _make_po()
    with patch("page_object.po_mcp_hub.Util.check_dom_visibility", return_value=False):
        result = po._servers_registry_button()
    assert result is po.page.get_by_test_id.return_value.first


def test_find_existing_gateway_id_reuse_first():
    """Idempotency: return the FIRST deployed cp_dp gateway id for the DP — reuse-first,
    NOT fail-loud on duplicate (contrast _api_get_gateway, which is a status poll)."""
    po = _make_po()
    po.page.context.request.get.side_effect = _route_get(
        gateways=[_gw(id="a", name=GW_NAME, deployed=True), _gw(id="b", name=GW_NAME, deployed=True)])
    assert po._find_existing_gateway_id(DP_NAME) == "a"


def test_find_existing_gateway_id_none_when_absent():
    po = _make_po()
    po.page.context.request.get.side_effect = _route_get(
        gateways=[_gw(id="x", name="other", deployed=True)])
    assert po._find_existing_gateway_id(DP_NAME) is None


def test_find_existing_gateway_id_ignores_direct():
    """A 'direct' row (wrong origin) is never reusable, even if deployed — only cp_dp
    (auto-provisioned) gateways are ours to reuse."""
    po = _make_po()
    po.page.context.request.get.side_effect = _route_get(gateways=[
        _gw(id="d", name=GW_NAME, origin="direct", deployed=True),
    ])
    assert po._find_existing_gateway_id(DP_NAME) is None


def test_find_existing_gateway_id_reuses_inprogress_cp_dp():
    """PCP-20573: an in-progress (not-yet-deployed) cp_dp gateway for the DP IS reusable.
    The deploy POST created the row but mcpgatewayDeployed has not flipped yet; reusing it
    (instead of returning None -> re-running the wizard) is what stops the retry leak."""
    po = _make_po()
    po.page.context.request.get.side_effect = _route_get(gateways=[
        _gw(id="u", name=GW_NAME, origin="cp_dp", deployed=False),
    ])
    assert po._find_existing_gateway_id(DP_NAME) == "u"


def test_find_existing_gateway_id_prefers_deployed_over_inprogress():
    """When both an in-progress and a deployed row exist for the DP, prefer the deployed
    (healthy) one regardless of list order — a stuck in-progress row must not shadow it."""
    po = _make_po()
    po.page.context.request.get.side_effect = _route_get(gateways=[
        _gw(id="u", name=GW_NAME, origin="cp_dp", deployed=False),
        _gw(id="d", name=GW_NAME, origin="cp_dp", deployed=True),
    ])
    assert po._find_existing_gateway_id(DP_NAME) == "d"


def test_find_existing_gateway_id_name_only_degrade_stays_deployed_only():
    """PCP-20573 safety: when the current dataPlaneId can't be resolved (name-only degrade),
    do NOT reuse an in-progress row by name only — it could be a stale orphan from a
    same-named DP delete/recreate. Only a deployed row is reused by name in the degrade path
    (see test_find_existing_gateway_id_name_only_when_dpid_unresolvable for the deployed case)."""
    po = _make_po()
    # data_planes=[] -> _resolve_dataplane_id returns None -> name-only degrade.
    po.page.context.request.get.side_effect = _route_get(
        data_planes=[],
        gateways=[_gw(id="u", name=GW_NAME, origin="cp_dp", deployed=False, data_plane_id="stale")],
    )
    assert po._find_existing_gateway_id(DP_NAME) is None


def test_find_existing_gateway_id_soft_on_api_error():
    """Idempotency must never BLOCK a deploy: an API error -> None (fall through to deploy),
    NOT exit_error (unlike the status-poll _api_get_gateway)."""
    po = _make_po()
    po.page.context.request.get.return_value = _api_response([], ok=False, status=500)
    with patch("page_object.po_mcp_hub.Util.exit_error",
               side_effect=AssertionError("idempotency check must not abort on API error")):
        assert po._find_existing_gateway_id(DP_NAME) is None


def test_deploy_reuses_existing_gateway_without_wizard():
    """PCP-20336 1.17.1 pile-up regression: when a deployed gateway already exists for the
    DP, deploy_mcp_gateway REUSES it (no Register wizard) so re-runs don't pile up
    duplicates — even when the UI dashboard lookup would have missed it."""
    po = _make_po()
    po.page.context.request.get.side_effect = _route_get(
        gateways=[_gw(id="gw-existing", name=GW_NAME, deployed=True)])
    # Simulate the 1.17.1 multi-gateway dashboard where the UI lookup misses it (the
    # pile-up root): deploy must still reuse via the deterministic gateways API.
    po._open_gateway_from_home = MagicMock(return_value=None)
    goto_calls = []
    po.page.goto.side_effect = lambda url, *a, **k: goto_calls.append(url)
    with patch.object(PageObjectMcpHub, "_wait_for_gateway_online"), \
         patch.object(PageObjectMcpHub, "_wait_for_target_dp_online",
                      side_effect=AssertionError("must NOT enter the wizard when a gateway already exists")):
        gid = po.deploy_mcp_gateway(DP_NAME, skip_online_wait=True)
    assert gid == "gw-existing"
    assert not any("/gateways/register" in u for u in goto_calls)


def test_deploy_reuses_inprogress_gateway_without_wizard():
    """PCP-20573: when a gateway for the DP already EXISTS but is still provisioning
    (mcpgatewayDeployed not yet true), deploy_mcp_gateway must REUSE it, NOT run the
    Register wizard again. The deploy POST creates the gateway row (+ Helm release +
    pod + PVC) minutes before the mcpgatewayDeployed flag flips; a prior retry that
    died in that window (e.g. wait_for_gateway_deployed timed out) leaves an
    in-progress row. If the idempotency guard only reuses *deployed* gateways, the
    retry re-enters the wizard and leaks a duplicate gateway (8+ observed on
    ins-pcp-20541). Reuse-first on the in-progress row prevents the pile-up."""
    po = _make_po()
    po.page.context.request.get.side_effect = _route_get(
        gateways=[_gw(id="gw-inprogress", name=GW_NAME, status="unknown", deployed=False)])
    # Simulate the multi-gateway dashboard where the UI lookup misses it (PCP-20336):
    # deploy must still reuse via the deterministic gateways API.
    po._open_gateway_from_home = MagicMock(return_value=None)
    goto_calls = []
    po.page.goto.side_effect = lambda url, *a, **k: goto_calls.append(url)
    with patch.object(PageObjectMcpHub, "_wait_for_gateway_online"), \
         patch.object(PageObjectMcpHub, "_wait_for_target_dp_online",
                      side_effect=AssertionError(
                          "must NOT enter the wizard when a gateway is already "
                          "provisioning for the DP")):
        gid = po.deploy_mcp_gateway(DP_NAME, skip_online_wait=True)
    assert gid == "gw-inprogress"
    assert not any("/gateways/register" in u for u in goto_calls)


def test_deploy_reuses_inprogress_gateway_waits_deployed_before_online():
    """PCP-20573: reusing an in-progress gateway with skip_online_wait=False must wait for it
    to be DEPLOYED (re-keying the id) BEFORE waiting for online — a reused row may still be
    provisioning, so _wait_for_gateway_online must not run on a not-yet-deployed gateway."""
    po = _make_po()
    po.page.context.request.get.side_effect = _route_get(
        gateways=[_gw(id="gw-inprogress", name=GW_NAME, status="unknown", deployed=False)])
    calls = []
    with patch.object(PageObjectMcpHub, "wait_for_gateway_deployed",
                      side_effect=lambda *a, **k: calls.append("deployed") or "gw-inprogress"), \
         patch.object(PageObjectMcpHub, "_wait_for_gateway_online",
                      side_effect=lambda *a, **k: calls.append("online")), \
         patch.object(PageObjectMcpHub, "_wait_for_target_dp_online",
                      side_effect=AssertionError("must NOT enter the wizard when a gateway already exists")):
        gid = po.deploy_mcp_gateway(DP_NAME, skip_online_wait=False)
    assert gid == "gw-inprogress"
    assert calls == ["deployed", "online"]  # deployed-wait precedes online-wait


# === PCP-21143: Register-wizard footer buttons drop data-testid (Fresco) ==========
#
# 1.17.1 migrated the Register wizard's footer nav buttons (Continue / Register &
# Deploy / Finish) to Fresco <Button>s that DROP data-testid (shared/ui/Button.tsx).
# Leading with get_by_test_id resolved to nothing, so click_button_until_enabled's
# element_handle() was None and its wait_for_function((b) => !b.disabled) burned the
# full 30s on a null arg (the #11 deploy-mcp-hub timeout). PCP-22575: _register_footer_button
# now resolves by the stable data-testid FIRST (register-continue / register-review-submit /
# register-finish, re-added Hub-side by PCP-22440), with role+name as the older-build fallback —
# the inverse of the pre-PCP-22575 label-first order, so a button-label rename can't break it.


def test_register_footer_button_prefers_testid():
    """PCP-22575: Fresco footer button -> resolve by the stable data-testid FIRST."""
    po = _make_po()
    with patch("page_object.po_mcp_hub.Util.check_dom_visibility", return_value=True):
        result = po._register_footer_button("Register & Deploy", test_id="register-review-submit")
    po.page.get_by_test_id.assert_called_with("register-review-submit")
    # returns the test-id locator, not the role+name one, when the test-id is present.
    assert result is po.page.get_by_test_id.return_value.first


def test_register_footer_button_falls_back_to_role_name_on_older_build():
    """PCP-22575: older build (pre-PCP-22440) has no data-testid -> fall back to role+name."""
    po = _make_po()
    # first check (by_test_id) False, second (by_role) True
    with patch("page_object.po_mcp_hub.Util.check_dom_visibility", side_effect=[False, True]):
        result = po._register_footer_button("Continue", test_id="register-continue")
    po.page.get_by_test_id.assert_called_with("register-continue")  # testid probed first
    assert result is po.page.get_by_role.return_value.first  # then role+name fallback returned


def test_register_footer_button_defaults_to_testid_locator_when_none_visible():
    """PCP-22575: neither variant visible yet + a test_id supplied -> return the durable test-id
    locator (a current Hub renders the test-id, not the label) so the caller's own
    check_dom_visibility polls the right hook rather than a label it never renders."""
    po = _make_po()
    with patch("page_object.po_mcp_hub.Util.check_dom_visibility", return_value=False):
        result = po._register_footer_button("Finish", test_id="register-finish")
    assert result is po.page.get_by_test_id.return_value.first  # the test-id locator
    po.page.get_by_role.assert_called()  # role+name was still probed as the fallback


def test_register_footer_button_substring_match_for_finish():
    """'Finish' is an UNANCHORED pattern so it matches 'Finish & open gateway' too."""
    po = _make_po()
    with patch("page_object.po_mcp_hub.Util.check_dom_visibility", return_value=True):
        po._register_footer_button("Finish", test_id="register-finish")
    pattern = po.page.get_by_role.call_args.kwargs["name"]
    assert pattern.search("Finish & open gateway")  # substring, not anchored


def test_register_footer_button_matches_ampersand_and_word_and():
    """PCP-22439: MCP Hub 1.20 (frontend wip-poc-1-4383ae4) relabelled the Review submit
    from 'Register & Deploy' (ampersand) to 'Register and Deploy' (the word 'and') with no
    test-id. The footer name pattern must match BOTH spellings regardless of which the
    caller passes, or deploy-mcp-hub aborts with 'forward button not found'."""
    po = _make_po()
    with patch("page_object.po_mcp_hub.Util.check_dom_visibility", return_value=True):
        po._register_footer_button("Register & Deploy", test_id="register-review-submit")
    pattern = po.page.get_by_role.call_args.kwargs["name"]
    # caller passed the ampersand spelling; both the ampersand AND the word-'and' render match
    assert pattern.search("Register & Deploy")
    assert pattern.search("Register and Deploy")

    # and the symmetric case: a caller passing the word-'and' spelling still matches both
    po2 = _make_po()
    with patch("page_object.po_mcp_hub.Util.check_dom_visibility", return_value=True):
        po2._register_footer_button("Register and Deploy", test_id="register-review-submit")
    pattern2 = po2.page.get_by_role.call_args.kwargs["name"]
    assert pattern2.search("Register and Deploy")
    assert pattern2.search("Register & Deploy")

    # a plain label with no ' & '/' and ' connector is unaffected (still a literal match)
    assert PageObjectMcpHub._footer_name_re("Continue").search("Continue")
    assert not PageObjectMcpHub._footer_name_re("Continue").search("Next")


def test_register_resource_add_uses_contextual_label():
    """PCP-21143: the resource-table create button is a Fresco <Button> whose label is
    contextual per step (ResourceTable.tsx addButtonLabel: "Add new" for ingress,
    "Add Storage Class" for storage) and drops data-testid. When the legacy testid is
    absent, the create trigger must be resolved by role+name on that contextual label —
    a hardcoded "Add new" missed the storage step's "Add Storage Class" button and hung
    on a 30s click timeout. check_dom_visibility flow: table(T), row(F→create),
    testid-add(F), role-add(T), dialog(T), submit-testid(T)."""
    po = _make_po()
    with patch("page_object.po_mcp_hub.Util.check_dom_visibility",
               side_effect=[True, False, False, True, True, True]):
        po._register_select_or_create_resource(
            "local-path", lambda: None, add_label="Add Storage Class")
    role_names = [c.kwargs["name"] for c in po.page.get_by_role.call_args_list if "name" in c.kwargs]
    assert any(getattr(n, "search", None) and n.search("Add Storage Class") for n in role_names), \
        "create button must be resolved by role+name on the contextual add_label"


def test_register_resource_add_label_defaults_to_add_new():
    """The default add label stays 'Add new' (Network Access / ingress step parity)."""
    po = _make_po()
    with patch("page_object.po_mcp_hub.Util.check_dom_visibility",
               side_effect=[True, False, False, True, True, True]):
        po._register_select_or_create_resource("mcp-dp", lambda: None)
    role_names = [c.kwargs["name"] for c in po.page.get_by_role.call_args_list if "name" in c.kwargs]
    assert any(getattr(n, "search", None) and n.search("Add new") for n in role_names)


def test_register_resource_add_and_submit_prefer_test_id():
    """PCP-22620: the resource-table create trigger and the Add-Resource dialog submit are already
    test-id-FIRST (`dp-action-resource-add` / `dp-action-add-resource-submit`, both re-added by
    PCP-22619). When the add test-id is visible the contextual-label role+name fallback is never
    built, and the submit is resolved by its test-id (no CSS fallback). cdv: table(T),
    row absent(F->create), add test-id(T->short-circuit), dialog open(T), submit test-id(T)."""
    po = _make_po()
    with patch("page_object.po_mcp_hub.Util.check_dom_visibility",
               side_effect=[True, False, True, True, True]), \
         patch("page_object.po_mcp_hub.Util.click_button_until_enabled"):
        po._register_select_or_create_resource("mcp-dp", lambda: None)
    po.page.get_by_test_id.assert_any_call("dp-action-resource-add")
    po.page.get_by_test_id.assert_any_call("dp-action-add-resource-submit")
    # add test-id visible -> the add-button role+name fallback must not be built (nor any other
    # role locator in this method), and the submit CSS fallback (.p-dialog-footer) is not used.
    po.page.get_by_role.assert_not_called()
    footer_css = [c for c in po.page.locator.call_args_list
                  if c.args and ".p-dialog-footer" in str(c.args[0])]
    assert not footer_css, "submit test-id visible -> CSS footer fallback must not be built"


# === PCP-22029: Fresco Register MODAL — 'Next', DP dropdown filter, card scope ==========
#
# The Register wizard migrated to a Fresco MODAL (tp-mcp-hub PCP-22027): the deep-link
# /gateways/register redirects to ?register=true and opens it; the forward footer button is
# relabelled Continue -> Next; the DP picker gained a .p-dropdown-filter + register-dp-option
# rows; and the merged "Network & Deployment" step renders multiple resource tables at once
# (scope by ConfigCard). These pin the adaptation's intent.


def test_register_continue_uses_next_when_present():
    """The Fresco forward button is 'Next' — _register_continue resolves it test-id-first
    (register-continue, PCP-22575) and does NOT fall back to the legacy 'Continue'."""
    po = _make_po()
    calls = []
    next_btn = MagicMock(name="next-btn")

    def _footer(label, test_id=None):
        calls.append((label, test_id))
        return next_btn

    with patch.object(PageObjectMcpHub, "_register_footer_button", side_effect=_footer), \
         patch("page_object.po_mcp_hub.Util.check_dom_visibility", return_value=True), \
         patch("page_object.po_mcp_hub.Util.click_button_until_enabled") as click:
        po._register_continue()
    # PCP-22575: the primary call now carries the register-continue test-id, and there is no fallback.
    assert calls == [("Next", "register-continue")], f"'Next' + register-continue only, no fallback; got {calls}"
    click.assert_called_once_with(po.page, next_btn)


def test_register_continue_falls_back_to_legacy_continue():
    """Older page wizard still uses 'Continue' — _register_continue tries 'Next' first, then falls
    back to the legacy 'Continue' (+ register-continue testid) when 'Next' is not visible."""
    po = _make_po()
    labels = []
    next_btn, continue_btn = MagicMock(name="next"), MagicMock(name="continue")

    def _footer(label, test_id=None):
        labels.append((label, test_id))
        return next_btn if label == "Next" else continue_btn

    # 'Next' locator not visible -> triggers the Continue fallback; anything else visible.
    def _cdv(page, locator, *a, **k):
        return locator is not next_btn

    with patch.object(PageObjectMcpHub, "_register_footer_button", side_effect=_footer), \
         patch("page_object.po_mcp_hub.Util.check_dom_visibility", side_effect=_cdv), \
         patch("page_object.po_mcp_hub.Util.click_button_until_enabled") as click:
        po._register_continue()
    assert labels[0] == ("Next", "register-continue"), f"'Next' + register-continue tried first; got {labels}"
    assert ("Continue", "register-continue") in labels, \
        f"must fall back to legacy 'Continue' + testid; got {labels}"
    click.assert_called_once_with(po.page, continue_btn)


def test_register_dp_picker_fills_filter_and_selects_testid_option():
    """Fresco DP dropdown -> open the trigger, type into '.p-dropdown-filter', then click the
    'register-dp-option' row (PCP-22027/22028)."""
    po = _make_po()
    with patch("page_object.po_mcp_hub.Util.check_dom_visibility", return_value=True):
        po._register_pick_target_dp(DP_NAME)
    po.page.get_by_test_id.assert_any_call("register-dp-picker")
    po.page.get_by_test_id.assert_any_call("register-dp-option")
    po.page.locator.assert_any_call(".p-dropdown-filter")
    po.page.locator.return_value.first.fill.assert_called_with(DP_NAME)  # filter typed
    # register-dp-option is matched with an ANCHORED regex (^name(?!\d)) so 'dp1' != 'dp10'
    anchored = po.page.get_by_test_id.return_value.filter.call_args.kwargs.get("has_text")
    pat = getattr(anchored, "pattern", "")
    assert pat.startswith("^") and "(?!" in pat, \
        f"register-dp-option must use an anchored regex; got {anchored!r}"
    # the resolved register-dp-option row was clicked
    po.page.get_by_test_id.return_value.filter.return_value.first.click.assert_called()


def test_register_dp_picker_falls_back_to_dropdown_item():
    """Older dropdown (no 'register-dp-option') -> fall back to '.p-dropdown-item' WITHIN the same
    branch (never hard-fail before the fallback)."""
    po = _make_po()
    # picker(T), trigger(T), trigger-recheck(T), filter(T), register-dp-option(F) -> fallback,
    # then .p-dropdown-item(T)
    with patch("page_object.po_mcp_hub.Util.check_dom_visibility",
               side_effect=[True, True, True, True, False, True]):
        po._register_pick_target_dp(DP_NAME)
    po.page.locator.assert_any_call(".p-dropdown-item")


def test_register_resource_scopes_to_config_card():
    """Merged Configure step renders several dp-action-resource tables — with card_test_id the
    table/row lookups are scoped to that ConfigCard, not page-global (PCP-22028/22029)."""
    po = _make_po()
    with patch("page_object.po_mcp_hub.Util.check_dom_visibility", return_value=True):
        po._register_select_or_create_resource(
            "mcp-dp", lambda: None, card_test_id="register-config-section-network")
    po.page.get_by_test_id.assert_any_call("register-config-section-network")
    card = po.page.get_by_test_id.return_value
    card.get_by_test_id.assert_any_call("dp-action-resource-table")
    card.get_by_test_id.assert_any_call("dp-action-resource-row")


def test_deploy_wires_card_test_id_for_network_and_deploy_mode():
    """deploy_mcp_gateway scopes the ingress resource to the Network ConfigCard and the storage
    resource to the Deployment-Mode ConfigCard (the merged Fresco Configure step, PCP-22028/22029)."""
    po = _make_po()
    po._open_gateway_from_home = MagicMock(return_value=None)
    po._hub_url = lambda route="": f"https://cp-sub1.example.com/cp/mcphub{route}"
    po.page.goto.side_effect = lambda url, *a, **k: None
    seen = []

    def _sel(*a, **k):
        seen.append(k.get("card_test_id"))

    # open-race(T), deployment-heading(T), mode-card(T), dp-picker(T=merged), deploy-mode(T=merged)
    cdv = [True, True, True, True, True]

    def _cdv(*a, **k):
        return cdv.pop(0) if cdv else True

    with patch.object(PageObjectMcpHub, "_find_existing_gateway_id", return_value=""), \
         patch.object(PageObjectMcpHub, "_wait_for_target_dp_online"), \
         patch.object(PageObjectMcpHub, "_register_continue"), \
         patch.object(PageObjectMcpHub, "_register_fill_identity"), \
         patch.object(PageObjectMcpHub, "_register_pick_target_dp"), \
         patch.object(PageObjectMcpHub, "_register_select_or_create_resource", side_effect=_sel), \
         patch.object(PageObjectMcpHub, "_register_review_and_deploy", return_value="gw-id"), \
         patch.object(PageObjectMcpHub, "_wait_for_gateway_online"), \
         patch("page_object.po_mcp_hub.Util.check_dom_visibility", side_effect=_cdv):
        po.deploy_mcp_gateway(DP_NAME, skip_online_wait=True)
    assert "register-config-section-network" in seen, \
        f"ingress must be scoped to the network card; got {seen}"
    assert "register-config-section-deploy-mode" in seen, \
        f"storage must be scoped to the deploy-mode card; got {seen}"


def test_deploy_errors_distinctly_when_modal_not_open():
    """If neither the Deployment heading nor the Setup DP picker appears (the OR-race open-signal is
    absent), deploy fails with the modal-not-open diagnostic, not the misleading CP-mode error."""
    po = _make_po()
    po._hub_url = lambda route="": f"https://cp-sub1.example.com/cp/mcphub{route}"
    po.page.goto.side_effect = lambda url, *a, **k: None
    # Single leading check: the OR-race open-signal (heading OR register-dp-picker) is False -> abort.
    with patch.object(PageObjectMcpHub, "_find_existing_gateway_id", return_value=""), \
         patch.object(PageObjectMcpHub, "_wait_for_target_dp_online"), \
         patch("page_object.po_mcp_hub.Util.check_dom_visibility", side_effect=[False]), \
         patch("page_object.po_mcp_hub.Util.exit_error", side_effect=SystemExit) as exit_err:
        with pytest.raises(SystemExit):
            po.deploy_mcp_gateway(DP_NAME, skip_online_wait=True)
    msg = exit_err.call_args.args[0].lower()
    assert "modal did not open" in msg, \
        f"expected the modal-not-open diagnostic; got: {msg}"


def test_deploy_flag_off_setup_entry_does_not_abort_and_reaches_setup():
    """PCP-22029 (alpha.24 regression): on a CP-default build (CP mode + enableStandaloneGateway
    off -> cpGateActive) the Fresco Register wizard DROPS the Deployment mode-picker step and opens
    directly on the Setup step. So register-mode-provision-auto never renders, and the portaled
    register-gateway-wizard wrapper has no visible box -- yet the modal IS open (register-dp-picker
    visible). deploy_mcp_gateway must NOT abort with 'modal did not open', must NOT click the absent
    mode card, and must proceed to pick the DP (mirrors tp-mcp-hub e2e RegisterGatewayPage.open /
    selectAutoInstall / hasDeploymentStep, PCP-22220).

    Uses a by-LOCATOR check_dom_visibility mock (visibility decided by WHAT is probed -- the OR-race
    open-signal locator, the heading-only has_deployment_step probe, or a testid -- not by positional
    call order) so the physical DOM scenario is pinned stably across the gate restructure. Pre-fix
    this reproduces the real alpha.24 modal-not-open abort (RED, via the old register-gateway-wizard
    + mode-card gate with Fact B's invisible portaled wrapper); post-fix it proceeds into the Setup
    step (GREEN)."""
    po = _make_po()
    po._open_gateway_from_home = MagicMock(return_value=None)
    po._hub_url = lambda route="": f"https://cp-sub1.example.com/cp/mcphub{route}"
    po.page.goto.side_effect = lambda url, *a, **k: None

    # Fixed tracked mock for the mode card so we can assert it is NEVER clicked on the flag-off path.
    mode_card = MagicMock(_tid="register-mode-provision-auto")

    def _by_test_id(tid):
        return mode_card if tid == "register-mode-provision-auto" else MagicMock(_tid=tid)

    # get_by_role('heading', ...) -> mock tagged _role='heading'; its .or_(other) -> the combined
    # OR-race open-signal locator tagged _open_signal. So the cdv mock decides by WHAT is probed,
    # robust to the gate's call order.
    def _by_role(role, **k):
        m = MagicMock(_role=role)
        # the gate uses `.or_(...).first`, so the open-signal tag must live on `.first` of the combined
        combined = MagicMock()
        combined.first = MagicMock(_open_signal=True)
        m.or_ = MagicMock(return_value=combined)
        return m

    po.page.get_by_test_id.side_effect = _by_test_id
    po.page.get_by_role.side_effect = _by_role

    def _cdv(page, locator, *a, **k):
        # `is True`, not truthiness: an unset attr on a MagicMock auto-creates a truthy child mock,
        # so match ONLY the explicitly-tagged combined open-signal locator here (== / is checks below
        # are likewise value-exact, so an auto-child never spuriously matches).
        if getattr(locator, "_open_signal", None) is True:
            return True    # OR-race (heading OR register-dp-picker).first: modal DID open (dp-picker present)
        if getattr(locator, "_role", None) == "heading":
            return False   # Fact A: Deployment step dropped -> heading absent -> has_deployment_step False
        tid = getattr(locator, "_tid", None)
        if tid == "register-gateway-wizard":
            return False   # Fact B: portaled wrapper -> no visible box (drives the OLD gate's true modal-not-open path pre-fix)
        if tid == "register-mode-provision-auto":
            return False   # rendered only on the (dropped) Deployment step
        if tid == "register-dp-picker":
            return True    # Setup step DP picker visible (downstream dp_on_identity probe)
        return True        # everything downstream proceeds

    with patch.object(PageObjectMcpHub, "_find_existing_gateway_id", return_value=""), \
         patch.object(PageObjectMcpHub, "_wait_for_target_dp_online"), \
         patch.object(PageObjectMcpHub, "_register_fill_identity"), \
         patch.object(PageObjectMcpHub, "_register_pick_target_dp") as pick_dp, \
         patch.object(PageObjectMcpHub, "_register_continue"), \
         patch.object(PageObjectMcpHub, "_register_select_or_create_resource"), \
         patch.object(PageObjectMcpHub, "_register_review_and_deploy", return_value="gw-id"), \
         patch.object(PageObjectMcpHub, "_wait_for_gateway_online"), \
         patch("page_object.po_mcp_hub.Util.check_dom_visibility", side_effect=_cdv), \
         patch("page_object.po_mcp_hub.Util.exit_error", side_effect=SystemExit) as exit_err:
        po.deploy_mcp_gateway(DP_NAME, skip_online_wait=True)

    assert not exit_err.called, \
        f"flag-off Setup entry must NOT abort as 'modal did not open'; got exit_error({exit_err.call_args})"
    mode_card.click.assert_not_called()   # the (absent) Deployment mode card must never be clicked
    pick_dp.assert_called_once()          # proceeded into the Setup step


def test_deploy_errors_distinctly_when_non_cp_backend():
    """When the Deployment step IS shown but the auto-provision mode card is absent, the backend is
    not in CP mode -> deploy must fail with the distinct 'card not found / CP mode' diagnostic, NOT
    the modal-not-open one. Guards the RESTORED non-CP diagnostic (pre-fix that branch was dead code:
    the portaled register-gateway-wizard was never visible, so the old gate mis-said modal-not-open)."""
    po = _make_po()
    po._hub_url = lambda route="": f"https://cp-sub1.example.com/cp/mcphub{route}"
    po.page.goto.side_effect = lambda url, *a, **k: None
    # Leading checks: open-race True (heading present), has_deployment_step True (heading),
    # mode-card False (non-CP backend has no provision-auto card).
    with patch.object(PageObjectMcpHub, "_find_existing_gateway_id", return_value=""), \
         patch.object(PageObjectMcpHub, "_wait_for_target_dp_online"), \
         patch("page_object.po_mcp_hub.Util.check_dom_visibility", side_effect=[True, True, False]), \
         patch("page_object.po_mcp_hub.Util.exit_error", side_effect=SystemExit) as exit_err:
        with pytest.raises(SystemExit):
            po.deploy_mcp_gateway(DP_NAME, skip_online_wait=True)
    msg = exit_err.call_args.args[0].lower()
    assert "cp mode" in msg or "card not found" in msg, \
        f"expected the non-CP-mode diagnostic; got: {msg}"
    assert "modal did not open" not in msg, \
        f"must NOT be the modal-not-open diagnostic; got: {msg}"


def test_deploy_flag_on_clicks_mode_card_then_enters_setup():
    """flag-on / legacy build: the Deployment step IS present with the auto-provision card, so
    deploy_mcp_gateway clicks 'Deploy to a TIBCO Data Plane' and continues into Setup -- the
    symmetric positive of the flag-off skip (which asserts the card is NOT clicked). Same by-locator
    mock style so it is robust to the gate's call order."""
    po = _make_po()
    po._open_gateway_from_home = MagicMock(return_value=None)
    po._hub_url = lambda route="": f"https://cp-sub1.example.com/cp/mcphub{route}"
    po.page.goto.side_effect = lambda url, *a, **k: None

    mode_card = MagicMock(_tid="register-mode-provision-auto")

    def _by_test_id(tid):
        return mode_card if tid == "register-mode-provision-auto" else MagicMock(_tid=tid)

    def _by_role(role, **k):
        m = MagicMock(_role=role)
        combined = MagicMock()
        combined.first = MagicMock(_open_signal=True)
        m.or_ = MagicMock(return_value=combined)
        return m

    po.page.get_by_test_id.side_effect = _by_test_id
    po.page.get_by_role.side_effect = _by_role

    def _cdv(page, locator, *a, **k):
        if getattr(locator, "_open_signal", None) is True:
            return True    # OR-race: modal open (heading present)
        if getattr(locator, "_role", None) == "heading":
            return True    # flag-on: Deployment step present -> has_deployment_step True
        if getattr(locator, "_tid", None) == "register-mode-provision-auto":
            return True    # auto-provision card present (CP mode)
        return True        # downstream proceeds

    with patch.object(PageObjectMcpHub, "_find_existing_gateway_id", return_value=""), \
         patch.object(PageObjectMcpHub, "_wait_for_target_dp_online"), \
         patch.object(PageObjectMcpHub, "_register_fill_identity"), \
         patch.object(PageObjectMcpHub, "_register_pick_target_dp"), \
         patch.object(PageObjectMcpHub, "_register_continue"), \
         patch.object(PageObjectMcpHub, "_register_select_or_create_resource"), \
         patch.object(PageObjectMcpHub, "_register_review_and_deploy", return_value="gw-id"), \
         patch.object(PageObjectMcpHub, "_wait_for_gateway_online"), \
         patch("page_object.po_mcp_hub.Util.check_dom_visibility", side_effect=_cdv), \
         patch("page_object.po_mcp_hub.Util.exit_error", side_effect=SystemExit) as exit_err:
        po.deploy_mcp_gateway(DP_NAME, skip_online_wait=True)

    assert not exit_err.called
    mode_card.click.assert_called_once()   # flag-on: the mode card IS clicked


# === PCP-21143: gateway name is prefixed 'gateway-<dp>' =============================
#
# The registered gateway is named gateway-<dp> (not the bare DP name) so it reads
# distinctly from its target Data Plane. _gateway_name() is the single source of
# truth shared by the Identity-step fill AND the name-based gateway lookups
# (_find_existing_gateway_id idempotency + _api_get_gateway status poll), so the
# wizard-written name and the reuse/status reads can never drift.


def test_gateway_name_is_prefixed():
    """_gateway_name maps a DP name to 'gateway-<dp>'."""
    assert PageObjectMcpHub._gateway_name("k8s-auto-dp2") == "gateway-k8s-auto-dp2"
    assert PageObjectMcpHub._gateway_name(DP_NAME) == GW_NAME


def test_register_fill_identity_writes_prefixed_name():
    """The Identity step fills 'gateway-<dp>', NOT the bare DP name (register-name testid)."""
    po = _make_po()
    with patch("page_object.po_mcp_hub.Util.check_dom_visibility", return_value=True):
        po._register_fill_identity(DP_NAME)
    po.page.get_by_test_id.assert_called_with("register-name")
    po.page.get_by_test_id.return_value.fill.assert_called_with(GW_NAME)


def test_register_fill_identity_legacy_input_also_prefixed():
    """Older build (no register-name testid) -> the plain text input also gets 'gateway-<dp>'."""
    po = _make_po()
    # first check (register-name testid) False, then the legacy .text-input True
    with patch("page_object.po_mcp_hub.Util.check_dom_visibility", side_effect=[False, True]):
        po._register_fill_identity(DP_NAME)
    po.page.locator.return_value.first.fill.assert_called_with(GW_NAME)


def test_find_existing_gateway_id_ignores_bare_dp_name():
    """A gateway named with the bare DP name (no prefix) must NOT be reused — the
    contract is the prefixed name, so a legacy/foreign bare-named row is skipped."""
    po = _make_po()
    po.page.context.request.get.return_value = _api_response(
        [_gw(id="bare", name=DP_NAME, deployed=True)])
    assert po._find_existing_gateway_id(DP_NAME) is None


def test_is_gateway_deployed_looks_up_prefixed_name():
    """PCP-21143 (cross-review): the home-list / dashboard fallback must search for the
    'gateway-<dp>' name, NOT the bare DP name — otherwise the UI lookup drifts from the
    API lookups and relies on accidental has_text substring containment (which also
    widens collisions to superstring DP names)."""
    po = _make_po()
    po._open_gateway_from_home = MagicMock(return_value="gw-1")
    assert po.is_gateway_deployed(DP_NAME) is True
    po._open_gateway_from_home.assert_called_once_with(GW_NAME)


# === PCP-21173: gateway reuse/status binds to the DP's CURRENT dataPlaneId ===========
#
# After a DP is deleted and recreated with the SAME name, /gateways keeps the OLD DP's
# orphaned gateway row (stale dataPlaneId). A name-only match treated that orphan as
# the live gateway, so deploy_mcp_gateway "reused" it and SKIPPED the wizard — the new
# DP silently got no gateway (false success). _resolve_dataplane_id resolves the DP's
# current id from /data-planes and the lookups require gateway.dataPlaneId to match;
# an unresolvable id degrades to name-only (no PCP-20336 dedup regression).


def test_resolve_dataplane_id_returns_current_dpid():
    """/data-planes -> the cp_dp DP's current dpId by name."""
    po = _make_po()
    po.page.context.request.get.side_effect = _route_get(
        data_planes=[_dp(name=DP_NAME, dp_id="dp-new")])
    assert po._resolve_dataplane_id(DP_NAME) == "dp-new"


def test_resolve_dataplane_id_none_when_absent_or_error():
    """DP not listed -> None; a non-OK /data-planes -> None (callers degrade to name-only)."""
    po = _make_po()
    po.page.context.request.get.side_effect = _route_get(data_planes=[_dp(name="other")])
    assert po._resolve_dataplane_id(DP_NAME) is None
    po.page.context.request.get.side_effect = lambda url, *a, **k: _api_response([], ok=False, status=500)
    assert po._resolve_dataplane_id(DP_NAME) is None


def test_find_existing_gateway_id_ignores_orphan_with_stale_dataplaneid():
    """Core PCP-21173 regression: a deployed cp_dp gateway whose dataPlaneId points at
    the OLD (deleted) DP must NOT be reused for the recreated same-named DP."""
    po = _make_po()
    po.page.context.request.get.side_effect = _route_get(
        gateways=[_gw(id="orphan", name=GW_NAME, deployed=True, data_plane_id="dp-old")],
        data_planes=[_dp(name=DP_NAME, dp_id="dp-new")])
    assert po._find_existing_gateway_id(DP_NAME) is None


def test_find_existing_gateway_id_reuses_when_dataplaneid_matches():
    """A gateway on the CURRENT DP (matching dataPlaneId) is still reused (no regression)."""
    po = _make_po()
    po.page.context.request.get.side_effect = _route_get(
        gateways=[_gw(id="live", name=GW_NAME, deployed=True, data_plane_id="dp-new")],
        data_planes=[_dp(name=DP_NAME, dp_id="dp-new")])
    assert po._find_existing_gateway_id(DP_NAME) == "live"


def test_find_existing_gateway_id_name_only_when_dpid_unresolvable():
    """If the current dpId can't be resolved (DP not listed), fall back to name-only so
    PCP-20336 duplicate-suppression is preserved (never block a deploy)."""
    po = _make_po()
    po.page.context.request.get.side_effect = _route_get(
        gateways=[_gw(id="x", name=GW_NAME, deployed=True, data_plane_id="dp-old")],
        data_planes=[])  # DP not listed -> dpId unresolvable
    assert po._find_existing_gateway_id(DP_NAME) == "x"


def test_api_get_gateway_name_fallback_ignores_orphan_with_stale_dataplaneid():
    """The status-poll name fallback must also reject a stale-dataPlaneId orphan."""
    po = _make_po()
    po.page.context.request.get.side_effect = _route_get(
        gateways=[_gw(id="orphan", name=GW_NAME, data_plane_id="dp-old")],
        data_planes=[_dp(name=DP_NAME, dp_id="dp-new")])
    assert po._api_get_gateway(dp_name=DP_NAME) is None


# --- PCP-21173 cross-review hardening: empty-string / absent dataPlaneId edge cases ---
# The backend emits a gateway's dataPlaneId as `dp_id || ''`, so an orphan/`direct`
# row can carry dataPlaneId == "" (falsy, not None). The match guard keys on a FALSY
# resolved id (`not dp_id`), not `is None`, so "" degrades to name-only and a truthy id
# never spuriously equals an empty/absent gateway dataPlaneId.


def test_resolve_dataplane_id_empty_dpid_degrades_to_none():
    """A /data-planes row with dpId == "" (and no usable id) resolves to None, so callers
    degrade to name-only rather than requiring an impossible `"" == <gateway id>`."""
    po = _make_po()
    po.page.context.request.get.side_effect = _route_get(
        data_planes=[_dp(name=DP_NAME, dp_id="")])
    assert po._resolve_dataplane_id(DP_NAME) is None


def test_resolve_dataplane_id_ignores_non_contract_id_field():
    """Only the verified-contract `dpId` is honored. A /data-planes row carrying a
    different `id` field (outside the contract) but no `dpId` resolves to None — so
    callers degrade to name-only rather than comparing gateways against a wrong id that
    matches none of them (review: adhanshe-tibco, PCP-21173)."""
    po = _make_po()
    po.page.context.request.get.side_effect = _route_get(
        data_planes=[{"name": DP_NAME, "origin": "cp_dp", "id": "not-the-dpid"}])
    assert po._resolve_dataplane_id(DP_NAME) is None


def test_resolve_dataplane_id_none_on_request_exception():
    """request.get raising (network blip) -> None (the except branch), so the lookup
    degrades to name-only instead of propagating."""
    po = _make_po()
    def _boom(url, *a, **k):
        raise ConnectionError("boom")
    po.page.context.request.get.side_effect = _boom
    assert po._resolve_dataplane_id(DP_NAME) is None


def test_find_existing_gateway_id_rejects_empty_dataplaneid_when_dp_resolves():
    """When the DP resolves to a real id, a gateway whose dataPlaneId is "" (orphan/direct
    artifact) must NOT match — `"" == <real id>` is False, so it is rejected, not reused."""
    po = _make_po()
    po.page.context.request.get.side_effect = _route_get(
        gateways=[_gw(id="empty", name=GW_NAME, deployed=True, data_plane_id="")],
        data_planes=[_dp(name=DP_NAME, dp_id="dp-new")])
    assert po._find_existing_gateway_id(DP_NAME) is None


def test_find_existing_gateway_id_name_only_reuses_despite_stale_id():
    """Name-only degrade (dpId unresolvable) reuses even a row whose dataPlaneId differs
    from another same-named row — proves the guard short-circuits on a falsy dp_id and
    does not secretly compare dataPlaneId (PCP-20336 reuse-first preserved)."""
    po = _make_po()
    po.page.context.request.get.side_effect = _route_get(
        gateways=[_gw(id="first", name=GW_NAME, deployed=True, data_plane_id="dp-old"),
                  _gw(id="second", name=GW_NAME, deployed=True, data_plane_id="dp-older")],
        data_planes=[])  # unresolvable -> name-only
    assert po._find_existing_gateway_id(DP_NAME) == "first"


# === PCP-21482: Register-wizard gateway-name field gated on DP readiness ===========
#
# On newer MCP Hub (base 1.19.0-alpha.160/161) the Identity-step name input renders
# VISIBLE but DISABLED (aria-describedby="register-name-awaiting-dp") until the
# wizard's target-DP list resolves. _register_fill_identity previously waited only
# for visibility, then called .fill() — which auto-waits for editability and blew its
# 30s timeout on the still-disabled field (the deploy-mcp-hub Register fill timeout).
# The fix waits for the field to be ENABLED (Util.check_dom_enabled) before filling,
# and fails loud with a screenshot if it never enables. The legacy plain-text-input
# path (older builds, no register-name testid) is not DP-gated, so it keeps its
# visibility-only wait.


def test_register_fill_identity_waits_for_enabled_before_fill():
    """The register-name (testid) path must wait for the field to be ENABLED before
    filling — else Playwright .fill() times out on the disabled 'awaiting-dp' input."""
    po = _make_po()
    with patch("page_object.po_mcp_hub.Util.check_dom_visibility", return_value=True), \
         patch("page_object.po_mcp_hub.Util.check_dom_enabled", return_value=True) as enabled, \
         patch("page_object.po_mcp_hub.Util.exit_error",
               side_effect=AssertionError("must not abort when the field enables")):
        po._register_fill_identity(DP_NAME)
    assert enabled.called  # the enabled-guard ran
    po.page.get_by_test_id.return_value.fill.assert_called_with(GW_NAME)


def test_register_fill_identity_exits_when_name_field_stays_disabled():
    """If the name field never enables (DP never ready) -> loud exit_error with a
    screenshot, NOT a silent Playwright .fill() timeout on the disabled input."""
    po = _make_po()
    with patch("page_object.po_mcp_hub.Util.check_dom_visibility", return_value=True), \
         patch("page_object.po_mcp_hub.Util.check_dom_enabled", return_value=False), \
         patch("page_object.po_mcp_hub.Util.exit_error", side_effect=SystemExit(1)) as exit_error:
        with pytest.raises(SystemExit):
            po._register_fill_identity(DP_NAME)
    assert exit_error.called
    # never attempted to fill the disabled field
    po.page.get_by_test_id.return_value.fill.assert_not_called()


def test_register_fill_identity_legacy_path_skips_enabled_guard():
    """The legacy plain-text-input path (no register-name testid) is not DP-gated, so
    it must NOT invoke the enabled-guard — it fills after the visibility wait."""
    po = _make_po()
    # first check_dom_visibility (register-name testid) False, then legacy input True
    with patch("page_object.po_mcp_hub.Util.check_dom_visibility", side_effect=[False, True]), \
         patch("page_object.po_mcp_hub.Util.check_dom_enabled",
               side_effect=AssertionError("legacy path must not use the enabled-guard")):
        po._register_fill_identity(DP_NAME)
    po.page.locator.return_value.first.fill.assert_called_with(GW_NAME)


# --- Util.check_dom_enabled: logged polling on is_enabled() -----------------------


def _enabled_locator(enabled):
    """A locator mock whose is_enabled() returns the given bool (or cycles a list)."""
    loc = MagicMock()
    if isinstance(enabled, list):
        loc.is_enabled.side_effect = enabled
    else:
        loc.is_enabled.return_value = enabled
    return loc


def test_check_dom_enabled_returns_true_when_enabled():
    """Enabled on the first poll -> returns True immediately (single is_enabled call)."""
    page = MagicMock()  # wait_for_timeout is a no-op mock, so no real sleeping
    loc = _enabled_locator(True)
    assert Util.check_dom_enabled(page, loc, interval=2, max_wait=10) is True
    assert loc.is_enabled.call_count == 1


def test_check_dom_enabled_polls_until_enabled():
    """Disabled for two polls, then enabled -> returns True (does not give up early)."""
    page = MagicMock()
    loc = _enabled_locator([False, False, True])
    assert Util.check_dom_enabled(page, loc, interval=1, max_wait=10) is True
    assert loc.is_enabled.call_count == 3


def test_check_dom_enabled_times_out_when_never_enabled():
    """Never enabled within the budget -> returns False (caller then screenshots/exits)."""
    page = MagicMock()
    loc = _enabled_locator(False)
    assert Util.check_dom_enabled(page, loc, interval=1, max_wait=3) is False


def test_check_dom_enabled_keeps_polling_when_is_enabled_raises():
    """Playwright is_enabled() RAISES on a transiently-absent element (unlike
    is_visible()). The helper must swallow it and keep polling, then succeed once
    the element resolves — never propagate the exception (graceful-boolean contract)."""
    page = MagicMock()
    loc = MagicMock()
    loc.is_enabled.side_effect = [RuntimeError("locator resolved to 0 elements"), True]
    assert Util.check_dom_enabled(page, loc, interval=1, max_wait=10) is True
    assert loc.is_enabled.call_count == 2


def test_check_dom_enabled_returns_false_not_raise_when_always_absent():
    """If is_enabled() raises on every poll (element never resolves), the helper
    returns False rather than raising — so the caller's exit_error/screenshot runs."""
    page = MagicMock()
    loc = MagicMock()
    loc.is_enabled.side_effect = RuntimeError("locator resolved to 0 elements")
    assert Util.check_dom_enabled(page, loc, interval=1, max_wait=3) is False


# === PCP-21482: Register wizard merged Target-DP into the Identity step ============
#
# Newer MCP Hub (1.17.1-alpha.81 on base 1.19.0-alpha.161) merged the Target Data
# Plane picker INTO the Identity step and gates the gateway-name field on it: the
# name input stays disabled (aria-describedby="register-name-awaiting-dp", hint
# "Select a Data Plane above to name the gateway.") until a DP row is selected. So
# deploy_mcp_gateway must pick the DP BEFORE filling the name when the DP picker is
# on the Identity step (verified live on ins-owen-mcp-81-b), while older builds keep
# them as two separate steps (name here, DP next). deploy_mcp_gateway branches on
# whether register-dp-option is visible on the Identity step.


def _deploy_call_order(dp_on_identity):
    """Run deploy_mcp_gateway capturing the order of pick-dp vs fill-name. The leading
    check_dom_visibility calls are (1) the mode-select card, then the DP-on-Identity
    probe. PCP-21970: that probe is now `register-dp-picker` OR `register-dp-option`,
    so the merged path is one check (picker present, short-circuits) while the legacy
    path is two (picker absent, option absent). The _register_* helpers are patched so
    they add no further check_dom_visibility."""
    po = _make_po()
    calls = []
    po._open_gateway_from_home = MagicMock(return_value=None)
    po._hub_url = lambda route="": f"https://cp-sub1.example.com/cp/mcphub{route}"
    po.page.goto.side_effect = lambda url, *a, **k: None
    # leading check_dom_visibility: (1) open-race (heading OR register-dp-picker, PCP-22029), (2) the
    # Deployment heading (has_deployment_step), (3) the mode-select card; then the DP-on-Identity
    # probe: merged -> picker True (1 check), legacy -> picker False + option False (2 checks).
    # Remaining checks default True.
    cdv = [True, True, True, True] if dp_on_identity else [True, True, True, False, False]

    def _cdv(*a, **k):
        return cdv.pop(0) if cdv else True

    with patch.object(PageObjectMcpHub, "_wait_for_target_dp_online"), \
         patch.object(PageObjectMcpHub, "_register_continue",
                      side_effect=lambda *a, **k: calls.append("continue")), \
         patch.object(PageObjectMcpHub, "_register_fill_identity",
                      side_effect=lambda *a, **k: calls.append("fill_name")), \
         patch.object(PageObjectMcpHub, "_register_pick_target_dp",
                      side_effect=lambda *a, **k: calls.append("pick_dp")), \
         patch.object(PageObjectMcpHub, "_register_select_or_create_resource"), \
         patch.object(PageObjectMcpHub, "_register_review_and_deploy", return_value="gw-id"), \
         patch.object(PageObjectMcpHub, "_wait_for_gateway_online"), \
         patch("page_object.po_mcp_hub.Util.check_dom_visibility", side_effect=_cdv):
        po.deploy_mcp_gateway(DP_NAME, skip_online_wait=True)
    return calls


def test_merged_identity_step_picks_dp_before_filling_name():
    """Newer merged step: pick the DP BEFORE filling the name (name is gated on DP
    selection), and the DP is picked exactly once (no separate second DP step)."""
    calls = _deploy_call_order(dp_on_identity=True)
    assert "pick_dp" in calls and "fill_name" in calls
    assert calls.index("pick_dp") < calls.index("fill_name"), \
        f"merged flow must pick DP before filling name; got {calls}"
    assert calls.count("pick_dp") == 1


def test_legacy_two_step_fills_name_then_picks_dp():
    """Older two-step flow: fill the name on the Identity step, then pick the DP on
    the following step (backward compatibility)."""
    calls = _deploy_call_order(dp_on_identity=False)
    assert calls.index("fill_name") < calls.index("pick_dp"), \
        f"legacy flow must fill name before picking DP; got {calls}"
    assert calls.count("pick_dp") == 1


# === PCP-21482: Register wizard merged Network Access + Deployment Mode/Storage ======
#
# Newer MCP Hub also merged Network Access and Deployment Mode (Lite/Prod + Storage
# Class) into ONE "Network & Deployment" step (register-config-section-deploy-mode
# present alongside the network section). The single Continue is gated on BOTH the
# ingress route AND a storage class being selected — so deploy_mcp_gateway must select
# the storage class on the SAME step (no Continue between ingress and storage) when the
# deploy-mode section is present; older builds keep them as two steps (a Continue
# between). Verified live on ins-owen-mcp-81-b: Continue stayed disabled after the
# ingress select and only enabled once the storage class was also selected.


def _deploy_full_order(step2_merged=True, step3_merged=True):
    """Capture the full ordered sequence of pick_dp / fill_name / ('select', name) /
    continue through deploy_mcp_gateway. check_dom_visibility side_effect: (1) open-race
    (heading OR register-dp-picker, PCP-22029), (2) the Deployment heading (has_deployment_step),
    (3) the mode-select card, (4) register-dp-picker-on-Identity = step2_merged,
    (5) register-config-section-deploy-mode = step3_merged; the _register_* helpers are patched so
    they add no further check_dom_visibility."""
    po = _make_po()
    calls = []
    po._open_gateway_from_home = MagicMock(return_value=None)
    po._hub_url = lambda route="": f"https://cp-sub1.example.com/cp/mcphub{route}"
    po.page.goto.side_effect = lambda url, *a, **k: None
    cdv = [True, True, True, step2_merged, step3_merged]

    def _cdv(*a, **k):
        return cdv.pop(0) if cdv else True

    def _sel(*a, **k):
        calls.append(("select", k.get("instance_name") or (a[0] if a else None)))

    with patch.object(PageObjectMcpHub, "_wait_for_target_dp_online"), \
         patch.object(PageObjectMcpHub, "_register_continue",
                      side_effect=lambda *a, **k: calls.append("continue")), \
         patch.object(PageObjectMcpHub, "_register_fill_identity",
                      side_effect=lambda *a, **k: calls.append("fill_name")), \
         patch.object(PageObjectMcpHub, "_register_pick_target_dp",
                      side_effect=lambda *a, **k: calls.append("pick_dp")), \
         patch.object(PageObjectMcpHub, "_register_select_or_create_resource", side_effect=_sel), \
         patch.object(PageObjectMcpHub, "_register_review_and_deploy", return_value="gw-id"), \
         patch.object(PageObjectMcpHub, "_wait_for_gateway_online"), \
         patch("page_object.po_mcp_hub.Util.check_dom_visibility", side_effect=_cdv):
        po.deploy_mcp_gateway(DP_NAME, skip_online_wait=True)
    return calls


def _select_indices(calls):
    return [i for i, c in enumerate(calls) if isinstance(c, tuple) and c[0] == "select"]


def test_merged_network_deploy_selects_storage_with_no_continue_between():
    """Merged 'Network & Deployment' step: ingress AND storage are both selected with
    NO Continue between them (a single Continue advances the merged step)."""
    calls = _deploy_full_order(step2_merged=True, step3_merged=True)
    idx = _select_indices(calls)
    assert len(idx) == 2, f"both ingress + storage selected; got {calls}"
    assert "continue" not in calls[idx[0] + 1:idx[1]], \
        f"merged step must NOT Continue between ingress and storage; got {calls}"


def test_legacy_network_deploy_has_continue_between_ingress_and_storage():
    """Legacy two-step flow: a Continue separates Network Access from Deployment Mode,
    so there IS a Continue between the ingress and storage selects."""
    calls = _deploy_full_order(step2_merged=True, step3_merged=False)
    idx = _select_indices(calls)
    assert len(idx) == 2, f"both ingress + storage selected; got {calls}"
    assert "continue" in calls[idx[0] + 1:idx[1]], \
        f"legacy flow must Continue between the two steps; got {calls}"


# === PCP-19765: gateway-id supersede recovery (resolveOn404) ========================
#
# The deploy POST returns a PLACEHOLDER gateway id that the backend RE-KEYS
# (supersedes) once async provision completes; the automation's id-primary Hub-API
# polls (health-check, sync/refresh, _api_get_gateway) then 404 / return None with no
# recovery and hard-abort — the intermittent "Gateway not found" false-abort. The React
# client recovers via resolveBySupersede; these pin the automation equivalent:
#   * _reresolve_gateway_id — STRICT (name + CURRENT dataPlaneId, loud on >1) + SOFT
#     (None on API error / unresolvable dpId, never exit_error), tried_ids-guarded;
#   * _api_get_gateway — id-miss + dp_name falls back to the name resolution;
#   * _wait_for_gateway_online / _refresh_and_count_tools — re-resolve on the wrong-id
#     404 and continue with the new id; NO-dp_name back-compat preserved (still aborts);
#   * wait_for_gateway_deployed — returns the resolved id so the caller can reassign.
# All are placed here (not sync_verify) to reuse the _route_get / _gw / _dp harness the
# re-resolve reads (/gateways + /data-planes).


def test_reresolve_gateway_id_strict_matches_name_and_dataplaneid():
    """Re-resolve returns the current gateway id by name + CURRENT dataPlaneId."""
    po = _make_po()
    po.page.context.request.get.side_effect = _route_get(
        gateways=[_gw(id="new", name=GW_NAME, data_plane_id=DP_ID)],
        data_planes=[_dp(name=DP_NAME, dp_id=DP_ID)])
    assert po._reresolve_gateway_id(DP_NAME) == "new"


def test_reresolve_gateway_id_soft_none_on_unresolvable_dpid():
    """dpId unresolvable (DP not listed) -> None (SOFT; caller retries), NOT name-only —
    the gating resolver must not degrade to a name-only match that could hit an orphan."""
    po = _make_po()
    po.page.context.request.get.side_effect = _route_get(
        gateways=[_gw(id="x", name=GW_NAME, data_plane_id="dp-old")],
        data_planes=[])  # DP not listed -> dpId unresolvable
    assert po._reresolve_gateway_id(DP_NAME) is None


def test_reresolve_gateway_id_soft_none_on_api_error():
    """A non-OK /gateways during re-resolve -> None (SOFT; never exit_error), so a
    transient blip during recovery does not hard-abort the gating loop."""
    po = _make_po()

    def _get(url, *a, **k):
        if str(url).endswith("/data-planes"):
            return _api_response([_dp(name=DP_NAME, dp_id=DP_ID)])
        return _api_response([], ok=False, status=502)
    po.page.context.request.get.side_effect = _get
    with patch("page_object.po_mcp_hub.Util.exit_error",
               side_effect=AssertionError("re-resolve must be soft on API error")):
        assert po._reresolve_gateway_id(DP_NAME) is None


def test_reresolve_gateway_id_ignores_orphan_stale_dataplaneid():
    """An orphan row (stale dataPlaneId != current) must NOT be re-resolved as current."""
    po = _make_po()
    po.page.context.request.get.side_effect = _route_get(
        gateways=[_gw(id="orphan", name=GW_NAME, data_plane_id="dp-old")],
        data_planes=[_dp(name=DP_NAME, dp_id="dp-new")])
    assert po._reresolve_gateway_id(DP_NAME) is None


def test_reresolve_gateway_id_loud_on_duplicate():
    """>1 gateway with the same name + current dataPlaneId -> loud exit_error (ambiguous;
    a status recovery must never silently pick one)."""
    po = _make_po()
    po.page.context.request.get.side_effect = _route_get(
        gateways=[_gw(id="a", name=GW_NAME, data_plane_id=DP_ID),
                  _gw(id="b", name=GW_NAME, data_plane_id=DP_ID)],
        data_planes=[_dp(name=DP_NAME, dp_id=DP_ID)])
    with patch("page_object.po_mcp_hub.Util.exit_error", side_effect=SystemExit(1)) as exit_error:
        with pytest.raises(SystemExit):
            po._reresolve_gateway_id(DP_NAME)
    assert exit_error.called


def test_reresolve_gateway_id_skips_tried_ids():
    """An id already in tried_ids is not returned again -> None (caller loop terminates)."""
    po = _make_po()
    po.page.context.request.get.side_effect = _route_get(
        gateways=[_gw(id="R", name=GW_NAME, data_plane_id=DP_ID)],
        data_planes=[_dp(name=DP_NAME, dp_id=DP_ID)])
    assert po._reresolve_gateway_id(DP_NAME, tried_ids={"R"}) is None


def test_api_get_gateway_id_miss_falls_back_to_dp_name():
    """PCP-19765: a stale (superseded) id WITH dp_name -> resolve the current row by
    name+dataPlaneId instead of returning None."""
    po = _make_po()
    po.page.context.request.get.side_effect = _route_get(
        gateways=[_gw(id="R", name=GW_NAME, data_plane_id=DP_ID)],
        data_planes=[_dp(name=DP_NAME, dp_id=DP_ID)])
    row = po._api_get_gateway(gateway_id="stale-placeholder", dp_name=DP_NAME)
    assert row is not None and row["id"] == "R"


def test_api_get_gateway_id_miss_no_dpname_stays_none():
    """Back-compat: an id miss with NO dp_name still returns None (unchanged contract)."""
    po = _make_po()
    po.page.context.request.get.return_value = _api_response([_gw(id="other")])
    assert po._api_get_gateway(gateway_id="stale") is None


def test_wait_online_reresolves_superseded_id_then_succeeds():
    """Core PCP-19765: health-check 404 'Gateway not found' on the placeholder id, WITH
    dp_name -> re-resolve to the new id and succeed on the next poll; returns the new id."""
    po = _make_po()
    po.gateway_id = "placeholder"
    po.page.context.request.post.side_effect = [
        _api_response({"error": "Gateway not found"}, ok=False, status=404,
                      text='{"error":"Gateway not found"}'),
        _api_response({"status": "online"}),
    ]
    po.page.context.request.get.side_effect = _route_get(
        gateways=[_gw(id="new-id", name=GW_NAME, data_plane_id=DP_ID)],
        data_planes=[_dp(name=DP_NAME, dp_id=DP_ID)])
    with patch("page_object.po_mcp_hub.Util.exit_error",
               side_effect=AssertionError("must recover, not abort")):
        eff = po._wait_for_gateway_online("placeholder", max_minutes=5, dp_name=DP_NAME)
    assert eff == "new-id"
    assert po.gateway_id == "new-id"
    assert "new-id" in po.page.context.request.post.call_args[0][0]  # 2nd probe hit the new id


def test_wait_online_reresolve_none_then_aborts():
    """dp_name set but re-resolve finds no new id (soft None) -> aborts (no infinite loop)."""
    po = _make_po()
    po.gateway_id = "placeholder"
    po.page.context.request.post.return_value = _api_response(
        {"error": "Gateway not found"}, ok=False, status=404, text='{"error":"Gateway not found"}')
    po.page.context.request.get.side_effect = _route_get(gateways=[], data_planes=[])  # soft None
    with patch("page_object.po_mcp_hub.Util.exit_error", side_effect=SystemExit(1)) as exit_error:
        with pytest.raises(SystemExit):
            po._wait_for_gateway_online("placeholder", max_minutes=5, dp_name=DP_NAME)
    assert exit_error.called


def test_wait_online_gateway_not_found_no_dpname_still_aborts():
    """Back-compat: a 'Gateway not found' 404 WITHOUT dp_name still aborts immediately
    after one probe (preserves test_wait_online_404_gateway_not_found_fails_loud)."""
    po = _make_po()
    po.gateway_id = GW_ID
    po.page.context.request.post.return_value = _api_response(
        {"error": "Gateway not found"}, ok=False, status=404, text='{"error":"Gateway not found"}')
    with patch.object(PageObjectMcpHub, "_reresolve_gateway_id",
                      side_effect=AssertionError("no dp_name -> must not re-resolve")), \
         patch("page_object.po_mcp_hub.Util.exit_error", side_effect=SystemExit(1)) as exit_error:
        with pytest.raises(SystemExit):
            po._wait_for_gateway_online(GW_ID, max_minutes=5)
    assert exit_error.called
    assert po.page.context.request.post.call_count == 1


def test_wait_online_generic_404_ui_fallback_not_reresolve():
    """A GENERIC 404 (endpoint absent, not 'Gateway not found') WITH dp_name still routes
    to the legacy UI fallback (dp_name threaded), NOT the supersede re-resolve."""
    po = _make_po()
    po.gateway_id = GW_ID
    po.page.context.request.post.return_value = _api_response({}, ok=False, status=404)
    with patch.object(PageObjectMcpHub, "_reresolve_gateway_id",
                      side_effect=AssertionError("generic 404 must not re-resolve")), \
         patch.object(PageObjectMcpHub, "_wait_for_gateway_online_ui") as ui, \
         patch("page_object.po_mcp_hub.Util.exit_error",
               side_effect=AssertionError("must UI-fallback, not abort")):
        po._wait_for_gateway_online(GW_ID, max_minutes=5, dp_name=DP_NAME)
    ui.assert_called_once()
    assert ui.call_args.kwargs.get("dp_name") == DP_NAME


def test_wait_deployed_returns_resolved_id_via_dpname_fallback():
    """wait_for_gateway_deployed recovers a superseded id via the dp_name fallback and
    RETURNS the current id (so the caller reassigns and stops propagating the placeholder)."""
    po = _make_po()
    po.page.context.request.get.side_effect = _route_get(
        gateways=[_gw(id="new-id", name=GW_NAME, deployed=True, data_plane_id=DP_ID)],
        data_planes=[_dp(name=DP_NAME, dp_id=DP_ID)])
    with patch.object(PageObjectMcpHub, "goto_gateway"), \
         patch.object(PageObjectMcpHub, "_detail_push_button", return_value=MagicMock()), \
         patch("page_object.po_mcp_hub.Util.check_dom_visibility", return_value=True), \
         patch("page_object.po_mcp_hub.Util.exit_error",
               side_effect=AssertionError("must not abort when deployed")):
        rid = po.wait_for_gateway_deployed("placeholder", dp_name=DP_NAME, max_minutes=5)
    assert rid == "new-id"
    assert po.gateway_id == "new-id"


def test_refresh_reresolves_superseded_id_then_counts():
    """PCP-19765: /sync/refresh 404 on the placeholder id, WITH dp_name -> re-resolve to
    the new id and retry, returning the discovered count; publishes the id on self."""
    po = _make_po()
    po.gateway_id = "placeholder"
    po.page.context.request.post.side_effect = [
        _api_response({"error": "not found"}, ok=False, status=404),
        _api_response({"tools": 7}),
    ]
    po.page.context.request.get.side_effect = _route_get(
        gateways=[_gw(id="new-id", name=GW_NAME, data_plane_id=DP_ID)],
        data_planes=[_dp(name=DP_NAME, dp_id=DP_ID)])
    with patch("page_object.po_mcp_hub.Util.exit_error",
               side_effect=AssertionError("must recover, not abort")):
        count = po._refresh_and_count_tools("placeholder", min_tools=1, dp_name=DP_NAME)
    assert count == 7
    assert po.gateway_id == "new-id"
    assert "new-id" in po.page.context.request.post.call_args[0][0]


def test_refresh_404_no_dpname_still_aborts():
    """Back-compat: /sync/refresh 404 WITHOUT dp_name aborts immediately (unchanged)."""
    po = _make_po()
    po.gateway_id = GW_ID
    po.page.context.request.post.return_value = _api_response(
        {"error": "not found"}, ok=False, status=404)
    with patch.object(PageObjectMcpHub, "_reresolve_gateway_id",
                      side_effect=AssertionError("no dp_name -> must not re-resolve")), \
         patch("page_object.po_mcp_hub.Util.exit_error", side_effect=SystemExit(1)) as exit_error:
        with pytest.raises(SystemExit):
            po._refresh_and_count_tools(GW_ID, min_tools=1)
    assert exit_error.called
