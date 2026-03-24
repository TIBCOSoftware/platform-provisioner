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
set +x

# delete the tmp file if it already exists
if [ -f tmp_pvc_list.txt ]; then
  echo "removing the existing tmp file"
  rm -rf tmp_pvc_list.txt
fi

echo "Export Global variables"
export TP_AZURE_REGION=${TP_AZURE_REGION:-"eastus"}
export TP_RESOURCE_GROUP=${TP_RESOURCE_GROUP:-"openshift-azure"}
export TP_STORAGE_ACCOUNT_RESOURCE_GROUP="${TP_STORAGE_ACCOUNT_RESOURCE_GROUP}"
export TP_STORAGE_ACCOUNT_NAME=${TP_STORAGE_ACCOUNT_NAME}

# list the persistent volumes in a file
oc get pv -o jsonpath='{range .items[?(@.spec.csi.driver=="file.csi.azure.com")]}{.metadata.name}{"\n"}{end}' >> tmp_pvc_list.txt

echo "deleting resource group"
az group delete -n ${TP_RESOURCE_GROUP} -y

# explicit fileshares deletion is require if it is NOT same as AKS resource group
# otherwise fileshares will be deleted as part of the resource group deletion
if [ -n "${TP_STORAGE_ACCOUNT_RESOURCE_GROUP}" ] && [ "${TP_STORAGE_ACCOUNT_RESOURCE_GROUP}" != "${TP_RESOURCE_GROUP}" ]; then
  echo "deleting file shares"
  while read -r line
    do
      echo "deleting ${line} in storage account ${TP_STORAGE_ACCOUNT_NAME}"
      az storage share delete --name ${line} --delete-snapshots "include" --account-name ${TP_STORAGE_ACCOUNT_NAME}
    done < tmp_pvc_list.txt
fi  

# remove tmp file
rm -rf tmp_pvc_list.txt 