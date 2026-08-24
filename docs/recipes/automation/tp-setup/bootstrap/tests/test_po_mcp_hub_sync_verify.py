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
# Regression tests for PCP-20924 — deploy-mcp-hub post-push sync verification on the
# gateway-centric React UI.
#
# Root cause (see docs/plan/PCP-20924-plan.md): the old verification keyed on transient
# sync dialogs (dp-action-sync-result / -refreshing) and DOM-scraped the tool count, then
# SOFT-failed — a missed dialog or a 0-tool result returned 0 / only warned, so a sync that
# discovered NO tools was reported as "[SUCCESS] 0 tools discovered" and the pipeline exited
# 0 (the alpha.49 false green); alpha.42 instead spun on the transient spinner.
#
# The fix (verified against tp-mcp-hub backend): push and discovery are TWO backend steps —
# POST /sync pushes config OUT, POST /sync/refresh DISCOVERS tools (fetchAllPages -> upsert
# cp_tools) and returns {tools: number|null, gatewayStatus, fetchErrors?}. push_to_gateway now
# keeps the UI Push click but DRIVES /sync/refresh itself (the analogue of
# _wait_for_gateway_online's POST health-check) and HARD-fails on a persistent 0-tool
# discovery / unreachable gateway, bounded; verify_tools is confirmatory (warn-not-abort).
#
# These tests pin that contract on the deterministic Hub-API path (MagicMock page, no browser),
# following the sibling suites' _make_po() / _api_response() pattern.

from unittest.mock import MagicMock, patch

import pytest

from page_object.po_mcp_hub import PageObjectMcpHub

DP_NAME = "k8s-auto-dp1"
GW_ID = "gw-uuid-1"
API_URL = "https://cp-sub1.example.com/cp/mcp-hub/api/mcp-hub/gateways"


def _make_po():
    """PageObjectMcpHub without __init__ (which needs a real Playwright page); inject a
    MagicMock page + a pre-captured gateways API URL. page.wait_for_timeout is a no-op
    MagicMock so the bounded poll never really sleeps."""
    po = PageObjectMcpHub.__new__(PageObjectMcpHub)
    po.page = MagicMock()
    po.gateway_id = GW_ID
    po._gateways_api_url = API_URL
    return po


def _api_response(payload, ok=True, status=200, text=""):
    resp = MagicMock()
    resp.ok = ok
    resp.status = status
    resp.json.return_value = payload
    resp.text.return_value = text
    return resp


# ============================================================================
# _refresh_and_count_tools — the authoritative post-push gate (drives /sync/refresh)
# ============================================================================

def test_refresh_succeeds_when_tools_discovered():
    """Happy path: /sync/refresh reports tools >= min_tools -> returns the count, no abort,
    and POSTs the refresh endpoint."""
    po = _make_po()
    po.page.context.request.post.return_value = _api_response({"tools": 5, "gatewayStatus": []})
    with patch("page_object.po_mcp_hub.Util.exit_error",
               side_effect=AssertionError("must not abort when tools were discovered")):
        count = po._refresh_and_count_tools(GW_ID, min_tools=1)
    assert count == 5
    assert po.page.context.request.post.call_count == 1
    assert po.page.context.request.post.call_args[0][0].endswith("/sync/refresh")


def test_refresh_absorbs_discovery_lag_then_succeeds():
    """No happy-path false-RED: discovery lags (0, then 0, then 3) -> keeps polling and
    returns 3 without ever aborting."""
    po = _make_po()
    po.page.context.request.post.side_effect = [
        _api_response({"tools": 0, "gatewayStatus": []}),
        _api_response({"tools": 0, "gatewayStatus": []}),
        _api_response({"tools": 3, "gatewayStatus": []}),
    ]
    with patch("page_object.po_mcp_hub.Util.exit_error",
               side_effect=AssertionError("must not abort while discovery is still lagging")):
        count = po._refresh_and_count_tools(GW_ID, min_tools=1, max_seconds=60)
    assert count == 3
    assert po.page.context.request.post.call_count == 3


def test_refresh_hard_fails_on_persistent_zero_tools():
    """THE alpha.49 fix: a sync that persistently discovers 0 tools (servers installed) ->
    HARD-fail after the bound, never a silent 0-tool success."""
    po = _make_po()
    po.page.context.request.post.return_value = _api_response({"tools": 0, "gatewayStatus": []})
    with patch("page_object.po_mcp_hub.Util.exit_error", side_effect=SystemExit(1)) as exit_error:
        with pytest.raises(SystemExit):
            po._refresh_and_count_tools(GW_ID, min_tools=1, max_seconds=10)
    assert exit_error.called
    assert "0 tools" in exit_error.call_args[0][0] or "did not register" in exit_error.call_args[0][0]


