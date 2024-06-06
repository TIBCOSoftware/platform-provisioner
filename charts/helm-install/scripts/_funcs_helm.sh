#!/bin/bash

#
# Copyright (c) 2019 - 2024 TIBCO Software Inc.
# All Rights Reserved. Confidential & Proprietary.
#

######################################### _download_funcs.sh #########################################

# download_public_helm_chart download chart from a given repo, The url must contain https:// as protocol
# this is used for the following recipe
#- name: ingress-nginx # chart name
#  version: 4.0.5 # chart version
#  repo:
#    helm:
#      url: https://kubernetes.github.io/ingress-nginx
# sample helm pull --repo https://kubernetes.github.io/ingress-nginx ingress-nginx --version 4.0.3
function download_public_helm_chart() {
  local _url=${1}
  local _name=${2}
  local _version=${3}
  common::debug "downloading chart ${_name} form ${_url} with version ${_version}"

  if ! "${HELM_COMMAND_LINE}" pull --repo "${_url}" "${_name}" --version "${_version}"; then
    common::err "${HELM_COMMAND_LINE} pull error"
    return 1
  fi
}

# ecr_login login to a given ECR
function ecr_login() {
  local _ecr_region=${1}
  local _ecr_registry=${2}

  if [ -z "${_ecr_registry}" ]; then
    common::err "ECR registry host is empty"
    return 1
  fi

  if [ -z "${_ecr_region}" ]; then
    _ecr_region=us-west-2
  fi

  # ECR login
  export HELM_EXPERIMENTAL_OCI=1
  common::debug "login to ECR: ${_ecr_registry}"
  aws ecr get-login-password --region ${_ecr_region} | \
  "${HELM_COMMAND_LINE}" registry login -u AWS --password-stdin "${_ecr_registry}"
  _res=$?
  if [ ${_res} -ne 0 ]; then
    common::err "ECR login error"
    return ${_res}
  fi
}

# download chart FROM ${_tenant_ecr_host_repo}/${_tenant_chart_repo}:${_tenant_version} and save to _dest_folder
# this is used for
#- name: <chart name># chart name
#  version: aws-dev # In case of ECR this is image tag
#  repo:
#    ecr: # ${repo.ecr.host}/${repo.ecr.name}:${version}
#      name: troposphere/tsc-top-level-chart # repository name
#      region: us-west-2 # helm will use this region to login to
#      host: xxxx.dkr.ecr.us-west-2.amazonaws.com
# input
# 1,2,3: ${_tenant_ecr_host_repo}/${_tenant_chart_repo}:${_tenant_version}
# 3: tenant chart name like <chart name>.tgz <tenant-chart-name>-<version>.tgz. so we use ${_tenant_chart_name}-*.tgz
# 4: destination folder
function pull_ecr_chart() {
  local _tenant_ecr_region=${1}
  local _tenant_ecr_host_repo=${2}
  local _tenant_chart_repo=${3}
  local _tenant_version=${4}
  local _tenant_chart_name=${5}
  local _dest_folder=${6}

  if ! ecr_login "${_tenant_ecr_region}" "${_tenant_ecr_host_repo}"; then
    common::err "ECR login error"
    return 1
  fi

  if [ -z "${_tenant_ecr_host_repo}" ]; then
    common::err "ECR registry host is empty"
    return 1
  fi

  local _helm_ver=""
  _helm_ver=$(${HELM_COMMAND_LINE} version --short)

  common::debug "pull chart from ECR using ${_helm_ver}"
  if ! ${HELM_COMMAND_LINE} pull "oci://${_tenant_ecr_host_repo}/${_tenant_chart_repo}" --version "${_tenant_version}"; then
    common::err "chart ${_tenant_ecr_host_repo}/${_tenant_chart_repo}:${_tenant_version} pull error"
    return 1
  fi

  if [ -n "${_dest_folder}" ] && [ "${_dest_folder}" != '.' ]; then
    if [ -d "${_dest_folder}" ]; then
      if [ -f ${_tenant_chart_name}-*.tgz ]; then
        common::debug "move to ${_dest_folder}"
        mv ${_tenant_chart_name}-*.tgz ${_dest_folder}
      fi
    fi
  fi
}

