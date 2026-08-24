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
# Regression tests for PCP-20701: on Windows (Git Bash / MSYS), Helper.run_shell_file
# must disable MSYS automatic Unix->Windows path conversion so that helm --set values
# beginning with '/' (e.g. a tp-tibtunnel accessKey) are passed through verbatim instead
# of being mangled into 'C:/Program Files/Git/...'. On non-Windows the env must be
# untouched.

import utils.helper as helper_mod
from utils.helper import Helper


class _FakeCompleted:
    def __init__(self):
        self.stdout = "ok"
        self.stderr = ""


def _make_script(tmp_path):
    script = tmp_path / "run.sh"
    script.write_text("#!/usr/bin/env bash\necho hi\n")
    return str(script)


def test_windows_disables_msys_path_conversion(tmp_path, monkeypatch):
    script = _make_script(tmp_path)
    monkeypatch.delenv("TP_AUTO_KUBECONFIG", raising=False)
    monkeypatch.setattr(helper_mod.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        Helper, "get_windows_bash",
        staticmethod(lambda: "C:/Program Files/Git/bin/bash.exe"),
    )

    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["env"] = kwargs.get("env")
        return _FakeCompleted()

    monkeypatch.setattr(helper_mod.subprocess, "run", fake_run)

    assert Helper.run_shell_file(script) == "ok"

    env = captured["env"]
    assert env["MSYS_NO_PATHCONV"] == "1"
    assert env["MSYS2_ARG_CONV_EXCL"] == "*"
    # On Windows the script is executed through Git Bash.
    assert captured["command"][0].endswith("bash.exe")


def test_non_windows_does_not_set_msys_vars(tmp_path, monkeypatch):
    script = _make_script(tmp_path)
    monkeypatch.delenv("TP_AUTO_KUBECONFIG", raising=False)
    monkeypatch.delenv("MSYS_NO_PATHCONV", raising=False)
    monkeypatch.delenv("MSYS2_ARG_CONV_EXCL", raising=False)
    monkeypatch.setattr(helper_mod.platform, "system", lambda: "Linux")

    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["env"] = kwargs.get("env")
        return _FakeCompleted()

    monkeypatch.setattr(helper_mod.subprocess, "run", fake_run)

    assert Helper.run_shell_file(script) == "ok"

    env = captured["env"]
    assert "MSYS_NO_PATHCONV" not in env
    assert "MSYS2_ARG_CONV_EXCL" not in env
    # On non-Windows the script is executed directly (no bash wrapper).
    assert captured["command"] == [script]
