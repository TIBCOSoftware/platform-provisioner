# Testing Guide

## Quick Start

| Command | Description |
|---------|-------------|
| `make test` | Run all tests (BATS unit + integration + Helm unittest) |
| `make test-unit` | Run BATS unit tests for bash scripts |
| `make test-integration` | Run BATS integration tests (pipeline orchestration, CUE) |
| `make test-skills` | Run the test runners of the `.ai/skills` suites (pytest, bats) |
| `make test-helm` | Run Helm chart unit tests |
| `make test-local` | Run e2e recipe test in Docker |
| `make lint` | Lint Helm charts (ct lint) |
| `make shellcheck` | Run shellcheck on bash scripts (severity: warning) |
| `make validate` | Run all validations (lint + shellcheck) |

## Prerequisites

Install test tools:

```bash
# BATS (Bash Automated Testing System)
brew install bats-core          # macOS
sudo apt-get install bats       # Ubuntu

# Helm unittest plugin
helm plugin install https://github.com/helm-unittest/helm-unittest.git

# Optional: shellcheck
brew install shellcheck         # macOS
sudo apt-get install shellcheck # Ubuntu

# Optional: cue (for schema validation tests)
brew install cue                # macOS

# yq (required by pipeline scripts)
brew install yq                 # macOS
```

## Test Structure

```
tests/
├── run-skill-tests.sh                       # Skill test runner: every .ai/skills/*/tests/run-tests.sh
├── unit/                                    # Unit tests — individual functions
│   └── bats/
│       ├── helpers/
│       │   └── setup.bash                   # Shared setup: env vars, source helpers
│       ├── README.md                        # Unit test documentation
│       ├── test_functions.bats              # _functions.sh (logging, yq, env vars)
│       ├── test_functions_edge.bats         # _functions.sh edge/boundary cases
│       ├── test_functions_mock.bats         # Cloud/orchestration mock tests
│       ├── test_fuzz.bats                   # Fuzz/property-based tests
│       ├── test_security.bats               # Security-focused tests
│       ├── test_generic_runner.bats         # _funcs_generic_runner.sh (script/payload/repo)
│       ├── test_funcs_helm.bats             # _funcs_helm.sh (chart download, flags, hooks)
│       ├── test_automation_deploy_gcp_paths.bats # make automation-deploy-gcp: local vs remote paths
│       ├── test_run_generic.bats            # generic-runner run.sh entry point
│       ├── test_run_helm.bats               # helm-install run.sh entry point
│       └── test_run_task.bats               # generic-runner::run_task lifecycle
├── integration/                             # Integration tests — multi-module pipelines
│   └── bats/
│       ├── README.md                        # Integration test documentation
│       ├── helpers/
│       │   └── setup.bash                   # Shared setup (same as unit)
│       ├── test_funcs_pipeline_generic.bats # generic-runner pipeline orchestration
│       ├── test_funcs_pipeline_helm.bats    # helm-install pipeline orchestration
│       ├── test_cue_validation.bats         # CUE schema validation
│       └── test_cue_contract.bats           # Contract tests: recipes vs CUE schemas
└── e2e/                                     # E2E tests — full recipes run in Docker
    ├── README.md                            # E2E test documentation
    ├── test-container-binaries.yaml         # Verify container tool versions
    ├── test-container-binaries-on-prem.yaml # On-prem container tool versions
    ├── test-local.yaml                      # Local k8s cluster test
    ├── test-retry.yaml                      # Retry/retryDelay behavior
    ├── test-aws.yaml                        # AWS assume role test
    ├── test-azure.yaml                      # Azure assume role test
    └── test-gcp.yaml                        # GCP federation test

.ai/skills/
├── deploy-tp-gcp-alpha/tests/               # pytest: fetch-versions.py
│   ├── test_fetch_versions.py               # Version selection + index fetch (needs PyYAML)
│   ├── test_next_step.py                    # The printed next step; no PyYAML, so it never skips
│   └── run-tests.sh                         # Runner of this skill, discovered by run-skill-tests.sh
└── validate-pipeline/tests/                 # pytest + bats: the provisioner MCP/REST skill scripts
    └── run-tests.sh                         # Runner of this skill, discovered by run-skill-tests.sh

charts/
├── common-dependency/tests/                 # Helm unittest for common-dependency
├── generic-runner/tests/                    # Helm unittest for generic-runner
├── helm-install/tests/                      # Helm unittest for helm-install
├── platform-provisioner-ui/tests/           # Helm unittest for UI chart
└── provisioner-config-local/tests/          # Helm unittest for config chart

docs/recipes/automation/tp-setup/bootstrap/
├── tests/                                   # pytest: the hermetic unit suite (CI runs this one)
│   └── conftest.py                          # Stubs the kubectl-backed ENV autodetect at module load
└── e2e/                                     # pytest: live-cluster suite (NOT run in CI)
```

