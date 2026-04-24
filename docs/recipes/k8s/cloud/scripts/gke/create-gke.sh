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

if [ -z "${GCP_PROJECT_ID}" ]; then
  echo "Please set GCP_PROJECT_ID environment variable"
  exit 1
fi

if [ -z "${TP_CLUSTER_NAME}" ]; then
  echo "Please set TP_CLUSTER_NAME environment variable"
  exit 1
fi

# default values
export GCP_REGION=${TP_CLUSTER_REGION:-us-west1}
export TP_CLUSTER_VPC_CIDR=${TP_CLUSTER_VPC_CIDR:-"10.0.0.0/20"}
# must be less than /21 otherwise: Cluster CIDR range is greater than maximum (24 > 21)
export TP_CLUSTER_CIDR=${TP_CLUSTER_CIDR:-"10.1.0.0/16"}
export TP_CLUSTER_SERVICE_CIDR=${TP_CLUSTER_SERVICE_CIDR:-"10.2.0.0/20"}
export TP_CLUSTER_PROXY_SUBNET_CIDR=${TP_CLUSTER_PROXY_SUBNET_CIDR:-"10.129.0.0/23"}
export TP_CLUSTER_VERSION=${TP_CLUSTER_VERSION:-"1.35"}
export TP_CLUSTER_INSTANCE_TYPE=${TP_CLUSTER_INSTANCE_TYPE:-"e2-standard-4"}
export TP_CLUSTER_DESIRED_CAPACITY=${TP_CLUSTER_DESIRED_CAPACITY:-"2"}
export TP_GATEWAY_API=${TP_GATEWAY_API:-"disabled"}

# GKE version check: query validMasterVersions from the GKE API for this region.
# Versions in validMasterVersions = standard support, use release-channel "regular".
# Versions NOT in validMasterVersions = extended support (extra cost), use release-channel "extended".
# See: https://cloud.google.com/kubernetes-engine/versioning
# To opt in to extended support, set: TP_ALLOW_EXTENDED_SUPPORT="I_ACKNOWLEDGE_EXTENDED_SUPPORT_COSTS"
_gke_valid_versions=$(gcloud container get-server-config \
  --region "${GCP_REGION}" \
  --project "${GCP_PROJECT_ID}" \
  --format="value(validMasterVersions)" 2>/dev/null || echo "")
_gke_valid_versions=$(echo "${_gke_valid_versions}" | tr ';' '\n')
if [ -z "${_gke_valid_versions}" ]; then
  echo "ERROR: Could not retrieve valid GKE versions for region ${GCP_REGION}."
  echo "  Run: gcloud container get-server-config --region ${GCP_REGION} --project ${GCP_PROJECT_ID}"
  exit 1
fi
# Match on minor version prefix (e.g. "1.33") to cover full patch versions like "1.33.4-gke.100"
_cluster_minor=$(echo "${TP_CLUSTER_VERSION}" | grep -oE '^[0-9]+\.[0-9]+')
_cluster_minor_re="${_cluster_minor//./\\.}"
_gke_release_channel="regular"
if ! echo "${_gke_valid_versions}" | grep -qE "^${_cluster_minor_re}\."; then
  if [ "${TP_ALLOW_EXTENDED_SUPPORT}" != "I_ACKNOWLEDGE_EXTENDED_SUPPORT_COSTS" ]; then
    echo "ERROR: GKE version ${TP_CLUSTER_VERSION} (${_cluster_minor}) was not found in validMasterVersions for region ${GCP_REGION}."
    echo "  It may require extended support (extra cost) via release-channel=extended."
    echo "  Run: gcloud container get-server-config --region ${GCP_REGION} --project ${GCP_PROJECT_ID}"
    echo "  To proceed with extended support, set: TP_ALLOW_EXTENDED_SUPPORT=\"I_ACKNOWLEDGE_EXTENDED_SUPPORT_COSTS\""
    exit 1
  fi
  _gke_release_channel="extended"
  echo "WARNING: GKE version ${TP_CLUSTER_VERSION} is not in standard support. Using release-channel=extended. Additional charges will apply."
else
  echo "GKE version ${TP_CLUSTER_VERSION} found in validMasterVersions for region ${GCP_REGION}."
fi

# add your public ip
# PIPELINE_OUTBOUND_IP_ADDRESS is the outbound ip address of the pipeline engine
AUTHORIZED_IP="${TP_AUTHORIZED_IP:-${PIPELINE_OUTBOUND_IP_ADDRESS}}"
if [ -n "${PIPELINE_OUTBOUND_IP_ADDRESS}" ] && [ -n "${TP_AUTHORIZED_IP}" ]; then
  AUTHORIZED_IP="${TP_AUTHORIZED_IP},${PIPELINE_OUTBOUND_IP_ADDRESS}"
