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

DP_NAME = "k8s-auto-dp1"
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


def _dp(name=DP_NAME, status="online", origin="cp_dp"):
    return {"name": name, "status": status, "origin": origin}


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


def _gw(id=GW_ID, name=DP_NAME, status="online", origin="cp_dp", deployed=True):
    return {"id": id, "name": name, "status": status, "origin": origin,
            "mcpgatewayDeployed": deployed}


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
    po.page.context.request.get.return_value = _api_response(
        [_gw(id="d1", name=DP_NAME, origin="direct"), _gw(id="c1", name=DP_NAME, origin="cp_dp")])
    row = po._api_get_gateway(dp_name=DP_NAME)
    assert row is not None and row["id"] == "c1"


def test_api_get_gateway_name_fallback_fails_loud_on_duplicate():
    """Two cp_dp gateways with the same name and no id -> exit_error (ambiguous;
    multi-gateway-per-dp). Never silently pick the first."""
    po = _make_po()
    po.page.context.request.get.return_value = _api_response(
        [_gw(id="a", name=DP_NAME), _gw(id="b", name=DP_NAME)])
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
