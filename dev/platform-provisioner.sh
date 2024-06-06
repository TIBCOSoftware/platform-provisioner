#!/bin/bash

#
# © 2022 - 2024 Cloud Software Group, Inc.
# All Rights Reserved. Confidential & Proprietary.
#

#######################################
# platform-provisioner.sh: this script will use docker to run the pipeline task
# Globals:
#   ACCOUNT: the account you want to assume to
#   REGION: the region
#   AWS_PROFILE: the aws profile; we normally needs to do AWS sso login to update this profile
#   GITHUB_TOKEN: the github token
#   PIPELINE_NAME:  We currently support 2 pipelines: generic-runner and helm-install
#   PIPELINE_TRIGGER_RUN_SH: true or other string if true, will run task directly. if other string, will just go to bash
#   PIPELINE_INPUT_RECIPE: the input file name; default is recipe.yaml
#   PIPELINE_MOCK: true or other string if true, will mock run pipeline. (only run meta part)
#   PIPELINE_LOG_DEBUG: true or other string if true, will print pipeline debug log
#   PIPELINE_VALIDATE_INPUT: true or other string if true, will validate input against cue schema
#   PIPELINE_CHECK_DOCKER_STATUS: true only when set to false to skip check docker status
#   PIPELINE_INITIAL_ASSUME_ROLE: true only when set to false to skip initial assume to target account
#   PIPELINE_USE_LOCAL_CREDS: false only when set to true to use local creds
#   PIPELINE_FUNCTION_INIT: true only when set to false to skip function init which is used to load TIBCO specific functions and envs for pipeline
#   PIPELINE_AWS_MANAGED_ACCOUNT_ROLE: the role to assume to. We will use current AWS role to assume to this role to perform the task. current role --> "arn:aws:iam::${_account}:role/${PIPELINE_AWS_MANAGED_ACCOUNT_ROLE}"
# Arguments:
#   TASK_NAME: We currently support 2 pipelines: generic-runner and helm-install
# Returns:
#   0 if thing was deleted, non-zero on error
# Notes:
#   The script will try to read recipe.yaml file and use .kind as pipeline name to pull the current pipeline from TIBCO public repo.
#   Pipeline image can be build in docker folder.
#   Recipe: can be found in TIBCO public repo: https://github.com/TIBCOSoftware/tp-helm-charts
#   Docker run command: It will mount necessary folder and bring environment variables to the container.
#                       It will also run the command defined in all pipeline task.
#                       It will also run the task if PIPELINE_TRIGGER_RUN_SH is set to true.
# Samples:
#   ./platform-provisioner.sh
#######################################

set +x

# pipeline image
[[ -z "${PIPELINE_DOCKER_IMAGE}" ]] && export PIPELINE_DOCKER_IMAGE=${PIPELINE_DOCKER_IMAGE:-"syantibco/platform-provisioner:latest"}
[[ -z "${PIPELINE_CHART_REPO}" ]] && export PIPELINE_CHART_REPO="tibcosoftware.github.io/platform-provisioner"

# we need to set REGION, otherwise the INPUT will not be loaded
[[ -z "${ACCOUNT}" ]] && export ACCOUNT="on-prem"
[[ -z "${REGION}" ]] && export REGION="us-west-2"

# default network is host
[[ -z "${PIPELINE_CONTAINER_NETWORK}" ]] && export PIPELINE_CONTAINER_NETWORK="host"

[[ -z "${PIPELINE_INPUT_RECIPE}" ]] && export PIPELINE_INPUT_RECIPE="recipe.yaml"
[[ -z "${PIPELINE_TRIGGER_RUN_SH}" ]] && export PIPELINE_TRIGGER_RUN_SH="true"
[[ -z "${PIPELINE_LOG_DEBUG}" ]] && export PIPELINE_LOG_DEBUG="true"
# For local test; we enable this flag by default
[[ -z "${PIPELINE_USE_LOCAL_CREDS}" ]] && export PIPELINE_USE_LOCAL_CREDS="true"
# For this script; we need to skip check docker status. The docker compose should set to true
[[ -z "${PIPELINE_MOCK}" ]] && export PIPELINE_MOCK="false"
[[ -z "${PIPELINE_CHECK_DOCKER_STATUS}" ]] && export PIPELINE_CHECK_DOCKER_STATUS="false"
# we don't want to initial assume role for local run
[[ -z "${PIPELINE_INITIAL_ASSUME_ROLE}" ]] && export PIPELINE_INITIAL_ASSUME_ROLE="false"
[[ -z "${PIPELINE_VALIDATE_INPUT}" ]] && export PIPELINE_VALIDATE_INPUT="true"

# by default we want to use on prem kubeconfig file
# This case is to use the default kubeconfig file. The default kubeconfig file is ~/.kube/config.
# We will mount this file to the container and rename to config-on-prem to avoid conflict with container kubeconfig file
[[ -z "${PIPELINE_ON_PREM_KUBECONFIG}" ]] && export PIPELINE_ON_PREM_KUBECONFIG="true"

