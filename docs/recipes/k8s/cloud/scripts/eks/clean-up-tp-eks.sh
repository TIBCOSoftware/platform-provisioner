#!/bin/bash

#
# Copyright (c) 2022 - 2024 TIBCO Software Inc.
# All Rights Reserved. Confidential & Proprietary.
#

#######################################
# clean-up-tp-eks will clean up and delete eks cluster
# Globals:
#   TP_CLUSTER_NAME: The cluster name
# Arguments:
#   None
# Returns:
#   0 if thing was deleted, non-zero on error
# Notes:
#   yq use version 4
# Samples:
#   None
#######################################

function remove-ingress() {
    # need to output empty string otherwise will output null
    echo "deleting all ingress objects"
    kubectl delete ingress -A --all

    echo "sleep 2 minutes"
    sleep 120
}

function remove-lb-service() {
    echo "deleting all LoadBalancer services"
    
    # delete only services that actually create AWS Load Balancers
    # this prevents accidentally deleting internal ClusterIP services
    kubectl get svc -A -o yaml | yq -o=j -I=0 '.items[] | select(.spec.type == "LoadBalancer")' |
    while read -r svc; do
        [[ -z "$svc" ]] && continue
        name=$(echo "$svc" | yq '.metadata.name')
        namespace=$(echo "$svc" | yq '.metadata.namespace')
        echo "deleting Service: $name in Namespace: $namespace"
        kubectl delete svc "$name" -n "$namespace" --wait=false
    done

    echo "sleep 3 minutes"
    sleep 180
}

function remove-charts() {
  # separate base charts to delete last
  local base_chart=""
  local base_namespace=""
  echo "deleting all installed charts with no layer labels"
  readarray arr < <(helm ls -a -A -l '!layer' -o yaml | yq -o=j -I=0 '.[]')
  for a in "${arr[@]}"; do
      [[ -z "$a" ]] && continue
      # identity mapping is a single json snippet representing a single entry
      release=$(echo "$a" | yq '.name')
      namespace=$(echo "$a" | yq '.namespace')

      # skip base charts for now, delete them last
      if [[ "$release" == "tibco-cp-base" || "$release" == "platform-base" ]]; then
          base_chart="$release"
          base_namespace="$namespace"
          continue
      fi
      helm uninstall -n "$namespace" "$release"
  done
  
  # delete base chart last if it exists
  if [[ -n "$base_chart" ]]; then
      echo "deleting base chart last: $base_chart"
      helm uninstall -n "$base_namespace" "$base_chart"
  fi

  for (( _chart_layer=2 ; _chart_layer>=0 ; _chart_layer-- ));
  do
    echo "deleting all installed charts with layer ${_chart_layer} labels"
    readarray arr < <(helm ls --selector "layer=${_chart_layer}" -a -A -o yaml | yq -o=j -I=0 '.[]')
    for a in "${arr[@]}"; do
        [[ -z "$a" ]] && continue
        # identity mapping is a single json snippet representing a single entry
        release=$(echo "$a" | yq '.name')
        namespace=$(echo "$a" | yq '.namespace')
        helm uninstall -n "$namespace" "$release"
    done
  done
}

function remove-efs() {
  # delete EFS by tag: Cluster=${TP_CLUSTER_NAME}
  EFS_TAG_VALUE="${TP_CLUSTER_NAME}"
  efs_array=$(aws efs describe-file-systems --query "FileSystems[?Tags[?Key=='Cluster'&&Value=='${EFS_TAG_VALUE}']].FileSystemId" --output yaml | yq -o=j -r -I=0 '.[]')
  readarray -t efs_ids <<< "${efs_array}"
  for _efs_id in "${efs_ids[@]}"; do
    echo "detected EFS_ID: ${_efs_id} now deleting EFS"
    _mount_targets=$(aws efs describe-mount-targets --file-system-id "${_efs_id}" --output yaml | yq -o=j -r -I=0 '.MountTargets[].MountTargetId')
    readarray -t _mount_targets_array <<< "${_mount_targets}"
    for _mount_target in "${_mount_targets_array[@]}"; do
      echo "Deleting Mount Target with ID: ${_mount_target}"
      aws efs delete-mount-target --mount-target-id "${_mount_target}"
    done
    echo "Mount Target deletion is in progress...sleep 2 minutes"
    sleep 120
    aws efs delete-file-system --file-system-id "${_efs_id}"
  done
}

function remove-efs-sg() {
  _efs_sg_ids=$(aws ec2 describe-security-groups --filters "Name=tag:Cluster,Values="${TP_CLUSTER_NAME}"" --query "SecurityGroups[*].{Name:GroupName,ID:GroupId}" | yq -o=j -r -I=0 '.[].ID')
  readarray -t _efs_sg_ids_array <<< "${_efs_sg_ids}"
  for _efs_id in "${_efs_sg_ids_array[@]}"; do
    echo "detected EFS_SG_ID: ${_efs_id} now deleting EFS_SG_ID"
    aws ec2 delete-security-group --group-id "${_efs_id}"
  done
}


function remove-cluster() {
  echo "deleting cluster"
  eksctl delete cluster --name="${TP_CLUSTER_NAME}" --disable-nodegroup-eviction --force
}

function main() {

  if [[ -z ${TP_CLUSTER_NAME} ]]; then
      echo "no cluster name is provided, exiting"
      exit 1
  fi

  remove-ingress
  remove-lb-service
  remove-charts
  remove-efs
  remove-efs-sg
  remove-cluster
}

main
