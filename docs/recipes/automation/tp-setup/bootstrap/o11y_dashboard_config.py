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
(PCP-20053, PCP-20424).

The Add Card catalog is built from the GLOBAL capability install status, so the
left-tree capability labels below double as the "is this capability installed?"
detection key. The per-app-type capability dashboards (BW6/Flogo/BW5/Spring Boot)
sample the first 3 cards per sub-menu (verified to have no has-text substring
collisions); the Integration General / Messaging General dashboards (PCP-20424)
instead bulk-add ALL cards under their node. Each dashboard stays at or below the
per-dashboard 15-card limit (MAX_CARD_COUNT).

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

# Integration General node (PCP-20424): the Kubernetes + Control Tower sub-nodes,
# 8 cards total = 4 + 4. (PromQL moved to its own PROMQL_DASHBOARD below.)
# Kubernetes and Control Tower expose identically-titled cards (k8s vs on_prem
# widgets); they are disambiguated by the sub-menu (level2) tree node, not the card
# title, so the duplicate titles across sub-menus are expected and unambiguous.
# Control Tower is present only when HAWKCONSOLE/BMDP is installed.
INTEGRATION_GENERAL_GROUPS = [
    ("Kubernetes", [
        "Application Instances",
        "Application Request Counts",
        "Application CPU Utilization",
        "Application Memory Usage",
    ]),
    ("Control Tower", [
        "Application Instances",
        "Application Request Counts",
        "Application CPU Utilization",
        "Application Memory Usage",
    ]),
]

# PromQL gets its OWN dashboard (PCP-20424). PromQL cards are not plain catalog
# cards: adding one auto-opens a query editor that must be filled + applied (a blank
# PromQL card can't be saved). The cards live under the "PromQL" sub-node of the
# "Integration General" catalog node (always present, since the custom-metrics
# widget always exists). Queries follow the editor's own placeholder suggestions.
#
# - Range Query: one card (a single time-series; no chart-type choice).
# - Instant Query: added once per CONCRETE chart type (Single Stat / Bar / Gauge /
#   Pie / Table), each renamed so the cards are distinguishable. "Auto" is excluded
#   (it auto-selects a shape rather than being a distinct visualisation).
PROMQL_DASHBOARD_NAME = "PromQL_dashboard"
PROMQL_SUBMENU = "PromQL"
PROMQL_CAPABILITY = "Integration General"  # catalog node that hosts the PromQL sub-node
PROMQL_RANGE_QUERY = "k8s_container_cpu_limit_utilization_ratio{app_type='flogo'}[1h]"
PROMQL_INSTANT_QUERY = "up{job='prometheus'}"
PROMQL_INSTANT_CHART_TYPES = ["Single Stat", "Bar", "Gauge", "Pie", "Table"]

# Range cards: (catalog_card_name, query)
PROMQL_RANGE_CARDS = [
    ("PromQL Range Query", PROMQL_RANGE_QUERY),
]
# Instant cards: (catalog_card_name, query, chart_type, dashboard_title) — one per chart type.
PROMQL_INSTANT_CARDS = [
    ("PromQL Instant Query", PROMQL_INSTANT_QUERY, chart_type, f"PromQL Instant Query - {chart_type}")
    for chart_type in PROMQL_INSTANT_CHART_TYPES
]

PROMQL_DASHBOARD = {
    "name": PROMQL_DASHBOARD_NAME,
    "capability": PROMQL_CAPABILITY,
    "submenu": PROMQL_SUBMENU,
    "range_cards": PROMQL_RANGE_CARDS,
    "instant_cards": PROMQL_INSTANT_CARDS,
}

# Messaging General node (PCP-20424) - CP <= 1.19 ONLY: 4 EMS cards directly under
# the node (no sub-menu, so level2 is None). The "Messaging General" label only
# appears in the catalog tree when the EMS capability is installed, so the
# dashboard-level capability gate naturally skips it on non-EMS clusters - and on CP
# 1.20+, where the node was replaced by MESSAGING_DATA_GRID_GROUPS below.
MESSAGING_GENERAL_GROUPS = [
    (None, [
        "EMS Server Messages",
        "EMS Server CPU Utilization",
        "EMS Server Memory Usage",
        # Title includes the ™ (U+2122) trademark char; matched verbatim by has-text,
        # verified against the live catalog (CP 1.19.0).
        "Enterprise Message Service™ Health",
    ]),
]

# Messaging / Data Grid node (PCP-21284): CP 1.20 reorganised the flat "Messaging
# General" node above into a "Messaging / Data Grid" ROOT with three leaves -
# Messaging (the EMS health card), Data Grid (the ActiveSpaces health card, added by
# PCP-21015 / PCP-21016 and renamed to "ActiveSpaces Health" by PCP-21323) and
# General (the three EMS server metric cards). Both this spec and the legacy
# MESSAGING_GENERAL_GROUPS one stay in CAPABILITY_DASHBOARDS: the dashboard-level
# capability gate matches whichever label the running CP actually renders, so old and
# new control planes each get exactly one messaging dashboard without version
# sniffing. 5 cards total, within MAX_CARD_COUNT.
MESSAGING_DATA_GRID_CAPABILITY = "Messaging / Data Grid"
ACTIVESPACES_HEALTH_CARD = "ActiveSpaces Health"
MESSAGING_DATA_GRID_GROUPS = [
    # Title includes the ™ (U+2122) trademark char; matched verbatim by has-text,
    # verified against the live catalog (CP 1.20.0).
    ("Messaging", ["Enterprise Message Service™ Health"]),
    ("Data Grid", [ACTIVESPACES_HEALTH_CARD]),
    ("General", [
        "EMS Server CPU Utilization",
        "EMS Server Memory Usage",
        "EMS Server Messages",
    ]),
]

# Each spec: dashboard name, the catalog capability label that must exist, and the
# (sub-menu, cards) groups to add. The capability label is also the level1 menu.
# (PromQL is handled separately by PROMQL_DASHBOARD, not here.)
CAPABILITY_DASHBOARDS = [
    {"name": "BW6_dashboard", "capability": "BW6 (Containers)", "groups": BW_GROUPS},
    {"name": "Flogo_dashboard", "capability": "Flogo", "groups": FLOGO_GROUPS},
    {"name": "BW5_dashboard", "capability": "BW5 (Containers)", "groups": BW_GROUPS},
    {"name": "SB_dashboard", "capability": "Spring Boot", "groups": SB_GROUPS_1},
    {"name": "SB_dashboard_2", "capability": "Spring Boot", "groups": SB_GROUPS_2},
    {"name": "Integration_General", "capability": "Integration General", "groups": INTEGRATION_GENERAL_GROUPS},
    {"name": "Messaging_General", "capability": "Messaging General", "groups": MESSAGING_GENERAL_GROUPS},
    {"name": "Messaging_Data_Grid", "capability": MESSAGING_DATA_GRID_CAPABILITY, "groups": MESSAGING_DATA_GRID_GROUPS},
]
