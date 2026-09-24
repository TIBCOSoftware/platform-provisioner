#!/usr/bin/env bats
#
# Every containerRegistry block that names a registry must also say how to authenticate
# to it.
#
# WHY THIS EXISTS.
#
# Charts resolve the pull secret from the credentials, and when they cannot they emit
# NO imagePullSecrets at all. tibco-cp-ai-agent 1.21.0-alpha.15 resolves it as
#
#     $secret := dig "tibco" "containerRegistry" "secret"   .Values.global
#     $user   := dig "tibco" "containerRegistry" "username" .Values.global
#     $pass   := dig "tibco" "containerRegistry" "password" .Values.global
#     if $secret / else if .Values.imagePullSecret / else if (and $user $pass) / else ""
#
# and the templates wrap the block in `{{- if (include "...container-registry.secret" .) }}`.
# So a recipe that supplies url + repository but omits username/password renders the
# workloads with no imagePullSecrets, containerd falls back to an ANONYMOUS pull, the
# registry answers 401, and the capability never starts. Nothing fails at helm time —
# the release installs green.
#
# This has now shipped twice, from the same file, five months apart:
#   * PCP-18094 / PR #284 (2026-04-01) — tibco-cp-mcp-hub
#   * PCP-24234            (2026-09-04) — tibco-cp-ai-agent
#
# READ THE DEPLOYED CHART, NOT THE REPO. The ai-agent gate is NEW in the chart's 1.21
# line; 1.20.0-alpha.12 and earlier emit a hard-coded secret name unconditionally, and
# tp-helm-charts `origin/main` still carries that old unconditional helper. Reading git
# therefore "disproves" a defect that is real in the version actually installed — a trap
# this ticket fell into and escaped only by reading the DEPLOYED release instead
# (`helm get values` / `helm get manifest` against a running Control Plane).
#
# That is also exactly why the guard is a RECIPE-level contract rather than a per-chart
# one: a block that names a registry must say how to authenticate to it, because the
# recipe author cannot know which of a recipe's ~12 charts gate on it — nor when a chart
# line silently starts to, as this one did between 1.20 and 1.21.
#
# Scope is the whole tracked tree rather than a hard-coded file list, so a NEW recipe is
# covered the day it lands instead of the day someone remembers to add it here.
#
# The scan is deliberately TEXTUAL, not structural. A yq walk over
# .helmCharts[].values.content would miss the blocks that live inside a `helm upgrade
# -f - << EOF` heredoc in a task script (docs/recipes/k8s/cloud/deploy-tp-aro.yaml:449
# is exactly that), and those are the same defect. Matching on indentation catches every
# form, and needs only awk — the BATS job has no python and no helm.
#
# FAIL CLOSED. A textual scanner cannot understand every YAML spelling, and the one
# thing it must never do is stay SILENT about a block it did not understand — a guard
# that quietly passes is worse than no guard, because it is mistaken for coverage. So
# any `containerRegistry` key whose shape this scanner cannot slice (flow mapping,
# anchor, alias, list item, tab indentation, merge key) is REPORTED as `unsupported
# syntax`, not skipped. The fix for such a report is to write the block in plain block
# style, or to teach the scanner that shape deliberately.
#

bats_require_minimum_version 1.5.0

export PROJECT_ROOT="$(cd "$(dirname "${BATS_TEST_DIRNAME}")/../.." && pwd)"

