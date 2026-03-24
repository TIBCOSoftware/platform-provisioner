#!/bin/bash

#
# Copyright 2025 Cloud Software Group, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

set -e

# Change to mcps directory if it exists (for container environments)
if [ -d /app ]; then
  cd /app
fi

# Run TIBCO Platform MCP Server using the main module
# Set default environment variables for TIBCO Platform MCP
export TP_MCP_TRANSPORT=${TP_MCP_TRANSPORT:-"streamable-http"}
export TP_MCP_SERVER_HOST=${TP_MCP_SERVER_HOST:-"0.0.0.0"}
export TP_MCP_SERVER_PORT=${TP_MCP_SERVER_PORT:-"8090"}
export TP_MCP_HTTP_BEARER_TOKEN=${TP_MCP_HTTP_BEARER_TOKEN:-""}
export TP_MCP_DEBUG=${TP_MCP_DEBUG:-"false"}

uv run -m mcps.tp_automation_mcp_server
