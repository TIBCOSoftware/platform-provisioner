#!/usr/bin/env bats
#
# make automation-deploy-gcp hands paths to two different worlds, and they are not
# interchangeable on Windows.
#
# `gcloud compute scp` shells out to a NATIVE Windows pscp.exe under Git Bash. A native
# binary reads "/tmp/x" literally as C:\tmp\x, while Git Bash maps /tmp to
# %LOCALAPPDATA%\Temp - so passing the raw POSIX path made this target fail at the upload
# step on EVERY Windows run ("/tmp/automation-sync.tar.gz: No such file or directory",
# pscp exit 1). It went unnoticed for so long because it works fine on Linux and macOS,
# where the two path worlds are the same one.
#
# The inverse mistake is just as easy and is why this guard checks both directions: tar,
# rm, and everything inside the ssh block run in a POSIX shell (MSYS locally, Linux on the
# instance), so converting THOSE would break the target everywhere.
#
# The assertions below are derived from `cygpath`'s presence rather than hard-coded, so
# this file runs on Windows and on the Linux CI runner instead of skipping on one of them.
#
# Be honest about what that buys on each platform. The scp-conversion test is only a real
# regression guard where cygpath exists, i.e. on a developer's Git Bash; on the Linux CI
# runner there is nothing to convert, so it passes either way. What DOES carry weight on
# every platform is the opposite direction - the tests asserting tar, the local rm, the scp
# destination and the whole ssh block stay POSIX. Those catch the over-correction (convert
# everything), which would break the target on Linux and macOS, and they fail on CI if
# someone makes it.
#

bats_require_minimum_version 1.5.0

export PROJECT_ROOT="$(cd "$(dirname "${BATS_TEST_DIRNAME}")/../.." && pwd)"

# Both scratch paths carry GCP_INSTANCE so concurrent deploys to different instances do not
# overwrite each other's list and tarball. Derive the expected names here rather than
# hard-coding them, so the suite follows that scheme instead of pinning one spelling of it.
BATS_INSTANCE="ins-bats-dummy"
EXPECTED_TAR="/tmp/automation-sync-${BATS_INSTANCE}.tar.gz"
EXPECTED_LIST="/tmp/automation-sync-${BATS_INSTANCE}-files.txt"

# Expand the recipe without running it. GCP_INSTANCE is required by the target's guard.
# --no-print-directory: -C otherwise emits "make: Entering directory 'C:/...'" on Windows,
# which would look like a drive-letter path leaking into the recipe.
expanded_recipe() {
  make -C "${PROJECT_ROOT}" --no-print-directory -n automation-deploy-gcp \
    GCP_INSTANCE="${BATS_INSTANCE}" 2>/dev/null
}

@test "the target's recipe expands at all" {
  run expanded_recipe
  [ "$status" -eq 0 ]
  [[ "$output" == *"gcloud compute scp"* ]]
}

@test "gcloud compute scp receives a path its native binary can open" {
  local expected
  if command -v cygpath >/dev/null 2>&1; then
    # Git Bash / Cygwin: gcloud is native, so the argument must be the converted form.
    expected="$(cygpath -m "${EXPECTED_TAR}")"
    # -m, not -w: forward slashes, which no shell can mistake for escape sequences.
    [[ "$expected" != *"\\"* ]]
  else
    # Linux / macOS: nothing to convert, and converting would be wrong.
    expected="${EXPECTED_TAR}"
  fi

  run expanded_recipe
  [ "$status" -eq 0 ]

  local scp_line
  scp_line="$(printf '%s\n' "$output" | grep 'gcloud compute scp')"
  [ -n "$scp_line" ]
  [[ "$scp_line" == *"${expected}"* ]]
}

@test "the scp destination stays POSIX - it is a path on the instance, not locally" {
  run expanded_recipe
  [ "$status" -eq 0 ]

  local scp_line
  scp_line="$(printf '%s\n' "$output" | grep 'gcloud compute scp')"
  [[ "$scp_line" == *"ubuntu@${BATS_INSTANCE}:/tmp/automation-sync.tar.gz"* ]]
}

