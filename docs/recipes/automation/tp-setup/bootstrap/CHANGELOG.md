## [1.7.47-auto-on-prem-jammy]
### Fixed
- [PCP-20336] `deploy-mcp-hub` gateway readiness now uses **deterministic Hub API signals** instead of brittle UI-flag polling (the contextforge/`mcpgatewayDeployed` flag could lag the running pod — BREAK A / PCP-20127). Complements PCP-20334 (which adapted the Register-wizard *selectors* to the alpha.142 redesign); this reworks the *readiness* layer PCP-20334 left on the old UI-flag path:
  - `wait_for_gateway_deployed` polls the gateways API (`GET .../gateways` → `mcpgatewayDeployed`) for the backend's own "deploy accepted" truth, then confirms the detail Push action is operable; if the API says deployed but the UI view never renders it fails loud (UI-flag lag, PCP-20127) instead of a blind 15-min poll. Resolves the row by id (deploy POST) or `dp_name`.
  - `_wait_for_gateway_online` forces a synchronous `POST .../gateways/{id}/health-check` and accepts the response's `status=='online'` (real probe); fails fast after 3 consecutive hard errors (auth/URL), single bounded UI fallback only when the endpoint is absent (404); a `Gateway not found` 404 (wrong id) fails loud.
  - new `_api_get_gateway` (id-primary; name-fallback requires `origin=='cp_dp'` and fails loud on >1 match — multi-gateway-per-dp safe) + `_detail_push_button` (role+name `Push Changes to Gateway`, legacy `dp-detail-sync` fallback) used by the deployed-wait and `push_to_gateway`.
  - `_wait_for_target_dp_online` restores the documented `origin=='cp_dp'` filter (zero live-behavior change — `/data-planes` carries no `origin`), fixing a pre-existing red regression test.
  - Extended `tests/test_po_mcp_hub_pick_target_dp.py` (34 unit tests green). Selector layer unchanged (owned by PCP-20334). Verified live on `ins-syan-70` (wip-poc-1-3ee6d26): the wizard drives end-to-end to the real provisioning POST; the gateway-pod deploy itself needs a full CP (the dev-k3s resource-create 403→502 is the orchestrator full-platform guard / PCP-20333, not the automation).

## [1.7.46-auto-on-prem-jammy]
### Fixed
- [PCP-20320] App build automation failed on a **fresh capability** (runtime version not provisioned) across flogo, bwce, and bw5ce.
  - **flogo** (`po_dp_flogo.py`): scoped the "Provision Flogo in another tab" locator to `.flogo-version-form-container .version-field-container .provision-link` so Step 2 (App Build Configurations) no longer hits a Playwright strict-mode violation when both the Flogo runtime version and a connector still need provisioning (two `.provision-link` elements).
  - **bwce/bw5ce** (`po_dp_bwce.py`): on a fresh capability the BW5/BW6 (Containers) runtime version is not provisioned, so the "Create New App Build & Deploy" button is absent and `bwce_app_build_and_deploy` exited. Added `bwce_provision_version()` — clicks the per-capability provision entry (`provision_plugin_button_selector`; bw5ce: in-appPackages `#buildComp-btn-importAppBuild`, bwce: `#capPackagesBackToDP`), walks the shared 2-step wizard (`#provisionPluginUpdt-footBtn-nextStep` → wait `#btnNavigationToIntegrationDetailsbtnRight`), returns to the capability page; `bwce_app_build_and_deploy` calls it when the build button isn't visible, then polls for the button to render.
  - **endpoint dialog** (`po_dp_bwce.py:bwce_app_config`): the Set Endpoint Visibility dialog only auto-closed on a success toast; with no toast (endpoint already Public → no change) it stayed open and intercepted the next tab click (Environmental Controls) → Timeout. Now surfaces a real error toast (no masking) then closes the lingering dialog before navigating on.
  Verified end-to-end on live on-prem (`k8s-auto-dp1`): flogo, bwce (fresh → auto-provisions version), and bw5ce all run to completion (build → deploy → endpoint Public → trace).
