#!/bin/bash

#
# © 2025 Cloud Software Group, Inc.
# All Rights Reserved. Confidential & Proprietary.
#

export CURRENT_PATH=$(pwd)

# set_github_token sets the GitHub token for TP private repo
function set_github_token() {
  if [ -z "$GITHUB_TOKEN" ]; then
    read -rp "Do you want to set a GitHub token for TP private repo? (Press Enter to skip): " GITHUB_TOKEN
  fi

  if [ -z "$GITHUB_TOKEN" ]; then
    echo "No GitHub token provided. Skipping..."
  else
    export GITHUB_TOKEN
    echo "Setting GitHub token..."
    local _recipe_file_name="02-tp-cp-on-perm.yaml"
    if [[ -f "${CURRENT_PATH}/${_recipe_file_name}" ]]; then
      echo "Update GitHub token for ${_recipe_file_name}..."
      yq eval -i '(.meta.guiEnv.GUI_CP_CHART_REPO_TOKEN = env(GITHUB_TOKEN)) |
      (.meta.guiEnv.GUI_DP_CHART_REPO_TOKEN = env(GITHUB_TOKEN))' ${_recipe_file_name}
    fi
    local _recipe_file_name="05-tp-auto-deploy-dp.yaml"
    if [[ -f "${CURRENT_PATH}/${_recipe_file_name}" ]]; then
      echo "Update GitHub token for ${_recipe_file_name}..."
      yq eval -i '(.meta.guiEnv.GUI_GITHUB_TOKEN = env(GITHUB_TOKEN))' ${_recipe_file_name}
    fi
  fi
}

# set_jfrog_token sets the JFrog token for CP private repo
function set_jfrog_token() {
  # Ask for JFrog variables one by one
  local _recipe_file_name="02-tp-cp-on-perm.yaml"
  if [[ ! -f "${CURRENT_PATH}/${_recipe_file_name}" ]]; then
    echo "Recipe file ${_recipe_file_name} not found."
    return 0
  fi
  read -rp "Enter JFrog Container Registry (Press Enter to skip): " GUI_CP_CONTAINER_REGISTRY
  if [ -n "$GUI_CP_CONTAINER_REGISTRY" ]; then
    echo "Update GitHub token for ${_recipe_file_name}..."
    export GUI_CP_CONTAINER_REGISTRY
    yq eval -i '(.meta.guiEnv.GUI_CP_CONTAINER_REGISTRY = env(GUI_CP_CONTAINER_REGISTRY))' "$_recipe_file_name"
  fi

  read -rp "Enter JFrog Container Registry Repository (Press Enter to skip): " GUI_CP_CONTAINER_REGISTRY_REPOSITORY
  if [ -n "$GUI_CP_CONTAINER_REGISTRY_REPOSITORY" ]; then
    echo "Update GitHub token for ${_recipe_file_name}..."
    export GUI_CP_CONTAINER_REGISTRY_REPOSITORY
    yq eval -i '(.meta.guiEnv.GUI_CP_CONTAINER_REGISTRY_REPOSITORY = env(GUI_CP_CONTAINER_REGISTRY_REPOSITORY))' "$_recipe_file_name"
  fi

  read -rp "Enter JFrog Container Registry Username (Press Enter to skip): " GUI_CP_CONTAINER_REGISTRY_USERNAME
  if [ -n "$GUI_CP_CONTAINER_REGISTRY_USERNAME" ]; then
    echo "Update GitHub token for ${_recipe_file_name}..."
    export GUI_CP_CONTAINER_REGISTRY_USERNAME
    yq eval -i '(.meta.guiEnv.GUI_CP_CONTAINER_REGISTRY_USERNAME = env(GUI_CP_CONTAINER_REGISTRY_USERNAME))' "$_recipe_file_name"
  fi

  read -rp "Enter JFrog Container Registry Password (Press Enter to skip): " GUI_CP_CONTAINER_REGISTRY_PASSWORD
  if [ -n "$GUI_CP_CONTAINER_REGISTRY_PASSWORD" ]; then
    echo "Update GitHub token for ${_recipe_file_name}..."
    export GUI_CP_CONTAINER_REGISTRY_PASSWORD
    yq eval -i '(.meta.guiEnv.GUI_CP_CONTAINER_REGISTRY_PASSWORD = env(GUI_CP_CONTAINER_REGISTRY_PASSWORD))' "$_recipe_file_name"
  fi
}

# set_ssl_cert sets the SSL certificate for TP
function set_ssl_cert() {
  # Ask for SSL cert variables one by one
  local _recipe_file_name="01-tp-on-perm.yaml"
  if [[ ! -f "${CURRENT_PATH}/${_recipe_file_name}" ]]; then
    echo "Recipe file ${_recipe_file_name} not found."
    return 0
  fi

  read -rp "Enter SSL Certificate (Press Enter to skip): " GUI_TP_TLS_CERT
  if [ -n "$GUI_TP_TLS_CERT" ]; then
    echo "Update GitHub token for ${_recipe_file_name}..."
    export GUI_TP_TLS_CERT
    yq eval -i '(.meta.guiEnv.GUI_TP_TLS_CERT = env(GUI_TP_TLS_CERT))' "$_recipe_file_name"
  fi

  read -rp "Enter SSL Certificate Key (Press Enter to skip): " GUI_TP_TLS_KEY
  if [ -n "$GUI_TP_TLS_KEY" ]; then
    echo "Update GitHub token for ${_recipe_file_name}..."
    export GUI_TP_TLS_KEY
    yq eval -i '(.meta.guiEnv.GUI_TP_TLS_KEY = env(GUI_TP_TLS_KEY))' "$_recipe_file_name"
  fi
}

# main function
function main() {
  set_github_token
  set_ssl_cert
  set_jfrog_token
}

main "$@"
