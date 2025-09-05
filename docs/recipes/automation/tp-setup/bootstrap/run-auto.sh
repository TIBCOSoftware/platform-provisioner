#!/bin/bash

#
# Copyright © 2025. Cloud Software Group, Inc.
# This file is subject to the license terms contained
# in the license file that is distributed with this file.
#

set -e

# Change to mcps directory if it exists (for container environments)
if [ -d /app ]; then
  cd /app
fi

export TP_AUTO_TASK_FROM_LOCAL_SOURCE=${TP_AUTO_TASK_FROM_LOCAL_SOURCE:-"true"}
export TP_AUTO_KUBECONFIG=${TP_AUTO_KUBECONFIG:-""}

uv run -m waitress --host=0.0.0.0 --port=3120 server:app