# Collect every `containerRegistry` key and report, per occurrence:
#   <file>:<line><TAB><status><TAB><comma-separated child keys>
#
# status is a TOKEN computed in awk — never a raw YAML value. Transporting the raw url
# was a real defect: tab is an IFS-whitespace character, so `IFS=$'\t' read -r a b c`
# collapses adjacent tabs and shifts the columns, and a literal value could also collide
# with a sentinel. A closed token set cannot do either.
#   SET             url has a non-empty value
#   EMPTY           url is explicitly "" or '' — the public-registry marker
#   NULL            the url key exists but has NO value (url:) — NOT the same as "",
#                   and NOT exempt: helm sees nil, i.e. no registry configured at all
#   ABSENT          no url key in the block
#   UNSUPPORTED:<r> the shape could not be sliced; always reported
#
# A block runs from the key line to the first later line indented no deeper. Only
# children at the FIRST child indent count, so a nested mapping (proxy.username) cannot
# smuggle a key in.
write_scanner() {
  cat > "$1" <<'AWK'
function emit() {
  if (in_block) {
    if (keys == "") keys = "<none>"
    printf "%s:%d\t%s\t%s\n", fname, start, urlstate, keys
    in_block = 0
  }
}
function report(f, l, reason) {
  printf "%s:%d\tUNSUPPORTED:%s\t<none>\n", f, l, reason
}
# Reduce the remainder after a `key:` to the VALUE alone — no surrounding blanks, no
# trailing inline comment. Only used on the key line and on `url:`, whose value is a
# scalar.
#
# The quoted branch is what makes `url: "" # public registry` classify as EMPTY rather
# than SET. Getting that wrong is not cosmetic: it would drop the public-registry
# exemption and REPORT a legitimate block. It also has to cut at the closing quote
# rather than at the first `#`, so a registry host that legitimately contains one
# (`url: "reg#1.example"`) keeps its full value.
function tidy(s,   q, rest) {
  sub(/^[ \t]+/, "", s)
  if (s ~ /^#/) return ""
  q = substr(s, 1, 1)
  if (q == "\"" || q == "'") {
    rest = substr(s, 2)
    if (match(rest, q)) return substr(s, 1, RSTART + 1)
  }
  # Plain scalar: per YAML, a `#` only starts a comment when preceded by whitespace.
  sub(/[ \t]+#.*$/, "", s)
  sub(/[ \t]+$/, "", s)
  return s
}
FNR == 1 { emit(); fname = FILENAME }
{
  line = $0
  sub(/\r$/, "", line)
  # Blank and comment-only lines carry no indentation meaning in YAML, so they must not
  # be allowed to close a block — the Oracle exemption below is introduced by comments.
  if (line ~ /^[ ]*$/ || line ~ /^[ ]*#/) next

  match(line, /^[ \t]*/)
  lead = substr(line, 1, RLENGTH)
  indent = RLENGTH
  has_tab_indent = (lead ~ /\t/)

  if (in_block) {
    if (has_tab_indent) {
      # Tabs are illegal as YAML indentation; column math would be meaningless, so do
      # not guess — surface it.
      emit()
      report(fname, FNR, "tab-indentation")
      next
    }
    if (indent <= block_indent) {
      emit()
    } else {
      if (child_indent < 0) child_indent = indent
      if (indent == child_indent) {
        if (line ~ /^[ ]*<<[ ]*:/) {
          # A merge key pulls keys in from an anchor this scanner cannot resolve.
          in_block = 0
          report(fname, start, "merge-key")
          next
        }
        if (line ~ /^[ ]*["']?[A-Za-z0-9_.-]+["']?[ ]*:/) {
          k = line
          sub(/^[ ]*["']?/, "", k)
          sub(/["']?[ ]*:.*$/, "", k)
          keys = (keys == "" ? k : keys "," k)
          if (k == "url") {
            raw = line
            sub(/^[ ]*["']?url["']?[ ]*:/, "", raw)
            raw = tidy(raw)
            if (raw == "")                          urlstate = "NULL"
            else if (raw == "\"\"" || raw == "''")  urlstate = "EMPTY"
            else                                    urlstate = "SET"
          }
        }
      }
    }
  }

  # Not an `else`: a block that just ended may be followed immediately by the next one.
  if (!in_block && line ~ /^[ \t]*-?[ \t]*["']?containerRegistry["']?[ \t]*:/) {
    if (line ~ /^[ \t]*-[ \t]*["']?containerRegistry/) {
      report(fname, FNR, "list-item")
      next
    }
    if (has_tab_indent) {
      report(fname, FNR, "tab-indentation")
      next
    }
    rest = line
    sub(/^[ ]*["']?containerRegistry["']?[ ]*:/, "", rest)
    rest = tidy(rest)
    if (rest == "") {
      in_block = 1
      block_indent = indent
      child_indent = -1
      keys = ""
      urlstate = "ABSENT"
      start = FNR
    } else if (substr(rest, 1, 1) == "{") {
      report(fname, FNR, "flow-mapping")
    } else if (substr(rest, 1, 1) == "&") {
      report(fname, FNR, "anchor")
    } else if (substr(rest, 1, 1) == "*") {
      report(fname, FNR, "alias")
    } else if (substr(rest, 1, 1) == "|" || substr(rest, 1, 1) == ">") {
      report(fname, FNR, "block-scalar")
    }
    # else: a plain scalar value — `containerRegistry: "${TP_REGISTRY}"`, the flat form
    # used by tp-deploy-bw5dm.yaml with sibling containerRegistryUsername/Password keys.
    # That is a different, self-consistent contract; not this one, and not a violation.
  }
}
END { emit() }
AWK
}

# Read scanner output on stdin, print one line per OFFENDING occurrence.
#
# The rule mirrors the CHART contract, which offers several ways to authenticate: the
# `secret -> imagePullSecret -> (username AND password) -> ""` order quoted in the header
# above (tibco-cp-ai-agent 1.21.0-alpha.15; the same order mcp-hub documents under
# PCP-21919 / PCP-9150), plus tibco-cp-base/templates/secret.yaml, which mints the shared
# secret only when `containerRegistry.secret` was NOT supplied. So a block passes when it has
#   url (non-empty) + repository + ( secret  OR  username AND password )
# Exemptions and hard reports:
#   EMPTY url        exempt — the explicit "pull from the public registry" marker
#                    (tp-base-on-prem*.yaml use it for the gvenzl Oracle image on
#                    docker.io, where credentials would be meaningless)
#   NULL url         REPORTED — `url:` with no value is not "public", it is unconfigured
#   UNSUPPORTED:*    REPORTED — see the fail-closed note in the header
filter_violations() {
  local where status keys missing
  while IFS=$'\t' read -r where status keys; do
    case "${status}" in
      UNSUPPORTED:*)
        echo "${where} unsupported syntax (${status#UNSUPPORTED:}) — rewrite as a plain block mapping or teach the scanner this shape"
        continue
        ;;
      EMPTY) continue ;;
    esac
    [ "${keys}" = "<none>" ] && keys=""
    missing=""
    _has() { case ",${keys}," in *",$1,"*) return 0 ;; *) return 1 ;; esac; }
    _has url || missing="${missing} url"
    [ "${status}" = "NULL" ] && missing="${missing} url(null)"
    _has repository || missing="${missing} repository"
    if ! _has secret; then
      _has username || missing="${missing} username"
      _has password || missing="${missing} password"
    fi
    [ -n "${missing}" ] && echo "${where} missing:${missing} (has: ${keys})"
  done
  return 0
}

find_violations() {
  local scanner="$1"
  shift
  awk -f "${scanner}" "$@" | filter_violations
}

setup() {
  SCANNER="${BATS_TEST_TMPDIR}/scan-container-registry.awk"
  write_scanner "${SCANNER}"
}

# Scan every tracked YAML file, so a new recipe is covered without editing this test.
#
# The paths are relative and awk runs from PROJECT_ROOT, so a violation is reported as
# `charts/.../recipe.yaml:1484` no matter where bats was invoked from. Passing the list as
# argv rather than through xargs keeps that one awk process (xargs would split the list and
# is happy to run awk with NO files at all, which reads stdin and hangs); ~89 files is far
# inside any ARG_MAX. A `while read -d ''` loop rather than `mapfile -d ''` keeps this
# runnable on the bash 3.2 that macOS still ships as /bin/bash.
scan_repo() {
  local files=() f
  while IFS= read -r -d '' f; do
    files+=("$f")
  done < <(git -C "${PROJECT_ROOT}" ls-files -z '*.yaml' '*.yml')
  [ "${#files[@]}" -gt 0 ] || return 1
  ( cd "${PROJECT_ROOT}" && awk -f "${SCANNER}" "${files[@]}" )
}

# Write $1 as a fixture file and echo its path.
fixture() {
  local path="${BATS_TEST_TMPDIR}/$1"
  cat > "${path}"
  echo "${path}"
}

# ============================================================================
# (a) The guard itself — proven against fixtures before it is trusted on the repo
# ============================================================================

@test "scanner: a complete block reports all four keys and a SET url" {
  local f
  f="$(fixture complete.yaml <<'EOF'
global:
  tibco:
    containerRegistry:
      url: ${CP_CONTAINER_REGISTRY}
      password: "${CP_CONTAINER_REGISTRY_PASSWORD}"
      username: "${CP_CONTAINER_REGISTRY_USERNAME}"
      repository: "${CP_CONTAINER_REGISTRY_REPOSITORY}"
    storageClass: default
EOF
)"
  run awk -f "${SCANNER}" "${f}"
  [ "$status" -eq 0 ]
  [[ "$output" == *":3	SET	url,password,username,repository"* ]]
  run find_violations "${SCANNER}" "${f}"
  [ -z "$output" ]
}

@test "scanner: the PCP-24234 shape is REPORTED as missing username and password" {
  # The exact block this ticket touched. If this row ever passes silently, the guard is dead.
  local f
  f="$(fixture ai-agent.yaml <<'EOF'
global:
  tibco:
    containerRegistry:
      repository: "${CP_CONTAINER_REGISTRY_REPOSITORY}"
      url: ${CP_CONTAINER_REGISTRY}
external:
  environment: dev
EOF
)"
  run find_violations "${SCANNER}" "${f}"
  [ -n "$output" ]
  [[ "$output" == *"missing:"* ]]
  [[ "$output" == *"username"* ]]
  [[ "$output" == *"password"* ]]
}

@test "scanner: the PCP-18094 shape (repository only) is REPORTED" {
  # What tibco-cp-mcp-hub looked like before PR #284 — the first chart to hit this, and
  # byte-for-byte the shape ai-agent regressed to five months later.
  local f
  f="$(fixture mcp-hub.yaml <<'EOF'
global:
  tibco:
    containerRegistry:
      repository: "${CP_CONTAINER_REGISTRY_REPOSITORY}"
      url: ${CP_CONTAINER_REGISTRY}
EOF
)"
  run find_violations "${SCANNER}" "${f}"
  [ -n "$output" ]
  [[ "$output" == *"username"* ]]
  [[ "$output" == *"password"* ]]
}

@test "scanner: an explicitly EMPTY url is exempt — that is the public-registry marker" {
  local f
  f="$(fixture public.yaml <<'EOF'
global:
  tibco:
    containerRegistry:
      # Empty registry -> pull the public gvenzl Oracle image from docker.io.
      url: ""
      repository: "${TP_CONTAINER_REGISTRY_REPOSITORY}"
    storageClass: default
EOF
)"
  run find_violations "${SCANNER}" "${f}"
  [ -z "$output" ]
}

@test "scanner: an EMPTY url with a TRAILING COMMENT is still exempt" {
  # Regression: tidy() used to only handle a comment-ONLY remainder, so `url: "" # ...`
  # came out as SET and the public-registry block was REPORTED — a false positive on
  # perfectly legitimate YAML. The in-repo Oracle blocks put the comment on its own line,
  # which is why the suite stayed green while the bug was live.
  local f
  f="$(fixture public-comment.yaml <<'EOF'
global:
  containerRegistry:
    url: "" # pull the public gvenzl Oracle image from docker.io
    repository: "${TP_CONTAINER_REGISTRY_REPOSITORY}"
EOF
)"
  run awk -f "${SCANNER}" "${f}"
  [[ "$output" == *"	EMPTY	"* ]]
  run find_violations "${SCANNER}" "${f}"
  [ -z "$output" ]
}

@test "scanner: a '#' INSIDE a quoted url is part of the value, not a comment" {
  # Cutting at the first '#' instead of at the closing quote would truncate a legitimate
  # registry host. The url must still read as SET, so the block is reported for its
  # missing credentials — not silently exempted by a mangled value.
  local f
  f="$(fixture hashurl.yaml <<'EOF'
global:
  containerRegistry:
    url: "reg#1.example"
    repository: "r"
EOF
)"
  run awk -f "${SCANNER}" "${f}"
  [[ "$output" == *"	SET	"* ]]
  run find_violations "${SCANNER}" "${f}"
  [ -n "$output" ]
  [[ "$output" == *"username"* ]]
}

@test "scanner: a trailing comment on a plain url value does not change its state" {
  local f
  f="$(fixture plaincomment.yaml <<'EOF'
global:
  containerRegistry:
    url: ${CP_CONTAINER_REGISTRY} # the CP registry
    repository: "r"
EOF
)"
  run awk -f "${SCANNER}" "${f}"
  [[ "$output" == *"	SET	"* ]]
  run find_violations "${SCANNER}" "${f}"
  [ -n "$output" ]
  [[ "$output" == *"password"* ]]
}

@test "scanner: a NULL url (key present, no value) is REPORTED, not treated as public" {
  # `url:` and `url: ""` are different things. Helm sees nil for the first — no registry
  # configured at all, which is worse than the shape this guard was written for. Only an
  # explicitly quoted empty string earns the public-registry exemption.
  local f
  f="$(fixture nullurl.yaml <<'EOF'
global:
  containerRegistry:
    url:
    repository: "r"
EOF
)"
  run find_violations "${SCANNER}" "${f}"
  [ -n "$output" ]
  [[ "$output" == *"url(null)"* ]]
}

@test "scanner: a block with NO url at all is REPORTED, not silently exempt" {
  local f
  f="$(fixture no-url.yaml <<'EOF'
global:
  tibco:
    containerRegistry:
      repository: "${CP_CONTAINER_REGISTRY_REPOSITORY}"
      username: "u"
      password: "p"
EOF
)"
  run find_violations "${SCANNER}" "${f}"
  [ -n "$output" ]
  [[ "$output" == *"url"* ]]
}

@test "scanner: a pre-supplied 'secret' satisfies the contract without username/password" {
  # tibco-cp-base/templates/secret.yaml mints the shared pull secret ONLY when
  # containerRegistry.secret was not supplied; a customer pointing at their own registry
  # with their own secret is the more-secure arm of the chart contract, not a violation.
  local f
  f="$(fixture secretform.yaml <<'EOF'
global:
  tibco:
    containerRegistry:
      url: ${R}
      repository: "r"
      secret: "my-preexisting-pull-secret"
EOF
)"
  run find_violations "${SCANNER}" "${f}"
  [ -z "$output" ]
}

