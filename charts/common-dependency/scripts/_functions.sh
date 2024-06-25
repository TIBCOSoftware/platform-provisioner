#!/bin/bash

#
# © 2019 - 2024 Cloud Software Group, Inc.
# All Rights Reserved. Confidential & Proprietary.
#

#######################################
# common::err will output err log if PIPELINE_LOG_DEBUG is set to true
# this function try to cover most common use case for yq version 4 and provide support for null value
# Globals:
#   None
# Arguments:
#   $*: the err log you want to output
# Returns:
#   None
# Notes:
#   refer: https://google.github.io/styleguide/shellguide.html#stdout-vs-stderr
# Samples:
#   common::err "this is err log"
function common::err() {
  echo "### [$(date +'%Y-%m-%dT%H:%M:%S%z')][ERROR]: $*" >&2
}

#######################################
# common::debug will output debug log if PIPELINE_LOG_DEBUG is set to true
# this function try to cover most common use case for yq version 4 and provide support for null value
# Globals:
#   PIPELINE_LOG_DEBUG: if set to true will output debug log
# Arguments:
#   $*: the debug log you want to output
# Returns:
#   None
# Notes:
#   refer: https://google.github.io/styleguide/shellguide.html#stdout-vs-stderr
# Samples:
#   common::debug "this is debug log"
#######################################
function common::debug() {
  if [[ "${PIPELINE_LOG_DEBUG}" == "true" ]]; then
    echo "### [$(date +'%Y-%m-%dT%H:%M:%S%z')][DEBUG]: $*" >&1
  fi
}

#######################################
# common::info will output info log if PIPELINE_LOG_DEBUG is set to true
# this function try to cover most common use case for yq version 4 and provide support for null value
# Globals:
#   None
# Arguments:
#   $*: the info log you want to output
# Returns:
#   None
# Notes:
#   refer: https://google.github.io/styleguide/shellguide.html#stdout-vs-stderr
# Samples:
#   common::info "this is info log"
#######################################
function common::info() {
  echo "### [$(date +'%Y-%m-%dT%H:%M:%S%z')][INFO]: $*" >&1
}

#######################################
# common::warn will output info log if PIPELINE_LOG_DEBUG is set to true
# this function try to cover most common use case for yq version 4 and provide support for null value
# Globals:
#   None
# Arguments:
#   $*: the warn log you want to output
# Returns:
#   None
# Notes:
#   refer: https://google.github.io/styleguide/shellguide.html#stdout-vs-stderr
# Samples:
#   common::warn "this is warn log"
#######################################
function common::warn() {
  echo "### [$(date +'%Y-%m-%dT%H:%M:%S%z')][WARNING]: $*" >&1
}

#######################################
# ll alias of ls. normally used for bash
#######################################
function ll() {
    ls -rtlahG "$@"
}

#######################################
# common::source_file source a file
# Globals:
#   None
# Arguments:
#   _file: file path to source
# Returns:
#   0 if thing was deleted, non-zero on error
# Notes:
#   None
# Samples:
#   None
#######################################
function common::source_file() {
  local _file=${1}
  [ -f "${_file}" ] || { common::err "error: file ${_file} does not exist"; exit 1; }
  # shellcheck source=./_file
  source "${_file}"
}

#######################################
# common::check_docker_status will wait and check docker daemon status. This function will block the script until docker daemon is ready
# Globals:
#   PIPELINE_CHECK_DOCKER_STATUS: if set to false will skip check docker status
# Arguments:
#   None
# Returns:
#   0 if thing was deleted, non-zero on error
# Notes:
#   None
# Samples:
#   common::check_docker_status
#######################################
function common::check_docker_status() {
  if [[ "${PIPELINE_CHECK_DOCKER_STATUS}" == false ]]; then
    common::debug "detect PIPELINE_CHECK_DOCKER_STATUS is false, skip check docker status"
    return 0
  fi
  for i in $(seq 1 15); do if docker ps >/dev/null; then break; fi; common::debug "Waiting on docker readiness (try ${i}/15, sleeping 15s)..."; sleep 15; done
  docker ps >/dev/null || { common::err "Docker is not ready."; return 1; }
}

#######################################
# common::yq4-get this will read data from input path.
# this function try to cover most common use case for yq version 4 and provide support for null value
# Globals:
#   None
# Arguments:
#   yq_path: the path you want to get from yaml file
#   rest: the rest of yq command
# Returns:
#   0 if thing was deleted, non-zero on error
# Notes:
#   It support both read from file and read from pipe.
#   It can easily replace yq version 3 command like this: yq r - fileName --> common::yq4-get fileName
# Samples:
#   echo "${_task_content}" | common::yq4-get '.condition'
#   common::yq4-get '.condition' test.yaml -o json
#######################################
function common::yq4-get() {
  local _input="${1}"
  shift
  yq_path=${_input} yq4 'eval(env(yq_path)) | select(. != null)' $@
}

# The reason that we unset these variables is because we will use AWS environment variables for assumed role.
# The default aws profile that mount on pod will always be the first role that we have
# pod aws profile role --> aws-role1 --> aws-role2
# we want above order always to be true. If we don't unset these variables; the next assume role will starts from aws-role2
# also eventually we use AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN to set kubeconfig
# see: https://awscli.amazonaws.com/v2/documentation/api/latest/topic/config-vars.html#precedence-1
# the use case is
# 1. user only set AWS_PROFILE; then we will use this profile to generate aws token environment variables
# 2. user only set AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN; then we will use these environment variables when PIPELINE_USE_LOCAL_CREDS is set
function unset-aws-env() {
  if [[ "${PIPELINE_USE_LOCAL_CREDS}" != "true" ]]; then
    common::debug "detect PIPELINE_USE_LOCAL_CREDS is NOT true, clear AWS environment variables"
    unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
  else
    common::debug "detect PIPELINE_USE_LOCAL_CREDS is true, skip clear AWS environment variables"
  fi
}

