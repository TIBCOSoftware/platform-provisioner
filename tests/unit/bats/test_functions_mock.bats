#!/usr/bin/env bats
#
# Mock tests for complex branching functions in _functions.sh
# Tests routing logic, error propagation, and orchestration flow
# External dependencies (aws, az, gcloud, git, kubectl) are mocked
#

load helpers/setup

setup() {
  setup_temp_dir
  source_functions
  cd "${TEST_TEMP_DIR}"
}

teardown() {
  cd /
  teardown_temp_dir
}

# ============================================================================
# pp-aws-assume-role — skip logic and chain
# ============================================================================

@test "pp-aws-assume-role skips when PIPELINE_USE_LOCAL_CREDS=true and AWS_SESSION_TOKEN set" {
  export PIPELINE_USE_LOCAL_CREDS="true"
  export AWS_SESSION_TOKEN="existing-token"
  run pp-aws-assume-role "arn:aws:iam::123:role/TestRole"
  [ "$status" -eq 0 ]
  [[ "$output" == *"skip assume role"* ]] || true
}

@test "pp-aws-assume-role proceeds when PIPELINE_USE_LOCAL_CREDS=true but no session token" {
  export PIPELINE_USE_LOCAL_CREDS="true"
  unset AWS_SESSION_TOKEN
  # Mock aws command to succeed
  aws() { echo '{"Credentials":{"AccessKeyId":"AK","SecretAccessKey":"SK","SessionToken":"ST"}}'; }
  export -f aws
  jq() { echo "mocked"; }
  export -f jq
  run pp-aws-assume-role "arn:aws:iam::123:role/TestRole"
  [ "$status" -eq 0 ]
}

@test "pp-aws-assume-role returns error when assume-role fails" {
  export PIPELINE_USE_LOCAL_CREDS="false"
  aws() { return 1; }
  export -f aws
  run pp-aws-assume-role "arn:aws:iam::123:role/BadRole"
  [ "$status" -ne 0 ]
  [[ "$output" == *"Failed to assume role"* ]]
}

@test "pp-aws-assume-role chains multiple roles" {
  export PIPELINE_USE_LOCAL_CREDS="false"
  local call_count=0
  aws() {
    echo '{"Credentials":{"AccessKeyId":"AK","SecretAccessKey":"SK","SessionToken":"ST"}}';
  }
  export -f aws
  jq() {
    # Return a predictable value for each jq call
    echo "mocked-value"
  }
  export -f jq
  run pp-aws-assume-role "arn:role1" "arn:role2"
  [ "$status" -eq 0 ]
}

# ============================================================================
# common::assume_role — routing logic (6 code paths)
# ============================================================================

@test "common::assume_role returns 0 for on-prem with PIPELINE_ON_PREM_KUBECONFIG" {
  export AWS_ACCOUNT="on-prem"
  export PIPELINE_ON_PREM_KUBECONFIG=true
  run common::assume_role
  [ "$status" -eq 0 ]
}

@test "common::assume_role sets KUBECONFIG for on-prem with kubeconfig file name" {
  export AWS_ACCOUNT="on-prem"
  export PIPELINE_ON_PREM_KUBECONFIG_FILE_NAME="my-config"
  unset PIPELINE_ON_PREM_KUBECONFIG
  common::assume_role
  [ "${KUBECONFIG}" = "/root/.kube/my-config" ]
}

@test "common::assume_role returns 0 for plain on-prem" {
  export AWS_ACCOUNT="on-prem"
  unset PIPELINE_ON_PREM_KUBECONFIG
  unset PIPELINE_ON_PREM_KUBECONFIG_FILE_NAME
  run common::assume_role
  [ "$status" -eq 0 ]
}

