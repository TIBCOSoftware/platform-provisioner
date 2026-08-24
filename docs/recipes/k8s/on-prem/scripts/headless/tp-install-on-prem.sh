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
# tp-install-on-prem.sh: this script will use docker to run the pipeline task
# Globals:
#   TP_TOP_DOMAIN: the top domain (default: tp.localhost)
#   TP_K8S_CLUSTER_TYPE_CODE: the k8s cluster type code. 1 for k3s, 2 for OpenShift, 3 for Docker Desktop (default), 4 for miniKube, 5 for kind, 6 for MicroK8s
#   TP_K8S_INGRESS_TYPE_CODE: the ingress type code. 1=nginx, 2=traefik (default), 3=nginx gateway fabric, 4=haproxy, 5=istio gateway, 6=traefik gateway, 7=netscaler cpx gateway
#   TP_AUTOMATION_SCRIPT_OPTIONS: the automation script options. see: https://github.com/TIBCOSoftware/platform-provisioner/blob/main/docs/recipes/automation/on-prem/run.sh
#   GUI_TP_LICENSE_FILE_PATH: the path to the .bin license file for file-based activation
#   GUI_TP_TLS_CERT: (optional) the SSL Certificate in base64. If empty, a self-signed cert will be generated
#   GUI_TP_TLS_KEY: (optional) the SSL key in base64. If empty, a self-signed cert will be generated
#   GUI_TP_ENABLE_HYBRID_CONNECTIVITY: true to enable hybrid connectivity (use tibtunnel) for DP. Default is false, this is a new feature 1.15+. 
#   GUI_TP_AUTO_USE_CLI: the flag to use CLI mode for DP operations. default is true
#   GUI_TP_AUTO_ENABLE_BWCE: the flag to enable BWCE. default follows GUI_TP_AUTO_ENABLE_DP
#   GUI_TP_AUTO_ACTIVE_USER: activate user automatically. default is true
#   GUI_TP_AUTO_ENABLE_CONFIG_O11Y: enable O11y config. default is true
#   GUI_TP_AUTO_ENABLE_FLOGO: enable Flogo. default follows GUI_TP_AUTO_ENABLE_DP
#   GUI_TP_AUTO_ENABLE_BW5CE: enable BW5CE. default is false
#   GUI_TP_AUTO_ENABLE_TIBCOHUB: enable TIBCO Hub. default is false
#   GUI_TP_AUTO_ENABLE_SB: enable SpringBoot. default is false
#   GUI_TP_AUTO_ENABLE_EMS: enable EMS. default is false
#   GUI_TP_AUTO_ENABLE_BMDP: enable BMDP. default is false
#   GUI_TP_AUTO_IS_ENABLE_RVDM: enable RV data model. default is true
#   GUI_TP_AUTO_IS_ENABLE_EMSDM: enable EMS data model. default is true
#   GUI_TP_AUTO_IS_ENABLE_BW6DM: enable BW6 data model. default is true
#   GUI_TP_AUTO_ENABLE_O11Y_WIDGET: enable O11y widget. default is true
#   GUI_TP_AUTO_ENABLE_E2E_TEST: enable E2E test. default is false
#   GUI_TP_AUTO_ENABLE_DP: enable Data Plane. default is true
#   GUI_TP_AUTO_INGRESS_CONTROLLER: (optional) ingress/gateway controller family name for DP automation (matches CP UI dropdown: nginx, traefik, haproxy, Istio). Auto-detected from TP_K8S_INGRESS_TYPE_CODE
#   GUI_TP_AUTO_GATEWAY_NAME: (optional) gateway object name for DP automation. Auto-detected from TP_K8S_INGRESS_TYPE_CODE
#   GUI_TP_AUTO_GATEWAY_NAMESPACE: (optional) gateway namespace for DP automation. Auto-detected from TP_K8S_INGRESS_TYPE_CODE
#   GITHUB_TOKEN: (optional) GitHub token for private repo access. When set, private repos/images are used; otherwise public defaults are used.
#   TP_SKIP_DEPLOY: (optional) when "true", generate recipes only without running ./run.sh. Default is "false".
# Arguments:
#   None
# Returns:
#   0 if thing was deleted, non-zero on error
# Notes:
#   This script will generate all TP recipes and customize them for public repo
#   Requires: docker, yq (v4.40+), helm, kubectl, mkcert
# Samples:
#   ./tp-install-on-prem.sh
########################################

# Source shared tool checks (downloaded by install-tp, or available locally)
_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${_SCRIPT_DIR}/_check-tools.sh" ]]; then
  source "${_SCRIPT_DIR}/_check-tools.sh"
fi

