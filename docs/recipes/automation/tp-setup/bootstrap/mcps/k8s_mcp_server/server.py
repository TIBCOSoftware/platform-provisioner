# Source: https://github.com/alexei-led/k8s-mcp-server
# License: MIT License
# Copyright (c) 2021 Alexei Ledenev

"""Main server implementation for K8s MCP Server.

This module defines the MCP server instance and tool functions for Kubernetes CLI interaction,
providing a standardized interface for kubectl, istioctl, helm, argocd, and tibcop command execution
and documentation.
"""

import asyncio
import logging
import subprocess
import threading
from contextlib import asynccontextmanager
from functools import wraps
from typing import Optional

# Add additional imports for detailed HTTP logging
import json
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field
from starlette.applications import Starlette

from . import __version__
from .auth_middleware import BearerTokenMiddleware
from .cli_executor import (
    execute_command,
    get_command_help,
)
from .config import DEFAULT_TIMEOUT, INSTRUCTIONS, SUPPORTED_CLI_TOOLS, MCP_HOST, MCP_PORT, MCP_DEBUG, MCP_LOG_REQUESTS, MCP_HTTP_BEARER_TOKEN
from .errors import (
    AuthenticationError,
    CommandExecutionError,
    CommandTimeoutError,
    CommandValidationError,
    create_error_result,
)
from .prompts import register_prompts
from .tools import CommandHelpResult, CommandResult

logger = logging.getLogger(__name__)


