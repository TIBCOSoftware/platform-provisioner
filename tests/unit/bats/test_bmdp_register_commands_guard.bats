#!/usr/bin/env bats
#
# Regression tests for the BMDP (Control Tower) registration guard.
#
# Bug: the registration page renders its command list behind a "Display Details &
# Registration Commands" toggle, under an *ngIf whose flag starts false, so the
# container is absent from the DOM until the toggle is clicked AND Angular has
# re-rendered. all_text_contents() is the only call in that flow that does not
# auto-wait: with zero matches it returns [] immediately, no timeout and no
# exception. Scraping straight after the click therefore yielded no commands, the
# execution loop ran zero times, nothing was deployed to the cluster, and the task
# still clicked "Done" and recorded success. Two presence-only short-circuits then
# turned that into a green pipeline: a data plane NAME in report.yaml, and a data
# plane CARD in the Control Plane list, were both treated as proof of a working data
# plane -- but a Control Plane record exists as soon as registration is submitted, so
# it proves only that an attempt was made.
#
# Coverage here is deliberately interpreter-free: the BATS job is the only required
# check on this repo, nothing runs pytest, and the runner has bats-core + yq + gettext
# but no helm and no python. So the recipe is asserted against its SOURCE file (never a
# helm-rendered artifact) and the python side is grep-only. The behavioural contract
# itself is pinned in docs/recipes/automation/tp-setup/bootstrap/tests/
# test_po_dataplane_bmdp_register.py, which CI does not run -- hence these pins.
#
# Scope: the BMDP path ONLY. The generic k8s data plane path (k8s_create_dataplane)
# carries the same latent defects and is deliberately left alone here, so nothing in
# this file may assert a repo-wide property that would also bind that method.
#

bats_require_minimum_version 1.5.0

export PROJECT_ROOT="$(cd "$(dirname "${BATS_TEST_DIRNAME}")/../.." && pwd)"
# The tracked source recipe. The local/headless install copy is gitignored and generated
# from this chart recipe by generate-recipe.sh, so this one is the source of truth.
RECIPE="${PROJECT_ROOT}/charts/provisioner-config-local/recipes/tp-automation-o11y.yaml"
BOOTSTRAP="${PROJECT_ROOT}/docs/recipes/automation/tp-setup/bootstrap"
PO_DATAPLANE="${BOOTSTRAP}/page_object/po_dataplane.py"

# Body of k8s_create_bmdp only: from its def to the next def at the same indent. Several
# pins below must not be satisfiable by the generic data plane twin, which is a near
# copy, so they are asserted against this slice rather than the whole file.
bmdp_method() {
  awk '/^    def k8s_create_bmdp\(/{f=1} f&&/^    def /&&!/k8s_create_bmdp/&&c++{exit} f' "${PO_DATAPLANE}"
}

# --- (a) the scrape must wait for the panel before reading it ------------------------

@test "the registration commands are scraped through a named seam, not inline" {
  # The seam is what makes the wait auditable and what the pytest suite drives.
  run grep -qF 'def _scrape_register_commands' "${PO_DATAPLANE}"
  [ "$status" -eq 0 ]

  bmdp_method | grep -qF '_scrape_register_commands()'
}

@test "the scrape waits for the commands container before calling all_text_contents" {
  # all_text_contents does not auto-wait, so the wait is the fix. Assert the container
  # wait appears BEFORE the read inside the seam.
  local seam
  seam="$(awk '/^    def _scrape_register_commands\(/{f=1} f&&/^    def /&&!/_scrape_register_commands/&&c++{exit} f' "${PO_DATAPLANE}")"

  # Key on the CALL, never on a mention of it: the docstring above the code discusses
  # all_text_contents by name, so an unqualified grep would match the prose and pass
  # while pinning nothing.
  local wait_line read_line
  wait_line="$(printf '%s\n' "${seam}" | grep -n 'Util.check_dom_visibility(' | head -1 | cut -d: -f1)"
  read_line="$(printf '%s\n' "${seam}" | grep -n 'all_text_contents()' | grep 'locator(' | head -1 | cut -d: -f1)"

  [ -n "${wait_line}" ]
  [ -n "${read_line}" ]
  [ "${wait_line}" -lt "${read_line}" ]
}

