#!/usr/bin/env python3

#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary

import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('tibco-platform-provisioner-config')

# Get project root directory
def get_project_root():
    """
    Get project root directory, supporting both development and container environments.
    Container: /app
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Check if we're in a container environment
    if '/app/mcps' in script_dir:
        # Container environment: /app/mcps/tp_automation_mcp_server -> /app
        return '/app'
    else:
        # Development environment: navigate up to platform-provisioner root
        # From tp_automation_mcp_server directory, go up 7 levels to reach platform-provisioner root
        return os.path.abspath(os.path.join(script_dir, '../../../../../../..'))

def get_automation_path():
    """
    Get automation path, supporting both development and container environments.
    """
    project_root = get_project_root()
    
    if project_root == '/app':
        # Container environment: automation scripts are in /app
        return '/app'
    else:
        # Development environment
        return os.path.join(project_root, 'docs/recipes/automation/tp-setup/bootstrap')

PROJECT_ROOT = get_project_root()
AUTOMATION_PATH = get_automation_path()

# MCP Server Configuration from Environment Variables
MCP_TRANSPORT = os.environ.get('TP_MCP_TRANSPORT', 'streamable-http')
MCP_SERVER_HOST = os.environ.get('TP_MCP_SERVER_HOST', '0.0.0.0')
MCP_SERVER_PORT = int(os.environ.get('TP_MCP_SERVER_PORT', '8090'))
MCP_HTTP_BEARER_TOKEN = os.environ.get('TP_MCP_HTTP_BEARER_TOKEN', None)

# Debug configuration
MCP_DEBUG = os.environ.get('TP_MCP_DEBUG', 'false').lower() in ('true', '1', 'yes')

# Validate transport type
VALID_TRANSPORTS = ['stdio', 'sse', 'streamable-http']
if MCP_TRANSPORT not in VALID_TRANSPORTS:
    logger.warning("Invalid transport '%s', using default 'streamable-http'", MCP_TRANSPORT)
    MCP_TRANSPORT = 'streamable-http'

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
    "BWCE_APP_NAME": "bwce-tt",
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
