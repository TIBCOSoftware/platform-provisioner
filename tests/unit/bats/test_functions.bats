#!/usr/bin/env bats
#
# Tests for charts/common-dependency/scripts/_functions.sh
# Core utility functions: logging, yq helpers, env variable processing, validation
#

load helpers/setup

setup() {
  setup_temp_dir
  source_functions
}

teardown() {
  teardown_temp_dir
}

# ============================================================================
# Logging functions
# ============================================================================

@test "common::err outputs ERROR to stderr" {
  run common::err "test error message"
  [ "$status" -eq 0 ]
  [[ "$output" == *"[ERROR]: test error message"* ]]
}

@test "common::info outputs INFO to stdout" {
  run common::info "test info message"
  [ "$status" -eq 0 ]
  [[ "$output" == *"[INFO]: test info message"* ]]
}

@test "common::warn outputs WARNING to stdout" {
  run common::warn "test warn message"
  [ "$status" -eq 0 ]
  [[ "$output" == *"[WARNING]: test warn message"* ]]
}

@test "common::debug outputs nothing when PIPELINE_LOG_DEBUG is false" {
  export PIPELINE_LOG_DEBUG="false"
  run common::debug "should not appear"
  [ "$status" -eq 0 ]
  [ "$output" = "" ]
}

@test "common::debug outputs DEBUG when PIPELINE_LOG_DEBUG is true" {
  export PIPELINE_LOG_DEBUG="true"
  run common::debug "debug message"
  [ "$status" -eq 0 ]
  [[ "$output" == *"[DEBUG]: debug message"* ]]
}

# ============================================================================
# common::source_file
# ============================================================================

@test "common::source_file fails for non-existent file" {
  run common::source_file "/nonexistent/file.sh"
  [ "$status" -ne 0 ]
}

@test "common::source_file succeeds for existing file" {
  echo 'export TEST_SOURCED_VAR="hello"' > "${TEST_TEMP_DIR}/test.sh"
  source_functions  # re-source to get clean state
  common::source_file "${TEST_TEMP_DIR}/test.sh"
  [ "${TEST_SOURCED_VAR}" = "hello" ]
}

# ============================================================================
# common::yq4-get
# ============================================================================

@test "common::yq4-get extracts value from yaml" {
  local yaml="name: test-recipe
kind: generic-runner"
  result=$(echo "${yaml}" | common::yq4-get '.name')
  [ "$result" = "test-recipe" ]
}

@test "common::yq4-get returns empty for null value" {
  local yaml="name: test"
  result=$(echo "${yaml}" | common::yq4-get '.nonexistent')
  [ -z "$result" ]
}

@test "common::yq4-get extracts nested value" {
  local yaml="meta:
  globalEnvVariable:
    MY_VAR: hello"
  result=$(echo "${yaml}" | common::yq4-get '.meta.globalEnvVariable.MY_VAR')
  [ "$result" = "hello" ]
}

# ============================================================================
# common::check_docker_status
# ============================================================================

@test "common::check_docker_status skips when PIPELINE_CHECK_DOCKER_STATUS is false" {
  export PIPELINE_CHECK_DOCKER_STATUS="false"
  run common::check_docker_status
  [ "$status" -eq 0 ]
}

# ============================================================================
# init-global-variables
# ============================================================================

@test "init-global-variables sets defaults" {
  unset REPLACE_RECIPE PIPELINE_MOCK PIPELINE_LOG_DEBUG PIPELINE_VALIDATE_INPUT
  init-global-variables
  [ "${REPLACE_RECIPE}" = "true" ]
  [ "${PIPELINE_MOCK}" = "false" ]
  [ "${PIPELINE_LOG_DEBUG}" = "false" ]
  [ "${PIPELINE_VALIDATE_INPUT}" = "true" ]
}

@test "init-global-variables preserves existing values" {
  export PIPELINE_MOCK="true"
  export PIPELINE_LOG_DEBUG="true"
  init-global-variables
  [ "${PIPELINE_MOCK}" = "true" ]
  [ "${PIPELINE_LOG_DEBUG}" = "true" ]
}

# ============================================================================
# common::export_variables
# ============================================================================

@test "common::export_variables exports key-value pairs from yaml" {
  local yaml="meta:
  globalEnvVariable:
    TEST_VAR_A: valueA
    TEST_VAR_B: valueB"
  common::export_variables ".meta.globalEnvVariable" "${yaml}"
  [ "${TEST_VAR_A}" = "valueA" ]
  [ "${TEST_VAR_B}" = "valueB" ]
}

@test "common::export_variables handles empty key gracefully" {
  local yaml="meta:
  other: value"
  run common::export_variables ".meta.globalEnvVariable" "${yaml}"
  [ "$status" -eq 0 ]
}

# ============================================================================
# common::replace_env_variables
# ============================================================================

@test "common::replace_env_variables substitutes env vars in recipe" {
  export MY_VALUE="replaced-value"
  local yaml='meta:
  globalEnvVariable:
    MY_VALUE: original
tasks:
  - name: "${MY_VALUE}"'
  common::replace_env_variables ".meta.globalEnvVariable" "${yaml}" "${TEST_TEMP_DIR}/output.yaml"
  local result=$(cat "${TEST_TEMP_DIR}/output.yaml")
  [[ "$result" == *"replaced-value"* ]]
}

@test "common::replace_env_variables skips when REPLACE_RECIPE is not true" {
  export REPLACE_RECIPE="false"
  local yaml='meta:
  globalEnvVariable:
    MY_VALUE: original
tasks:
  - name: "${MY_VALUE}"'
  common::replace_env_variables ".meta.globalEnvVariable" "${yaml}" "${TEST_TEMP_DIR}/output.yaml"
  # should still write the file (just without substitution)
  [ -f "${TEST_TEMP_DIR}/output.yaml" ]
}

# ============================================================================
# common::validate_input
# ============================================================================

@test "common::validate_input skips when PIPELINE_VALIDATE_INPUT is false" {
  export PIPELINE_VALIDATE_INPUT="false"
  run common::validate_input "any-content" "nonexistent.cue"
  [ "$status" -eq 0 ]
}

@test "common::validate_input skips when validation file does not exist" {
  export PIPELINE_VALIDATE_INPUT="true"
  run common::validate_input "any-content" "/nonexistent/check.cue"
  [ "$status" -eq 0 ]
}

# ============================================================================
# unset-aws-env
# ============================================================================

@test "unset-aws-env clears AWS vars when PIPELINE_USE_LOCAL_CREDS is not true" {
  export PIPELINE_USE_LOCAL_CREDS="false"
  export AWS_ACCESS_KEY_ID="test-key"
  export AWS_SECRET_ACCESS_KEY="test-secret"
  export AWS_SESSION_TOKEN="test-token"
  unset-aws-env
  [ -z "${AWS_ACCESS_KEY_ID}" ]
  [ -z "${AWS_SECRET_ACCESS_KEY}" ]
  [ -z "${AWS_SESSION_TOKEN}" ]
}

@test "unset-aws-env preserves AWS vars when PIPELINE_USE_LOCAL_CREDS is true" {
  export PIPELINE_USE_LOCAL_CREDS="true"
  export AWS_ACCESS_KEY_ID="test-key"
  unset-aws-env
  [ "${AWS_ACCESS_KEY_ID}" = "test-key" ]
}