@test "tar and the local cleanup keep the POSIX path - they run in a POSIX shell" {
  run expanded_recipe
  [ "$status" -eq 0 ]

  local tar_line
  tar_line="$(printf '%s\n' "$output" | grep 'tar czf')"
  [ -n "$tar_line" ]
  [[ "$tar_line" == *"tar czf ${EXPECTED_TAR}"* ]]

  # The final local rm, i.e. an `rm -f` that is not indented inside the ssh block. It
  # removes both scratch files, and both must stay POSIX.
  printf '%s\n' "$output" | grep -qF "rm -f ${EXPECTED_TAR} ${EXPECTED_LIST}"
}

@test "everything inside the ssh block stays POSIX - it runs on the instance" {
  run expanded_recipe
  [ "$status" -eq 0 ]

  # kubectl cp / tar / rm all execute on the instance and in the pod, so a Windows path
  # would be meaningless there even when the local machine is Windows.
  [[ "$output" == *"kubectl cp /tmp/automation-sync.tar.gz"* ]]
  [[ "$output" == *"tar xzf /tmp/automation-sync.tar.gz -C /app"* ]]

  # No drive-letter path may leak into the remote half. The leading [^A-Za-z] is what
  # separates a real drive letter from the tail of a longer token: without it this also
  # matches the "s:/" of the https:// URL in the closing banner and the "D:/" of
  # "$POD:/tmp/...", neither of which is a Windows path.
  local remote_half
  remote_half="$(printf '%s\n' "$output" | grep -v 'gcloud compute scp')"
  ! printf '%s\n' "$remote_half" | grep -qE '(^|[^A-Za-z])[A-Za-z]:[/\\]'
}

# --------------------------------------------------------------------------
# What actually goes in the tarball.
#
# These run the REAL listing command against the REAL tree, with files planted for the
# purpose, instead of asserting on the recipe's text. A string match cannot tell you that
# .env was shipped; only building the list can. Everything planted is removed in teardown.
# --------------------------------------------------------------------------

BOOTSTRAP_DIR="${PROJECT_ROOT}/docs/recipes/automation/tp-setup/bootstrap"

planted=()
planted_dirs=()

# Plant a file, NEVER over an existing one.
#
# These are the real paths a developer uses - .env, a Chrome profile, the license blob -
# because those are exactly the paths whose handling is under test. That makes an
# unconditional write destructive: all of them are untracked by definition, so git could
# not restore one this suite clobbered. If the path is already there, skip the test and say
# why; a skipped test is a bad outcome, deleting someone's .env is a worse one.
plant() {
  local path="$1"
  local content="$2"
  # Deliberately NOT `local path="$1" full="${BOOTSTRAP_DIR}/${path}"`. `local` is a
  # command, so bash expands every one of its arguments BEFORE running it - ${path} there
  # is the old, empty value, and `full` comes out as the directory itself. `[ -e ]` on a
  # directory is true, so the guard below skipped every test with a plausible-looking
  # message while asserting nothing: three "ok ... # skip" lines that tested exactly
  # nothing. Caught only by printing the path.
  local full="${BOOTSTRAP_DIR}/${path}"
  local dir
  if [ -e "$full" ]; then
    skip "refusing to overwrite an existing ${path} - move it aside to run this test"
  fi
  dir="$(dirname "$full")"
  if [ ! -d "$dir" ]; then
    mkdir -p "$dir"
    planted_dirs+=("$dir")   # only remove directories this suite created
  fi
  printf '%s\n' "$content" > "$full"
  planted+=("$full")
}

teardown() {
  local p d
  for p in "${planted[@]:-}"; do
    [ -n "$p" ] && rm -f "$p"
  done
  for d in "${planted_dirs[@]:-}"; do
    [ -n "$d" ] && rmdir "$d" 2>/dev/null || true
  done
  planted=()
  planted_dirs=()
}

# The recipe's SYNC_EXCLUDES, once. The drift guard below asserts the Makefile still
# contains EVERY element of this array and no others, so the two cannot diverge silently.
#
# That guard used to pin only the first three, which left the four security-relevant ones
# unguarded: deleting the *.pem / *.key / *.p12 / *kubeconfig* pathspecs from the Makefile
# left all 13 cases green, because shipped_files() kept its own copy and went on excluding
# them. Verified by doing exactly that. Pinning the whole list is the point.
#
# Kept as an array, not a string: ':(exclude)tests' unquoted is a bash syntax error on the
# parenthesis, so it can be neither eval'd nor word-split.
SYNC_EXCLUDES=(
  ':(exclude)tests' ':(exclude)e2e'
  ':(exclude).env*' ':(exclude).netrc' ':(exclude).npmrc'
  ':(exclude)*.pem' ':(exclude)*.key' ':(exclude)*.p12' ':(exclude)*.pfx'
  ':(exclude)*.jks' ':(exclude)*.crt' ':(exclude)*kubeconfig*'
  ':(exclude)id_rsa*' ':(exclude)id_ed25519*' ':(exclude)id_ecdsa*'
  ':(exclude)credentials*.json' ':(exclude)service-account*.json'
)

