# Integration Tests

BATS integration tests for multi-module pipeline orchestration.

## Scope

Tests verify interactions between multiple scripts working together:
- Pipeline task condition evaluation and execution order
- CUE schema validation of recipe YAML files
- Pre/post task processing across pipeline stages

## Test Files

| File | Tests | What it covers |
|------|-------|---------------|
| `test_funcs_pipeline_generic.bats` | Pipeline orchestration | Task conditions, execution order, empty/missing tasks |
| `test_funcs_pipeline_helm.bats` | Helm pipeline | Pre/post task processing, multi-task execution |
| `test_cue_validation.bats` | Schema validation | Valid/invalid recipes against CUE schemas |

## Prerequisites

- `yq` — required by all tests
- `cue` — required by `test_cue_validation.bats` (tests skip if not installed)

## Running

```bash
# All integration tests
bats tests/integration/bats/ --recursive --timing

# Single file
bats tests/integration/bats/test_cue_validation.bats
```