@test "scanner: the flat scalar form is a different contract and is not reported" {
  # tp-deploy-bw5dm.yaml passes the registry as a single string with sibling
  # containerRegistryUsername/Password keys.
  local f
  f="$(fixture scalar.yaml <<'EOF'
global:
  containerRegistry: "${TP_CONTAINER_REGISTRY}"
  containerRegistryUsername: "${TP_CONTAINER_REGISTRY_USERNAME}"
  containerRegistryPassword: "${TP_CONTAINER_REGISTRY_PASSWORD}"
EOF
)"
  run find_violations "${SCANNER}" "${f}"
  [ -z "$output" ]
}

@test "scanner: quoted child keys are recognised, not silently dropped" {
  local f
  f="$(fixture quotedkeys.yaml <<'EOF'
global:
  containerRegistry:
    "url": ${R}
    "username": "u"
    "password": "p"
    "repository": "r"
EOF
)"
  run find_violations "${SCANNER}" "${f}"
  [ -z "$output" ]
}

@test "scanner: a deeper nested key cannot stand in for a missing top-level one" {
  # proxy.username is not the registry username. Counting any descendant would let a
  # block like this pass while still under-specifying the registry.
  local f
  f="$(fixture nested.yaml <<'EOF'
global:
  tibco:
    containerRegistry:
      url: ${CP_CONTAINER_REGISTRY}
      repository: "${CP_CONTAINER_REGISTRY_REPOSITORY}"
      proxy:
        username: "someone"
        password: "secret"
EOF
)"
  run find_violations "${SCANNER}" "${f}"
  [ -n "$output" ]
  [[ "$output" == *"username"* ]]
  [[ "$output" == *"password"* ]]
}

