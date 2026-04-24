#!/usr/bin/env bash
#
# Common test setup for BATS tests.
# Sources pipeline functions with mocked external dependencies.
#

bats_require_minimum_version 1.5.0

# Absolute path to project root
# BATS_TEST_DIRNAME = tests/unit/bats or tests/integration/bats
export PROJECT_ROOT="$(cd "$(dirname "${BATS_TEST_DIRNAME}")/../.." && pwd)"
export CHARTS_DIR="${PROJECT_ROOT}/charts"

# Mock external commands by default
export PIPELINE_LOG_DEBUG="false"
export PIPELINE_CHECK_DOCKER_STATUS="false"
export PIPELINE_INITIAL_ASSUME_ROLE="false"
export PIPELINE_USE_LOCAL_CREDS="true"
export PIPELINE_MOCK="true"
export PIPELINE_VALIDATE_INPUT="false"
export PIPELINE_FUNCTION_INIT="false"
export PIPELINE_CMD_NAME_YQ="yq"
export REPLACE_RECIPE="true"

# Source the common functions (without triggering init)
source_functions() {
  source "${CHARTS_DIR}/common-dependency/scripts/_functions.sh"
}

# Create a temp dir for test artifacts
setup_temp_dir() {
  export TEST_TEMP_DIR="$(mktemp -d)"
}

# Clean up temp dir
teardown_temp_dir() {
  if [[ -n "${TEST_TEMP_DIR}" && -d "${TEST_TEMP_DIR}" ]]; then
    rm -rf "${TEST_TEMP_DIR}"
  fi
}

# Generate a unique test ID for data isolation (e.g., "test-a3f7b2c1")
test_id() {
  local prefix="${1:-test}"
  echo "${prefix}-$(head -c 4 /dev/urandom | od -An -tx1 | tr -d ' \n')"
}

# Build a generic-runner recipe YAML.
# Usage: build_generic_recipe "echo hello" [condition] [ignoreErrors]
build_generic_recipe() {
  local script_content="${1:?script content required}"
  local condition="${2:-true}"
  local ignore_errors="${3:-false}"
  cat <<EOF
apiVersion: v1
kind: generic-runner
meta:
  globalEnvVariable:
    PIPELINE_MOCK: "true"
tasks:
  - condition: ${condition}
    script:
      ignoreErrors: ${ignore_errors}
      fileName: script.sh
      content: |
        ${script_content}
EOF
}

# Build a helm-install recipe YAML.
# Usage: build_helm_recipe "release-name" "chart-name" "https://repo-url" [namespace]
build_helm_recipe() {
  local release_name="${1:?release name required}"
  local chart_name="${2:?chart name required}"
  local repo_url="${3:?repo URL required}"
  local namespace="${4:-default}"
  cat <<EOF
apiVersion: v1
kind: helm-install
meta:
  globalEnvVariable:
    PIPELINE_MOCK: "true"
helmCharts:
  - name: ${chart_name}
    releaseName: ${release_name}
    namespace: ${namespace}
    repo:
      helm:
        url: ${repo_url}
    cluster:
      names:
        - test-cluster
EOF
}
