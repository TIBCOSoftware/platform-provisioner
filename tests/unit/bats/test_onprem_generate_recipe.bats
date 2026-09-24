#!/usr/bin/env bats
#
# PCP-23809: guards for the generate-recipe.sh half of the DNS-ordering fix.
#
# The run.sh half of that fix is covered by test_onprem_dns_before_cp.bats. The changes here
# were shipping untested, and one of them is load-bearing for an argument made over there:
# option 3 in run.sh is allowed to WARN rather than abort on a missing 03-tp-adjust-dns.yaml
# specifically because freshly generated CP-only workspaces now contain it. If the emission
# below regresses (a renamed ConfigMap key, a yq behaviour change), that warn-and-continue
# branch silently becomes the common path instead of the legacy one and the deadlock returns
# for CP-only workspaces - announced only by a WARNING line in a log nobody reads.
#
# These run the real script against a stubbed `helm`/`yq` in a temp dir, so they assert what
# the script actually writes rather than what its source looks like.
#

bats_require_minimum_version 1.5.0

export PROJECT_ROOT="$(cd "$(dirname "${BATS_TEST_DIRNAME}")/../.." && pwd)"
GEN_SH="${PROJECT_ROOT}/docs/recipes/automation/on-prem/generate-recipe.sh"

setup() {
  WORK="$(mktemp -d)"
  BIN="${WORK}/bin"
  mkdir -p "${BIN}"

  # helm: the script only pipes its output into yq, and the yq stub below ignores the
  # content, so any non-empty marker will do.
  cat > "${BIN}/helm" <<'EOS'
#!/bin/bash
echo "STUBBED_CHART_TEMPLATE"
EOS
  chmod +x "${BIN}/helm"

  # yq: the script's pipeline is
  #   echo "$_data" | yq eval .data | yq eval '.["<key>.yaml"]' | yq eval .recipe > NN-....yaml
  # Only the LAST stage's stdout reaches the output file, so echoing a fixed marker is enough
  # to prove which files the script chose to write - which is the whole question here.
  #
  # `--version` must NOT read stdin: check_yq calls `yq --version` with the terminal still
  # attached, so an unconditional `cat` there blocks forever. It also has to satisfy the
  # v4.40+ gate, hence a real-looking version string.
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

  export PATH="${BIN}:${PATH}"
}

teardown() {
  [ -n "${WORK:-}" ] && rm -rf "${WORK}"
}

# Run generate-recipe.sh with both choices preselected, from the scratch dir.
#   $1 = source choice (1 = public repo, which the helm stub satisfies)
#   $2 = recipe choice
generate() {
  cd "${WORK}" || return 1
  bash "${GEN_SH}" "$1" "$2"
}

@test "the CP-only recipe set ships the DNS recipe alongside the CP recipe" {
  # THE regression guard. Before this change option 2 emitted only 02, so
  # `generate-recipe.sh <src> 2` followed by `./run.sh 3` produced a workspace whose CP
  # deploy had no DNS prerequisite to apply.
  run generate 1 2
  [ "$status" -eq 0 ]

  [ -s "${WORK}/02-tp-cp-on-prem.yaml" ]
  [ -s "${WORK}/03-tp-adjust-dns.yaml" ]
}

@test "the CP-only set stays minimal - it does not become the full set" {
  # 03 is emitted because it is a prerequisite of 02, not because option 2 should start
  # producing everything. If this starts failing, option 2 has quietly become option 1.
  run generate 1 2
  [ "$status" -eq 0 ]

  [ ! -e "${WORK}/01-tp-on-prem.yaml" ]
  [ ! -e "${WORK}/04-tp-adjust-resource.yaml" ]
  [ ! -e "${WORK}/05-tp-auto-deploy-dp.yaml" ]
  [ ! -e "${WORK}/06-tp-o11y-stack.yaml" ]
  [ ! -e "${WORK}/07-tp-bw5-stack.yaml" ]
}

@test "the full recipe set still emits all seven" {
  run generate 1 1
  [ "$status" -eq 0 ]

  local f
  for f in 01-tp-on-prem 02-tp-cp-on-prem 03-tp-adjust-dns 04-tp-adjust-resource \
           05-tp-auto-deploy-dp 06-tp-o11y-stack 07-tp-bw5-stack; do
    [ -s "${WORK}/${f}.yaml" ]
  done
}