shipped_files() {
  ( cd "${BOOTSTRAP_DIR}" && git ls-files -co --exclude-standard -- . "${SYNC_EXCLUDES[@]}" )
}

@test "a gitignored secret is never packaged" {
  # Measured against the exclude-list this replaced: .env, the Chrome profile (which can
  # hold live CP session cookies) and the license blob all landed in a tarball bound for a
  # shared pod. git's own ignore rules keep them out now, so there is no list to forget.
  # Inert marker content on purpose - no credential-shaped literal is written into the
  # working tree, not even a fake one.
  plant ".env" "PLANTED_BY_BATS=not-a-real-value"
  plant ".chrome-profile-test/Cookies" "PLANTED_BY_BATS=not-a-real-value"
  plant "upload/license-file.bin" "PLANTED_BY_BATS"
  plant "test_example.py" "# PLANTED_BY_BATS"

  run shipped_files
  [ "$status" -eq 0 ]

  ! printf '%s\n' "$output" | grep -qx '\.env'
  ! printf '%s\n' "$output" | grep -q '\.chrome-profile-test/'
  ! printf '%s\n' "$output" | grep -qx 'upload/license-file\.bin'
  ! printf '%s\n' "$output" | grep -qx 'test_example\.py'
}

@test "an untracked secret-shaped file is never packaged" {
  # -o ships untracked files so a newly created module deploys; the same flag would ship an
  # untracked .env.local, kubeconfig or *.pem, none of which .gitignore covers here. That
  # half of the list is a denylist, so this pins the shapes it must catch - including at
  # depth, which is why one of them is nested.
  # Extension-based AND extensionless shapes: id_rsa and .netrc are the ones a denylist
  # built from file suffixes misses, and they are the two most likely to be sitting in a
  # developer's tree.
  plant ".env.local" "PLANTED_BY_BATS=not-a-real-value"
  plant "my-cluster.pem" "PLANTED_BY_BATS"
  plant "page_object/nested-key.pem" "PLANTED_BY_BATS"
  plant "kubeconfig-planted.yaml" "PLANTED_BY_BATS"
  plant "id_rsa" "PLANTED_BY_BATS"
  plant ".netrc" "PLANTED_BY_BATS"
  plant ".npmrc" "PLANTED_BY_BATS"
  plant "credentials-planted.json" "PLANTED_BY_BATS"

  run shipped_files
  [ "$status" -eq 0 ]

  ! printf '%s\n' "$output" | grep -qx '\.env\.local'
  ! printf '%s\n' "$output" | grep -qx 'my-cluster\.pem'
  ! printf '%s\n' "$output" | grep -qx 'page_object/nested-key\.pem'
  ! printf '%s\n' "$output" | grep -qx 'kubeconfig-planted\.yaml'
  ! printf '%s\n' "$output" | grep -qx 'id_rsa'
  ! printf '%s\n' "$output" | grep -qx '\.netrc'
  ! printf '%s\n' "$output" | grep -qx '\.npmrc'
  ! printf '%s\n' "$output" | grep -qx 'credentials-planted\.json'
}

@test "a failing file lister stops the build instead of shipping an empty tarball" {
  # `git ls-files | tar --null -T -` swallows a failing lister: tar reads an empty stream,
  # writes a valid 0-entry archive and exits 0, so the target would scp it, extract nothing,
  # restart waitress and report success - the silent no-op this target exists to fix,
  # reintroduced by the fix's own plumbing. Measured:
  #     $ false | tar czf out.tgz --null -T - ; echo $?   -> 0, archive has 0 entries
  # So the recipe writes the list to a file and refuses to continue when it is empty.
  run expanded_recipe
  [ "$status" -eq 0 ]

  [[ "$output" == *"> ${EXPECTED_LIST}"* ]]
  [[ "$output" == *"test -s ${EXPECTED_LIST}"* ]]
  [[ "$output" == *"tar czf ${EXPECTED_TAR} --null -T ${EXPECTED_LIST}"* ]]

  # The unguarded pipe must not come back.
  [[ "$output" != *"| tar czf"* ]]

  # And the guard has to actually fire on an empty list.
  run bash -c 'set -e; : > /tmp/bats-empty-list.txt; test -s /tmp/bats-empty-list.txt'
  [ "$status" -ne 0 ]
  rm -f /tmp/bats-empty-list.txt
}

