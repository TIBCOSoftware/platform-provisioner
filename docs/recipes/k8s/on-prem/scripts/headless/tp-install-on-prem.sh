#!/bin/bash

#
# Copyright © 2025. Cloud Software Group, Inc.
# This file is subject to the license terms contained
# in the license file that is distributed with this file.
#

#######################################
# headless-tp-install-public.sh: this script will use docker to run the pipeline task
# Globals:
#   TP_TOP_DOMAIN: the top domain
#   TP_K8S_CLUSTER_TYPE_CODE: the k8s cluster type code. 1 for k3s, 2 for OpenShift, 3 for Docker Desktop (default), 4 for miniKube, 5 for kind, 6 for MicroK8s
#   TP_AUTOMATION_SCRIPT_OPTIONS: the automation script options. see: https://github.com/TIBCOSoftware/platform-provisioner/blob/main/docs/recipes/automation/on-prem/run.sh
#   GUI_TP_TLS_CERT: the SSL Certificate
#   GUI_TP_TLS_KEY: the SSL key
#   TP_AUTO_ENABLE_BWCE: the flag to enable BWCE default is true
# Arguments:
#   None
# Returns:
#   0 if thing was deleted, non-zero on error
# Notes:
#   This script will generate all TP recipes and customize them for public repo
# Samples:
#   ./headless-tp-install-public.sh
########################################

function customize-tp() {
  echo "Customize TP..."
  _recipe_file_name="01-tp-on-prem.yaml"
  export TP_TOP_DOMAIN=${TP_TOP_DOMAIN:-"localhost.dataplanes.pro"}
  yq eval -i '(.meta.guiEnv.GUI_TP_DNS_DOMAIN = env(TP_TOP_DOMAIN))' "$_recipe_file_name"

  _recipe_file_name="02-tp-cp-on-prem.yaml"
  yq eval -i '(.meta.guiEnv.GUI_TP_DNS_DOMAIN = env(TP_TOP_DOMAIN))' "$_recipe_file_name"
  # Enable BWCE by default for headless
  export TP_AUTO_ENABLE_BWCE=${TP_AUTO_ENABLE_BWCE:-"true"}
  yq eval -i '(.meta.guiEnv.GUI_CP_INSTALL_INTEGRATION_BWCE = env(TP_AUTO_ENABLE_BWCE))' "$_recipe_file_name"
  yq eval -i '(.meta.guiEnv.GUI_CP_INSTALL_INTEGRATION_BWCE_UTILITIES = env(TP_AUTO_ENABLE_BWCE))' "$_recipe_file_name"
  yq eval -i '(.meta.guiEnv.GUI_CP_INSTALL_INTEGRATION_BW5 = env(TP_AUTO_ENABLE_BWCE))' "$_recipe_file_name"

  # Update the platform version
  if [[ -n "$TP_PLATFORM_BOOTSTRAP_VERSION" ]]; then
    echo "Update the platform version to $TP_PLATFORM_BOOTSTRAP_VERSION"
    yq eval -i '(.meta.guiEnv.GUI_CP_PLATFORM_BOOTSTRAP_VERSION = env(TP_PLATFORM_BOOTSTRAP_VERSION))' "$_recipe_file_name"
  fi
  if [[ -n "$TP_PLATFORM_BASE_VERSION" ]]; then
    echo "Update the platform base version to $TP_PLATFORM_BASE_VERSION"
    yq eval -i '(.meta.guiEnv.GUI_CP_PLATFORM_BASE_VERSION = env(TP_PLATFORM_BASE_VERSION))' "$_recipe_file_name"
  fi

  _recipe_file_name="05-tp-auto-deploy-dp.yaml"
  yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_ENABLE_BWCE = env(TP_AUTO_ENABLE_BWCE))' "$_recipe_file_name"
}

function install-tp() {
  export GITHUB_BRANCH=${GITHUB_BRANCH:-"main"}
  export GITHUB_PATH="TIBCOSoftware/platform-provisioner/refs/heads/${GITHUB_BRANCH}/docs/recipes/automation/on-prem"

  curl -fsSL -o generate-recipe.sh https://raw.githubusercontent.com/${GITHUB_PATH}/generate-recipe.sh
  curl -fsSL -o adjust-recipe.sh https://raw.githubusercontent.com/${GITHUB_PATH}/adjust-recipe.sh
  curl -fsSL -o adjust-ingress.sh https://raw.githubusercontent.com/${GITHUB_PATH}/adjust-ingress.sh
  curl -fsSL -o update-recipe-tokens.sh https://raw.githubusercontent.com/${GITHUB_PATH}/update-recipe-tokens.sh
  curl -fsSL -o run.sh https://raw.githubusercontent.com/${GITHUB_PATH}/run.sh
  chmod u+x *.sh

  echo "Generate recipe from latest provisioner-config-local chart..."
  ./generate-recipe.sh 1 1

  export TP_K8S_CLUSTER_TYPE_CODE=${TP_K8S_CLUSTER_TYPE_CODE:-""} # 1 for k3s, 2 for OpenShift, 3 for Docker Desktop
  ./adjust-recipe.sh ${TP_K8S_CLUSTER_TYPE_CODE}

  export TP_K8S_INGRESS_TYPE_CODE=${TP_K8S_INGRESS_TYPE_CODE:-""} # 1 for nginx, 2 for traefik
  ./adjust-ingress.sh ${TP_K8S_INGRESS_TYPE_CODE}

  echo "Update recipe tokens..."
  ./update-recipe-tokens.sh

  customize-tp

  echo "Run the TP installation with headless mode..."
  export CURRENT_PATH=$(realpath .)
  mkdir -p ${CURRENT_PATH}/report
  export PIPELINE_CONTAINER_OPTIONAL_PARAMETER="-v /${CURRENT_PATH}/report:/tmp/auto/report"
  export TP_AUTOMATION_SCRIPT_OPTIONS=${TP_AUTOMATION_SCRIPT_OPTIONS:-""}
  export PIPELINE_DOCKER_IMAGE_RUNNER="ghcr.io/tibcosoftware/platform-provisioner/platform-provisioner:on-prem"
  export PIPELINE_DOCKER_IMAGE_TESTER="ghcr.io/tibcosoftware/platform-provisioner/platform-provisioner:tester-on-prem"
  ./run.sh ${TP_AUTOMATION_SCRIPT_OPTIONS}
}

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

function main() {
  check-yq
  install-tp
}

main "$@"