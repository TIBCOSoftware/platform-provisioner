#!/bin/bash

#
# © 2024 Cloud Software Group, Inc.
# All Rights Reserved. Confidential & Proprietary.
#

#######################################
# platform-provisioner-install.sh: this will deploy all supporting components for Platform Provisioner in headless mode with tekton pipeline
# Globals:
#   PIPELINE_GUI_DOCKER_IMAGE_REPO: the ECR repo to pull Platform Provisioner images
#   PIPELINE_GUI_DOCKER_IMAGE_USERNAME: the username for ECR to pull Platform Provisioner images
#   PIPELINE_GUI_DOCKER_IMAGE_TOKEN: the read-only token for ECR to pull Platform Provisioner images
#   PIPELINE_NAMESPACE: the namespace to deploy the pipeline and provisioner GUI
#   PLATFORM_PROVISIONER_PIPELINE_REPO: the repo to pull the pipeline and provisioner GUI helm charts
#   PIPELINE_DOCKER_IMAGE: the docker image for the pipeline
#   PIPELINE_SKIP_PROVISIONER_UI: true or other string if true, will skip installing platform-provisioner GUI
#   PIPELINE_SKIP_TEKTON_DASHBOARD: true or other string if true, will skip installing tekton dashboard
#   GITHUB_TOKEN: the token to access github that all pipeline can share
# Arguments:
#   None
# Returns:
#   0 if thing was deleted, non-zero on error
# Notes:
#   By default without any input, it will install tekton, common-dependency, generic-runner, helm-install pipelines
#   If we want to add tekton official dashboard, we can set PIPELINE_SKIP_TEKTON_DASHBOARD to false
#   If we want to add platform-provisioner GUI, we need to set PIPELINE_GUI_DOCKER_IMAGE_REPO, PIPELINE_GUI_DOCKER_IMAGE_USERNAME, PIPELINE_GUI_DOCKER_IMAGE_TOKEN
#      and set PIPELINE_SKIP_PROVISIONER_UI to false to install provisioner GUI
# Samples:
#    export PIPELINE_GUI_DOCKER_IMAGE_TOKEN="your-ecr-token"
#    export PIPELINE_GUI_DOCKER_IMAGE_REPO="your-ecr-repo"
#   ./platform-provisioner-install.sh
#######################################

[[ -z "${PIPELINE_DOCKER_IMAGE}" ]] && export PIPELINE_DOCKER_IMAGE=${PIPELINE_DOCKER_IMAGE:-"syantibco/platform-provisioner:latest"}
[[ -z "${PIPELINE_SKIP_PROVISIONER_UI}" ]] && export PIPELINE_SKIP_PROVISIONER_UI=${PIPELINE_SKIP_PROVISIONER_UI:-true}
[[ -z "${PIPELINE_SKIP_TEKTON_DASHBOARD}" ]] && export PIPELINE_SKIP_TEKTON_DASHBOARD=${PIPELINE_SKIP_TEKTON_DASHBOARD:-true}
[[ -z "${TEKTON_PIPELINE_RELEASE}" ]] && export TEKTON_PIPELINE_RELEASE=${TEKTON_PIPELINE_RELEASE:-"v0.59.0"}
[[ -z "${TEKTON_DASHBOARD_RELEASE}" ]] && export TEKTON_DASHBOARD_RELEASE=${TEKTON_DASHBOARD_RELEASE:-"v0.46.0"}

if [[ ${PIPELINE_SKIP_PROVISIONER_UI} == "false" ]]; then
  # your ECR read-only token
  if [[ -z ${PIPELINE_GUI_DOCKER_IMAGE_TOKEN} ]]; then
    echo "PIPELINE_GUI_DOCKER_IMAGE_TOKEN is not set"
    exit 1
  fi

  if [[ -z ${PIPELINE_GUI_DOCKER_IMAGE_REPO} ]]; then
    echo "PIPELINE_GUI_DOCKER_IMAGE_REPO is not set"
    exit 1
  fi
  [[ -z "${PIPELINE_GUI_DOCKER_IMAGE_USERNAME}" ]] && export PIPELINE_GUI_DOCKER_IMAGE_USERNAME=${PIPELINE_GUI_DOCKER_IMAGE_USERNAME:-"AWS"}
fi

# The tekton version to install
kubectl apply -f https://storage.googleapis.com/tekton-releases/pipeline/previous/${TEKTON_PIPELINE_RELEASE}/release.yaml
if [[ $? -ne 0 ]]; then
  echo "failed to install tekton pipeline"
  exit 1
fi

if [[ ${PIPELINE_SKIP_TEKTON_DASHBOARD} != "true" ]]; then
  echo "#### installing tekton dashboard"
  kubectl apply --filename https://storage.googleapis.com/tekton-releases/dashboard/previous/${TEKTON_DASHBOARD_RELEASE}/release.yaml
  if [[ $? -ne 0 ]]; then
    echo "failed to install tekton dashboard"
    exit 1
  fi
fi

kubectl create namespace tekton-tasks

