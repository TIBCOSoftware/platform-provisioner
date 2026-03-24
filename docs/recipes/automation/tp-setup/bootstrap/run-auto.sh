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

# by default, the TP_AUTO_TASK_FROM_LOCAL_SOURCE is empty, because of "Platform Automation Hub" should keep it empty
# for local testing, you can set TP_AUTO_TASK_FROM_LOCAL_SOURCE to "true" to load tasks from local source code
export TP_AUTO_TASK_FROM_LOCAL_SOURCE=${TP_AUTO_TASK_FROM_LOCAL_SOURCE:-""}
export TP_AUTO_KUBECONFIG=${TP_AUTO_KUBECONFIG:-""}

uv run -m waitress --host=0.0.0.0 --port=3120 server:app
