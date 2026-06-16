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

function adjust_ingress() {
  local choice="${1:-""}"
  while true; do
    if [[ -z $choice ]]; then
      echo "Please select an option:"
      echo "1. Adjust for nginx"
      echo "2. Adjust for traefik"
      echo "3. Adjust for nginx gateway fabric"
      echo "4. Adjust for haproxy"
      echo "5. Adjust for istio gateway"
      echo "6. Adjust for traefik gateway"
      echo "7. Adjust for netscaler cpx gateway controller"
      echo "0. Exit"
      read -rp "Enter your choice (0-7): " choice
    fi

    case $choice in
      1)
        echo "Adjusting ingress for nginx..."
        _recipe_file_name="01-tp-on-prem.yaml"
        export TP_INGRESS_CLASS_NAME="nginx"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_NGINX_INGRESS = true)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_TRAEFIK_INGRESS = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_NGINX_GATEWAY = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_HAPROXY_INGRESS = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_ISTIO_GATEWAY = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_TRAEFIK_GATEWAY = false)' "$_recipe_file_name"
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

        _recipe_file_name="07-tp-bw5-stack.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_CLASS = env(TP_INGRESS_CLASS_NAME))' "$_recipe_file_name"
        fi

        break
        ;;
      2)
        echo "Adjusting ingress for traefik..."
        _recipe_file_name="01-tp-on-prem.yaml"
        export TP_INGRESS_CLASS_NAME="traefik"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_NGINX_INGRESS = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_TRAEFIK_INGRESS = true)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_NGINX_GATEWAY = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_HAPROXY_INGRESS = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_ISTIO_GATEWAY = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_TRAEFIK_GATEWAY = false)' "$_recipe_file_name"
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

        _recipe_file_name="07-tp-bw5-stack.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_CLASS = env(TP_INGRESS_CLASS_NAME))' "$_recipe_file_name"
        fi

        break
        ;;
      3)
        echo "Adjusting ingress for nginx gateway fabric..."
        _recipe_file_name="01-tp-on-prem.yaml"
        export TP_GATEWAY_NAME="nginx-gateway"
        export TP_AUTO_INGRESS_CONTROLLER="nginx"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_NGINX_INGRESS = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_TRAEFIK_INGRESS = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_NGINX_GATEWAY = true)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_TRAEFIK_GATEWAY = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_OBJECT = "gateway")' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_GATEWAY_NAME = env(TP_GATEWAY_NAME))' "$_recipe_file_name"
        fi

        _recipe_file_name="02-tp-cp-on-prem.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_GATEWAY_NAME = env(TP_GATEWAY_NAME))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_OBJECT = "gateway")' "$_recipe_file_name"
          # PCP-19615: the AI agent backend (agent-cp-only) has no gatewayRoute under gateway-API ingress,
          # so tenant provisioning cannot reach it. Disable the AI agent when a gateway is selected.
          yq eval -i '(.meta.guiEnv.GUI_CP_INSTALL_PLATFORM_AI_AGENT = false)' "$_recipe_file_name"
        fi

        _recipe_file_name="03-tp-adjust-dns.yaml"
        export TP_INGRESS_SERVICE_NAME="nginx-gateway-nginx.ingress-system.svc.cluster.local"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TARGET_SERVICE = env(TP_INGRESS_SERVICE_NAME))' "$_recipe_file_name"
        fi

        _recipe_file_name="05-tp-auto-deploy-dp.yaml"
        export TP_INGRESS_CONTROLLER_SERVICE_NAME="nginx-gateway-nginx"
        export TP_INGRESS_CONTROLLER_SERVICE_NAMESPACE="ingress-system"
        export TP_INGRESS_CONTROLLER_SERVICE_PORT="443:https"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_CONTROLLER_SERVICE_NAME = env(TP_INGRESS_CONTROLLER_SERVICE_NAME))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_CONTROLLER_SERVICE_NAMESPACE = env(TP_INGRESS_CONTROLLER_SERVICE_NAMESPACE))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_CONTROLLER_SERVICE_PORT = env(TP_INGRESS_CONTROLLER_SERVICE_PORT))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_INGRESS_OBJECT = "gateway")' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_INGRESS_CONTROLLER = env(TP_AUTO_INGRESS_CONTROLLER))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_GATEWAY_NAME = env(TP_GATEWAY_NAME))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_GATEWAY_NAMESPACE = env(TP_INGRESS_CONTROLLER_SERVICE_NAMESPACE))' "$_recipe_file_name"
        fi

        _recipe_file_name="06-tp-o11y-stack.yaml"
        export TP_O11Y_INGRESS_GATEWAY_SELECTION="gateway"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_GATEWAY_NAME = env(TP_GATEWAY_NAME))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_O11Y_INGRESS_GATEWAY_SELECTION = env(TP_O11Y_INGRESS_GATEWAY_SELECTION))' "$_recipe_file_name"
        fi

        _recipe_file_name="07-tp-bw5-stack.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_OBJECT = "gateway")' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_GATEWAY_NAME = env(TP_GATEWAY_NAME))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_GATEWAY_NAMESPACE = env(TP_INGRESS_CONTROLLER_SERVICE_NAMESPACE))' "$_recipe_file_name"
        fi

        break
        ;;
      4)
        echo "Adjusting ingress for haproxy..."
        _recipe_file_name="01-tp-on-prem.yaml"
        export TP_INGRESS_CLASS_NAME="haproxy"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_NGINX_INGRESS = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_TRAEFIK_INGRESS = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_NGINX_GATEWAY = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_HAPROXY_INGRESS = true)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_ISTIO_GATEWAY = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_TRAEFIK_GATEWAY = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_PROVISIONER_UI_INGRESS_CLASSNAME = env(TP_INGRESS_CLASS_NAME))' "$_recipe_file_name"
        fi

        _recipe_file_name="02-tp-cp-on-prem.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_CP_INGRESS_CLASSNAME = env(TP_INGRESS_CLASS_NAME))' "$_recipe_file_name"
        fi

        _recipe_file_name="03-tp-adjust-dns.yaml"
        export TP_INGRESS_SERVICE_NAME="haproxy-ingress-kubernetes-ingress.ingress-system.svc.cluster.local"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TARGET_SERVICE = env(TP_INGRESS_SERVICE_NAME))' "$_recipe_file_name"
        fi

        _recipe_file_name="05-tp-auto-deploy-dp.yaml"
        export TP_INGRESS_CONTROLLER_SERVICE_NAME="haproxy-ingress-kubernetes-ingress"
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

        _recipe_file_name="07-tp-bw5-stack.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_CLASS = env(TP_INGRESS_CLASS_NAME))' "$_recipe_file_name"
        fi

        break
        ;;
      5) 
        echo "Adjusting ingress for istio gateway..."
        _recipe_file_name="01-tp-on-prem.yaml"
        export TP_GATEWAY_NAME="istio-gateway"
        export TP_AUTO_INGRESS_CONTROLLER="Istio"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_NGINX_INGRESS = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_TRAEFIK_INGRESS = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_NGINX_GATEWAY = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_HAPROXY_INGRESS = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_ISTIO_GATEWAY = true)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_TRAEFIK_GATEWAY = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_OBJECT = "gateway")' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_GATEWAY_NAME = env(TP_GATEWAY_NAME))' "$_recipe_file_name"
        fi

        _recipe_file_name="02-tp-cp-on-prem.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_GATEWAY_NAME = env(TP_GATEWAY_NAME))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_OBJECT = "gateway")' "$_recipe_file_name"
          # PCP-19615: the AI agent backend (agent-cp-only) has no gatewayRoute under gateway-API ingress,
          # so tenant provisioning cannot reach it. Disable the AI agent when a gateway is selected.
          yq eval -i '(.meta.guiEnv.GUI_CP_INSTALL_PLATFORM_AI_AGENT = false)' "$_recipe_file_name"
        fi

        _recipe_file_name="03-tp-adjust-dns.yaml"
        export TP_INGRESS_SERVICE_NAME="istio-gateway-istio.ingress-system.svc.cluster.local"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TARGET_SERVICE = env(TP_INGRESS_SERVICE_NAME))' "$_recipe_file_name"
        fi

        _recipe_file_name="05-tp-auto-deploy-dp.yaml"
        export TP_INGRESS_CONTROLLER_SERVICE_NAME="istio-gateway-istio"
        export TP_INGRESS_CONTROLLER_SERVICE_NAMESPACE="ingress-system"
        export TP_INGRESS_CONTROLLER_SERVICE_PORT="443:https"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_CONTROLLER_SERVICE_NAME = env(TP_INGRESS_CONTROLLER_SERVICE_NAME))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_CONTROLLER_SERVICE_NAMESPACE = env(TP_INGRESS_CONTROLLER_SERVICE_NAMESPACE))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_CONTROLLER_SERVICE_PORT = env(TP_INGRESS_CONTROLLER_SERVICE_PORT))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_INGRESS_OBJECT = "gateway")' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_INGRESS_CONTROLLER = env(TP_AUTO_INGRESS_CONTROLLER))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_GATEWAY_NAME = env(TP_GATEWAY_NAME))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_GATEWAY_NAMESPACE = env(TP_INGRESS_CONTROLLER_SERVICE_NAMESPACE))' "$_recipe_file_name"
        fi

        _recipe_file_name="06-tp-o11y-stack.yaml"
        export TP_O11Y_INGRESS_GATEWAY_SELECTION="gateway"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_GATEWAY_NAME = env(TP_GATEWAY_NAME))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_O11Y_INGRESS_GATEWAY_SELECTION = env(TP_O11Y_INGRESS_GATEWAY_SELECTION))' "$_recipe_file_name"
        fi

        _recipe_file_name="07-tp-bw5-stack.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_OBJECT = "gateway")' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_GATEWAY_NAME = env(TP_GATEWAY_NAME))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_GATEWAY_NAMESPACE = env(TP_INGRESS_CONTROLLER_SERVICE_NAMESPACE))' "$_recipe_file_name"
        fi

        break
        ;;
      6)
        echo "Adjusting ingress for traefik gateway..."
        _recipe_file_name="01-tp-on-prem.yaml"
        export TP_GATEWAY_NAME="traefik-gateway"
        export TP_AUTO_INGRESS_CONTROLLER="traefik"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_NGINX_INGRESS = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_TRAEFIK_INGRESS = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_NGINX_GATEWAY = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_HAPROXY_INGRESS = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_ISTIO_GATEWAY = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_TRAEFIK_GATEWAY = true)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_OBJECT = "gateway")' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_GATEWAY_NAME = env(TP_GATEWAY_NAME))' "$_recipe_file_name"
        fi

        _recipe_file_name="02-tp-cp-on-prem.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_GATEWAY_NAME = env(TP_GATEWAY_NAME))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_OBJECT = "gateway")' "$_recipe_file_name"
          # PCP-19615: the AI agent backend (agent-cp-only) has no gatewayRoute under gateway-API ingress,
          # so tenant provisioning cannot reach it. Disable the AI agent when a gateway is selected.
          yq eval -i '(.meta.guiEnv.GUI_CP_INSTALL_PLATFORM_AI_AGENT = false)' "$_recipe_file_name"
        fi

        _recipe_file_name="03-tp-adjust-dns.yaml"
        export TP_INGRESS_SERVICE_NAME="traefik-gateway.ingress-system.svc.cluster.local"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TARGET_SERVICE = env(TP_INGRESS_SERVICE_NAME))' "$_recipe_file_name"
        fi

        _recipe_file_name="05-tp-auto-deploy-dp.yaml"
        export TP_INGRESS_CONTROLLER_SERVICE_NAME="traefik-gateway"
        export TP_INGRESS_CONTROLLER_SERVICE_NAMESPACE="ingress-system"
        export TP_INGRESS_CONTROLLER_SERVICE_PORT="8443:websecure"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_CONTROLLER_SERVICE_NAME = env(TP_INGRESS_CONTROLLER_SERVICE_NAME))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_CONTROLLER_SERVICE_NAMESPACE = env(TP_INGRESS_CONTROLLER_SERVICE_NAMESPACE))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_CONTROLLER_SERVICE_PORT = env(TP_INGRESS_CONTROLLER_SERVICE_PORT))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_INGRESS_OBJECT = "gateway")' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_INGRESS_CONTROLLER = env(TP_AUTO_INGRESS_CONTROLLER))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_GATEWAY_NAME = env(TP_GATEWAY_NAME))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_GATEWAY_NAMESPACE = env(TP_INGRESS_CONTROLLER_SERVICE_NAMESPACE))' "$_recipe_file_name"
        fi

        _recipe_file_name="06-tp-o11y-stack.yaml"
        export TP_O11Y_INGRESS_GATEWAY_SELECTION="gateway"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_GATEWAY_NAME = env(TP_GATEWAY_NAME))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_O11Y_INGRESS_GATEWAY_SELECTION = env(TP_O11Y_INGRESS_GATEWAY_SELECTION))' "$_recipe_file_name"
        fi

        _recipe_file_name="07-tp-bw5-stack.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_OBJECT = "gateway")' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_GATEWAY_NAME = env(TP_GATEWAY_NAME))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_GATEWAY_NAMESPACE = env(TP_INGRESS_CONTROLLER_SERVICE_NAMESPACE))' "$_recipe_file_name"
        fi

        break
        ;;
      7)
        echo "Adjusting ingress for netscaler cpx gateway controller..."
        # NOTE: NetScaler CPX gateway controller chart is NOT yet wired into tp-base-on-prem.yaml
        # (PCP-18628 only added it to deploy-tp-eks.yaml for EKS). For on-prem usage you must
        # install netscaler-cpx-with-gateway-controller manually before selecting this option.
        _recipe_file_name="01-tp-on-prem.yaml"
        export TP_GATEWAY_NAME="netscalercpx-gateway"
        export TP_AUTO_INGRESS_CONTROLLER="netscaler"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_NGINX_INGRESS = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_TRAEFIK_INGRESS = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_NGINX_GATEWAY = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_HAPROXY_INGRESS = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_ISTIO_GATEWAY = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INSTALL_TRAEFIK_GATEWAY = false)' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_OBJECT = "gateway")' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_GATEWAY_NAME = env(TP_GATEWAY_NAME))' "$_recipe_file_name"
        fi

        _recipe_file_name="02-tp-cp-on-prem.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_GATEWAY_NAME = env(TP_GATEWAY_NAME))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_OBJECT = "gateway")' "$_recipe_file_name"
          # PCP-19615: the AI agent backend (agent-cp-only) has no gatewayRoute under gateway-API ingress,
          # so tenant provisioning cannot reach it. Disable the AI agent when a gateway is selected.
          yq eval -i '(.meta.guiEnv.GUI_CP_INSTALL_PLATFORM_AI_AGENT = false)' "$_recipe_file_name"
        fi

        _recipe_file_name="03-tp-adjust-dns.yaml"
        export TP_INGRESS_SERVICE_NAME="cpx-gateway-controller-cpx-service.ingress-system.svc.cluster.local"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TARGET_SERVICE = env(TP_INGRESS_SERVICE_NAME))' "$_recipe_file_name"
        fi

        _recipe_file_name="05-tp-auto-deploy-dp.yaml"
        export TP_INGRESS_CONTROLLER_SERVICE_NAME="cpx-gateway-controller-cpx-service"
        export TP_INGRESS_CONTROLLER_SERVICE_NAMESPACE="ingress-system"
        export TP_INGRESS_CONTROLLER_SERVICE_PORT="443:https"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_CONTROLLER_SERVICE_NAME = env(TP_INGRESS_CONTROLLER_SERVICE_NAME))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_CONTROLLER_SERVICE_NAMESPACE = env(TP_INGRESS_CONTROLLER_SERVICE_NAMESPACE))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_CONTROLLER_SERVICE_PORT = env(TP_INGRESS_CONTROLLER_SERVICE_PORT))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_INGRESS_OBJECT = "gateway")' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_INGRESS_CONTROLLER = env(TP_AUTO_INGRESS_CONTROLLER))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_GATEWAY_NAME = env(TP_GATEWAY_NAME))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_AUTO_GATEWAY_NAMESPACE = env(TP_INGRESS_CONTROLLER_SERVICE_NAMESPACE))' "$_recipe_file_name"
        fi

        _recipe_file_name="06-tp-o11y-stack.yaml"
        export TP_O11Y_INGRESS_GATEWAY_SELECTION="gateway"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_GATEWAY_NAME = env(TP_GATEWAY_NAME))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_O11Y_INGRESS_GATEWAY_SELECTION = env(TP_O11Y_INGRESS_GATEWAY_SELECTION))' "$_recipe_file_name"
        fi

        _recipe_file_name="07-tp-bw5-stack.yaml"
        if [[ -f "${_recipe_file_name}" ]]; then
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_OBJECT = "gateway")' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_GATEWAY_NAME = env(TP_GATEWAY_NAME))' "$_recipe_file_name"
          yq eval -i '(.meta.guiEnv.GUI_TP_INGRESS_GATEWAY_NAMESPACE = env(TP_INGRESS_CONTROLLER_SERVICE_NAMESPACE))' "$_recipe_file_name"
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

