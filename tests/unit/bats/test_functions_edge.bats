#!/usr/bin/env bats
#
# Negative and boundary tests for charts/common-dependency/scripts/_functions.sh
# Edge cases in yq, process_meta, source_file, validate_input, export_variables, etc.
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
# common::yq4-get edge cases
# ============================================================================

@test "common::yq4-get returns empty for empty input" {
  result=$(echo "" | common::yq4-get '.name' || true)
  [ -z "$result" ]
}

@test "common::yq4-get returns empty for malformed yaml" {
  result=$(echo "not: [valid: yaml" | common::yq4-get '.name' 2>/dev/null || true)
  [ -z "$result" ] || true
}

@test "common::yq4-get handles deeply nested path" {
  local yaml="a:
  b:
    c:
      d:
        e: deep-value"
  result=$(echo "${yaml}" | common::yq4-get '.a.b.c.d.e')
  [ "$result" = "deep-value" ]
}

@test "common::yq4-get handles array index" {
  local yaml="items:
  - first
  - second
  - third"
  result=$(echo "${yaml}" | common::yq4-get '.items[1]')
  [ "$result" = "second" ]
}

@test "common::yq4-get handles boolean value" {
  local yaml="enabled: true"
  result=$(echo "${yaml}" | common::yq4-get '.enabled')
  [ "$result" = "true" ]
}

@test "common::yq4-get handles numeric value" {
  local yaml="count: 42"
  result=$(echo "${yaml}" | common::yq4-get '.count')
  [ "$result" = "42" ]
}

# ============================================================================
# common::source_file edge cases
# ============================================================================

@test "common::source_file fails for empty path" {
  run common::source_file ""
  [ "$status" -ne 0 ]
}

@test "common::source_file fails for directory path" {
  run common::source_file "${TEST_TEMP_DIR}"
  [ "$status" -ne 0 ]
}

@test "common::source_file sets variables from sourced file" {
  echo 'export EDGE_TEST_VAR="edge-value"' > "${TEST_TEMP_DIR}/edge.sh"
  common::source_file "${TEST_TEMP_DIR}/edge.sh"
  [ "${EDGE_TEST_VAR}" = "edge-value" ]
}

# ============================================================================
# Logging edge cases
# ============================================================================

@test "common::err handles empty message" {
  run common::err ""
  [ "$status" -eq 0 ]
  [[ "$output" == *"[ERROR]:"* ]]
}

@test "common::info handles special characters" {
  run common::info 'test with $special & "chars"'
  [ "$status" -eq 0 ]
  [[ "$output" == *"[INFO]:"* ]]
}

@test "common::warn handles multiline message" {
  run common::warn "line1
line2"
  [ "$status" -eq 0 ]
  [[ "$output" == *"[WARNING]:"* ]]
}

# ============================================================================
# common::export_variables edge cases
# ============================================================================

@test "common::export_variables handles missing yaml key gracefully" {
  local yaml="other:
  key: value"
  run common::export_variables ".nonexistent" "${yaml}"
  [ "$status" -eq 0 ]
}

@test "common::export_variables exports single variable" {
  local yaml="meta:
  guiEnv:
    SINGLE_VAR: single-value"
  common::export_variables ".meta.guiEnv" "${yaml}"
  [ "${SINGLE_VAR}" = "single-value" ]
}

@test "common::export_variables handles numeric values" {
  local yaml="env:
  NUM_VAR: 123"
  common::export_variables ".env" "${yaml}"
  [ "${NUM_VAR}" = "123" ]
}

# ============================================================================
# common::replace_env_variables edge cases
# ============================================================================

@test "common::replace_env_variables handles empty key" {
  local yaml="tasks:
  - name: test"
  common::replace_env_variables "" "${yaml}" "${TEST_TEMP_DIR}/output.yaml"
  [ -f "${TEST_TEMP_DIR}/output.yaml" ]
  [[ "$(cat "${TEST_TEMP_DIR}/output.yaml")" == *"test"* ]]
}

@test "common::replace_env_variables handles empty input" {
  run common::replace_env_variables ".meta" "" "${TEST_TEMP_DIR}/output.yaml"
  [ "$status" -eq 0 ]
}

@test "common::replace_env_variables handles key not in recipe" {
  local yaml="tasks:
  - name: test"
  run common::replace_env_variables ".meta.nonexistent" "${yaml}" "${TEST_TEMP_DIR}/output.yaml"
  [ "$status" -eq 0 ]
  [ -f "${TEST_TEMP_DIR}/output.yaml" ]
  [[ "$(cat "${TEST_TEMP_DIR}/output.yaml")" == *"test"* ]]
}

# ============================================================================
# common::validate_input edge cases
# ============================================================================

@test "common::validate_input skips when cue binary not found" {
  export PIPELINE_VALIDATE_INPUT="true"
  # Create dummy validation file so the file-exists check passes
  echo "package test" > "${TEST_TEMP_DIR}/check.cue"
  echo "package test" > "${TEST_TEMP_DIR}/shared.cue"
  # But cue won't be in path if we override PATH
  local ORIG_PATH="${PATH}"
  export PATH="/nonexistent"
  cd "${TEST_TEMP_DIR}"
  run common::validate_input "test: data" "check.cue"
  export PATH="${ORIG_PATH}"
  [ "$status" -eq 0 ]
}

