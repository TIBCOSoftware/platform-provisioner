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
#   TP_TOP_DOMAIN: the top domain (default: dev.localhost)
#   TP_K8S_CLUSTER_TYPE_CODE: the k8s cluster type code. 1 for k3s, 2 for OpenShift, 3 for Docker Desktop (default), 4 for miniKube, 5 for kind, 6 for MicroK8s
#   TP_AUTOMATION_SCRIPT_OPTIONS: the automation script options. see: https://github.com/TIBCOSoftware/platform-provisioner/blob/main/docs/recipes/automation/on-prem/run.sh
#   GUI_TP_LICENSE_FILE_PATH: the path to the .bin license file for file-based activation
#   GUI_TP_TLS_CERT: (optional) the SSL Certificate in base64. If empty, a self-signed cert will be generated
#   GUI_TP_TLS_KEY: (optional) the SSL key in base64. If empty, a self-signed cert will be generated
#   GUI_TP_AUTO_USE_CLI: the flag to use CLI mode for DP operations. default is true
#   GUI_TP_AUTO_ENABLE_BWCE: the flag to enable BWCE. default is true
#   GUI_TP_AUTO_ACTIVE_USER: activate user automatically. default is true
#   GUI_TP_AUTO_ENABLE_CONFIG_O11Y: enable O11y config. default is true
#   GUI_TP_AUTO_ENABLE_FLOGO: enable Flogo. default is true
#   GUI_TP_AUTO_ENABLE_BW5CE: enable BW5CE. default is false
#   GUI_TP_AUTO_ENABLE_TIBCOHUB: enable TIBCO Hub. default is false
#   GUI_TP_AUTO_ENABLE_EMS: enable EMS. default is false
#   GUI_TP_AUTO_ENABLE_BMDP: enable BMDP. default is false
#   GUI_TP_AUTO_IS_ENABLE_RVDM: enable RV data model. default is true
#   GUI_TP_AUTO_IS_ENABLE_EMSDM: enable EMS data model. default is true
#   GUI_TP_AUTO_IS_ENABLE_BW6DM: enable BW6 data model. default is true
#   GUI_TP_AUTO_ENABLE_O11Y_WIDGET: enable O11y widget. default is true
#   GUI_TP_AUTO_ENABLE_E2E_TEST: enable E2E test. default is false
#   GUI_TP_AUTO_ENABLE_DP: enable Data Plane. default is true
#   GITHUB_TOKEN: (optional) GitHub token for private repo access. When set, private repos/images are used; otherwise public defaults are used.
#   TP_SKIP_DEPLOY: (optional) when "true", generate recipes only without running ./run.sh. Default is "false".
# Arguments:
#   None
# Returns:
#   0 if thing was deleted, non-zero on error
# Notes:
#   This script will generate all TP recipes and customize them for public repo
#   Requires: docker, yq (v4), helm, kubectl, mkcert
# Samples:
#   ./tp-install-on-prem.sh
########################################

# Check if yq is installed
function check-yq() {
  if ! command -v yq &> /dev/null; then
    echo "Error: yq is not installed. Please install yq before running this script."
    echo "Installation instructions:"

    case "$OSTYPE" in
      darwin*)
        echo "  - macOS: brew install yq"
        ;;
      linux*)
        echo "  - Linux: wget https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 -O /usr/local/bin/yq && chmod +x /usr/local/bin/yq"
        ;;
      msys*|cygwin*|win32*)
        echo "  - Windows: Install Scoop first (https://scoop.sh), then run:"
        echo "      scoop install yq"
        ;;
      *)
        echo "  - Unsupported OS. Please refer to the official documentation: https://github.com/mikefarah/yq"
        ;;
    esac

    exit 1
  fi

  # Check yq version, which should be 4.x
  yq_version=$(yq --version | awk '{print $4}' | cut -c 2)
  if [ "$yq_version" != "4" ]; then
    echo "Error: yq version 4 is required. Please check your yq version."
    exit 1
  fi
}