# this will also do a chain of assumption until the last one. So the current environment is on the last role
# pp-aws-assume-role "aws-role1" "aws-role2"
function pp-aws-assume-role() {

  # only when PIPELINE_USE_LOCAL_CREDS is true and AWS_SESSION_TOKEN is set; we will skip assume role
  # we do need to generate AWS_SESSION_TOKEN as we don't use aws profile inside kubeconfig
  if [[ "${PIPELINE_USE_LOCAL_CREDS}" == "true" ]] && [[ -n "${AWS_SESSION_TOKEN}" ]]; then
    common::debug "detect PIPELINE_USE_LOCAL_CREDS is true, skip assume role"
    return 0
  fi

  unset-aws-env

  function assume-role() {
    local ROLE_ARN=$1
    # Role chaining limits your AWS CLI or AWS API role session to a maximum of one hour and can't be increased.
    # see: https://aws.amazon.com/premiumsupport/knowledge-center/iam-role-chaining-limit/
    # we have to be limited in 1 hour because of AWS
    # local MAX_SESSION=14400
    local MAX_SESSION=3600
    local _res=''
    _res=$(aws sts assume-role --role-arn "${ROLE_ARN}" --duration-seconds ${MAX_SESSION} --role-session-name AWSCLI-Session 2>/dev/null)
    local ret=$?
    if [ ${ret} -ne 0 ]; then
      common::debug "can not use ${MAX_SESSION} for role ${ROLE_ARN}; using default session"
      _res=$(aws sts assume-role --role-arn "${ROLE_ARN}" --role-session-name AWSCLI-Session)
      [ $? -eq 0 ] || return 1
    fi
    export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
    AWS_ACCESS_KEY_ID=$(echo "${_res}" | jq -r ".Credentials.AccessKeyId")
    AWS_SECRET_ACCESS_KEY=$(echo "${_res}" | jq -r ".Credentials.SecretAccessKey")
    AWS_SESSION_TOKEN=$(echo "${_res}" | jq -r ".Credentials.SessionToken")
    return $?
  }

  # https://google.github.io/styleguide/shellguide.html#variable-names
  # we need to set role as local variable; otherwise it will leak to other functions
  local role=""
  for role in "$@"; do
    common::debug "assuming ${role}"
    if ! assume-role "${role}" ; then
      common::err "Failed to assume role ${role}"
      return 1
    fi
  done
}

# this will do a chain of role assumption until the last one and set the temp token to kubeconfig
# For the pipeline usage we always want to set CLUSTER_NAME. The auto detect is for local usage
# eks-pp-assume-role "aws-role1" "aws-role2"
# so that no matter of the aws environment setting; this kubconfig will always work
function eks-pp-assume-role() {
  AWS_ACCESS_KEY_ID_ORIGINAL=${AWS_ACCESS_KEY_ID}
  AWS_SECRET_ACCESS_KEY_ORIGINAL=${AWS_SECRET_ACCESS_KEY}
  AWS_SESSION_TOKEN_ORIGINAL=${AWS_SESSION_TOKEN}

  if ! pp-aws-assume-role $@ ; then
    common::err "assume-role error"
    return 1
  fi

  local _k8s_user=kubernetic
  [ -z "${AWS_REGION}" ] && AWS_REGION="us-west-2"

  if [ -z "${CLUSTER_NAME}" ]; then
    # if we set cluster name then we don't need to get automatically
    CLUSTER_NAME=$(aws eks --region ${AWS_REGION} list-clusters --output text | awk '{print $2}')
    [ -z "${CLUSTER_NAME}" ] && common::err "exit: CLUSTER_NAME empty in AWS_REGION: ${AWS_REGION}" && return 1
  fi

  common::info "Connecting to cluster: \"${CLUSTER_NAME}\""
  local _cluster_ep=""
  _cluster_ep=$(aws eks --region ${AWS_REGION} describe-cluster --name "${CLUSTER_NAME}" --query cluster.endpoint --output text 2>/dev/null)
  [ -z "${_cluster_ep}" ] && common::err "exit: cluster.endpoint is empty in AWS_REGION: ${AWS_REGION}" && return 1
  local _cluster_cert=""
  _cluster_cert=$(aws eks --region ${AWS_REGION} describe-cluster --name "${CLUSTER_NAME}" --query cluster.certificateAuthority.data --output text 2>/dev/null)
  [ -z "${_cluster_cert}" ] && common::err "exit: cluster.certificateAuthority.data is empty in AWS_REGION: ${AWS_REGION}" && return 1

  kubectl config set-cluster "${CLUSTER_NAME}" --server="${_cluster_ep}" > /dev/null
  kubectl config set-context "${CLUSTER_NAME}" --cluster="${CLUSTER_NAME}" --user=${_k8s_user} > /dev/null
  # workaround to set certificate-authority-data without using file
  kubectl config set clusters."${CLUSTER_NAME}".certificate-authority-data "${_cluster_cert}" > /dev/null

  local _aws_cli=""
  _aws_cli="$(command -v aws)"
  _aws_cli=${_aws_cli:-"/usr/local/bin/aws"}

  kubectl config unset users.${_k8s_user} > /dev/null

  kubectl config set-credentials ${_k8s_user} \
  --exec-api-version='client.authentication.k8s.io/v1beta1' --exec-command="${_aws_cli}" \
  --exec-arg=eks --exec-arg=get-token --exec-arg=--region --exec-arg="${AWS_REGION}" \
  --exec-arg=--cluster-name --exec-arg="${CLUSTER_NAME}" \
  --exec-env=AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID}" \
  --exec-env=AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY}" \
  --exec-env=AWS_SESSION_TOKEN="${AWS_SESSION_TOKEN}" > /dev/null

  kubectl config use-context "${CLUSTER_NAME}" > /dev/null

  export AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID_ORIGINAL}
  export AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY_ORIGINAL}
  export AWS_SESSION_TOKEN=${AWS_SESSION_TOKEN_ORIGINAL}
}

