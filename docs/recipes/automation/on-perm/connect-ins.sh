#!/bin/bash

#
# © 2025 Cloud Software Group, Inc.
# All Rights Reserved. Confidential & Proprietary.
#

#######################################
# connect-ins.sh: this script will connect to the instance and forward the local port to the instance port
# Globals:
#   None
# Arguments:
#   1 - 4: the choice of the task
# Returns:
#   None
# Notes:
#   This is the utility script to connect to the instance and forward the local port to the instance port
# Samples:
#   open in one terminal run: ./connect-ins.sh 1 to setup the ssh port forwarding
#   open in one terminal run: ./connect-ins.sh 2 to setup the kubeconfig and start the instance port-forwarding
#######################################

forward_port_to_instance() {
  echo "Forwarding local port to instance port"
  ssh-keygen -R "${INSTANCE_IP}"
  ssh -o "StrictHostKeyChecking no" -A -L ${LOCAL_PORT}:0.0.0.0:${INS_PORT} -N -i "${KEY_PEM}" ubuntu@"${INSTANCE_IP}"
  echo "Forward local port ${LOCAL_PORT} to instance port ${INS_PORT}"
}

ssh_instance() {
  echo "SSH instance"
  ssh -o "StrictHostKeyChecking no" -i "${KEY_PEM}" ubuntu@"${INSTANCE_IP}"
}

copy_instance_kubeconfig() {
  mkdir -p ~/.kube
  scp -i "${KEY_PEM}" ubuntu@"${INSTANCE_IP}":~/.kube/config ~/.kube/"${INS_KUBECONFIG}"
  echo "Copy Kubeconfig to: $HOME/.kube/${INS_KUBECONFIG}"
  yq eval ".clusters[0].cluster.server |= sub(\"${INS_PORT}\", \"${LOCAL_PORT}\")" -i ~/.kube/"${INS_KUBECONFIG}"
  echo "Copy instance Kubeconfig to local and change the port from ${INS_PORT} to ${LOCAL_PORT}"
}

start_local_server() {
  export KUBECONFIG=""
  kubectl -n "${INGRESS_SERVICE_NAMESPACE_LOCAL}" patch service "${INGRESS_SERVICE_NAME_LOCAL}" -p '{"spec": {"type": "LoadBalancer"}}'
  echo "Start Local CP Ingress"
}

stop_local_server() {
  export KUBECONFIG=""
  kubectl -n "${INGRESS_SERVICE_NAMESPACE_LOCAL}" patch service "${INGRESS_SERVICE_NAME_LOCAL}" -p '{"spec": {"type": "ClusterIP"}}'
  echo "Disable Local CP Ingress"
}

forward_ingress_to_instance() {
  export KUBECONFIG=~/.kube/${INS_KUBECONFIG}
  kubectl port-forward -n "${INGRESS_SERVICE_NAMESPACE_INSTANCE}" --address 0.0.0.0 "service/${INGRESS_SERVICE_NAME_INSTANCE}" "${INGRESS_SERVICE_PORT_INSTANCE}"
  echo "instance Server started"
}

copy_instance_report() {
  set -x
  mkdir -p "./ins-report/"
  scp -r -o StrictHostKeyChecking=no -i "${KEY_PEM}" ubuntu@"${INSTANCE_IP}":/home/ubuntu/tp/report ./ins-report/"${INSTANCE_IP}"
  set +x
  echo "Copy instance automation report to local"
}

# Function: Prompt user for INSTANCE_IP if not defined
prompt_for_instance_ip() {
  if [ -z "${INSTANCE_IP}" ]; then
    read -rp "Please enter the INSTANCE_IP: " INSTANCE_IP
    if [ -z "${INSTANCE_IP}" ]; then
      echo "Error: INSTANCE_IP is required. Exiting."
      exit 1
    fi
    INS_KUBECONFIG="ins-${INSTANCE_IP}.yaml"
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
    echo "or set KEY_PEM to the path of your key file"
    exit 1
  fi
}

show_help() {
  echo "export INSTANCE_IP=x.x.x.x"
  echo "export KEY_PEM=xxx.pem"
  echo "export LOCAL_PORT=8443"
  echo "export INS_PORT=6443"
  echo ""
  echo "Usage: $0 [0|1|2|3|4|5]"
  echo "0: Create/Print instance key"
  echo "1: Forward local port to instance port"
  echo "2: Copy kubeconfig, modify port, and start instance server"
  echo "3: Start Local server"
  echo "4: Copy instance automation report to local"
  echo "5: SSH login to instance"
}

function connect_ins() {
  export KEY_PEM="${KEY_PEM:-"./ins-key.pem"}"
  export INSTANCE_IP="${INSTANCE_IP:-""}"
  export LOCAL_PORT=${LOCAL_PORT:-8443}
  export INS_PORT=${INS_PORT:-6443}
  export KUBECONFIG=""
  export INS_KUBECONFIG="ins-${INSTANCE_IP}.yaml"
  export INGRESS_SERVICE_NAME_LOCAL=${INGRESS_SERVICE_NAME_LOCAL:-"ingress-nginx-controller"}
  export INGRESS_SERVICE_NAMESPACE_LOCAL=${INGRESS_SERVICE_NAMESPACE_LOCAL:-"ingress-system"}
  export INGRESS_SERVICE_NAME_INSTANCE=${INGRESS_SERVICE_NAME_INSTANCE:-"ingress-nginx-controller"} # for nginx ingress use ingress-nginx-controller, for traefik ingress use traefik
  export INGRESS_SERVICE_NAMESPACE_INSTANCE=${INGRESS_SERVICE_NAMESPACE_INSTANCE:-"ingress-system"}
  export INGRESS_SERVICE_PORT_INSTANCE=${INGRESS_SERVICE_PORT_INSTANCE:-"443:https"} # for nginx ingress use 443:https, for traefik ingress use 443:websecure

  if [ -z "$1" ]; then
    show_help
    exit 1
  fi

  case "$1" in
    0)
      echo "Executing Task 0: Create/Print instance key"
      create_pem_key "print"
      ;;
    1)
      echo "Executing Task 1: Forwarding local port to instance port"
      check_pem_key

      prompt_for_instance_ip

      forward_port_to_instance
      ;;
    2)
      echo "Executing Task 2: Copying kubeconfig, modifying port, and forwarding ingress"
      check_pem_key

      prompt_for_instance_ip

      copy_instance_kubeconfig
      stop_local_server
      forward_ingress_to_instance
      ;;
    3)
      echo "Executing Task 3: Start Local server"

      start_local_server
      ;;
    4)
      echo "Executing Task 4: Copy instance automation report to local"
      check_pem_key

      prompt_for_instance_ip

      copy_instance_report
      ;;
    5)
      echo "Executing Task 5: SSH login to instance"
      check_pem_key

      prompt_for_instance_ip

      ssh_instance
      ;;
    *)
      echo "Invalid option: $1"
      show_help
      exit 1
      ;;
  esac
}

# main function
function main() {
  connect_ins "$@"
}

main "$@"
