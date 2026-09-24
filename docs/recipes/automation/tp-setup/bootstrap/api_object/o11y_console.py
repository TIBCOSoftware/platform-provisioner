#
# Copyright 2025 Cloud Software Group, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Global observability configuration via the internal Console API.

PUBLIC / STABLE — outcome verbs. Callers depend on these and on the read-back,
never on which endpoint gets used:

    ensure_pillars()            -> {resource_instance_name: instance_id}
    ensure_global_config()      -> stack_id
    link_to_global(dp_id)       -> bool
    unlink_from_global(dp_id)   -> bool
    is_linked_to_global(dp_id)  -> bool

WORKAROUND / UNSTABLE — PCP-21542. We do what the Console UI does, because the
public resource API cannot express this:

  * `POST /cp/api/v1/resources/instances/{type}` is MISSING resource models. The
    two AuditSafe types silently drop the log index whatever the spelling — see
    the note in api_object/resources.py::_build_payload. Through the Console API
    the same value persists, which is the whole reason pillar creation lives here.
  * `/cp/api/v1/data-planes/{id}/resource-association` refuses O11Y types, and
    tibcop's `link-resource-instance-to-dataplane` only accepts ACTIVATION_SERVER
    (checked on both the 1.9 and the 1.21 CLI). There is no public link at all.

When PCP-21542 lands, replace these THREE method bodies and delete nothing else:

    _create_pillar_via_console()      POST /cp/v1/resource-instances
    _create_stack_via_console()       POST /cp/v1/resource-instances
    _reprovision_o11y_capability()    PUT  /cp/v1/switch (+ capabilities-metadata)

Note that PCP-21542 as written only covers the first one. The stack-assembly and
link operations have no public equivalent even after it ships; retiring those two
needs its own enhancement request.

