#!/usr/bin/env bats
#
# Regression tests for the "capability enabled while this run creates no Data Plane"
# guard. PCP-22771.
#
# Bug: a capability is provisioned INSIDE a Data Plane, so GUI_TP_AUTO_ENABLE_DP=false
# together with e.g. GUI_TP_AUTO_ENABLE_FLOGO=true can never be satisfied. The pipeline
# used to run on: page_dp.py skipped every capability and then walked an unguarded
# epilogue into a Data Plane that was never created, so the run either exploded far from
# the cause or exited 0 having provisioned nothing. Fix: a recipe pre-flight task that
# names every conflicting flag at once and fails before any task touches the CP, plus a
# fail-fast guard in page_dp.py before the browser is launched, plus relocating the
# page_dp.py / page_bmdp.py epilogues inside their create guards, plus defaulting the
# headless installer's capability flags to GUI_TP_AUTO_ENABLE_DP (group (f)).
#
# Scope of the pre-flight: exactly the capabilities whose deploy-* task executes page_dp.py.
# deploy-infra-mcp-server and deploy-mcp-hub run case/ modules against an ALREADY registered Data
# Plane, so they are legitimate DP=false runs and their flags are pinned here as PASSING. That
# exemption is PER-FLAG, not per-run: an exempt capability sitting next to a genuinely requested
# page_dp.py capability must still refuse. Note that the shipped guiEnv default is
# GUI_TP_AUTO_ENABLE_FLOGO: true (tp-automation-o11y.yaml:44), so a user who unticks only
# "Create DP" in the GUI IS refused - intentionally: the Flogo checkbox is right there and the
# refusal message names it.
#
# Coverage here is deliberately interpreter-free: the BATS job is the only required
# check on this repo, nothing runs pytest, and the runner has bats-core + yq + gettext
# but no helm and no python. So the recipe is asserted against its SOURCE file (never a
# helm-rendered artifact) and the python side is grep-only.
#

bats_require_minimum_version 1.5.0

export PROJECT_ROOT="$(cd "$(dirname "${BATS_TEST_DIRNAME}")/../.." && pwd)"
# The tracked source recipe. The local/headless install copy
# (docs/recipes/automation/cp-installation/05-tp-auto-deploy-dp.yaml) is gitignored and
# generated from this chart recipe by generate-recipe.sh, so this one is the source of truth.
RECIPE="${PROJECT_ROOT}/charts/provisioner-config-local/recipes/tp-automation-o11y.yaml"
BOOTSTRAP="${PROJECT_ROOT}/docs/recipes/automation/tp-setup/bootstrap"
PAGE_DP="${BOOTSTRAP}/page_dp.py"
PAGE_BMDP="${BOOTSTRAP}/page_bmdp.py"
GUARD_TASK="validate-dp-capability-flags"
# The headless installer writes the guiEnv values this recipe is then driven by. Only its
# GUI_TP_AUTO_ENABLE_* derivation is exercised, in group (f).
INSTALLER="${PROJECT_ROOT}/docs/recipes/k8s/on-prem/scripts/headless/tp-install-on-prem.sh"

task_body() {
  TASK_NAME="$1" yq e '.tasks[] | select(.name == strenv(TASK_NAME)) | .script.content' "${RECIPE}"
}

task_index() {
  TASK_NAME="$1" yq e '.tasks | to_entries | .[] | select(.value.name == strenv(TASK_NAME)) | .key' "${RECIPE}"
}

# Mirror of common::replace_env_variables in charts/common-dependency/scripts/_functions.sh:
# envsubst is SCOPED to the keys declared under .meta.globalEnvVariable, which is why the
# task body may keep its own ${_local} variables. envsubst treats the shell-format as a
# token list, so newline-vs-comma separation is irrelevant.
envsubst_keys() {
  yq e '.meta.globalEnvVariable | keys | .[] | " $" + .' "${RECIPE}" | tr '\n' ' '
}

# Every TP_AUTO_ENABLE_* name that some task turns into a TP_AUTO_IS_PROVISION_* export,
# i.e. the capability set derived from the recipe itself. Takes the SECOND capture group:
# the two names differ (TP_AUTO_IS_PROVISION_SPRINGBOOT=${TP_AUTO_ENABLE_SB}).
recipe_capability_enable_names() {
  yq e '.tasks[] | select(has("script")) | .script.content // ""' "${RECIPE}" \
    | grep -oE 'export TP_AUTO_IS_PROVISION_[A-Z0-9_]+=\$\{TP_AUTO_ENABLE_[A-Z0-9_]+\}' \
    | sed -E 's/^.*\$\{TP_AUTO_ENABLE_([A-Z0-9_]+)\}$/\1/' \
    | LC_ALL=C sort -u
}

# Capabilities the recipe provisions that the pre-flight deliberately does NOT check, because
# their deploy-* task does not run page_dp.py: deploy-infra-mcp-server runs
# `python -m case.k8s_provision_infra_mcp_server` against an ALREADY registered Data Plane, so
# "the Data Plane exists, now add this capability" is a supported TP_AUTO_ENABLE_DP=false run.
# Kept as an explicit, asserted-exactly set so that exempting a second capability has to be a
# deliberate, reviewed edit here rather than a quiet hole in the drift test below.
# (TP_AI_ENABLE_MCP_HUB needs no entry: it is never exported as TP_AUTO_IS_PROVISION_*, so the
# extraction above never sees it. Its behaviour is pinned in group (a) instead.)
PREFLIGHT_EXEMPT_CAPABILITIES=("INFRA_MCP_SERVER")

is_preflight_exempt() {
  local _name="$1" _exempt
  for _exempt in "${PREFLIGHT_EXEMPT_CAPABILITIES[@]}"; do
    [ "$_name" = "$_exempt" ] && return 0
  done
  return 1
}

