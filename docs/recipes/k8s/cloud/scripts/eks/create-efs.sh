#!/bin/bash

#
# Copyright (c) 2022 - 2024 TIBCO Software Inc.
# All Rights Reserved. Confidential & Proprietary.
#

#######################################
# create-eks will create eks cluster
# Globals:
#   TP_CLUSTER_NAME: The cluster name
#   TP_STORAGE_CLASS_EFS: The storage class name for EFS
#   TP_INSTALL_RESOURCE_FOLDER: The shared folder to store all generated resource files
#   TP_INSTALL_EFS_VALUES_FILE: The shared file to store chart values for EFS. (full path)
# Arguments:
#   None
# Returns:
#   0 if thing was deleted, non-zero on error
# Notes:
#   yq use version 4
# Samples:
#   None
#######################################

echo "input global variables:"
echo "TP_CLUSTER_NAME: ${TP_CLUSTER_NAME}"
echo "TP_STORAGE_CLASS_EFS: ${TP_STORAGE_CLASS_EFS}"
echo "TP_INSTALL_RESOURCE_FOLDER: ${TP_INSTALL_RESOURCE_FOLDER}"
echo "TP_INSTALL_EFS_VALUES_FILE: ${TP_INSTALL_EFS_VALUES_FILE}"

EFS_ID=$(kubectl get sc "${TP_STORAGE_CLASS_EFS}" -oyaml | yq eval '.parameters.fileSystemId // ""')
if [ "${EFS_ID}" != "" ]; then
  echo "detected EFS_ID: ${EFS_ID} skip creating EFS"
  exit 0
fi

echo "now creating EFS for cluster ${TP_CLUSTER_NAME}"
echo "get basic info"
_vpc_id=$(aws eks describe-cluster --name "${TP_CLUSTER_NAME}" --query "cluster.resourcesVpcConfig.vpcId" --output text)
_cidr_block=$(aws ec2 describe-vpcs --vpc-ids "${_vpc_id}" --query "Vpcs[].CidrBlock" --output text)

echo "setup security group for EFS"
_mount_target_group_name="${TP_CLUSTER_NAME}-EFS-SG"
_mount_target_group_id=$(aws ec2 describe-security-groups --filters Name=group-name,Values="${_mount_target_group_name}" Name=vpc-id,Values="${_vpc_id}" --query "SecurityGroups[*].{Name:GroupName,ID:GroupId}" |  jq --raw-output '.[].ID')
if [ -z "${_mount_target_group_id}" ]; then
  echo "creating SecurityGroup \"${_mount_target_group_id}\" for EFS"
  _mount_target_group_desc="NFS access to EFS from EKS worker nodes"
  _mount_target_group_id=$(aws ec2 create-security-group --group-name "${_mount_target_group_name}" --description "${_mount_target_group_desc}" --vpc-id "${_vpc_id}" | jq --raw-output '.GroupId')
  aws ec2 create-tags --resources "${_mount_target_group_id}" --tags Key=Owner,Value="${TP_CLUSTER_NAME}" Key=Cluster,Value="${TP_CLUSTER_NAME}"
  aws ec2 authorize-security-group-ingress --group-id "${_mount_target_group_id}" --protocol tcp --port 2049 --cidr "${_cidr_block}"
else
  echo "detect security group for EFS ${_mount_target_group_name} already created"
fi

echo "create EFS"
export FILE_SYSTEM_ID=""
FILE_SYSTEM_ID=$(aws efs create-file-system | jq --raw-output '.FileSystemId')
_res=$?
if [ ${_res} -ne 0 ]; then
  echo "create efs error"
  exit ${_res}
fi
aws efs describe-file-systems --file-system-id "${FILE_SYSTEM_ID}"
# adding tag to EFS
aws efs create-tags --file-system-id "${FILE_SYSTEM_ID}" --tags Key=Owner,Value="${TP_CLUSTER_NAME}" Key=Cluster,Value="${TP_CLUSTER_NAME}"

echo "creating mount target"
_tag1="tag:alpha.eksctl.io/cluster-name"
_tag2="tag:kubernetes.io/role/elb"
readarray arr < <(aws ec2 describe-subnets --filters "Name=${_tag1},Values=${TP_CLUSTER_NAME}" "Name=${_tag2},Values=1" | yq -o=j -I=0 '.Subnets[]')
for a in "${arr[@]}"; do
  subnet=$(echo "$a" | yq '.SubnetId')
  echo "creating mount target in " "${subnet}"
  aws efs create-mount-target --file-system-id "${FILE_SYSTEM_ID}" --subnet-id "${subnet}" --security-groups "${_mount_target_group_id}"
done

aws efs describe-mount-targets --file-system-id "${FILE_SYSTEM_ID}" | jq --raw-output '.MountTargets[].LifeCycleState'

echo "use the following EFS id in meta.globalEnvVariable.TP_EFS_ID"
echo "${FILE_SYSTEM_ID}"
# save to values file
mkdir -p "${TP_INSTALL_RESOURCE_FOLDER}"
touch "${TP_INSTALL_EFS_VALUES_FILE}"
yq eval ".storageClass.efs.parameters.fileSystemId = env(FILE_SYSTEM_ID)" "${TP_INSTALL_EFS_VALUES_FILE}" > "${TP_INSTALL_EFS_VALUES_FILE}"_tmp
mv "${TP_INSTALL_EFS_VALUES_FILE}"_tmp "${TP_INSTALL_EFS_VALUES_FILE}"
echo "efs values:"
cat "${TP_INSTALL_EFS_VALUES_FILE}"