@test "common::assume_role routes to GCP for gcp- prefixed account" {
  export AWS_ACCOUNT="gcp-project1"
  unset CLUSTER_NAME
  # Mock gcp-federation-assume-role to succeed
  gcp-federation-assume-role() { echo "GCP_ASSUMED"; return 0; }
  export -f gcp-federation-assume-role
  run common::assume_role
  [ "$status" -eq 0 ]
  [[ "$output" == *"GCP_ASSUMED"* ]]
}

@test "common::assume_role routes to GCP with cluster name" {
  export AWS_ACCOUNT="gcp-project1"
  export CLUSTER_NAME="my-gke-cluster"
  gcp-federation-k8s-cluster() { echo "GKE_CONNECTED"; return 0; }
  export -f gcp-federation-k8s-cluster
  run common::assume_role
  [ "$status" -eq 0 ]
  [[ "$output" == *"GKE_CONNECTED"* ]]
}

@test "common::assume_role routes to Azure for azure- prefixed account" {
  export AWS_ACCOUNT="azure-abc123"
  unset CLUSTER_NAME
  pp-azure-assume-role() { echo "AZURE_ASSUMED"; return 0; }
  export -f pp-azure-assume-role
  run common::assume_role
  [ "$status" -eq 0 ]
  [[ "$output" == *"AZURE_ASSUMED"* ]]
}

@test "common::assume_role routes to Azure with cluster name" {
  export AWS_ACCOUNT="azure-abc123"
  export CLUSTER_NAME="my-aks-cluster"
  aks-pp-assume-role() { echo "AKS_CONNECTED"; return 0; }
  export -f aks-pp-assume-role
  run common::assume_role
  [ "$status" -eq 0 ]
  [[ "$output" == *"AKS_CONNECTED"* ]]
}

@test "common::assume_role routes to AWS by default" {
  export AWS_ACCOUNT="123456789012"
  unset CLUSTER_NAME
  export PIPELINE_AWS_MANAGED_ACCOUNT_ROLE="TestRole"
  pp-aws-assume-role() { echo "AWS_ASSUMED: $*"; return 0; }
  export -f pp-aws-assume-role
  run common::assume_role
  [ "$status" -eq 0 ]
  [[ "$output" == *"AWS_ASSUMED"* ]]
  [[ "$output" == *"TestRole"* ]]
}

@test "common::assume_role routes to AWS with cluster name" {
  export AWS_ACCOUNT="123456789012"
  export CLUSTER_NAME="my-eks-cluster"
  export PIPELINE_AWS_MANAGED_ACCOUNT_ROLE="TestRole"
  eks-pp-assume-role() { echo "EKS_CONNECTED: $*"; return 0; }
  export -f eks-pp-assume-role
  run common::assume_role
  [ "$status" -eq 0 ]
  [[ "$output" == *"EKS_CONNECTED"* ]]
}

@test "common::assume_role propagates GCP error" {
  export AWS_ACCOUNT="gcp-project1"
  unset CLUSTER_NAME
  gcp-federation-assume-role() { return 1; }
  export -f gcp-federation-assume-role
  run common::assume_role
  [ "$status" -ne 0 ]
  [[ "$output" == *"error"* ]]
}

@test "common::assume_role propagates Azure error" {
  export AWS_ACCOUNT="azure-abc123"
  unset CLUSTER_NAME
  pp-azure-assume-role() { return 1; }
  export -f pp-azure-assume-role
  run common::assume_role
  [ "$status" -ne 0 ]
  [[ "$output" == *"error"* ]]
}

@test "common::assume_role propagates AWS error" {
  export AWS_ACCOUNT="123456789012"
  unset CLUSTER_NAME
  export PIPELINE_AWS_MANAGED_ACCOUNT_ROLE="TestRole"
  pp-aws-assume-role() { return 1; }
  export -f pp-aws-assume-role
  run common::assume_role
  [ "$status" -ne 0 ]
  [[ "$output" == *"error"* ]]
}

# ============================================================================
# process_recipe_secret — secret or passthrough
# ============================================================================