# pull_github_chart download chart from github
function pull_github_chart() {
  local _repo=${1}
  local _branch_name=${2}
  local _git_folder=git_remote
  local _git_path=${3}
  local _git_hash=${4}

  if ! common::git_clone "${_repo}" "${_branch_name}" "${_git_folder}" "${_git_hash}"; then
    common::err "git clone error"
    return 1
  fi

  if [ ! -d "${_git_folder}"/"${_git_path}" ]; then
    common::err "can not find chart folder in: ${_git_folder}/${_git_path}"
    return 1
  fi

  # chart might have dependency reference to other charts. we need to update them
  # this will only apply to install helm chart from source directly. The chart museum will not have this issue. It will have all dependency chart in the same folder
  if ! helmDepUp "${_git_folder}"/"${_git_path}"; then
    common::err "helm dependency update error"
    return 1
  fi

  if ! "${HELM_COMMAND_LINE}" package "${_git_folder}"/"${_git_path}"; then
    common::err "helm package error"
    return 1
  fi
}

# downloadChart this will download chart
function downloadChart() {
  local _repo_section=${1}
  local _chart_name=${2}
  local _chart_version=${3}

  local _chart_repo_helm=""
  _chart_repo_helm=$(echo "${_repo_section}" | common::yq4-get '.helm')
  local _chart_repo_ecr=""
  _chart_repo_ecr=$(echo "${_repo_section}" | common::yq4-get '.ecr')
  local _chart_git_ecr=""
  _chart_git_ecr=$(echo "${_repo_section}" | common::yq4-get '.git')
  if [[ -n ${_chart_repo_helm} ]]; then
    download_public_helm_chart "$(echo "${_chart_repo_helm}" | common::yq4-get '.url')" "${_chart_name}" "${_chart_version}"
    _res=$?
    if [ ${_res} -ne 0 ]; then
      common::err "download public helm chart error"
      return ${_res}
    fi
  fi

  if [[ -n ${_chart_repo_ecr} ]]; then
    pull_ecr_chart "$(echo "${_chart_repo_ecr}" | common::yq4-get '.region')" "$(echo "${_chart_repo_ecr}" | common::yq4-get '.host')" "$(echo "${_chart_repo_ecr}" | common::yq4-get '.name')" "${_chart_version}" "${_chart_name}" "."
    _res=$?
    if [ ${_res} -ne 0 ]; then
      common::err "pull ECR error"
      return ${_res}
    fi
  fi

  if [[ -n ${_chart_git_ecr} ]]; then
    pull_github_chart "$(echo "${_chart_git_ecr}" | common::yq4-get '.github'.repo)" "${_chart_version}" "$(echo "${_chart_git_ecr}" | common::yq4-get '.github.path')" "$(echo "${_chart_git_ecr}" | common::yq4-get '.github.hash')"
    _res=$?
    if [ ${_res} -ne 0 ]; then
      common::err "pull from git error"
      return ${_res}
    fi
  fi

  common::debug "downloaded chart: "
  common::debug "$(ls -al)"
}

######################################### _values_funcs.sh #########################################

function yq-get-data() {
  local data="$1"

  if [[ $(which yq) == "" ]]; then
    >&2 common::err "Please install yq utility."
    exit 1
  fi

  echo "${data}" | common::yq4-get '.data'
}

# getCurrentValues will generate values-current.yaml
function getCurrentValues() {
  local _chart_values_section=${1}
  local _chart_release_name=${2}
  local _chart_namespace=${3}

  local _chartFileName=values-current.yaml

  local _keep_previous=""
  _keep_previous=$(echo "${_chart_values_section}" | common::yq4-get '.keepPrevious')
  if [ "${_keep_previous}" != "true" ]; then
    common::debug "skipping previous chart values"
    return
  fi
  common::debug "keepPrevious is set to true and try to get previous release chart values"
  echo "" > ${_chartFileName}
  echo -n "--values ${_chartFileName} " >> "${HELM_VALUES_FLAG_FILE}"
  "${HELM_COMMAND_LINE}" get values -n "${_chart_namespace}" "${_chart_release_name}" -o yaml 2> /dev/null > ${_chartFileName}
}


