#!/usr/bin/env bats
#
# PCP-24040: every option menu under docs/recipes/automation/on-prem/ must terminate.
#
# All four scripts had the same shape - a `while true` loop around a `read`, with a `*)`
# branch that neither broke nor cleared the choice variable:
#
#   while true; do
#     if [[ -z $choice ]]; then <menu>; read -rp "..." choice; fi
#     case $choice in
#       1) …; break ;;  …
#       *) echo "Invalid option. Please try again." ;;   # no break, choice left set
#     esac
#   done
#
# That produced two distinct non-terminating states, and MEASURING them is what shows why
# a single guard in `*)` closes both:
#
#   A. $choice ends up non-empty and invalid. `[[ -z $choice ]]` is then false forever, so
#      the loop stops re-prompting AND stops reading stdin - it just spins on `*)`. Measured
#      on the pre-fix code: `run.sh 99` printed the menu 0 times and "Invalid option"
#      223,460 times in 4s. NOTE this needs no pipe and no CI: a human at a terminal who
#      mistypes once lands here too, because stdin is never read again. "Please try again"
#      was never true.
#   B. $choice stays empty because `read` failed - stdin closed or not a TTY (bats, CI,
#      cron, `< /dev/null`). Every pass re-prints the whole menu: 25,245 menus in 4s.
#
# Both states arrive at `*)`, so leaving the loop there fixes both. A bats process left in
# state B on a workstation held 24.97 GB of commit charge after 7 days and pushed the machine
# to 98.4% of its commit limit, at which point unrelated tooling began failing.
#
# The siblings matter as much as run.sh: tp-install-on-prem.sh:451-452 defaults
# TP_K8S_CLUSTER_TYPE_CODE to the empty string and expands it unquoted, so a headless install
# calls `./adjust-recipe.sh` with ZERO arguments - state B, non-interactively, by default.
#
# Every case runs the script under `timeout`, so a regression fails the suite instead of
# hanging it again - the whole point is that this class of bug must not be able to consume
# the machine a second time. Output goes to a FILE, never a shell variable: capturing into
# memory is exactly what turned this bug into a 25 GB leak, so the harness must not reproduce
# the thing it guards against. It also makes the output size assertable.
#
# NOT covered: a real TTY, which bats cannot provide without a pty. State A's terminal form
# (a human mistyping) is therefore only covered by its pipe equivalent below; state A does not
# depend on stdin's type, since stdin is never read in it.
#

bats_require_minimum_version 1.5.0

export PROJECT_ROOT="$(cd "$(dirname "${BATS_TEST_DIRNAME}")/../.." && pwd)"
ONPREM_DIR="${PROJECT_ROOT}/docs/recipes/automation/on-prem"
RUN_SH="${ONPREM_DIR}/run.sh"

# Deliberately far above what these paths need (they do no real work) because the cost of the
# two directions is wildly asymmetric: too high only makes an actual regression take longer to
# report, while too low turns a loaded CI box or a Windows Git-Bash agent - where a single bash
# spawn can take a second - into a flaky red.
TIMEOUT_SECS=20
# A terminating run prints at most a menu plus one diagnostic - measured at 44-543 bytes across
# all four scripts. A pre-fix spin produced 6-13 MB in 4s. Those two are ~4 orders of magnitude
# apart, so the exact threshold barely matters; 100 KB sits between them with ~2 orders of
# headroom either way (184x above the largest real run, 60x below the smallest spin), which is
# wide enough not to be brittle about wording and tight enough that a spin cannot slip under it.
MAX_OUTPUT_BYTES=100000

# macOS has no `timeout` (coreutils installs it as `gtimeout`), and this repo's documented
# local setup is `brew install bats-core` - so resolve it rather than letting the whole suite
# fail as a confusing 127 in the middle of unrelated assertions.
setup_file() {
  if command -v timeout >/dev/null 2>&1; then
    export TIMEOUT_BIN="timeout"
  elif command -v gtimeout >/dev/null 2>&1; then
    export TIMEOUT_BIN="gtimeout"
  else
    echo "GNU timeout is required by this suite (macOS: brew install coreutils)" >&2
    return 1
  fi
}

