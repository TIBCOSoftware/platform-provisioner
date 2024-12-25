#!/bin/bash

#
# Copyright (c) 2019 - 2024 TIBCO Software Inc.
# All Rights Reserved. Confidential & Proprietary.
#

#######################################
# generic-runner::setup_repo this will clone repo and copy files to current folder
# Globals:
#   None
# Arguments:
#   _repo_section: the repo section in recipe
# Returns:
#   0 if thing was deleted, non-zero on error
# Notes:
#   None
# Samples:
#   repo:
#     git:
#       github:
#         repo: github.com/TIBCOSoftware/tp-helm-charts
#         path: charts/dp-config-es
#         branch: master  # optional, branch or tag name, the default is main
#         hash: xxxxxx    # optional, default value is empty and will not get from hash
#         token: ${GITHUB_TOKEN} # the token used to for GitHub
#######################################
function generic-runner::setup_repo() {
  local _repo_section=${1}
  if [ -z "${_repo_section}" ]; then
    common::debug "no repo part detected, skipping repo setup"
    return 0
  fi

  local _repo_github_section=""
  _repo_github_section=$(echo "${_repo_section}" | common::yq4-get .git)

  if ! common::recipe_github_clone "${_repo_github_section}" "."; then
    common::err "error: common::recipe_github_clone return none 0: ${_res}"
    return 1
  fi
}

#######################################
# generic-runner::setup_payload this will cat payload in recipe as a files
# Globals:
#   None
# Arguments:
#   _payload_section: the payload section in recipe
# Returns:
#   0 if thing was deleted, non-zero on error
# Notes:
#   None
# Samples:
#   payload: # optional, the whole payload section is optional
#     base64Encoded: false
#     fileName: recipe.yaml # optional, if not specified the default payload file name is recipe.yaml
#     content: |
#       anything: applies
#######################################
function generic-runner::setup_payload() {
  local _payload_section=${1}
  if [ -z "${_payload_section}" ]; then
    common::debug "no payload part detected, skipping payload setup"
    return 0
  fi

  local _payload_filename=""
  _payload_filename=$(echo "${_payload_section}" | common::yq4-get .fileName)
  _payload_filename="${_payload_filename:-recipe.yaml}"

  local _base64_encoded=""
  _base64_encoded=$(echo "${_payload_section}" | common::yq4-get .base64Encoded)
  if [[ ${_base64_encoded} == "true" ]]; then
    common::debug "use base64 to decode script"
    if ! echo "${_payload_section}" | common::yq4-get .content | base64 -d > "${_payload_filename}"; then
      common::err "error: generic-runner::setup_payload base64 -d return none 0"
      return 1
    fi
  else
    echo "${_payload_section}" | common::yq4-get .content > "${_payload_filename}"
  fi
}

