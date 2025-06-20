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
- K8S_MCP_HOST: Host to bind the server to (default: "127.0.0.1")
- K8S_MCP_PORT: Port to bind the server to (default: 8091)
- K8S_CONTEXT: Kubernetes context to use (default: current context)
- K8S_NAMESPACE: Kubernetes namespace to use (default: "default")
- K8S_MCP_SECURITY_MODE: Security mode for command validation ("strict", "permissive", default: "strict")
- K8S_MCP_SECURITY_CONFIG: Path to YAML config file for security rules (default: None)
- TIBCOP_CLI_CPURL: TIBCO Control Plane URL for tibcop authentication (required for tibcop commands)
- TIBCOP_CLI_OAUTH_TOKEN: OAuth authentication token for tibcop (required for tibcop commands)
"""

import os
from pathlib import Path

# Command execution settings
DEFAULT_TIMEOUT = int(os.environ.get("K8S_MCP_TIMEOUT", "300"))
MAX_OUTPUT_SIZE = int(os.environ.get("K8S_MCP_MAX_OUTPUT", "100000"))

# Server settings
MCP_TRANSPORT = os.environ.get("K8S_MCP_TRANSPORT", "stdio")  # Transport protocol: stdio or sse or streamable-http
MCP_HOST = os.environ.get("K8S_MCP_HOST", "0.0.0.0")  # Host to bind the server to
MCP_PORT = int(os.environ.get("K8S_MCP_PORT", "8091"))  # Port to bind the server to
MCP_INITIALIZATION_TIMEOUT = int(os.environ.get("K8S_MCP_INIT_TIMEOUT", "30"))  # Server initialization timeout
MCP_STARTUP_DELAY = float(os.environ.get("K8S_MCP_STARTUP_DELAY", "2.0"))  # Additional startup delay for streamable-http

# Additional server settings for HTTP transport
MCP_DEBUG = os.environ.get("K8S_MCP_DEBUG", "false").lower() == "true"  # Enable debug logging
MCP_CORS_ORIGINS = os.environ.get("K8S_MCP_CORS_ORIGINS", "*")  # CORS origins
MCP_LOG_REQUESTS = os.environ.get("K8S_MCP_LOG_REQUESTS", "true").lower() == "true"  # Log HTTP requests

# Authentication settings
MCP_HTTP_BEARER_TOKEN = os.environ.get("K8S_MCP_HTTP_BEARER_TOKEN", "")  # Bearer token for HTTP authentication

# Kubernetes specific settings
K8S_CONTEXT = os.environ.get("K8S_CONTEXT", "")  # Empty means use current context
K8S_NAMESPACE = os.environ.get("K8S_NAMESPACE", "default")

# TIBCO Platform CLI settings
TIBCOP_CLI_CPURL = os.environ.get("TIBCOP_CLI_CPURL", "")  # TIBCO Control Plane URL
TIBCOP_CLI_OAUTH_TOKEN = os.environ.get("TIBCOP_CLI_OAUTH_TOKEN", "")  # OAuth authentication token

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
    "tibcop": {
        "check_cmd": "tibcop --version",
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
- tibcop: TIBCO Platform CLI tool

Available tools:
- Use describe_kubectl, describe_helm, describe_istioctl, describe_argocd, or describe_tibcop to get documentation for CLI tools
- Use execute_kubectl, execute_helm, execute_istioctl, execute_argocd, or execute_tibcop to run commands

Command execution supports Unix pipes (|) to filter or transform output:
  Example: kubectl get pods -o json | jq '.items[].metadata.name'
  Example: helm list | grep mysql

TIBCO Platform CLI (tibcop) Usage:
IMPORTANT: tibcop is designed for non-interactive use and must be configured with environment variables.
Always use --json flag for machine-readable output and --onlyPrintScripts for script generation.

Required environment variables for tibcop:
  TIBCOP_CLI_CPURL: Control Plane URL (e.g., https://api.your-tibco-platform.com)
  TIBCOP_CLI_OAUTH_TOKEN: OAuth authentication token

Before running tibcop commands, ensure these environment variables are exported:
  export TIBCOP_CLI_CPURL="https://api.your-tibco-platform.com"
  export TIBCOP_CLI_OAUTH_TOKEN="your-oauth-token-here"

The system will automatically use these environment variables when executing tibcop commands.
If these variables are not set, tibcop commands will fail with authentication errors.

Common tibcop patterns:
  - List dataplanes: tibcop tplatform:list-dataplanes --json
  - Register dataplane: tibcop tplatform:register-k8s-dataplane --onlyPrintScripts --name=dp-name
  - Provision capability: tibcop tplatform:provision-capability --dataplane-name=dp-name --capability=FLOGO
  - Create resources: tibcop tplatform:create-storage-resource-instance --dataplane-name=dp-name

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