def test_refresh_hard_fails_on_tools_null_read_failure():
    """tools=null means the refresh READ failed (distinct from a genuine 0) -> the
    bound-exhausted message must say 'read ... failing', not '0 tools'."""
    po = _make_po()
    po.page.context.request.post.return_value = _api_response({"tools": None, "fetchErrors": [{"entity": "tools"}]})
    with patch("page_object.po_mcp_hub.Util.exit_error", side_effect=SystemExit(1)) as exit_error:
        with pytest.raises(SystemExit):
            po._refresh_and_count_tools(GW_ID, min_tools=1, max_seconds=10)
    assert exit_error.called
    assert "null" in exit_error.call_args[0][0] or "read" in exit_error.call_args[0][0].lower()


def test_refresh_aborts_after_three_consecutive_unreachable():
    """A persistent 502 (gateway unreachable) -> fail fast after 3 consecutive, not the
    full budget."""
    po = _make_po()
    po.page.context.request.post.return_value = _api_response({}, ok=False, status=502)
    with patch("page_object.po_mcp_hub.Util.exit_error", side_effect=SystemExit(1)) as exit_error:
        with pytest.raises(SystemExit):
            po._refresh_and_count_tools(GW_ID, min_tools=1, max_seconds=60)
    assert exit_error.called
    assert po.page.context.request.post.call_count == 3


def test_refresh_404_aborts_immediately():
    """A 404 (wrong id / endpoint absent) -> distinct loud error on the first POST."""
    po = _make_po()
    po.page.context.request.post.return_value = _api_response({"error": "Data Plane not found"},
                                                             ok=False, status=404)
    with patch("page_object.po_mcp_hub.Util.exit_error", side_effect=SystemExit(1)) as exit_error:
        with pytest.raises(SystemExit):
            po._refresh_and_count_tools(GW_ID, min_tools=1)
    assert exit_error.called
    assert po.page.context.request.post.call_count == 1


def test_refresh_fails_fast_on_auth_error():
    """An auth/path client error (401) is NOT a slow gateway -> fail fast on the first POST,
    no 3-strike reachability retry."""
    po = _make_po()
    po.page.context.request.post.return_value = _api_response({}, ok=False, status=401)
    with patch("page_object.po_mcp_hub.Util.exit_error", side_effect=SystemExit(1)) as exit_error:
        with pytest.raises(SystemExit):
            po._refresh_and_count_tools(GW_ID, min_tools=1)
    assert exit_error.called
    assert po.page.context.request.post.call_count == 1


def test_refresh_partial_with_tools_warns_but_does_not_abort():
    """AC-5 guard: a partial refresh (fetchErrors) that STILL discovered >= min_tools must
    be surfaced (warn) but NOT aborted, and must return the discovered count."""
    po = _make_po()
    po.page.context.request.post.return_value = _api_response(
        {"tools": 3, "gatewayStatus": [], "fetchErrors": [{"entity": "prompts", "error": "boom"}]})
    with patch("page_object.po_mcp_hub.Util.exit_error",
               side_effect=AssertionError("must NOT abort a partial that still discovered tools")), \
         patch("page_object.po_mcp_hub.Util.warning_screenshot") as warn:
        count = po._refresh_and_count_tools(GW_ID, min_tools=1)
    assert count == 3
    assert warn.called


# ============================================================================
# push_to_gateway — delegates the gate to _refresh_and_count_tools; surfaces partial push
# ============================================================================

def _patch_push_ui():
    """Patches for push_to_gateway's UI interaction so a unit test can reach the new gate."""
    return [
        patch.object(PageObjectMcpHub, "goto_gateway"),
        patch.object(PageObjectMcpHub, "wait_for_gateway_deployed"),
        patch.object(PageObjectMcpHub, "_detail_push_button", return_value=MagicMock()),
        patch.object(PageObjectMcpHub, "_diff_confirm_push", return_value=MagicMock()),
        patch("page_object.po_mcp_hub.Util.check_dom_visibility", return_value=True),
    ]