# --- (b) an empty command list must abort --------------------------------------------

@test "an empty registration command list aborts instead of clicking Done" {
  bmdp_method | grep -qF 'if not commands_title:'
  bmdp_method | grep -q 'produced no commands to run'
}

@test "the abort happens before the Done button is clicked" {
  local body abort_line done_line
  body="$(bmdp_method)"
  abort_line="$(printf '%s\n' "${body}" | grep -n 'produced no commands to run' | head -1 | cut -d: -f1)"
  done_line="$(printf '%s\n' "${body}" | grep -n 'data-plane-finished-btn' | head -1 | cut -d: -f1)"

  [ -n "${abort_line}" ]
  [ -n "${done_line}" ]
  [ "${abort_line}" -lt "${done_line}" ]
}

@test "a title / download-button count mismatch aborts" {
  bmdp_method | grep -q 'refusing to run mismatched commands'
}

# --- (c) completion evidence, not mere presence ---------------------------------------

@test "the report.yaml short-circuit requires completion evidence" {
  # A bare name is written as soon as any card with that name is seen.
  bmdp_method | grep -qF '_is_bmdp_complete(dp_name)'

  local predicate
  predicate="$(awk '/^    def _is_bmdp_complete\(/{f=1} f&&/^    def /&&!/_is_bmdp_complete/&&c++{exit} f' "${PO_DATAPLANE}")"
  printf '%s\n' "${predicate}" | grep -qF 'BMDP_STATUS_RUNNING'
  # The CLI registration path writes only healthStatus; rejecting it would make the
  # browser flow replay a wizard over a data plane that is already in place.
  printf '%s\n' "${predicate}" | grep -qF 'BMDP_HEALTH_STATUS_GREEN'
}

@test "the completion status is only written after the workload is proven" {
  # Both guards treat this status as proof the data plane came up, and the report file
  # outlives the process on a host mount. Writing it anywhere that runs before the
  # workload probe would let an aborted run short-circuit the next retry to green.
  local marker
  marker="$(awk '/^    def _mark_bmdp_complete\(/{f=1} f&&/^    def /&&!/_mark_bmdp_complete/&&c++{exit} f' "${PO_DATAPLANE}")"
  printf '%s\n' "${marker}" | grep -qF 'set_dataplane_info(dp_name, "status"'

  # k8s_wait_bmdp_ready runs BEFORE the workload probe, so the copy it still owns (kept for
  # the non-BMDP contract) must stay behind the is_update_report guard. Any UNGUARDED write
  # outside _mark_bmdp_complete reintroduces the defect.
  local ready
  ready="$(awk '/^    def k8s_wait_bmdp_ready\(/{f=1} f&&/^    def /&&!/k8s_wait_bmdp_ready/&&c++{exit} f' "${PO_DATAPLANE}")"
  printf '%s\n' "${ready}" | grep -qF 'if is_update_report:'

  local guard_line write_line
  guard_line="$(printf '%s\n' "${ready}" | grep -n 'if is_update_report:' | head -1 | cut -d: -f1)"
  write_line="$(printf '%s\n' "${ready}" | grep -n 'set_dataplane_info(dp_name, "status"' | head -1 | cut -d: -f1)"
  [ -n "${write_line}" ]
  [ "${guard_line}" -lt "${write_line}" ]
}

@test "the readiness wait is called with the report update suppressed" {
  # k8s_wait_bmdp_ready runs BEFORE the workload probe on every BMDP path.
  local calls deferred
  calls="$(grep -c 'self.k8s_wait_bmdp_ready(dp_name' "${PO_DATAPLANE}")"
  deferred="$(grep -c 'self.k8s_wait_bmdp_ready(dp_name, False)' "${PO_DATAPLANE}")"
  [ "${calls}" -eq "${deferred}" ]
}

