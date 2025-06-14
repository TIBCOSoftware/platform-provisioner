# TIBCO Platform MCP Server

TIBCO Platform MCP (Model Context Protocol) Server provides automation capabilities for TIBCO Platform environments, including Data Plane management, capability provisioning, and application deployment.

## Architecture

The server is structured as a Python package with the following components:

- `__main__.py` - Main entry point for the server
- `__init__.py` - Package initialization
- `mcp_server.py` - FastMCP server definition and tool registration
- `config.py` - Configuration management
- `server_lifecycle.py` - Server lifecycle management
- `*_tools.py` - Various tool modules for different functionalities

## Running the Server

### Using Python Module (Recommended)

```bash
# From the mcps directory
cd /path/to/mcps
python -m tp_mcp_server
```

### Using the Shell Script

```bash
# Run the provided shell script
./run-mcp-tp.sh
```

### Environment Variables

The server can be configured using environment variables:

- `K8S_MCP_TRANSPORT` - Transport protocol (default: "streamable-http")
- `K8S_MCP_SERVER_HOST` - Server host (default: "0.0.0.0")  
- `K8S_MCP_SERVER_PORT` - Server port (default: "8090")
- `K8S_MCP_HTTP_BEARER_TOKEN` - Bearer token for authentication (optional)

## Available Tools

The server provides the following categories of tools:

### Environment Management
- `show_current_environment()` - Display current environment information
- `create_user_subscription()` - Create user subscription
- `configure_global_o11y()` - Configure global observability
- `configure_o11y_widget()` - Configure observability widget

### Data Plane Management  
- `create_kubernetes_dataplane()` - Create K8s Data Plane
- `configure_dataplane_o11y()` - Configure Data Plane observability
- `delete_kubernetes_dataplane()` - Delete Data Plane

### Capability Provisioning
- `provision_bwce_capability()` - Provision BWCE capability
- `provision_ems_capability()` - Provision EMS capability  
- `provision_flogo_capability()` - Provision Flogo capability
- `provision_pulsar_capability()` - Provision Pulsar capability
- `provision_tibcohub_capability()` - Provision TIBCO Hub capability

### Application Management
- `create_and_start_bwce_app()` - Create and start BWCE application
- `create_and_start_flogo_app()` - Create and start Flogo application
- `delete_bwce_application()` - Delete BWCE application
- `delete_flogo_application()` - Delete Flogo application

## Server Status

Use the `status()` tool to get detailed information about the server configuration and available automation cases.

## Transport Protocols

The server supports multiple transport protocols:

- **streamable-http** (default) - HTTP-based transport for web clients
- **stdio** - Standard input/output for command-line clients  
- **sse** - Server-sent events for streaming clients

## Logging

The server uses structured logging with configurable levels. Debug mode can be enabled by setting a bearer token.

## Integration

This server is designed to integrate with:

- TIBCO Control Plane environments
- Kubernetes clusters  
- TIBCO Platform automation workflows
- MCP-compatible clients (like Claude Desktop, VS Code, etc.)