# For Azure; we assume to load token from system
function pp-azure-assume-role() {

  if [[ "${PIPELINE_USE_LOCAL_CREDS}" == "true" ]]; then
    common::debug "detect PIPELINE_USE_LOCAL_CREDS is true, skip assume role"
    return 0
  fi

  return 0
}

# generate aks kubeconfig
function aks-pp-assume-role() {
  if [ -z "${CLUSTER_NAME}" ]; then
    common::err "Please set CLUSTER_NAME environment variable"
    return 1
  fi

  if [ -z "${AZURE_RESOURCE_GROUP}" ]; then
    common::err "Please set AZURE_RESOURCE_GROUP environment variable"
    return 1
  fi

  # get azure token first
  if ! pp-azure-assume-role; then
    common::err "pp-azure-assume-role error"
    return 1
  fi

  az aks get-credentials --resource-group "${AZURE_RESOURCE_GROUP}" --name "${CLUSTER_NAME}" --overwrite-existing 1> /dev/null
  if [ $? -ne 0 ]; then
    common::err "generate kubeconfig for aks ${AZURE_RESOURCE_GROUP}/${CLUSTER_NAME} failed"
    return 1
  fi
}

#######################################
# common::assume_role will automatically detect if it is on-prem, Azure or AWS account and try to connect to target account
# after connecting to target account if CLUSTER_NAME is set, it will try to refresh kubeconfig token for CLUSTER_NAME
# Globals:
#   AWS_ACCOUNT: For AWS we need to setup AWS_ACCOUNT and AWS_REGION
#   AWS_REGION: Only works for AWS account
#   AWS_PROFILE: will be used as the initial AWS role that the pipeline will use
#   AZURE_RESOURCE_GROUP: For Azure we need to setup AWS_ACCOUNT (see get-azure-sub-id) and AZURE_RESOURCE_GROUP
#   CLUSTER_NAME: If we want to generate kubeconfig we need to set: CLUSTER_NAME
#   PIPELINE_USE_LOCAL_CREDS: if set to true will use local creds
#   PIPELINE_AWS_MANAGED_ACCOUNT_ROLE: the role to assume to. We will use current AWS role to assume to this role to perform the task. current role --> "arn:aws:iam::${_account}:role/${PIPELINE_AWS_MANAGED_ACCOUNT_ROLE}"
# Arguments:
#   None
# Returns:
#   0 if thing was deleted, non-zero on error
# Notes:
#   We normally should only use this in pipeline script
#   If we want to run locally we need to set AWS_PROFILE before using this function
#   the assume role will reset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN environment variables; so we always starts from initial role in aws profile
#   1. AWS Pipeline use case: The pod will have aws profile mounted and we will always use this profile to assume to target account
#      There are no AWS environment variables set. (No AWS_PROFILE, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN) All the token is generated by assume role.
#   2. AWS Local use case:
#     2.1 If we set PIPELINE_USE_LOCAL_CREDS is not set; only AWS_PROFILE can be used to assume to target account. (like the pipeline use case)
#         AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN will be cleaned
#     2.2 If we set PIPELINE_USE_LOCAL_CREDS is set to true; we can use AWS_PROFILE (will jump to PIPELINE_AWS_MANAGED_ACCOUNT_ROLE role to get token)
#         or AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN to assume to target account. (local use case) (will NOT jump to PIPELINE_AWS_MANAGED_ACCOUNT_ROLE role. We will use the token as it is to setup kubeconfig file)
#   3. Azure Pipeline use case: You need to set PIPELINE_USE_LOCAL_CREDS not true to use this feature
#   4. Azure Local use case: Only works with PIPELINE_USE_LOCAL_CREDS is set to true. Except admin; no one can use AzureFederation role to assume to Azure account
#   5. On-prem use case:
# Samples:
#  if ! common::assume_role; then
#    err "common::assume_role error"
#    exit 1
#  fi
#######################################
function common::assume_role() {

  # although the sub-calls needs these exports; we try to use local in this function
  local _account=${AWS_ACCOUNT}
  local _cluster_name=${CLUSTER_NAME}

  # on-prem use case this will use user's default kubeconfig
  if [[ "${_account}" == "on-prem" ]] && [[ "${PIPELINE_ON_PREM_KUBECONFIG}" == true ]]; then
    common::debug "Looks like select on-prem with PIPELINE_ON_PREM_KUBECONFIG"
    common::debug "Now set KUBECONFIG set to/root/.kube/config-on-prem"
    export KUBECONFIG=/root/.kube/config-on-prem
    return 0
  fi

  # this will use given kubeconfig file
  if [[ "${_account}" == "on-prem" ]] && [[ -n "${PIPELINE_ON_PREM_KUBECONFIG_FILE_NAME}" ]]; then
    common::debug "Looks like select on-prem with PIPELINE_ON_PREM_KUBECONFIG_FILE_NAME"
    common::debug "Looks like PIPELINE_ON_PREM_KUBECONFIG_FILE_NAME is set to ${PIPELINE_ON_PREM_KUBECONFIG_FILE_NAME}"
    common::debug "Now set KUBECONFIG set to/root/.kube/${PIPELINE_ON_PREM_KUBECONFIG_FILE_NAME}"
    export KUBECONFIG=/root/.kube/"${PIPELINE_ON_PREM_KUBECONFIG_FILE_NAME}"
    return 0
  fi

  if [[ "${_account}" == "on-prem" ]]; then
    common::debug "Looks like select on-prem without setting PIPELINE_ON_PREM_KUBECONFIG or PIPELINE_ON_PREM_KUBECONFIG_FILE_NAME"
    return 0
  fi

  # azure use case
  # the pattern is azure-72f677ccb9aa, the last section of Azure sub id
  if echo "${_account}" | grep -q "azure-"; then
    common::debug "Looks like select Azure account ${_account}"

    # check if we have get-azure-sub-id function
    if declare -F get-azure-sub-id > /dev/null; then
      if ! get-azure-sub-id "${_account}"; then
        common::err "get azure sub id error"
        return 1
      fi
    fi

    # if we set CLUSTER_NAME then we will try to generate kubeconfig
    if [[ -n "${_cluster_name}" ]]; then
      common::debug "detect CLUSTER_NAME is set to ${_cluster_name}"
      aks-pp-assume-role
      return $?
    else
      # if not then we will just assume to Azure account
      if ! pp-azure-assume-role; then
        common::err "pp-azure-assume-role error"
        return 1
      fi
    fi

    return 0
  fi

  # aws use case
  # by default we use AWS to connect
  common::debug "Looks like AWS account: ${_account} is selected"

  if [[ -n "${_cluster_name}" ]]; then
    common::debug "detect CLUSTER_NAME is set to ${_cluster_name}"
    common::debug "try to refresh kubeconfig token for ${_cluster_name}"
    if ! eks-pp-assume-role "arn:aws:iam::${_account}:role/${PIPELINE_AWS_MANAGED_ACCOUNT_ROLE}"; then
      common::err "eks-pp-assume-role error"
      return 1
    fi
  else
    common::debug "refresh environment AWS token"
    if ! pp-aws-assume-role "arn:aws:iam::${_account}:role/${PIPELINE_AWS_MANAGED_ACCOUNT_ROLE}"; then
      common::err "assume-role error"
      return 1
    fi
  fi
}