## Unit Tests (`tests/unit/bats/`)

Unit tests cover individual bash functions in isolation.

### Core Functions (`test_functions.bats`)
- Logging functions (`common::err`, `common::info`, `common::warn`, `common::debug`)
- YAML parsing (`common::yq4-get`)
- Environment variable export and substitution
- Input validation toggle behavior
- Global variable initialization

### Security Tests (`test_security.bats`)
- Path traversal resistance in `common::source_file`
- Injection resistance in `common::export_variables` and `common::replace_env_variables`
- Secret leakage prevention (stderr isolation, debug toggle)
- YAML parsing safety (XSS-like content, depth, long values)
- Credential cleanup verification (`unset-aws-env`)
- Safe default verification (validation enabled, mock disabled)

### Fuzz / Property Tests (`test_fuzz.bats`)
- `common::yq4-get` with empty, whitespace, binary, unicode, emoji, and long inputs
- `common::replace_env_variables` with empty key/input, missing keys, multiline values, long values
- `common::export_variables` with empty YAML, numeric keys, boolean-like values, many variables
- Logging functions with empty messages, percent signs, backslashes, very long messages
- `init-global-variables` with empty string and unusual pre-set values

### Generic Runner (`test_generic_runner.bats`)
- Script/payload setup for generic-runner tasks
- Base64 encoded content handling
- Default file name behavior
- Repository setup

### Helm Functions (`test_funcs_helm.bats`)
- Chart flag generation (`process_chart_flags`)
- Install skip behavior (`installChart` with skip flag)
- Local chart tgz resolution (`getLocalChartName`)
- Values processing (`getValues`, `getRecipeValues`)
- Hook setup (`setupHooks` — pre/post deploy, base64, skip)
- Helm version resolution (`getHelmVersion`)
- ECR login validation (`ecr_login`)

### Entry Points (`test_run_generic.bats`, `test_run_helm.bats`)
- `save_input` writes INPUT to RECIPE_FILE
- `initial_assume_to_target_account` skip behavior
- `main` error on empty INPUT, success with PIPELINE_MOCK

### Task Lifecycle (`test_run_task.bats`)
- Script execution, skip, ignoreErrors, payload creation, cleanup, task index

### Edge Cases (`test_functions_edge.bats`)
- `common::yq4-get` with empty input, malformed YAML, deep nesting, arrays, booleans, numerics
- `common::source_file` with empty path, directory path
- Logging with empty/special/multiline messages
- `common::export_variables` with missing keys, single vars, numeric values
- `common::replace_env_variables` with empty key, empty input, missing recipe key
- `common::validate_input` when cue/shared.cue not found
- `init-global-variables` defaults and preservation
- `load-customized-env` with non-existent and existing files

### Mock Tests (`test_functions_mock.bats`)
- `pp-aws-assume-role` skip logic, chain assumption, error propagation
- `common::assume_role` routing: on-prem (3 paths), GCP, Azure, AWS, with/without cluster name, error propagation
- `process_recipe_secret` passthrough vs AWS secret, assume-role failure
- `gitops_replace_recipe` passthrough vs git clone, clone failure
- `common::process_meta` full orchestration flow, env substitution, error propagation from sub-functions

### How isolation works
- Tests run with `PIPELINE_FUNCTION_INIT=false` to skip the `init()` function
- External dependencies (Docker, AWS, cloud CLIs) are mocked via env var overrides
- Each test uses a temporary directory that is cleaned up on teardown
- Helm commands are mocked with `HELM_COMMAND_LINE="echo helm"`

### Shared test helpers (`helpers/setup.bash`)

| Helper | Purpose | Example |
|--------|---------|---------|
| `setup_temp_dir` | Creates isolated `$TEST_TEMP_DIR` | `setup_temp_dir` in `setup()` |
| `teardown_temp_dir` | Cleans up temp dir | `teardown_temp_dir` in `teardown()` |
| `source_functions` | Sources `_functions.sh` with mocks | `source_functions` in `setup()` |
| `test_id [prefix]` | Generates unique ID (e.g., `test-a3f7b2c1`) | `local name=$(test_id "release")` |
| `build_generic_recipe "script" [cond] [ignoreErr]` | Generates generic-runner recipe YAML | `local recipe=$(build_generic_recipe "echo hello")` |
| `build_helm_recipe "release" "chart" "url" [ns]` | Generates helm-install recipe YAML | `local recipe=$(build_helm_recipe "app" "nginx" "https://repo")` |

