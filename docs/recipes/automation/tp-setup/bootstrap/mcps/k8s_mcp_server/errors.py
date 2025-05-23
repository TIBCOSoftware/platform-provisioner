# Source: https://github.com/alexei-led/k8s-mcp-server
# License: MIT License
# Copyright (c) 2021 Alexei Ledenev

"""Error handling for K8s MCP Server.

This module provides standardized error handling for the K8s MCP Server,
including exception classes and helper functions for creating structured error responses.
"""

from typing import Any

from .tools import CommandResult, ErrorDetails, ErrorDetailsNested


class K8sMCPError(Exception):
    """Base class for all K8s MCP Server exceptions."""

    def __init__(self, message: str, code: str = "INTERNAL_ERROR", details: dict[str, Any] | None = None):
        """Initialize K8sMCPError.

        Args:
            message: Error message
            code: Error code
            details: Additional error details
        """
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


class CommandValidationError(K8sMCPError):
    """Exception raised when a command fails validation."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        """Initialize CommandValidationError.

        Args:
            message: Error message
            details: Additional error details
        """
        super().__init__(message, "VALIDATION_ERROR", details)


class CommandExecutionError(K8sMCPError):
    """Exception raised when a command fails to execute."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        """Initialize CommandExecutionError.

        Args:
            message: Error message
            details: Additional error details
        """
        super().__init__(message, "EXECUTION_ERROR", details)


class AuthenticationError(K8sMCPError):
    """Exception raised when authentication fails."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        """Initialize AuthenticationError.

        Args:
            message: Error message
            details: Additional error details
        """
        super().__init__(message, "AUTH_ERROR", details)


class CommandTimeoutError(K8sMCPError):
    """Exception raised when a command times out."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        """Initialize CommandTimeoutError.

        Args:
            message: Error message
            details: Additional error details
        """
        super().__init__(message, "TIMEOUT_ERROR", details)


def create_error_result(error: K8sMCPError, command: str | None = None, exit_code: int | None = None, stderr: str | None = None) -> CommandResult:
    """Create a CommandResult with error details from a K8sMCPError.

    Args:
        error: The exception that occurred
        command: The command that caused the error
        exit_code: The exit code of the command
        stderr: Standard error output from the command

    Returns:
        CommandResult with error details
    """
    # Create nested error details
    nested_details = ErrorDetailsNested()
    if command:
        nested_details["command"] = command
    if exit_code is not None:
        nested_details["exit_code"] = exit_code
    if stderr:
        nested_details["stderr"] = stderr

    # Add any custom details from the exception
    for key, value in error.details.items():
        if key not in nested_details:
            nested_details[key] = value

    # Create error details
    error_details = ErrorDetails(message=str(error), code=error.code, details=nested_details)

    # Create command result
    return CommandResult(status="error", output=str(error), error=error_details, exit_code=exit_code)