Everything here was verified against a live CP 1.21.0-alpha.129.
"""

import copy

from api_object.client import ConsoleApiClient
from api_object.resources import _WIZARD_RESOURCES, _backend_overrides
from utils.color_logger import ColorLogger
from utils.env import ENV
from utils.helper import o11y_log_index

# Grep target: this string is how a future maintainer finds every line that has
# to go when the public API is complete. The containment test asserts the three
# back-door endpoints appear in this module and nowhere else.
WORKAROUND_TICKET = "PCP-21542"

_STACK_RESOURCE_ID = "O11YV3"
_STACK_NAME = "Global Observability Config"
_METADATA_FIELD_KEY = "O11YV3 Resources"

# O11YV3 slot -> (pillar name suffix, kind). The stack references each pillar by
# INSTANCE ID; the suffix is only how we look that id up. Matching on the name and
# not on resource_id is deliberate: METRICS_PRX_PROM and METRICS_EXP_PROM each have
# TWO instances at subscription scope ("global-metrics-*" and "_system$metricsServer"),
# and the UI-built stack references the "global-*" ones. Keying on resource_id picks
# whichever came back last and silently points the stack at the wrong prometheus.
_PROXY_SLOTS = {
    "logsServerUserApps":  ("logs-qsqs-1",   "elasticSearch"),
    "logsServerAuditSafe": ("logs-qsbaqs-1", "elasticSearch"),
    "metricsServer":       ("metrics-qs-1",  "prometheus"),
    "tracesServer":        ("traces-qs-1",   "elasticSearch"),
}
_EXPORTER_SLOTS = {
    "logsServerUserApps":  ("logs-euae-1",        "elasticSearch"),
    "logsServerServices":  ("logs-ese-1",         "elasticSearch"),
    "logsServerAuditSafe": ("logs-ebae-1",        "elasticSearch"),
    "metricsServer":       ("metrics-exporter-1", "prometheus"),
    "tracesServer":        ("traces-exporter-1",  "elasticSearch"),
}
# The UI always sends these four as present-but-disabled. There is deliberately no
# auditSafe secondary — that slot does not exist in the CP resource definition.
_EXPORTER_SECONDARY = (
    "logsServerUserAppsSecondary",
    "logsServerServicesSecondary",
    "metricsServerSecondary",
    "tracesServerSecondary",
)
_EMPTY_SLOT = {"enabled": False, "instanceId": "", "kind": "", "scope": ""}

_O11Y_CAPABILITY_ID = "O11Y"
# `type=` in the switch query string is ignored by the server; the body's
# capabilityType is what decides. Both are sent, to match the UI byte for byte.
_CAPABILITY_TYPE_LINKED = "PLATFORM"
_CAPABILITY_TYPE_UNLINKED = "INFRA"

_SWITCH_TIMEOUT = 90  # observed 11.8-18.6 s; a 30 s default is not enough headroom


class O11yConsoleError(RuntimeError):
    """A Console-API o11y operation failed in a way the caller must not paper over."""


class O11yDataPlaneUnreachable(O11yConsoleError):
    """The CP<->DP tunnel is down (ATMOSPHERE-11002).

    Named separately so a caller can tell infrastructure (retry later, triage as
    infra) from a rejected payload (a bug in us). `/cp/v1/switch` answers 503 for
    the former, and ConsoleApiClient raises an undifferentiated ConsoleApiError.
    """


class O11yConsoleApi:
    """Assemble and attach the Global observability configuration."""

    def __init__(self, client: ConsoleApiClient, scope_id=None):
        self.client = client
        self._scope_id = scope_id
        self._registry = None

    # ----- shared reads -----

    @property
    def scope_id(self):
        if self._scope_id is None:
            self._scope_id = self.client.whoami_subscription_id()
        return self._scope_id

    def _details(self, resource_id, scope="SUBSCRIPTION", scope_id=None):
        """Own-scope rows for one resource type.

        `resource-instances-details`, NOT `resource-instances`: the latter silently
        ignores resourceId/resourceLevel and returns the inherited UNION, so it is
        unconditionally non-empty and an idempotency check built on it would always
        skip creation.

        A non-200 raises out of ConsoleApiClient. That is the point — a wrong scopeId
        answers 403, and swallowing it into an empty list would read as "does not
        exist" and create a duplicate.
        """
        resp = self.client.get(
            f"/cp/v1/resource-instances-details"
            f"?scope={scope}&scopeId={scope_id or self.scope_id}"
            f"&resourceLevel=PLATFORM&resourceId={resource_id}"
        )
        return (resp or {}).get("data") or []

    def _registry_template(self, resource_id):
        """The CP's own field template for a resource type, from GET /cp/v1/resources.

        MUST come from the registry, never from an existing instance: a stored
        instance reads its password back as TP1.<ciphertext>, and posting that back
        gets it encrypted a SECOND time (verified: 74 -> 140 bytes, different value).
        The result is a credential that looks valid and silently fails to
        authenticate. The registry template has the secret fields as null.
        """
        if self._registry is None:
            resp = self.client.get("/cp/v1/resources")
            self._registry = {r["resource_id"]: r for r in ((resp or {}).get("data") or [])}
        entry = self._registry.get(resource_id)
        if not entry:
            raise O11yConsoleError(f"resource type {resource_id!r} is not in /cp/v1/resources")
        return copy.deepcopy(entry.get("resource_metadata") or {})

    # ----- WORKAROUND (PCP-21542) -----

    def _create_pillar_via_console(self, resource_id, name, backend_key, log_index):
        """POST /cp/v1/resource-instances for one observability server."""
        endpoint, username, password = _backend_overrides(backend_key)
        metadata = self._registry_template(resource_id)
        for field in metadata.get("fields", []):
            value = field.get("value")
            if not isinstance(value, dict):
                continue
            for _kind, body in value.items():
                for leaf in (body or {}).get("fields", []):
                    key = leaf.get("key", "")
                    if key.endswith(".logIndex") and log_index is not None:
                        leaf["value"] = log_index
                    elif key.endswith(".endpoint"):
                        leaf["value"] = endpoint
                    elif key.endswith(".username"):
                        leaf["value"] = username
                    elif key.endswith(".password"):
                        # Plaintext on the wire; the server stores TP1.<ciphertext>.
                        leaf["value"] = password
                    elif key.endswith(".headers"):
                        # Registry leaves this null; the UI sends {}. Match the UI —
                        # null and {} render differently into the helm values.
                        leaf["value"] = {}
        resp = self.client.post("/cp/v1/resource-instances", {
            "resourceId": resource_id,
            "payload": {
                "region": "global",
                "resourceInstanceMetadata": metadata,
                "resourceInstanceName": name,
                "description": "",
                "resourceLevel": "PLATFORM",
                "scope": "SUBSCRIPTION",
                "scopeId": self.scope_id,
            },
        })
        instance_id = (resp or {}).get("resource_instance_id")
        if not instance_id:
            raise O11yConsoleError(f"create {resource_id} {name!r}: no resource_instance_id in {resp!r}")
        return instance_id

    def _create_stack_via_console(self, pillar_ids):
        """POST /cp/v1/resource-instances for the O11YV3 aggregate.

        Note the envelope differs from the UPDATE path: create is WRAPPED
        ({resourceId, payload}), update is flat with the target in the query string.
        Copying one shape onto the other fails.
        """
        def slot(suffix, kind):
            return {
                "instanceId": pillar_ids[suffix],
                "kind": kind,
                "scope": "SUBSCRIPTION",
                "enabled": True,
            }

        proxies = {s: slot(sfx, kind) for s, (sfx, kind) in _PROXY_SLOTS.items()}
        exporters = {s: slot(sfx, kind) for s, (sfx, kind) in _EXPORTER_SLOTS.items()}
        for name in _EXPORTER_SECONDARY:
            exporters[name] = dict(_EMPTY_SLOT)

        resp = self.client.post("/cp/v1/resource-instances", {
            "resourceId": _STACK_RESOURCE_ID,
            "payload": {
                "scope": "SUBSCRIPTION",
                "resourceLevel": "PLATFORM",
                "resourceInstanceName": _STACK_NAME,
                "resourceInstanceMetadata": {"fields": [{
                    "dataType": "",
                    "key": _METADATA_FIELD_KEY,
                    "name": _METADATA_FIELD_KEY,
                    "required": False,
                    "value": {"exporters": exporters, "proxies": proxies},
                }]},
                "scopeId": self.scope_id,
                "region": "global",
            },
        })
        stack_id = (resp or {}).get("resource_instance_id")
        if not stack_id:
            raise O11yConsoleError(f"create O11YV3 stack: no resource_instance_id in {resp!r}")
        return stack_id

    def _o11y_capability_payload(self, dp_id, capability_type, stack_id=None):
        """Build the /cp/v1/switch body from the CP's own capability package.

        Fetched per direction and per call, never cached across directions: the
        PLATFORM and INFRA recipes are DIFFERENT documents (PLATFORM carries the
        configured exporter switches, INFRA is the bare variant), and reusing one
        for the other pushes the wrong configuration. Never hardcoded either — the
        recipe pins six chart versions and would go stale on the next CP release.
        """
        resp = self.client.get(
            f"/cp/v1/capabilities-metadata"
            f"?capability-ids={_O11Y_CAPABILITY_ID}&capability-type={capability_type}"
        )
        rows = (resp or {}).get("data") or []
        if not rows:
            raise O11yConsoleError(
                f"capabilities-metadata returned no O11Y package for {capability_type}")
        package = (rows[0].get("package") or {}).get("package") or {}
        recipe = dict(package.get("recipe") or {})
        # The UI adds this empty constant; it is absent from the metadata response.
        recipe.setdefault("helmChartsCommon", {})

        body = {
            "recipe": recipe,
            "services": package.get("services"),
            "provisioningRoles": package.get("provisioningRoles"),
            "version": rows[0].get("version"),
            "capabilityType": capability_type,
            "dataPlaneId": dp_id,
        }
        # Presence of this key IS the link/unlink discriminator.
        if stack_id is not None:
            body["resourceInstanceDetails"] = {"scope": "SUBSCRIPTION", "instanceId": stack_id}
        return body

    def _reprovision_o11y_capability(self, dp_id, stack_id=None):
        """PUT /cp/v1/switch — re-provision the DP's O11Y capability.

        This is not a metadata write: it ships a ~66 KB rendered helm recipe through
        the tunnel and recycles the DP's o11y pods. Synchronous — every authoritative
        signal has settled by the time it returns, so the caller reads back once
        rather than polling.
        """
        capability_type = _CAPABILITY_TYPE_UNLINKED if stack_id is None else _CAPABILITY_TYPE_LINKED
        body = self._o11y_capability_payload(dp_id, capability_type, stack_id)
        try:
            return self.client.put(
                f"/cp/v1/switch?type={capability_type}&operation=UPDATE", body,
                timeout=_SWITCH_TIMEOUT,
            )
        except Exception as exc:
            # 503 ATMOSPHERE-11002 means the DP tunnel is severed — infrastructure,
            # not a bad payload. 403 here means a bad dataPlaneId, NOT a permission
            # problem, and reporting it as one sends triage down the wrong path.
            text = str(exc)
            if "ATMOSPHERE-11002" in text:
                raise O11yDataPlaneUnreachable(
                    f"data plane {dp_id} is not reachable from the control plane: {text}") from exc
            raise

    # ----- PUBLIC -----

    def ensure_pillars(self):
        """Create the 9 Global observability servers idempotently.

        Returns {resource_instance_name_suffix: instance_id} for every one of them,
        created or pre-existing, so the stack can reference them by id.
        """
        pillar_ids = {}
        for resource_id, suffix, _kind, backend_key, log_index_branch in _WIZARD_RESOURCES:
            name = "global-" + suffix
            existing = {r.get("resource_instance_name"): r.get("resource_instance_id")
                        for r in self._details(resource_id)}
            if name in existing:
                ColorLogger.success(f"O11Y {resource_id} '{name}' already exists, skipping")
                pillar_ids[suffix] = existing[name]
                continue
            log_index = (o11y_log_index(log_index_branch, ENV.TP_AUTO_DP_NAME_GLOBAL, name)
                         if log_index_branch else None)
            ColorLogger.info(f"O11Y POST {resource_id} '{name}'")
            pillar_ids[suffix] = self._create_pillar_via_console(
                resource_id, name, backend_key, log_index)
            ColorLogger.success(f"O11Y {resource_id} '{name}' created (id={pillar_ids[suffix]})")
        return pillar_ids

    def global_stack_id(self):
        """The O11YV3 stack id at subscription scope, or None.

        Matching is on resource_id, which the server already filters for us — NOT on
        the instance name. "Global Observability Config" is a GUI default string that
        appears nowhere in this repo; it is not an API invariant.

        More than one stack is an ambiguous state we refuse to guess our way out of.
        The CP happily allows duplicates (verified), so this is a real state, not a
        theoretical one, and picking [0] is how you end up linking data planes to
        different stacks.
        """
        rows = self._details(_STACK_RESOURCE_ID)
        if not rows:
            return None
        if len(rows) > 1:
            names = [r.get("resource_instance_name") for r in rows]
            raise O11yConsoleError(
                f"{len(rows)} O11YV3 stacks exist at subscription scope ({names}); "
                "refusing to guess which one data planes should link to")
        return rows[0].get("resource_instance_id")

    def ensure_global_config(self):
        """Create the Global observability stack idempotently. Returns its id."""
        existing = self.global_stack_id()
        if existing:
            ColorLogger.success(f"O11Y stack '{_STACK_NAME}' already exists (id={existing}), skipping")
            return existing
        pillar_ids = self.ensure_pillars()
        ColorLogger.info(f"O11Y POST O11YV3 stack '{_STACK_NAME}'")
        stack_id = self._create_stack_via_console(pillar_ids)
        ColorLogger.success(f"O11Y stack '{_STACK_NAME}' created (id={stack_id})")
        return stack_id

    def is_linked_to_global(self, dp_id, stack_id=None):
        """True when the data plane's O11Y capability references the Global stack.

        Reads `capability-instances`, whose resourceInstanceIds answer is INDEPENDENT
        of capabilityType. That matters: capabilityType is itself the link state
        (PLATFORM when linked, INFRA when not), so querying
        capability-instances-details with a fixed type is circular — it returns 0 for
        every unlinked data plane and reads as "no O11Y capability at all".

        Deliberately NOT /o11y/v1/dataplanes: hasO11yCfg and linkedDataPlanes there
        are cached ~120 s and were observed lying in both directions.
        """
        stack_id = stack_id or self.global_stack_id()
        if not stack_id:
            return False
        resp = self.client.get(
            f"/cp/v1/capability-instances"
            f"?capabilityId={_O11Y_CAPABILITY_ID}&dataPlaneId={dp_id}"
        )
        for instance in (resp or {}).get("capabilityInstances") or []:
            if stack_id in (instance.get("resourceInstanceIds") or []):
                return True
        return False

    def link_to_global(self, dp_id):
        """Point a data plane at the Global observability stack.

        Returns the READ-BACK, not the HTTP status: a 200 that did not change the
        state is a failure, and this area has regressed three times by reporting the
        call rather than the outcome.
        """
        stack_id = self.global_stack_id()
        if not stack_id:
            raise O11yConsoleError(
                "no Global observability stack exists; create it before linking a data plane")
        if self.is_linked_to_global(dp_id, stack_id):
            ColorLogger.success(f"O11Y data plane {dp_id} already linked to Global, skipping")
            return True
        ColorLogger.info(f"O11Y linking data plane {dp_id} to Global stack {stack_id}")
        self._reprovision_o11y_capability(dp_id, stack_id)
        linked = self.is_linked_to_global(dp_id, stack_id)
        if linked:
            ColorLogger.success(f"O11Y data plane {dp_id} linked to Global")
        else:
            ColorLogger.error(f"O11Y data plane {dp_id} still not linked after the switch call")
        return linked

    def unlink_from_global(self, dp_id):
        """Return a data plane to its unconfigured observability state.

        Verified to be an exact reset: the capability object comes back byte-identical
        to a never-configured one, only the helm revision counter advances. Guarded by
        a read because the call is not free — ~12 s and a full helm reconcile even
        when it is a no-op.
        """
        if not self.is_linked_to_global(dp_id):
            ColorLogger.success(f"O11Y data plane {dp_id} is not linked, nothing to unlink")
            return True
        ColorLogger.info(f"O11Y unlinking data plane {dp_id} from Global")
        self._reprovision_o11y_capability(dp_id, None)
        still_linked = self.is_linked_to_global(dp_id)
        if still_linked:
            ColorLogger.error(f"O11Y data plane {dp_id} is still linked after the unlink call")
        return not still_linked
