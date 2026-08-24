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
# Regression tests for PCP-22771 — a TP_AUTO_IS_CREATE_DP=false run died at the very end, in
# page_dp.py's epilogue (goto_left_navbar_dataplane / goto_dataplane / screenshot), navigating
# to a Data Plane that was never created.
# Repro: run generic-runner-gcp-98372901679-1785344080534 on instance dgidwani-pcp22651 —
# GUI_TP_AUTO_ENABLE_DP=false with a capability flag left on.
#
# Root cause, two halves: the epilogue sat outside the `if ENV.TP_AUTO_IS_CREATE_DP:` block,
# and the run should never have reached it at all — a capability is provisioned INSIDE a Data
# Plane, so enabling one while creating none can never be satisfied. The capability was
# silently skipped and the run only failed later, on an unrelated-looking navigation error.
#
# Fix: utils.env.unsatisfiable_capabilities() names every capability flag this run can never
# satisfy and page_dp.py fails fast on it before launching the browser (the epilogue itself
# just moved one indentation level in — a __main__ block, so not unit testable).
#
# Covered here is the PURE predicate only: no page_dp import, no monkeypatching, no browser.

from utils.env import unsatisfiable_capabilities

# The real TP_AUTO_IS_PROVISION_* attributes of EnvConfig, spelled out rather than reflected,
# so a rename shows up as a failing test instead of as a silently narrower guard. The predicate
# itself allowlists nothing — see the fail-closed tests below.
#
# In scope: every capability page_dp.py itself provisions (its capability blocks are Flogo,
# BWCE/BW5CE, EMS, Pulsar, TibcoHub, SpringBoot — page_dp.py:83-215).
_CAPABILITY_FLAGS = (
    "TP_AUTO_IS_PROVISION_BWCE",
    "TP_AUTO_IS_PROVISION_BW5CE",
    "TP_AUTO_IS_PROVISION_EMS",
    "TP_AUTO_IS_PROVISION_FLOGO",
    "TP_AUTO_IS_PROVISION_PULSAR",
    "TP_AUTO_IS_PROVISION_TIBCOHUB",
    "TP_AUTO_IS_PROVISION_SPRINGBOOT",
)
# Out of scope, for two different reasons — see _OUT_OF_SCOPE_PROVISION_FLAGS in utils/env.py.
_NON_CAPABILITY_FLAG = "TP_AUTO_IS_PROVISION_USER_WITHOUT_EMAIL"
_NOT_PAGE_DP_CAPABILITY_FLAG = "TP_AUTO_IS_PROVISION_INFRA_MCP_SERVER"
_OUT_OF_SCOPE_FLAGS = (_NON_CAPABILITY_FLAG, _NOT_PAGE_DP_CAPABILITY_FLAG)


def _flags(*enabled, **extra):
    """Every known TP_AUTO_IS_PROVISION_* flag off, except the ones named."""
    flags = {name: False for name in _CAPABILITY_FLAGS}
    flags.update({name: False for name in _OUT_OF_SCOPE_FLAGS})
    flags.update({name: True for name in enabled})
    flags.update(extra)
    return flags


