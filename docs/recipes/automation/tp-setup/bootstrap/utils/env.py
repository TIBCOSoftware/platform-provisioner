#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary

import socket
import os
import pytz
from dataclasses import dataclass
from datetime import datetime
from utils.color_logger import ColorLogger
from utils.helper import Helper

@dataclass(frozen=True)
class EnvConfig:
    IS_HEADLESS = Helper.is_headless()

    # GITHUB_TOKEN = os.getenv("GITHUB_TOKEN") or "" # GitHub token is not used for now
    RETRY_TIME = datetime.now(pytz.timezone("America/Chicago"))
    RETRY_TIME_FOLDER = RETRY_TIME.strftime("%Y%m%d-%H%M%S")
    DP_HOST_PREFIX = os.environ.get("DP_HOST_PREFIX") or "cp-sub1"
    DP_USER_EMAIL = os.environ.get("DP_USER_EMAIL") or "cp-sub1@tibco.com"
    DP_USER_PASSWORD = os.environ.get("DP_USER_PASSWORD") or "Tibco@123"
    CP_ADMIN_EMAIL = os.environ.get("CP_ADMIN_EMAIL") or "cp-test@tibco.com"
    CP_ADMIN_PASSWORD = os.environ.get("CP_ADMIN_PASSWORD") or "Tibco@123"

    # other setup
    TP_AUTO_KUBECONFIG = os.environ.get("TP_AUTO_KUBECONFIG") or ""
    TP_AUTO_K8S_DP_SERVICE_ACCOUNT_CREATION_ADDITIONAL_SETTINGS = os.environ.get("TP_AUTO_K8S_DP_SERVICE_ACCOUNT_CREATION_ADDITIONAL_SETTINGS") or ""
    TP_CREATE_NETWORK_POLICIES = os.environ.get("TP_CREATE_NETWORK_POLICIES") or "false"
    TP_CLUSTER_NODE_CIDR = os.environ.get("TP_CLUSTER_NODE_CIDR") or ""
    TP_CLUSTER_POD_CIDR = os.environ.get("TP_CLUSTER_POD_CIDR") or ""
    TP_CLUSTER_SERVICE_CIDR = os.environ.get("TP_CLUSTER_SERVICE_CIDR") or ""

    # automation setup
    TP_AUTO_CP_VERSION = os.environ.get("TP_AUTO_CP_VERSION") or Helper.get_cp_version() or "1.4"
    TP_AUTO_REPORT_PATH = os.environ.get("TP_AUTO_REPORT_PATH") or os.path.join(os.getcwd(), "report")
    TP_AUTO_REPORT_YAML_FILE = os.environ.get("TP_AUTO_REPORT_YAML_FILE") or "report.yaml"  # automation script will create this file
    TP_AUTO_REPORT_TXT_FILE = os.environ.get("TP_AUTO_REPORT_TXT_FILE") or "report.txt"    # this is the final report file for user to view
    TP_AUTO_REPORT_TRACE = os.environ.get("TP_AUTO_REPORT_TRACE", "true").lower() == "true"
    TP_AUTO_IS_CREATE_DP = os.environ.get("TP_AUTO_IS_CREATE_DP", "false").lower() == "true"
    TP_AUTO_IS_CREATE_BMDP = os.environ.get("TP_AUTO_IS_CREATE_BMDP", "true").lower() == "true"
    TP_AUTO_IS_ENABLE_RVDM = os.environ.get("TP_AUTO_IS_ENABLE_RVDM", "true").lower() == "true"
    TP_AUTO_IS_ENABLE_EMSDM = os.environ.get("TP_AUTO_IS_ENABLE_EMSDM", "true").lower() == "true"
    TP_AUTO_IS_ENABLE_EMS_SERVER = os.environ.get("TP_AUTO_IS_ENABLE_EMS_SERVER", "true").lower() == "true"
    TP_AUTO_IS_CONFIG_O11Y = os.environ.get("TP_AUTO_IS_CONFIG_O11Y", "false").lower() == "true"
    TP_AUTO_IS_PROVISION_BWCE = os.environ.get("TP_AUTO_IS_PROVISION_BWCE", "false").lower() == "true"
    TP_AUTO_IS_PROVISION_EMS = os.environ.get("TP_AUTO_IS_PROVISION_EMS", "false").lower() == "true"
    TP_AUTO_IS_PROVISION_FLOGO = os.environ.get("TP_AUTO_IS_PROVISION_FLOGO", "false").lower() == "true"
    TP_AUTO_IS_PROVISION_PULSAR = os.environ.get("TP_AUTO_IS_PROVISION_PULSAR", "false").lower() == "true"
    TP_AUTO_IS_PROVISION_TIBCOHUB = os.environ.get("TP_AUTO_IS_PROVISION_TIBCOHUB", "false").lower() == "true"

    # k8s data plane
    TP_AUTO_K8S_DP_NAME_GLOBAL = "Global"
    TP_AUTO_K8S_DP_NAME = os.environ.get("TP_AUTO_K8S_DP_NAME") or "k8s-auto-dp1"
    TP_AUTO_K8S_DP_NAMESPACE = os.environ.get("TP_AUTO_K8S_DP_NAMESPACE") or f"{TP_AUTO_K8S_DP_NAME}ns"
    TP_AUTO_K8S_DP_SERVICE_ACCOUNT = os.environ.get("TP_AUTO_K8S_DP_SERVICE_ACCOUNT") or f"{TP_AUTO_K8S_DP_NAME}sa"

    # BMDP
    TP_AUTO_K8S_BMDP_NAME = os.environ.get("TP_AUTO_K8S_BMDP_NAME") or "k8s-auto-bmdp1"
    TP_AUTO_K8S_BMDP_NAMESPACE = os.environ.get("TP_AUTO_K8S_BMDP_NAMESPACE") or f"{TP_AUTO_K8S_BMDP_NAME}ns"
    TP_AUTO_K8S_BMDP_SERVICE_ACCOUNT = os.environ.get("TP_AUTO_K8S_BMDP_SERVICE_ACCOUNT") or f"{TP_AUTO_K8S_BMDP_NAME}sa"
    TP_AUTO_FQDN_BMDP = os.environ.get("TP_AUTO_FQDN_BMDP") or socket.gethostname()
    TP_AUTO_K8S_BMDP_BW5_RVDM = os.environ.get("TP_AUTO_K8S_BMDP_BW5_RVDM") or "tra5130rv"
    TP_AUTO_K8S_BMDP_BW5_RVDM_RV_SERVICE = os.environ.get("TP_AUTO_K8S_BMDP_BW5_RVDM_RV_SERVICE") or "7474"
    TP_AUTO_K8S_BMDP_BW5_RVDM_RV_NETWORK = os.environ.get("TP_AUTO_K8S_BMDP_BW5_RVDM_RV_NETWORK") or ""
    TP_AUTO_K8S_BMDP_BW5_RVDM_RV_DAEMON = os.environ.get("TP_AUTO_K8S_BMDP_BW5_RVDM_RV_DAEMON") or "tcp:rvd.bw5dm.svc.cluster.local:7474"
    TP_AUTO_K8S_BMDP_BW5_EMSDM = os.environ.get("TP_AUTO_K8S_BMDP_BW5_EMSDM") or "tra5130ems"
    TP_AUTO_K8S_BMDP_BW5_EMS_SERVER_URL = os.environ.get("TP_AUTO_K8S_BMDP_BW5_EMS_URL") or "tcp://ems.bw5dm.svc.cluster.local:7222"
    TP_AUTO_K8S_BMDP_BW5_EMS_USERNAME = os.environ.get("TP_AUTO_K8S_BMDP_BW5_EMS_USERNAME") or "admin"
    TP_AUTO_K8S_BMDP_BW5_EMS_PASSWORD = os.environ.get("TP_AUTO_K8S_BMDP_BW5_EMS_PASSWORD") or ""


    # CP_DNS_DOMAIN
    TP_AUTO_CP_INSTANCE_ID = os.environ.get("TP_AUTO_CP_INSTANCE_ID") or "cp1"
    TP_AUTO_CP_DNS_DOMAIN = os.environ.get("TP_AUTO_CP_DNS_DOMAIN") or Helper.get_cp_dns_domain() or "localhost.dataplanes.pro"
    TP_AUTO_CP_SERVICE_DNS_DOMAIN = os.environ.get("TP_AUTO_CP_SERVICE_DNS_DOMAIN") or f"{TP_AUTO_CP_INSTANCE_ID}-my.{TP_AUTO_CP_DNS_DOMAIN}"
    TP_AUTO_CP_DNS_DOMAIN_PREFIX_BWCE = os.environ.get("TP_AUTO_CP_DNS_DOMAIN_PREFIX_BWCE") or "bwce"
    TP_AUTO_CP_DNS_DOMAIN_PREFIX_FLOGO = os.environ.get("TP_AUTO_CP_DNS_DOMAIN_PREFIX_FLOGO") or "flogo"
    TP_AUTO_CP_DNS_DOMAIN_PREFIX_TIBCOHUB = os.environ.get("TP_AUTO_CP_DNS_DOMAIN_PREFIX_TIBCOHUB") or "tibcohub"

    TP_AUTO_LOGIN_URL = os.environ.get("TP_AUTO_LOGIN_URL") or f"https://{DP_HOST_PREFIX}.{TP_AUTO_CP_SERVICE_DNS_DOMAIN}/cp/login"
    TP_AUTO_MAIL_URL = os.environ.get("TP_AUTO_MAIL_URL") or f"https://mail.{TP_AUTO_CP_DNS_DOMAIN}/#/"
    TP_AUTO_ADMIN_URL = os.environ.get("TP_AUTO_ADMIN_URL") or f"https://admin.{TP_AUTO_CP_SERVICE_DNS_DOMAIN}/admin"

    # elastic and prometheus
    TP_AUTO_ELASTIC_URL = os.environ.get("TP_AUTO_ELASTIC_URL") or f"https://elastic.{TP_AUTO_CP_DNS_DOMAIN}/"
    TP_AUTO_KIBANA_URL = f"https://kibana.{TP_AUTO_CP_DNS_DOMAIN}/"
    TP_AUTO_ELASTIC_USER = os.environ.get("TP_AUTO_ELASTIC_USER") or "elastic"
    TP_AUTO_ELASTIC_PASSWORD = os.environ.get("TP_AUTO_ELASTIC_PASSWORD") or Helper.get_elastic_password()
    TP_AUTO_PROMETHEUS_URL = os.environ.get("TP_AUTO_PROMETHEUS_URL") or f"https://prometheus-internal.{TP_AUTO_CP_DNS_DOMAIN}/"
    TP_AUTO_PROMETHEUS_USER = os.environ.get("TP_AUTO_PROMETHEUS_USER") or ""
    TP_AUTO_PROMETHEUS_PASSWORD = os.environ.get("TP_AUTO_PROMETHEUS_PASSWORD") or ""

    # fqdn
    TP_AUTO_FQDN_BWCE = os.environ.get("TP_AUTO_FQDN_BWCE") or f"{TP_AUTO_CP_DNS_DOMAIN_PREFIX_BWCE}.{TP_AUTO_CP_DNS_DOMAIN}"
    TP_AUTO_FQDN_FLOGO = os.environ.get("TP_AUTO_FQDN_FLOGO") or f"{TP_AUTO_CP_DNS_DOMAIN_PREFIX_FLOGO}.{TP_AUTO_CP_DNS_DOMAIN}"
    TP_AUTO_FQDN_TIBCOHUB = os.environ.get("TP_AUTO_FQDN_TIBCOHUB") or f"{TP_AUTO_CP_DNS_DOMAIN_PREFIX_TIBCOHUB}.{TP_AUTO_CP_DNS_DOMAIN}"

    # capabilities url
    TP_AUTO_EMS_CAPABILITY_SERVER_NAME = os.environ.get("TP_AUTO_EMS_CAPABILITY_SERVER_NAME") or "ems-sn"
    TP_AUTO_PULSAR_CAPABILITY_SERVER_NAME = os.environ.get("TP_AUTO_PULSAR_CAPABILITY_SERVER_NAME") or "pulsar-sn"
    TP_AUTO_TIBCOHUB_CAPABILITY_HUB_NAME = os.environ.get("TP_AUTO_TIBCOHUB_CAPABILITY_HUB_NAME") or "tibco-hub"

    # data plane config
    TP_AUTO_DATA_PLANE_O11Y_SYSTEM_CONFIG = os.environ.get("TP_AUTO_DATA_PLANE_O11Y_SYSTEM_CONFIG", "false").lower() == "true"
    TP_AUTO_INGRESS_CONTROLLER = os.environ.get("TP_AUTO_INGRESS_CONTROLLER") or "nginx"
    TP_AUTO_INGRESS_CONTROLLER_CLASS_NAME = os.environ.get("TP_AUTO_INGRESS_CONTROLLER_CLASS_NAME") or "nginx"
    TP_AUTO_INGRESS_CONTROLLER_BWCE = os.environ.get("TP_AUTO_INGRESS_CONTROLLER_BWCE") or f"{TP_AUTO_INGRESS_CONTROLLER}-{TP_AUTO_CP_DNS_DOMAIN_PREFIX_BWCE}"
    TP_AUTO_INGRESS_CONTROLLER_FLOGO = os.environ.get("TP_AUTO_INGRESS_CONTROLLER_FLOGO") or f"{TP_AUTO_INGRESS_CONTROLLER}-{TP_AUTO_CP_DNS_DOMAIN_PREFIX_FLOGO}"
    TP_AUTO_INGRESS_CONTROLLER_TIBCOHUB = os.environ.get("TP_AUTO_INGRESS_CONTROLLER_TIBCOHUB") or f"{TP_AUTO_INGRESS_CONTROLLER}-{TP_AUTO_CP_DNS_DOMAIN_PREFIX_TIBCOHUB}"
    # TP_AUTO_INGRESS_CONTROLLER_KEYS = os.environ.get("TP_AUTO_INGRESS_CONTROLLER_KEYS") or ""
    # TP_AUTO_INGRESS_CONTROLLER_VALUES = os.environ.get("TP_AUTO_INGRESS_CONTROLLER_VALUES") or ""
    TP_AUTO_STORAGE_CLASS = os.environ.get("TP_AUTO_STORAGE_CLASS") or Helper.get_storage_class()
    # Due to the fuzzy matching of the dp name by Playwright
    # At most 0-9 dp are supported, if more dp is needed, the matching rule of dp selector is required
    TP_AUTO_MAX_DATA_PLANE = 9

    # apps: bwce, flogo
    BWCE_APP_FILE_NAME = os.environ.get("TP_AUTO_BWCE_APP_FILE_NAME") or "tt.ear"
    BWCE_APP_NAME = os.environ.get("BWCE_APP_NAME") or BWCE_APP_FILE_NAME.removesuffix(".ear")
    FLOGO_APP_FILE_NAME = os.environ.get("TP_AUTO_FLOGO_APP_FILE_NAME") or "flogo.json"
    # need to make sure the flogo app name is unique and lower case in the above JSON file
    FLOGO_APP_NAME = os.environ.get("FLOGO_APP_NAME") or Helper.get_app_name(FLOGO_APP_FILE_NAME)

    def pre_check(self):
        current_time = self.RETRY_TIME.strftime("%Y-%m-%d %H:%M:%S")
        ColorLogger.info(f"Current Retry time at '{current_time}'")
        ColorLogger.info(f"Current CP version is '{self.TP_AUTO_CP_VERSION}'")
        ColorLogger.info(f"Headless mode is {self.IS_HEADLESS}")
        if not self.TP_AUTO_CP_VERSION:
            ColorLogger.warning("CP version GUI_TP_AUTO_CP_VERSION is not set")
        if not self.TP_AUTO_IS_CREATE_DP:
            ColorLogger.warning(f"TP_AUTO_IS_CREATE_DP is false, will not create Data Plane")
        if not self.TP_AUTO_IS_CONFIG_O11Y:
            ColorLogger.warning(f"TP_AUTO_IS_CONFIG_O11Y is false, will not config Data Plane o11y")
        if not self.TP_AUTO_IS_PROVISION_BWCE:
            ColorLogger.warning(f"TP_AUTO_IS_PROVISION_BWCE is false, will not provision BWCE capability")
        if not self.TP_AUTO_IS_PROVISION_EMS:
            ColorLogger.warning(f"TP_AUTO_IS_PROVISION_EMS is false, will not provision EMS capability")
        if not self.TP_AUTO_IS_PROVISION_FLOGO:
            ColorLogger.warning(f"TP_AUTO_IS_PROVISION_FLOGO is false, will not provision Flogo capability")
        if not self.TP_AUTO_IS_PROVISION_PULSAR:
            ColorLogger.warning(f"TP_AUTO_IS_PROVISION_PULSAR is false, will not provision Pulsar capability")
        if not self.TP_AUTO_IS_PROVISION_TIBCOHUB:
            ColorLogger.warning(f"TP_AUTO_IS_PROVISION_TIBCOHUB is false, will not provision TibcoHub capability")

        if not os.environ.get("DP_HOST_PREFIX"):
            ColorLogger.warning(f"DP_HOST_PREFIX is not set, will use default: {self.DP_HOST_PREFIX}")
        if not os.environ.get("DP_USER_EMAIL"):
            ColorLogger.warning(f"DP_USER_EMAIL is not set, will use default: {self.DP_USER_EMAIL}")
        if not os.environ.get("DP_USER_PASSWORD"):
            ColorLogger.warning(f"DP_USER_PASSWORD is not set, will use default: {self.DP_USER_PASSWORD}")
        if not os.environ.get("CP_ADMIN_EMAIL"):
            ColorLogger.warning(f"CP_ADMIN_EMAIL is not set, will use default: {self.CP_ADMIN_EMAIL}")
        if not os.environ.get("CP_ADMIN_PASSWORD"):
            ColorLogger.warning(f"CP_ADMIN_PASSWORD is not set, will use default: {self.CP_ADMIN_PASSWORD}")

ENV = EnvConfig()
