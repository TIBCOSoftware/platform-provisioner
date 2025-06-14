# MCP Servers Environment Variable Configuration

This document describes the environment variables available for configuring the two FastMCP-based servers.

## k8s_mcp_server

The Kubernetes MCP server supports the following environment variables:

### Server Configuration
- `K8S_MCP_HOST`: Host to bind the server to (default: "127.0.0.1")
- `K8S_MCP_PORT`: Port to bind the server to (default: 8091)
- `K8S_MCP_TRANSPORT`: Transport protocol ("stdio", "sse", or "streamable-http", default: "stdio")

### Command Execution Settings
- `K8S_MCP_TIMEOUT`: Custom timeout in seconds (default: 300)
- `K8S_MCP_MAX_OUTPUT`: Maximum output size in characters (default: 100000)
- `K8S_MCP_INIT_TIMEOUT`: Server initialization timeout (default: 30)
- `K8S_MCP_STARTUP_DELAY`: Additional startup delay for streamable-http (default: 2.0)

### Kubernetes Settings
- `K8S_CONTEXT`: Kubernetes context to use (default: current context)
- `K8S_NAMESPACE`: Kubernetes namespace to use (default: "default")

### Security Settings
- `K8S_MCP_SECURITY_MODE`: Security mode for command validation ("strict" or "permissive", default: "strict")
- `K8S_MCP_SECURITY_CONFIG`: Path to YAML config file for security rules (default: None)

## tp_mcp_server

The TIBCO Platform MCP server supports the following environment variables:

### Server Configuration
- `K8S_MCP_SERVER_HOST`: Host to bind the server to (default: "127.0.0.1")
- `K8S_MCP_SERVER_PORT`: Port to bind the server to (default: 8090)
- `K8S_MCP_TRANSPORT`: Transport protocol (default: "streamable-http")
- `K8S_MCP_HTTP_BEARER_TOKEN`: Optional bearer token for HTTP authentication

## Container Deployment

To deploy both servers in containers and bind them to all interfaces (0.0.0.0):

### k8s_mcp_server
```bash
docker run -e K8S_MCP_HOST=0.0.0.0 -e K8S_MCP_PORT=8091 -p 8091:8091 k8s-mcp-server
```

### tp_mcp_server
```bash
docker run -e K8S_MCP_SERVER_HOST=0.0.0.0 -e K8S_MCP_SERVER_PORT=8090 -p 8090:8090 tp-mcp-server
```

## FastMCP Compatibility

Both servers now include:
- Minimal async lifespan functions for streamable-http mode compatibility
- Pre-initialization to avoid async race conditions
- Robust error handling with chunked reading for HTTP requests
- Configurable host/port binding via environment variables

## Error Handling Improvements

The tp_mcp_server includes enhanced error handling in automation_executor.py:
- Chunked reading for large HTTP responses
- Retry logic for urllib requests
- Graceful handling of IncompleteRead errors with partial output recovery
