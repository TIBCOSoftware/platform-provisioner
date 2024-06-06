#!/bin/bash

#
# Copyright (c) 2024 TIBCO Software Inc.
# All Rights Reserved. Confidential & Proprietary.
#

#######################################
# pre-aks-cluster-script - create pre-requisites for AKS cluster
# Globals:
#   TP_SUBSCRIPTION_ID: azure subscription id
#   TP_AZURE_REGION: azure region 📝
#   TP_RESOURCE_GROUP: resource group name 📝
#   TP_CLUSTER_NAME: aks cluster name. default: dp-aks-cluster 📝
#   TP_USER_ASSIGNED_IDENTITY_NAME: user assigned identity to be associated with cluster
#   TP_DNS_RESOURCE_GROUP: dns resource group name
#   TP_VNET_NAME: virtual network name
#   TP_VNET_CIDR: virtual network cidr
#   TP_AKS_SUBNET_NAME: aks subnet name
#   TP_AKS_SUBNET_CIDR: aks subnet cidr
#   TP_APPLICATION_GW_SUBNET_NAME: application gateway subnet name
#   TP_APPLICATION_GW_SUBNET_CIDR: application gateway subnet cidr
#   TP_PUBLIC_IP_NAME: public ip name
#   TP_NAT_GW_NAME: nat gateway name
#   TP_NAT_GW_SUBNET_NAME: nat gateway subnet name
#   TP_NAT_GW_SUBNET_CIDR: nat gateway subnet cidr
#   TP_APISERVER_SUBNET_NAME: api server subnet name
#   TP_APISERVER_SUBNET_CIDR: api server subnet cidr
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
export TP_RESOURCE_GROUP=${TP_RESOURCE_GROUP:-"dp-resource-group"}
export TP_CLUSTER_NAME=${TP_CLUSTER_NAME:-"dp-aks-cluster"}
export TP_USER_ASSIGNED_IDENTITY_NAME="${TP_CLUSTER_NAME}-identity"
export TP_DNS_RESOURCE_GROUP=${TP_DNS_RESOURCE_GROUP:-"cic-dns"}

export TP_VNET_NAME=${TP_VNET_NAME:-"${TP_CLUSTER_NAME}-vnet"}
export TP_VNET_CIDR=${TP_VNET_CIDR:-"10.4.0.0/16"}
export TP_AKS_SUBNET_NAME=${TP_AKS_SUBNET_NAME:-"${TP_CLUSTER_NAME}-aks-subnet"}
export TP_AKS_SUBNET_CIDR=${TP_AKS_SUBNET_CIDR:-"10.4.0.0/20"}
export TP_APPLICATION_GW_SUBNET_NAME=${TP_APPLICATION_GW_SUBNET_NAME:-"${TP_CLUSTER_NAME}-application-gw-subnet"}
export TP_APPLICATION_GW_SUBNET_CIDR=${TP_APPLICATION_GW_SUBNET_CIDR:-"10.4.17.0/24"}
export TP_PUBLIC_IP_NAME=${TP_PUBLIC_IP_NAME:-"${TP_CLUSTER_NAME}-public-ip"}
export TP_NAT_GW_NAME=${TP_NAT_GW_NAME:-"${TP_CLUSTER_NAME}-nat-gw"}
export TP_NAT_GW_SUBNET_NAME=${TP_NAT_GW_SUBNET_NAME:-"${TP_CLUSTER_NAME}-nat-gw-subnet"}
export TP_NAT_GW_SUBNET_CIDR=${TP_NAT_GW_SUBNET_CIDR:-"10.4.18.0/27"}
export TP_APISERVER_SUBNET_NAME=${TP_APISERVER_SUBNET_NAME:-"${TP_CLUSTER_NAME}-api-server-subnet"}
export TP_APISERVER_SUBNET_CIDR=${TP_APISERVER_SUBNET_CIDR:-"10.4.19.0/28"}


function verify_error() {
  _exit_code="${1}"
  _command="${2}"
  [ "${_exit_code}" -eq "0" ] || { echo "Failed to run the az command to create ${_command}"; exit ${_exit_code}; }
}

# create resource group
az group create --location "${TP_AZURE_REGION}" --name "${TP_RESOURCE_GROUP}"
_ret=$?
verify_error "${_ret}" "resource_group"

# create user-assigned identity
az identity create --name "${TP_USER_ASSIGNED_IDENTITY_NAME}" --resource-group "${TP_RESOURCE_GROUP}"
_ret=$?
verify_error "${_ret}" "identity"
_user_assigned_identity_object_id="$(az identity show --resource-group "${TP_RESOURCE_GROUP}" --name "${TP_USER_ASSIGNED_IDENTITY_NAME}" --query 'principalId' -otsv)"

