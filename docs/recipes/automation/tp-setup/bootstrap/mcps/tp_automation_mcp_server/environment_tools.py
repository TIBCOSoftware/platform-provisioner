#!/usr/bin/env python3

#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary

import logging

from .automation_executor import run_automation_task, execute_module
from .config import DEFAULT_VALUES

logger = logging.getLogger('tibco-platform-provisioner-environment')

async def show_environment() -> str:
    """Show Current Environment (Login CP/Elastic Credentials)

    Returns:
        Information about the current environment
    """
    try:
        return await run_automation_task("page_env")
    except Exception as e:
        logger.error("Failed to run through API, trying direct module execution: %s", e)
        return await execute_module("page_env")

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
        logger.error("Failed to run through API, trying direct module execution: %s", e)
        return await execute_module("page_auth", params)

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
        logger.error("Failed to run through API, trying direct module execution: %s", e)
        return await execute_module("page_o11y", params)

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

    logger.info("Configuring global O11y with system config: %s", use_system_config)

    try:
        return await run_automation_task("case.create_global_config", params)
    except Exception as e:
        logger.error("Failed to run through API, trying direct module execution: %s", e)
        return await execute_module("case.create_global_config", params)
