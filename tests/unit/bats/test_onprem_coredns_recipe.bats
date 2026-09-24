#!/usr/bin/env bats
#
# PCP-23809: behavioural guards for the config-coredns recipe's script block.
#
# The two run.sh suites stub the pipeline runner, so they prove WHICH recipe runs and in what
# order — they never execute this recipe's script. The existing checks on it were structural
# (the YAML parses, `helm template` renders), and those pass just as well if the rollout wait
# is deleted. A regression there would not surface as a red
# test; it would surface in the field as an hour-long helm timeout, which is the exact failure
# this ticket exists to remove.
#
# So these extract the script straight out of the recipe YAML and run it against a stubbed
# kubectl, asserting on what it actually does.
#

bats_require_minimum_version 1.5.0

export PROJECT_ROOT="$(cd "$(dirname "${BATS_TEST_DIRNAME}")/../.." && pwd)"
RECIPE="${PROJECT_ROOT}/charts/provisioner-config-local/config/pp-maintain-tp-config-coredns.yaml"

# base64 of '(.*)\.localhost\.dataplanes\.pro' — the recipe's own default.
REGEX_B64="KC4qKVwubG9jYWxob3N0XC5kYXRhcGxhbmVzXC5wcm8K"

setup() {
  command -v python3 >/dev/null 2>&1 || skip "python3 is needed to extract the script from the recipe YAML"
  python3 -c "import yaml" 2>/dev/null || skip "pyyaml is needed to extract the script from the recipe YAML"

  WORK="$(mktemp -d)"
  BIN="${WORK}/bin"
  mkdir -p "${BIN}"
  SCRIPT="${WORK}/coredns.sh"
  CALLS="${WORK}/kubectl-calls.txt"
  : > "${CALLS}"

  # Pull the task's script content out of the recipe exactly as the pipeline would receive it
  # (recipe is a YAML block scalar inside the config file, so this also proves the heredoc
  # survives block-scalar extraction).
  RECIPE_PATH="${RECIPE}" OUT_PATH="${SCRIPT}" python3 - <<'EOS'
import os, yaml
d = yaml.safe_load(open(os.environ["RECIPE_PATH"], encoding="utf-8"))
r = yaml.safe_load(d["recipe"])
content = r["tasks"][0]["script"]["content"]
open(os.environ["OUT_PATH"], "w", encoding="utf-8", newline="\n").write(content)
EOS

  # kubectl stub: records every invocation, and answers the two reads the script makes.
  # COREFILE_HAS_IMPORT picks which branch runs; ROLLOUT_RC forces a rollout failure.
  cat > "${BIN}/kubectl" <<'EOS'
#!/bin/bash
echo "$*" >> "$CALLS"
case "$*" in
  *"get cm coredns"*)
    if [[ "${COREFILE_HAS_IMPORT:-true}" == "true" ]]; then
      echo "import /etc/coredns/custom/*.override"
    else
      echo ".:53 { ready }"
    fi
    ;;
  *"get configmap coredns"*)
    echo '{"data":{"Corefile":".:53 {\n    ready\n}"}}'
    ;;
  *"apply -f -"*)        cat > /dev/null; echo "configmap/coredns-custom created" ;;
  *"apply -f "*)         echo "configmap/coredns configured" ;;
  *"rollout restart"*)   echo "deployment.apps/coredns restarted" ;;
  *"rollout status"*)    exit "${ROLLOUT_RC:-0}" ;;
  *) ;;
esac
exit 0
EOS
  chmod +x "${BIN}/kubectl"
  export PATH="${BIN}:${PATH}" CALLS
  export REGEX_PATTERN_BASE64="${REGEX_B64}"
  export TARGET_SERVICE="traefik.ingress-system.svc.cluster.local"
}

teardown() {
  [ -n "${WORK:-}" ] && rm -rf "${WORK}"
}

@test "the recipe waits for the CoreDNS rollout, and does it after requesting the restart" {
  # The wait is the whole point of the change: `rollout restart` only REQUESTS a restart, so
  # returning immediately hands the CP helm phase a CoreDNS that is still cycling.
  run bash "${SCRIPT}"
  [ "$status" -eq 0 ]

  grep -q "rollout restart deployment coredns" "${CALLS}"
  grep -q "rollout status deployment coredns" "${CALLS}"

  local restart_at status_at
  restart_at="$(grep -n "rollout restart" "${CALLS}" | head -1 | cut -d: -f1)"
  status_at="$(grep -n "rollout status" "${CALLS}" | head -1 | cut -d: -f1)"
  [ "$restart_at" -lt "$status_at" ]
}

@test "a rollout that never converges fails the step instead of continuing" {
  # Deliberately fatal: the CP deploy behind this would otherwise block on --wait for an hour
  # and report the real cause an hour upstream in the log.
  ROLLOUT_RC=1 run bash "${SCRIPT}"
  [ "$status" -ne 0 ]
}

@test "the managed-Corefile fallback still restarts and waits" {
  # The branch taken on clusters whose Corefile has no custom import. It was never exercised
  # by anything before, which is how an earlier version of this change shipped a guard that
  # could not fire on it.
  command -v jq >/dev/null 2>&1 || skip "jq is needed by the managed-Corefile fallback"
  COREFILE_HAS_IMPORT=false run bash "${SCRIPT}"
  [ "$status" -eq 0 ]

  grep -q "rollout restart deployment coredns" "${CALLS}"
  grep -q -- "--timeout=180s" "${CALLS}"
}