# add contributor privileged role
# required to create resources
az role assignment create \
  --role "Contributor" \
  --assignee-object-id "${_user_assigned_identity_object_id}" \
  --assignee-principal-type "ServicePrincipal" \
  --scope "/subscriptions/${TP_SUBSCRIPTION_ID}" \
  --description "Allow Contributor access to AKS Managed Identity"
_ret=$?
verify_error "${_ret}" "role_assignment"

# add network contributor permission
# required to join app gateway subnet
az role assignment create \
  --role "Network Contributor" \
  --assignee-object-id "${_user_assigned_identity_object_id}" \
  --assignee-principal-type "ServicePrincipal" \
  --scope "/subscriptions/${TP_SUBSCRIPTION_ID}/resourceGroups/${TP_RESOURCE_GROUP}" \
  --description "Allow Network Contributor access to AKS Managed Identity"
_ret=$?
verify_error "${_ret}" "role_assignment"

# add dns zone contributor permission
# required to create new record sets in dns zone
az role assignment create \
  --role "DNS Zone Contributor" \
  --assignee-object-id "${_user_assigned_identity_object_id}" \
  --assignee-principal-type "ServicePrincipal" \
  --scope "/subscriptions/${TP_SUBSCRIPTION_ID}/resourceGroups/${TP_DNS_RESOURCE_GROUP}" \
  --description "Allow Contributor access to AKS Managed Identity"
_ret=$?
verify_error "${_ret}" "role_assignment"

# create public ip
az network public-ip create -g "${TP_RESOURCE_GROUP}" -n "${TP_PUBLIC_IP_NAME}" --sku "Standard" --allocation-method "Static"
_ret=$?
verify_error "${_ret}" "public_ip"
_public_ip_id="/subscriptions/${TP_SUBSCRIPTION_ID}/resourceGroups/${TP_RESOURCE_GROUP}/providers/Microsoft.Network/publicIPAddresses/${TP_PUBLIC_IP_NAME}"

# create nat gateway
az network nat gateway create --resource-group "${TP_RESOURCE_GROUP}" --name "${TP_NAT_GW_NAME}" --public-ip-addresses "${_public_ip_id}"
_ret=$?
verify_error "${_ret}" "nat_gateway"
_net_gw_id="/subscriptions/${TP_SUBSCRIPTION_ID}/resourceGroups/${TP_RESOURCE_GROUP}/providers/Microsoft.Network/natGateways/${TP_NAT_GW_NAME}"

# create virtual network
az network vnet create -g "${TP_RESOURCE_GROUP}" -n "${TP_VNET_NAME}" --address-prefix "${TP_VNET_CIDR}"
_ret=$?
verify_error "${_ret}" "VNet"

# create application gateway subnets
az network vnet subnet create -g "${TP_RESOURCE_GROUP}" --vnet-name "${TP_VNET_NAME}" -n "${TP_APPLICATION_GW_SUBNET_NAME}" --address-prefixes "${TP_APPLICATION_GW_SUBNET_CIDR}"
_ret=$?
verify_error "${_ret}" "application_gateway_subnet"

# create aks subnet
az network vnet subnet create -g "${TP_RESOURCE_GROUP}" --vnet-name "${TP_VNET_NAME}" -n "${TP_AKS_SUBNET_NAME}" --address-prefixes "${TP_AKS_SUBNET_CIDR}" --nat-gateway "${_net_gw_id}"
_ret=$?
verify_error "${_ret}" "aks_subnet"

# create aks subnet
az network vnet subnet create -g "${TP_RESOURCE_GROUP}" --vnet-name "${TP_VNET_NAME}" -n "${TP_APISERVER_SUBNET_NAME}" --address-prefixes "${TP_APISERVER_SUBNET_CIDR}"
_ret=$?
verify_error "${_ret}" "api_server_subnet"

# create nat gateway subnet
az network vnet subnet create -g "${TP_RESOURCE_GROUP}" --vnet-name "${TP_VNET_NAME}" -n "${TP_NAT_GW_SUBNET_NAME}" --address-prefixes "${TP_NAT_GW_SUBNET_CIDR}" --nat-gateway "${_net_gw_id}"
_ret=$?
verify_error "${_ret}" "nat_gateway_subnet"
export NAT_GW_VNET_SUBNET_ID="/subscriptions/${TP_SUBSCRIPTION_ID}/resourceGroups/${TP_RESOURCE_GROUP}/providers/Microsoft.Network/virtualNetworks/${TP_VNET_NAME}/subnets/${TP_NAT_GW_SUBNET_NAME}"

echo "finished creating pre-requisites for AKS cluster"