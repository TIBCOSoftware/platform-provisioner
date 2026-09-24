#!/usr/bin/env bats
#
# Regression tests for the DB engine selector shared by the on-prem base recipes
# (tp-base-on-prem.yaml, tp-base-on-prem-https.yaml) and the Control Plane recipe
# (pp-deploy-cp-core-on-prem.yaml).
#
# The engine is picked in the GUI as a string (postgres | oracle) and everything else is
# DERIVED from it inside .meta.globalEnvVariable: TP_INSTALL_ORACLE becomes the literal
# "true"/"false" a helmCharts condition can be compared against, and the CP DB host / port
# / user name / name switch to the in-cluster Oracle service. Those derivations are plain
# `$(if ...)` command substitutions evaluated in DECLARATION ORDER, so a key that reads
# ${CP_DB_ENGINE} before CP_DB_ENGINE is declared silently resolves to the empty string:
# no error, no failed task, just a Control Plane quietly wired to the wrong database.
# Group (b) is the guard for exactly that.
#
# Coverage is deliberately interpreter-free: the BATS job has bats-core + yq (and gettext)
# but no helm and no python, so the recipes are asserted against their SOURCE files rather
# than a helm-rendered artifact. The rendered ConfigMap is covered separately by
# charts/provisioner-config-local/tests/config_test.yaml.
#

bats_require_minimum_version 1.5.0

export PROJECT_ROOT="$(cd "$(dirname "${BATS_TEST_DIRNAME}")/../.." && pwd)"
RECIPES="${PROJECT_ROOT}/charts/provisioner-config-local/recipes"
CP_RECIPE="${RECIPES}/pp-deploy-cp-core-on-prem.yaml"
BASE_RECIPE="${RECIPES}/tp-base-on-prem.yaml"
BASE_HTTPS_RECIPE="${RECIPES}/tp-base-on-prem-https.yaml"
GUARD_TASK="validate-db-engine"

guard_body() {
  yq e '.preTasks[0].script.content' "$1"
}

guard_field() {
  yq e ".preTasks[0].${2}" "$1"
}

# Position of a key inside .meta.globalEnvVariable, in declaration order. Empty when the
# key is absent, which every caller asserts against before comparing.
env_index() {
  KEY="$2" yq e '.meta.globalEnvVariable | keys | to_entries | .[] | select(.value == strenv(KEY)) | .key' "$1"
}

# Mirror of common::replace_env_variables (charts/common-dependency/scripts/_functions.sh):
# envsubst is SCOPED to the keys declared under .meta.globalEnvVariable.
envsubst_keys() {
  yq e '.meta.globalEnvVariable | keys | .[] | " $" + .' "$1" | tr '\n' ' '
}

# Run an extracted guard body. Both variables are pre-seeded empty so an ambient CP_DB_*
# in the developer's shell cannot decide the verdict; `env` applies assignments left to
# right, so "$@" overrides.
run_cp_guard() {
  env CP_DB_ENGINE= CP_MANAGE_DB_SCHEMA= "$@" bash "${CP_BODY}"
}

run_base_guard() {
  env TP_DB_ENGINE= "$@" bash "${BASE_BODY}"
}

run_https_guard() {
  env TP_DB_ENGINE= "$@" bash "${BASE_HTTPS_BODY}"
}

setup() {
  CP_BODY="${BATS_TEST_TMPDIR}/cp-guard.sh"
  BASE_BODY="${BATS_TEST_TMPDIR}/base-guard.sh"
  BASE_HTTPS_BODY="${BATS_TEST_TMPDIR}/base-https-guard.sh"
  guard_body "${CP_RECIPE}" > "${CP_BODY}"
  guard_body "${BASE_RECIPE}" > "${BASE_BODY}"
  guard_body "${BASE_HTTPS_RECIPE}" > "${BASE_HTTPS_BODY}"
}

# ============================================================================
# (a) Source-recipe structure — asserted against the source YAML, not a render
# ============================================================================