# parse-with-aws-secret-manager read secret defined in meta.secret.aws.secretId as environment and replace recipe.yaml with given secret
function parse-with-aws-secret-manager() {
  local aws_region=${1}
  local recipe=${2}
  local output=${3}

  if [ -z "${output}" ]; then
    common::err "please set output file"
    return 1
  fi

  secret_id=$(cat "${recipe}" | common::yq4-get .meta.secret.aws.secretName)

  if [ -z "${secret_id}" ]; then
    return 0
  fi

  common::debug "detect meta.secret.aws.secretId is set; using aws secret manager to parse recipe"

  _out=$(aws secretsmanager get-secret-value --region "${aws_region}" --secret-id ${secret_id} --query 'SecretString' --output json)
  if [ $? -ne 0 ]; then
    common::err "get AWS secret error drop replace secret"
    return 1
  fi
  (
    eval $(echo "${_out}" | jq '. | fromjson' | jq -r 'keys[] as $k | "export \($k)=\"\(.[$k])\""')
    _replace_variables="$(echo "${_out}" | jq '. | fromjson' | jq -r 'keys[] as $k | "$\($k)"')"
    common::debug "replace recipe secret with AWS secret variables: "
    common::debug "${_replace_variables}"
    envsubst "${_replace_variables}" < "${recipe}" > "${output}"
    common::debug "done replacing variables"
  )
}

# process_recipe_secret replace recipe with secret value
function process_recipe_secret() {

  local _aws_region=${1}
  local _aws_account=${2}
  local _input=${3}
  local _outputFile=${4}

  # process secret replacement
  secret_id=$(echo "${_input}" | common::yq4-get .meta.secret.aws.secretName)
  if [ -n "${secret_id}" ]; then
    common::debug "detect meta.secret.aws.secretName=${secret_id} is used. now parsing recipe with values in AWS secret manager"

    # assume to target account for getting secret field
    if ! pp-aws-assume-role "arn:aws:iam::${_aws_account}:role/${PIPELINE_AWS_MANAGED_ACCOUNT_ROLE}" ; then
      common::err "assume role error"
      return 1
    fi

    echo "${_input}" > _input_recipe_tmp.yaml
    # process secret fields
    parse-with-aws-secret-manager "${_aws_region}" _input_recipe_tmp.yaml "${_outputFile}"
    rm -rf _input_recipe_tmp.yaml
  else
    common::debug "no meta.secret.aws.secretName is set"
    echo "${_input}" > "${_outputFile}"
  fi
}

#######################################
# common::git_clone this will clone repo and copy files to current folder. It will do a few extra things:
# 1. if GITHUB_TOKEN is not set then read from secret volume
# 2. if GIT_HASH is set then checkout to that hash (full git clone)
# 3. if GIT_HASH is not set then use --depth 1 (shallow clone
# Globals:
#   GITHUB_TOKEN: the token used to access GitHub. if not set then read from secret volume
# Arguments:
#   REPO: the repo section in recipe
#   BRANCH_NAME: the branch name in recipe
#   GIT_FOLDER: the folder to clone to
#   GIT_HASH: the hash to checkout to
# Returns:
#   0 if thing was deleted, non-zero on error
# Notes:
#   None
# Samples:
#   repo: github.com/TIBCOSoftware/tp-helm-charts
#   path: charts/dp-config-es
#   branch: master  # optional, branch or tag name, the default is main
#   hash: xxxxxx    # optional, default value is empty and will not get from hash
#######################################
function common::git_clone() {
  common::debug "common::git_clone parameters: $*"
  git_clone "$@"
}