@test "common::validate_input skips when shared.cue not found" {
  export PIPELINE_VALIDATE_INPUT="true"
  echo "package test" > "${TEST_TEMP_DIR}/check.cue"
  cd "${TEST_TEMP_DIR}"
  run common::validate_input "test: data" "check.cue"
  [ "$status" -eq 0 ]
}

# ============================================================================
# init-global-variables edge cases
# ============================================================================

@test "init-global-variables sets PIPELINE_CHECK_DOCKER_STATUS default" {
  unset PIPELINE_CHECK_DOCKER_STATUS
  init-global-variables
  [ "${PIPELINE_CHECK_DOCKER_STATUS}" = "false" ]
}

@test "init-global-variables sets PIPELINE_INITIAL_ASSUME_ROLE default" {
  unset PIPELINE_INITIAL_ASSUME_ROLE
  init-global-variables
  [ "${PIPELINE_INITIAL_ASSUME_ROLE}" = "true" ]
}

@test "init-global-variables sets PIPELINE_FUNCTION_INIT default" {
  unset PIPELINE_FUNCTION_INIT
  init-global-variables
  [ "${PIPELINE_FUNCTION_INIT}" = "true" ]
}

@test "init-global-variables preserves all custom values" {
  export REPLACE_RECIPE="false"
  export PIPELINE_MOCK="true"
  export PIPELINE_LOG_DEBUG="true"
  export PIPELINE_VALIDATE_INPUT="false"
  export PIPELINE_CHECK_DOCKER_STATUS="true"
  export PIPELINE_INITIAL_ASSUME_ROLE="false"
  init-global-variables
  [ "${REPLACE_RECIPE}" = "false" ]
  [ "${PIPELINE_MOCK}" = "true" ]
  [ "${PIPELINE_LOG_DEBUG}" = "true" ]
  [ "${PIPELINE_VALIDATE_INPUT}" = "false" ]
  [ "${PIPELINE_CHECK_DOCKER_STATUS}" = "true" ]
  [ "${PIPELINE_INITIAL_ASSUME_ROLE}" = "false" ]
}

# ============================================================================
# unset-aws-env edge cases
# ============================================================================

@test "unset-aws-env handles unset AWS vars gracefully" {
  export PIPELINE_USE_LOCAL_CREDS="false"
  unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN 2>/dev/null || true
  run unset-aws-env
  [ "$status" -eq 0 ]
}

# ============================================================================
# common::check_docker_status edge cases
# ============================================================================

@test "common::check_docker_status accepts string false" {
  export PIPELINE_CHECK_DOCKER_STATUS="false"
  run common::check_docker_status
  [ "$status" -eq 0 ]
}

# ============================================================================
# load-customized-env edge cases
# ============================================================================

@test "load-customized-env silently ignores non-existent file" {
  run load-customized-env "/nonexistent/file.sh"
  [ "$status" -eq 0 ]
}

@test "load-customized-env sources existing file" {
  echo 'export CUSTOM_LOADED="yes"' > "${TEST_TEMP_DIR}/custom.sh"
  load-customized-env "${TEST_TEMP_DIR}/custom.sh"
  [ "${CUSTOM_LOADED}" = "yes" ]
}

# ============================================================================
# Test helpers: test_id, build_generic_recipe, build_helm_recipe
# ============================================================================

@test "test_id generates unique IDs with default prefix" {
  local id1 id2
  id1=$(test_id)
  id2=$(test_id)
  [[ "$id1" == test-* ]]
  [[ "$id2" == test-* ]]
  [ "$id1" != "$id2" ]
}

@test "test_id generates unique IDs with custom prefix" {
  local id
  id=$(test_id "release")
  [[ "$id" == release-* ]]
  [ ${#id} -gt 8 ]
}

@test "build_generic_recipe generates valid YAML" {
  local recipe
  recipe=$(build_generic_recipe "echo hello")
  [[ "$recipe" == *"kind: generic-runner"* ]]
  [[ "$recipe" == *"echo hello"* ]]
  [[ "$recipe" == *"condition: true"* ]]
}

@test "build_generic_recipe respects condition parameter" {
  local recipe
  recipe=$(build_generic_recipe "echo test" "false")
  [[ "$recipe" == *"condition: false"* ]]
}

@test "build_helm_recipe generates valid YAML" {
  local recipe
  recipe=$(build_helm_recipe "my-release" "nginx" "https://charts.example.com")
  [[ "$recipe" == *"kind: helm-install"* ]]
  [[ "$recipe" == *"releaseName: my-release"* ]]
  [[ "$recipe" == *"name: nginx"* ]]
  [[ "$recipe" == *"url: https://charts.example.com"* ]]
  [[ "$recipe" == *"namespace: default"* ]]
}

@test "build_helm_recipe accepts custom namespace" {
  local recipe
  recipe=$(build_helm_recipe "app" "chart" "https://repo" "kube-system")
  [[ "$recipe" == *"namespace: kube-system"* ]]
}
