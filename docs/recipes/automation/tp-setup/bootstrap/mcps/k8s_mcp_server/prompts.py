# Source: https://github.com/alexei-led/k8s-mcp-server
# License: MIT License
# Copyright (c) 2021 Alexei Ledenev

"""Kubernetes CLI prompt definitions for the K8s MCP Server.

This module provides a collection of useful prompt templates for common Kubernetes operations.
These prompts help ensure consistent best practices and efficient Kubernetes resource management.
"""

import logging

logger = logging.getLogger(__name__)


def register_prompts(mcp):
    """Register all prompts with the MCP server instance.

    Args:
        mcp: The FastMCP server instance
    """
    logger.info("Registering Kubernetes prompt templates")

    @mcp.prompt()
    def k8s_resource_status(resource_type: str, namespace: str = "default") -> str:
        """Generate kubectl commands to check the status of Kubernetes resources.

        Args:
            resource_type: Type of Kubernetes resource (e.g., pods, deployments)
            namespace: Kubernetes namespace to target

        Returns:
            Formatted prompt string for resource status checks
        """
        return f"""Generate kubectl commands to check the status of {resource_type}
in the {namespace} namespace.

Include commands to:
1. List all {resource_type} with basic information
2. Show detailed status and conditions
3. Check recent events related to these resources
4. Identify any issues or potential problems
5. Retrieve logs if applicable

Structure the commands to be easily executed and parsed."""

    @mcp.prompt()
    def k8s_deploy_application(app_name: str, image: str, namespace: str = "default", replicas: int = 1) -> str:
        """Generate kubectl commands to deploy an application.

        Args:
            app_name: Name for the application
            image: Container image to deploy
            namespace: Kubernetes namespace for deployment
            replicas: Number of replicas to run

        Returns:
            Formatted prompt string for application deployment
        """
        return f"""Generate kubectl commands to deploy an application named '{app_name}'
using the image '{image}' with {replicas} replicas in the {namespace} namespace.

Include commands to:
1. Create necessary Kubernetes resources (Deployment, Service, etc.)
2. Set appropriate resource limits and requests
3. Configure health checks and probes
4. Apply proper labels and annotations
5. Verify the deployment was successful
6. Test connectivity to the deployed application

The deployment should follow Kubernetes best practices for security and reliability."""

    @mcp.prompt()
    def k8s_troubleshoot(resource_type: str, resource_name: str, namespace: str = "default") -> str:
        """Generate kubectl commands for troubleshooting Kubernetes resources.

        Args:
            resource_type: Type of Kubernetes resource (e.g., pod, deployment)
            resource_name: Name of the specific resource to troubleshoot
            namespace: Kubernetes namespace containing the resource

        Returns:
            Formatted prompt string for troubleshooting commands
        """
        return f"""Generate kubectl commands to troubleshoot issues with the {resource_type}
named '{resource_name}' in the {namespace} namespace.

Include commands to:
1. Check the current status and configuration of the resource
2. View events related to this resource
3. Examine logs and error messages
4. Verify dependencies and related resources
5. Check networking and security settings
6. Compare against best practices for this resource type

Organize the commands in a systematic troubleshooting flow from basic to advanced checks."""

    @mcp.prompt()
    def k8s_resource_inventory(namespace: str = "") -> str:
        """Generate kubectl commands to inventory Kubernetes cluster resources.

        Args:
            namespace: Optional namespace to limit inventory (empty for all namespaces)

        Returns:
            Formatted prompt string for resource inventory commands
        """
        scope = f"in the {namespace} namespace" if namespace else "across all namespaces"
        return f"""Generate kubectl commands to create a comprehensive inventory
of resources {scope}.

Include commands to:
1. List all resource types available in the cluster
2. Count resources by type
3. Show resource utilization and allocation
4. Identify critical system components
5. Check for resources without proper labels or annotations
6. Export the inventory in a structured format (JSON or YAML)

Structure the commands to build a complete picture of the cluster state."""

    @mcp.prompt()
    def k8s_security_check(namespace: str = "") -> str:
        """Generate kubectl commands for security analysis of Kubernetes resources.

        Args:
            namespace: Optional namespace to limit checks (empty for all namespaces)

        Returns:
            Formatted prompt string for security check commands
        """
        scope = f"in the {namespace} namespace" if namespace else "across the entire cluster"
        return f"""Generate kubectl commands to perform a security assessment
of Kubernetes resources {scope}.

Include commands to check for:
1. Pods running as root or with privileged security contexts
2. Resources without proper RBAC restrictions
3. Secrets that might be exposed or improperly managed
4. Network policies and service configurations
5. Container image vulnerabilities and best practices
6. Resource configurations against CIS benchmarks

Explain the security implications of each check and provide remediation suggestions."""

    @mcp.prompt()
    def k8s_resource_scaling(resource_type: str, resource_name: str, namespace: str = "default") -> str:
        """Generate kubectl commands for scaling Kubernetes resources.

        Args:
            resource_type: Type of resource to scale (e.g., deployment, statefulset)
            resource_name: Name of the specific resource to scale
            namespace: Kubernetes namespace containing the resource

        Returns:
            Formatted prompt string for scaling commands
        """
        return f"""Generate kubectl commands to scale the {resource_type}
named '{resource_name}' in the {namespace} namespace.

Include commands to:
1. Check current scaling parameters and resource utilization
2. Scale the resource manually with appropriate safeguards
3. Set up Horizontal Pod Autoscaling if applicable
4. Monitor the scaling operation
5. Verify application health during and after scaling
6. Rollback in case of issues

Provide commands for both scaling up and down with appropriate checks and validations."""

    @mcp.prompt()
    def k8s_logs_analysis(pod_name: str, namespace: str = "default", container: str = "") -> str:
        """Generate kubectl commands for analyzing logs from Kubernetes resources.

        Args:
            pod_name: Name of the pod to analyze logs from
            namespace: Kubernetes namespace containing the pod
            container: Optional container name for multi-container pods

        Returns:
            Formatted prompt string for log analysis commands
        """
        container_clause = f" container '{container}' in" if container else ""
        return f"""Generate kubectl commands to analyze logs from{container_clause}
pod '{pod_name}' in the {namespace} namespace.

Include commands to:
1. Retrieve recent logs with appropriate timestamps
2. Filter logs for errors and warnings
3. Search for specific patterns or events
4. Follow logs in real-time for monitoring
5. Extract and analyze specific log sections
6. Export logs for offline analysis

Provide commands that can help identify common issues like application errors,
crashes, resource constraints, or performance problems."""

    @mcp.prompt()
    def istio_service_mesh(namespace: str = "default") -> str:
        """Generate istioctl commands for managing Istio service mesh.

        Args:
            namespace: Kubernetes namespace to target

        Returns:
            Formatted prompt string for Istio management commands
        """
        return f"""Generate istioctl commands to manage and analyze the Istio service mesh
in the {namespace} namespace.

Include commands to:
1. Analyze the mesh for issues and configuration problems
2. Inspect traffic routing and service configurations
3. Check security policies and mTLS settings
4. Monitor mesh performance and health
5. Debug common service mesh problems
6. Visualize the service topology

The commands should follow Istio best practices and focus on operational excellence."""

    @mcp.prompt()
    def helm_chart_management(release_name: str = "", namespace: str = "default") -> str:
        """Generate helm commands for managing Helm charts and releases.

        Args:
            release_name: Optional specific release to manage
            namespace: Kubernetes namespace for Helm operations

        Returns:
            Formatted prompt string for Helm management commands
        """
        release_specific = f"for release '{release_name}'" if release_name else "for all releases"
        return f"""Generate helm commands to manage Helm charts {release_specific}
in the {namespace} namespace.

Include commands to:
1. List and inspect installed releases
2. Manage release lifecycle (install, upgrade, rollback)
3. Validate chart templates and values
4. Check release history and status
5. Debug common Helm deployment issues
6. Manage Helm repositories

The commands should follow Helm best practices and include proper validation steps."""

    @mcp.prompt()
    def argocd_application(app_name: str = "", namespace: str = "argocd") -> str:
        """Generate argocd commands for managing ArgoCD applications.

        Args:
            app_name: Optional specific application to manage
            namespace: Kubernetes namespace where ArgoCD is installed

        Returns:
            Formatted prompt string for ArgoCD management commands
        """
        app_specific = f"for application '{app_name}'" if app_name else "for all applications"
        return f"""Generate argocd commands to manage GitOps deployments {app_specific}
with ArgoCD in the {namespace} namespace.

Include commands to:
1. List and inspect applications and their statuses
2. Manage application lifecycle (create, sync, delete)
3. Monitor sync status and health
4. Troubleshoot deployment issues
5. Handle rollbacks and recovery
6. Manage application configurations and settings

The commands should follow ArgoCD and GitOps best practices for continuous delivery."""

    logger.info("Successfully registered all Kubernetes prompt templates")
