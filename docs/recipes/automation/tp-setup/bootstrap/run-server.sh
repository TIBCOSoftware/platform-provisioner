#!/bin/bash

#
# Copyright © 2025. Cloud Software Group, Inc.
# This file is subject to the license terms contained
# in the license file that is distributed with this file.
#
current_dir=$(pwd)
if [[ "$(uname -s)" =~ MINGW ]]; then
  current_dir=$(pwd -W)
fi

export PIPELINE_INPUT_RECIPE=server-recipe.yaml
export PIPELINE_DOCKER_IMAGE="ghcr.io/tibcosoftware/platform-provisioner/platform-provisioner:1.6.0-tester-on-prem-jammy"

export PIPELINE_CONTAINER_OPTIONAL_PARAMETER="-v ${current_dir}:/tmp/auto"
export PIPELINE_CONTAINER_RUN_NAME="automation"
export PIPELINE_FAIL_STAY_IN_CONTAINER="true"

if [[ "${TP_AUTO_REMOTE_INSTANCE}" == "true" ]]; then
  # private key file location
  export PEM_FILE="${PEM_FILE:-""}"
  # remote instance IP address
  export REMOTE_IP="${REMOTE_IP:-""}"

  export PIPELINE_CONTAINER_OPTIONAL_PARAMETER="${PIPELINE_CONTAINER_OPTIONAL_PARAMETER} -v ${current_dir}/../../on-prem:/tmp/on-prem -v ${PEM_FILE}:/tmp/keys/key.pem"
  _recipe_file_name="server-recipe.yaml"
  yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_REMOTE_INSTANCE = true)' "$_recipe_file_name"
  yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_REMOTE_INSTANCE_IP = env(REMOTE_IP))' "$_recipe_file_name"
  yq eval -i '(.meta.globalEnvVariable.PIPELINE_ON_PREM_KUBECONFIG = ~/.kube/config)' "$_recipe_file_name"
fi

/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/TIBCOSoftware/platform-provisioner/main/dev/platform-provisioner.sh)"
