#!/bin/bash

#
# Copyright © 2025. Cloud Software Group, Inc.
# This file is subject to the license terms contained
# in the license file that is distributed with this file.
#

set -e

# Run TIBCO Platform MCP Server using the main module
# Set default environment variables for TIBCO Platform MCP
export TP_MCP_TRANSPORT=${TP_MCP_TRANSPORT:-"streamable-http"}
export TP_MCP_SERVER_HOST=${TP_MCP_SERVER_HOST:-"0.0.0.0"}
export TP_MCP_SERVER_PORT=${TP_MCP_SERVER_PORT:-"8090"}
export TP_MCP_HTTP_BEARER_TOKEN=${TP_MCP_HTTP_BEARER_TOKEN:-""}
export TP_MCP_DEBUG=${TP_MCP_DEBUG:-"false"}

cd /app/mcps && /tmp/auto-py-env/bin/python -m tp_automation_mcp_server
