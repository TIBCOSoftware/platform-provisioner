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
# Make page_object unit tests hermetic and fast.
#
# Importing any page_object.* module pulls in utils.env, whose EnvConfig class
# body eagerly resolves cluster/CP facts AT IMPORT TIME by shelling out
# (Helper.get_command_output("kubectl cluster-info"), get_cp_version(),
# get_cp_dns_domain(), get_elastic_password(), get_storage_class()). On a box
# without a cluster that is slow and noisy; in CI it is non-deterministic. A
# monkeypatch inside a test body runs too late — the shell-out already happened
# at collection-time import. So we neutralize those autodetect entry points HERE,
# at conftest module load, which pytest executes before importing any test module
# (and therefore before any page_object import). utils.helper imports no project
# modules of its own, so importing it here does not trigger utils.env.

import utils.helper as _helper


def _quiet_autodetect(*_args, **_kwargs):
    """Stub for the kubectl-backed ENV autodetect calls — returns empty so the
    EnvConfig defaults fall back to their os.environ / literal defaults."""
    return ""


for _name in (
    "get_command_output",
    "get_cp_version",
    "get_cp_dns_domain",
    "get_elastic_password",
    "get_storage_class",
):
    setattr(_helper.Helper, _name, staticmethod(_quiet_autodetect))
