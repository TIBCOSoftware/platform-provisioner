#
# Copyright 2025 Cloud Software Group, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""REST API client for BW5 Domain registration on a BMDP (Control Tower).

Domains are stored as `HAWKDOMAIN` resource_instances. Each instance carries
the transport (`tibems` or `tibrv`) and its connection parameters under
`resource_instance_metadata.domains[0].regular`.

Endpoints (verified against CP 1.18):
- LIST:   GET    /cp/v1/resource-instances-details?...&resourceId=HAWKDOMAIN
- CREATE: PUT    /cp/v1/data-planes/{dp}/domains/{name}?new_domain=true
- DELETE: DELETE /cp/v1/data-planes/{dp}/domains/{name}

Idempotency: `add_*` methods skip when an existing entry with the same
`resource_instance_name` is already `REGISTERED`. Entries left in
`FAILED_TO_REGISTER` (or any other non-healthy status) are deleted and
recreated, since the backend keeps the row even on failed PUT.
"""

from api_object.client import ConsoleApiClient
from utils.color_logger import ColorLogger


_RESOURCE_ID = "HAWKDOMAIN"
_HEALTHY_STATUS = "REGISTERED"


class BmdpBw5Api:
    def __init__(self, client: ConsoleApiClient):
        self.client = client

    # ----- low-level -----

    def list_domains(self, dp_id):
        """Return the list of HAWKDOMAIN resource_instances on `dp_id`."""
        resp = self.client.get(
            f"/cp/v1/resource-instances-details"
            f"?scope=DATAPLANE&scopeId={dp_id}"
            f"&resourceLevel=PLATFORM&resourceId={_RESOURCE_ID}"
        )
        return (resp or {}).get("data") or []

    def find_domain(self, dp_id, name):
        """Return the resource_instance dict for `name`, or None."""
        for item in self.list_domains(dp_id):
            if item.get("resource_instance_name") == name:
                return item
        return None

    def delete_domain(self, dp_id, name):
        """Unregister a domain by name. Returns the API response dict."""
        return self.client.delete(f"/cp/v1/data-planes/{dp_id}/domains/{name}")

    # ----- internal create helpers -----

    @staticmethod
    def _domain_status(existing):
        domains = (existing.get("resource_instance_metadata") or {}).get("domains") or []
        return (domains[0] or {}).get("status") if domains else None

    def _ensure_clean_slot(self, dp_id, name):
        """If a stale (non-REGISTERED) row exists, delete it. Returns True if a
        new PUT should proceed, False if a healthy row already exists."""
        existing = self.find_domain(dp_id, name)
        if not existing:
            return True
        status = self._domain_status(existing)
        if status == _HEALTHY_STATUS:
            ColorLogger.success(
                f"BW5 domain '{name}' already {_HEALTHY_STATUS} on DP {dp_id}, skipping"
            )
            return False
        ColorLogger.warning(
            f"BW5 domain '{name}' has status={status!r}, deleting before re-create"
        )
        self.delete_domain(dp_id, name)
        return True

    def _put_domain(self, dp_id, name, regular):
        path = f"/cp/v1/data-planes/{dp_id}/domains/{name}?new_domain=true"
        body = {"domains": [{"regular": regular}]}
        resp = self.client.put(path, body)
        ColorLogger.success(f"BW5 domain '{name}' registered on DP {dp_id}")
        return resp

    # ----- high-level (idempotent) -----

    def add_ems_domain(self, dp_id, name, ems_server_url, ems_user, ems_password,
                       ssl_trusted="", ssl_private_key="", ssl_identity="", ssl_password=""):
        """Register a tibems-transport domain. Idempotent."""
        if not self._ensure_clean_slot(dp_id, name):
            return self.find_domain(dp_id, name)
        return self._put_domain(dp_id, name, {
            "domainName": name,
            "transport": "tibems",
            "tibems": {
                "emsServerUrl":    ems_server_url,
                "emsUserName":     ems_user,
                "emsPassword":     ems_password,
                "emsSslTrusted":   ssl_trusted,
                "emsSslPrivateKey": ssl_private_key,
                "emsSslIdentity":  ssl_identity,
                "emsSslPassword":  ssl_password,
            },
        })

    def add_rv_domain(self, dp_id, name, rv_service, rv_network, rv_daemon):
        """Register a tibrv-transport domain. Idempotent."""
        if not self._ensure_clean_slot(dp_id, name):
            return self.find_domain(dp_id, name)
        return self._put_domain(dp_id, name, {
            "domainName": name,
            "transport": "tibrv",
            "tibrv": {
                "rvService": rv_service,
                "rvNetwork": rv_network,
                "rvDaemon":  rv_daemon,
            },
        })
