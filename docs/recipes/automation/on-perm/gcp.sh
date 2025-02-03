#!/bin/bash

forward_port_to_gcp() {
  echo "Forwarding local port to GCP port"
  ssh-keygen -R "${GCP_INSTANCE_IP}"
  ssh -o "StrictHostKeyChecking no" -A -L ${LOCAL_PORT}:0.0.0.0:${GCP_PORT} -N -i "${KEY_PEM}" ubuntu@"${GCP_INSTANCE_IP}"
  echo "Forward local port ${LOCAL_PORT} to GCP port ${GCP_PORT}"
}

start_gcp_server() {
  local gcp_yaml="gcp-${GCP_INSTANCE_IP}.yaml"
  scp -i "${KEY_PEM}" ubuntu@"${GCP_INSTANCE_IP}":~/.kube/config ~/.kube/"${gcp_yaml}"
  yq eval ".clusters[0].cluster.server |= sub(\"${GCP_PORT}\", \"${LOCAL_PORT}\")" -i ~/.kube/"${gcp_yaml}"
  echo "Copy GCP Kubeconfig to local and change the port from ${GCP_PORT} to ${LOCAL_PORT}"

  export KUBECONFIG=""
  kubectl -n ingress-system patch service ingress-nginx-controller -p '{"spec": {"type": "ClusterIP"}}'
  echo "Disable Local CP Ingress"

  export KUBECONFIG=~/.kube/${gcp_yaml}
  kubectl port-forward -n ingress-system --address 0.0.0.0 service/ingress-nginx-controller 443:https
  echo "GCP Server started"
}

start_local_server() {
  export KUBECONFIG=""
  kubectl -n ingress-system patch service ingress-nginx-controller -p '{"spec": {"type": "LoadBalancer"}}'
  echo "Start Local CP Ingress"
}

copy_gcp_report() {
  set -x
  mkdir -p "./gcp-report/"
  scp -r -o StrictHostKeyChecking=no -i "${KEY_PEM}" ubuntu@"${GCP_INSTANCE_IP}":/home/ubuntu/tp/report ./gcp-report/"${GCP_INSTANCE_IP}"
  set +x
  echo "Copy GCP automation report to local"
}

# Function: Prompt user for GCP_INSTANCE_IP if not defined
prompt_for_gcp_instance_ip() {
  if [ -z "${GCP_INSTANCE_IP}" ]; then
    read -rp "Please enter the GCP_INSTANCE_IP: " GCP_INSTANCE_IP
    if [ -z "${GCP_INSTANCE_IP}" ]; then
      echo "Error: GCP_INSTANCE_IP is required. Exiting."
      exit 1
    fi
  fi
}

create_pem_key() {
  if [ ! -f "${KEY_PEM}" ]; then
    echo "Key file not found, generating a new key '${KEY_PEM}'"
    ssh-keygen -t ed25519 -a 100 -f "$KEY_PEM" -C "tibco@cloud.com" -N "" >/dev/null 2>&1
  fi
  if [ "$1" == "print" ]; then
    base64 -i "$KEY_PEM.pub"
    exit 1
  fi
}

check_pem_key() {
  if [ ! -f "${KEY_PEM}" ]; then
    echo "Key file not found, please run '${0} 0' to generate a new key"
    exit 1
  fi
}

show_help() {
  echo "export GCP_INSTANCE_IP=x.x.x.x"
  echo ""
  echo "Usage: $0 [0|1|2|3|4]"
  echo "0: Create/Print GCP key"
  echo "1: Forward local port to GCP port"
  echo "2: Copy kubeconfig, modify port, and start GCP server"
  echo "3: Start Local server"
  echo "4: Copy GCP automation report to local"
}

export KEY_PEM="${KEY_PEM:-"./gcp"}"
export GCP_INSTANCE_IP="${GCP_INSTANCE_IP:-""}"
export LOCAL_PORT=8443
export GCP_PORT=6443
export KUBECONFIG=""

if [ -z "$1" ]; then
  show_help
  exit 1
fi

case "$1" in
  0)
    echo "Executing Task 0: Create/Print GCP key"
    create_pem_key "print"
    ;;
  1)
    echo "Executing Task 1: Forwarding local port to GCP port"
    check_pem_key

    prompt_for_gcp_instance_ip

    forward_port_to_gcp
    ;;
  2)
    echo "Executing Task 2: Copying kubeconfig, modifying port, and forwarding ingress"
    check_pem_key

    prompt_for_gcp_instance_ip

    start_gcp_server
    ;;
  3)
    echo "Executing Task 3: Start Local server"

    start_local_server
    ;;
  4)
    echo "Executing Task 4: Copy GCP automation report to local"
    check_pem_key

    prompt_for_gcp_instance_ip

    copy_gcp_report
    ;;
  *)
    echo "Invalid option: $1"
    show_help
    exit 1
    ;;
esac