#######################################
# Generate locally-trusted certificate for *.${TP_TOP_DOMAIN} using mkcert
# Only generates if both GUI_TP_TLS_CERT and GUI_TP_TLS_KEY are empty
# Globals:
#   TP_TOP_DOMAIN: the top domain
#   GUI_TP_TLS_CERT: (output) base64-encoded certificate
#   GUI_TP_TLS_KEY: (output) base64-encoded key
#######################################
function generate-self-signed-cert() {
  if [[ -n "${GUI_TP_TLS_CERT}" && -n "${GUI_TP_TLS_KEY}" ]]; then
    echo "TLS cert and key already provided, skipping cert generation."
    return
  fi

  echo "Generating locally-trusted certificate for *.${TP_TOP_DOMAIN} using mkcert..."

  # Install the local CA if not already done
  mkcert -install 2>/dev/null

  local _cert_file="tp-cert.pem"
  local _key_file="tp-key.pem"

  mkcert -cert-file "${_cert_file}" -key-file "${_key_file}" \
    "*.${TP_TOP_DOMAIN}" \
    "*.cp1-my.${TP_TOP_DOMAIN}" \
    "*.cp1-tunnel.${TP_TOP_DOMAIN}" \
    localhost 127.0.0.1 ::1

  if [[ $? -ne 0 ]]; then
    echo "Error: Failed to generate certificate with mkcert."
    rm -f "${_cert_file}" "${_key_file}"
    exit 1
  fi

  export GUI_TP_TLS_CERT=$(base64 < "${_cert_file}" | tr -d '\n\r')
  export GUI_TP_TLS_KEY=$(base64 < "${_key_file}" | tr -d '\n\r')
  export GUI_TP_IS_CERT_SELF_SIGNED="true"
  echo "Certificate generated successfully."
}

#######################################
# Convert license file (.bin) to base64-encoded zip
# Globals:
#   GUI_TP_LICENSE_FILE_PATH: path to the .bin license file
#   GUI_TP_ACTIVATION_ZIP_FILE_BASE64: (output) base64-encoded zip of the license file
#######################################
function convert-license-file-to-base64() {
  if [[ -n "${GUI_TP_LICENSE_FILE_PATH}" && -f "${GUI_TP_LICENSE_FILE_PATH}" ]]; then
    echo "Convert license file to base64 string..."
    if command -v zip >/dev/null 2>&1 && base64 --help 2>&1 | grep -q "\-w"; then
      # Linux / macOS GNU coreutils
      GUI_TP_ACTIVATION_ZIP_FILE_BASE64=$(zip -j -q - "${GUI_TP_LICENSE_FILE_PATH}" | base64 -w 0)
    else
      # Windows Git Bash fallback
      local win_src win_zip bash_zip
      win_src=$(cygpath -aw "$GUI_TP_LICENSE_FILE_PATH")
      win_zip=$(powershell -NoProfile -Command "[IO.Path]::Combine(\$env:TEMP,'activation.zip')")
      powershell -NoProfile -Command "Compress-Archive -Path '$win_src' -DestinationPath '$win_zip' -Force"
      bash_zip=$(cygpath -au "$win_zip")
      GUI_TP_ACTIVATION_ZIP_FILE_BASE64=$(base64 < "$bash_zip" | tr -d '\r\n')
      rm -f "$bash_zip"
    fi
    export GUI_TP_ACTIVATION_ZIP_FILE_BASE64
  fi
}

