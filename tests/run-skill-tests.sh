#!/bin/bash

#
# Copyright 2025 Cloud Software Group, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

#######################################
# run-skill-tests.sh: run every test runner found under the skills tree
# Globals:
#   SKILLS_DIR: the skills tree, relative to the project root; default .ai/skills
#   SKILL_TESTS_STRICT: "true" to run the suites the way CI runs them; default off
# Arguments:
#   SKILL: the name of one skill; only its runner is executed. The default is every skill
# Returns:
#   0 when every runner passed, non-zero when a runner failed or when no runner was found
# Notes:
#   A skill carries its own runner (tests/run-tests.sh) because each suite brings its own tools:
#   pytest for the python scripts, bats for the shell scripts. The runners are discovered instead
#   of listed here, so a new skill test suite is picked up by CI without touching this script.
#   The runners are all run, a failing one does not stop the sweep; the summary names each of them.
#   Discovery is verified first: an empty or renamed skills root is a hard failure, never a clean
#   run. A sweep that silently finds nothing would report a green run for tests that never ran.
#   The same reason makes the strict mode of the runners an opt-in of this sweep: a suite that
#   skips itself — no bats on the machine, no PyYAML in the python, a filesystem that does not
#   report the modes it is given — is the right answer on a laptop and the wrong one in CI, where
#   every tool is installed and a skip means a check silently stopped being made.
# Samples:
#   ./tests/run-skill-tests.sh                      # every skill
#   ./tests/run-skill-tests.sh validate-pipeline    # one skill
#   SKILLS_DIR=.ai/skills ./tests/run-skill-tests.sh
#   SKILL_TESTS_STRICT=true ./tests/run-skill-tests.sh    # the way CI runs them
#######################################

set -uo pipefail

_SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_PROJECT_ROOT="$(cd "${_SCRIPT_PATH}/.." && pwd)"

SKILLS_DIR="${SKILLS_DIR:-.ai/skills}"

# the runner every skill test suite provides; see .ai/skills/*/tests/README.md
_RUNNER_NAME="run-tests.sh"

# Handed to every runner, so one sweep runs every suite the same way — including the value a caller
# set as a plain shell variable of its own instead of an exported one.
export SKILL_TESTS_STRICT="${SKILL_TESTS_STRICT:-}"

# usage prints how to call this script
function usage() {
  cat <<EOF
Usage: tests/run-skill-tests.sh [skill]

Runs ${SKILLS_DIR}/<skill>/tests/${_RUNNER_NAME} for every skill that has one.
Without an argument every discovered runner is executed.

Environment:
  SKILLS_DIR           the skills tree, relative to the project root (default: .ai/skills)
  SKILL_TESTS_STRICT   "true" runs the suites the way CI does: every tool is required and a test
                       that skips itself fails the run (default: off)
EOF
}

#######################################
# discover_runners prints the test runners of the requested skills, one per line
# Arguments:
#   _skill: the name of one skill, or empty for every skill
#######################################
function discover_runners() {
  local _skill=${1:-}
  local _root="${_PROJECT_ROOT}/${SKILLS_DIR}"

  if [[ ! -d "${_root}" ]]; then
    echo "skills root not found: ${_root}" >&2
    return 1
  fi

  if [[ -n "${_skill}" ]]; then
    if [[ ! -d "${_root}/${_skill}" ]]; then
      echo "unknown skill: ${_skill}" >&2
      return 1
    fi
    _root="${_root}/${_skill}"
  fi

  find "${_root}" -type f -name "${_RUNNER_NAME}" | sort
}

# main
function main() {
  local _skill=""
  if [[ $# -gt 0 ]]; then
    case "${1}" in
      -h|--help)
        usage
        return 0
        ;;
      -*)
        echo "unknown option: ${1}" >&2
        usage >&2
        return 1
        ;;
      *)
        _skill="${1}"
        ;;
    esac
  fi

  local _found
  _found="$(discover_runners "${_skill}")" || return 1

  # the discovery is verified before anything is run: a sweep over nothing must never look green
  if [[ -z "${_found}" ]]; then
    echo "no ${_RUNNER_NAME} found under ${SKILLS_DIR}${_skill:+/${_skill}}" >&2
    echo "  a skills tree without a single test runner is an error: it would turn an empty sweep green" >&2
    return 1
  fi

  local _runners=()
  while IFS= read -r _runner; do
    _runners+=("${_runner}")
  done <<< "${_found}"

  echo "Found ${#_runners[@]} skill test runner(s) under ${SKILLS_DIR}"
  case "${SKILL_TESTS_STRICT}" in
    1|true|TRUE|True|yes|YES)
      echo "SKILL_TESTS_STRICT: a suite that skips a test fails this sweep"
      ;;
  esac

  local _summary=""
  local _failed=0
  for _runner in "${_runners[@]}"; do
    # the name of the skill the runner belongs to: <skills root>/<skill>/tests/run-tests.sh
    local _name
    _name="$(basename "$(dirname "$(dirname "${_runner}")")")"

    echo ""
    echo "==> ${_name}: ${_runner#"${_PROJECT_ROOT}"/}"
    if bash "${_runner}"; then
      _summary+="  PASS  ${_name}"$'\n'
    else
      _summary+="  FAIL  ${_name}"$'\n'
      _failed=$((_failed + 1))
    fi
  done

  echo ""
  echo "Skill test summary"
  printf '%s' "${_summary}"

  if [[ ${_failed} -gt 0 ]]; then
    echo "${_failed} skill test runner(s) failed" >&2
    return 1
  fi
}

main "$@"
