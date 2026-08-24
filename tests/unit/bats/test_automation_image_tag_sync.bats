#!/usr/bin/env bats
#
# The automation image tag must move with the automation source version.
#
# docs/recipes/automation/tp-setup/bootstrap/version.txt is the version of the automation
# python; the recipes pin the automation image by tag. Bumping the first without the second
# is silent and total: the deploy keeps pulling the previous image, so none of the new python
# runs, while any recipe change in the same commit DOES take effect immediately. That split
# is worse than shipping nothing, because a recipe guard can then key on evidence that the
# still-running old image never writes.
#
# Every prior bump in this repo changes all five files together; nothing enforced it until
# now. This guard is deliberately generic and version-agnostic: it compares the four pins
# against version.txt rather than hard-coding a number, so it never needs editing on a bump.
#

bats_require_minimum_version 1.5.0

export PROJECT_ROOT="$(cd "$(dirname "${BATS_TEST_DIRNAME}")/../.." && pwd)"
VERSION_FILE="${PROJECT_ROOT}/docs/recipes/automation/tp-setup/bootstrap/version.txt"

# The four places the automation image tag is pinned.
PINNED_FILES=(
  "charts/provisioner-config-local/recipes/tp-base-on-prem.yaml"
  "charts/provisioner-config-local/recipes/tp-base-on-prem-https.yaml"
  "docs/recipes/tp-base/tp-base-on-prem.yaml"
  "docs/recipes/tp-base/tp-base-on-prem-https.yaml"
)

@test "version.txt holds a single automation version" {
  [ -f "${VERSION_FILE}" ]
  run tr -d '[:space:]' < "${VERSION_FILE}"
  [ "$status" -eq 0 ]
  [ -n "$output" ]
  [[ "$output" == *"-auto-on-prem-"* ]]
}

@test "every automation image tag pin matches version.txt" {
  local version
  version="$(tr -d '[:space:]' < "${VERSION_FILE}")"

  local file path found
  for file in "${PINNED_FILES[@]}"; do
    path="${PROJECT_ROOT}/${file}"
    [ -f "${path}" ] || {
      echo "pinned file is missing: ${file}" >&2
      return 1
    }

    # Match the tag wherever it appears (GUI_TP_AUTOMATION_DOCKER_IMAGE_TAG: or tag:).
    found="$(grep -oE '[0-9]+\.[0-9]+\.[0-9]+-auto-on-prem-[a-z0-9]+' "${path}" | sort -u)"
    [ -n "${found}" ] || {
      echo "no automation image tag found in ${file}" >&2
      return 1
    }

    [ "${found}" = "${version}" ] || {
      echo "${file} pins '${found}' but version.txt says '${version}'" >&2
      echo "bump the tag in all four pinned recipes in the same commit as version.txt" >&2
      return 1
    }
  done
}
