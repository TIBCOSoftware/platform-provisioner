#
# Copyright 2025 Cloud Software Group, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""REST API client for EMS Server (Messaging) registration on a BMDP.

This wraps the `/msg/api/*` endpoints — a separate family from `/cp/v1/*` but
served from the same host with the same Bearer token. Each EMS server is
stored as a `MSGSERVER` resource_instance with `groupType="ems"`.

Endpoints (verified against CP 1.18):
- LIST:     GET    /msg/api/getServers?dp_id={dp}
- VALIDATE: POST   /msg/api/ems/register?test=true&dp_id={dp}
- CREATE:   POST   /msg/api/ems/register?test=false&dp_id={dp}
- DELETE:   DELETE /cp/v1/resource-instances?...&resourceInstanceId=...

`register_ems` is idempotent on `groupName`. `validate_ems` is a stateless
probe (no DB row created) — never skipped.
"""

from api_object.client import ConsoleApiClient
from utils.color_logger import ColorLogger


class BmdpEmsApi:
    def __init__(self, client: ConsoleApiClient):
        self.client = client

    # ----- low-level -----

    def list_servers(self, dp_id):
        """Return the list of MSGSERVER resource_instances on `dp_id`."""
        resp = self.client.get(f"/msg/api/getServers?dp_id={dp_id}")
        return resp or []

    def find_server(self, dp_id, group_name):
        """Return the resource_instance dict whose first field has the given
        `groupName`, or None."""
        for ri in self.list_servers(dp_id):
            fields = (ri.get("resource_instance_metadata") or {}).get("fields") or []
            for field in fields:
                if field.get("groupName") == group_name:
                    return ri
        return None

    def delete_server(self, dp_id, group_name=None, resource_instance_id=None):
        """Unregister an EMS server by groupName (looked up) or direct id."""
        if not resource_instance_id:
            if not group_name:
                raise ValueError("delete_server requires group_name or resource_instance_id")
            existing = self.find_server(dp_id, group_name)
            if not existing:
                ColorLogger.warning(
                    f"EMS server '{group_name}' not found on DP {dp_id}, nothing to delete"
                )
                return None
            resource_instance_id = existing["resource_instance_id"]
        return self.client.delete(
            f"/cp/v1/resource-instances"
            f"?scope=DATAPLANE&resourceInstanceId={resource_instance_id}&scopeId={dp_id}"
        )

    # ----- writes -----

    @staticmethod
    def _build_payload(dp_id, group_name, client_url, monitor_url, reg_user,
                       reg_pass, description, client_mtls, monitor_mtls):
        payload = {
            "groupName":        group_name,
            "description":      description,
            "groupType":        "ems",
            "clientUrl":        client_url,
            "monitorUrl":       monitor_url,
            "registrationUser": reg_user,
            "registrationPass": reg_pass,
            "dataplaneId":      dp_id,
        }
        if client_mtls is not None:
            payload["clientMtls"] = client_mtls
        if monitor_mtls is not None:
            payload["monitorMtls"] = monitor_mtls
        return payload

    def validate_ems(self, dp_id, group_name, client_url, monitor_url,
                     reg_user, reg_pass, description="",
                     client_mtls=None, monitor_mtls=None):
        """Probe-only registration (no DB write). Returns the API response."""
        payload = self._build_payload(dp_id, group_name, client_url, monitor_url,
                                       reg_user, reg_pass, description,
                                       client_mtls, monitor_mtls)
        return self.client.post(
            f"/msg/api/ems/register?test=true&dp_id={dp_id}", payload
        )

    def register_ems(self, dp_id, group_name, client_url, monitor_url,
                     reg_user, reg_pass, description="",
                     client_mtls=None, monitor_mtls=None):
        """Register an EMS server. Idempotent — returns existing
        resource_instance_id if a server with this groupName already exists."""
        existing = self.find_server(dp_id, group_name)
        if existing:
            ColorLogger.success(
                f"EMS server '{group_name}' already exists on DP {dp_id}, skipping"
            )
            return existing["resource_instance_id"]

        payload = self._build_payload(dp_id, group_name, client_url, monitor_url,
                                       reg_user, reg_pass, description,
                                       client_mtls, monitor_mtls)
        resp = self.client.post(
            f"/msg/api/ems/register?test=false&dp_id={dp_id}", payload
        )
        errors = (resp or {}).get("errors") or []
        if errors:
            raise RuntimeError(f"EMS register failed for '{group_name}': {errors}")
        # Response is {message, errors, ...} — no id field. Re-list to find the new id.
        created = self.find_server(dp_id, group_name)
        ri_id = created["resource_instance_id"] if created else None
        ColorLogger.success(f"EMS server '{group_name}' registered (id={ri_id})")
        return ri_id
