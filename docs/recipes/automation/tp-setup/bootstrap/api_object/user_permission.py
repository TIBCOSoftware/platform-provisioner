#
# Copyright 2025 Cloud Software Group, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Grant CP user permissions via the Console REST API (browser-free).

Replaces the Playwright "Assign Permissions" wizard
(`page_object/po_user_management.grant_product_permission`) for the CLI/API
path. The wizard's "Update" button POSTs the user's *entire* desired
permission set to `POST /cp/v1/users-permissions`; this module reproduces that
read-modify-write so no browser is needed.

Endpoints used (CP host `/cp/v1/*`, Bearer auth):
  - GET  /cp/v1/account/users?person={email}            -> userEntityId
  - GET  /cp/v1/accounts/user/permissions/{email}?contributing-resource=CP
                                                         -> current permissions
  - POST /cp/v1/users-permissions                        -> apply full set
"""

from urllib.parse import quote

from api_object.client import ConsoleApiClient
from utils.color_logger import ColorLogger
from utils.env import ENV


class ApiUserPermission:
    """Read-modify-write a CP user's permissions via /cp/v1/users-permissions."""

    def __init__(self, client: ConsoleApiClient):
        self.client = client

    # ----- discovery -----

    def resolve_user_id(self, email):
        """Return the userEntityId for `email`, or None if not found."""
        resp = self.client.get("/cp/v1/account/users", params={"person": email, "page": 1, "limit": 20})
        for user in (resp or {}).get("users", []):
            if user.get("email") == email:
                return user.get("userEntityId")
        return None

    def get_permissions(self, email):
        """Return the user's current permissions as a flat POST-format list.

        The GET response nests instance-scoped grants under `instanceDetails`;
        the POST body wants one flat entry per grant. CP-level roles (empty
        instanceDetails) become {roleId, exclude}; DP/instance-scoped roles
        become {roleId, exclude, dataplaneId, instanceId}.
        """
        resp = self.client.get(
            f"/cp/v1/accounts/user/permissions/{quote(email)}",
            params={"contributing-resource": "CP"},
        )
        perms = []
        for role in (resp or []):
            role_id = role.get("roleId")
            exclude = role.get("exclude", False)
            details = role.get("instanceDetails") or []
            if not details:
                perms.append({"roleId": role_id, "exclude": exclude})
            else:
                for detail in details:
                    perms.append({
                        "roleId": detail.get("roleId", role_id),
                        "exclude": detail.get("exclude", exclude),
                        "dataplaneId": detail.get("dataplaneId"),
                        "instanceId": detail.get("instanceId"),
                    })
        return perms

    # ----- grant -----

    def grant_product_permission(self, dp_name, capability, write=True, domain_ids=None, email=None):
        """Grant a user Product Permission on a capability of a data plane.

        Mirrors the GUI wizard path: Product Permission -> <dp_name> ->
        <capability> -> (all current and future domains | specific domains) ->
        Write/Read -> Update.

        Args:
            dp_name: DataPlane name (e.g. the BMDP name); resolved to its id.
            capability: product key shown on the card, e.g. "BW5"/"BW6". Maps to
                the payload `instanceId` (lower-cased).
            write: True -> CAPABILITY_ADMIN (Write); False -> CAPABILITY_USER (Read).
            domain_ids: optional list of domain resource-instance ids to scope to
                specific domains (`instanceId` "<capability>|<domainId>"). When
                None, grants on all current and future domains
                (`instanceId` "<capability>"), matching the wizard's
                "All current and future domains" checkbox.
            email: target user (defaults to ENV.DP_USER_EMAIL).

        Returns True on success (or when nothing needed changing), False on error.
        Idempotent: an already-present grant is left unchanged.
        """
        email = email or ENV.DP_USER_EMAIL
        ColorLogger.info(f"Granting Product Permission via API: {dp_name} => {capability} (write={write})")

        user_id = self.resolve_user_id(email)
        if not user_id:
            ColorLogger.error(f"Could not resolve userEntityId for '{email}', skipping product permission")
            return False

        try:
            dp_id = self.client.resolve_dataplane_id(dp_name)
        except Exception as e:
            ColorLogger.error(f"Could not resolve dataplane id for '{dp_name}': {e}")
            return False

        instance_key = capability.lower()
        role_id = "CAPABILITY_ADMIN" if write else "CAPABILITY_USER"
        targets = [instance_key] if not domain_ids else [f"{instance_key}|{domain_id}" for domain_id in domain_ids]

        perms = self.get_permissions(email)

        def _has(target_role, instance_id):
            return any(
                p.get("roleId") == target_role
                and p.get("dataplaneId") == dp_id
                and p.get("instanceId") == instance_id
                for p in perms
            )

        added = 0
        for instance_id in targets:
            if _has(role_id, instance_id):
                ColorLogger.success(f"Permission {role_id} on {dp_name}/{instance_id} already present")
                continue
            perms.append({"roleId": role_id, "exclude": False, "dataplaneId": dp_id, "instanceId": instance_id})
            added += 1

        if added == 0:
            return True

        payload = {"userIds": [user_id], "emails": [email], "permissions": perms}
        try:
            self.client.post("/cp/v1/users-permissions", payload)
            ColorLogger.success(
                f"Granted {role_id} to '{email}' on {dp_name} => {capability} ({added} new grant(s))"
            )
            return True
        except Exception as e:
            ColorLogger.error(f"Failed to POST /cp/v1/users-permissions for '{email}': {e}")
            return False
