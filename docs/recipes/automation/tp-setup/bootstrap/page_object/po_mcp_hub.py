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

import re

from playwright.sync_api import expect

from page_object.po_global import PageObjectGlobal
from utils.color_logger import ColorLogger
from utils.env import ENV
from utils.util import Util


class PageObjectMcpHub(PageObjectGlobal):
    """MCP Hub automation for the gateway-centric React UI (PCP-19623).

    The MCP Hub UI was rewritten Angular -> React (PrimeReact + Fresco) and made
    gateway-centric. Deploying the MCP Gateway is now the **Register Gateway**
    wizard with the "Deploy to a TIBCO Data Plane" (auto-provision) mode, which
    fires ``POST {apiBasePath}/gateways/{dpUuid}/deploy``. The standalone
    "MCP Tools" tab was retired; discovered tools now live in a per-server
    "Tools details" slide-over drawer.

    Selectors below were verified against the merged redesign code
    (tp-mcp-hub @ aff65c8, branch wip/PCP-19623-redesign). Prefer ``data-testid``
    locators; visible text / CSS classes are used only where no testid exists.

    The MCP Hub is mounted as an MFE under the CP shell at ``/cp/mcphub``.
    """

    # MFE basepath under the CP shell (config.mode === 'cp'). Routes are relative
    # to this prefix (e.g. /cp/mcphub/gateways/register).
    HUB_BASE_PATH = "/cp/mcphub"

    # Registry display names per short server key. Cards are matched by their
    # visible display name (server.title ?? server.name); these must match the
    # names shown in the live MCP Server Registry.
    MCP_SERVER_CATALOG = {
        "cp-mcp-server": "TIBCO® Control Plane MCP Server",
        "o11y-mcp-server": "TIBCO® Observability MCP Server",
        "flogo-mcp-server": "TIBCO Flogo® MCP Server",
        "bw-mcp-server": "TIBCO BusinessWorks™ MCP Server",
        "devhub-mcp-server": "TIBCO Developer Hub MCP Server",
    }

    # MCP Hub API base under the CP shell (config.mode === 'cp'). Distinct from
    # HUB_BASE_PATH: the UI route prefix is '/cp/mcphub' but the REST base is
    # '/cp/mcp-hub/api/mcp-hub' (tp-mcp-hub main.tsx default). Used only as a
    # fallback when the real URL was not observed on the wire (see
    # _capture_gateways_api_url).
    HUB_API_BASE_PATH = "/cp/mcp-hub/api/mcp-hub"

    def __init__(self, page):
        super().__init__(page)
        # Gateway UUID (DataPlane.id) captured from the deploy response; used to
        # navigate to the gateway detail / servers tab for later steps.
        self.gateway_id = None
        # The real Hub `GET .../gateways` URL, captured off the wire the first
        # time the gateways list loads (apiBasePath can be shell-overridden, so we
        # prefer the observed URL over the HUB_API_BASE_PATH literal). Used by the
        # pre-wizard DP-readiness gate (PCP-20127).
        self._gateways_api_url = None
        page.on("response", self._capture_gateways_api_url)

    def _capture_gateways_api_url(self, response):
        """Best-effort capture of the Hub gateways-list API URL off the wire.

        The gateways list is fetched whenever the MCP Hub home loads; we snapshot
        the first matching GET xhr/fetch request whose path ends in '/gateways' so
        the readiness gate polls the exact URL the app uses (no hardcoded
        apiBasePath). Best-effort: failures are swallowed and the literal fallback
        applies.
        """
        try:
            if self._gateways_api_url:
                return
            request = response.request
            if request.method != "GET" or request.resource_type not in ("xhr", "fetch"):
                return
            base = response.url.split("?", 1)[0]
            # Latch only the MCP Hub's OWN same-origin gateways-list endpoint
            # (.../<mcp-hub api base>/gateways). Requiring same origin + an 'mcp'
            # path marker (covers 'mcp-hub'/'mcphub') avoids the one-shot capture
            # latching onto an unrelated CP/MFE '/api/.../gateways' request that
            # might fire first. A shell-overridden base without the marker simply
            # falls back to HUB_API_BASE_PATH (and fails loud at poll time if wrong).
            if (base.startswith(self._hub_origin())
                    and "/api/" in base
                    and "mcp" in base.lower()
                    and base.rstrip("/").endswith("/gateways")):
                self._gateways_api_url = base
                ColorLogger.info(f"Captured MCP Hub gateways API URL: {base}")
        except Exception:
            pass  # capture is best-effort; the HUB_API_BASE_PATH fallback is used

    # ------------------------------------------------------------------ #
    # URL / navigation helpers
    # ------------------------------------------------------------------ #
    def _hub_origin(self):
        """Origin of the CP shell, e.g. https://cp-sub1.cp1-my.<domain>."""
        return f"https://{ENV.DP_HOST_PREFIX}.{ENV.TP_AUTO_CP_SERVICE_DNS_DOMAIN}"

    def _hub_url(self, route=""):
        """Build a full MCP Hub MFE URL for an in-app route (basepath-relative)."""
        return f"{self._hub_origin()}{self.HUB_BASE_PATH}{route}"

    def goto_mcp_hub(self):
        """Navigate to the MCP Hub gateways home (the gateway list = index route '/')."""
        url = self._hub_url("/")
        ColorLogger.info(f"Navigating to MCP Hub home: {url}")
        self.page.goto(url, wait_until="domcontentloaded")
        if not Util.check_dom_visibility(self.page, self.page.get_by_test_id("dashboard-root"), 3, 30):
            Util.exit_error("MCP Hub gateways home (dashboard-root) did not load", self.page, "mcp_hub_home.png")
        self.page.wait_for_timeout(1000)
        ColorLogger.success("Navigated to MCP Hub gateways home")

    def goto_gateway(self, gateway_id=None, tab=""):
        """Navigate to a gateway detail page (by UUID) and optionally a tab.

        Args:
            gateway_id: Gateway UUID (DataPlane.id). Falls back to self.gateway_id.
            tab: Optional detail tab route segment (e.g. 'servers', 'overview').
        """
        gid = gateway_id or self.gateway_id
        if not gid:
            Util.exit_error("No gateway id available to open the gateway detail page", self.page, "goto_gateway.png")
        route = f"/gateways/{gid}" + (f"/{tab}" if tab else "")
        url = self._hub_url(route)
        ColorLogger.info(f"Navigating to gateway detail: {url}")
        self.page.goto(url, wait_until="domcontentloaded")
        if not Util.check_dom_visibility(self.page, self.page.get_by_test_id("dp-detail-root"), 3, 30):
            Util.exit_error(f"Gateway detail page (dp-detail-root) did not load for '{gid}'", self.page, "goto_gateway.png")
        self.page.wait_for_timeout(1000)

    def _open_gateway_from_home(self, name):
        """Find a deployed gateway row on the home list by name and open it.

        Returns the resolved gateway UUID (from the resulting URL), or None if no
        matching deployed gateway exists. The home only lists deployed/direct
        gateways; a bare cp_dp DP that has not been deployed does not appear.
        """
        self.goto_mcp_hub()
        # Dashboard rows carry data-testid="dashboard-gateway-row" (Dashboard.tsx); the legacy
        # .gw-row CSS class was dropped in the Fresco UX migration (PCP-19991 / commit 2dcbb2e).
        # has_text=name already excludes the add-row (it carries no DP name), so no :not(.gw-row-add).
        row = self.page.get_by_test_id("dashboard-gateway-row").filter(has_text=name)
        if not Util.check_dom_visibility(self.page, row.first, 1, 5):
            return None
        row.first.click()
        if not Util.check_dom_visibility(self.page, self.page.get_by_test_id("dp-detail-root"), 2, 20):
            return None
        match = re.search(r"/gateways/([^/?#]+)", self.page.url)
        return match.group(1) if match else None

    # ------------------------------------------------------------------ #
    # Gateway status
    # ------------------------------------------------------------------ #
    def is_gateway_deployed(self, dp_name):
        """Whether a deployed MCP Gateway already exists for dp_name (on the home list)."""
        # PCP-21143: the dashboard row carries the gateway's display name 'gateway-<dp>'
        # (_gateway_name), not the bare DP name — look it up through the same single
        # source of truth as the API lookups so the UI fallback can't drift / collide.
        return self._open_gateway_from_home(self._gateway_name(dp_name)) is not None

    def is_gateway_online(self):
        """Whether the gateway detail header shows the gateway as online.

        Reads the React status text (.gw-health-text); the old Angular
        span.p-tag-label 'online' selector is gone.
        """
        health = self.page.locator(".gw-health-text")
        if Util.check_dom_visibility(self.page, health.first, 1, 3):
            return "online" in (health.first.inner_text() or "").lower()
        return False

    @staticmethod
    def _gateway_name(dp_name):
        """The registered gateway name for a target DP — prefixed ``gateway-<dp>``
        (PCP-21143). Single source of truth: used BOTH when filling the Register
        wizard Identity step and when resolving a gateway by name in the gateways
        API (idempotency reuse / status poll), so the wizard-written name and the
        name-based lookups never drift apart. The target-DP selection still keys on
        the bare ``dp_name`` (that matches the Data Plane, not the gateway)."""
        return f"gateway-{dp_name}"

    def _api_get_gateway(self, gateway_id=None, dp_name=None):
        """Fetch a gateway row from the Hub gateways API (deterministic signal, not
        the UI). Polls the captured ``GET .../gateways`` URL via the
        browser-auth-shared ``page.context.request`` (shared cookie session).

        Matching is **id-primary** — the gateway UUID resolved from the deploy POST.
        A ``name``-only fallback is used ONLY when no id is available, requires
        ``origin == 'cp_dp'`` and FAILS LOUD on >1 match: under multi-gateway-per-dp
        (PCP-19802) one DP can host several gateways, so a bare name match could
        target the wrong one. Returns the row dict, or None if no row matches.
        Fails fast & loud on an API error (PCP-20336).
        """
        gid = gateway_id or self.gateway_id
        url = self._gateways_api_url or f"{self._hub_origin()}{self.HUB_API_BASE_PATH}/gateways"
        response = self.page.context.request.get(url)
        if not response.ok:
            Util.exit_error(
                f"MCP Hub gateways API returned HTTP {response.status} for {url} — cannot verify "
                "gateway status. Check the MCP Hub webserver / the captured API path.",
                self.page, "gateway_api_error.png")
            return None  # defensive: exit_error sys.exit()s
        try:
            data = response.json()
        except Exception:
            Util.exit_error(f"MCP Hub gateways API returned non-JSON for {url}",
                            self.page, "gateway_api_error.png")
            return None
        rows = data if isinstance(data, list) else (
            data.get("gateways", []) if isinstance(data, dict) else [])
        if gid:
            hit = next((g for g in rows if isinstance(g, dict) and g.get("id") == gid), None)
            if hit is not None:
                return hit
            # PCP-19765: the id may be a SUPERSEDED placeholder (re-keyed after async
            # provision). With no dp_name we keep the "id given, not found -> None"
            # contract; with a dp_name, fall through to the name+dataPlaneId resolution
            # below so a superseded id still resolves the current gateway row.
            if not dp_name:
                return None
        if dp_name:
            # Name match uses the prefixed gateway name (PCP-21143, _gateway_name),
            # AND is scoped to the DP's CURRENT dataPlaneId (PCP-21173) so a stale
            # orphan row (same name, deleted+recreated DP) can't be polled as the live
            # gateway. A FALSY dp_id (None, or "" — the backend emits dataPlaneId as
            # `dp_id || ''`) means unresolvable -> name-only (no behavior change); a
            # truthy dp_id requires an exact match, so an orphan/`direct` row whose
            # dataPlaneId is "" or absent can never satisfy `"" == <real id>`.
            gw_name = self._gateway_name(dp_name)
            dp_id = self._resolve_dataplane_id(dp_name)
            matches = [g for g in rows if isinstance(g, dict)
                       and g.get("name") == gw_name and g.get("origin", "cp_dp") == "cp_dp"
                       and (not dp_id or g.get("dataPlaneId") == dp_id)]
            if len(matches) > 1:
                Util.exit_error(
                    f"Multiple gateways named '{gw_name}' on the same DP — cannot disambiguate "
                    "without a gateway id (multi-gateway-per-dp). Resolve the id from the deploy "
                    "response before polling status.",
                    self.page, "gateway_api_ambiguous.png")
                return None
            return matches[0] if matches else None
        return None

    def _resolve_dataplane_id(self, dp_name):
        """Current ``dpId`` of the cp_dp Data Plane named ``dp_name`` (or None).

        Reads the ``/data-planes`` API and returns its ``dpId`` field — i.e. the value
        callers compare against a gateway row's ``dataPlaneId`` (the gateways API maps
        the same DP id into ``dataPlaneId``; ``/data-planes`` exposes it as ``dpId``).

        PCP-21173: gateway reuse/status lookups must bind to the DP's IDENTITY, not
        just its name. After a Data Plane is deleted and recreated with the SAME name,
        the gateways API keeps the OLD DP's orphaned gateway row (stale
        ``dataPlaneId``); a name-only match would treat that orphan as the live
        gateway. Resolving the DP's CURRENT id from ``/data-planes`` (the same
        endpoint the Register wizard reads, see ``_wait_for_target_dp_online``) lets
        the name-based lookups reject the orphan.

        Returns None on any API error or if the DP is not listed — callers then fall
        back to name-only matching, so this can only ADD precision, never block a
        deploy (no regression to the PCP-20336 dedup).
        """
        base = self._gateways_api_url or f"{self._hub_origin()}{self.HUB_API_BASE_PATH}/gateways"
        url = base.rsplit("/gateways", 1)[0] + "/data-planes"
        try:
            response = self.page.context.request.get(url)
            if not response.ok:
                return None
            data = response.json()
        except Exception:
            return None
        rows = data if isinstance(data, list) else (
            data.get("dataPlanes", []) if isinstance(data, dict) else [])
        for d in rows:
            if (isinstance(d, dict) and d.get("name") == dp_name
                    and d.get("origin", "cp_dp") == "cp_dp"):
                # Return ONLY the verified-contract field (dpId); coerce a falsy/empty
                # value to None so callers degrade to name-only. Do NOT fall back to a
                # different `id` field — it is outside the /data-planes contract and a
                # row whose `id` != dpId would yield a truthy value matching no
                # gateway's dataPlaneId, wrongly rejecting the live gateway instead of
                # degrading (review: adhanshe-tibco, PCP-21173).
                return d.get("dpId") or None
        return None

    def _find_existing_gateway_id(self, dp_name):
        """Idempotency lookup: the id of an existing cp_dp gateway for ``dp_name``
        to REUSE — a fully-deployed one preferred, else one still provisioning — or
        None. Via the deterministic gateways API, NOT the UI dashboard.

        PCP-20336 (1.17.1 minor line): the UI dashboard lookup
        (``_open_gateway_from_home``) stopped resolving an existing gateway on the
        multi-gateway-per-dp dashboard (the row click no longer lands on
        ``/gateways/<id>``), so ``deploy_mcp_gateway`` re-deployed on every re-run
        and piled up duplicate gateways until the DP node ran out of schedulable
        CPU. The gateways API lists a gateway as soon as it exists, so it is the
        reliable idempotency signal.

        PCP-20573: the deploy POST creates the gateway row (+ Helm release + pod +
        PVC) IMMEDIATELY, but ``mcpgatewayDeployed`` flips true only minutes later.
        A retry whose prior attempt died in that window (e.g. ``wait_for_gateway_deployed``
        timed out) must reuse the in-progress row, NOT re-run the wizard and leak a
        duplicate — so an in-progress (not-yet-deployed) row is reusable too. We PREFER
        a fully-deployed row and only fall back to an in-progress one; the status enum is
        online|offline|unknown (no "failed"), so a genuinely stuck gateway is surfaced by
        the later ``wait_for_gateway_deployed`` timeout, not masked here.

        Distinct from ``_api_get_gateway(dp_name=…)``, which fails LOUD on >1 match
        because it is a STATUS poll (ambiguity is unsafe there); for idempotency any
        reusable cp_dp gateway means "already registered", so reuse the first. Soft on
        API error (returns None) — an idempotency miss must never BLOCK a deploy, only
        avoid a duplicate.
        """
        url = self._gateways_api_url or f"{self._hub_origin()}{self.HUB_API_BASE_PATH}/gateways"
        try:
            response = self.page.context.request.get(url)
            if not response.ok:
                return None
            data = response.json()
        except Exception:
            return None
        rows = data if isinstance(data, list) else (
            data.get("gateways", []) if isinstance(data, dict) else [])
        # Bind the reuse to the prefixed gateway name (PCP-21143, _gateway_name) AND
        # the DP's CURRENT dataPlaneId (PCP-21173): resolve the live dataPlaneId and
        # require the gateway to belong to it, so an orphaned row left by a same-named
        # DP delete/recreate is NOT mistaken for a live gateway. A FALSY dp_id (None, or
        # "" — the backend emits dataPlaneId as `dp_id || ''`) means the id can't be
        # resolved (API hiccup / DP not yet listed): fall back to name-only matching to
        # preserve the PCP-20336 duplicate-suppression. A truthy dp_id requires an exact
        # match, so a `""`/absent-dataPlaneId orphan is rejected.
        gw_name = self._gateway_name(dp_name)
        dp_id = self._resolve_dataplane_id(dp_name)
        candidates = [
            g for g in rows
            if isinstance(g, dict) and g.get("name") == gw_name
            and g.get("origin", "cp_dp") == "cp_dp"
            and (not dp_id or g.get("dataPlaneId") == dp_id)
        ]
        # Prefer a fully-deployed gateway (healthy, ready for install/push).
        for g in candidates:
            if g.get("mcpgatewayDeployed"):
                if not dp_id:
                    # Degraded path: could not confirm the gateway belongs to the live
                    # DP, so a stale orphan from a same-named recreate might be reused
                    # here. Surface it (never a silent false "already deployed").
                    ColorLogger.warning(
                        f"PCP-21173: could not resolve current dataPlaneId for '{dp_name}'; "
                        f"reusing gateway {g.get('id')} by name only — if this DP was just "
                        "recreated, verify it is not a stale orphan.")
                return g.get("id")
        # PCP-20573: else reuse an in-progress (not-yet-deployed) gateway so a retry in
        # the deploy-POST -> mcpgatewayDeployed window does not leak a duplicate — but
        # ONLY when bound to the current dataPlaneId. In the name-only degrade (dp_id
        # unresolvable) we do NOT reuse an in-progress row, to avoid resurrecting a stale
        # in-progress orphan from a same-named DP recreate.
        if dp_id and candidates:
            return candidates[0].get("id")
        return None

    def _reresolve_gateway_id(self, dp_name, tried_ids=()):
        """PCP-19765: re-resolve the CURRENT gateway id for ``dp_name`` after a wrong-id
        404 — the deploy-POST returns a PLACEHOLDER gateway id the backend RE-KEYS
        (supersedes) once async provision completes, so polling the placeholder id 404s
        "Gateway not found" (the React client recovers from exactly this via
        ``resolveBySupersede``). This is the automation's equivalent for the id-primary
        Hub-API polls that bypass the UI.

        STRICT (gating-safe): matches ``_gateway_name(dp_name)`` + ``origin=='cp_dp'`` +
        the DP's CURRENT ``dataPlaneId`` (via ``_resolve_dataplane_id``) — NO name-only
        degrade (that is for idempotency, not a status recovery), and fails LOUD on >1
        (ambiguous multi-gateway-per-dp). It does NOT require ``mcpgatewayDeployed`` (the
        row may be re-keyed before the flag flips).

        SOFT: returns ``None`` (never ``exit_error``) on any API error or an unresolvable
        ``dataPlaneId``, so the CALLER's bounded loop owns retry-vs-abort — a transient
        ``/gateways`` blip during recovery must not hard-abort the gate. Returns an id
        NOT already in ``tried_ids`` (so a re-resolve that keeps returning an
        already-failed id lets the caller terminate), or ``None``.
        """
        dp_id = self._resolve_dataplane_id(dp_name)
        if not dp_id:
            return None  # can't strictly bind to the DP identity -> caller retries/aborts
        url = self._gateways_api_url or f"{self._hub_origin()}{self.HUB_API_BASE_PATH}/gateways"
        try:
            response = self.page.context.request.get(url)
            if not response.ok:
                return None
            data = response.json()
        except Exception:
            return None
        rows = data if isinstance(data, list) else (
            data.get("gateways", []) if isinstance(data, dict) else [])
        gw_name = self._gateway_name(dp_name)
        ids = [g.get("id") for g in rows if isinstance(g, dict)
               and g.get("name") == gw_name and g.get("origin", "cp_dp") == "cp_dp"
               and g.get("dataPlaneId") == dp_id and g.get("id")]
        if len(set(ids)) > 1:
            Util.exit_error(
                f"Multiple gateways named '{gw_name}' on DP '{dp_name}' — cannot re-resolve a "
                "superseded gateway id unambiguously (multi-gateway-per-dp)",
                self.page, "gateway_reresolve_ambiguous.png")
            return None  # defensive: exit_error sys.exit()s
        for gid in ids:
            if gid not in tried_ids:
                return gid
        return None

    def _detail_push_button(self):
        """The gateway-detail Push action, scoped to dp-detail-root. Rendered as a
        Fresco Button 'Push Changes to Gateway'.

        PCP-22620: unlike the other deploy-mcp-hub controls (flipped to test-id-first
        against the PCP-22619 hooks), this one stays role+name-FIRST on purpose — the
        ``dp-detail-sync`` header action is DESCOPED in PCP-22619: a Fresco
        ``TibcoHeader`` action button cannot carry a per-action data-testid even at
        alpha.87 (tracked in PCP-22627). So the durable hook does not exist on the
        current Hub; the legacy ``dp-detail-sync`` test-id is kept only as an
        older-build fallback (CLAUDE.md §6, PCP-20336). Once PCP-22627 lands, flip this
        to test-id-first too."""
        new = self.page.get_by_test_id("dp-detail-root").get_by_role(
            "button", name=re.compile(r"Push Changes to Gateway", re.I)).first
        if Util.check_dom_visibility(self.page, new, 1, 2):
            return new
        legacy = self.page.get_by_test_id("dp-detail-sync").first
        if Util.check_dom_visibility(self.page, legacy, 1, 1):
            return legacy
        return new

    def _servers_registry_button(self):
        """The MCP Servers tab 'Browse Registry' action.

        PCP-22620: resolve by the stable ``servers-registry-button`` test-id FIRST
        (PCP-22619 re-added it via the Fresco alpha.87 test-id passthrough / PLTUX-1299),
        falling back to the label 'Browse Registry' by role+name only for older Hub
        builds that predate the test-id — so a visible-label rename can never break the
        selector again (same test-id-first flip as the Register footer, PCP-22575). The
        role+name match is unanchored, because a PrimeReact icon glyph can fold into the
        accessible name. Returns the test-id locator when neither variant is visible yet
        (a current Hub renders the durable test-id, not the label), so the caller's own
        check_dom_visibility polls the right hook (CLAUDE.md §6 backward-compat)."""
        by_test_id = self.page.get_by_test_id("servers-registry-button").first
        if Util.check_dom_visibility(self.page, by_test_id, 1, 3):
            return by_test_id
        by_role = self.page.get_by_role("button", name=re.compile(r"Browse Registry")).first
        if Util.check_dom_visibility(self.page, by_role, 1, 2):
            return by_role
        return by_test_id

    def wait_for_gateway_deployed(self, gateway_id=None, dp_name=None, max_minutes=15):
        """Wait until the gateway is deployed, then ensure the detail DEPLOYED VIEW
        is operable so subsequent steps (install servers / push) can drive it.

        Two signals, in order (PCP-20336):
          1. DETERMINISTIC: poll the gateways API (``_api_get_gateway``) until the
             row exists with ``mcpgatewayDeployed`` true — the backend's own
             "deploy accepted" truth, not a UI flag. Resolved by id (from the
             deploy POST), else by ``dp_name``.
          2. UI-OPERABLE: once the API says deployed, open the detail page and
             confirm the Push action renders (the element install/push need). The
             detail deployed view is gated on the SAME ``mcpgatewayDeployed`` flag,
             so once (1) holds a fresh load renders it; if it does NOT within a
             bounded wait, that is the UI-flag lag (PCP-20127) — fail loud and
             specific, never a blind 15-minute poll.
        """
        gid = gateway_id or self.gateway_id
        for i in range(max_minutes * 2):  # 30s interval
            row = self._api_get_gateway(gateway_id=gid, dp_name=dp_name)
            if row and row.get("mcpgatewayDeployed"):
                # PCP-19765: rid is the CURRENT id (via _api_get_gateway's dp_name fallback
                # it may differ from a superseded placeholder gid). Track it on self AND
                # return it so the caller can reassign and stop passing the stale id
                # downstream (goto_gateway / online / refresh all key off the id).
                rid = row.get("id") or gid
                if rid:
                    self.gateway_id = rid
                    self.goto_gateway(rid)
                if Util.check_dom_visibility(self.page, self._detail_push_button(), 2, 30):
                    ColorLogger.success("MCP Gateway is deployed (API mcpgatewayDeployed + detail view operable)")
                    return rid
                Util.exit_error(
                    "Gateway reports deployed via the Hub API (mcpgatewayDeployed) but the detail "
                    "view never rendered the Push action — the UI deployed flag is lagging the "
                    "running pod (PCP-20127); report to the MCP Hub team",
                    self.page, "mcp_gateway_ui_lag.png")
                return rid
            ColorLogger.info(f"Gateway not deployed yet per Hub API (pod starting)... ({i * 30}s)")
            self.page.wait_for_timeout(30000)
        Util.exit_error(
            f"MCP Gateway did not report deployed via the Hub API within {max_minutes} minutes — "
            "the deploy may have failed; report to the MCP Hub/DP team",
            self.page, "mcp_gateway_not_deployed.png")

    def _wait_for_gateway_online(self, gateway_id=None, max_minutes=15, *, dp_name=None):
        """Wait for the MCP Gateway to come ONLINE via the DETERMINISTIC Hub API
        (PCP-20336): force a fresh health-check probe and accept the response's
        ``status == 'online'``. POST /gateways/{id}/health-check runs a real HTTP
        GET to the gateway /health and returns the live status synchronously, so
        this does not depend on a lagging UI flag. Keeps a loud 15-min timeout for
        a genuinely-offline gateway (a real DP/pod issue to report, not mask).
        Falls back to the legacy UI status only when the endpoint is absent.

        PCP-19765: when ``dp_name`` is provided and the health-check reports the id
        "Gateway not found" (a SUPERSEDED placeholder id — re-keyed after async
        provision), re-resolve the current gateway id for ``dp_name`` and keep polling
        the new id instead of hard-aborting. Returns the effective (possibly re-resolved)
        gateway id so the caller can reassign its local id.
        """
        gid = gateway_id or self.gateway_id
        if not gid:
            Util.exit_error("No gateway id available to poll for online status",
                            self.page, "gateway_online_noid.png")
        base = self._gateways_api_url or f"{self._hub_origin()}{self.HUB_API_BASE_PATH}/gateways"
        health_url = f"{base.rstrip('/')}/{gid}/health-check"
        ColorLogger.info(f"Waiting for MCP Gateway to come online (via {health_url})...")
        consecutive_errors = 0
        tried_ids = set()  # PCP-19765: superseded ids already proven 404, for loop termination
        for i in range(max_minutes * 2):  # 30s interval
            resp = self.page.context.request.post(health_url)
            if resp.status == 404:
                # Disambiguate the two 404s: the route returns 404 {error:'Gateway not
                # found'} for a wrong/missing id (endpoint EXISTS) vs a generic 404 when
                # the endpoint is absent (legacy variant). A wrong id must fail loud, not
                # silently UI-fallback into a confusing timeout (PCP-20336).
                body = ""
                try:
                    body = resp.text() or ""
                except Exception:
                    body = ""
                if "Gateway not found" in body:
                    # PCP-19765: a "Gateway not found" 404 = this id is a SUPERSEDED
                    # placeholder (re-keyed after async provision). Re-resolve the current
                    # gateway id for dp_name (strict + soft) and keep polling the new id;
                    # only abort if re-resolution yields no NEW id (tried_ids guards the loop).
                    if dp_name:
                        tried_ids.add(gid)
                        new_id = self._reresolve_gateway_id(dp_name, tried_ids)
                        if new_id:
                            ColorLogger.info(
                                f"Health-check: gateway id '{gid}' superseded; re-resolved to "
                                f"'{new_id}' by DP '{dp_name}', continuing")
                            gid = new_id
                            self.gateway_id = new_id
                            health_url = f"{base.rstrip('/')}/{gid}/health-check"
                            continue
                    Util.exit_error(
                        f"Health-check reports gateway '{gid}' not found — the resolved gateway id "
                        "is wrong; cannot verify online status",
                        self.page, "gateway_not_found.png")
                    return gid
                # Legacy variant without the health-check endpoint: switch to a single
                # bounded UI poll (do NOT re-run the deployed-wait every iteration — that
                # would be quadratic in wall-clock).
                ColorLogger.info("health-check endpoint absent (404); using the legacy UI online check")
                self._wait_for_gateway_online_ui(gid, max_minutes, dp_name=dp_name)
                return gid
            if not resp.ok:
                # A persistent hard error (401/400/5xx) is an auth/URL/Hub problem, NOT a
                # slow gateway — fail fast after a few rather than burning the full budget
                # masquerading as 'offline'.
                consecutive_errors += 1
                if consecutive_errors >= 3:
                    Util.exit_error(
                        f"MCP Hub health-check API returned HTTP {resp.status} 3x for {health_url} — "
                        "cannot verify online status (auth/URL/Hub issue, not a slow gateway)",
                        self.page, "gateway_healthcheck_error.png")
                    return
                ColorLogger.warning(f"health-check HTTP {resp.status} ({consecutive_errors}/3); retrying...")
            else:
                consecutive_errors = 0
                try:
                    status = (resp.json() or {}).get("status")
                except Exception:
                    status = None
                if status == "online":
                    ColorLogger.success("MCP Gateway is online!")
                    return gid
                ColorLogger.info(f"Gateway not online yet (status={status or 'unknown'})... ({i * 30}s)")
            if i < max_minutes * 2 - 1:
                self.page.wait_for_timeout(30000)
        Util.exit_error(
            f"MCP Gateway did not come online within {max_minutes} minutes "
            "(health-check status != online) — report to the MCP Hub/DP team if the pod is stuck",
            self.page, "mcp_gateway_not_online.png")
        return gid

    def _wait_for_gateway_online_ui(self, gid, max_minutes=15, *, dp_name=None):
        """LEGACY UI online poll — used ONLY when the health-check endpoint returns
        404 (an older variant). One deployed-wait, then a bounded reload+status poll
        (NOT nested per-iteration; avoids the quadratic wall-clock). PCP-20336.
        PCP-19765: threads dp_name so the deployed-wait can recover a superseded id."""
        self.wait_for_gateway_deployed(gid, dp_name=dp_name)
        for i in range(max_minutes * 2):  # 30s interval
            if self.is_gateway_online():
                ColorLogger.success("MCP Gateway is online! (UI fallback)")
                return
            ColorLogger.info(f"Gateway not online yet (UI)... ({i * 30}s)")
            self.page.wait_for_timeout(30000)
            self.page.reload(wait_until="domcontentloaded")
            self.page.wait_for_timeout(2000)
        Util.exit_error(
            f"MCP Gateway did not come online within {max_minutes} minutes (UI fallback)",
            self.page, "mcp_gateway_not_online.png")

    def _wait_for_target_dp_online(self, dp_name, max_minutes=15):
        """Wait until the target cp_dp Data Plane reports status 'online' (PCP-20127).

        Must be called BEFORE entering the Register Gateway wizard. The wizard's
        target-DP list is fetched once at page mount (useGateways: staleTime 0, no
        refetchInterval) and never refreshes mid-wizard, so a DP that is still
        coming online (created ~2-3 min earlier) renders as a disabled row the
        wizard cannot recover from. Gating here — on the same Hub `/gateways` API
        the wizard itself reads — means the wizard's mount-time fetch sees the DP
        online and renders the row enabled.

        Polls the deterministic API (not the UI), via the browser-auth-shared
        ``page.context.request`` (the Hub authenticates by cookie, so the request
        context shares the session). A DP is ready when the entry with this name
        AND ``origin == 'cp_dp'`` has ``status == 'online'`` (status enum is
        online|offline|unknown). Fails fast and loud on an API error rather than
        burning the full timeout on a wrong URL.
        """
        # PCP-19802 (design-B): the Register-Gateway wizard populates its target-DP
        # dropdown from GET /data-planes (useInstallableDataPlanes), NOT /gateways.
        # Under design-B, /gateways returns only DEPLOYED gateway rows (no bare cp_dp DP
        # rows), so polling /gateways for the DP can never match and deadlocks. Poll
        # /data-planes — the same endpoint the wizard reads — which lists every
        # installable DP with a status (online|offline|unknown).
        base = self._gateways_api_url or f"{self._hub_origin()}{self.HUB_API_BASE_PATH}/gateways"
        url = base.rsplit("/gateways", 1)[0] + "/data-planes"
        ColorLogger.info(f"Waiting for target Data Plane '{dp_name}' to be online (via {url})...")
        attempts = max(1, max_minutes * 2)  # 30s interval
        for i in range(attempts):
            response = self.page.context.request.get(url)
            if not response.ok:
                Util.exit_error(
                    f"MCP Hub gateways readiness API returned HTTP {response.status} "
                    f"for {url} — cannot verify the target Data Plane is online. Check "
                    "the MCP Hub webserver / the captured API path.",
                    self.page, "register_dp_online_api.png")
                return  # defensive: exit_error sys.exit()s; never fall through to use unbound data
            try:
                data = response.json()
            except Exception:
                Util.exit_error(
                    f"MCP Hub gateways readiness API returned non-JSON for {url}",
                    self.page, "register_dp_online_api.png")
                return
            dp = None
            if isinstance(data, list):
                # /data-planes entries are installable DPs: {dpId,name,status,gatewayCount}.
                # Key on origin=='cp_dp' (the method's contract): a 'direct' row with
                # the same name must not satisfy the gate. The live /data-planes payload
                # carries no 'origin', so it defaults to 'cp_dp' (every installable DP
                # matches) — zero live-behavior change; this only excludes an explicit
                # non-cp_dp row (PCP-20336).
                dp = next(
                    (g for g in data
                     if isinstance(g, dict) and g.get("name") == dp_name
                     and g.get("origin", "cp_dp") == "cp_dp"),
                    None)
            status = dp.get("status") if dp else None
            if status == "online":
                ColorLogger.success(f"Target Data Plane '{dp_name}' is online")
                return
            ColorLogger.info(
                f"Target Data Plane '{dp_name}' not online yet (status={status or 'not listed'})... ({i * 30}s)")
            if i < attempts - 1:  # don't sleep after the final check, before the timeout error
                self.page.wait_for_timeout(30000)
        Util.exit_error(
            f"Target Data Plane '{dp_name}' did not come online within {max_minutes} minutes "
            "— it must be online before deploying the gateway onto it (report to the CP/DP team "
            "if the DP is stuck).",
            self.page, "register_dp_not_online.png")

    # ------------------------------------------------------------------ #
    # Deploy gateway via the Register Gateway wizard (auto-provision)
    # ------------------------------------------------------------------ #
    def deploy_mcp_gateway(self, dp_name, skip_online_wait=False):
        """Deploy the MCP Gateway onto a bare CP Data Plane via the Register
        Gateway wizard, "Deploy to a TIBCO Data Plane" (auto-provision) path.

        Wizard sub-steps (auto-provision, Fresco modal): [deployment ->] setup
        (identity + target-dp) -> network & deploy-mode -> review -> verify (older
        builds split identity/DP and network/deploy-mode into separate steps and
        insert Advanced / Gateway-Config steps before Review; all still handled
        below). The Deployment mode-picker step is CONDITIONAL (PCP-22220): on a
        CP-default
        build (CP mode + standalone-gateway flag off -> cpGateActive) it is dropped
        and the wizard opens directly on the Setup step; flag-on / standalone /
        legacy builds keep it. The deploy POST fires on entering the Verify step;
        the Verify animation is a client-side timer and is NOT a reliable success
        signal, so this method captures the POST response to resolve the gateway
        UUID.

        Args:
            dp_name: Target Data Plane name (the bare cp_dp DP to deploy onto).
            skip_online_wait: If True, do not wait for the gateway to come online
                (servers are installed and pushed before the gateway is ready).

        Returns:
            str: The gateway UUID (DataPlane.id), or "" if it could not be resolved.
        """
        # Idempotency: reuse an existing gateway for this DP if present — deployed
        # preferred, else one still provisioning (PCP-20573). Deterministic
        # gateways-API lookup, NOT the UI dashboard: on the 1.17.1 multi-gateway-per-dp
        # dashboard the UI lookup missed existing gateways, so re-runs re-deployed and
        # piled up duplicates (PCP-20336). Reusing an in-progress row (the deploy POST
        # creates it minutes before mcpgatewayDeployed flips) stops a retry in that
        # window from leaking another gateway.
        existing_id = self._find_existing_gateway_id(dp_name)
        if existing_id:
            ColorLogger.info(f"MCP Gateway already registered for '{dp_name}' (id={existing_id})")
            self.gateway_id = existing_id
            if not skip_online_wait:
                # A reused gateway may still be provisioning (PCP-20573) — ensure it is
                # deployed (re-keying to the current id) before waiting for online.
                existing_id = self.wait_for_gateway_deployed(existing_id, dp_name=dp_name) or existing_id
                self.gateway_id = existing_id
                self._wait_for_gateway_online(existing_id, dp_name=dp_name)
            return existing_id

        # PCP-20127: the Register wizard fetches its target-DP list once at page
        # mount and never refreshes it, so the DP must already be online before we
        # enter the wizard (independent of skip_online_wait, which governs the
        # separate post-deploy gateway-online wait).
        self._wait_for_target_dp_online(dp_name)

        ColorLogger.info(f"Deploying MCP Gateway for '{dp_name}' via Register Gateway wizard...")
        self.page.goto(self._hub_url("/gateways/register"), wait_until="domcontentloaded")

        # Step 1: open the Register wizard. PCP-22027: it is a Fresco MODAL reached by a deep-link
        # - /gateways/register redirects to the gateways list with "?register=true" and
        # RegisterGatewayModalHost opens the wizard (the redirect is intentional and explicitly kept
        # for this automation). PCP-22220: on a CP-default build (CP mode + standalone-gateway flag
        # OFF -> cpGateActive) the wizard DROPS the Deployment mode-picker step and opens directly on
        # the Setup step (DP picker + name); flag-on / standalone / legacy builds still open on the
        # Deployment step. Detect "modal open" the way tp-mcp-hub's own e2e POM does
        # (RegisterGatewayPage.open): an OR-RACE on the Deployment heading OR the Setup DP picker,
        # returning as soon as EITHER appears - NOT two sequential waits. Do NOT key on
        # 'register-gateway-wizard': it wraps a Fresco dialog that portals OUTSIDE .mcp-hub-root, so
        # it has no visible box (a heading-first sequential wait would also burn its full ~22s budget
        # on the CP-default path and re-emit a false "Dom not visible" signature, and could miss a
        # slow-opening flag-on heading). (CLAUDE.md §6 backward-compat: the legacy full-page wizard
        # still renders the heading, so the heading arm of the race covers old builds.)
        # The Setup arm keys on register-dp-picker only (the PCP-21970 dropdown); a step-dropping
        # build (PCP-22220) is strictly newer than that dropdown so it always renders it, so one arm
        # suffices here (downstream 759+ keeps the register-dp-option fallback for pre-dropdown
        # builds). Pass `.or_(...).first`: check_dom_visibility's is_visible() raises a strict-mode
        # violation if BOTH arms are attached at once (step-transition overlap); `.first` narrows to
        # one (repo convention - see po_settings.py + CLAUDE.md §3).
        deploy_heading_re = re.compile("How do you want to deploy", re.I)
        if not Util.check_dom_visibility(
                self.page,
                self.page.get_by_role("heading", name=deploy_heading_re)
                    .or_(self.page.get_by_test_id("register-dp-picker")).first,
                2, 30):
            Util.exit_error(
                "Register Gateway modal did not open after navigating to /gateways/register. "
                "Expected the deep-link redirect to '/?register=true' to open the Fresco modal "
                "(RegisterGatewayModalHost) on either the Deployment step ('How do you want to "
                "deploy') or the Setup step (register-dp-picker). Check the MCP Hub build (register "
                "modal host) and the deep-link redirect.",
                self.page, "register_modal_not_open.png")

        # Step 1 mode-card is CONDITIONAL - present only when the wizard opened on the Deployment
        # step (flag-on / standalone / legacy). The heading is co-located with the mode card in
        # StepDeployment.tsx, so the heading alone distinguishes the layouts (mirrors the e2e POM's
        # hasDeploymentStep - do NOT re-add a 'register-mode-provision-auto' open check here). When
        # present, select "Deploy to a TIBCO Data Plane" (auto-provision) + Next; a non-CP backend
        # keeps the Deployment step but has no provision-auto card, so diagnose that distinctly.
        # When the step was dropped (CP default), the wizard already opened on the Setup step with
        # auto-provision forced, so fall straight into the Setup/Identity handling below.
        has_deployment_step = Util.check_dom_visibility(
            self.page, self.page.get_by_role("heading", name=deploy_heading_re), 1, 2)
        if has_deployment_step:
            if not Util.check_dom_visibility(
                    self.page, self.page.get_by_test_id("register-mode-provision-auto"), 2, 20):
                Util.exit_error(
                    "'Deploy to a TIBCO Data Plane' card not found on the Deployment step. The MCP "
                    "Hub backend must be in CP mode (MCP_HUB_MODE=cp) for auto-provision; without it "
                    "the wizard only offers Manual Helm / Connect-a-running-gateway. Verify the "
                    "webserver deployment env.",
                    self.page, "register_no_cp_mode.png")
            self.page.get_by_test_id("register-mode-provision-auto").click()
            self._register_continue()

        # Step 2: Identity (+ Target Data Plane). PCP-21482: newer MCP Hub
        # (1.17.1-alpha.81 on base 1.19.0-alpha.161) MERGED the Target Data Plane
        # picker INTO the Identity step and gates the name field on it — the name
        # input renders disabled (aria-describedby="register-name-awaiting-dp") with
        # the hint "Select a Data Plane above to name the gateway." until a DP row is
        # selected. So when the DP picker is present on THIS step, pick the DP FIRST
        # (which enables the name field), then fill the name, then a single Continue.
        # Older builds keep them as two separate steps (name here, DP on the next),
        # so branch on whether register-dp-option is on the Identity step (CLAUDE.md
        # §6 backward-compat). Verified live on ins-owen-mcp-81-b.
        # PCP-21970: newer MCP Hub (1.17.1-alpha.103 on base 1.19.0-alpha.185)
        # replaced the clickable DP rows with a PrimeNG dropdown
        # (data-testid "register-dp-picker"); detect either so the merged
        # pick-DP-then-name flow is taken for both variants.
        dp_on_identity = Util.check_dom_visibility(
            self.page, self.page.get_by_test_id("register-dp-picker"), 1, 5) or \
            Util.check_dom_visibility(
                self.page, self.page.get_by_test_id("register-dp-option").first, 1, 5)
        if dp_on_identity:
            self._register_pick_target_dp(dp_name)   # enables the name field
            self._register_fill_identity(dp_name)
            self._register_continue()
        else:
            # Legacy two-step flow: Identity (name) then a separate Target DP step.
            self._register_fill_identity(dp_name)
            self._register_continue()
            self._register_pick_target_dp(dp_name)
            self._register_continue()

        # Step 3/4: Network Access (+ possibly MERGED Deployment Mode + Storage).
        # PCP-21482: newer MCP Hub merged these into one "Network & Deployment" step —
        # the ingress Route Resource table AND the Deployment Mode (Lite default) +
        # Storage Class table render together (register-config-section-network +
        # register-config-section-deploy-mode), and the single Continue stays disabled
        # until BOTH the ingress route AND a storage class are selected. Older builds
        # keep Network Access and Deployment Mode as two separate steps. Both resource
        # tables share the dp-action-resource-row test-id, so _register_select_or_create_resource
        # disambiguates by the unique instance name across either layout (CLAUDE.md §6
        # backward-compat). Verified live on ins-owen-mcp-81-b.
        self._register_select_or_create_resource(
            instance_name=f"mcp-{dp_name}",
            fill_fields_fn=lambda: self._fill_ingress_resource_fields(dp_name),
            card_test_id="register-config-section-network",
        )
        deploy_mode_merged = Util.check_dom_visibility(
            self.page, self.page.get_by_test_id("register-config-section-deploy-mode"), 1, 3)
        if deploy_mode_merged:
            # Merged step: select the storage class on the SAME page (Lite is default),
            # then a single Continue advances past Network & Deployment.
            self._register_select_or_create_resource(
                instance_name=ENV.TP_AUTO_STORAGE_CLASS,
                fill_fields_fn=lambda: self._fill_storage_resource_fields(ENV.TP_AUTO_STORAGE_CLASS),
                add_label="Add Storage Class",
                card_test_id="register-config-section-deploy-mode",
            )
            self._register_continue()
        else:
            # Legacy two-step flow: Network Access here, Deployment Mode/storage next.
            self._register_continue()
            self._register_select_or_create_resource(
                instance_name=ENV.TP_AUTO_STORAGE_CLASS,
                fill_fields_fn=lambda: self._fill_storage_resource_fields(ENV.TP_AUTO_STORAGE_CLASS),
                add_label="Add Storage Class",
                card_test_id="register-config-section-deploy-mode",
            )
            self._register_continue()

        # PCP-21970: older builds insert extra intermediate steps (Advanced,
        # Gateway Configuration) between Network & Deployment and Review & Deploy;
        # the consolidated wizard (MCP Hub 1.17.1-alpha.103 on base 1.19.0-alpha.185)
        # drops them and lands directly on Review & Deploy. Advance with Continue
        # until the Review step (its 'Register & Deploy' button) is reached — the
        # defaults on any intermediate step are valid — so both layouts work
        # (CLAUDE.md §6 backward-compat).
        for _ in range(3):
            if Util.check_dom_visibility(
                    self.page,
                    self._register_footer_button("Register & Deploy", test_id="register-review-submit"),
                    1, 2):
                break
            self._register_continue()

        # Review & Deploy -> Verify (deploy POST fires here).
        gateway_id = self._register_review_and_deploy(dp_name)
        self.gateway_id = gateway_id

        if not skip_online_wait:
            self._wait_for_gateway_online(gateway_id, dp_name=dp_name)
        return gateway_id

    @staticmethod
    def _footer_name_re(label):
        """Compile the role+name regex for a footer button, treating ' & ' and ' and '
        as equivalent (PCP-22439).

        MCP Hub 1.20 (frontend wip-poc-1-4383ae4) relabelled the Review submit button
        from 'Register & Deploy' (ampersand) to 'Register and Deploy' (the word 'and'),
        and it still carries no per-action test-id. A literal ``re.escape(label)`` match
        on one spelling misses the other, so ``deploy-mcp-hub`` aborted with 'forward
        button not found'. Escape the label, then collapse an escaped ' & ' or ' and '
        connector to '(?:&|and)' so a caller passing EITHER spelling matches BOTH
        (CLAUDE.md §6 backward-compat). Labels without that connector are unaffected.
        """
        connector = r" (?:&|and) "
        pattern = re.escape(label)
        pattern = pattern.replace(re.escape(" & "), connector).replace(re.escape(" and "), connector)
        return re.compile(pattern)

    def _register_footer_button(self, label, test_id=None):
        """Resolve a Register-wizard footer nav button (Continue / Register & Deploy /
        Finish) to a single-match locator, across MCP Hub versions (PCP-21143).

        MCP Hub 1.17.0-alpha.142+ dropped the per-action data-testids
        (register-continue / register-review-submit / register-finish) when the
        wizard footer moved to plain buttons, and 1.17.1 migrated them to Fresco
        <Button>s that DROP data-testid entirely (shared/ui/Button.tsx: "no
        data-testid ... select buttons by role+name"). Both variants render a real
        <button> whose accessible name is the visible label.

        PCP-22575: resolve by the per-action data-testid FIRST (PCP-22440 re-added
        register-continue / register-review-submit / register-finish via Fresco
        alpha.86's *ButtonTestId passthrough / PLTUX-1298), falling back to the
        label-tolerant role+name match only for older Hub builds that predate the
        test-id — so a visible-label rename can never break the selector again
        (PCP-22432: "Register & Deploy" -> "Register and Deploy"; the forward button's
        label is even Fresco-default "Next", not "Continue", so role+name alone cannot
        resolve it on a current Hub).

        The role+name match is UNANCHORED (substring) — a PrimeReact icon glyph can
        fold into the accessible name (same caveat as _servers_registry_button /
        _detail_push_button), and it lets a label whose suffix varies still match
        (e.g. "Finish" matching "Finish & open gateway"). The sibling Back/Cancel
        buttons have distinct names, so name matching never collides with them.
        Return semantics when a `test_id` IS supplied: the test-id locator if it is visible;
        else the role+name locator if THAT is visible (older-Hub fallback); else the test-id
        locator when neither is visible yet (a current Hub renders the durable test-id, not the
        "Continue"/"Finish" label, so the caller's own check_dom_visibility polls the right hook).
        With NO `test_id`, role+name is used directly.

        PCP-22029: the Fresco Register wizard is a modal, but a properly-modal dialog
        a11y-hides the page behind it, so a page-global role+name match sees only the modal's
        button — this mirrors tp-mcp-hub's own e2e POM (e2e/pages/register-gateway.page.ts),
        which resolves the footer page-global (getByRole('button', {name: 'Next'})). So no
        dialog scoping is needed; the resolution stays page-global — now test-id-first with
        role+name as the older-build fallback (PCP-22575, inverting the earlier order).
        """
        by_role = self.page.get_by_role("button", name=self._footer_name_re(label)).first
        if test_id:
            by_test_id = self.page.get_by_test_id(test_id).first
            if Util.check_dom_visibility(self.page, by_test_id, 1, 3):
                return by_test_id
            # Test-id not up yet: use role+name only if it is actually present (an older Hub
            # build that predates the test-id); otherwise keep the test-id locator so the caller
            # polls the durable hook, not a "Continue"/"Finish" label a current Hub never renders.
            if Util.check_dom_visibility(self.page, by_role, 1, 2):
                return by_role
            return by_test_id
        return by_role

    def _register_continue(self):
        """Advance the Register wizard by one step (click the forward footer button once enabled).

        PCP-22029: the Fresco Register modal relabelled the forward nav button 'Continue' -> 'Next'
        (StepDeployment/StepSetup/StepConfigure footers; the terminal step keeps its own verb
        'Register & Deploy'). PCP-22575: resolve by the stable 'register-continue' test-id FIRST
        (re-added on the Hub side by PCP-22440), so neither the 'Continue' -> 'Next' relabel nor any
        future forward-button rename can break selection; '_register_footer_button' falls back to the
        'Next' role+name for a Hub that predates the test-id. A second call adds the legacy 'Continue'
        role+name for the very old full-page wizard (CLAUDE.md §6 backward-compat). The Fresco 'Next'
        button is never disabled (it validates on click and simply does not advance on an invalid
        step), so click_button_until_enabled still applies for the legacy 'Continue' path.
        """
        btn = self._register_footer_button("Next", test_id="register-continue")
        if not Util.check_dom_visibility(self.page, btn, 1, 5):
            btn = self._register_footer_button("Continue", test_id="register-continue")
        if not Util.check_dom_visibility(self.page, btn, 1, 15):
            Util.exit_error(
                "Register wizard forward button not found (looked for 'Next', then legacy 'Continue')",
                self.page, "register_continue.png")
        Util.click_button_until_enabled(self.page, btn)
        self.page.wait_for_timeout(800)

    def _register_fill_identity(self, dp_name):
        """Fill the gateway name on the Identity step.

        The name is ``gateway-<dp_name>`` (PCP-21143, via ``_gateway_name``) so the
        gateway is named distinctly from its target Data Plane; the same helper backs
        the name-based gateway lookups, keeping the wizard write and the reuse/status
        reads in lockstep.
        """
        gw_name = self._gateway_name(dp_name)
        # Newer MCP Hub gives the name input a 'register-name' test-id (PrimeNG
        # inputtext); older builds used a plain '.rg-step-page input.text-input'.
        if Util.check_dom_visibility(self.page, self.page.get_by_test_id("register-name"), 1, 10):
            # PCP-21482: newer MCP Hub gates this field on DP readiness — it renders
            # visible but DISABLED (aria-describedby="register-name-awaiting-dp")
            # until the wizard's target-DP list resolves. A disabled input makes
            # Playwright .fill() blow its 30s timeout, so wait for enabled first and
            # fail loud with a screenshot if it never enables (rather than a silent
            # fill timeout).
            if not Util.check_dom_enabled(self.page, self.page.get_by_test_id("register-name"), 2, 60):
                Util.exit_error(
                    "Register wizard gateway-name field stayed disabled (awaiting DP). "
                    "The target Data Plane is not ready for the wizard.",
                    self.page, "register_name_awaiting_dp.png")
            self.page.get_by_test_id("register-name").fill(gw_name)
        else:
            selector = ".rg-step-page input.text-input"
            if not Util.check_dom_visibility(self.page, self.page.locator(selector).first, 1, 5):
                selector = "input.text-input"
            self.page.locator(selector).first.fill(gw_name)
        ColorLogger.info(f"Gateway name: {gw_name}")

    def _register_pick_target_dp(self, dp_name):
        """Pick the target Data Plane on the Target Data Plane step.

        UI variants (CLAUDE.md §6 backward-compat):
          * PCP-22027/22028 (Fresco modal): a PrimeNG dropdown (data-testid 'register-dp-picker')
            with a '.p-dropdown-filter' search box and option rows tagged 'register-dp-option' —
            open it, type the DP name into the filter, then click the 'register-dp-option' row
            (anchored match).
          * PCP-21970 (older): the same 'register-dp-picker' dropdown but with no filter and plain
            '.p-dropdown-item' options — handled by this branch's fallback.
          * Oldest builds render clickable rows sharing data-testid 'register-dp-option' with no
            dropdown (filter by DP name).
        Only cp_dp DPs are listed; degraded (status != online) DPs are disabled.
        """
        # Newer PrimeNG-dropdown variant.
        if Util.check_dom_visibility(self.page, self.page.get_by_test_id("register-dp-picker"), 1, 5):
            picker = self.page.get_by_test_id("register-dp-picker")
            trigger = picker.locator(".p-dropdown-trigger").first
            if not Util.check_dom_visibility(self.page, trigger, 1, 10):
                trigger = picker.locator(".p-dropdown-label").first
            if not Util.check_dom_visibility(self.page, trigger, 1, 3):
                trigger = picker.locator(".p-dropdown").first
            trigger.click()
            # PCP-22029: the Fresco DP dropdown (PCP-22027/22028) adds a filter box and tags each
            # option row with a 'register-dp-option' test-id. Type the DP name into the filter to
            # narrow a long/virtualized list — optional: older PrimeNG dropdowns render every option
            # with no filter, so only fill it when the filter is present.
            dp_filter = self.page.locator(".p-dropdown-filter")
            if Util.check_dom_visibility(self.page, dp_filter.first, 1, 3):
                dp_filter.first.fill(dp_name)
                self.page.wait_for_timeout(300)
            # Prefer the 'register-dp-option' rows (Fresco wizard); their text is the DP name+health
            # concatenated with no separators, so anchor the match to the start with a digit
            # negative-lookahead. Fall back to the plain PrimeNG '.p-dropdown-item' (older dropdown
            # build) WITHIN this branch — never hard-fail before trying the fallback.
            anchored = re.compile("^" + re.escape(dp_name) + r"(?!\d)")
            option = self.page.get_by_test_id("register-dp-option").filter(has_text=anchored)
            if not Util.check_dom_visibility(self.page, option.first, 1, 5):
                option = self.page.locator(".p-dropdown-item").filter(has_text=dp_name)
            if not Util.check_dom_visibility(self.page, option.first, 1, 10):
                Util.exit_error(
                    f"Target Data Plane '{dp_name}' not listed in the Register wizard DP dropdown "
                    "(only cp_dp DPs appear here)",
                    self.page, "register_dp_missing.png")
            # Degraded DPs render with aria-disabled=true — the readiness gate
            # (PCP-20127) already waited for online, so a disabled option here is a
            # status-mapping/timing skew worth reporting rather than clicking blindly.
            if option.first.get_attribute("aria-disabled") == "true":
                Util.exit_error(
                    f"Target Data Plane '{dp_name}' renders as disabled in the wizard even though it "
                    "was reported online before the wizard opened — likely a DP-status timing skew or "
                    "status-mapping mismatch to report to the MCP Hub team",
                    self.page, "register_dp_degraded.png")
            option.first.click()
            ColorLogger.info(f"Selected target Data Plane: {dp_name}")
            return

        # Legacy clickable-row variant.
        if not Util.check_dom_visibility(self.page, self.page.get_by_test_id("register-dp-option").first, 2, 20):
            Util.exit_error("No target Data Plane options in the Register wizard", self.page, "register_no_dp.png")
        row = self.page.get_by_test_id("register-dp-option").filter(has_text=dp_name)
        if not Util.check_dom_visibility(self.page, row.first, 1, 10):
            Util.exit_error(
                f"Target Data Plane '{dp_name}' not listed (only cp_dp DPs appear here)",
                self.page, "register_dp_missing.png")
        # Postcondition guard: deploy_mcp_gateway already waited for this DP to be
        # online (PCP-20127) before entering the wizard, so the row should render
        # enabled. A one-shot check is correct here (no in-wizard poll): the
        # wizard's DP list is fetched once at mount and does not refresh, so
        # re-querying could never see a disabled row flip. A disabled row at this
        # point means the readiness gate and the wizard disagree (timing skew /
        # status-mapping issue) — fail fast and report it.
        if not row.first.is_enabled():
            Util.exit_error(
                f"Target Data Plane '{dp_name}' renders as disabled in the wizard even though it "
                "was reported online before the wizard opened — likely a DP-status timing skew or "
                "status-mapping mismatch to report to the MCP Hub team",
                self.page, "register_dp_degraded.png")
        row.first.click()
        ColorLogger.info(f"Selected target Data Plane: {dp_name}")

    def _register_select_or_create_resource(self, instance_name, fill_fields_fn, add_label="Add new",
                                            card_test_id=None):
        """Select an existing resource-instance row by name, or create one via the
        Add-Resource dialog.

        Shared by the Network Access (ingress) and Deployment Mode (storage) steps
        — both render the same ResourceTable (data-testid dp-action-resource-*).
        On successful create the new instance is auto-selected.

        The create trigger is resolved test-id-FIRST (`dp-action-resource-add`, re-added by
        PCP-22619), falling back to role+name on the contextual `add_label` for older Hub
        builds. `add_label` is the create-button text, which is contextual per step
        (ResourceTable.tsx `addButtonLabel`: "Add new" for Network Access, "Add Storage Class"
        for Deployment Mode), so the fallback must be given the right label. The Add-Resource
        dialog submit is likewise test-id-first (`dp-action-add-resource-submit`, PCP-22619),
        with a dialog-scoped CSS fallback.

        PCP-22028/22029: the Fresco "Network & Deployment" step renders MULTIPLE resource tables
        at once — the Network, Deployment Mode and Logs ConfigCards — all sharing the
        dp-action-resource-* test-ids. Pass `card_test_id` (register-config-section-network for
        ingress, register-config-section-deploy-mode for storage) to SCOPE the table / row /
        Add-button lookups to the owning card, so an unscoped `.first` can't act on the wrong
        card's table. The Add-Resource dialog it opens is a body-level modal and stays page-scoped.
        Falls back to unscoped (page) when card_test_id is None or the card is absent — the older
        single-table steps (CLAUDE.md §6 backward-compat).
        """
        # Scope to the owning ConfigCard when present (Fresco merged Configure step); else the page.
        scope = self.page
        if card_test_id and Util.check_dom_visibility(
                self.page, self.page.get_by_test_id(card_test_id), 1, 3):
            scope = self.page.get_by_test_id(card_test_id)

        # Fail early + loud (with a screenshot) if the resource table never renders,
        # rather than continuing and failing later in a less-specific way (CLAUDE.md §5).
        if not Util.check_dom_visibility(self.page, scope.get_by_test_id("dp-action-resource-table").first, 2, 20):
            Util.exit_error("Resource table (dp-action-resource-table) did not render",
                            self.page, "resource_table_missing.png")

        row = scope.get_by_test_id("dp-action-resource-row").filter(has_text=instance_name)
        if Util.check_dom_visibility(self.page, row.first, 1, 5):
            row.first.click()
            ColorLogger.info(f"Selected existing resource: {instance_name}")
            return

        ColorLogger.info(f"Resource '{instance_name}' not found, creating it...")
        # PCP-22620: prefer the `dp-action-resource-add` test-id FIRST (re-added by PCP-22619);
        # older Hub builds fall back to the trigger's contextual per-step label
        # ("Add new" / "Add Storage Class") by role+name. Guard with check_dom_visibility so a
        # selector miss fails fast with a screenshot, not a blind 30s click timeout.
        add_btn = scope.get_by_test_id("dp-action-resource-add").first
        if not Util.check_dom_visibility(self.page, add_btn, 1, 3):
            add_btn = scope.get_by_role("button", name=re.compile(re.escape(add_label))).first
            if not Util.check_dom_visibility(self.page, add_btn, 1, 10):
                Util.exit_error(f"Resource table add button (labelled '{add_label}') not found",
                                self.page, "add_resource_button.png")
        add_btn.click()
        if not Util.check_dom_visibility(self.page, self.page.get_by_test_id("dp-action-add-resource"), 2, 15):
            Util.exit_error("Add-Resource dialog did not open", self.page, "add_resource_dialog.png")

        self.page.locator("#resource-name").fill(instance_name)
        fill_fields_fn()
        # PCP-22620: prefer the `dp-action-add-resource-submit` test-id FIRST (re-added by
        # PCP-22619). Older Hub builds fall back to the primary PrimeNG button in the
        # Add-Resource dialog footer (a pi-plus icon + "Add" label) via dialog-scoped CSS rather than
        # accessible name — Chrome folds the icon's CSS ::before glyph into the a11y
        # name, so get_by_role(name="Add") does not match.
        submit = self.page.get_by_test_id("dp-action-add-resource-submit")
        if not Util.check_dom_visibility(self.page, submit, 1, 3):
            submit = self.page.locator(
                ".p-dialog", has=self.page.get_by_test_id("dp-action-add-resource")
            ).locator(".p-dialog-footer button.p-button:not(.p-button-text):not(.p-button-outlined)")
        Util.click_button_until_enabled(self.page, submit.first)
        # The dialog closes on success and the new instance is auto-selected.
        self.page.get_by_test_id("dp-action-add-resource").wait_for(state="hidden", timeout=30000)
        ColorLogger.success(f"Created resource: {instance_name}")

    def _fill_ingress_resource_fields(self, dp_name):
        """Fill the Add-Resource dialog fields for a new ingress controller.

        The ingress-controller field is a plain InputText in the merged code, but
        the live CP /resource-metadata/INGRESS response may render it as a
        PrimeReact dropdown (enum). Branch on the presence of a dropdown.
        """
        controller = ENV.TP_AUTO_INGRESS_CONTROLLER
        class_name = ENV.TP_AUTO_INGRESS_CONTROLLER_CLASS_NAME
        fqdn = f"mcp-hub-{dp_name}.{ENV.TP_AUTO_CP_DNS_DOMAIN}"
        dialog = self.page.get_by_test_id("dp-action-add-resource")

        dropdown = dialog.locator(".p-dropdown")
        if Util.check_dom_visibility(self.page, dropdown.first, 1, 3):
            dropdown.first.click()
            self.page.wait_for_timeout(500)
            option = self.page.locator(".p-dropdown-item", has_text=controller)
            if Util.check_dom_visibility(self.page, option.first, 1, 3):
                option.first.click()
            ColorLogger.info(f"Selected ingress controller (dropdown): {controller}")
        elif Util.check_dom_visibility(self.page, self.page.locator("#field-ingressController"), 1, 3):
            self.page.locator("#field-ingressController").fill(controller)
            ColorLogger.info(f"Filled ingress controller: {controller}")

        if Util.check_dom_visibility(self.page, self.page.locator("#field-ingressClassName"), 1, 3):
            self.page.locator("#field-ingressClassName").fill(class_name)
        if Util.check_dom_visibility(self.page, self.page.locator("#field-fqdn"), 1, 3):
            self.page.locator("#field-fqdn").fill(fqdn)
        ColorLogger.info(f"Ingress FQDN: {fqdn}")

    def _fill_storage_resource_fields(self, storage_class):
        """Fill the Add-Resource dialog fields for a new storage class."""
        if Util.check_dom_visibility(self.page, self.page.locator("#field-storageClassName"), 1, 3):
            self.page.locator("#field-storageClassName").fill(storage_class)

    def _register_review_and_deploy(self, dp_name):
        """Advance Review -> Verify (firing the deploy POST) and finish.

        Returns the gateway UUID parsed from the deploy POST response (preferred),
        from the resulting URL, or from the home list (fallback).
        """
        # PCP-22575: resolve by the stable 'register-review-submit' test-id first
        # (re-added Hub-side by PCP-22440), role+name on 'Register & Deploy' as the older-build fallback.
        if not Util.check_dom_visibility(
                self.page,
                self._register_footer_button("Register & Deploy", test_id="register-review-submit"),
                2, 15):
            Util.exit_error("Register wizard 'Register & Deploy' button not found on Review step",
                            self.page, "register_review.png")

        gateway_id = ""
        response = None
        # PCP-20175 #3: harden against a "Register & Deploy" click race. The
        # submit button's onClick only ADVANCES the stepper Review -> Verify;
        # the deploy POST (.../gateways/<dpUuid>/deploy) is fired separately by
        # a verify-step useEffect (exactly-once, guarded). Click and POST are
        # decoupled, so a single click occasionally advanced to Verify without
        # the automation capturing the POST. This is automation timing, NOT a
        # UI bug. Mirror the proven driver pattern: arm expect_response for the
        # non-GET deploy POST BEFORE clicking, resolve a FRESH submit locator
        # inside the loop, and retry up to 3x. If the button is already gone (a
        # prior attempt advanced to Verify), do NOT click — the verify-effect
        # still fires the POST and the armed expect_response can catch it.
        for attempt in range(1, 4):
            try:
                with self.page.expect_response(
                    lambda r: "/gateways/" in r.url and r.url.rstrip("/").endswith("/deploy")
                    and r.request.method == "POST",
                    timeout=40000,
                ) as resp_info:
                    submit = self._register_footer_button("Register & Deploy", test_id="register-review-submit")
                    if Util.check_dom_visibility(self.page, submit, 1, 3):
                        submit.click()
                    else:
                        ColorLogger.info(
                            f"'Register & Deploy' no longer visible on attempt {attempt}/3; "
                            "stepper already on Verify — waiting for the verify-effect deploy POST"
                        )
                response = resp_info.value
                break
            except Exception as e:
                ColorLogger.warning(
                    f"Deploy POST not observed on attempt {attempt}/3: {e}"
                )
                self.page.wait_for_timeout(2500)

        if response is not None:
            ColorLogger.info(f"Deploy POST {response.status} {response.url}")
            if response.ok:
                try:
                    data = response.json()
                    gateway_id = data.get("id", "") if isinstance(data, dict) else ""
                except Exception:
                    gateway_id = ""
            else:
                Util.warning_screenshot(f"Deploy POST returned status {response.status}",
                                        self.page, "deploy_post_failed.png")
        else:
            Util.warning_screenshot("Did not observe the deploy POST response after 3 attempts",
                                    self.page, "deploy_post_missing.png")

        # Verify step: 'Finish & open gateway' enables only when the verify handshake
        # is terminal (disabled={!isVerifyTerminal}), which for a freshly deployed
        # gateway can take a few minutes — longer than Playwright's default wait. The
        # deploy POST already fired above, so finishing is just navigation; click it
        # BEST-EFFORT (generous bounded wait) and never abort the deploy if the
        # handshake is slow. Readiness is owned by the deterministic
        # wait_for_gateway_deployed downstream, which surfaces a real failure loudly.
        # PCP-22575: resolve by the stable 'register-finish' test-id first (re-added
        # Hub-side by PCP-22440); role+name on "Finish" (substring also matches
        # "Finish & open gateway") is the older-build fallback.
        finish = self._register_footer_button("Finish", test_id="register-finish")
        if Util.check_dom_visibility(self.page, finish, 2, 30):
            try:
                # Wait via expect().to_be_enabled — it RE-RESOLVES the locator each
                # poll, so the Verify step's re-render can't leave us polling a stale
                # frozen element_handle() that never observes the enabled flip and burns
                # the whole timeout (PCP-21143 review). Best-effort: a slow/never-terminal
                # handshake is fine — wait_for_gateway_deployed downstream owns readiness.
                expect(finish).to_be_enabled(timeout=120000)
                finish.click()
                self.page.wait_for_timeout(2000)
            # Broad except is INTENTIONAL (not just the to_be_enabled AssertionError):
            # this Finish step is cosmetic navigation — the deploy POST already fired and
            # wait_for_gateway_deployed owns real readiness. After deploy the Verify step
            # often auto-navigates, so a click/handle error here is benign; narrowing the
            # catch would abort a SUCCESSFUL deploy on a harmless post-deploy nav (review).
            except Exception as e:
                ColorLogger.warning(
                    f"'Finish & open gateway' did not become clickable ({e}); the deploy POST "
                    "already submitted — continuing to the deterministic deployed-wait")

        if not gateway_id:
            match = re.search(r"/gateways/([^/?#]+)", self.page.url)
            if match and match.group(1) != "register":
                gateway_id = match.group(1)
        if not gateway_id:
            # Deploy POST/URL did not yield an id (e.g. response missed). Resolve
            # the gateway from the home list by its 'gateway-<dp>' name (PCP-21143,
            # via _gateway_name) as a last resort.
            ColorLogger.warning("Gateway id not resolved from response/URL; resolving from home list...")
            gateway_id = self._open_gateway_from_home(self._gateway_name(dp_name)) or ""
        if not gateway_id:
            Util.warning_screenshot("Could not resolve the gateway id after deploy",
                                    self.page, "deploy_no_gateway_id.png")
        ColorLogger.success(f"MCP Gateway deploy submitted (gateway id: {gateway_id or 'unknown'})")
        return gateway_id

    # ------------------------------------------------------------------ #
    # Install MCP servers from the registry (in-gateway Browse Registry)
    # ------------------------------------------------------------------ #
    def _card_installed_on_dp(self, card):
        """Whether a registry ``catalog-card`` already shows the 'added on this DP'
        badge (the server is already installed on the pre-selected gateway DP).

        PCP-22376: this is the deterministic "already-done" signal for the Browse
        flow's idempotency short-circuit. The badge is driven by a separate
        "which DPs is this server installed on" query, so it can render slightly
        AFTER the card body — use a modest polled wait (not a single instantaneous
        read) so a late badge is not missed. Card-scoped so it reads THIS server's
        card, not a sibling.

        MCP Hub 1.20.0 renamed the installed badge 'Installed on this DP' ->
        'Added on this DP' (the whole flow moved Install -> Add), so match either
        wording (CLAUDE.md §6 backward-compat). The '… on this DP' suffix is what
        makes this the INSTALLED signal — it never matches the NOT-installed pill
        'Not added' (no 'on this DP'), so the two states are never confused.
        """
        # .first: a card could carry more than one node with this text (badge + tooltip),
        # which would trip Playwright strict mode on the is_visible() read (CLAUDE.md §3).
        badge = card.get_by_text(re.compile(r"(Added|Installed) on this DP")).first
        return Util.check_dom_visibility(self.page, badge, 1, 3)

    def _skip_already_installed(self, catalog_name):
        """Idempotent skip for an already-added server: log it and close the Browse
        dialog. Single source of truth so the pre-check and the button-absent re-check
        (PCP-22376) stay in lockstep."""
        ColorLogger.info(f"'{catalog_name}' already added on this DP, skipping")
        self._close_browse_registry()

    @staticmethod
    def _is_visible_now(locator):
        """Instantaneous visibility probe (no polling sleep). Used only to CHOOSE between
        locator variants; the caller still polls the chosen locator with
        check_dom_visibility. Swallows the raise-on-absent so it honours a bool contract."""
        try:
            return locator.is_visible()
        except Exception:
            return False

    def _install_dialog(self):
        """The Add/Install server wizard dialog, across MCP Hub versions (PCP-22376).

        MCP Hub 1.20.0 renamed the wizard title 'Install <server>' -> 'Add <server>'
        AND its Fresco dialog carries NO aria-label, so
        ``get_by_role('dialog', name=/^Install/)`` no longer resolves it. The step
        indicator 'Step N of M' is unique to this wizard (the Browse Registry dialog
        has none), so scope by that; fall back to the legacy name-titled dialog for
        older builds (CLAUDE.md §6). Returns the step-scoped locator when neither
        variant is visible yet, so the caller's own check_dom_visibility polls the
        current selector.
        """
        step = self.page.get_by_role("dialog").filter(
            has=self.page.get_by_text(re.compile(r"Step\s+\d+\s+of\s+\d+"))).first
        # Instantaneous probe (no polling sleep) to CHOOSE the variant — callers of
        # _install_dialog() do their OWN check_dom_visibility polling on the returned
        # locator, so a sleeping check here would only add latency per wizard step (this
        # is called from every step). The wizard dialog is already open by the time this
        # runs; if neither is visible yet, return the step locator for the caller to poll.
        if self._is_visible_now(step):
            return step
        legacy = self.page.get_by_role("dialog", name=re.compile(r"^Install ")).first
        if self._is_visible_now(legacy):
            return legacy
        return step

    def add_mcp_server(self, name, token="", gateway_id=None, url=""):
        """Install an MCP server from the registry onto the gateway's Data Plane.

        Uses the in-gateway "Browse Registry" entry on the MCP Servers tab, which
        opens the InstallDialog with this gateway's DP pre-selected (shown as a
        chip). The credentials step appears only when the server declares install
        variables.

        Args:
            name: Short server key (mapped to a registry display name via
                MCP_SERVER_CATALOG; falls back to the raw name).
            token: Bearer token for the server's credential install variable.
            gateway_id: Gateway UUID; falls back to self.gateway_id.
            url: Accepted for backward-compatible call sites; unused (registry
                servers carry their own URL).
        """
        catalog_name = self.MCP_SERVER_CATALOG.get(name, name)

        self.goto_gateway(gateway_id, tab="servers")
        if not Util.check_dom_visibility(self.page, self.page.get_by_test_id("servers-page"), 2, 20):
            Util.exit_error("MCP Servers tab did not load", self.page, "servers_page.png")

        registry_btn = self._servers_registry_button()
        if not Util.check_dom_visibility(self.page, registry_btn, 1, 10):
            Util.exit_error("MCP Servers 'Browse Registry' button not found", self.page, "servers_registry_button.png")
        Util.click_button_until_enabled(self.page, registry_btn)
        # PCP-22376: the MCP Hub 1.20.0 Browse Registry dialog is a Fresco modal with NO
        # aria-label, so get_by_role("dialog", name="Browse MCP Registry") no longer
        # resolves it. Wait on the catalog cards themselves (present only once the dialog
        # is open) as the deterministic "dialog opened" signal.
        if not Util.check_dom_visibility(self.page, self.page.get_by_test_id("catalog-card").first, 2, 15):
            Util.exit_error("Browse MCP Registry dialog did not open (no catalog cards)",
                            self.page, "browse_registry.png")

        card = self.page.get_by_test_id("catalog-card").filter(has_text=catalog_name).first
        if not Util.check_dom_visibility(self.page, card, 2, 15):
            Util.warning_screenshot(f"MCP Server '{catalog_name}' not found in registry, skipping",
                                    self.page, "registry_card_missing.png")
            self._close_browse_registry()
            return

        # Already added on this DP? (Browse flow shows '(Added|Installed) on this DP'.)
        if self._card_installed_on_dp(card):
            self._skip_already_installed(catalog_name)
            return

        ColorLogger.info(f"Adding '{catalog_name}' from registry...")
        # PCP-22620: prefer the stable card-scoped `catalog-card-install` test-id
        # (PCP-22619 added it on CatalogCard via the Fresco alpha.87 passthrough), falling
        # back to the label 'Add'/'Install' by role+name only for older Hub builds. The
        # test-id MUST stay card-scoped: it is SHARED per card (many render on the registry
        # page), and card-scoping also disambiguates from the wizard's "Add to N DP" confirm
        # button (which portals to document.body, outside the card subtree). CatalogCard only
        # renders `catalog-card-install` on a NOT-added card, so the test-id path is inherently
        # safe against clicking an added card's action.
        install_btn = card.get_by_test_id("catalog-card-install")
        if not Util.check_dom_visibility(self.page, install_btn.first, 1, 3):
            # Older build: no test-id -> the Fresco Button labelled 'Add' (1.20.0) / 'Install'
            # (older). PCP-22376: match either as a WORD-BOUNDARY regex, never the bare string —
            # Playwright's name=<string> is a case-insensitive SUBSTRING match, so "Add"/"Install"
            # would also match "Uninstall"/"Added" and could resolve to a destructive action on an
            # already-added card. `\b(Add|Install)\b` is case-sensitive with word boundaries: it
            # excludes "Uninstall" (case) and "Added" (trailing \b fails before "ed"), yet still
            # tolerates a PrimeReact icon glyph folded into the accessible name (CLAUDE.md §6).
            install_btn = card.get_by_role("button", name=re.compile(r"\b(Add|Install)\b"))
        if not Util.check_dom_visibility(self.page, install_btn.first, 1, 5):
            # PCP-22376: an already-added card has NO 'Add'/'Install' button — it shows the
            # '(Added|Installed) on this DP' badge instead. That badge is driven by a separate
            # "which DPs is this server on" query that can render AFTER the card body, so the
            # pre-check above (short wait) can miss a late badge and fall through to here.
            # RE-CHECK the already-added state before failing; treat it as an idempotent
            # success skip rather than a hard error (the deploy really succeeded — the
            # assertion was just wrong). Only fail loud when neither the button NOR the badge
            # is present (a genuine registry/selector issue, never masked).
            if self._card_installed_on_dp(card):
                self._skip_already_installed(catalog_name)
                return
            Util.exit_error(f"Add button not found on registry card '{catalog_name}'",
                            self.page, "card_install_btn.png")
        install_btn.first.click()

        if not Util.check_dom_visibility(self.page, self._install_dialog(), 2, 15):
            Util.exit_error("Add server dialog did not open", self.page, "install_dialog.png")
        self._install_wizard(token)
        ColorLogger.success(f"Added MCP Server '{catalog_name}'")

    def _install_wizard(self, token=""):
        """Drive the Add/Install wizard: Select Gateway/DP -> [Credentials] -> Review & Add.

        PCP-22376: MCP Hub 1.20.0 is the gateway-centric 3-step flow — Step 1
        'Select Gateway' (target gateway pre-selected) -> Step 2 'Configure Credentials'
        -> Step 3 'Review & Add' (confirm 'Add to N DP'). Older builds titled it
        'Select Data Planes' / 'Review & Install' / 'Install on N DP' with an
        'install-preselected-dp' chip — both are handled (CLAUDE.md §6). The credentials
        step appears only when the server declares install variables.
        """
        # Step 1: target already selected (gateway pre-selected in the in-gateway flow).
        # Legacy builds show an 'install-preselected-dp' chip; 1.20.0 shows a
        # 'Select Gateway' step with the gateway pre-filled. Either way, just advance.
        if Util.check_dom_visibility(self.page, self.page.get_by_test_id("install-preselected-dp"), 1, 3):
            ColorLogger.info("Target Data Plane pre-selected (chip)")
        self._install_click_next()

        # Step 2: Configure Credentials (only for servers with install variables).
        if Util.check_dom_visibility(self.page, self.page.get_by_text("Configure Credentials").first, 1, 4):
            ColorLogger.info("Configuring credentials...")
            if token and self._fill_install_credential(token):
                ColorLogger.info("Credential configured")
            else:
                ColorLogger.warning("No token / credential field; continuing without credentials")
            self._install_click_next()

        # Step 3: Review & Add (older: Review & Install).
        Util.check_dom_visibility(
            self.page, self.page.get_by_text(re.compile(r"Review & (Add|Install)")).first, 1, 5)
        # Role+name fallback rationale (older Hub, before the PCP-22619 test-id):
        # the Fresco Button (PCP-19991 / commit 2dcbb2e) emitted NO data-testid — the documented
        # convention is select-by-role+name (react/src/shared/ui/Button.tsx). The confirm button
        # label is `Install on N DP(s)` (InstallDialog.tsx). Dialog-scoped because the Browse and
        # Install dialogs coexist; `Install on \d+ DP` is unique (card "Install" / footer
        # "Install more" don't contain it). The button regex is deliberately UNANCHORED: PrimeReact
        # renders the `pi pi-cloud-upload` icon as a `::before` glyph (PUA U+E944) that Playwright
        # folds into the button's ACCESSIBLE NAME *before* the label ("Install on 1 DP"), so a
        # leading ^ anchor never matches (verified live on alpha.113). `\b` keeps both "DP"/"DPs".
        # PCP-22620: prefer the stable dialog-scoped `install-submit` test-id (PCP-22619 added
        # it on the InstallDialog footer confirm), falling back to the label by role+name for
        # older Hub builds. Both stay dialog-scoped (Browse + Install dialogs coexist).
        # `.first` is safe even though InstallDialog.tsx emits `install-submit` on BOTH the real
        # confirm (`!deploying`) and the loading placeholder (`deploying`): they are mutually
        # exclusive ternary branches, so at this pre-submit point (deploying=false) only the real
        # confirm is in the DOM — verified against tp-mcp-hub InstallDialog.tsx (PCP-22619).
        install_dialog = self._install_dialog()
        install_confirm = install_dialog.get_by_test_id("install-submit").first
        if not Util.check_dom_visibility(self.page, install_confirm, 1, 3):
            install_confirm = install_dialog.get_by_role(
                "button", name=re.compile(r"(Add to|Install on)\s+\d+\s+DPs?\b")).first
        if not Util.check_dom_visibility(self.page, install_confirm, 1, 10):
            Util.exit_error("Add-to-DP confirm button not found", self.page, "install_confirm.png")
        install_confirm.click()
        self.page.wait_for_timeout(3000)
        self._install_finish()

    def _install_click_next(self):
        """Click the Add/Install wizard 'Next' button when enabled (if present)."""
        # Scope to the add/install dialog — it coexists in the DOM with the Browse dialog.
        install_dialog = self._install_dialog()
        # PCP-22620: prefer the `install-next` test-id (PCP-22619 added it on the InstallDialog
        # footer), falling back to the label 'Next' by role+name for older Hub builds.
        nxt = install_dialog.get_by_test_id("install-next").first
        if not Util.check_dom_visibility(self.page, nxt, 1, 3):
            nxt = install_dialog.get_by_role("button", name="Next").first
        if Util.check_dom_visibility(self.page, nxt, 1, 8):
            Util.click_button_until_enabled(self.page, nxt)
            self.page.wait_for_timeout(800)

    def _fill_install_credential(self, token):
        """Fill the credential/token field on the InstallDialog credentials step.

        The field id/label is the install variable NAME (dynamic per server,
        commonly 'token'). Try known names, then fall back to the first text or
        password input inside the dialog.
        """
        dialog = self._install_dialog()
        for var in ("token", "Token", "apiKey", "API_KEY", "api_key"):
            field = dialog.locator(f"#{var}").first
            if Util.check_dom_visibility(self.page, field, 1, 2):
                field.fill(token)
                ColorLogger.info(f"Filled credential '{var}'")
                return True
        # Fallback: first password or text input in the dialog body.
        field = dialog.locator("input[type='password'], input[type='text']").first
        if Util.check_dom_visibility(self.page, field, 1, 2):
            field.fill(token)
            ColorLogger.info("Filled credential (first input fallback)")
            return True
        return False

    def _install_finish(self):
        """Close the Add/Install wizard after it completes, if it shows a terminal button.

        Best-effort: click a 'Done'/'Close' button only if present, else no-op. Scope to the
        add/install dialog (coexists with Browse). Note the terminal button is CONDITIONAL: it
        renders only in the DP-embedded (Browse) flow AFTER deploy results land (InstallDialog.tsx
        `preSelectedDpId`/`deployResults` branch). In the common in-gateway path the wizard closes
        right after 'Add to N DP', so nothing terminal renders — hence the instantaneous probe
        below. PCP-22619 DID add `install-done`/`install-close` test-ids for the branch that does
        render one; this method prefers them and only no-ops when neither the test-id nor the
        label is present (i.e. no terminal button this run)."""
        # Instantaneous probe (NOT check_dom_visibility): on 1.20.0 the wizard auto-closes
        # after 'Add to N DP', so neither Done nor Close ever renders — a polling wait here
        # would burn ~10s (2 labels x 5s) per install for nothing. _install_wizard already
        # waited 3s after the confirm click, so any older-build Done/Close is present now.
        install_dialog = self._install_dialog()
        # PCP-22620: prefer the stable `install-done`/`install-close` test-ids (PCP-22619),
        # falling back to the visible label by role+name for older Hub builds.
        for test_id, label in (("install-done", "Done"), ("install-close", "Close")):
            btn = install_dialog.get_by_test_id(test_id).first
            if not self._is_visible_now(btn):
                btn = install_dialog.get_by_role("button", name=label).first
            if self._is_visible_now(btn):
                btn.click()
                self.page.wait_for_timeout(1500)
                return

    def _close_browse_registry(self):
        """Close the Browse MCP Registry dialog.

        PCP-22376: the MCP Hub 1.20.0 Browse dialog is a Fresco modal with no aria-label,
        so scope it as the role=dialog that CONTAINS the catalog cards (rather than by a
        title that no longer resolves); fall back to the legacy titled dialog. Escape is
        the robust final fallback if no close button is found.
        """
        dialog = self.page.get_by_role("dialog").filter(
            has=self.page.get_by_test_id("catalog-card")).first
        if not Util.check_dom_visibility(self.page, dialog, 1, 2):
            dialog = self.page.get_by_role("dialog", name="Browse MCP Registry")
        close = dialog.get_by_role("button", name=re.compile(r"^(Close|Cancel)$")).first
        if Util.check_dom_visibility(self.page, close, 1, 3):
            close.click()
        else:
            self.page.keyboard.press("Escape")
        self.page.wait_for_timeout(1000)

    # ------------------------------------------------------------------ #
    # Push to gateway + verify discovered tools
    # ------------------------------------------------------------------ #
    def _diff_confirm_push(self):
        """The Preview-Changes diff dialog's confirm action ('Push to Gateway').

        PCP-22620: resolve by the stable ``dp-action-diff-push`` test-id FIRST
        (PCP-22619 re-added it on the PushFlowDialog via the Fresco alpha.87 test-id
        passthrough / PLTUX-1299), falling back to the label 'Push to Gateway' by
        role+name only for older Hub builds that predate the test-id — so a label
        rename can never break the selector again (same test-id-first flip as the
        Register footer, PCP-22575; supersedes the earlier PCP-20368 role+name-first
        adaptation).

        The role+name fallback stays DIALOG-SCOPED: the button renders in the dialog
        FOOTER (.p-dialog-footer) — OUTSIDE the 'dp-action-diff-preview' content div —
        so it is scoped to the role=dialog that CONTAINS that content marker
        (filter has=dp-action-diff-preview, the same marker the caller just verified
        visible). That scope, not the regex, guarantees uniqueness and keeps the
        fallback from colliding with the gateway-detail 'Push Changes to Gateway'
        button. The regex is an UNANCHORED substring match because PrimeReact folds the
        'pi pi-cloud-upload' ::before glyph (PUA U+E944) into the accessible name
        before the label (verified live on alpha.113 — see _install_wizard), so a
        leading ^ / exact match never hits. Returns the test-id locator when neither
        variant is visible yet, so the caller re-guards with check_dom_visibility
        (CLAUDE.md §6 backward-compat)."""
        # The test-id path is page-scoped (not dialog-scoped): `dp-action-diff-push` is unique to
        # the single PushFlowDialog (tp-mcp-hub PushFlowDialog.tsx, PCP-22619), so `.first` cannot
        # mis-resolve. The role+name FALLBACK below stays dialog-scoped because a bare label could
        # collide with the gateway-detail 'Push Changes to Gateway' button.
        by_test_id = self.page.get_by_test_id("dp-action-diff-push").first
        if Util.check_dom_visibility(self.page, by_test_id, 1, 3):
            return by_test_id
        dialog = self.page.get_by_role("dialog").filter(
            has=self.page.get_by_test_id("dp-action-diff-preview"))
        by_role = dialog.get_by_role("button", name=re.compile(r"\bPush to Gateway\b")).first
        if Util.check_dom_visibility(self.page, by_role, 1, 2):
            return by_role
        return by_test_id

    def push_to_gateway(self, gateway_id=None, min_tools=1, *, dp_name=None):
        """Push configuration to the MCP Gateway and wait for sync + tool discovery.

        PCP-19765: pass ``dp_name`` so the deployed/online/refresh id-primary polls can
        recover a SUPERSEDED placeholder gateway id (re-keyed after async provision).

        A freshly deployed gateway reports status "unknown" / sync "pending" until
        the first push — pushing is what syncs the config and brings the gateway
        online and triggers tool discovery. So this only ensures the gateway is
        deployed (not online) before pushing; waiting for online here would
        deadlock.

        Returns:
            int: Number of tools discovered after sync (>= min_tools). HARD-fails via the
                /sync/refresh gate on an unreachable gateway or a persistent shortfall.
        """
        self.goto_gateway(gateway_id)
        # Pushing is the trigger that syncs config + discovers tools, so ensure the
        # gateway is deployed but do NOT wait for it to be online first. dp_name lets the
        # deployed-wait recover a superseded id (PCP-19765).
        self.wait_for_gateway_deployed(gateway_id, dp_name=dp_name)

        ColorLogger.info("Pushing to MCP Gateway...")
        # The newer MCP Hub renders the Push action as a Fresco Button 'Push Changes
        # to Gateway' (no testid), scoped to dp-detail-root; legacy dp-detail-sync
        # fallback (PCP-20336).
        push_btn = self._detail_push_button()
        if not Util.check_dom_visibility(self.page, push_btn, 2, 20):
            Util.exit_error("'Push to Gateway' button not found", self.page, "push_button.png")
        push_btn.click()
        self.page.wait_for_timeout(1000)

        # Preview Changes diff dialog (PrimeReact portal) -> confirm push.
        if Util.check_dom_visibility(self.page, self.page.get_by_test_id("dp-action-diff-preview"), 2, 15):
            ColorLogger.info("Preview Changes dialog shown, confirming push...")
            # Let the diff finish loading before pushing (the total line appears when
            # ready; absent on the no-changes "Everything is in sync" path, so the
            # boolean is intentionally not asserted).
            Util.check_dom_visibility(self.page, self.page.get_by_test_id("dp-action-diff-total"), 1, 10)
            # The Fresco diff-confirm button dropped its 'dp-action-diff-push' testid
            # (PCP-20368); select it by dialog-scoped role+name and re-guard like the
            # gateway-detail push (a bare .click() would silent-timeout on a future
            # drift, reproducing this very ticket).
            diff_push = self._diff_confirm_push()
            if not Util.check_dom_visibility(self.page, diff_push, 2, 20):
                Util.exit_error("Diff dialog 'Push to Gateway' confirm button not found",
                                self.page, "diff_confirm_push.png")
            diff_push.click()

        # Verify the push actually SYNCED and discovered tools via the deterministic Hub
        # API (PCP-20924) — NOT the transient sync dialogs the old code keyed on, which
        # mis-time on the gateway-centric UI (alpha.42 spinner spin; alpha.49 missed dialog
        # -> silent "0 tools" [SUCCESS]). Drive /sync/refresh ourselves and gate on its
        # discovered tool count.
        gid = gateway_id or self.gateway_id
        # PCP-21970: a freshly-deployed gateway pod (tp-mcp-gateway) takes a few
        # minutes to become Ready; until then its ingress /sync/refresh returns 502.
        # The push above is the trigger that brings the gateway online, so NOW wait
        # for it to report online via the deterministic Hub health-check API (which
        # serves status, not the gateway ingress, so it does NOT 502) BEFORE driving
        # /sync/refresh — otherwise the sync verification races the cold pod and
        # fails on transient 502s. Waiting here (AFTER the push) does not deadlock,
        # unlike waiting before the push (see this method's docstring).
        # PCP-19765: reassign gid from the online-wait's return + self.gateway_id, so a
        # supersede recovered mid-push flows into the refresh + soft sync-status reads
        # (the caller passed the placeholder id explicitly, so self-mutation alone wasn't
        # enough — the local gid must be updated too).
        gid = self._wait_for_gateway_online(gid, dp_name=dp_name) or gid
        count = self._refresh_and_count_tools(gid, min_tools=min_tools, dp_name=dp_name)
        gid = self.gateway_id or gid

        # Surface a PARTIAL push (some server defs failed to push OUT -> gateway row
        # sync_status='error') for visibility — non-gating, since tools WERE discovered.
        # /sync/refresh's response carries refresh-read errors, not the push's status, so
        # read the gateway row's syncStatus (gateways.ts rowToJson exposes it).
        # SOFT read: a transient gateways-API hiccup here must NOT abort an already-verified
        # deploy. _api_get_gateway hard-exits on any non-OK response, so it can't back a
        # non-gating visibility read (cross-review PCP-20924 Finding 1) — use the soft variant.
        if self._api_gateway_sync_status_soft(gid) == "error":
            Util.warning_screenshot(
                f"Sync reported partial/error (sync_status=error) — {count} tools discovered "
                "but some entities failed to push; report to the MCP Hub/DP team",
                self.page, "sync_partial.png")
        return count

    def _refresh_and_count_tools(self, gateway_id=None, min_tools=1, max_seconds=60, *, dp_name=None):
        """Drive tool discovery and verify it via the DETERMINISTIC Hub API (PCP-20924).

        On the gateway-centric UI the post-push flow is two backend steps: the Push click
        triggers ``POST /sync`` (pushes config OUT, sets sync_status) and the SyncResultDialog
        then polls ``POST /sync/refresh`` to DISCOVER tools from the registered MCP servers and
        populate ``cp_tools``. The old code keyed verification on the transient sync dialogs,
        which mis-time on this UI (alpha.42 spinner spin; alpha.49 missed dialog -> silent
        ``0 tools`` "[SUCCESS]"). Instead DRIVE ``/sync/refresh`` ourselves — the true analogue
        of ``_wait_for_gateway_online``'s POST health-check — and gate on its response, bounded
        so a stuck discovery fails fast instead of spinning to the Tekton ceiling.

        ``/sync/refresh`` returns ``{tools: number|null, gatewayStatus, fetchErrors?}``
        (``tools=null`` => the read FAILED, distinct from ``0`` = genuinely none; HTTP 502 =>
        gateway unreachable; 404 => DP not found). Discovery lag is expected — the gateway's
        listTools can lag and the backend documents re-refreshing to absorb it — so never
        hard-fail on the first ``0``/``null`` read, only after the bound. The ~60s bound is
        intentionally a little longer than the browser's 30s refresh window (we are the sole
        driver); exceeding it is the intended bounded fail-fast.

        Returns the discovered tool count (>= ``min_tools``). HARD-fails (``Util.exit_error``)
        on an unreachable/erroring gateway or a persistent shortfall.
        """
        gid = gateway_id or self.gateway_id
        if not gid:
            Util.exit_error("No gateway id available to verify sync/tool discovery",
                            self.page, "sync_refresh_noid.png")
        base = self._gateways_api_url or f"{self._hub_origin()}{self.HUB_API_BASE_PATH}/gateways"
        refresh_url = f"{base.rstrip('/')}/{gid}/sync/refresh"
        ColorLogger.info(f"Verifying sync + tool discovery (driving {refresh_url})...")
        interval = 5
        attempts = max(1, max_seconds // interval)
        consecutive_unreachable = 0
        last_tools = 0
        ever_read_ok = False
        tried_ids = set()  # PCP-19765: superseded ids already proven 404, for loop termination
        for i in range(attempts):
            resp = self.page.context.request.post(refresh_url)
            status = resp.status
            if status == 404:
                # PCP-19765: a 404 here can be a SUPERSEDED placeholder id (re-keyed after
                # async provision). Re-resolve the current gateway id for dp_name (strict +
                # soft) and retry with it; only abort if re-resolution yields no NEW id
                # (tried_ids guards the loop). The recovered id is published on
                # self.gateway_id so push_to_gateway's later soft reads use it.
                if dp_name:
                    tried_ids.add(gid)
                    new_id = self._reresolve_gateway_id(dp_name, tried_ids)
                    if new_id:
                        ColorLogger.info(
                            f"sync/refresh: gateway id '{gid}' superseded; re-resolved to "
                            f"'{new_id}' by DP '{dp_name}', retrying")
                        gid = new_id
                        self.gateway_id = new_id
                        refresh_url = f"{base.rstrip('/')}/{gid}/sync/refresh"
                        if i < attempts - 1:
                            self.page.wait_for_timeout(interval * 1000)
                        continue
                # Unlike _wait_for_gateway_online's 404 (which can fall back to a legacy UI
                # check), /sync/refresh has no legacy fallback, so any 404 here is fatal — a
                # wrong gateway id or an absent endpoint; report, don't mask.
                Util.exit_error(
                    f"sync/refresh returned 404 for gateway '{gid}' — the id is wrong or the "
                    "endpoint is absent; cannot verify tool discovery",
                    self.page, "sync_refresh_404.png")
                return 0
            if status in (400, 401, 403):
                Util.exit_error(
                    f"sync/refresh returned HTTP {status} for {refresh_url} — an auth/path/Hub "
                    "problem (not a slow gateway); cannot verify tool discovery",
                    self.page, "sync_refresh_auth.png")
                return 0
            if not resp.ok:
                # 5xx/502: the gateway is (transiently) unreachable — tolerate a few, then fail.
                consecutive_unreachable += 1
                if consecutive_unreachable >= 3:
                    Util.exit_error(
                        f"MCP Gateway unreachable — sync/refresh returned HTTP {status} 3x for "
                        f"{refresh_url}; report to the MCP Hub/DP team",
                        self.page, "sync_refresh_unreachable.png")
                    return 0
                ColorLogger.warning(f"sync/refresh HTTP {status} ({consecutive_unreachable}/3); retrying...")
                if i < attempts - 1:
                    self.page.wait_for_timeout(interval * 1000)
                continue
            consecutive_unreachable = 0
            try:
                body = resp.json() or {}
            except Exception:
                body = {}
            tools = body.get("tools")
            fetch_errors = body.get("fetchErrors")
            if tools is None:
                # The tools read FAILED (distinct from a genuine 0). Keep polling; may recover.
                ColorLogger.info(f"Tool discovery read not ready (tools=null)... ({i * interval}s)")
            else:
                ever_read_ok = True
                last_tools = tools
                if tools >= min_tools:
                    if fetch_errors:
                        Util.warning_screenshot(
                            f"Sync partial: discovered {tools} tools but {len(fetch_errors)} "
                            "refresh read(s) failed; report to the MCP Hub/DP team",
                            self.page, "sync_refresh_partial.png")
                    else:
                        ColorLogger.success(f"MCP Gateway synced: {tools} tools discovered (via /sync/refresh)")
                    return tools
                ColorLogger.info(
                    f"Discovered {tools} tools so far (< {min_tools}); discovery may be lagging... "
                    f"({i * interval}s)")
            if i < attempts - 1:
                self.page.wait_for_timeout(interval * 1000)
        # Bound exhausted without reaching min_tools. Distinguish "every read failed"
        # (tools=null throughout -> a Hub/gateway read error) from "discovery genuinely
        # returned too few" (at least one clean count came back) by whether ANY read succeeded,
        # so a mixed null/0 history is labelled by the real outcome, not just the last poll.
        if not ever_read_ok:
            Util.exit_error(
                f"MCP Gateway tool discovery read kept failing (tools=null) within {max_seconds}s — "
                "a Hub/gateway read error, not a healthy 0-tool result; report to the MCP Hub/DP team",
                self.page, "sync_refresh_readfail.png")
        else:
            Util.exit_error(
                f"MCP Gateway discovered {last_tools} tools (expected >= {min_tools}) within "
                f"{max_seconds}s — the installed MCP servers did not register their tools; report "
                "to the MCP Hub/DP team",
                self.page, "sync_refresh_zero_tools.png")
        return last_tools

    def _api_stats_tools_total_soft(self, gateway_id=None):
        """Gateway-wide tool count from the Hub stats API (GET .../gateways/{id}/stats ->
        ``{tools: {total, active}}``), the same source that backs the UI servers-stat-tools
        stat. SOFT: returns None on any error (never ``exit_error``) — this is a confirmatory
        read for ``verify_tools`` and must never be the thing that fails the deploy (the hard
        gate already ran in ``push_to_gateway``)."""
        gid = gateway_id or self.gateway_id
        base = self._gateways_api_url or f"{self._hub_origin()}{self.HUB_API_BASE_PATH}/gateways"
        url = f"{base.rstrip('/')}/{gid}/stats"
        try:
            resp = self.page.context.request.get(url)
            if not resp.ok:
                return None
            data = resp.json() or {}
        except Exception:
            return None
        tools = data.get("tools")
        if isinstance(tools, dict) and isinstance(tools.get("total"), int):
            return tools["total"]
        return None

    def _api_gateway_sync_status_soft(self, gateway_id=None):
        """Best-effort read of the gateway row's ``syncStatus`` (gateways.ts rowToJson) for the
        post-gate partial-push warning. SOFT: returns None on any error (never ``exit_error``) —
        discovery was already hard-gated in ``_refresh_and_count_tools``, so this visibility-only
        read must never abort a verified deploy (unlike ``_api_get_gateway``, which hard-exits on
        a non-OK response)."""
        gid = gateway_id or self.gateway_id
        base = self._gateways_api_url or f"{self._hub_origin()}{self.HUB_API_BASE_PATH}/gateways"
        try:
            resp = self.page.context.request.get(base)
            if not resp.ok:
                return None
            data = resp.json() or {}
        except Exception:
            return None
        rows = data if isinstance(data, list) else (
            data.get("gateways", []) if isinstance(data, dict) else [])
        row = next((g for g in rows if isinstance(g, dict) and g.get("id") == gid), None)
        return row.get("syncStatus") if row else None

    def verify_tools(self, gateway_id=None, min_tools=1):
        """Confirmatory tool-count check for the deploy success log.

        ``push_to_gateway`` already drove ``/sync/refresh`` and HARD-gated discovery
        (>= ``min_tools``), so this is a NON-aborting sanity read of the gateway-wide stat:
        it logs the count and WARNs on an unexpected shortfall, but never fails the deploy
        itself. Making it a second hard gate on the differently-defined ``/stats.tools.total``
        (which also counts Hub-managed REST tools, not just MCP-discovered) would only add a
        redundant false-RED surface (e.g. a transient stats error). The alpha.49 fix proper
        lives in ``push_to_gateway``.

        Returns:
            int: Gateway-wide tool count (0 if unreadable).
        """
        gid = gateway_id or self.gateway_id
        count = self._api_stats_tools_total_soft(gid)
        if count is None:
            Util.warning_screenshot(
                "verify_tools: could not read the gateway tool stat (confirmatory only; "
                "discovery was already gated in push_to_gateway)",
                self.page, "verify_tools_stat_unreadable.png")
            return 0
        ColorLogger.info(f"Gateway-wide tools discovered (Hub API stats): {count}")
        if count < min_tools:
            Util.warning_screenshot(
                f"verify_tools: gateway-wide tool count {count} < expected {min_tools} "
                "(confirmatory; push_to_gateway already gated discovery) — report if unexpected",
                self.page, "verify_tools_low.png")
        else:
            ColorLogger.success(f"Tools verified: {count} tools discovered")
        return count