# Run the extracted pre-flight body. Running the real body instead of a hand-written
# mirror removes any chance of the mirror drifting away from the recipe. Every capability
# flag is pre-seeded empty so an ambient TP_AUTO_* in the developer's shell cannot decide
# the verdict; `env` applies assignments left to right, so "$@" overrides.
run_preflight() {
  env TP_AUTO_ENABLE_DP= TP_AUTO_ENABLE_FLOGO= TP_AUTO_ENABLE_BWCE= TP_AUTO_ENABLE_BW5CE= \
      TP_AUTO_ENABLE_TIBCOHUB= TP_AUTO_ENABLE_SB= TP_AUTO_ENABLE_EMS= \
      TP_AUTO_ENABLE_INFRA_MCP_SERVER= TP_AI_ENABLE_MCP_HUB= TP_AUTO_USE_CLI= \
      TP_AUTO_K8S_DP_NAME="k8s-auto-dp1" TP_AUTO_REPORT_PATH="${BATS_TEST_TMPDIR}/report" \
      "$@" bash "${BODY}"
}

setup() {
  BODY="${BATS_TEST_TMPDIR}/preflight.sh"
  task_body "${GUARD_TASK}" > "${BODY}"
}

# ============================================================================
# (a) Behavioural — the pre-flight verdict, driven by the real task body
# ============================================================================

@test "DP=false + FLOGO=true fails and names the offending flag" {
  run run_preflight TP_AUTO_ENABLE_DP=false TP_AUTO_ENABLE_FLOGO=true
  [ "$status" -eq 1 ]
  [[ "$output" == *"GUI_TP_AUTO_ENABLE_FLOGO=true"* ]]
  [[ "$output" == *"k8s-auto-dp1"* ]]
}

# CLI mode is deliberately NOT exempt. Skipping the check when TP_AUTO_USE_CLI=true is the
# intuitive guess and it is wrong: cli-full-automation does not REPLACE the deploy-* tasks, it
# runs alongside them. cli-full-automation is gated on ${TP_AUTO_USE_CLI}, but deploy-flogo is
# gated on ${TP_AUTO_ENABLE_FLOGO} ALONE and executes page_dp.py (PYTHON_FILE_ENTRY_POINT), so
# with no Data Plane it hits the PCP-22771 path for real. These two pin the decision so nobody
# "optimises" the exemption back in.
@test "USE_CLI=true + DP=false + FLOGO=true STILL FAILS: deploy-flogo runs page_dp.py regardless of CLI mode" {
  run run_preflight TP_AUTO_USE_CLI=true TP_AUTO_ENABLE_DP=false TP_AUTO_ENABLE_FLOGO=true
  [ "$status" -eq 1 ]
  [[ "$output" == *"GUI_TP_AUTO_ENABLE_FLOGO=true"* ]]
}

@test "the pre-flight body has no CLI-mode exemption and never substitutes the CLI flag" {
  [ -s "${BODY}" ]
  # No code reading it...
  run grep -c '_use_cli' "${BODY}"
  [ "$output" = "0" ]
  # ...and no ${...} reference to it ANYWHERE, comments included: envsubst rewrites those at
  # render time, so a comment citing ${TP_AUTO_USE_CLI} would ship as a comment citing "false".
  run grep -cF '${TP_AUTO_USE_CLI}' "${BODY}"
  [ "$output" = "0" ]
}

# The recipe wiring the decision rests on: deploy-flogo is gated on its own capability flag only,
# and the shared entry point really is page_dp.py. If either changes, revisit the exemption.
@test "deploy-flogo is gated on its capability flag alone and runs the page_dp.py entry point" {
  [ -f "${RECIPE}" ]
  run grep -cE '^- condition: \$\{TP_AUTO_ENABLE_FLOGO\}' "${RECIPE}"
  [ "$output" = "1" ]
  run grep -cE '^ +PYTHON_FILE_ENTRY_POINT: page_dp\.py\r?$' "${RECIPE}"
  [ "$output" = "1" ]
}

@test "DP=false + EMS=true fails" {
  run run_preflight TP_AUTO_ENABLE_DP=false TP_AUTO_ENABLE_EMS=true
  [ "$status" -eq 1 ]
  [[ "$output" == *"GUI_TP_AUTO_ENABLE_EMS=true"* ]]
}

@test "DP=false + MCP_HUB=true PASSES: deploy-mcp-hub targets an already registered Data Plane" {
  # Regression pin. deploy-mcp-hub runs `python -m case.k8s_deploy_mcp_hub`, which navigates to
  # an EXISTING Data Plane (deploy_mcp_gateway(dp_name)) and never reads TP_AUTO_IS_CREATE_DP.
  # "The Data Plane already exists, now add MCP Hub" was a supported exit-0 DP=false run, and an
  # earlier revision of this pre-flight aborted it before anything executed.
  run run_preflight TP_AUTO_ENABLE_DP=false TP_AI_ENABLE_MCP_HUB=true
  [ "$status" -eq 0 ]
  [[ "$output" != *"GUI_TP_AI_ENABLE_MCP_HUB"* ]]
}

@test "DP=false + INFRA_MCP_SERVER=true PASSES: deploy-infra-mcp-server targets an existing Data Plane" {
  # The twin of the test above: deploy-infra-mcp-server runs
  # `python -m case.k8s_provision_infra_mcp_server`, which does goto_dataplane(TP_AUTO_K8S_DP_NAME)
  # on a Data Plane it expects to be there already.
  # Note the seeding: run_preflight blanks every other capability, so this row shows only that
  # INFRA_MCP_SERVER alone does not trigger the guard. It is NOT "an Infra MCP run is exempt" - the
  # test below pins that, against the flags the recipe actually ships.
  run run_preflight TP_AUTO_ENABLE_DP=false TP_AUTO_ENABLE_INFRA_MCP_SERVER=true
  [ "$status" -eq 0 ]
  [[ "$output" != *"GUI_TP_AUTO_ENABLE_INFRA_MCP_SERVER"* ]]
}