# git_clone will clone the github repo
# git_clone "github.com/TIBCOSoftware/tp-helm-charts.git" "master" "git_remote" "git_hash"
# git_hash is optional
function git_clone() {

  local REPO=${1}
  local BRANCH_NAME=${2}
  local GIT_FOLDER=${3}
  local GIT_HASH=${4} # optional

  # by default use public repo
  _git_url="https://${REPO}"
  if [ -z "${GITHUB_TOKEN}" ]; then
    # try token on secret volume
    common::debug "try to read github token from secret volume"
    if [[ -f /tmp/secret-github/GITHUB_TOKEN ]]; then
      common::debug "read github token from secret volume"
      GITHUB_TOKEN=$(cat /tmp/secret-github/GITHUB_TOKEN)
      _git_url="https://${GITHUB_TOKEN}:x-oauth-basic@${REPO}"
    fi
  else
    _git_url="https://${GITHUB_TOKEN}:x-oauth-basic@${REPO}"
  fi

  mkdir -p ${GIT_FOLDER}

  if [ -n "${GIT_HASH}" ]; then
    git clone -q --branch "${BRANCH_NAME}" "${_git_url}" "${GIT_FOLDER}"
    if [ $? -ne 0 ]; then
      common::err "git clone error"
      return 1
    fi
    common::debug "detect git repo hash: ${GIT_HASH}"
    local CURRENT_PATH=$(pwd)
    cd "${GIT_FOLDER}" || exit
    git checkout "${GIT_HASH}"
    if [ $? -ne 0 ]; then
      common::err "git checkout error"
      return 1
    fi
    git branch
    if [ $? -ne 0 ]; then
      common::err "git branch error"
      return 1
    fi
    cd "${CURRENT_PATH}" || exit
  else
    git clone -q --branch "${BRANCH_NAME}" --depth 1 "${_git_url}" "${GIT_FOLDER}"
    if [ $? -ne 0 ]; then
      common::err "git clone with branch ${BRANCH_NAME} error"
      return 1
    fi
  fi
}

# replace_recipe_gitops if the input contains meta.git.github, it will replace the recipe file with github recipe.
function gitops_replace_recipe() {

  local _input=${1}
  local _outputFile=${2}

  github=$(echo "${_input}" | common::yq4-get .meta.git.github)
  if [ -n "${github}" ]; then
    common::debug "detect meta.git.github is used. now parsing recipe with github repo"
    REPO=$(echo "${_input}" | common::yq4-get .meta.git.github.repo)
    BRANCH_NAME=$(echo "${_input}" | common::yq4-get .meta.git.github.branch)
    GIT_FOLDER="git_remote"
    GIT_PATH=$(echo "${_input}" | common::yq4-get .meta.git.github.path)
    GIT_HASH=$(echo "${_input}" | common::yq4-get .meta.git.github.hash)
    GIT_TOKEN=$(echo "${_input}" | common::yq4-get .meta.git.github.token)
    if [ -n "${GIT_TOKEN}" ]; then
      common::debug "setup github token from recipe"
      export GITHUB_TOKEN="${GIT_TOKEN}"
    fi
    common::debug "git repo: ${REPO} with branch: ${BRANCH_NAME}"
    common::git_clone "${REPO}" "${BRANCH_NAME}" "${GIT_FOLDER}" "${GIT_HASH}"
    local _ret=$?
    [ ${_ret} -eq 0 ] || { common::err "ERROR Running git_clone"; return ${_ret}; }
    cp "${GIT_FOLDER}"/"${GIT_PATH}" "${_outputFile}"
    _ret=$?
    [ ${_ret} -eq 0 ] || { common::err "ERROR cp git folder ${GIT_FOLDER}/${GIT_PATH} to ${_outputFile}"; return ${_ret}; }
    common::debug "=========== show git cloned recipe: ${_outputFile}   ==================="
    local _output_content=""
    _output_content=$(cat "${_outputFile}")
    common::debug "${_output_content}"
    common::debug ""
    common::debug "=========== end of git cloned recipe: ${_outputFile} ==================="
    rm -rf ${GIT_FOLDER}
  else
    common::debug "no meta.git.github is set"
    echo "${_input}" > "${_outputFile}"
  fi
}

