#!/usr/bin/env python3

#  Copyright © 2025. Cloud Software Group, Inc.
#  This file is subject to the license terms contained
#  in the license file that is distributed with this file.

from mcp.server.fastmcp import FastMCP
import os
import subprocess
import logging
import json
import urllib.request
import urllib.parse
import urllib.error
from typing import Dict, Any, List, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('tibco-platform-provisioner-mcp')

# Create the server - use the exact naming convention from examples
mcp = FastMCP("TIBCO Platform Automation", port=8090)

mcp_with_instructions = FastMCP(
    name="HelpfulAssistant",
    instructions="""
        This server provides basic functionality for TIBCO Platform. 
        It is designed for DevOps to automate the setup of TIBCO Platform environments.
        TIBCO Platform consist two main components: Control Plane (CP) and Data Plane (DP).
        This MCP automation server is designed to run automation for DP mainly.
        Call show_environment() to get the current environment.
        """
)

# Basic dynamic resource returning a string
@mcp.resource("resource://greeting")
def get_greeting() -> str:
    """Provides a simple greeting message."""
    return "Welcome to TIBCO Platform Infrastructure MCP server!"

# Get project root directory
def get_project_root():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(script_dir, '../../../..'))

PROJECT_ROOT = get_project_root()
AUTOMATION_PATH = os.path.join(PROJECT_ROOT, 'docs/recipes/automation/tp-setup/bootstrap')

# Default values from the UI
DEFAULT_VALUES = {
    "TP_AUTO_ADMIN_URL": "https://admin.cp1-my.localhost.dataplanes.pro/admin",
    "CP_ADMIN_EMAIL": "cp-test@tibco.com",
    "CP_ADMIN_PASSWORD": "Tibco@123",
    "TP_AUTO_LOGIN_URL": "https://cp-sub1.cp1-my.localhost.dataplanes.pro/cp/login",
    "DP_HOST_PREFIX": "cp-sub1",
    "DP_USER_EMAIL": "cp-sub1@tibco.com",
    "DP_USER_PASSWORD": "Tibco@123",
    "TP_AUTO_MAIL_URL": "https://mail.localhost.dataplanes.pro/#/",
    "TP_AUTO_K8S_DP_NAME": "k8s-auto-dp1",
    "TP_AUTO_K8S_BMDP_NAME": "k8s-auto-bmdp1",
    "TP_AUTO_DATA_PLANE_O11Y_SYSTEM_CONFIG": False,
    "TP_AUTO_K8S_DP_SERVICE_ACCOUNT_CREATION_ADDITIONAL_SETTINGS": "",
    "BWCE_APP_NAME": "tt",
    "FLOGO_APP_NAME": "flogo-auto-1",
    "TP_AUTO_IS_CONFIG_O11Y": True,
    "HEADLESS": True,
    "FORCE_RUN_AUTOMATION": False,
    "IS_CLEAN_REPORT": False,
    # Additional parameters needed for DataPlane creation
    "TP_AUTO_KUBECONFIG": "",
    "TP_CREATE_NETWORK_POLICIES": "false",
    "TP_CLUSTER_NODE_CIDR": "",
    "TP_CLUSTER_POD_CIDR": "",
    "TP_CLUSTER_SERVICE_CIDR": "",
    "TP_AUTO_IS_CREATE_DP": True,
    "TP_AUTO_IS_CREATE_BMDP": True,
    "TP_AUTO_IS_ENABLE_RVDM": True,
    "TP_AUTO_IS_ENABLE_EMSDM": True,
    "TP_AUTO_IS_ENABLE_EMS_SERVER": True,
    # DNS and FQDN settings
    "TP_AUTO_CP_INSTANCE_ID": "cp1",
    "TP_AUTO_CP_DNS_DOMAIN": "localhost.dataplanes.pro",
    "TP_AUTO_CP_SERVICE_DNS_DOMAIN": "cp1-my.localhost.dataplanes.pro",
    "TP_AUTO_CP_DNS_DOMAIN_PREFIX_BWCE": "bwce",
    "TP_AUTO_CP_DNS_DOMAIN_PREFIX_FLOGO": "flogo",
    "TP_AUTO_CP_DNS_DOMAIN_PREFIX_TIBCOHUB": "tibcohub",
    "TP_AUTO_FQDN_BWCE": "bwce.localhost.dataplanes.pro",
    "TP_AUTO_FQDN_FLOGO": "flogo.localhost.dataplanes.pro",
    "TP_AUTO_FQDN_TIBCOHUB": "tibcohub.localhost.dataplanes.pro",
    # Ingress and Storage settings
    "TP_AUTO_INGRESS_CONTROLLER": "nginx",
    "TP_AUTO_INGRESS_CONTROLLER_CLASS_NAME": "nginx",
    "TP_AUTO_INGRESS_CONTROLLER_BWCE": "nginx-bwce",
    "TP_AUTO_INGRESS_CONTROLLER_FLOGO": "nginx-flogo",
    "TP_AUTO_INGRESS_CONTROLLER_TIBCOHUB": "nginx-tibcohub",
    "TP_AUTO_STORAGE_CLASS": "local-path",
    # Capability server names
    "TP_AUTO_EMS_CAPABILITY_SERVER_NAME": "ems-sn",
    "TP_AUTO_PULSAR_CAPABILITY_SERVER_NAME": "pulsar-sn",
    "TP_AUTO_TIBCOHUB_CAPABILITY_HUB_NAME": "tibco-hub",
    # Elastic and Prometheus settings
    "TP_AUTO_ELASTIC_URL": "https://elastic.localhost.dataplanes.pro/",
    "TP_AUTO_KIBANA_URL": "https://kibana.localhost.dataplanes.pro/",
    "TP_AUTO_ELASTIC_USER": "elastic",
    "TP_AUTO_ELASTIC_PASSWORD": "",  # Will be set dynamically
    "TP_AUTO_PROMETHEUS_URL": "https://prometheus-internal.localhost.dataplanes.pro/",
    "TP_AUTO_PROMETHEUS_USER": "",
    "TP_AUTO_PROMETHEUS_PASSWORD": "",
    # Capability provisioning flags
    "TP_AUTO_IS_PROVISION_BWCE": False,
    "TP_AUTO_IS_PROVISION_EMS": False,
    "TP_AUTO_IS_PROVISION_FLOGO": False,
    "TP_AUTO_IS_PROVISION_PULSAR": False,
    "TP_AUTO_IS_PROVISION_TIBCOHUB": False
}

# Map case values to Python modules (not shell scripts)
CASE_TO_MODULE = {
    "page_env": "page_env",
    "page_auth": "page_auth",
    "page_o11y": "page_o11y",
    "case.create_global_config": "case.create_global_config",
    "case.k8s_create_dp": "case.k8s_create_dp",
    "case.k8s_config_dp_o11y": "case.k8s_config_dp_o11y",
    "case.k8s_delete_dp": "case.k8s_delete_dp",
    "case.k8s_provision_capability": "case.k8s_provision_capability",
    "provision_bwce": "provision_bwce",
    "provision_ems": "provision_ems",
    "provision_flogo": "provision_flogo",
    "provision_pulsar": "provision_pulsar",
    "provision_tibcohub": "provision_tibcohub",
    "case.k8s_create_and_start_bwce_app": "case.k8s_create_and_start_bwce_app",
    "case.k8s_create_and_start_flogo_app": "case.k8s_create_and_start_flogo_app",
    "delete_bwce_app": "delete_bwce_app",
    "delete_flogo_app": "delete_flogo_app"
}

