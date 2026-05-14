## [1.7.32-auto-on-prem-jammy]
### Added
- [PCP-19289] Lower flogoprovisioner pod resources right after FLOGO capability provisioning. 

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