class TestUnsatisfiableCapabilities:
    def test_creating_a_dataplane_is_always_satisfiable(self):
        # When the run creates the Data Plane, every capability can be satisfied — even with
        # all of them turned on.
        assert unsatisfiable_capabilities(True, _flags(*_CAPABILITY_FLAGS)) == []

    def test_single_enabled_capability_is_reported(self):
        found = unsatisfiable_capabilities(False, _flags("TP_AUTO_IS_PROVISION_FLOGO"))
        assert found == [{"flag": "TP_AUTO_IS_PROVISION_FLOGO", "setting": "GUI_TP_AUTO_ENABLE_FLOGO"}]

    def test_several_enabled_capabilities_are_all_reported(self):
        found = unsatisfiable_capabilities(False, _flags(
            "TP_AUTO_IS_PROVISION_BWCE", "TP_AUTO_IS_PROVISION_FLOGO", "TP_AUTO_IS_PROVISION_SPRINGBOOT"))
        # One row per offending flag, in a deterministic (sorted) order. Spring Boot also
        # exercises the override table: its GUI variable is GUI_TP_AUTO_ENABLE_SB.
        assert [f["setting"] for f in found] == [
            "GUI_TP_AUTO_ENABLE_BWCE", "GUI_TP_AUTO_ENABLE_FLOGO", "GUI_TP_AUTO_ENABLE_SB"]

    def test_no_capability_enabled_is_clean(self):
        assert unsatisfiable_capabilities(False, _flags()) == []

    def test_user_without_email_is_not_a_capability(self):
        # THE regression the denylist exists for. TP_AUTO_IS_PROVISION_USER_WITHOUT_EMAIL
        # matches the TP_AUTO_IS_PROVISION_* prefix but gates a user-creation mode, not a Data
        # Plane capability — and it defaults to true on both sides: the EnvConfig attribute in
        # utils/env.py and
        # charts/provisioner-config-local/recipes/tp-automation-o11y.yaml:178. Counting it
        # would make the guard refuse every legitimate CP-only run.
        assert unsatisfiable_capabilities(False, _flags(_NON_CAPABILITY_FLAG)) == []
        # ...and it must not mask a real capability enabled next to it.
        found = unsatisfiable_capabilities(False, _flags(_NON_CAPABILITY_FLAG, "TP_AUTO_IS_PROVISION_EMS"))
        assert [f["flag"] for f in found] == ["TP_AUTO_IS_PROVISION_EMS"]

    def test_infra_mcp_server_is_a_capability_page_dp_does_not_provision(self):
        # Regression pin. The Infra MCP Server IS a capability, but it is provisioned by
        # case/k8s_provision_infra_mcp_server.py against an already registered Data Plane — the
        # deploy-infra-mcp-server task runs that module, not page_dp.py, and page_dp.py is the only
        # caller of this guard. "The Data Plane already exists, now add the K8s MCP Server" is a
        # supported TP_AUTO_IS_CREATE_DP=false run; refusing on this flag broke it.
        assert unsatisfiable_capabilities(False, _flags(_NOT_PAGE_DP_CAPABILITY_FLAG)) == []
        # ...and it must not mask a capability page_dp.py really does provision.
        found = unsatisfiable_capabilities(
            False, _flags(_NOT_PAGE_DP_CAPABILITY_FLAG, "TP_AUTO_IS_PROVISION_FLOGO"))
        assert [f["flag"] for f in found] == ["TP_AUTO_IS_PROVISION_FLOGO"]

    def test_pulsar_stays_in_scope(self):
        # The counterpart to the exemption above: page_dp.py:193 does provision Pulsar, so its
        # flag must keep failing the run. Pins that the exemption set was not widened by reflex
        # to every capability with an unusual deploy path.
        found = unsatisfiable_capabilities(False, _flags("TP_AUTO_IS_PROVISION_PULSAR"))
        assert found == [{"flag": "TP_AUTO_IS_PROVISION_PULSAR", "setting": "TP_AUTO_IS_PROVISION_PULSAR"}]

    def test_a_capability_with_no_gui_variable_reports_its_raw_env_var(self):
        # Pulsar is the one page_dp.py capability with no GUI variable anywhere:
        # GUI_TP_AUTO_ENABLE_PULSAR is in no recipe, no Provisioner UI descriptor and not in
        # tp-install-on-prem.sh, and there is no TP_AUTO_ENABLE_PULSAR pipeline global either
        # (which is why the recipe pre-flight has no Pulsar row). The mechanical derivation would
        # invent that name and send the user looking for a knob that does not exist, so the
        # finding names the raw environment variable, which is the only way Pulsar is turned on.
        found = unsatisfiable_capabilities(False, _flags("TP_AUTO_IS_PROVISION_PULSAR"))
        assert found[0]["setting"] == "TP_AUTO_IS_PROVISION_PULSAR"
        assert "GUI_" not in found[0]["setting"]
        # ...and this is an exception, not the rule: its neighbours still report their GUI name.
        found = unsatisfiable_capabilities(
            False, _flags("TP_AUTO_IS_PROVISION_PULSAR", "TP_AUTO_IS_PROVISION_FLOGO"))
        assert [f["setting"] for f in found] == [
            "GUI_TP_AUTO_ENABLE_FLOGO", "TP_AUTO_IS_PROVISION_PULSAR"]


class TestFailsClosedOnNewCapabilities:
    def test_unknown_capability_is_reported_with_a_derived_gui_name(self):
        # A capability added tomorrow must be caught without touching this guard: nothing is
        # allowlisted, so an unseen flag is REPORTED rather than silently missed - that is the
        # load-bearing property here.
        #
        # The name it is reported under is the repo convention (TP_AUTO_IS_PROVISION_X ->
        # GUI_TP_AUTO_ENABLE_X), which every capability except Pulsar follows. A future
        # capability shipped without a GUI variable needs an entry in
        # _PROVISION_FLAGS_WITHOUT_GUI, exactly as Pulsar has - the guard still catches it
        # either way, only the name it prints would be a guess.
        found = unsatisfiable_capabilities(False, _flags(TP_AUTO_IS_PROVISION_NEWCAP=True))
        assert found == [{"flag": "TP_AUTO_IS_PROVISION_NEWCAP", "setting": "GUI_TP_AUTO_ENABLE_NEWCAP"}]

    def test_every_finding_carries_a_settable_name(self):
        # page_dp.py renders finding["setting"] to the user, so it must always be a name the
        # user can actually change: the GUI variable where there is one, the raw flag where
        # there is not. Empty, or a bare prefix, would make the remediation unactionable.
        found = unsatisfiable_capabilities(False, _flags(*_CAPABILITY_FLAGS, TP_AUTO_IS_PROVISION_NEWCAP=True))
        assert len(found) == len(_CAPABILITY_FLAGS) + 1
        for finding in found:
            setting = finding["setting"]
            assert setting, finding
            assert setting in (finding["flag"],) or setting.startswith("GUI_TP_AUTO_ENABLE_"), finding
            assert setting != "GUI_TP_AUTO_ENABLE_", finding
