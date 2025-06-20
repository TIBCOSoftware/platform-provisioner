# Source: https://github.com/alexei-led/k8s-mcp-server
# License: MIT License
# Copyright (c) 2021 Alexei Ledenev

"""Utility for executing Kubernetes CLI commands.

This module provides functions to validate and execute commands for various
Kubernetes CLI tools (kubectl, istioctl, helm, argocd) with proper error handling,
timeouts, and output processing. It handles command execution with proper security
validation, context/namespace injection, and resource limitations.
"""

import asyncio
import logging
import os
import shlex
import time
from asyncio.subprocess import PIPE

from .config import (
    DEFAULT_TIMEOUT,
    K8S_CONTEXT,
    K8S_NAMESPACE,
    MAX_OUTPUT_SIZE,
    SUPPORTED_CLI_TOOLS,
    TIBCOP_CLI_CPURL,
    TIBCOP_CLI_OAUTH_TOKEN,
)
from .errors import (
    AuthenticationError,
    CommandExecutionError,
    CommandTimeoutError,
    CommandValidationError,
)
from .security import validate_command
from .tools import (
    CommandHelpResult,
    CommandResult,
    is_pipe_command,
    split_pipe_command,
)

logger = logging.getLogger(__name__)


async def check_cli_installed(cli_tool: str) -> bool:
    """Check if a Kubernetes CLI tool is installed and accessible.

    Args:
        cli_tool: Name of the CLI tool to check (kubectl, istioctl, helm, argocd, tibcop)

    Returns:
        True if the CLI tool is installed, False otherwise
    """
    if cli_tool not in SUPPORTED_CLI_TOOLS:
        logger.warning(f"Unsupported CLI tool: {cli_tool}")
        return False

    try:
        cmd = SUPPORTED_CLI_TOOLS[cli_tool]["check_cmd"]
        cmd_args = shlex.split(cmd)
        process = await asyncio.create_subprocess_exec(*cmd_args, stdout=PIPE, stderr=PIPE)
        await process.communicate()
        return process.returncode == 0
    except Exception as e:
        logger.warning(f"Error checking if {cli_tool} is installed: {e}")
        return False


def is_auth_error(error_output: str) -> bool:
    """Detect if an error is related to authentication.

    Args:
        error_output: The error output from CLI tool

    Returns:
        True if the error is related to authentication, False otherwise
    """
    auth_error_patterns = [
        "Unable to connect to the server",
        "Unauthorized",
        "forbidden",
        "Invalid kubeconfig",
        "Unable to load authentication",
        "Error loading config",
        "no configuration has been provided",
        "You must be logged in",  # For argocd
        "Error: Helm repo",  # For Helm repo authentication
    ]
    return any(pattern.lower() in error_output.lower() for pattern in auth_error_patterns)


def get_tool_from_command(command: str) -> str | None:
    """Extract the CLI tool from a command string.

    Args:
        command: The command string

    Returns:
        The CLI tool name or None if not found
    """
    cmd_parts = shlex.split(command)
    if not cmd_parts:
        return None

    return cmd_parts[0] if cmd_parts[0] in SUPPORTED_CLI_TOOLS else None


