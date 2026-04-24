#!/usr/bin/env bats
#
# Tests for docs/recipes/automation/on-prem/_check-tools.sh
# Validates yq version checking logic used by on-prem provisioner scripts.
#

bats_require_minimum_version 1.5.0

export PROJECT_ROOT="$(cd "$(dirname "${BATS_TEST_DIRNAME}")/../.." && pwd)"

setup() {
  source "${PROJECT_ROOT}/docs/recipes/automation/on-prem/_check-tools.sh"
}

# ============================================================================
# validate_yq_version — pass cases
# ============================================================================

@test "validate_yq_version accepts 4.53.2 (current)" {
  run validate_yq_version "4.53.2"
  [ "$status" -eq 0 ]
}

@test "validate_yq_version accepts 4.40.0 (minimum boundary)" {
  run validate_yq_version "4.40.0"
  [ "$status" -eq 0 ]
}

@test "validate_yq_version accepts 4.44.6" {
  run validate_yq_version "4.44.6"
  [ "$status" -eq 0 ]
}

@test "validate_yq_version accepts 4.99.0 (future)" {
  run validate_yq_version "4.99.0"
  [ "$status" -eq 0 ]
}

# ============================================================================
# validate_yq_version — fail cases
# ============================================================================

@test "validate_yq_version rejects 4.39.0 (one below minimum)" {
  run validate_yq_version "4.39.0"
  [ "$status" -eq 1 ]
}

@test "validate_yq_version rejects 4.2.0 (user-reported old version)" {
  run validate_yq_version "4.2.0"
  [ "$status" -eq 1 ]
}

@test "validate_yq_version rejects 4.18.1 (has env() but below 4.40)" {
  run validate_yq_version "4.18.1"
  [ "$status" -eq 1 ]
}

@test "validate_yq_version rejects 3.4.1 (wrong major version)" {
  run validate_yq_version "3.4.1"
  [ "$status" -eq 1 ]
}

@test "validate_yq_version rejects 5.0.0 (future major version)" {
  run validate_yq_version "5.0.0"
  [ "$status" -eq 1 ]
}

@test "validate_yq_version rejects empty string" {
  run validate_yq_version ""
  [ "$status" -ne 0 ]
}

@test "validate_yq_version rejects malformed input" {
  run validate_yq_version "not-a-version"
  [ "$status" -eq 1 ]
}

# ============================================================================
# get_yq_version — basic contract
# ============================================================================

@test "get_yq_version returns a semver string" {
  if ! command -v yq &> /dev/null; then
    skip "yq not installed"
  fi
  run get_yq_version
  [ "$status" -eq 0 ]
  [[ "$output" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
}
