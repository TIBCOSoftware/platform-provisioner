# This task will deploy a BW5 domains to the cluster.
import sys
from utils.color_logger import ColorLogger
from utils.helper import Helper
from utils.util import Util

def delete_bw5dm_command():
    # Create the helm command for uninstalling BW5 domains
    helm_command_str = (f"helm uninstall -n bw5dm bw5dm \n"
        "kubectl delete namespace bw5dm")
    return helm_command_str

def check_bw5dm_status():
    # Check if BW5 domain is deployed
    if Helper.get_command_output("helm ls -n bw5dm --no-headers") is None:
        ColorLogger.info("BW5 domain is not deployed.")
        sys.exit(0)

if __name__ == "__main__":
    check_bw5dm_status()
    print("BW5 domain is deployed. Uninstalling...")

    helm_command = delete_bw5dm_command()
    script_path = Util.save_command_to_file(helm_command, "bmdp_delete_bw5dm.sh")
    ColorLogger.info(f"Script generated at: {script_path}")
    Helper.run_shell_file(script_path)
    ColorLogger.success("BW5 domain uninstallation script executed successfully.")
