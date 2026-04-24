# QA Maturity Assessment for platform-provisioner

**Date**: `2026-04-24`
**Commit**: `ebaa68a`
**Overall QA Score**: **`9.0 / 10`** (maintained from previous assessment)
**Language(s)**: `Bash, YAML (Helm)`
**Test Framework(s)**: `BATS (Bash), helm-unittest (Helm)`

---

## I. Executive Summary

The platform-provisioner project maintains **strong QA maturity** for a Bash/Helm project. Since the last assessment (2026-03-25), the project added `_check-tools.sh` as a testable shared module with pure functions, and `test_check_tools.bats` with 12 new test cases covering yq version validation (pass/fail/edge cases). Total unit tests grew from ~200 to 215 and source code expanded to 3,114 LOC across 8 scripts.

**Key strengths**: Multi-layer test structure, CI quality gates, test type diversity (8 types), comprehensive documentation, backward-compatible architecture with testable shared modules.

**New since last assessment**: `_check-tools.sh` extracted pure functions (`validate_yq_version`, `get_yq_version`) for BATS testing while keeping `generate-recipe.sh` self-contained for backward compatibility with gdrive-distributed scripts.

**Remaining opportunities**: Dynamic coverage badge (requires external service), historical trend chart.

---

## II. Dimension Scores

| # | Dimension | Weight | Score | Bar | Key Evidence |
|---|-----------|--------|-------|-----|-------------|
| 1 | Test Structure & Organization | 15% | 9.0 | `█████████░` | 3-tier dirs (unit/integration/e2e), per-dir helpers, per-dir READMEs, consistent `test_*.bats` naming, charts co-located tests, new `test_check_tools.bats` follows conventions |
| 2 | Coverage Configuration | 15% | 9.5 | `██████████` | kcov with `--branch-coverage`, 85% threshold, diff-cover on PRs with PR comment, coverage badge in README, history tracking |
| 3 | Test Isolation & DB Safety | 10% | 9.0 | `█████████░` | `PIPELINE_FUNCTION_INIT=false`, `PIPELINE_MOCK=true`, all CLIs mocked via `export -f`, temp dirs with auto-cleanup, no shared state, `_check-tools.sh` sourced in setup() |
| 4 | Flakiness Management | 5% | 9.0 | `█████████░` | Zero `sleep` in tests, deterministic fixtures, no network calls, `--jobs 2` parallel, randomized file order via `shuf` in CI |
| 5 | CI/CD Integration | 15% | 9.0 | `█████████░` | 8 CI jobs, auto-run on PR+push, JUnit XML + `dorny/test-reporter`, parallel BATS, timeout-minutes on all jobs, yq cache, ShellCheck blocking |
| 6 | Test Type Diversity | 15% | 9.0 | `█████████░` | 8 types: unit, integration, e2e, security, fuzz, Helm unittest, smoke, contract (CUE schema), ShellCheck (static analysis) |
| 7 | Test Documentation | 5% | 9.0 | `█████████░` | TESTING.md (290+ lines), `tests/AGENTS.md`, per-dir READMEs (unit/integration/e2e), placement guide, fixture docs |
| 8 | Fixtures & Test Helpers | 5% | 9.0 | `█████████░` | Shared `helpers/setup.bash` (unit + integration), `source_functions()`, `setup_temp_dir()`/`teardown_temp_dir()`, `test_id()`, `build_generic_recipe()`, `build_helm_recipe()`, mock patterns via `export -f` |
| 9 | Test Data Management | 5% | 8.5 | `█████████░` | `mktemp -d` for isolation, auto-cleanup in teardown, inline YAML fixtures (deterministic), `test_id()` for unique data, `build_*_recipe()` factories, no secrets in test data |
| 10 | Reporting & Observability | 10% | 8.0 | `████████░░` | JUnit XML + dorny/test-reporter, coverage JSON summary, `--timing` flag, GitHub Step Summary, coverage badge in README, PR coverage comments |