# Check if mkcert is installed
function check-mkcert() {
  if ! command -v mkcert &> /dev/null; then
    echo "Error: mkcert is not installed. Please install mkcert before running this script."
    echo "Installation instructions:"

    case "$OSTYPE" in
      darwin*)
        echo "  - macOS: brew install mkcert"
        ;;
      linux*)
        echo "  - Linux: curl -JLO https://dl.filippo.io/mkcert/latest?for=linux/amd64"
        echo "          chmod +x mkcert-v*-linux-amd64"
        echo "          sudo cp mkcert-v*-linux-amd64 /usr/local/bin/mkcert"
        echo "          See: https://github.com/FiloSottile/mkcert"
        ;;
      msys*|cygwin*|win32*)
        echo "  - Windows: Install Scoop first (https://scoop.sh), then run:"
        echo "     scoop bucket add extras"
        echo "     scoop install extras/mkcert"
        ;;
      *)
        echo "  - Unsupported OS. Please refer to: https://github.com/FiloSottile/mkcert"
        ;;
    esac

    exit 1
  fi
}

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
  export TP_TOP_DOMAIN=${TP_TOP_DOMAIN:-"dev.localhost"}
  export GUI_CP_CONTAINER_REGISTRY=${GUI_CP_CONTAINER_REGISTRY:-"csgprduswrepoedge.jfrog.io"}
  export GUI_CP_CONTAINER_REGISTRY_REPOSITORY=${GUI_CP_CONTAINER_REGISTRY_REPOSITORY:-"tibco-platform-docker-prod"}
  export GUI_CP_CONTAINER_REGISTRY_USERNAME=${GUI_CP_CONTAINER_REGISTRY_USERNAME:-""}
  export GUI_CP_CONTAINER_REGISTRY_PASSWORD=${GUI_CP_CONTAINER_REGISTRY_PASSWORD:-""}

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
      yq eval -i '(.meta.guiEnv.GUI_TP_CHART_REPO = env(TP_CHART_REPO))' "$_recipe_file_name"
      yq eval -i '(.meta.guiEnv.GUI_GITHUB_TOKEN = env(GITHUB_TOKEN))' "$_recipe_file_name"
      yq eval -i '(.meta.guiEnv.GUI_TP_CHART_REPO_TOKEN = env(GITHUB_TOKEN))' "$_recipe_file_name"
    fi
  fi

  # Update 02-tp-cp-on-prem.yaml: domain, BWCE, platform versions
  _recipe_file_name="02-tp-cp-on-prem.yaml"
  if [[ -f "${_recipe_file_name}" ]]; then
    yq eval -i '(.meta.guiEnv.GUI_CP_DNS_DOMAIN = env(TP_TOP_DOMAIN))' "$_recipe_file_name"

    # Enable BWCE by default for headless
    export GUI_TP_AUTO_ENABLE_BWCE=${GUI_TP_AUTO_ENABLE_BWCE:-"true"}
    yq eval -i '(.meta.guiEnv.GUI_CP_INSTALL_INTEGRATION_BW = env(GUI_TP_AUTO_ENABLE_BWCE))' "$_recipe_file_name"
    yq eval -i '(.meta.guiEnv.GUI_CP_INSTALL_INTEGRATION_BWCE_UTILITIES = env(GUI_TP_AUTO_ENABLE_BWCE))' "$_recipe_file_name"
    yq eval -i '(.meta.guiEnv.GUI_CP_INSTALL_INTEGRATION_BW5CE_UTILITIES = env(GUI_TP_AUTO_ENABLE_BWCE))' "$_recipe_file_name"

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
      yq eval -i '(.meta.guiEnv.GUI_CP_CHART_REPO = env(TP_CHART_REPO))' "$_recipe_file_name"
      yq eval -i '(.meta.guiEnv.GUI_DP_CHART_REPO = env(TP_CHART_REPO))' "$_recipe_file_name"
      yq eval -i '(.meta.guiEnv.GUI_DP_CHART_REPO_HOST = env(TP_CHART_REPO_HOST))' "$_recipe_file_name"
      yq eval -i '(.meta.guiEnv.GUI_DP_CHART_REPO_PATH = env(TP_CHART_REPO_PATH))' "$_recipe_file_name"
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

    export GUI_TP_AUTO_ENABLE_FLOGO=${GUI_TP_AUTO_ENABLE_FLOGO:-"true"}
    yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_ENABLE_FLOGO = env(GUI_TP_AUTO_ENABLE_FLOGO))' "$_recipe_file_name"

    export GUI_TP_AUTO_ENABLE_BWCE=${GUI_TP_AUTO_ENABLE_BWCE:-"true"}
    yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_ENABLE_BWCE = env(GUI_TP_AUTO_ENABLE_BWCE))' "$_recipe_file_name"

    export GUI_TP_AUTO_ENABLE_BW5CE=${GUI_TP_AUTO_ENABLE_BW5CE:-"false"}
    yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_ENABLE_BW5CE = env(GUI_TP_AUTO_ENABLE_BW5CE))' "$_recipe_file_name"

    export GUI_TP_AUTO_ENABLE_TIBCOHUB=${GUI_TP_AUTO_ENABLE_TIBCOHUB:-"false"}
    yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_ENABLE_TIBCOHUB = env(GUI_TP_AUTO_ENABLE_TIBCOHUB))' "$_recipe_file_name"

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

    # Enable/disable DP
    export GUI_TP_AUTO_ENABLE_DP=${GUI_TP_AUTO_ENABLE_DP:-"true"}
    yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_ENABLE_DP = env(GUI_TP_AUTO_ENABLE_DP))' "$_recipe_file_name"
    # Self-signed certificate support for DP registration
    yq eval -i '(.meta.guiEnv.GUI_TP_IS_CERT_SELF_SIGNED = env(GUI_TP_IS_CERT_SELF_SIGNED))' "$_recipe_file_name"

    # Private repo: override automation code source; public mode keeps the chart defaults.
    if [[ -n "${GITHUB_TOKEN}" ]]; then
      yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_GITHUB_REPO_NAME = env(GUI_TP_AUTO_GITHUB_REPO_NAME))' "$_recipe_file_name"
      yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_GITHUB_REPO_PATH = env(GUI_TP_AUTO_GITHUB_REPO_PATH))' "$_recipe_file_name"
      yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_GITHUB_REPO_BRANCH = env(GITHUB_BRANCH))' "$_recipe_file_name"
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

  export TP_K8S_INGRESS_TYPE_CODE=${TP_K8S_INGRESS_TYPE_CODE:-"2"} # 1 for nginx, 2 for traefik
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
  check-yq
  check-mkcert
  install-tp
}

main "$@"