@test "cluster lookups distinguish 'absent' from 'could not be queried'" {
  # get_command_output returns None on ANY non-zero exit, so treating None as 'absent'
  # would let a transient kubectl failure delete a live data plane.
  grep -qF -- '--ignore-not-found' "${PO_DATAPLANE}"
  local state
  state="$(awk '/^    def _namespace_state\(/{f=1} f&&/^    def /&&!/_namespace_state/&&c++{exit} f' "${PO_DATAPLANE}")"
  printf '%s\n' "${state}" | grep -qF '"unknown"'
}

@test "Kubernetes names are validated before being interpolated into a shell command" {
  grep -qF 'def _safe_k8s_name' "${PO_DATAPLANE}"
  grep -qF '_safe_k8s_name(namespace)' "${PO_DATAPLANE}"
}

@test "the BMDP path never deletes a data plane" {
  # An automatic delete-and-re-register was considered and rejected: the only evidence
  # available is a namespace name from the environment, never read back from the record
  # being deleted, and this entry point is reachable from the unauthenticated local script
  # endpoint with a caller-supplied data plane name and namespace. The acceptance criterion
  # is met by failing the task instead.
  local body
  body="$(bmdp_method)"
  ! printf '%s
' "${body}" | grep -q 'k8s_delete_dataplane'

  local recover
  recover="$(awk '/^    def _recover_unhealthy_bmdp\(/{f=1} f&&/^    def /&&!/_recover_unhealthy_bmdp/&&c++{exit} f' "${PO_DATAPLANE}")"
  ! printf '%s
' "${recover}" | grep -q 'k8s_delete_dataplane'
  printf '%s
' "${recover}" | grep -qF 'bmdp_unhealthy_existing.png'
}

@test "an unhealthy existing data plane is judged on the namespace it was registered with" {
  # An existing data plane may predate the current environment default.
  grep -qF 'def _bmdp_namespace' "${PO_DATAPLANE}"
  local workload
  workload="$(awk '/^    def _assert_bmdp_workload\(/{f=1} f&&/^    def /&&!/_assert_bmdp_workload/&&c++{exit} f' "${PO_DATAPLANE}")"
  printf '%s
' "${workload}" | grep -qF '_bmdp_namespace(dp_name)'
  ! printf '%s
' "${workload}" | grep -q 'ENV.TP_AUTO_K8S_BMDP_NAMESPACE'
}

@test "the registration-page gate does not hinge on a single class" {
  # If one anchor is renamed by a future Control Plane the gate must not fail the whole flow.
  local body
  body="$(bmdp_method)"
  printf '%s
' "${body}" | grep -qF 'BMDP_REGISTER_LEGACY_CONTENT'
  printf '%s
' "${body}" | grep -qF 'BMDP_REGISTER_FINISHED_CONTENT'
  printf '%s
' "${body}" | grep -qF 'BMDP_REGISTER_FINISHED_BUTTON'
}

@test "the Control Plane card short-circuit is health-verified" {
  run grep -qF 'def _is_dataplane_status_green' "${PO_DATAPLANE}"
  [ "$status" -eq 0 ]
  bmdp_method | grep -qF '_is_dataplane_status_green(dp_name)'
}

@test "the health oracle uses the data plane status icon and never tunnel state" {
  local oracle
  oracle="$(awk '/^    def _is_dataplane_status_green\(/{f=1} f&&/^    def /&&!/_is_dataplane_status_green/&&c++{exit} f' "${PO_DATAPLANE}")"

  printf '%s\n' "${oracle}" | grep -qF 'data-plane-status svg.green'
  # A disconnected tunnel is not a reason to destroy a data plane.
  ! printf '%s\n' "${oracle}" | grep -q 'tunnel-status'
}

