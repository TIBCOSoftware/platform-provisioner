#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary

import subprocess
import os
import sys
import json
import platform
from pathlib import Path

from utils.color_logger import ColorLogger

# do not import env.py or util.py in this file
class Helper:
    @staticmethod
    def is_headless():
        # headless mode is enabled in docker
        if os.path.exists("/.dockerenv"):
            return True
        return os.environ.get("HEADLESS", "true").lower() == "true"

    @staticmethod
    def get_windows_bash():
        bash_path = Path(r"C:\Program Files\Git\bin\bash.exe")
        if not bash_path.exists():
            ColorLogger.error(f"The git bash '{bash_path}' does not exist.")
            sys.exit()
        return bash_path

    @staticmethod
    def run_shell_file(script_path, custom_env_dict=None):
        # Check if the script file exists
        if not os.path.exists(script_path):
            raise FileNotFoundError(f"Script file not found: {script_path}")

        # Set execute permissions for the script
        os.chmod(script_path, 0o755)

        try:
            command = [script_path]
            if platform.system() == "Windows":
                bash_path = Helper.get_windows_bash()
                print(f"Run Windows command: {bash_path} -c {script_path}")
                command = [bash_path, script_path]
            # Execute the shell script using subprocess
            print(f"Running script: {script_path}")
            env_vars = {
                **Helper.get_env_vars(),
                **(custom_env_dict or {})
            }
            result = subprocess.run(
                command,             # Path to the script
                shell=False,               # Run without invoking the shell for added security
                check=True,                # Raise an error if the script exits with a non-zero status
                capture_output=True,       # Capture standard output and standard error
                text=True,                 # Decode the output as text (not bytes)
                env=env_vars
            )
            if result.stderr:
                print(f"Command stderr: {result.stderr.strip()}")
            # Print the script's standard output
            print(f"Script output:\n{result.stdout}")
            return result.stdout
        except subprocess.CalledProcessError as e:
            # Handle errors during script execution
            print(f"Error while executing script: {e}")
            print(f"Script stderr:\n{e.stderr}")
        except Exception as e:
            # Handle any unexpected exceptions
            print(f"An unexpected error occurred: {e}")
        return ""

    @staticmethod
    def get_command_output(command, is_print_cmd=False):
        try:
            if platform.system() == "Windows":
                bash_path = Helper.get_windows_bash()
                if is_print_cmd:
                    print(f"Run Windows command: {bash_path} -c {command}")
                # For Windows, use '-c' to run the command
                command = [bash_path, "-c", command]
            else:
                if is_print_cmd:
                    print(f"Run command: {command}")
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                check=True,
                env=Helper.get_env_vars()
            )
            if result.stderr:
                print(f"Command stderr: {result.stderr.strip()}")
            return result.stdout.strip()  # Return standard output
        except subprocess.CalledProcessError as e:
            print(f"Failed command: {command}")
            print(f"Command failed with error: {e.stderr.strip()}")
            return None

    @staticmethod
    def get_env_vars():
        env_vars = os.environ.copy()
        tp_auto_kubeconfig = os.environ.get("TP_AUTO_KUBECONFIG")
        if tp_auto_kubeconfig:
            tp_auto_kubeconfig = os.path.expanduser(tp_auto_kubeconfig)
            env_vars["KUBECONFIG"] = tp_auto_kubeconfig
        return env_vars

    @staticmethod
    def get_cp_dns_domain():
        return Helper.get_command_output("kubectl get ingress -A | awk '$2 == \"router\" {print $4; exit}' | sed -E 's/^\\*?\\.//' | cut -d. -f2-")

    @staticmethod
    def get_elastic_password():
        return Helper.get_command_output("kubectl get secret -n elastic-system dp-config-es-es-elastic-user -o=jsonpath='{.data.elastic}' | base64 --decode; echo")

    @staticmethod
    def get_cp_version():
        return Helper.get_command_output("helm ls -A | grep platform-base | awk '{print $9}' | awk -F 'platform-base-' '{print $2}' | cut -d'.' -f1,2")

    @staticmethod
    def get_cp_platform_bootstrap_version():
        return Helper.get_command_output(r"helm list --all-namespaces | grep platform-bootstrap | sed -n 's/.*platform-bootstrap-\(.*\)[[:space:]].*/\1/p' | sed 's/[[:space:]].*//'")

    @staticmethod
    def get_cp_platform_base_version():
        return Helper.get_command_output(r"helm list --all-namespaces | grep platform-base | sed -n 's/.*platform-base-\(.*\)[[:space:]].*/\1/p' | sed 's/[[:space:]].*//'")

    @staticmethod
    def get_storage_class():
        return Helper.get_command_output("kubectl get sc | awk '/\\(default\\)/ {print $1}'")

    @staticmethod
    def get_app_file_fullpath(app_file_name):
        file_path = os.path.join(os.path.dirname(__file__), "..", "upload", app_file_name)

        if not os.path.isfile(file_path):
            ColorLogger.error(f"The app name is empty in file {file_path}.")
            sys.exit()
        return file_path

    @staticmethod
    def get_app_name(app_file_name):
        file_path = Helper.get_app_file_fullpath(app_file_name)
        with open(file_path, "r") as f:
            flogo_json = json.load(f)
            app_name = flogo_json["name"]

        if app_name == "":
            ColorLogger.error(f"The app name is empty in file {file_path}.")
            sys.exit()
        return app_name

    @staticmethod
    def get_o11y_sub_name_input(dp_name, menu_name, tab_name, tab_sub_name=""):
        tab_name = tab_name if tab_sub_name == "" else f"{tab_name} {tab_sub_name}"
        tab = tab_name.lower()
        words = tab_name.split()
        if len(words) > 1:
            tab = ''.join(word[0].lower() for word in words)

        index = 1
        if dp_name == "":
            name_input = f"GLOBAL_{menu_name}-{tab}".upper()
        else:
            name_input = f"{dp_name}-{menu_name}-{tab}-{index}".lower()
        return name_input