setup() {
  # A bare `mktemp -d` is a GNU extension; BSD/macOS mktemp requires a template and exits
  # with a usage error without one. This suite already goes out of its way to run on macOS
  # (the gtimeout fallback in setup_file), so failing one line into setup() there would be
  # incoherent. The sibling suites use the bare form and would break on macOS too, but that
  # is theirs to fix.
  WORK="$(mktemp -d "${TMPDIR:-/tmp}/pcp24040.XXXXXX")"
  BIN="${WORK}/bin"
  mkdir -p "${BIN}"

  # Stands in for dev/platform-provisioner.sh. Only run.sh's valid-choice cases reach it; it
  # must not do anything, because these tests are about the loop, not about deployment.
  cat > "${BIN}/record.sh" <<'EOS'
#!/bin/bash
echo "PIPELINE_RAN $(basename "${PIPELINE_INPUT_RECIPE}")"
exit 0
EOS
  chmod +x "${BIN}/record.sh"

  # generate-recipe.sh gates on `yq --version` >= 4.40 and on helm BEFORE its menu. Without
  # stubs these tests would pass or fail on what the host happens to have installed rather
  # than on the loop under test - and would silently never reach the menu at all. Same stubs
  # as test_onprem_generate_recipe.bats.
  cat > "${BIN}/yq" <<'EOS'
#!/bin/bash
if [[ "$1" == "--version" ]]; then
  echo "yq (https://github.com/mikefarah/yq/) version v4.44.3"
  exit 0
fi
cat > /dev/null
echo "STUBBED_RECIPE_CONTENT"
EOS
  chmod +x "${BIN}/yq"

  cat > "${BIN}/helm" <<'EOS'
#!/bin/bash
echo "STUBBED_CHART_TEMPLATE"
EOS
  chmod +x "${BIN}/helm"

  printf -v PIPELINE_SCRIPT 'bash %q' "${BIN}/record.sh"
  export PIPELINE_SCRIPT
  export PATH="${BIN}:${PATH}"

  OUT="${WORK}/out.txt"
}

teardown() {
  # `if`, not `[ … ] && …`: as a one-liner an unset WORK makes teardown itself exit non-zero
  # and bats then reports the test as failed for a reason that has nothing to do with it.
  if [ -n "${WORK:-}" ]; then
    rm -rf "${WORK}"
  fi
}

#   run_bounded <script> <stdin_file> [args…]
# Sets $_rb_status (124 = the timeout fired, i.e. it never terminated) and $_rb_bytes.
# Prefixed, so a future `run run_bounded …` cannot silently collide with bats' own
# $status/$output and invert what these assertions mean.
run_bounded() {
  local script=$1 stdin_src=$2
  shift 2
  cd "${WORK}" || return 1
  # `|| _rb_status=$?` rather than a bare call: bats runs tests under errexit, and a non-zero
  # exit is the expected outcome of most of these cases.
  _rb_status=0
  "${TIMEOUT_BIN}" "${TIMEOUT_SECS}" bash "${script}" "$@" < "${stdin_src}" > "${OUT}" 2>&1 || _rb_status=$?
  _rb_bytes=$(wc -c < "${OUT}")
}

# State A driven by a stream that genuinely never ends. A large FILE of invalid lines would
# not do: it can be drained, and a half-fixed loop that consumed it would then hit EOF and
# terminate for the wrong reason. `yes` cannot be drained, so the only way out is the guard
# under test. It is reaped by SIGPIPE when the reader exits.
# This is also the pipe equivalent of a human mistyping once at the prompt: in state A stdin
# is never read again, so the first invalid value is all that matters.
run_bounded_endless_invalid() {
  local script=$1
  cd "${WORK}" || return 1
  _rb_status=0
  yes 99 | "${TIMEOUT_BIN}" "${TIMEOUT_SECS}" bash "${script}" > "${OUT}" 2>&1 || _rb_status=$?
  _rb_bytes=$(wc -c < "${OUT}")
}

# Bounded, and exit code exactly 1. Pinning `-eq 1` rather than "non-zero" matters: 124
# (timeout), 127 (missing binary) and 126 are also non-zero. It also pins that the guard uses
# `exit 1` and not `break` - after a break, run.sh's closing printf sets the process exit code
# to 0 and a rejected option would report success (the PCP-23809 false-green trap).
assert_rejected() {
  [ "$_rb_status" -ne 124 ]
  [ "$_rb_status" -eq 1 ]
  [ "$_rb_bytes" -lt "${MAX_OUTPUT_BYTES}" ]
  grep -q "Invalid or missing option" "${OUT}"
}

# ---------------------------------------------------------------------------------------
# run.sh - the ticket's primary subject, covered in detail
# ---------------------------------------------------------------------------------------

@test "run.sh: state B - no stdin at all terminates" {
  run_bounded "${RUN_SH}" /dev/null

  assert_rejected
  # The menu is offered once (there is no way to know stdin is spent until read fails), but
  # exactly once - reprinting it is the regression.
  [ "$(grep -c "Please select an option" "${OUT}")" -eq 1 ]
}

