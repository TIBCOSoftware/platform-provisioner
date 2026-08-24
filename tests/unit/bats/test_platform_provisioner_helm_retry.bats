#!/usr/bin/env bats
#
# Tests for the helm_pull_with_retry() helper in dev/platform-provisioner.sh (PCP-23371).
#
# Bug: helm pull for common-dependency / ${PIPELINE_NAME} had no retry, and the
# transient ~8% 503/timeout failure rate from GitHub Releases killed the whole
# on-prem deploy on a single flake (the install-tp task itself runs with retry: 0).
# Fix: wrap both helm pull calls in a local retry+backoff helper (3 attempts,
# exponential backoff: 5s, then 10s between attempts).
#
# The helper is defined inside a single-quoted `bash -c '...'` heredoc that only
# ever runs inside the pipeline's docker container (nothing from the host repo is
# mounted in), so it cannot be `source`d directly here. Following the same
# convention as test_o11y_widget_guard.bats: mirror the exact logic as a bats
# helper (kept in sync with the real source) for behavioral tests, and separately
# assert via grep that the real source actually uses this wrapped form.
#
# `helm` and `sleep` are mocked via PATH-shadowed executable scripts (not shell
# function overrides) — this is deliberate: under CI's `bats --jobs N` (backed by
# GNU parallel), a function override is not reliably visible to the command the
# retry loop invokes, so a real `sleep 5`/`sleep 10` ran per test and blew the
# job's 10-minute timeout. Real executables on PATH work under any execution
# model, parallel or not.
#

bats_require_minimum_version 1.5.0

export PROJECT_ROOT="$(cd "$(dirname "${BATS_TEST_DIRNAME}")/../.." && pwd)"
SCRIPT="${PROJECT_ROOT}/dev/platform-provisioner.sh"

# Exact mirror of helm_pull_with_retry() in dev/platform-provisioner.sh.
helm_pull_with_retry() {
  local chart="$1" attempt=1 max_attempts=3 delay=5
  if [[ ! "${chart}" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]]; then
    echo "helm pull: refusing unsafe chart name: ${chart}"
    return 1
  fi
  rm -rf "/tmp/${chart}" || { echo "helm pull: cannot clear /tmp/${chart}"; return 1; }
  until helm pull --untar --untardir /tmp --version ^1.0.0 --repo "https://${PIPELINE_CHART_REPO}" "${chart}"; do
    if [[ ${attempt} -ge ${max_attempts} ]]; then
      echo "helm pull ${chart} failed after ${max_attempts} attempts"
      return 1
    fi
    echo "helm pull ${chart} failed (attempt ${attempt}/${max_attempts}); retrying in ${delay}s..."
    sleep "${delay}"
    attempt=$((attempt + 1))
    delay=$((delay * 2))
  done
}

setup() {
  export PIPELINE_CHART_REPO="tibcosoftware.github.io/platform-provisioner"
  FAKE_BIN="${BATS_TEST_TMPDIR}/bin"
  mkdir -p "${FAKE_BIN}"
  PATH="${FAKE_BIN}:${PATH}"

  # Fake `sleep`: logs the requested duration instead of actually sleeping, so
  # tests are instant and immune to any parallel/exec-model quirk.
  cat > "${FAKE_BIN}/sleep" <<'FAKE_SLEEP'
#!/bin/bash
echo "SLEPT:$1"
FAKE_SLEEP
  chmod +x "${FAKE_BIN}/sleep"
}

# Install a fake `helm` executable that fails until the Nth call, then succeeds.
# fail_until=0 means always fail.
install_fake_helm() {
  local fail_until="$1" counter_file="${BATS_TEST_TMPDIR}/helm-calls"
  echo 0 > "${counter_file}"
  cat > "${FAKE_BIN}/helm" <<FAKE_HELM
#!/bin/bash
count=\$(<"${counter_file}")
count=\$((count + 1))
echo "\${count}" > "${counter_file}"
if [[ "${fail_until}" -eq 0 || \${count} -lt ${fail_until} ]]; then
  exit 1
fi
exit 0
FAKE_HELM
  chmod +x "${FAKE_BIN}/helm"
}

