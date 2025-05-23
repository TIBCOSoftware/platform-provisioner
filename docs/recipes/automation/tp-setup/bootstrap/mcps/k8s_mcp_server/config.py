# Source: https://github.com/alexei-led/k8s-mcp-server
# License: MIT License
# Copyright (c) 2021 Alexei Ledenev
# Modified by Cloud Software Group, 2025

"""Configuration settings for the K8s MCP Server.

This module contains configuration settings for the K8s MCP Server.

Environment variables:
- K8S_MCP_TIMEOUT: Custom timeout in seconds (default: 300)
- K8S_MCP_MAX_OUTPUT: Maximum output size in characters (default: 100000)
- K8S_MCP_TRANSPORT: Transport protocol to use ("stdio" or "sse" or "streamable-http", default: "stdio")
- K8S_CONTEXT: Kubernetes context to use (default: current context)
- K8S_NAMESPACE: Kubernetes namespace to use (default: "default")
- K8S_MCP_SECURITY_MODE: Security mode for command validation ("strict", "permissive", default: "strict")
- K8S_MCP_SECURITY_CONFIG: Path to YAML config file for security rules (default: None)
"""

import os
from pathlib import Path

# Command execution settings
DEFAULT_TIMEOUT = int(os.environ.get("K8S_MCP_TIMEOUT", "300"))
MAX_OUTPUT_SIZE = int(os.environ.get("K8S_MCP_MAX_OUTPUT", "100000"))

# Server settings
MCP_TRANSPORT = os.environ.get("K8S_MCP_TRANSPORT", "stdio")  # Transport protocol: stdio or sse or streamable-http

# Kubernetes specific settings
K8S_CONTEXT = os.environ.get("K8S_CONTEXT", "")  # Empty means use current context
K8S_NAMESPACE = os.environ.get("K8S_NAMESPACE", "default")

# Security settings
SECURITY_MODE = os.environ.get("K8S_MCP_SECURITY_MODE", "strict")  # strict or permissive
SECURITY_CONFIG_PATH = os.environ.get("K8S_MCP_SECURITY_CONFIG", None)

# Supported CLI tools
SUPPORTED_CLI_TOOLS = {
    "kubectl": {
        "check_cmd": "kubectl version --client",
        "help_flag": "--help",
    },
    "istioctl": {
        "check_cmd": "istioctl version --remote=false",
        "help_flag": "--help",
    },
    "helm": {
        "check_cmd": "helm version",
        "help_flag": "--help",
    },
    "argocd": {
        "check_cmd": "argocd version --client",
        "help_flag": "--help",
    },
}

# Instructions displayed to client during initialization
INSTRUCTIONS = """
K8s MCP Server provides a simple interface to Kubernetes CLI tools.

Supported CLI tools:
- kubectl: Kubernetes command-line tool
- istioctl: Command-line tool for Istio service mesh
- helm: Kubernetes package manager
- argocd: GitOps continuous delivery tool for Kubernetes

Available tools:
- Use describe_kubectl, describe_helm, describe_istioctl, or describe_argocd to get documentation for CLI tools
- Use execute_kubectl, execute_helm, execute_istioctl, or execute_argocd to run commands

Command execution supports Unix pipes (|) to filter or transform output:
  Example: kubectl get pods -o json | jq '.items[].metadata.name'
  Example: helm list | grep mysql

Use the built-in prompt templates for common Kubernetes tasks:
  - k8s_resource_status: Check status of Kubernetes resources
  - k8s_deploy_application: Deploy an application to Kubernetes
  - k8s_troubleshoot: Troubleshoot Kubernetes resources
  - k8s_resource_inventory: List all resources in cluster
  - istio_service_mesh: Manage Istio service mesh
  - helm_chart_management: Manage Helm charts
  - argocd_application: Manage ArgoCD applications
  - k8s_security_check: Security analysis for Kubernetes resources
  - k8s_resource_scaling: Scale Kubernetes resources
  - k8s_logs_analysis: Analyze logs from Kubernetes resources
"""

# Application paths
BASE_DIR = Path(__file__).parent.parent.parent
