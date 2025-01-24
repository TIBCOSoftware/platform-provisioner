#!/bin/bash

#
# © 2025 Cloud Software Group, Inc.
# All Rights Reserved. Confidential & Proprietary.
#

# This script will generate the recipe for deploying TP on-prem
function adjust_recipes() {
  local choice="${1:-""}"
  while true; do
    if [[ -z $choice ]]; then
      echo "Please select an option:"
      echo "1. Adjust for k3s"
      echo "2. Adjust for openshift"
      echo "3. Exit"
      read -rp "Enter your choice (1-3): " choice
    fi

    case $choice in
      1)
        echo "Adjusting for k3s..."
        _recipe_file_name="01-tp-on-perm.yaml"
        export TP_STORAGE_CLASS="local-path"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_SERVICE_TYPE = "ClusterIP")' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_STORAGE_CLASS = env(TP_STORAGE_CLASS))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_STORAGE_CLASS_FOR_NFS_SERVER_PROVISIONER = env(TP_STORAGE_CLASS))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_NFS_SERVER_PROVISIONER = true)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_METRICS_SERVER = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_PROVISIONER_UI = false)' "$_recipe_file_name"
        fi

        _recipe_file_name="02-tp-cp-on-perm.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_CP_STORAGE_CLASS = "nfs")' "$_recipe_file_name"
        fi

        _recipe_file_name="04-tp-adjust-resource.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TASK_REMOVE_RESOURCES = false)' "$_recipe_file_name"
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
      2)
        echo "Adjusting for openshift..."
        _recipe_file_name="01-tp-on-perm.yaml"
        export TP_STORAGE_CLASS="crc-csi-hostpath-provisioner"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_SERVICE_TYPE = "ClusterIP")' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_STORAGE_CLASS = env(TP_STORAGE_CLASS))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_STORAGE_CLASS_FOR_NFS_SERVER_PROVISIONER = env(TP_STORAGE_CLASS))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_NFS_SERVER_PROVISIONER = true)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_METRICS_SERVER = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_PROVISIONER_UI = false)' "$_recipe_file_name"
        fi

        _recipe_file_name="02-tp-cp-on-perm.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_CP_STORAGE_CLASS = "nfs")' "$_recipe_file_name"
        fi

        _recipe_file_name="04-tp-adjust-resource.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TASK_REMOVE_RESOURCES = false)' "$_recipe_file_name"
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
        echo "Exiting..."
        break
        ;;
      *)
        echo "Invalid option. Please try again."
        ;;
    esac
  done
}


# main function
function main() {
  adjust_recipes "$@"
}

main "$@"