# yq-get-data will get data from a given configmap
function kube-get-data() {
  local _chart_namespace="$1"
  local _data="$2"
  local _cfg=""
  _cfg=$(kubectl get configmap -n "${_chart_namespace}" "${_data}" -o yaml 2>/dev/null)
  _res=$?
  if [ ${_res} -ne 0 ]; then
    # no such configmap return empty string
    echo ""
  else
    # return configmap
    echo "${_cfg}"
  fi
}

# getRecipeValues this will generate values-recipe.yaml for the data that we have in recipe
function getRecipeValues() {
  local _chart_values_section=${1}
  local _chartFileName=values-recipe.yaml
  echo "" > ${_chartFileName}
  echo -n "--values ${_chartFileName} " >> "${HELM_VALUES_FLAG_FILE}"

  local _base64=""
  _base64=$(echo "${_chart_values_section}" | common::yq4-get '.base64Encoded')
  if [[ ${_base64} == "true" ]]; then
    common::debug "use base64 to decode values"
    echo "${_chart_values_section}" | common::yq4-get '.content' | base64 -D > ${_chartFileName}
  else
    echo "${_chart_values_section}" | common::yq4-get '.content' > ${_chartFileName}
  fi
}

# getValues will generate values.yaml and values flag files
function getValues() {
  local _chart_values_section=${1}
  local _chart_release_name=${2}
  local _chart_namespace=${3}

  if [ -z "${_chart_values_section}" ]; then
    common::debug "no values part skipping set any values"
    return
  fi

  getCurrentValues "${_chart_values_section}" "${_chart_release_name}" "${_chart_namespace}"

  getRecipeValues "${_chart_values_section}"
}

# getHelmVersion match helm version based on helmCharts[].helmSettings.version
function getHelmVersion() {
  local _helm_version=${1}
  [ "${_helm_version}" != "default" ] || _helm_version=''
  local _helm_cmd="helm"
  if [ -n "${_helm_version}" ]; then
      _helm_cmd=$(which helm-${_helm_version})
      [ -n "${_helm_cmd}" ] || _helm_cmd=$(which helm-v${_helm_version}) # TODO: back-compatibility, can remove later
  fi
  [ -n "${_helm_cmd}" ] || { >&2 common::err "Error obtaining Helm command for recipe-supplied Helm version (${_helm_version})."; return 1; }
  echo -n "${_helm_cmd}"
}

######################################### _install_funcs.sh #########################################

# getLocalChartName get the actual chart tgz file that need to be installed
function getLocalChartName() {
  local _chart_name=${1}
  # we have case like cert-manager-v1.11.2.tgz
  local _pattern="${_chart_name}-*[0-9]*.tgz"

  fileCount=$(find . -maxdepth 1 -name "${_pattern}" | wc -l)
  if [[ ${fileCount} -ne 1 ]]; then
    common::err "unexpected chart tgz file find under current folder. Only exactly 1 tgz is expected. pattern is ${_chart_name}-*[0-9]*.tgz"
    common::err "Found:"
    common::err "$(ls ./*.tgz)"
    return 1
  fi

  local_chart_name=$(eval echo "${_pattern}")
  echo "${local_chart_name}"
}

