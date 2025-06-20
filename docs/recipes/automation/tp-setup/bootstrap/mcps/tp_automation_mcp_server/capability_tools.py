#!/usr/bin/env python3

#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary

import logging
from typing import Dict, Any

from .automation_executor import run_automation_task, execute_module
from .config import DEFAULT_VALUES

logger = logging.getLogger('tibco-platform-provisioner-capability')

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
    params: Dict[str, Any] = {
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

    default_dp_name = params.get('TP_AUTO_K8S_DP_NAME', DEFAULT_VALUES['TP_AUTO_K8S_DP_NAME'])
    logger.info("Provisioning BWCE capability in Data Plane '%s'", default_dp_name)

    try:
        return await run_automation_task("case.k8s_provision_capability", params)
    except Exception as e:
        logger.error("Failed to run through API, trying direct module execution: %s", e)
        return await execute_module("case.k8s_provision_capability", params)

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
    params: Dict[str, Any] = {
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

    default_dp_name = params.get('TP_AUTO_K8S_DP_NAME', DEFAULT_VALUES['TP_AUTO_K8S_DP_NAME'])
    logger.info("Provisioning EMS capability in Data Plane '%s'", default_dp_name)

    try:
        return await run_automation_task("case.k8s_provision_capability", params)
    except Exception as e:
        logger.error("Failed to run through API, trying direct module execution: %s", e)
        return await execute_module("case.k8s_provision_capability", params)

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
    params: Dict[str, Any] = {
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

    default_dp_name = params.get('TP_AUTO_K8S_DP_NAME', DEFAULT_VALUES['TP_AUTO_K8S_DP_NAME'])
    logger.info("Provisioning Flogo capability in Data Plane '%s'", default_dp_name)

    try:
        return await run_automation_task("case.k8s_provision_capability", params)
    except Exception as e:
        logger.error("Failed to run through API, trying direct module execution: %s", e)
        return await execute_module("case.k8s_provision_capability", params)

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
    params: Dict[str, Any] = {
        "TP_AUTO_IS_CONFIG_O11Y": True,
        "TP_AUTO_IS_PROVISION_PULSAR": True,
        "HEADLESS": True,
        "FORCE_RUN_AUTOMATION": False,
        "IS_CLEAN_REPORT": False,
    }

    # Set Data Plane name if provided
    if dp_name:
        params["TP_AUTO_K8S_DP_NAME"] = dp_name

    default_dp_name = params.get('TP_AUTO_K8S_DP_NAME', DEFAULT_VALUES['TP_AUTO_K8S_DP_NAME'])
    logger.info("Provisioning Pulsar capability in Data Plane '%s'", default_dp_name)

    try:
        return await run_automation_task("case.k8s_provision_capability", params)
    except Exception as e:
        logger.error("Failed to run through API, trying direct module execution: %s", e)
        return await execute_module("case.k8s_provision_capability", params)

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
    params: Dict[str, Any] = {
        "TP_AUTO_IS_CONFIG_O11Y": True,
        "TP_AUTO_IS_PROVISION_TIBCOHUB": True,
        "HEADLESS": True,
        "FORCE_RUN_AUTOMATION": False,
        "IS_CLEAN_REPORT": False,
    }

    # Set Data Plane name if provided
    if dp_name:
        params["TP_AUTO_K8S_DP_NAME"] = dp_name

    default_dp_name = params.get('TP_AUTO_K8S_DP_NAME', DEFAULT_VALUES['TP_AUTO_K8S_DP_NAME'])
    logger.info("Provisioning TIBCO Hub capability in Data Plane '%s'", default_dp_name)

    try:
        return await run_automation_task("case.k8s_provision_capability", params)
    except Exception as e:
        logger.error("Failed to run through API, trying direct module execution: %s", e)
        return await execute_module("case.k8s_provision_capability", params)
