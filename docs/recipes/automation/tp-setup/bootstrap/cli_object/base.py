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
"""
Base CLI handler with core command execution functionality.

This module provides the foundation for all tibcop CLI operations:
- Command formatting
- Command execution with proper environment setup
- Error handling and logging
"""

import os
import shlex
import subprocess
from utils.env import ENV
from utils.helper import Helper


# tibcop CLI enums use mixed casing that .title() mangles
# (e.g. HaProxy -> Haproxy, NetScaler -> Netscaler). Normalize explicitly.
_INGRESS_CONTROLLER_ENUM = {
    "nginx": "Nginx", "kong": "Kong", "traefik": "Traefik",
    "openshiftrouter": "OpenshiftRouter", "haproxy": "HaProxy",
}
_GATEWAY_CONTROLLER_ENUM = {
    "nginx": "Nginx", "traefik": "Traefik", "gke": "GKE",
    "istio": "Istio", "netscaler": "NetScaler", "other": "Other",
}


def normalize_ingress_controller(value):
    return _INGRESS_CONTROLLER_ENUM.get((value or "").lower(), value)


def normalize_gateway_controller(value):
    return _GATEWAY_CONTROLLER_ENUM.get((value or "").lower(), value)


class TibcopBase:
    """
    Base class for tibcop CLI operations.

    Provides core functionality for executing tibcop commands with proper
    environment variable handling and error checking.
    """

    def __init__(self, custom_env=None):
        """
        Initialize the base CLI handler.

        Args:
            custom_env: Optional dictionary of custom environment variables
                       to merge with system environment when running commands
        """
        # tibcop is invoked WITHOUT a shell (TPSEC-134), so the NODE_TLS flag is passed
        # via the child environment in run_command, not as a shell `export ... &&` prefix
        # (that prefix was the only reason the sink needed shell=True).
        self.TIBCOP_CLI_PATH = "tibcop"
        self.CUSTOM_ENV = custom_env or {}

    @staticmethod
    def format_command(string_command, other_args=None):
        """
        Format a command as a bash script.

        Args:
            string_command: The main command to execute
            other_args: Optional additional arguments to append

        Returns:
            Formatted bash script as a string with shebang and newline
        """
        lines = [
            '#!/bin/bash',
            '',
            string_command,
            other_args or ''
        ]
        return '\n'.join(lines) + '\n'

    def run_command_result_from_file(self, command, file_path):
        """
        Run a command, save output to a file, then execute that file.

        This is useful for commands that generate shell scripts which
        need to be executed subsequently.

        Args:
            command: Command to run
            file_path: Path where to save the command output

        Returns:
            Output from executing the generated file, or empty string on failure
        """
        script_content = self.run_command(command)
        if not script_content:
            return ""

        # Check if the output contains CLI error indicators (e.g., ✖)
        # The tibcop CLI may return exit code 0 but output error messages
        # instead of the expected shell script content
        if self.is_cli_error(script_content):
            print(f"Command output contains error indicators, not saving as script: {script_content}")
            return ""

        script_content = self.format_command(script_content)

        with open(file_path, "w") as f:
            f.write(script_content)
        return Helper.run_shell_file(file_path)

    def run_command(self, command, custom_env_dict=None, verbose=True):
        """
        Execute a shell command with proper environment setup.

        Automatically handles TIBCO Platform CLI environment variables
        (TIBCOP_CLI_CPURL, TIBCOP_CLI_OAUTH_TOKEN) for tibcop commands.

        Args:
            command: Shell command to execute
            custom_env_dict: Optional additional environment variables
                           to merge for this specific command
            verbose: Whether to print command and output (default: True)

        Returns:
            Command stdout as string (stripped), or None if command failed
        """
        # Build environment variables: system env + custom env + command-specific env
        env_vars = {
            **Helper.get_env_vars(),
            **self.CUSTOM_ENV,
            **(custom_env_dict or {}),
        }

        # Ensure TIBCO Platform CLI environment variables are set for tibcop commands
        if command.strip().startswith('tibcop'):
            # NODE_TLS_REJECT_UNAUTHORIZED was previously prepended to the command as a
            # shell `export ... &&`; move it into the child env so tibcop can run without
            # a shell (TPSEC-134). tibcop is a Node CLI and reads this at startup.
            env_vars["NODE_TLS_REJECT_UNAUTHORIZED"] = "0"
            # Check if TIBCO CLI environment variables are already in env_vars
            # If not, try to get from system environment
            if "TIBCOP_CLI_CPURL" not in env_vars:
                tibco_cpurl = os.environ.get("TIBCOP_CLI_CPURL")
                if tibco_cpurl:
                    env_vars["TIBCOP_CLI_CPURL"] = tibco_cpurl
                else:
                    print("WARNING: TIBCOP_CLI_CPURL environment variable is not set")

            if "TIBCOP_CLI_OAUTH_TOKEN" not in env_vars:
                tibco_token = os.environ.get("TIBCOP_CLI_OAUTH_TOKEN")
                if tibco_token:
                    env_vars["TIBCOP_CLI_OAUTH_TOKEN"] = tibco_token
                else:
                    print("WARNING: TIBCOP_CLI_OAUTH_TOKEN environment variable is not set")

        if verbose:
            print(f"Running script:")
            print(command)

        # Run WITHOUT a shell so shell metacharacters in request-derived arguments
        # (TIBCOP_CLI_OTHER_ARGS and the structured params) are inert literal argv
        # tokens instead of shell syntax (TPSEC-134/f023). run_command executes a
        # SINGLE command; shell pipelines belong in Helper.get_command_output /
        # run_shell_file. NOTE: shlex.split is POSIX — a server run locally on Windows
        # would mis-tokenize backslash paths; the deployed/attack surface is the Linux
        # container (paths like /app/upload/...). See TPSEC-134.
        try:
            argv = shlex.split(command)
        except ValueError as e:
            # Unbalanced quotes etc.: previously the shell failed and run_command
            # returned None — preserve that contract instead of raising in the worker.
            print(f"Command could not be parsed and was not run: {e}")
            return None
        if not argv:
            return None

        result = subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            env=env_vars
        )

        if result.returncode != 0:
            stderr_output = result.stderr.strip() if result.stderr else ""
            stdout_output = result.stdout.strip() if result.stdout else ""
            combined_output = f"{stdout_output}\n{stderr_output}".strip()

            # Check if this is an "already provisioned" case - treat as success
            if 'already provisioned' in combined_output.lower():
                if verbose:
                    print(f"Resource already provisioned (treating as success)")
                return "ALREADY_PROVISIONED"

            # Always print errors even in non-verbose mode
            print(f"Command failed with return code {result.returncode}")
            if stdout_output:
                print(f"Command stdout: {stdout_output}")
            if stderr_output:
                print(f"Command stderr: {stderr_output}")
            return None  # Return None on failure to distinguish from empty stdout

        # Check if stdout is empty - this might indicate an issue
        output = result.stdout.strip() if result.stdout else ""
        stderr_output = result.stderr.strip() if result.stderr else ""

        # If output is empty but stderr has content, include stderr in the result
        # This handles cases where tibcop CLI returns exit code 0 but error in stderr
        if not output and stderr_output:
            if verbose:
                print(f"Command returned empty stdout but has stderr:")
                print(f"Command stderr: {stderr_output}")
            # Return stderr as the output so error detection can work
            return stderr_output

        # Only print stdout on success if verbose=True
        if verbose and output:
            # Only print first 1000 chars to avoid cluttering logs with huge outputs
            if len(output) > 1000:
                print(f"{output[:1000]}... (truncated)")
            else:
                print(output)

        return output

    @staticmethod
    def is_cli_error(result):
        """
        Check if the CLI result contains error indicators.

        The tibcop CLI may return exit code 0 even when there's an error,
        showing error messages like "✖ Dataplane not found" in the output.

        Note: "Warning: No xxx found" messages are NOT errors - they indicate
        the operation succeeded but returned empty results. Use is_empty_warning()
        to detect this case.

        Args:
            result: The output from run_command

        Returns:
            True if the result indicates an error, False otherwise
        """
        if result is None:
            return True
        if not result:
            return False

        # Check for success indicator (✔) first - if the final status line
        # contains a checkmark, the command succeeded regardless of other text
        if '✔' in result:
            # Find the last line with ✔ - tibcop shows progress with spinner
            # then replaces with ✔ on success or ✖ on failure
            lines = result.strip().split('\n')
            last_check = None
            last_cross = None
            for i, line in enumerate(lines):
                if '✔' in line:
                    last_check = i
                if '✖' in line:
                    last_cross = i
            # If the last status indicator is a checkmark, it's a success
            if last_cross is None or (last_check is not None and last_check > last_cross):
                return False

        # Check for the cross mark (✖) which indicates an actual error
        if '✖' in result:
            return True

        # Filter out Node.js NODE_TLS_REJECT_UNAUTHORIZED warning lines
        # before checking for error patterns. This warning is informational
        # and not an actual CLI error.
        filtered_lines = []
        for line in result.split('\n'):
            if 'NODE_TLS_REJECT_UNAUTHORIZED' in line:
                continue
            if 'trace-warnings' in line:
                continue
            filtered_lines.append(line)
        filtered_result = '\n'.join(filtered_lines).lower()

        # Check for actual error patterns (not informational warnings)
        error_patterns = [
            'error:',
            'failed',
            'invalid',
            'request failed',
            'connection refused',
            'unauthorized',
            'forbidden',
        ]
        for pattern in error_patterns:
            if pattern in filtered_result:
                return True

        return False

    @staticmethod
    def is_empty_warning(result):
        """
        Check if the CLI result indicates an empty result (not an error).

        The tibcop CLI returns "Warning: No xxx found" when a list operation
        succeeds but returns no items. This is not an error.

        Args:
            result: The output from run_command

        Returns:
            True if the result indicates empty/no items found, False otherwise
        """
        if not result:
            return False

        result_lower = result.lower()

        # Check for "Warning: No xxx found" pattern
        # This is informational, not an error
        import re
        if re.search(r'warning:\s*no\s+\w+.*\s+found', result_lower):
            return True

        return False
