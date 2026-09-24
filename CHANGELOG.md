# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Versions refer to Helm chart releases. See [tags](https://github.com/TIBCOSoftware/platform-provisioner/tags) for all releases.

## [Unreleased]

### Added
- [PCP-23863] Control Plane database engine selector for the on-prem pipelines: the tp-base and CP recipes/forms take a `postgres | oracle` choice (GUI_TP_DB_ENGINE / GUI_CP_DB_ENGINE) that drives the Oracle release toggle and the CP `CP_DB_*` connection values plus the chart-side engine global. `postgres` remains the default; the only change to a default install is the new engine global set to `postgres` and a `validate-db-engine` preTask that rejects an unrecognised engine name. Oracle schema management requires a `tibco-cp-base` whose `core-cp-scripts` image carries an Oracle client and whose schema Job emits `ORACLE_HOST`/`ORACLE_PORT`; the guard names that requirement rather than refusing, and only an unrecognised engine is fatal. Keycloak continues to use the PostgreSQL pod regardless of the selected engine. The engine global moved in the chart from `global.tibco.dbEngine` to `global.external.db_type` (PCP-24360), so the CP recipe now emits **both** keys from the same `CP_DB_ENGINE` value: `global.external.db_type` is what a current `tibco-cp-base` reads, `global.tibco.dbEngine` is what the charts already in flight for this epic still read. Emitting only the new key would silently render the PostgreSQL schema Job on an `oracle` run against any base built before the move. `global.tibco.dbEngine` is dropped once no supported `tibco-cp-base` reads it. The `tibco-cp-hawk` and `tibco-cp-ai-agent` blocks stop emitting an engine key altogether — neither chart ever read one and both hardcode `postgres-helper.bash`, so those injections were dead, not translations. The CP recipe also emits `global.external.db_driver` from a new `GUI_CP_DB_DRIVER`, which defaults to the selected engine — `postgres` selects the `postgres` driver and `oracle` the `oracle` driver, those being the names the two drivers register under. Set it only to choose a different registered driver for the same engine (e.g. `pgx`); it does not switch engines. Without it the chart shipped an empty `DATABASE_DRIVER`, so an Oracle install called `sql.Open("postgres", "oracle://...")`.
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

### Removed
- [PCP-23863] `GUI_TP_INSTALL_ORACLE` (and its "Install Oracle" checkbox) is replaced by the `GUI_TP_DB_ENGINE` selector in the on-prem base recipes and forms. Set `GUI_TP_DB_ENGINE=oracle` instead; the old flag is no longer read.

### Fixed
- `pp-deploy-cp-core-on-prem`: the `tibco-cp-ai-agent` `containerRegistry` block now carries `username`/`password` alongside `url`/`repository`, like every other chart in the recipe. Without them the chart renders the ai-agent workloads with **no `imagePullSecrets` at all**, containerd falls back to an anonymous pull, JFrog answers 401, and `tp-cp-ai-agent` / `tp-cp-ai-agent-ui` / the `tibco-cp-ai-agent-db-setup` Job never start — on every deploy with `GUI_CP_INSTALL_PLATFORM_AI_AGENT=true` (the `mcp` profile). Nothing fails at helm time, which is why it shipped: the release installs green. **The gate is new in the chart's 1.21 line**, which is why older deploys were fine: `tibco-cp-ai-agent` `1.20.0-alpha.12` and earlier emit a hard-coded secret name unconditionally, whereas 1.21 resolves it as `secret` → `imagePullSecret` → `and username password` → *empty*, with the templates wrapping the block in `{{- if (include "...container-registry.secret" .) }}`. So a chart upgrade turned a long-standing recipe omission into a failure. That is the same shape as `tibco-cp-mcp-hub`, fixed for the identical reason in PCP-18094 / #284. When checking this, read the chart from the **deployed release** (`helm get values` / `helm get manifest`) rather than from a tp-helm-charts checkout: `origin/main` still carries the old unconditional helper, so the repo appears to disprove a defect that is real in the version actually installed. A new `test_container_registry_creds_guard.bats` scans every tracked YAML and fails any `containerRegistry` block that names a registry without saying how to authenticate to it (`secret`, or `username`+`password`) — mirroring the chart's own resolution order, since a recipe author cannot be expected to know which of a recipe's ~12 charts gate on it, nor when a chart line starts to. The scanner **fails closed**: a shape it cannot slice (flow mapping, anchor, alias, merge key, list item, tab indentation) is reported as `unsupported syntax` rather than skipped, because a guard that silently passes is worse than none. An explicitly empty `url` stays exempt (the public-registry marker for the docker.io Oracle image); a `url:` with no value at all does not (PCP-24234)
- on-prem option menus (`run.sh`, `adjust-recipe.sh`, `adjust-ingress.sh`, `generate-recipe.sh` ×2) no longer spin forever, leaking unbounded memory into whatever captures their output. Each was `while true` around a `read` whose `*)` branch neither broke nor cleared the choice, giving two non-terminating states: **(a)** the choice ends up non-empty and invalid, so the `[[ -z $choice ]]` guard is false forever and the loop stops re-prompting *and* stops reading stdin — measured at 223,460 `Invalid option` lines in 4 s with the menu printed 0 times; **(b)** the choice stays empty because `read` failed on closed/non-TTY stdin, re-printing the whole menu every pass — 25,245 menus in 4 s. Note (a) needs no pipe and no CI: **a human at a terminal who mistypes once lands there too**, because stdin is never read again — `Please try again` was never true. Both states reach `*)`, so the fix is to leave the loop there (`exit 1`, not `break`, which would reset `$?` and report success). Also reachable by default from the headless installer, which defaults `TP_K8S_CLUSTER_TYPE_CODE` to the empty string and expands it unquoted, calling `./adjust-recipe.sh` with zero arguments. The `run.sh` header comment advertising `Arguments: 1 - 9` is corrected to `0 - 8` — the `case` never had a 9, so following the documentation was itself a way in (PCP-24040)
- on-prem `run.sh`: the standalone CP deploy (`./run.sh 3`) now applies the CoreDNS `*.localhost.dataplanes.pro` rewrite before deploying, and `generate-recipe.sh` option 2 emits recipe `03` alongside `02` so a CP-only workspace has it. The documented `./run.sh 2` then `./run.sh 3` flow previously left a cluster with no rewrite at all, so CP pods that resolve their own `CP_DOMAIN` at startup crash-loop and `helm upgrade --install platform-base --wait` blocks until its 1h timeout. A failing rewrite is now fatal instead of unchecked (PCP-23809)
- on-prem `run.sh`: `./run.sh 1` no longer exits 0 when `deploy-subscription` fails every retry — `break` reset `$?` and the closing `printf` set the process exit code, so the main deploy path reported success after the DP automation never completed (PCP-23809)
- `pp-maintain-tp-config-coredns`: wait for the CoreDNS rollout to converge instead of returning as soon as the restart is requested; the step now runs immediately before the CP helm phase, where returning early races the pods it exists to unblock (PCP-23809)
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