# Based on the server.py implementation, this function calls the API to run the automation
async def run_automation_task(case: str, params: Optional[Dict[str, Any]] = None) -> str:
    """Run an automation task by making an API call to the bootstrap server.
    
    Args:
        case: The automation case to run (e.g., page_env, case.k8s_create_dp)
        params: Optional parameters to pass to the automation task
    
    Returns:
        The output of the automation task as a string
    """
    # Start with default values
    request_params = DEFAULT_VALUES.copy()
    
    # Set the case
    request_params["case"] = case
    
    # Simplified special case handling, since provision tools now call the correct case directly
    delete_case_mapping = {
        "delete_bwce_app": "bwce",
        "delete_flogo_app": "flogo",
    }

    # Only keep delete-related special handling
    if case in delete_case_mapping:
        request_params["CAPABILITY"] = delete_case_mapping[case]
        request_params["case"] = "case.k8s_delete_app"
    
    # Add additional parameters
    if params:
        request_params.update(params)
    
    # Format parameters for URL
    query_params = urllib.parse.urlencode(request_params)
    
    # Local flask server URL (using port 3120 as seen in server.py)
    flask_url = f"https://automation.localhost.dataplanes.pro/run-script?{query_params}"
    
    logger.info(f"Running automation task: {case}")
    logger.info(f"API URL: {flask_url}")
    
    try:
        # Use urllib to make the HTTP request
        with urllib.request.urlopen(flask_url) as response:
            # Read response data
            output = ""
            for line in response:
                decoded_line = line.decode('utf-8')
                output += decoded_line
                logger.info(f"Output line: {decoded_line.strip()}")
            
            return output
    except urllib.error.URLError as e:
        error_msg = f"Error connecting to automation server: {str(e)}"
        logger.error(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"Automation task failed: {str(e)}"
        logger.error(error_msg)
        return error_msg

# Get project root directory
def get_project_root():
    # Assuming this script is in a subdirectory of the project
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Adjust path to project root based on actual project structure
    return os.path.abspath(os.path.join(script_dir, '../../../..'))

PROJECT_ROOT = get_project_root()
AUTOMATION_PATH = os.path.join(PROJECT_ROOT, 'docs/recipes/automation/tp-setup/bootstrap')
def run_bash_script(script_name: str, args: Dict[str, Any] = None) -> Dict[str, Any]:
    """Run bash script and return the result"""
    script_path = os.path.join(AUTOMATION_PATH, script_name)

    cmd = [script_path]
    if args:
        for k, v in args.items():
            cmd.extend([f"--{k}", str(v)])

    logger.info(f"Running command: {' '.join(cmd)}")

    try:
        # Run script and capture output
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info(f"Command completed successfully: {result.stdout}")

        # Try to parse output as JSON
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"success": True, "output": result.stdout, "message": "Command executed successfully"}

    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed with error: {e.stderr}")
        return {"success": False, "error": e.stderr, "message": "Command execution failed"}

# Execute Python modules directly as a fallback
async def execute_module(module_name: str, params: Optional[Dict[str, Any]] = None) -> str:
    """Execute a Python module directly as a fallback method.
    
    Args:
        module_name: Name of the module to run
        params: Optional dictionary of environment variables to set
    
    Returns:
        The output of the module execution as a string
    """
    # Check if module exists
    if module_name not in CASE_TO_MODULE:
        return f"Error: Module {module_name} not found in the mapping"
    
    # Get the actual module path
    python_module = CASE_TO_MODULE[module_name]
    
    logger.info(f"Executing Python module: {python_module}")
    
    try:
        # Set environment variables from DEFAULT_VALUES and params
        env = os.environ.copy()
        for key, value in DEFAULT_VALUES.items():
            env[key] = str(value)
        
        if params:
            for key, value in params.items():
                env[key] = str(value)
        
        # Run the Python module
        cmd = [os.sys.executable, "-u", "-m", python_module]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, env=env)
        logger.info(f"Module executed successfully")
        return result.stdout
    except subprocess.CalledProcessError as e:
        logger.error(f"Module execution failed: {e.stderr}")
        return f"Error: {e.stderr}"

# Environment Management Actions
@mcp.tool()
async def show_environment() -> str:
    """Show Current Environment (Login CP/Elastic Credentials)
    
    Returns:
        Information about the current environment
    """
    try:
        return await run_automation_task("page_env")
    except Exception as e:
        logger.error(f"Failed to run through API, trying direct module execution: {str(e)}")
        return await execute_module("page_env")

@mcp.tool()
async def create_subscription(email: str = "") -> str:
    """Create new subscription with User Email
    
    This tool creates a new subscription in the TIBCO Control Plane for a specified user.
    Subscriptions are required before creating and using a Data Plane.
    
    This tool automates the following process:
    1. Checks if the host prefix already exists
    2. If not, provisions a new user with specified email
    3. Activates the user through an email verification
    
    Args:
        email: User email address for the subscription (optional). 
               If not provided, the default email from the environment configuration will be used.
    
    Returns:
        Result of the subscription creation process
        
    Example:
        # Create subscription with default email
        create_subscription()
        
        # Create subscription with custom email
        create_subscription(email="user@example.com")
    """
    params = {}
    if email:
        params["DP_USER_EMAIL"] = email
    
    try:
        return await run_automation_task("page_auth", params)
    except Exception as e:
        logger.error(f"Failed to run through API, trying direct module execution: {str(e)}")
        return await execute_module("page_auth", params)

