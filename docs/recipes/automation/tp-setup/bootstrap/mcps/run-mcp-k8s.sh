#!/bin/bash

#
# Copyright © 2025. Cloud Software Group, Inc.
# This file is subject to the license terms contained
# in the license file that is distributed with this file.
#

set -e

cd /app/mcps

export K8S_MCP_TRANSPORT=${K8S_MCP_TRANSPORT:-"streamable-http"}
export K8S_MCP_HOST=${K8S_MCP_HOST:-"0.0.0.0"}
export K8S_MCP_PORT=${K8S_MCP_PORT:-"8091"}
export K8S_MCP_HTTP_BEARER_TOKEN=${K8S_MCP_HTTP_BEARER_TOKEN:-""}
export K8S_MCP_INIT_TIMEOUT=45
export K8S_MCP_DEBUG=${K8S_MCP_DEBUG:-"false"}
export K8S_MCP_LOG_REQUESTS=${K8S_MCP_LOG_REQUESTS:-"false"}
python -m k8s_mcp_server
