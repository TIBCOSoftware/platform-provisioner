account: on-prem
region: eu-west-1
pipeline: generic-runner
content:
  apiVersion: v1
  kind: generic-runner
  meta:
    guiEnv:
      note: config-coredns
      GUI_PIPELINE_LOG_DEBUG: false
      GUI_TARGET_SERVICE: ingress-nginx-controller.ingress-system.svc.cluster.local
      GUI_REGEX_PATTERN_BASE64: KC4qKVwubG9jYWxob3N0XC5kYXRhcGxhbmVzXC5wcm8K
    globalEnvVariable:
      REPLACE_RECIPE: true
      PIPELINE_LOG_DEBUG: ${GUI_PIPELINE_LOG_DEBUG:-false}
      REGEX_PATTERN_BASE64: ${GUI_REGEX_PATTERN_BASE64:-"KC4qKVwubG9jYWxob3N0XC5kYXRhcGxhbmVzXC5wcm8K"}
      TARGET_SERVICE: ${GUI_TARGET_SERVICE:-"ingress-nginx-controller.ingress-system.svc.cluster.local"}
  tasks:
    - condition: true
      clusters:
        - name: ${TP_CLUSTER_NAME}
      script:
        ignoreErrors: false
        fileName: script.sh
        content: |
          #!/bin/bash
          REGEX_PATTERN=$(echo $REGEX_PATTERN_BASE64 | base64 --decode)
          kubectl get configmap coredns -n kube-system -o json | jq --arg regex "$REGEX_PATTERN" --arg target "$TARGET_SERVICE" '
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
          ' > coredns-updated.json


          kubectl apply -f coredns-updated.json

          kubectl rollout restart deployment coredns -n kube-system