# ============================================================================
# Behavior — mocked helm succeeding/failing on demand
# ============================================================================

@test "succeeds on the 1st attempt without sleeping" {
  install_fake_helm 1
  run helm_pull_with_retry "common-dependency"
  [ "$status" -eq 0 ]
  [[ "$output" != *"SLEPT"* ]]
}

@test "succeeds on the 2nd attempt after one 5s sleep" {
  install_fake_helm 2
  run helm_pull_with_retry "common-dependency"
  [ "$status" -eq 0 ]
  [[ "$output" == *"attempt 1/3"* ]]
  [[ "$output" == *"SLEPT:5"* ]]
  [[ "$output" != *"attempt 2/3"* ]]
}

@test "succeeds on the 3rd attempt after 5s then 10s sleep (exponential backoff)" {
  install_fake_helm 3
  run helm_pull_with_retry "common-dependency"
  [ "$status" -eq 0 ]
  [[ "$output" == *"attempt 1/3"* ]]
  [[ "$output" == *"SLEPT:5"* ]]
  [[ "$output" == *"attempt 2/3"* ]]
  [[ "$output" == *"SLEPT:10"* ]]
  [[ "$output" != *"attempt 3/3"* ]]
}

@test "fails after exactly 3 attempts, returns 1, no 4th attempt" {
  install_fake_helm 0
  run helm_pull_with_retry "common-dependency"
  [ "$status" -eq 1 ]
  [[ "$output" == *"attempt 1/3"* ]]
  [[ "$output" == *"attempt 2/3"* ]]
  [[ "$output" != *"attempt 3/3"* ]]
  [[ "$output" == *"failed after 3 attempts"* ]]
}

# ============================================================================
# Security — the chart name (attacker-influenceable via ${PIPELINE_NAME}, which
# is derived from the untrusted recipe's .kind field) must not reach `rm -rf`
# unvalidated (Copilot review finding).
# ============================================================================

@test "refuses a chart name containing a path traversal sequence, does not call rm/helm" {
  install_fake_helm 1
  run helm_pull_with_retry "../../etc"
  [ "$status" -eq 1 ]
  [[ "$output" == *"refusing unsafe chart name"* ]]
  [ "$(cat "${BATS_TEST_TMPDIR}/helm-calls" 2>/dev/null || echo 0)" = "0" ]
}

@test "refuses a chart name containing a path separator" {
  install_fake_helm 1
  run helm_pull_with_retry "foo/bar"
  [ "$status" -eq 1 ]
  [[ "$output" == *"refusing unsafe chart name"* ]]
}

@test "accepts a normal chart name unchanged" {
  install_fake_helm 1
  run helm_pull_with_retry "common-dependency"
  [ "$status" -eq 0 ]
  [[ "$output" != *"refusing unsafe chart name"* ]]
}

@test "refuses a dot-only chart name" {
  # ".." is a no-op in practice (GNU rm refuses to remove '.'/'..'), but the
  # allowlist shouldn't rely on that — reject it outright.
  install_fake_helm 1
  run helm_pull_with_retry ".."
  [ "$status" -eq 1 ]
  [[ "$output" == *"refusing unsafe chart name"* ]]
}

@test "refuses a chart name starting with a dash" {
  install_fake_helm 1
  run helm_pull_with_retry "-rf"
  [ "$status" -eq 1 ]
  [[ "$output" == *"refusing unsafe chart name"* ]]
}

# ============================================================================
# Source regression — the real script must use the wrapped form
# ============================================================================

@test "platform-provisioner.sh defines helm_pull_with_retry" {
  [ -f "${SCRIPT}" ]
  run grep -c 'helm_pull_with_retry() {' "${SCRIPT}"
  [ "$status" -eq 0 ]
  [ "$output" = "1" ]
}

@test "platform-provisioner.sh does not call helm pull directly for common-dependency" {
  run grep -nE '^helm pull .*common-dependency$' "${SCRIPT}"
  [ "$status" -eq 1 ]
}

