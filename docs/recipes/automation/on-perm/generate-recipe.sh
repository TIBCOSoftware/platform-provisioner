#!/bin/bash

#
# © 2024 Cloud Software Group, Inc.
# All Rights Reserved. Confidential & Proprietary.
#

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
          read -rp "What provisioner-config-local version do you want to use? (Press Enter to use latest): " PIPELINE_CHART_VERSION_PROVISIONER_CONFIG_LOCAL
            # generate from public release
          export PIPELINE_CHART_VERSION_PROVISIONER_CONFIG_LOCAL=${PIPELINE_CHART_VERSION_PROVISIONER_CONFIG_LOCAL:-"^1.0.0"}
          _data=$(helm template provisioner-config-local provisioner-config-local --repo https://tibcosoftware.github.io/platform-provisioner --version "${PIPELINE_CHART_VERSION_PROVISIONER_CONFIG_LOCAL}")
          generate_recipe "${_data}" "${choice2}"
          break
          ;;
        2)
          # generate from local
          _data=$(helm template provisioner-config-local "../../../../charts/provisioner-config-local")
          generate_recipe "${_data}" "${choice2}"
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
      echo "4. Exit"
      read -rp "Enter your choice (1-4): " choice2
    fi

    case $choice2 in
      1)
        echo "${_data}" | yq eval .data | yq eval '.["pp-deploy-tp-base-on-prem-cert.yaml"]' | yq eval .recipe > 01-tp-on-perm.yaml
        echo "${_data}" | yq eval .data | yq eval '.["pp-deploy-cp-core-on-prem.yaml"]' | yq eval .recipe > 02-tp-cp-on-perm.yaml
        echo "${_data}" | yq eval .data | yq eval '.["pp-maintain-tp-config-coredns.yaml"]' | yq eval .recipe > 03-tp-adjust-dns.yaml
        echo "${_data}" | yq eval .data | yq eval '.["pp-maintain-tp-remove-resource.yaml"]' | yq eval .recipe > 04-tp-adjust-resource.yaml
        echo "${_data}" | yq eval .data | yq eval '.["pp-maintain-tp-automation-o11y.yaml"]' | yq eval .recipe > 05-tp-auto-deploy-dp.yaml
        echo "${_data}" | yq eval .data | yq eval '.["pp-o11y-full.yaml"]' | yq eval .recipe > 06-tp-o11y-stack.yaml
        break
        ;;
      2)
        echo "${_data}" | yq eval .data | yq eval '.["pp-deploy-cp-core-on-prem.yaml"]' | yq eval .recipe > 02-tp-cp-on-perm.yaml
        break
        ;;
      3)
        echo "${_data}" | yq eval .data | yq eval '.["pp-maintain-tp-automation-o11y.yaml"]' | yq eval .recipe > 05-tp-auto-deploy-dp.yaml
        break
        ;;
      4)
        echo "Exiting..."
        break
        ;;
      *)
        echo "Invalid option. Please try again."
        ;;
    esac
  done
}

# main function
function main() {
  select_recipe_source "$@"
}

main "$@"
