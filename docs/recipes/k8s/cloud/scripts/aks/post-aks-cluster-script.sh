#!/bin/bash

#
# Copyright (c) 2024 TIBCO Software Inc.
# All Rights Reserved. Confidential & Proprietary.
#

#######################################
# pre-aks-cluster-script - create pre-requisites for AKS cluster
# Globals:
#   TP_SUBSCRIPTION_ID: azure subscription id
#   TP_CLUSTER_NAME: aks cluster name 📝
#   TP_RESOURCE_GROUP: resource group name 📝
#   TP_USER_ASSIGNED_IDENTITY_NAME: user assigned identity to be associated with cluster
#   TP_DNS_RESOURCE_GROUP: dns resource group name
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
export TP_AZURE_REGION=${TP_AZURE_REGION:-"eastus"}
export TP_RESOURCE_GROUP=${TP_RESOURCE_GROUP:-"dp-resource-group"}
export TP_CLUSTER_NAME=${TP_CLUSTER_NAME:-"dp-aks-cluster"}
export TP_USER_ASSIGNED_IDENTITY_NAME="${TP_CLUSTER_NAME}-identity"
export TP_TENANT_ID=$(az account show --query tenantId -o tsv)
export KUBECONFIG="${TP_CLUSTER_NAME}.yaml"

# DNS part
export TP_DNS_RESOURCE_GROUP=${TP_DNS_RESOURCE_GROUP:-"cic-dns"}

function verify_error() {
  _exit_code="${1}"
  _command="${2}"
  [ "${_exit_code}" -eq "0" ] || { echo "Failed to run the az command to create ${_command}"; exit ${_exit_code}; }
}

_user_assigned_identity_client_id=$(az aks show --resource-group "${TP_RESOURCE_GROUP}" --name "${TP_CLUSTER_NAME}" --query "identityProfile.kubeletidentity.clientId" --output tsv)

# get oidc issuer
_aks_oidc_issuer="$(az aks show -n ${TP_CLUSTER_NAME} -g "${TP_RESOURCE_GROUP}" --query "oidcIssuerProfile.issuerUrl" -otsv)"

# workload identity federation for cert manager
echo "create federated workload identity federation for ${TP_USER_ASSIGNED_IDENTITY_NAME} in cert-manager/cert-manager"
az identity federated-credential create --name "cert-manager-cert-manager-federated" \
  --resource-group "${TP_RESOURCE_GROUP}" \
  --identity-name "${TP_USER_ASSIGNED_IDENTITY_NAME}" \
  --issuer "${_aks_oidc_issuer}" \
  --subject system:serviceaccount:cert-manager:cert-manager \
  --audience api://AzureADTokenExchange
_ret=$?
verify_error "${_ret}" "create federated workload identity for cert-manager/cert-manager"

# workload identity federation for external dns system
echo "create federated workload identity federation for ${TP_USER_ASSIGNED_IDENTITY_NAME} in external-dns-system/external-dns"
az identity federated-credential create --name "external-dns-system-external-dns-federated" \
  --resource-group "${TP_RESOURCE_GROUP}" \
  --identity-name "${TP_USER_ASSIGNED_IDENTITY_NAME}" \
  --issuer "${_aks_oidc_issuer}" \
  --subject system:serviceaccount:external-dns-system:external-dns \
  --audience api://AzureADTokenExchange
_ret=$?
verify_error "${_ret}" "create federated workload identity for external-dns-system/external-dns"

# external dns configuration
_azure_external_dns_json_file=azure.json

cat <<-EOF > ${_azure_external_dns_json_file}
{
  "tenantId": "${TP_TENANT_ID}",
  "subscriptionId": "${TP_SUBSCRIPTION_ID}",
  "resourceGroup": "${TP_DNS_RESOURCE_GROUP}",
  "useManagedIdentityExtension": true, 
  "userAssignedIdentityID": "${_user_assigned_identity_client_id}"
}
EOF

# connect to cluster
az aks get-credentials --name "${TP_CLUSTER_NAME}" --resource-group "${TP_RESOURCE_GROUP}" --file "${KUBECONFIG}" --overwrite-existing
_ret=$?
verify_error "${_ret}" "generate kubeconfig"

export KUBECONFIG=${KUBECONFIG}

# create namespace and secrets for external-dns-system
kubectl create ns external-dns-system 2> /dev/null
kubectl delete secret --namespace external-dns-system azure-config-file 2> /dev/null
kubectl create secret generic azure-config-file --namespace external-dns-system --from-file ./${_azure_external_dns_json_file} 2> /dev/null

rm -rf ./${_azure_external_dns_json_file}

echo "finished running post-creation scripts of AKS cluster"
