#!/usr/bin/env bats
#
# Tests for charts/common-dependency/scripts/_funcs_generic_runner.sh
# Task setup functions: repo, payload, script handling
#

load helpers/setup

setup() {
  setup_temp_dir
  source_functions
  source "${CHARTS_DIR}/common-dependency/scripts/_funcs_generic_runner.sh"
  cd "${TEST_TEMP_DIR}"
}

teardown() {
  cd /
  teardown_temp_dir
}

# ============================================================================
# generic-runner::setup_script
# ============================================================================

@test "setup_script creates script from content" {
  local script_section='fileName: test.sh
content: |
  echo "hello world"'
  run generic-runner::setup_script "${script_section}"
  [ "$status" -eq 0 ]
  [ -f "test.sh" ]
  [ -x "test.sh" ]
  [[ "$(cat test.sh)" == *"hello world"* ]]
}

@test "setup_script uses default script.sh name when fileName not set" {
  local script_section='content: |
  echo "default name"'
  run generic-runner::setup_script "${script_section}"
  [ "$status" -eq 0 ]
  [ -f "script.sh" ]
  [ -x "script.sh" ]
}

@test "setup_script fails when no content and no file exists" {
  run generic-runner::setup_script ""
  [ "$status" -ne 0 ]
}

@test "setup_script uses existing file when no content provided" {
  echo '#!/bin/bash' > script.sh
  chmod +x script.sh
  run generic-runner::setup_script ""
  [ "$status" -eq 0 ]
  [ -x "script.sh" ]
}

@test "setup_script fails when content would overwrite existing file" {
  echo "existing" > myfile.sh
  local script_section='fileName: myfile.sh
content: |
  echo "new content"'
  run generic-runner::setup_script "${script_section}"
  [ "$status" -ne 0 ]
}

@test "setup_script handles base64 encoded content" {
  local encoded=$(echo 'echo "decoded"' | base64)
  local script_section="base64Encoded: true
fileName: b64.sh
content: |
  ${encoded}"
  run generic-runner::setup_script "${script_section}"
  [ "$status" -eq 0 ]
  [ -f "b64.sh" ]
  [[ "$(cat b64.sh)" == *"decoded"* ]]
}

@test "setup_script uses PIPELINE_RUNNER_SCRIPT_NAME_SH env" {
  echo '#!/bin/bash' > custom.sh
  chmod +x custom.sh
  export PIPELINE_RUNNER_SCRIPT_NAME_SH="custom.sh"
  run generic-runner::setup_script ""
  [ "$status" -eq 0 ]
  unset PIPELINE_RUNNER_SCRIPT_NAME_SH
}

# ============================================================================
# generic-runner::setup_payload
# ============================================================================

@test "setup_payload creates payload file" {
  local payload_section='fileName: data.yaml
content: |
  key: value'
  run generic-runner::setup_payload "${payload_section}"
  [ "$status" -eq 0 ]
  [ -f "data.yaml" ]
  [[ "$(cat data.yaml)" == *"key: value"* ]]
}

@test "setup_payload uses default recipe.yaml name" {
  local payload_section='content: |
  key: value'
  run generic-runner::setup_payload "${payload_section}"
  [ "$status" -eq 0 ]
  [ -f "recipe.yaml" ]
}

@test "setup_payload skips when empty" {
  run generic-runner::setup_payload ""
  [ "$status" -eq 0 ]
}

@test "setup_payload handles base64 encoded content" {
  local encoded=$(echo 'decoded-payload' | base64)
  local payload_section="base64Encoded: true
fileName: payload.txt
content: |
  ${encoded}"
  run generic-runner::setup_payload "${payload_section}"
  [ "$status" -eq 0 ]
  [ -f "payload.txt" ]
  [[ "$(cat payload.txt)" == *"decoded-payload"* ]]
}

# ============================================================================
# generic-runner::setup_repo
# ============================================================================

@test "setup_repo skips when empty" {
  run generic-runner::setup_repo ""
  [ "$status" -eq 0 ]
}