async def execute_command(command: str, timeout: int | None = None) -> CommandResult:
    """Execute a Kubernetes CLI command and return the result.

    Validates, executes, and processes the results of a CLI command,
    handling timeouts and output size limits.

    Args:
        command: The CLI command to execute (must start with supported CLI tool)
        timeout: Optional timeout in seconds (defaults to DEFAULT_TIMEOUT)

    Returns:
        CommandResult containing output and status

    Raises:
        CommandValidationError: If the command is invalid
        CommandExecutionError: If the command fails to execute
        AuthenticationError: If authentication fails
        CommandTimeoutError: If the command times out
    """
    # Validate the command
    try:
        validate_command(command)
    except ValueError as e:
        raise CommandValidationError(str(e), {"command": command}) from e

    # Handle piped commands
    is_piped = is_pipe_command(command)
    full_piped_command = None  # Initialize to None
    
    if is_piped:
        commands = split_pipe_command(command)
        logger.debug("Split pipe command into %d parts: %s", len(commands), commands)
        
        if not commands:
            raise CommandExecutionError("Failed to split piped command", {"command": command})
        
        # Process each command in the pipe, applying context/namespace injection where needed
        processed_commands = []
        for i, cmd in enumerate(commands):
            if not cmd.strip():
                logger.warning("Empty command found in pipe at position %d", i)
                continue
            # Apply context/namespace injection to each kubectl/istioctl command in the pipe
            processed_cmd = inject_context_namespace(cmd.strip())
            processed_commands.append(processed_cmd)
            logger.debug("Processed command %d: %s -> %s", i, cmd.strip(), processed_cmd)
        
        if not processed_commands:
            raise CommandExecutionError("No valid commands found in pipe", {"command": command})
        
        # Reconstruct the full command with pipes for shell execution
        full_piped_command = " | ".join(processed_commands)
        logger.debug("Reconstructed piped command: %s", full_piped_command)
    else:
        # Handle context and namespace for non-piped commands
        command = inject_context_namespace(command)

    # Set timeout
    if timeout is None:
        timeout = DEFAULT_TIMEOUT

    # Log the command that will actually be executed
    actual_command = full_piped_command if is_piped else command
    logger.debug("Executing %s command: %s", "piped" if is_piped else "direct", actual_command)
    start_time = time.time()

    # Prepare environment variables for the command
    command_env = prepare_command_environment(actual_command or "")

    try:
        if is_piped:
            # Execute piped commands by using shell with proper pipe handling
            # This is safer than trying to manually chain asyncio processes
            # which can cause StreamReader fileno() issues
            
            # Ensure we have a command to execute
            if full_piped_command is None:
                raise CommandExecutionError("Failed to construct piped command", {"command": command})
            
            # Use shell=True for pipe commands to let the shell handle piping
            process = await asyncio.create_subprocess_shell(
                full_piped_command,
                stdout=PIPE,
                stderr=PIPE,
                env=command_env,
            )
        else:
            # Use safer create_subprocess_exec for non-piped commands
            cmd_args = shlex.split(command)
            process = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=PIPE,
                stderr=PIPE,
                env=command_env,
            )

        # Wait for the process to complete with timeout
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout)
            logger.debug(f"Command completed with return code: {process.returncode}")
        except TimeoutError:
            logger.warning(f"Command timed out after {timeout} seconds: {command}")
            try:
                process.kill()
            except Exception as e:
                logger.error(f"Error killing process: {e}")

            execution_time = time.time() - start_time
            raise CommandTimeoutError(f"Command timed out after {timeout} seconds", {"command": command, "timeout": timeout}) from None

        # Process output
        stdout_str = stdout.decode("utf-8", errors="replace")
        stderr_str = stderr.decode("utf-8", errors="replace")
        execution_time = time.time() - start_time

        # Truncate output if necessary
        if len(stdout_str) > MAX_OUTPUT_SIZE:
            logger.info(f"Output truncated from {len(stdout_str)} to {MAX_OUTPUT_SIZE} characters")
            stdout_str = stdout_str[:MAX_OUTPUT_SIZE] + "\n... (output truncated)"

        if process.returncode != 0:
            logger.warning(f"Command failed with return code {process.returncode}: {command}")
            logger.debug(f"Command error output: {stderr_str}")

            error_message = stderr_str or "Command failed with no error output"

            if is_auth_error(stderr_str):
                cli_tool = get_tool_from_command(command)
                auth_error_msg = f"Authentication error: {stderr_str}"

                match cli_tool:
                    case "kubectl":
                        auth_error_msg += "\nPlease check your kubeconfig."
                    case "istioctl":
                        auth_error_msg += "\nPlease check your Istio configuration."
                    case "helm":
                        auth_error_msg += "\nPlease check your Helm repository configuration."
                    case "argocd":
                        auth_error_msg += "\nPlease check your ArgoCD login status."

                raise AuthenticationError(
                    auth_error_msg,
                    {
                        "command": command,
                        "exit_code": process.returncode,
                        "stderr": stderr_str,
                    },
                )
            else:
                raise CommandExecutionError(
                    error_message,
                    {
                        "command": command,
                        "exit_code": process.returncode,
                        "stderr": stderr_str,
                    },
                )

        return CommandResult(status="success", output=stdout_str, exit_code=process.returncode, execution_time=execution_time)
    except asyncio.CancelledError:
        raise
    except (CommandValidationError, CommandExecutionError, AuthenticationError, CommandTimeoutError):
        # Re-raise specific exceptions so they can be caught and handled at the API boundary
        raise
    except Exception as e:
        logger.error(f"Failed to execute command: {str(e)}")
        raise CommandExecutionError(f"Failed to execute command: {str(e)}", {"command": command}) from e