function k8s-waitfor-deployment() {
  _deployment_namespace=$1
  _deployment_name=$2
  _timeout=$3
  echo "waiting for ${_deployment_name} in namespace: ${_deployment_namespace} to be ready..."
  kubectl wait --for=condition=available -n ${_deployment_namespace} "deployment/${_deployment_name}" --timeout=${_timeout}
  if [ $? -ne 0 ]; then
    echo "Timeout: Deployment '${_deployment_name}' did not become available within ${_timeout}."
    return 1
  else
    echo "Deployment '${_deployment_name}' is now ready."
  fi
}

k8s-waitfor-deployment "tekton-pipelines" "tekton-pipelines-controller" "120s"
k8s-waitfor-deployment "tekton-pipelines" "tekton-pipelines-webhook" "120s"

# create service account for this pipeline
kubectl create -n tekton-tasks serviceaccount pipeline-cluster-admin
kubectl create clusterrolebinding pipeline-cluster-admin --clusterrole=cluster-admin --serviceaccount=tekton-tasks:pipeline-cluster-admin

export PLATFORM_PROVISIONER_PIPELINE_REPO=${PLATFORM_PROVISIONER_PIPELINE_REPO:-"https://tibcosoftware.github.io/platform-provisioner"}
export PIPELINE_NAMESPACE=${PIPELINE_NAMESPACE:-"tekton-tasks"}

# install a sample pipeline with docker image that can run locally
helm upgrade --install -n "${PIPELINE_NAMESPACE}" common-dependency common-dependency \
  --version ^1.0.0 --repo "${PLATFORM_PROVISIONER_PIPELINE_REPO}" \
  --set githubToken="${GITHUB_TOKEN}"
if [[ $? -ne 0 ]]; then
  echo "failed to install common-dependency"
  exit 1
fi

helm upgrade --install -n "${PIPELINE_NAMESPACE}" generic-runner generic-runner \
  --version ^1.0.0 --repo "${PLATFORM_PROVISIONER_PIPELINE_REPO}" \
  --set serviceAccount=pipeline-cluster-admin \
  --set pipelineImage="${PIPELINE_DOCKER_IMAGE}"
if [[ $? -ne 0 ]]; then
  echo "failed to install generic-runner pipeline"
  exit 1
fi

helm upgrade --install -n "${PIPELINE_NAMESPACE}" helm-install helm-install \
  --version ^1.0.0 --repo "${PLATFORM_PROVISIONER_PIPELINE_REPO}" \
  --set serviceAccount=pipeline-cluster-admin \
  --set pipelineImage="${PIPELINE_DOCKER_IMAGE}"
if [[ $? -ne 0 ]]; then
  echo "failed to install helm-install pipeline"
  exit 1
fi

# create secret for pulling images from ECR
if [[ ${PIPELINE_SKIP_PROVISIONER_UI} == "true" ]]; then
  echo "### skip installing platform-provisioner GUI"
  exit 0
fi

# install provisioner config
helm upgrade --install -n "${PIPELINE_NAMESPACE}" provisioner-config-local provisioner-config-local \
  --version ^1.0.0 --repo "${PLATFORM_PROVISIONER_PIPELINE_REPO}"
if [[ $? -ne 0 ]]; then
  echo "failed to install provisioner-config-local"
  exit 1
fi

_image_pull_secret_name="platform-provisioner-ui-image-pull"
if kubectl get secret -n "${PIPELINE_NAMESPACE}" ${_image_pull_secret_name} > /dev/null 2>&1; then
  kubectl delete secret -n "${PIPELINE_NAMESPACE}" ${_image_pull_secret_name}
fi
kubectl create secret docker-registry -n "${PIPELINE_NAMESPACE}" ${_image_pull_secret_name} \
  --docker-server="${PIPELINE_GUI_DOCKER_IMAGE_REPO}" \
  --docker-username="${PIPELINE_GUI_DOCKER_IMAGE_USERNAME}" \
  --docker-password="${PIPELINE_GUI_DOCKER_IMAGE_TOKEN}"
if [[ $? -ne 0 ]]; then
  echo "failed to create image pull secret"
  exit 1
fi

# install provisioner web ui
helm upgrade --install -n "${PIPELINE_NAMESPACE}" platform-provisioner-ui platform-provisioner-ui --repo "${PLATFORM_PROVISIONER_PIPELINE_REPO}" \
  --version ^1.0.0 \
  --set image.repository="${PIPELINE_GUI_DOCKER_IMAGE_REPO}"/stratosphere/cic2-provisioner-webui \
  --set image.tag=latest \
  --set "imagePullSecrets[0].name=${_image_pull_secret_name}" \
  --set guiConfig.onPremMode=true \
  --set guiConfig.pipelinesCleanUpEnabled=true \
  --set guiConfig.dataConfigMapName="provisioner-config-local-config"
if [[ $? -ne 0 ]]; then
  echo "failed to install platform-provisioner-ui"
  exit 1
fi

k8s-waitfor-deployment "${PIPELINE_NAMESPACE}" "platform-provisioner-ui" "300s"
