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
# retry count
export TP_SUBSCRIPTION_DEPLOY_RETRY_COUNT=${TP_SUBSCRIPTION_DEPLOY_RETRY_COUNT:-10}

export PIPELINE_DOCKER_IMAGE_RUNNER=${PIPELINE_DOCKER_IMAGE_RUNNER:-"ghcr.io/tibcosoftware/platform-provisioner/platform-provisioner:latest"}
export PIPELINE_DOCKER_IMAGE_TESTER=${PIPELINE_DOCKER_IMAGE_TESTER:-"ghcr.io/tibcosoftware/platform-provisioner/platform-provisioner:v1.0.0-tester"}

export CURRENT_PATH=$(pwd)
export _PIPELINE_PUBLIC_SCRIPT='/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/TIBCOSoftware/platform-provisioner/main/dev/platform-provisioner.sh)"'
export PIPELINE_SCRIPT="${PIPELINE_SCRIPT:-${_PIPELINE_PUBLIC_SCRIPT}}"

if [[ "${IS_LOCAL_AUTOMATION}" = "true" ]]; then
  PIPELINE_SCRIPT="$(realpath "../../../../dev/platform-provisioner.sh")"
  echo "Using local automation script: ${PIPELINE_SCRIPT}"
  export PIPELINE_CONTAINER_OPTIONAL_PARAMETER="-v $(realpath '../tp-setup/bootstrap/'):/tmp/auto"
fi

# deploy-on-prem-base deploys base on-prem
function deploy-on-prem-base() {
  local _recipe_file_name="01-tp-on-perm.yaml"
  if [[ ! -f "${CURRENT_PATH}/${_recipe_file_name}" ]]; then
    echo "Recipe file ${_recipe_file_name} not found."
    return 1
  fi
  export PIPELINE_NAME=helm-install
  export PIPELINE_DOCKER_IMAGE="${PIPELINE_DOCKER_IMAGE_RUNNER}"
  export PIPELINE_INPUT_RECIPE="${CURRENT_PATH}/${_recipe_file_name}"
  bash -c "${PIPELINE_SCRIPT}"
}

# deploy-tp deploys CP on-prem
function deploy-tp() {
  local _recipe_file_name="02-tp-cp-on-perm.yaml"
  if [[ ! -f "${CURRENT_PATH}/${_recipe_file_name}" ]]; then
    echo "Recipe file ${_recipe_file_name} not found."
    return 1
  fi
  export PIPELINE_NAME=helm-install
  export PIPELINE_DOCKER_IMAGE="${PIPELINE_DOCKER_IMAGE_RUNNER}"
  export PIPELINE_INPUT_RECIPE="${CURRENT_PATH}/${_recipe_file_name}"
  bash -c "${PIPELINE_SCRIPT}"
}

# post-deploy-adjust-dns adjusts DNS
function post-deploy-adjust-dns(){
  local _recipe_file_name="03-tp-adjust-dns.yaml"
  if [[ ! -f "${CURRENT_PATH}/${_recipe_file_name}" ]]; then
    echo "Recipe file ${_recipe_file_name} not found."
    return 1
  fi
  export PIPELINE_NAME=generic-runner
  export PIPELINE_DOCKER_IMAGE="${PIPELINE_DOCKER_IMAGE_RUNNER}"
  export PIPELINE_INPUT_RECIPE="${CURRENT_PATH}/${_recipe_file_name}"
  bash -c "${PIPELINE_SCRIPT}"
}

# post-deploy-cleanup-resource cleans up resources
function post-deploy-cleanup-resource(){
  local _recipe_file_name="04-tp-adjust-resource.yaml"
  if [[ ! -f "${CURRENT_PATH}/${_recipe_file_name}" ]]; then
    echo "Recipe file ${_recipe_file_name} not found."
    return 1
  fi
  export PIPELINE_NAME=generic-runner
  export PIPELINE_DOCKER_IMAGE="${PIPELINE_DOCKER_IMAGE_RUNNER}"
  export PIPELINE_INPUT_RECIPE="${CURRENT_PATH}/${_recipe_file_name}"
  bash -c "${PIPELINE_SCRIPT}"
}

# deploy-subscription deploys CP subscription
function deploy-subscription() {
  local _recipe_file_name="05-tp-auto-deploy-dp.yaml"
  if [[ ! -f "${CURRENT_PATH}/${_recipe_file_name}" ]]; then
    echo "Recipe file ${_recipe_file_name} not found."
    return 1
  fi
  export PIPELINE_NAME=generic-runner
  export PIPELINE_DOCKER_IMAGE="${PIPELINE_DOCKER_IMAGE_TESTER}"
  export PIPELINE_INPUT_RECIPE="${CURRENT_PATH}/${_recipe_file_name}"
  bash -c "${PIPELINE_SCRIPT}"
}

