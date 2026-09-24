#!/bin/bash

#
# Copyright 2025 Cloud Software Group, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

#######################################
# adjust-recipe.sh: this script will adjust the recipe for deploying TP on-prem for different k8s environments
# Globals:
#   None
# Arguments:
#   0 - 5: the choice of the environment. Any other non-empty value is rejected with exit 1;
#          no argument at all (or an empty one) opens the interactive menu.
# Returns:
#   None
# Notes:
#   Ideally we should use ./generate-recipe.sh to generate the recipe first before adjusting it.
# Samples:
#   ./adjust-recipe.sh 1
#######################################

# This script will generate the recipe for deploying TP on-prem
function adjust_recipes() {
  local choice="${1:-""}"

  # DB engine: one choice drives both the infra (01) and the CP (02) recipe, so a headless run
  # cannot end up with the CP pointed at an engine that was never installed. It has to be written
  # into the recipes: common::export_variables exports the recipe's guiEnv values unconditionally,
  # so exporting GUI_CP_DB_ENGINE alone is a silent no-op.
  export GUI_TP_DB_ENGINE=${GUI_TP_DB_ENGINE:-"postgres"}
  case "${GUI_TP_DB_ENGINE}" in
    postgres|oracle) ;;
    *)
      echo "ERROR: GUI_TP_DB_ENGINE must be postgres or oracle, got: ${GUI_TP_DB_ENGINE}"
      exit 1
      ;;
  esac
  # yq env() ABORTS when the variable is unset, so this default is required, not cosmetic.
  export GUI_TP_ORACLE_PASSWORD=${GUI_TP_ORACLE_PASSWORD:-"oracle"}
  # GUI_TP_INSTALL_ORACLE was replaced by GUI_TP_DB_ENGINE. Refuse it rather than
  # silently ignoring it and installing no Oracle.
  case "${GUI_TP_INSTALL_ORACLE:-}" in
    ""|false|False|FALSE) ;;
    *)
      echo "ERROR: GUI_TP_INSTALL_ORACLE is no longer supported. Use GUI_TP_DB_ENGINE=oracle."
      exit 1
      ;;
  esac

  while true; do
    if [[ -z $choice ]]; then
      echo "Please select an option:"
      echo "1. Adjust for k3s"
      echo "2. Adjust for OpenShift"
      echo "3. Adjust for Docker Desktop"
      echo "4. Adjust for minikube"
      echo "5. Adjust for kind"
      # echo "6. Adjust for MicroK8s"
      echo "0. Exit"
      read -rp "Enter your choice (0-5): " choice
    fi

    case $choice in
      1)
        echo "Adjusting kubernetes config for k3s..."
        _recipe_file_name="01-tp-on-prem.yaml"
        export TP_STORAGE_CLASS="local-path"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_SERVICE_TYPE = "ClusterIP")' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_STORAGE_CLASS = env(TP_STORAGE_CLASS))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_STORAGE_CLASS_FOR_NFS_SERVER_PROVISIONER = env(TP_STORAGE_CLASS))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_NFS_SERVER_PROVISIONER = true)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_METRICS_SERVER = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_PROVISIONER_UI = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_DB_ENGINE = env(GUI_TP_DB_ENGINE))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_ORACLE_PASSWORD = strenv(GUI_TP_ORACLE_PASSWORD))' "$_recipe_file_name"
        fi

        _recipe_file_name="02-tp-cp-on-prem.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_CP_STORAGE_CLASS = "nfs")' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_CP_DB_ENGINE = env(GUI_TP_DB_ENGINE))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_CP_ORACLE_DB_PASSWORD = strenv(GUI_TP_ORACLE_PASSWORD))' "$_recipe_file_name"
        fi

        _recipe_file_name="04-tp-adjust-resource.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TASK_REMOVE_RESOURCES = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TASK_SHOW_RESOURCES = false)' "$_recipe_file_name"
        fi

        _recipe_file_name="05-tp-auto-deploy-dp.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_USE_LOCAL_SCRIPT = false)' ${_recipe_file_name}
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_USE_GITHUB_SCRIPT = true)' ${_recipe_file_name}
          # yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_STORAGE_CLASS = env(TP_STORAGE_CLASS))' ${_recipe_file_name}
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_STORAGE_CLASS = "nfs")' ${_recipe_file_name} # BMDP Hawk need RWM but they will change soon.
        fi

        _recipe_file_name="06-tp-o11y-stack.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_STORAGE_CLASS = env(TP_STORAGE_CLASS))' "$_recipe_file_name"
        fi

        break
        ;;
      2)
        echo "Adjusting kubernetes config for OpenShift..."
        _recipe_file_name="01-tp-on-prem.yaml"
        export TP_STORAGE_CLASS="crc-csi-hostpath-provisioner"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_SERVICE_TYPE = "ClusterIP")' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_STORAGE_CLASS = env(TP_STORAGE_CLASS))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_STORAGE_CLASS_FOR_NFS_SERVER_PROVISIONER = env(TP_STORAGE_CLASS))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_NFS_SERVER_PROVISIONER = true)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_METRICS_SERVER = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_PROVISIONER_UI = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_DB_ENGINE = env(GUI_TP_DB_ENGINE))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_ORACLE_PASSWORD = strenv(GUI_TP_ORACLE_PASSWORD))' "$_recipe_file_name"
        fi

        _recipe_file_name="02-tp-cp-on-prem.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_CP_STORAGE_CLASS = "nfs")' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_CP_DB_ENGINE = env(GUI_TP_DB_ENGINE))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_CP_ORACLE_DB_PASSWORD = strenv(GUI_TP_ORACLE_PASSWORD))' "$_recipe_file_name"
        fi

        _recipe_file_name="04-tp-adjust-resource.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TASK_REMOVE_RESOURCES = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TASK_SHOW_RESOURCES = false)' "$_recipe_file_name"
        fi

        _recipe_file_name="05-tp-auto-deploy-dp.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_USE_LOCAL_SCRIPT = false)' ${_recipe_file_name}
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_USE_GITHUB_SCRIPT = true)' ${_recipe_file_name}
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_STORAGE_CLASS = env(TP_STORAGE_CLASS))' ${_recipe_file_name}
        fi

        _recipe_file_name="06-tp-o11y-stack.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_STORAGE_CLASS = env(TP_STORAGE_CLASS))' "$_recipe_file_name"
        fi
        break
        ;;
      3)
        echo "Adjusting kubernetes config for Docker Desktop..."
        _recipe_file_name="01-tp-on-prem.yaml"
        export TP_STORAGE_CLASS="hostpath"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_SERVICE_TYPE = "LoadBalancer")' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_STORAGE_CLASS = env(TP_STORAGE_CLASS))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_STORAGE_CLASS_FOR_NFS_SERVER_PROVISIONER = env(TP_STORAGE_CLASS))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_NFS_SERVER_PROVISIONER = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_METRICS_SERVER = true)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_PROVISIONER_UI = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_DB_ENGINE = env(GUI_TP_DB_ENGINE))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_ORACLE_PASSWORD = strenv(GUI_TP_ORACLE_PASSWORD))' "$_recipe_file_name"
        fi

        _recipe_file_name="02-tp-cp-on-prem.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_CP_STORAGE_CLASS = "hostpath")' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_CP_DB_ENGINE = env(GUI_TP_DB_ENGINE))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_CP_ORACLE_DB_PASSWORD = strenv(GUI_TP_ORACLE_PASSWORD))' "$_recipe_file_name"
        fi

        _recipe_file_name="04-tp-adjust-resource.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TASK_REMOVE_RESOURCES = true)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TASK_SHOW_RESOURCES = false)' "$_recipe_file_name"
        fi

        _recipe_file_name="05-tp-auto-deploy-dp.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_USE_LOCAL_SCRIPT = false)' ${_recipe_file_name}
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_USE_GITHUB_SCRIPT = true)' ${_recipe_file_name}
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_STORAGE_CLASS = env(TP_STORAGE_CLASS))' ${_recipe_file_name}
        fi

        _recipe_file_name="06-tp-o11y-stack.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_STORAGE_CLASS = env(TP_STORAGE_CLASS))' "$_recipe_file_name"
        fi
        break
        ;;
      4)
        echo "Adjusting kubernetes config for minikube..."

        echo "adjust kubeconfig for minikube..."
        echo "please make sure you have installed minikube and start it with --embed-certs"

        _recipe_file_name="01-tp-on-prem.yaml"
        export TP_STORAGE_CLASS="standard"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_SERVICE_TYPE = "ClusterIP")' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_STORAGE_CLASS = env(TP_STORAGE_CLASS))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_STORAGE_CLASS_FOR_NFS_SERVER_PROVISIONER = env(TP_STORAGE_CLASS))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_NFS_SERVER_PROVISIONER = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_METRICS_SERVER = true)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_PROVISIONER_UI = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_DB_ENGINE = env(GUI_TP_DB_ENGINE))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_ORACLE_PASSWORD = strenv(GUI_TP_ORACLE_PASSWORD))' "$_recipe_file_name"
        fi

        _recipe_file_name="02-tp-cp-on-prem.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_CP_STORAGE_CLASS = "standard")' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_CP_DB_ENGINE = env(GUI_TP_DB_ENGINE))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_CP_ORACLE_DB_PASSWORD = strenv(GUI_TP_ORACLE_PASSWORD))' "$_recipe_file_name"
        fi

        _recipe_file_name="04-tp-adjust-resource.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TASK_REMOVE_RESOURCES = true)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TASK_SHOW_RESOURCES = false)' "$_recipe_file_name"
        fi

        _recipe_file_name="05-tp-auto-deploy-dp.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_USE_LOCAL_SCRIPT = false)' ${_recipe_file_name}
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_USE_GITHUB_SCRIPT = true)' ${_recipe_file_name}
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_STORAGE_CLASS = env(TP_STORAGE_CLASS))' ${_recipe_file_name}
        fi

        _recipe_file_name="06-tp-o11y-stack.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_STORAGE_CLASS = env(TP_STORAGE_CLASS))' "$_recipe_file_name"
        fi
        break
        ;;
      5)
        echo "Adjusting kubernetes config for kind..."
        _recipe_file_name="01-tp-on-prem.yaml"
        export TP_STORAGE_CLASS="standard"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_SERVICE_TYPE = "ClusterIP")' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_STORAGE_CLASS = env(TP_STORAGE_CLASS))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_STORAGE_CLASS_FOR_NFS_SERVER_PROVISIONER = env(TP_STORAGE_CLASS))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_NFS_SERVER_PROVISIONER = true)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_METRICS_SERVER = true)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_PROVISIONER_UI = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_DB_ENGINE = env(GUI_TP_DB_ENGINE))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_ORACLE_PASSWORD = strenv(GUI_TP_ORACLE_PASSWORD))' "$_recipe_file_name"
        fi

        _recipe_file_name="02-tp-cp-on-prem.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_CP_STORAGE_CLASS = "nfs")' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_CP_DB_ENGINE = env(GUI_TP_DB_ENGINE))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_CP_ORACLE_DB_PASSWORD = strenv(GUI_TP_ORACLE_PASSWORD))' "$_recipe_file_name"
        fi

        _recipe_file_name="04-tp-adjust-resource.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TASK_REMOVE_RESOURCES = true)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TASK_SHOW_RESOURCES = false)' "$_recipe_file_name"
        fi

        _recipe_file_name="05-tp-auto-deploy-dp.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_USE_LOCAL_SCRIPT = false)' ${_recipe_file_name}
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_USE_GITHUB_SCRIPT = true)' ${_recipe_file_name}
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_STORAGE_CLASS = env(TP_STORAGE_CLASS))' ${_recipe_file_name}
        fi

        _recipe_file_name="06-tp-o11y-stack.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_STORAGE_CLASS = env(TP_STORAGE_CLASS))' "$_recipe_file_name"
        fi
        break
        ;;
      0)
        echo "Exiting..."
        break
        ;;
      *)
        # PCP-24040: exit rather than loop; exit, not break (see run.sh).
        echo "Invalid or missing option: '${choice}' - aborting." >&2
        exit 1
        ;;
    esac
  done
}

# main function
function main() {
  adjust_recipes "$@"
}

main "$@"
