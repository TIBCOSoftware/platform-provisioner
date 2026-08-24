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
# get_permissions() reads the CP's permission set and re-posts it with additions.
# The GET and the POST do NOT accept the same shape: CP returns dataplane-level
# roles carrying an instanceId, but rejects that instanceId on the way back in --
#
#   HTTP 400 PLATFORM-WS-001: "'instanceId' is not applicable for role 'PLATFORM_OPS'"
#
# while still requiring dataplaneId for the same role. Measured against a live
# control plane: keeping instanceId 400s; dropping instanceId AND dataplaneId 400s
# on the missing dataplaneId; keeping dataplaneId and dropping instanceId returns
# 200. CAPABILITY_ADMIN, CAPABILITY_USER and DEV_OPS all accept an instanceId.
#
# This matters for every real user the automation creates, because it always grants
# Data plane Manager (PLATFORM_OPS). It stayed hidden because the POST only fires
# when something actually needs adding -- once the grants exist, added == 0 and the
# method returns before it can fail.

from unittest.mock import MagicMock

from api_object.user_permission import ApiUserPermission, DATAPLANE_LEVEL_ROLES


def _api(get_response):
    client = MagicMock()
    client.get.return_value = get_response
    return ApiUserPermission(client), client


GET_RESPONSE = [
    # CP-level role: no instanceDetails at all
    {"roleId": "TEAM_ADMIN", "exclude": False, "instanceDetails": []},
    # dataplane-level role: CP hands it back WITH an instanceId it will not accept
    {
        "roleId": "PLATFORM_OPS",
        "exclude": False,
        "instanceDetails": [
            {"roleId": "PLATFORM_OPS", "exclude": False, "dataplaneId": "dp-1", "instanceId": "*"}
        ],
    },
    # instance-scoped role: the instanceId is meaningful and must survive
    {
        "roleId": "CAPABILITY_ADMIN",
        "exclude": False,
        "instanceDetails": [
            {"roleId": "CAPABILITY_ADMIN", "exclude": False, "dataplaneId": "dp-1", "instanceId": "bw5"}
        ],
    },
]


def _by_role(perms, role_id):
    return next(p for p in perms if p["roleId"] == role_id)


class TestDataplaneLevelRolesDropInstanceId:
    def test_platform_ops_is_returned_without_an_instance_id(self):
        api, _ = _api(GET_RESPONSE)

        entry = _by_role(api.get_permissions("cp-sub1@tibco.com"), "PLATFORM_OPS")

        assert "instanceId" not in entry, (
            "CP rejects the whole POST with \"'instanceId' is not applicable for role "
            "'PLATFORM_OPS'\", so it must be stripped when echoing the set back"
        )

    def test_platform_ops_keeps_its_dataplane_id(self):
        """Stripping the entry entirely is NOT a valid fix: CP then rejects the POST
        with "'dataplaneId' is required for dataplane-level role 'PLATFORM_OPS'"."""
        api, _ = _api(GET_RESPONSE)

        entry = _by_role(api.get_permissions("cp-sub1@tibco.com"), "PLATFORM_OPS")

        assert entry["dataplaneId"] == "dp-1"
        assert entry["roleId"] == "PLATFORM_OPS"

    def test_instance_scoped_roles_keep_their_instance_id(self):
        """The bug is specific to dataplane-level roles. A product grant is
        identified BY its instanceId, so dropping it there would silently turn every
        product permission into something else."""
        api, _ = _api(GET_RESPONSE)

        entry = _by_role(api.get_permissions("cp-sub1@tibco.com"), "CAPABILITY_ADMIN")

        assert entry["instanceId"] == "bw5"
        assert entry["dataplaneId"] == "dp-1"

    def test_cp_level_roles_are_unchanged(self):
        api, _ = _api(GET_RESPONSE)

        entry = _by_role(api.get_permissions("cp-sub1@tibco.com"), "TEAM_ADMIN")

        assert entry == {"roleId": "TEAM_ADMIN", "exclude": False}

    def test_every_returned_entry_is_postable(self):
        """Whole-set invariant: nothing may carry an instanceId for a dataplane-level
        role, because CP rejects the POST as a unit -- one bad entry fails them all.

        Deliberately hardcodes PLATFORM_OPS instead of iterating DATAPLANE_LEVEL_ROLES:
        keying the assertion off the same global the production code strips by would
        make this test pass vacuously the moment that set is emptied, which is exactly
        the regression it exists to catch.
        """
        api, _ = _api(GET_RESPONSE)
        perms = api.get_permissions("cp-sub1@tibco.com")

        assert any(p["roleId"] == "PLATFORM_OPS" for p in perms), "fixture must exercise the role"
        for entry in perms:
            if entry["roleId"] == "PLATFORM_OPS":
                assert "instanceId" not in entry
                assert entry.get("dataplaneId")

    def test_platform_ops_is_declared_dataplane_level(self):
        assert "PLATFORM_OPS" in DATAPLANE_LEVEL_ROLES


class TestGrantStillDedupes:
    def test_an_existing_product_grant_is_not_re_posted(self):
        """The dedupe must keep working after the strip: an already-granted product
        means added == 0 and no POST at all. This is also why the PLATFORM_OPS bug
        stayed hidden for so long -- the failing POST only fires when there is real
        work to do."""
        api, client = _api(GET_RESPONSE)
        api.resolve_user_id = MagicMock(return_value="user-1")
        client.resolve_dataplane_id.return_value = "dp-1"

        assert api.grant_product_permission("k8s-auto-bmdp1", "BW5") is True
        client.post.assert_not_called()
