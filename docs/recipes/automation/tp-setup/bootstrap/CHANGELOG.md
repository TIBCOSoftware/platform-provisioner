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
