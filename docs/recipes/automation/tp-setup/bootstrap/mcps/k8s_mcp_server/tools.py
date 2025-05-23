# Source: https://github.com/alexei-led/k8s-mcp-server
# License: MIT License
# Copyright (c) 2021 Alexei Ledenev

"""Command utilities for K8s MCP Server.

This module provides core utilities for validating and working with Kubernetes commands,
including helper functions for command parsing and validation. It focuses on the command
structure and validation requirements, not execution logic.
"""

import shlex
from dataclasses import dataclass
from typing import Literal, NotRequired, TypedDict

# List of allowed Unix commands that can be used in a pipe
ALLOWED_UNIX_COMMANDS = [
    # File operations
    "cat",
    "ls",
    "cd",
    "pwd",
    "cp",
    "mv",
    "rm",
    "mkdir",
    "touch",
    "chmod",
    "chown",
    # Text processing
    "grep",
    "sed",
    "awk",
    "cut",
    "sort",
    "uniq",
    "wc",
    "head",
    "tail",
    "tr",
    "find",
    # System information
    "ps",
    "top",
    "df",
    "du",
    "uname",
    "whoami",
    "date",
    "which",
    "echo",
    # Networking
    "ping",
    "ifconfig",
    "netstat",
    "curl",
    "wget",
    "dig",
    "nslookup",
    "ssh",
    "scp",
    # Other utilities
    "man",
    "less",
    "tar",
    "gzip",
    "gunzip",
    "zip",
    "unzip",
    "xargs",
    "jq",  # JSON processor
    "yq",  # YAML processor
    "tee",
    "column",  # Table formatting
    "watch",  # Repeat command execution
]

# List of allowed Kubernetes CLI tools
ALLOWED_K8S_TOOLS = [
    "kubectl",
    "istioctl",
    "helm",
    "argocd",
]


class ErrorDetailsNested(TypedDict, total=False):
    """Type definition for nested error details."""

    command: str
    exit_code: int
    stderr: str


class ErrorDetails(TypedDict, total=False):
    """Type definition for detailed error information matching the spec."""

    message: str
    code: str
    details: ErrorDetailsNested  # Use the nested type here


class CommandResult(TypedDict):
    """Type definition for command execution results following the specification."""

    status: Literal["success", "error"]
    output: str
    exit_code: NotRequired[int]
    execution_time: NotRequired[float]
    error: NotRequired[ErrorDetails]


@dataclass
class CommandHelpResult:
    """Type definition for command help results."""

    help_text: str
    status: str = "success"
    error: ErrorDetails | None = None


def is_valid_k8s_tool(command: str) -> bool:
    """Check if a command starts with a valid Kubernetes CLI tool.

    Args:
        command: The command to check

    Returns:
        True if the command starts with a valid Kubernetes CLI tool, False otherwise
    """
    cmd_parts = shlex.split(command)
    if not cmd_parts:
        return False

    return cmd_parts[0] in ALLOWED_K8S_TOOLS


def validate_unix_command(command: str) -> bool:
    """Validate that a command is an allowed Unix command.

    Args:
        command: The Unix command to validate

    Returns:
        True if the command is valid, False otherwise
    """
    cmd_parts = shlex.split(command)
    if not cmd_parts:
        return False

    # Check if the command is in the allowed list
    return cmd_parts[0] in ALLOWED_UNIX_COMMANDS


def is_pipe_command(command: str) -> bool:
    """Check if a command contains a pipe operator.

    Args:
        command: The command to check

    Returns:
        True if the command contains a pipe operator, False otherwise
    """
    # Simple check for pipe operator that's not inside quotes
    in_single_quote = False
    in_double_quote = False

    for i, char in enumerate(command):
        if char == "'" and (i == 0 or command[i - 1] != "\\"):
            in_single_quote = not in_single_quote
        elif char == '"' and (i == 0 or command[i - 1] != "\\"):
            in_double_quote = not in_double_quote
        elif char == "|" and not in_single_quote and not in_double_quote:
            return True

    return False


def split_pipe_command(pipe_command: str) -> list[str]:
    """Split a piped command into individual commands.

    Args:
        pipe_command: The piped command string

    Returns:
        List of individual command strings
    """
    if not pipe_command:
        return [""]  # Return a list with an empty string for empty input

    commands = []
    current_command = ""
    in_single_quote = False
    in_double_quote = False

    for i, char in enumerate(pipe_command):
        if char == "'" and (i == 0 or pipe_command[i - 1] != "\\"):
            in_single_quote = not in_single_quote
            current_command += char
        elif char == '"' and (i == 0 or pipe_command[i - 1] != "\\"):
            in_double_quote = not in_double_quote
            current_command += char
        elif char == "|" and not in_single_quote and not in_double_quote:
            commands.append(current_command.strip())
            current_command = ""
        else:
            current_command += char

    if current_command.strip():
        commands.append(current_command.strip())

    return commands
