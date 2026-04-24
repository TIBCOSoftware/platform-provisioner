#!/usr/bin/env bats
#
# Contract tests: validate that recipe YAML files conform to CUE schemas.
# Tests both synthetic helm-install recipes and real example recipes from docs/.
#

load helpers/setup

CUE_DIR=""
GENERIC_RUNNER_CUE_DIR=""
HELM_INSTALL_CUE_DIR=""

setup() {
  setup_temp_dir
  CUE_DIR="${CHARTS_DIR}/common-dependency/scripts"
  GENERIC_RUNNER_CUE_DIR="${CHARTS_DIR}/generic-runner/scripts"
  HELM_INSTALL_CUE_DIR="${CHARTS_DIR}/helm-install/scripts"
}

teardown() {
  teardown_temp_dir
}

# Skip all tests if cue is not installed
cue_available() {
  command -v cue >/dev/null 2>&1
}

# ============================================================================
# helm-install schema validation — synthetic recipes
# ============================================================================

@test "contract: valid helm-install recipe passes CUE validation" {
  cue_available || skip "cue not installed"
  cat > "${TEST_TEMP_DIR}/valid-helm.yaml" <<'EOF'
apiVersion: v1
kind: helm-install
meta:
  globalEnvVariable:
    PIPELINE_MOCK: "true"
helmCharts:
  - name: nginx
    releaseName: my-nginx
    namespace: default
    repo:
      helm:
        url: https://charts.bitnami.com/bitnami
    cluster:
      names:
        - my-cluster
    values:
      content: |
        replicaCount: 1
EOF
  run cue vet "${TEST_TEMP_DIR}/valid-helm.yaml" \
    "${CUE_DIR}/shared.cue" \
    "${HELM_INSTALL_CUE_DIR}/check.cue"
  [ "$status" -eq 0 ]
}

@test "contract: helm-install with preTasks and postTasks passes CUE validation" {
  cue_available || skip "cue not installed"
  cat > "${TEST_TEMP_DIR}/helm-with-tasks.yaml" <<'EOF'
apiVersion: v1
kind: helm-install
preTasks:
  - condition: true
    script:
      content: echo pre-deploy
postTasks:
  - condition: true
    script:
      content: echo post-deploy
helmCharts:
  - name: app
    releaseName: my-app
    repo:
      helm:
        url: https://example.com/charts
    cluster:
      names:
        - cluster-1
EOF
  run cue vet "${TEST_TEMP_DIR}/helm-with-tasks.yaml" \
    "${CUE_DIR}/shared.cue" \
    "${HELM_INSTALL_CUE_DIR}/check.cue"
  [ "$status" -eq 0 ]
}

@test "contract: helm-install with hooks passes CUE validation" {
  cue_available || skip "cue not installed"
  cat > "${TEST_TEMP_DIR}/helm-hooks.yaml" <<'EOF'
helmCharts:
  - name: app
    releaseName: my-app
    repo:
      helm:
        url: https://example.com/charts
    cluster:
      names:
        - cluster-1
    hooks:
      preDeploy:
        content: echo pre
      postDeploy:
        content: echo post
        ignoreErrors: true
EOF
  run cue vet "${TEST_TEMP_DIR}/helm-hooks.yaml" \
    "${CUE_DIR}/shared.cue" \
    "${HELM_INSTALL_CUE_DIR}/check.cue"
  [ "$status" -eq 0 ]
}

@test "contract: helm-install with all flags passes CUE validation" {
  cue_available || skip "cue not installed"
  cat > "${TEST_TEMP_DIR}/helm-flags.yaml" <<'EOF'
helmCharts:
  - name: app
    releaseName: my-app
    repo:
      helm:
        url: https://example.com/charts
    cluster:
      names:
        - cluster-1
    flags:
      debug: true
      wait: true
      timeout: "15m"
      dryRun: false
      createNamespace: true
      force: false
EOF
  run cue vet "${TEST_TEMP_DIR}/helm-flags.yaml" \
    "${CUE_DIR}/shared.cue" \
    "${HELM_INSTALL_CUE_DIR}/check.cue"
  [ "$status" -eq 0 ]
}

@test "contract: helm-install without helmCharts fails CUE validation" {
  cue_available || skip "cue not installed"
  cat > "${TEST_TEMP_DIR}/no-helmcharts.yaml" <<'EOF'
apiVersion: v1
kind: helm-install
meta:
  globalEnvVariable:
    PIPELINE_MOCK: "true"
EOF
  run cue vet "${TEST_TEMP_DIR}/no-helmcharts.yaml" \
    "${CUE_DIR}/shared.cue" \
    "${HELM_INSTALL_CUE_DIR}/check.cue"
  [ "$status" -ne 0 ]
}

@test "contract: helm-install with empty helmCharts fails CUE validation" {
  cue_available || skip "cue not installed"
  cat > "${TEST_TEMP_DIR}/empty-helmcharts.yaml" <<'EOF'
helmCharts: []
EOF
  run cue vet "${TEST_TEMP_DIR}/empty-helmcharts.yaml" \
    "${CUE_DIR}/shared.cue" \
    "${HELM_INSTALL_CUE_DIR}/check.cue"
  [ "$status" -ne 0 ]
}