#######################################
# process_chart_flags this will handle chart flags
# Globals:
#   None
# Arguments:
#   _chart_name: the name of the chart
#   _chart_namespace: the namespace of the chart
#   _chart_flags_section: the flags section of the chart
#   _install_cmd_file: the file name that will be used to store the helm install command
#   _values_flag: the values flag that will be used to store the helm install command
# Returns:
#   0 if thing was deleted, non-zero on error
# Notes:
#   The flag section is defined as below:
# 	flags?: {
# 		debug?: "true" | "false" | true | false | *false
# 		wait?: "true" | "false" | true | false | *true
# 		timeout?: string | *"10m"
# 		labels?: string
# 		dryRun?: "true" | "false" | true | false | *false
# 		noHooks?: "true" | "false" | true | false | *false
# 		createNamespace?: "true" | "false" | true | false | *false
# 		force?: "true" | "false" | true | false | *false
# 		compare?: "true" | "false" | true | false | *false
# 		skip?: "true" | "false" | true | false | *false
# 		extra?: string
# 	}
# Samples:
#   process_chart_flags "${_chart_name}" "${_chart_namespace}" "${_chart_flags_section}" "${_install_cmd_file}"
#######################################
function process_chart_flags() {
  local _chart_name=${1}
  local _chart_namespace=${2}
  local _chart_flags_section=${3}
  local _install_cmd_file=${4}
  local _values_flag=${5}

  # start of helm command
  echo -n "${HELM_COMMAND_LINE} " > "${_install_cmd_file}"

  local _chart_debug=""
  _chart_debug=$(echo "${_chart_flags_section}" | common::yq4-get '.debug')
  if [ "${_chart_debug}" = "true" ]; then
    echo -n "--debug " >> "${_install_cmd_file}"
  fi

  echo -n "upgrade --install " >> "${_install_cmd_file}"
  if [ -n "${_chart_namespace}" ]; then
    echo -n "-n ${_chart_namespace} " >> "${_install_cmd_file}"
  fi

  local _chart_wait=""
  _chart_wait=$(echo "${_chart_flags_section}" | common::yq4-get '.wait')
  if [ "${_chart_wait}" = "true" ] || [ -z "${_chart_wait}" ]; then
    echo -n "--wait " >> "${_install_cmd_file}"
  fi

  local _chart_timeout=""
  _chart_timeout=$(echo "${_chart_flags_section}" | common::yq4-get '.timeout')
  if [ -n "${_chart_timeout}" ]; then
    echo -n "--timeout ${_chart_timeout} " >> "${_install_cmd_file}"
  fi

  local _chart_label_flags=""
  _chart_label_flags=$(echo "${_chart_flags_section}" | common::yq4-get '.labels')
  if [ -n "${_chart_label_flags}" ]; then
    echo -n "--labels ${_chart_label_flags} " >> "${_install_cmd_file}"
    # echo -n "--labels " >> "${_install_cmd_file}"
  fi

  local _chart_dryrun=""
  _chart_dryrun=$(echo "${_chart_flags_section}" | common::yq4-get '.dryRun')
  if [ "${_chart_dryrun}" = "true" ]; then
    echo -n "--dry-run " >> "${_install_cmd_file}"
  fi

  local _chart_nohooks=""
  _chart_nohooks=$(echo "${_chart_flags_section}" | common::yq4-get '.noHooks')
  if [ "${_chart_nohooks}" = "true" ]; then
    echo -n "--no-hooks " >> "${_install_cmd_file}"
  fi

  local _chart_create_ns=""
  _chart_create_ns=$(echo "${_chart_flags_section}" | common::yq4-get '.createNamespace')
  if [ "${_chart_create_ns}" = "true" ]; then
    echo -n "--create-namespace " >> "${_install_cmd_file}"
  fi

  local _chart_force=""
  _chart_force=$(echo "${_chart_flags_section}" | common::yq4-get '.force')
  if [ "${_chart_force}" = "true" ]; then
    echo -n "--force " >> "${_install_cmd_file}"
  fi

  echo -n "${_chart_release_name} " >> "${_install_cmd_file}"

  local _chart_name_tgz
  _chart_name_tgz=$(getLocalChartName "${_chart_name}")
  _res=$?
  if [ ${_res} -ne 0 ]; then
    common::err "get chart tgz error"
    return ${_res}
  fi
  echo -n "${_chart_name_tgz} " >> "${_install_cmd_file}"

  # add values flags
  echo -n "${_values_flag} " >> ${_install_cmd_file}

  # extera flags as last one to be able to override any flags
  local _extra_flag=""
  _extra_flag=$(echo "${_chart_flags_section}" | common::yq4-get '.extra')
  if [ -n "${_extra_flag}" ]; then
    echo -n "${_extra_flag} " >> "${_install_cmd_file}"
  fi

  common::debug "helm install command after processing flag:$(cat "${_install_cmd_file}")"
}