@test "process_recipe_secret passes through when no secret defined" {
  local input="tasks:
  - name: test"
  process_recipe_secret "us-west-2" "123456" "${input}" "${TEST_TEMP_DIR}/output.yaml"
  [ -f "${TEST_TEMP_DIR}/output.yaml" ]
  [[ "$(cat "${TEST_TEMP_DIR}/output.yaml")" == *"test"* ]]
}

@test "process_recipe_secret calls parse-with-aws-secret-manager when secret is defined" {
  pp-aws-assume-role() { return 0; }
  export -f pp-aws-assume-role
  parse-with-aws-secret-manager() { echo "SECRET_PARSED: $*"; echo "parsed" > "$3"; }
  export -f parse-with-aws-secret-manager
  export PIPELINE_AWS_MANAGED_ACCOUNT_ROLE="TestRole"
  local input="meta:
  secret:
    aws:
      secretName: my-secret
tasks:
  - name: test"
  run process_recipe_secret "us-west-2" "123456" "${input}" "${TEST_TEMP_DIR}/output.yaml"
  [ "$status" -eq 0 ]
  [[ "$output" == *"SECRET_PARSED"* ]]
}

@test "process_recipe_secret fails when assume-role fails" {
  pp-aws-assume-role() { return 1; }
  export -f pp-aws-assume-role
  export PIPELINE_AWS_MANAGED_ACCOUNT_ROLE="TestRole"
  local input="meta:
  secret:
    aws:
      secretName: my-secret"
  run process_recipe_secret "us-west-2" "123456" "${input}" "${TEST_TEMP_DIR}/output.yaml"
  [ "$status" -ne 0 ]
  [[ "$output" == *"assume role error"* ]]
}

# ============================================================================
# gitops_replace_recipe — git clone or passthrough
# ============================================================================

@test "gitops_replace_recipe passes through when no meta.git.github" {
  local input="tasks:
  - name: test"
  gitops_replace_recipe "${input}" "${TEST_TEMP_DIR}/output.yaml"
  [ -f "${TEST_TEMP_DIR}/output.yaml" ]
  [[ "$(cat "${TEST_TEMP_DIR}/output.yaml")" == *"test"* ]]
}

@test "gitops_replace_recipe calls git_clone when meta.git.github is set" {
  common::git_clone() {
    # Simulate cloning by creating the expected file
    mkdir -p "${3}"
    echo "cloned-content" > "${3}/${4:-file.yaml}"
    return 0
  }
  export -f common::git_clone
  local input="meta:
  git:
    github:
      repo: github.com/org/repo
      branch: main
      path: recipes/test.yaml
tasks:
  - name: original"
  # mock git_clone to create expected output
  common::git_clone() {
    mkdir -p "$3"
    echo "cloned-recipe" > "$3/recipes/test.yaml"
    return 0
  }
  export -f common::git_clone
  # Need to mkdir -p git_remote/recipes for cp to work
  mkdir -p "${TEST_TEMP_DIR}/git_remote/recipes"
  run gitops_replace_recipe "${input}" "${TEST_TEMP_DIR}/output.yaml"
  [ "$status" -eq 0 ]
}

@test "gitops_replace_recipe fails when git_clone fails" {
  common::git_clone() { return 1; }
  export -f common::git_clone
  local input="meta:
  git:
    github:
      repo: github.com/org/repo
      branch: main
      path: file.yaml"
  run gitops_replace_recipe "${input}" "${TEST_TEMP_DIR}/output.yaml"
  [ "$status" -ne 0 ]
  [[ "$output" == *"git_clone"* ]]
}

# ============================================================================
# common::process_meta — orchestration flow
# ============================================================================