function customize-tp() {
  echo "Customize TP..."
  export TP_TOP_DOMAIN=${TP_TOP_DOMAIN:-"tp.localhost"}
  export GUI_CP_CONTAINER_REGISTRY=${GUI_CP_CONTAINER_REGISTRY:-"csgprduswrepoedge.jfrog.io"}
  export GUI_CP_CONTAINER_REGISTRY_REPOSITORY=${GUI_CP_CONTAINER_REGISTRY_REPOSITORY:-"tibco-platform-docker-prod"}
  export GUI_CP_CONTAINER_REGISTRY_USERNAME=${GUI_CP_CONTAINER_REGISTRY_USERNAME:-""}
  export GUI_CP_CONTAINER_REGISTRY_PASSWORD=${GUI_CP_CONTAINER_REGISTRY_PASSWORD:-""}

  # PCP-22771: a capability is provisioned inside a Data Plane, so the capability flags must
  # not silently default ON when DP creation is off; the CP-only install
  # (GUI_TP_AUTO_ENABLE_DP=false) would otherwise ask the automation to deploy capabilities the
  # user never asked for into a Data Plane that is never created. Resolve the DP flag first, so
  # the capability defaults below can follow it. An explicitly set capability value always wins.
  #
  # Normalised here, ONCE, before anything derives from it, because the value is load-bearing all
  # the way down: yq writes it into .meta.guiEnv verbatim (casing and all), the recipe turns it
  # into a task condition, and charts/generic-runner/scripts/_funcs_pipeline.sh:99 compares that
  # condition with EXACT string equality - [ "${_recipe_task_condition}" == "true" ]. So
  # GUI_TP_AUTO_ENABLE_DP=True would deschedule create-dp and, now that the capability defaults
  # below follow it, deploy-flogo and deploy-bwce as well: a green pipeline that provisioned
  # nothing. Whitespace goes for the same reason, and specifically the trailing \r of a CRLF env
  # file on the Windows/Git-Bash path this script supports - the activation-file handling above
  # already strips CR (`base64 ... | tr -d '\n\r'`) for exactly that reason. Lowercased with tr
  # rather than a bash 4 case-folding parameter expansion, because this script must still parse
  # under the bash 3.2 that macOS ships.
  GUI_TP_AUTO_ENABLE_DP=$(printf '%s' "${GUI_TP_AUTO_ENABLE_DP:-true}" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')
  # ...and then VALIDATED, because normalising alone stopped being enough once three flags derive
  # from this one. GUI_TP_AUTO_ENABLE_DP=yes normalises to 'yes', which is exactly equal to
  # neither task condition, so create-dp AND deploy-flogo AND deploy-bwce are all descheduled and
  # the pre-flight in tp-automation-o11y.yaml sees no capability that is exactly "true" and exits
  # 0: a green run that provisioned nothing, which is the silent no-op class PCP-22771 exists to
  # remove. Before the capability flags were derived, a typo here still left deploy-flogo
  # scheduled and it failed loudly, so refusing the typo is what keeps that property.
  # An empty value is NOT a typo: `:-` above has already turned it into the documented default,
  # the same as every other GUI_* flag in this script.
  case "${GUI_TP_AUTO_ENABLE_DP}" in
    true|false) ;;
    *)
      echo "ERROR: GUI_TP_AUTO_ENABLE_DP must be 'true' or 'false' (any casing), got: '${GUI_TP_AUTO_ENABLE_DP}'"
      exit 1
      ;;
  esac
  export GUI_TP_AUTO_ENABLE_DP
  # GUI_TP_AUTO_ENABLE_BWCE also drives the CP side (02-tp-cp-on-prem.yaml) and is defaulted
  # there first, so remember what the caller actually set for the DP side to use below.
  local _gui_tp_auto_enable_bwce_requested="${GUI_TP_AUTO_ENABLE_BWCE:-}"

  # Generate self-signed cert if not provided
  generate-self-signed-cert

  # Update 01-tp-on-prem.yaml: domain, TLS cert, and cluster settings
  _recipe_file_name="01-tp-on-prem.yaml"
  if [[ -f "${_recipe_file_name}" ]]; then
    yq eval -i '(.meta.guiEnv.GUI_TP_DNS_DOMAIN = env(TP_TOP_DOMAIN))' "$_recipe_file_name"
    yq eval -i '(.meta.guiEnv.GUI_TP_TLS_CERT = env(GUI_TP_TLS_CERT))' "$_recipe_file_name"
    yq eval -i '(.meta.guiEnv.GUI_TP_TLS_KEY = env(GUI_TP_TLS_KEY))' "$_recipe_file_name"
    yq eval -i '(.meta.guiEnv.GUI_TP_IS_CERT_SELF_SIGNED = env(GUI_TP_IS_CERT_SELF_SIGNED))' "$_recipe_file_name"
    # install nfs server for control tower Dataplane
    yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_NFS_SERVER_PROVISIONER = true)' "$_recipe_file_name"
    # for pulling images from for on-premises-third-party
    yq eval -i '(.meta.guiEnv.GUI_TP_CONTAINER_REGISTRY_URL = env(GUI_CP_CONTAINER_REGISTRY))' "$_recipe_file_name"
    yq eval -i '(.meta.guiEnv.GUI_TP_CONTAINER_REGISTRY_REPOSITORY = env(GUI_CP_CONTAINER_REGISTRY_REPOSITORY))' "$_recipe_file_name"
    yq eval -i '(.meta.guiEnv.GUI_TP_CONTAINER_REGISTRY_USER = env(GUI_CP_CONTAINER_REGISTRY_USERNAME))' "$_recipe_file_name"
    yq eval -i '(.meta.guiEnv.GUI_TP_CONTAINER_REGISTRY_PASSWORD = env(GUI_CP_CONTAINER_REGISTRY_PASSWORD))' "$_recipe_file_name"
    # enable automation ui
    yq eval -i '(.meta.guiEnv.GUI_TP_AUTOMATION_INSTALL = true)' "$_recipe_file_name"
    if [[ ${TP_K8S_CLUSTER_TYPE_CODE} == "5" ]]; then
      # only when we deploy on kind; we enable Calico CNI by default
      yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_CALICO_CNI = true)' "$_recipe_file_name"
    fi
    # Private repo: set private chart repo and token for on-premises-third-party
    if [[ -n "${GITHUB_TOKEN}" ]]; then
      yq eval -i '(.meta.guiEnv.GUI_TP_CHART_REPO = env(TP_PRIVATE_REPO))' "$_recipe_file_name"
      yq eval -i '(.meta.guiEnv.GUI_GITHUB_TOKEN = env(GITHUB_TOKEN))' "$_recipe_file_name"
      yq eval -i '(.meta.guiEnv.GUI_TP_CHART_REPO_TOKEN = env(GITHUB_TOKEN))' "$_recipe_file_name"
    fi
  fi

  # Hybrid connectivity: default disabled; can be overridden via GUI_TP_ENABLE_HYBRID_CONNECTIVITY
  export GUI_TP_ENABLE_HYBRID_CONNECTIVITY=${GUI_TP_ENABLE_HYBRID_CONNECTIVITY:-"true"}
  # Update 02-tp-cp-on-prem.yaml: domain, BWCE, platform versions
  _recipe_file_name="02-tp-cp-on-prem.yaml"
  if [[ -f "${_recipe_file_name}" ]]; then
    yq eval -i '(.meta.guiEnv.GUI_CP_DNS_DOMAIN = env(TP_TOP_DOMAIN))' "$_recipe_file_name"

    yq eval -i '(.meta.guiEnv.GUI_CP_ENABLE_HYBRID_CONNECTIVITY = env(GUI_TP_ENABLE_HYBRID_CONNECTIVITY))' "$_recipe_file_name"

    # PCP-19763: keep CP admin-init mode in lock-step with the DP automation login mode.
    # enable_api_based_initialization (this recipe) MUST equal GUI_TP_AUTO_USE_CLI (05-tp-auto-deploy-dp.yaml),
    # so derive both from the single GUI_TP_AUTO_USE_CLI source of truth (default true).
    export GUI_TP_AUTO_USE_CLI=${GUI_TP_AUTO_USE_CLI:-"true"}
    yq eval -i '(.meta.guiEnv.GUI_CP_ENABLE_API_BASED_INITIALIZATION = env(GUI_TP_AUTO_USE_CLI))' "$_recipe_file_name"

    # Enable BWCE by default for headless; BW5CE is off by default
    export GUI_TP_AUTO_ENABLE_BWCE=${GUI_TP_AUTO_ENABLE_BWCE:-"true"}
    export GUI_TP_AUTO_ENABLE_BW5CE=${GUI_TP_AUTO_ENABLE_BW5CE:-"false"}
    yq eval -i '(.meta.guiEnv.GUI_CP_INSTALL_INTEGRATION_BW = env(GUI_TP_AUTO_ENABLE_BWCE))' "$_recipe_file_name"
    yq eval -i '(.meta.guiEnv.GUI_CP_INSTALL_INTEGRATION_BWCE_UTILITIES = env(GUI_TP_AUTO_ENABLE_BWCE))' "$_recipe_file_name"
    # BW5CE utilities must follow the BW5CE enable flag, not BWCE (only bites the
    # BWCE=false & BW5CE=true case). Mirrors the SaaS gcp-install-tp.sh fix (PCP-14123).
    yq eval -i '(.meta.guiEnv.GUI_CP_INSTALL_INTEGRATION_BW5CE_UTILITIES = env(GUI_TP_AUTO_ENABLE_BW5CE))' "$_recipe_file_name"

    # Update the platform version (CP >= 1.14)
    if [[ -n "$GUI_CP_PLATFORM_TIBCO_CP_BASE_VERSION" ]]; then
      echo "Update the platform base version to $GUI_CP_PLATFORM_TIBCO_CP_BASE_VERSION"
      yq eval -i '(.meta.guiEnv.GUI_CP_PLATFORM_TIBCO_CP_BASE_VERSION = env(GUI_CP_PLATFORM_TIBCO_CP_BASE_VERSION))' "$_recipe_file_name"
    fi
    if [[ -n "$GUI_CP_PLATFORM_INTEGRATION_BW_VERSION" ]]; then
      echo "Update the platform integration bw version to $GUI_CP_PLATFORM_INTEGRATION_BW_VERSION"
      yq eval -i '(.meta.guiEnv.GUI_CP_PLATFORM_INTEGRATION_BW_VERSION = env(GUI_CP_PLATFORM_INTEGRATION_BW_VERSION))' "$_recipe_file_name"
    fi
    if [[ -n "$GUI_CP_PLATFORM_INTEGRATION_FLOGO_VERSION" ]]; then
      echo "Update the platform integration flogo version to $GUI_CP_PLATFORM_INTEGRATION_FLOGO_VERSION"
      yq eval -i '(.meta.guiEnv.GUI_CP_PLATFORM_INTEGRATION_FLOGO_VERSION = env(GUI_CP_PLATFORM_INTEGRATION_FLOGO_VERSION))' "$_recipe_file_name"
    fi
    if [[ -n "$GUI_CP_PLATFORM_INTEGRATION_SB_VERSION" ]]; then
      echo "Update the platform integration sb version to $GUI_CP_PLATFORM_INTEGRATION_SB_VERSION"
      yq eval -i '(.meta.guiEnv.GUI_CP_PLATFORM_INTEGRATION_SB_VERSION = env(GUI_CP_PLATFORM_INTEGRATION_SB_VERSION))' "$_recipe_file_name"
    fi
    if [[ -n "$GUI_CP_PLATFORM_HAWK_VERSION" ]]; then
      echo "Update the platform hawk version to $GUI_CP_PLATFORM_HAWK_VERSION"
      yq eval -i '(.meta.guiEnv.GUI_CP_PLATFORM_HAWK_VERSION = env(GUI_CP_PLATFORM_HAWK_VERSION))' "$_recipe_file_name"
    fi
    if [[ -n "$GUI_CP_PLATFORM_TIBCOHUB_VERSION" ]]; then
      echo "Update the platform tibcohub version to $GUI_CP_PLATFORM_TIBCOHUB_VERSION"
      yq eval -i '(.meta.guiEnv.GUI_CP_PLATFORM_TIBCOHUB_VERSION = env(GUI_CP_PLATFORM_TIBCOHUB_VERSION))' "$_recipe_file_name"
    fi
    if [[ -n "$GUI_CP_PLATFORM_MESSAGING_VERSION" ]]; then
      echo "Update the platform messaging version to $GUI_CP_PLATFORM_MESSAGING_VERSION"
      yq eval -i '(.meta.guiEnv.GUI_CP_PLATFORM_MESSAGING_VERSION = env(GUI_CP_PLATFORM_MESSAGING_VERSION))' "$_recipe_file_name"
    fi
    if [[ -n "$GUI_CP_PLATFORM_EVENTPROCESSING_VERSION" ]]; then
      echo "Update the platform eventprocessing version to $GUI_CP_PLATFORM_EVENTPROCESSING_VERSION"
      yq eval -i '(.meta.guiEnv.GUI_CP_PLATFORM_EVENTPROCESSING_VERSION = env(GUI_CP_PLATFORM_EVENTPROCESSING_VERSION))' "$_recipe_file_name"
    fi
    if [[ -n "$GUI_CP_PLATFORM_AI_AGENT_VERSION" ]]; then
      echo "Update the platform ai agent version to $GUI_CP_PLATFORM_AI_AGENT_VERSION"
      yq eval -i '(.meta.guiEnv.GUI_CP_PLATFORM_AI_AGENT_VERSION = env(GUI_CP_PLATFORM_AI_AGENT_VERSION))' "$_recipe_file_name"
    fi
    # Private repo: set private CP/DP chart repos
    if [[ -n "${GITHUB_TOKEN}" ]]; then
      yq eval -i '(.meta.guiEnv.GUI_CP_CHART_REPO = env(TP_PRIVATE_REPO))' "$_recipe_file_name"
      yq eval -i '(.meta.guiEnv.GUI_DP_CHART_REPO_HOST = env(TP_PRIVATE_REPO_HOST))' "$_recipe_file_name"
      yq eval -i '(.meta.guiEnv.GUI_DP_CHART_REPO_PATH = env(TP_PRIVATE_REPO_PATH))' "$_recipe_file_name"
      yq eval -i '(.meta.guiEnv.GUI_DP_CHART_REPO_TOKEN = env(GITHUB_TOKEN))' "$_recipe_file_name"
    fi
  fi

  # Update 03-tp-adjust-dns.yaml: DNS regex pattern
  _recipe_file_name="03-tp-adjust-dns.yaml"
  if [[ -f "${_recipe_file_name}" ]]; then
    local _escaped_domain
    _escaped_domain=$(echo "${TP_TOP_DOMAIN}" | sed 's/\./\\./g')
    export GUI_REGEX_PATTERN_BASE64=$(printf '%s' "(.*)\\.${_escaped_domain}" | base64 | tr -d '\n\r')
    yq eval -i '(.meta.guiEnv.GUI_REGEX_PATTERN_BASE64 = env(GUI_REGEX_PATTERN_BASE64))' "$_recipe_file_name"
  fi

  # Update 05-tp-auto-deploy-dp.yaml: domain, feature flags, CLI mode, license file
  _recipe_file_name="05-tp-auto-deploy-dp.yaml"
  if [[ -f "${_recipe_file_name}" ]]; then
    yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_CP_DNS_DOMAIN = env(TP_TOP_DOMAIN))' "$_recipe_file_name"

    # Feature flags for DP capabilities
    export GUI_TP_AUTO_ACTIVE_USER=${GUI_TP_AUTO_ACTIVE_USER:-"true"}
    yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_ACTIVE_USER = env(GUI_TP_AUTO_ACTIVE_USER))' "$_recipe_file_name"

    export GUI_TP_AUTO_ENABLE_CONFIG_O11Y=${GUI_TP_AUTO_ENABLE_CONFIG_O11Y:-"true"}
    yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_ENABLE_CONFIG_O11Y = env(GUI_TP_AUTO_ENABLE_CONFIG_O11Y))' "$_recipe_file_name"

    # PCP-22771: these two default to the DP flag resolved at the top of customize-tp, so a
    # CP-only install does not request capabilities the user never enabled.
    export GUI_TP_AUTO_ENABLE_FLOGO=${GUI_TP_AUTO_ENABLE_FLOGO:-"${GUI_TP_AUTO_ENABLE_DP}"}
    yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_ENABLE_FLOGO = env(GUI_TP_AUTO_ENABLE_FLOGO))' "$_recipe_file_name"

    # Only the DP side of BWCE follows the DP flag; the CP side above keeps installing BWCE by
    # default, so the capability stays available for a Data Plane registered later by hand.
    export GUI_TP_AUTO_ENABLE_BWCE=${_gui_tp_auto_enable_bwce_requested:-"${GUI_TP_AUTO_ENABLE_DP}"}
    yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_ENABLE_BWCE = env(GUI_TP_AUTO_ENABLE_BWCE))' "$_recipe_file_name"

    export GUI_TP_AUTO_ENABLE_BW5CE=${GUI_TP_AUTO_ENABLE_BW5CE:-"false"}
    yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_ENABLE_BW5CE = env(GUI_TP_AUTO_ENABLE_BW5CE))' "$_recipe_file_name"

    export GUI_TP_AUTO_ENABLE_TIBCOHUB=${GUI_TP_AUTO_ENABLE_TIBCOHUB:-"false"}
    yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_ENABLE_TIBCOHUB = env(GUI_TP_AUTO_ENABLE_TIBCOHUB))' "$_recipe_file_name"

    export GUI_TP_AUTO_ENABLE_SB=${GUI_TP_AUTO_ENABLE_SB:-"false"}
    yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_ENABLE_SB = env(GUI_TP_AUTO_ENABLE_SB))' "$_recipe_file_name"

    export GUI_TP_AUTO_ENABLE_EMS=${GUI_TP_AUTO_ENABLE_EMS:-"false"}
    yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_ENABLE_EMS = env(GUI_TP_AUTO_ENABLE_EMS))' "$_recipe_file_name"

    export GUI_TP_AUTO_ENABLE_BMDP=${GUI_TP_AUTO_ENABLE_BMDP:-"false"}
    yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_ENABLE_BMDP = env(GUI_TP_AUTO_ENABLE_BMDP))' "$_recipe_file_name"

    export GUI_TP_AUTO_IS_ENABLE_RVDM=${GUI_TP_AUTO_IS_ENABLE_RVDM:-"true"}
    yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_IS_ENABLE_RVDM = env(GUI_TP_AUTO_IS_ENABLE_RVDM))' "$_recipe_file_name"

    export GUI_TP_AUTO_IS_ENABLE_EMSDM=${GUI_TP_AUTO_IS_ENABLE_EMSDM:-"true"}
    yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_IS_ENABLE_EMSDM = env(GUI_TP_AUTO_IS_ENABLE_EMSDM))' "$_recipe_file_name"

    export GUI_TP_AUTO_IS_ENABLE_BW6DM=${GUI_TP_AUTO_IS_ENABLE_BW6DM:-"true"}
    yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_IS_ENABLE_BW6DM = env(GUI_TP_AUTO_IS_ENABLE_BW6DM))' "$_recipe_file_name"

    export GUI_TP_AUTO_ENABLE_O11Y_WIDGET=${GUI_TP_AUTO_ENABLE_O11Y_WIDGET:-"true"}
    yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_ENABLE_O11Y_WIDGET = env(GUI_TP_AUTO_ENABLE_O11Y_WIDGET))' "$_recipe_file_name"

    export GUI_TP_AUTO_ENABLE_E2E_TEST=${GUI_TP_AUTO_ENABLE_E2E_TEST:-"false"}
    yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_ENABLE_E2E_TEST = env(GUI_TP_AUTO_ENABLE_E2E_TEST))' "$_recipe_file_name"

    # Enable CLI mode for DP operations
    export GUI_TP_AUTO_USE_CLI=${GUI_TP_AUTO_USE_CLI:-"true"}
    yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_USE_CLI = env(GUI_TP_AUTO_USE_CLI))' "$_recipe_file_name"

    # Convert and inject license file if provided
    convert-license-file-to-base64
    if [[ -n "${GUI_TP_ACTIVATION_ZIP_FILE_BASE64}" ]]; then
      yq eval -i '(.meta.guiEnv.GUI_TP_ACTIVATION_ZIP_FILE_BASE64 = env(GUI_TP_ACTIVATION_ZIP_FILE_BASE64))' "$_recipe_file_name"
    fi

    # Enable/disable DP; the default is resolved at the top of customize-tp (PCP-22771), because
    # the capability flags above are derived from it.
    yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_ENABLE_DP = env(GUI_TP_AUTO_ENABLE_DP))' "$_recipe_file_name"
    # Self-signed certificate support for DP registration
    yq eval -i '(.meta.guiEnv.GUI_TP_IS_CERT_SELF_SIGNED = env(GUI_TP_IS_CERT_SELF_SIGNED))' "$_recipe_file_name"

    # Non-hybrid connectivity: when CP disables hybrid (1.15+), tell automation to fill Reachable DP URL
    # Note: non-hybrid DP registration is only supported by GUI (Playwright) automation, not CLI mode
    yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_ENABLE_HYBRID_CONNECTIVITY = env(GUI_TP_ENABLE_HYBRID_CONNECTIVITY))' "$_recipe_file_name"

    # Private repo: override automation code source; public mode keeps the chart defaults.
    if [[ -n "${GITHUB_TOKEN}" ]]; then
      yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_GITHUB_REPO_NAME = env(GUI_TP_AUTO_GITHUB_REPO_NAME))' "$_recipe_file_name"
      yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_GITHUB_REPO_PATH = env(GUI_TP_AUTO_GITHUB_REPO_PATH))' "$_recipe_file_name"
      yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_GITHUB_REPO_BRANCH = env(GUI_TP_AUTO_GITHUB_REPO_BRANCH))' "$_recipe_file_name"
    fi

    # Gateway API support: set gateway-specific variables for DP automation
    case "${TP_K8S_INGRESS_TYPE_CODE}" in
      3)
        export GUI_TP_AUTO_INGRESS_CONTROLLER=${GUI_TP_AUTO_INGRESS_CONTROLLER:-"nginx"}
        export GUI_TP_AUTO_GATEWAY_NAME=${GUI_TP_AUTO_GATEWAY_NAME:-"nginx-gateway"}
        export GUI_TP_AUTO_GATEWAY_NAMESPACE=${GUI_TP_AUTO_GATEWAY_NAMESPACE:-"ingress-system"}
        ;;
      5)
        export GUI_TP_AUTO_INGRESS_CONTROLLER=${GUI_TP_AUTO_INGRESS_CONTROLLER:-"Istio"}
        export GUI_TP_AUTO_GATEWAY_NAME=${GUI_TP_AUTO_GATEWAY_NAME:-"istio-gateway-istio"}
        export GUI_TP_AUTO_GATEWAY_NAMESPACE=${GUI_TP_AUTO_GATEWAY_NAMESPACE:-"ingress-system"}
        ;;
      6)
        export GUI_TP_AUTO_INGRESS_CONTROLLER=${GUI_TP_AUTO_INGRESS_CONTROLLER:-"traefik"}
        export GUI_TP_AUTO_GATEWAY_NAME=${GUI_TP_AUTO_GATEWAY_NAME:-"traefik-gateway"}
        export GUI_TP_AUTO_GATEWAY_NAMESPACE=${GUI_TP_AUTO_GATEWAY_NAMESPACE:-"ingress-system"}
        ;;
      7)
        export GUI_TP_AUTO_INGRESS_CONTROLLER=${GUI_TP_AUTO_INGRESS_CONTROLLER:-"netscaler"}
        export GUI_TP_AUTO_GATEWAY_NAME=${GUI_TP_AUTO_GATEWAY_NAME:-"netscalercpx-gateway"}
        export GUI_TP_AUTO_GATEWAY_NAMESPACE=${GUI_TP_AUTO_GATEWAY_NAMESPACE:-"ingress-system"}
        ;;
    esac
    if [[ "${TP_K8S_INGRESS_TYPE_CODE}" =~ ^(3|5|6|7)$ ]]; then
      echo "Gateway mode: configuring gateway API variables for automation..."
      yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_INGRESS_CONTROLLER = env(GUI_TP_AUTO_INGRESS_CONTROLLER))' "$_recipe_file_name"
      yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_GATEWAY_NAME = env(GUI_TP_AUTO_GATEWAY_NAME))' "$_recipe_file_name"
      yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_GATEWAY_NAMESPACE = env(GUI_TP_AUTO_GATEWAY_NAMESPACE))' "$_recipe_file_name"
      yq eval -i '(.meta.globalEnvVariable.TP_AUTO_INGRESS_CONTROLLER = "${GUI_TP_AUTO_INGRESS_CONTROLLER}")' "$_recipe_file_name"
      yq eval -i '(.meta.globalEnvVariable.TP_AUTO_GATEWAY_CONTROLLER = "${GUI_TP_AUTO_INGRESS_CONTROLLER}")' "$_recipe_file_name"
      yq eval -i '(.meta.globalEnvVariable.TP_AUTO_GATEWAY_NAME = "${GUI_TP_AUTO_GATEWAY_NAME}")' "$_recipe_file_name"
      yq eval -i '(.meta.globalEnvVariable.TP_AUTO_GATEWAY_NAMESPACE = "${GUI_TP_AUTO_GATEWAY_NAMESPACE}")' "$_recipe_file_name"
    fi
  fi

  # Update 06-tp-o11y-stack.yaml: domain
  _recipe_file_name="06-tp-o11y-stack.yaml"
  if [[ -f "${_recipe_file_name}" ]]; then
    yq eval -i '(.meta.guiEnv.GUI_TP_DOMAIN = env(TP_TOP_DOMAIN))' "$_recipe_file_name"
  fi

  # Update 07-tp-bw5-stack.yaml: JFrog token, activation server info, license file. This is for TIBCO team internal use only.
  _recipe_file_name="07-tp-bw5-stack.yaml"
  if [[ -f "${_recipe_file_name}" ]]; then
    # as of 2025Q4 we move from github to jfrog for internal repo
    echo "Update JFrog token for ${_recipe_file_name}..."
    yq eval -i '(.meta.guiEnv.GUI_BW5_CHART_REPO_USER_NAME = env(GUI_CP_CONTAINER_REGISTRY_USERNAME))' ${_recipe_file_name}
    yq eval -i '(.meta.guiEnv.GUI_BW5_CHART_REPO_TOKEN = env(GUI_CP_CONTAINER_REGISTRY_PASSWORD))' ${_recipe_file_name}
    yq eval -i '(.meta.guiEnv.GUI_TP_ACTIVATION_ZIP_FILE_BASE64 = env(GUI_TP_ACTIVATION_ZIP_FILE_BASE64))' ${_recipe_file_name}
  fi
}

