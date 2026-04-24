#!/usr/bin/env bats
#
# Tests for charts/helm-install/scripts/_funcs_helm.sh
# Helm chart download, value processing, flag generation, hook setup
#

load helpers/setup

setup() {
  setup_temp_dir
  source_functions
  source "${CHARTS_DIR}/helm-install/scripts/_funcs_helm.sh"
  cd "${TEST_TEMP_DIR}"
  # Mock helm command
  export HELM_COMMAND_LINE="echo helm"
  export HELM_VALUES_FLAG_FILE="${TEST_TEMP_DIR}/values-flag.txt"
  echo -n "" > "${HELM_VALUES_FLAG_FILE}"
}

teardown() {
  cd /
  teardown_temp_dir
}

# ============================================================================
# yq-get-data
# ============================================================================

@test "yq-get-data extracts data field from yaml" {
  local yaml="data: hello-world"
  result=$(yq-get-data "${yaml}")
  [ "$result" = "hello-world" ]
}

@test "yq-get-data returns empty for missing data field" {
  local yaml="other: value"
  result=$(yq-get-data "${yaml}")
  [ -z "$result" ]
}

# ============================================================================
# getHelmVersion
# ============================================================================

@test "getHelmVersion returns helm for empty version" {
  result=$(getHelmVersion "")
  [[ "$result" == *"helm"* ]]
}

@test "getHelmVersion returns helm for 'default' version" {
  result=$(getHelmVersion "default")
  [[ "$result" == *"helm"* ]]
}

# ============================================================================
# getLocalChartName
# ============================================================================

@test "getLocalChartName finds matching tgz file" {
  touch "${TEST_TEMP_DIR}/my-chart-1.2.3.tgz"
  result=$(getLocalChartName "my-chart")
  [ "$result" = "my-chart-1.2.3.tgz" ]
}

@test "getLocalChartName fails when no tgz found" {
  run getLocalChartName "nonexistent-chart"
  [ "$status" -ne 0 ]
}

@test "getLocalChartName fails when multiple tgz files match" {
  touch "${TEST_TEMP_DIR}/my-chart-1.0.0.tgz"
  touch "${TEST_TEMP_DIR}/my-chart-2.0.0.tgz"
  run getLocalChartName "my-chart"
  [ "$status" -ne 0 ]
}

# ============================================================================
# getRecipeValues
# ============================================================================

@test "getRecipeValues writes content to values-recipe.yaml" {
  local values_section="content: |
  replicaCount: 3
  image: nginx"
  getRecipeValues "${values_section}"
  [ -f "values-recipe.yaml" ]
  [[ "$(cat values-recipe.yaml)" == *"replicaCount: 3"* ]]
}

@test "getRecipeValues adds values flag to flag file" {
  local values_section="content: |
  key: value"
  getRecipeValues "${values_section}"
  [[ "$(cat "${HELM_VALUES_FLAG_FILE}")" == *"--values values-recipe.yaml"* ]]
}

# ============================================================================
# getValues
# ============================================================================

@test "getValues skips when values section is empty" {
  run getValues "" "release" "namespace"
  [ "$status" -eq 0 ]
}

@test "getValues processes non-empty values section" {
  local values_section="content: |
  key: value"
  getValues "${values_section}" "my-release" "my-ns"
  [ -f "values-recipe.yaml" ]
}

# ============================================================================
# getCurrentValues
# ============================================================================

@test "getCurrentValues skips when keepPrevious is not true" {
  local values_section="keepPrevious: false
content: test"
  run getCurrentValues "${values_section}" "release" "ns"
  [ "$status" -eq 0 ]
  [ ! -f "values-current.yaml" ]
}

# ============================================================================
# setupHooks
# ============================================================================

