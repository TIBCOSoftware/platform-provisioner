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

"""Dashboard / card definitions for the Observability auto-configuration flow
(PCP-20053).

The Add Card catalog is built from the GLOBAL capability install status, so the
left-tree capability labels below double as the "is this capability installed?"
detection key. Card lists follow the catalog sub-menu order (first 3 per
sub-menu, verified to have no has-text substring collisions). Each capability
dashboard stays at or below the per-dashboard 15-card limit (MAX_CARD_COUNT).

This module intentionally has no third-party / environment imports so the card
definitions can be unit tested without a live cluster or browser.
"""

# Per-dashboard card limit enforced by the Observability UI (widget-list MAX_CARD_COUNT).
MAX_CARD_COUNT = 15

LOG_DASHBOARD_NAME = "logs_dashboard"

# Note: the Default dashboard is populated by "Reset Layout" (page_o11y.py), which
# restores the system-default Integration General (Kubernetes + Control Tower) and
# Messaging General cards, so no explicit Default card list is needed here.

# logs_dashboard - History Logs / Business Activities always; Audit History only
# when the Audit Trail capability is installed (detected from the catalog).
LOG_CARDS = [
    "History Logs",
    "Business Activities",
]

# BW6 (BWCE) and BW5 (BW5CE) share the same Engine/Process/Activity card set.
BW_GROUPS = [
    ("Engine", [
        "Active Thread Count",
        "CPU Utilization/Limit Percentage",
        "CPU Utilization/Request Percentage",
    ]),
    ("Process", [
        "Process Max Elapsed Time",
        "Process Max Execution Time",
        "Process Min Elapsed Time",
    ]),
    ("Activity", [
        "Activity Max Elapsed Time",
        "Activity Max Execution Time",
        "Activity Min Elapsed Time",
    ]),
]

FLOGO_GROUPS = [
    ("Engine", [
        "CPU Utilization/Limit Percentage",
        "CPU Utilization/Request Percentage",
        "Memory Usage/Limit Percentage",
    ]),
    ("Flow", ["Total Flow Executions"]),
    ("Activity", ["Total Activity Executions"]),
]

# Spring Boot has 23 cards across 9 sub-menus, which exceeds the 15-card limit,
# so it is split across two dashboards (sub-menus kept intact).
SB_GROUPS_1 = [
    ("Batch", ["Batch Items Read", "Batch Items Written", "Batch Job Execution Time"]),
    ("Database", ["Active Database Connections", "Database Query Duration", "Pending Connection Requests"]),
    ("HTTP", ["Active HTTP Requests", "Outbound Request Latency", "Outbound Request Volume"]),
    ("JMS", ["JMS Messages Transmitted", "JMS Processing Duration"]),
    ("JVM", ["GC CPU Overhead", "JVM CPU Utilization", "JVM Memory Usage"]),
]
SB_GROUPS_2 = [
    ("Kafka", ["Kafka Average Batch Size", "Kafka Consumer Lag", "Kafka Producer Errors"]),
    ("Security", ["Authorization Denials", "Scheduled Task Failures", "Successful Authentications"]),
    ("System", ["Open File Descriptors", "System CPU Usage"]),
    ("Tomcat", ["Tomcat Busy Threads"]),
]

# Each spec: dashboard name, the catalog capability label that must exist, and the
# (sub-menu, cards) groups to add. The capability label is also the level1 menu.
CAPABILITY_DASHBOARDS = [
    {"name": "BW6_dashboard", "capability": "BW6 (Containers)", "groups": BW_GROUPS},
    {"name": "Flogo_dashboard", "capability": "Flogo", "groups": FLOGO_GROUPS},
    {"name": "BW5_dashboard", "capability": "BW5 (Containers)", "groups": BW_GROUPS},
    {"name": "SB_dashboard", "capability": "Spring Boot", "groups": SB_GROUPS_1},
    {"name": "SB_dashboard_2", "capability": "Spring Boot", "groups": SB_GROUPS_2},
]
