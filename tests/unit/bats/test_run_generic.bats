#!/usr/bin/env bats
#
# Tests for charts/generic-runner/scripts/run.sh
# Entry point functions: save_input, initial_assume_to_target_account, main
#

load helpers/setup

setup() {
  setup_temp_dir
  source_functions
  source "${CHARTS_DIR}/common-dependency/scripts/_funcs_generic_runner.sh"
  source "${CHARTS_DIR}/generic-runner/scripts/_funcs_pipeline.sh"

  # Extract function definitions from run.sh without executing top-level code
  local _run_sh="${CHARTS_DIR}/generic-runner/scripts/run.sh"
  eval "$(awk '/^function save_input\(\)/,/^}/' "${_run_sh}")"
  eval "$(awk '/^function initial_assume_to_target_account\(\)/,/^}/' "${_run_sh}")"
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

@test "save_input writes INPUT to RECIPE_FILE" {
  export INPUT='key: value'
  export RECIPE_FILE="${TEST_TEMP_DIR}/recipe.yaml"
  export PIPELINE_RECIPE_PRINT="false"
  save_input
  [ -f "${RECIPE_FILE}" ]
  [[ "$(cat "${RECIPE_FILE}")" == *"key: value"* ]]
}

@test "save_input prints recipe when PIPELINE_RECIPE_PRINT is not false" {
  export INPUT='printme: yes'
  export RECIPE_FILE="${TEST_TEMP_DIR}/recipe.yaml"
  export PIPELINE_RECIPE_PRINT="true"
  run save_input
  [ "$status" -eq 0 ]
  [[ "$output" == *"printme: yes"* ]]
}

@test "save_input skips print when PIPELINE_RECIPE_PRINT is false" {
  export INPUT='secret: data'
  export RECIPE_FILE="${TEST_TEMP_DIR}/recipe.yaml"
  export PIPELINE_RECIPE_PRINT="false"
  run save_input
  [ "$status" -eq 0 ]
  [[ "$output" != *"secret: data"* ]]
}

# ============================================================================
# initial_assume_to_target_account
# ============================================================================

@test "initial_assume_to_target_account skips when PIPELINE_INITIAL_ASSUME_ROLE is false" {
  export PIPELINE_INITIAL_ASSUME_ROLE="false"
  run initial_assume_to_target_account
  [ "$status" -eq 0 ]
}

# ============================================================================
# main
# ============================================================================

@test "main returns error when INPUT is empty" {
  export INPUT=""
  export RECIPE_FILE="${TEST_TEMP_DIR}/recipe.yaml"
  run main
  [ "$status" -ne 0 ]
  [[ "$output" == *"INPUT is empty"* ]]
}

@test "main returns success with PIPELINE_MOCK true" {
  export INPUT='tasks:
  - script:
      content: echo test'
  export RECIPE_FILE="${TEST_TEMP_DIR}/recipe.yaml"
  export PIPELINE_MOCK="true"
  run main
  [ "$status" -eq 0 ]
  [[ "$output" == *"PIPELINE_MOCK"* ]]
}
