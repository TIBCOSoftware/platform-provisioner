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
# Unit tests for Helper.resolve_github_token() — verifies the env -> mounted-secret
# precedence mirrors common-dependency/scripts/_functions.sh git_clone().

from utils.helper import Helper


def test_env_token_takes_precedence(monkeypatch, tmp_path):
    secret = tmp_path / "GITHUB_TOKEN"
    secret.write_text("file-token\n")
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    # env wins even when the secret file is present
    assert Helper.resolve_github_token(str(secret)) == "env-token"


def test_falls_back_to_secret_file(monkeypatch, tmp_path):
    secret = tmp_path / "GITHUB_TOKEN"
    secret.write_text("file-token\n")  # trailing newline must be stripped
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert Helper.resolve_github_token(str(secret)) == "file-token"


def test_empty_when_neither_present(monkeypatch, tmp_path):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    missing = tmp_path / "does-not-exist"
    assert Helper.resolve_github_token(str(missing)) == ""


def test_empty_env_string_falls_back_to_file(monkeypatch, tmp_path):
    secret = tmp_path / "GITHUB_TOKEN"
    secret.write_text("file-token")
    monkeypatch.setenv("GITHUB_TOKEN", "")  # empty env is treated as unset
    assert Helper.resolve_github_token(str(secret)) == "file-token"
