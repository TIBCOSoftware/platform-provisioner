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