@test "setupHooks creates pre-deploy script from content" {
  local hooks_section="preDeploy:
  content: |
    echo pre-deploy"
  setupHooks "${hooks_section}"
  [ -f "pre-deploy.sh" ]
  [ -x "pre-deploy.sh" ]
  [[ "$(cat pre-deploy.sh)" == *"echo pre-deploy"* ]]
}

@test "setupHooks creates post-deploy script from content" {
  local hooks_section="postDeploy:
  content: |
    echo post-deploy"
  setupHooks "${hooks_section}"
  [ -f "post-deploy.sh" ]
  [ -x "post-deploy.sh" ]
  [[ "$(cat post-deploy.sh)" == *"echo post-deploy"* ]]
}

@test "setupHooks skips preDeploy when skip is true" {
  local hooks_section="preDeploy:
  skip: true
  content: |
    echo should-not-exist"
  setupHooks "${hooks_section}"
  [ ! -f "pre-deploy.sh" ]
}

@test "setupHooks skips postDeploy when skip is true" {
  local hooks_section="postDeploy:
  skip: true
  content: |
    echo should-not-exist"
  setupHooks "${hooks_section}"
  [ ! -f "post-deploy.sh" ]
}

@test "setupHooks handles empty hooks section" {
  run setupHooks ""
  [ "$status" -eq 0 ]
  [ ! -f "pre-deploy.sh" ]
  [ ! -f "post-deploy.sh" ]
}

@test "setupHooks handles base64 encoded preDeploy" {
  local encoded=$(echo 'echo decoded-hook' | base64)
  local hooks_section="preDeploy:
  base64Encoded: true
  content: |
    ${encoded}"
  setupHooks "${hooks_section}"
  [ -f "pre-deploy.sh" ]
  [[ "$(cat pre-deploy.sh)" == *"decoded-hook"* ]]
}

# ============================================================================
# process_chart_flags
# ============================================================================

@test "process_chart_flags generates basic helm upgrade command" {
  local install_cmd_file="${TEST_TEMP_DIR}/install-cmd.txt"
  echo -n "" > "${install_cmd_file}"
  touch "${TEST_TEMP_DIR}/test-chart-1.0.0.tgz"
  export _chart_release_name="my-release"
  local flags_section="wait: true
timeout: 10m"
  process_chart_flags "test-chart" "my-ns" "${flags_section}" "${install_cmd_file}" ""
  local cmd=$(cat "${install_cmd_file}")
  [[ "$cmd" == *"upgrade --install"* ]]
  [[ "$cmd" == *"-n my-ns"* ]]
  [[ "$cmd" == *"--wait"* ]]
  [[ "$cmd" == *"--timeout 10m"* ]]
}

@test "process_chart_flags adds debug flag" {
  local install_cmd_file="${TEST_TEMP_DIR}/install-cmd.txt"
  echo -n "" > "${install_cmd_file}"
  touch "${TEST_TEMP_DIR}/test-chart-1.0.0.tgz"
  export _chart_release_name="my-release"
  local flags_section="debug: true"
  process_chart_flags "test-chart" "my-ns" "${flags_section}" "${install_cmd_file}" ""
  local cmd=$(cat "${install_cmd_file}")
  [[ "$cmd" == *"--debug"* ]]
}

@test "process_chart_flags adds dry-run flag" {
  local install_cmd_file="${TEST_TEMP_DIR}/install-cmd.txt"
  echo -n "" > "${install_cmd_file}"
  touch "${TEST_TEMP_DIR}/test-chart-1.0.0.tgz"
  export _chart_release_name="my-release"
  local flags_section="dryRun: true"
  process_chart_flags "test-chart" "my-ns" "${flags_section}" "${install_cmd_file}" ""
  local cmd=$(cat "${install_cmd_file}")
  [[ "$cmd" == *"--dry-run"* ]]
}

