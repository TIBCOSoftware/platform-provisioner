#
# Copyright 2025 Cloud Software Group, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""REST API clients for CP and capability endpoints.

- `ConsoleApiClient` / `OllyApi`: CP host `/cp/v1/*` (Bearer auth, requests).
- `CpRestApi`: capability FQDNs (BWCE/BW5CE/FLOGO) via curl through TibcopBase.
- `CapabilityVersionApi`: capability / Flogo connector version lookup.
- `AppEndpointApi`: make app endpoint public and verify reachability.
"""

from api_object.client import ConsoleApiClient, ConsoleApiError
from api_object.resources import OllyApi, LicenseApi
from api_object.call_cp_rest_api import CpRestApi
from api_object.get_capability_version import CapabilityVersionApi
from api_object.test_app_endpoint import AppEndpointApi
from api_object.api_auth import ApiAuth, ApiAuthError
from api_object.bmdp_bw5 import BmdpBw5Api
from api_object.bmdp_bw6 import BmdpBw6Api
from api_object.bmdp_ems import BmdpEmsApi
from api_object.user_permission import ApiUserPermission

__all__ = [
    "ConsoleApiClient",
    "ConsoleApiError",
    "OllyApi",
    "LicenseApi",
    "CpRestApi",
    "CapabilityVersionApi",
    "AppEndpointApi",
    "ApiAuth",
    "ApiAuthError",
    "BmdpBw5Api",
    "BmdpBw6Api",
    "BmdpEmsApi",
]
