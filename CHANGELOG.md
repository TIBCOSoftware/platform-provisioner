# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Versions refer to Helm chart releases. See [tags](https://github.com/TIBCOSoftware/platform-provisioner/tags) for all releases.

## [Unreleased]

### Added
- Comprehensive test suite: 225+ BATS unit/integration tests, 65+ Helm unittest assertions
- CI pipeline (`test.yaml`): 8 parallel jobs — BATS, coverage (kcov), Helm unittest, ShellCheck, recipe smoke, diff-coverage, integration (generic-runner + helm-install)
- Security and fuzz test layers (`test_security.bats`, `test_fuzz.bats`)
- CUE schema contract tests for recipe validation
- Test documentation: `TESTING.md`, per-directory READMEs, `tests/AGENTS.md`
- Coverage enforcement: 90% threshold with branch coverage via kcov
- Diff-coverage reporting on pull requests with PR comments
- Makefile targets: `test`, `test-unit`, `test-integration`, `test-helm`, `lint`, `shellcheck`, `validate`
- E2E test recipe for retry functionality (`test-retry.yaml`)
- Coverage and test badges in README

### Changed
- [PCP-20335] Rename K8s MCP Server automation vocabulary to Infra MCP Server (recipe flags, env vars, Playwright page object/case, GUI form) to align with the CP web-UI/chart rename; adds GUI_TP_AUTO_ENABLE_INFRA_MCP_SERVER with backward-compatible fallback to GUI_TP_AUTO_ENABLE_K8S_MCP_SERVER.

### Fixed
- `common::replace_env_variables` not writing output file when `REPLACE_RECIPE != true`, causing downstream pipeline steps to read empty/stale recipe content
- o11y automation (`create_global_config`): wait for async-rendered wizard toggles before reading/clicking them, so a slow/cold CP render no longer misses `#traces-toggle-system-config` and falls into the manual-config branch that times out on the disabled `traces-proxy` toggle (Step 3), which left the global observability resource uncreated and the Data Plane not green (PCP-21866)
- mcp-hub automation (`deploy-mcp-hub`): match the Register-Gateway wizard Review-step submit button on MCP Hub 1.20.0-alpha.27/alpha.29, which relabelled it from `Register & Deploy` (ampersand) to `Register and Deploy` (the word "and") with no `register-review-submit` test-id, causing `#11 deploy-mcp-hub` to abort with `Register wizard forward button not found`; `_register_footer_button` now treats ` & ` and ` and ` as equivalent so either render matches (automation image 1.7.62) (PCP-22439)

## [common-dependency-1.0.19] — 2026-03-24

### Added
- Apache 2.0 license headers to all source files
- Community files: `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `SECURITY.md`
- GitHub issue templates (bug report, feature request) and PR template
- `CODEOWNERS` file
- `NOTICE` file with copyright attribution

### Changed
- Updated chart metadata with homepage, maintainers, and sources

## [common-dependency-1.0.18] — 2026-02-03

### Added
- `retryCount` and `retryDelay` support for pipeline tasks — tasks can now automatically retry on failure

## [helm-install-1.0.16] — 2026-02-03

### Added
- Retry support for helm-install pipeline tasks

## [generic-runner-1.0.9] — 2025-11-19

### Added
- OCI registry login support for private Helm chart repositories

## [platform-provisioner-ui-1.0.12] — 2026-03-24

### Changed
- Updated UI image references and chart metadata for open-source release

## [provisioner-config-local-1.15.8] — 2026-03-24

### Changed
- Updated recipe configurations for open-source readiness
- Removed `useSingleNamespace` from recipes

### Added
- Traefik gateway support for provisioner deployment
- nginx-gateway-fabric Helm release and cert setup
- OpenSearch configuration for observability stack
- AI agent chart values
- Langfuse integration for local deployments
- Hybrid connectivity option for CP core on-prem config

### Fixed
- Elastic configmaps idempotency
- Windows Docker volume mount paths
- Automation issues for BA index and permissions

[Unreleased]: https://github.com/TIBCOSoftware/platform-provisioner/compare/common-dependency-1.0.19...HEAD
[common-dependency-1.0.19]: https://github.com/TIBCOSoftware/platform-provisioner/compare/common-dependency-1.0.18...common-dependency-1.0.19
[common-dependency-1.0.18]: https://github.com/TIBCOSoftware/platform-provisioner/compare/helm-install-1.0.16...common-dependency-1.0.18
[helm-install-1.0.16]: https://github.com/TIBCOSoftware/platform-provisioner/compare/generic-runner-1.0.9...helm-install-1.0.16
[generic-runner-1.0.9]: https://github.com/TIBCOSoftware/platform-provisioner/compare/platform-provisioner-ui-1.0.12...generic-runner-1.0.9
[platform-provisioner-ui-1.0.12]: https://github.com/TIBCOSoftware/platform-provisioner/releases/tag/platform-provisioner-ui-1.0.12
[provisioner-config-local-1.15.8]: https://github.com/TIBCOSoftware/platform-provisioner/releases/tag/provisioner-config-local-1.15.8
