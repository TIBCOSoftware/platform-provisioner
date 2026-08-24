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
# Regression test for PCP-20701: with MSYS path conversion disabled in run_shell_file,
# the self-signed cert secret snippet must hand the native kubectl a path it can resolve.
# It writes /tmp/cp-cert.pem (bash redirect, still goes to the MSYS /tmp mount) but passes
# the secret file as `cygpath -w`-converted on Windows (Linux falls back to /tmp as-is),
# so it must NOT use the old bare `--from-file=cert=/tmp/cp-cert.pem` form that would be
# read by kubectl.exe as C:\tmp\cp-cert.pem and fail.

import cli_object.dataplane as dp_mod
from cli_object.dataplane import TibcopDataPlane


class _FakeBase:
    """Minimal TibcopBase stand-in for _run_dp_registration_script."""

    def run_command(self, command):
        # A registration script that contains a helm upgrade step.
        return "helm upgrade --install tp-tibtunnel ... --set accessKey=/abc\n"

    def is_cli_error(self, text):
        return False

    def format_command(self, text):
        return text


class _FakeEnvSelfSigned:
    TP_IS_CERT_SELF_SIGNED = True


def test_cert_secret_uses_cygpath_not_bare_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(dp_mod, "ENV", _FakeEnvSelfSigned)
    # Do not actually execute the generated script.
    monkeypatch.setattr(dp_mod.Helper, "run_shell_file", staticmethod(lambda path: "ok"))

    script_path = str(tmp_path / "register.sh")
    dp = TibcopDataPlane(_FakeBase())
    dp._run_dp_registration_script("dummy-command", script_path, "myns")

    with open(script_path, encoding="utf-8") as f:
        content = f.read()

    # New, Windows-safe form.
    assert 'cert_path="$(cygpath -w "$cert_file" 2>/dev/null || echo "$cert_file")"' in content
    assert '--from-file=cert="$cert_path"' in content
    # The old vulnerable bare form must be gone.
    assert "--from-file=cert=/tmp/cp-cert.pem" not in content
    # The secret is still created in the target namespace (quoted) before helm upgrade.
    assert 'self-signed-cert -n "myns"' in content
    assert content.index("self-signed-cert") < content.index("helm upgrade")
