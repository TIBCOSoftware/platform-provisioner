#!/bin/bash

#
# Copyright © 2025. Cloud Software Group, Inc.
# This file is subject to the license terms contained
# in the license file that is distributed with this file.
#

set -e

cd /app/mcps

export K8S_MCP_TRANSPORT=streamable-http
python -m k8s_mcp_server