---

## III. Improvement Roadmap (Priority Order)

### Quick Wins (< 1 day each)

1. **Make coverage badge dynamic** — Impact: low, Effort: low
   - Use a GitHub Action to update badge from `coverage-summary.json` after each merge
   - Definition of Done: README badge shows current coverage percentage automatically

### Medium-Term (1-3 days each)

1. **Add coverage trend tracking** — Impact: medium, Effort: medium
   - Store `coverage-summary.json` in a separate branch or use a coverage service
   - Show coverage delta in PR comments (not just Step Summary)
   - Definition of Done: PRs show coverage trend (up/down arrow with percentage)

2. **Expand contract tests** — Impact: medium, Effort: medium
   - Add CUE validation for all recipe types in `docs/recipes/`
   - Definition of Done: Every recipe type has schema validation tests in CI

### Strategic (1+ week)

1. **Historical test metrics dashboard** — Impact: low, Effort: high
   - Track test count, pass rate, coverage over time
   - Definition of Done: Trend chart accessible to team

---

## IV. Benchmark Comparison

| Practice | This Project | Gold Standard (Bash/Helm) |
|----------|-------------|--------------------------|
| Coverage threshold | 85% (kcov) | >= 80% with kcov |
| Test types | 8 types | 5+ types (unit/integration/e2e + security + static) |
| CI quality gates | Yes (8 jobs, pass-to-merge) | Pass-to-merge enforced |
| Test documentation | TESTING.md + AGENTS.md + per-dir READMEs | TESTING.md + AGENTS.md + per-dir READMEs |
| Test isolation | Mocked CLIs, temp dirs, env var overrides | Mocked externals, temp dirs |
| Test structure | `tests/{unit,integration,e2e}/bats/` + `charts/*/tests/` | `tests/bats/` + `charts/*/tests/` |
| Diff coverage | Yes (PR only) | Yes (PR only) |
| Security tests | Dedicated `test_security.bats` | Often absent |
| Fuzz tests | Dedicated `test_fuzz.bats` | Rarely present |
| Pure function testing | `_check-tools.sh` with `validate_yq_version()` | Rare in Bash projects |
| Test reporting | JUnit XML + dorny/test-reporter | JUnit XML + CI annotations |

**Assessment**: This project **exceeds** the gold standard for Bash/Helm projects in most dimensions. Security and fuzz testing layers are impressive — rarely seen in infrastructure projects. The new `_check-tools.sh` pattern of extracting pure functions for testability while maintaining backward compatibility is exemplary.

---

## V. Scope & Exclusions

**Project Identity:**
- Name: platform-provisioner
- Purpose: Recipe-based provisioning system for cloud-native platforms
- Primary language(s): Bash (scripts), YAML (Helm charts, recipes)
- Source code: `charts/*/scripts/*.sh` (7 files), `docs/recipes/automation/on-prem/_check-tools.sh` (1 file) — 3,114 LOC total