@test "scanner: two adjacent blocks are both seen, and the second is not swallowed" {
  local f
  f="$(fixture adjacent.yaml <<'EOF'
a:
  containerRegistry:
    url: ${R}
    username: "u"
    password: "p"
    repository: "r"
b:
  containerRegistry:
    url: ${R}
    repository: "r"
EOF
)"
  run awk -f "${SCANNER}" "${f}"
  [ "${#lines[@]}" -eq 2 ]
  run find_violations "${SCANNER}" "${f}"
  [ "${#lines[@]}" -eq 1 ]
  [[ "$output" == *":8 "* ]]
}

@test "scanner: a block at end-of-file is still emitted" {
  # The END rule, not the dedent rule, has to close the last block.
  local f
  f="$(fixture eof.yaml <<'EOF'
global:
  containerRegistry:
    url: ${R}
    repository: "r"
EOF
)"
  run find_violations "${SCANNER}" "${f}"
  [ -n "$output" ]
}

@test "scanner: a heredoc-embedded block inside a task script is scanned too" {
  # deploy-tp-aro.yaml ships its registry block inside `helm upgrade -f - << EOF`.
  # A structural yq walk over .helmCharts[] would never reach it.
  local f
  f="$(fixture heredoc.yaml <<'EOF'
tasks:
- name: postgres
  script:
    content: |
      helm upgrade --install postgresql postgresql/on-premises-third-party -f - << EOF
      global:
        tibco:
          containerRegistry:
            url: "${TP_CONTAINER_REGISTRY_URL}"
            repository: "${TP_CONTAINER_REGISTRY_REPOSITORY}"
      EOF
EOF
)"
  run find_violations "${SCANNER}" "${f}"
  [ -n "$output" ]
  [[ "$output" == *"username"* ]]
}

