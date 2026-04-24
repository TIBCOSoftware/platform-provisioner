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
# Shared prerequisite checks for on-prem scripts.
# Sourced by generate-recipe.sh, tp-install-on-prem.sh, etc.
#######################################

# Minimum required yq version (major.minor)
_YQ_MIN_MAJOR=4
_YQ_MIN_MINOR=40

#######################################
# Parse yq version string into major.minor.patch components.
# Arguments:
#   None (reads from yq --version)
# Outputs:
#   Writes version string (e.g., "4.53.2") to stdout
# Returns:
#   0 on success, 1 if yq not found or version unparseable
#######################################
get_yq_version() {
  local version_output
  version_output=$(yq --version 2>&1) || return 1
  echo "${version_output}" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1
}

#######################################
# Validate that a version string meets the minimum yq requirement.
# Arguments:
#   1 - version string (e.g., "4.53.2")
# Returns:
#   0 if version >= minimum, 1 otherwise
#######################################
validate_yq_version() {
  local version="${1:?version string required}"
  local major minor
  major=$(echo "${version}" | cut -d. -f1)
  minor=$(echo "${version}" | cut -d. -f2)

  if [[ -z "${major}" || -z "${minor}" || ! "${major}" =~ ^[0-9]+$ || ! "${minor}" =~ ^[0-9]+$ ]]; then
    return 1
  fi

  if [[ "${major}" -ne ${_YQ_MIN_MAJOR} ]] || [[ "${minor}" -lt ${_YQ_MIN_MINOR} ]]; then
    return 1
  fi
  return 0
}

#######################################
# Check if yq is installed and meets the minimum version requirement.
# Globals:
#   None
# Arguments:
#   None
# Returns:
#   Exits with 1 if yq is missing or version is too old
#######################################
check_yq() {
  if ! command -v yq &> /dev/null; then
    echo "Error: yq is not installed. Please install yq (v${_YQ_MIN_MAJOR}.${_YQ_MIN_MINOR}+) before running this script."
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

  local yq_version_full
  yq_version_full=$(get_yq_version)
  if ! validate_yq_version "${yq_version_full}"; then
    echo "Error: yq version ${_YQ_MIN_MAJOR}.${_YQ_MIN_MINOR}+ is required. Current version: ${yq_version_full}"
    echo "Please upgrade yq: https://github.com/mikefarah/yq/releases"
    exit 1
  fi
}

#######################################
# Check if Helm is installed.
# Arguments:
#   None
# Returns:
#   Exits with 1 if Helm is missing
#######################################
check_helm() {
  if ! command -v helm &> /dev/null; then
    echo "Error: Helm is not installed. Please install Helm before running this script."
    echo "Installation instructions:"

    case "$OSTYPE" in
      darwin*)
        echo "  - macOS: brew install helm"
        ;;
      linux*)
        echo "  - Linux: curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash"
        ;;
      msys*|cygwin*|win32*)
        echo "  - Windows: Install Scoop first (https://scoop.sh), then run:"
        echo "      scoop install helm"
        echo "  - Or use Chocolatey: choco install kubernetes-helm"
        ;;
      *)
        echo "  - Unsupported OS. Please refer to the official documentation: https://helm.sh/docs/intro/install/"
        ;;
    esac

    exit 1
  fi
}

#######################################
# Check if mkcert is installed.
# Arguments:
#   None
# Returns:
#   Exits with 1 if mkcert is missing
#######################################
check_mkcert() {
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