@test "DP=false + FLOGO=true + INFRA_MCP_SERVER=true FAILS: the exemption is per-FLAG, not per-run" {
  # The semantics the exemption above makes it easy to misread. Exempting INFRA_MCP_SERVER exempts
  # THAT FLAG, never the run: Flogo really was requested and really will not be delivered, so the
  # pre-flight must still refuse and must still name Flogo.
  #
  # This is the run a GUI user gets by unticking only "Create DP", because the recipe ships
  # GUI_TP_AUTO_ENABLE_FLOGO: true - asserted here so that changing the default reds this test
  # rather than quietly changing what the row means.
  run yq e '.meta.guiEnv.GUI_TP_AUTO_ENABLE_FLOGO' "${RECIPE}"
  [ "$output" = "true" ]

  run run_preflight TP_AUTO_ENABLE_DP=false TP_AUTO_ENABLE_FLOGO=true \
      TP_AUTO_ENABLE_INFRA_MCP_SERVER=true
  [ "$status" -eq 1 ]
  [[ "$output" == *"GUI_TP_AUTO_ENABLE_FLOGO=true"* ]]
  [[ "$output" != *"GUI_TP_AUTO_ENABLE_INFRA_MCP_SERVER"* ]]
}

@test "every conflicting flag is named in ONE message" {
  # The whole point of the pre-flight: it is the only place that sees all flags at once,
  # so a user must not have to fix one capability, re-run, and discover the next.
  # SB is in the mix because its GUI name is not mechanically derived from the pipeline global.
  run run_preflight TP_AUTO_ENABLE_DP=false TP_AUTO_ENABLE_FLOGO=true \
      TP_AUTO_ENABLE_EMS=true TP_AUTO_ENABLE_SB=true
  [ "$status" -eq 1 ]
  [[ "$output" == *"GUI_TP_AUTO_ENABLE_FLOGO=true"* ]]
  [[ "$output" == *"GUI_TP_AUTO_ENABLE_EMS=true"* ]]
  [[ "$output" == *"GUI_TP_AUTO_ENABLE_SB=true"* ]]
}

@test "an exempt capability alongside a real conflict does not mask the conflict" {
  # The exemptions must be per-flag, not an early return that swallows the whole verdict.
  run run_preflight TP_AUTO_ENABLE_DP=false TP_AUTO_ENABLE_INFRA_MCP_SERVER=true \
      TP_AI_ENABLE_MCP_HUB=true TP_AUTO_ENABLE_FLOGO=true
  [ "$status" -eq 1 ]
  [[ "$output" == *"GUI_TP_AUTO_ENABLE_FLOGO=true"* ]]
  [[ "$output" != *"GUI_TP_AUTO_ENABLE_INFRA_MCP_SERVER"* ]]
  [[ "$output" != *"GUI_TP_AI_ENABLE_MCP_HUB"* ]]
}

# --- the comparison contract: two sides, two deciding layers ---------------------------------
# The two sides of the pre-flight are compared DIFFERENTLY, on purpose, because a DIFFERENT layer
# decides each of them:
#
#   * capability side, EXACT == "true" - whether a capability's deploy-* task is SCHEDULED is
#     decided by the runner, charts/generic-runner/scripts/_funcs_pipeline.sh:99:
#       [ "${_recipe_task_condition}" == "true" ] || { echo "Skipping task..."; continue; }
#     so a capability flag that is not exactly "true" is never requested at all, and flagging it
#     would abort a run in which that capability was never going to execute.
#
#   * Data Plane side, LOWERCASE TOLERANT - whether the Data Plane is CREATED is decided by
#     python, docs/recipes/automation/tp-setup/bootstrap/utils/env.py:132:
#       TP_AUTO_IS_CREATE_DP = os.environ.get("TP_AUTO_IS_CREATE_DP", "false").lower() == "true"
#     inside whichever task ends up running page_dp.py. TP_AUTO_IS_CREATE_DP is a pipeline global
#     (tp-automation-o11y.yaml:180, straight from GUI_TP_AUTO_ENABLE_DP) that deploy-flogo inherits
#     rather than re-exports, so DP='True' skips create-dp but page_dp.py, launched by deploy-flogo,
#     reads it as truthy and creates the Data Plane itself. The guard must match python's tolerance
#     or it refuses a configuration that works.
#
# The rows below are the whole truth table for DP x capability.

@test "DP=true + FLOGO=true passes: the runner schedules create-dp and python creates the Data Plane" {
  run run_preflight TP_AUTO_ENABLE_DP=true TP_AUTO_ENABLE_FLOGO=true
  [ "$status" -eq 0 ]
}

@test "DP='True' + FLOGO=true passes: create-dp is skipped, but page_dp.py under deploy-flogo still creates the Data Plane" {
  # The row that decides the whole contract, and a configuration that WORKS TODAY: the runner
  # skips create-dp (its condition is an exact match, _funcs_pipeline.sh:99) but schedules
  # deploy-flogo, whose page_dp.py run sees the inherited TP_AUTO_IS_CREATE_DP='True', lowercases
  # it (utils/env.py:132) and creates the Data Plane before provisioning Flogo. An exact match on
  # the DP side here aborts that run - a regression, not a fix.
  run run_preflight TP_AUTO_ENABLE_DP=True TP_AUTO_ENABLE_FLOGO=true
  [ "$status" -eq 0 ]
}

@test "DP='TRUE' + FLOGO=true passes: python lowercases, so any casing still creates the Data Plane" {
  run run_preflight TP_AUTO_ENABLE_DP=TRUE TP_AUTO_ENABLE_FLOGO=true
  [ "$status" -eq 0 ]
}

@test "DP=true + FLOGO='True' passes: the runner never schedules deploy-flogo" {
  # create-dp runs; deploy-flogo is skipped by the runner. Nothing is unsatisfiable.
  run run_preflight TP_AUTO_ENABLE_DP=true TP_AUTO_ENABLE_FLOGO=True
  [ "$status" -eq 0 ]
}

@test "DP='True' + FLOGO='True' passes: no capability is requested and the Data Plane is created anyway" {
  run run_preflight TP_AUTO_ENABLE_DP=True TP_AUTO_ENABLE_FLOGO=True
  [ "$status" -eq 0 ]
}

@test "DP=false + FLOGO=true FAILS: the runner schedules deploy-flogo, python creates no Data Plane" {
  # THE PCP-22771 bug, as a truth-table row; the message content is asserted in group (a) above.
  run run_preflight TP_AUTO_ENABLE_DP=false TP_AUTO_ENABLE_FLOGO=true
  [ "$status" -eq 1 ]
  # The verdict must show what was actually typed, not a value the guard assumed.
  [[ "$output" == *"GUI_TP_AUTO_ENABLE_DP='false'"* ]]
}

