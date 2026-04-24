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
# pre-aks-cluster-script - create pre-requisites for AKS cluster
# Globals:
#   TP_SUBSCRIPTION_ID: azure subscription id
#   TP_AZURE_REGION: azure region
#   TP_CLUSTER_NAME: aks cluster name
#   TP_CLUSTER_VERSION: aks cluster version
#   TP_CLUSTER_INSTANCE_TYPE: aks cluster instance type. Standard_D8_v5: 8 vCPUs, 32 GiB memory
#   TP_RESOURCE_GROUP: resource group name
#   TP_USER_ASSIGNED_IDENTITY_NAME: user assigned identity to be associated with cluster
#   TP_AUTHORIZED_IP: authorized ip address access to api server (add your public ip)
#   TP_NETWORK_POLICY: "" # possible values "" (to disable network policy), "azure", "calico"
#   TP_VNET_NAME: virtual network name
#   TP_ADDON_ENABLE_APPLICATION_GW: enable application gateway integration
#   TP_APPLICATION_GW_SUBNET_NAME: application gateway subnet name
#   TP_PUBLIC_IP_NAME: public ip name
#   TP_AKS_SUBNET_NAME: aks subnet name
#   TP_APISERVER_SUBNET_NAME: api server subnet name
#   TP_SERVICE_CIDR: ip range from which to assign service cluster ip. This range must not overlap with any Subnet IP ranges
#   TP_SERVICE_DNS_IP: ip address assigned to the kubernetes dns service. This address must be within the kubernetes service address range
#   TP_AKS_TIER: AKS cluster tier for standard-support versions: "free", "standard" (default), or "premium". LTS forces "premium".
#              Note: "free" tier does not support --k8s-support-plan and has limited SLA/features.
# Arguments:
#   None
# Returns:
#   0 if thing was deleted, non-zero on error
# Notes:
#   None
# Samples:
#   None
#######################################

export TP_SUBSCRIPTION_ID=$(az account show --query id -o tsv)
export TP_AZURE_REGION=${TP_AZURE_REGION:-"westus2"}
export TP_CLUSTER_NAME=${TP_CLUSTER_NAME:-"tp-cluster"}
export TP_CLUSTER_VERSION=${TP_CLUSTER_VERSION:-"1.35"}
export TP_CLUSTER_INSTANCE_TYPE=${TP_CLUSTER_INSTANCE_TYPE:-"Standard_D8_v5"}
export TP_RESOURCE_GROUP=${TP_RESOURCE_GROUP:-"tp-resource-group"}
export TP_USER_ASSIGNED_IDENTITY_NAME="${TP_CLUSTER_NAME}-identity"
export TP_NETWORK_POLICY=${TP_NETWORK_POLICY:-"azure"}
export TP_VNET_NAME=${TP_VNET_NAME:-"${TP_CLUSTER_NAME}-vnet"}
export TP_SERVICE_CIDR=${TP_SERVICE_CIDR:-"10.0.0.0/16"}
export TP_SERVICE_DNS_IP=${TP_SERVICE_DNS_IP:-"10.0.0.10"}
export TP_ADDON_ENABLE_APPLICATION_GW=${TP_ADDON_ENABLE_APPLICATION_GW:-"false"}
export TP_APPLICATION_GW_SUBNET_NAME=${TP_APPLICATION_GW_SUBNET_NAME:-"${TP_CLUSTER_NAME}-application-gw-subnet"}
export TP_PUBLIC_IP_NAME=${TP_PUBLIC_IP_NAME:-"${TP_CLUSTER_NAME}-public-ip"}
export TP_AKS_SUBNET_NAME=${TP_AKS_SUBNET_NAME:-"${TP_CLUSTER_NAME}-aks-subnet"}
export TP_APISERVER_SUBNET_NAME=${TP_APISERVER_SUBNET_NAME:-"${TP_CLUSTER_NAME}-api-server-subnet"}
export TP_AKS_TIER=${TP_AKS_TIER:-"standard"}

# AKS version check: query the support plan for TP_CLUSTER_VERSION from the AKS API.
# KubernetesOfficial = community support (free) | AKSLongTermSupport = extra cost (Premium tier).
# See: https://learn.microsoft.com/en-us/azure/aks/supported-kubernetes-versions
# To opt in to LTS versions, set: TP_ALLOW_EXTENDED_SUPPORT="I_ACKNOWLEDGE_EXTENDED_SUPPORT_COSTS"
_cluster_minor=$(echo "${TP_CLUSTER_VERSION}" | grep -oE '^[0-9]+\.[0-9]+')
_aks_support_plan=$(az aks get-versions --location "${TP_AZURE_REGION}" \
  --query "values[?version=='${_cluster_minor}'].capabilities.supportPlan" \
  -o tsv 2>/dev/null || echo "")
if [ -z "${_aks_support_plan}" ]; then
  echo "ERROR: AKS version ${TP_CLUSTER_VERSION} (${_cluster_minor}) was not found in the supported versions list for region ${TP_AZURE_REGION}."
  echo "  Run: az aks get-versions --location ${TP_AZURE_REGION} --output table"
  exit 1
elif echo "${_aks_support_plan}" | grep -q "AKSLongTermSupport" && ! echo "${_aks_support_plan}" | grep -q "KubernetesOfficial"; then
  # LTS-only: past community support end-of-life, requires Premium tier
  if [ "${TP_ALLOW_EXTENDED_SUPPORT}" != "I_ACKNOWLEDGE_EXTENDED_SUPPORT_COSTS" ]; then
    echo "ERROR: AKS version ${TP_CLUSTER_VERSION} is only available under Long Term Support (LTS)."
    echo "  LTS requires AKS Premium tier and incurs additional charges."
    echo "  To proceed anyway, set: TP_ALLOW_EXTENDED_SUPPORT=\"I_ACKNOWLEDGE_EXTENDED_SUPPORT_COSTS\""
    exit 1
  fi
  echo "WARNING: AKS version ${TP_CLUSTER_VERSION} is LTS-only. Additional charges will apply."
  _aks_support_plan="AKSLongTermSupport"
  _aks_tier="premium"
