#!/bin/bash

#
# © 2024 Cloud Software Group, Inc.
# All Rights Reserved. Confidential & Proprietary.
#

#######################################
# platform-provisioner-pipelinerun.sh: this script will submit a pipelinerun to tekton.
# Globals:
#   PIPELINE_INPUT_RECIPE: the input file name; default is recipe.yaml
#   PIPELINE_NAME:  We currently support 2 pipelines: generic-runner and helm-install
#   ACCOUNT: the account you want to assume to
#   REGION: the region
#   PIPELINE_SERVICE_ACCOUNT_NAME: the service account name for the pipeline to use
# Arguments:
#   None
# Returns:
#   0 if thing was deleted, non-zero on error
# Notes:
#   None
# Samples:
#   ./platform-provisioner-pipelinerun.sh
#######################################

[[ -z "${PIPELINE_INPUT_RECIPE}" ]] && export PIPELINE_INPUT_RECIPE="recipe.yaml"
[[ -z "${PIPELINE_NAME}" ]] && export PIPELINE_NAME="generic-runner"
[[ -z "${PIPELINE_SERVICE_ACCOUNT_NAME}" ]] && export PIPELINE_SERVICE_ACCOUNT_NAME="pipeline-cluster-admin"

# we need to set REGION, otherwise the INPUT will not be loaded
[[ -z "${ACCOUNT}" ]] && export ACCOUNT="on-prem"
[[ -z "${REGION}" ]] && export REGION="us-west-2"

if [[ ! -f "${PIPELINE_INPUT_RECIPE}" ]]; then
    echo "file ${PIPELINE_INPUT_RECIPE} does not exist"
    exit 1
fi

# Accept the integer input from the user
recipe_template='
apiVersion: tekton.dev/v1beta1
kind: PipelineRun
metadata:
  labels:
    argocd.argoproj.io/instance: "${pipeline_name}"
    env.cloud.tibco.com/account: "${account}"
    env.cloud.tibco.com/action: pipeline
    env.cloud.tibco.com/created-by: ${user_name}
    env.cloud.tibco.com/name: "${pipeline_name}"
    tekton.dev/pipeline: "${pipeline_name}"
  name: ${pipeline_name}-${account}-${random_number}
  namespace: tekton-tasks
spec:
  params:
    - name: input
      value: |
${pipeline_recipe}
        createdBy:
          email: ${user_name}@cloud.com
    - name: awsAccount
      value: "${account}"
    - name: awsRegion
      value: "${region}"
  pipelineRef:
    name: "${pipeline_name}"
  serviceAccountName: ${pipeline_service_account_name}
  timeouts:
    finally: 5m0s
    pipeline: 2h0m0s
    tasks: 1h55m0s
'

# If yq is installed; we can get pipeline name from PIPELINE_INPUT_RECIPE
if command -v yq >/dev/null 2>&1; then
  pipeline_name=$(cat "${PIPELINE_INPUT_RECIPE}" | yq ".kind | select(. != null)" )
else
  echo "yq is not installed, please consider install yq to automatically get pipeline name from input recipe"
  echo "otherwise, please set the pipeline name in the environment variable PIPELINE_NAME as generic-runner or helm-install"
fi

pipeline_name=${pipeline_name:-${PIPELINE_NAME}}
pipeline_recipe=$(cat ${PIPELINE_INPUT_RECIPE} | sed 's/^/        /')
pipeline_service_account_name=${PIPELINE_SERVICE_ACCOUNT_NAME}

# Set the account and region
account=${ACCOUNT}
region=${REGION}

# Set the user name
user_name="admin"

# Generate a random number
random_number=$((RANDOM % 100))

export account region pipeline_service_account_name user_name random_number pipeline_name pipeline_recipe
keys='$account, $region, $pipeline_service_account_name $user_name, $random_number, $pipeline_name, $pipeline_recipe'

recipe_replaced=$(envsubst "${keys}" <<< "${recipe_template}")
echo "create tekton ${pipeline_name} pipelinerun ${account}-${random_number} for ${user_name}"
#echo "${recipe_replaced}"
if ! kubectl apply -f <(echo "${recipe_replaced}"); then
    echo "kubectl apply error"
    exit 1
fi