# O11y Configuration Actions
@mcp.tool()
async def config_o11y_widget() -> str:
    """Config o11y widget
    
    This tool configures the Observability (o11y) dashboard widgets in the TIBCO Control Plane.
    Observability provides monitoring and visualization capabilities for your Data Planes.
    
    This tool performs the following operations:
    1. Logs into the Control Plane
    2. Navigates to the Observability dashboard
    3. Resets the current dashboard layout
    4. Adds various monitoring widgets including:
       - Integration metrics (CPU, Memory, Instances, Request Counts)
       - BWCE metrics (Engine, Process, Activity)
       - Flogo metrics (Engine, Flow, Activity)
    5. Configures these widgets for both Kubernetes and Control Tower platforms
    
    The configured dashboard provides comprehensive visibility into your Data Plane
    performance and health metrics.
    
    Returns:
        Result of the o11y widget configuration process
    """
    params = {
        "TP_AUTO_IS_CONFIG_O11Y": True,
        "HEADLESS": True,
        "FORCE_RUN_AUTOMATION": False,
        "IS_CLEAN_REPORT": False,
        "TP_AUTO_LOGIN_URL": DEFAULT_VALUES["TP_AUTO_LOGIN_URL"],
        "DP_HOST_PREFIX": DEFAULT_VALUES["DP_HOST_PREFIX"],
        "DP_USER_EMAIL": DEFAULT_VALUES["DP_USER_EMAIL"],
        "DP_USER_PASSWORD": DEFAULT_VALUES["DP_USER_PASSWORD"],
        "TP_AUTO_MAIL_URL": DEFAULT_VALUES["TP_AUTO_MAIL_URL"],
        "TP_AUTO_K8S_DP_NAME": DEFAULT_VALUES["TP_AUTO_K8S_DP_NAME"],
        "TP_AUTO_K8S_BMDP_NAME": DEFAULT_VALUES["TP_AUTO_K8S_BMDP_NAME"],
        "TP_AUTO_KUBECONFIG": DEFAULT_VALUES.get("TP_AUTO_KUBECONFIG", ""),
        "TP_AUTO_DATA_PLANE_O11Y_SYSTEM_CONFIG": DEFAULT_VALUES["TP_AUTO_DATA_PLANE_O11Y_SYSTEM_CONFIG"],
        "TP_AUTO_K8S_DP_SERVICE_ACCOUNT_CREATION_ADDITIONAL_SETTINGS": DEFAULT_VALUES["TP_AUTO_K8S_DP_SERVICE_ACCOUNT_CREATION_ADDITIONAL_SETTINGS"],
        "BWCE_APP_NAME": DEFAULT_VALUES["BWCE_APP_NAME"],
        "FLOGO_APP_NAME": DEFAULT_VALUES["FLOGO_APP_NAME"]
    }
    
    logger.info("Configuring O11y dashboard widgets")
    
    try:
        return await run_automation_task("page_o11y", params)
    except Exception as e:
        logger.error(f"Failed to run through API, trying direct module execution: {str(e)}")
        return await execute_module("page_o11y", params)

# DataPlane Configuration Actions
@mcp.tool()
async def config_global_o11y(use_system_config: bool = False) -> str:
    """Config Global O11y
    
    This tool configures the global Observability (o11y) settings for TIBCO Platform.
    These global settings provide centralized monitoring and logging capabilities
    that can be applied to all Data Planes in the system.
    
    The tool automates the following configuration process:
    1. Logs into the Control Plane with administrator credentials
    2. Sets up proper user permissions for Observability access
    3. Navigates to the Global Observability configuration page
    4. Configures the following components:
       - Log Server: Sets up Query Service and Exporters for logs
       - Metrics Server: Configures Prometheus integration for metrics collection
       - Traces Server: Sets up distributed tracing capabilities
    
    Args:
        use_system_config: Whether to use the system's predefined Observability configuration.
                          If True, uses built-in system settings for Metrics and Traces.
                          If False, configures custom settings using environment variables.
    
    Returns:
        Result of the global Observability configuration process
        
    Example:
        # Configure with custom settings defined in environment variables
        config_global_o11y()
        
        # Configure using system-defined settings
        config_global_o11y(use_system_config=True)
    """
    params = {
        "TP_AUTO_IS_CONFIG_O11Y": True,
        "HEADLESS": True,
        "FORCE_RUN_AUTOMATION": False,
        "IS_CLEAN_REPORT": False,
        "TP_AUTO_LOGIN_URL": DEFAULT_VALUES["TP_AUTO_LOGIN_URL"],
        "DP_HOST_PREFIX": DEFAULT_VALUES["DP_HOST_PREFIX"],
        "DP_USER_EMAIL": DEFAULT_VALUES["DP_USER_EMAIL"],
        "DP_USER_PASSWORD": DEFAULT_VALUES["DP_USER_PASSWORD"],
        "TP_AUTO_MAIL_URL": DEFAULT_VALUES["TP_AUTO_MAIL_URL"],
        "TP_AUTO_K8S_DP_NAME": DEFAULT_VALUES["TP_AUTO_K8S_DP_NAME"],
        "TP_AUTO_K8S_BMDP_NAME": DEFAULT_VALUES["TP_AUTO_K8S_BMDP_NAME"],
        "TP_AUTO_KUBECONFIG": DEFAULT_VALUES.get("TP_AUTO_KUBECONFIG", ""),
        "TP_AUTO_DATA_PLANE_O11Y_SYSTEM_CONFIG": use_system_config,
        "TP_AUTO_K8S_DP_SERVICE_ACCOUNT_CREATION_ADDITIONAL_SETTINGS": DEFAULT_VALUES["TP_AUTO_K8S_DP_SERVICE_ACCOUNT_CREATION_ADDITIONAL_SETTINGS"],
        "BWCE_APP_NAME": DEFAULT_VALUES["BWCE_APP_NAME"],
        "FLOGO_APP_NAME": DEFAULT_VALUES["FLOGO_APP_NAME"]
    }
    
    logger.info(f"Configuring global O11y with system config: {use_system_config}")
    
    try:
        return await run_automation_task("case.create_global_config", params)
    except Exception as e:
        logger.error(f"Failed to run through API, trying direct module execution: {str(e)}")
        return await execute_module("case.create_global_config", params)

@mcp.tool()
async def create_k8s_dataplane(
    dp_name: str = "", 
    sa_additional_settings: str = "", 
    use_system_o11y: bool = False, 
    kubeconfig: str = "",
    dp_host_prefix: str = "",
    dp_user_email: str = "",
    dp_user_password: str = "",
    bmdp_name: str = "",
    login_url: str = "",
    mail_url: str = "",
    bwce_app_name: str = "",
    flogo_app_name: str = "",
    headless: bool = True,
    force_run: bool = False,
    clean_report: bool = False
) -> str:
    """Create K8s DataPlane (Include run helm command)

    Creates a new TIBCO Data Plane in Kubernetes. This tool automates the entire setup process
    including creating the necessary resources and running Helm commands.

    Args:
        dp_name: Name for the new dataplane (overrides default TP_AUTO_K8S_DP_NAME)
        sa_additional_settings: Additional settings for service account creation
        use_system_o11y: Whether to use system observability configuration (default: False)
        kubeconfig: Path to custom kubeconfig file (optional)
        dp_host_prefix: Host prefix for dataplane (overrides default DP_HOST_PREFIX)
        dp_user_email: User email for dataplane (overrides default DP_USER_EMAIL)
        dp_user_password: User password for dataplane (overrides default DP_USER_PASSWORD)
        bmdp_name: Name for the BMDP (overrides default TP_AUTO_K8S_BMDP_NAME)
        login_url: Login URL (overrides default TP_AUTO_LOGIN_URL)
        mail_url: Mail URL (overrides default TP_AUTO_MAIL_URL)
        bwce_app_name: BWCE application name (overrides default BWCE_APP_NAME)
        flogo_app_name: Flogo application name (overrides default FLOGO_APP_NAME)
        headless: Whether to run in headless mode (default: True)
        force_run: Whether to force run the automation (default: False)
        clean_report: Whether to clean the report (default: False)
    
    Returns:
        Result of the K8s DataPlane creation process with status information

    Examples:
        # Create dataplane with default settings
        create_k8s_dataplane()

        # Create dataplane with custom name
        create_k8s_dataplane(dp_name="my-custom-dp")

        # Create dataplane with system observability enabled
        create_k8s_dataplane(dp_name="o11y-dp", use_system_o11y=True)

        # Create dataplane with custom host prefix and user email
        create_k8s_dataplane(
            dp_name="custom-dp", 
            dp_host_prefix="custom-prefix", 
            dp_user_email="custom@example.com"
        )
    """
    # Start with default parameters
    params = {
        "TP_AUTO_IS_CONFIG_O11Y": True,
        "HEADLESS": headless,
        "FORCE_RUN_AUTOMATION": force_run,
        "IS_CLEAN_REPORT": clean_report
    }
    
    # Set custom values for parameters if provided
    if dp_name:
        params["TP_AUTO_K8S_DP_NAME"] = dp_name
    
    if sa_additional_settings:
        params["TP_AUTO_K8S_DP_SERVICE_ACCOUNT_CREATION_ADDITIONAL_SETTINGS"] = sa_additional_settings
    
    if use_system_o11y:
        params["TP_AUTO_DATA_PLANE_O11Y_SYSTEM_CONFIG"] = use_system_o11y
    
    if kubeconfig:
        params["TP_AUTO_KUBECONFIG"] = kubeconfig
    
    if dp_host_prefix:
        params["DP_HOST_PREFIX"] = dp_host_prefix
    
    if dp_user_email:
        params["DP_USER_EMAIL"] = dp_user_email
    
    if dp_user_password:
        params["DP_USER_PASSWORD"] = dp_user_password
    
    if bmdp_name:
        params["TP_AUTO_K8S_BMDP_NAME"] = bmdp_name
    
    if login_url:
        params["TP_AUTO_LOGIN_URL"] = login_url
    
    if mail_url:
        params["TP_AUTO_MAIL_URL"] = mail_url
    
    if bwce_app_name:
        params["BWCE_APP_NAME"] = bwce_app_name
    
    if flogo_app_name:
        params["FLOGO_APP_NAME"] = flogo_app_name
    
    logger.info(f"Creating K8s DataPlane with parameters: {params}")
    
    try:
        return await run_automation_task("case.k8s_create_dp", params)
    except Exception as e:
        logger.error(f"Failed to run through API, trying direct module execution: {str(e)}")
        return await execute_module("case.k8s_create_dp", params)

