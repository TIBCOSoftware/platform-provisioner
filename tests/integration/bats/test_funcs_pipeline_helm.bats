#!/usr/bin/env bats
#
# Tests for charts/helm-install/scripts/_funcs_pipeline.sh
# Helm pipeline orchestration: run_task_helm, run_task_generic, run_task_array, process_recipe
#

load helpers/setup

setup() {
  setup_temp_dir
  source_functions
  source "${CHARTS_DIR}/common-dependency/scripts/_funcs_generic_runner.sh"
  source "${CHARTS_DIR}/helm-install/scripts/_funcs_helm.sh"
  source "${CHARTS_DIR}/helm-install/scripts/_funcs_pipeline.sh"
  cd "${TEST_TEMP_DIR}"
  export HELM_COMMAND_LINE="echo helm"
}

teardown() {
  cd /
  teardown_temp_dir
}

# ============================================================================
# run_task_array — preTasks / postTasks (generic-runner tasks in helm pipeline)
# ============================================================================

@test "run_task_array handles preTasks with conditions" {
  cat > "${TEST_TEMP_DIR}/recipe.yaml" <<'EOF'
preTasks:
  - condition: true
    script:
      fileName: script.sh
      content: |
        echo "pre-task"
  - condition: false
    script:
      content: |
        echo "skipped pre-task"
EOF
  run run_task_array "${TEST_TEMP_DIR}/recipe.yaml" ".preTasks" "run_task_generic"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Skipping task 1"* ]]
}

@test "run_task_array handles postTasks" {
  cat > "${TEST_TEMP_DIR}/recipe.yaml" <<'EOF'
postTasks:
  - condition: true
    script:
      fileName: script.sh
      content: |
        echo "post-task"
EOF
  run run_task_array "${TEST_TEMP_DIR}/recipe.yaml" ".postTasks" "run_task_generic"
  [ "$status" -eq 0 ]
}

@test "run_task_array skips when root element is empty array" {
  cat > "${TEST_TEMP_DIR}/recipe.yaml" <<'EOF'
preTasks: []
EOF
  run run_task_array "${TEST_TEMP_DIR}/recipe.yaml" ".preTasks" "run_task_generic"
  [ "$status" -eq 0 ]
}

@test "run_task_array skips when root element does not exist" {
  cat > "${TEST_TEMP_DIR}/recipe.yaml" <<'EOF'
helmCharts:
  - name: test
EOF
  run run_task_array "${TEST_TEMP_DIR}/recipe.yaml" ".preTasks" "run_task_generic"
  [ "$status" -eq 0 ]
}

# ============================================================================
# run_task_array — multiple conditions
# ============================================================================

@test "run_task_array evaluates each task condition independently" {
  cat > "${TEST_TEMP_DIR}/recipe.yaml" <<'EOF'
postTasks:
  - condition: false
    script:
      content: echo skipped-1
  - condition: false
    script:
      content: echo skipped-2
  - condition: true
    script:
      fileName: script.sh
      content: |
        echo "only-this-runs"
EOF
  run run_task_array "${TEST_TEMP_DIR}/recipe.yaml" ".postTasks" "run_task_generic"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Skipping task 0"* ]]
  [[ "$output" == *"Skipping task 1"* ]]
}

# ============================================================================
# run_task_helm (mocked helm-install::process_chart)
# ============================================================================

@test "run_task_helm calls helm-install::process_chart" {
  # Mock process_chart to just echo
  helm-install::process_chart() { echo "CHART_PROCESSED: $1"; return 0; }
  export -f helm-install::process_chart
  local task_content='name: my-chart
version: "1.0"
namespace: default'
  run run_task_helm 0 "${task_content}"
  [ "$status" -eq 0 ]
  [[ "$output" == *"CHART_PROCESSED"* ]]
}

@test "run_task_helm returns error when process_chart fails" {
  helm-install::process_chart() { return 1; }
  export -f helm-install::process_chart
  local task_content='name: fail-chart'
  run run_task_helm 0 "${task_content}"
  [ "$status" -ne 0 ]
  [[ "$output" == *"helm install error"* ]]
}

# ============================================================================
# run_task_array with helmCharts (dispatch to run_task_helm)
# ============================================================================

@test "run_task_array dispatches helmCharts to run_task_helm" {
  helm-install::process_chart() { echo "HELM_DISPATCHED"; return 0; }
  export -f helm-install::process_chart
  cat > "${TEST_TEMP_DIR}/recipe.yaml" <<'EOF'
helmCharts:
  - name: dispatched-chart
    version: "1.0"
    namespace: default
EOF
  run run_task_array "${TEST_TEMP_DIR}/recipe.yaml" ".helmCharts" "run_task_helm"
  [ "$status" -eq 0 ]
  [[ "$output" == *"HELM_DISPATCHED"* ]]
}

@test "run_task_array skips helmChart with condition false" {
  cat > "${TEST_TEMP_DIR}/recipe.yaml" <<'EOF'
helmCharts:
  - condition: false
    name: skipped-chart
    version: "1.0"
EOF
  run run_task_array "${TEST_TEMP_DIR}/recipe.yaml" ".helmCharts" "run_task_helm"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Skipping task 0"* ]]
}

# ============================================================================
# process_recipe (mocked — tests orchestration of preTasks/helmCharts/postTasks)
# ============================================================================

@test "process_recipe runs preTasks, helmCharts, postTasks in order" {
  # Mock source_file to avoid file-not-found for _funcs_helm.sh and _funcs_generic_runner.sh
  common::source_file() { return 0; }
  export -f common::source_file

  helm-install::process_chart() { echo "HELM_STEP"; return 0; }
  export -f helm-install::process_chart

  cat > "${TEST_TEMP_DIR}/recipe.yaml" <<'EOF'
preTasks:
  - condition: true
    script:
      fileName: script.sh
      content: |
        echo "PRE_STEP"
helmCharts:
  - name: test-chart
    version: "1.0"
    namespace: default
postTasks:
  - condition: true
    script:
      fileName: script.sh
      content: |
        echo "POST_STEP"
EOF
  run process_recipe "${TEST_TEMP_DIR}/recipe.yaml"
  [ "$status" -eq 0 ]
  [[ "$output" == *"PRE_STEP"* ]]
  [[ "$output" == *"HELM_STEP"* ]]
  [[ "$output" == *"POST_STEP"* ]]
}

@test "process_recipe succeeds with only helmCharts (no pre/post)" {
  common::source_file() { return 0; }
  export -f common::source_file

  helm-install::process_chart() { echo "ONLY_HELM"; return 0; }
  export -f helm-install::process_chart

  cat > "${TEST_TEMP_DIR}/recipe.yaml" <<'EOF'
helmCharts:
  - name: solo-chart
    version: "1.0"
    namespace: default
EOF
  run process_recipe "${TEST_TEMP_DIR}/recipe.yaml"
  [ "$status" -eq 0 ]
  [[ "$output" == *"ONLY_HELM"* ]]
}

@test "process_recipe fails when preTasks fail" {
  common::source_file() { return 0; }
  export -f common::source_file

  cat > "${TEST_TEMP_DIR}/recipe.yaml" <<'EOF'
preTasks:
  - condition: true
    script:
      fileName: script.sh
      content: |
        exit 1
helmCharts: []
EOF
  run process_recipe "${TEST_TEMP_DIR}/recipe.yaml"
  [ "$status" -ne 0 ]
}
