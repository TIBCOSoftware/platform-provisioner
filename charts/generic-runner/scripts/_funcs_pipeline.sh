#!/bin/bash

#
# Copyright (c) 2019 - 2024 TIBCO Software Inc.
# All Rights Reserved. Confidential & Proprietary.
#

#######################################
# run_task_helm actual logic to process each tasks
# Globals:
#   None
# Arguments:
#   _task_index: the task index
#   _task_content: the task content
# Returns:
#   0 if thing was deleted, non-zero on error
# Notes:
#   None
# Samples:
#   None
#######################################
function run_task_generic() {
  local _task_index=${1}
  local _task_content=${2}
  common::debug "running recipe task index #${_task_index}"
  common::debug "running recipe task content:"
  common::debug "${_task_content}"
  if ! generic-runner::run_task "${_task_index}" "${_task_content}"; then
    common::err "Run task #${_task_index} error"
    return 1
  fi
}

#######################################
# run_task_array loop through an array for a given root element
# Globals:
#   None
# Arguments:
#   _recipe_file: the input recipe
#   _recipe_root_name: the task root name eg: .tasks
#   _recipe_handle_func: the function to handle the task
# Returns:
#   0 if thing was deleted, non-zero on error
# Notes:
#   This function will loop through all tasks and run them one by one
#   If the task has condition, it will check the condition first
#   In case of generic-runner, we use .task as the root name. In case of helm-runner, we use .preTasks and .postTasks as the root name
# Samples:
#   run_task_array "${_recipe_file}" ".helmCharts" "run_task_helm"
#   run_task_array "${_recipe_file}" ".tasks" "run_task_generic"
#######################################
function run_task_array() {

  local _recipe_file=${1}
  local _recipe_root_name=${2}
  local _recipe_handle_func=${3}

  local _recipe_task_count=0
  _recipe_task_count=$(_yq_key=${_recipe_root_name} yq4 eval 'eval(env(_yq_key)) | length' "${_recipe_file}")
  if [[ "${_recipe_task_count}" -eq 0 ]]; then
    common::debug "skipping: task count for ${_recipe_root_name} is 0"
    retrun 0
  fi

  # loop through all tasks
  for (( cc=0; cc<_recipe_task_count; cc++ ))
  do
    local _recipe_task_index=$cc
    local _recipe_task_content=""

    # eg: _yq_key=".tasks[0]"
    _recipe_task_content=$(_yq_key="${_recipe_root_name}[${_recipe_task_index}]" yq4 eval "eval(env(_yq_key))" "${_recipe_file}")
    common::debug "working on task:"
    common::debug "${_recipe_task_content}"

    # for each of the task; check if it is empty
    if [[ -z "${_recipe_task_content}" ]]; then
      common::debug "task #${_recipe_task_index} content is empty"
      continue # skip empty task
    fi

    # for each of the task we will check condition first
    local _recipe_task_condition=""
    _recipe_task_condition=$(echo "${_recipe_task_content}" | common::yq4-get '.condition')
    common::debug "detect recipe task condition is: ${_recipe_task_condition}"
    [ -n "${_recipe_task_condition}" ] || _recipe_task_condition="true" # default is to run
    # skip the for loop if condition is not true
    [ "${_recipe_task_condition}" == "true" ] || { echo "Skipping task ${_recipe_task_index} as task condition is: ${_recipe_task_condition}"; continue; }

    # run the task
    if ! ${_recipe_handle_func} "${_recipe_task_index}" "${_recipe_task_content}"; then
      common::err "Run script error"
      retrun 1
    fi
  done
}

#######################################
# process_recipe The main function to process recipe
# Globals:
#   None
# Arguments:
#   _recipe: the input recipe
# Returns:
#   0 if thing was deleted, non-zero on error
# Notes:
#   A recipe might have multiple root element. eg: .preTasks, .helmCharts, .postTasks. This function intend to deal with root element
# Samples:
#   process_recipe "${RECIPE_FILE}"
#######################################
function process_recipe() {
  local _recipe_file=${1}

  local _funcs_business_logic="./_funcs_generic_runner.sh"
  if ! common::source_file "${_funcs_business_logic}"; then
    common::err "source file: ${_funcs_business_logic} error"
    return 1
  fi

  # process root tasks
  if ! run_task_array "${_recipe_file}" ".tasks" "run_task_generic"; then
    common::err "run_task_array .tasks error"
    return 1
  fi
}
