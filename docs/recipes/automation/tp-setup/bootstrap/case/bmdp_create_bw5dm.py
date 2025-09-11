# This task will deploy a BW5 domains to the cluster.
import os
from utils.color_logger import ColorLogger
from utils.helper import Helper
from utils.env import ENV
from utils.util import Util

def create_helm_command():
    # Create the helm command for deploying BW5 domains.
    TP_OTEL_TRACES_ENDPOINT = f"http://otel-userapp-traces.{ENV.TP_AUTO_K8S_BMDP_NAME}ns.svc:4318/v1/traces"
    helm_command_str = f"""
helm upgrade --install --create-namespace -n bw5dm bw5dm bw5dm-chart \
  --repo 'https://{ENV.GITHUB_TOKEN}@raw.githubusercontent.com/tibco/cicinfra-integration/gh-pages/' \
  --version '^1.0.0' \
  -f - <<EOF
githubToken: {ENV.GITHUB_TOKEN}
secret:
  enabled: true
ems-server:
  enabled: true
  deployment:
    image:
      tag: "{ENV.TP_BMDP_IMAGE_TAG_EMS}"
    env:
      - name: TIBEMS_LICENSE
        value: "https://{ENV.TP_ACTIVATION_SERVER_CERT_HOSTNAME}:{ENV.TP_ACTIVATION_SERVER_PORT}"
bw5emsdm:
  enabled: true
  deployment:
    image:
      tag: "{ENV.TP_BMDP_IMAGE_TAG_BW5EMSDM}"
    env:
      - name: OTEL_TRACES_ENDPOINT
        value: "{TP_OTEL_TRACES_ENDPOINT}"
      - name: LICENSE_URL
        value: "{ENV.TP_ACTIVATION_URL}"
      - name: ACTIVATION_SERVER_IP
        value: "{ENV.TP_ACTIVATION_SERVER_IP}"
      - name: ACTIVATION_SERVER_HOSTNAME
        value: "{ENV.TP_ACTIVATION_SERVER_CERT_HOSTNAME}"
bw5rvdm:
  enabled: true
  deployment:
    image:
      tag: "{ENV.TP_BMDP_IMAGE_TAG_BW5RVDM}"
    env:
      - name: OTEL_TRACES_ENDPOINT
        value: "{TP_OTEL_TRACES_ENDPOINT}"
      - name: LICENSE_URL
        value: "{ENV.TP_ACTIVATION_URL}"
      - name: ACTIVATION_SERVER_IP
        value: "{ENV.TP_ACTIVATION_SERVER_IP}"
      - name: ACTIVATION_SERVER_HOSTNAME
        value: "{ENV.TP_ACTIVATION_SERVER_CERT_HOSTNAME}"
hawkconsole:
  enabled: true
bw6dm:
  enabled: true
  deployment:
    image:
      tag: "{ENV.TP_BMDP_IMAGE_TAG_BW6DM}"
EOF
"""

    return helm_command_str

# Since the tp-dp-hawk-console pod does not restart automatically now,
# we add a restart command here to ensure that the console works properly.
def restart_hawk_console():
    ColorLogger.info("Restarting Hawk Console")
    helm_command_str = f"kubectl -n {ENV.TP_AUTO_K8S_BMDP_NAMESPACE} rollout restart statefulset tp-dp-hawk-console"
    return Helper.get_command_output(helm_command_str, True)

if __name__ == "__main__":
    if not os.environ.get("GITHUB_TOKEN"):
        ColorLogger.error("Error: GITHUB_TOKEN is not set.")
        exit(1)
    print("GITHUB_TOKEN is set. Proceeding with the script...")

    helm_command = create_helm_command()
    ColorLogger.info(f"Generating shell script in system tmp folder for BW5 domain deployment.")
    script_path = Util.save_command_to_file(helm_command, "bmdp_create_bw5dm.sh")
    ColorLogger.info(f"Script generated at: {script_path}")
    Helper.run_shell_file(script_path)
    ColorLogger.success("BW5 domain deployment script executed successfully.")

    restart_hawk_console_result = restart_hawk_console()
    if restart_hawk_console_result is not None:
        ColorLogger.info("Restart Hawk Console result:" + restart_hawk_console_result)