@test "DP=false + FLOGO='True' passes: the runner never schedules deploy-flogo" {
  # The capability side is exact, so 'True' never requests Flogo, so nothing is unsatisfiable.
  run run_preflight TP_AUTO_ENABLE_DP=false TP_AUTO_ENABLE_FLOGO=True
  [ "$status" -eq 0 ]
}

@test "DP=false + FLOGO='TRUE' passes: the runner skips deploy-flogo too" {
  # Same rule, upper case: 'TRUE' never schedules deploy-flogo, so failing here would abort a run
  # in which no capability task was ever going to execute.
  run run_preflight TP_AUTO_ENABLE_DP=false TP_AUTO_ENABLE_FLOGO=TRUE
  [ "$status" -eq 0 ]
}

@test "DP=false + no capability passes" {
  run run_preflight TP_AUTO_ENABLE_DP=false
  [ "$status" -eq 0 ]
}

@test "unset DP + no capability passes (must never false-fire)" {
  run run_preflight
  [ "$status" -eq 0 ]
}

# --- the misconfiguration breadcrumb is cleaned up on success --------------------------------

@test "both success paths remove a stale misconfiguration.txt" {
  # TP_AUTO_REPORT_PATH is bind mounted to the host in the headless install
  # (docs/recipes/k8s/on-prem/scripts/headless/tp-install-on-prem.sh:436), so a breadcrumb written
  # by an earlier failing run outlives that run: without cleanup it sits next to a green run's
  # artefacts and reads as a current failure.
  local crumb="${BATS_TEST_TMPDIR}/report/misconfiguration.txt"

  # A failing run writes it...
  run run_preflight TP_AUTO_ENABLE_DP=false TP_AUTO_ENABLE_FLOGO=true
  [ "$status" -eq 1 ]
  [ -f "${crumb}" ]

  # ...the "Data Plane will be created" exit removes it...
  run run_preflight TP_AUTO_ENABLE_DP=true TP_AUTO_ENABLE_FLOGO=true
  [ "$status" -eq 0 ]
  [ ! -f "${crumb}" ]

  # ...and so does the "no capability requested" exit.
  echo stale > "${crumb}"
  [ -f "${crumb}" ]
  run run_preflight TP_AUTO_ENABLE_DP=false
  [ "$status" -eq 0 ]
  [ ! -f "${crumb}" ]
}

@test "cleanup never decides the verdict: missing or empty report path still exits 0" {
  # The pre-flight fails on flags, never on housekeeping. The report directory usually does not
  # exist yet on a success path, and TP_AUTO_REPORT_PATH could be blanked by a caller.
  run run_preflight TP_AUTO_ENABLE_DP=true TP_AUTO_REPORT_PATH="${BATS_TEST_TMPDIR}/no/such/dir"
  [ "$status" -eq 0 ]
  run run_preflight TP_AUTO_ENABLE_DP=false TP_AUTO_REPORT_PATH=
  [ "$status" -eq 0 ]
}

# ============================================================================
# (b) Source-recipe structure — asserted against the source YAML, not a render
# ============================================================================

@test "pre-flight task exists, is unconditional, and never retries" {
  [ -f "${RECIPE}" ]
  [ -s "${BODY}" ]
  run task_body "${GUARD_TASK}"
  [ "$status" -eq 0 ]
  # A misconfigured recipe must stop the pipeline, not be skipped or slept over.
  run yq e ".tasks[] | select(.name == \"${GUARD_TASK}\") | .condition" "${RECIPE}"
  [ "$output" = "true" ]
  run yq e ".tasks[] | select(.name == \"${GUARD_TASK}\") | .script.retryCount" "${RECIPE}"
  [ "$output" = "0" ]
  run yq e ".tasks[] | select(.name == \"${GUARD_TASK}\") | .script.ignoreErrors" "${RECIPE}"
  [ "$output" = "false" ]
}

@test "pre-flight pins fileName: script.sh so the runner cannot execute a different file" {
  # generic-runner::setup_script WRITES the body to .fileName defaulting to script.sh
  # (charts/common-dependency/scripts/_funcs_generic_runner.sh:156-157), but
  # generic-runner::run_task resolves what it EXECUTES from .fileName, else
  # ${PIPELINE_RUNNER_SCRIPT_NAME_SH}, else script.sh (:274-284). Leave .fileName unset with
  # PIPELINE_RUNNER_SCRIPT_NAME_SH pointing elsewhere and the `[[ -f ./<name> ]]` at :333 finds
  # nothing: the subshell exits 0 and the guard silently vanishes. Fail-open is the worst
  # possible outcome for a task whose only job is to fail the run.
  run yq e ".tasks[] | select(.name == \"${GUARD_TASK}\") | .script.fileName" "${RECIPE}"
  [ "$output" = "script.sh" ]
}

@test "pre-flight is ordered after create-oauth-token and before cli-full-automation/create-dp" {
  local guard oauth cli dp
  guard="$(task_index "${GUARD_TASK}")"
  oauth="$(task_index create-oauth-token)"
  cli="$(task_index cli-full-automation)"
  dp="$(task_index create-dp)"
  # One assertion per name: a renamed/removed anchor must red here, not later as an
  # "integer expression expected" from a -lt on an empty string. `set -e` only fires on
  # the LAST command of an && list, so these cannot be chained.
  [ -n "$guard" ]
  [ -n "$oauth" ]
  [ -n "$cli" ]
  [ -n "$dp" ]
  [ "$oauth" -lt "$guard" ]
  [ "$guard" -lt "$cli" ]
  [ "$guard" -lt "$dp" ]
}

@test "pre-flight body fails the task on a conflict" {
  [ -s "${BODY}" ]
  run grep -c 'exit 1' "${BODY}"
  [ "$status" -eq 0 ]
}