@test "scanner: crlf line endings do not hide a violation" {
  # The recipes are edited on Windows too; a stray \r must not become part of a key.
  local f="${BATS_TEST_TMPDIR}/crlf.yaml"
  printf 'global:\r\n  containerRegistry:\r\n    url: ${R}\r\n    repository: "r"\r\n' > "${f}"
  run find_violations "${SCANNER}" "${f}"
  [ -n "$output" ]
  [[ "$output" == *"username"* ]]
}

# ============================================================================
# (a2) FAIL CLOSED — shapes the scanner cannot slice must be REPORTED, never skipped.
#      Each of these silently vanished before, which made the guard fail open.
# ============================================================================

@test "fail-closed: a trailing comment on the key line does NOT hide the block" {
  # THE regression that mattered most. `^containerRegistry:[ ]*$` required end-of-line,
  # so one comment disarmed the guard for that block with zero signal — in a file whose
  # very next line up is `enabled: ${CP_LOG_ENABLE} # set to true to enable fluentbit`.
  # A trailing comment is ordinary YAML, so it is SUPPORTED (scanned), not just reported.
  local f
  f="$(fixture keycomment.yaml <<'EOF'
global:
  containerRegistry: # the CP registry
    url: ${R}
    repository: "r"
EOF
)"
  run find_violations "${SCANNER}" "${f}"
  [ -n "$output" ]
  [[ "$output" == *"username"* ]]
  [[ "$output" == *"password"* ]]
}

