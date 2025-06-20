# TIBCO Platform MCP Server - Modular Architecture

This project has been refactored to split the original large `mcp-server.py` file into multiple modules based on functionality, improving code maintainability and readability.

## File Structure

### Core Modules

1. **`config.py`** - Configuration and Constants
   - Project path configuration
   - Default values configuration
   - Case-to-module mapping

2. **`server_lifecycle.py`** - Server Lifecycle Management
   - Server initialization
   - Lifecycle management
   - Server status checking

3. **`automation_executor.py`** - Core Automation Executor
   - API call execution
   - Direct module execution
   - Error handling and retry logic

### Functional Modules

1. **`environment_tools.py`** - Environment Management Tools
   - `show_environment()` - Show current environment
   - `create_subscription()` - Create user subscription
   - `config_o11y_widget()` - Configure observability widgets
   - `config_global_o11y()` - Configure global observability

2. **`dataplane_tools.py`** - Data Plane Management Tools
   - `create_k8s_dataplane()` - Create Kubernetes data plane
   - `config_dataplane_o11y()` - Configure data plane observability
   - `delete_dataplane()` - Delete data plane

3. **`capability_tools.py`** - Capability Configuration Tools
   - `provision_bwce()` - Provision BWCE capability
   - `provision_ems()` - Provision EMS capability
   - `provision_flogo()` - Provision Flogo capability
   - `provision_pulsar()` - Provision Pulsar capability
   - `provision_tibcohub()` - Provision TibcoHub capability

4. **`application_tools.py`** - Application Management Tools
   - `create_start_bwce_app()` - Create and start BWCE application
   - `create_start_flogo_app()` - Create and start Flogo application
   - `delete_bwce_app()` - Delete BWCE application
   - `delete_flogo_app()` - Delete Flogo application

### Main Server File

1. **`mcp_server.py`** - MCP Server Main File
   - FastMCP server configuration
   - All MCP tool definitions
   - Resource definitions
   - Main program entry point

## Usage

### Starting the Server

```bash
cd /path/to/tp_mcp_server
python mcp_server.py
```

### Importing and Using Modules

```python
# Import specific functional modules
from environment_tools import show_environment, create_subscription
from dataplane_tools import create_k8s_dataplane
from capability_tools import provision_bwce

# Use functions
result = await show_environment()
dataplane_result = await create_k8s_dataplane(dp_name="my-dp")
bwce_result = await provision_bwce(dp_name="my-dp")
```

## Module Dependencies

```text
mcp_server.py (main entry)
├── server_lifecycle.py (lifecycle management)
│   └── config.py (configuration)
├── environment_tools.py (environment tools)
│   ├── automation_executor.py (executor)
│   └── config.py (configuration)
├── dataplane_tools.py (data plane tools)
│   ├── automation_executor.py (executor)
│   └── config.py (configuration)
├── capability_tools.py (capability tools)
│   ├── automation_executor.py (executor)
│   └── config.py (configuration)
└── application_tools.py (application tools)
    ├── automation_executor.py (executor)
    └── config.py (configuration)
```

## Advantages

1. **Modularity**: Each file has a clear responsibility
2. **Maintainability**: Easier to find and modify specific functionality
3. **Reusability**: Can independently import and use specific modules
4. **Testability**: Can independently test each module
5. **Readability**: Clearer code structure, easier to understand

## Configuration

All configurations are defined in `config.py`, including:

- Default value settings
- Project paths
- Case mappings
- MCP Server settings

### Environment Variables

The following environment variables can be used to configure the MCP server:

- **`K8S_MCP_TRANSPORT`** - Transport protocol for the MCP server
  - Valid values: `stdio`, `sse`, `streamable-http`
  - Default: `streamable-http`
  
- **`K8S_MCP_SERVER_PORT`** - Port number for the MCP server
  - Valid values: Any valid port number (1-65535)
  - Default: `8090`
  
- **`K8S_MCP_HTTP_BEARER_TOKEN`** - Bearer token for HTTP authentication
  - Optional security token for API access
  - Default: Not set (no authentication)

### Example Usage

```bash
# Set custom transport and port
export K8S_MCP_TRANSPORT=sse
export K8S_MCP_SERVER_PORT=9090
export K8S_MCP_HTTP_BEARER_TOKEN=your-secret-token

# Start the server
python mcp_server.py
```

To modify other configurations, edit the `config.py` file directly.

## Error Handling

Each module includes appropriate error handling:

- Automatic fallback to direct module execution when API calls fail
- Detailed logging
- User-friendly error messages

## Logging

Each module has its own logger:

- `tibco-platform-provisioner-config`
- `tibco-platform-provisioner-lifecycle`
- `tibco-platform-provisioner-executor`
- `tibco-platform-provisioner-environment`
- `tibco-platform-provisioner-dataplane`
- `tibco-platform-provisioner-capability`
- `tibco-platform-provisioner-application`
- `tibco-platform-provisioner-mcp`
