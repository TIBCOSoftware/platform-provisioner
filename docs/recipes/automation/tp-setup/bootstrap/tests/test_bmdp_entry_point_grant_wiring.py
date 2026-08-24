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
# Wiring guard: every BMDP browser entry point must actually CALL the proactive
# Product Permission grant. ensure_bmdp_product_permissions can be perfect and
# still ship a no-op if one of the three scripts that drive a BMDP never invokes
# it — and that failure only shows up as a disabled BW5/BW6 card much later, on a
# real instance.
#
# WHY THIS IS PINNED BY SOURCE TEXT, NOT BY IMPORT OR AST:
#   * Importing is impossible. These scripts have no importable entry function;
#     the whole flow is a top-level `if __name__ == "__main__":` body that calls
#     Util.browser_launch() / ENV.pre_check() / po_auth.login() the moment it
#     runs. There is nothing to import without launching a browser and logging
#     into a Control Plane.
#   * An AST walk would parse them fine, but buys nothing here: the body is
#     straight-line script code, so "the call exists, in this position relative
#     to these two other calls" is precisely a text fact. An AST version would be
#     ten times the code for the same guarantee.
# So: keep it COARSE — presence plus one ordering fact per file. Do NOT grow this
# into a line-by-line transcript of the scripts; that is what would make it churn
# on every unrelated edit and train reviewers to delete it.

import os

BOOTSTRAP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Dotted forms: these scripts discuss the same functions in their comments, and an
# ordering pin must key on the CALL, never on a mention of it.
ENSURE_CALL = ".ensure_bmdp_product_permissions("
SET_USER_PERMISSION = ".set_user_permission()"
GOTO_PRODUCTS = ".goto_products("


def _source(*parts):
    with open(os.path.join(BOOTSTRAP_DIR, *parts), encoding="utf-8") as f:
        return f.read()


def test_page_bmdp_grants_after_base_policies_and_before_any_product_card():
    """page_bmdp.py is the pipeline entry point. The grant has to sit AFTER
    set_user_permission() — the base CP/DP policies it creates are a prerequisite
    of any product grant — and BEFORE the first goto_products(), which is where a
    disabled product card would otherwise stall the capability flow."""
    src = _source("page_bmdp.py")

    assert ENSURE_CALL in src
    assert src.index(SET_USER_PERMISSION) < src.index(ENSURE_CALL) < src.index(GOTO_PRODUCTS)


def test_bmdp_create_dp_case_grants_after_base_policies():
    """case/bmdp_create_dp.py creates a BMDP and stops there, so this is the only
    chance it ever gets to leave the product grant behind."""
    src = _source("case", "bmdp_create_dp.py")

    assert ENSURE_CALL in src
    assert src.index(SET_USER_PERMISSION) < src.index(ENSURE_CALL)


def test_bmdp_provision_capability_case_grants_after_base_policies():
    """case/bmdp_provision_capability.py runs stand-alone against an EXISTING BMDP,
    so nothing before it has established the grant."""
    src = _source("case", "bmdp_provision_capability.py")

    assert ENSURE_CALL in src
    assert src.index(SET_USER_PERMISSION) < src.index(ENSURE_CALL)
