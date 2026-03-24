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

# see: https://github.com/nginxinc/nginx-ingress-operator/blob/03ff09ae0f26f66175ecdcda1312eb0bba64b276/pkg/controller/nginxingresscontroller/scc.go
oc adm policy add-scc-to-user privileged system:serviceaccount:ingress-system:ingress-nginx-admission
oc adm policy add-scc-to-user privileged system:serviceaccount:ingress-system:ingress-nginx

# for traefik see: https://doc.traefik.io/traefik-enterprise/v1.2/integrating/openshift/
oc adm policy add-scc-to-user privileged system:serviceaccount:ingress-system:traefik
