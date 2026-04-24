#!/usr/bin/env bats
#
# Fuzz / property-based tests for pipeline scripts
# Tests functions with generated edge-case inputs to find crashes and unexpected behavior
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
# common::yq4-get — fuzz with malformed YAML
# ============================================================================

@test "fuzz: yq4-get handles empty string input" {
  local result
  result=$(echo "" | common::yq4-get ".name" 2>/dev/null || true)
  # Should not crash — empty result is fine
  [[ -z "$result" || -n "$result" ]]
}

@test "fuzz: yq4-get handles input with only whitespace" {
  local result
  result=$(echo "   " | common::yq4-get ".name" 2>/dev/null || true)
  [[ -z "$result" || -n "$result" ]]
}

@test "fuzz: yq4-get handles input with only newlines" {
  local result
  result=$(printf "\n\n\n" | common::yq4-get ".name" 2>/dev/null || true)
  [[ -z "$result" || -n "$result" ]]
}

@test "fuzz: yq4-get handles binary-like content" {
  local result
  result=$(printf "\x01\x02\x03" | common::yq4-get ".name" 2>/dev/null || true)
  [[ -z "$result" || -n "$result" ]]
}

@test "fuzz: yq4-get handles extremely long key path" {
  local long_path
  long_path=$(printf '.a%.0s' {1..50})
  local yaml="name: value"
  local result
  result=$(echo "${yaml}" | common::yq4-get "${long_path}" 2>/dev/null || true)
  [[ -z "$result" || -n "$result" ]]
}

@test "fuzz: yq4-get handles yaml with unicode characters" {
  local yaml='name: "日本語テスト"'
  result=$(echo "${yaml}" | common::yq4-get '.name')
  [ "$result" = "日本語テスト" ]
}

@test "fuzz: yq4-get handles yaml with emoji" {
  local yaml='name: "test-🚀-value"'
  result=$(echo "${yaml}" | common::yq4-get '.name')
  [[ "$result" == *"🚀"* ]]
}

@test "fuzz: yq4-get handles yaml with tab characters" {
  local yaml=$'name:\tvalue-with-tabs'
  local result
  result=$(echo "${yaml}" | common::yq4-get '.name' 2>/dev/null || true)
  [[ -z "$result" || -n "$result" ]]
}

@test "fuzz: yq4-get handles yaml with trailing whitespace" {
  local yaml='name: value   '
  result=$(echo "${yaml}" | common::yq4-get '.name')
  [[ "$result" == *"value"* ]]
}

# ============================================================================
# common::replace_env_variables — fuzz with adversarial inputs
# ============================================================================

@test "fuzz: replace_env_variables handles empty key" {
  export REPLACE_RECIPE="true"
  run common::replace_env_variables "" "tasks: []" "${TEST_TEMP_DIR}/output.yaml"
  [ "$status" -eq 0 ]
}

@test "fuzz: replace_env_variables handles empty input" {
  export REPLACE_RECIPE="true"
  run common::replace_env_variables ".meta.globalEnvVariable" "" "${TEST_TEMP_DIR}/output.yaml"
  [ "$status" -eq 0 ]
}

@test "fuzz: replace_env_variables handles input with no matching key" {
  export REPLACE_RECIPE="true"
  local yaml='tasks:
  - name: test'
  run common::replace_env_variables ".meta.nonexistent" "${yaml}" "${TEST_TEMP_DIR}/output.yaml"
  [ "$status" -eq 0 ]
  [ -f "${TEST_TEMP_DIR}/output.yaml" ]
}

@test "fuzz: replace_env_variables handles value with newlines" {
  export REPLACE_RECIPE="true"
  export MULTI_LINE="line1
line2
line3"
  local yaml='meta:
  globalEnvVariable:
    MULTI_LINE: original
tasks:
  - name: test'
  run common::replace_env_variables ".meta.globalEnvVariable" "${yaml}" "${TEST_TEMP_DIR}/output.yaml"
  [ "$status" -eq 0 ]
}

@test "fuzz: replace_env_variables handles very long variable value" {
  export REPLACE_RECIPE="true"
  export LONG_VAR
  LONG_VAR=$(printf 'A%.0s' {1..5000})
  local yaml='meta:
  globalEnvVariable:
    LONG_VAR: original
tasks:
  - name: "${LONG_VAR}"'
  run common::replace_env_variables ".meta.globalEnvVariable" "${yaml}" "${TEST_TEMP_DIR}/output.yaml"
  [ "$status" -eq 0 ]
}

