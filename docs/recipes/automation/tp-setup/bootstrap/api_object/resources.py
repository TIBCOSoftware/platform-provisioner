#
# Copyright 2025 Cloud Software Group, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""REST API wrapper for TIBCO Platform resources.

Includes:
  - O11Y resources (observability: logs, metrics, traces)
  - License/activation file upload
"""

import json
import os
import subprocess
from api_object.client import ConsoleApiClient
from utils.color_logger import ColorLogger
from utils.env import ENV


# (resource_type, instance_name, backend_kind, backend_key)
#   backend_kind:
#     'es-log'        -> elasticSearchSchema (name, logIndex, endpoint, username, password)
#     'es-no-log'     -> elasticSearchSchemaNoLogIndex (name, endpoint, username, password)
#     'es-no-headers' -> elasticSearchSchemaNoLogIndexAndHeaders (name, endpoint, username, password)
#     'prom-exporter' -> resourceMetricsServerExporterPrometheusSchema (name only)
_WIZARD_RESOURCES = [
    ("LOGS_PRX_UA_ES",   "logs-qsqs-1",         "es-log",        "elastic"),
    ("LOGS_EXP_UA_ES",   "logs-euae-1",         "es-log",        "elastic"),
    ("LOGS_EXP_SRV_ES",  "logs-ese-1",          "es-log",        "elastic"),
    ("LOGS_PRX_AS_ES",   "logs-qsbaqs-1",       "es-log",        "elastic"),
    ("LOGS_EXP_AS_ES",   "logs-ebae-1",         "es-log",        "elastic"),
    ("METRICS_PRX_PROM", "metrics-qs-1",        "es-no-log",     "prometheus"),
    ("METRICS_EXP_PROM", "metrics-exporter-1",  "prom-exporter", None),
    ("TRACES_PRX_ES",    "traces-qs-1",         "es-no-headers", "elastic"),
    ("TRACES_EXP_ES",    "traces-exporter-1",   "es-no-headers", "elastic"),
]


def _backend_overrides(backend_key):
    if backend_key == "prometheus":
        return (ENV.TP_AUTO_PROMETHEUS_URL, ENV.TP_AUTO_PROMETHEUS_USER, ENV.TP_AUTO_PROMETHEUS_PASSWORD)
    if backend_key == "elastic":
        return (ENV.TP_AUTO_ELASTIC_URL, ENV.TP_AUTO_ELASTIC_USER, ENV.TP_AUTO_ELASTIC_PASSWORD)
    return (None, None, None)


def _build_payload(name, schema_kind, backend_key, log_index):
    endpoint, username, password = _backend_overrides(backend_key)
    if schema_kind == "prom-exporter":
        return {"name": name}
    body = {"name": name, "endpoint": endpoint}
    if username:
        body["username"] = username
    if password:
        body["password"] = password
    if schema_kind == "es-log":
        body["logIndex"] = log_index
    return body


class OllyApi:
    """Create the 9 O11Y wizard resources via the flat REST API.

    Supports both SUBSCRIPTION-scope (Global) and DATA-PLANE-scope
    creation. DP-scoped resources are implicitly bound to the DP at
    creation time (no separate link step needed — the dedicated link
    endpoint `/cp/api/v1/data-planes/{id}/resource-association` does
    not accept O11Y resource types).
    """

    def __init__(self, client: ConsoleApiClient):
        self.client = client

    # ----- path resolution -----

    def _resolve_dp(self, dp_id_or_name):
        """Resolve an id-or-name to (id, name). Raises if not found."""
        for dp in self.client.list_dataplanes():
            if dp.get("id") == dp_id_or_name or dp.get("name") == dp_id_or_name:
                return dp["id"], dp.get("name")
        raise ValueError(f"DataPlane '{dp_id_or_name}' not found")

    def _list_path(self, dp_id):
        if dp_id is None:
            return "/cp/api/v1/resources/instances?scope=SUBSCRIPTION&type={type}"
        return f"/cp/api/v1/data-planes/{dp_id}/resources/instances"

    def _create_path(self, dp_id, resource_type):
        if dp_id is None:
            return f"/cp/api/v1/resources/instances/{resource_type}"
        return f"/cp/api/v1/data-planes/{dp_id}/resources/instances/{resource_type}"

    # ----- low-level API -----

    def list_instances(self, resource_type, dp_id=None):
        if dp_id is None:
            resp = self.client.get(f"/cp/api/v1/resources/instances?scope=SUBSCRIPTION&type={resource_type}")
            items = (resp or {}).get("response") or (resp or {}).get("data") or []
        else:
            resp = self.client.get(f"/cp/api/v1/data-planes/{dp_id}/resources/instances")
            items = (resp or {}).get("response") or []
            # DP-scoped list returns all types — filter client-side.
            # Note: backend may return type='' for AS types (missing from spec discriminator).
            items = [i for i in items if i.get("type") in ("", resource_type)]
        return items

    def existing_by_name(self, resource_type, dp_id=None):
        return {i.get("name"): i.get("id") for i in self.list_instances(resource_type, dp_id)}

    def create_instance(self, resource_type, payload, dp_id=None):
        resp = self.client.post(self._create_path(dp_id, resource_type), payload)
        inner = (resp or {}).get("response") or {}
        return inner.get("resource_instance_id") or inner.get("id")

    # ----- high-level -----

    def create_o11y_resources(self, target="global"):
        """Create all 9 wizard resources idempotently.

        Args:
            target: 'global' for SUBSCRIPTION-scope creation, or a
                    DataPlane id / name for DP-scoped creation.

        Returns:
            {'created': [(type, name, id)], 'skipped': [(type, name, id)],
             'scope': 'SUBSCRIPTION' | 'DATA_PLANE',
             'dp_id': str | None}
        """
        if target == "global":
            dp_id = None
            scope_label = "SUBSCRIPTION"
            name_prefix = "global-"
            log_index = "global-log-index"
        else:
            dp_id, dp_name = self._resolve_dp(target)
            scope_label = "DATA_PLANE"
            name_prefix = f"{dp_name}-"
            log_index = f"{dp_name}-log-index"

        ColorLogger.info(f"O11Y creating resources at scope={scope_label} dp_id={dp_id}")
        created, skipped = [], []

        for resource_type, suffix, schema_kind, backend_key in _WIZARD_RESOURCES:
            name = name_prefix + suffix
            existing = self.existing_by_name(resource_type, dp_id)
            if name in existing:
                existing_id = existing[name]
                ColorLogger.success(f"O11Y {resource_type} '{name}' already exists (id={existing_id}), skipping")
                skipped.append((resource_type, name, existing_id))
                continue

            payload = _build_payload(name, schema_kind, backend_key, log_index)
            ColorLogger.info(f"O11Y POST {resource_type} '{name}'")
            new_id = self.create_instance(resource_type, payload, dp_id)
            ColorLogger.success(f"O11Y {resource_type} '{name}' created (id={new_id})")
            created.append((resource_type, name, new_id))

        ColorLogger.info(f"O11Y summary [{scope_label}]: created={len(created)}, skipped={len(skipped)}")
        return {"created": created, "skipped": skipped, "scope": scope_label, "dp_id": dp_id}


class LicenseApi:
    """Upload license/activation files via REST API."""

    def __init__(self, cp_url: str, token: str):
        self.cp_url = cp_url.rstrip("/")
        self.token = token

    def upload_license_file(self, file_path: str, dp_id=None):
        """Upload license/activation file via multipart form PUT.

        Args:
            file_path: Path to .bin or .zip license file
            dp_id: DataPlane ID for DP-scoped upload. If None, uploads to
                   subscription (global) scope.

        Returns:
            Response dict or None on error
        """
        if not os.path.isfile(file_path):
            ColorLogger.error(f"License file not found: {file_path}")
            return None

        if dp_id:
            endpoint = f"/cp/api/v1/data-planes/{dp_id}/license"
            scope = f"DataPlane {dp_id}"
        else:
            endpoint = "/cp/api/v1/subscription/license"
            scope = "SUBSCRIPTION"

        ColorLogger.info(f"Uploading license file to {scope}: {file_path}")

        curl_cmd = (
            f"curl -sk -X PUT '{self.cp_url}{endpoint}' "
            f"-H 'Authorization: Bearer {self.token}' "
            f"-F 'files=@\"{file_path}\"'"
        )
        try:
            result = subprocess.run(curl_cmd, shell=True, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                ColorLogger.error(f"License upload failed: {result.stderr}")
                return None
            return json.loads(result.stdout) if result.stdout.strip() else {"status": "ok"}
        except Exception as e:
            ColorLogger.error(f"License upload error: {e}")
            return None