@test "run.sh: state A - an invalid argument terminates and names the value" {
  run_bounded "${RUN_SH}" /dev/null 99

  assert_rejected
  grep -q "'99'" "${OUT}"
  # $choice was set before the loop, so no menu is ever offered.
  ! grep -q "Please select an option" "${OUT}"
}

@test "run.sh: argument 9 terminates - the value the old header comment advertised" {
  # The file header used to read `Arguments: 1 - 9` while the case statement only ever had
  # 0-8, so following the documentation was itself a way into the infinite loop. The comment
  # is corrected in this change; this pins the behaviour regardless.
  run_bounded "${RUN_SH}" /dev/null 9

  assert_rejected
  grep -q "'9'" "${OUT}"
}

@test "run.sh: a non-numeric argument terminates" {
  # `./run.sh --help` is the shape a user reaches for first, and it used to spin.
  run_bounded "${RUN_SH}" /dev/null --help

  assert_rejected
  grep -q -- "'--help'" "${OUT}"
}

@test "run.sh: state A - an endless stream of invalid choices terminates" {
  run_bounded_endless_invalid "${RUN_SH}"

  assert_rejected
  # Stopped on the FIRST invalid value rather than chewing through the stream.
  [ "$(grep -c "Please select an option" "${OUT}")" -eq 1 ]
}

@test "run.sh: an empty argument still means 'no choice given'" {
  # `./run.sh "$SOME_UNSET_VAR"` has always fallen through to the menu - callers expand it
  # unquoted from a variable. It must not be mistaken for an invalid choice, so: menu first,
  # and the diagnostic reports an empty value rather than a bogus one.
  run_bounded "${RUN_SH}" /dev/null ""

  assert_rejected
  [ "$(grep -c "Please select an option" "${OUT}")" -eq 1 ]
  grep -q "option: ''" "${OUT}"
}

@test "run.sh: a valid choice fed on stdin still runs its step" {
  # The fix must not cost the normal menu path. Option 6 is the cheapest branch that reaches
  # the pipeline: one recipe, no retries, no sleeps.
  : > "${WORK}/04-tp-adjust-resource.yaml"
  printf '6\n' > "${WORK}/in.txt"
  run_bounded "${RUN_SH}" "${WORK}/in.txt"

  [ "$_rb_status" -eq 0 ]
  grep -q "PIPELINE_RAN 04-tp-adjust-resource.yaml" "${OUT}"
}

@test "run.sh: a valid choice with no trailing newline is still honoured" {
  # `printf '6'` makes `read` return non-zero while still assigning $choice. A fix that
  # treated a failed read as fatal would reject input the script used to accept; this guard
  # sits in `*)` instead and never inspects read's status, so the case is handled by
  # construction. Pinned because a future "improvement" could easily reintroduce the check.
  : > "${WORK}/04-tp-adjust-resource.yaml"
  printf '6' > "${WORK}/in.txt"
  run_bounded "${RUN_SH}" "${WORK}/in.txt"

  [ "$_rb_status" -eq 0 ]
  grep -q "PIPELINE_RAN 04-tp-adjust-resource.yaml" "${OUT}"
}

@test "run.sh: a valid argument still runs its step" {
  # The argument path every documented invocation uses (./run.sh 1 .. ./run.sh 8).
  : > "${WORK}/04-tp-adjust-resource.yaml"
  run_bounded "${RUN_SH}" /dev/null 6

  [ "$_rb_status" -eq 0 ]
  grep -q "PIPELINE_RAN 04-tp-adjust-resource.yaml" "${OUT}"
}

@test "run.sh: choice 0 still exits cleanly" {
  # 0 is a real option but not a deployment step; a guard that treated only 1-8 as valid
  # would break the documented way to leave the menu.
  run_bounded "${RUN_SH}" /dev/null 0

  [ "$_rb_status" -eq 0 ]
  grep -q "Exiting" "${OUT}"
}

# ---------------------------------------------------------------------------------------
# The sibling menus in the same directory - same defect, same two states.
# One test per script per state, so a failure names the script that regressed.
# ---------------------------------------------------------------------------------------

@test "adjust-recipe.sh: state B - no stdin terminates" {
  # The headless installer's default path: tp-install-on-prem.sh:452 calls this with zero
  # arguments whenever TP_K8S_CLUSTER_TYPE_CODE is unset, which is its own default.
  run_bounded "${ONPREM_DIR}/adjust-recipe.sh" /dev/null

  assert_rejected
}

