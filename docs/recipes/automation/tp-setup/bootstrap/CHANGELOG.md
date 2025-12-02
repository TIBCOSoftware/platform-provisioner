## [12/02/2025 09:28]
### Fixed
- The automation support for 1.13 release 
  - Fix issue after activation URL UI changed

## [11/18/2025 13:06]
### Fixed
- Windows Docker + Git Bash need double slash for mounting local folder into pod.
- Browser launch failure due to --single-process issue in windows VDI environment.

## [10/14/2025 14:58]
### Fixed
- Fix bug: ems and tibcohub do not deployed by default
- Remove deploy Pussar by default

## [10/07/2025 13:51]
### Fixed
- If button "Use Global Activation URL" is disabled, skip config it. 

## [10/04/2025 22:17]
### Added
- Support for creating OAuth Token and saving it to kubernetes secret.
### Fixed
- Link k8s dataplane activation url to global.

## [09/27/2025 21:30]
### Fixed
- Fixed deploy flogo issue after flogo UI is changed
- Do not cache UI for One-Click Setup CP index.html file
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
- In select "Force Run Automation" in One-Click Setup UI
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
- Add new automation case in One-Click Setup CP UI
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
- Update capability status to "Running" in report yaml if it is running

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
- Add tooltips for CP URL and CLI Token input field in One-Click Setup CP UI
- Remove everything after the domain in the CP URL input field

## [06/11/2025 13:59]
### Added
- Add CLI tab for One-Click Setup CP UI (Only need to provide CP URL and Token)
- One-Click Setup CP UI supports for listing/creating/deleting Dataplane via CLI

## [06/03/2025 14:01]

### Fixed
- Reduce the pre-configured o11y widget by one, and configure a maximum of only 15
- When the "Add widget button" is disabled, the addition will no longer continue

## [05/16/2025 22:45]

### Fixed
- Fix issue for Automation Case "Create new subscription with User Email"


## [05/15/2025 16:54]

### Added
- One-Click UI supports running multiple tasks in parallel or stopping tasks in multi browser window tab.

### Changed
- Do not show "Run in Browser" option if One-Click UI is not started from the source code

### Fixed
- Fix the o11y configuration item that has been added when configuring o11y, and wait for the data to be displayed before configuring
- Fix the problem that the page loads too slowly when switching o11y to global, and refresh the page
