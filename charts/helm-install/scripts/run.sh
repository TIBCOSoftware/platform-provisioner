#!/bin/bash

#
# Copyright (c) 2019 - 2024 TIBCO Software Inc.
# All Rights Reserved. Confidential & Proprietary.
#

source _funcs_pipeline.sh

declare -xr AWS_ACCOUNT="${1}"
declare -xr AWS_REGION="${2}"
declare -xr INPUT=${3}

declare -xr WORKING_PATH="/workspace"
declare -xr RECIPE_FILE=recipe.yaml

# save input to recipe.yaml
function save_input() {
  echo "${INPUT}" | common::yq4-get . > "${RECIPE_FILE}"
  common::info "input recipe:"
  common::info "$(cat ${RECIPE_FILE})"
}

#######################################
# initial_assume_to_target_account will assume to target account. it will skip if PIPELINE_INITIAL_ASSUME_ROLE is false
# Before we run whatever script inside the pipeline, we need to assume to target account to avoid running inside provisioner account
# Sometime we know we will not assume to any account we run want to run some computation inside provisioner account. In this case, we can set PIPELINE_INITIAL_ASSUME_ROLE to false
# Globals:
#   PIPELINE_INITIAL_ASSUME_ROLE: true or other string if true, will initial assume to target account. if other string, will skip initial assume to target account
#   AWS_ACCOUNT: the aws account you want to assume to
#   AWS_REGION: the aws region
# Arguments:
#   None
# Returns:
#   0 if thing was deleted, non-zero on error
# Notes:
#   None
# Samples:
#   if ! initial_assume_to_target_account; then
#     common::err "initial_assume_to_target_account error"
#     return 1
#   fi
function initial_assume_to_target_account() {

  if [[ "${PIPELINE_INITIAL_ASSUME_ROLE}" == "false" ]]; then
    common::debug "detect PIPELINE_INITIAL_ASSUME_ROLE is false, skip initial assume to target account"
    return 0
  fi

  # assume to target account
  common::debug "input account: ${AWS_ACCOUNT}"
  common::debug "input region: ${AWS_REGION}"
  common::debug "now assume to target account"
  # Set the local CLUSTER_NAME as empty. The purpose of this initial_assume_to_target_account is to assume to target account.
  # We don't want to connect to any cluster at this point. This is the initial jump. We will use credentials from the target account to connect to the cluster
  if [[ -n ${CLUSTER_NAME} ]]; then
    CLUSTER_NAME=""
  fi
  if ! common::assume_role; then
    common::err "common::assume_role error"
    return 1
  fi
}

#######################################
# call_pipeline_script will actually run the pipeline script
# Globals:
#   RECIPE_FILE: the recipe file name
# Arguments:
#   None
# Returns:
#   0 if thing was deleted, non-zero on error
# Notes:
#   None
# Samples:
#   call_pipeline_script
function call_pipeline_script() {
  if ! process_recipe "${RECIPE_FILE}"; then
    common::err "process_recipe error"
    return 1
  fi
}

# the main function
function main() {
  common::debug "I am in main"
  if [[ -z "${INPUT}" ]]; then
    common::err "INPUT is empty"
    return 1
  fi

  common::debug "start of pipeline"

  # save input to recipe.yaml
  save_input

  # process meta part of recipe
  if ! common::process_meta "${INPUT}" "${RECIPE_FILE}"; then
    common::err "common::process_meta error"
    return 1
  fi

  common::debug "finish process_meta"
  # validate input after we process meta and replace all environment variables
  if ! common::validate_input "$(cat ${RECIPE_FILE})" check.cue; then
    return 1
  fi

  # skip call pipeline script if PIPELINE_MOCK is true
  if [[ "${PIPELINE_MOCK}" == "true" ]]; then
    common::info "detect PIPELINE_MOCK is true, skip call pipeline script"
    return 0
  fi

  # check docker status just before we run the actual pipeline script
#  if ! common::check_docker_status; then
#    common::err "check_docker_status error"
#    return 1
#  fi

  # initial assume to target account
  if ! initial_assume_to_target_account; then
    common::err "initial_assume_to_target_account error"
    return 1
  fi

  # actually run the pipeline script
  if ! call_pipeline_script; then
    common::err "call_pipeline_script error"
    return 1
  fi
}

# actual run the script
if ! main "$@"; then
  common::err "main error"
  exit 1
fi

common::info "end of pipeline"