@test "pre-flight body uses no envsubst-hostile constructs" {
  # grep exits 2 on a missing file (which also satisfies "-ne 0"), so require the body to
  # be non-empty and grep to exit exactly 1: ran, found nothing.
  [ -s "${BODY}" ]
  # envsubst has no :- default support; ${VAR:-x} renders as the empty string.
  run grep -nE '\$\{[A-Za-z_][A-Za-z0-9_]*:-' "${BODY}"
  [ "$status" -eq 1 ]
  [ -s "${BODY}" ]
  run grep -nF '$(' "${BODY}"
  [ "$status" -eq 1 ]
  [ -s "${BODY}" ]
  # Recipes are copied verbatim into a ConfigMap; Go templating is not available here.
  run grep -nE '\{\{|\}\}' "${BODY}"
  [ "$status" -eq 1 ]
}

@test "the DP side is case tolerant to match python, the capability side is exact to match the runner" {
  # The source-level twin of the truth table above. Asserted as two specific properties rather
  # than as a blanket "no case tolerance anywhere": that blanket rule is what pinned the regression
  # in which DP='True' + FLOGO=true - a configuration that works today - was refused.
  [ -s "${BODY}" ]
  # The Data Plane side accepts any casing, matching utils/env.py:132's .lower(). A case PATTERN,
  # not a ${_enable_dp,,} expansion - see the envsubst-immunity test below.
  # Exactly ONE case-tolerant comparison, and it is the Data Plane flag. Named rather than
  # counted: a bare number would silently accept a case fold being added somewhere else.
  run grep -cF '[Tt][Rr][Uu][Ee])' "${BODY}"
  [ "$output" = "1" ]
  run grep -cF 'case "${_enable_dp}" in' "${BODY}"
  [ "$output" = "1" ]
  # The capability side is exact, matching the exact string compare at _funcs_pipeline.sh:99.
  run grep -cF '[[ "${_value}" == "true" ]]' "${BODY}"
  [ "$output" = "1" ]
  # The count above is what keeps the Data Plane comparison the ONLY case tolerant one: a second
  # case pattern - on the capability side, say - makes it 2 and reds this test.
}

@test "pre-flight body works under EITHER envsubst: no bash-4 expansions, no arrays" {
  # The body is rendered through envsubst before bash ever sees it
  # (common::replace_env_variables, charts/common-dependency/scripts/_functions.sh:909), and the
  # runtime images install BOTH gettext and the standalone envsubst package (docker/Dockerfile:72,
  # docker/Dockerfile-on-prem:30-31). GNU gettext's envsubst understands only $VAR and ${VAR} and
  # leaves everything else verbatim; a bash-aware implementation also rewrites ${var,,} and
  # friends, at render time, when the local it names is unset - which would silently delete the
  # comparison this whole task hangs on.
  #
  # The round-trip test above can only ever exercise whichever envsubst the CI runner happens to
  # have, so it structurally cannot catch this. THIS test is the durable protection: keep the body
  # to constructs no envsubst rewrites, and the verdict cannot depend on which binary is installed.
  [ -s "${BODY}" ]
  # Case-folding parameter expansions: ${var,,} ${var,} ${var^^} ${var^}
  run grep -nE '\$\{[A-Za-z_][A-Za-z0-9_]*(,,?|\^\^?)\}' "${BODY}"
  [ "$status" -eq 1 ]
  # ...and the bare operators too, so a comment showing one off cannot be copied into code.
  [ -s "${BODY}" ]
  run grep -nF ',,}' "${BODY}"
  [ "$status" -eq 1 ]
  [ -s "${BODY}" ]
  run grep -nF '^^}' "${BODY}"
  [ "$status" -eq 1 ]
  # Bash arrays: append, expand-all and length.
  [ -s "${BODY}" ]
  run grep -nF '+=(' "${BODY}"
  [ "$status" -eq 1 ]
  [ -s "${BODY}" ]
  run grep -nF '[@]' "${BODY}"
  [ "$status" -eq 1 ]
  [ -s "${BODY}" ]
  run grep -nE '\$\{#' "${BODY}"
  [ "$status" -eq 1 ]
}

# ============================================================================
# (c) Syntax — the only syntax check a recipe body ever gets (ShellCheck in
#     .github/workflows/test.yaml only covers charts/*/scripts, dev and docker .sh)
# ============================================================================

@test "pre-flight body is valid bash" {
  [ -s "${BODY}" ]
  run bash -n "${BODY}"
  [ "$status" -eq 0 ]
}

# ============================================================================
# (c2) Real envsubst round-trip — what the pipeline actually executes
# ============================================================================

@test "envsubst resolves the pipeline globals into the locals and leaves the comparisons intact" {
  if ! command -v envsubst >/dev/null 2>&1; then
    skip "envsubst (gettext) not available"
  fi
  [ -s "${BODY}" ]
  local rendered="${BATS_TEST_TMPDIR}/preflight.rendered.sh"
  TP_AUTO_ENABLE_DP=false TP_AUTO_ENABLE_FLOGO=true TP_AUTO_K8S_DP_NAME=k8s-auto-dp1 \
    envsubst "$(envsubst_keys)" < "${BODY}" > "${rendered}"

  # The pipeline globals resolved...
  run grep -c '_enable_dp="false"' "${rendered}"
  [ "$output" = "1" ]
  run grep -c '_enable_flogo="true"' "${rendered}"
  [ "$output" = "1" ]
  run grep -c '_dp_name="k8s-auto-dp1"' "${rendered}"
  [ "$output" = "1" ]
  # ...and none left behind.
  run grep -nE '\$\{TP_AUTO_ENABLE_|\$\{TP_AI_ENABLE_' "${rendered}"
  [ "$status" -eq 1 ]
  # ...while the local the verdict is actually computed from is untouched, and so is the case
  # pattern it is matched against: no envsubst has anything to say about either, which is the
  # property the immunity test below pins at the source level.
  run grep -cF 'case "${_enable_dp}" in' "${rendered}"
  [ "$output" = "1" ]
  run grep -cF '[Tt][Rr][Uu][Ee])' "${rendered}"
  [ "$output" = "1" ]

  run bash -n "${rendered}"
  [ "$status" -eq 0 ]
}

# ============================================================================
# (d) Python source — grep only, no interpreter on the BATS runner
# ============================================================================

