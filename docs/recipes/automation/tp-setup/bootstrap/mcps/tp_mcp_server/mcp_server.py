#!/usr/bin/env python3

#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary

import logging
from typing import Optional

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from .server_lifecycle import lifespan, ensure_server_ready, get_server_status, is_server_initialized
from .config import DEFAULT_VALUES, CASE_TO_MODULE, MCP_TRANSPORT, MCP_SERVER_HOST, MCP_SERVER_PORT, MCP_HTTP_BEARER_TOKEN
from .environment_tools import show_environment, create_subscription, config_o11y_widget, config_global_o11y
from .dataplane_tools import create_k8s_dataplane, config_dataplane_o11y, delete_dataplane
from .capability_tools import provision_bwce, provision_ems, provision_flogo, provision_pulsar, provision_tibcohub
from .application_tools import create_start_bwce_app, create_start_flogo_app, delete_bwce_app, delete_flogo_app
from .auth_middleware import BearerTokenMiddleware

logger = logging.getLogger('tibco-platform-provisioner-mcp')


class AuthenticatedFastMCP(FastMCP):
    """FastMCP with Bearer Token authentication support."""
    
    def __init__(self, bearer_token: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.bearer_token = bearer_token
        
    def streamable_http_app(self) -> Starlette:
        """Override to add authentication middleware."""
        app = super().streamable_http_app()
        
        # Add Bearer Token authentication middleware if configured
        if self.bearer_token:
            app.add_middleware(BearerTokenMiddleware, expected_token=self.bearer_token)
            logger.info("Bearer Token authentication middleware added to streamable-http app")
        
        return app


# Create the FastMCP server with authentication support
mcp_kwargs = {
    "name": "TIBCO Platform Automation",
    "host": MCP_SERVER_HOST,
    "port": MCP_SERVER_PORT,
    "lifespan": lifespan,  # Required for streamable-http mode
    "instructions": """
        This server provides basic functionality for TIBCO Platform. 
        It is designed for DevOps to automate the setup of TIBCO Platform environments.
        TIBCO Platform consist two main components: Control Plane (CP) and Data Plane (DP).
        This MCP automation server is designed to run automation for DP mainly.
        Call show_environment() to get the current environment.
        """,
    "bearer_token": MCP_HTTP_BEARER_TOKEN
}

# Log authentication status
if MCP_HTTP_BEARER_TOKEN:
    logger.info("Bearer Token authentication will be enforced")
else:
    logger.info("Bearer Token authentication disabled - server running without authentication")

mcp = AuthenticatedFastMCP(**mcp_kwargs)

# Environment Management Actions
@mcp.tool()
async def show_current_environment() -> str:
    """Show Current Environment (Login CP/Elastic Credentials)

    Returns:
        Information about the current environment
    """
    return await show_environment()

@mcp.tool()
async def create_user_subscription(email: str = "") -> str:
    """Create new subscription with User Email

    Args:
        email: User email address for the subscription (optional).

    Returns:
        Result of the subscription creation process
    """
    return await create_subscription(email)

# O11y Configuration Actions
@mcp.tool()
async def configure_o11y_widget() -> str:
    """Config o11y widget

    Returns:
        Result of the o11y widget configuration process
    """
    return await config_o11y_widget()

@mcp.tool()
async def configure_global_o11y(use_system_config: bool = False) -> str:
    """Config Global O11y

    Args:
        use_system_config: Whether to use the system's predefined Observability configuration.

    Returns:
        Result of the global Observability configuration process
    """
    return await config_global_o11y(use_system_config)

# DataPlane Configuration Actions
@mcp.tool()
async def create_kubernetes_dataplane(
    dp_name: str = "",
    sa_additional_settings: str = "",
    use_system_o11y: bool = False,
    kubeconfig: str = "",
    dp_host_prefix: str = "",
    dp_user_email: str = "",
    dp_user_password: str = "",
    bmdp_name: str = "",
    login_url: str = "",
    mail_url: str = "",
    bwce_app_name: str = "",
    flogo_app_name: str = "",
    headless: bool = True,
    force_run: bool = False,
    clean_report: bool = False
) -> str:
    """Create K8s DataPlane (Include run helm command)

    Args:
        dp_name: Name for the new dataplane
        sa_additional_settings: Additional settings for service account creation
        use_system_o11y: Whether to use system observability configuration
        kubeconfig: Path to custom kubeconfig file
        dp_host_prefix: Host prefix for dataplane
        dp_user_email: User email for dataplane
        dp_user_password: User password for dataplane
        bmdp_name: Name for the BMDP
        login_url: Login URL
        mail_url: Mail URL
        bwce_app_name: BWCE application name
        flogo_app_name: Flogo application name
        headless: Whether to run in headless mode
        force_run: Whether to force run the automation
        clean_report: Whether to clean the report

    Returns:
        Result of the K8s DataPlane creation process
    """
    return await create_k8s_dataplane(
        dp_name, sa_additional_settings, use_system_o11y, kubeconfig,
        dp_host_prefix, dp_user_email, dp_user_password, bmdp_name,
        login_url, mail_url, bwce_app_name, flogo_app_name,
        headless, force_run, clean_report
    )

@mcp.tool()
async def configure_dataplane_o11y(use_system_config: bool = False, dp_name: str = "") -> str:
    """Config DataPlane O11y

    Args:
        use_system_config: Whether to use the system's predefined Observability configuration.
        dp_name: Name of the Data Plane to configure O11y for.

    Returns:
        Result of the Data Plane Observability configuration process
    """
    return await config_dataplane_o11y(use_system_config, dp_name)

@mcp.tool()
async def delete_kubernetes_dataplane(dp_name: str = "") -> str:
    """Delete DataPlane (Include run helm command)

    Args:
        dp_name: Name of the dataplane to delete

    Returns:
        Result of the DataPlane deletion
    """
    return await delete_dataplane(dp_name)

# Provision Capability Actions
@mcp.tool()
async def provision_bwce_capability(dp_name: str = "") -> str:
    """Provision BWCE

    Args:
        dp_name: Name of the Data Plane to provision BWCE capability in.

    Returns:
        Result of the BWCE provisioning process
    """
    return await provision_bwce(dp_name)

@mcp.tool()
async def provision_ems_capability(dp_name: str = "") -> str:
    """Provision EMS

    Args:
        dp_name: Name of the Data Plane to provision EMS capability in.

    Returns:
        Result of the EMS provisioning process
    """
    return await provision_ems(dp_name)

@mcp.tool()
async def provision_flogo_capability(dp_name: str = "") -> str:
    """Provision Flogo

    Args:
        dp_name: Name of the Data Plane to provision Flogo capability in.

    Returns:
        Result of the Flogo provisioning process
    """
    return await provision_flogo(dp_name)

@mcp.tool()
async def provision_pulsar_capability(dp_name: str = "") -> str:
    """Provision Pulsar

    Args:
        dp_name: Name of the Data Plane to provision Pulsar capability in.

    Returns:
        Result of the Pulsar provisioning process
    """
    return await provision_pulsar(dp_name)

@mcp.tool()
async def provision_tibcohub_capability(dp_name: str = "") -> str:
    """Provision TibcoHub

    Args:
        dp_name: Name of the Data Plane to provision TIBCO Hub capability in.

    Returns:
        Result of the TibcoHub provisioning process
    """
    return await provision_tibcohub(dp_name)

# Create and Start App Actions
@mcp.tool()
async def create_and_start_bwce_app(app_name: str = "", dp_name: str = "") -> str:
    """Create And Start BWCE App

    Args:
        app_name: BWCE application name.
        dp_name: Data Plane name where to create the BWCE application.

    Returns:
        Result of the BWCE app creation and startup process
    """
    return await create_start_bwce_app(app_name, dp_name)

@mcp.tool()
async def create_and_start_flogo_app(app_name: str = "", dp_name: str = "") -> str:
    """Create And Start Flogo App

    Args:
        app_name: Flogo application name.
        dp_name: Data Plane name where to create the Flogo application.

    Returns:
        Result of the Flogo app creation and startup process
    """
    return await create_start_flogo_app(app_name, dp_name)

# Delete App Actions
@mcp.tool()
async def delete_bwce_application(app_name: str = "", dp_name: str = "") -> str:
    """Delete BWCE App

    Args:
        app_name: BWCE application name to delete.
        dp_name: Data Plane name where the application is deployed.

    Returns:
        Result of the BWCE app deletion process
    """
    return await delete_bwce_app(app_name, dp_name)

@mcp.tool()
async def delete_flogo_application(app_name: str = "", dp_name: str = "") -> str:
    """Delete Flogo App

    Args:
        app_name: Flogo application name to delete.
        dp_name: Data Plane name where the application is deployed.

    Returns:
        Result of the Flogo app deletion process
    """
    return await delete_flogo_app(app_name, dp_name)

@mcp.tool()
async def status() -> str:
    """Get the status of the TIBCO Platform Automation server

    Returns:
        A detailed report of the server status, configuration parameters, and available cases
    """
    try:
        # Check if server is ready
        server_ready = ensure_server_ready()

        status_text = "TIBCO Platform Automation Server Status\n"
        status_text += "=================================\n\n"

        if server_ready:
            status_text += "✓ Server is running and ready to accept commands\n\n"
        else:
            status_text += "⚠ Server is running but not fully ready\n\n"

        # Add initialization status
        status_text += f"Initialization Status: {'✓ Complete' if is_server_initialized() else '⚠ In Progress'}\n"

        # Add server information
        server_status = get_server_status()
        if server_status:
            status_text += f"Project Root: {server_status.get('project_root', 'Unknown')}\n"
            status_text += f"Automation Path: {server_status.get('automation_path', 'Unknown')}\n\n"

        # Add configuration information
        status_text += "Default Configuration:\n"
        status_text += "---------------------\n"
        for key in sorted(DEFAULT_VALUES.keys()):
            value = DEFAULT_VALUES[key]
            # Mask password fields for security
            if 'PASSWORD' in key:
                display_value = '********'
            else:
                display_value = value
            status_text += f"  {key}: {display_value}\n"

        # Add available automation cases
        status_text += "\nAvailable Automation Cases:\n"
        status_text += "---------------------------\n"
        for case, module in sorted(CASE_TO_MODULE.items()):
            status_text += f"  {case} -> {module}\n"

        # Add tool statistics
        status_text += f"\nServer Port: {MCP_SERVER_PORT}\n"
        status_text += f"Transport: {MCP_TRANSPORT}\n"
        status_text += f"Bearer Token: {'Set' if MCP_HTTP_BEARER_TOKEN else 'Not Set'}\n"
        status_text += f"Ready for Commands: {'Yes' if server_ready else 'No'}\n"

        return status_text

    except RuntimeError as e:
        error_status = "TIBCO Platform Automation Server Status\n"
        error_status += "=================================\n\n"
        error_status += f"Server may still be initializing or encountered an error: {str(e)}\n"
        return error_status

# Basic dynamic resource returning a string
@mcp.resource("resource://greeting")
def get_greeting() -> str:
    """Provides a simple greeting message."""
    return "Welcome to TIBCO Platform Infrastructure MCP server!"

# For manual testing
if __name__ == "__main__":
    logger.info("TIBCO Platform Automation MCP Server initialized")
    from .config import PROJECT_ROOT, AUTOMATION_PATH
    logger.info("Project root: %s", PROJECT_ROOT)
    logger.info("Automation path: %s", AUTOMATION_PATH)
    logger.info("MCP Server Configuration:")
    logger.info("  Transport: %s", MCP_TRANSPORT)
    logger.info("  Port: %d", MCP_SERVER_PORT)
    logger.info("  Bearer Token: %s", "Set" if MCP_HTTP_BEARER_TOKEN else "Not Set")
    
    # Use configured transport (with type casting to satisfy type checker)
    transport_type = MCP_TRANSPORT  # type: ignore
    mcp.run(transport=transport_type)
