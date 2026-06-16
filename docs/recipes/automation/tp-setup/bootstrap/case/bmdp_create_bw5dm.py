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

# Deploy BW5 domains (ems-server / bw5emsdm / bw5rvdm / bw6dm / hawkconsole)
# from the JFrog-hosted bw5-test chart, using a license-file secret (no
# activation server). Mirrors charts/provisioner-config-local/recipes/tp-deploy-bw5dm.yaml.
import os
from utils.color_logger import ColorLogger
from utils.helper import Helper
from utils.env import ENV
from utils.util import Util

def create_helm_command():
    TP_OTEL_TRACES_ENDPOINT = f"http://otel-userapp-traces.{ENV.TP_AUTO_K8S_BMDP_NAME}ns.svc:4318/v1/traces"
    TP_OTEL_METRICS_ENDPOINT = f"http://otel-userapp-metrics.{ENV.TP_AUTO_K8S_BMDP_NAME}ns.svc:4318/v1/metrics"
    TP_OTEL_LOGS_ENDPOINT = f"http://otel-userapp-logs.{ENV.TP_AUTO_K8S_BMDP_NAME}ns.svc:4318/v1/logs"

    # The JFrog Helm chart and container registry share the same read account.
    chart_repo = ENV.TP_BW5_CHART_REPO
    chart_user = ENV.TP_BW5_CHART_REPO_USER_NAME
    chart_token = ENV.TP_BW5_CHART_REPO_TOKEN
    chart_version = ENV.TP_BW5_CHART_VERSION
    registry = ENV.TP_BW5_CONTAINER_REGISTRY
    repository = ENV.TP_BW5_CONTAINER_REGISTRY_REPOSITORY
    image_base = f"{registry}/{repository}/bw5-test"

    helm_command_str = f"""
helm upgrade --install --create-namespace -n bw5dm bw5dm bw5-test \\
  --repo '{chart_repo}' \\
  --username '{chart_user}' \\
  --password '{chart_token}' \\
  --version '{chart_version}' \\
  -f - <<EOF
global:
  containerRegistry: "{registry}"
  containerRegistryUsername: "{chart_user}"
  containerRegistryPassword: "{chart_token}"
secret:
  enabled: true
ems-server:
  enabled: true
  deployment:
    image:
      repository: "{image_base}"
      tag: "{ENV.TP_BMDP_IMAGE_TAG_EMS}"
    volumeMounts:
      - name: license-secret
        mountPath: /opt/tibco/license-file.bin
        subPath: license-file.bin
        readOnly: true
    volumes:
      - name: license-secret
        secret:
          secretName: activation-file-secret
          optional: true
bw5emsdm:
  enabled: true
  deployment:
    image:
      repository: "{image_base}"
      tag: "{ENV.TP_BMDP_IMAGE_TAG_BW5EMSDM}"
    env:
      - name: OTEL_TRACES_ENDPOINT
        value: "{TP_OTEL_TRACES_ENDPOINT}"
      - name: OTEL_METRICS_ENDPOINT
        value: "{TP_OTEL_METRICS_ENDPOINT}"
      - name: OTEL_LOGS_ENDPOINT
        value: "{TP_OTEL_LOGS_ENDPOINT}"
    volumeMounts:
      - name: license-secret
        mountPath: /opt/tibco/license-file.bin
        subPath: license-file.bin
        readOnly: true
    volumes:
      - name: license-secret
        secret:
          secretName: activation-file-secret
          optional: true
bw5rvdm:
  enabled: true
  deployment:
    image:
      repository: "{image_base}"
      tag: "{ENV.TP_BMDP_IMAGE_TAG_BW5RVDM}"
    env:
      - name: OTEL_TRACES_ENDPOINT
        value: "{TP_OTEL_TRACES_ENDPOINT}"
      - name: OTEL_METRICS_ENDPOINT
        value: "{TP_OTEL_METRICS_ENDPOINT}"
      - name: OTEL_LOGS_ENDPOINT
        value: "{TP_OTEL_LOGS_ENDPOINT}"
    volumeMounts:
      - name: license-secret
        mountPath: /opt/tibco/license-file.bin
        subPath: license-file.bin
        readOnly: true
    volumes:
      - name: license-secret
        secret:
          secretName: activation-file-secret
          optional: true
hawkconsole:
  enabled: true
  deployment:
    image:
      repository: "{image_base}"
bw6dm:
  enabled: true
  deployment:
    image:
      repository: "{image_base}"
      tag: "{ENV.TP_BMDP_IMAGE_TAG_BW6DM}"
    volumeMounts:
      - name: license-secret
        mountPath: /opt/tibco/license-file.bin
        subPath: license-file.bin
        readOnly: true
    volumes:
      - name: license-secret
        secret:
          secretName: activation-file-secret
          optional: true
EOF
"""

    return helm_command_str

# Create the activation license file secret in the bw5dm namespace.
# Mirrors the headless recipe tp-deploy-bw5dm.yaml: BW/EMS pods mount the
# license file from this secret at /opt/tibco/license-file.bin (mount is optional).
def create_activation_file_secret():
    namespace = "bw5dm"
    secret_name = "activation-file-secret"

    # Ensure the namespace exists before creating the secret (idempotent).
    Helper.get_command_output(
        f"kubectl create namespace {namespace} --dry-run=client -o yaml | kubectl apply -f -", True)

    existing_secret = Helper.get_command_output(
        f"kubectl get secret {secret_name} -n {namespace} --ignore-not-found -o name", is_print_error=False)
    if existing_secret and secret_name in existing_secret:
        ColorLogger.success(f"Secret '{secret_name}' already exists in namespace '{namespace}'. Skipping creation.")
        return

    license_file = Helper.get_file_fullpath_in_upload_folder(ENV.TP_ACTIVATION_FILENAME)
    if not os.path.isfile(license_file):
        ColorLogger.warning(f"Activation license file '{license_file}' not found. "
                            f"Skipping secret creation (license mount is optional).")
        return

    ColorLogger.info(f"Creating secret '{secret_name}' in namespace '{namespace}' from '{license_file}'...")
    Helper.get_command_output(
        f"kubectl create secret generic {secret_name} -n {namespace} --from-file=license-file.bin={license_file}", True)
    ColorLogger.success(f"Secret '{secret_name}' created successfully.")

# Since the tp-dp-hawk-console pod does not restart automatically now,
# we add a restart command here to ensure that the console works properly.
def restart_hawk_console():
    ColorLogger.info("Restarting Hawk Console")
    helm_command_str = f"kubectl -n {ENV.TP_AUTO_K8S_BMDP_NAMESPACE} rollout restart statefulset tp-dp-hawk-console"
    return Helper.get_command_output(helm_command_str, True)

if __name__ == "__main__":
    if not ENV.TP_BW5_CHART_REPO_TOKEN:
        ColorLogger.error("Error: TP_BW5_CHART_REPO_TOKEN is not set. "
                          "Set the JFrog token (Helm chart + container registry).")
        exit(1)

    create_activation_file_secret()

    helm_command = create_helm_command()
    ColorLogger.info("Generating shell script in system tmp folder for BW5 domain deployment.")
    script_path = Util.save_command_to_file(helm_command, "bmdp_create_bw5dm.sh")
    ColorLogger.info(f"Script generated at: {script_path}")
    Helper.run_shell_file(script_path)
    ColorLogger.success("BW5 domain deployment script executed successfully.")

    restart_hawk_console_result = restart_hawk_console()
    if restart_hawk_console_result is not None:
        ColorLogger.info("Restart Hawk Console result:" + restart_hawk_console_result)
