#!/usr/bin/env bats
#
# Regression tests for the "o11y widget already exists" idempotency guard in
# charts/provisioner-config-local/recipes/tp-automation-o11y.yaml (task
# add-card-to-o11y). PCP-20053.
#
# Bug: the guard used `[.dataPlane[] | select(...).o11yWidget] // ""`. When the
# DP exists but has no `o11yWidget` key, the array-wrap yields `[null]`, which yq
# renders as the NON-EMPTY string "- null". `[[ -n ... ]]` then wrongly concludes
# the widget already exists and skips page_o11y on a fresh instance, so no
# dashboards are ever created. Fix: drop the array-wrap so the value is "" when
# absent and "true" when present.
#

bats_require_minimum_version 1.5.0

export PROJECT_ROOT="$(cd "$(dirname "${BATS_TEST_DIRNAME}")/../.." && pwd)"
# The tracked source recipe. The local/headless install copy
# (docs/recipes/automation/cp-installation/05-tp-auto-deploy-dp.yaml) is gitignored
# and generated from this chart recipe by generate-recipe.sh, so fixing this one is
# sufficient — the generated copy inherits the fix on regeneration.
RECIPE="${PROJECT_ROOT}/charts/provisioner-config-local/recipes/tp-automation-o11y.yaml"

# Mirror of the recipe guard expressions (kept in sync with the recipe; the last
# tests assert the recipe itself uses this corrected, non-array-wrapped form).
# Two helpers so each exercises the exact env var the recipe uses for that line:
# the k8s DP line keys on TP_AUTO_K8S_DP_NAME, the BMDP line on TP_AUTO_K8S_BMDP_NAME.
o11y_widget_status() {
  local report_file="$1" dp_name="$2"
  TP_AUTO_K8S_DP_NAME="$dp_name" yq e -r '.dataPlane[] | select(.name == env(TP_AUTO_K8S_DP_NAME)).o11yWidget // ""' "$report_file"
}

o11y_widget_status_bmdp() {
  local report_file="$1" dp_name="$2"
  TP_AUTO_K8S_BMDP_NAME="$dp_name" yq e -r '.dataPlane[] | select(.name == env(TP_AUTO_K8S_BMDP_NAME)).o11yWidget // ""' "$report_file"
}

setup() {
  REPORT="${BATS_TEST_TMPDIR}/report.yaml"
}

# ============================================================================
# Guard behaviour — DP present but o11yWidget absent (fresh instance)
# ============================================================================

