#!/bin/bash

#
# © 2025 Cloud Software Group, Inc.
# All Rights Reserved. Confidential & Proprietary.
#


# Create a new Security Context Constraint (SCC) for OpenShift

function setup-sc() {
  local _namespace=$1
  local _service_account=$2
  oc adm policy add-scc-to-user tp-scc system:serviceaccount:${_namespace}:default
  oc adm policy add-scc-to-user tp-scc system:serviceaccount:${_namespace}:${_service_account}
}

function main() {
  setup-sc "$@"
}

main "$@"