class AuthenticatedFastMCP(FastMCP):
    """FastMCP with Bearer Token authentication support for K8s MCP Server."""
    
    def __init__(self, bearer_token: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.bearer_token = bearer_token
        
    def streamable_http_app(self) -> Starlette:
        """Override to add authentication middleware."""
        app = super().streamable_http_app()
        
        # Add Bearer Token authentication middleware if configured
        if self.bearer_token:
            # Create a middleware class with the token pre-configured
            token = self.bearer_token
            class ConfiguredBearerTokenMiddleware(BearerTokenMiddleware):
                def __init__(self, app):
                    super().__init__(app, expected_token=token)
            
            app.add_middleware(ConfiguredBearerTokenMiddleware)
            logger.info("Bearer Token authentication middleware added to K8s MCP streamable-http app")
        
        return app


logger = logging.getLogger(__name__)

# Configure logging level based on debug setting
if MCP_DEBUG:
    logging.getLogger().setLevel(logging.DEBUG)
    logger.setLevel(logging.DEBUG)
    logger.debug("Debug logging enabled for K8s MCP Server")

# Log configuration settings for debugging
logger.info("=== K8S MCP SERVER CONFIGURATION ===")
logger.info(f"MCP_DEBUG: {MCP_DEBUG}")
logger.info(f"MCP_LOG_REQUESTS: {MCP_LOG_REQUESTS}")
logger.info(f"MCP_HOST: {MCP_HOST}")
logger.info(f"MCP_PORT: {MCP_PORT}")
logger.info(f"DEFAULT_TIMEOUT: {DEFAULT_TIMEOUT}")
logger.info(f"Authentication: {'Enabled' if MCP_HTTP_BEARER_TOKEN else 'Disabled'}")
if MCP_HTTP_BEARER_TOKEN:
    logger.info("Bearer Token authentication will be enforced")
else:
    logger.info("Bearer Token authentication disabled - server running without authentication")
logger.info("=====================================")

# Enhanced error logging configuration
import logging
debug_handler = logging.StreamHandler()
debug_handler.setLevel(logging.DEBUG if MCP_DEBUG else logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
debug_handler.setFormatter(formatter)
logger.addHandler(debug_handler)

# Force log level to capture all errors
if not MCP_DEBUG:
    # Even if not in debug mode, we want to catch ERROR level for 400 debugging
    logger.setLevel(logging.INFO)
    logging.getLogger("mcp").setLevel(logging.INFO)
    logging.getLogger("fastapi").setLevel(logging.INFO)
    logging.getLogger("uvicorn").setLevel(logging.INFO)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Comprehensive middleware to log HTTP requests and responses for debugging."""
    
    async def dispatch(self, request: Request, call_next):
        # Log request details
        logger.info(f"HTTP {request.method} {request.url.path}")
        logger.info(f"Query params: {dict(request.query_params)}")
        logger.info(f"Headers: {dict(request.headers)}")
        
        # Try to read body for debugging (only for reasonable sizes)
        if request.method in ("POST", "PUT", "PATCH"):
            try:
                body = await request.body()
                if len(body) < 10000:  # Only log bodies under 10KB
                    try:
                        body_str = body.decode('utf-8')
                        logger.info(f"Request body: {body_str}")
                    except UnicodeDecodeError:
                        logger.info(f"Request body (binary): {len(body)} bytes")
                else:
                    logger.info(f"Request body: {len(body)} bytes (too large to log)")
            except Exception as e:
                logger.warning(f"Could not read request body: {e}")
        
        # Process the request and capture response details
        try:
            response = await call_next(request)
            logger.info(f"Response status: {response.status_code}")
            
            # Log response headers for debugging
            if response.status_code >= 400:
                logger.error(f"ERROR RESPONSE {response.status_code} for {request.method} {request.url.path}")
                logger.error(f"Response headers: {dict(response.headers)}")
                
                # Try to capture response body for 400 errors
                if hasattr(response, 'body'):
                    try:
                        # This might not work for all response types, but worth trying
                        logger.error(f"Response body preview: {str(response.body)[:500]}")
                    except Exception as e:
                        logger.debug(f"Could not read response body: {e}")
            
            return response
        except Exception as e:
            logger.error(f"Request processing error for {request.method} {request.url.path}: {e}")
            logger.error(f"Exception type: {type(e).__name__}")
            logger.error(f"Exception details: {str(e)}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise


# Global initialization state
_initialization_lock = threading.Lock()
_is_initialized = threading.Event()
_cli_status: Optional[dict[str, bool]] = None
_initialization_completed = False


def require_initialization(func):
    """Decorator to ensure server is initialized before executing tool functions."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # For streamable-http, we need to be more lenient with initialization
        # Set initialization if not already set to avoid blocking
        if not _is_initialized.is_set():
            logger.info("Initializing server state on first request...")
            _initialize_cli_status()
            _is_initialized.set()
        
        return await func(*args, **kwargs)
    return wrapper


def _initialize_cli_status():
    """Initialize CLI status in a thread-safe way."""
    global _cli_status, _initialization_completed
    
    if _cli_status is not None and _initialization_completed:
        return _cli_status
    
    with _initialization_lock:
        if _cli_status is None:
            logger.info("Running CLI availability checks...")
            # Set defaults first
            _cli_status = {tool: False for tool in SUPPORTED_CLI_TOOLS}
            
            # Check each tool availability
            for cli_tool in SUPPORTED_CLI_TOOLS:
                try:
                    cmd = SUPPORTED_CLI_TOOLS[cli_tool]["check_cmd"]
                    result = subprocess.run(
                        cmd.split(), 
                        capture_output=True, 
                        text=True, 
                        timeout=5,  # Short timeout for each check
                        check=False  # Don't raise exception on non-zero exit
                    )
                    if result.returncode == 0:
                        logger.info("%s is installed and available", cli_tool)
                        _cli_status[cli_tool] = True
                    else:
                        logger.warning("%s is not installed or not in PATH", cli_tool)
                except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
                    logger.warning("Error checking %s installation: %s", cli_tool, e)
                    _cli_status[cli_tool] = False
            
            # Log warning if kubectl is not available
            if not _cli_status.get("kubectl", False):
                logger.warning("kubectl is required but not found. Server will start with limited functionality.")
            
            _initialization_completed = True
            logger.info("CLI availability checks completed successfully")
    
    return _cli_status


@asynccontextmanager
async def lifespan(_app: FastMCP):
    """Minimal lifespan manager for FastMCP streamable-http compatibility."""
    logger.info("K8s MCP Server starting up...")
    
    # Add request logging if enabled
    if MCP_LOG_REQUESTS:
        # This will be handled by FastMCP's internal logging
        logger.info("HTTP request logging is enabled")
    
    yield
    logger.info("K8s MCP Server shutting down...")


def get_cli_status() -> dict[str, bool]:
    """Get CLI status, initializing if necessary."""
    if _cli_status is None or not _initialization_completed:
        return _initialize_cli_status()
    
    return _cli_status


# Create the FastMCP server with minimal configuration for streamable-http compatibility
# Pre-initialize CLI status to avoid lazy initialization issues
logger.info("Pre-initializing K8s MCP Server...")
_initialize_cli_status()
_is_initialized.set()
logger.info("Pre-initialization completed")

mcp = AuthenticatedFastMCP(
    name="K8s MCP Server",
    instructions=INSTRUCTIONS,
    version=__version__,
    settings={},
    host=MCP_HOST,
    port=MCP_PORT,
    lifespan=lifespan,  # Required for streamable-http mode
    bearer_token=MCP_HTTP_BEARER_TOKEN if MCP_HTTP_BEARER_TOKEN else None
)

logger.info("FastMCP server created successfully")
logger.info(f"Server details - Name: K8s MCP Server, Version: {__version__}")
logger.info(f"Host: {MCP_HOST}, Port: {MCP_PORT}")
logger.info(f"Available mcp methods: {[method for method in dir(mcp) if not method.startswith('_')]}")

# Enhanced logging for debugging
if MCP_DEBUG:
    logger.debug("K8s MCP Server initialized with debug mode")
    logger.debug(f"Host: {MCP_HOST}, Port: {MCP_PORT}")
    logger.debug(f"CLI status: {get_cli_status()}")
    logger.debug(f"Supported CLI tools: {list(SUPPORTED_CLI_TOOLS.keys())}")
    logger.debug(f"Instructions: {INSTRUCTIONS[:200]}..." if len(INSTRUCTIONS) > 200 else INSTRUCTIONS)

# For now, we'll add enhanced logging at the tool level instead of middleware
# The 400 errors will be captured by the FastMCP internal error handling
logger.info("Enhanced error logging enabled - will capture request details in tool functions")

# Add global exception logging
import sys
import traceback
def log_unhandled_exception(exc_type, exc_value, exc_traceback):
    """Log unhandled exceptions that might cause 400 errors."""
    logger.error("=== UNHANDLED EXCEPTION ===")
    logger.error(f"Unhandled exception: {exc_type.__name__}: {exc_value}")
    logger.error("".join(traceback.format_exception(exc_type, exc_value, exc_traceback)))

# Set the exception hook
sys.excepthook = log_unhandled_exception

# Register prompt templates
register_prompts(mcp)


async def _execute_tool_command(tool: str, command: str, timeout: int | None, ctx: Context | None) -> CommandResult:
    """Internal implementation for executing tool commands.

    Args:
        tool: The CLI tool name (kubectl, istioctl, helm, argocd, tibcop)
        command: The command to execute
        timeout: Optional timeout in seconds
        ctx: Optional MCP context for request tracking

    Returns:
        CommandResult containing output and status
    """
    # Enhanced logging for debugging 400 errors
    logger.info("=== TOOL EXECUTION START ===")
    logger.info("Executing %s command: %s%s", tool, command, f" with timeout: {timeout}" if timeout else "")
    logger.info("Context available: %s", ctx is not None)
    
    try:
        # Add debug logging to track function calls
        if MCP_DEBUG:
            logger.debug(f"_execute_tool_command called with tool={tool}, command={command}")
            logger.debug(f"Current thread: {threading.current_thread().name}")
            logger.debug(f"CLI status: {get_cli_status()}")

        # Get current CLI status
        cli_status = get_cli_status()

        # Check if tool is installed
        if not cli_status.get(tool, False):
            message = f"{tool} is not installed or not in PATH"
            logger.error(f"Tool not available: {message}")
            if ctx:
                await ctx.error(message)
            return CommandResult(status="error", output=message)

        # Handle timeout default
        actual_timeout = timeout if timeout is not None else DEFAULT_TIMEOUT

        # Add tool prefix if not present
        if not command.strip().startswith(tool):
            command = f"{tool} {command}"

        if ctx:
            is_pipe = "|" in command
            message = "Executing" + (" piped" if is_pipe else "") + f" {tool} command"
            await ctx.info(message + (f" with timeout: {actual_timeout}s" if actual_timeout else ""))

        logger.info("About to execute command: %s", command)
        result = await execute_command(command, timeout=actual_timeout)
        logger.info("Command execution completed with status: %s", result.get("status", "unknown"))

        if result["status"] == "success":
            if ctx:
                await ctx.info(f"{tool} command executed successfully")
            logger.info("=== TOOL EXECUTION SUCCESS ===")
        else:
            if ctx:
                await ctx.warning(f"{tool} command failed")
            logger.warning("=== TOOL EXECUTION FAILED ===")
            logger.warning("Error details: %s", result.get("output", "No error output"))

        return result
        
    except Exception as e:
        error_msg = f"Exception in _execute_tool_command: {e}"
        logger.error("=== TOOL EXECUTION EXCEPTION ===")
        logger.error(error_msg)
        logger.error(f"Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        
        if ctx:
            await ctx.error(error_msg)
        
        # Create appropriate error result based on exception type
        if isinstance(e, (CommandValidationError, CommandExecutionError, AuthenticationError, CommandTimeoutError)):
            return create_error_result(e, command=command)
        else:
            error = CommandExecutionError(f"Unexpected error: {str(e)}", {"command": command})
            return create_error_result(error, command=command)


# Tool-specific command documentation functions
@mcp.tool()
@require_initialization
async def describe_kubectl(
    command: str | None = Field(description="Specific kubectl command to get help for", default=None),
    ctx: Context | None = None,
) -> CommandHelpResult:
    """Get documentation and help text for kubectl commands.

    Args:
        command: Specific command or subcommand to get help for (e.g., 'get pods')
        ctx: Optional MCP context for request tracking

    Returns:
        CommandHelpResult containing the help text
    """
    logger.info("=== DESCRIBE_KUBECTL START ===")
    logger.info("Getting kubectl documentation for command: %s", command or 'None')
    logger.info("Context available: %s", ctx is not None)
    
    try:
        # Add debug logging to track tool function calls
        if MCP_DEBUG:
            logger.debug(f"describe_kubectl called with command={command}")

        # Check if kubectl is installed
        cli_status = get_cli_status()
        if not cli_status.get("kubectl", False):
            message = "kubectl is not installed or not in PATH"
            logger.error(f"Tool check failed: {message}")
            if ctx:
                await ctx.error(message)
            return CommandHelpResult(help_text=message, status="error")

        if ctx:
            await ctx.info(f"Fetching kubectl help for {command or 'general usage'}")

        result = await get_command_help("kubectl", command)
        if ctx and result.status == "error":
            await ctx.error(f"Error retrieving kubectl help: {result.help_text}")
        
        logger.info("=== DESCRIBE_KUBECTL COMPLETED ===")
        return result
        
    except Exception as e:
        logger.error("=== DESCRIBE_KUBECTL EXCEPTION ===")
        logger.error(f"Error in describe_kubectl: {e}")
        logger.error(f"Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        
        if ctx:
            await ctx.error(f"Unexpected error retrieving kubectl help: {str(e)}")
        return CommandHelpResult(help_text=f"Error retrieving kubectl help: {str(e)}", status="error", error={"message": str(e), "code": "INTERNAL_ERROR"})


@mcp.tool()
@require_initialization
async def describe_helm(
    command: str | None = Field(description="Specific Helm command to get help for", default=None),
    ctx: Context | None = None,
) -> CommandHelpResult:
    """Get documentation and help text for Helm commands.

    Args:
        command: Specific command or subcommand to get help for (e.g., 'list')
        ctx: Optional MCP context for request tracking

    Returns:
        CommandHelpResult containing the help text
    """
    logger.info("Getting Helm documentation for command: %s", command or 'None')

    # Check if Helm is installed
    cli_status = get_cli_status()
    if not cli_status.get("helm", False):
        message = "helm is not installed or not in PATH"
        if ctx:
            await ctx.error(message)
        return CommandHelpResult(help_text=message, status="error")

    try:
        if ctx:
            await ctx.info(f"Fetching Helm help for {command or 'general usage'}")

        result = await get_command_help("helm", command)
        if ctx and result.status == "error":
            await ctx.error(f"Error retrieving Helm help: {result.help_text}")
        return result
    except Exception as e:
        logger.error(f"Error in describe_helm: {e}")
        if ctx:
            await ctx.error(f"Unexpected error retrieving Helm help: {str(e)}")
        return CommandHelpResult(help_text=f"Error retrieving Helm help: {str(e)}", status="error", error={"message": str(e), "code": "INTERNAL_ERROR"})


@mcp.tool()
@require_initialization
async def describe_istioctl(
    command: str | None = Field(description="Specific Istio command to get help for", default=None),
    ctx: Context | None = None,
) -> CommandHelpResult:
    """Get documentation and help text for Istio commands.

    Args:
        command: Specific command or subcommand to get help for (e.g., 'analyze')
        ctx: Optional MCP context for request tracking

    Returns:
        CommandHelpResult containing the help text
    """
    logger.info("Getting istioctl documentation for command: %s", command or 'None')

    # Check if istioctl is installed
    cli_status = get_cli_status()
    if not cli_status.get("istioctl", False):
        message = "istioctl is not installed or not in PATH"
        if ctx:
            await ctx.error(message)
        return CommandHelpResult(help_text=message, status="error")

    try:
        if ctx:
            await ctx.info(f"Fetching istioctl help for {command or 'general usage'}")

        result = await get_command_help("istioctl", command)
        if ctx and result.status == "error":
            await ctx.error(f"Error retrieving istioctl help: {result.help_text}")
        return result
    except Exception as e:
        logger.error(f"Error in describe_istioctl: {e}")
        if ctx:
            await ctx.error(f"Unexpected error retrieving istioctl help: {str(e)}")
        return CommandHelpResult(help_text=f"Error retrieving istioctl help: {str(e)}", status="error", error={"message": str(e), "code": "INTERNAL_ERROR"})


@mcp.tool()
@require_initialization
async def describe_argocd(
    command: str | None = Field(description="Specific ArgoCD command to get help for", default=None),
    ctx: Context | None = None,
) -> CommandHelpResult:
    """Get documentation and help text for ArgoCD commands.

    Args:
        command: Specific command or subcommand to get help for (e.g., 'app')
        ctx: Optional MCP context for request tracking

    Returns:
        CommandHelpResult containing the help text
    """
    logger.info("Getting ArgoCD documentation for command: %s", command or 'None')

    # Check if ArgoCD is installed
    cli_status = get_cli_status()
    if not cli_status.get("argocd", False):
        message = "argocd is not installed or not in PATH"
        if ctx:
            await ctx.error(message)
        return CommandHelpResult(help_text=message, status="error")

    try:
        if ctx:
            await ctx.info(f"Fetching ArgoCD help for {command or 'general usage'}")

        result = await get_command_help("argocd", command)
        if ctx and result.status == "error":
            await ctx.error(f"Error retrieving ArgoCD help: {result.help_text}")
        return result
    except Exception as e:
        logger.error(f"Error in describe_argocd: {e}")
        if ctx:
            await ctx.error(f"Unexpected error retrieving ArgoCD help: {str(e)}")
        return CommandHelpResult(help_text=f"Error retrieving ArgoCD help: {str(e)}", status="error", error={"message": str(e), "code": "INTERNAL_ERROR"})


@mcp.tool()
@require_initialization
async def describe_tibcop(
    command: str | None = Field(description="Specific TIBCO Platform CLI command to get help for", default=None),
    ctx: Context | None = None,
) -> CommandHelpResult:
    """Get documentation and help text for TIBCO Platform CLI commands.

    IMPORTANT: tibcop is designed for non-interactive use. For automation:
    - Set TIBCOP_CLI_CPURL and TIBCOP_CLI_OAUTH_TOKEN environment variables
    - Use --json flag for machine-readable output
    - Use --onlyPrintScripts flag for script generation
    - Avoid interactive commands like 'login', 'init', 'add-profile'

    Args:
        command: Specific command or subcommand to get help for (e.g., 'tplatform', 'thub')
        ctx: Optional MCP context for request tracking

    Returns:
        CommandHelpResult containing the help text
    """
    logger.info("Getting TIBCO Platform CLI documentation for command: %s", command or 'None')

    # Check if tibcop is installed
    cli_status = get_cli_status()
    if not cli_status.get("tibcop", False):
        message = "tibcop is not installed or not in PATH"
        if ctx:
            await ctx.error(message)
        return CommandHelpResult(help_text=message, status="error")

    try:
        if ctx:
            await ctx.info(f"Fetching TIBCO Platform CLI help for {command or 'general usage'}")

        result = await get_command_help("tibcop", command)
        if ctx and result.status == "error":
            await ctx.error(f"Error retrieving TIBCO Platform CLI help: {result.help_text}")
        return result
    except Exception as e:
        logger.error(f"Error in describe_tibcop: {e}")
        if ctx:
            await ctx.error(f"Unexpected error retrieving TIBCO Platform CLI help: {str(e)}")
        return CommandHelpResult(help_text=f"Error retrieving TIBCO Platform CLI help: {str(e)}", status="error", error={"message": str(e), "code": "INTERNAL_ERROR"})


# Tool-specific command execution functions
@mcp.tool(
    description="Execute kubectl commands with support for Unix pipes.",
)
@require_initialization
async def execute_kubectl(
    command: str = Field(description="Complete kubectl command to execute (including any pipes and flags)"),
    timeout: int | None = Field(description="Maximum execution time in seconds (default: 300)", default=None),
    ctx: Context | None = None,
) -> CommandResult:
    """Execute kubectl commands with support for Unix pipes.

    Executes kubectl commands with proper validation, error handling, and resource limits.
    Supports piping output to standard Unix utilities for filtering and transformation.

    Security considerations:
    - Commands are validated against security policies
    - Dangerous operations require specific resource names
    - Interactive shells via kubectl exec are restricted

    Examples:
        kubectl get pods
        kubectl get pods -o json | jq '.items[].metadata.name'
        kubectl describe pod my-pod
        kubectl logs my-pod -c my-container

    Args:
        command: Complete kubectl command to execute (can include Unix pipes)
        timeout: Optional timeout in seconds
        ctx: Optional MCP context for request tracking

    Returns:
        CommandResult containing output and status with structured error information
    """
    return await _execute_tool_command("kubectl", command, timeout, ctx)


@mcp.tool(
    description="Execute Helm commands with support for Unix pipes.",
)
@require_initialization
async def execute_helm(
    command: str = Field(description="Complete Helm command to execute (including any pipes and flags)"),
    timeout: int | None = Field(description="Maximum execution time in seconds (default: 300)", default=None),
    ctx: Context | None = None,
) -> CommandResult:
    """Execute Helm commands with support for Unix pipes.

    Executes Helm commands with proper validation, error handling, and resource limits.
    Supports piping output to standard Unix utilities for filtering and transformation.

    Security considerations:
    - Commands are validated against security policies
    - Dangerous operations like delete/uninstall require confirmation

    Examples:
        helm list
        helm status my-release
        helm get values my-release
        helm get values my-release -o json | jq '.global'

    Args:
        command: Complete Helm command to execute (can include Unix pipes)
        timeout: Optional timeout in seconds
        ctx: Optional MCP context for request tracking

    Returns:
        CommandResult containing output and status with structured error information
    """
    return await _execute_tool_command("helm", command, timeout, ctx)


@mcp.tool(
    description="Execute Istio commands with support for Unix pipes.",
)
@require_initialization
async def execute_istioctl(
    command: str = Field(description="Complete Istio command to execute (including any pipes and flags)"),
    timeout: int | None = Field(description="Maximum execution time in seconds (default: 300)", default=None),
    ctx: Context | None = None,
) -> CommandResult:
    """Execute Istio commands with support for Unix pipes.

    Executes istioctl commands with proper validation, error handling, and resource limits.
    Supports piping output to standard Unix utilities for filtering and transformation.

    Security considerations:
    - Commands are validated against security policies
    - Experimental commands and proxy-config access are restricted

    Examples:
        istioctl version
        istioctl analyze
        istioctl proxy-status
        istioctl dashboard kiali

    Args:
        command: Complete Istio command to execute (can include Unix pipes)
        timeout: Optional timeout in seconds
        ctx: Optional MCP context for request tracking

    Returns:
        CommandResult containing output and status with structured error information
    """
    return await _execute_tool_command("istioctl", command, timeout, ctx)


@mcp.tool(
    description="Execute ArgoCD commands with support for Unix pipes.",
)
@require_initialization
async def execute_argocd(
    command: str = Field(description="Complete ArgoCD command to execute (including any pipes and flags)"),
    timeout: int | None = Field(description="Maximum execution time in seconds (default: 300)", default=None),
    ctx: Context | None = None,
) -> CommandResult:
    """Execute ArgoCD commands with support for Unix pipes.

    Executes ArgoCD commands with proper validation, error handling, and resource limits.
    Supports piping output to standard Unix utilities for filtering and transformation.

    Security considerations:
    - Commands are validated against security policies
    - Destructive operations like app delete and repo removal are restricted

    Examples:
        argocd app list
        argocd app get my-app
        argocd cluster list
        argocd repo list

    Args:
        command: Complete ArgoCD command to execute (can include Unix pipes)
        timeout: Optional timeout in seconds
        ctx: Optional MCP context for request tracking

    Returns:
        CommandResult containing output and status with structured error information
    """
    return await _execute_tool_command("argocd", command, timeout, ctx)


@mcp.tool(
    description="Execute TIBCO Platform CLI commands with support for Unix pipes.",
)
@require_initialization
async def execute_tibcop(
    command: str = Field(description="Complete TIBCO Platform CLI command to execute (including any pipes and flags)"),
    timeout: int | None = Field(description="Maximum execution time in seconds (default: 300)", default=None),
    ctx: Context | None = None,
) -> CommandResult:
    """Execute TIBCO Platform CLI commands with support for Unix pipes.

    Executes tibcop commands with proper validation, error handling, and resource limits.
    Supports piping output to standard Unix utilities for filtering and transformation.

    IMPORTANT: tibcop is designed for non-interactive use with environment variables.
    
    Required environment variables:
    - TIBCOP_CLI_CPURL: Control Plane URL
    - TIBCOP_CLI_OAUTH_TOKEN: OAuth authentication token
    
    Recommended practices:
    - Always use --json flag for machine-readable output
    - Use --onlyPrintScripts for script generation without execution
    - Set specific environment variables for dataplane operations

    Security considerations:
    - Commands are validated against security policies
    - Authentication tokens and credentials are handled securely
    - Interactive commands are restricted

    Examples:
        tibcop --help
        tibcop list-profiles
        tibcop tplatform:list-dataplanes --json
        tibcop tplatform:register-k8s-dataplane --onlyPrintScripts --name=dp-name
        tibcop tplatform:provision-capability --dataplane-name=dp-name --capability=FLOGO
        tibcop tplatform:list-resource-instances --dataplane-name=dp-name --json | jq '.[]'

    Args:
        command: Complete TIBCO Platform CLI command to execute (can include Unix pipes)
        timeout: Optional timeout in seconds
        ctx: Optional MCP context for request tracking

    Returns:
        CommandResult containing output and status with structured error information
    """
    return await _execute_tool_command("tibcop", command, timeout, ctx)