@mcp.tool()
async def config_dataplane_o11y(use_system_config: bool = False, dp_name: str = "") -> str:
    """Config DataPlane O11y
    
    This tool configures Observability (o11y) settings for a specific Data Plane.
    Observability provides monitoring, logging, and tracing capabilities for tracking
    the performance and health of applications running in the Data Plane.
    
    The tool automates the following configuration process:
    1. Logs into the Control Plane
    2. Sets up proper user permissions for Observability access
    3. Navigates to the specific Data Plane's configuration page
    4. Configures three key Observability components:
       - Log Server: Sets up ElasticSearch integration for logs collection and query
       - Metrics Server: Configures Prometheus integration for metrics collection
       - Traces Server: Sets up distributed tracing capabilities
    
    Each component includes both Query Service (for retrieving data) and Exporters
    (for sending data to monitoring systems).
    
    Args:
        use_system_config: Whether to use the system's predefined Observability configuration.
                          If True, uses built-in system settings for Metrics and Traces,
                          which simplifies configuration but offers less customization.
                          If False, configures custom settings using environment variables.
        dp_name: Name of the Data Plane to configure O11y for (optional).
                If not provided, the default Data Plane name from environment
                configuration will be used.
    
    Returns:
        Result of the Data Plane Observability configuration process
        
    Example:
        # Configure with custom settings for default Data Plane
        config_dataplane_o11y()
        
        # Configure using system-defined settings for default Data Plane
        config_dataplane_o11y(use_system_config=True)
        
        # Configure custom Data Plane with custom settings
        config_dataplane_o11y(use_system_config=False, dp_name="my-custom-dp")
    """
    params = {
        "TP_AUTO_IS_CONFIG_O11Y": True,
        "HEADLESS": True,
        "FORCE_RUN_AUTOMATION": False,
        "IS_CLEAN_REPORT": False,
        "TP_AUTO_LOGIN_URL": DEFAULT_VALUES["TP_AUTO_LOGIN_URL"],
        "DP_HOST_PREFIX": DEFAULT_VALUES["DP_HOST_PREFIX"],
        "DP_USER_EMAIL": DEFAULT_VALUES["DP_USER_EMAIL"],
        "DP_USER_PASSWORD": DEFAULT_VALUES["DP_USER_PASSWORD"],
        "TP_AUTO_MAIL_URL": DEFAULT_VALUES["TP_AUTO_MAIL_URL"],
        "TP_AUTO_K8S_DP_NAME": DEFAULT_VALUES["TP_AUTO_K8S_DP_NAME"],
        "TP_AUTO_K8S_BMDP_NAME": DEFAULT_VALUES["TP_AUTO_K8S_BMDP_NAME"],
        "TP_AUTO_KUBECONFIG": DEFAULT_VALUES.get("TP_AUTO_KUBECONFIG", ""),
        "TP_AUTO_DATA_PLANE_O11Y_SYSTEM_CONFIG": use_system_config,
        "TP_AUTO_K8S_DP_SERVICE_ACCOUNT_CREATION_ADDITIONAL_SETTINGS": DEFAULT_VALUES["TP_AUTO_K8S_DP_SERVICE_ACCOUNT_CREATION_ADDITIONAL_SETTINGS"],
        "BWCE_APP_NAME": DEFAULT_VALUES["BWCE_APP_NAME"],
        "FLOGO_APP_NAME": DEFAULT_VALUES["FLOGO_APP_NAME"]
    }
    
    # Set Data Plane name if provided
    if dp_name:
        params["TP_AUTO_K8S_DP_NAME"] = dp_name
    
    logger.info(f"Configuring Data Plane O11y for '{params['TP_AUTO_K8S_DP_NAME']}' with system config: {use_system_config}")
    
    try:
        return await run_automation_task("case.k8s_config_dp_o11y", params)
    except Exception as e:
        logger.error(f"Failed to run through API, trying direct module execution: {str(e)}")
        return await execute_module("case.k8s_config_dp_o11y", params)

@mcp.tool()
async def delete_dataplane(dp_name: str = "") -> str:
    """Delete DataPlane (Include run helm command)
    
    Args:
        dp_name: Name of the dataplane to delete (overrides default TP_AUTO_K8S_DP_NAME)
    
    Returns:
        Result of the DataPlane deletion
        
    Examples:
        # Delete dataplane with default name
        delete_dataplane()
        
        # Delete specific dataplane
        delete_dataplane(dp_name="my-custom-dp")
    """
    params = {}
    
    # Set dataplane name if provided
    if dp_name:
        params["TP_AUTO_K8S_DP_NAME"] = dp_name
    
    logger.info(f"Deleting K8s DataPlane with parameters: {params}")
    
    try:
        return await run_automation_task("case.k8s_delete_dp", params)
    except Exception as e:
        logger.error(f"Failed to run through API, trying direct module execution: {str(e)}")
        return await execute_module("case.k8s_delete_dp", params)

