#!/usr/bin/env bats
#
# Tests for CUE schema validation of recipe YAML files
# Validates that valid recipes pass and invalid recipes are rejected
#

load helpers/setup

CUE_DIR=""
GENERIC_RUNNER_CUE_DIR=""

setup() {
  setup_temp_dir
  CUE_DIR="${CHARTS_DIR}/common-dependency/scripts"
  GENERIC_RUNNER_CUE_DIR="${CHARTS_DIR}/generic-runner/scripts"
}

teardown() {
  teardown_temp_dir
}

# Skip all tests if cue is not installed
cue_available() {
  command -v cue >/dev/null 2>&1
}

# ============================================================================
# Valid recipes should pass CUE validation
# ============================================================================

@test "valid generic-runner recipe passes CUE validation" {
  cue_available || skip "cue not installed"
  cat > "${TEST_TEMP_DIR}/valid.yaml" <<'EOF'
apiVersion: v1
kind: generic-runner
meta:
  globalEnvVariable:
    PIPELINE_MOCK: true
tasks:
  - condition: true
    script:
      fileName: script.sh
      content: |
        echo "hello"
EOF
  run cue vet "${TEST_TEMP_DIR}/valid.yaml" \
    "${CUE_DIR}/shared.cue" \
    "${GENERIC_RUNNER_CUE_DIR}/check.cue"
  [ "$status" -eq 0 ]
}

@test "minimal valid recipe passes CUE validation" {
  cue_available || skip "cue not installed"
  cat > "${TEST_TEMP_DIR}/minimal.yaml" <<'EOF'
tasks:
  - script:
      content: echo hello
EOF
  run cue vet "${TEST_TEMP_DIR}/minimal.yaml" \
    "${CUE_DIR}/shared.cue" \
    "${GENERIC_RUNNER_CUE_DIR}/check.cue"
  [ "$status" -eq 0 ]
}

@test "recipe with multiple tasks passes CUE validation" {
  cue_available || skip "cue not installed"
  cat > "${TEST_TEMP_DIR}/multi.yaml" <<'EOF'
apiVersion: v1
kind: generic-runner
tasks:
  - condition: true
    script:
      fileName: first.sh
      content: echo first
  - condition: false
    script:
      fileName: second.sh
      content: echo second
EOF
  run cue vet "${TEST_TEMP_DIR}/multi.yaml" \
    "${CUE_DIR}/shared.cue" \
    "${GENERIC_RUNNER_CUE_DIR}/check.cue"
  [ "$status" -eq 0 ]
}

@test "recipe with retry fields passes CUE validation" {
  cue_available || skip "cue not installed"
  cat > "${TEST_TEMP_DIR}/retry.yaml" <<'EOF'
tasks:
  - script:
      content: echo retry-test
      retryCount: 3
      retryDelay: 5
EOF
  run cue vet "${TEST_TEMP_DIR}/retry.yaml" \
    "${CUE_DIR}/shared.cue" \
    "${GENERIC_RUNNER_CUE_DIR}/check.cue"
  [ "$status" -eq 0 ]
}

# ============================================================================
# Invalid recipes should fail CUE validation
# ============================================================================

@test "recipe without tasks field fails CUE validation" {
  cue_available || skip "cue not installed"
  cat > "${TEST_TEMP_DIR}/no-tasks.yaml" <<'EOF'
apiVersion: v1
kind: generic-runner
meta:
  globalEnvVariable:
    PIPELINE_MOCK: true
EOF
  run cue vet "${TEST_TEMP_DIR}/no-tasks.yaml" \
    "${CUE_DIR}/shared.cue" \
    "${GENERIC_RUNNER_CUE_DIR}/check.cue"
  [ "$status" -ne 0 ]
}

@test "recipe with empty tasks array fails CUE validation" {
  cue_available || skip "cue not installed"
  cat > "${TEST_TEMP_DIR}/empty-tasks.yaml" <<'EOF'
apiVersion: v1
tasks: []
EOF
  run cue vet "${TEST_TEMP_DIR}/empty-tasks.yaml" \
    "${CUE_DIR}/shared.cue" \
    "${GENERIC_RUNNER_CUE_DIR}/check.cue"
  [ "$status" -ne 0 ]
}

@test "recipe with negative retryCount fails CUE validation" {
  cue_available || skip "cue not installed"
  cat > "${TEST_TEMP_DIR}/bad-retry.yaml" <<'EOF'
tasks:
  - script:
      content: echo test
      retryCount: -1
EOF
  run cue vet "${TEST_TEMP_DIR}/bad-retry.yaml" \
    "${CUE_DIR}/shared.cue" \
    "${GENERIC_RUNNER_CUE_DIR}/check.cue"
  [ "$status" -ne 0 ]
}

# ============================================================================
# Existing test recipe files should pass CUE validation
# ============================================================================

@test "recipe with env var condition fails strict CUE (pre-substitution)" {
  cue_available || skip "cue not installed"
  # Recipes using ${VAR} as condition fail CUE validation before env var substitution.
  # This is expected — CUE validates after substitution in the real pipeline.
  cat > "${TEST_TEMP_DIR}/env-condition.yaml" <<'EOF'
apiVersion: v1
kind: generic-runner
meta:
  globalEnvVariable:
    RUN1: true
tasks:
  - condition: ${RUN1}
    script:
      content: echo hello
EOF
  run cue vet "${TEST_TEMP_DIR}/env-condition.yaml" \
    "${CUE_DIR}/shared.cue" \
    "${GENERIC_RUNNER_CUE_DIR}/check.cue"
  [ "$status" -ne 0 ]
}

@test "recipe with string 'true' condition passes CUE validation" {
  cue_available || skip "cue not installed"
  # After env var substitution, condition becomes "true" (string) — this should pass
  cat > "${TEST_TEMP_DIR}/string-condition.yaml" <<'EOF'
tasks:
  - condition: "true"
    script:
      content: echo hello
EOF
  run cue vet "${TEST_TEMP_DIR}/string-condition.yaml" \
    "${CUE_DIR}/shared.cue" \
    "${GENERIC_RUNNER_CUE_DIR}/check.cue"
  [ "$status" -eq 0 ]
}