#######################################
# installChart will generate installation script and run helm install
# Globals:
#   None
# Arguments:
#   _chart_name: the name of the chart
#   _chart_namespace: the namespace of the chart
#   _chart_release_name: the release name of the chart
#   _chart_flags_section: the flags section of the chart
#   _values_flag: the values flag that will be used to store the helm install command
# Returns:
#   0 if thing was deleted, non-zero on error
# Notes:
#   None
# Samples:
#   installChart "${_chart_name}" "${_chart_namespace}" "${_chart_release_name}" "${_chart_flags_section}" "${_values_flag}"
#######################################
function installChart() {
  local _chart_name=${1}
  local _chart_namespace=${2}
  local _chart_release_name=${3}
  local _chart_flags_section=${4}
  local _values_flag=${5}

  local _chart_skip=""
  _chart_skip=$(echo "${_chart_flags_section}" | common::yq4-get '.skip')
  if [ "${_chart_skip}" = "true" ]; then
    common::debug "detect skip flag is set to true. skip install chart: ${_chart_name}"
    return 0
  fi

  local _install_cmd_file=chart-install-cmd.txt

  process_chart_flags "${_chart_name}" "${_chart_namespace}" "${_chart_flags_section}" "${_install_cmd_file}" "${_values_flag}"

  common::info "########## helm command that will run: ############"
  local _helm_cmd=""
  _helm_cmd=$(cat ${_install_cmd_file})
  common::info "${_helm_cmd}"

  local _chart_dryrun=""
  _chart_dryrun=$(echo "${_chart_flags_section}" | common::yq4-get '.dryRun')
  if [ "${_chart_dryrun}" = "true" ]; then
    eval "${_helm_cmd}" > dry-run.txt
    _res=$?
    if [ ${_res} -ne 0 ]; then
      common::err "Run helm install with dry-run error"
      return ${_res}
    fi
    common::info "$(cat dry-run.txt)"
  else
    eval "${_helm_cmd}"
    _res=$?
    if [ ${_res} -ne 0 ]; then
      common::err "Run helm install error"
      return ${_res}
    fi
  fi

  local _chart_compare=""
  _chart_compare=$(echo "${_chart_flags_section}" | common::yq4-get '.compare')
  if [ "${_chart_compare}" = "true" ]; then
    local _chart_get_cmd=chart-get-cmd.txt
    echo -n "helm get manifest " > ${_chart_get_cmd}
    if [ -n "${_chart_namespace}" ]; then
      echo -n "-n ${_chart_namespace} " >> ${_chart_get_cmd}
    fi
    echo -n "${_chart_release_name} " >> ${_chart_get_cmd}

    eval "${_helm_cmd}" > manifest-current.txt
    common::info "########### start showing diff ##################"
    common::info "$(diff manifest-current.txt dry-run.txt)"
    common::info "########### finish showing diff ##################"
  fi
}