### Running a single test file
```bash
bats tests/unit/bats/test_functions.bats
bats tests/unit/bats/test_funcs_helm.bats

# With parallel execution (requires bats-core >= 1.7.0)
bats tests/unit/bats/ --recursive --timing --jobs 2
```

## Integration Tests (`tests/integration/bats/`)

Integration tests verify multi-module pipeline orchestration.

### Pipeline Orchestration (`test_funcs_pipeline_generic.bats`, `test_funcs_pipeline_helm.bats`)
- Task condition evaluation (true/false/default)
- Multiple task execution order
- Empty and missing task handling
- Pre/post task processing in helm-install pipeline

### CUE Schema Validation (`test_cue_validation.bats`)
- Valid recipes pass schema validation
- Invalid recipes (missing tasks, empty tasks, negative retry) are rejected
- Requires `cue` CLI (tests skip if not installed)

### Contract Tests (`test_cue_contract.bats`)
- helm-install schema validation (valid/invalid synthetic recipes)
- Validates all repo types (helm, ECR, git), hooks, flags, multiple charts
- Validates real example recipes in `docs/recipes/` have required fields
- Ensures helm-install recipes have `helmCharts`, generic-runner recipes have `tasks`
- Requires `cue` CLI (tests skip if not installed)

### Running integration tests
```bash
bats tests/integration/bats/ --recursive
```

## E2E Tests (`tests/e2e/`)

E2E tests are recipe YAML files that run inside the Docker runtime container via `make test-local`. They exercise the full pipeline end-to-end including Docker image, tool binaries, and real script execution.

| Recipe | Requires | What it tests |
|--------|----------|---------------|
| `test-container-binaries.yaml` | Docker image | All tool versions (aws, az, helm, kubectl, etc.) |
| `test-container-binaries-on-prem.yaml` | Docker image | On-prem tool versions (no cloud CLIs) |
| `test-local.yaml` | Docker + k8s cluster | kubectl get nodes via on-prem kubeconfig |
| `test-retry.yaml` | Docker image | retryCount and retryDelay behavior |
| `test-aws.yaml` | Docker + AWS credentials | AWS STS assume role |
| `test-azure.yaml` | Docker + Azure credentials | Azure subscription access |
| `test-gcp.yaml` | Docker + GCP credentials | GCP project access |

### Running e2e tests
```bash
# Default (test-container-binaries-on-prem)
make test-local

# Specific recipe
make test-local PIPELINE_INPUT_RECIPE=tests/e2e/test-retry.yaml
```

## Helm Unit Tests

Helm unittest tests validate that chart templates render correctly. Tests are co-located with each chart in `charts/<chart>/tests/`.

### Charts with tests
- **common-dependency**: Secret rendering, ConfigMap for scripts and CUE schemas
- **generic-runner**: Tekton Task and Pipeline rendering, params, volumes, sidecars
- **helm-install**: Tekton Task and Pipeline rendering (no dind sidecar)
- **platform-provisioner-ui**: Deployment, Service, ServiceAccount, Ingress
- **provisioner-config-local**: ConfigMap rendering with labels and namespace

### Running tests for a specific chart
```bash
helm unittest --strict charts/platform-provisioner-ui/
helm unittest --strict charts/generic-runner/
```

## Skill Tests (`.ai/skills/*/tests/`)

The skills under `.ai/skills/` ship scripts that drive a pipeline run (trigger, fetch a recipe, parse a
log, look up chart versions). Each skill owns its tests and its own runner, `tests/run-tests.sh`, because
each suite brings its own tools: pytest for the python scripts, bats for the shell scripts. The suites are
network-free — the MCP/REST calls, the `gh api` index and the pipeline itself are stubbed.

| Skill | Suites | Covers |
|-------|--------|--------|
| `validate-pipeline` | pytest + bats | `provisioner-mcp.py`, `trigger-pipeline.sh`, `fetch-recipe.sh`, `parse-log.sh`, `cancel-pipeline.sh` |
| `deploy-tp-gcp-alpha` | pytest | `fetch-versions.py` (chart version selection and index fetch in `test_fetch_versions.py`, the printed next step in `test_next_step.py`) |

[`tests/run-skill-tests.sh`](tests/run-skill-tests.sh) **discovers** the runners instead of listing them,
so a new `.ai/skills/<skill>/tests/run-tests.sh` is picked up by CI without touching the harness or the
workflow. Every runner is executed even when one fails, and the summary names each of them. A skills tree
without a single runner fails the sweep: an empty discovery would report a green run for tests that never ran.