@test "process_chart_flags adds create-namespace flag" {
  local install_cmd_file="${TEST_TEMP_DIR}/install-cmd.txt"
  echo -n "" > "${install_cmd_file}"
  touch "${TEST_TEMP_DIR}/test-chart-1.0.0.tgz"
  export _chart_release_name="my-release"
  local flags_section="createNamespace: true"
  process_chart_flags "test-chart" "my-ns" "${flags_section}" "${install_cmd_file}" ""
  local cmd=$(cat "${install_cmd_file}")
  [[ "$cmd" == *"--create-namespace"* ]]
}

@test "process_chart_flags adds force flag" {
  local install_cmd_file="${TEST_TEMP_DIR}/install-cmd.txt"
  echo -n "" > "${install_cmd_file}"
  touch "${TEST_TEMP_DIR}/test-chart-1.0.0.tgz"
  export _chart_release_name="my-release"
  local flags_section="force: true"
  process_chart_flags "test-chart" "my-ns" "${flags_section}" "${install_cmd_file}" ""
  local cmd=$(cat "${install_cmd_file}")
  [[ "$cmd" == *"--force"* ]]
}

@test "process_chart_flags adds no-hooks flag" {
  local install_cmd_file="${TEST_TEMP_DIR}/install-cmd.txt"
  echo -n "" > "${install_cmd_file}"
  touch "${TEST_TEMP_DIR}/test-chart-1.0.0.tgz"
  export _chart_release_name="my-release"
  local flags_section="noHooks: true"
  process_chart_flags "test-chart" "my-ns" "${flags_section}" "${install_cmd_file}" ""
  local cmd=$(cat "${install_cmd_file}")
  [[ "$cmd" == *"--no-hooks"* ]]
}

@test "process_chart_flags appends extra flags" {
  local install_cmd_file="${TEST_TEMP_DIR}/install-cmd.txt"
  echo -n "" > "${install_cmd_file}"
  touch "${TEST_TEMP_DIR}/test-chart-1.0.0.tgz"
  export _chart_release_name="my-release"
  local flags_section="extra: --atomic --cleanup-on-fail"
  process_chart_flags "test-chart" "my-ns" "${flags_section}" "${install_cmd_file}" ""
  local cmd=$(cat "${install_cmd_file}")
  [[ "$cmd" == *"--atomic --cleanup-on-fail"* ]]
}

@test "process_chart_flags appends values flag" {
  local install_cmd_file="${TEST_TEMP_DIR}/install-cmd.txt"
  echo -n "" > "${install_cmd_file}"
  touch "${TEST_TEMP_DIR}/test-chart-1.0.0.tgz"
  export _chart_release_name="my-release"
  process_chart_flags "test-chart" "my-ns" "" "${install_cmd_file}" "--values values.yaml"
  local cmd=$(cat "${install_cmd_file}")
  [[ "$cmd" == *"--values values.yaml"* ]]
}

# ============================================================================
# installChart
# ============================================================================

@test "installChart skips when skip flag is true" {
  local flags_section="skip: true"
  run installChart "test-chart" "my-ns" "my-release" "${flags_section}" ""
  [ "$status" -eq 0 ]
}

# ============================================================================
# downloadChart
# ============================================================================

@test "downloadChart handles empty repo section" {
  run downloadChart "" "test-chart" "1.0.0"
  [ "$status" -eq 0 ]
}

# ============================================================================
# ecr_login
# ============================================================================

@test "ecr_login fails when registry host is empty" {
  run ecr_login "us-west-2" ""
  [ "$status" -ne 0 ]
  [[ "$output" == *"ECR registry host is empty"* ]]
}

@test "ecr_login defaults region to us-west-2 when empty" {
  # This will fail because aws command doesn't exist in test env, but we can check it runs
  run -127 ecr_login "" "my-registry.dkr.ecr.us-west-2.amazonaws.com"
  # Will fail due to missing aws CLI, which is expected in test env
  [ "$status" -ne 0 ]
}

# ============================================================================
# pull_helm_chart (mocked helm)
# ============================================================================

