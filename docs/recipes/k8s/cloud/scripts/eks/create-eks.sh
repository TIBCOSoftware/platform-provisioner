#!/bin/bash

#
# Copyright (c) 2022 - 2024 TIBCO Software Inc.
# All Rights Reserved. Confidential & Proprietary.
#

#######################################
# create-eks will create eks cluster
# Globals:
#   TP_CLUSTER_NAME: The cluster name
#   TP_CLUSTER_VERSION: The cluster version
#   TP_CLUSTER_REGION: The cluster region
#   TP_CLUSTER_VPC_CIDR: The VPC CIDR
#   TP_CLUSTER_INSTANCE_TYPE: The instance type
#   TP_CLUSTER_DESIRED_CAPACITY: The desired capacity
#   TP_CLUSTER_ENABLE_NETWORK_POLICY: Use AWS CNI for network policy
# Arguments:
#   None
# Returns:
#   0 if thing was deleted, non-zero on error
# Notes:
#   None
# Samples:
#   None
#######################################

export TP_CLUSTER_NAME=${TP_CLUSTER_NAME:-"tp-cluster"}
export TP_CLUSTER_VERSION=${TP_CLUSTER_VERSION:-"1.28"}
export TP_CLUSTER_REGION=${TP_CLUSTER_REGION:-"us-west-2"}
export TP_CLUSTER_VPC_CIDR=${TP_CLUSTER_VPC_CIDR:-"10.180.0.0/16"}
export TP_CLUSTER_INSTANCE_TYPE=${TP_CLUSTER_INSTANCE_TYPE:-"r5ad.xlarge"}
export TP_CLUSTER_DESIRED_CAPACITY=${TP_CLUSTER_DESIRED_CAPACITY:-"2"}
export TP_CLUSTER_ENABLE_NETWORK_POLICY=${TP_CLUSTER_ENABLE_NETWORK_POLICY:-"true"}

cat >eksctl-config.yaml<<EOF
apiVersion: eksctl.io/v1alpha5
kind: ClusterConfig
metadata:
  name: ${TP_CLUSTER_NAME}
  region: ${TP_CLUSTER_REGION}
  version: "${TP_CLUSTER_VERSION}"
nodeGroups:
  - name: ${TP_CLUSTER_NAME}-ng-1
    instanceType: ${TP_CLUSTER_INSTANCE_TYPE}
    desiredCapacity: ${TP_CLUSTER_DESIRED_CAPACITY}
    # volumeIOPS: 3000
    # volumeThroughput: 125
    volumeSize: 100
    volumeType: gp3
    privateNetworking: true
    iam:
      withAddonPolicies:
        ebs: true
        efs: true
iam:
  withOIDC: true
  serviceAccounts:
    - metadata:
        name: ebs-csi-controller-sa
        namespace: kube-system
      wellKnownPolicies:
        ebsCSIController: true
    - metadata:
        name: efs-csi-controller-sa
        namespace: kube-system
      wellKnownPolicies:
        efsCSIController: true
    - metadata:
        name: aws-load-balancer-controller
        namespace: kube-system
      wellKnownPolicies:
        awsLoadBalancerController: true
    - metadata:
        name: external-dns
        namespace: external-dns-system
      wellKnownPolicies:
        externalDNS: true
    - metadata:
        name: cert-manager
        namespace: cert-manager
      wellKnownPolicies:
        certManager: true
vpc:
  cidr: ${TP_CLUSTER_VPC_CIDR}
  clusterEndpoints:
    privateAccess: true
    publicAccess: true
  publicAccessCIDRs:
    - 0.0.0.0/0
addons:
  - name: vpc-cni # no version is specified so it deploys the default version
    attachPolicyARNs:
      - arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy
    configurationValues: |-
      enableNetworkPolicy: "${TP_CLUSTER_ENABLE_NETWORK_POLICY}"
  - name: kube-proxy
    version: latest
  - name: coredns
    version: latest
  - name: aws-ebs-csi-driver
    wellKnownPolicies:      # add IAM and service account
      ebsCSIController: true
    # disable snapshotter to avoid installing external snapshotter which does not have helm chart and need to install before this addon
    # update addon: eksctl update addon -f config.yaml
    configurationValues: |
      {
        "sidecars":
          {
            "snapshotter":
              {
                "forceEnable": false
              }
          }
      }
  - name: aws-efs-csi-driver
    wellKnownPolicies:      # add IAM and service account
      efsCSIController: true
EOF

echo "create cluster ${TP_CLUSTER_NAME} with eksctl-config.yaml"
cat eksctl-config.yaml
aws eks describe-cluster --name "${TP_CLUSTER_NAME}" &> /dev/null
_res=$?
if [ "${_res}" -ne 0 ]; then
  eksctl create cluster -f eksctl-config.yaml
  _res=$?
  echo "res: ${_res}"
  if [ "${_res}" -ne 0 ]; then
    echo "create cluster: \"${TP_CLUSTER_NAME}\" error"
    exit ${_res}
  fi
  echo "done creating cluster"
else
  echo "detect ${TP_CLUSTER_NAME} already created"
fi
