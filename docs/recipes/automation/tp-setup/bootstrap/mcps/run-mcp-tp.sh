#!/bin/bash

#
# Copyright © 2025. Cloud Software Group, Inc.
# This file is subject to the license terms contained
# in the license file that is distributed with this file.
#

set -e
/tmp/auto-py-env/bin/fastmcp run -t streamable-http /app/mcps/tp_mcp_server/mcp-server.py
