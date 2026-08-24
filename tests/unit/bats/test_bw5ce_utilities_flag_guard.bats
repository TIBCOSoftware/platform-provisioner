#!/usr/bin/env bats
#
# Regression tests for the BW5CE-utilities enable flag in the on-prem headless
# installer docs/recipes/k8s/on-prem/scripts/headless/tp-install-on-prem.sh. PCP-21685.
#
# Bug: the installer stamped
#   GUI_CP_INSTALL_INTEGRATION_BW5CE_UTILITIES = env(GUI_TP_AUTO_ENABLE_BWCE)
# i.e. it drove the BW5CE utilities install off the BWCE enable flag. This only
# bites the BWCE=false & BW5CE=true case: BW5CE is requested but its utilities are
# skipped (flag follows BWCE=false), so BW5CE never provisions correctly. Fix: drive
# it off GUI_TP_AUTO_ENABLE_BW5CE (mirrors the SaaS gcp-install-tp.sh fix, PCP-14123),
# and export GUI_TP_AUTO_ENABLE_BW5CE with a default so the stamp is defined at that
# point in the script (it was previously only exported later, in the 05 DP block).
#

bats_require_minimum_version 1.5.0

export PROJECT_ROOT="$(cd "$(dirname "${BATS_TEST_DIRNAME}")/../.." && pwd)"
# The tracked on-prem headless installer. The private gdrive copies
# (docs/recipes/automation/cp-installation/headless-tp-install-private*.sh) are
# gitignored and maintained out of band, so this tracked script is the source of truth.
INSTALLER="${PROJECT_ROOT}/docs/recipes/k8s/on-prem/scripts/headless/tp-install-on-prem.sh"

# Mirror of the installer's three integration-BW stamping lines (kept in sync with
# the script; the source-regression tests below assert the script uses this form).
# Each key is driven by the exact env var the script uses for that line:
#   BW / BWCE_UTILITIES  -> GUI_TP_AUTO_ENABLE_BWCE
#   BW5CE_UTILITIES      -> GUI_TP_AUTO_ENABLE_BW5CE
stamp_integration_bw_flags() {
  local recipe_file="$1"
  yq eval -i '(.meta.guiEnv.GUI_CP_INSTALL_INTEGRATION_BW = env(GUI_TP_AUTO_ENABLE_BWCE))' "$recipe_file"
  yq eval -i '(.meta.guiEnv.GUI_CP_INSTALL_INTEGRATION_BWCE_UTILITIES = env(GUI_TP_AUTO_ENABLE_BWCE))' "$recipe_file"
  yq eval -i '(.meta.guiEnv.GUI_CP_INSTALL_INTEGRATION_BW5CE_UTILITIES = env(GUI_TP_AUTO_ENABLE_BW5CE))' "$recipe_file"
}

guienv_value() {
  local recipe_file="$1" key="$2"
  yq e -r ".meta.guiEnv.${key}" "$recipe_file"
}

setup() {
  RECIPE="${BATS_TEST_TMPDIR}/02-tp-cp-on-prem.yaml"
  cat > "${RECIPE}" <<'EOF'
meta:
  guiEnv:
    GUI_CP_INSTALL_INTEGRATION_BW: "unset"
    GUI_CP_INSTALL_INTEGRATION_BWCE_UTILITIES: "unset"
    GUI_CP_INSTALL_INTEGRATION_BW5CE_UTILITIES: "unset"
EOF
}

# ============================================================================
# Behavioural — BW5CE utilities must follow the BW5CE flag, not BWCE
# ============================================================================

@test "BWCE=false & BW5CE=true -> BW5CE utilities enabled, BWCE utilities disabled" {
  GUI_TP_AUTO_ENABLE_BWCE="false" GUI_TP_AUTO_ENABLE_BW5CE="true" stamp_integration_bw_flags "${RECIPE}"
  run guienv_value "${RECIPE}" "GUI_CP_INSTALL_INTEGRATION_BW5CE_UTILITIES"
  [ "$status" -eq 0 ]
  [ "$output" = "true" ]
  run guienv_value "${RECIPE}" "GUI_CP_INSTALL_INTEGRATION_BWCE_UTILITIES"
  [ "$status" -eq 0 ]
  [ "$output" = "false" ]
}

