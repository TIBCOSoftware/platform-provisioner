#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary
import inspect
import os
import subprocess
from utils.color_logger import ColorLogger
from utils.env import ENV
from utils.helper import Helper
from utils.util import Util

class TibcopCliHandler:
    def __init__(self, custom_env=None):
        self.TIBCOP_CLI_PATH = "tibcop"
        self.CUSTOM_ENV = custom_env

    @staticmethod
    def format_command(string_command, other_args=None):
        lines = [
            '#!/bin/bash',
            '',
            string_command,
            other_args or ''
        ]
        return '\n'.join(lines) + '\n'

    # Runs a command and saves the output to a file, then executes that file.
    def run_command_result_from_file(self, command, file_path):
        script_content = self.run_command(command)
        if not script_content:
            return ""

        script_content = self.format_command(script_content)

        with open(file_path, "w") as f:
            f.write(script_content)
        return Helper.run_shell_file(file_path)

    def run_command(self, command, custom_env_dict=None):
        env_vars = {
            **Helper.get_env_vars(),
            **(self.CUSTOM_ENV or {}),
            **(custom_env_dict or {}),
        }
        
        # Ensure TIBCO Platform CLI environment variables are set for tibcop commands
        if command.strip().startswith('tibcop'):
            # Get TIBCO CLI environment variables from system environment
            tibco_cpurl = os.environ.get("TIBCOP_CLI_CPURL")
            tibco_token = os.environ.get("TIBCOP_CLI_OAUTH_TOKEN")
            
            if tibco_cpurl:
                env_vars["TIBCOP_CLI_CPURL"] = tibco_cpurl
            else:
                print("WARNING: TIBCOP_CLI_CPURL environment variable is not set")
                
            if tibco_token:
                env_vars["TIBCOP_CLI_OAUTH_TOKEN"] = tibco_token
            else:
                print("WARNING: TIBCOP_CLI_OAUTH_TOKEN environment variable is not set")
        
        print(f"Running script:")
        print(command)
        result = subprocess.run(command, shell=True,capture_output=True, text=True, env=env_vars)
        if result.returncode != 0:
            print(f"Command failed with return code {result.returncode}")
            if result.stderr:
                print(f"Command stderr: {result.stderr.strip()}")
        return result.stdout.strip()

    def tplatform_list_dataplane(self, other_args=None):
        command = (
            f'{self.TIBCOP_CLI_PATH} tplatform:list-dataplanes '
            f'{other_args}'
        )
        return self.run_command(command)

    def is_dataplane_created(self, dp_name):
        """
        Checks if a dataplane with the specified name exists.
        :param dp_name: Name of the dataplane to check.
        :return: True if the dataplane exists, False otherwise.
        """
        command = (
            f'--name="{dp_name}" '
            f'--json '
        )
        result = self.tplatform_list_dataplane(command)
        if not result:
            ColorLogger.info(f"Dataplanes '{dp_name}' not found.")
            return False
        data = Util.parse_json_result(result)
        return data is not None

    # Registers a Kubernetes dataplane with the specified name, namespace, and service account.
    # run this command in a shell script file
    def tplatform_register_k8s_dataplane(self,
                                         dp_name,
                                         dp_namespace=None,
                                         dp_service_account_name=None,
                                         other_args=None):
        if self.is_dataplane_created(dp_name):
            ColorLogger.success(f"Dataplane '{dp_name}' already exists. Skip registration.")
            return ""

        ColorLogger.info(f"Dataplane '{dp_name}' does not exist. Starting registration...")
        dp_namespace = dp_namespace or f"{dp_name}ns"
        dp_service_account_name = dp_service_account_name or f"{dp_name}sa"
        command = (
            f'{self.TIBCOP_CLI_PATH} tplatform:register-k8s-dataplane --onlyPrintScripts '
            f'--name="{dp_name}" '
            f'--namespace="{dp_namespace}" '
            f'--service-account-name="{dp_service_account_name}" '
            f'{other_args}'
        )
        script_path = os.path.join(ENV.TP_AUTO_REPORT_PATH, f"{inspect.currentframe().f_code.co_name}.sh")
        return self.run_command_result_from_file(command, script_path)

    # Unregisters a dataplane with the specified name.
    # run this command in a shell script file
    def tplatform_unregister_dataplane(self, dp_name, other_args=None):
        if not self.is_dataplane_created(dp_name):
            ColorLogger.success(f"Dataplane '{dp_name}' does not exist. Skip unregistration.")
            return ""

        ColorLogger.info(f"Dataplane '{dp_name}' exists. Starting unregistration...")
        command = (
            f'{self.TIBCOP_CLI_PATH} tplatform:unregister-dataplane --onlyPrintScripts --force '
            f'--name="{dp_name}" '
            f'{other_args}'
        )
        script_path = os.path.join(ENV.TP_AUTO_REPORT_PATH, f"{inspect.currentframe().f_code.co_name}.sh")
        return self.run_command_result_from_file(command, script_path)