# setupHooks this will output hooks for pre/post helm install as 2 sh files
function setupHooks() {
  local _chart_hooks_section=${1}

  local _chart_pre_deploy=""
  _chart_pre_deploy=$(echo "${_chart_hooks_section}" | common::yq4-get '.preDeploy')

  _chart_pre_deploy_skip=$(echo "${_chart_pre_deploy}" | common::yq4-get '.skip')
  if [[ ${_chart_pre_deploy_skip} == "true" ]]; then
    common::debug "detect skip for preDeploy; skipping preDeploy hook"
  else
    if [ -n "${_chart_pre_deploy}" ]; then
      local _pre_deploy_script=pre-deploy.sh

      local _base64_pre=""
      _base64_pre=$(echo "${_chart_pre_deploy}" | common::yq4-get '.base64Encoded')
      if [[ ${_base64_pre} == "true" ]]; then
        common::debug "use base64 to decode pre-deploy hook"
        echo "${_chart_pre_deploy}" | common::yq4-get '.content' | base64 -D > ${_pre_deploy_script}
      else
        echo "${_chart_pre_deploy}" | common::yq4-get '.content' > ${_pre_deploy_script}
      fi

      chmod u+x ${_pre_deploy_script}
    fi
  fi

  local _chart_post_deploy=""
  _chart_post_deploy=$(echo "${_chart_hooks_section}" | common::yq4-get '.postDeploy')
  local _chart_post_deploy_skip=""
  _chart_post_deploy_skip=$(echo "${_chart_post_deploy}" | common::yq4-get '.skip')
  if [[ ${_chart_post_deploy_skip} == "true" ]]; then
    common::debug "detect skip for postDeploy; skipping postDeploy hook"
  else
    if [ -n "${_chart_post_deploy}" ]; then
      local _post_deploy_script=post-deploy.sh

      local _base64_post=""
      _base64_post=$(echo "${_chart_post_deploy}" | common::yq4-get '.base64Encoded')
      if [[ ${_base64_post} == "true" ]]; then
        common::debug "use base64 to decode pre-deploy hook"
        echo "${_chart_post_deploy}" | common::yq4-get '.content' | base64 -D > ${_post_deploy_script}
      else
        echo "${_chart_post_deploy}" | common::yq4-get '.content' > ${_post_deploy_script}
      fi

      chmod u+x ${_post_deploy_script}
    fi
  fi
}

