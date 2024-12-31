#!/bin/bash

#
# © 2024 Cloud Software Group, Inc.
# All Rights Reserved. Confidential & Proprietary.
#

# This script will generate the recipe for deploying TP on-prem
function generate_recipe() {
  local _data=""
  while true; do
    echo "Please select an option:"
    echo "1. Use public repo to generate recipe"
    echo "2. Use local repo to generate recipe"
    echo "3. Exit"
    read -rp "Enter your choice (1-3): " choice

    case $choice in
        1)
          read -rp "What provisioner-config-local version do you want to use? (Press Enter to use latest): " PIPELINE_CHART_VERSION_PROVISIONER_CONFIG_LOCAL
            # generate from public release
          export PIPELINE_CHART_VERSION_PROVISIONER_CONFIG_LOCAL=${PIPELINE_CHART_VERSION_PROVISIONER_CONFIG_LOCAL:-"^1.0.0"}
          _data=$(helm template provisioner-config-local provisioner-config-local --repo https://tibcosoftware.github.io/platform-provisioner --version ${PIPELINE_CHART_VERSION_PROVISIONER_CONFIG_LOCAL})
          break
          ;;
        2)
          # generate from local
          _data=$(helm template provisioner-config-local "../../../../charts/provisioner-config-local")
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

  echo "${_data}" | yq eval .data | yq eval '.["pp-deploy-tp-base-on-prem-cert.yaml"]' | yq eval .recipe > 01-tp-on-perm.yaml
  echo "${_data}" | yq eval .data | yq eval '.["pp-deploy-cp-core-on-prem.yaml"]' | yq eval .recipe > 02-tp-cp-on-perm.yaml
  echo "${_data}" | yq eval .data | yq eval '.["pp-maintain-tp-config-coredns.yaml"]' | yq eval .recipe > 03-tp-adjust-dns.yaml
  echo "${_data}" | yq eval .data | yq eval '.["pp-maintain-tp-remove-resource.yaml"]' | yq eval .recipe > 04-tp-adjust-resource.yaml
  echo "${_data}" | yq eval .data | yq eval '.["pp-maintain-tp-automation-o11y.yaml"]' | yq eval .recipe > 05-tp-auto-deploy-dp.yaml
}

# set_github_token sets the GitHub token for TP private repo
function set_github_token() {
  read -rp "Do you want to set a GitHub token for TP private repo? (Press Enter to skip): " GITHUB_TOKEN

  if [ -z "$GITHUB_TOKEN" ]; then
    echo "No GitHub token provided. Skipping..."
  else
    export GITHUB_TOKEN
    echo "Setting GitHub token..."
    yq eval -i '(.meta.guiEnv.GUI_CP_CHART_REPO_TOKEN = env(GITHUB_TOKEN)) |
      (.meta.guiEnv.GUI_DP_CHART_REPO_TOKEN = env(GITHUB_TOKEN))' 02-tp-cp-on-perm.yaml
    yq eval -i '(.meta.guiEnv.GUI_GITHUB_TOKEN = env(GITHUB_TOKEN))' 05-tp-auto-deploy-dp.yaml
  fi
}

# set_jfrog_token sets the JFrog token for CP private repo
function set_jfrog_token() {
  # Ask for JFrog variables one by one
  local _recipe="02-tp-cp-on-perm.yaml"
  read -rp "Enter JFrog Container Registry (Press Enter to skip): " GUI_CP_CONTAINER_REGISTRY
  if [ -n "$GUI_CP_CONTAINER_REGISTRY" ]; then
      export GUI_CP_CONTAINER_REGISTRY
      yq eval -i '(.meta.guiEnv.GUI_CP_CONTAINER_REGISTRY = env(GUI_CP_CONTAINER_REGISTRY))' "$_recipe"
  fi

  read -rp "Enter JFrog Container Registry Repository (Press Enter to skip): " GUI_CP_CONTAINER_REGISTRY_REPOSITORY
  if [ -n "$GUI_CP_CONTAINER_REGISTRY_REPOSITORY" ]; then
      export GUI_CP_CONTAINER_REGISTRY_REPOSITORY
      yq eval -i '(.meta.guiEnv.GUI_CP_CONTAINER_REGISTRY_REPOSITORY = env(GUI_CP_CONTAINER_REGISTRY_REPOSITORY))' "$_recipe"
  fi

  read -rp "Enter JFrog Container Registry Username (Press Enter to skip): " GUI_CP_CONTAINER_REGISTRY_USERNAME
  if [ -n "$GUI_CP_CONTAINER_REGISTRY_USERNAME" ]; then
      export GUI_CP_CONTAINER_REGISTRY_USERNAME
      yq eval -i '(.meta.guiEnv.GUI_CP_CONTAINER_REGISTRY_USERNAME = env(GUI_CP_CONTAINER_REGISTRY_USERNAME))' "$_recipe"
  fi

  read -rp "Enter JFrog Container Registry Password (Press Enter to skip): " GUI_CP_CONTAINER_REGISTRY_PASSWORD
  if [ -n "$GUI_CP_CONTAINER_REGISTRY_PASSWORD" ]; then
      export GUI_CP_CONTAINER_REGISTRY_PASSWORD
      yq eval -i '(.meta.guiEnv.GUI_CP_CONTAINER_REGISTRY_PASSWORD = env(GUI_CP_CONTAINER_REGISTRY_PASSWORD))' "$_recipe"
  fi
}

# set_ssl_cert sets the SSL certificate for TP
function set_ssl_cert() {
  # Ask for SSL cert variables one by one
  local _recipe="01-tp-on-perm.yaml"
  read -rp "Enter SSL Certificate (Press Enter to skip): " GUI_TP_TLS_CERT
  if [ -n "$GUI_TP_TLS_CERT" ]; then
      export GUI_TP_TLS_CERT
      yq eval -i '(.meta.guiEnv.GUI_TP_TLS_CERT = env(GUI_TP_TLS_CERT))' "$_recipe"
  fi

  read -rp "Enter SSL Certificate Key (Press Enter to skip): " GUI_TP_TLS_KEY
  if [ -n "$GUI_TP_TLS_KEY" ]; then
      export GUI_TP_TLS_KEY
      yq eval -i '(.meta.guiEnv.GUI_TP_TLS_KEY = env(GUI_TP_TLS_KEY))' "$_recipe"
  fi
}

# main function
function main() {
  generate_recipe
  set_github_token
  set_ssl_cert
  set_jfrog_token
}

main
