#!/usr/bin/env bats
#
# PCP-23809: on-prem "deploy from scratch" must apply the CoreDNS rewrite BEFORE the CP
# helm phase, not after it.
#
# *.localhost.dataplanes.pro is a public wildcard A record pointing at 127.0.0.1. Until
# 03-tp-adjust-dns.yaml rewrites it to the in-cluster ingress service, a CP pod that talks
# to its own CP_DOMAIN at startup dials itself and gets "connection refused".
# tp-cp-infra's infra-alerts-services does exactly that (fetching the OIDC well-known
# config, fail-fast) from image 327 onwards, so it crash-loops and
# `helm upgrade --install platform-base --wait --timeout 1h` blocks for the full hour and
# then fails the pipeline. Measured on run generic-runner-gcp-98372901679-1787636461480:
# the DNS step ran at 06:22:00, two seconds AFTER the CP phase it was supposed to unblock,
# and the install only completed because the ConfigMap was created by hand at ~06:15.
#
# These tests EXECUTE run.sh choice 1 with the pipeline runner stubbed out and record the
# order in which recipes are handed to it, rather than pattern-matching the source. Asserting
# on the text would not catch a reordering done by moving the call into a helper, and could
# not check the abort-on-failure behaviour at all.
#

bats_require_minimum_version 1.5.0

export PROJECT_ROOT="$(cd "$(dirname "${BATS_TEST_DIRNAME}")/../.." && pwd)"
RUN_SH="${PROJECT_ROOT}/docs/recipes/automation/on-prem/run.sh"

# Every recipe run.sh can hand to the pipeline. They are only ever passed through to
# $PIPELINE_SCRIPT as a path, so empty files are enough - and keep the stub honest, since a
# recipe with content might tempt a future test into parsing it instead of recording it.
RECIPES=(
  01-tp-on-prem.yaml
  02-tp-cp-on-prem.yaml
  03-tp-adjust-dns.yaml
  04-tp-adjust-resource.yaml
  05-tp-auto-deploy-dp.yaml
  06-tp-o11y-stack.yaml
  07-tp-bw5-stack.yaml
)

setup() {
  WORK="$(mktemp -d)"
  BIN="${WORK}/bin"
  mkdir -p "${BIN}"

  local recipe
  for recipe in "${RECIPES[@]}"; do
    : > "${WORK}/${recipe}"
  done

  # The recorder that stands in for dev/platform-provisioner.sh. run.sh invokes it as
  # `bash -c "${PIPELINE_SCRIPT}"` with PIPELINE_INPUT_RECIPE exported, so the recipe
  # basename is the whole observable effect of a step.
  #
  # FAIL_ON lets a test make one step fail without touching the others, which is how the
  # abort case below is driven.
  cat > "${BIN}/record.sh" <<'EOS'
#!/bin/bash
name="$(basename "${PIPELINE_INPUT_RECIPE}")"
echo "${name}" >> "${RECORD_FILE}"
if [[ -n "${FAIL_ON:-}" && "${name}" == "${FAIL_ON}" ]]; then
  exit 1
fi
exit 0
EOS
  chmod +x "${BIN}/record.sh"

  # sleep: run.sh waits 30s twice on the happy path and 10s between subscription retries.
  # Stubbing it keeps the suite at well under a second without weakening any assertion -
  # nothing under test depends on wall-clock time.
  cat > "${BIN}/sleep" <<'EOS'
#!/bin/bash
exit 0
EOS
  chmod +x "${BIN}/sleep"

  # yq is only consulted for GUI_TP_AUTO_USE_LOCAL_SCRIPT. "null" is what real yq returns
  # for the empty recipe files above; stubbing it means the suite runs on a machine (or CI
  # image) without yq installed instead of silently skipping.
  cat > "${BIN}/yq" <<'EOS'
#!/bin/bash
echo "null"
EOS
  chmod +x "${BIN}/yq"

  export RECORD_FILE="${WORK}/order.txt"
  : > "${RECORD_FILE}"
  # %q, because run.sh runs this through `bash -c "${PIPELINE_SCRIPT}"` - an unquoted
  # path with a space in it would word-split there and fail as a confusing shell error
  # rather than as a test assertion.
  printf -v PIPELINE_SCRIPT 'bash %q' "${BIN}/record.sh"
  export PIPELINE_SCRIPT
  export PATH="${BIN}:${PATH}"
  # One retry, so a deliberately failing subscription step does not spin three times.
  export TP_SUBSCRIPTION_DEPLOY_RETRY_COUNT=1
  # Pin the BW5 branch off: run.sh reads TP_AUTO_ENABLE_BMDP from the ambient environment,
  # so a shell or CI image that exports "true" would silently run a different path than
  # these tests assert on. Passing for a reason the test does not control is not passing.
  export TP_AUTO_ENABLE_BMDP=false
}

teardown() {
  [ -n "${WORK:-}" ] && rm -rf "${WORK}"
}

# Run `run.sh 1` from the scratch dir - run.sh reads CURRENT_PATH from $(pwd).
deploy_from_scratch() {
  cd "${WORK}" || return 1
  bash "${RUN_SH}" 1
}

# 1-based position of a recipe in the recorded order, or empty if it never ran.
position_of() {
  grep -n -x -F "$1" "${RECORD_FILE}" | head -1 | cut -d: -f1
}