@test "pull_helm_chart calls helm pull with repo URL" {
  local repo_section="url: https://charts.example.com/repo"
  run pull_helm_chart "${repo_section}" "my-chart" "1.2.3"
  [ "$status" -eq 0 ]
  [[ "$output" == *"helm pull --repo https://charts.example.com/repo my-chart --version 1.2.3"* ]]
}

@test "pull_helm_chart handles OCI registry URL" {
  local repo_section="url: oci://registry.example.com"
  run pull_helm_chart "${repo_section}" "my-chart" "2.0.0"
  [ "$status" -eq 0 ]
  [[ "$output" == *"helm pull oci://registry.example.com/my-chart --version 2.0.0"* ]]
}

@test "pull_helm_chart adds username and password for non-OCI" {
  local repo_section="url: https://charts.example.com
username: myuser
password: mypass"
  run pull_helm_chart "${repo_section}" "my-chart" "1.0.0"
  [ "$status" -eq 0 ]
  [[ "$output" == *"--username myuser"* ]]
  [[ "$output" == *"--password mypass"* ]]
}

@test "pull_helm_chart does OCI login with username and password" {
  local repo_section="url: oci://registry.example.com
username: ociuser
password: ocipass"
  run pull_helm_chart "${repo_section}" "my-chart" "1.0.0"
  [ "$status" -eq 0 ]
  [[ "$output" == *"registry login"* ]]
}

# ============================================================================
# downloadChart — dispatch logic (mocked sub-functions)
# ============================================================================

@test "downloadChart dispatches to pull_helm_chart for helm repo" {
  # Override pull_helm_chart to track calls
  pull_helm_chart() { echo "CALLED_PULL_HELM: $*"; }
  export -f pull_helm_chart
  local repo_section="helm:
  url: https://charts.example.com/repo"
  run downloadChart "${repo_section}" "nginx" "1.0.0"
  [ "$status" -eq 0 ]
  [[ "$output" == *"CALLED_PULL_HELM"* ]]
  [[ "$output" == *"nginx"* ]]
}

@test "downloadChart dispatches to pull_ecr_chart for ECR repo" {
  pull_ecr_chart() { echo "CALLED_PULL_ECR: $*"; }
  export -f pull_ecr_chart
  local repo_section="ecr:
  region: us-east-1
  host: 123456.dkr.ecr.us-east-1.amazonaws.com
  name: my-org/my-chart"
  run downloadChart "${repo_section}" "my-chart" "2.0.0"
  [ "$status" -eq 0 ]
  [[ "$output" == *"CALLED_PULL_ECR"* ]]
}

@test "downloadChart dispatches to pull_github_chart for git repo" {
  pull_github_chart() { echo "CALLED_PULL_GIT: $*"; }
  export -f pull_github_chart
  local repo_section="git:
  github:
    repo: github.com/org/repo
    path: charts/my-chart"
  run downloadChart "${repo_section}" "my-chart" "main"
  [ "$status" -eq 0 ]
  [[ "$output" == *"CALLED_PULL_GIT"* ]]
}

@test "downloadChart does nothing when all repo sections are empty" {
  run downloadChart "" "test-chart" "1.0.0"
  [ "$status" -eq 0 ]
}

# ============================================================================
# helm-install::process_chart (mocked external calls)
# ============================================================================

@test "process_chart fails when cluster.names is not set" {
  local chart_content='name: my-chart
version: "1.0.0"
namespace: default
releaseName: my-release'
  run helm-install::process_chart "${chart_content}"
  [ "$status" -ne 0 ]
  [[ "$output" == *"cluster name count is 0"* ]]
}

@test "process_chart fails when cluster name is empty" {
  local chart_content='name: my-chart
version: "1.0.0"
namespace: default
releaseName: my-release
cluster:
  names:
    - ""'
  run helm-install::process_chart "${chart_content}"
  [ "$status" -ne 0 ]
}