#######################################
# generic-runner::setup_script this will cat script in recipe as a files
# Globals:
#   PIPELINE_RUNNER_SCRIPT_NAME_SH: the default script file name
# Arguments:
#   _script_section: the payload section in recipe
# Returns:
#   0 if thing was deleted, non-zero on error
# Notes:
#   script section is optional. if not set; we will check if env PIPELINE_RUNNER_SCRIPT_NAME_SH is set. If that is set; will run scritp with that name. If not set; will run script.sh
#   The content section on the script section is optional. If set; we will use fileName to create the file with the content. 
#   If there is already a file with the same name; we will report error. Because either the same file is copied from repo or the file is created by pipeline. 
#   If the content section is not set; we will use the fileName to run the script.
# Samples:
#   script:
#     ignoreErrors: true # only when set to true the task script error will be skipped
#     base64Encoded: false # only when set to true to decode content as base64
#     skip: false   # only when set to true to skip this task
#     fileName: abc.sh # optional, if not specified the default script file name is script.sh
#     content: |
#       echo "hihi task 0"
#######################################
function generic-runner::setup_script() {
  local _script_section=${1}
  local _default_script_file_name="script.sh"

  # the script section is optional
  # if set; then we setup it
  # if not set; then we check if env PIPELINE_RUNNER_SCRIPT_NAME_SH is set
  # PIPELINE_RUNNER_SCRIPT_NAME_SH is set and file exist; then we use it
  # PIPELINE_RUNNER_SCRIPT_NAME_SH is NOT set; then we use script.sh as default
  if [[ -z "${_script_section}" ]]; then
    common::debug "no script part detected"
    if [[ -n "${PIPELINE_RUNNER_SCRIPT_NAME_SH}" ]]; then
      common::debug "detect PIPELINE_RUNNER_SCRIPT_NAME_SH is set to ${PIPELINE_RUNNER_SCRIPT_NAME_SH}"
      local _script_filename="${PIPELINE_RUNNER_SCRIPT_NAME_SH}"
      if [[ -f "${_script_filename}" ]]; then
        chmod u+x "${_script_filename}"
        return 0
      else
        common::err "detect env PIPELINE_RUNNER_SCRIPT_NAME_SH set but file ${_script_filename} does not exist"
        return 1
      fi
    else
      common::debug "detect PIPELINE_RUNNER_SCRIPT_NAME_SH is not set"
      if [[ -f "${_default_script_file_name}" ]]; then
        common::debug "detect file ${_default_script_file_name}; use it as default script file name"
        chmod u+x "${_default_script_file_name}"
        return 0
      else
        common::err "env PIPELINE_RUNNER_SCRIPT_NAME_SH is NOT set and default file ${_default_script_file_name} does not exist"
        return 1
      fi
      return 0
    fi
  fi

  common::debug "script part detected"

  local _script_filename=""
  _script_filename=$(echo "${_script_section}" | common::yq4-get .fileName)
  _script_filename="${_script_filename:-script.sh}"

  local _script_content=""
  _script_content=$(echo "${_script_section}" | common::yq4-get .content)

  # if we set content then we will use that content to run the script
  if [[ -n "${_script_content}" ]]; then
    common::debug "detect script[${_task_index}].content is set in recipe"
    if [[ -f "${_script_filename}" ]]; then
      common::err "detect script file ${_script_filename} already exist; you might not want to override it"
      return 1
    fi

    local _base64_encoded=""
    _base64_encoded=$(echo "${_script_section}" | common::yq4-get .base64Encoded)
    if [[ ${_base64_encoded} == "true" ]]; then
      common::debug "use base64 to decode script"
      if ! echo "${_script_content}" | base64 -d > "${_script_filename}"; then
        common::err "error: generic-runner::setup_script base64 -d return none 0"
        return 1
      fi
    else
      echo "${_script_content}" > "${_script_filename}"
    fi
  fi

  if [[ -f "${_script_filename}" ]]; then
    chmod u+x "${_script_filename}"
    return 0
  else
    common::err "detect script file ${_script_filename} does not exist"
    return 1
  fi
}

