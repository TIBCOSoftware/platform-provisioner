#!/bin/bash

#
# © 2024 - 2025 Cloud Software Group, Inc.
# All Rights Reserved. Confidential & Proprietary.
#

#######################################
# generate-recipe.sh: this script will generate the recipe for deploying TP on-prem
# Globals:
#   PIPELINE_CHART_REPO_PROVISIONER_CONFIG_LOCAL: the helm chart repo for provisioner-config-local
#   PIPELINE_CHART_VERSION_PROVISIONER_CONFIG_LOCAL: the helm chart version for provisioner-config-local
# Arguments:
#   1 - 3: the choice of the source of the recipe
# Returns:
#   None
# Notes:
#   The recipe comes from provisioner-config-local chart. It can be generated from public repo or local repo.
#   The default recipe values are designed for Docker Desktop environment. It can be adjusted for different k8s environments by running adjust-recipe.sh.
#   After adjust the recipes; we can use ./update-recipe-tokens.sh to update the tokens for private repos.
# Samples:
#   ./generate-recipe.sh 1 1
#######################################

export PIPELINE_CHART_REPO_PROVISIONER_CONFIG_LOCAL=${PIPELINE_CHART_REPO_PROVISIONER_CONFIG_LOCAL:-"https://tibcosoftware.github.io/platform-provisioner"}
export PIPELINE_CHART_VERSION_PROVISIONER_CONFIG_LOCAL=${PIPELINE_CHART_VERSION_PROVISIONER_CONFIG_LOCAL:-"^1.0.0"}

# This script will generate the recipe for deploying TP on-prem
function select_recipe_source() {
  local choice="${1:-""}"
  local choice2="${2:-""}"
  local _data=""
  while true; do
    if [[ -z $choice ]]; then
      echo "Please select an option:"
      echo "1. Use public repo to generate recipe"
      echo "2. Use local repo to generate recipe"
      echo "3. Exit"
      read -rp "Enter your choice (1-3): " choice
    fi

    case $choice in
      1)
        # generate from public release
        _data=$(helm template provisioner-config-local provisioner-config-local --repo "${PIPELINE_CHART_REPO_PROVISIONER_CONFIG_LOCAL}" --version "${PIPELINE_CHART_VERSION_PROVISIONER_CONFIG_LOCAL}")
        generate_recipe "${_data}" "${choice2}"
        break
        ;;
      2)
        # generate from local
        _data=$(helm template provisioner-config-local "../../../../charts/provisioner-config-local")
        generate_recipe "${_data}" "${choice2}"
        local _recipe_file_name="05-tp-auto-deploy-dp.yaml"
        # set recipe to use local script
        if [[ -f ${_recipe_file_name} ]]; then
          echo "Update recipe ${_recipe_file_name} to use local script..."
          export GUI_TP_AUTO_USE_LOCAL_SCRIPT=true
          export GUI_TP_AUTO_USE_GITHUB_SCRIPT=false
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_USE_LOCAL_SCRIPT = env(GUI_TP_AUTO_USE_LOCAL_SCRIPT))' ${_recipe_file_name}
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_USE_GITHUB_SCRIPT = env(GUI_TP_AUTO_USE_GITHUB_SCRIPT))' ${_recipe_file_name}
        fi
        break
        ;;
      3)
        echo "Exiting..."
        break
        ;;
      *)
        echo "Invalid option. Please try again."
        ;;
    esac
  done
}

function generate_recipe() {
  local _data=$1
  local choice2=$2
  while true; do
    if [[ -z $choice2 ]]; then
      echo "Which recipe do you want to generate:"
      echo "1. All TP recipes (Infra, TP, O11y, DNS adjustment, Resource adjustment, Auto deploy DP etc.)"
      echo "2. TP recipes"
      echo "3. Auto deploy DP recipe"
      echo "0. Exit"
      read -rp "Enter your choice (1-4): " choice2
    fi

    case $choice2 in
      1)
        echo "${_data}" | yq eval .data | yq eval '.["pp-deploy-tp-base-on-prem-cert.yaml"]' | yq eval .recipe > 01-tp-on-prem.yaml
        echo "${_data}" | yq eval .data | yq eval '.["pp-deploy-cp-core-on-prem.yaml"]' | yq eval .recipe > 02-tp-cp-on-prem.yaml
        echo "${_data}" | yq eval .data | yq eval '.["pp-maintain-tp-config-coredns.yaml"]' | yq eval .recipe > 03-tp-adjust-dns.yaml
        echo "${_data}" | yq eval .data | yq eval '.["pp-maintain-tp-remove-resource.yaml"]' | yq eval .recipe > 04-tp-adjust-resource.yaml
        echo "${_data}" | yq eval .data | yq eval '.["pp-maintain-tp-automation-o11y.yaml"]' | yq eval .recipe > 05-tp-auto-deploy-dp.yaml
        echo "${_data}" | yq eval .data | yq eval '.["pp-o11y-full.yaml"]' | yq eval .recipe > 06-tp-o11y-stack.yaml
        echo "${_data}" | yq eval .data | yq eval '.["pp-maintain-tp-deploy-bw5dm.yaml"]' | yq eval .recipe > 07-tp-bw5-stack.yaml
        break
        ;;
      2)
        echo "${_data}" | yq eval .data | yq eval '.["pp-deploy-cp-core-on-prem.yaml"]' | yq eval .recipe > 02-tp-cp-on-prem.yaml
        break
        ;;
      3)
        echo "${_data}" | yq eval .data | yq eval '.["pp-maintain-tp-automation-o11y.yaml"]' | yq eval .recipe > 05-tp-auto-deploy-dp.yaml
        break
        ;;
      0)
        echo "Exiting..."
        break
        ;;
      *)
        echo "Invalid option. Please try again."
        ;;
    esac
  done

  update_05-tp-auto-deploy-dp
}

# Update the recipe file 05-tp-auto-deploy-dp.yaml
update_05-tp-auto-deploy-dp() {
  local recipe_file="05-tp-auto-deploy-dp.yaml"

  # Check if the recipe file exists
  if [[ ! -f "${recipe_file}" ]]; then
    echo "Recipe file ${recipe_file} does not exist. Exiting."
    return
  fi

  # Define a space-separated list of environment variables
  local env_var env_vars="GITHUB_TOKEN TP_AUTO_ACTIVE_USER"

  for env_var in $env_vars; do
    local field="GUI_$env_var"

    # Check if the environment variable is set
    if [[ -n "${!env_var}" ]]; then
      echo "Updating recipe: ${recipe_file}, ${field}=${!env_var}"
      yq eval ".meta.guiEnv.${field} = env(${env_var})" -i "${recipe_file}"
    fi
  done
}

# Check if yq is installed
check_yq() {
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
}

# main function
function main() {
  check_yq
  select_recipe_source "$@"
}

main "$@"