@test "BWCE=true & BW5CE=false (default) -> BW5CE utilities NOT enabled" {
  GUI_TP_AUTO_ENABLE_BWCE="true" GUI_TP_AUTO_ENABLE_BW5CE="false" stamp_integration_bw_flags "${RECIPE}"
  run guienv_value "${RECIPE}" "GUI_CP_INSTALL_INTEGRATION_BW5CE_UTILITIES"
  [ "$status" -eq 0 ]
  [ "$output" = "false" ]
  run guienv_value "${RECIPE}" "GUI_CP_INSTALL_INTEGRATION_BWCE_UTILITIES"
  [ "$status" -eq 0 ]
  [ "$output" = "true" ]
}

@test "both enabled -> both utilities enabled" {
  GUI_TP_AUTO_ENABLE_BWCE="true" GUI_TP_AUTO_ENABLE_BW5CE="true" stamp_integration_bw_flags "${RECIPE}"
  run guienv_value "${RECIPE}" "GUI_CP_INSTALL_INTEGRATION_BW5CE_UTILITIES"
  [ "$status" -eq 0 ]
  [ "$output" = "true" ]
  run guienv_value "${RECIPE}" "GUI_CP_INSTALL_INTEGRATION_BWCE_UTILITIES"
  [ "$status" -eq 0 ]
  [ "$output" = "true" ]
}

# ============================================================================
# Source regression — the installer must drive BW5CE utilities off the BW5CE flag
# ============================================================================

@test "installer stamps BW5CE_UTILITIES from GUI_TP_AUTO_ENABLE_BW5CE" {
  [ -f "${INSTALLER}" ]
  run grep -c 'GUI_CP_INSTALL_INTEGRATION_BW5CE_UTILITIES = env(GUI_TP_AUTO_ENABLE_BW5CE))' "${INSTALLER}"
  [ "$status" -eq 0 ]
  [ "$output" = "1" ]
}

@test "installer does NOT drive BW5CE_UTILITIES off GUI_TP_AUTO_ENABLE_BWCE (the bug)" {
  # grep exits 2 on a missing file (which would also satisfy "-ne 0"); assert the
  # file exists and require grep to exit exactly 1 (ran, found no buggy line).
  [ -f "${INSTALLER}" ]
  run grep -nE 'GUI_CP_INSTALL_INTEGRATION_BW5CE_UTILITIES = env\(GUI_TP_AUTO_ENABLE_BWCE\)\)' "${INSTALLER}"
  [ "$status" -eq 1 ]
}

@test "installer exports GUI_TP_AUTO_ENABLE_BW5CE BEFORE the BW5CE_UTILITIES stamp (02 block)" {
  [ -f "${INSTALLER}" ]
  # A plain "export exists" count is satisfied by the pre-existing 05 DP-block export
  # alone, so it can't catch a regression that removes the 02-block export the fix added
  # (yq env() would then resolve to null at the stamp). Guard the ordering contract: the
  # earliest defaulted export must precede the BW5CE_UTILITIES stamp line.
  local stamp_line export_line
  stamp_line=$(grep -n 'GUI_CP_INSTALL_INTEGRATION_BW5CE_UTILITIES = env(GUI_TP_AUTO_ENABLE_BW5CE))' "${INSTALLER}" | head -1 | cut -d: -f1)
  [ -n "$stamp_line" ]
  export_line=$(grep -n 'export GUI_TP_AUTO_ENABLE_BW5CE=${GUI_TP_AUTO_ENABLE_BW5CE:-"false"}' "${INSTALLER}" | head -1 | cut -d: -f1)
  [ -n "$export_line" ]
  [ "$export_line" -lt "$stamp_line" ]
}
