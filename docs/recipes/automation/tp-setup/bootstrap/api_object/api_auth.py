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

`/init` is NOT idempotent — it creates the account, and a second POST fails with
`host_prefix has been used in another account`. The caller (`run.sh`'s
`run-with-retry deploy-subscription`) re-runs the WHOLE step on failure, so every
piece of recoverable state is persisted to a k8s secret the moment it is obtained
and a retry resumes instead of restarting (PCP-23839).
"""

import json
import shlex
import time
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
ADMIN_IAT_SECRET = "cp-admin-iat"
CP_IAT_SECRET = "cp-iat"
CP_OAUTH_CLIENT_SECRET = "cp-oauth-client"

# Retries absorb a CP that is still warming up. In-process, so the IAT stays in hand —
# unlike the outer whole-step retry, which restarts from the non-idempotent /init.
ADMIN_CLIENT_REGISTER_ATTEMPTS = 3
ADMIN_CLIENT_REGISTER_BACKOFF = 10  # seconds
RETRYABLE_STATUSES = frozenset({408, 429})

# A busy cluster fails kubectl too, and these secrets ARE the resume state.
SECRET_WRITE_ATTEMPTS = 3
SECRET_WRITE_BACKOFF = 5

# The observed failure was a bare `TimeoutError`, not a wrapped ReadTimeout -> catch OSError.
TRANSPORT_ERRORS = (requests.exceptions.RequestException, OSError)


class ApiAuthError(RuntimeError):
    pass


class InconclusiveApiError(ApiAuthError):
    """Says NOTHING about whether the credentials are valid (transport / non-401-403).

    Treating one of these as "credentials are bad" sends `ensure_admin_token` back to
    the non-idempotent /init, turning a busy CP into an unrecoverable deploy.
    """


class ApiAuth:
    def __init__(self, admin_url=None, admin_email=None, admin_password=None, timeout=None, verify=False):
        self.admin_url = (admin_url or f"https://admin.{ENV.TP_AUTO_CP_SERVICE_DNS_DOMAIN}").rstrip("/")
        self.admin_email = admin_email or ENV.CP_ADMIN_EMAIL
        self.admin_password = admin_password or ENV.CP_ADMIN_PASSWORD
        # PCP-23839: default comes from TP_AUTO_API_TIMEOUT, not a hard-coded 30s.
        self.timeout = timeout or ENV.TP_AUTO_API_TIMEOUT
        self.verify = verify
        self.ns = ENV.TP_AUTO_TOKEN_NAMESPACE

    # ----- admin bootstrap (api-samples steps 1-4) -----

    def bootstrap_admin(self, host_prefix="admin"):
        """Run Steps 1-4: init -> register client -> revoke IAT -> exchange token.

        Resumable: each step persists what it produced BEFORE the next one can lose it,
        so a half-finished bootstrap picks up where it stopped instead of re-POSTing the
        non-idempotent /init (PCP-23839).

          1. /init            -> IAT      -> `cp-admin-iat`  (skipped when cached)
          2. register client  -> client   -> `cp-admin-oauth-client`
          3. revoke IAT + clear `cp-admin-iat`, but only once step 2 is confirmed stored
          4. exchange token

        Returns admin access_token. Raises ApiAuthError on any non-2xx.
        """
        iat = self._cached_admin_iat()
        iat_is_durable = bool(iat)
        if iat:
            ColorLogger.warning(
                f"Resuming admin bootstrap from the IAT cached in {self.ns}/{ADMIN_IAT_SECRET} "
                "- skipping /init (the account already exists)"
            )
        else:
            iat = self._init_admin_account(host_prefix)
            iat_is_durable = self._store_admin_iat(iat)
            if not iat_is_durable:
                # Not fatal - this attempt can still finish - but say what it costs.
                ColorLogger.warning(
                    f"CRITICAL: could not persist the admin IAT to {self.ns}/{ADMIN_IAT_SECRET}. "
                    "The account now exists, so if this attempt fails from here on NO retry "
                    "can recover it. Check kubectl access to the namespace."
                )

        client_id, client_secret = self._register_admin_client(iat)
        client_stored = self._store_admin_client(client_id, client_secret)

        if client_stored:
            try:  # step 3: revoke the now-superseded IAT (best-effort, non-fatal)
                requests.delete(f"{self.admin_url}/idm/v1/oauth2/clients/initial-token",
                                headers={"Authorization": f"Bearer {iat}"},
                                verify=self.verify, timeout=self.timeout)
            except Exception as e:
                ColorLogger.warning(f"Step 3 IAT revoke failed (non-fatal): {e}")
            self._delete_admin_iat()
        elif iat_is_durable:
            # An unverified client write leaves the IAT as the ONLY resume path, so neither
            # revoke nor delete it - a revoked IAT is as dead an end as a deleted one.
            ColorLogger.warning(
                f"Keeping (and not revoking) the cached IAT because {self.ns}/"
                f"{ADMIN_CLIENT_SECRET} could not be confirmed, so a retry can still resume."
            )
        else:
            ColorLogger.warning(
                f"CRITICAL: neither {self.ns}/{ADMIN_IAT_SECRET} nor {self.ns}/"
                f"{ADMIN_CLIENT_SECRET} could be persisted. If this attempt fails from here "
                "on there is nothing to resume from and the instance has to be rebuilt."
            )

        token = self._exchange_client_credentials(client_id, client_secret)
        ColorLogger.success("Admin token bootstrapped via API")
        return token

    def _init_admin_account(self, host_prefix):
        """Step 1: POST /init. NOT idempotent - it creates the account.

        A transport failure HERE is the one case no client-side code can recover (the
        account may or may not exist and no IAT came back); TP_AUTO_API_TIMEOUT is the
        only mitigation for it.
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
            raise ApiAuthError(self._init_failure_message(r))
        iat = (r.json().get("iat") or {}).get("accessToken")
        if not iat:
            raise ApiAuthError(f"Step 1 returned no IAT: {r.text[:500]}")
        return iat

    def _init_failure_message(self, response):
        """Turn the /init 400 into something actionable.

        `host_prefix has been used in another account` reads like a cross-environment
        conflict. It is not: each on-prem instance is its own cluster with its own CP,
        so the colliding account is the one THIS run created earlier.
        """
        detail = f"Step 1 /init failed: {response.status_code} {response.text[:500]}"
        if "host_prefix has been used" not in response.text:
            return detail
        return (
            f"{detail}\n"
            "The colliding account was created by THIS cluster's own admin bootstrap, and "
            f"the IAT it returned was lost before it reached {self.ns}/{ADMIN_IAT_SECRET}, "
            "so re-running /init cannot succeed. First check that secret really is absent "
            f"(`kubectl get secret {ADMIN_IAT_SECRET} -n {self.ns}`) — if it exists this was "
            "a transient read and a plain retry resumes. Otherwise recreate the instance, or "
            "re-run with TP_AUTO_USE_CLI=false to bootstrap through the browser path."
        )

    def _register_admin_client(self, iat):
        """Step 2: register the admin OAuth client, retried in-process.

        Fresh client_name per attempt: a read timeout may mean the server DID create the
        client, and reusing the name could then collide on a uniqueness constraint.
        """
        last_error = None
        for attempt in range(1, ADMIN_CLIENT_REGISTER_ATTEMPTS + 1):
            client_name = f"admin-client-{uuid.uuid4().hex[:8]}"
            ColorLogger.info(
                f"Registering admin OAuth client '{client_name}' "
                f"(attempt {attempt}/{ADMIN_CLIENT_REGISTER_ATTEMPTS})"
            )
            try:
                r = requests.post(f"{self.admin_url}/idm/v1/oauth2/clients",
                                  data={"client_name": client_name, "scope": "ADMIN",
                                        "token_endpoint_auth_method": "client_secret_basic"},
                                  headers={"Authorization": f"Bearer {iat}",
                                           "Content-Type": "application/x-www-form-urlencoded"},
                                  verify=self.verify, timeout=self.timeout)
            except TRANSPORT_ERRORS as e:
                last_error = f"{type(e).__name__}: {e}"
            else:
                if r.status_code < 400:
                    client = r.json()
                    return client["client_id"], client["client_secret"]
                if r.status_code in (401, 403):
                    raise ApiAuthError(
                        f"Step 2 register client rejected the IAT: {r.status_code} {r.text[:300]}. "
                        f"The IAT cached in {self.ns}/{ADMIN_IAT_SECRET} is stale or already "
                        "revoked; deleting it will NOT help, since /init cannot run again "
                        "against the existing account. Recreate the instance."
                    )
                if r.status_code < 500 and r.status_code not in RETRYABLE_STATUSES:
                    raise ApiAuthError(f"Step 2 register client failed: {r.status_code} {r.text[:500]}")
                last_error = f"{r.status_code} {r.text[:300]}"

            if attempt < ADMIN_CLIENT_REGISTER_ATTEMPTS:
                ColorLogger.warning(
                    f"Step 2 register client failed ({last_error}); "
                    f"retrying in {ADMIN_CLIENT_REGISTER_BACKOFF}s"
                )
                time.sleep(ADMIN_CLIENT_REGISTER_BACKOFF)

        raise ApiAuthError(
            f"Step 2 register client failed after {ADMIN_CLIENT_REGISTER_ATTEMPTS} "
            f"attempts: {last_error}"
        )

    def ensure_admin_token(self):
        """Reuse cached admin client_id/secret if present; else bootstrap."""
        client_id = self._read_secret(ADMIN_CLIENT_SECRET, "client-id")
        client_secret = self._read_secret(ADMIN_CLIENT_SECRET, "client-secret")
        if client_id and client_secret:
            try:
                token = self._exchange_client_credentials(client_id, client_secret)
                ColorLogger.success(f"Admin token from cached client ({ADMIN_CLIENT_SECRET})")
                return token
            except InconclusiveApiError as e:
                # Re-bootstrapping would run /init against an account that already exists
                # and fail permanently - an unrecoverable deploy manufactured out of a CP
                # that was merely busy. Only a definitive rejection (below) justifies that.
                raise ApiAuthError(
                    f"Admin token exchange failed for the cached client in {self.ns}/"
                    f"{ADMIN_CLIENT_SECRET}: {e}. NOT re-bootstrapping — /init cannot run "
                    "again against the existing account. Retry once the CP is responsive."
                )
            except ApiAuthError as e:
                ColorLogger.warning(f"Cached admin client invalid ({e}); re-bootstrapping")
        return self.bootstrap_admin()

    def _exchange_client_credentials(self, client_id, client_secret):
        """Exchange client_credentials for an access token.

        401/403 -> ApiAuthError (credentials really are bad); transport or any other
        status -> InconclusiveApiError, which `ensure_admin_token` must not re-bootstrap on.
        """
        try:
            r = requests.post(f"{self.admin_url}/idm/v1/oauth2/token",
                              data={"grant_type": "client_credentials", "scope": "ADMIN"},
                              auth=(client_id, client_secret),
                              headers={"Content-Type": "application/x-www-form-urlencoded"},
                              verify=self.verify, timeout=self.timeout)
        except TRANSPORT_ERRORS as e:
            raise InconclusiveApiError(f"Token exchange transport error: {type(e).__name__}: {e}")
        if r.status_code in (401, 403):
            raise ApiAuthError(
                f"Token exchange rejected the client credentials: {r.status_code} {r.text[:300]}"
            )
        if r.status_code >= 400:
            raise InconclusiveApiError(f"Token exchange failed: {r.status_code} {r.text[:300]}")
        return r.json()["access_token"]

    def _read_secret(self, name, key):
        return Helper.get_command_output(
            f"kubectl get secret {name} -n {self.ns} "
            f"-o jsonpath=\"{{.data['{key}']}}\" 2>/dev/null | base64 --decode"
        ) or ""

    def _store_secret(self, name, literals):
        """Write a k8s secret and CONFIRM every key landed, retrying a transient failure.

        Returns True only on a verified write, and callers MUST branch on it:
        `Helper.get_command_output` swallows a failed subprocess into `None`, so an
        unchecked write is indistinguishable from a successful one.

        `is_print_error=False` because that helper echoes the entire failed command,
        which would put the raw credential in the pipeline log.

        Values are shlex-quoted: the helper runs with `shell=True`, and `admin-url` here
        derives from an env var, so naive `'{v}'` interpolation is injectable.
        """
        args = " ".join(f"--from-literal={k}={shlex.quote(v)}" for k, v in literals.items())
        for attempt in range(1, SECRET_WRITE_ATTEMPTS + 1):
            Helper.get_command_output(f"kubectl create namespace {self.ns} 2>/dev/null || true")
            Helper.get_command_output(f"kubectl delete secret {name} -n {self.ns} 2>/dev/null || true")
            Helper.get_command_output(
                f"kubectl create secret generic {name} -n {self.ns} {args}", is_print_error=False
            )
            if all(self._read_secret(name, k) == v for k, v in literals.items()):
                return True
            if attempt < SECRET_WRITE_ATTEMPTS:
                ColorLogger.warning(
                    f"Secret {self.ns}/{name} did not persist (attempt {attempt}/"
                    f"{SECRET_WRITE_ATTEMPTS}); retrying in {SECRET_WRITE_BACKOFF}s"
                )
                time.sleep(SECRET_WRITE_BACKOFF)
        return False

    def _cached_admin_iat(self):
        """The IAT from a previous, half-finished bootstrap attempt.

        Scoped to `admin_url`, because a CP reinstalled in this cluster leaves the old
        secret behind and resuming with an IAT from a CP that no longer exists would fail
        at step 2 with advice that is wrong for that case.
        """
        iat = self._read_secret(ADMIN_IAT_SECRET, "iat")
        if not iat:
            return ""
        cached_url = self._read_secret(ADMIN_IAT_SECRET, "admin-url")
        if cached_url and cached_url != self.admin_url:
            ColorLogger.warning(
                f"Ignoring the IAT cached in {self.ns}/{ADMIN_IAT_SECRET}: it was issued for "
                f"{cached_url}, not {self.admin_url}"
            )
            return ""
        return iat

    def _store_admin_iat(self, iat):
        """Persist the /init IAT immediately, so a retry can skip /init."""
        if self._store_secret(ADMIN_IAT_SECRET, {"iat": iat, "admin-url": self.admin_url}):
            ColorLogger.success(
                f"Admin IAT stored in secret {self.ns}/{ADMIN_IAT_SECRET} (a retry can resume from here)"
            )
            return True
        return False

    def _delete_admin_iat(self):
        Helper.get_command_output(f"kubectl delete secret {ADMIN_IAT_SECRET} -n {self.ns} 2>/dev/null || true")

    def _store_admin_client(self, client_id, client_secret):
        """Persist the admin OAuth client. Verified — see `_store_secret`."""
        if self._store_secret(ADMIN_CLIENT_SECRET, {
            "client-id": client_id,
            "client-secret": client_secret,
            "admin-url": self.admin_url,
        }):
            ColorLogger.success(f"Admin client stored in secret {self.ns}/{ADMIN_CLIENT_SECRET}")
            return True
        ColorLogger.warning(f"Could not persist the admin client to {self.ns}/{ADMIN_CLIENT_SECRET}")
        return False

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
            f"--from-literal=iat={shlex.quote(iat)} "
            f"--from-literal=subscription-url={shlex.quote(sub_url)} "
            f"--from-literal=host-prefix={shlex.quote(host_prefix)}",
            is_print_error=False,
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
                f"--from-literal=client-id={shlex.quote(client_id)} "
                f"--from-literal=client-secret={shlex.quote(client_secret)} "
                f"--from-literal=subscription-url={shlex.quote(sub_url)}",
                is_print_error=False,
            )
            ColorLogger.success(f"OAuth client stored in secret {ns}/{CP_OAUTH_CLIENT_SECRET}")

        ColorLogger.info(f"Exchanging client_credentials for access_token at {sub_url}...")
        token = ConsoleApiClient.exchange_client_credentials(sub_url, client_id, client_secret)

        name = ENV.TP_AUTO_TOKEN_NAME
        Helper.get_command_output(f"kubectl create namespace {ns} 2>/dev/null || true")
        Helper.get_command_output(f"kubectl delete secret {name} -n {ns} 2>/dev/null || true")
        Helper.get_command_output(
            f"kubectl create secret generic {name} -n {ns} --from-literal=auto-token={shlex.quote(token)}",
            is_print_error=False,
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
