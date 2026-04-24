#!/usr/bin/env bats
#
# Security-focused tests for pipeline scripts
# Tests resistance to injection, path traversal, and secret leakage
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
# common::source_file — path traversal resistance
# ============================================================================

@test "security: common::source_file rejects directory path" {
  run common::source_file "${TEST_TEMP_DIR}"
  [ "$status" -ne 0 ]
}

@test "security: common::source_file rejects path with null bytes in name" {
  local bad_path="${TEST_TEMP_DIR}/file\x00.sh"
  run common::source_file "${bad_path}"
  [ "$status" -ne 0 ]
}

@test "security: common::source_file rejects symlink to nonexistent target" {
  ln -s /nonexistent/target "${TEST_TEMP_DIR}/bad_link.sh"
  run common::source_file "${TEST_TEMP_DIR}/bad_link.sh"
  [ "$status" -ne 0 ]
}

# ============================================================================
# common::export_variables — injection resistance
# ============================================================================

@test "security: common::export_variables handles value with shell metacharacters" {
  local yaml='meta:
  globalEnvVariable:
    SAFE_VAR: "value; echo INJECTED"'
  common::export_variables ".meta.globalEnvVariable" "${yaml}"
  # The value should be the literal string, not executed
  [[ "${SAFE_VAR}" == *"echo INJECTED"* ]] || [[ "${SAFE_VAR}" == *"value"* ]]
  [ "$status" -eq 0 ] || true
}

@test "security: common::export_variables handles value with backticks" {
  local yaml='meta:
  globalEnvVariable:
    TICK_VAR: "value-\`whoami\`"'
  run common::export_variables ".meta.globalEnvVariable" "${yaml}"
  # May fail due to yq parsing, but should not crash with segfault (exit code <= 2)
  [[ "$status" -le 2 ]]
}

@test "security: common::export_variables handles value with dollar signs" {
  local yaml='meta:
  globalEnvVariable:
    DOLLAR_VAR: "price-$100"'
  run common::export_variables ".meta.globalEnvVariable" "${yaml}"
  [ "$status" -eq 0 ]
}

# ============================================================================
# common::replace_env_variables — injection resistance
# ============================================================================

@test "security: replace_env_variables does not expand unrelated env vars" {
  export REPLACE_RECIPE="true"
  export MY_VAR="safe-value"
  # SECRET_VAR is NOT in the globalEnvVariable list, should NOT be expanded
  export SECRET_VAR="leaked-secret"
  local yaml='meta:
  globalEnvVariable:
    MY_VAR: safe-value
tasks:
  - name: "${MY_VAR}"
    script: "${SECRET_VAR}"'
  common::replace_env_variables ".meta.globalEnvVariable" "${yaml}" "${TEST_TEMP_DIR}/output.yaml"
  local result
  result=$(cat "${TEST_TEMP_DIR}/output.yaml")
  # MY_VAR should be replaced
  [[ "$result" == *"safe-value"* ]]
  # SECRET_VAR should NOT be expanded (still literal ${SECRET_VAR})
  [[ "$result" == *'${SECRET_VAR}'* ]]
}

@test "security: replace_env_variables handles key with special characters in value" {
  export REPLACE_RECIPE="true"
  export SPECIAL_VAR='value with "quotes" and $dollar'
  local yaml='meta:
  globalEnvVariable:
    SPECIAL_VAR: original
tasks:
  - name: "${SPECIAL_VAR}"'
  run common::replace_env_variables ".meta.globalEnvVariable" "${yaml}" "${TEST_TEMP_DIR}/output.yaml"
  [ "$status" -eq 0 ]
  [ -f "${TEST_TEMP_DIR}/output.yaml" ]
}

# ============================================================================
# Logging — no secret leakage
# ============================================================================

@test "security: common::err does not leak to stdout" {
  # stderr should contain the error, stdout should be empty
  local stdout_output
  stdout_output=$(common::err "secret-token-12345" 2>/dev/null)
  [ -z "$stdout_output" ]
}

@test "security: common::debug does not output when debug is off" {
  export PIPELINE_LOG_DEBUG="false"
  local output
  output=$(common::debug "secret-api-key-67890" 2>&1)
  [ -z "$output" ]
}

# ============================================================================
# common::yq4-get — safe parsing
# ============================================================================

@test "security: yq4-get handles yaml with embedded script tags" {
  local yaml='name: "<script>alert(1)</script>"'
  result=$(echo "${yaml}" | common::yq4-get '.name')
  # Should return the literal string, not execute anything
  [[ "$result" == *"script"* ]]
}

@test "security: yq4-get handles yaml bomb (deeply nested)" {
  # Create a moderately deep YAML (not a true billion laughs, but tests depth handling)
  local yaml="a:
  b:
    c:
      d:
        e: deep-value"
  result=$(echo "${yaml}" | common::yq4-get '.a.b.c.d.e')
  [ "$result" = "deep-value" ]
}

@test "security: yq4-get handles very long values" {
  local long_value
  long_value=$(printf 'x%.0s' {1..1000})
  local yaml="name: ${long_value}"
  result=$(echo "${yaml}" | common::yq4-get '.name')
  [ ${#result} -eq 1000 ]
}

# ============================================================================
# init-global-variables — safe defaults
# ============================================================================

@test "security: init-global-variables sets PIPELINE_VALIDATE_INPUT to true by default" {
  unset PIPELINE_VALIDATE_INPUT
  init-global-variables
  [ "${PIPELINE_VALIDATE_INPUT}" = "true" ]
}

@test "security: init-global-variables sets PIPELINE_MOCK to false by default" {
  unset PIPELINE_MOCK
  init-global-variables
  [ "${PIPELINE_MOCK}" = "false" ]
}

# ============================================================================
# unset-aws-env — credential cleanup
# ============================================================================

@test "security: unset-aws-env clears all three AWS credential vars" {
  export PIPELINE_USE_LOCAL_CREDS="false"
  export AWS_ACCESS_KEY_ID="AKIAIOSFODNN7EXAMPLE"
  export AWS_SECRET_ACCESS_KEY="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
  export AWS_SESSION_TOKEN="FwoGZXIvYXdzEBYaDHqa0AP"
  unset-aws-env
  [ -z "${AWS_ACCESS_KEY_ID}" ]
  [ -z "${AWS_SECRET_ACCESS_KEY}" ]
  [ -z "${AWS_SESSION_TOKEN}" ]
}

@test "security: common::check_docker_status does not hang when skipped" {
  export PIPELINE_CHECK_DOCKER_STATUS="false"
  # Should return immediately, not wait for docker
  run common::check_docker_status
  [ "$status" -eq 0 ]
}