# this case is used for on prem cluster; user will specify kubeconfig file name
if [[ -z "${PIPELINE_ON_PREM_KUBECONFIG_FILE_NAME}" ]]; then
  export DOCKER_MOUNT_KUBECONFIG_FILE_NAME="target=/tmp1"
else
  export DOCKER_MOUNT_KUBECONFIG_FILE_NAME="type=bind,source=${HOME}/.kube/${PIPELINE_ON_PREM_KUBECONFIG_FILE_NAME},target=/root/.kube/${PIPELINE_ON_PREM_KUBECONFIG_FILE_NAME}"
fi

# this is used for k8s on docker for mac
if [[ "${PIPELINE_ON_PREM_DOCKER_FOR_MAC}" == "true" ]]; then
  DOCKER_FOR_MAC_NODE_IP=$(kubectl get nodes -o yaml | yq '.items[].status.addresses[] | select(.type == "InternalIP") | .address')
  export DOCKER_FOR_MAC_ADD_HOST="--add-host=kubernetes.docker.internal:${DOCKER_FOR_MAC_NODE_IP}"
else
  export DOCKER_FOR_MAC_ADD_HOST="--add-host=kubernetes.docker.internal:127.0.0.1"
fi

# will only pass the content of the recipe file to the container
export PIPLINE_INPUT_RECIPE_CONTENT=""
[[ -f "${PIPELINE_INPUT_RECIPE}" ]] && PIPLINE_INPUT_RECIPE_CONTENT=$(cat ${PIPELINE_INPUT_RECIPE})

echo "Using platform provisioner docker image: ${PIPELINE_DOCKER_IMAGE}"

# is used to export functions; so subshell can use it
docker run -it --rm \
  --name provisioner-pipeline-task \
  --net ${PIPELINE_CONTAINER_NETWORK} \
  -e ACCOUNT \
  -e REGION \
  -e AWS_PROFILE \
  -e AWS_ACCESS_KEY_ID \
  -e AWS_SECRET_ACCESS_KEY \
  -e AWS_SESSION_TOKEN \
  -e GITHUB_TOKEN \
  -e PIPELINE_TRIGGER_RUN_SH \
  -e PIPELINE_INPUT_RECIPE \
  -e PIPLINE_INPUT_RECIPE_CONTENT \
  -e PIPELINE_MOCK \
  -e PIPELINE_LOG_DEBUG \
  -e PIPELINE_CHECK_DOCKER_STATUS \
  -e PIPELINE_INITIAL_ASSUME_ROLE \
  -e PIPELINE_USE_LOCAL_CREDS \
  -e PIPELINE_FUNCTION_INIT \
  -e PIPELINE_VALIDATE_INPUT \
  -e PIPELINE_ON_PREM_KUBECONFIG \
  -e PIPELINE_ON_PREM_KUBECONFIG_FILE_NAME \
  -e PIPELINE_AWS_MANAGED_ACCOUNT_ROLE \
  -e PIPELINE_CHART_REPO \
  -e PIPELINE_NAME \
  -v "${HOME}"/.aws:/root/.aws \
  -v "${HOME}"/.azure:/root/.azure \
  -v "${HOME}"/.kube/config:/root/.kube/config-on-prem \
  --mount "${DOCKER_MOUNT_KUBECONFIG_FILE_NAME}" \
  "${DOCKER_FOR_MAC_ADD_HOST}" \
  -v "${HOME}"/.docker:/root/.docker -v /var/run/docker.sock:/var/run/docker.sock \
  "${PIPELINE_DOCKER_IMAGE}" bash -c 'export REGION=${REGION:-"us-west-2"} \
  && declare -xr WORKING_PATH=/workspace \
  && declare -xr SCRIPTS=${WORKING_PATH}/task-scripts \
  && declare -xr INPUT="${PIPLINE_INPUT_RECIPE_CONTENT}" \
  && [[ -z ${PIPELINE_NAME} ]] && export PIPELINE_NAME=$(echo "${PIPLINE_INPUT_RECIPE_CONTENT}" | yq ".kind | select(. != null)" ) \
  && echo "using pipeline: ${PIPELINE_NAME}" \
  && [[ -z ${PIPELINE_NAME} ]] && { echo "PIPELINE_NAME can not be empty"; exit 1; } || true \
  && mkdir -p "${SCRIPTS}" \
  && helm pull --untar --untardir /tmp --version ^1.0.0 --repo https://${PIPELINE_CHART_REPO} common-dependency \
  && cp -LR /tmp/common-dependency/scripts/* "${SCRIPTS}" \
  && helm pull --untar --untardir /tmp --version ^1.0.0 --repo https://${PIPELINE_CHART_REPO} ${PIPELINE_NAME} \
  && cp -LR /tmp/${PIPELINE_NAME}/scripts/* "${SCRIPTS}" \
  && chmod +x "${SCRIPTS}"/*.sh \
  && cd "${SCRIPTS}" \
  && set -a && . _functions.sh && set +a \
  && [[ -z ${ACCOUNT} ]] && { echo "ACCOUNT can not be empty"; exit 1; } || true \
  && [[ "${PIPELINE_TRIGGER_RUN_SH}" == "true" ]] && ./run.sh ${ACCOUNT} ${REGION} "${INPUT}" || bash'
