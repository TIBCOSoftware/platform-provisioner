#
# Copyright 2025 Cloud Software Group, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""REST API client for BW6 TEA Agent registration on a BMDP.

Adding an agent is a two-step write:
  1. POST /cp/v1/resource-instances             (create BW6TEAAGENT resource)
  2. POST /cp/v1/data-planes/{dp}/resource-instance?capability_instance_id={cap}
                                                (link it to the BWADAPTER capability)

Both steps need the BWADAPTER capability_instance_id, which is looked up via
/cp/v1/capability-instances-details. Before the create we probe the agent URL
with /agent-connection-status — its response yields `networkName / productName
/ productVersion` that the create payload requires.

Idempotency: if a BW6TEAAGENT resource with the same `resource_instance_name`
already exists on the DP, the existing id is returned and no create/link is
performed.
"""

from urllib.parse import quote

from api_object.client import ConsoleApiClient
from utils.color_logger import ColorLogger


_RESOURCE_ID = "BW6TEAAGENT"
_CAPABILITY_ID = "BWADAPTER"


class BmdpBw6Api:
    def __init__(self, client: ConsoleApiClient):
        self.client = client

    # ----- lookups -----

    def bwadapter_capability_instance_id(self, dp_id):
        """Return the BWADAPTER capability_instance_id provisioned on `dp_id`."""
        resp = self.client.get(
            f"/cp/v1/capability-instances-details"
            f"?dataPlaneId={dp_id}&capabilityId={_CAPABILITY_ID}"
        )
        rows = (resp or {}).get("data") or []
        if not rows:
            raise RuntimeError(
                f"{_CAPABILITY_ID} capability is not provisioned on DP {dp_id}"
            )
        return rows[0]["capability_instance_id"]

    def list_agents(self, dp_id):
        """Return the list of BW6TEAAGENT resource_instances on `dp_id`."""
        resp = self.client.get(
            f"/cp/v1/resource-instances-details"
            f"?scope=DATAPLANE&scopeId={dp_id}"
            f"&resourceLevel=PLATFORM&resourceId={_RESOURCE_ID}"
        )
        return (resp or {}).get("data") or []

    def find_agent(self, dp_id, name):
        for item in self.list_agents(dp_id):
            if item.get("resource_instance_name") == name:
                return item
        return None

    def test_connection(self, dp_id, agent_url, agent_name, cap_inst_id=None):
        """Probe the agent endpoint. Returns the agent's self-described metadata
        (`{id, name, version, agentInfo, protocol, ...}`)."""
        if cap_inst_id is None:
            cap_inst_id = self.bwadapter_capability_instance_id(dp_id)
        path = (
            f"/cp/v1/data-planes/{dp_id}/agent-connection-status"
            f"?url={quote(agent_url, safe='')}"
            f"&capability_instance_id={cap_inst_id}"
            f"&network_name={quote(agent_name, safe='')}"
        )
        return self.client.get(path)

    # ----- writes -----

    def add_agent(self, dp_id, name, agent_url, description=""):
        """Register a BW6 TEA agent. Idempotent — returns existing
        resource_instance_id if an agent with this name is already registered."""
        existing = self.find_agent(dp_id, name)
        if existing:
            ColorLogger.success(
                f"BW6 agent '{name}' already exists on DP {dp_id}, skipping"
            )
            return existing["resource_instance_id"]

        cap_inst_id = self.bwadapter_capability_instance_id(dp_id)
        probe = self.test_connection(dp_id, agent_url, name, cap_inst_id)
        network_name = probe.get("id")
        product_name = probe.get("name")
        product_version = probe.get("version")
        if not (network_name and product_name and product_version):
            raise RuntimeError(
                f"agent-connection-status probe returned incomplete metadata: {probe!r}"
            )

        create_resp = self.client.post("/cp/v1/resource-instances", {
            "resourceId": _RESOURCE_ID,
            "payload": {
                "region": "global",
                "resourceInstanceMetadata": {
                    "url":            agent_url,
                    "name":           name,
                    "networkName":    network_name,
                    "productName":    product_name,
                    "productVersion": product_version,
                    "description":    description,
                },
                "resourceInstanceName": name,
                "description":          description,
                "resourceLevel":        "PLATFORM",
                "scope":                "DATAPLANE",
                "scopeId":              dp_id,
            },
        })
        ri_id = (create_resp or {}).get("resource_instance_id")
        if not ri_id:
            raise RuntimeError(f"create BW6 agent: missing resource_instance_id in {create_resp!r}")

        self.client.post(
            f"/cp/v1/data-planes/{dp_id}/resource-instance"
            f"?capability_instance_id={cap_inst_id}",
            {"agentNetworks": {network_name: {
                "name":               name,
                "resourceInstanceId": ri_id,
                "url":                agent_url,
            }}},
        )
        ColorLogger.success(f"BW6 agent '{name}' registered (id={ri_id})")
        return ri_id

    def delete_agent(self, dp_id, name=None, resource_instance_id=None):
        """Unregister an agent by name (looked up) or by resource_instance_id."""
        if not resource_instance_id:
            if not name:
                raise ValueError("delete_agent requires name or resource_instance_id")
            existing = self.find_agent(dp_id, name)
            if not existing:
                ColorLogger.warning(f"BW6 agent '{name}' not found on DP {dp_id}, nothing to delete")
                return None
            resource_instance_id = existing["resource_instance_id"]
        return self.client.delete(
            f"/cp/v1/resource-instances"
            f"?scope=DATAPLANE&resourceInstanceId={resource_instance_id}&scopeId={dp_id}"
        )
