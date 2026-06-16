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
"""Pure-API (no browser) admin bootstrap + CP subscription provisioning.

Mirrors `tp-helm-charts/scripts/api-samples` steps 1-4 + 7. Requires CP to be
installed with helm value `global.external.enable_api_based_initialization=true`
so the post-install hook only creates the Default-IdP admin user and leaves
the admin subscription un-provisioned for API bootstrap.

If admin UI is logged in before this runs, the chart-side branch flips and
`/platform-console/api/v1/init` returns 403 ATMOSPHERE-11006 — fail fast.
"""

import json
import uuid

import requests
import urllib3

from api_object.client import ConsoleApiClient
from utils.color_logger import ColorLogger
from utils.env import ENV
from utils.helper import Helper
from utils.report import ReportYaml

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ADMIN_CLIENT_SECRET = "cp-admin-oauth-client"
CP_IAT_SECRET = "cp-iat"
CP_OAUTH_CLIENT_SECRET = "cp-oauth-client"


class ApiAuthError(RuntimeError):
    pass


class ApiAuth:
    def __init__(self, admin_url=None, admin_email=None, admin_password=None, timeout=30, verify=False):
        self.admin_url = (admin_url or f"https://admin.{ENV.TP_AUTO_CP_SERVICE_DNS_DOMAIN}").rstrip("/")
        self.admin_email = admin_email or ENV.CP_ADMIN_EMAIL
        self.admin_password = admin_password or ENV.CP_ADMIN_PASSWORD
        self.timeout = timeout
        self.verify = verify
        self.ns = ENV.TP_AUTO_TOKEN_NAMESPACE

    # ----- admin bootstrap (api-samples steps 1-4) -----

    def bootstrap_admin(self, host_prefix="admin"):
        """Run Steps 1-4: init -> register client -> revoke IAT -> exchange token.

        Persists client_id/secret to k8s secret `cp-admin-oauth-client` for reuse.
        Returns admin access_token. Raises ApiAuthError on any non-2xx.
        """
        ColorLogger.info(f"Admin bootstrap via {self.admin_url}/platform-console/api/v1/init")
        init_body = {
            "externalAccountId": "admin",
            "externalSubscriptionId": "admin-sub",
            "firstName": "Admin",
            "lastName": "User",
            "email": self.admin_email,
            "organizationName": "TSC Admin Subscription",
            "hostPrefix": host_prefix,
            "prefixId": "tibc",
            "generateIAT": True,
            "tenantSubscriptionDetails": [{
                "eula": True, "region": "global", "expiryInMonths": -1,
                "planId": "TIB_CLD_ADMIN_TIB_CLOUDOPS", "tenantId": "ADMIN",
                "seats": {"ADMIN": {"ENGR": -1, "PM": -1, "SUPT": -1, "OPS": -1, "PROV": -1, "TSUPT": -1}},
            }],
            "skipEmail": True,
        }
        r = requests.post(f"{self.admin_url}/platform-console/api/v1/init",
                          json=init_body, auth=(self.admin_email, self.admin_password),
                          verify=self.verify, timeout=self.timeout)
        if r.status_code == 403 and "ATMOSPHERE-11006" in r.text:
            raise ApiAuthError(
                "Admin /init returned 403 ATMOSPHERE-11006. CP was likely installed without "
                "global.external.enable_api_based_initialization=true, or admin UI was already "
                "logged in (which disables API-based bootstrap)."
            )
        if r.status_code >= 400:
            raise ApiAuthError(f"Step 1 /init failed: {r.status_code} {r.text[:500]}")
        iat = (r.json().get("iat") or {}).get("accessToken")
        if not iat:
            raise ApiAuthError(f"Step 1 returned no IAT: {r.text[:500]}")

        client_name = f"admin-client-{uuid.uuid4().hex[:8]}"
        ColorLogger.info(f"Registering admin OAuth client '{client_name}'")
        r2 = requests.post(f"{self.admin_url}/idm/v1/oauth2/clients",
                           data={"client_name": client_name, "scope": "ADMIN",
                                 "token_endpoint_auth_method": "client_secret_basic"},
                           headers={"Authorization": f"Bearer {iat}",
                                    "Content-Type": "application/x-www-form-urlencoded"},
                           verify=self.verify, timeout=self.timeout)
        if r2.status_code >= 400:
            raise ApiAuthError(f"Step 2 register client failed: {r2.status_code} {r2.text[:500]}")
        client = r2.json()
        client_id, client_secret = client["client_id"], client["client_secret"]

        # Step 3: revoke IAT (best-effort; non-fatal)
        try:
            requests.delete(f"{self.admin_url}/idm/v1/oauth2/clients/initial-token",
                            headers={"Authorization": f"Bearer {iat}"},
                            verify=self.verify, timeout=self.timeout)
        except Exception as e:
            ColorLogger.warning(f"Step 3 IAT revoke failed (non-fatal): {e}")

        self._store_admin_client(client_id, client_secret)
        token = self._exchange_client_credentials(client_id, client_secret)
        ColorLogger.success("Admin token bootstrapped via API")
        return token

    def ensure_admin_token(self):
        """Reuse cached admin client_id/secret if present; else bootstrap."""
        client_id = Helper.get_command_output(
            f"kubectl get secret {ADMIN_CLIENT_SECRET} -n {self.ns} "
            f"-o jsonpath=\"{{.data['client-id']}}\" 2>/dev/null | base64 --decode"
        )
        client_secret = Helper.get_command_output(
            f"kubectl get secret {ADMIN_CLIENT_SECRET} -n {self.ns} "
            f"-o jsonpath=\"{{.data['client-secret']}}\" 2>/dev/null | base64 --decode"
        )
        if client_id and client_secret:
            try:
                token = self._exchange_client_credentials(client_id, client_secret)
                ColorLogger.success(f"Admin token from cached client ({ADMIN_CLIENT_SECRET})")
                return token
            except ApiAuthError as e:
                ColorLogger.warning(f"Cached admin client invalid ({e}); re-bootstrapping")
        return self.bootstrap_admin()

    def _exchange_client_credentials(self, client_id, client_secret):
        r = requests.post(f"{self.admin_url}/idm/v1/oauth2/token",
                          data={"grant_type": "client_credentials", "scope": "ADMIN"},
                          auth=(client_id, client_secret),
                          headers={"Content-Type": "application/x-www-form-urlencoded"},
                          verify=self.verify, timeout=self.timeout)
        if r.status_code >= 400:
            raise ApiAuthError(f"Token exchange failed: {r.status_code} {r.text[:300]}")
        return r.json()["access_token"]

    def _store_admin_client(self, client_id, client_secret):
        Helper.get_command_output(f"kubectl create namespace {self.ns} 2>/dev/null || true")
        Helper.get_command_output(f"kubectl delete secret {ADMIN_CLIENT_SECRET} -n {self.ns} 2>/dev/null || true")
        Helper.get_command_output(
            f"kubectl create secret generic {ADMIN_CLIENT_SECRET} -n {self.ns} "
            f"--from-literal=client-id='{client_id}' --from-literal=client-secret='{client_secret}' "
            f"--from-literal=admin-url='{self.admin_url}'"
        )
        ColorLogger.success(f"Admin client stored in secret {self.ns}/{ADMIN_CLIENT_SECRET}")

    # ----- CP subscription provisioning (api-samples step 7) -----

    def provision_cp_subscription(self, admin_token, email, host_prefix, password):
        """POST /platform-console/api/v1/subscriptions with admin Bearer.

        Sets `generateIAT=true` and `userRoles=["*"]` so the resulting CP IAT
        can bootstrap a full-permission OAuth client without UI grants.
        Persists CP IAT to k8s secret `cp-iat`. Idempotent on duplicate.
        """
        ColorLogger.info(f"Provision CP subscription email={email} host_prefix={host_prefix}")
        first_name = email.split("@")[0]
        payload = {
            "userDetails": {
                "firstName": first_name, "lastName": "Auto", "email": email,
                "initialPassword": password, "country": "US", "state": "TX",
            },
            "accountDetails": {
                "companyName": f"Tibco-{first_name}", "ownerLimit": 10,
                "hostPrefix": host_prefix,
                "comment": "Provisioned by automation via Admin API",
            },
            "generateIAT": True,
            "copyAdminIdP": False,
            "userRoles": ["*"],
            "useDefaultIDP": True,
            "customContainerRegistry": False,
        }
        r = requests.post(f"{self.admin_url}/platform-console/api/v1/subscriptions",
                          json=payload,
                          headers={"Authorization": f"Bearer {admin_token}",
                                   "Content-Type": "application/json"},
                          verify=self.verify, timeout=self.timeout)
        body_text = r.text
        try:
            parsed = r.json()
        except ValueError:
            parsed = {}

        if r.status_code in (200, 201) and parsed.get("status") != "error":
            ColorLogger.success(f"CP subscription {host_prefix} created")
            self._persist_cp_iat(parsed, host_prefix)
            return parsed
        if "already exists" in body_text.lower() or "duplicate" in body_text.lower():
            ColorLogger.warning(f"CP subscription {host_prefix} already exists — continuing")
            return parsed
        raise ApiAuthError(f"CP subscription provision failed: {r.status_code} {body_text[:500]}")

    def _persist_cp_iat(self, parsed, host_prefix):
        inner = parsed.get("response", {}) if isinstance(parsed, dict) else {}
        iat = (inner.get("iat") or {}).get("accessToken")
        sub_url = (inner.get("details", {}).get("provisioningDetails", {}) or {}).get("subscriptionUrl") or ""
        if not iat:
            ColorLogger.warning("CP subscription response missing IAT; downstream CLI bootstrap will fail")
            return
        if sub_url and not sub_url.startswith("http"):
            sub_url = f"https://{sub_url}"
        Helper.get_command_output(f"kubectl create namespace {self.ns} 2>/dev/null || true")
        Helper.get_command_output(f"kubectl delete secret {CP_IAT_SECRET} -n {self.ns} 2>/dev/null || true")
        Helper.get_command_output(
            f"kubectl create secret generic {CP_IAT_SECRET} -n {self.ns} "
            f"--from-literal=iat='{iat}' --from-literal=subscription-url='{sub_url}' "
            f"--from-literal=host-prefix='{host_prefix}'"
        )
        ColorLogger.success(f"CP IAT stored in secret {self.ns}/{CP_IAT_SECRET} (sub_url={sub_url})")

    # ----- top-level orchestrator -----

    def init_cp_user(self, email, host_prefix, password):
        """End-to-end: ensure admin token, then provision the CP subscription."""
        admin_token = self.ensure_admin_token()
        result = self.provision_cp_subscription(admin_token, email, host_prefix, password)
        # API path baked userRoles=["*"] into the subscription, so user is active
        # and fully permissioned without any GUI grant step.
        ReportYaml.set(".ENV.REPORT_AUTO_ACTIVE_USER", True)
        ReportYaml.set(".ENV.REPORT_USER_PERMISSION", True)
        return result

    # ----- tenant-side bootstrap (api-samples steps 8-9) -----

    @staticmethod
    def bootstrap_tenant_token():
        """Browser-free tenant OAuth token bootstrap.

        Reads the CP IAT captured by `provision_cp_subscription` and:
          1. If `cp-oauth-client` lacks a cached client_id/client_secret,
             registers a new OAuth client via the IAT (single-use).
          2. Exchanges client_credentials for an access_token.
          3. Stores the token in the `auto-token` secret consumed by tibcop
             and `Helper.get_auto_token()`.

        Writes REPORT_OAUTH_TOKEN and REPORT_OAUTH_TOKEN_SECRET to the report.
        Returns (token, sub_url).
        """
        ns = ENV.TP_AUTO_TOKEN_NAMESPACE

        iat = Helper.get_command_output(
            f"kubectl get secret {CP_IAT_SECRET} -n {ns} -o jsonpath=\"{{.data['iat']}}\" 2>/dev/null | base64 --decode"
        )
        sub_url = Helper.get_command_output(
            f"kubectl get secret {CP_IAT_SECRET} -n {ns} -o jsonpath=\"{{.data['subscription-url']}}\" 2>/dev/null | base64 --decode"
        )
        if not sub_url:
            sub_url = f"https://{ENV.DP_HOST_PREFIX}.{ENV.TP_AUTO_CP_SERVICE_DNS_DOMAIN}"

        client_id = Helper.get_command_output(
            f"kubectl get secret {CP_OAUTH_CLIENT_SECRET} -n {ns} -o jsonpath=\"{{.data['client-id']}}\" 2>/dev/null | base64 --decode"
        )
        client_secret = Helper.get_command_output(
            f"kubectl get secret {CP_OAUTH_CLIENT_SECRET} -n {ns} -o jsonpath=\"{{.data['client-secret']}}\" 2>/dev/null | base64 --decode"
        )

        if not (client_id and client_secret):
            if not iat:
                raise ApiAuthError(
                    f"No {CP_IAT_SECRET} secret found and no {CP_OAUTH_CLIENT_SECRET} cached. "
                    "Re-run init-user with TP_AUTO_USE_CLI=true to capture IAT."
                )
            client_name = f"auto-cli-{uuid.uuid4().hex[:8]}"
            ColorLogger.info(f"Registering OAuth client '{client_name}' at {sub_url} via IAT...")
            body = ConsoleApiClient.register_oauth_client(sub_url, iat, client_name)
            client_id = body["client_id"]
            client_secret = body["client_secret"]
            Helper.get_command_output(f"kubectl create namespace {ns} 2>/dev/null || true")
            Helper.get_command_output(f"kubectl delete secret {CP_OAUTH_CLIENT_SECRET} -n {ns} 2>/dev/null || true")
            Helper.get_command_output(
                f"kubectl create secret generic {CP_OAUTH_CLIENT_SECRET} -n {ns} "
                f"--from-literal=client-id='{client_id}' "
                f"--from-literal=client-secret='{client_secret}' "
                f"--from-literal=subscription-url='{sub_url}'"
            )
            ColorLogger.success(f"OAuth client stored in secret {ns}/{CP_OAUTH_CLIENT_SECRET}")

        ColorLogger.info(f"Exchanging client_credentials for access_token at {sub_url}...")
        token = ConsoleApiClient.exchange_client_credentials(sub_url, client_id, client_secret)

        name = ENV.TP_AUTO_TOKEN_NAME
        Helper.get_command_output(f"kubectl create namespace {ns} 2>/dev/null || true")
        Helper.get_command_output(f"kubectl delete secret {name} -n {ns} 2>/dev/null || true")
        Helper.get_command_output(
            f"kubectl create secret generic {name} -n {ns} --from-literal=auto-token='{token}'"
        )
        ColorLogger.success(f"OAuth token stored in secret {ns}/{name}")
        ReportYaml.set(".ENV.REPORT_OAUTH_TOKEN", True)
        ReportYaml.set(".ENV.REPORT_OAUTH_TOKEN_SECRET", f"{ns}/{name}")
        return token, sub_url

    @staticmethod
    def get_subscription_url():
        """Best-effort lookup of tenant CP base URL.

        Returns subscription-url from `cp-iat` secret if present, else None.
        """
        ns = ENV.TP_AUTO_TOKEN_NAMESPACE
        sub_url = Helper.get_command_output(
            f"kubectl get secret {CP_IAT_SECRET} -n {ns} -o jsonpath=\"{{.data['subscription-url']}}\" 2>/dev/null | base64 --decode"
        )
        return sub_url or None