def test_push_to_gateway_delegates_to_refresh_gate():
    """push_to_gateway must verify via _refresh_and_count_tools (the deterministic gate),
    threading min_tools, and return its count."""
    po = _make_po()
    po._refresh_and_count_tools = MagicMock(return_value=4)
    # PCP-21970: push_to_gateway now waits for the gateway to come online (via the
    # Hub health-check) before driving /sync/refresh — stub it so the unit test
    # exercises the refresh-gate delegation, not the real online poll.
    po._wait_for_gateway_online = MagicMock()
    po._api_gateway_sync_status_soft = MagicMock(return_value="synced")
    ctx = _patch_push_ui()
    for c in ctx:
        c.start()
    try:
        with patch("page_object.po_mcp_hub.Util.exit_error",
                   side_effect=AssertionError("must not abort on a healthy push")), \
             patch("page_object.po_mcp_hub.Util.warning_screenshot") as warn:
            count = po.push_to_gateway(gateway_id=GW_ID, min_tools=1)
    finally:
        for c in ctx:
            c.stop()
    assert count == 4
    po._wait_for_gateway_online.assert_called_once()  # PCP-21970: online wait precedes the refresh gate
    po._refresh_and_count_tools.assert_called_once()
    assert po._refresh_and_count_tools.call_args.kwargs.get("min_tools") == 1
    assert not warn.called  # syncStatus 'synced' -> no partial warning


def test_push_to_gateway_warns_on_partial_push_status():
    """A partial PUSH (gateway row sync_status='error') with tools discovered is surfaced
    (warn) but NOT aborted — visibility without flaking."""
    po = _make_po()
    po._refresh_and_count_tools = MagicMock(return_value=4)
    po._wait_for_gateway_online = MagicMock()  # PCP-21970: stub the pre-refresh online wait
    po._api_gateway_sync_status_soft = MagicMock(return_value="error")
    ctx = _patch_push_ui()
    for c in ctx:
        c.start()
    try:
        with patch("page_object.po_mcp_hub.Util.exit_error",
                   side_effect=AssertionError("a partial push with tools must not abort")), \
             patch("page_object.po_mcp_hub.Util.warning_screenshot") as warn:
            count = po.push_to_gateway(gateway_id=GW_ID, min_tools=1)
    finally:
        for c in ctx:
            c.stop()
    assert count == 4
    assert warn.called


# ============================================================================
# verify_tools — confirmatory only (NON-aborting); the hard gate lives in push_to_gateway
# ============================================================================

def test_verify_tools_returns_stats_total():
    """Confirmatory read returns the gateway-wide /stats tools.total."""
    po = _make_po()
    po.page.context.request.get.return_value = _api_response({"tools": {"total": 7, "active": 7}})
    with patch("page_object.po_mcp_hub.Util.exit_error",
               side_effect=AssertionError("verify_tools must never abort (confirmatory only)")):
        count = po.verify_tools(GW_ID, min_tools=1)
    assert count == 7
    assert po.page.context.request.get.call_args[0][0].endswith("/stats")


def test_verify_tools_does_not_abort_on_low_count():
    """verify_tools is confirmatory: a shortfall WARNs but does NOT abort (push_to_gateway
    already owns the hard gate) — it must not re-introduce a redundant false-RED."""
    po = _make_po()
    po.page.context.request.get.return_value = _api_response({"tools": {"total": 0, "active": 0}})
    with patch("page_object.po_mcp_hub.Util.exit_error",
               side_effect=AssertionError("verify_tools must not abort on a low count")), \
         patch("page_object.po_mcp_hub.Util.warning_screenshot") as warn:
        count = po.verify_tools(GW_ID, min_tools=1)
    assert count == 0
    assert warn.called


def test_verify_tools_soft_on_stats_api_error():
    """A transient /stats error must NOT fail the deploy via verify_tools (soft) — it warns
    and returns 0; the deploy's success was already gated by push_to_gateway."""
    po = _make_po()
    po.page.context.request.get.return_value = _api_response({}, ok=False, status=500)
    with patch("page_object.po_mcp_hub.Util.exit_error",
               side_effect=AssertionError("verify_tools must be soft on a stats API error")), \
         patch("page_object.po_mcp_hub.Util.warning_screenshot") as warn:
        count = po.verify_tools(GW_ID, min_tools=1)
    assert count == 0
    assert warn.called


# ============================================================================
# Partial-push visibility read is SOFT (cross-review Finding 1) + the soft helper
# ============================================================================

