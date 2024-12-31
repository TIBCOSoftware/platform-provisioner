#!/bin/bash

#
# © 2024 Cloud Software Group, Inc.
# All Rights Reserved. Confidential & Proprietary.
#

# run with local platform-provisioner.sh script with export PIPELINE_SCRIPT=../../../../dev/platform-provisioner.sh

export PIPELINE_ON_PREM_KUBECONFIG_FILE_NAME=config
# don't print debug log
export PIPELINE_LOG_DEBUG=false
# don't print recipe
export PIPELINE_RECIPE_PRINT=false

export CURRENT_PATH=$(pwd)
export _PIPELINE_PUBLIC_SCRIPT='/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/TIBCOSoftware/platform-provisioner/main/dev/platform-provisioner.sh)"'
export PIPELINE_SCRIPT=${PIPELINE_SCRIPT:-${_PIPELINE_PUBLIC_SCRIPT}}

# deploy-on-prem-base deploys base on-prem
function deploy-on-prem-base() {
  export PIPELINE_NAME=helm-install
  export PIPELINE_INPUT_RECIPE="${CURRENT_PATH}/01-tp-on-perm.yaml" && \
  bash -c "${PIPELINE_SCRIPT}"
}

# deploy-tp deploys CP on-prem
function deploy-tp() {
  export PIPELINE_NAME=helm-install
  export PIPELINE_INPUT_RECIPE="${CURRENT_PATH}/02-tp-cp-on-perm.yaml" && \
  bash -c "${PIPELINE_SCRIPT}"
}

# post-deploy-cleanup-resource cleans up resources
function post-deploy-cleanup-resource(){
  export PIPELINE_NAME=generic-runner
  export PIPELINE_INPUT_RECIPE="${CURRENT_PATH}/04-tp-adjust-resource.yaml" && \
  bash -c "${PIPELINE_SCRIPT}"
}

# post-deploy-adjust-dns adjusts DNS
function post-deploy-adjust-dns(){
  export PIPELINE_NAME=generic-runner
  export PIPELINE_INPUT_RECIPE="${CURRENT_PATH}/03-tp-adjust-dns.yaml" && \
  bash -c "${PIPELINE_SCRIPT}"
}

# deploy-subscription deploys CP subscription
function deploy-subscription() {
  export PIPELINE_NAME=generic-runner
  export PIPELINE_DOCKER_IMAGE="ghcr.io/tibcosoftware/platform-provisioner/platform-provisioner:v1.0.0-tester"
  export PIPELINE_INPUT_RECIPE="${CURRENT_PATH}/05-tp-auto-deploy-dp.yaml" && \
  bash -c "${PIPELINE_SCRIPT}"
}

# run-with-retry runs a command with retries
function run-with-retry() {
  local _cmd=$1
  local _max_retries=$2

  local attempt=0
  local success=false

  while (( attempt < _max_retries )); do
    ((attempt++))
    echo "Attempt $attempt of $_max_retries..."
    if $_cmd; then
      echo "${_cmd} succeeded on attempt $attempt."
      success=true
      break
    else
      echo "${_cmd} failed on attempt $attempt. Retrying in 10 seconds..."
    fi
    sleep 10  # Optional: Add a delay between retries
  done

  if [ "$success" = true ]; then
    echo "${_cmd} completed successfully."
  else
    echo "${_cmd} failed after $_max_retries attempts."
    return 1
  fi
}

while true; do
  echo "Please select an option:"
  echo "1. Deploy TP from scratch"
  echo "2. Deploy platform-bootstrap and platform-base only"
  echo "3. Deploy CP subscription"
  echo "4. Cleanup resource"
  echo "5. Exit"
  read -rp "Enter your choice (1-5): " choice

  case $choice in
    1)
      echo "Deploying TP from scratch..."
      start_time=$(date +%s)
      deploy-on-prem-base
      deploy-tp
      echo "Finish deploy TP in $(($(date +%s) - start_time)) seconds"
      post-deploy-adjust-dns
      post-deploy-cleanup-resource
      # run with retry
      run-with-retry deploy-subscription 5
      end_time=$(date +%s)
      total_time=$((end_time - start_time))
      echo "Total execution time: ${total_time} seconds"
      break
      ;;
    2)
      echo "Deploying platform-bootstrap and platform-base..."
      deploy-tp
      break
      ;;
    3)
      echo "Deploying CP subscription..."
      echo "Run with $PIPELINE_SCRIPT"
      deploy-subscription
      break
      ;;
    4)
      echo "Cleaning up resources..."
      post-deploy-cleanup-resource
      break
      ;;
    5)
      echo "Exiting..."
      break
      ;;
    *)
      echo "Invalid option. Please try again."
      ;;
  esac
done