@test "all three edited recipes are parseable YAML" {
  # One `run` per file: a recipe broken by the engine edit must red on its own line
  # rather than hide behind whichever file yq happened to reach first.
  run yq e '.' "${CP_RECIPE}"
  [ "$status" -eq 0 ]
  run yq e '.' "${BASE_RECIPE}"
  [ "$status" -eq 0 ]
  run yq e '.' "${BASE_HTTPS_RECIPE}"
  [ "$status" -eq 0 ]
}

@test "the engine guard is the FIRST preTask of all three recipes" {
  # First, so it refuses a bad engine before any task touches the cluster.
  run guard_field "${CP_RECIPE}" name
  [ "$output" = "${GUARD_TASK}" ]
  run guard_field "${BASE_RECIPE}" name
  [ "$output" = "${GUARD_TASK}" ]
  run guard_field "${BASE_HTTPS_RECIPE}" name
  [ "$output" = "${GUARD_TASK}" ]
}

@test "the engine guard fails the run: ignoreErrors is false everywhere" {
  # ignoreErrors: true turns the whole task into an expensive echo.
  run guard_field "${CP_RECIPE}" script.ignoreErrors
  [ "$output" = "false" ]
  run guard_field "${BASE_RECIPE}" script.ignoreErrors
  [ "$output" = "false" ]
  run guard_field "${BASE_HTTPS_RECIPE}" script.ignoreErrors
  [ "$output" = "false" ]
}

@test "the engine guard is unconditional" {
  # A condition on a validation task is a way to skip validation.
  run guard_field "${CP_RECIPE}" condition
  [ "$output" = "null" ]
  run guard_field "${BASE_RECIPE}" condition
  [ "$output" = "null" ]
  run guard_field "${BASE_HTTPS_RECIPE}" condition
  [ "$output" = "null" ]
}

@test "the engine guard pins fileName: script.sh so the runner cannot execute a different file" {
  # run_task resolves what it EXECUTES from .fileName, else ${PIPELINE_RUNNER_SCRIPT_NAME_SH},
  # else script.sh. Leave it unset with that global pointing elsewhere and the guard silently
  # vanishes — fail-open is the worst outcome for a task whose only job is to fail the run.
  run guard_field "${CP_RECIPE}" script.fileName
  [ "$output" = "script.sh" ]
  run guard_field "${BASE_RECIPE}" script.fileName
  [ "$output" = "script.sh" ]
  run guard_field "${BASE_HTTPS_RECIPE}" script.fileName
  [ "$output" = "script.sh" ]
}

@test "every guard body is valid bash and fails the task on an unknown engine" {
  [ -s "${CP_BODY}" ]
  run bash -n "${CP_BODY}"
  [ "$status" -eq 0 ]
  # Only the unknown-engine arm is fatal, in every guard body.
  run grep -c 'exit 1' "${CP_BODY}"
  [ "$output" = "1" ]

  [ -s "${BASE_BODY}" ]
  run bash -n "${BASE_BODY}"
  [ "$status" -eq 0 ]
  run grep -c 'exit 1' "${BASE_BODY}"
  [ "$output" = "1" ]

  [ -s "${BASE_HTTPS_BODY}" ]
  run bash -n "${BASE_HTTPS_BODY}"
  [ "$status" -eq 0 ]
  run grep -c 'exit 1' "${BASE_HTTPS_BODY}"
  [ "$output" = "1" ]
}

@test "no guard body uses a construct envsubst cannot render" {
  # envsubst has no :- default support; ${VAR:-x} renders as the empty string, which here
  # would turn a valid engine into the unknown-engine arm. grep exits 2 on a missing file
  # (which also satisfies "-ne 0"), so require a non-empty body and grep to exit exactly 1.
  [ -s "${CP_BODY}" ]
  run grep -nE '\$\{[A-Za-z_][A-Za-z0-9_]*:-' "${CP_BODY}"
  [ "$status" -eq 1 ]
  [ -s "${BASE_BODY}" ]
  run grep -nE '\$\{[A-Za-z_][A-Za-z0-9_]*:-' "${BASE_BODY}"
  [ "$status" -eq 1 ]
  [ -s "${BASE_HTTPS_BODY}" ]
  run grep -nE '\$\{[A-Za-z_][A-Za-z0-9_]*:-' "${BASE_HTTPS_BODY}"
  [ "$status" -eq 1 ]
}