@test "fail-closed: a trailing comment does not create a false positive on a good block" {
  local f
  f="$(fixture keycomment-ok.yaml <<'EOF'
global:
  containerRegistry: # the CP registry
    url: ${R}
    username: "u"
    password: "p"
    repository: "r"
EOF
)"
  run find_violations "${SCANNER}" "${f}"
  [ -z "$output" ]
}

@test "fail-closed: a flow mapping is REPORTED as unsupported, not skipped" {
  local f
  f="$(fixture flow.yaml <<'EOF'
global:
  containerRegistry: {url: "${R}", repository: "r"}
EOF
)"
  run find_violations "${SCANNER}" "${f}"
  [ -n "$output" ]
  [[ "$output" == *"unsupported syntax (flow-mapping)"* ]]
}

@test "fail-closed: an anchor on the key line is REPORTED as unsupported" {
  local f
  f="$(fixture anchor.yaml <<'EOF'
global:
  containerRegistry: &reg
    url: ${R}
    repository: "r"
EOF
)"
  run find_violations "${SCANNER}" "${f}"
  [ -n "$output" ]
  [[ "$output" == *"unsupported syntax (anchor)"* ]]
}

@test "fail-closed: an alias is REPORTED as unsupported" {
  # The mapping lives elsewhere; a textual scanner cannot resolve it, so it must not
  # pretend the block is fine.
  local f
  f="$(fixture alias.yaml <<'EOF'
global:
  containerRegistry: *credential_less_registry
EOF
)"
  run find_violations "${SCANNER}" "${f}"
  [ -n "$output" ]
  [[ "$output" == *"unsupported syntax (alias)"* ]]
}

