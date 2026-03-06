#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary
"""
Kubectl command module.

Provides kubectl-based operations for Kubernetes cluster resources.
"""

import time

from utils.color_logger import ColorLogger
from utils.helper import Helper


class TibcopKubectl:
    """
    Kubectl command operations.

    Provides methods for executing kubectl commands to query Kubernetes
    cluster resources.
    """

    def __init__(self, base):
        """
        Initialize Kubectl handler.

        Args:
            base: TibcopBase instance for command execution
        """
        self.base = base

    def run_kubectl(self, command):
        """
        Run a generic kubectl command.

        This is the base method for all kubectl operations. Other methods
        can call this to execute kubectl commands.

        Args:
            command: The kubectl command to run (without 'kubectl' prefix)

        Returns:
            Command output as string, or None if failed
        """
        full_command = f"kubectl {command}"

        result = Helper.get_command_output(full_command, is_print_error=False)
        return result

    def list_storage_classes(self):
        """
        List available storage classes in the current Kubernetes cluster.

        Returns:
            Storage classes output as string
        """
        ColorLogger.info("Listing storage classes...")

        output_lines = []
        output_lines.append("=" * 60)
        output_lines.append("Storage Classes:")
        output_lines.append("=" * 60)

        storage_result = self.run_kubectl("get storageclasses -o wide")
        if storage_result:
            output_lines.append(storage_result)
        else:
            output_lines.append("No storage classes found or command failed")

        output_lines.append("=" * 60)

        result = '\n'.join(output_lines)
        ColorLogger.success("Storage classes listed successfully")
        return result

    def list_ingress_classes(self):
        """
        List available ingress classes in the current Kubernetes cluster.

        Filters out ingress classes that start with "tibco-dp" from the output.

        Returns:
            Ingress classes output as string (excluding tibco-dp*)
        """
        ColorLogger.info("Listing ingress classes...")

        output_lines = []
        output_lines.append("=" * 60)
        output_lines.append("Ingress Classes (excluding tibco-dp*):")
        output_lines.append("=" * 60)

        ingress_result = self.run_kubectl("get ingressclasses -o wide")
        if ingress_result:
            # Filter out lines where the ingress class name starts with "tibco-dp"
            lines = ingress_result.split('\n')
            filtered_lines = []
            for i, line in enumerate(lines):
                # Keep header line (first line) or lines that don't start with tibco-dp
                if i == 0 or not line.strip().startswith("tibco-dp"):
                    filtered_lines.append(line)
            output_lines.append('\n'.join(filtered_lines))
        else:
            output_lines.append("No ingress classes found or command failed")

        output_lines.append("=" * 60)

        result = '\n'.join(output_lines)
        ColorLogger.success("Ingress classes listed successfully")
        return result

    def wait_for_provisioner_pods(self, namespace, timeout=300, interval=10):
        """Wait until all *provisioner* pods in the namespace are Running.

        After capabilities are provisioned, the platform creates provisioner pods
        (e.g. flogo-provisioner, bwce-provisioner). These must be fully Running
        before app build & deploy can succeed.

        Args:
            namespace: Kubernetes namespace to check
            timeout: Maximum wait time in seconds (default: 300)
            interval: Polling interval in seconds (default: 10)

        Returns:
            True if all provisioner pods are Running, False if timed out
        """
        ColorLogger.info("=" * 60)
        ColorLogger.info(f"Waiting for provisioner pods in '{namespace}' to be Running (timeout: {timeout}s)...")
        ColorLogger.info("=" * 60)

        elapsed = 0
        while elapsed < timeout:
            output = self.run_kubectl(f'get pods -n {namespace} --no-headers')

            if not output:
                ColorLogger.info(f"No pods found in '{namespace}', waiting...")
                time.sleep(interval)
                elapsed += interval
                continue

            # Filter lines containing "provisioner" or "artifactmanager"
            pod_keywords = ['provisioner', 'artifactmanager']
            provisioner_lines = [
                line.strip() for line in output.strip().split('\n')
                if line.strip() and any(kw in line.lower() for kw in pod_keywords)
            ]

            if not provisioner_lines:
                ColorLogger.info(f"No provisioner/artifactmanager pods found yet in '{namespace}', waiting...")
                time.sleep(interval)
                elapsed += interval
                continue

            # Check each provisioner pod's READY (2nd col) and STATUS (3rd col)
            # Format: NAME  READY  STATUS  RESTARTS  AGE
            # e.g.:   flogo-provisioner-xxx  2/2  Running  0  1m
            not_running = []
            for line in provisioner_lines:
                parts = line.split()
                if len(parts) >= 3:
                    pod_name = parts[0]
                    ready = parts[1]    # e.g. "2/2"
                    status = parts[2]   # e.g. "Running"
                    if status != 'Running':
                        not_running.append(f"{pod_name}({status})")
                    elif '/' in ready:
                        ready_count, total_count = ready.split('/')
                        if ready_count != total_count:
                            not_running.append(f"{pod_name}(Ready:{ready})")

            if not not_running:
                ColorLogger.success(
                    f"All {len(provisioner_lines)} provisioner pod(s) in '{namespace}' are Running"
                )
                return True

            ColorLogger.info(f"Provisioner pods not ready: {', '.join(not_running)}, waiting...")
            time.sleep(interval)
            elapsed += interval

        ColorLogger.error(f"Provisioner pods in '{namespace}' did not all become Running within {timeout}s")
        return False

    def wait_for_app_pods(self, namespace, app_name, timeout=120, interval=10):
        """Wait until pods matching app_name are Running and Ready.

        Args:
            namespace: Kubernetes namespace to check
            app_name: App name to match in pod names
            timeout: Maximum wait time in seconds (default: 120)
            interval: Polling interval in seconds (default: 10)

        Returns:
            True if matching pods are Running and Ready, False if timed out
        """
        ColorLogger.info(f"Waiting for app '{app_name}' pods in '{namespace}' to be Running (timeout: {timeout}s)...")

        elapsed = 0
        while elapsed < timeout:
            output = self.run_kubectl(f'get pods -n {namespace} --no-headers')

            if not output:
                ColorLogger.info(f"No pods found in '{namespace}', waiting...")
                time.sleep(interval)
                elapsed += interval
                continue

            # Filter lines containing app_name
            app_lines = [
                line.strip() for line in output.strip().split('\n')
                if line.strip() and app_name.lower() in line.lower()
            ]

            if not app_lines:
                ColorLogger.info(f"No pods matching '{app_name}' found yet, waiting...")
                time.sleep(interval)
                elapsed += interval
                continue

            # Check each pod's READY and STATUS
            # Format: NAME  READY  STATUS  RESTARTS  AGE
            not_ready = []
            for line in app_lines:
                parts = line.split()
                if len(parts) >= 3:
                    pod_name = parts[0]
                    ready = parts[1]
                    status = parts[2]
                    if status != 'Running':
                        not_ready.append(f"{pod_name}({status})")
                    elif '/' in ready:
                        ready_count, total_count = ready.split('/')
                        if ready_count != total_count:
                            not_ready.append(f"{pod_name}(Ready:{ready})")

            if not not_ready:
                ColorLogger.success(
                    f"All {len(app_lines)} pod(s) for app '{app_name}' are Running and Ready"
                )
                return True

            ColorLogger.info(f"App '{app_name}' pods not ready: {', '.join(not_ready)}, waiting...")
            time.sleep(interval)
            elapsed += interval

        ColorLogger.error(f"App '{app_name}' pods in '{namespace}' did not become Running within {timeout}s")
        return False

    def list_cluster_resources(self):
        """
        List available storage classes and ingress classes in the current Kubernetes cluster.

        Filters out ingress classes that start with "tibco-dp" from the output.

        Returns:
            Combined output of storage classes and ingress classes as string
        """
        ColorLogger.info("Listing cluster resources (storage classes and ingress classes)...")

        storage_output = self.list_storage_classes()
        ingress_output = self.list_ingress_classes()

        result = storage_output + "\n\n" + ingress_output

        ColorLogger.success("Cluster resources listed successfully")
        return result