@test "the completion marker creates the report entry before writing into it" {
  # set_dataplane_info only mutates an entry that already exists, so the order is
  # load-bearing: writing the marker first is a silent no-op.
  local marker set_line info_line
  marker="$(awk '/^    def _mark_bmdp_complete\(/{f=1} f&&/^    def /&&!/_mark_bmdp_complete/&&c++{exit} f' "${PO_DATAPLANE}")"

  set_line="$(printf '%s\n' "${marker}" | grep -n 'ReportYaml.set_dataplane(' | head -1 | cut -d: -f1)"
  info_line="$(printf '%s\n' "${marker}" | grep -n 'ReportYaml.set_dataplane_info(' | head -1 | cut -d: -f1)"

  [ -n "${set_line}" ]
  [ -n "${info_line}" ]
  [ "${set_line}" -lt "${info_line}" ]
}

@test "the BMDP path proves a real workload, not just a green card" {
  run grep -qF 'def _assert_bmdp_workload' "${PO_DATAPLANE}"
  [ "$status" -eq 0 ]
  bmdp_method | grep -qF '_assert_bmdp_workload(dp_name)'
}

# --- (d) control flow ------------------------------------------------------------------

@test "k8s_create_bmdp does not recurse" {
  # The old code recursed after deleting the data plane, and the outer frame then fell
  # through to re-scrape a page that had moved on. Both the delete and the recursion are
  # gone: a failed registration now fails the task and a human decides what to do, so the
  # fall-through cannot exist.
  local body
  body="$(bmdp_method)"
  ! printf '%s
' "${body}" | grep -q 'self.k8s_create_bmdp('
}

@test "the legacy 1.4 registration panel is still supported" {
  # Older Control Planes only render '.install-content'. Removing this probe would drop
  # support for them, so its budget is pinned verbatim.
  bmdp_method | grep -qF 'Util.check_dom_visibility(self.page, self.page.locator(BMDP_REGISTER_LEGACY_CONTENT).first, 2, 10)'
}

@test "a generic primary button cannot satisfy the registration-page gate" {
  # It matches a button on nearly every wizard page; treating it as proof of the
  # registration step is what made the original guard unreachable.
  local body gate
  body="$(bmdp_method)"
  gate="$(printf '%s\n' "${body}" | grep -n 'is_register_page = ' | head -1 | cut -d: -f1)"
  [ -n "${gate}" ]
  # The gate itself must be built only from the two page-specific anchors.
  printf '%s\n' "${body}" | sed -n "${gate},$((gate + 1))p" | grep -qF 'BMDP_REGISTER_LEGACY_CONTENT'
  printf '%s\n' "${body}" | sed -n "${gate},$((gate + 1))p" | grep -qF 'BMDP_REGISTER_FINISHED_CONTENT'
  ! printf '%s\n' "${body}" | sed -n "${gate},$((gate + 1))p" | grep -qF 'BMDP_REGISTER_PRIMARY_BUTTON'
}

# --- (e) the recipe layer ----------------------------------------------------------------

@test "create-bmdp guard keys on the completion status, not a bare name" {
  run yq e '.tasks[] | select(.name == "create-bmdp") | .script.content' "${RECIPE}"
  [ "$status" -eq 0 ]
  [[ "$output" == *'Running successfully'* ]]
  # The old predicate selected on the name alone and exited 0 on it.
  [[ "$output" != *'select(.name == env(TP_AUTO_K8S_BMDP_NAME)) | .name'* ]]
}

@test "create-bmdp retry budget matches the in-process bound" {
  run yq e '.tasks[] | select(.name == "create-bmdp") | .script.retryCount' "${RECIPE}"
  [ "$status" -eq 0 ]
  [ "$output" = "3" ]
}

@test "create-bmdp still fails the pipeline on a non-zero exit" {
  run yq e '.tasks[] | select(.name == "create-bmdp") | .script.ignoreErrors' "${RECIPE}"
  [ "$status" -eq 0 ]
  [ "$output" = "false" ]
}
