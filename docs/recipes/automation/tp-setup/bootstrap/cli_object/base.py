#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary
"""
Base CLI handler with core command execution functionality.

This module provides the foundation for all tibcop CLI operations:
- Command formatting
- Command execution with proper environment setup
- Error handling and logging
"""

import os
import subprocess
from utils.helper import Helper


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

        result = subprocess.run(
            command,
            shell=True,
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

        result_lower = result.lower()

        # Check for the cross mark (✖) which indicates an actual error
        if '✖' in result:
            return True

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
            if pattern in result_lower:
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