@test "adjust-recipe.sh: state A - an invalid argument terminates" {
  run_bounded "${ONPREM_DIR}/adjust-recipe.sh" /dev/null 99

  assert_rejected
  grep -q "'99'" "${OUT}"
}

@test "adjust-recipe.sh: state A - an endless stream of invalid choices terminates" {
  run_bounded_endless_invalid "${ONPREM_DIR}/adjust-recipe.sh"

  assert_rejected
}

@test "adjust-ingress.sh: state B - no stdin terminates" {
  run_bounded "${ONPREM_DIR}/adjust-ingress.sh" /dev/null

  assert_rejected
}

@test "adjust-ingress.sh: state A - an invalid argument terminates" {
  run_bounded "${ONPREM_DIR}/adjust-ingress.sh" /dev/null 99

  assert_rejected
  grep -q "'99'" "${OUT}"
}

@test "adjust-ingress.sh: state A - an endless stream of invalid choices terminates" {
  run_bounded_endless_invalid "${ONPREM_DIR}/adjust-ingress.sh"

  assert_rejected
}

@test "generate-recipe.sh: state B - no stdin terminates" {
  run_bounded "${ONPREM_DIR}/generate-recipe.sh" /dev/null

  assert_rejected
}

@test "generate-recipe.sh: state A - an invalid source argument terminates" {
  run_bounded "${ONPREM_DIR}/generate-recipe.sh" /dev/null 99

  assert_rejected
  grep -q "'99'" "${OUT}"
}

@test "generate-recipe.sh: state A - an endless stream of invalid choices terminates" {
  run_bounded_endless_invalid "${ONPREM_DIR}/generate-recipe.sh"

  assert_rejected
}

@test "generate-recipe.sh: the SECOND menu is guarded too" {
  # This file has two of these loops. `1` picks a valid source (the helm/yq stubs satisfy it
  # offline) so the invalid `99` lands in generate_recipe's own menu - a loop that a fix
  # applied only to select_recipe_source would have left spinning.
  #
  # assert_rejected's `-eq 1` is load-bearing here beyond "it failed": generate_recipe runs
  # inside a case arm of select_recipe_source ending in `break`, so a `return 1` in its guard
  # would be swallowed and the script would exit 0. This reds a future tidy-up that makes the
  # two menus "consistent" by switching to `return`.
  run_bounded "${ONPREM_DIR}/generate-recipe.sh" /dev/null 1 99

  assert_rejected
  grep -q "'99'" "${OUT}"
}

@test "the headless installer propagates the adjust-* scripts' exit status" {
  # These two `|| exit $?` are what makes the fix land on the path this PR cites as the reason
  # the sibling scripts are in scope: tp-install-on-prem.sh has no `set -e`, so without them it
  # prints the rejection and carries on into the token update and a full ./run.sh deploy with
  # recipes never adjusted for the cluster - a loud hang traded for a quiet wrong deploy.
  #
  # This is a SOURCE-level assertion, deliberately weaker than everything else in this file,
  # and it goes against the sibling suite's rule of executing rather than pattern-matching.
  # The justification is cost: reaching that line behaviourally means stubbing curl, docker and
  # five sibling scripts and running ~450 lines of prelude, for two lines of straight-line
  # status propagation with no branching. What it pins is not that `||` works - bash guarantees
  # that - but that a future edit to this block (e.g. giving TP_K8S_CLUSTER_TYPE_CODE a real
  # default and "simplifying" the now-redundant-looking guard away) cannot silently reopen it.
  # Counted, not merely matched: a bare `grep -q` for the guarded form catches a DELETED
  # guard but not a STRANDED one - duplicate the call site, or move this block somewhere it
  # no longer runs, and a "does a guarded call exist anywhere" assertion stays green.
  # Comparing the two counts asserts the actual property: every invocation is guarded.
  # `^[[:space:]]*\./` anchors to invocation lines so the comment block above them, which
  # also contains the literal `|| exit $?`, cannot satisfy either count.
  local installer="${PROJECT_ROOT}/docs/recipes/k8s/on-prem/scripts/headless/tp-install-on-prem.sh"
  [ -f "${installer}" ]

  local script total guarded
  for script in adjust-recipe adjust-ingress; do
    total=$(grep -cE "^[[:space:]]*\./${script}\.sh " "${installer}")
    guarded=$(grep -cE "^[[:space:]]*\./${script}\.sh .*\|\| exit \\\$\\?" "${installer}")
    [ "${total}" -ge 1 ]
    [ "${total}" -eq "${guarded}" ]
  done
}
