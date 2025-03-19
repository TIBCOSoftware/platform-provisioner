#!/bin/bash

#
# © 2025 Cloud Software Group, Inc.
# All Rights Reserved. Confidential & Proprietary.
#

function adjust_ingress() {
  local choice="${1:-""}"
  while true; do
    if [[ -z $choice ]]; then
      echo "Please select an option:"
      echo "1. Adjust for nginx"
      echo "2. Adjust for traefik"
      echo "0. Exit"
      read -rp "Enter your choice (0-2): " choice
    fi

    case $choice in
      1)
        echo "Adjusting ingress for nginx..."
        _recipe_file_name="01-tp-on-prem.yaml"
        export TP_INGRESS_CLASS_NAME="nginx"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_NGINX_INGRESS = true)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_TRAEFIK_INGRESS = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_PROVISIONER_UI_INGRESS_CLASSNAME = env(TP_INGRESS_CLASS_NAME))' "$_recipe_file_name"
        fi

        _recipe_file_name="02-tp-cp-on-prem.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_CP_INGRESS_CLASSNAME = env(TP_INGRESS_CLASS_NAME))' "$_recipe_file_name"
        fi

        _recipe_file_name="03-tp-adjust-dns.yaml"
        export TP_INGRESS_SERVICE_NAME="ingress-nginx-controller.ingress-system.svc.cluster.local"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TARGET_SERVICE = env(TP_INGRESS_SERVICE_NAME))' "$_recipe_file_name"
        fi

        _recipe_file_name="05-tp-auto-deploy-dp.yaml"
        export TP_INGRESS_CONTROLLER_SERVICE_NAME="ingress-nginx-controller"
        export TP_INGRESS_CONTROLLER_SERVICE_NAMESPACE="ingress-system"
        export TP_INGRESS_CONTROLLER_SERVICE_PORT="443:https"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_INGRESS_CONTROLLER = env(TP_INGRESS_CLASS_NAME))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_INGRESS_CONTROLLER_CLASS_NAME = env(TP_INGRESS_CLASS_NAME))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_CONTROLLER_SERVICE_NAME = env(TP_INGRESS_CONTROLLER_SERVICE_NAME))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_CONTROLLER_SERVICE_NAMESPACE = env(TP_INGRESS_CONTROLLER_SERVICE_NAMESPACE))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_CONTROLLER_SERVICE_PORT = env(TP_INGRESS_CONTROLLER_SERVICE_PORT))' "$_recipe_file_name"
        fi

        _recipe_file_name="06-tp-o11y-stack.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_CLASS = env(TP_INGRESS_CLASS_NAME))' "$_recipe_file_name"
        fi

        break
        ;;
      2)
        echo "Adjusting ingress for treafik..."
        _recipe_file_name="01-tp-on-prem.yaml"
        export TP_INGRESS_CLASS_NAME="traefik"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_NGINX_INGRESS = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_TRAEFIK_INGRESS = true)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_PROVISIONER_UI_INGRESS_CLASSNAME = env(TP_INGRESS_CLASS_NAME))' "$_recipe_file_name"
        fi

        _recipe_file_name="02-tp-cp-on-prem.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_CP_INGRESS_CLASSNAME = env(TP_INGRESS_CLASS_NAME))' "$_recipe_file_name"
        fi

        _recipe_file_name="03-tp-adjust-dns.yaml"
        export TP_INGRESS_SERVICE_NAME="traefik.ingress-system.svc.cluster.local"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TARGET_SERVICE = env(TP_INGRESS_SERVICE_NAME))' "$_recipe_file_name"
        fi

        _recipe_file_name="05-tp-auto-deploy-dp.yaml"
        export TP_INGRESS_CONTROLLER_SERVICE_NAME="traefik"
        export TP_INGRESS_CONTROLLER_SERVICE_NAMESPACE="ingress-system"
        export TP_INGRESS_CONTROLLER_SERVICE_PORT="443:websecure"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_INGRESS_CONTROLLER = env(TP_INGRESS_CLASS_NAME))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_INGRESS_CONTROLLER_CLASS_NAME = env(TP_INGRESS_CLASS_NAME))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_CONTROLLER_SERVICE_NAME = env(TP_INGRESS_CONTROLLER_SERVICE_NAME))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_CONTROLLER_SERVICE_NAMESPACE = env(TP_INGRESS_CONTROLLER_SERVICE_NAMESPACE))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_CONTROLLER_SERVICE_PORT = env(TP_INGRESS_CONTROLLER_SERVICE_PORT))' "$_recipe_file_name"
        fi

        _recipe_file_name="06-tp-o11y-stack.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_CLASS = env(TP_INGRESS_CLASS_NAME))' "$_recipe_file_name"
        fi

        break
        ;;
      0)
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
  adjust_ingress "$@"
}

main "$@"

