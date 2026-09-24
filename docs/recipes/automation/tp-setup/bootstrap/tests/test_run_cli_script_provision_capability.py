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
# PCP-24380 — /run-cli-script's `provision-capability` case must map each request
# parameter onto its OWN tibcop flag.
#
# It did not. The case called provision_capability() with EIGHT positional values:
#
#     dp_name, capability_id, storage_resource_id, ingress_resource_id,
#     None, devhub_name, k8s_secret, other_args
#
# into a NINE-parameter signature (..., gateway_resource_id, path_prefix, devhub_name,
# k8s_secret, other_args, ...). From the fifth value on, everything landed one slot
# early: path_prefix=devhub_name, devhub_name=k8s_secret, k8s_secret=other_args, and
# other_args was dropped. TIBCOHUB provisioning from the Web UI had been mis-wired ever
# since gateway_resource_id was inserted into the middle of that signature — silently,
# because every value is a string and tibcop accepts all of them.
#
# The call is keyword-based now, and these tests are what stops the next signature edit
# from re-opening it. They are ROUTE-LEVEL on purpose: the EMS unit tests in
# test_capability_ems_provision.py call provision_capability() directly and therefore
# cannot see a wiring bug that lives in server.py. Here the real Flask route runs, builds
# the real TibcopCLI, and the command is asserted on the captured ARGV — what the child
# process actually receives — with subprocess.run monkeypatched so nothing executes. Same
# shape as tests/test_run_cli_script_injection.py, which owns the shell-safety contract of
# this endpoint; argument mapping is a separate concern and lives here.

import types

import pytest

import server
from cli_object.base import TibcopBase
from cli_object.capability import TibcopCapability
from cli_object.dataplane import TibcopDataPlane
from utils.env import ENV

DP = "k8s-auto-dp1"
BANNER = "@tibco/tp-cli/1.21.0 linux-x64 node-v20.11.1"


@pytest.fixture
def client():
    server.app.config.update(TESTING=True)
    return server.app.test_client()


@pytest.fixture
def argv_calls(monkeypatch):
    """Capture every tibcop argv the route issues; execute nothing."""
    calls = []

    def fake_run(cmd, *_args, **_kwargs):
        cmd = list(cmd)
        calls.append(cmd)
        # TibcopCLI.__init__ asserts the CLI version before anything else (PCP-24379).
        if "--version" in cmd:
            return types.SimpleNamespace(stdout=BANNER, stderr="", returncode=0)
        return types.SimpleNamespace(stdout="✔ done", stderr="", returncode=0)

    monkeypatch.setattr("cli_object.base.subprocess.run", fake_run)
    # get_version caches per cli_path on the class, so a value left by another module
    # would decide whether the route 503s here. Clear on both sides.
    TibcopBase._versions.clear()
    # Stub the two reads provision_capability makes BEFORE building its command (the
    # idempotency check and the DP id lookup) so the provision command is the only
    # tibcop invocation that reaches the sink.
    monkeypatch.setattr(TibcopCapability, "list_capabilities", lambda *_a, **_kw: "[]")
    monkeypatch.setattr(TibcopDataPlane, "get_dataplane_id", lambda _self, _dp: "dp-abc123")
    yield calls
    TibcopBase._versions.clear()


def _get(client, **params):
    """Drive the real HTTP route and drain the stream (which joins the worker thread)."""
    query = {"case": "provision-capability", "TIBCOP_CLI_DP_NAME": DP}
    query.update(params)
    response = client.get("/run-cli-script", query_string=query)
    body = response.get_data(as_text=True)
    assert response.status_code == 200, f"{response.status_code}: {body}"
    assert "[ERROR]" not in body, f"the worker thread raised: {body}"
    return body


def _provision_argv(calls):
    provisions = [c for c in calls if "tplatform:provision-capability" in c]
    assert len(provisions) == 1, f"expected exactly one provision command, got {provisions!r}"
    return provisions[0]


def _flag(argv, name):
    """The value of `--name` in an argv list, or None if the flag is absent."""
    return argv[argv.index(name) + 1] if name in argv else None


