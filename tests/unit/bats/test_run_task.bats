#!/usr/bin/env bats
#
# Tests for generic-runner::run_task
# Full task lifecycle: script setup, execution, skip, ignoreErrors, payload, cleanup
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
# Basic task execution
# ============================================================================

@test "run_task executes script from content" {
  local task_content='script:
  fileName: script.sh
  content: |
    echo "hello from task"'
  run generic-runner::run_task 0 "${task_content}"
  [ "$status" -eq 0 ]
  [[ "$output" == *"hello from task"* ]]
}

@test "run_task prints task name when provided" {
  local task_content='name: my-test-task
script:
  fileName: script.sh
  content: |
    echo "named"'
  run generic-runner::run_task 0 "${task_content}"
  [ "$status" -eq 0 ]
  [[ "$output" == *"my-test-task"* ]]
}

@test "run_task prints task index when no name" {
  local task_content='script:
  fileName: script.sh
  content: |
    echo "unnamed"'
  run generic-runner::run_task 0 "${task_content}"
  [ "$status" -eq 0 ]
  [[ "$output" == *"running task #0"* ]]
}

# ============================================================================
# Skip
# ============================================================================

@test "run_task skips when script.skip is true" {
  local task_content='script:
  skip: true
  content: |
    echo "should not run"'
  run generic-runner::run_task 0 "${task_content}"
  [ "$status" -eq 0 ]
  [[ "$output" == *"skipping"* ]]
  [[ "$output" != *"should not run"* ]]
}

# ============================================================================
# ignoreErrors
# ============================================================================

@test "run_task succeeds when ignoreErrors is true and script fails" {
  local task_content='script:
  ignoreErrors: true
  fileName: script.sh
  content: |
    exit 1'
  run generic-runner::run_task 0 "${task_content}"
  [ "$status" -eq 0 ]
}

@test "run_task fails when script exits non-zero" {
  local task_content='script:
  fileName: script.sh
  content: |
    exit 1'
  run generic-runner::run_task 0 "${task_content}"
  [ "$status" -ne 0 ]
}

# ============================================================================
# Cleanup
# ============================================================================

@test "run_task cleans up temp task directory" {
  local task_content='script:
  fileName: script.sh
  content: |
    echo cleanup-test'
  run generic-runner::run_task 0 "${task_content}"
  [ "$status" -eq 0 ]
  [ ! -d "${TEST_TEMP_DIR}/task-0-0" ]
}

# ============================================================================
# Payload
# ============================================================================

@test "run_task creates payload file for script" {
  local task_content='script:
  fileName: script.sh
  content: |
    cat recipe.yaml
payload:
  fileName: recipe.yaml
  content: |
    mykey: myvalue'
  run generic-runner::run_task 0 "${task_content}"
  [ "$status" -eq 0 ]
  [[ "$output" == *"mykey: myvalue"* ]]
}

# ============================================================================
# Default file name
# ============================================================================

@test "run_task uses script.sh as default file name" {
  local task_content='script:
  content: |
    echo "default-name"'
  run generic-runner::run_task 0 "${task_content}"
  [ "$status" -eq 0 ]
  [[ "$output" == *"default-name"* ]]
}

# ============================================================================
# Task index
# ============================================================================

@test "run_task uses correct task index" {
  local task_content='script:
  fileName: script.sh
  content: |
    echo "task-5"'
  run generic-runner::run_task 5 "${task_content}"
  [ "$status" -eq 0 ]
  [[ "$output" == *"running task #5"* ]]
  [ ! -d "${TEST_TEMP_DIR}/task-5-0" ]
}

# ============================================================================
# Finish message
# ============================================================================

@test "run_task prints finish message on success" {
  local task_content='script:
  fileName: script.sh
  content: |
    echo "done"'
  run generic-runner::run_task 0 "${task_content}"
  [ "$status" -eq 0 ]
  [[ "$output" == *"finish task #0"* ]]
}