# deploy O11Y stack
function deploy-tp-o11y-stack() {
  local _recipe_file_name="06-tp-o11y-stack.yaml"
  if [[ ! -f "${CURRENT_PATH}/${_recipe_file_name}" ]]; then
    echo "Recipe file ${_recipe_file_name} not found."
    return 1
  fi
  export PIPELINE_NAME=helm-install
  export PIPELINE_DOCKER_IMAGE="${PIPELINE_DOCKER_IMAGE_RUNNER}"
  export PIPELINE_INPUT_RECIPE="${CURRENT_PATH}/${_recipe_file_name}"
  bash -c "${PIPELINE_SCRIPT}"
}

# redeploy O11Y stack
function redeploy-tp-o11y-stack() {
  helm delete -n elastic-system dp-config-es
  deploy-tp-o11y-stack
}

# deploy-tp-o11y-resource deploys TP o11y resources # 6
function deploy-tp-o11y-resource() {
  local _recipe_file_name="05-tp-auto-deploy-dp.yaml"
  if [[ ! -f "${CURRENT_PATH}/${_recipe_file_name}" ]]; then
    echo "Recipe file ${_recipe_file_name} not found."
    return 1
  fi
  # change GUI_TP_AUTO_IS_CONFIG_O11Y to true to config TP o11y
  _old=$(yq '.meta.guiEnv.GUI_TP_AUTO_IS_CONFIG_O11Y' 05-tp-auto-deploy-dp.yaml)
  export GUI_TP_AUTO_IS_CONFIG_O11Y=true
  yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_IS_CONFIG_O11Y = env(GUI_TP_AUTO_IS_CONFIG_O11Y))' 05-tp-auto-deploy-dp.yaml
  export PIPELINE_NAME=generic-runner
  export PIPELINE_DOCKER_IMAGE="${PIPELINE_DOCKER_IMAGE_TESTER}"
  export PIPELINE_INPUT_RECIPE="${CURRENT_PATH}/${_recipe_file_name}"
  bash -c "${PIPELINE_SCRIPT}"
  # set GUI_TP_AUTO_IS_CONFIG_O11Y back
  export GUI_TP_AUTO_IS_CONFIG_O11Y=${_old}
  yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_IS_CONFIG_O11Y = env(GUI_TP_AUTO_IS_CONFIG_O11Y))' 05-tp-auto-deploy-dp.yaml
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

if [[ $# -gt 0 ]]; then
  choice=$1
fi
while true; do
  if [[ -z $choice ]]; then
    echo "Please select an option:"
    echo "1. Deploy TP from scratch. (All steps: 2,5,7,3,7,4,6)"
    echo "2. Prepare TP cluster (Ingress, DB, storage, etc.)"
    echo "3. Deploy platform-bootstrap and platform-base only"
    echo "4. Deploy CP subscription (Admin, sub user, DP, app, etc.)"
    echo "5. Deploy o11y stack (Elastic, Prometheus, OTel Collector, etc.)"
    echo "6. Deploy TP o11y resources (Config, o11y, etc.)"
    echo "7. Cleanup resource (Remove resource limits, etc.)"
    echo "8. Undeploy o11y stack then Redeploy o11y stack (dp-config-es-es-default-0 pod is pending)"
    echo "9. Exit"
    read -rp "Enter your choice (1-8): " choice
  fi

  case $choice in
    1)
      echo "Deploying TP from scratch..."
      start_time=$(date +%s)
      deploy-on-prem-base # 2
      deploy-tp-o11y-stack # 5
      post-deploy-cleanup-resource # 7
      echo "Wait for 30 seconds before deploying CP..."
      sleep 30
      deploy-tp # 3
      echo "Finish deploy TP in $(($(date +%s) - start_time)) seconds"
      post-deploy-adjust-dns # dns adjustment
      post-deploy-cleanup-resource # 7

      echo "Wait for 30 seconds before deploying CP subscription..."
      sleep 30

      # run with retry for # 4
      run-with-retry deploy-subscription "${TP_SUBSCRIPTION_DEPLOY_RETRY_COUNT}"

      deploy-tp-o11y-resource # 6

      end_time=$(date +%s)
      total_time=$((end_time - start_time))
      echo "Total execution time: ${total_time} seconds"
      break
      ;;
    2)
      echo "Prepare TP cluster..."
      deploy-on-prem-base
      break
      ;;
    3)
      echo "Deploying platform-bootstrap and platform-base..."
      deploy-tp
      break
      ;;
    4)
      echo "Deploying CP subscription..."
      echo "Run with $PIPELINE_SCRIPT with retry count $TP_SUBSCRIPTION_DEPLOY_RETRY_COUNT"
      run-with-retry deploy-subscription "${TP_SUBSCRIPTION_DEPLOY_RETRY_COUNT}"
      break
      ;;
    5)
      echo "Deploying o11y stack..."
      deploy-tp-o11y-stack
      break
      ;;
    6)
      echo "Deploying TP o11y resources..."
      deploy-tp-o11y-resource
      break
      ;;
    7)
      echo "Cleaning up resources..."
      post-deploy-cleanup-resource
      break
      ;;
    8)
      echo "Undeploy o11y stack then Redeploy o11y stack..."
      redeploy-tp-o11y-stack
      break
      ;;
    9)
      echo "Exiting..."
      break
      ;;
    *)
      echo "Invalid option. Please try again."
      ;;
  esac
done