def inject_context_namespace(command: str) -> str:
    """Inject context and namespace flags into kubectl and istioctl commands if needed.

    This function analyzes kubectl and istioctl commands and automatically injects:
    1. --context flag if K8S_CONTEXT is set and no context is specified
    2. --namespace flag if K8S_NAMESPACE is set and:
       - The command operates on namespaced resources
       - No namespace is already specified (-n, --namespace)
       - Not requesting all namespaces (-A, --all-namespaces)
       - Not targeting cluster-scoped resources (nodes, pv, etc.)
       - Not using cluster-scoped commands (api-resources, etc.)

    Args:
        command: The CLI command to analyze and potentially modify

    Returns:
        Command with context and/or namespace flags added if appropriate
    """
    # Only apply to kubectl and istioctl commands
    if not command.startswith("kubectl") and not command.startswith("istioctl"):
        return command

    try:
        # Parse command into words, preserving quotes
        args = shlex.split(command)
    except ValueError as e:
        # Handle parsing errors (like unclosed quotes)
        logger.warning(f"Could not parse command for context/namespace injection: {command} - {e}")
        return command

    if not args:
        return command

    tool_name = args[0]
    remaining_args = args[1:]

    # Use a more structured approach to check for flags and commands
    has_context = any(arg.startswith("--context") for arg in remaining_args)
    has_namespace = any(arg.startswith("--namespace") or arg.startswith("-n") for arg in remaining_args)
    has_all_namespaces = "-A" in remaining_args or "--all-namespaces" in remaining_args

    # More reliable detection of resource commands and non-namespaced resources
    resource_commands = {"get", "describe", "delete", "edit", "label", "annotate", "patch", "apply", "logs", "exec", "rollout", "scale", "autoscale", "expose"}

    non_namespace_resources = {
        "nodes",
        "namespaces",
        "ns",
        "pv",
        "persistentvolumes",
        "storageclasses",
        "clusterroles",
        "clusterrolebindings",
        "apiservices",
        "certificatesigningrequests",
        "csr",
    }

    cluster_scoped_commands = {"api-resources", "api-versions", "cluster-info", "config", "version", "completion", "plugin"}

    # Analyze the command structure more carefully
    is_resource_command = False
    targets_non_namespace_resource = False
    is_cluster_scoped_command = False

    # Special case for commands with explicit context but no namespace
    # e.g. "kubectl --context=prod get pods"
    if has_context and not has_namespace:
        for i, arg in enumerate(remaining_args):
            if arg in resource_commands:
                is_resource_command = True
                # Check if next arg is a resource type
                if i + 1 < len(remaining_args) and not remaining_args[i + 1].startswith("-"):
                    if remaining_args[i + 1] not in non_namespace_resources:
                        # Add namespace if there's a context with resource command that needs namespace
                        if "get" in remaining_args or "describe" in remaining_args:
                            is_resource_command = True
                            break

    # For certain command patterns, consider them resource commands by default
    # This handles cases like 'kubectl get pod nginx-pod'
    if len(remaining_args) >= 2:
        if remaining_args[0] in resource_commands:
            is_resource_command = True
            # Check if the resource type is non-namespaced
            if remaining_args[1] in non_namespace_resources:
                targets_non_namespace_resource = True

    # Handle 'analyze' command for istioctl (special case)
    if tool_name == "istioctl" and "analyze" in remaining_args:
        is_resource_command = True

    # Examine each argument and classify the command
    for i, arg in enumerate(remaining_args):
        # Skip flags and their values
        if arg.startswith("-"):
            continue

        # Check if it's a resource command
        if arg in resource_commands:
            is_resource_command = True
            # Look for the resource type in the next argument
            if i + 1 < len(remaining_args) and not remaining_args[i + 1].startswith("-"):
                if remaining_args[i + 1] in non_namespace_resources:
                    targets_non_namespace_resource = True

        # Check if it's a cluster-scoped command
        if arg in cluster_scoped_commands:
            is_cluster_scoped_command = True

    # Build a list of flags to add
    flags_to_add = []

    # Add context flag if needed and available
    if K8S_CONTEXT and not has_context:
        flags_to_add.append(f"--context={K8S_CONTEXT}")
        logger.debug(f"Injecting context: --context={K8S_CONTEXT}")

    # Add namespace flag if all conditions are met
    if (
        K8S_NAMESPACE
        and not has_namespace
        and not has_all_namespaces
        and is_resource_command
        and not targets_non_namespace_resource
        and not is_cluster_scoped_command
    ):
        flags_to_add.append(f"--namespace={K8S_NAMESPACE}")
        logger.debug(f"Injecting namespace: --namespace={K8S_NAMESPACE}")

    # Return original command if no flags to add
    if not flags_to_add:
        return command

    # Insert flags after the tool name
    new_args = [tool_name] + flags_to_add + remaining_args

    # Reconstruct command with added flags
    try:
        # Use shlex.join in Python 3.8+ for proper quoting
        from shlex import join as shlex_join

        # This will properly handle preserving quotes in arguments
        return shlex_join(new_args)
    except ImportError:
        # Fallback for older Python versions - manually preserve quotes
        reconstructed = [tool_name]
        reconstructed.extend(flags_to_add)

        for arg in remaining_args:
            # Add quotes around arguments with spaces if they don't already have them
            if " " in arg and not (arg.startswith('"') and arg.endswith('"')) and not (arg.startswith("'") and arg.endswith("'")):
                arg = f'"{arg}"'
            reconstructed.append(arg)

        return " ".join(reconstructed)


