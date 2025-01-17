from dataclasses import dataclass
from color_logger import ColorLogger
from util import Util
import os

@dataclass
class EnvConfig:
    IS_HEADLESS = Util.is_headless()
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN") or ""
    DP_HOST_PREFIX = os.environ.get("DP_HOST_PREFIX") or "cp-sub1"
    DP_USER_EMAIL = os.environ.get("DP_USER_EMAIL") or "cp-sub1@tibco.com"
    DP_USER_PASSWORD = os.environ.get("DP_USER_PASSWORD") or "Tibco@123"
    CP_ADMIN_EMAIL = os.environ.get("CP_ADMIN_EMAIL") or "cp-test@tibco.com"
    CP_ADMIN_PASSWORD = os.environ.get("CP_ADMIN_PASSWORD") or "Tibco@123"

    TP_AUTO_CP_VERSION = os.environ.get("TP_AUTO_CP_VERSION") or "1.3"
    TP_AUTO_IS_CONFIG_O11Y = os.environ.get("TP_AUTO_IS_CONFIG_O11Y", "false").lower() == "true"

    # k8s data plane
    TP_AUTO_K8S_DP_NAME = os.environ.get("TP_AUTO_K8S_DP_NAME") or "k8s-auto-dp1"
    TP_AUTO_K8S_DP_NAMESPACE = os.environ.get("TP_AUTO_K8S_DP_NAMESPACE") or f"{TP_AUTO_K8S_DP_NAME}ns"
    TP_AUTO_K8S_DP_SERVICE_ACCOUNT = os.environ.get("TP_AUTO_K8S_DP_SERVICE_ACCOUNT") or f"{TP_AUTO_K8S_DP_NAME}sa"

    # CP_DNS_DOMAIN
    TP_AUTO_CP_INSTANCE_ID = os.environ.get("TP_AUTO_CP_INSTANCE_ID") or "cp1"
    TP_AUTO_CP_DNS_DOMAIN = os.environ.get("TP_AUTO_CP_DNS_DOMAIN") or "localhost.dataplanes.pro"
    TP_AUTO_CP_SERVICE_DNS_DOMAIN = os.environ.get("TP_AUTO_CP_SERVICE_DNS_DOMAIN") or f"{TP_AUTO_CP_INSTANCE_ID}-my.{TP_AUTO_CP_DNS_DOMAIN}"

    TP_AUTO_LOGIN_URL = os.environ.get("TP_AUTO_LOGIN_URL") or f"https://{DP_HOST_PREFIX}.{TP_AUTO_CP_SERVICE_DNS_DOMAIN}/cp/login"
    TP_AUTO_MAIL_URL = os.environ.get("TP_AUTO_MAIL_URL") or f"https://mail.{TP_AUTO_CP_DNS_DOMAIN}/#/"
    TP_AUTO_ADMIN_URL = os.environ.get("TP_AUTO_ADMIN_URL") or f"https://admin.{TP_AUTO_CP_SERVICE_DNS_DOMAIN}/admin/login"

    # elastic and prometheus
    TP_AUTO_ELASTIC_URL = os.environ.get("TP_AUTO_ELASTIC_URL") or f"https://elastic.{TP_AUTO_CP_DNS_DOMAIN}/"
    TP_AUTO_KIBANA_URL = f"https://kibana.{TP_AUTO_CP_DNS_DOMAIN}/"
    TP_AUTO_ELASTIC_USER = os.environ.get("TP_AUTO_ELASTIC_USER") or "elastic"
    TP_AUTO_ELASTIC_PASSWORD = os.environ.get("TP_AUTO_ELASTIC_PASSWORD") or Util.get_elastic_password()
    TP_AUTO_PROMETHEUS_URL = os.environ.get("TP_AUTO_PROMETHEUS_URL") or f"https://prometheus-internal.{TP_AUTO_CP_DNS_DOMAIN}/"
    TP_AUTO_PROMETHEUS_USER = os.environ.get("TP_AUTO_PROMETHEUS_USER") or ""
    TP_AUTO_PROMETHEUS_PASSWORD = os.environ.get("TP_AUTO_PROMETHEUS_PASSWORD") or ""

    # capabilities url
    TP_AUTO_FLOGO_CAPABILITY_URL = os.environ.get("TP_AUTO_FLOGO_CAPABILITY_URL") or f"flogo.{TP_AUTO_CP_DNS_DOMAIN}"

    # data plane config
    TP_AUTO_INGRESS_CONTROLLER = os.environ.get("TP_AUTO_INGRESS_CONTROLLER") or "nginx"
    TP_AUTO_STORAGE_CLASS = os.environ.get("TP_AUTO_STORAGE_CLASS") or Util.get_storage_class()
    # Due to the fuzzy matching of the dp name by Playwright
    # At most 0-9 dp are supported. If more dp are needed, the matching rule of dp selector is required
    TP_AUTO_MAX_DATA_PLANE = 9

    # flogo
    FLOGO_APP_FILE_NAME = "flogo.json"
    # need to make sure the flogo app name is unique and lower case in above json file
    FLOGO_APP_NAME = Util.get_app_name(FLOGO_APP_FILE_NAME)

    def pre_check(self):
        ColorLogger.info(f"Current CP version is '{self.TP_AUTO_CP_VERSION}'")
        ColorLogger.info(f"Headless mode is {self.IS_HEADLESS}")
        if not self.GITHUB_TOKEN:
            ColorLogger.warning(f"GITHUB_TOKEN is not set, DataPlane Helm Chart Repository Only support for 'Global Repository'.")
        if not self.TP_AUTO_IS_CONFIG_O11Y:
            ColorLogger.warning(f"TP_AUTO_IS_CONFIG_O11Y is false, will not config Data Plane o11y")
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
