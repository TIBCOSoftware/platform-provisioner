#!/usr/bin/env python3

#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary

import logging
from typing import Dict, Any

from .automation_executor import run_automation_task, execute_module
from .config import DEFAULT_VALUES

logger = logging.getLogger('tibco-platform-provisioner-application')

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
    params: Dict[str, Any] = {
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

    logger.info("Creating and starting BWCE application '%s' with parameters: %s", 
                params['BWCE_APP_NAME'], params)

    try:
        return await run_automation_task("case.k8s_create_and_start_bwce_app", params)
    except Exception as e:
        logger.error("Failed to run through API, trying direct module execution: %s", e)
        return await execute_module("case.k8s_create_and_start_bwce_app", params)

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
    params: Dict[str, Any] = {
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

    logger.info("Creating and starting Flogo application '%s' with parameters: %s", 
                params['FLOGO_APP_NAME'], params)

    try:
        return await run_automation_task("case.k8s_create_and_start_flogo_app", params)
    except Exception as e:
        logger.error("Failed to run through API, trying direct module execution: %s", e)
        return await execute_module("case.k8s_create_and_start_flogo_app", params)

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
    params: Dict[str, Any] = {}

    # Set application name if provided, otherwise use default
    if app_name:
        params["BWCE_APP_NAME"] = app_name
    else:
        params["BWCE_APP_NAME"] = DEFAULT_VALUES["BWCE_APP_NAME"]

    # Set Data Plane name if provided
    if dp_name:
        params["TP_AUTO_K8S_DP_NAME"] = dp_name

    default_dp_name = params.get('TP_AUTO_K8S_DP_NAME', DEFAULT_VALUES['TP_AUTO_K8S_DP_NAME'])
    logger.info("Deleting BWCE application '%s' from Data Plane '%s'", 
                params.get('BWCE_APP_NAME'), default_dp_name)

    try:
        # Try to run the task through the API
        result = await run_automation_task("delete_bwce_app", params)
        logger.info("Successfully deleted BWCE application through API")
        return result
    except Exception as e:
        # Fallback to direct module execution if API fails
        logger.error("Failed to run through API, trying direct module execution: %s", e)
        return await execute_module("delete_bwce_app", params)

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
    params: Dict[str, Any] = {}

    # Set application name if provided, otherwise use default
    if app_name:
        params["FLOGO_APP_NAME"] = app_name
    else:
        params["FLOGO_APP_NAME"] = DEFAULT_VALUES["FLOGO_APP_NAME"]

    # Set Data Plane name if provided
    if dp_name:
        params["TP_AUTO_K8S_DP_NAME"] = dp_name

    default_dp_name = params.get('TP_AUTO_K8S_DP_NAME', DEFAULT_VALUES['TP_AUTO_K8S_DP_NAME'])
    logger.info("Deleting Flogo application '%s' from Data Plane '%s'", 
                params.get('FLOGO_APP_NAME'), default_dp_name)

    try:
        # Try to run the task through the API
        result = await run_automation_task("delete_flogo_app", params)
        logger.info("Successfully deleted Flogo application through API")
        return result
    except Exception as e:
        # Fallback to direct module execution if API fails
        logger.error("Failed to run through API, trying direct module execution: %s", e)
        return await execute_module("delete_flogo_app", params)