# Provision Capability Actions
@mcp.tool()
async def provision_bwce(dp_name: str = "") -> str:
    """Provision BWCE
    
    This tool provisions the TIBCO BusinessWorks Container Edition (BWCE) capability
    in an existing Kubernetes Data Plane. BWCE is a container-based integration platform
    for developing and running integration applications.
    
    The tool automates the following configuration process:
    1. Logs into the Control Plane
    2. Navigates to the specified Data Plane
    3. Configures required resources:
       - Storage Class for BWCE applications
       - Ingress Controller for external access
    4. Provisions the BWCE capability in the Data Plane
    5. Sets up BWCE Plugins and Connectors for integration capabilities
    
    After successful provisioning, the Data Plane will be able to deploy and run
    BWCE applications, connecting to various systems and services.
    
    Args:
        dp_name: Name of the Data Plane to provision BWCE capability in (optional).
                If not provided, the default Data Plane name from environment
                configuration will be used.
    
    Returns:
        Result of the BWCE provisioning process
        
    Examples:
        # Provision BWCE capability in the default Data Plane
        provision_bwce()
        
        # Provision BWCE capability in a specific Data Plane
        provision_bwce(dp_name="my-custom-dp")
    
    Note:
        Make sure to create a Data Plane first using create_k8s_dataplane().
    """
    params = {
        "TP_AUTO_IS_CONFIG_O11Y": True,
        "TP_AUTO_IS_PROVISION_BWCE": True,
        "HEADLESS": True,
        "FORCE_RUN_AUTOMATION": False,
        "IS_CLEAN_REPORT": False,
        "BWCE_APP_NAME": DEFAULT_VALUES.get("BWCE_APP_NAME", "tt"),
    }
    
    # Set Data Plane name if provided
    if dp_name:
        params["TP_AUTO_K8S_DP_NAME"] = dp_name
    
    logger.info(f"Provisioning BWCE capability in Data Plane '{params.get('TP_AUTO_K8S_DP_NAME', DEFAULT_VALUES['TP_AUTO_K8S_DP_NAME'])}'")
    
    try:
        return await run_automation_task("case.k8s_provision_capability", params)
    except Exception as e:
        logger.error(f"Failed to run through API, trying direct module execution: {str(e)}")
        return await execute_module("case.k8s_provision_capability", params)

@mcp.tool()
async def provision_ems(dp_name: str = "") -> str:
    """Provision EMS
    
    This tool provisions the TIBCO Enterprise Message Service (EMS) capability
    in an existing Kubernetes Data Plane. EMS is TIBCO's enterprise messaging solution
    that provides reliable, high-performance messaging for integration applications.
    
    The tool automates the following configuration process:
    1. Logs into the Control Plane
    2. Navigates to the specified Data Plane
    3. Configures required storage resources:
       - Message Storage for persisting messages
       - Log Storage for EMS server logs
    4. Sets up an EMS server instance with a specific name
    5. Completes the provisioning process with default configurations
    
    After successful provisioning, the Data Plane will have a fully functional
    EMS server instance that can be used for messaging between applications,
    supporting features like queues, topics, durable subscribers, and more.
    
    Args:
        dp_name: Name of the Data Plane to provision EMS capability in (optional).
                If not provided, the default Data Plane name from environment
                configuration will be used.
    
    Returns:
        Result of the EMS provisioning process
        
    Examples:
        # Provision EMS capability in the default Data Plane
        provision_ems()
        
        # Provision EMS capability in a specific Data Plane
        provision_ems(dp_name="my-custom-dp")
    
    Note:
        Make sure to create a Data Plane first using create_k8s_dataplane().
    """
    params = {
        "TP_AUTO_IS_CONFIG_O11Y": True,
        "TP_AUTO_IS_PROVISION_EMS": True,
        "HEADLESS": True,
        "FORCE_RUN_AUTOMATION": False,
        "IS_CLEAN_REPORT": False,
        "TP_AUTO_LOGIN_URL": DEFAULT_VALUES["TP_AUTO_LOGIN_URL"],
        "DP_HOST_PREFIX": DEFAULT_VALUES["DP_HOST_PREFIX"],
        "DP_USER_EMAIL": DEFAULT_VALUES["DP_USER_EMAIL"],
        "DP_USER_PASSWORD": DEFAULT_VALUES["DP_USER_PASSWORD"],
        "TP_AUTO_MAIL_URL": DEFAULT_VALUES["TP_AUTO_MAIL_URL"],
        "TP_AUTO_K8S_DP_NAME": DEFAULT_VALUES["TP_AUTO_K8S_DP_NAME"],
        "TP_AUTO_K8S_BMDP_NAME": DEFAULT_VALUES["TP_AUTO_K8S_BMDP_NAME"],
        "TP_AUTO_KUBECONFIG": DEFAULT_VALUES.get("TP_AUTO_KUBECONFIG", ""),
        "TP_AUTO_DATA_PLANE_O11Y_SYSTEM_CONFIG": DEFAULT_VALUES["TP_AUTO_DATA_PLANE_O11Y_SYSTEM_CONFIG"],
        "TP_AUTO_K8S_DP_SERVICE_ACCOUNT_CREATION_ADDITIONAL_SETTINGS": DEFAULT_VALUES["TP_AUTO_K8S_DP_SERVICE_ACCOUNT_CREATION_ADDITIONAL_SETTINGS"],
        "BWCE_APP_NAME": DEFAULT_VALUES["BWCE_APP_NAME"],
        "FLOGO_APP_NAME": DEFAULT_VALUES["FLOGO_APP_NAME"]
    }
    
    # Set Data Plane name if provided
    if dp_name:
        params["TP_AUTO_K8S_DP_NAME"] = dp_name
    
    logger.info(f"Provisioning EMS capability in Data Plane '{params.get('TP_AUTO_K8S_DP_NAME', DEFAULT_VALUES['TP_AUTO_K8S_DP_NAME'])}'")
    
    try:
        return await run_automation_task("case.k8s_provision_capability", params)
    except Exception as e:
        logger.error(f"Failed to run through API, trying direct module execution: {str(e)}")
        return await execute_module("case.k8s_provision_capability", params)

@mcp.tool()
async def provision_flogo(dp_name: str = "") -> str:
    """Provision Flogo
    
    This tool provisions the TIBCO Flogo Enterprise capability in an existing
    Kubernetes Data Plane. Flogo is an ultralight edge microservices framework
    designed for building event-driven applications and IoT solutions.
    
    The tool automates the following configuration process:
    1. Logs into the Control Plane
    2. Navigates to the specified Data Plane
    3. Configures required resources:
       - Storage Class for Flogo applications
       - Ingress Controller for external access
    4. Provisions the Flogo capability in the Data Plane
    5. Sets up Flogo Connectors (such as HTTP, Websocket) for integration capabilities
    
    After successful provisioning, the Data Plane will be able to deploy and run
    Flogo applications with enhanced capabilities for event processing, API integration,
    and building lightweight microservices.
    
    Args:
        dp_name: Name of the Data Plane to provision Flogo capability in (optional).
                If not provided, the default Data Plane name from environment
                configuration will be used.
    
    Returns:
        Result of the Flogo provisioning process
        
    Examples:
        # Provision Flogo capability in the default Data Plane
        provision_flogo()
        
        # Provision Flogo capability in a specific Data Plane
        provision_flogo(dp_name="my-custom-dp")
    
    Note:
        Make sure to create a Data Plane first using create_k8s_dataplane().
    """
    params = {
        "TP_AUTO_IS_CONFIG_O11Y": True,
        "TP_AUTO_IS_PROVISION_FLOGO": True,
        "HEADLESS": True,
        "FORCE_RUN_AUTOMATION": False,
        "IS_CLEAN_REPORT": False,
        "FLOGO_APP_NAME": DEFAULT_VALUES.get("FLOGO_APP_NAME", "flogo-auto-1"),
    }
    
    # Set Data Plane name if provided
    if dp_name:
        params["TP_AUTO_K8S_DP_NAME"] = dp_name
    
    logger.info(f"Provisioning Flogo capability in Data Plane '{params.get('TP_AUTO_K8S_DP_NAME', DEFAULT_VALUES['TP_AUTO_K8S_DP_NAME'])}'")
    
    try:
        return await run_automation_task("case.k8s_provision_capability", params)
    except Exception as e:
        logger.error(f"Failed to run through API, trying direct module execution: {str(e)}")
        return await execute_module("case.k8s_provision_capability", params)

