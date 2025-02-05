#!/bin/bash

#
# © 2025 Cloud Software Group, Inc.
# All Rights Reserved. Confidential & Proprietary.
#

# Create a new Security Context Constraint (SCC) for OpenShift

# see: https://github.com/nginxinc/nginx-ingress-operator/blob/03ff09ae0f26f66175ecdcda1312eb0bba64b276/pkg/controller/nginxingresscontroller/scc.go
oc adm policy add-scc-to-user privileged system:serviceaccount:ingress-system:ingress-nginx-admission
oc adm policy add-scc-to-user privileged system:serviceaccount:ingress-system:ingress-nginx

# for traefik see: https://doc.traefik.io/traefik-enterprise/v1.2/integrating/openshift/
oc adm policy add-scc-to-user privileged system:serviceaccount:ingress-system:traefik