@test "contract: helm-install with missing releaseName fails CUE validation" {
  cue_available || skip "cue not installed"
  cat > "${TEST_TEMP_DIR}/no-release.yaml" <<'EOF'
helmCharts:
  - name: app
    repo:
      helm:
        url: https://example.com/charts
    cluster:
      names:
        - cluster-1
EOF
  run cue vet "${TEST_TEMP_DIR}/no-release.yaml" \
    "${CUE_DIR}/shared.cue" \
    "${HELM_INSTALL_CUE_DIR}/check.cue"
  [ "$status" -ne 0 ]
}

@test "contract: helm-install with ECR repo passes CUE validation" {
  cue_available || skip "cue not installed"
  cat > "${TEST_TEMP_DIR}/helm-ecr.yaml" <<'EOF'
helmCharts:
  - name: app
    releaseName: my-app
    repo:
      ecr:
        name: my-app
        region: us-west-2
        host: 123456.dkr.ecr.us-west-2.amazonaws.com
    cluster:
      names:
        - cluster-1
EOF
  run cue vet "${TEST_TEMP_DIR}/helm-ecr.yaml" \
    "${CUE_DIR}/shared.cue" \
    "${HELM_INSTALL_CUE_DIR}/check.cue"
  [ "$status" -eq 0 ]
}

@test "contract: helm-install with multiple charts passes CUE validation" {
  cue_available || skip "cue not installed"
  cat > "${TEST_TEMP_DIR}/multi-chart.yaml" <<'EOF'
helmCharts:
  - name: ingress-nginx
    releaseName: ingress
    repo:
      helm:
        url: https://kubernetes.github.io/ingress-nginx
    cluster:
      names:
        - cluster-1
  - name: cert-manager
    releaseName: cert-manager
    repo:
      helm:
        url: https://charts.jetstack.io
    cluster:
      names:
        - cluster-1
EOF
  run cue vet "${TEST_TEMP_DIR}/multi-chart.yaml" \
    "${CUE_DIR}/shared.cue" \
    "${HELM_INSTALL_CUE_DIR}/check.cue"
  [ "$status" -eq 0 ]
}

# ============================================================================
# Contract tests for real example recipes in docs/recipes/
# Recipes using ${VAR} placeholders will fail strict CUE validation
# (pre-substitution), so we test what we can.
# ============================================================================

@test "contract: docs/recipes/k8s/cloud/deploy-tp-aro.yaml is valid generic-runner YAML" {
  cue_available || skip "cue not installed"
  local recipe="${PROJECT_ROOT}/docs/recipes/k8s/cloud/deploy-tp-aro.yaml"
  [ -f "${recipe}" ] || skip "recipe file not found"
  # This recipe is kind: generic-runner — validate YAML is parseable
  run yq eval '.kind' "${recipe}"
  [ "$status" -eq 0 ]
  [ "$output" = "generic-runner" ]
}

@test "contract: docs/recipes example recipes have required top-level fields" {
  local failed=0
  for recipe in "${PROJECT_ROOT}"/docs/recipes/controlplane/*.yaml \
                "${PROJECT_ROOT}"/docs/recipes/tp-base/*.yaml \
                "${PROJECT_ROOT}"/docs/recipes/k8s/cloud/*.yaml; do
    [ -f "${recipe}" ] || continue
    local kind
    kind=$(yq eval '.kind' "${recipe}" 2>/dev/null)
    if [ -z "${kind}" ] || [ "${kind}" = "null" ]; then
      echo "FAIL: ${recipe} missing 'kind' field"
      failed=1
    fi
  done
  [ "${failed}" -eq 0 ]
}

@test "contract: helm-install example recipes have helmCharts field" {
  local failed=0
  for recipe in "${PROJECT_ROOT}"/docs/recipes/controlplane/*.yaml \
                "${PROJECT_ROOT}"/docs/recipes/tp-base/*.yaml \
                "${PROJECT_ROOT}"/docs/recipes/k8s/cloud/*.yaml; do
    [ -f "${recipe}" ] || continue
    local kind
    kind=$(yq eval '.kind' "${recipe}" 2>/dev/null)
    if [ "${kind}" = "helm-install" ]; then
      local charts_count
      charts_count=$(yq eval '.helmCharts | length' "${recipe}" 2>/dev/null)
      if [ -z "${charts_count}" ] || [ "${charts_count}" = "0" ] || [ "${charts_count}" = "null" ]; then
        echo "FAIL: ${recipe} (helm-install) has no helmCharts"
        failed=1
      fi
    fi
  done
  [ "${failed}" -eq 0 ]
}

@test "contract: generic-runner example recipes have tasks field" {
  local failed=0
  for recipe in "${PROJECT_ROOT}"/docs/recipes/k8s/cloud/*.yaml; do
    [ -f "${recipe}" ] || continue
    local kind
    kind=$(yq eval '.kind' "${recipe}" 2>/dev/null)
    if [ "${kind}" = "generic-runner" ]; then
      local tasks_count
      tasks_count=$(yq eval '.tasks | length' "${recipe}" 2>/dev/null)
      if [ -z "${tasks_count}" ] || [ "${tasks_count}" = "0" ] || [ "${tasks_count}" = "null" ]; then
        echo "FAIL: ${recipe} (generic-runner) has no tasks"
        failed=1
      fi
    fi
  done
  [ "${failed}" -eq 0 ]
}