@mcp.tool()
async def provision_pulsar(dp_name: str = "") -> str:
    """Provision Pulsar
    
    This tool provisions the TIBCO Messaging Quasar (powered by Apache Pulsar) capability
    in an existing Kubernetes Data Plane. Apache Pulsar is a cloud-native, distributed
    messaging and streaming platform designed for high-performance workloads.
    
    The tool automates the following configuration process:
    1. Logs into the Control Plane
    2. Navigates to the specified Data Plane
    3. Configures required storage resources:
       - Message Storage for persisting messages
       - Journal Storage for transaction logs
       - Log Storage for Pulsar server logs
    4. Sets up a Pulsar server instance with a specific name
    5. Completes the provisioning process with default configurations
    
    After successful provisioning, the Data Plane will have a fully functional
    Pulsar server instance that provides publish-subscribe messaging capabilities
    with multi-tenancy, geo-replication, and guaranteed message delivery options.
    
    Args:
        dp_name: Name of the Data Plane to provision Pulsar capability in (optional).
                If not provided, the default Data Plane name from environment
                configuration will be used.
    
    Returns:
        Result of the Pulsar provisioning process
        
    Examples:
        # Provision Pulsar capability in the default Data Plane
        provision_pulsar()
        
        # Provision Pulsar capability in a specific Data Plane
        provision_pulsar(dp_name="my-custom-dp")
    
    Note:
        Make sure to create a Data Plane first using create_k8s_dataplane().
    """
    params = {
        "TP_AUTO_IS_CONFIG_O11Y": True,
        "TP_AUTO_IS_PROVISION_PULSAR": True,
        "HEADLESS": True,
        "FORCE_RUN_AUTOMATION": False,
        "IS_CLEAN_REPORT": False,
    }
    
    # Set Data Plane name if provided
    if dp_name:
        params["TP_AUTO_K8S_DP_NAME"] = dp_name
    
    logger.info(f"Provisioning Pulsar capability in Data Plane '{params.get('TP_AUTO_K8S_DP_NAME', DEFAULT_VALUES['TP_AUTO_K8S_DP_NAME'])}'")
    
    try:
        return await run_automation_task("case.k8s_provision_capability", params)
    except Exception as e:
        logger.error(f"Failed to run through API, trying direct module execution: {str(e)}")
        return await execute_module("case.k8s_provision_capability", params)

@mcp.tool()
async def provision_tibcohub(dp_name: str = "") -> str:
    """Provision TibcoHub
    
    This tool provisions the TIBCO Developer Hub capability in an existing Data Plane.
    TIBCO Hub is a central place to discover, access, and share business data.
    
    The tool automates the following configuration process:
    1. Logs into the Control Plane
    2. Navigates to the specified Data Plane
    3. Configures required resources:
       - Storage Class for TIBCO Hub data
       - Ingress Controller for external access
    4. Sets up a TIBCO Developer Hub instance with a specific name
    5. Completes the provisioning process with default configurations
    
    After successful provisioning, the Data Plane will have a fully functional
    TIBCO Developer Hub that provides a centralized platform for developers to
    collaborate, discover APIs, and manage application resources.
    
    Args:
        dp_name: Name of the Data Plane to provision TIBCO Hub capability in (optional).
                If not provided, the default Data Plane name from environment
                configuration will be used.
    
    Returns:
        Result of the TibcoHub provisioning process
        
    Examples:
        # Provision TIBCO Hub capability in the default Data Plane
        provision_tibcohub()
        
        # Provision TIBCO Hub capability in a specific Data Plane
        provision_tibcohub(dp_name="my-custom-dp")
    
    Note:
        Make sure to create a Data Plane first using create_k8s_dataplane().
    """
    params = {
        "TP_AUTO_IS_CONFIG_O11Y": True,
        "TP_AUTO_IS_PROVISION_TIBCOHUB": True,
        "HEADLESS": True,
        "FORCE_RUN_AUTOMATION": False,
        "IS_CLEAN_REPORT": False,
    }
    
    # Set Data Plane name if provided
    if dp_name:
        params["TP_AUTO_K8S_DP_NAME"] = dp_name
    
    logger.info(f"Provisioning TIBCO Hub capability in Data Plane '{params.get('TP_AUTO_K8S_DP_NAME', DEFAULT_VALUES['TP_AUTO_K8S_DP_NAME'])}'")
    
    try:
        return await run_automation_task("case.k8s_provision_capability", params)
    except Exception as e:
        logger.error(f"Failed to run through API, trying direct module execution: {str(e)}")
        return await execute_module("case.k8s_provision_capability", params)