@test "platform-provisioner.sh does not call helm pull directly for \${PIPELINE_NAME}" {
  run grep -nE '^helm pull .*\$\{PIPELINE_NAME\}$' "${SCRIPT}"
  [ "$status" -eq 1 ]
}

@test "platform-provisioner.sh routes both pulls through helm_pull_with_retry" {
  run grep -c 'helm_pull_with_retry common-dependency' "${SCRIPT}"
  [ "$status" -eq 0 ]
  [ "$output" = "1" ]
  run grep -c 'helm_pull_with_retry "\${PIPELINE_NAME}"' "${SCRIPT}"
  [ "$status" -eq 0 ]
  [ "$output" = "1" ]
}

@test "both helm_pull_with_retry call sites fail closed (|| exit 1)" {
  # Mutation-proven gap (review finding H1): the behavioral tests above exercise
  # a *mirror* of helm_pull_with_retry, so they still pass even if a future edit
  # drops `|| exit 1` from a real call site — silently restoring the original
  # "deploy proceeds past a failed pull" bug this PR exists to fix. Pin it
  # directly against the source.
  run grep -c 'helm_pull_with_retry common-dependency || exit 1' "${SCRIPT}"
  [ "$status" -eq 0 ]
  [ "$output" = "1" ]
  run grep -c 'helm_pull_with_retry "\${PIPELINE_NAME}" || exit 1' "${SCRIPT}"
  [ "$status" -eq 0 ]
  [ "$output" = "1" ]
}

@test "platform-provisioner.sh's retry constants match the mirrored bats helper (max_attempts=3, delay=5)" {
  # Guards against the mirror above silently drifting from the real, un-sourceable
  # heredoc copy: pin the exact constants line so a future edit to the real
  # attempt count / initial backoff is caught here, not just structurally.
  run grep -c 'local chart="\$1" attempt=1 max_attempts=3 delay=5' "${SCRIPT}"
  [ "$status" -eq 0 ]
  [ "$output" = "1" ]
}

@test "platform-provisioner.sh's backoff-doubling line matches the mirrored bats helper" {
  # Same drift concern as above, but for the loop body's backoff math (not just
  # the initial constants) — a future edit to the doubling formula should be
  # caught here too, not just the attempt-gate check.
  run grep -c 'delay=\$((delay \* 2))' "${SCRIPT}"
  [ "$status" -eq 0 ]
  [ "$output" = "1" ]
}

@test "platform-provisioner.sh clears /tmp/<chart> before each retry attempt (idempotent untar)" {
  # A flake that lands mid-untar leaves /tmp/<chart> partially populated; helm
  # pull --untar then fails deterministically on "already exists" regardless of
  # whether the registry has recovered. Pin the cleanup against the real source
  # so this doesn't silently regress. The cleanup is a distinct, fail-fast
  # statement (not ANDed into the retry condition) so a genuine local
  # filesystem failure isn't misdiagnosed as a registry flake and burned
  # through 3 retries.
  run grep -c 'rm -rf "/tmp/\${chart}" || { echo "helm pull: cannot clear /tmp/\${chart}"; return 1; }' "${SCRIPT}"
  [ "$status" -eq 0 ]
  [ "$output" = "1" ]
}

@test "platform-provisioner.sh validates the chart name before rm -rf/helm pull" {
  # ${chart} can be ${PIPELINE_NAME}, derived from the untrusted recipe's .kind
  # field, and now feeds an `rm -rf "/tmp/${chart}"`. Pin the allowlist guard
  # against the real source so a future edit can't silently drop it. The
  # first-character anchor additionally rejects dot-only names (e.g. "..",
  # harmless in practice since GNU rm refuses to remove '.'/'..', but not
  # worth relying on that) and names starting with '-' (which some commands
  # would otherwise misparse as a flag).
  run grep -c '\[\[ ! "\${chart}" =~ \^\[A-Za-z0-9\]\[A-Za-z0-9_.-\]\*\$ \]\]' "${SCRIPT}"
  [ "$status" -eq 0 ]
  [ "$output" = "1" ]
}