else
  _aks_support_plan="KubernetesOfficial"
  _aks_tier="${TP_AKS_TIER}"
fi
# --k8s-support-plan is only valid for standard and premium tiers
if [ "${_aks_tier}" != "free" ]; then
  _aks_support_plan_flag="--k8s-support-plan ${_aks_support_plan}"
else
  _aks_support_plan_flag=""
fi
echo "AKS version ${TP_CLUSTER_VERSION} support plan: ${_aks_support_plan}, tier: ${_aks_tier}"

function verify_error() {
  _exit_code="${1}"
  _command="${2}"
  [ "${_exit_code}" -eq "0" ] || { echo "Failed to run the az command to create ${_command}"; exit ${_exit_code}; }
}

# add your public ip
_my_public_ip=$(curl -s https://ipinfo.io/ip)
if [ -n "${TP_AUTHORIZED_IP}" ]; then
  export TP_AUTHORIZED_IP="${TP_AUTHORIZED_IP},${_my_public_ip}"
else
  export TP_AUTHORIZED_IP="${_my_public_ip}"
fi

if [ -n "${TP_NETWORK_POLICY}" ]; then
  _network_policy_parameter=" --network-policy ${TP_NETWORK_POLICY}"
fi

# append nat gateway public ip
_nat_gw_public_ip=$(az network public-ip show -g "${TP_RESOURCE_GROUP}" -n "${TP_PUBLIC_IP_NAME}"  --query 'ipAddress' -otsv)
export TP_AUTHORIZED_IP="${TP_AUTHORIZED_IP},${_nat_gw_public_ip}"

# PIPELINE_OUTBOUND_IP_ADDRESS is the outbound ip address of the pipeline engine
AUTHORIZED_IP="${TP_AUTHORIZED_IP:-${PIPELINE_OUTBOUND_IP_ADDRESS}}"
if [ -n "${PIPELINE_OUTBOUND_IP_ADDRESS}" ] && [ -n "${TP_AUTHORIZED_IP}" ]; then
  AUTHORIZED_IP="${TP_AUTHORIZED_IP},${PIPELINE_OUTBOUND_IP_ADDRESS}"
fi

# set aks identity details
_user_assigned_id="/subscriptions/${TP_SUBSCRIPTION_ID}/resourcegroups/${TP_RESOURCE_GROUP}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/${TP_USER_ASSIGNED_IDENTITY_NAME}"

# set aks vnet details
_aks_vnet_subnet_id="/subscriptions/${TP_SUBSCRIPTION_ID}/resourceGroups/${TP_RESOURCE_GROUP}/providers/Microsoft.Network/virtualNetworks/${TP_VNET_NAME}/subnets/${TP_AKS_SUBNET_NAME}"

# set api server subnet details
_apiserver_subnet_id="/subscriptions/${TP_SUBSCRIPTION_ID}/resourceGroups/${TP_RESOURCE_GROUP}/providers/Microsoft.Network/virtualNetworks/${TP_VNET_NAME}/subnets/${TP_APISERVER_SUBNET_NAME}"

_application_gw_parameter=""
# set application gateway subnet details and other details related to application gateway
if [ "${TP_ADDON_ENABLE_APPLICATION_GW}" == "true" ]; then
  _application_gw_subnet_id="/subscriptions/${TP_SUBSCRIPTION_ID}/resourceGroups/${TP_RESOURCE_GROUP}/providers/Microsoft.Network/virtualNetworks/${TP_VNET_NAME}/subnets/${TP_APPLICATION_GW_SUBNET_NAME}"
  _application_gw_parameter="--enable-addons ingress-appgw --appgw-name ${TP_CLUSTER_NAME}-app-gw --appgw-subnet-id ${_application_gw_subnet_id}"
fi

# create aks cluster
echo "start to create AKS: ${TP_RESOURCE_GROUP}/${TP_CLUSTER_NAME}"
az aks create -g "${TP_RESOURCE_GROUP}" -n "${TP_CLUSTER_NAME}" \
  --node-vm-size "${TP_CLUSTER_INSTANCE_TYPE}" --node-count 1 --min-count 1 --max-count 10 \
  --enable-cluster-autoscaler ${_application_gw_parameter} \
  --enable-msi-auth-for-monitoring false \
  --generate-ssh-keys \
  --api-server-authorized-ip-ranges "${AUTHORIZED_IP}" \
  --enable-oidc-issuer \
  --enable-workload-identity \
  --network-plugin azure${_network_policy_parameter} \
  --kubernetes-version "${TP_CLUSTER_VERSION}" \
  --tier "${_aks_tier}" \
  ${_aks_support_plan_flag} \
  --outbound-type userAssignedNATGateway \
  --vnet-subnet-id "${_aks_vnet_subnet_id}" \
  --service-cidr "${TP_SERVICE_CIDR}" \
  --dns-service-ip "${TP_SERVICE_DNS_IP}" \
  --enable-apiserver-vnet-integration \
  --apiserver-subnet-id "${_apiserver_subnet_id}" \
  --assign-identity "${_user_assigned_id}" \
  --assign-kubelet-identity "${_user_assigned_id}"
_ret=$?
verify_error "${_ret}" "cluster"

echo "finished creating AKS cluster"