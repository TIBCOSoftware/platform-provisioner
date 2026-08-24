#
# Copyright 2025 Cloud Software Group, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import socket
import os
import pytz
from dataclasses import dataclass
from datetime import datetime
from utils.color_logger import ColorLogger
from utils.helper import Helper
# Note: do NOT import utils.util here, it imports utils.report and is itself imported by
# page_dp.py -> that would be a circular import.

_PROVISION_FLAG_PREFIX = "TP_AUTO_IS_PROVISION_"

# TP_AUTO_IS_PROVISION_* flags that must never make a run look like it wants a Data Plane.
# Two DIFFERENT reasons live here, both load-bearing:
#
# (1) "not a capability at all" - TP_AUTO_IS_PROVISION_USER_WITHOUT_EMAIL gates a user creation
#     mode. It defaults to "true" below, and
#     charts/provisioner-config-local/recipes/tp-automation-o11y.yaml exports it as a pipeline
#     global that also defaults to true. Without this entry the guard would refuse 100% of
#     TP_AUTO_IS_CREATE_DP=false runs, including the legitimate CP-only ones - a worse outage
#     than the bug it is meant to catch.
#
# (2) "a capability, but not one page_dp.py can provision" - page_dp.py's capability blocks are
#     Flogo, BWCE/BW5CE, EMS, Pulsar, TibcoHub and SpringBoot only. The Infra MCP Server is
#     provisioned by case/k8s_provision_infra_mcp_server.py against an ALREADY registered Data
#     Plane (the deploy-infra-mcp-server task runs that module, not page_dp.py), so
#     TP_AUTO_IS_PROVISION_INFRA_MCP_SERVER can never make a page_dp.py run unsatisfiable. Only
#     page_dp.py consults this guard, so refusing on that flag would abort a run whose
#     capability work is done elsewhere, against a Data Plane that already exists.
_OUT_OF_SCOPE_PROVISION_FLAGS = frozenset({
    "TP_AUTO_IS_PROVISION_USER_WITHOUT_EMAIL",  # (1) not a capability
    "TP_AUTO_IS_PROVISION_INFRA_MCP_SERVER",      # (2) not provisioned by page_dp.py
})

# python flag name -> GUI variable a user actually sets, for the non-mechanical cases only.
# Everything else is derived as TP_AUTO_IS_PROVISION_X -> GUI_TP_AUTO_ENABLE_X.
_PROVISION_FLAG_GUI_OVERRIDES = {
    "TP_AUTO_IS_PROVISION_SPRINGBOOT": "GUI_TP_AUTO_ENABLE_SB",
}

# Capabilities with NO GUI variable at all. The derivation above is mechanical, so without this
# set it would invent a name: GUI_TP_AUTO_ENABLE_PULSAR exists nowhere - not in
# charts/provisioner-config-local/recipes/tp-automation-o11y.yaml, not in
# charts/provisioner-config-local/config/pp-maintain-tp-automation-o11y.yaml (the Provisioner UI
# descriptor), and not in docs/recipes/k8s/on-prem/scripts/headless/tp-install-on-prem.sh. Pulsar
# is reachable only through the raw TP_AUTO_IS_PROVISION_PULSAR environment variable, and it has
# no TP_AUTO_ENABLE_PULSAR pipeline global either, which is why the recipe pre-flight has no
# Pulsar row to check. Telling a user to unset a variable that does not exist is worse than
# telling them nothing, so these report the knob they can actually turn.
_PROVISION_FLAGS_WITHOUT_GUI = frozenset({
    "TP_AUTO_IS_PROVISION_PULSAR",
})

def provision_flag_setting_name(flag_name):
    """Map a TP_AUTO_IS_PROVISION_* flag to the variable a user can actually set.

    That is the GUI_* variable where one exists - user-facing text is keyed on the variable name
    rather than on a checkbox label because the variable names are byte-identical in the on-prem
    and SaaS UIs while the labels are not - and the raw flag itself where one does not.

    The return value is never empty: every finding must name something settable, or the
    remediation it appears in is unactionable.
    """
    if flag_name in _PROVISION_FLAGS_WITHOUT_GUI:
        return flag_name
    if flag_name in _PROVISION_FLAG_GUI_OVERRIDES:
        return _PROVISION_FLAG_GUI_OVERRIDES[flag_name]
    return f"GUI_TP_AUTO_ENABLE_{flag_name[len(_PROVISION_FLAG_PREFIX):]}"

def unsatisfiable_capabilities(is_create_dp, provision_flags):
    """Return the capability flags that can never be satisfied by this run.

    Capabilities are provisioned inside a Data Plane, so every enabled capability flag is
    unsatisfiable when the run does not create one, except for the flags listed in
    _OUT_OF_SCOPE_PROVISION_FLAGS. Returns one entry per offending flag:
    {"flag": <python flag name>, "setting": <variable the user sets>} - both are always
    populated, so a caller can never render a name the user has no way to change.

    Pure on purpose: no ENV access and no I/O, so it is unit testable without monkeypatching.
    """
    if is_create_dp:
        return []

    findings = []
    for flag_name in sorted(provision_flags):  # sorted so the reported order is deterministic
        if flag_name in _OUT_OF_SCOPE_PROVISION_FLAGS:
            continue
        if not provision_flags[flag_name]:
            continue
        findings.append({"flag": flag_name, "setting": provision_flag_setting_name(flag_name)})
    return findings

