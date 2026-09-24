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
"""Naming conventions the browser layer and the CLI layer must agree on.

Two questions live here, and each one has already cost a deploy when a second copy
of the answer disagreed with the first:

  * "what can this Data Plane's storage resource be called?" (PCP-23953)
  * "does this cell name THIS app, or one whose name merely starts the same way?"
    (PCP-24348, PCP-24359)

Why `utils/` and not `PageObjectDataPlane`, where both used to live: `cli_object`
now has to ask the same questions (PCP-24380 provisions EMS through tibcop), and
importing a page object to get them would drag Playwright into the CLI process --
`page_object.po_dataplane` imports `utils.util`, which does
`from playwright.sync_api import sync_playwright` at module scope. `utils/` is the
one package both layers already depend on (`utils.env`, `utils.color_logger`) and
it costs no browser. `utils/util.py` itself is disqualified for exactly the reason
above; a module with no Playwright import is the point, so keep it that way.
"""

import re

from utils.env import ENV


def storage_resource_candidates(dp_name):
    """The names a Data Plane's storage resource can have, most likely first.

    The name is NOT fixed - it depends on which mode provisioned the Data Plane:
      1. '<dp_name>-storage' - what CLI mode creates (cli_object/orchestrator.py), and
         what a resource provisioned with the Data Plane itself is called (observed
         live on CP 1.20/1.21: "k8s-auto-dp1-storage (<id>)").
      2. ENV.TP_AUTO_STORAGE_CLASS - what GUI mode names the resource it creates in
         po_dp_config.dp_config_resources_storage(); that is a Kubernetes StorageClass
         name ('nfs'), which is a different thing from the resource instance's name.

    Shared by every capability wizard that has to pick one - and, since PCP-24380, by
    the CLI EMS arm in cli_object/capability.py too - because the last time this
    knowledge lived in two places the second copy did not have it: ActiveSpaces already
    tried both conventions while the EMS fresco wizard knew only (2), so every
    TP_AUTO_USE_CLI=true deploy failed EMS provisioning deterministically (PCP-23953).
    A blank StorageClass is left out on purpose - callers build an alternation out of
    this list, and an empty alternative matches every row.
    """
    candidates = [f"{dp_name}-storage"]
    # .strip() before the truthiness test: a whitespace-only StorageClass is truthy and
    # would contribute an alternative of nothing but \s*, i.e. the same "matches every
    # row" hazard the blank guard exists to stop, only narrower. Helper.get_storage_class()
    # reads it off the cluster with awk, so blank and padded values are both reachable.
    storage_class = (ENV.TP_AUTO_STORAGE_CLASS or "").strip()
    if storage_class and storage_class not in candidates:
        candidates.append(storage_class)
    return candidates


def capability_instance_name_pattern(instance_name):
    """Anchored matcher for a capability instance's NAME, as a card or a table renders it.

    Playwright's `has_text` is a case-insensitive SUBSTRING match, so passing the
    bare name lets `rest-flogo-1` - the project default - match a `rest-flogo-10`
    row. Combined with a count()-based duplicate check that is worse than the strict
    mode error it replaces: a perfectly healthy Data Plane looks duplicated, the
    guard reports `rest-flogo-1` as already built when only `rest-flogo-10` exists,
    and `.first` can deploy the WRONG build. Anchoring at the start and refusing to
    let the next character continue the name closes it.

    Deliberately NOT anchored at the end. The cell renders the bare name today,
    but PCP-23953 had to walk back exactly this kind of both-ends anchor after it
    turned an unverifiable `<name> (<id>)` rendering into a failed deploy on a
    path nobody could test. Start-anchor + boundary keeps the `-1` vs `-10`
    protection without betting on what follows the name.

    The boundary excludes a DOT as well as word characters and hyphens (PCP-24359).
    `(?![\\w-])` alone let `rest-flogo-1` match a `rest-flogo-1.2` row - the same
    class of bug as `-1` vs `-10`, one character over. Unlike the `-10` case this was
    not settled by reading the regex: whether a dot can legally follow the name is a
    question about the live CP, so it was answered against one. On a real Data Plane
    (CP 1.21) an app whose Flogo JSON `name` is `rest-flogo-1.2` uploads cleanly, and
    the wizard's `#build-name` field takes it with no `pattern`, no `maxlength` and
    `checkValidity() == true`; the build is created and the App Builds table renders
    `rest-flogo-1.2` verbatim - ABOVE `rest-flogo-1`. So the old pattern matched two
    rows, the count()-based guard reported a duplicate that did not exist, and
    `.first` handed `flogo_app_deploy` the WRONG build to deploy.

    Excluding the dot is safe for every rendering this matcher is VERIFIED to accept
    (bare name, padded, and `<name> (<build id>)`) - each continues with a space or
    end-of-string. It is not a claim about every rendering that could ever exist: a
    cell truncated in JS to `rest-flogo-1...` would now stop matching. CSS
    `text-overflow: ellipsis` does not change `textContent` and a U+2026 `…` still
    matches, so this only bites if CP starts truncating in script - which it does not
    today. Note the boundary excludes `\\w`, `-` and `.` but not `:`.

    `IGNORECASE` because a *string* `has_text` is case-INSENSITIVE while a compiled
    pattern uses its own flags. Without it this change would have silently narrowed
    the match as well as anchoring it — `REST-FLOGO-1` used to match and would have
    stopped — which is a different behaviour change from the one intended, made in
    the one function whose whole job is to find the right row. Anchoring is the
    deliberate narrowing here; case is not.

    Named for the capability instance rather than the app build since PCP-24380: the
    EMS capability card renders the same way, so a Data Plane holding both `ems-sn` and
    `ems-sn-2` needs the same anchoring for a name check to pick the right card.

    Note what this does NOT buy on the EMS side, because an earlier revision of this
    docstring claimed it did. `po_dataplane.is_capability_provisioned` calls `is_visible()`
    on the OUTER `capability-card #ems` locator - un-narrowed, no name filter - before this
    pattern is applied. With two or more EMS servers that raises a strict-mode violation,
    the method's `except Exception` swallows it and it answers False, which
    `po_dp_ems.ems_verify_capability` turns into `Util.exit_error()`. Tested on a live CP
    1.21: one EMS card -> True, three -> False. Pre-existing and out of scope for
    PCP-24380. `app_build_name_pattern` remains as the Flogo-facing alias so that call site
    keeps reading in its own terms.
    """
    return re.compile(r"^\s*" + re.escape(instance_name) + r"(?![\w.-])", re.IGNORECASE)


# The App Builds table was the first caller and names the concept in its own terms;
# the pattern itself is capability-agnostic. One implementation, two readable names.
app_build_name_pattern = capability_instance_name_pattern
