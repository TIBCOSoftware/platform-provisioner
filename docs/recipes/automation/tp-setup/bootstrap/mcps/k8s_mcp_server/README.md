# K8s MCP Server - Fixed Version

## Problem Description

The original K8s MCP Server was experiencing initialization issues with the following errors:
- `RuntimeError: Received request before initialization was complete`
- `RuntimeError: Task group is not initialized. Make sure to use run().`

## Fixed Issues

### 1. Race Condition in Initialization
**Problem**: The server was receiving requests before the initialization process completed, causing task group errors.

**Solution**: 
- Added proper lifespan management with `@asynccontextmanager`
- Implemented initialization state tracking with `threading.Event`
- Added proper startup sequence and initialization checks

### 2. CLI Tool Check Blocking
**Problem**: Synchronous CLI tool checks during server startup could block the async event loop.

**Solution**:
- Moved CLI tool checks to thread pool execution
- Added proper error handling and timeout mechanisms
- Implemented graceful degradation for missing tools

### 3. Concurrent Request Handling
**Problem**: Multiple requests arriving simultaneously could cause initialization race conditions.

**Solution**:
- Added thread-safe initialization locks
- Implemented request queuing until initialization completes
- Added proper error responses for pre-initialization requests

## New Features

### Health Check Script
A new health check script `health_check.py` is available to verify server status:

```bash
python -m k8s_mcp_server.health_check
```

### Enhanced Configuration
New environment variables for better control:
- `K8S_MCP_INIT_TIMEOUT`: Server initialization timeout (default: 30 seconds)
- `K8S_MCP_STARTUP_DELAY`: Additional startup delay for streamable-http (default: 2.0 seconds)

## Usage

### Basic Usage
```bash
# Run with stdio transport (default)
python -m k8s_mcp_server

# Run with streamable-http transport
K8S_MCP_TRANSPORT=streamable-http python -m k8s_mcp_server
```

### Environment Variables
```bash
export K8S_MCP_TRANSPORT=streamable-http
export K8S_MCP_INIT_TIMEOUT=45
export K8S_MCP_STARTUP_DELAY=3.0
export K8S_MCP_TIMEOUT=300
```

### Docker Usage
```bash
# Build the container
docker build -t k8s-mcp-server .

# Run with default settings
docker run -p 8091:8091 k8s-mcp-server

# Run with custom environment
docker run -p 8091:8091 \
  -e K8S_MCP_TRANSPORT=streamable-http \
  -e K8S_MCP_INIT_TIMEOUT=45 \
  k8s-mcp-server
```

## Architecture Changes

### Before (Original)
```
Server Start → CLI Checks (blocking) → FastMCP Run
     ↓
Requests → Direct CLI Status Access → Potential Race Condition
```

### After (Fixed)
```
Server Start → Lifespan Manager → Thread Pool CLI Checks → Set Initialized
     ↓                              ↓
Requests → Check Initialized → Wait if needed → Get CLI Status → Execute
```

## Troubleshooting

### Common Issues

#### 1. Server Still Getting Initialization Errors
```bash
# Check if all required tools are available
kubectl version --client
helm version
istioctl version --remote=false
argocd version --client

# Run health check
python -m k8s_mcp_server.health_check

# Increase initialization timeout
export K8S_MCP_INIT_TIMEOUT=60
```

#### 2. Slow Startup with streamable-http
```bash
# Increase startup delay
export K8S_MCP_STARTUP_DELAY=5.0

# Or switch to stdio transport for faster startup
export K8S_MCP_TRANSPORT=stdio
```
