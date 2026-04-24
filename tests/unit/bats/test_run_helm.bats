#!/usr/bin/env bats
#
# Tests for charts/helm-install/scripts/run.sh
# Entry point functions: save_input, initial_assume_to_target_account, main, call_pipeline_script
#

load helpers/setup

setup() {
  setup_temp_dir
  source_functions
  source "${CHARTS_DIR}/common-dependency/scripts/_funcs_generic_runner.sh"
  source "${CHARTS_DIR}/helm-install/scripts/_funcs_pipeline.sh"

  # Extract function definitions from run.sh without executing top-level code
  local _run_sh="${CHARTS_DIR}/helm-install/scripts/run.sh"
  eval "$(awk '/^function save_input\(\)/,/^}/' "${_run_sh}")"
  eval "$(awk '/^function initial_assume_to_target_account\(\)/,/^}/' "${_run_sh}")"
  eval "$(awk '/^function call_pipeline_script\(\)/,/^}/' "${_run_sh}")"
  eval "$(awk '/^function main\(\)/,/^}/' "${_run_sh}")"

  cd "${TEST_TEMP_DIR}"
}

teardown() {
  cd /
  teardown_temp_dir
}

# ============================================================================
# save_input
# ============================================================================

@test "helm run.sh: save_input writes INPUT to RECIPE_FILE" {
  export INPUT='helmCharts:
  - name: test-chart'
  export RECIPE_FILE="${TEST_TEMP_DIR}/recipe.yaml"
  export PIPELINE_RECIPE_PRINT="false"
  save_input
  [ -f "${RECIPE_FILE}" ]
  [[ "$(cat "${RECIPE_FILE}")" == *"test-chart"* ]]
}

@test "helm run.sh: save_input prints recipe when PIPELINE_RECIPE_PRINT is not false" {
  export INPUT='helmCharts:
  - name: printme'
  export RECIPE_FILE="${TEST_TEMP_DIR}/recipe.yaml"
  export PIPELINE_RECIPE_PRINT="true"
  run save_input
  [ "$status" -eq 0 ]
  [[ "$output" == *"printme"* ]]
}

@test "helm run.sh: save_input skips print when PIPELINE_RECIPE_PRINT is false" {
  export INPUT='helmCharts:
  - name: secret-chart'
  export RECIPE_FILE="${TEST_TEMP_DIR}/recipe.yaml"
  export PIPELINE_RECIPE_PRINT="false"
  run save_input
  [ "$status" -eq 0 ]
  [[ "$output" != *"secret-chart"* ]]
}

# ============================================================================
# initial_assume_to_target_account
# ============================================================================

@test "helm run.sh: initial_assume_to_target_account skips when PIPELINE_INITIAL_ASSUME_ROLE is false" {
  export PIPELINE_INITIAL_ASSUME_ROLE="false"
  run initial_assume_to_target_account
  [ "$status" -eq 0 ]
}

# ============================================================================
# main
# ============================================================================

@test "helm run.sh: main returns error when INPUT is empty" {
  export INPUT=""
  export RECIPE_FILE="${TEST_TEMP_DIR}/recipe.yaml"
  run main
  [ "$status" -ne 0 ]
  [[ "$output" == *"INPUT is empty"* ]]
}

@test "helm run.sh: main returns success with PIPELINE_MOCK true" {
  export INPUT='helmCharts:
  - name: mock-chart
    namespace: default
    version: "1.0"'
  export RECIPE_FILE="${TEST_TEMP_DIR}/recipe.yaml"
  export PIPELINE_MOCK="true"
  run main
  [ "$status" -eq 0 ]
  [[ "$output" == *"PIPELINE_MOCK"* ]]
}

@test "helm run.sh: main calls save_input and writes recipe file" {
  export INPUT='helmCharts:
  - name: file-check-chart'
  export RECIPE_FILE="${TEST_TEMP_DIR}/recipe.yaml"
  export PIPELINE_MOCK="true"
  run main
  [ "$status" -eq 0 ]
  [ -f "${RECIPE_FILE}" ]
}