@test "fail-closed: a merge key inside the block is REPORTED as unsupported" {
  local f
  f="$(fixture merge.yaml <<'EOF'
global:
  containerRegistry:
    <<: *credentialedRegistry
    repository: "r"
EOF
)"
  run find_violations "${SCANNER}" "${f}"
  [ -n "$output" ]
  [[ "$output" == *"unsupported syntax (merge-key)"* ]]
}

@test "fail-closed: a quoted parent key is still recognised as a block" {
  local f
  f="$(fixture quotedparent.yaml <<'EOF'
global:
  "containerRegistry":
    url: ${R}
    repository: "r"
EOF
)"
  run find_violations "${SCANNER}" "${f}"
  [ -n "$output" ]
  [[ "$output" == *"username"* ]]
}

@test "fail-closed: a list-item key is REPORTED as unsupported" {
  local f
  f="$(fixture listitem.yaml <<'EOF'
registries:
  - containerRegistry:
      url: ${R}
      repository: "r"
EOF
)"
  run find_violations "${SCANNER}" "${f}"
  [ -n "$output" ]
  [[ "$output" == *"unsupported syntax (list-item)"* ]]
}

@test "fail-closed: a TAB after the key is REPORTED, not silently skipped" {
  local f="${BATS_TEST_TMPDIR}/tabkey.yaml"
  printf 'global:\n  containerRegistry:\t\n    url: ${R}\n    repository: "r"\n' > "${f}"
  run find_violations "${SCANNER}" "${f}"
  [ -n "$output" ]
  # A tab is only whitespace here, so the block is scanned normally and reported for the
  # missing credentials — what must NOT happen is silence.
  [[ "$output" == *"username"* ]]
}

@test "fail-closed: tab-indented children are REPORTED as unsupported" {
  local f="${BATS_TEST_TMPDIR}/tabindent.yaml"
  printf 'global:\n  containerRegistry:\n\turl: ${R}\n\trepository: "r"\n' > "${f}"
  run find_violations "${SCANNER}" "${f}"
  [ -n "$output" ]
  [[ "$output" == *"unsupported syntax (tab-indentation)"* ]]
}

# ============================================================================
# (b) The repo — the assertion that actually keeps the defect out
# ============================================================================

@test "the repo scan sees the known blocks AND the ai-agent block specifically" {
  # Two separate protections against a scanner that has quietly stopped matching:
  #  - a floor on the total (a no-op scanner would emit nothing), and
  #  - a named check that the exact block this ticket is about is one of them, so the
  #    floor cannot be met by 25 OTHER blocks while this one silently vanishes.
  local out
  out="$(scan_repo)"
  [ -n "${out}" ]
  local count
  count="$(printf '%s\n' "${out}" | wc -l)"
  [ "${count}" -ge 25 ]
  printf '%s\n' "${out}" | grep -q "charts/provisioner-config-local/recipes/pp-deploy-cp-core-on-prem.yaml:"
}

@test "every containerRegistry block in the repo is fully specified" {
  local out
  out="$(scan_repo | filter_violations)"
  if [ -n "${out}" ]; then
    echo "containerRegistry blocks that are under-specified or unscannable:"
    echo "${out}"
  fi
  [ -z "${out}" ]
}

@test "the tibco-cp-ai-agent block specifically carries username and password (PCP-24234)" {
  # The regression this guard was written for, pinned by name so a future edit that
  # strips the credentials again reds on a row that says why.
  local recipe="${PROJECT_ROOT}/charts/provisioner-config-local/recipes/pp-deploy-cp-core-on-prem.yaml"
  [ -f "${recipe}" ]
  run yq e '.helmCharts[] | select(.name == "tibco-cp-ai-agent") | .values.content | from_yaml | .global.tibco.containerRegistry | keys | sort | join(",")' "${recipe}"
  [ "$status" -eq 0 ]
  [ "$output" = "password,repository,url,username" ]
}