#######################################
# common::recipe_github_clone read from recipe section and clone to given folder
# Globals:
#   GITHUB_TOKEN: the token used to access GitHub. if not set then read from secret volume
# Arguments:
#   ${1}: the repo yaml section
#   ${2}: the output folder name or file name.
# Returns:
#   0 if thing was deleted, non-zero on error
# Notes:
#   The github section is defined as:
#			github!:{
#				repo!: =~"^github.com"
#				path!: string
#				branch!: string | *main
#				hash?: string
#				token?: string
#			}
#   The path is the key to copy from github repo to output.
#   If the path point of a file; then we will rename the file to output file name. If output is set as "."; then we will keep the file name
#   If the path point of a folder; then we will copy the folder content to output folder. If output is set as "."; then we will copy the folder content to current folder
#   If the output is not a "."; then we will create the folder if it does not exist
# Samples:
#   in the case of copy file:
#   _repo_section=$(echo "${INPUT}" | common::yq4-get '.meta.git')
#   common::recipe_git_clone "${_repo_section}" "recipe.yaml"
#   in the case of copy folder:
#   _repo_section=$(echo "${INPUT}" | common::yq4-get '.repo.git')
#   common::recipe_git_clone "${_repo_section}" "."
#######################################
function common::recipe_github_clone() {
  local _github_section=${1}
  local output=${2}
  if [ -z "${_github_section}" ]; then
    common::debug "no repo part detected, skipping recipe_github_clone"
    return 0
  fi

  # github.repo
  local _repo=""
  _repo=$(echo "${_github_section}" | common::yq4-get .github.repo)

  # github.branch
  local _branch_name=""
  _branch_name=$(echo "${_github_section}" | common::yq4-get .github.branch)
  _branch_name="${_branch_name:-main}"

  # github.path
  local _git_path=""
  _git_path=$(echo "${_github_section}" | common::yq4-get .github.path)

  # github.hash
  local _git_hash=""
  _git_hash=$(echo "${_github_section}" | common::yq4-get .github.hash)

  # github.token
  GIT_TOKEN=$(echo "${_github_section}" | common::yq4-get .github.token)
  if [ -n "${GIT_TOKEN}" ]; then
    common::debug "use github token from recipe"
    export GITHUB_TOKEN="${GIT_TOKEN}"
  fi

  _git_folder="git_remote"
  common::git_clone "${_repo}" "${_branch_name}" "${_git_folder}" "${_git_hash}"
  _res=$?
  unset GITHUB_TOKEN
  if [ ${_res} -ne 0 ]; then
    common::err "git clone error"
    return ${_res}
  fi

  if [[ -f "${_git_folder}"/"${_git_path}" ]]; then
    common::debug "copy file ${_git_folder}/${_git_path} to ${output}"
    cp "${_git_folder}"/"${_git_path}" "${output}"
  elif [[ -d "${_git_folder}"/"${_git_path}" ]]; then
    common::debug "copy folder ${_git_folder}/${_git_path}/* to ${output}"
    if ! [[ -d "${output}" ]]; then
      common::debug "create output folder ${output}"
      mkdir -p "${output}"
    fi
    cp -R "${_git_folder}"/"${_git_path}"/* "${output}"
  else
    common::err "can not find ${_git_folder}/${_git_path}"
    return 1
  fi

  rm -rf "${_git_folder}"
}

#######################################
# common::export_variables will expose variable in recipe to environment variable
# Globals:
#   None
# Arguments:
#   ${1}: the yaml key to read from recipe. should start with . eg: .meta.guiEnv
#   ${2}: the recipe yaml content
# Returns:
#   0 if thing was deleted, non-zero on error
# Notes:
#   None
# Samples:
#   common::export_variables ".meta.guiEnv" "${INPUT}"
#######################################
function common::export_variables() {
  local _env_array
  _env_array=$(echo "${2}" | _yq_key=${1} yq4 -o=j -I=0 'eval(env(_yq_key)) | to_entries | .[]')
  if [ $? -ne 0 ]; then
    common::err "yq read key ${1} error"
    return 1
  fi

  if [ -z "${_env_array}" ]; then
    common::debug "no data for key ${1}"
    return 0
  fi

  common::debug "export variables from key ${1}:"

  readarray envs <<< "${_env_array}"

  for _env in "${envs[@]}"; do
    local _key=""
    _key=$(echo "$_env" | yq4 '.key')
    local _value=""
    _value=$(echo "$_env" | yq4 '.value')
    common::debug "$_key=$_value"
    eval export "${_key}"="${_value}"
  done
}

#######################################
# common::replace_env_variables will replace recipe with env variables. Bascially we have a key and recipe as input.
# We will read the key from recipe and convert it to list of keys. Then we will use envsubst to replace the recipe with given env variables
# This function will not export the env variables to environment. It will only replace the recipe with env variables
# Globals:
#   REPLACE_RECIPE: if set to true then replace recipe with env variables
# Arguments:
#   ${1}: the recipe yaml content
#   ${2}: output file name
#   ${3}: the yaml key to read from recipe. should start with . eg: .meta.guiEnv
# Returns:
#   0 if thing was deleted, non-zero on error
# Notes:
#   None
# Samples:
#   common::replace_env_variables ".meta.guiEnv" "${INPUT}" recipe.yaml
#######################################
function common::replace_env_variables() {
  local _the_key=${1}
  local _input=${2}
  local _outputFile=${3}

  # if key is empty then just return
  if [ -z "${_the_key}" ]; then
    common::debug "no key is set"
    echo "${_input}" > "${_outputFile}"
    return 0
  fi

  # if input is empty then just return
  if [[ -z "${_input}" ]]; then
    common::debug "input is empty"
    return 0
  fi

  # if key is empty then just return
  echo "${_input}" | _yq_key=${_the_key} yq4 -e 'eval(env(_yq_key))' &> /dev/null
  if [ $? -ne 0 ]; then
    common::debug "recipe field for key ${_the_key} is empty"
    echo "${_input}" > "${_outputFile}"
    return 0
  fi

  # replace recipe with env variables
  if [[ ${REPLACE_RECIPE} == "true" ]]; then
    common::debug "replace recipe key: ${_the_key} with env variables:"

    # for a given key like .meta.guiEnv
    # we will read the key from recipe and convert it to list of keys like [a\nb\nc]
    # we then add $ to each key like [$a\n$b\n$c]
    # then we use paste to convert it to $a, $b, $c
    # envsubst works with this format of keys.
    keys=$(echo "${_input}" | _yq_key=${_the_key} yq4 'eval(env(_yq_key)) | keys | .[] | " $" + .' | paste -sd, -)

    common::debug "${keys}"
    echo "${_input}" | envsubst "${keys}" > "${_outputFile}"

    common::debug "replaced recipe with env variables listed in ${_the_key}:"
    common::debug "$(cat "${_outputFile}")"
  else
    common::debug "Global environment REPLACE_RECIPE is not set to true; skip replace recipe with env variables"
  fi
}

#######################################
# common::validate_input used to validate input with cue vet
# Globals:
#   PIPELINE_VALIDATE_INPUT: if set to false then skip cue vet
# Arguments:
#   ${1}: the recipe yaml content as input
#   ${2}: the .cue validation file
# Returns:
#   0 if thing was deleted, non-zero on error
# Notes:
#   None
# Samples:
#   common::validate_input "${INPUT}" "check_meta.cue"
#######################################
function common::validate_input() {
  local _input=${1}
  local _validation_file=${2}
  if [[ ${PIPELINE_VALIDATE_INPUT} == "false" ]]; then
    common::debug "PIPELINE_VALIDATE_INPUT is set to false; skip cue vet"
    return 0
  fi

  if ! [[ -f ${_validation_file} ]]; then
    common::debug "${_validation_file} not found; skip cue vet"
    return 0
  fi

  local _shared_cue_file="shared.cue"
  if ! [[ -f "${_shared_cue_file}" ]]; then
    common::debug "shared.cue not found; skip cue vet"
    return 0
  fi

  if ! [[ -f $(which cue) ]]; then
    common::debug "cue is not installed; skip cue vet"
    return 0
  fi

  common::debug "validate input with cue vet ${_validation_file}"
  echo "${_input}" > "${_validation_file}.data.yaml"
  cue vet "${_validation_file}.data.yaml" "${_shared_cue_file}" "${_validation_file}"
  local _res=$?
  rm -rf "${_validation_file}.data.yaml"
  if [[ _res -ne 0 ]]; then
      common::err "cue vet error: input validation error please check input recipe"
      common::info "############## validation cue file: ##############"
      cat "${_validation_file}"
      common::info "############## shared cue file: ##############"
      cat "${_shared_cue_file}"
      common::info "############## processing recipe: ##############"
      echo "${_input}"
      return 1
  fi
  common::debug "cue vet success with ${_validation_file}"
}

#######################################
# common::process_meta will replace recipe with env variables.
# Globals:
#   AWS_ACCOUNT: This is used for AWS secret
#   AWS_REGION: This is used for AWS secret
# Arguments:
#   ${1}: the recipe yaml content as input
#   ${2}: output file name
# Returns:
#   0 if thing was deleted, non-zero on error
# Notes:
#   None
# Samples:
#   common::process_meta "${INPUT}" recipe.yaml
#######################################
function common::process_meta() {
  local _input="${1}"
  local _recipe_file_name="${2}"

  local _tmp_recipe_file="recipe.tmp.yaml"
  local _meta_guiEnv=".meta.guiEnv"
  local _meta_globalEnvVariable=".meta.globalEnvVariable"

  # process gitOps part
  # 1. if meta.secret.aws.secretName exists; will replace secret. like github token
  # 2. if meta.git.github.repo exists; will replace recipe with the one on github
  # 3. process recipe secret for the last time

  # use GUI to replace recipe if .meta.guiEnv exists
  # we should only have one .meta.guiEnv to cover both current recipe and replaced recipe (the one on github)
  common::export_variables "${_meta_guiEnv}" "${_input}"
  common::export_variables "${_meta_globalEnvVariable}" "${_input}"
  common::replace_env_variables "${_meta_guiEnv}" "${_input}" "${_tmp_recipe_file}"
  common::replace_env_variables "${_meta_globalEnvVariable}" "$(cat ${_tmp_recipe_file})" "${_tmp_recipe_file}"
  mv "${_tmp_recipe_file}" "${_recipe_file_name}"

  if ! process_recipe_secret "${AWS_REGION}" "${AWS_ACCOUNT}" "$(cat "${_recipe_file_name}")" "${_recipe_file_name}"; then
    common::err "Run process_recipe_secret error"
    return 1
  fi

  if ! gitops_replace_recipe "$(cat "${_recipe_file_name}")" "${_recipe_file_name}"; then
    common::err "Run gitops_replace_recipe error"
    return 1
  fi

  if ! process_recipe_secret "${AWS_REGION}" "${AWS_ACCOUNT}" "$(cat "${_recipe_file_name}")" "${_recipe_file_name}"; then
    common::err "Run process_recipe_secret error"
    return 1
  fi

  # we should only replace the recipe with key list in .meta.guiEnv and .meta.globalEnvVariable

  # at this point in the current env; we have
  # 1. .meta.guiEnv
  # 2. .meta.globalEnvVariable
  # 3. .meta.secret.aws.secretName
  # 4. the new replaced recipe
  # So we only need to process recipe one more time with all these envs
  # yq4 envsubst will replace all envs in the recipe. Ideally we only want to some given keys.
  # yq4 '(.. | select(tag == "!!str")) |= envsubst' "${_recipe_file_name}" > tmpfile && mv tmpfile "${_recipe_file_name}"
  # envsubst require to use $$var to escape $var. see: https://github.com/a8m/envsubst
  common::replace_env_variables "${_meta_guiEnv}" "$(cat "${_recipe_file_name}")" "${_tmp_recipe_file}"
  common::replace_env_variables "${_meta_globalEnvVariable}" "$(cat ${_tmp_recipe_file})" "${_tmp_recipe_file}"
  mv "${_tmp_recipe_file}" "${_recipe_file_name}"

  common::debug "============Final recipe:=============="
  common::debug "$(cat "${_recipe_file_name}")"

  if ! common::adjust_tool_binaries "${_recipe_file_name}"; then
    common::err "Run adjust_tool_binaries error"
    return 1
  fi
}

# helmDepUp update helm chart dependencies
function helmDepUp () {
  path=$1
  (
    cd $path
    common::debug "Updating dependencies inside $path ..."
    if [ -f Chart.yaml ] ; then
        helm dep update
        if [ -d charts ]; then
          pushd charts
          ls *.tgz | xargs -n 1 tar -zxvf
          rm -rf *.tgz
          popd
        fi
    fi
    common::debug "... done."
    if [ -d charts ]; then
      for nextPath in $(find charts -mindepth 1 -maxdepth 1 -type d)
      do
        helmDepUp $(pwd)"/"$nextPath
      done
    fi
  )
}

# adjustToolBinaries will adjust tool binaries. we will relink binaries to the version specified in recipe
function adjustToolBinaries() {
  local _recipe="${1}"
  local _version=''
  local _ret=''

  local _tools_section=""
  _tools_section=$(cat "${_recipe}" | common::yq4-get .meta.tools)
  if [[ -z "${_tools_section}" ]]; then
    common::debug "no meta.tools is set"
    return 0
  fi

  ## declare an array variable with fixed values, as we need to have control over what tools can be updated
  declare -a _tool_name_array=("kubectl" "helm" "calicoctl" "yq")
  ## loop through the above array
  for _tool_name in "${_tool_name_array[@]}"
  do
    common::debug "### adjusting binary for ${_tool_name}"
    _version=$(cat "${_recipe}" | common::yq4-get ".meta.tools.${_tool_name}") ## default yq version i.e. yq3
    if [ -n "${_version}" ]; then
      common::debug "### replacing ${_tool_name} binary with version ${_version}"
      ## check if file exists to copy
      if [ -f /usr/local/bin/${_tool_name}-${_version} ]; then
        ## update the soft link
        ln -sf /usr/local/bin/${_tool_name}-${_version} /usr/local/bin/${_tool_name}
        _ret=$?
        [ ${_ret} -eq 0 ] || { common::err "### ERROR: Failed to update symlink for ${_tool_name} for version ${_version}"; return ${_ret}; }
      else
        ## better to fail than using different tool version
        common::err "### ERROR: Binary file for ${_tool_name} with version ${_version} is not supported; Exiting"
        common::err "### Check for supported versions for ${_tool_name} binary in pipeline description"
        return 1
      fi
    else
      common::debug "### INFO: No version specified for ${_tool_name} binary, using image default"
    fi
  done
}

#######################################
# common::adjust_tool_binaries this will adjust tool binaries. we will relink binaries to the version specified in recipe
# Globals:
#   None
# Arguments:
#   _recipe: the recipe yaml content as input. We will only parse meta.tools section
# Returns:
#   0 if thing was deleted, non-zero on error
# Notes:
#   None
# Samples:
#   repo: github.com/TIBCOSoftware/tp-helm-charts
#   path: charts/dp-config-es
#   branch: master  # optional, branch or tag name, the default is main
#   hash: xxxxxx    # optional, default value is empty and will not get from hash
#######################################
function common::adjust_tool_binaries() {
  common::debug "common::adjust_tool_binaries parameters: $*"
  adjustToolBinaries "$@"
}

# source customized env
function load-customized-env() {
  local _file=${1}
  if [[ -f "${_file}" ]]; then
    common::debug "loading ${_file}"
    # shellcheck source=./_file
    source "${_file}"
  fi
}

# init-global-variables will init global variables
# this needs to be as same as shard.cue defined
function init-global-variables() {
  export REPLACE_RECIPE=${REPLACE_RECIPE:-"true"}
  export PIPELINE_LOG_DEBUG=${PIPELINE_LOG_DEBUG:-"false"}
}

#######################################
# init: init function will be triggered when anyone source this file
# Globals:
#   PIPELINE_FUNCTION_INIT: if set to false then skip init
# Arguments:
#   None
# Returns:
#   None
# Notes:
#   Currently we want to support automatically load customized env. So we will load all _funcs_customize_*.sh files
# Samples:
#   None
#######################################
function init() {
  common::debug "_function.sh input parameters: $*"
  PIPELINE_FUNCTION_INIT=${PIPELINE_FUNCTION_INIT:-"true"}
  if [[ "${PIPELINE_FUNCTION_INIT}" != "true" ]]; then
    common::debug "PIPELINE_FUNCTION_INIT is not true; skip init"
    return 0
  fi

  init-global-variables

  for _file in _funcs_customize_*.sh; do
    load-customized-env "./${_file}"
  done

  if [[ -z $(which yq4 2>/dev/null) ]]; then
    common::err "yq4 is not installed"
    exit 1
  fi

  # setup cloud account roles
  export PIPELINE_AWS_MANAGED_ACCOUNT_ROLE=${PIPELINE_AWS_MANAGED_ACCOUNT_ROLE:-"${TIBCO_AWS_CONTROLLED_ACCOUNT_ROLE}"}
  export PIPELINE_AZURE_FEDERATION_ROLE=${PIPELINE_AZURE_FEDERATION_ROLE:-"${TIBCO_AZURE_FEDERATION_ROLE}"}
  export PIPELINE_AWS_COGNITO_IDENTITY_POOL=${PIPELINE_AWS_COGNITO_IDENTITY_POOL:-"${TIBCO_AWS_COGNITO_IDENTITY_POOL}"}
  export PIPELINE_AWS_COGNITO_IDENTITY_POOL_LOGINS=${PIPELINE_AWS_COGNITO_IDENTITY_POOL_LOGINS:-"${TIBCO_AWS_COGNITO_IDENTITY_POOL_LOGINS}"}
  export PIPELINE_TIBCO_AZURE_TIBCO_ORG_TENANT_ID=${PIPELINE_TIBCO_AZURE_TIBCO_ORG_TENANT_ID:-"${TIBCO_AZURE_TIBCO_ORG_TENANT_ID}"}
  export PIPELINE_TIBCO_AZURE_MANAGED_IDENTITY=${PIPELINE_TIBCO_AZURE_MANAGED_IDENTITY:-"${TIBCO_AZURE_MANAGED_IDENTITY}"}
}

# init
init "$@"