# Create and Start App Actions
@mcp.tool()
async def create_start_bwce_app(app_name: str = "", dp_name: str = "") -> str:
    """Create And Start BWCE App (Include set endpoint to public and Test swagger API)
    
    This tool automates the entire lifecycle of creating, deploying, configuring,
    and starting a BWCE (BusinessWorks Container Edition) application in an existing
    Data Plane that has the BWCE capability provisioned.
    
    The tool performs the following operations:
    1. Logs into the Control Plane
    2. Navigates to the specified Data Plane
    3. Builds and deploys the BWCE application:
       - Uploads the application EAR file
       - Creates an application build
       - Configures necessary deployment parameters
    4. Deploys the application to a Kubernetes namespace
    5. Configures the application:
       - Sets endpoints to public for external access
       - Enables tracing for observability
    6. Starts the application and ensures it's running
    
    Args:
        app_name: BWCE application name (optional). If not provided,
                 the default name from environment configuration will be used.
        dp_name: Data Plane name where to create the BWCE application (optional).
                If not provided, the default Data Plane name from environment
                configuration will be used.
    
    Returns:
        Result of the BWCE app creation and startup process
        
    Example:
        # Create and start BWCE app with default name
        create_start_bwce_app()
        
        # Create and start BWCE app with custom name
        create_start_bwce_app(app_name="my-bwce-app")
        
        # Create and start BWCE app in specific Data Plane
        create_start_bwce_app(app_name="my-bwce-app", dp_name="my-dataplane")
        
    Note:
        This tool requires that the BWCE capability has already been provisioned
        in the Data Plane using the provision_bwce() tool.
    """
    # Set all required parameters for BWCE app creation
    params = {
        "TP_AUTO_IS_CONFIG_O11Y": True,
        "HEADLESS": True,
        "FORCE_RUN_AUTOMATION": False,
        "IS_CLEAN_REPORT": False,
        "TP_AUTO_LOGIN_URL": DEFAULT_VALUES["TP_AUTO_LOGIN_URL"],
        "DP_HOST_PREFIX": DEFAULT_VALUES["DP_HOST_PREFIX"],
        "DP_USER_EMAIL": DEFAULT_VALUES["DP_USER_EMAIL"],
        "DP_USER_PASSWORD": DEFAULT_VALUES["DP_USER_PASSWORD"],
        "TP_AUTO_MAIL_URL": DEFAULT_VALUES["TP_AUTO_MAIL_URL"],
        "TP_AUTO_K8S_DP_NAME": DEFAULT_VALUES["TP_AUTO_K8S_DP_NAME"],
        "TP_AUTO_K8S_BMDP_NAME": DEFAULT_VALUES["TP_AUTO_K8S_BMDP_NAME"],
        "TP_AUTO_KUBECONFIG": DEFAULT_VALUES.get("TP_AUTO_KUBECONFIG", ""),
        "TP_AUTO_DATA_PLANE_O11Y_SYSTEM_CONFIG": DEFAULT_VALUES["TP_AUTO_DATA_PLANE_O11Y_SYSTEM_CONFIG"],
        "TP_AUTO_K8S_DP_SERVICE_ACCOUNT_CREATION_ADDITIONAL_SETTINGS": DEFAULT_VALUES["TP_AUTO_K8S_DP_SERVICE_ACCOUNT_CREATION_ADDITIONAL_SETTINGS"],
        "BWCE_APP_NAME": DEFAULT_VALUES["BWCE_APP_NAME"],
        "FLOGO_APP_NAME": DEFAULT_VALUES["FLOGO_APP_NAME"]
    }
    
    # Override BWCE app name if provided
    if app_name:
        params["BWCE_APP_NAME"] = app_name
    
    # Set Data Plane name
    if dp_name:
        params["TP_AUTO_K8S_DP_NAME"] = dp_name
    
    logger.info(f"Creating and starting BWCE application '{params['BWCE_APP_NAME']}' with parameters: {params}")
    
    try:
        return await run_automation_task("case.k8s_create_and_start_bwce_app", params)
    except Exception as e:
        logger.error(f"Failed to run through API, trying direct module execution: {str(e)}")
        return await execute_module("case.k8s_create_and_start_bwce_app", params)

@mcp.tool()
async def create_start_flogo_app(app_name: str = "", dp_name: str = "") -> str:
    """Create And Start Flogo App (Include set endpoint to public and Test swagger API)

    This tool automates the entire lifecycle of creating, deploying, configuring,
    and starting a TIBCO Flogo Enterprise application in an existing Data Plane
    that has the Flogo capability provisioned.

    The tool performs the following operations:
    1. Logs into the Control Plane
    2. Navigates to the specified Data Plane
    3. Builds and deploys the Flogo application:
       - Uploads the application JSON/ZIP file
       - Creates an application build
       - Configures necessary deployment parameters
    4. Deploys the application to a Kubernetes namespace
    5. Configures the application:
       - Sets endpoints to public for external access
       - Enables tracing for observability
       - Configures necessary application properties
    6. Starts the application and ensures it's running
    7. Tests the application's Swagger API to verify functionality

    Flogo applications provide a lightweight, event-driven architecture for
    building microservices and integration flows. They excel at handling
    API integrations, event processing, and data transformations with
    minimal resource consumption.

    Args:
        app_name: Flogo application name (optional). If not provided,
                 the default name from environment configuration will be used.
                 The default name is defined in the DEFAULT_VALUES dictionary.
        dp_name: Data Plane name where to create the Flogo application (optional).
                If not provided, the default Data Plane name from environment
                configuration will be used.

    Returns:
        Result of the Flogo app creation and startup process with detailed status information

    Example:
        # Create and start Flogo app with default name
        create_start_flogo_app()

        # Create and start Flogo app with custom name
        create_start_flogo_app(app_name="my-custom-flogo-app")

        # Create and start Flogo app in specific Data Plane
        create_start_flogo_app(app_name="my-custom-flogo-app", dp_name="my-dataplane")

    Note:
        This tool requires that the Flogo capability has already been provisioned
        in the Data Plane using the provision_flogo() tool. The Data Plane must
        also have been created using create_k8s_dataplane() and configured for
        ingress and storage.
    """
    # Set all required parameters for Flogo app creation
    params = {
        "TP_AUTO_IS_CONFIG_O11Y": True,
        "HEADLESS": True,
        "FORCE_RUN_AUTOMATION": False,
        "IS_CLEAN_REPORT": False,
        "TP_AUTO_LOGIN_URL": DEFAULT_VALUES["TP_AUTO_LOGIN_URL"],
        "DP_HOST_PREFIX": DEFAULT_VALUES["DP_HOST_PREFIX"],
        "DP_USER_EMAIL": DEFAULT_VALUES["DP_USER_EMAIL"],
        "DP_USER_PASSWORD": DEFAULT_VALUES["DP_USER_PASSWORD"],
        "TP_AUTO_MAIL_URL": DEFAULT_VALUES["TP_AUTO_MAIL_URL"],
        "TP_AUTO_K8S_DP_NAME": DEFAULT_VALUES["TP_AUTO_K8S_DP_NAME"],
        "TP_AUTO_K8S_BMDP_NAME": DEFAULT_VALUES["TP_AUTO_K8S_BMDP_NAME"],
        "TP_AUTO_KUBECONFIG": DEFAULT_VALUES.get("TP_AUTO_KUBECONFIG", ""),
        "TP_AUTO_DATA_PLANE_O11Y_SYSTEM_CONFIG": DEFAULT_VALUES["TP_AUTO_DATA_PLANE_O11Y_SYSTEM_CONFIG"],
        "TP_AUTO_K8S_DP_SERVICE_ACCOUNT_CREATION_ADDITIONAL_SETTINGS": DEFAULT_VALUES["TP_AUTO_K8S_DP_SERVICE_ACCOUNT_CREATION_ADDITIONAL_SETTINGS"],
        "BWCE_APP_NAME": DEFAULT_VALUES["BWCE_APP_NAME"],
        "FLOGO_APP_NAME": DEFAULT_VALUES["FLOGO_APP_NAME"]
    }
    
    # Override Flogo app name if provided
    if app_name:
        params["FLOGO_APP_NAME"] = app_name
    
    # Set Data Plane name
    if dp_name:
        params["TP_AUTO_K8S_DP_NAME"] = dp_name
    
    logger.info(f"Creating and starting Flogo application '{params['FLOGO_APP_NAME']}' with parameters: {params}")
    
    try:
        return await run_automation_task("case.k8s_create_and_start_flogo_app", params)
    except Exception as e:
        logger.error(f"Failed to run through API, trying direct module execution: {str(e)}")
        return await execute_module("case.k8s_create_and_start_flogo_app", params)

