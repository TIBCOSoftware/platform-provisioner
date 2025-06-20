#!/usr/bin/env python3

#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary

import logging
from typing import Dict, Any

from .automation_executor import run_automation_task, execute_module
from .config import DEFAULT_VALUES

logger = logging.getLogger('tibco-platform-provisioner-dataplane')

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
    params: Dict[str, Any] = {
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

    logger.info("Creating K8s DataPlane with parameters: %s", params)

    try:
        logger.info("Starting DataPlane creation automation...")
        result = await run_automation_task("case.k8s_create_dp", params)
        logger.info("DataPlane creation automation completed successfully")
        return result
    except Exception as e:
        logger.error("Failed to run through API, trying direct module execution: %s", e)
        try:
            logger.info("Attempting direct module execution...")
            result = await execute_module("case.k8s_create_dp", params)
            logger.info("Direct module execution completed successfully")
            return result
        except Exception as module_error:
            error_msg = f"Both API call and direct module execution failed. API error: {str(e)}, Module error: {str(module_error)}"
            logger.error(error_msg)
            return error_msg

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

    logger.info("Configuring Data Plane O11y for '%s' with system config: %s", 
                params['TP_AUTO_K8S_DP_NAME'], use_system_config)

    try:
        return await run_automation_task("case.k8s_config_dp_o11y", params)
    except Exception as e:
        logger.error("Failed to run through API, trying direct module execution: %s", e)
        return await execute_module("case.k8s_config_dp_o11y", params)

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
    params: Dict[str, Any] = {}

    # Set dataplane name if provided
    if dp_name:
        params["TP_AUTO_K8S_DP_NAME"] = dp_name

    logger.info("Deleting K8s DataPlane with parameters: %s", params)

    try:
        return await run_automation_task("case.k8s_delete_dp", params)
    except Exception as e:
        logger.error("Failed to run through API, trying direct module execution: %s", e)
        return await execute_module("case.k8s_delete_dp", params)