@test "absent o11yWidget yields empty status (guard does NOT skip)" {
  cat > "${REPORT}" <<'EOF'
dataPlane:
  - name: k8s-auto-dp1
    o11yConfig: true
    o11yResources: true
  - name: k8s-auto-bmdp1
    o11yConfig: true
EOF
  run o11y_widget_status "${REPORT}" "k8s-auto-dp1"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# ============================================================================
# Guard behaviour — o11yWidget already set (re-run idempotency: must skip)
# ============================================================================

@test "present o11yWidget=true yields non-empty status (guard skips)" {
  cat > "${REPORT}" <<'EOF'
dataPlane:
  - name: k8s-auto-dp1
    o11yWidget: true
EOF
  run o11y_widget_status "${REPORT}" "k8s-auto-dp1"
  [ "$status" -eq 0 ]
  [ "$output" = "true" ]
}

# ============================================================================
# Guard behaviour — no matching DP in the report
# ============================================================================

@test "no matching data plane yields empty status (guard does NOT skip)" {
  cat > "${REPORT}" <<'EOF'
dataPlane:
  - name: some-other-dp
    o11yWidget: true
EOF
  run o11y_widget_status "${REPORT}" "k8s-auto-dp1"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "empty dataPlane list yields empty status" {
  cat > "${REPORT}" <<'EOF'
dataPlane: []
EOF
  run o11y_widget_status "${REPORT}" "k8s-auto-dp1"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "missing dataPlane key yields empty status (no crash)" {
  cat > "${REPORT}" <<'EOF'
some: thing
EOF
  run o11y_widget_status "${REPORT}" "k8s-auto-dp1"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# ============================================================================
# Guard behaviour — explicit falsy o11yWidget values must NOT skip
# (the report only ever writes `true`; `// ""` treats false/null as "not done")
# ============================================================================

@test "o11yWidget: false yields empty status (guard does NOT skip)" {
  cat > "${REPORT}" <<'EOF'
dataPlane:
  - name: k8s-auto-dp1
    o11yWidget: false
EOF
  run o11y_widget_status "${REPORT}" "k8s-auto-dp1"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "o11yWidget: null yields empty status (guard does NOT skip)" {
  cat > "${REPORT}" <<'EOF'
dataPlane:
  - name: k8s-auto-dp1
    o11yWidget: null
EOF
  run o11y_widget_status "${REPORT}" "k8s-auto-dp1"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# ============================================================================
# End-to-end skip decision — mirror of the recipe's combined OR guard:
#   if [[ -n "$k8s_o11y_widget_status" || -n "$bmdp_o11y_widget_status" ]]; then skip
# widget_guard_skips returns 0 (skip) if EITHER DP already has o11yWidget, else 1 (run).
# ============================================================================

widget_guard_skips() {
  local report_file="$1" k8s bmdp
  k8s="$(o11y_widget_status "$report_file" "k8s-auto-dp1")"
  bmdp="$(o11y_widget_status_bmdp "$report_file" "k8s-auto-bmdp1")"
  [[ -n "$k8s" || -n "$bmdp" ]]
}

@test "guard RUNS (does not skip) when neither DP has o11yWidget" {
  cat > "${REPORT}" <<'EOF'
dataPlane:
  - name: k8s-auto-dp1
    o11yConfig: true
  - name: k8s-auto-bmdp1
    o11yConfig: true
EOF
  run widget_guard_skips "${REPORT}"
  [ "$status" -eq 1 ]
}

@test "guard SKIPS when only the k8s DP has o11yWidget" {
  cat > "${REPORT}" <<'EOF'
dataPlane:
  - name: k8s-auto-dp1
    o11yWidget: true
  - name: k8s-auto-bmdp1
    o11yConfig: true
EOF
  run widget_guard_skips "${REPORT}"
  [ "$status" -eq 0 ]
}

@test "guard SKIPS when only the bmdp DP has o11yWidget" {
  cat > "${REPORT}" <<'EOF'
dataPlane:
  - name: k8s-auto-dp1
    o11yConfig: true
  - name: k8s-auto-bmdp1
    o11yWidget: true
EOF
  run widget_guard_skips "${REPORT}"
  [ "$status" -eq 0 ]
}

# ============================================================================
# Recipe regression — must NOT use the buggy array-wrapped form
# ============================================================================

@test "recipe guard does not use the buggy [.dataPlane[] ... o11yWidget] array-wrap" {
  # Guard against a moved/renamed recipe masking the check: grep exits 2 on a
  # missing file (which would also satisfy "-ne 0"), so assert the file exists and
  # require grep's exit code to be exactly 1 (ran successfully, found no match).
  [ -f "${RECIPE}" ]
  run grep -nE '\[\.dataPlane\[\][^]]*\.o11yWidget\]' "${RECIPE}"
  [ "$status" -eq 1 ]
}

@test "recipe guard uses the corrected '.o11yWidget // \"\"' form for both DP and BMDP" {
  run grep -c 'select(.name == env(TP_AUTO_K8S_DP_NAME)).o11yWidget // ""' "${RECIPE}"
  [ "$status" -eq 0 ]
  [ "$output" = "1" ]
  run grep -c 'select(.name == env(TP_AUTO_K8S_BMDP_NAME)).o11yWidget // ""' "${RECIPE}"
  [ "$status" -eq 0 ]
  [ "$output" = "1" ]
}

# ============================================================================
# add-card-to-o11y silent-failure marker (PCP-23371)
#
# Bug: when page_o11y.py fails, the add-card-to-o11y task still hardcodes
# `exit 0` (intentionally non-blocking — a dashboard-widget task should not
# fail the whole TP install) but the failure was completely unreported: no
# marker distinguished "failed but allowed to continue" from "succeeded",
# so parse-log.sh's "Detected Issues" summary reported nothing.
# Fix: emit a greppable [WARNING] line when ${_result} != 0, still exit 0.
# ============================================================================

# Mirror of the recipe's add-card-to-o11y result-handling block (kept in sync
# with the recipe; the last test asserts the recipe itself uses this form).
add_card_to_o11y_result_handling() {
  local _result="$1"
  echo "python return code: ${_result}"
  if [[ "${_result}" -ne 0 ]]; then
    echo "[WARNING] add-card-to-o11y: page_o11y.py exited ${_result} — o11y dashboard cards were not configured, continuing anyway"
  fi
  return 0
}

@test "add-card-to-o11y: success (_result=0) does not emit a WARNING" {
  run add_card_to_o11y_result_handling 0
  [ "$status" -eq 0 ]
  [[ "$output" != *"[WARNING]"* ]]
}

@test "add-card-to-o11y: failure (_result!=0) emits a greppable WARNING but still returns 0" {
  run add_card_to_o11y_result_handling 1
  [ "$status" -eq 0 ]
  [[ "$output" == *"[WARNING] add-card-to-o11y: page_o11y.py exited 1"* ]]
}

@test "recipe's add-card-to-o11y task emits [WARNING] on non-zero _result" {
  run grep -c '\[WARNING\] add-card-to-o11y: page_o11y.py exited \${_result}' "${RECIPE}"
  [ "$status" -eq 0 ]
  [ "$output" = "1" ]
}

@test "recipe's add-card-to-o11y task still exits 0 unconditionally (stays non-blocking)" {
  # The task block must end with a bare 'exit 0' (not 'exit ${_result}') right
  # after the WARNING guard — non-blocking behavior must be preserved.
  # Range starts at the python-invocation line (not 'name: add-card-to-o11y')
  # so it excludes the task's earlier, unrelated "already configured" skip-guard
  # exit 0 — otherwise the positive 'exit 0' assertion below would pass even if
  # the WARNING guard's own exit 0 were removed.
  run awk '/Running file \$\{PYTHON_FILE_ENTRY_POINT_O11Y\}/,/name: print-report/' "${RECIPE}"
  [ "$status" -eq 0 ]
  [[ "$output" == *"exit 0"* ]]
  [[ "$output" != *"exit \${_result}"* ]]
}