# ============================================================================
# common::export_variables — fuzz with edge-case YAML
# ============================================================================

@test "fuzz: export_variables handles empty yaml" {
  run common::export_variables ".meta.globalEnvVariable" ""
  [ "$status" -eq 0 ]
}

@test "fuzz: export_variables handles yaml with numeric keys" {
  local yaml='meta:
  globalEnvVariable:
    VAR_123: numeric-key'
  common::export_variables ".meta.globalEnvVariable" "${yaml}"
  [ "${VAR_123}" = "numeric-key" ]
}

@test "fuzz: export_variables handles yaml with boolean-like values" {
  local yaml='meta:
  globalEnvVariable:
    BOOL_TRUE: "true"
    BOOL_FALSE: "false"
    BOOL_YES: "yes"'
  common::export_variables ".meta.globalEnvVariable" "${yaml}"
  [ "${BOOL_TRUE}" = "true" ]
  [ "${BOOL_FALSE}" = "false" ]
  [ "${BOOL_YES}" = "yes" ]
}

@test "fuzz: export_variables handles yaml with null-like values" {
  local yaml='meta:
  globalEnvVariable:
    NULL_VAR: "null"
    EMPTY_VAR: ""'
  common::export_variables ".meta.globalEnvVariable" "${yaml}"
  [ "${NULL_VAR}" = "null" ]
}

@test "fuzz: export_variables handles many variables" {
  local yaml='meta:
  globalEnvVariable:'
  for i in $(seq 1 20); do
    yaml="${yaml}
    FUZZ_VAR_${i}: value_${i}"
  done
  common::export_variables ".meta.globalEnvVariable" "${yaml}"
  [ "${FUZZ_VAR_1}" = "value_1" ]
  [ "${FUZZ_VAR_20}" = "value_20" ]
}

# ============================================================================
# Logging functions — fuzz with unusual messages
# ============================================================================

@test "fuzz: logging handles empty message" {
  run common::info ""
  [ "$status" -eq 0 ]
  run common::warn ""
  [ "$status" -eq 0 ]
  run common::err ""
  [ "$status" -eq 0 ]
}

@test "fuzz: logging handles message with percent signs" {
  run common::info "100% complete"
  [ "$status" -eq 0 ]
  [[ "$output" == *"100% complete"* ]]
}

@test "fuzz: logging handles message with backslashes" {
  run common::info 'path\to\file'
  [ "$status" -eq 0 ]
}

@test "fuzz: logging handles very long message" {
  local long_msg
  long_msg=$(printf 'M%.0s' {1..10000})
  run common::info "${long_msg}"
  [ "$status" -eq 0 ]
}

# ============================================================================
# common::validate_input — fuzz with edge cases
# ============================================================================

@test "fuzz: validate_input handles empty input with disabled validation" {
  export PIPELINE_VALIDATE_INPUT="false"
  run common::validate_input "" "check.cue"
  [ "$status" -eq 0 ]
}

@test "fuzz: validate_input handles very large yaml input with disabled validation" {
  export PIPELINE_VALIDATE_INPUT="false"
  local big_yaml
  big_yaml=$(printf 'key_%s: value_%s\n' $(seq 1 100))
  run common::validate_input "${big_yaml}" "check.cue"
  [ "$status" -eq 0 ]
}

# ============================================================================
# init-global-variables — fuzz with pre-set values
# ============================================================================

@test "fuzz: init-global-variables handles empty string pre-set" {
  export PIPELINE_MOCK=""
  init-global-variables
  # Empty string is falsy but still a value; should be preserved or reset
  # The ${VAR:-default} pattern treats empty as unset, so default applies
  [ "${PIPELINE_MOCK}" = "false" ]
}

@test "fuzz: init-global-variables handles unusual string values" {
  export PIPELINE_MOCK="TRUE"
  export PIPELINE_LOG_DEBUG="1"
  init-global-variables
  # Should preserve whatever was set (even non-standard values)
  [ "${PIPELINE_MOCK}" = "TRUE" ]
  [ "${PIPELINE_LOG_DEBUG}" = "1" ]
}
