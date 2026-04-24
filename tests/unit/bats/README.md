# Unit Tests

BATS unit tests for individual bash functions in isolation.

## Scope

Tests cover functions from:
- `charts/common-dependency/scripts/_functions.sh` — logging, yq helpers, env vars, validation
- `charts/generic-runner/scripts/_funcs_generic_runner.sh` — script/payload/repo setup
- `charts/helm-install/scripts/_funcs_helm.sh` — chart flags, hooks, values
- `charts/generic-runner/scripts/run.sh` — generic-runner entry point
- `charts/helm-install/scripts/run.sh` — helm-install entry point

## Test Files

| File | Tests | What it covers |
|------|-------|---------------|
| `test_functions.bats` | Core functions | Logging, yq, env vars, validation |
| `test_functions_edge.bats` | Edge cases | Boundary inputs, empty values, malformed YAML |
| `test_functions_mock.bats` | Mock tests | Cloud routing, error propagation, orchestration |
| `test_generic_runner.bats` | Generic runner | Script/payload setup, base64, repo |
| `test_funcs_helm.bats` | Helm functions | Chart flags, hooks, values, ECR login |
| `test_run_generic.bats` | Entry point | generic-runner `run.sh` main flow |
| `test_run_helm.bats` | Entry point | helm-install `run.sh` main flow |
| `test_run_task.bats` | Task lifecycle | Script exec, skip, ignoreErrors, cleanup |
| `test_security.bats` | Security | Injection resistance, path traversal, secret leakage |
| `test_fuzz.bats` | Fuzz/property | Generated edge-case inputs, crash resistance |

## How Isolation Works

- `PIPELINE_FUNCTION_INIT=false` skips the `init()` function
- External CLIs (aws, az, gcloud, docker) are mocked via env var overrides or `export -f`
- Each test uses `mktemp -d` for artifacts, cleaned in teardown
- Helm commands are mocked with `HELM_COMMAND_LINE="echo helm"`

## Running

```bash
# All unit tests
bats tests/unit/bats/ --recursive --timing

# Single file
bats tests/unit/bats/test_functions.bats

# With parallel execution
bats tests/unit/bats/ --recursive --timing --jobs 2
```

## Adding New Tests

1. Create `test_<topic>.bats` in this directory
2. Add `load helpers/setup` at the top
3. Source the script under test in `setup()`
4. Use `run` to execute functions, assert on `$status` and `$output`
