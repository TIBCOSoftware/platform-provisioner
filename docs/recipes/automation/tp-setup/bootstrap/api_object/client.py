#
# Copyright 2025 Cloud Software Group, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Minimal Bearer-token HTTP client for the CP `/cp/v1/*` Console REST API."""

import json
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class ConsoleApiError(RuntimeError):
    def __init__(self, method, url, status, body):
        super().__init__(f"{method} {url} -> HTTP {status}: {body[:500]}")
        self.status = status
        self.body = body


class ConsoleApiClient:
    def __init__(self, base_url, bearer_token, timeout=30, verify=False):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        self.session.verify = verify
        self.timeout = timeout

    def _request(self, method, path, **kwargs):
        url = self.base_url + path
        r = self.session.request(method, url, timeout=self.timeout, **kwargs)
        if r.status_code >= 400:
            raise ConsoleApiError(method, url, r.status_code, r.text)
        if not r.content:
            return None
        try:
            return r.json()
        except ValueError:
            return r.text

    def get(self, path, params=None):
        return self._request("GET", path, params=params)

    def post(self, path, payload):
        return self._request("POST", path, data=json.dumps(payload))

    def put(self, path, payload):
        return self._request("PUT", path, data=json.dumps(payload))

    def delete(self, path):
        return self._request("DELETE", path)

    @staticmethod
    def register_oauth_client(sub_url, iat, client_name, scope="TSC", verify=False, timeout=30):
        """POST {sub_url}/idm/v1/oauth2/clients (TIBCO private, form-urlencoded).

        Returns dict with client_id, client_secret. Raises on non-2xx.
        """
        url = f"{sub_url.rstrip('/')}/idm/v1/oauth2/clients"
        r = requests.post(
            url,
            data={
                "client_name": client_name,
                "scope": scope,
                "token_endpoint_auth_method": "client_secret_basic",
            },
            headers={
                "Authorization": f"Bearer {iat}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            verify=verify, timeout=timeout,
        )
        if r.status_code >= 400:
            raise ConsoleApiError("POST", url, r.status_code, r.text)
        return r.json()

    @staticmethod
    def exchange_client_credentials(sub_url, client_id, client_secret, scope="TSC", verify=False, timeout=30):
        """POST {sub_url}/idm/v1/oauth2/token (client_credentials, HTTP Basic).

        Returns access_token string. Raises on non-2xx.
        """
        url = f"{sub_url.rstrip('/')}/idm/v1/oauth2/token"
        r = requests.post(
            url,
            data={"grant_type": "client_credentials", "scope": scope},
            auth=(client_id, client_secret),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            verify=verify, timeout=timeout,
        )
        if r.status_code >= 400:
            raise ConsoleApiError("POST", url, r.status_code, r.text)
        return r.json()["access_token"]

    def whoami_subscription_id(self):
        """Return the subscription id (`gsbc`) used as `scopeId` for O11Y POSTs."""
        data = self.get("/cp/v1/whoami")
        sub_id = data.get("gsbc") or data.get("subscriptionId") or data.get("accountId")
        if not sub_id:
            raise RuntimeError(f"/cp/v1/whoami returned no subscription id: keys={list(data.keys())}")
        return sub_id

    def list_dataplanes(self):
        """Return all dataplanes as a list of `{id, name}` dicts.

        Uses the lightweight `/cp/api/v1/data-planes` summary endpoint.
        """
        resp = self.get("/cp/api/v1/data-planes")
        return (resp or {}).get("response") or []

    def resolve_dataplane_id(self, name):
        """Return the dp_id for the dataplane named `name`. Raises if not found."""
        for dp in self.list_dataplanes():
            if dp.get("name") == name:
                return dp["id"]
        raise RuntimeError(f"DataPlane '{name}' not found")

    @classmethod
    def from_auto_token(cls, base_url=None, **kwargs):
        """Build a client using the cluster `auto-token` secret.

        Reads the OAuth access_token stored by `ApiAuth.bootstrap_tenant_token()`
        and uses it as the Bearer credential. `base_url` defaults to the tenant
        CP host derived from ENV (`DP_HOST_PREFIX` + `TP_AUTO_CP_SERVICE_DNS_DOMAIN`).
        """
        from utils.env import ENV
        from utils.helper import Helper
        token = Helper.get_auto_token()
        if not token:
            raise RuntimeError(
                "auto-token secret not found in namespace 'automation'. "
                "Run ApiAuth.bootstrap_tenant_token() or the init-user task first."
            )
        if base_url is None:
            base_url = f"https://{ENV.DP_HOST_PREFIX}.{ENV.TP_AUTO_CP_SERVICE_DNS_DOMAIN}"
        return cls(base_url=base_url, bearer_token=token, **kwargs)
