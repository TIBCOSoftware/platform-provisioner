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
        return self._open_gateway_from_home(dp_name) is not None

    def is_gateway_online(self):
        """Whether the gateway detail header shows the gateway as online.

        Reads the React status text (.gw-health-text); the old Angular
        span.p-tag-label 'online' selector is gone.
        """
        health = self.page.locator(".gw-health-text")
        if Util.check_dom_visibility(self.page, health.first, 1, 3):
            return "online" in (health.first.inner_text() or "").lower()
        return False

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
            return next((g for g in rows if isinstance(g, dict) and g.get("id") == gid), None)
        if dp_name:
            matches = [g for g in rows if isinstance(g, dict)
                       and g.get("name") == dp_name and g.get("origin", "cp_dp") == "cp_dp"]
            if len(matches) > 1:
                Util.exit_error(
                    f"Multiple gateways named '{dp_name}' on the same DP — cannot disambiguate "
                    "without a gateway id (multi-gateway-per-dp). Resolve the id from the deploy "
                    "response before polling status.",
                    self.page, "gateway_api_ambiguous.png")
                return None
            return matches[0] if matches else None
        return None

    def _detail_push_button(self):
        """The gateway-detail Push action, scoped to dp-detail-root. The newer MCP
        Hub renders it as a Fresco Button 'Push Changes to Gateway' (no testid);
        the prior variant used data-testid 'dp-detail-sync'. Returns a single-match
        locator preferring the new variant, falling back to the legacy testid
        (CLAUDE.md §6, PCP-20336)."""
        new = self.page.get_by_test_id("dp-detail-root").get_by_role(
            "button", name=re.compile(r"Push Changes to Gateway", re.I)).first
        if Util.check_dom_visibility(self.page, new, 1, 2):
            return new
        legacy = self.page.get_by_test_id("dp-detail-sync").first
        if Util.check_dom_visibility(self.page, legacy, 1, 1):
            return legacy
        return new

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
                rid = row.get("id") or gid
                if rid:
                    self.goto_gateway(rid)
                if Util.check_dom_visibility(self.page, self._detail_push_button(), 2, 30):
                    ColorLogger.success("MCP Gateway is deployed (API mcpgatewayDeployed + detail view operable)")
                    return
                Util.exit_error(
                    "Gateway reports deployed via the Hub API (mcpgatewayDeployed) but the detail "
                    "view never rendered the Push action — the UI deployed flag is lagging the "
                    "running pod (PCP-20127); report to the MCP Hub team",
                    self.page, "mcp_gateway_ui_lag.png")
                return
            ColorLogger.info(f"Gateway not deployed yet per Hub API (pod starting)... ({i * 30}s)")
            self.page.wait_for_timeout(30000)
        Util.exit_error(
            f"MCP Gateway did not report deployed via the Hub API within {max_minutes} minutes — "
            "the deploy may have failed; report to the MCP Hub/DP team",
            self.page, "mcp_gateway_not_deployed.png")

    def _wait_for_gateway_online(self, gateway_id=None, max_minutes=15):
        """Wait for the MCP Gateway to come ONLINE via the DETERMINISTIC Hub API
        (PCP-20336): force a fresh health-check probe and accept the response's
        ``status == 'online'``. POST /gateways/{id}/health-check runs a real HTTP
        GET to the gateway /health and returns the live status synchronously, so
        this does not depend on a lagging UI flag. Keeps a loud 15-min timeout for
        a genuinely-offline gateway (a real DP/pod issue to report, not mask).
        Falls back to the legacy UI status only when the endpoint is absent.
        """
        gid = gateway_id or self.gateway_id
        if not gid:
            Util.exit_error("No gateway id available to poll for online status",
                            self.page, "gateway_online_noid.png")
        base = self._gateways_api_url or f"{self._hub_origin()}{self.HUB_API_BASE_PATH}/gateways"
        health_url = f"{base.rstrip('/')}/{gid}/health-check"
        ColorLogger.info(f"Waiting for MCP Gateway to come online (via {health_url})...")
        consecutive_errors = 0
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
                    Util.exit_error(
                        f"Health-check reports gateway '{gid}' not found — the resolved gateway id "
                        "is wrong; cannot verify online status",
                        self.page, "gateway_not_found.png")
                    return
                # Legacy variant without the health-check endpoint: switch to a single
                # bounded UI poll (do NOT re-run the deployed-wait every iteration — that
                # would be quadratic in wall-clock).
                ColorLogger.info("health-check endpoint absent (404); using the legacy UI online check")
                return self._wait_for_gateway_online_ui(gid, max_minutes)
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
                    return
                ColorLogger.info(f"Gateway not online yet (status={status or 'unknown'})... ({i * 30}s)")
            if i < max_minutes * 2 - 1:
                self.page.wait_for_timeout(30000)
        Util.exit_error(
            f"MCP Gateway did not come online within {max_minutes} minutes "
            "(health-check status != online) — report to the MCP Hub/DP team if the pod is stuck",
            self.page, "mcp_gateway_not_online.png")

    def _wait_for_gateway_online_ui(self, gid, max_minutes=15):
        """LEGACY UI online poll — used ONLY when the health-check endpoint returns
        404 (an older variant). One deployed-wait, then a bounded reload+status poll
        (NOT nested per-iteration; avoids the quadratic wall-clock). PCP-20336."""
        self.wait_for_gateway_deployed(gid)
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

        Wizard sub-steps (auto-provision): deployment -> identity -> target-dp ->
        network -> deploy-mode -> advanced -> gateway-config -> review -> verify.
        The deploy POST fires on entering the Verify step; the Verify animation is
        a client-side timer and is NOT a reliable success signal, so this method
        captures the POST response to resolve the gateway UUID.

        Args:
            dp_name: Target Data Plane name (the bare cp_dp DP to deploy onto).
            skip_online_wait: If True, do not wait for the gateway to come online
                (servers are installed and pushed before the gateway is ready).

        Returns:
            str: The gateway UUID (DataPlane.id), or "" if it could not be resolved.
        """
        # Idempotency: reuse an existing deployed gateway for this DP if present.
        existing_id = self._open_gateway_from_home(dp_name)
        if existing_id:
            ColorLogger.info(f"MCP Gateway already deployed for '{dp_name}' (id={existing_id})")
            self.gateway_id = existing_id
            if not skip_online_wait:
                self._wait_for_gateway_online(existing_id)
            return existing_id

        # PCP-20127: the Register wizard fetches its target-DP list once at page
        # mount and never refreshes it, so the DP must already be online before we
        # enter the wizard (independent of skip_online_wait, which governs the
        # separate post-deploy gateway-online wait).
        self._wait_for_target_dp_online(dp_name)

        ColorLogger.info(f"Deploying MCP Gateway for '{dp_name}' via Register Gateway wizard...")
        self.page.goto(self._hub_url("/gateways/register"), wait_until="domcontentloaded")

        # Step 1: Deployment mode — "Deploy to a TIBCO Data Plane" (CP-mode only).
        if not Util.check_dom_visibility(self.page, self.page.get_by_test_id("register-mode-provision-auto"), 2, 20):
            Util.exit_error(
                "'Deploy to a TIBCO Data Plane' card not found. The MCP Hub backend must be in "
                "CP mode (MCP_HUB_MODE=cp) for auto-provision; without it the wizard only offers "
                "Manual Helm / Connect-a-running-gateway. Verify the webserver deployment env.",
                self.page, "register_no_cp_mode.png")
        self.page.get_by_test_id("register-mode-provision-auto").click()
        self._register_continue()

        # Step 2: Identity — gateway name (required to advance).
        self._register_fill_identity(dp_name)
        self._register_continue()

        # Step 3: Target Data Plane — pick the bare cp_dp DP.
        self._register_pick_target_dp(dp_name)
        self._register_continue()

        # Step 4: Network Access — select or create the ingress controller.
        self._register_select_or_create_resource(
            instance_name=f"mcp-{dp_name}",
            fill_fields_fn=lambda: self._fill_ingress_resource_fields(dp_name),
        )
        self._register_continue()

        # Step 5: Deployment Mode — Lite is the default; select a storage class
        # (Lite mode gating requires a storage instance).
        self._register_select_or_create_resource(
            instance_name=ENV.TP_AUTO_STORAGE_CLASS,
            fill_fields_fn=lambda: self._fill_storage_resource_fields(ENV.TP_AUTO_STORAGE_CLASS),
        )
        self._register_continue()

        # Step 6: Advanced — defaults are valid.
        self._register_continue()

        # Step 7: Gateway Configuration — defaults are valid.
        self._register_continue()

        # Step 8: Review & Deploy -> Step 9: Verify (deploy POST fires here).
        gateway_id = self._register_review_and_deploy(dp_name)
        self.gateway_id = gateway_id

        if not skip_online_wait:
            self._wait_for_gateway_online(gateway_id)
        return gateway_id

    def _register_footer_button(self, label, exact=True):
        """Locator for a Register-wizard footer action button by visible label.

        MCP Hub 1.17.0-alpha.142+ (PrimeNG wizard redesign) dropped the per-action
        test-ids (register-continue / register-review-submit / register-finish) and
        renders the primary nav button in the persistent '.rg-foot-actions' footer as
        a plain PrimeNG button labelled per step (Continue / Register & Deploy /
        Finish). Filtering by text avoids matching the sibling 'Back' button.

        `exact=True` anchors the match to the full button text (avoids a future
        footer label that merely *contains* the word colliding); `exact=False`
        prefix-matches, for labels whose suffix may vary across versions
        (e.g. "Finish" vs "Finish & open gateway"). The button's icon is an inline
        <svg> with no text, so matching on text content is reliable here.
        """
        anchor = r"\s*$" if exact else ""
        pattern = re.compile(r"^\s*" + re.escape(label) + anchor)
        return self.page.locator(".rg-foot-actions button").filter(has_text=pattern)

    def _register_continue(self):
        """Click the Register wizard 'Continue' button once it is enabled."""
        # Newer MCP Hub dropped the 'register-continue' test-id; fall back to the
        # '.rg-foot-actions' footer button labelled "Continue".
        btn = self.page.get_by_test_id("register-continue")
        if not Util.check_dom_visibility(self.page, btn, 1, 3):
            btn = self._register_footer_button("Continue")
            if not Util.check_dom_visibility(self.page, btn, 1, 15):
                Util.exit_error("Register wizard 'Continue' button not found", self.page, "register_continue.png")
        Util.click_button_until_enabled(self.page, btn)
        self.page.wait_for_timeout(800)

    def _register_fill_identity(self, dp_name):
        """Fill the gateway name on the Identity step."""
        # Newer MCP Hub gives the name input a 'register-name' test-id (PrimeNG
        # inputtext); older builds used a plain '.rg-step-page input.text-input'.
        if Util.check_dom_visibility(self.page, self.page.get_by_test_id("register-name"), 1, 10):
            self.page.get_by_test_id("register-name").fill(dp_name)
        else:
            selector = ".rg-step-page input.text-input"
            if not Util.check_dom_visibility(self.page, self.page.locator(selector).first, 1, 5):
                selector = "input.text-input"
            self.page.locator(selector).first.fill(dp_name)
        ColorLogger.info(f"Gateway name: {dp_name}")

    def _register_pick_target_dp(self, dp_name):
        """Pick the target Data Plane row on the Target Data Plane step.

        Rows share the data-testid 'register-dp-option' (filter by DP name). Only
        cp_dp DPs are listed; degraded (status != online) DPs are disabled.
        """
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

    def _register_select_or_create_resource(self, instance_name, fill_fields_fn):
        """Select an existing resource-instance row by name, or create one via the
        Add-Resource dialog.

        Shared by the Network Access (ingress) and Deployment Mode (storage) steps
        — both render the same ResourceTable (data-testid dp-action-resource-*).
        On successful create the new instance is auto-selected.
        """
        Util.check_dom_visibility(self.page, self.page.get_by_test_id("dp-action-resource-table").first, 2, 20)

        row = self.page.get_by_test_id("dp-action-resource-row").filter(has_text=instance_name)
        if Util.check_dom_visibility(self.page, row.first, 1, 5):
            row.first.click()
            ColorLogger.info(f"Selected existing resource: {instance_name}")
            return

        ColorLogger.info(f"Resource '{instance_name}' not found, creating it...")
        # Newer MCP Hub dropped the 'dp-action-resource-add' test-id; the trigger is
        # now a plain 'Add new' PrimeNG button.
        add_btn = self.page.get_by_test_id("dp-action-resource-add")
        if not Util.check_dom_visibility(self.page, add_btn.first, 1, 3):
            add_btn = self.page.get_by_role("button", name="Add new")
        add_btn.first.click()
        if not Util.check_dom_visibility(self.page, self.page.get_by_test_id("dp-action-add-resource"), 2, 15):
            Util.exit_error("Add-Resource dialog did not open", self.page, "add_resource_dialog.png")

        self.page.locator("#resource-name").fill(instance_name)
        fill_fields_fn()
        # Newer MCP Hub dropped the 'dp-action-add-resource-submit' test-id; the submit
        # control is now the primary PrimeNG button in the Add-Resource dialog footer
        # (a pi-plus icon + "Add" label). Match it by dialog-scoped CSS rather than
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
        # Newer MCP Hub dropped the 'register-review-submit' test-id; the deploy
        # action is the '.rg-foot-actions' footer button labelled "Register & Deploy".
        if not Util.check_dom_visibility(self.page, self.page.get_by_test_id("register-review-submit"), 2, 10) \
                and not Util.check_dom_visibility(self.page, self._register_footer_button("Register & Deploy"), 1, 10):
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
                    submit = self.page.get_by_test_id("register-review-submit")
                    if not Util.check_dom_visibility(self.page, submit, 1, 2):
                        submit = self._register_footer_button("Register & Deploy")
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

        # Verify step: wait for 'Finish & open gateway' to enable (client-side
        # timer), then finish — navigates to the gateway detail page.
        # Newer MCP Hub dropped the 'register-finish' test-id; fall back to the
        # '.rg-foot-actions' footer button labelled "Finish".
        finish = self.page.get_by_test_id("register-finish")
        if not Util.check_dom_visibility(self.page, finish, 1, 2):
            # prefix match — the verify-step label may be "Finish" or "Finish & open gateway"
            finish = self._register_footer_button("Finish", exact=False)
        if Util.check_dom_visibility(self.page, finish, 2, 30):
            Util.click_button_until_enabled(self.page, finish)
            self.page.wait_for_timeout(2000)

        if not gateway_id:
            match = re.search(r"/gateways/([^/?#]+)", self.page.url)
            if match and match.group(1) != "register":
                gateway_id = match.group(1)
        if not gateway_id:
            # Deploy POST/URL did not yield an id (e.g. response missed). Resolve
            # the gateway from the home list by DP name as a last resort.
            ColorLogger.warning("Gateway id not resolved from response/URL; resolving from home list...")
            gateway_id = self._open_gateway_from_home(dp_name) or ""
        if not gateway_id:
            Util.warning_screenshot("Could not resolve the gateway id after deploy",
                                    self.page, "deploy_no_gateway_id.png")
        ColorLogger.success(f"MCP Gateway deploy submitted (gateway id: {gateway_id or 'unknown'})")
        return gateway_id

    # ------------------------------------------------------------------ #
    # Install MCP servers from the registry (in-gateway Browse Registry)
    # ------------------------------------------------------------------ #
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

        self.page.get_by_test_id("servers-registry-button").click()
        if not Util.check_dom_visibility(self.page, self.page.get_by_role("dialog", name="Browse MCP Registry"), 2, 15):
            Util.exit_error("Browse MCP Registry dialog did not open", self.page, "browse_registry.png")

        card = self.page.get_by_test_id("catalog-card").filter(has_text=catalog_name).first
        if not Util.check_dom_visibility(self.page, card, 2, 15):
            Util.warning_screenshot(f"MCP Server '{catalog_name}' not found in registry, skipping",
                                    self.page, "registry_card_missing.png")
            self._close_browse_registry()
            return

        # Already installed on this DP? (Browse flow shows 'Installed on this DP'.)
        if Util.check_dom_visibility(self.page, card.get_by_text("Installed on this DP"), 1, 2):
            ColorLogger.info(f"'{catalog_name}' already installed on this DP, skipping")
            self._close_browse_registry()
            return

        ColorLogger.info(f"Installing '{catalog_name}' from registry...")
        # The card "Install" is a Fresco Button (role+name); the legacy .reg-install-btn CSS
        # class was removed in the UX migration (commit 2dcbb2e), so the old fallback is dead.
        # card-scoping disambiguates from the install dialog's "Install on N DP" button (which
        # portals to document.body, outside the card subtree).
        install_btn = card.get_by_role("button", name="Install")
        if not Util.check_dom_visibility(self.page, install_btn.first, 1, 5):
            Util.exit_error(f"Install button not found on registry card '{catalog_name}'",
                            self.page, "card_install_btn.png")
        install_btn.first.click()

        if not Util.check_dom_visibility(self.page, self.page.get_by_role("dialog", name=re.compile(r"^Install ")), 2, 15):
            Util.exit_error("Install dialog did not open", self.page, "install_dialog.png")
        self._install_wizard(token)
        ColorLogger.success(f"Installed MCP Server '{catalog_name}'")

    def _install_wizard(self, token=""):
        """Drive the InstallDialog: Select DP(s) -> [Credentials] -> Review & Install.

        The DP step is a pre-selected chip in the Browse flow; the Credentials step
        is present only when the server declares install variables.
        """
        # Step 1: Select Data Planes (pre-selected chip in the Browse flow).
        if Util.check_dom_visibility(self.page, self.page.get_by_test_id("install-preselected-dp"), 1, 5):
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

        # Step 3: Review & Install.
        Util.check_dom_visibility(self.page, self.page.get_by_text("Review & Install").first, 1, 5)
        # The Fresco Button (PCP-19991 / commit 2dcbb2e) emits NO data-testid — the documented
        # convention is select-by-role+name (react/src/shared/ui/Button.tsx). The confirm button
        # label is `Install on N DP(s)` (InstallDialog.tsx). Dialog-scoped because the Browse and
        # Install dialogs coexist; `Install on \d+ DP` is unique (card "Install" / footer
        # "Install more" don't contain it). The button regex is deliberately UNANCHORED: PrimeReact
        # renders the `pi pi-cloud-upload` icon as a `::before` glyph (PUA U+E944) that Playwright
        # folds into the button's ACCESSIBLE NAME *before* the label ("Install on 1 DP"), so a
        # leading ^ anchor never matches (verified live on alpha.113). `\b` keeps both "DP"/"DPs".
        install_dialog = self.page.get_by_role("dialog", name=re.compile(r"^Install "))
        install_confirm = install_dialog.get_by_role("button", name=re.compile(r"Install on \d+ DPs?\b"))
        if not Util.check_dom_visibility(self.page, install_confirm, 1, 10):
            Util.exit_error("Install confirm button not found", self.page, "install_confirm.png")
        install_confirm.click()
        self.page.wait_for_timeout(3000)
        self._install_finish()

    def _install_click_next(self):
        """Click the InstallDialog 'Next' button when enabled (if present)."""
        # Scope to the install dialog — it coexists in the DOM with the Browse dialog.
        install_dialog = self.page.get_by_role("dialog", name=re.compile(r"^Install "))
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
        dialog = self.page.get_by_role("dialog", name=re.compile(r"^Install "))
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
        """Close the InstallDialog after install (Browse flow: 'Done'; standalone: 'Close')."""
        # Scope to the install dialog — it coexists in the DOM with the Browse dialog.
        install_dialog = self.page.get_by_role("dialog", name=re.compile(r"^Install "))
        for label in ("Done", "Close"):
            btn = install_dialog.get_by_role("button", name=label).first
            if Util.check_dom_visibility(self.page, btn, 1, 5):
                btn.click()
                self.page.wait_for_timeout(1500)
                return

    def _close_browse_registry(self):
        """Close the Browse MCP Registry dialog."""
        dialog = self.page.get_by_role("dialog", name="Browse MCP Registry")
        close = dialog.get_by_role("button", name="Close").first
        if Util.check_dom_visibility(self.page, close, 1, 3):
            close.click()
        else:
            self.page.keyboard.press("Escape")
        self.page.wait_for_timeout(1000)

    # ------------------------------------------------------------------ #
    # Push to gateway + verify discovered tools
    # ------------------------------------------------------------------ #
    def _diff_confirm_push(self):
        """The Preview-Changes diff dialog's confirm action.

        The newer MCP Hub renders it as a Fresco Button 'Push to Gateway' (no
        testid) in the dialog FOOTER (.p-dialog-footer) — OUTSIDE the
        'dp-action-diff-preview' content div — so it cannot be scoped on that content
        testid. It is instead scoped to the role=dialog that CONTAINS that content
        marker (filter has=dp-action-diff-preview — the same marker the caller just
        verified visible; the footer button is a sibling of the content div within
        the same dialog). Tying the scope to the proven content marker, rather than a
        rewordable header string, mirrors the install_confirm has= idiom and is
        robust even if another titled dialog ever coexists. The legacy
        'dp-action-diff-push' testid is the backward-compat fallback for an older
        pre-Fresco hub (PCP-20368; same Fresco-drops-data-testid drift as PCP-20334 /
        PCP-20336).

        The button regex is intentionally an UNANCHORED substring match: PrimeReact
        renders the 'pi pi-cloud-upload' icon as a ::before glyph (PUA U+E944) that
        Playwright folds into the accessible name BEFORE the label (verified live on
        alpha.113 — see _install_wizard), so a leading ^ / exact match never hits;
        the dialog scope (not the regex) guarantees uniqueness. Returns an unusable
        locator when neither variant is visible — the caller re-guards with
        check_dom_visibility (CLAUDE.md §6)."""
        dialog = self.page.get_by_role("dialog").filter(
            has=self.page.get_by_test_id("dp-action-diff-preview"))
        new = dialog.get_by_role("button", name=re.compile(r"\bPush to Gateway\b")).first
        if Util.check_dom_visibility(self.page, new, 1, 3):
            return new
        legacy = self.page.get_by_test_id("dp-action-diff-push").first
        if Util.check_dom_visibility(self.page, legacy, 1, 1):
            return legacy
        return new

    def push_to_gateway(self, gateway_id=None):
        """Push configuration to the MCP Gateway and wait for sync + tool discovery.

        A freshly deployed gateway reports status "unknown" / sync "pending" until
        the first push — pushing is what syncs the config and brings the gateway
        online and triggers tool discovery. So this only ensures the gateway is
        deployed (not online) before pushing; waiting for online here would
        deadlock.

        Returns:
            int: Number of tools discovered after sync (0 if none / not reported).
        """
        self.goto_gateway(gateway_id)
        # Pushing is the trigger that syncs config + discovers tools, so ensure the
        # gateway is deployed but do NOT wait for it to be online first.
        self.wait_for_gateway_deployed(gateway_id)

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

        # Sync result dialog.
        if not Util.check_dom_visibility(self.page, self.page.get_by_test_id("dp-action-sync-result"), 2, 60):
            Util.warning_screenshot("Sync Result dialog not detected", self.page, "sync_result_missing.png")
            return 0
        result = self.page.get_by_test_id("dp-action-sync-result")

        # Tool discovery polling phase ('Discovering tools...').
        if Util.check_dom_visibility(self.page, self.page.get_by_test_id("dp-action-sync-refreshing"), 2, 10):
            ColorLogger.info("Tool discovery in progress...")
            self.page.get_by_test_id("dp-action-sync-refreshing").wait_for(state="hidden", timeout=60000)

        # Discovered tool count: text "{N} tools from {M} gateway(s)".
        tools_count = 0
        discovered = result.get_by_text(re.compile(r"\d+ tools from"))
        if Util.check_dom_visibility(self.page, discovered.first, 2, 10):
            text = discovered.first.text_content() or ""
            match = re.search(r"(\d+) tools from", text)
            tools_count = int(match.group(1)) if match else 0

        if Util.check_dom_visibility(self.page, result.get_by_text("Partial Failure").first, 1, 2):
            ColorLogger.warning(f"Sync partial failure, {tools_count} tools discovered")
        elif Util.check_dom_visibility(self.page, result.get_by_text("Synced").first, 1, 2):
            ColorLogger.success(f"Sync success, {tools_count} tools discovered")
        else:
            ColorLogger.info(f"Sync completed, {tools_count} tools discovered")

        close = result.get_by_role("button", name="Close").first
        if Util.check_dom_visibility(self.page, close, 1, 3):
            close.click()
            result.wait_for(state="hidden", timeout=10000)
        self.page.wait_for_timeout(1500)
        return tools_count

    def get_tools_count(self, gateway_id=None):
        """Read the gateway-wide 'Tools discovered' stat on the MCP Servers tab."""
        self.goto_gateway(gateway_id, tab="servers")
        Util.check_dom_visibility(self.page, self.page.get_by_test_id("servers-page"), 2, 20)
        stat = self.page.get_by_test_id("servers-stat-tools").locator(".stat-val")
        if Util.check_dom_visibility(self.page, stat, 1, 10):
            text = stat.first.text_content() or ""
            match = re.search(r"\d+", text)
            return int(match.group()) if match else 0
        return 0

    def verify_tools(self, gateway_id=None):
        """Verify discovered tools.

        Reads the gateway-wide 'Tools discovered' stat and confirms the per-server
        Tools-details drawer shows discovered tools (role=treeitem rows), which is
        the surface that replaced the retired standalone MCP Tools tab.

        Returns:
            int: Tool count (gateway-wide stat, falling back to the first server's
                drawer count).
        """
        gid = gateway_id or self.gateway_id
        total = self.get_tools_count(gid)
        ColorLogger.info(f"Gateway-wide tools discovered: {total}")

        drawer_count = 0
        card = self.page.get_by_test_id("servers-card").first
        if Util.check_dom_visibility(self.page, card, 2, 15):
            cta = card.get_by_role("button", name="Tools details").first
            if Util.check_dom_visibility(self.page, cta, 1, 5):
                cta.click()
            else:
                card.locator(".vs-row-cta").first.click()

            if Util.check_dom_visibility(self.page, self.page.get_by_test_id("tools-drawer"), 2, 20):
                drawer = self.page.get_by_test_id("tools-drawer")
                if Util.check_dom_visibility(self.page, self.page.get_by_test_id("tools-drawer-empty"), 1, 3):
                    drawer_count = 0
                else:
                    drawer_count = drawer.get_by_role("treeitem").count()
                ColorLogger.info(f"First server tools in drawer: {drawer_count}")
                close = self.page.get_by_test_id("tools-drawer-close")
                if Util.check_dom_visibility(self.page, close, 1, 3):
                    close.click()
                    self.page.wait_for_timeout(1000)

        count = total if total > 0 else drawer_count
        if count > 0:
            ColorLogger.success(f"Tools verified: {count} tools discovered")
        else:
            ColorLogger.warning("No tools discovered")
        return count
