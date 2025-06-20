# TIBCO Platform MCP Server Environment Variables

## Environment Variables

TIBCO Platform MCP Server uses environment variables with the `TP_MCP_*` prefix for configuration:

### Environment Variable Configuration

```bash
# Transport protocol (stdio, sse, streamable-http)
export TP_MCP_TRANSPORT="streamable-http"

# Server host address
export TP_MCP_SERVER_HOST="0.0.0.0"

# Server port
export TP_MCP_SERVER_PORT="8090"

# Bearer authentication token
export TP_MCP_HTTP_BEARER_TOKEN="your-secret-token"

# Debug mode (true/false)
export TP_MCP_DEBUG="true"
```

## Bearer Token Usage

Bearer Token can be used for server authentication:

```bash
# Set Bearer Token
export TP_MCP_HTTP_BEARER_TOKEN="your-secret-bearer-token"

# Start server
python -m tp_automation_mcp_server
```

Server startup will display:

```text
Server configuration: host=0.0.0.0, port=8090, bearer_token=Set, debug=false
```

## Debug Mode

Enable Debug mode:

```bash
export TP_MCP_DEBUG="true"
# or
export TP_MCP_DEBUG="1"
# or
export TP_MCP_DEBUG="yes"
```

When Debug mode is enabled:

- Log level is set to DEBUG
- More detailed debug information is displayed
- Uvicorn server also enables debug mode

## Test Configuration

Verify configuration is correct:

```bash
# Set environment variables
export TP_MCP_HTTP_BEARER_TOKEN="test-token"
export TP_MCP_DEBUG="true"

# Test configuration
python -c "import sys; sys.path.append('./tp_mcp_server'); from config import MCP_HTTP_BEARER_TOKEN, MCP_DEBUG; print(f'Bearer Token: {MCP_HTTP_BEARER_TOKEN}'); print(f'Debug Mode: {MCP_DEBUG}')"
```

Expected output:

```text
Bearer Token: test-token
Debug Mode: True
```

## Complete Startup Example

```bash
#!/bin/bash

# Set TIBCO Platform MCP Server configuration
export TP_MCP_TRANSPORT="streamable-http"
export TP_MCP_SERVER_HOST="0.0.0.0"
export TP_MCP_SERVER_PORT="8090"
export TP_MCP_HTTP_BEARER_TOKEN="my-secure-token"
export TP_MCP_DEBUG="false"

# Start server
python -m tp_automation_mcp_server
```