#######################################
# helm-install::process_chart this will process chart and install it
# Globals:
#   None
# Arguments:
#   _chart_content: the chart content
# Returns:
#   0 if thing was deleted, non-zero on error
# Notes:
#   this will process one element of helm chart section: helmCharts[]
# Samples:
#   helm-install::process_chart "${_task_content}"
#######################################
function helm-install::process_chart() {
  local _chart_content=${1}

  local _chart_name=""
  _chart_name=$(echo "${_chart_content}" | common::yq4-get '.name')
  local _chart_version=""
  _chart_version=$(echo "${_chart_content}" | common::yq4-get '.version')
  local _chart_repo_section=""
  _chart_repo_section=$(echo "${_chart_content}" | common::yq4-get '.repo')
  local _chart_values_section=""
  _chart_values_section=$(echo "${_chart_content}" | common::yq4-get '.values')
  local _chart_release_name=""
  _chart_release_name=$(echo "${_chart_content}" | common::yq4-get '.releaseName')
  local _chart_namespace=""
  _chart_namespace=$(echo "${_chart_content}" | common::yq4-get '.namespace')
  local _chart_flags_section=""
  _chart_flags_section=$(echo "${_chart_content}" | common::yq4-get '.flags')
  local _chart_hooks_section=""
  _chart_hooks_section=$(echo "${_chart_content}" | common::yq4-get '.hooks')
  local _helm_setting_section=""
  _helm_setting_section=$(echo "${_chart_content}" | common::yq4-get '.helmSettings')

  local _helm_command_line=""
  _helm_command_line="$(getHelmVersion "$(echo "${_helm_setting_section}" | common::yq4-get '.version')")"
  [ -n "${_helm_command_line}" ] || _helm_command_line="helm"

  local _cluster_name_count=0
  _cluster_name_count=$(echo "${_chart_content}" | common::yq4-get '.cluster.names | length')
  if [[ "${_cluster_name_count}" -eq 0 ]]; then
    common::err "error: cluster name count is 0, or cluster.name is not set"
    return 1
  fi
  for (( cn=0; cn<_cluster_name_count; cn++ ))
  do
    local _cluster_name=""
    _cluster_name=$(echo "${_chart_content}" | common::yq4-get ".cluster.names[${cn}]")
    if [ -z "${_cluster_name}" ]; then
      common::err "cluster name is not set"
      return 1
    fi
    common::debug "working on cluster: ${_cluster_name}"

    # start a subshell to install chart
    # When the subshell is created, all environment variables are copied from the parent shell including internal data like local ones.
    # https://unix.stackexchange.com/questions/138463/do-parentheses-really-put-the-command-in-a-subshell
    (
    # used for subshell functions
    export HELM_COMMAND_LINE="${_helm_command_line}"
    export CLUSTER_NAME="${_cluster_name}"
    export HELM_VALUES_FLAG_FILE=values-flag.txt
    export SKIP_INSTALL_HELM_CHART_FILE_NAME="DONT_INSTALL_HELM"

    # create new folder
    mkdir -p "${_cluster_name}"-"${_chart_name}"
    cd "${_cluster_name}"-"${_chart_name}" || exit

    # setup hooks
    setupHooks "${_chart_hooks_section}"

    # run pre-deploy hook before processing chart
    if [ -f ./pre-deploy.sh ]; then
      # try to assume and get role
      common::assume_role
      common::debug "detect pre-deploy hook; running hooks"
      ./pre-deploy.sh
      _res=$?
      _ignore_error=$(echo "${_chart_content}" | common::yq4-get '.hooks.preDeploy.ignoreErrors')
      if [ "${_ignore_error}" != "true" ] && [ ${_res} -ne 0 ]; then
        common::err "Run pre-deploy hook error"
        exit ${_res}
      fi
    fi

    # connect
    if ! common::assume_role; then
      common::err "try to connect to cluster \"${_cluster_name}\" error"
      exit ${_res}
    fi

    # download chart
    common::debug "downloading chart: ${_chart_name}"
    if ! downloadChart "${_chart_repo_section}" "${_chart_name}" "${_chart_version}"; then
      common::err "download chart error"
      exit ${_res}
    fi

    # get values
    common::debug "get values for: ${_chart_name} with release name: ${_chart_release_name}"
    if ! getValues "${_chart_values_section}" "${_chart_release_name}" "${_chart_namespace}"; then
      common::err "get values error"
      exit 1
    fi

    ########## special file to skip helm installation ##########
    # ideally this is used for predeploy script to generate some files and skip helm install
    if [ -f ./${SKIP_INSTALL_HELM_CHART_FILE_NAME} ]; then
      common::info "detect file named ${SKIP_INSTALL_HELM_CHART_FILE_NAME} and skipping install chart ${_chart_name}"
    else
      # install
      _values_flag=""
      if [ -f ./values-flag.txt ]; then
        _values_flag=$(cat values-flag.txt)
      fi
      installChart "${_chart_name}" "${_chart_namespace}" "${_chart_release_name}" "${_chart_flags_section}" "${_values_flag}"
      _res=$?
      _ignore_error=$(echo "${_chart_content}" | common::yq4-get '.ignoreErrors')
      if [ "${_ignore_error}" != "true" ] && [ ${_res} -ne 0 ]; then
        common::err "Run installChart error"
        exit ${_res}
      fi
    fi

    if [ -f ./post-deploy.sh ]; then
      common::debug "detect post-deploy hook; running hooks"
      ./post-deploy.sh
      _res=$?
      _ignore_error=$(echo "${_chart_content}" | common::yq4-get '.hooks.postDeploy.ignoreErrors')
      if [ "${_ignore_error}" != "true" ] && [ ${_res} -ne 0 ]; then
        common::err "Run post-deploy hook error"
        exit ${_res}
      fi
    fi
    cd ..
    rm -rf "${_cluster_name}"-"${_chart_name}"
    )
    _res=$?
    if [ ${_res} -ne 0 ]; then
      common::err "error: sub shell return none 0: ${_res}"
      exit ${_res}
    fi
  done
}
