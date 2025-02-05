#!/bin/bash

#
# © 2025 Cloud Software Group, Inc.
# All Rights Reserved. Confidential & Proprietary.
#

# scale down so will not update dns config
kubectl scale deployment dns-operator --replicas=0 -n openshift-dns-operator
# this operator will scale dns operator back
kubectl scale deployment cluster-version-operator --replicas=0 -n openshift-cluster-version

export REGEX_PATTERN_BASE64="KC4qKVwubG9jYWxob3N0XC5kYXRhcGxhbmVzXC5wcm8K"
export TARGET_SERVICE="ingress-nginx-controller.ingress-system.svc.cluster.local"
REGEX_PATTERN=$(echo $REGEX_PATTERN_BASE64 | base64 --decode)
kubectl get configmap dns-default -n openshift-dns -o json | jq --arg regex "$REGEX_PATTERN" --arg target "$TARGET_SERVICE" '
.data.Corefile |=
if (. | test("rewrite name regex \\Q" + $regex + "\\E " + $target)) then
  # If the rewrite rule already exists, leave the Corefile unchanged
  .
else
  # If the rewrite rule does not exist, insert it after the "ready" line
  (split("\n") | map(
    if test("^\\s*ready") then
      . + "\n    rewrite name regex " + $regex + " " + $target
    else
      .
    end
  ) | join("\n"))
end
' > oc-dns-updated.json

kubectl apply -f oc-dns-updated.json

kubectl rollout restart daemonset dns-default -n openshift-dns