function install-tp() {
  export GITHUB_BRANCH=${GITHUB_BRANCH:-"main"}
  export GITHUB_PATH=${GITHUB_PATH:-"https://raw.githubusercontent.com/TIBCOSoftware/platform-provisioner/refs/heads/${GITHUB_BRANCH}/docs/recipes/automation/on-prem"}

  curl -fsSL -o _check-tools.sh ${GITHUB_PATH}/_check-tools.sh
  source ./_check-tools.sh
  check_yq
  check_mkcert

  curl -fsSL -o generate-recipe.sh ${GITHUB_PATH}/generate-recipe.sh
  _res=$?
  if [[ $_res -ne 0 ]]; then
    echo "Failed to download generate-recipe.sh. Check your GITHUB_BRANCH${GITHUB_TOKEN:+ and GITHUB_TOKEN}."
    exit $_res
  fi
  curl -fsSL -o adjust-recipe.sh ${GITHUB_PATH}/adjust-recipe.sh
  curl -fsSL -o adjust-ingress.sh ${GITHUB_PATH}/adjust-ingress.sh
  curl -fsSL -o update-recipe-tokens.sh ${GITHUB_PATH}/update-recipe-tokens.sh
  curl -fsSL -o run.sh ${GITHUB_PATH}/run.sh
  chmod u+x *.sh

  # Private repo: docker login for private container images
  if [[ -n "${GITHUB_TOKEN}" ]]; then
    docker login -u "ghcr" -p "${GITHUB_TOKEN}" ghcr.io
  fi

  echo "Generate recipe from latest provisioner-config-local chart..."
  ./generate-recipe.sh 1 1

  export TP_K8S_CLUSTER_TYPE_CODE=${TP_K8S_CLUSTER_TYPE_CODE:-""} # 1 for k3s, 2 for OpenShift, 3 for Docker Desktop
  ./adjust-recipe.sh ${TP_K8S_CLUSTER_TYPE_CODE}

  export TP_K8S_INGRESS_TYPE_CODE=${TP_K8S_INGRESS_TYPE_CODE:-"2"} # 1=nginx, 2=traefik, 3=nginx-gw-fabric, 4=haproxy, 5=istio-gw, 6=traefik-gw, 7=netscaler-gw
  ./adjust-ingress.sh ${TP_K8S_INGRESS_TYPE_CODE}

  echo "Update recipe tokens..."
  echo "" | ./update-recipe-tokens.sh

  customize-tp

  echo "Run the TP installation with headless mode..."
  export CURRENT_PATH=$(realpath .)
  mkdir -p ${CURRENT_PATH}/report
  export PIPELINE_CONTAINER_OPTIONAL_PARAMETER="-v /${CURRENT_PATH}/report:/tmp/auto/report"
  export TP_AUTOMATION_SCRIPT_OPTIONS=${TP_AUTOMATION_SCRIPT_OPTIONS:-"1"}

  if [[ "${TP_SKIP_DEPLOY:-false}" == "true" ]]; then
    echo "TP_SKIP_DEPLOY is set. Skipping deployment. Recipes are in: $(pwd)"
    echo "To deploy manually, run: ./run.sh ${TP_AUTOMATION_SCRIPT_OPTIONS}"
  else
    ./run.sh ${TP_AUTOMATION_SCRIPT_OPTIONS}
  fi
}

function main() {
  install-tp
}

main "$@"