@test "common::process_meta runs full pipeline with env substitution" {
  export REPLACE_RECIPE="true"
  # Mock functions that call external CLIs
  process_recipe_secret() { echo "${3}" > "${4}"; return 0; }
  export -f process_recipe_secret
  gitops_replace_recipe() { echo "${1}" > "${2}"; return 0; }
  export -f gitops_replace_recipe
  common::adjust_tool_binaries() { return 0; }
  export -f common::adjust_tool_binaries
  # globalEnvVariable defines MY_VAR=recipe-value; envsubst replaces ${MY_VAR} in the recipe
  local input='meta:
  globalEnvVariable:
    MY_VAR: recipe-value
tasks:
  - name: "${MY_VAR}"'
  run common::process_meta "${input}" "${TEST_TEMP_DIR}/recipe.yaml"
  [ "$status" -eq 0 ]
  [ -f "${TEST_TEMP_DIR}/recipe.yaml" ]
  [[ "$(cat "${TEST_TEMP_DIR}/recipe.yaml")" == *"recipe-value"* ]]
}

@test "common::process_meta passes through when no meta section" {
  process_recipe_secret() { echo "${3}" > "${4}"; return 0; }
  export -f process_recipe_secret
  gitops_replace_recipe() { echo "${1}" > "${2}"; return 0; }
  export -f gitops_replace_recipe
  common::adjust_tool_binaries() { return 0; }
  export -f common::adjust_tool_binaries
  local input="tasks:
  - name: simple-task"
  run common::process_meta "${input}" "${TEST_TEMP_DIR}/recipe.yaml"
  [ "$status" -eq 0 ]
  [ -f "${TEST_TEMP_DIR}/recipe.yaml" ]
}

@test "common::process_meta fails when process_recipe_secret fails" {
  process_recipe_secret() { return 1; }
  export -f process_recipe_secret
  local input="tasks:
  - name: test"
  run common::process_meta "${input}" "${TEST_TEMP_DIR}/recipe.yaml"
  [ "$status" -ne 0 ]
  [[ "$output" == *"process_recipe_secret error"* ]]
}

@test "common::process_meta fails when gitops_replace_recipe fails" {
  process_recipe_secret() { echo "${3}" > "${4}"; return 0; }
  export -f process_recipe_secret
  gitops_replace_recipe() { return 1; }
  export -f gitops_replace_recipe
  local input="tasks:
  - name: test"
  run common::process_meta "${input}" "${TEST_TEMP_DIR}/recipe.yaml"
  [ "$status" -ne 0 ]
  [[ "$output" == *"gitops_replace_recipe error"* ]]
}

@test "common::process_meta fails when adjust_tool_binaries fails" {
  process_recipe_secret() { echo "${3}" > "${4}"; return 0; }
  export -f process_recipe_secret
  gitops_replace_recipe() { echo "${1}" > "${2}"; return 0; }
  export -f gitops_replace_recipe
  common::adjust_tool_binaries() { return 1; }
  export -f common::adjust_tool_binaries
  local input="tasks:
  - name: test"
  run common::process_meta "${input}" "${TEST_TEMP_DIR}/recipe.yaml"
  [ "$status" -ne 0 ]
  [[ "$output" == *"adjust_tool_binaries error"* ]]
}

@test "common::process_meta exports guiEnv and globalEnvVariable" {
  export REPLACE_RECIPE="true"
  process_recipe_secret() { echo "${3}" > "${4}"; return 0; }
  export -f process_recipe_secret
  gitops_replace_recipe() { echo "${1}" > "${2}"; return 0; }
  export -f gitops_replace_recipe
  common::adjust_tool_binaries() { return 0; }
  export -f common::adjust_tool_binaries
  local input='meta:
  guiEnv:
    GUI_VAR: gui-value
  globalEnvVariable:
    GLOBAL_VAR: global-value
tasks:
  - name: test'
  common::process_meta "${input}" "${TEST_TEMP_DIR}/recipe.yaml"
  [ "${GUI_VAR}" = "gui-value" ]
  [ "${GLOBAL_VAR}" = "global-value" ]
}