@test "the harness records the steps of a full deploy at all" {
  run deploy_from_scratch
  [ "$status" -eq 0 ]

  # Sanity: if the stub silently recorded nothing, every ordering assertion below would be
  # vacuously true.
  [ -s "${RECORD_FILE}" ]
  [ -n "$(position_of 01-tp-on-prem.yaml)" ]
  [ -n "$(position_of 02-tp-cp-on-prem.yaml)" ]
}

@test "a failing DNS step aborts the deploy instead of running into the CP deadlock" {
  # If the rewrite cannot be applied there is no point starting the CP helm phase: it would
  # block on --wait for an hour and then fail anyway, with the real cause an hour upstream in
  # the log. Fail where the fault is.
  FAIL_ON=03-tp-adjust-dns.yaml run deploy_from_scratch
  [ "$status" -ne 0 ]

  [[ "$output" == *"Failed to adjust DNS"* ]]
  [ -z "$(position_of 02-tp-cp-on-prem.yaml)" ]
}

@test "a full deploy aborts when recipe 03 is absent, unlike option 3" {
  # The mirror of "a standalone CP deploy warns but still deploys when recipe 03 is absent".
  # The two CP-deploying paths treat the same condition differently ON PURPOSE, so pin both:
  # option 1 needs the whole recipe set regardless (it would fail on a missing 01 or 05 too),
  # so an incomplete workspace is an anomaly; option 3 is a-la-carte and may legitimately be
  # reached from a CP-only workspace. Without this test the asymmetry is a side effect of
  # where ensure-dns happens to be called rather than a decision on record.
  cd "${WORK}"
  rm -f "${WORK}/03-tp-adjust-dns.yaml"
  run bash "${RUN_SH}" 1
  [ "$status" -ne 0 ]

  [[ "$output" == *"Failed to adjust DNS"* ]]
  [ -z "$(position_of 02-tp-cp-on-prem.yaml)" ]
}

@test "a full deploy whose subscription step exhausts every retry reports failure" {
  # `run-with-retry` returns 1 once the retries are spent, but nothing consumed that status,
  # and `break` + the closing printf then set the process exit code to 0. Measured before the
  # fix: `FAIL_ON=05-tp-auto-deploy-dp.yaml ./run.sh 1` exited 0 after failing every attempt.
  # This is the primary deploy path the SaaS pipeline drives, and it is the same false-green
  # class this suite already pins for option 9.
  cd "${WORK}"
  FAIL_ON=05-tp-auto-deploy-dp.yaml run bash "${RUN_SH}" 1
  [ "$status" -ne 0 ]

  [[ "$output" == *"Failed to deploy CP subscription"* ]]
}

@test "a standalone CP deploy applies the DNS rewrite first" {
  # Option 3 deploys the CP on its own, so it has the SAME prerequisite option 1 does.
  # `./run.sh 2` then `./run.sh 3` is a documented flow (the install-tp-local skill drives
  # exactly that), and with option 3 going straight to the CP it hit the identical
  # hour-long deadlock this ticket is about - the fix to option 1 alone did not cover it.
  cd "${WORK}"
  run bash "${RUN_SH}" 3
  [ "$status" -eq 0 ]

  local dns cp
  dns="$(position_of 03-tp-adjust-dns.yaml)"
  cp="$(position_of 02-tp-cp-on-prem.yaml)"
  [ -n "$dns" ]
  [ -n "$cp" ]
  [ "$dns" -lt "$cp" ]
}

@test "a standalone CP deploy warns but still deploys when recipe 03 is absent" {
  # generate-recipe.sh option 2 used to emit ONLY 02-tp-cp-on-prem.yaml, and users keep
  # generated workspaces on disk next to their pem files. Requiring 03 unconditionally
  # would turn those existing CP-chart upgrades into a hard stop — a worse regression than
  # the deadlock being guarded against, which at least announces itself in the log.
  # (option 2 now emits 03 too, so this only covers workspaces predating that.)
  cd "${WORK}"
  rm -f "${WORK}/03-tp-adjust-dns.yaml"
  run bash "${RUN_SH}" 3
  [ "$status" -eq 0 ]

  [[ "$output" == *"03-tp-adjust-dns.yaml not found"* ]]
  [ -z "$(position_of 03-tp-adjust-dns.yaml)" ]
  # The CP deploy still happened — warned, not blocked.
  [ -n "$(position_of 02-tp-cp-on-prem.yaml)" ]
}

@test "a standalone CP deploy aborts when the DNS rewrite fails" {
  cd "${WORK}"
  FAIL_ON=03-tp-adjust-dns.yaml run bash "${RUN_SH}" 3
  [ "$status" -ne 0 ]

  [ -z "$(position_of 02-tp-cp-on-prem.yaml)" ]
}

@test "a failed standalone CP deploy reports failure, not success" {
  # The DNS half of option 3 aborting loudly while the CP half exited 0 would be a worse
  # state than before this change - install-tp-local drives `./run.sh 3` for CP chart
  # upgrades and reads the exit code.
  cd "${WORK}"
  FAIL_ON=02-tp-cp-on-prem.yaml run bash "${RUN_SH}" 3
  [ "$status" -ne 0 ]

  [[ "$output" == *"Failed to deploy CP"* ]]
  # The DNS step still ran - this is the CP deploy failing, not the prerequisite.
  [ -n "$(position_of 03-tp-adjust-dns.yaml)" ]
}