## [1.7.45-auto-on-prem-jammy]
### Fixed
- [PCP-20334] `deploy-mcp-hub` automation adapted to the MCP Hub 1.17.0-alpha.142 Register Gateway wizard (PrimeNG redesign). The wizard dropped the per-action test-ids and moved nav/action buttons into a shared `.rg-foot-actions` footer, so `_register_continue` timed out on the missing `register-continue` test-id. Backward-compatible selector updates in `po_mcp_hub.py` (old test-id tried first, then the redesign fallback): `_register_continue` / `_register_review_and_deploy` / `register-finish` → `.rg-foot-actions` footer buttons ("Continue" / "Register & Deploy" / "Finish") via a new `_register_footer_button` helper; `_register_fill_identity` → `register-name`; `_register_select_or_create_resource` → "Add new" trigger + dialog-footer primary "Add" submit (matched by dialog-scoped CSS, since Chrome folds the pi-plus icon glyph into the button's accessible name). Selectors that were unchanged (`register-dp-option`, `dp-action-resource-table`/`-row`, `dp-action-add-resource`, `#resource-name`, `#field-*`) are retained. Verified by driving the full redesigned wizard live on 1.17.0-alpha.142. Note: full E2E is currently blocked downstream by PCP-20333 (MCP Hub backend returns 403→502 on ingress-resource create), which is a separate product bug.

## [1.7.44-auto-on-prem-jammy]
### Fixed
- [PCP-20250] `deploy-flogo` (and any DP→Global Observability link flow) no longer fails on 1.19.0-alpha with a fatal `nav-bar-pointer` timeout and a false "Linked … failed". Black-box verification on live 1.19.0-alpha showed the selectors the ticket blamed are all intact (`.nav-bar-pointer` "Data Planes", `.use-global-resource .o11y-btn`, the "Link Data plane to this resource ?" dialog, and `.o11y-panel-actions .global-resource-name`); the real cause was fragile waits. Two robustness fixes (no selector changes):
  - `po_global.py:goto_left_navbar` now polls with `Util.check_dom_visibility` (logged, screenshot-on-failure) instead of a silent `wait_for(state="visible")`, so a slow left-nav re-render right after a heavy DP-config operation fails with diagnostics instead of an opaque `Timeout 30000ms exceeded`.
  - `po_dataplane.py:switch_to_global_config` no longer reloads the page when the legacy `.switch-to-global` selector is absent (the reload was racing the freshly re-rendering Angular o11y panel and skipping the link). Pre-link checks now poll without reloading; the post-link confirmation polls up to 30s before declaring failure. Validated end-to-end against live 1.19.0-alpha (unlink → re-link).

## [1.7.43-auto-on-prem-jammy]
### Fixed
- [PCP-20157] `springboot_provision_connector` passed `app_name=None` to `is_app_created`, causing a Playwright strict-mode violation in `deploy-sb` (false PARTIAL pipeline result). Root cause: unlike `springboot_app_build_and_deploy`, the connector method did not default the name, so `is_app_created` ran `locator(..., has_text=None)` which applies no filter and resolves to every app row — `is_visible()` then throws once >=2 apps exist (e.g. the o11y profile provisions BWCE+BW5CE+Flogo before SB). Two fixes: (1) `springboot_provision_connector` now defaults `app_name = app_name or ENV.SPRINGBOOT_APP_NAME` (root cause); (2) `is_app_created` defensively returns `False` on a falsy `app_name` without touching the locator, so any future `None` caller neither throws nor mis-judges. Added regression unit tests (`tests/test_po_app_name_guard.py`).

## [1.7.42-auto-on-prem-jammy]
### Added
- [PCP-19768] No-tibtunnel DP reachability, end-to-end. With hybrid connectivity disabled there is no tibtunnel — the CP reaches the DP via `tp-dp-proxy` → the registered Reachable DP URL. The automation now makes that URL actually reachable after DP/BMDP create (gated by `GUI_TP_AUTO_DP_MANAGE_REACHABILITY`, default `true`):
  - **Option A (default)** — creates a controller-adaptive `cpdpproxy-public` ingress in the DP namespace pointing at `cpdpproxy:80`, host `https://dp-<dpName>.<cpDnsDomain>`. The flavor (Ingress for `traefik`/`nginx`/`haProxy`/`kong`, OpenShift `Route`, or Gateway-API `HTTPRoute`) is selected from the same `TP_AUTO_INGRESS_OBJECT` / `TP_AUTO_INGRESS_CONTROLLER`(`_CLASS_NAME`) / `TP_AUTO_GATEWAY_*` settings the automation already feeds the CP "Add Ingress/Route" wizard, mirroring the capability charts (`dp-flogo-app`/`dp-bwce-app`).
  - **Option B (opt-in, `GUI_TP_AUTO_DP_APPLY_NETPOL_LABELS=true`)** — instead labels the `cpdpproxy` (DP side, `networking.platform.tibco.com/cluster-ingress`) and `tp-dp-proxy` (CP side, `…/cluster-egress`) deployments + pod templates so `tp-dp-proxy` can reach the `cpdpproxy` ClusterIP directly, and uses the private `http://cpdpproxy.<ns>.svc.cluster.local` URL.
  - New ENV (and `GUI_…` recipe inputs): `TP_AUTO_DP_MANAGE_REACHABILITY`, `TP_AUTO_DP_APPLY_NETPOL_LABELS`, `TP_AUTO_DP_PROXY_SERVICE_NAME` (default `cpdpproxy`), `TP_AUTO_DP_PROXY_SERVICE_PORT` (default `80`). `TP_AUTO_REACHABLE_DP_URL`/`TP_AUTO_REACHABLE_BMDP_URL` default to the public host **only** for no-tibtunnel Option A (hybrid OFF and not applying netpol labels); when hybrid is ON (default) or Option B is selected they keep the in-cluster `cpdpproxy` svc URL, preserving the pre-existing hybrid-ON registration (incl. the BMDP Reachable-URL field). An explicit value still overrides.

### Fixed
- [PCP-19768] `k8s_wait_tunnel_connected()` (`po_dataplane.py`) is now guarded on `TP_AUTO_ENABLE_HYBRID_CONNECTIVITY`. With hybrid disabled there is no tibtunnel, so the unconditional wait for `.tunnel-status svg.green` previously hard-exited after 180s and killed both the DP-create and BMDP-create flows. The automation now confirms the DP is created, waits for the card-level DP readiness icon (`.data-plane-status svg.green`, polling 20s/300s with page refresh to match `k8s_wait_bmdp_ready`) instead of the tunnel status, and records `tunnelConnected: false`. Fixes both `k8s_create_dataplane` and `k8s_create_bmdp` callers.

> **No-tibtunnel run — flags to set.** The **automation** hybrid flag is `GUI_TP_AUTO_ENABLE_HYBRID_CONNECTIVITY` (→ `TP_AUTO_ENABLE_HYBRID_CONNECTIVITY`). A full run also needs the **CP** deployed with hybrid off (`GUI_CP_ENABLE_HYBRID_CONNECTIVITY=false`) — the two flags are independent. Non-hybrid DP registration is GUI/Playwright-only (CLI mode has no Reachable-URL field), so also set `GUI_TP_AUTO_USE_CLI=false`. The product-side gateway fix is PCP-19767.

## [1.7.41-auto-on-prem-jammy]
### Fixed
- [PCP-20127] `deploy-mcp-hub` automation no longer aborts on a not-yet-online target Data Plane. The Register Gateway wizard fetches its target-DP list once at page mount (`useGateways`: `staleTime:0`, no `refetchInterval`) and never refreshes mid-wizard, so a DP still coming online (~2-3 min after creation) rendered as a disabled row that `_register_pick_target_dp` hard-errored on. `deploy_mcp_gateway` now waits for the target `cp_dp` DP to report `status == 'online'` — via the same Hub `/gateways` API the wizard reads (cookie-auth-shared `page.context.request`, real URL captured off the wire with an `apiBasePath` fallback, fail-fast on API errors) — BEFORE entering the wizard, so its mount-time fetch shows the row enabled. The in-wizard check stays a one-shot postcondition guard (re-querying could never see a frozen disabled row flip) with a clearer timing-skew error. New `tests/test_po_mcp_hub_pick_target_dp.py` + `tests/conftest.py` (neutralizes `utils.env` import-time cluster autodetect for hermetic unit tests).

## [1.7.40-auto-on-prem-jammy]
### Added
- [PCP-20053] Observability dashboard automation: `page_o11y.py` now creates per-capability dashboards and bulk-adds cards — resets the Default dashboard, creates `logs_dashboard`, and creates one dashboard per installed capability (Spring Boot split into two dashboards to respect the 15-card limit); uninstalled capabilities are skipped with a log line, and older CP (no "Add dashboard" button) falls back to the legacy widget flow. New `page_object/po_o11y.py` helpers (`get_catalog_menu_labels`, `create_dashboard`, `is_dashboard_exists`, `goto_dashboard`, `add_widgets`, `has_add_dashboard_button`, `is_catalog_card_available`) plus fixes to `goto_left_navbar_o11y` (gate on `.dashboard-actions-row`) and `selector_dialog_left_menu` for the new `tibco-header` / PrimeNG 18 build. Card/dashboard definitions in `o11y_dashboard_config.py` with unit tests; gated by the existing `TP_AUTO_ENABLE_O11Y_WIDGET` toggle (default false) with a "Setup Observability dashboards and cards" UI checkbox.

## [1.7.39-auto-on-prem-jammy]
### Added
- [PCP-19592] End-to-end SpringBoot (SB) capability automation: new `po_dp_springboot.py` page object and `case/k8s_create_and_start_springboot_app.py` covering provision, app build, deploy, endpoint config, and start; SB env/ingress/Gateway API defaults in `env.py`; GUI SB cases and `.jar` uploads (`index.html`/`index.js`/`server.py`); `deploy-sb` task in `tp-automation-o11y.yaml`; and a GitHub Release download fallback in `helper.py` (`gh` CLI preferred, curl fallback) for fetching SB JARs. Review fixes: curl downloads use `-f` so a 404/401 fails fast instead of writing a corrupt JAR that passes the `os.path.isfile()` check, and corrected a misleading success log on the endpoint-config failure branch.

## [1.7.38-auto-on-prem-jammy]
### Changed
- [PCP-19573] CLI `create-activation-file-resource` now uploads the activation license file via the CP license REST API instead of creating an activation server (casri) resource.
- [PCP-19573] Replaced the activation server info to activation file in `Deploy BW5 domain` automation case, and update the related steps.

## [1.7.37-auto-on-prem-jammy]
### Added
- [PCP-19413] API-based BMDP registration: new `api_object` clients for BW5/BW6 domain, agent, and EMS-server registration; `page_cli.py` BMDP config now goes through REST instead of the browser, plus an API-based product-permission grant for the CLI BMDP path.
### Fixed
- [PCP-19413] Flogo/BWCE/BW5CE app-endpoint exposure under Gateway API ingress.

## [1.7.36-auto-on-prem-jammy]
### Added
- [PCP-19413] Browser-free API init path (`TP_AUTO_USE_CLI=true`): admin bootstrap, tenant OAuth, O11Y, and license upload all via REST — no Playwright.
- [PCP-19413] Gateway API support across CLI (resource, capability, CT-DP, endpoint test).
### Changed
- [PCP-19413] Rewrote `OllyApi` on flat `/resources/instances/{type}`; supports global + DP-scoped creation with instance-ID capture.
- [PCP-19413] Bumped tibcop CLI to `1.9.0-alpha.2046`.
- [PCP-19765] Rewrote MCP Hub automation (`po_mcp_hub.py`) for the gateway-centric React UI (PCP-19623). Deploy now drives the **Register Gateway** wizard → "Deploy to a TIBCO Data Plane" (auto-provision, `POST /api/mcp-hub/gateways/{dpUuid}/deploy`); servers are installed via the in-gateway **Browse Registry** InstallDialog (DP pre-selected); push uses the `dp-detail-sync` → Preview Changes → Sync Result flow; tools are verified in the per-server **Tools details** drawer (`role=treeitem`). Selectors moved to React `data-testid`/ARIA (verified against tp-mcp-hub @ `aff65c8`).
  - `goto_dataplane()` (MCP Hub) replaced by `goto_gateway(gateway_id, tab=…)`; the gateway UUID is captured from the deploy POST response.
  - Removed the Angular/PrimeNG selectors and the legacy add-server / `_has_registry_ui` paths (the gateway-centric React UI fully replaces the Angular MCP Hub UI).
  - Corrected the `deploy_mcp_hub()` MCP wrapper docstring (it runs the UI automation case, not a helm install).
  - Requires the MCP Hub backend in CP mode (`MCP_HUB_MODE=cp`) so the "Deploy to a TIBCO Data Plane" card renders.

## [1.7.35-auto-on-prem-jammy]
### Changed
- [PCP-19589] Raise `wait_for_dataplane_green` default timeout from 300s to 480s — tolerates slower hybrid-proxy tunnel establishment without triggering a full `cli-full-automation` task restart (which wastes ~5 min on re-login + re-OAuth-token).

## [1.7.34-auto-on-prem-jammy]
### Added
- [PCP-18499] Add gateway support to 3rd party, CP, DP, BMDP, automation.

## [1.7.33-auto-on-prem-jammy]
### Added
- [PCP-18499] Add Kubernetes MCP Server capability provisioning automation

## [1.7.31-auto-on-prem-jammy]
### Fixed
- [PCP-19290] Use `check_dom_visibility(10, 60, True)` for create-dp modal wait — polls with page refresh instead of silent Playwright timeout
- [PCP-19290] Added Escape key fallback when ingress error Cancel button selector doesn't match — prevents unclosed modal from blocking navigation
- [PCP-19284] Fixed automation for CP 1.18 UI changes: login flow (generateIAT=True), ingress/route resource toggle, EULA checkbox step
### Added
- Added wait pattern guideline to CLAUDE.md: prefer `check_dom_visibility` over `wait_for(timeout=N)`

## [1.7.29-auto-on-prem-jammy]
### Fixed
- [PCP-19216] Restored email activation retry in `active_user_in_mail()` — replaced single `is_visible()` check with `Util.check_dom_visibility()` polling (10s interval, 60s max, with page refresh)

## [1.7.28-auto-on-prem-jammy]
### Fixed
- [PCP-19158] Fixed Playwright strict mode violation on combined CSS selectors (storage, ingress toggle, EULA) by adding `.first`
- [PCP-19158] Simplified ingress section expand check — replaced SVG `xlink:href` inspection with button visibility check
- [PCP-19158] Fixed cached locator pattern in Flogo, BWCE, and TibcoHub ingress table selection — store selector strings, re-query on each use
- [PCP-19216] Removed email server DB hack (`_configure_email_server_via_kubectl`) — superseded by PCP-19150 no-email path
### Added
- Added Playwright Automation Principles to CLAUDE.md (user simulator philosophy, selector abstraction, strict mode, locator caching, backward compatibility)

## [1.7.27-auto-on-prem-jammy]
### Updated
- Updated MCP Hub automation for CP 1.17 5-step gateway wizard (added Advanced and Gateway Configuration steps with backward compatibility)
- Updated MCP Hub sidebar navigation from tabs to links with tab fallback for older CP versions
- Fixed tools count extraction for new sidebar badge format

## [1.7.26-auto-on-prem-jammy]
### Added
- [PCP-19150] Added no-email user provisioning path (now default). Set `TP_AUTO_IS_PROVISION_USER_WITHOUT_EMAIL=false` to fall back to the legacy maildev-based flow. Admin uses chart-bootstrapped `adminInitialPassword` + first-login reset; regular DP user is created via `POST /platform-console/api/v1/subscriptions` with `initialPassword` + first-login reset. `login` and `login_admin_user` now transparently handle the forced first-login password reset.

## [1.7.25-auto-on-prem-jammy]
### Fixed
- [PCP-19158] Fixed MCP Hub `verify_tools()` tab selector: CP 1.17.0 renamed "Tools" tab to "MCP Tools", updated regex
- [PCP-19158] Fixed `create-bmdp` spinner blocking button click: wait for `.pl-primary-spinner` to hide, detect disabled button with tooltip
- [PCP-19158] Fixed BMDP EMS success alert strict mode violation: added `.first` to avoid resolving to 2 elements
### Changed
- [PCP-19158] Added wait for DP Resources page storage/ingress sections to render after DP creation
- [PCP-19158] Reduced outer `deploy-subscription` retry loop default from 10 to 3

## [1.7.24-auto-on-prem-jammy]
### Updated
- [PCP-18595] Updated bw5 images to support TP 1.16+
- updated bw5 recipe to support logs and metrics configuration
## [1.7.23-auto-on-prem-jammy]
### Fixed
- [PCP-18853] Updated MCP Hub automation for CP 1.17.0: 3-step provisioning wizard, create storage class if missing, new Add MCP Server dialog selectors, Preview Changes confirmation dialog

## [1.7.22-auto-on-prem-jammy]
### Fixed
- [PCP-18746] Added handling for 'Preview / Customize Recipe' step during Flogo capability provisioning

## [1.7.21-auto-on-prem-jammy]
### Added
- [PCP-18427] Integrated MCP Hub automation into headless pipeline (deploy-mcp-hub task in tp-automation-o11y recipe)
- Added `GUI_TP_AI_ENABLE_MCP_HUB` toggle to automation recipe and Provisioner UI config

## [1.7.20-auto-on-prem-jammy]
### Added
- Added non-hybrid connectivity to bmdp in automation.
## [1.7.19-auto-on-prem-jammy]
### Added
- [PCP-18427] Added MCP Hub Playwright automation: deploy MCP Gateway, add MCP Server with Bearer Token auth, push to gateway with tool discovery, and verify tools
- Added "Deploy MCP Gateway" option in Automation Hub dropdown
- Added `make automation-deploy-gcp` target for deploying code to remote GCP automation pod
- Documented remote GCP instance connection workflow (connect-ins.sh) in CLAUDE.md

## [1.7.18-auto-on-prem-jammy]
### Added
- Now supported to disable hybrid connectivity in automation. By default, the automation will enable hybrid connectivity for TP with tibtunnel. User can set `GUI_CP_ENABLE_HYBRID_CONNECTIVITY` to false to disable it if needed.
## [1.7.17-auto-on-prem-jammy]
### Added
- Updated /recipes/k8s/on-prem/scripts/headless/tp-install-on-prem.sh to support private repository
### Fixed
- Exit cli task when DP is RED for over 300s.
- Fix one cli task issue in automation GUI option
## [1.7.16-auto-on-prem-jammy]
### Added
- Support self-signed certificate. By default, the automation will use self-signed certificate for TP  with domain `dev.localhost`.
- All users(TIBCO internal and customers) can use /recipes/k8s/on-prem/scripts/headless/tp-install-on-prem.sh to install TP.
## [1.7.15-auto-on-prem-jammy]
### Fixed
- Handle domain card layout changes for CP versions after 1.16: added fallback click on domain card when "Go to Domain" footer link is not visible
- Guard BW6 app status checks with visibility detection to avoid failures when the application card layout is absent
### Added
- Added retry logic to DP automation recipe at task level. Each task will retry up to 10 times with 10 seconds interval. 

## [1.7.14-auto-on-prem-jammy]
### Fixed
- Use regex to match both "Currently linked to the" and "View License" text variants when checking activation file status, as the UI text may vary across CP versions
- Replace direct `is_visible()` with `check_dom_visibility` retry pattern for the activation file Add button to improve reliability
- Standardize DOM visibility check timeouts for activation file upload flow

## [1.7.13-auto-on-prem-jammy]
### Added
- [PCP-16940] Added support for "Use CLI" option in Platform Automation Hub. When this option is enabled, the automation will run CLI commands instead of GUI cases.

## [1.7.12-auto-on-prem-jammy]
### Fixed
- [PCP-16998] Business Activities Query Service/Exporter now use the same index name as other BA services (`{dp_title}-ba-log-index`)
- Improved `grant_permission()` to handle both single and multiple permission checkbox scenarios. Added logic to detect and click "All current and future" labels when multiple selectors are present.
- Added debug logging for BMDP machine host name input
- Fixed log message from "Input Ingress Description" to "Input Ingress Resource Name"

## [1.7.11-auto-on-prem-jammy]
### Added
- Add a method can get the storage class and ingress class from the cluster
### Changed
- In advance mode, exposed storage class and ingress class and FQDN with register control tower dataplane
### Certified
- Certified CLI cases with SaaS CP. All cases are working with SaaS CP.

## [1.7.10-auto-on-prem-jammy]
### Added
- Support for Dataplane listing/registration/unregistration via tibcop CLI
- Support for Resources, Capabilities(EMS not included) add/list/delete via tibcop CLI
- Support for apps(Flogo/BWCE/BW5CE) listing/creation/deletion via tibcop CLI

- Add AI skill ui-ux-pro-max to update UI style
- Added "About" tab with platform feature overview
- Added custom SVG icon for page and favicon

### Changed
- Renamed project to "Platform Automation Hub"
- Rewrote DESCRIPTION.md with comprehensive platform overview
- Removed TIBCO branding from user-facing text

### Fixed
- Fixed tab button and link text color visibility
- Fixed select dropdown duplicate arrow icons

## [1.7.4-auto-on-prem-jammy]
### Added
- Support for config Business Activities in o11y configuration automation.
- Support for In-Product activation


## [1.7.3-auto-on-prem-jammy]
### Fixed
- Add new version of tibcop

## [1.7.2-auto-on-prem-jammy]
### Fixed
- Fixed provision user issue when select "State" in dropdown list.
- When "Create New App Build & Deploy" app button is not visible, exit automation with error message.

## [1.7.1-auto-on-prem-jammy]
### Added
- Added tibcop binary

## [1.6.19-auto-on-prem-jammy]
### Fixed
- Fixed automation issue BWCE and BW5CE support for load 'Preview/Customize Recipe page' during provisioning.

## [1.6.18-auto-on-prem-jammy]
### Fixed
- Fixed automation issue after O11y upgrade to PrimeNG 18

## [1.6.17-auto-on-prem-jammy]
### Fixed
- Fixed automation issue after BW/Flogo app use new Fresco header

## [1.6.16-auto-on-prem-jammy]
### Added
- Added an API `/cp_api` for calling CP API directly from Platform Automation Hub.
  - api_path: The CP API path, e.g. `/cp/v1/dataplanes`
  - api_method: HTTP method, e.g. GET, POST, DELETE
  - api_data: Request body for POST/PUT methods
- Will prefilled activation Server fields when select automation case: "Deploy BW5 domain"
### Fixed
- Fix config BMDP app issue: BMDP app required to set up user permission before accessing the app.
- The automation support for o11y new dataplane dropdown, after it changes to PrimeNG auto complete component.
- Fixed issue if checked "Is Using O11y System Config"

## [1.6.15-auto-on-prem-jammy]
### Fixed
- Automaton Support for CP WebServer Fresco header change

## [1.6.13-auto-on-prem-jammy]
### Changed
- Change version from update time to semantic versioning format.
- Update toolkit script `bump_version.sh` to support semantic versioning format update.
  * change `version` in `charts/provisioner-config-local/Chart.yaml` file
  * change `1.x.x-auto-on-prem-jammy` in `docs/recipes/automation/tp-setup/bootstrap/version.txt` file
  * search `-auto-on-prem-jammy` in the specified file, then update it.

## [12/08/2025 22:30]
### Added
- Support for config MCP Server in settings page before creating OAuth Token
- Print more helm chart information in "Show Current Environment" automation case
  
## [12/05/2025 19:12]
### Fixed
- The automation support for 1.13 release
  - Fix issue after BMDP creation UI changed

## [12/02/2025 22:35]
### Fixed
- The automation support for 1.13 release 
  - Fix issue after activation URL UI changed
  - Fix issue after BMDP BW5 domain UI changed

## [11/18/2025 13:06]
### Fixed
- Windows Docker and Git Bash need double slash for mounting local folder into pod.
- Browser launch failure due to --single-process issue in windows VDI environment.

## [10/14/2025 14:58]
### Fixed
- Fix bug: ems and tibcohub do not deploy by default
- Remove deploy Pussar by default

## [10/07/2025 13:51]
### Fixed
- If the button "Use Global Activation URL" is disabled, skip config it. 

## [10/04/2025 22:17]
### Added
- Support for creating OAuth Token and saving it to kubernetes secret.
### Fixed
- Link k8s dataplane activation url to global.

## [09/27/2025 21:30]
### Fixed
- Fixed deploy flogo issue after flogo UI is changed
- Do not cache UI for Platform Automation Hub index.html file
- Change "Automation Case" dropdown list will reset input file field and filename field to default value
### Changed
- Will switch to global dataplane configuration, remove config dataplane level o11y
- Rename "flogo-auto-1" to "rest-flogo-1" for flogo app name in automation script
- Rename "bwce-tt" to "rest-bwce-1" for bwce app name in automation script

## [09/22/2025 10:06]
### Fixed
- Fixed config dataplane's activation url issue.

## [09/19/2025 14:30]
### Fixed
- Select "Force Run Automation" in Platform Automation Hub
  - will automatically switch dataplane to use global activation url.
  - will automatically switch dataplane to use global dataplane configuration.

## [09/18/2025 21:55]
### Fixed
- Improve the execution speed of the automated setup script after CP is successfully installed. Detect in advance whether the task to be executed has been completed to avoid repeated execution.
  - Avoid redeploying Flogo/BWCE/BW5CE, if the Flogo/BWCE/BW5CE app is already running successfully, skip it
  - Avoid recreating tibcohub/ems, if tibcohub/ems has already been created successfully, skip it
  - Avoid recreating BMDP, if BMDP has already been created successfully, skip it
    - If the BW5/BW6 app of BMDP is already running successfully, skip it
    - If the EMSServer of BMDP is already connected successfully, skip it
  - Avoid reconfiguring o11y card, if the o11y card has already been configured successfully, skip it

## [09/09/2025 21:14]
### Added
- Add new automation case in Platform Automation Hub
  - For K8s Dataplane
    - Support for provision BW5(BW5CE) Capability
    - Support for create and start BW5(BW5CE), include upload app file
    - Support for delete BW5(BW5CE) app
  - For Control Tower Dataplane(BMDP)
    - Support for creating/deleting Control Tower Dataplane(BMDP)
    - Support for config Control Tower Dataplane(BMDP) o11y
    - Support for deploy BW5 domain(Include rvdm, emsdm, bw6dm, emsserver)
    - Support for register/delete BW5 domain
- Support for provision BW5CE capability in K8s Dataplane if bwce is installed and cp version >=1.10
- Support for do not start BWCE app and BW5CE app by default after created in local environment

## [08/15/2025 11:40]
### Fixed
- Change admin user automation activation steps after activation step changed in CP
- Fix provision bwce automation issue after bwce UI is changed.
- Fixed config flogo issue after flogo UI(set Endpoint visibility to Public dialog) is changed
- Change name "BW5 Adapters" to BW5 for bmdp
- Update capability status to "Running" in report YAML if it is running

### Added
- Add reset password steps if admin user did not receive active email
- Support for config activation url, if TP_ACTIVATION_URL is not set, skip config Activation url.
- Add a compatibility handling after BWCE changed to BW6 (Containers) in version 1.10 (#127)
- Add ems/tibcohub capability check, skip it if it has not been installed.
- Add Pussar capability check, it has been removed since CP 1.10

## [06/16/2025 23:41]
### Fixed
- Fix the issue that the Set Endpoint visibility dialog cannot be found when setting Endpoint visibility for bwce
- Fix the issue that clicking the provision button does not respond when provisioning flogo/bwce

## [06/13/2025 16:39]
### Fixed
- Fix the issue that the endpoint visibility cannot be set correctly when setting the endpoint visibility of the bw app
- Fix the issue that the dom xpath is incorrect when judging whether the swagger UI title is displayed

## [06/12/2025 11:57]
### Added
- Add tooltips for CP URL and CLI Token input field in Platform Automation Hub
- Remove everything after the domain in the CP URL input field

## [06/11/2025 13:59]
### Added
- Add CLI tab for Platform Automation Hub (Only need to provide CP URL and Token)
- Platform Automation Hub supports for listing/creating/deleting Dataplane via CLI

## [06/03/2025 14:01]

### Fixed
- Reduce the pre-configured o11y widget by one, and configure a maximum of only 15
- When the "Add widget button" is disabled, the addition will no longer continue

## [05/16/2025 22:45]

### Fixed
- Fix issue for Automation Case "Create new subscription with User Email"


## [05/15/2025 16:54]

### Added
- Platform Automation Hub supports running multiple tasks in parallel or stopping tasks in multi browser window tab.

### Changed
- Do not show "Run in Browser" option if Platform Automation Hub is not started from the source code

### Fixed
- Fix the o11y configuration item that has been added when configuring o11y, and wait for the data to be displayed before configuring
- Fix the problem that the page loads too slowly when switching o11y to global, and refresh the page