@test "page_dp.py imports ColorLogger exactly once" {
  # The guard logs through ColorLogger; without the import it dies with a NameError
  # instead of printing the diagnosis it exists to print.
  #
  # \r?$ rather than $ on every end-anchored pattern in this group: the repo sets
  # core.autocrlf=true and ships no .gitattributes, so a Windows working copy has CRLF line
  # endings and a bare $ anchor never matches. Dropping the anchor instead would weaken the
  # assertion - "exactly once, on its own line" is the point.
  [ -f "${PAGE_DP}" ]
  run grep -cE '^from utils\.color_logger import ColorLogger\r?$' "${PAGE_DP}"
  [ "$output" = "1" ]
}

@test "page_dp.py calls the capability guard exactly once, before the browser launches" {
  [ -f "${PAGE_DP}" ]
  run grep -c 'ENV\.check_capabilities_require_dataplane()' "${PAGE_DP}"
  [ "$output" = "1" ]
  # Ordering, not indentation depth: fail-fast means no browser, no CP login, no
  # half-provisioned run. An exact space count would red on any reformat.
  local guard_line launch_line
  guard_line=$(grep -n 'ENV\.check_capabilities_require_dataplane()' "${PAGE_DP}" | head -1 | cut -d: -f1)
  launch_line=$(grep -n 'Util\.browser_launch()' "${PAGE_DP}" | head -1 | cut -d: -f1)
  [ -n "$guard_line" ]
  [ -n "$launch_line" ]
  [ "$guard_line" -lt "$launch_line" ]
}

@test "page_dp.py epilogue navigation sits inside the create-DP guard" {
  # At 8 spaces the navigation is unguarded and opens a Data Plane that was never
  # created; the relocated call is nested one level deeper.
  [ -f "${PAGE_DP}" ]
  run grep -nE '^ {8}po_dp\.goto_dataplane' "${PAGE_DP}"
  [ "$status" -eq 1 ]
}

@test "page_dp.py still logs out exactly once, unguarded" {
  # logout must NOT move inside the guard: we logged in either way.
  [ -f "${PAGE_DP}" ]
  run grep -cE '^ {8}po_auth\.logout\(\)\r?$' "${PAGE_DP}"
  [ "$output" = "1" ]
}

@test "page_bmdp.py epilogue navigation sits inside the create-BMDP guard" {
  [ -f "${PAGE_BMDP}" ]
  run grep -nE '^ {8}po_dp\.goto_dataplane' "${PAGE_BMDP}"
  [ "$status" -eq 1 ]
}

@test "page_bmdp.py still logs out exactly once, unguarded" {
  [ -f "${PAGE_BMDP}" ]
  run grep -cE '^ {8}po_auth\.logout\(\)\r?$' "${PAGE_BMDP}"
  [ "$output" = "1" ]
}

# ============================================================================
# (e) Derived drift — the recipe is compared to ITSELF, so adding a capability
#     without extending the pre-flight reds the build
# ============================================================================

@test "the capability set derived from the recipe is exactly the expected 8 names" {
  # Self-test for the extraction below: if the export spelling changes, the drift test
  # would silently pass on an empty set instead of failing. This is every capability the recipe
  # provisions, exemptions included — the exemption is applied by the coverage test, not here.
  local names
  names="$(recipe_capability_enable_names)"
  [ "$(echo $names)" = "AS BW5CE BWCE EMS FLOGO INFRA_MCP_SERVER SB TIBCOHUB" ]
  [ "$(recipe_capability_enable_names | wc -l | tr -d ' ')" = "8" ]
}

@test "the pre-flight exemption set is exactly 1 capability: INFRA_MCP_SERVER" {
  # Widening the exemption set is how the F3 regression would come back quietly, so the set is
  # pinned by value. Adding a second entry has to be a deliberate edit to BOTH the helper and
  # this assertion, with a reviewer looking at the reason.
  [ "${#PREFLIGHT_EXEMPT_CAPABILITIES[@]}" -eq 1 ]
  [ "${PREFLIGHT_EXEMPT_CAPABILITIES[0]}" = "INFRA_MCP_SERVER" ]
}

@test "every capability the recipe provisions via page_dp.py is covered by the pre-flight (7 of 8)" {
  [ -s "${BODY}" ]
  local name covered=0
  for name in $(recipe_capability_enable_names); do
    if is_preflight_exempt "${name}"; then
      # The exemption has to be real, not just declared: the body must NOT mention the flag,
      # otherwise a stale collect_enabled_capability call would still abort a legitimate run.
      run grep -n "TP_AUTO_ENABLE_${name}" "${BODY}"
      [ "$status" -eq 1 ] || {
        echo "capability TP_AUTO_ENABLE_${name} is exempt but ${GUARD_TASK} still checks it"
        return 1
      }
      continue
    fi
    run grep -c "TP_AUTO_ENABLE_${name}" "${BODY}"
    [ "$status" -eq 0 ] || {
      echo "capability TP_AUTO_ENABLE_${name} is provisioned by a task but not checked by ${GUARD_TASK}"
      return 1
    }
    covered=$((covered + 1))
  done
  # Stated explicitly so a shrinking derived set cannot pass on a near-empty loop.
  [ "$covered" -eq 7 ]
}

@test "the pre-flight never mentions TP_AI_ENABLE_MCP_HUB" {
  # MCP Hub is invisible to the derived set above (never exported as TP_AUTO_IS_PROVISION_*), so
  # it needs its own source-level pin. deploy-mcp-hub runs case.k8s_deploy_mcp_hub against an
  # already registered Data Plane and must keep working on a TP_AUTO_ENABLE_DP=false run.
  [ -s "${BODY}" ]
  run grep -n 'MCP_HUB' "${BODY}"
  [ "$status" -eq 1 ]
}