@dataclass(frozen=True)
class EnvConfig:
    IS_HEADLESS = Helper.is_headless()
    IS_CLUSTER_ACCESSIBLE = "Kubernetes control plane" in (Helper.get_command_output("kubectl cluster-info", is_print_error=False) or "")

    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN") or ""
    TP_AUTO_APP_RELEASE_REPO = os.getenv("TP_AUTO_APP_RELEASE_REPO", "tibco/platform-provisioner")
    TP_AUTO_APP_RELEASE_TAG = os.getenv("TP_AUTO_APP_RELEASE_TAG", "test-apps-v1.0.0")

    # BW5 domain chart + image registry (JFrog). Defaults mirror charts/.../recipes/tp-deploy-bw5dm.yaml
    TP_BW5_CHART_REPO = os.environ.get("TP_BW5_CHART_REPO") or "https://csgprdusw2reposaas.jfrog.io/artifactory/api/helm/tibco-platform-helm-dev-github"
    TP_BW5_CHART_REPO_USER_NAME = os.environ.get("TP_BW5_CHART_REPO_USER_NAME") or "tibco-platform-devops-read"
    TP_BW5_CHART_REPO_TOKEN = os.environ.get("TP_BW5_CHART_REPO_TOKEN") or ""
    TP_BW5_CHART_VERSION = os.environ.get("TP_BW5_CHART_VERSION") or "^1.2.0"
    TP_BW5_CONTAINER_REGISTRY = os.environ.get("TP_BW5_CONTAINER_REGISTRY") or "csgprdusw2reposaas.jfrog.io"
    TP_BW5_CONTAINER_REGISTRY_REPOSITORY = os.environ.get("TP_BW5_CONTAINER_REGISTRY_REPOSITORY") or "tibco-platform-docker-dev"
    TIME_ZONE = "America/Chicago"
    RETRY_TIME = datetime.now(pytz.timezone(TIME_ZONE))
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

    # CLI mode: when true, use tibcop CLI instead of GUI (Playwright) for DP operations
    TP_AUTO_USE_CLI = os.environ.get("TP_AUTO_USE_CLI", "false").lower() == "true"

    # automation setup
    TP_AUTO_CP_VERSION = os.environ.get("TP_AUTO_CP_VERSION") or Helper.get_cp_version() or ""
    TP_AUTO_REPORT_PATH = os.environ.get("TP_AUTO_REPORT_PATH") or os.path.join(os.getcwd(), "report")
    TP_AUTO_REPORT_YAML_FILE = os.environ.get("TP_AUTO_REPORT_YAML_FILE") or "report.yaml"  # automation script will create this file
    TP_AUTO_REPORT_TXT_FILE = os.environ.get("TP_AUTO_REPORT_TXT_FILE") or "report.txt"    # this is the final report file for user to view
    TP_AUTO_REPORT_TRACE = os.environ.get("TP_AUTO_REPORT_TRACE", "true").lower() == "true"
    TP_AUTO_IS_CREATE_DP = os.environ.get("TP_AUTO_IS_CREATE_DP", "false").lower() == "true"
    TP_AUTO_IS_CREATE_BMDP = os.environ.get("TP_AUTO_IS_CREATE_BMDP", "true").lower() == "true"
    TP_AUTO_IS_ENABLE_RVDM = os.environ.get("TP_AUTO_IS_ENABLE_RVDM", "true").lower() == "true"
    TP_AUTO_IS_ENABLE_EMSDM = os.environ.get("TP_AUTO_IS_ENABLE_EMSDM", "true").lower() == "true"
    TP_AUTO_IS_ENABLE_EMS_SERVER = os.environ.get("TP_AUTO_IS_ENABLE_EMS_SERVER", "true").lower() == "true"
    TP_AUTO_IS_ENABLE_BW6DM = os.environ.get("TP_AUTO_IS_ENABLE_BW6DM", "true").lower() == "true"
    TP_AUTO_IS_CONFIG_O11Y = os.environ.get("TP_AUTO_IS_CONFIG_O11Y", "false").lower() == "true"
    TP_AUTO_IS_PROVISION_AS = os.environ.get("TP_AUTO_IS_PROVISION_AS", "false").lower() == "true"
    TP_AUTO_IS_PROVISION_BWCE = os.environ.get("TP_AUTO_IS_PROVISION_BWCE", "false").lower() == "true"
    TP_AUTO_IS_PROVISION_BW5CE = os.environ.get("TP_AUTO_IS_PROVISION_BW5CE", "false").lower() == "true"
    TP_AUTO_IS_PROVISION_EMS = os.environ.get("TP_AUTO_IS_PROVISION_EMS", "false").lower() == "true"
    TP_AUTO_IS_PROVISION_FLOGO = os.environ.get("TP_AUTO_IS_PROVISION_FLOGO", "false").lower() == "true"
    TP_AUTO_IS_PROVISION_PULSAR = os.environ.get("TP_AUTO_IS_PROVISION_PULSAR", "false").lower() == "true"
    TP_AUTO_IS_PROVISION_TIBCOHUB = os.environ.get("TP_AUTO_IS_PROVISION_TIBCOHUB", "false").lower() == "true"
    TP_AUTO_IS_PROVISION_INFRA_MCP_SERVER = os.environ.get("TP_AUTO_IS_PROVISION_INFRA_MCP_SERVER", "false").lower() == "true"
    TP_AUTO_IS_PROVISION_SPRINGBOOT = os.environ.get("TP_AUTO_IS_PROVISION_SPRINGBOOT", "false").lower() == "true"
    TP_AI_ENABLE_MCP_HUB = os.environ.get("TP_AI_ENABLE_MCP_HUB", "false").lower() == "true"
    TP_AUTO_IS_PROVISION_USER_WITHOUT_EMAIL = os.environ.get("TP_AUTO_IS_PROVISION_USER_WITHOUT_EMAIL", "true").lower() == "true"

    # OAuth token
    TP_AUTO_TOKEN_NAMESPACE = os.environ.get("TP_AUTO_TOKEN_NAMESPACE") or "automation"
    TP_AUTO_TOKEN_NAME = os.environ.get("TP_AUTO_TOKEN_NAME") or "auto-token"
    TP_AUTO_TOKEN_DURATION = os.environ.get("TP_AUTO_TOKEN_DURATION") or "12"
    TP_AUTO_TOKEN_DURATION_UNIT = os.environ.get("TP_AUTO_TOKEN_DURATION_UNIT") or "Months"

    # start app or not
    TP_AUTO_START_FLOGO_APP = os.environ.get("TP_AUTO_START_FLOGO_APP", "true").lower() == "true"
    TP_AUTO_START_BWCE_APP = os.environ.get("TP_AUTO_START_BWCE_APP", "false").lower() == "true"
    TP_AUTO_START_BW5CE_APP = os.environ.get("TP_AUTO_START_BW5CE_APP", "false").lower() == "true"
    TP_AUTO_START_SPRINGBOOT_APP = os.environ.get("TP_AUTO_START_SPRINGBOOT_APP", "false").lower() == "true"

    # k8s data plane
    TP_AUTO_DP_NAME_GLOBAL = "Global"
    TP_AUTO_K8S_DP_NAME = os.environ.get("TP_AUTO_K8S_DP_NAME") or "k8s-auto-dp1"
    TP_AUTO_K8S_DP_NAMESPACE = os.environ.get("TP_AUTO_K8S_DP_NAMESPACE") or f"{TP_AUTO_K8S_DP_NAME}ns"
    TP_AUTO_K8S_DP_SERVICE_ACCOUNT = os.environ.get("TP_AUTO_K8S_DP_SERVICE_ACCOUNT") or f"{TP_AUTO_K8S_DP_NAME}sa"
    TIBCOP_CLI_DP_NAME = os.environ.get("TIBCOP_CLI_DP_NAME") or "k8s-auto-dp1"
    TIBCOP_CLI_DP_NAMESPACE = os.environ.get("TIBCOP_CLI_DP_NAMESPACE") or f"{TIBCOP_CLI_DP_NAME}ns"
    TIBCOP_CLI_DP_SERVICE_ACCOUNT = os.environ.get("TIBCOP_CLI_DP_SERVICE_ACCOUNT") or f"{TIBCOP_CLI_DP_NAME}sa"

    # activation sever file
    TP_ACTIVATION_ZIP_FILE_BASE64 = os.environ.get("TP_ACTIVATION_ZIP_FILE_BASE64") or ""
    TP_ACTIVATION_FILENAME = "license-file.bin"
    TP_AUTO_LICENSE_FILE_PATH = os.environ.get("TP_AUTO_LICENSE_FILE_PATH") or Helper.get_file_fullpath_in_upload_folder(TP_ACTIVATION_FILENAME)

    # self-signed certificate
    TP_IS_CERT_SELF_SIGNED = os.environ.get("TP_IS_CERT_SELF_SIGNED", "false").lower() == "true"

    # activation url
    TP_ACTIVATION_SERVER_CERT_HOSTNAME = os.environ.get("TP_ACTIVATION_SERVER_CERT_HOSTNAME") or ""
    TP_ACTIVATION_SERVER_PORT = os.environ.get("TP_ACTIVATION_SERVER_PORT") or "7070"
    TP_ACTIVATION_SERVER_FINGER_PRINT = os.environ.get("TP_ACTIVATION_SERVER_FINGER_PRINT") or ""
    TP_ACTIVATION_URL = (
        f"https://{TP_ACTIVATION_SERVER_CERT_HOSTNAME}:{TP_ACTIVATION_SERVER_PORT}/?fp={TP_ACTIVATION_SERVER_FINGER_PRINT}"
        if TP_ACTIVATION_SERVER_CERT_HOSTNAME and TP_ACTIVATION_SERVER_FINGER_PRINT
        else ""
    )

    # BMDP
    TP_AUTO_K8S_BMDP_NAME = os.environ.get("TP_AUTO_K8S_BMDP_NAME") or "k8s-auto-bmdp1"
    TP_AUTO_K8S_BMDP_NAMESPACE = os.environ.get("TP_AUTO_K8S_BMDP_NAMESPACE") or f"{TP_AUTO_K8S_BMDP_NAME}ns"
    TP_AUTO_K8S_BMDP_SERVICE_ACCOUNT = os.environ.get("TP_AUTO_K8S_BMDP_SERVICE_ACCOUNT") or f"{TP_AUTO_K8S_BMDP_NAME}sa"
    TP_AUTO_FQDN_BMDP = os.environ.get("TP_AUTO_FQDN_BMDP") or socket.gethostname().lower()
    TP_AUTO_BW5_APP_NAME = os.environ.get("TP_AUTO_BW5_APP_NAME") or os.environ.get("TP_BW5_APP_NAME") or "RestSample"
    TP_AUTO_K8S_BMDP_BW5_RVDM = os.environ.get("TP_AUTO_K8S_BMDP_BW5_RVDM") or "tra5130rv"
    TP_AUTO_K8S_BMDP_BW5_RVDM_RV_SERVICE = os.environ.get("TP_AUTO_K8S_BMDP_BW5_RVDM_RV_SERVICE") or "7474"
    TP_AUTO_K8S_BMDP_BW5_RVDM_RV_NETWORK = os.environ.get("TP_AUTO_K8S_BMDP_BW5_RVDM_RV_NETWORK") or ""
    TP_AUTO_K8S_BMDP_BW5_RVDM_RV_DAEMON = os.environ.get("TP_AUTO_K8S_BMDP_BW5_RVDM_RV_DAEMON") or "tcp:rvd.bw5dm.svc.cluster.local:7474"
    TP_AUTO_K8S_BMDP_BW5_EMSDM = os.environ.get("TP_AUTO_K8S_BMDP_BW5_EMSDM") or "tra5130ems"
    TP_AUTO_K8S_BMDP_BW5_EMS_SERVER_URL = os.environ.get("TP_AUTO_K8S_BMDP_BW5_EMS_URL") or "tcp://ems.bw5dm.svc.cluster.local:7222"
    TP_AUTO_K8S_BMDP_BW5_EMS_MONITOR_URL = os.environ.get("TP_AUTO_K8S_BMDP_BW5_EMS_MONITOR_URL") or "http://ems.bw5dm.svc.cluster.local:7220"
    TP_AUTO_K8S_BMDP_BW5_EMS_USERNAME = os.environ.get("TP_AUTO_K8S_BMDP_BW5_EMS_USERNAME") or "admin"
    TP_AUTO_K8S_BMDP_BW5_EMS_PASSWORD = os.environ.get("TP_AUTO_K8S_BMDP_BW5_EMS_PASSWORD") or ""
    TP_AUTO_K8S_BMDP_BW6DM = os.environ.get("TP_AUTO_K8S_BMDP_BW6DM") or "bw6110"
    TP_AUTO_K8S_BMDP_BW6DM_URL = os.environ.get("TP_AUTO_K8S_BMDP_BW6DM_URL") or "http://bw6dm.bw5dm.svc:9091/bwta"
    TP_OTEL_TRACES_ENDPOINT = os.environ.get("TP_OTEL_TRACES_ENDPOINT") or "http://otel-userapp-traces.k8s-auto-bmdp1ns.svc:4318/v1/traces"
    TP_OTEL_METRICS_ENDPOINT = os.environ.get("TP_OTEL_METRICS_ENDPOINT") or "http://otel-userapp-metrics.k8s-auto-bmdp1ns.svc:4318/v1/metrics"
    TP_OTEL_LOGS_ENDPOINT = os.environ.get("TP_OTEL_LOGS_ENDPOINT") or "http://otel-userapp-logs.k8s-auto-bmdp1ns.svc:4318/v1/logs"
    TP_BMDP_IMAGE_TAG_BW5EMSDM = os.environ.get("TP_BMDP_IMAGE_TAG_BW5EMSDM") or "emsdm-latest"
    TP_BMDP_IMAGE_TAG_EMS = os.environ.get("TP_BMDP_IMAGE_TAG_EMS") or "ems-latest"
    TP_BMDP_IMAGE_TAG_BW5RVDM = os.environ.get("TP_BMDP_IMAGE_TAG_BW5RVDM") or "rvdm-latest"
    TP_BMDP_IMAGE_TAG_BW6DM = os.environ.get("TP_BMDP_IMAGE_TAG_BW6DM") or "bw6-latest"

    # CP_DNS_DOMAIN
    TP_AUTO_CP_INSTANCE_ID = os.environ.get("TP_AUTO_CP_INSTANCE_ID") or "cp1"
    TP_AUTO_CP_NAMESPACE = os.environ.get("TP_AUTO_CP_NAMESPACE") or f"{TP_AUTO_CP_INSTANCE_ID}-ns"
    TP_AUTO_CP_DNS_DOMAIN = os.environ.get("TP_AUTO_CP_DNS_DOMAIN") or Helper.get_cp_dns_domain() or "localhost.dataplanes.pro"
    TP_AUTO_CP_SERVICE_DNS_DOMAIN = os.environ.get("TP_AUTO_CP_SERVICE_DNS_DOMAIN") or f"{TP_AUTO_CP_INSTANCE_ID}-my.{TP_AUTO_CP_DNS_DOMAIN}"
    TP_AUTO_CP_DNS_DOMAIN_PREFIX_BWCE = os.environ.get("TP_AUTO_CP_DNS_DOMAIN_PREFIX_BWCE") or "bwce"
    TP_AUTO_CP_DNS_DOMAIN_PREFIX_BW5CE = os.environ.get("TP_AUTO_CP_DNS_DOMAIN_PREFIX_BW5CE") or "bw5ce"
    TP_AUTO_CP_DNS_DOMAIN_PREFIX_FLOGO = os.environ.get("TP_AUTO_CP_DNS_DOMAIN_PREFIX_FLOGO") or "flogo"
    TP_AUTO_CP_DNS_DOMAIN_PREFIX_TIBCOHUB = os.environ.get("TP_AUTO_CP_DNS_DOMAIN_PREFIX_TIBCOHUB") or "tibcohub"
    TP_AUTO_CP_DNS_DOMAIN_PREFIX_INFRA_MCP_SERVER = os.environ.get("TP_AUTO_CP_DNS_DOMAIN_PREFIX_INFRA_MCP_SERVER") or "k8smcp"
    TP_AUTO_CP_DNS_DOMAIN_PREFIX_SPRINGBOOT = os.environ.get("TP_AUTO_CP_DNS_DOMAIN_PREFIX_SPRINGBOOT") or "springboot"

    TP_AUTO_LOGIN_URL = os.environ.get("TP_AUTO_LOGIN_URL") or f"https://{DP_HOST_PREFIX}.{TP_AUTO_CP_SERVICE_DNS_DOMAIN}/cp/login"
    TP_AUTO_MAIL_URL = os.environ.get("TP_AUTO_MAIL_URL") or f"https://mail.{TP_AUTO_CP_DNS_DOMAIN}/#/"
    TP_AUTO_ADMIN_URL = os.environ.get("TP_AUTO_ADMIN_URL") or f"https://admin.{TP_AUTO_CP_SERVICE_DNS_DOMAIN}/admin"

    # elastic and prometheus
    TP_AUTO_ELASTIC_URL = os.environ.get("TP_AUTO_ELASTIC_URL") or f"https://elastic.{TP_AUTO_CP_DNS_DOMAIN}/"
    TP_AUTO_KIBANA_URL = f"https://kibana.{TP_AUTO_CP_DNS_DOMAIN}/"
    TP_AUTO_ELASTIC_USER = os.environ.get("TP_AUTO_ELASTIC_USER") or "elastic"
    TP_AUTO_ELASTIC_PASSWORD = os.environ.get("TP_AUTO_ELASTIC_PASSWORD") or Helper.get_elastic_password()
    # PCP-16998
    TP_AUTO_PROMETHEUS_URL = os.environ.get("TP_AUTO_PROMETHEUS_URL") or f"http://kube-prometheus-stack-prometheus.prometheus-system.svc.cluster.local:9090"
    TP_AUTO_PROMETHEUS_USER = os.environ.get("TP_AUTO_PROMETHEUS_USER") or ""
    TP_AUTO_PROMETHEUS_PASSWORD = os.environ.get("TP_AUTO_PROMETHEUS_PASSWORD") or ""

    # fqdn
    TP_AUTO_FQDN_BWCE = os.environ.get("TP_AUTO_FQDN_BWCE") or f"{TP_AUTO_CP_DNS_DOMAIN_PREFIX_BWCE}.{TP_AUTO_CP_DNS_DOMAIN}"
    TP_AUTO_FQDN_BW5CE = os.environ.get("TP_AUTO_FQDN_BW5CE") or f"{TP_AUTO_CP_DNS_DOMAIN_PREFIX_BW5CE}.{TP_AUTO_CP_DNS_DOMAIN}"
    TP_AUTO_FQDN_FLOGO = os.environ.get("TP_AUTO_FQDN_FLOGO") or f"{TP_AUTO_CP_DNS_DOMAIN_PREFIX_FLOGO}.{TP_AUTO_CP_DNS_DOMAIN}"
    TP_AUTO_FQDN_TIBCOHUB = os.environ.get("TP_AUTO_FQDN_TIBCOHUB") or f"{TP_AUTO_CP_DNS_DOMAIN_PREFIX_TIBCOHUB}.{TP_AUTO_CP_DNS_DOMAIN}"
    TP_AUTO_FQDN_INFRA_MCP_SERVER = os.environ.get("TP_AUTO_FQDN_INFRA_MCP_SERVER") or f"{TP_AUTO_CP_DNS_DOMAIN_PREFIX_INFRA_MCP_SERVER}.{TP_AUTO_CP_DNS_DOMAIN}"
    TP_AUTO_FQDN_SPRINGBOOT = os.environ.get("TP_AUTO_FQDN_SPRINGBOOT") or f"{TP_AUTO_CP_DNS_DOMAIN_PREFIX_SPRINGBOOT}.{TP_AUTO_CP_DNS_DOMAIN}"

    # capabilities url
    TP_AUTO_EMS_CAPABILITY_SERVER_NAME = os.environ.get("TP_AUTO_EMS_CAPABILITY_SERVER_NAME") or "ems-sn"
    TP_AUTO_PULSAR_CAPABILITY_SERVER_NAME = os.environ.get("TP_AUTO_PULSAR_CAPABILITY_SERVER_NAME") or "pulsar-sn"
    TP_AUTO_TIBCOHUB_CAPABILITY_HUB_NAME = os.environ.get("TP_AUTO_TIBCOHUB_CAPABILITY_HUB_NAME") or "tibco-hub"

    # hybrid connectivity
    TP_AUTO_ENABLE_HYBRID_CONNECTIVITY = os.environ.get("TP_AUTO_ENABLE_HYBRID_CONNECTIVITY", "true").lower() == "true"
    # No-tibtunnel (hybrid disabled) reachability: the CP reaches the DP via tp-dp-proxy -> Reachable DP URL.
    # When managing reachability (default), the automation creates a controller-adaptive ingress in the DP
    # namespace (Option A, public host). When TP_AUTO_DP_APPLY_NETPOL_LABELS is set, it instead labels the
    # cpdpproxy/tp-dp-proxy deployments so tp-dp-proxy can reach the cpdpproxy ClusterIP directly (Option B,
    # private svc URL). Either path can be skipped with TP_AUTO_DP_MANAGE_REACHABILITY=false.
    TP_AUTO_DP_MANAGE_REACHABILITY = os.environ.get("TP_AUTO_DP_MANAGE_REACHABILITY", "true").lower() == "true"
    TP_AUTO_DP_APPLY_NETPOL_LABELS = os.environ.get("TP_AUTO_DP_APPLY_NETPOL_LABELS", "false").lower() == "true"
    TP_AUTO_DP_PROXY_SERVICE_NAME = os.environ.get("TP_AUTO_DP_PROXY_SERVICE_NAME") or "cpdpproxy"
    TP_AUTO_DP_PROXY_SERVICE_PORT = os.environ.get("TP_AUTO_DP_PROXY_SERVICE_PORT") or "80"
    # CP-side dp-proxy deployment that caches DP connection-details; restarted after registration
    # so it re-reads the reachable URL instead of dialing the stale svc address.
    TP_AUTO_CP_DP_PROXY_DEPLOYMENT = os.environ.get("TP_AUTO_CP_DP_PROXY_DEPLOYMENT") or "tp-dp-proxy"
    # Public host is used ONLY for no-tibtunnel Option A: reachability management ON, hybrid OFF,
    # and not applying netpol labels — i.e. exactly the case where the automation creates the public
    # cpdpproxy ingress. When management is OFF (no ingress is created), hybrid is ON (default), or
    # Option B is selected, keep the in-cluster cpdpproxy svc URL — preserving the pre-existing
    # default so a hybrid-ON (or unmanaged) DP/BMDP registration is unchanged. The BMDP "Reachable
    # DP URL" field is filled on visibility (not hybrid-gated), so this guard matters for the BMDP
    # create flow under hybrid-ON. An explicit override always wins.
    _reachable_public = TP_AUTO_DP_MANAGE_REACHABILITY and not TP_AUTO_ENABLE_HYBRID_CONNECTIVITY and not TP_AUTO_DP_APPLY_NETPOL_LABELS
    TP_AUTO_REACHABLE_DP_URL = os.environ.get("TP_AUTO_REACHABLE_DP_URL") or (
        f"https://dp-{TP_AUTO_K8S_DP_NAME}.{TP_AUTO_CP_DNS_DOMAIN}" if _reachable_public
        else f"http://cpdpproxy.{TP_AUTO_K8S_DP_NAMESPACE}.svc.cluster.local"
    )
    TP_AUTO_REACHABLE_BMDP_URL = os.environ.get("TP_AUTO_REACHABLE_BMDP_URL") or (
        f"https://dp-{TP_AUTO_K8S_BMDP_NAME}.{TP_AUTO_CP_DNS_DOMAIN}" if _reachable_public
        else f"http://cpdpproxy.{TP_AUTO_K8S_BMDP_NAMESPACE}.svc.cluster.local"
    )

    # data plane config
    TP_AUTO_DATA_PLANE_O11Y_SYSTEM_CONFIG = os.environ.get("TP_AUTO_DATA_PLANE_O11Y_SYSTEM_CONFIG", "false").lower() == "true"
    TP_AUTO_INGRESS_OBJECT = os.environ.get("TP_AUTO_INGRESS_OBJECT") or "ingress"
    TP_AUTO_INGRESS_CONTROLLER = os.environ.get("TP_AUTO_INGRESS_CONTROLLER") or "traefik"
    TP_AUTO_INGRESS_CONTROLLER_CLASS_NAME = os.environ.get("TP_AUTO_INGRESS_CONTROLLER_CLASS_NAME") or "traefik"
    TP_AUTO_INGRESS_CONTROLLER_BWCE = os.environ.get("TP_AUTO_INGRESS_CONTROLLER_BWCE") or f"{TP_AUTO_INGRESS_CONTROLLER}-{TP_AUTO_CP_DNS_DOMAIN_PREFIX_BWCE}"
    TP_AUTO_INGRESS_CONTROLLER_BW5CE = os.environ.get("TP_AUTO_INGRESS_CONTROLLER_BW5CE") or f"{TP_AUTO_INGRESS_CONTROLLER}-{TP_AUTO_CP_DNS_DOMAIN_PREFIX_BW5CE}"
    TP_AUTO_INGRESS_CONTROLLER_FLOGO = os.environ.get("TP_AUTO_INGRESS_CONTROLLER_FLOGO") or f"{TP_AUTO_INGRESS_CONTROLLER}-{TP_AUTO_CP_DNS_DOMAIN_PREFIX_FLOGO}"
    TP_AUTO_INGRESS_CONTROLLER_TIBCOHUB = os.environ.get("TP_AUTO_INGRESS_CONTROLLER_TIBCOHUB") or f"{TP_AUTO_INGRESS_CONTROLLER}-{TP_AUTO_CP_DNS_DOMAIN_PREFIX_TIBCOHUB}"
    TP_AUTO_INGRESS_CONTROLLER_INFRA_MCP_SERVER = os.environ.get("TP_AUTO_INGRESS_CONTROLLER_INFRA_MCP_SERVER") or f"{TP_AUTO_INGRESS_CONTROLLER}-{TP_AUTO_CP_DNS_DOMAIN_PREFIX_INFRA_MCP_SERVER}"
    TP_AUTO_INGRESS_CONTROLLER_SPRINGBOOT = os.environ.get("TP_AUTO_INGRESS_CONTROLLER_SPRINGBOOT") or f"{TP_AUTO_INGRESS_CONTROLLER}-{TP_AUTO_CP_DNS_DOMAIN_PREFIX_SPRINGBOOT}"
    # TP_AUTO_INGRESS_CONTROLLER_KEYS = os.environ.get("TP_AUTO_INGRESS_CONTROLLER_KEYS") or ""
    # TP_AUTO_INGRESS_CONTROLLER_VALUES = os.environ.get("TP_AUTO_INGRESS_CONTROLLER_VALUES") or ""
    # gateway API config
    TP_AUTO_GATEWAY_CONTROLLER = os.environ.get("TP_AUTO_GATEWAY_CONTROLLER") or "nginx"
    TP_AUTO_GATEWAY_NAME = os.environ.get("TP_AUTO_GATEWAY_NAME") or "nginx-gateway"
    TP_AUTO_GATEWAY_NAMESPACE = os.environ.get("TP_AUTO_GATEWAY_NAMESPACE") or "ingress-system"
    TP_AUTO_GATEWAY_SECTION_NAME = os.environ.get("TP_AUTO_GATEWAY_SECTION_NAME") or ""
    TP_AUTO_GATEWAY_CONTROLLER_BWCE = os.environ.get("TP_AUTO_GATEWAY_CONTROLLER_BWCE") or f"{TP_AUTO_GATEWAY_CONTROLLER}-{TP_AUTO_CP_DNS_DOMAIN_PREFIX_BWCE}"
    TP_AUTO_GATEWAY_CONTROLLER_BW5CE = os.environ.get("TP_AUTO_GATEWAY_CONTROLLER_BW5CE") or f"{TP_AUTO_GATEWAY_CONTROLLER}-{TP_AUTO_CP_DNS_DOMAIN_PREFIX_BW5CE}"
    TP_AUTO_GATEWAY_CONTROLLER_FLOGO = os.environ.get("TP_AUTO_GATEWAY_CONTROLLER_FLOGO") or f"{TP_AUTO_GATEWAY_CONTROLLER}-{TP_AUTO_CP_DNS_DOMAIN_PREFIX_FLOGO}"
    TP_AUTO_GATEWAY_CONTROLLER_TIBCOHUB = os.environ.get("TP_AUTO_GATEWAY_CONTROLLER_TIBCOHUB") or f"{TP_AUTO_GATEWAY_CONTROLLER}-{TP_AUTO_CP_DNS_DOMAIN_PREFIX_TIBCOHUB}"
    TP_AUTO_GATEWAY_CONTROLLER_SPRINGBOOT = os.environ.get("TP_AUTO_GATEWAY_CONTROLLER_SPRINGBOOT") or f"{TP_AUTO_GATEWAY_CONTROLLER}-{TP_AUTO_CP_DNS_DOMAIN_PREFIX_SPRINGBOOT}"
    TP_AUTO_STORAGE_CLASS = os.environ.get("TP_AUTO_STORAGE_CLASS") or Helper.get_storage_class()
    # Due to the fuzzy matching of the dp name by Playwright
    # At most 0-9 dp are supported, if more dp is needed, the matching rule of dp selector is required
    TP_AUTO_MAX_DATA_PLANE = 9

    # apps: bwce, bw5ce, flogo
    BWCE_APP_FILE_NAME = os.environ.get("TP_AUTO_BWCE_APP_FILE_NAME") or "rest-bwce-1.ear"
    BWCE_APP_PAYLOAD_JSON = os.environ.get("TP_AUTO_BWCE_APP_PAYLOAD_JSON") or "bwce-payload.json"
    BWCE_APP_NAME = os.environ.get("BWCE_APP_NAME") or BWCE_APP_FILE_NAME.removesuffix(".ear")
    BW5CE_APP_FILE_NAME = os.environ.get("TP_AUTO_BW5CE_APP_FILE_NAME") or "bw5ce-dynamicheaders.ear"
    BW5CE_APP_NAME = os.environ.get("BW5CE_APP_NAME") or BW5CE_APP_FILE_NAME.removesuffix(".ear").lower()
    FLOGO_APP_FILE_NAME = os.environ.get("TP_AUTO_FLOGO_APP_FILE_NAME") or "rest-flogo-1.json"
    # need to make sure the flogo app name is unique and lower case in the above JSON file
    FLOGO_APP_NAME = os.environ.get("FLOGO_APP_NAME") or Helper.get_app_name(FLOGO_APP_FILE_NAME)
    SPRINGBOOT_APP_FILE_NAME = os.environ.get("TP_AUTO_SPRINGBOOT_APP_FILE_NAME") or "sb-observability-metrics-app-1.0.0.jar"
    SPRINGBOOT_APP_NAME = os.environ.get("SPRINGBOOT_APP_NAME") or "sb-observability-metrics-app"

    def pre_check(self):
        current_time = self.RETRY_TIME.strftime("%Y-%m-%d %H:%M:%S")
        ColorLogger.info(f"Current Retry time at '{current_time}'")
        ColorLogger.info(f"Current CP version is '{self.TP_AUTO_CP_VERSION}'")
        ColorLogger.info(f"Headless mode is {self.IS_HEADLESS}")
        ColorLogger.info(f"CLI mode is {self.TP_AUTO_USE_CLI}")
        if not self.TP_AUTO_CP_VERSION:
            ColorLogger.warning("CP version GUI_TP_AUTO_CP_VERSION is not set")
        if not self.TP_AUTO_IS_CREATE_DP:
            ColorLogger.warning(f"TP_AUTO_IS_CREATE_DP is false, will not create Data Plane")
        if not self.TP_AUTO_IS_CONFIG_O11Y:
            ColorLogger.warning(f"TP_AUTO_IS_CONFIG_O11Y is false, will not config Data Plane o11y")
        if not self.TP_AUTO_IS_PROVISION_AS:
            ColorLogger.warning(f"TP_AUTO_IS_PROVISION_AS is false, will not provision ActiveSpaces capability")
        if not self.TP_AUTO_IS_PROVISION_BWCE:
            ColorLogger.warning(f"TP_AUTO_IS_PROVISION_BWCE is false, will not provision BWCE capability")
        if not self.TP_AUTO_IS_PROVISION_BW5CE:
            ColorLogger.warning(f"TP_AUTO_IS_PROVISION_BW5CE is false, will not provision BW5CE capability")
        if not self.TP_AUTO_IS_PROVISION_EMS:
            ColorLogger.warning(f"TP_AUTO_IS_PROVISION_EMS is false, will not provision EMS capability")
        if not self.TP_AUTO_IS_PROVISION_FLOGO:
            ColorLogger.warning(f"TP_AUTO_IS_PROVISION_FLOGO is false, will not provision Flogo capability")
        if not self.TP_AUTO_IS_PROVISION_PULSAR:
            ColorLogger.warning(f"TP_AUTO_IS_PROVISION_PULSAR is false, will not provision Pulsar capability")
        if not self.TP_AUTO_IS_PROVISION_TIBCOHUB:
            ColorLogger.warning(f"TP_AUTO_IS_PROVISION_TIBCOHUB is false, will not provision TibcoHub capability")
        if not self.TP_AUTO_IS_PROVISION_INFRA_MCP_SERVER:
            ColorLogger.warning(f"TP_AUTO_IS_PROVISION_INFRA_MCP_SERVER is false, will not provision Infra MCP Server capability")
        if not self.TP_AUTO_IS_PROVISION_SPRINGBOOT:
            ColorLogger.warning(f"TP_AUTO_IS_PROVISION_SPRINGBOOT is false, will not provision Spring Boot capability")

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

        if self.TP_ACTIVATION_ZIP_FILE_BASE64:
            activation_file = Helper.get_file_fullpath_in_upload_folder(self.TP_ACTIVATION_FILENAME)
            if os.path.isfile(activation_file):
                ColorLogger.info(f"Activation file '{self.TP_ACTIVATION_FILENAME}' already exists in {activation_file}.")
            elif Helper.save_activation_file(self.TP_ACTIVATION_ZIP_FILE_BASE64, f"{activation_file}.zip"):
                ColorLogger.info(f"Saved activation file to '{activation_file}'.")
            else:
                ColorLogger.error("Failed to save activation file from base64 string.")

    def check_capabilities_require_dataplane(self):
        """Report the capability flags that are on while this run creates no Data Plane.

        EnvConfig declares no annotated dataclass fields, so every TP_AUTO_IS_PROVISION_* flag
        is a plain class attribute and vars(type(self)) enumerates them.

        TP_AI_ENABLE_MCP_HUB is not covered and does not need to be: it does not match
        TP_AUTO_IS_PROVISION_*, so this reflection structurally cannot see it, and deploy-mcp-hub
        runs case/k8s_deploy_mcp_hub.py against an already registered Data Plane rather than this
        file. The recipe pre-flight leaves it alone for the same reason - see
        _OUT_OF_SCOPE_PROVISION_FLAGS (2) for the identical Infra MCP Server case.

        Returns the findings, it does not log fatally or exit - the caller decides how to die.
        """
        provision_flags = {
            name: value for name, value in vars(type(self)).items()
            if name.startswith(_PROVISION_FLAG_PREFIX)
        }
        return unsatisfiable_capabilities(self.TP_AUTO_IS_CREATE_DP, provision_flags)

ENV = EnvConfig()
