# K8s MCP Server Authentication Setup

K8s MCP Server now supports Bearer Token authentication, similar to the TIBCO Platform MCP Server.

## Configuration

### Environment Variables

Add the following environment variable to enable authentication:

```bash
export K8S_MCP_HTTP_BEARER_TOKEN="your-k8s-secret-token"
```

### Complete Configuration Example

```bash
# Server settings
export K8S_MCP_TRANSPORT="streamable-http"
export K8S_MCP_HOST="0.0.0.0"
export K8S_MCP_PORT="8091"

# Authentication
export K8S_MCP_HTTP_BEARER_TOKEN="k8s-secret-token"

# Debug settings
export K8S_MCP_DEBUG="true"
export K8S_MCP_LOG_REQUESTS="true"

# Start server
./run-mcp-k8s.sh
```

## MCP Inspector Configuration

### For K8s MCP Server

1. **Transport Type**: Streamable HTTP
2. **URL**: `http://localhost:8091/mcp/`
3. **Authentication**: 
   - Header Name: `Authorization`
   - Bearer Token: `k8s-secret-token` (or whatever you set in K8S_MCP_HTTP_BEARER_TOKEN)

### Server Comparison

| Feature        | TIBCO Platform MCP         | K8s MCP Server              |
|----------------|----------------------------|-----------------------------|
| Default Port   | 8090                       | 8091                        |
| Token Variable | `TP_MCP_HTTP_BEARER_TOKEN` | `K8S_MCP_HTTP_BEARER_TOKEN` |
| URL Path       | `/mcp/`                    | `/mcp/`                     |
| Transport      | streamable-http            | streamable-http             |

## Authentication Behavior

- **Without token**: Server runs without authentication (all requests allowed)
- **With token**: Authentication is enforced for `/mcp` endpoints
- **Health endpoint**: Always accessible without authentication (`/health`)
- **Invalid token**: Returns HTTP 403 Forbidden
- **Missing header**: Returns HTTP 401 Unauthorized

## Testing Authentication

Use the provided test script:

```bash
# Set the token you want to test with
export K8S_MCP_HTTP_BEARER_TOKEN="k8s-test-token"

# Run the test
./debug_k8s_auth.sh
```

## Security Notes

1. **Token Storage**: Store tokens securely (environment variables, secrets management)
2. **HTTPS**: Use HTTPS in production environments
3. **Token Rotation**: Regularly rotate bearer tokens
4. **Logging**: Be careful not to log bearer tokens in debug output

## Troubleshooting

### Common Issues

1. **Connection Refused**: Check if server is running on correct port (8091)
2. **403 Forbidden**: Verify bearer token matches exactly
3. **401 Unauthorized**: Check Authorization header format (`Bearer token`)
4. **Wrong Port**: K8s MCP uses 8091, TP MCP uses 8090

### Debug Commands

```bash
# Check if server is running
curl -v http://localhost:8091/health

# Test without authentication (should work if no token set)
curl -v http://localhost:8091/mcp/

# Test with authentication
curl -v -H "Authorization: Bearer your-token" http://localhost:8091/mcp/
```

## Implementation Details

The authentication is implemented using:
- **Middleware**: `BearerTokenMiddleware` class
- **Scope**: Applied only to `/mcp` paths
- **Method**: Standard HTTP Bearer Token authentication
- **Error Responses**: JSON formatted error messages