**Excluded from scoring** (tests that do not test this repo's code):
- `docs/recipes/automation/tp-setup/bootstrap/` — Independent Python project (has own `pyproject.toml`), tests TIBCO Platform product, not this repo's code

---

## VI. Evidence Log

### Structure (9.0)
- `tests/unit/bats/` — 11 test files (including new `test_check_tools.bats`), `helpers/setup.bash`, `README.md`
- `tests/integration/bats/` — 3 test files, `helpers/setup.bash`, `README.md`
- `tests/e2e/` — 7 recipe YAML files, `README.md`
- `charts/{common-dependency,generic-runner,helm-install,platform-provisioner-ui,provisioner-config-local}/tests/` — co-located Helm tests
- Consistent naming: `test_*.bats` (BATS), `*_test.yaml` (Helm)

### Coverage (9.5)
- `.github/workflows/test.yaml:89-94` — kcov with `--include-path` targeting source dirs
- `.github/workflows/test.yaml:97-105` — 85% threshold check
- `.github/workflows/test.yaml:231-290` — Diff coverage for changed `.sh` files (PR only)
- Coverage badge in README
- PR coverage trend comments

### Isolation (9.0)
- `tests/unit/bats/helpers/setup.bash:15-23` — 8 env vars mock all external dependencies
- `tests/unit/bats/helpers/setup.bash:32-40` — `setup_temp_dir()` / `teardown_temp_dir()` for each test
- `tests/unit/bats/test_functions_mock.bats` — `export -f` pattern to mock `aws`, `jq`, cloud CLIs
- `tests/unit/bats/test_check_tools.bats` — sources `_check-tools.sh` in `setup()`, tests pure functions
- No test-to-test dependencies observed

### Flakiness (9.0)
- Zero `sleep` calls in any BATS test file
- All tests use inline YAML fixtures (deterministic)
- `--jobs 2` parallel execution in CI (tests must be independent)
- Randomized file order via `shuf` in CI

### CI (9.0)
- `.github/workflows/test.yaml` — 8 jobs: bats, bats-coverage, helm-unittest, shellcheck, recipe-smoke, diff-coverage, integration, integration-helm
- All jobs have `timeout-minutes` (5-15)
- `actions/cache@v4` for yq binary
- `dorny/test-reporter@v2` for PR annotations
- `actions/upload-artifact@v4` for test results and coverage

### Diversity (9.0)
- Unit: `tests/unit/bats/` (11 files, 215 tests — including 12 new `test_check_tools.bats`)
- Integration: `tests/integration/bats/` (3 files, 41 tests)
- E2E: `tests/e2e/` (7 recipe YAMLs, Docker-based)
- Security: `tests/unit/bats/test_security.bats` (17 tests)
- Fuzz: `tests/unit/bats/test_fuzz.bats` (27 tests)
- Helm unittest: `charts/*/tests/` (11 files, 36 assertions)
- Smoke: `.github/workflows/test.yaml:186-230` (recipe YAML validation)
- Contract: CUE schema validation tests
- Static analysis: ShellCheck in CI

### Documentation (9.0)
- `TESTING.md` — 290+ lines, comprehensive guide
- `tests/AGENTS.md` — AI assistant conventions
- `tests/unit/bats/README.md` — 55 lines, scope/files/isolation/running
- `tests/integration/bats/README.md` — integration-specific docs
- `tests/e2e/README.md` — e2e test docs

### Fixtures (9.0)
- `tests/unit/bats/helpers/setup.bash` — shared setup with `source_functions()`, `setup_temp_dir()`, `teardown_temp_dir()`, `test_id()`, `build_generic_recipe()`, `build_helm_recipe()`
- `tests/integration/bats/helpers/setup.bash` — identical shared setup (kept in sync)
- Mock patterns: `export -f` for CLI mocking, `HELM_COMMAND_LINE="echo helm"`
- Recipe builder helpers reduce boilerplate and ensure consistent YAML structure across tests

### Data Management (8.5)
- `mktemp -d` provides unique temp dirs per test
- Automatic cleanup in `teardown()` via `teardown_temp_dir()`
- `test_id()` generates unique identifiers for data isolation between tests
- `build_generic_recipe()` / `build_helm_recipe()` — factory functions for recipe YAML test data
- Inline YAML fixtures (no external test data files to manage)
- No secrets in test data (AWS examples use `EXAMPLE` suffixed keys)

### Reporting (8.0)
- JUnit XML output: `bats --formatter junit > test-results/bats-*-results.xml`
- `dorny/test-reporter@v2` for GitHub PR annotations
- Coverage JSON: `coverage/coverage-summary.json`
- `$GITHUB_STEP_SUMMARY` for coverage report table
- `--timing` flag on BATS runs
- Coverage badge in README
- PR coverage comments
