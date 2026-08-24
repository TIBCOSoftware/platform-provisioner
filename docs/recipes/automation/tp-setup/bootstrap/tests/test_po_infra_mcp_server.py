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
# PCP-20335 — contract smoke for the renamed Infra MCP Server page object.
# Guards the interdependent identifiers that the live CP web-UI selectors and
# the recipe/env wiring all rely on: the lowercase capability string
# ("inframcpserver"), its uppercase form (the derived select-button id
# "#INFRAMCPSERVER-capability-select-button"), the renamed provision method,
# and the renamed ENV attribute (with the old one fully gone).

import ast
import inspect

from page_object import po_dp_infra_mcp_server
from page_object.po_dp_infra_mcp_server import PageObjectDataPlaneInfraMcpServer
from utils.env import ENV


def _selector_literals(module):
    """Every string literal in the module — i.e. the selectors actually used at runtime.

    Asserting against raw source would also match explanatory comments (which legitimately
    name the ids this wizard does NOT have), so the checks below inspect literals only.
    """
    tree = ast.parse(inspect.getsource(module))
    return " | ".join(
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    )


class TestInfraMcpServerPageObjectContract:
    def test_capability_is_lowercase_inframcpserver(self):
        assert PageObjectDataPlaneInfraMcpServer.capability == "inframcpserver"

    def test_capability_upper_matches_select_button_token(self):
        # The select-button id is derived as f'#{self.capability.upper()}-...'.
        assert PageObjectDataPlaneInfraMcpServer.capability.upper() == "INFRAMCPSERVER"

    def test_select_button_id_is_derived_from_capability_not_hardcoded(self):
        # The check above is a str.upper() tautology — it never reads the real
        # selector source, so a hardcoded old id would still pass it. Inspect the
        # actual page-object source to prove the select-button id is *derived*
        # from self.capability (f'#{self.capability.upper()}-...'), not a literal,
        # and that the old K8SMCPSERVER token is fully gone from the source.
        src = inspect.getsource(po_dp_infra_mcp_server)
        assert "self.capability.upper()" in src, (
            "select-button id must be derived from self.capability.upper(), "
            "not a hardcoded literal"
        )
        assert "K8SMCPSERVER" not in src, (
            "residual old K8SMCPSERVER token found in page-object source"
        )

    def test_provision_method_renamed(self):
        assert hasattr(PageObjectDataPlaneInfraMcpServer, "infra_mcp_server_provision_capability")

    def test_old_provision_method_gone(self):
        # Symmetric negative (mirrors TestEnvRename new-present + old-gone): the
        # pre-rename method name must no longer exist on the page object.
        assert not hasattr(PageObjectDataPlaneInfraMcpServer, "k8s_mcp_server_provision_capability")

    def test_flow_has_no_k8s_mcp_resources_step(self):
        src = inspect.getsource(po_dp_infra_mcp_server)
        assert ".resources-content" not in src          # no K8s-MCP Resources step
        assert "resource-table" not in src              # no route/ingress radio-select
        assert "TP_AUTO_INGRESS_CONTROLLER_INFRA_MCP_SERVER" not in src
        assert "Capability Provision Request Completed" in src

    def test_flow_does_not_use_nonexistent_button_ids(self):
        # Ground-truthed against live CP 1.20: the Infra MCP wizard is the shared "fresco" modal
        # whose footer buttons have NO ids. The ids used by the other seven capabilities are
        # absent from this wizard's DOM, so waiting on them times out (the run-3 failure).
        lits = _selector_literals(po_dp_infra_mcp_server)
        assert "btnNextCapabilityProvision" not in lits
        assert "btnCapabilityProvision" not in lits
        assert ".resource-success" not in lits          # success title is a plain <h2>, not .resource-success
        assert "fresco-wizard-modal-footer-system-actions" in lits
        assert 'button:text-is("Next")' in lits
        assert 'button:text-is("Provision")' in lits

    def test_flow_accepts_required_eua_checkbox(self):
        # The EUA checkbox gates 'Next' via CSS (pointer-events: none) while reporting
        # disabled == false, so it must be clicked explicitly and must not be treated as optional.
        lits = _selector_literals(po_dp_infra_mcp_server)
        assert "End User Agreement" in lits
        assert 'input[type="checkbox"]' in lits
        assert ".resource-agree" not in lits            # that container does not exist in this wizard

    def test_flow_does_not_use_build_hashed_css_module_classes(self):
        # CSS-module class names (e.g. gcMB2pVADeQWYuXfKQ3X) change on every UI build; selectors
        # must stay anchored on text or stable component classes instead.
        src = inspect.getsource(po_dp_infra_mcp_server)
        for hashed in ("gcMB2pVADeQWYuXfKQ3X", "jj51uZ5S7UvL7be_GyIN", "fYzv6RKOGPTRvQPnB1QW"):
            assert hashed not in src


class TestEnvRename:
    def test_new_provision_flag_present(self):
        assert hasattr(ENV, "TP_AUTO_IS_PROVISION_INFRA_MCP_SERVER")

    def test_old_provision_flag_gone(self):
        assert not hasattr(ENV, "TP_AUTO_IS_PROVISION_K8S_MCP_SERVER")
