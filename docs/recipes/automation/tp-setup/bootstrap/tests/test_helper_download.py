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
# Regression test for Helper._download_via_curl() — guards the curl `-f` flag.
# Without `-f`, curl exits 0 on an HTTP 404/401 and writes the error body into
# the destination file, producing a corrupt JAR that passes the downstream
# os.path.isfile() check and gets deployed. Both curl invocations (release-info
# fetch and asset download) must use `-f` so HTTP errors fail fast.

import json
import types

from utils.helper import Helper


def test_download_via_curl_uses_fail_flag(monkeypatch, tmp_path):
    captured_cmds = []

    release_json = json.dumps({
        "assets": [{"name": "app.jar", "url": "https://api.github.com/asset/1"}]
    })

    def fake_run(cmd, *args, **kwargs):
        captured_cmds.append(cmd)
        # First call fetches release info via the API and reads stdout.
        if kwargs.get("capture_output"):
            return types.SimpleNamespace(stdout=release_json, stderr="", returncode=0)
        return types.SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(Helper, "resolve_github_token", staticmethod(lambda *a, **k: ""))
    monkeypatch.setattr("utils.helper.subprocess.run", fake_run)

    Helper._download_via_curl("owner/repo", "v1", "app.jar", str(tmp_path / "app.jar"))

    # Both curl commands (release info + asset download) must carry the fail flag.
    curl_cmds = [c for c in captured_cmds if c and c[0] == "curl"]
    assert len(curl_cmds) == 2, f"expected 2 curl calls, got {curl_cmds}"
    for cmd in curl_cmds:
        assert any(arg.startswith("-f") and "f" in arg for arg in cmd), \
            f"curl call missing -f (fail) flag: {cmd}"