@test "the untracked files being shipped are printed, not shipped silently" {
  # A denylist can miss a shape. Printing what -o picked up turns a leak into something you
  # see in the terminal rather than discover in the pod.
  run expanded_recipe
  [ "$status" -eq 0 ]

  [[ "$output" == *"git ls-files -o --exclude-standard"* ]]
  [[ "$output" == *"shipping untracked: "* ]]
}

@test "a brand-new untracked source file still deploys" {
  # The reason for -o. A plain `git ls-files` would drop a module you just created and the
  # deploy would silently run without it - the exact PCP-23458 failure, reintroduced by the
  # fix for it. This is the case that makes -co right and -c wrong.
  plant "page_object/po_planted_by_bats.py" "def planted(): pass"

  run shipped_files
  [ "$status" -eq 0 ]

  printf '%s\n' "$output" | grep -qx 'page_object/po_planted_by_bats\.py'
}

@test "the packages the old allow-list dropped are all present" {
  # PCP-23458: the allow-list (case/ page_object/ utils/ templates/ static/ server.py mcps/)
  # silently omitted these, so a change to any of them deployed as a no-op.
  run shipped_files
  [ "$status" -eq 0 ]

  printf '%s\n' "$output" | grep -qx 'cli_object/orchestrator\.py'
  printf '%s\n' "$output" | grep -qx 'api_object/client\.py'
  printf '%s\n' "$output" | grep -qx 'page_cli\.py'
  printf '%s\n' "$output" | grep -qx 'server\.py'
  # upload/ payloads are tracked source; dropping them would lose a payload-default change.
  printf '%s\n' "$output" | grep -qx 'upload/bwce-payload\.json'
}

@test "the two test trees are excluded, and every listed path is real" {
  run shipped_files
  [ "$status" -eq 0 ]

  ! printf '%s\n' "$output" | grep -q '^tests/'
  ! printf '%s\n' "$output" | grep -q '^e2e/'

  # Everything listed must exist: a stale pathspec that silently matched nothing, or a
  # deleted-but-tracked file, would otherwise leave this green while tar fails at deploy time.
  local f
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    [ -e "${BOOTSTRAP_DIR}/${f}" ]
  done <<< "$output"
}

@test "the recipe uses the git-derived list, NUL-delimited" {
  run expanded_recipe
  [ "$status" -eq 0 ]

  # -z/--null: a path containing a space must not split into two arguments.
  [[ "$output" == *"git ls-files -coz --exclude-standard"* ]]
  [[ "$output" == *"tar czf ${EXPECTED_TAR} --null -T ${EXPECTED_LIST}"* ]]

  # EVERY pathspec, not a sample. Dropping one from the Makefile is the dangerous direction
  # and used to pass, because shipped_files() carried its own copy.
  local spec
  for spec in "${SYNC_EXCLUDES[@]}"; do
    if [[ "$output" != *"'${spec}'"* ]]; then
      echo "the recipe is missing pathspec ${spec}" >&2
      return 1
    fi
  done

  # ...and no others: an exclusion added to the Makefile but not here would otherwise sit
  # untested, and one added HERE but not to the Makefile would make shipped_files() a
  # fiction. Count on the SYNC_EXCLUDES definition line, not the expanded recipe, since the
  # recipe repeats $(SYNC_EXCLUDES) in both git invocations.
  local defined
  defined="$(sed -n '/^SYNC_EXCLUDES/,/[^\\]$/p' "${PROJECT_ROOT}/Makefile" | grep -o ":(exclude)" | wc -l)"
  [ "$defined" -eq "${#SYNC_EXCLUDES[@]}" ]

  # The hand-maintained exclude list must not come back: it is what shipped .env.
  [[ "$output" != *"--exclude='./tests'"* ]]
  [[ "$output" != *"--anchored"* ]]
}