def test_each_tibcohub_request_value_reaches_its_own_flag(client, argv_calls):
    """The regression itself: four distinct request values, four distinct flags.

    Under the positional call the devhub flag carried the K8S_SECRET value and the
    secret flag carried OTHER_ARGS, so three of these assertions fail at once.
    """
    _get(client,
         TIBCOP_CLI_CAPABILITY_ID="TIBCOHUB",
         TIBCOP_CLI_STORAGE_RESOURCE_ID="storage-res-1",
         TIBCOP_CLI_INGRESS_RESOURCE_ID="ingress-res-1",
         TIBCOP_CLI_DEVHUB_NAME="my-devhub",
         TIBCOP_CLI_K8S_SECRET="my-k8s-secret",
         TIBCOP_CLI_OTHER_ARGS="--json --verbose")

    argv = _provision_argv(argv_calls)
    assert _flag(argv, "--dataplane-name") == DP
    assert _flag(argv, "--capability") == "TIBCOHUB"
    assert _flag(argv, "--storage-resource-instance-id") == "storage-res-1"
    assert _flag(argv, "--ingress-resource-instance-id") == "ingress-res-1"
    assert _flag(argv, "--developer-hub-name") == "my-devhub", (
        f"TIBCOP_CLI_DEVHUB_NAME must reach --developer-hub-name: {argv!r}")
    assert _flag(argv, "--kubernetes-secret-object") == "my-k8s-secret", (
        f"TIBCOP_CLI_K8S_SECRET must reach --kubernetes-secret-object: {argv!r}")
    # other_args is appended verbatim and tokenized into argv of its own. TWO tokens, so
    # the assertion also fails when other_args is swallowed as the VALUE of a preceding
    # flag (the positional form passed it as k8s_secret -> a single '--json --verbose'
    # token), not only when it is dropped.
    assert argv[-2:] == ["--json", "--verbose"], (
        f"TIBCOP_CLI_OTHER_ARGS must survive as trailing argv tokens: {argv!r}")
    # path_prefix has no request parameter at all; the positional form nonetheless set it
    # to the devhub name. Inert for TIBCOHUB only because this capability skips the
    # path-prefix arm — pin that the value never leaks into the command.
    assert "--path-prefix" not in argv, f"TIBCOHUB takes no path prefix: {argv!r}"
    assert argv.count("my-devhub") == 1, (
        f"the devhub name must appear once, as the devhub flag's value: {argv!r}")


def test_each_ems_request_value_reaches_its_own_flag(client, argv_calls):
    """The EMS parameters are the reason the signature grew, so guard the same mapping
    for them: they are keyword-only in practice and a future positional caller would
    shift them exactly as it shifted the TIBCOHUB ones."""
    ems_name = "ems-from-the-request"
    assert ems_name != ENV.TP_AUTO_EMS_CAPABILITY_SERVER_NAME, (
        "the request value must differ from the ENV default, or the assertion below "
        "passes even when the request value never arrives")

    _get(client,
         TIBCOP_CLI_CAPABILITY_ID="EMS",
         TIBCOP_CLI_EMS_NAME=ems_name,
         TIBCOP_CLI_EMS_SIZING="large",
         TIBCOP_CLI_EMS_USE="prod",
         TIBCOP_CLI_MSG_DATA_RESOURCE_ID="msg-res-1",
         TIBCOP_CLI_LOG_DATA_RESOURCE_ID="log-res-1")

    argv = _provision_argv(argv_calls)
    assert _flag(argv, "--capability") == "EMS"
    assert _flag(argv, "--ems-name") == ems_name, (
        f"TIBCOP_CLI_EMS_NAME must reach --ems-name: {argv!r}")
    assert _flag(argv, "--ems-sizing") == "large"
    assert _flag(argv, "--ems-use") == "prod"
    assert _flag(argv, "--msg-data-resource-instance-id") == "msg-res-1"
    assert _flag(argv, "--log-data-resource-instance-id") == "log-res-1"