# ============================================================================
# (b) Declaration ORDER inside .meta.globalEnvVariable — the silent-breakage
#     guard. The derived keys are `$(if ...)` substitutions that read an
#     EARLIER key; move the engine below a consumer and the consumer sees "".
# ============================================================================

@test "base recipe: TP_DB_ENGINE is declared before the TP_INSTALL_ORACLE it derives" {
  local engine oracle
  engine="$(env_index "${BASE_RECIPE}" TP_DB_ENGINE)"
  oracle="$(env_index "${BASE_RECIPE}" TP_INSTALL_ORACLE)"
  # One assertion per name: a renamed key must red here, not later as an "integer
  # expression expected" from a -lt on an empty string.
  [ -n "$engine" ]
  [ -n "$oracle" ]
  [ "$engine" -lt "$oracle" ]
}

@test "base cert recipe: TP_DB_ENGINE is declared before the TP_INSTALL_ORACLE it derives" {
  local engine oracle
  engine="$(env_index "${BASE_HTTPS_RECIPE}" TP_DB_ENGINE)"
  oracle="$(env_index "${BASE_HTTPS_RECIPE}" TP_INSTALL_ORACLE)"
  [ -n "$engine" ]
  [ -n "$oracle" ]
  [ "$engine" -lt "$oracle" ]
}

@test "CP recipe: CP_DB_ENGINE is declared before every CP_DB_* value derived from it" {
  local engine host port user name driver
  engine="$(env_index "${CP_RECIPE}" CP_DB_ENGINE)"
  host="$(env_index "${CP_RECIPE}" CP_DB_HOST)"
  port="$(env_index "${CP_RECIPE}" CP_DB_PORT)"
  user="$(env_index "${CP_RECIPE}" CP_DB_USER_NAME)"
  name="$(env_index "${CP_RECIPE}" CP_DB_NAME)"
  # CP_DB_DRIVER defaults to CP_DB_ENGINE, so declaring it first would default it to
  # nothing and ship an empty driver. This list is by name, so a new CP_DB_* derived
  # from the engine must be ADDED here or it lands untested.
  driver="$(env_index "${CP_RECIPE}" CP_DB_DRIVER)"
  [ -n "$engine" ]
  [ -n "$host" ]
  [ -n "$port" ]
  [ -n "$user" ]
  [ -n "$name" ]
  [ -n "$driver" ]
  [ "$engine" -lt "$host" ]
  [ "$engine" -lt "$port" ]
  [ "$engine" -lt "$user" ]
  [ "$engine" -lt "$name" ]
  [ "$engine" -lt "$driver" ]
}

@test "CP recipe: the Keycloak DB keys are declared after the CP DB keys they fall back to" {
  # Keycloak always talks to the shared PostgreSQL pod, so on the postgres arm
  # CP_KEYCLOAK_DB_HOST/PORT echo CP_DB_HOST/CP_DB_PORT. Declared first, they would
  # echo nothing and Keycloak would get "jdbc:postgresql://:/keycloak".
  local engine host port kc_host kc_port kc_password
  engine="$(env_index "${CP_RECIPE}" CP_DB_ENGINE)"
  host="$(env_index "${CP_RECIPE}" CP_DB_HOST)"
  port="$(env_index "${CP_RECIPE}" CP_DB_PORT)"
  kc_host="$(env_index "${CP_RECIPE}" CP_KEYCLOAK_DB_HOST)"
  kc_port="$(env_index "${CP_RECIPE}" CP_KEYCLOAK_DB_PORT)"
  kc_password="$(env_index "${CP_RECIPE}" CP_KEYCLOAK_DB_PASSWORD)"
  [ -n "$engine" ]
  [ -n "$host" ]
  [ -n "$port" ]
  [ -n "$kc_host" ]
  [ -n "$kc_port" ]
  [ -n "$kc_password" ]
  [ "$engine" -lt "$kc_host" ]
  [ "$engine" -lt "$kc_port" ]
  [ "$engine" -lt "$kc_password" ]
  [ "$host" -lt "$kc_host" ]
  [ "$port" -lt "$kc_port" ]
  [ "$host" -lt "$kc_password" ]
}

