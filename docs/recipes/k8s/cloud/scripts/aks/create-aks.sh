#!/bin/bash

#
# Copyright (c) 2024 TIBCO Software Inc.
# All Rights Reserved. Confidential & Proprietary.
#

#######################################
# pre-aks-cluster-script - create pre-requisites for AKS cluster
# Globals:
#   TP_SUBSCRIPTION_ID: azure subscription id
#   TP_CLUSTER_NAME: aks cluster name
#   TP_CLUSTER_VERSION: aks cluster version
#   TP_CLUSTER_INSTANCE_TYPE: aks cluster instance type. Standard_D8_v5: 8 vCPUs, 32 GiB memory
#   TP_RESOURCE_GROUP: resource group name
#   TP_USER_ASSIGNED_IDENTITY_NAME: user assigned identity to be associated with cluster
#   TP_AUTHORIZED_IP: authorized ip address access to api server (add your public ip)
#   TP_NETWORK_POLICY: "" # possible values "" (to disable network policy), "azure", "calico"
#   TP_VNET_NAME: virtual network name
#   TP_APPLICATION_GW_SUBNET_NAME: application gateway subnet name
#   TP_PUBLIC_IP_NAME: public ip name
#   TP_AKS_SUBNET_NAME: aks subnet name
#   TP_APISERVER_SUBNET_NAME: api server subnet name
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
export TP_CLUSTER_NAME=${TP_CLUSTER_NAME:-"tp-cluster"}
export TP_CLUSTER_VERSION=${TP_CLUSTER_VERSION:-"1.29"}
export TP_CLUSTER_INSTANCE_TYPE=${TP_CLUSTER_INSTANCE_TYPE:-"Standard_D8_v5"}
export TP_RESOURCE_GROUP=${TP_RESOURCE_GROUP:-"tp-resource-group"}
export TP_USER_ASSIGNED_IDENTITY_NAME="${TP_CLUSTER_NAME}-identity"
export TP_NETWORK_POLICY=${TP_NETWORK_POLICY:-"azure"}
export TP_VNET_NAME=${TP_VNET_NAME:-"${TP_CLUSTER_NAME}-vnet"}
export TP_APPLICATION_GW_SUBNET_NAME=${TP_APPLICATION_GW_SUBNET_NAME:-"${TP_CLUSTER_NAME}-application-gw-subnet"}
export TP_PUBLIC_IP_NAME=${TP_PUBLIC_IP_NAME:-"${TP_CLUSTER_NAME}-public-ip"}
export TP_AKS_SUBNET_NAME=${TP_AKS_SUBNET_NAME:-"${TP_CLUSTER_NAME}-aks-subnet"}
export TP_APISERVER_SUBNET_NAME=${TP_APISERVER_SUBNET_NAME:-"${TP_CLUSTER_NAME}-api-server-subnet"}

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
_nat_gw_public_ip=$(az network public-ip show -g ${TP_RESOURCE_GROUP} -n ${TP_PUBLIC_IP_NAME}  --query 'ipAddress' -otsv)
export TP_AUTHORIZED_IP="${TP_AUTHORIZED_IP},${_nat_gw_public_ip}"

# set aks identity details
_user_assigned_id="/subscriptions/${TP_SUBSCRIPTION_ID}/resourcegroups/${TP_RESOURCE_GROUP}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/${TP_USER_ASSIGNED_IDENTITY_NAME}"

# set aks vnet details
_aks_vnet_subnet_id="/subscriptions/${TP_SUBSCRIPTION_ID}/resourceGroups/${TP_RESOURCE_GROUP}/providers/Microsoft.Network/virtualNetworks/${TP_VNET_NAME}/subnets/${TP_AKS_SUBNET_NAME}"

# set application gateway subnet details
_application_gw_subnet_id="/subscriptions/${TP_SUBSCRIPTION_ID}/resourceGroups/${TP_RESOURCE_GROUP}/providers/Microsoft.Network/virtualNetworks/${TP_VNET_NAME}/subnets/${TP_APPLICATION_GW_SUBNET_NAME}"

# set api server subnet details
_apiserver_subnet_id="/subscriptions/${TP_SUBSCRIPTION_ID}/resourceGroups/${TP_RESOURCE_GROUP}/providers/Microsoft.Network/virtualNetworks/${TP_VNET_NAME}/subnets/${TP_APISERVER_SUBNET_NAME}"

# create aks cluster
echo "start to create AKS: ${TP_RESOURCE_GROUP}/${TP_CLUSTER_NAME}"
az aks create -g "${TP_RESOURCE_GROUP}" -n "${TP_CLUSTER_NAME}" \
  --node-count 1 \
  --enable-cluster-autoscaler \
  --min-count 1 \
  --max-count 10 \
  --enable-addons ingress-appgw \
  --enable-msi-auth-for-monitoring false \
  --generate-ssh-keys \
  --api-server-authorized-ip-ranges "${TP_AUTHORIZED_IP}" \
  --enable-oidc-issuer \
  --enable-workload-identity \
  --network-plugin azure${_network_policy_parameter} \
  --kubernetes-version "${TP_CLUSTER_VERSION}" \
  --outbound-type userAssignedNATGateway \
  --appgw-name gateway \
  --vnet-subnet-id "${_aks_vnet_subnet_id}" \
  --appgw-subnet-id "${_application_gw_subnet_id}" \
  --enable-apiserver-vnet-integration \
  --apiserver-subnet-id "${_apiserver_subnet_id}" \
  --assign-identity "${_user_assigned_id}" \
  --assign-kubelet-identity "${_user_assigned_id}"
_ret=$?
verify_error "${_ret}" "cluster"

echo "finished creating AKS cluster"