# ============================================================================
# (f) The headless installer's capability defaults follow GUI_TP_AUTO_ENABLE_DP,
#     so that flag has to be canonicalised before anything derives from it
# ============================================================================
#
# tp-install-on-prem.sh defaults GUI_TP_AUTO_ENABLE_FLOGO and GUI_TP_AUTO_ENABLE_BWCE to
# GUI_TP_AUTO_ENABLE_DP, and yq writes all three into .meta.guiEnv VERBATIM - casing included.
# The recipe turns each of them into a task condition, and the runner compares conditions with
# exact string equality (_funcs_pipeline.sh:99), so an unnormalised GUI_TP_AUTO_ENABLE_DP=True
# would deschedule create-dp AND deploy-flogo AND deploy-bwce: a green pipeline that created
# nothing, which is the very class of silent no-op PCP-22771 exists to remove. Nor would the
# pre-flight above catch it - it is deliberately lowercase tolerant on the Data Plane side, so
# 'True' takes its "nothing to validate" early exit.
#
# The statements are EXTRACTED from the installer rather than re-typed, for the same reason the
# pre-flight body is: a hand-written mirror can drift away from the script it claims to mirror.

installer_stmt() { # $1: a literal fragment of the wanted statement
  grep -hF -- "$1" "${INSTALLER}" | head -1 | tr -d '\r' \
    | sed 's/^[[:space:]]*//; s/[[:space:]]*$//; s/^local //'
}

# The value validation is a multi-line `case`, so it cannot be pulled out a line at a time like
# the assignments above. Extracted from its opening line through its own `esac`, so the rows
# below exercise the installer's real accept/reject rule and not a re-typed copy of it.
installer_dp_validation() {
  awk '
    /^[[:space:]]*case "\$\{GUI_TP_AUTO_ENABLE_DP\}" in[[:space:]]*$/ { _in = 1 }
    _in { print }
    _in && /^[[:space:]]*esac[[:space:]]*$/ { exit }
  ' "${INSTALLER}" | tr -d '\r'
}

# Replay the installer's flag derivation for one set of caller-supplied GUI_* values and echo
# the three values the recipe ends up with: "<DP> <FLOGO> <BWCE>". A value the installer refuses
# returns non-zero with the installer's own error message on stdout, exactly as the script does.
derive_flags() {
  local _dp_norm _dp_validate _bwce_capture _bwce_cp _flogo _bwce_dp _kv
  _dp_norm="$(installer_stmt 'GUI_TP_AUTO_ENABLE_DP=$(printf')"
  _dp_validate="$(installer_dp_validation)"
  _bwce_capture="$(installer_stmt '_gui_tp_auto_enable_bwce_requested="${GUI_TP_AUTO_ENABLE_BWCE:-}"')"
  _bwce_cp="$(installer_stmt 'export GUI_TP_AUTO_ENABLE_BWCE=${GUI_TP_AUTO_ENABLE_BWCE:-"true"}')"
  _flogo="$(installer_stmt 'export GUI_TP_AUTO_ENABLE_FLOGO=${GUI_TP_AUTO_ENABLE_FLOGO:-')"
  _bwce_dp="$(installer_stmt 'export GUI_TP_AUTO_ENABLE_BWCE=${_gui_tp_auto_enable_bwce_requested:-')"
  # Self-test: an extraction that came back empty would make every row below pass vacuously.
  if [ -z "$_dp_norm" ] || [ -z "$_dp_validate" ] || [ -z "$_bwce_capture" ] || [ -z "$_bwce_cp" ] || [ -z "$_flogo" ] || [ -z "$_bwce_dp" ]; then
    echo "could not extract the derivation statements from ${INSTALLER}"
    return 2
  fi
  # ...and that the validation really is the whole construct, not a truncated head of it: a block
  # missing its `*)` arm would accept everything and every rejection row below would red for the
  # wrong reason.
  case "$_dp_validate" in
    *esac) ;;
    *) echo "extracted DP validation is not a complete case block"; return 2 ;;
  esac
  (
    unset GUI_TP_AUTO_ENABLE_DP GUI_TP_AUTO_ENABLE_FLOGO GUI_TP_AUTO_ENABLE_BWCE
    for _kv in "$@"; do export "${_kv}"; done
    eval "$_dp_norm"
    eval "$_dp_validate"    # exits 1 on a value that is neither true nor false
    export GUI_TP_AUTO_ENABLE_DP
    eval "$_bwce_capture"   # customize-tp, before the CP default below overwrites the variable
    eval "$_bwce_cp"        # 02-tp-cp-on-prem.yaml, the CP side (unconditional "true")
    eval "$_flogo"          # 05-tp-auto-deploy-dp.yaml, the DP side
    eval "$_bwce_dp"
    echo "${GUI_TP_AUTO_ENABLE_DP} ${GUI_TP_AUTO_ENABLE_FLOGO} ${GUI_TP_AUTO_ENABLE_BWCE}"
  )
}

@test "installer: unset DP defaults everything on, exactly as before the capability flags were derived" {
  [ -f "${INSTALLER}" ]
  run derive_flags
  [ "$status" -eq 0 ]
  [ "$output" = "true true true" ]
}

@test "installer: DP=true is unchanged - true/true/true, all three tasks scheduled" {
  run derive_flags GUI_TP_AUTO_ENABLE_DP=true
  [ "$output" = "true true true" ]
}

@test "installer: DP='True' derives exactly 'true', so create-dp/deploy-flogo/deploy-bwce all schedule" {
  # THE regression pin. Unnormalised, this produced FLOGO='True' and BWCE='True', the runner
  # skipped all three tasks on its exact-match rule, and the run went green having done nothing.
  run derive_flags GUI_TP_AUTO_ENABLE_DP=True
  [ "$output" = "true true true" ]
}

@test "installer: DP='TRUE' derives exactly 'true' too" {
  run derive_flags GUI_TP_AUTO_ENABLE_DP=TRUE
  [ "$output" = "true true true" ]
}

@test "installer: DP=false derives exactly 'false' - the CP-only install PCP-22771 is about" {
  run derive_flags GUI_TP_AUTO_ENABLE_DP=false
  [ "$output" = "false false false" ]
}

@test "installer: DP='False' derives exactly 'false', not 'False'" {
  # Normalising must not be one-sided: a falsy casing that leaked through as 'False' would be
  # compared against "true" and skip anyway, but the recipe would then report a value the user
  # cannot match against anything in the docs.
  run derive_flags GUI_TP_AUTO_ENABLE_DP=False
  [ "$output" = "false false false" ]
}