# ============================================================================
# (c) Behavioural — the CP verdict, driven by the real preTask body
# ============================================================================

@test "CP guard: postgres passes silently" {
  run run_cp_guard CP_DB_ENGINE=postgres CP_MANAGE_DB_SCHEMA=true
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "CP guard: oracle with schema management on proceeds, naming the chart requirement" {
  # Oracle schema management became possible once core-cp-scripts gained an Oracle client
  # and the schema Job started emitting ORACLE_HOST/ORACLE_PORT. The guard now informs
  # rather than refuses; only an unrecognised engine is fatal.
  run run_cp_guard CP_DB_ENGINE=oracle CP_MANAGE_DB_SCHEMA=true
  [ "$status" -eq 0 ]
  [[ "$output" == *"WARNING"* ]]
  [[ "$output" == *"CP Manage DB Schema is on"* ]]
}

@test "CP guard: oracle with schema management off proceeds, with a warning" {
  run run_cp_guard CP_DB_ENGINE=oracle CP_MANAGE_DB_SCHEMA=false
  [ "$status" -eq 0 ]
  [[ "$output" == *"WARNING"* ]]
  [[ "$output" != *"CP Manage DB Schema is on"* ]]
}

@test "CP guard: 'Oracle' is REFUSED, the arm is matched exactly and casing is not folded" {
  # The chart globals and the derived CP_DB_* substitutions both compare against the exact
  # lowercase string, so a capitalised value would deploy postgres wiring under an Oracle
  # engine selection. Refusing is the only safe answer.
  run run_cp_guard CP_DB_ENGINE=Oracle CP_MANAGE_DB_SCHEMA=false
  [ "$status" -eq 1 ]
  [[ "$output" == *"ERROR"* ]]
  [[ "$output" == *"Oracle"* ]]
}

@test "CP guard: 'postgresql' is REFUSED, the engine name is postgres" {
  run run_cp_guard CP_DB_ENGINE=postgresql CP_MANAGE_DB_SCHEMA=false
  [ "$status" -eq 1 ]
  [[ "$output" == *"ERROR"* ]]
}

@test "CP guard: an empty engine is refused by the guard body itself" {
  # NOTE: unreachable through the recipe -- CP_DB_ENGINE: ${GUI_CP_DB_ENGINE:-"postgres"}
  # turns an empty GUI value into postgres before the guard runs. This pins the guard body
  # in isolation, so the guard stays safe if that upstream default is ever removed.
  run run_cp_guard CP_MANAGE_DB_SCHEMA=false
  [ "$status" -eq 1 ]
  [[ "$output" == *"ERROR"* ]]
}

# ============================================================================
# (d) Behavioural — the on-prem base verdict
# ============================================================================

@test "base guard: postgres passes and echoes the engine" {
  run run_base_guard TP_DB_ENGINE=postgres
  [ "$status" -eq 0 ]
  [[ "$output" == *"postgres"* ]]
}

@test "base guard: oracle passes and echoes the engine" {
  run run_base_guard TP_DB_ENGINE=oracle
  [ "$status" -eq 0 ]
  [[ "$output" == *"oracle"* ]]
}

@test "base guard: an unknown engine is REFUSED" {
  run run_base_guard TP_DB_ENGINE=mysql
  [ "$status" -eq 1 ]
  [[ "$output" == *"ERROR"* ]]
  [[ "$output" == *"mysql"* ]]
}

@test "base guard: an empty engine is refused by the guard body itself" {
  # NOTE: unreachable through the recipe -- TP_DB_ENGINE: ${GUI_TP_DB_ENGINE:-"postgres"}
  # defaults an empty GUI value to postgres upstream. Pins the guard body in isolation.
  run run_base_guard
  [ "$status" -eq 1 ]
  [[ "$output" == *"ERROR"* ]]
}

@test "base cert guard: same verdicts as the http base recipe" {
  # The two base recipes are maintained side by side; the cert one drifting is the
  # failure mode this row exists for.
  run run_https_guard TP_DB_ENGINE=postgres
  [ "$status" -eq 0 ]
  run run_https_guard TP_DB_ENGINE=oracle
  [ "$status" -eq 0 ]
  run run_https_guard TP_DB_ENGINE=mysql
  [ "$status" -eq 1 ]
  [[ "$output" == *"ERROR"* ]]
}

# ============================================================================
# (e) Real envsubst round-trip — what the pipeline actually executes. The body
#     reaches bash with the engine already substituted in as a literal.
# ============================================================================

@test "envsubst round-trip: the rendered CP guard still reaches the right arm" {
  if ! command -v envsubst >/dev/null 2>&1; then
    skip "envsubst (gettext) not available"
  fi
  [ -s "${CP_BODY}" ]
  local rendered="${BATS_TEST_TMPDIR}/cp-guard.rendered.sh"

  # schema management OFF: the substituted body must reach the oracle arm and continue
  CP_DB_ENGINE=oracle CP_MANAGE_DB_SCHEMA=false \
    envsubst "$(envsubst_keys "${CP_RECIPE}")" < "${CP_BODY}" > "${rendered}"
  run grep -nE '\$\{CP_DB_ENGINE\}|\$\{CP_MANAGE_DB_SCHEMA\}' "${rendered}"
  [ "$status" -eq 1 ]
  run bash "${rendered}"
  [ "$status" -eq 0 ]
  [[ "$output" == *"WARNING"* ]]

  # schema management ON: proceeds, and still names the requirement
  CP_DB_ENGINE=oracle CP_MANAGE_DB_SCHEMA=true \
    envsubst "$(envsubst_keys "${CP_RECIPE}")" < "${CP_BODY}" > "${rendered}"
  run bash "${rendered}"
  [ "$status" -eq 0 ]
  [[ "$output" == *"CP Manage DB Schema is on"* ]]

  CP_DB_ENGINE=mysql CP_MANAGE_DB_SCHEMA=false \
    envsubst "$(envsubst_keys "${CP_RECIPE}")" < "${CP_BODY}" > "${rendered}"
  run bash "${rendered}"
  [ "$status" -eq 1 ]
  [[ "$output" == *"mysql"* ]]
}

@test "envsubst round-trip: the rendered base guard still reaches the right arm" {
  if ! command -v envsubst >/dev/null 2>&1; then
    skip "envsubst (gettext) not available"
  fi
  [ -s "${BASE_BODY}" ]
  local rendered="${BATS_TEST_TMPDIR}/base-guard.rendered.sh"

  TP_DB_ENGINE=oracle envsubst "$(envsubst_keys "${BASE_RECIPE}")" < "${BASE_BODY}" > "${rendered}"
  run grep -nE '\$\{TP_DB_ENGINE\}' "${rendered}"
  [ "$status" -eq 1 ]
  run bash "${rendered}"
  [ "$status" -eq 0 ]
  [[ "$output" == *"oracle"* ]]

  TP_DB_ENGINE=mysql envsubst "$(envsubst_keys "${BASE_RECIPE}")" < "${BASE_BODY}" > "${rendered}"
  run bash "${rendered}"
  [ "$status" -eq 1 ]
  [[ "$output" == *"ERROR"* ]]
}