def test_push_partial_warn_is_soft_on_gateways_api_error():
    """Finding 1: the post-gate partial-push visibility read must be SOFT — a transient
    gateways-API error AFTER discovery already passed must NOT abort the (verified) deploy."""
    po = _make_po()
    po._refresh_and_count_tools = MagicMock(return_value=4)
    po._wait_for_gateway_online = MagicMock()  # PCP-21970: stub the pre-refresh online wait
    # The soft syncStatus read hits a transient non-OK -> returns None -> no warn, no abort.
    po.page.context.request.get.return_value = _api_response({}, ok=False, status=502)
    ctx = _patch_push_ui()
    for c in ctx:
        c.start()
    try:
        with patch("page_object.po_mcp_hub.Util.exit_error",
                   side_effect=AssertionError("a transient gateways-API error must not abort a verified deploy")), \
             patch("page_object.po_mcp_hub.Util.warning_screenshot") as warn:
            count = po.push_to_gateway(gateway_id=GW_ID, min_tools=1)
    finally:
        for c in ctx:
            c.stop()
    assert count == 4
    assert not warn.called


def test_api_gateway_sync_status_soft_reads_matching_row():
    po = _make_po()
    po.page.context.request.get.return_value = _api_response(
        [{"id": "other", "syncStatus": "synced"}, {"id": GW_ID, "syncStatus": "error"}])
    assert po._api_gateway_sync_status_soft(GW_ID) == "error"


def test_api_gateway_sync_status_soft_returns_none_on_error():
    po = _make_po()
    po.page.context.request.get.return_value = _api_response({}, ok=False, status=500)
    assert po._api_gateway_sync_status_soft(GW_ID) is None


# ============================================================================
# Additional _refresh_and_count_tools coverage (cross-review LOW gaps)
# ============================================================================

def test_refresh_min_tools_zero_returns_zero_no_abort():
    """A flow that legitimately expects no tools (min_tools=0) accepts a 0 discovery without
    aborting — the documented future 0-tool flow; guards against a >= -> > off-by-one."""
    po = _make_po()
    po.page.context.request.post.return_value = _api_response({"tools": 0, "gatewayStatus": []})
    with patch("page_object.po_mcp_hub.Util.exit_error",
               side_effect=AssertionError("min_tools=0 must accept a 0-tool discovery")):
        count = po._refresh_and_count_tools(GW_ID, min_tools=0)
    assert count == 0


def test_refresh_recovers_after_transient_502():
    """A transient 502 then a good read -> consecutive_unreachable resets, returns the count,
    never aborts (the reset-on-recovery branch)."""
    po = _make_po()
    po.page.context.request.post.side_effect = [
        _api_response({}, ok=False, status=502),
        _api_response({"tools": 3, "gatewayStatus": []}),
    ]
    with patch("page_object.po_mcp_hub.Util.exit_error",
               side_effect=AssertionError("a transient 502 that then recovers must not abort")):
        count = po._refresh_and_count_tools(GW_ID, min_tools=1, max_seconds=60)
    assert count == 3
    assert po.page.context.request.post.call_count == 2


def test_refresh_aborts_with_no_gateway_id():
    """No gateway id available -> loud guard, not a malformed request."""
    po = _make_po()
    po.gateway_id = None
    with patch("page_object.po_mcp_hub.Util.exit_error", side_effect=SystemExit(1)) as exit_error:
        with pytest.raises(SystemExit):
            po._refresh_and_count_tools(gateway_id=None, min_tools=1)
    assert exit_error.called


def test_refresh_mixed_null_then_zero_reports_zero_not_readfail():
    """M1: a mixed history (a null read then a clean 0) must report the genuine 'did not
    register / 0 tools' outcome, NOT 'read kept failing' — labelled by whether ANY read
    succeeded, not just the last poll."""
    po = _make_po()
    po.page.context.request.post.side_effect = [
        _api_response({"tools": None, "fetchErrors": [{"entity": "tools"}]}),
        _api_response({"tools": 0, "gatewayStatus": []}),
    ]
    with patch("page_object.po_mcp_hub.Util.exit_error", side_effect=SystemExit(1)) as exit_error:
        with pytest.raises(SystemExit):
            po._refresh_and_count_tools(GW_ID, min_tools=1, max_seconds=10)
    assert exit_error.called
    msg = exit_error.call_args[0][0]
    assert "did not register" in msg or "0 tools" in msg
    assert "kept failing" not in msg