fi

echo "create vpc"
gcloud compute networks create "${TP_CLUSTER_NAME}" \
  --project="${GCP_PROJECT_ID}" \
  --description=TIBCO\ Platform\ VPC \
  --subnet-mode=custom \
  --mtu=1460 \
  --bgp-routing-mode=regional
if [ $? -ne 0 ]; then
  echo "create vpc failed"
  exit 1
fi

echo "create subnet"
gcloud compute networks subnets create "${TP_CLUSTER_NAME}" \
  --network "${TP_CLUSTER_NAME}" \
  --region "${GCP_REGION}" \
  --range "${TP_CLUSTER_VPC_CIDR}"
if [ $? -ne 0 ]; then
  echo "create subnet failed"
  exit 1
fi

if [[ "${TP_GATEWAY_API}" != "disabled" ]]; then
  echo "create proxy subnet"
  gcloud compute networks subnets create "${TP_CLUSTER_NAME}-proxy-subnet" \
    --network "${TP_CLUSTER_NAME}" \
    --region "${GCP_REGION}" \
    --range "${TP_CLUSTER_PROXY_SUBNET_CIDR}" \
    --purpose "REGIONAL_MANAGED_PROXY" \
    --role "ACTIVE"
  if [ $? -ne 0 ]; then
    echo "create proxy subnet failed"
  exit 1
  fi
fi

echo "create firewall rule"
gcloud compute firewall-rules create "${TP_CLUSTER_NAME}" \
  --project="${GCP_PROJECT_ID}" \
  --network=projects/"${GCP_PROJECT_ID}"/global/networks/"${TP_CLUSTER_NAME}" \
  --description=Allows\ connection\ from\ any\ source\ to\ any\ instance\ on\ the\ network\ using\ custom\ protocols. \
  --direction=INGRESS \
  --priority=65534 \
  --source-ranges="${AUTHORIZED_IP}" \
  --action=ALLOW \
  --rules=all
if [ $? -ne 0 ]; then
  echo "create firewall rule failed"
  exit 1
fi

echo "create GKE"
gcloud beta container \
  --project "${GCP_PROJECT_ID}" \
  clusters create "${TP_CLUSTER_NAME}" \
  --region "${GCP_REGION}" \
  --no-enable-basic-auth \
  --cluster-version "${TP_CLUSTER_VERSION}" \
  --release-channel "${_gke_release_channel}" \
  --machine-type "${TP_CLUSTER_INSTANCE_TYPE}" \
  --image-type "COS_CONTAINERD" \
  --disk-type "pd-balanced" \
  --disk-size "50" \
  --metadata disable-legacy-endpoints=true \
  --scopes "https://www.googleapis.com/auth/devstorage.read_only","https://www.googleapis.com/auth/logging.write","https://www.googleapis.com/auth/monitoring","https://www.googleapis.com/auth/servicecontrol","https://www.googleapis.com/auth/service.management.readonly","https://www.googleapis.com/auth/trace.append" \
  --num-nodes "${TP_CLUSTER_DESIRED_CAPACITY}" \
  --monitoring=SYSTEM \
  --enable-ip-alias \
  --gateway-api "${TP_GATEWAY_API}" \
  --network "${TP_CLUSTER_NAME}" \
  --subnetwork "${TP_CLUSTER_NAME}" \
  --cluster-ipv4-cidr "${TP_CLUSTER_CIDR}" \
  --services-ipv4-cidr "${TP_CLUSTER_SERVICE_CIDR}" \
  --no-enable-intra-node-visibility \
  --default-max-pods-per-node "110" \
  --enable-autoscaling \
  --total-min-nodes "0" \
  --total-max-nodes "10" \
  --location-policy "BALANCED" \
  --security-posture=standard \
  --workload-vulnerability-scanning=disabled \
  --enable-master-authorized-networks \
  --master-authorized-networks "${AUTHORIZED_IP}" \
  --addons HorizontalPodAutoscaling,HttpLoadBalancing,GcePersistentDiskCsiDriver,GcpFilestoreCsiDriver \
  --enable-autoupgrade \
  --enable-autorepair \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0 \
  --binauthz-evaluation-mode=DISABLED \
  --no-enable-managed-prometheus \
  --workload-pool "${GCP_PROJECT_ID}.svc.id.goog" \
  --enable-shielded-nodes
