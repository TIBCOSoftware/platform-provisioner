#!/usr/bin/env bats
#
# Tests for charts/generic-runner/scripts/_funcs_pipeline.sh
# Pipeline orchestration: run_task_generic, run_task_array, process_recipe
#

load helpers/setup

setup() {
  setup_temp_dir
  source_functions
  source "${CHARTS_DIR}/common-dependency/scripts/_funcs_generic_runner.sh"
  source "${CHARTS_DIR}/generic-runner/scripts/_funcs_pipeline.sh"
  cd "${TEST_TEMP_DIR}"
}

teardown() {
  cd /
  teardown_temp_dir
}

# ============================================================================
# run_task_array — condition handling
# ============================================================================

@test "run_task_array skips task when condition is false" {
  cat > "${TEST_TEMP_DIR}/recipe.yaml" <<'EOF'
tasks:
  - condition: false
    script:
      content: |
        echo "should not run"
EOF
  run run_task_array "${TEST_TEMP_DIR}/recipe.yaml" ".tasks" "run_task_generic"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Skipping task 0"* ]]
}

@test "run_task_array runs task when condition is true" {
  cat > "${TEST_TEMP_DIR}/recipe.yaml" <<'EOF'
tasks:
  - condition: true
    script:
      fileName: script.sh
      content: |
        echo "hello from task"
EOF
  run run_task_array "${TEST_TEMP_DIR}/recipe.yaml" ".tasks" "run_task_generic"
  [ "$status" -eq 0 ]
}

@test "run_task_array defaults condition to true when not specified" {
  cat > "${TEST_TEMP_DIR}/recipe.yaml" <<'EOF'
tasks:
  - script:
      fileName: script.sh
      content: |
        echo "no condition set"
EOF
  run run_task_array "${TEST_TEMP_DIR}/recipe.yaml" ".tasks" "run_task_generic"
  [ "$status" -eq 0 ]
}

@test "run_task_array handles zero tasks gracefully" {
  cat > "${TEST_TEMP_DIR}/recipe.yaml" <<'EOF'
tasks: []
EOF
  run run_task_array "${TEST_TEMP_DIR}/recipe.yaml" ".tasks" "run_task_generic"
  [ "$status" -eq 0 ]
}

@test "run_task_array skips empty task content" {
  cat > "${TEST_TEMP_DIR}/recipe.yaml" <<'EOF'
tasks:
  -
EOF
  run run_task_array "${TEST_TEMP_DIR}/recipe.yaml" ".tasks" "run_task_generic"
  [ "$status" -eq 0 ]
}

# ============================================================================
# run_task_array — multiple tasks
# ============================================================================

@test "run_task_array processes multiple tasks in order" {
  cat > "${TEST_TEMP_DIR}/recipe.yaml" <<'EOF'
tasks:
  - condition: true
    script:
      fileName: script.sh
      content: |
        echo "task-1"
  - condition: false
    script:
      content: |
        echo "task-2-skipped"
  - condition: true
    script:
      fileName: script.sh
      content: |
        echo "task-3"
EOF
  run run_task_array "${TEST_TEMP_DIR}/recipe.yaml" ".tasks" "run_task_generic"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Skipping task 1"* ]]
}

# ============================================================================
# run_task_array — missing root element
# ============================================================================

@test "run_task_array handles missing root element" {
  cat > "${TEST_TEMP_DIR}/recipe.yaml" <<'EOF'
other: value
EOF
  run run_task_array "${TEST_TEMP_DIR}/recipe.yaml" ".tasks" "run_task_generic"
  [ "$status" -eq 0 ]
}