#######################################
# run_task actual logic to process each tasks
# Globals:
#   PIPELINE_RUNNER_SCRIPT_NAME_SH: the default script file name
# Arguments:
#   _task_index: the task index
#   _task_content: the task content
# Returns:
#   0 if thing was deleted, non-zero on error
# Notes:
#   None
# Samples:
#   tasks:
#   - repo: # optional, the whole repo section is optional
#       git:
#         github:
#           repo: github.com/TIBCOSoftware/tp-helm-charts
#           path: charts/dp-config-es
#           branch: master  # optional, branch or tag name, the default is main
#           hash: xxxxxx    # optional, default value is empty and will not get from hash
#           key: ${GITHUB_KEY} # the key used to for GitHub
#     clusters:     # the cluster name that the pipeline will be connected to
#     - name: <cluster01>
#     - name: <cluster02>
#     script:
#       ignoreErrors: true # only when set to true the task script error will be skipped
#       base64Encoded: false # only when set to true to decode content as base64
#       skip: false   # only when set to true to skip this task
#       fileName: abc.sh # optional, if not specified the default script file name is script.sh
#       content: |
#         echo "hihi task 0"
#         pwd
#         tree .
#     payload: # optional, the whole payload section is optional
#       base64Encoded: false
#       fileName: recipe.yaml # optional, if not specified the default payload file name is recipe.yaml
#       content: |
#         anything: applies
#######################################
function generic-runner::run_task() {
  local _task_index=${1}
  local _task_content=${2}
  common::info "running task #${_task_index}"

  local _task_script_section=""
  _task_script_section=$(echo "${_task_content}" | common::yq4-get '.script')
  local _task_repo_section=""
  _task_repo_section=$(echo "${_task_content}" | common::yq4-get '.repo')
  local _task_payload_section=""
  _task_payload_section=$(echo "${_task_content}" | common::yq4-get '.payload')
  local _task_clusters_section=""
  _task_clusters_section=$(echo "${_task_content}" | common::yq4-get '.clusters')

  # script.skip is used to skip the task. this is for backward compatibility.
  # Now we suggest to use condition to skip task
  local _script_skip=""
  _script_skip=$(echo "${_task_script_section}" | common::yq4-get '.skip')
  if [[ ${_script_skip} == "true" ]]; then
      common::info "detect skip for script[${_task_index}]; skipping"
      return 0
  fi

  local _task_ignore_error=""
  _task_ignore_error=$(echo "${_task_script_section}" | common::yq4-get '.ignoreErrors')

  # get default script file name
  local _task_file_name=""
  _task_file_name=$(echo "${_task_script_section}" | common::yq4-get '.fileName')
  if [[ -z "${_task_file_name}" ]]; then
    common::debug "detect script[${_task_index}].fileName is not set in recipe"
    if [[ -n "${PIPELINE_RUNNER_SCRIPT_NAME_SH}" ]]; then
      common::debug "detect PIPELINE_RUNNER_SCRIPT_NAME_SH is set to ${PIPELINE_RUNNER_SCRIPT_NAME_SH}"
      _task_file_name="${PIPELINE_RUNNER_SCRIPT_NAME_SH}"
    else
      common::debug "detect PIPELINE_RUNNER_SCRIPT_NAME_SH is not set"
      _task_file_name="script.sh"
    fi
  fi

  local _cluster_name_count=0
  _cluster_name_count=$(echo "${_task_clusters_section}" | yq4 '. | length')
  if [[ "${_cluster_name_count}" -eq 0 ]]; then
    common::debug "detect script[${_task_index}].clusters is not set in recipe"
    # we need to run the task no matter if we have cluster name or not
    _cluster_name_count=1
    local _cluster_name_none=true
  else
    common::debug "cluster name count is ${_cluster_name_count}"
  fi

  for (( cn=0; cn<_cluster_name_count; cn++ ))
  do
    if [[ "${_cluster_name_none}" != true ]]; then
      # this will be used for assume role
      CLUSTER_NAME=$(echo "${_task_clusters_section}" | yq4 ".[${cn}].name")
      common::debug "detect cluster name working on cluster: ${CLUSTER_NAME}"
    fi
    local _task_cluster_index=$cn

    # open a subprocess to install child
    (

    # create new folder
    local _task_tmp_folder="task"-"${_task_index}"-"${_task_cluster_index}"
    mkdir -p "${_task_tmp_folder}"
    cd "${_task_tmp_folder}" || exit

    # We do the repo first so we can override using the script and payload
    # setup repo files
    if ! generic-runner::setup_repo "${_task_repo_section}"; then
      common::err "error: setup repo return none 0: ${_res}"
      exit 1
    fi

    # setup payload
    if ! generic-runner::setup_payload "${_task_payload_section}"; then
      common::err "error: setup payload return none 0: ${_res}"
      exit 1
    fi

    # setup script
    if ! generic-runner::setup_script "${_task_script_section}"; then
      common::err "error: setup script return none 0: ${_res}"
      exit 1
    fi

    if [[ -f ./"${_task_file_name}" ]]; then
      if [[ -n ${CLUSTER_NAME} ]]; then
        common::debug "detect CLUSTER_NAME is set to ${CLUSTER_NAME}"
        if ! common::assume_role; then
          common::err "common::assume_role error"
          exit 1
        fi
      fi

      common::debug "============= running script ${_task_file_name} for task #${_task_index} ================="
      common::info "running task file ${_task_file_name} for task #${_task_index}"
      ./"${_task_file_name}"
      _res=$?
      if [[ "${_task_ignore_error}" == "true" ]] && [[ ${_res} -ne 0 ]]; then
        common::debug "Detect ignore error is true, skipping error: ${_res} for task #${_task_index}"
      fi
      if [[ "${_task_ignore_error}" != "true" ]] && [[ ${_res} -ne 0 ]]; then
        common::err "Run task #${_task_index} error"
        exit ${_res}
      fi
      common::debug "=========================== task #${_task_index} done ===================================="
    fi

    cd ..
    common::debug "clean up working folder: \"${_task_tmp_folder}\""
    rm -rf "${_task_tmp_folder}"
    )
    _res=$?
    if [ ${_res} -ne 0 ]; then
      common::err "error: sub shell return none 0: ${_res}"
      exit ${_res}
    fi
    ## reset CLUSTER_NAME
    if [[ "${_cluster_name_none}" != true ]]; then
      unset CLUSTER_NAME
    fi
  done
  unset _cluster_name_none
  common::info "finish task #${_task_index}"
}