# --- the value is VALIDATED, not just case folded ---------------------------------------------
#
# Folding case alone stopped being enough the moment three flags started deriving from this one.
# GUI_TP_AUTO_ENABLE_DP=yes folds to 'yes', which is exactly equal to neither task condition, so
# create-dp AND deploy-flogo AND deploy-bwce are all descheduled; the pre-flight then finds no
# capability that is exactly "true" and exits 0, and the pipeline goes GREEN having provisioned
# nothing. Before the capability flags were derived, the same typo left deploy-flogo scheduled and
# it failed loudly - so without this validation the derivation WIDENS the silent no-op class this
# ticket exists to remove.

@test "installer: DP='yes' is REFUSED, not turned into a green run that provisions nothing" {
  run derive_flags GUI_TP_AUTO_ENABLE_DP=yes
  [ "$status" -eq 1 ]
  [[ "$output" == *"GUI_TP_AUTO_ENABLE_DP"* ]]
  [[ "$output" == *"'yes'"* ]]
  # The message has to say what IS accepted, or the user is left guessing.
  [[ "$output" == *"true"* ]]
  [[ "$output" == *"false"* ]]
}

@test "installer: DP='1' is REFUSED" {
  run derive_flags GUI_TP_AUTO_ENABLE_DP=1
  [ "$status" -eq 1 ]
  [[ "$output" == *"'1'"* ]]
}

@test "installer: DP='on' is REFUSED" {
  run derive_flags GUI_TP_AUTO_ENABLE_DP=on
  [ "$status" -eq 1 ]
  [[ "$output" == *"'on'"* ]]
}

@test "installer: a trailing CR from a CRLF env file is STRIPPED, not refused" {
  # The Windows/Git-Bash path this script documents reads env files that may be CRLF, and the
  # script already strips CR elsewhere (`base64 ... | tr -d '\n\r'`). 'true\r' is a line-ending
  # artefact, not a typo, so the right answer is to normalise it - refusing would fail a
  # correctly-configured install.
  run derive_flags "GUI_TP_AUTO_ENABLE_DP=$(printf 'true\r')"
  [ "$status" -eq 0 ]
  [ "$output" = "true true true" ]
  run derive_flags "GUI_TP_AUTO_ENABLE_DP=$(printf 'False\r')"
  [ "$status" -eq 0 ]
  [ "$output" = "false false false" ]
}

@test "installer: surrounding whitespace is STRIPPED, whitespace-only is REFUSED" {
  run derive_flags "GUI_TP_AUTO_ENABLE_DP=  true  "
  [ "$status" -eq 0 ]
  [ "$output" = "true true true" ]
  # ...but a value that is nothing but whitespace is not the empty string: `:-` never fired, so
  # the caller did set something, and what they set is not a boolean.
  run derive_flags "GUI_TP_AUTO_ENABLE_DP=   "
  [ "$status" -eq 1 ]
}

@test "installer: an EMPTY DP value takes the documented default, it is not a typo" {
  # Deliberately not in the refusal list above. ${VAR:-true} has already turned an empty value
  # into the documented default before the validation sees it, exactly as it does for every other
  # GUI_* flag in this script, and the result is the full default install - true/true/true - not a
  # run that provisions nothing. Refusing here would break `export GUI_TP_AUTO_ENABLE_DP=` and
  # would make this one flag behave unlike all its neighbours.
  run derive_flags GUI_TP_AUTO_ENABLE_DP=
  [ "$status" -eq 0 ]
  [ "$output" = "true true true" ]
}

@test "installer: an explicitly set capability still wins over the DP default" {
  # The derivation is a DEFAULT, not an override: asking for Flogo on a DP=false run must still
  # reach the pre-flight above and be refused there, with the reason named.
  run derive_flags GUI_TP_AUTO_ENABLE_DP=false GUI_TP_AUTO_ENABLE_FLOGO=true
  [ "$output" = "false true false" ]
  run derive_flags GUI_TP_AUTO_ENABLE_DP=false GUI_TP_AUTO_ENABLE_BWCE=true
  [ "$output" = "false false true" ]
  # ...and opting a capability out of an otherwise enabled run works in the other direction.
  run derive_flags GUI_TP_AUTO_ENABLE_DP=True GUI_TP_AUTO_ENABLE_FLOGO=false
  [ "$output" = "true false true" ]
}

@test "installer: the DP flag is normalised BEFORE the capability defaults read it" {
  # Ordering, not text: normalising after the derivations would leave the derived flags with the
  # original casing and reintroduce the skip-everything run.
  [ -f "${INSTALLER}" ]
  local norm_line flogo_line bwce_line
  norm_line=$(grep -nF 'GUI_TP_AUTO_ENABLE_DP=$(printf' "${INSTALLER}" | head -1 | cut -d: -f1)
  flogo_line=$(grep -nF 'export GUI_TP_AUTO_ENABLE_FLOGO=${GUI_TP_AUTO_ENABLE_FLOGO:-' "${INSTALLER}" | head -1 | cut -d: -f1)
  bwce_line=$(grep -nF 'export GUI_TP_AUTO_ENABLE_BWCE=${_gui_tp_auto_enable_bwce_requested:-' "${INSTALLER}" | head -1 | cut -d: -f1)
  [ -n "$norm_line" ]
  [ -n "$flogo_line" ]
  [ -n "$bwce_line" ]
  [ "$norm_line" -lt "$flogo_line" ]
  [ "$norm_line" -lt "$bwce_line" ]
}

@test "installer: the DP flag is lowercased with tr, not a bash 4 case-folding expansion" {
  # tp-install-on-prem.sh runs on developer machines including macOS, whose /bin/bash is 3.2:
  # a case-folding parameter expansion is a PARSE error there, so it would not fail this one
  # flag, it would fail the whole script before its first line executes. The script uses no
  # other bash 4 syntax, so this stays true by keeping the construct out entirely - comments
  # included, since a comment that spells it out is the obvious thing to copy.
  [ -f "${INSTALLER}" ]
  run grep -cF "tr '[:upper:]' '[:lower:]'" "${INSTALLER}"
  [ "$output" = "1" ]
  run grep -nF ',,}' "${INSTALLER}"
  [ "$status" -eq 1 ]
}