async def get_command_help(cli_tool: str, command: str | None = None) -> CommandHelpResult:
    """Get help documentation for a Kubernetes CLI tool or command.

    Retrieves the help documentation for a specified CLI tool or command
    by executing the appropriate help command.

    Args:
        cli_tool: The CLI tool name (kubectl, istioctl, helm, argocd)
        command: Optional command within the CLI tool

    Returns:
        CommandHelpResult containing the help text
    """
    if cli_tool not in SUPPORTED_CLI_TOOLS:
        return CommandHelpResult(help_text=f"Unsupported CLI tool: {cli_tool}", status="error")

    # Build the help command
    help_flag = SUPPORTED_CLI_TOOLS[cli_tool]["help_flag"]
    if command:
        cmd_str = f"{cli_tool} {command} {help_flag}"
    else:
        cmd_str = f"{cli_tool} {help_flag}"

    try:
        logger.debug(f"Getting command help for: {cmd_str}")
        result = await execute_command(cmd_str)
        return CommandHelpResult(help_text=result["output"])
    except CommandValidationError as e:
        logger.warning(f"Help command validation error: {e}")
        return CommandHelpResult(
            help_text=f"Command validation error: {str(e)}",
            status="error",
            error={"message": str(e), "code": "VALIDATION_ERROR"},
        )
    except CommandExecutionError as e:
        logger.warning(f"Help command execution error: {e}")
        return CommandHelpResult(
            help_text=f"Command execution error: {str(e)}",
            status="error",
            error={"message": str(e), "code": "EXECUTION_ERROR"},
        )
    except AuthenticationError as e:
        logger.warning(f"Help command authentication error: {e}")
        return CommandHelpResult(
            help_text=f"Authentication error: {str(e)}",
            status="error",
            error={"message": str(e), "code": "AUTH_ERROR"},
        )
    except CommandTimeoutError as e:
        logger.warning(f"Help command timeout error: {e}")
        return CommandHelpResult(
            help_text=f"Command timed out: {str(e)}",
            status="error",
            error={"message": str(e), "code": "TIMEOUT_ERROR"},
        )
    except Exception as e:
        logger.error(f"Unexpected error while getting command help: {e}", exc_info=True)
        return CommandHelpResult(
            help_text=f"Error retrieving help: {str(e)}",
            status="error",
            error={"message": f"Error retrieving help: {str(e)}", "code": "INTERNAL_ERROR"},
        )


def prepare_command_environment(command: str) -> dict:
    """Prepare environment variables for command execution.
    
    For tibcop commands, ensures TIBCOP_CLI_CPURL and TIBCOP_CLI_OAUTH_TOKEN 
    environment variables are available.
    
    Args:
        command: The command to be executed
        
    Returns:
        Dictionary of environment variables to be passed to the subprocess
    """
    # Start with current environment
    env = os.environ.copy()
    
    # Add specific environment variables for tibcop commands
    if command.strip().startswith('tibcop'):
        if TIBCOP_CLI_CPURL:
            env['TIBCOP_CLI_CPURL'] = TIBCOP_CLI_CPURL
        if TIBCOP_CLI_OAUTH_TOKEN:
            env['TIBCOP_CLI_OAUTH_TOKEN'] = TIBCOP_CLI_OAUTH_TOKEN
            
        # Log environment variable status for debugging
        if TIBCOP_CLI_CPURL:
            logger.debug("TIBCOP_CLI_CPURL environment variable is set")
        else:
            logger.warning("TIBCOP_CLI_CPURL environment variable is not set - tibcop commands may fail")
            
        if TIBCOP_CLI_OAUTH_TOKEN:
            logger.debug("TIBCOP_CLI_OAUTH_TOKEN environment variable is set")
        else:
            logger.warning("TIBCOP_CLI_OAUTH_TOKEN environment variable is not set - tibcop commands may fail")
    
    return env
