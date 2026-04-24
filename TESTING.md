# Testing Guide

## Quick Start

| Command | Description |
|---------|-------------|
| `make test` | Run all tests (BATS unit + integration + Helm unittest) |
| `make test-unit` | Run BATS unit tests for bash scripts |
| `make test-integration` | Run BATS integration tests (pipeline orchestration, CUE) |
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

charts/
├── common-dependency/tests/                 # Helm unittest for common-dependency
├── generic-runner/tests/                    # Helm unittest for generic-runner
├── helm-install/tests/                      # Helm unittest for helm-install
├── platform-provisioner-ui/tests/           # Helm unittest for UI chart
└── provisioner-config-local/tests/          # Helm unittest for config chart
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

## CI Integration

Tests run automatically via `.github/workflows/test.yaml` on:
- Push to `main`
- Pull requests targeting `main`

The CI pipeline runs these jobs:

1. **BATS Unit + Integration Tests** — runs both `tests/unit/bats/` and `tests/integration/bats/` with randomized file order (`shuf`) and parallel execution (`--jobs 2`), outputs JUnit XML, reports 10 slowest tests
2. **BATS Coverage** — runs all BATS tests through kcov with branch coverage, enforces minimum 90% threshold, outputs coverage summary with history
3. **Helm Unit Tests** — runs helm-unittest for all charts with `tests/`, outputs JUnit XML
4. **ShellCheck** — lints all bash scripts with `--severity=warning` (blocking)
5. **Recipe Smoke Tests** — validates e2e recipe YAML syntax and structure
6. **Diff Coverage (PR only)** — computes coverage delta for changed `.sh` files, posts coverage summary as PR comment with trend indicator
7. **Integration Test (generic-runner)** — runs generic-runner pipeline end-to-end with a real recipe (no Docker required)
8. **Integration Test (helm-install)** — runs helm-install pipeline end-to-end in mock mode (validates recipe processing)

All jobs have explicit `timeout-minutes` and use `actions/cache` for yq binary. BATS is installed from bats-core git (not apt) to support `--jobs` parallel execution.

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