```bash
# every skill
make test-skills
./tests/run-skill-tests.sh

# one skill
make test-skills SKILL=validate-pipeline
./tests/run-skill-tests.sh validate-pipeline

# the way CI runs them: every tool required, a test that skips itself fails
SKILL_TESTS_STRICT=true ./tests/run-skill-tests.sh
```

| Variable | Default | Purpose |
|----------|---------|---------|
| `SKILL` | *(empty)* | Limits `make test-skills` to one skill |
| `SKILLS_DIR` | `.ai/skills` | The skills tree the runners are discovered in |
| `SKILL_TESTS_STRICT` | *(off)* | Treats a missing tool and a test that skips itself as a failure. Set on the CI job |

- **pytest** and **PyYAML** are required; the runners fall back to `uv run --with pytest` when pytest is
  not importable.
- **bats** is optional locally — a runner prints a `SKIP` note without it. CI installs it and verifies the
  tools up front, so a suite can never silently skip there.
- The `parse-log` suite exercises the GNU-only `grep -oP` of the script under test, so it needs GNU grep
  (CI has it; on macOS use `brew install grep`, on Alpine the BusyBox grep is not enough).
- Skill tests are not part of `make test`: they need a python toolchain, while the BATS and Helm suites
  only need bash. CI runs them on every PR.

### Nothing green may stand for nothing run

A suite that skips itself reports neither a pass nor a failure, and a sweep of such suites reads exactly
like a clean run. Three guards keep the skill tests honest, and each of them is a hard failure:

| Guard | Where |
|-------|-------|
| A skills tree with no runner at all fails the sweep | `tests/run-skill-tests.sh` |
| A runner that ran no suite fails, even when nothing failed | `.ai/skills/*/tests/run-tests.sh` |
| With `SKILL_TESTS_STRICT`, a missing tool and a skipped test fail (bats is run through the TAP formatter, which names a skipped test; pytest reports its skips with `-rs`) | `.ai/skills/*/tests/run-tests.sh` |

The same rule shapes where a test lives: the guard on the next step `fetch-versions.py` prints sits in
`test_next_step.py`, which needs no PyYAML, because next to the index fixture it was skipped on every
machine without it — a guard behind a skip guards nothing.

## Automation Bootstrap Unit Tests (`docs/recipes/automation/tp-setup/bootstrap/tests/`)

The Platform Automation Hub under `docs/recipes/automation/tp-setup/bootstrap/` is a standalone
`uv` sub-project (Flask + Playwright). Its `tests/` tree is a pytest suite over the page objects,
the CLI orchestrator and the server routes. It needs **no cluster, no Control Plane and no
tibcop** — but cluster-free is not browser-free: `test_local_secret_prefill.py` (the TPSEC-124
regression) drives a real chromium against an in-process Flask server, so a browser binary has to
be present or that one case errors out.

```bash
cd docs/recipes/automation/tp-setup/bootstrap
uv sync
uv run playwright install chromium   # once; only test_local_secret_prefill.py needs it
uv run pytest tests/ -rs
```

**`tests/` only — never `tests/ e2e/`.** The sibling `e2e/` tree is the live-cluster suite: its
`conftest.py` probes helm at collection time and raises a `TypeError` when no cluster is present,
so pulling it in fails the run on every machine without one. `tests/conftest.py` is built for the
opposite: it stubs the kubectl-backed `ENV` autodetect entry points (`get_command_output`,
`get_cp_version`, `get_cp_dns_domain`, `get_elastic_password`, `get_storage_class`) at module load,
before pytest imports any test module, so nothing shells out at collection.

The CI job therefore installs chromium (`playwright install --with-deps chromium`) before running
the suite. Skipping that step does not fail the suite so much as make it lie: it ends
`609 passed, 1 error` and exits 1, which reads as a broken build when it is a missing binary.

The CI job is scoped the same way. `pytest` exits 5 when it collects nothing, so a suite that
disappears fails the job rather than reporting a green run for tests that never ran — the same rule
the skill tests follow under *Nothing green may stand for nothing run*.

> Until PCP-23458 no CI job ran this tree at all: 39 test files, 8 green checks on a PR, and not one
> of those checks executed a single case. The suite is only worth what CI enforces.

## CI Integration

Tests run automatically via `.github/workflows/test.yaml` on:
- Push to `main`
- Pull requests targeting `main`

The CI pipeline runs these jobs:

1. **BATS Unit + Integration Tests** — runs both `tests/unit/bats/` and `tests/integration/bats/` with randomized file order (`shuf`) and parallel execution (`--jobs 2`), outputs JUnit XML, reports 10 slowest tests
2. **Skill Tests (`.ai/skills`)** — installs python (pytest, PyYAML) and bats, verifies both are on PATH, sets `SKILL_TESTS_STRICT=true` so a suite that skips a test fails the job, then runs every `run-tests.sh` discovered by `tests/run-skill-tests.sh`
3. **Automation Bootstrap Unit Tests** — `uv sync --frozen`, `playwright install --with-deps chromium`, then `uv run pytest tests/` inside `docs/recipes/automation/tp-setup/bootstrap`, scoped to `tests/` so the live-cluster `e2e/` tree is never collected; uploads the JUnit XML
4. **Helm Unit Tests** — runs helm-unittest for all charts with `tests/`, outputs JUnit XML
5. **ShellCheck** — lints all bash scripts with `--severity=error` (blocking)
6. **Recipe Smoke Tests** — validates e2e recipe YAML syntax and structure
7. **Integration Test (generic-runner)** — runs generic-runner pipeline end-to-end with a real recipe (no Docker required)
8. **Integration Test (helm-install)** — runs helm-install pipeline end-to-end in mock mode (validates recipe processing)

That is the whole list — eight jobs, matching `test.yaml` exactly. This section previously also
described a **BATS Coverage** job ("enforces minimum 90% threshold") and a **Diff Coverage (PR
only)** job ("posts coverage summary as PR comment"). Neither exists in any of the eight workflow
files — `kcov`, `diff-cover` and any coverage job name return nothing across `.github/workflows/`
— so both were removed rather than renumbered. A documented gate that does not run is worse than
no gate: it is the same "nothing green may stand for nothing run" failure this file warns about,
one level up, in the description of the CI itself.

All jobs have explicit `timeout-minutes` and use `actions/cache` for yq binary. BATS is installed from bats-core git (not apt) to support `--jobs` parallel execution.

Every step that pipes a test run into `tee` sets `set -o pipefail` first: a GitHub step is graded on the
exit code of the pipeline, which is otherwise the one of `tee` — the failing run would be written into the
report and the job would still be green.

Test results are uploaded as GitHub Actions artifacts and displayed as PR check annotations via `dorny/test-reporter`.

### Branch Protection

The `main` branch is protected with the following quality gates:
- **Required status checks** (must pass before merge): BATS Unit Tests, Helm Unit Tests, ShellCheck, Recipe Smoke Tests
- **Required PR reviews**: 1 approving review, stale reviews dismissed on new pushes
- **Force pushes** and **branch deletion** are disabled

Helm chart linting (ct lint) runs separately via `.github/workflows/lint-test.yaml` on chart changes.

## Adding New Tests

### Adding BATS unit tests

1. Create `tests/unit/bats/test_<topic>.bats`
2. Load the shared setup: `load helpers/setup`
3. Source the script under test in `setup()`
4. Use `run` to execute functions and assert on `$status` and `$output`

### Adding BATS integration tests

1. Create `tests/integration/bats/test_<topic>.bats`
2. Load the shared setup: `load helpers/setup`
3. Source multiple scripts and test their interaction

### Adding e2e tests

1. Create `tests/e2e/test-<name>.yaml` as a recipe YAML
2. Run with `make test-local PIPELINE_INPUT_RECIPE=tests/e2e/test-<name>.yaml`

### Adding Helm tests

1. Create `charts/<chart>/tests/<template>_test.yaml`
2. Reference the template file in the `templates:` field
3. Use `set:` to override values and `asserts:` to validate output
4. See [helm-unittest docs](https://github.com/helm-unittest/helm-unittest) for assertion reference

### Adding skill tests

1. Create `.ai/skills/<skill>/tests/` with the suites the scripts need (pytest, bats, or both)
2. Add `.ai/skills/<skill>/tests/run-tests.sh`: it runs the suites of that skill and exits non-zero when
   one fails, and when none of them ran at all — that is the whole contract, `tests/run-skill-tests.sh`
   and CI discover it by its name
3. Honour `SKILL_TESTS_STRICT` in the runner: with it set, a tool it would otherwise skip over and a
   test that skipped itself both fail the run (see the two runners for the shape)
4. Keep a guard out of a suite that can skip itself — a check behind a `SKIP` is a check nobody makes
5. Keep the suites network-free (stub the MCP/REST calls) and document them in `tests/README.md`
6. Verify with `make test-skills SKILL=<skill>` and `make test-skills SKILL=<skill> SKILL_TESTS_STRICT=true`