# Delete App Actions
@mcp.tool()
async def delete_bwce_app(app_name: str = "", dp_name: str = "") -> str:
    """Delete BWCE App (Include removing the app from the kubernetes cluster)
    
    This tool automates the process of deleting a TIBCO BusinessWorks Container Edition (BWCE)
    application from a Kubernetes Data Plane. It performs a comprehensive deletion that includes
    removing the application from both the Control Plane management interface and the underlying
    Kubernetes resources.
    
    The tool performs the following operations:
    1. Logs into the Control Plane
    2. Navigates to the specified Data Plane
    3. Locates the BWCE application by name
    4. Initiates the deletion process which:
       - Stops the running application pods
       - Removes Kubernetes deployments, services, and other resources
       - Cleans up storage volumes associated with the application
       - Removes the application from the Control Plane registry
    
    Args:
        app_name: BWCE application name to delete (optional). If not provided,
                 the default name from environment configuration will be used.
        dp_name: Data Plane name where the application is deployed (optional).
                If not provided, the default Data Plane name from environment
                configuration will be used.
    
    Returns:
        Result of the BWCE app deletion process with detailed status information
        
    Example:
        # Delete BWCE app with default name
        delete_bwce_app()
        
        # Delete specific BWCE app
        delete_bwce_app(app_name="my-bwce-app")
        
        # Delete BWCE app from specific Data Plane
        delete_bwce_app(app_name="my-bwce-app", dp_name="my-dataplane")
        
    Note:
        This operation is irreversible. The application and all its data will be
        permanently deleted from the system. Make sure to back up any important
        data before proceeding with the deletion.
    """
    # Initialize parameters
    params = {}
    
    # Set application name if provided, otherwise use default
    if app_name:
        params["BWCE_APP_NAME"] = app_name
    else:
        params["BWCE_APP_NAME"] = DEFAULT_VALUES["BWCE_APP_NAME"]
    
    # Set Data Plane name if provided
    if dp_name:
        params["TP_AUTO_K8S_DP_NAME"] = dp_name
    
    logger.info(f"Deleting BWCE application '{params.get('BWCE_APP_NAME')}' from Data Plane '{params.get('TP_AUTO_K8S_DP_NAME', DEFAULT_VALUES['TP_AUTO_K8S_DP_NAME'])}")
    
    try:
        # Try to run the task through the API
        result = await run_automation_task("delete_bwce_app", params)
        logger.info(f"Successfully deleted BWCE application through API")
        return result
    except Exception as e:
        # Fallback to direct module execution if API fails
        logger.error(f"Failed to run through API, trying direct module execution: {str(e)}")
        return await execute_module("delete_bwce_app", params)

@mcp.tool()
async def delete_flogo_app(app_name: str = "", dp_name: str = "") -> str:
    """Delete Flogo App (Include removing the app from the kubernetes cluster)
    
    This tool automates the process of deleting a TIBCO Flogo Enterprise application
    from a Kubernetes Data Plane. It performs a comprehensive deletion that includes
    removing the application from both the Control Plane management interface and the
    underlying Kubernetes resources.
    
    The tool performs the following operations:
    1. Logs into the Control Plane
    2. Navigates to the specified Data Plane
    3. Locates the Flogo application by name
    4. Initiates the deletion process which:
       - Stops the running application pods
       - Removes Kubernetes deployments, services, and other resources
       - Cleans up storage volumes associated with the application
       - Removes the application from the Control Plane registry
       - Deletes any application-specific configurations
    
    Args:
        app_name: Flogo application name to delete (optional). If not provided,
                 the default name from environment configuration will be used.
        dp_name: Data Plane name where the application is deployed (optional).
                If not provided, the default Data Plane name from environment
                configuration will be used.
    
    Returns:
        Result of the Flogo app deletion process with detailed status information
        
    Example:
        # Delete Flogo app with default name
        delete_flogo_app()
        
        # Delete specific Flogo app
        delete_flogo_app(app_name="my-flogo-app")
        
        # Delete Flogo app from specific Data Plane
        delete_flogo_app(app_name="my-flogo-app", dp_name="my-dataplane")
        
    Note:
        This operation is irreversible. The application and all its data will be
        permanently deleted from the system. Make sure to back up any important
        data before proceeding with the deletion.
    """
    # Initialize parameters
    params = {}
    
    # Set application name if provided, otherwise use default
    if app_name:
        params["FLOGO_APP_NAME"] = app_name
    else:
        params["FLOGO_APP_NAME"] = DEFAULT_VALUES["FLOGO_APP_NAME"]
    
    # Set Data Plane name if provided
    if dp_name:
        params["TP_AUTO_K8S_DP_NAME"] = dp_name
    
    logger.info(f"Deleting Flogo application '{params.get('FLOGO_APP_NAME')}' from Data Plane '{params.get('TP_AUTO_K8S_DP_NAME', DEFAULT_VALUES['TP_AUTO_K8S_DP_NAME'])}")
    
    try:
        # Try to run the task through the API
        result = await run_automation_task("delete_flogo_app", params)
        logger.info(f"Successfully deleted Flogo application through API")
        return result
    except Exception as e:
        # Fallback to direct module execution if API fails
        logger.error(f"Failed to run through API, trying direct module execution: {str(e)}")
        return await execute_module("delete_flogo_app", params)

# Simple status check tool to verify server is running
@mcp.tool()
async def status() -> str:
    """Get the status of the TIBCO Platform Automation server
    
    This tool provides comprehensive information about the current state of the TIBCO
    Platform Automation server, including configuration settings and available automation
    cases. Use this to verify the server is running correctly and to check the current
    environment configuration.
    
    The tool returns the following information:
    1. Server Status: Confirms that the server is running and ready to accept commands
    2. Default Configuration: Lists all configuration parameters with their current values
       including Control Plane URLs, credentials, Data Plane names, and more
    3. Available Cases: Lists all automation cases that can be run, showing both the case name
       and the corresponding Python module
    
    This tool is useful for troubleshooting, verification, and understanding the
    current server configuration without making any changes to the system.
    
    Returns:
        A detailed report of the server status, configuration parameters, and available cases
        
    Example:
        # Check server status and configuration
        status()
    """
    status_text = "TIBCO Platform Automation Server Status\n"
    status_text += "=================================\n\n"
    status_text += "✓ Server is running and ready to accept commands\n\n"
    
    # Add server version if available
    # status_text += f"Server Version: {VERSION}\n\n"  # Uncomment when version is available
    
    # Add configuration information
    status_text += "Default Configuration:\n"
    status_text += "---------------------\n"
    for key in sorted(DEFAULT_VALUES.keys()):
        value = DEFAULT_VALUES[key]
        # Mask password fields for security
        if 'PASSWORD' in key:
            display_value = '********'
        else:
            display_value = value
        status_text += f"  {key}: {display_value}\n"
    
    # Add available automation cases
    status_text += "\nAvailable Automation Cases:\n"
    status_text += "---------------------------\n"
    for case, module in sorted(CASE_TO_MODULE.items()):
        status_text += f"  {case} -> {module}\n"
    
    # Add tool statistics
    tools_count = len([m for m in dir(mcp) if not m.startswith('_') and callable(getattr(mcp, m))])
    status_text += f"\nAvailable Tools: {tools_count}\n"
    
    return status_text

# For manual testing
if __name__ == "__main__":
    logger.info(f"TIBCO Platform Automation MCP Server initialized")
    logger.info(f"Project root: {PROJECT_ROOT}")
    logger.info(f"Automation path: {AUTOMATION_PATH}")
    mcp.port = 8090
    mcp.run()