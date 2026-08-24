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
# Regression tests for TPSEC-163 (f026 residual): an unauthenticated attacker can plant a
# malicious kubeconfig and get it used as KUBECONFIG; a subsequent kubectl/helm executes the
# kubeconfig's users[].user.exec (or legacy auth-provider cmd-path) credential plugin -> RCE.
#
# Helper.get_env_vars() must therefore validate the EFFECTIVE KUBECONFIG (whether set via
# TP_AUTO_KUBECONFIG or a pre-existing/bare KUBECONFIG) and refuse it when it (A) resolves
# inside the unauthenticated-writable upload folder, or (B) declares a credential-plugin
# (exec / auth-provider) command — while still accepting a legitimate cert/token kubeconfig.
#
# Scope note: the bare-KUBECONFIG *request-param* denylist and the /run-cli-script env
# restriction are TPSEC-134's; /upload path traversal is TPSEC-128's. These tests pin the
# sink-layer validation in helper.py that is TPSEC-163's scope.

import os
from pathlib import Path

import pytest

import utils.helper as helper_mod
from utils.helper import Helper


def _upload_dir():
    # Same computation helper.py uses (get_file_fullpath_in_upload_folder):
    # utils/helper.py -> parent.parent (bootstrap) / upload
    return Path(helper_mod.__file__).resolve().parent.parent / "upload"


_BENIGN_KUBECONFIG = """\
apiVersion: v1
kind: Config
clusters:
- name: k3s
  cluster:
    server: https://127.0.0.1:6443
    certificate-authority-data: ZmFrZQ==
users:
- name: admin
  user:
    token: fake-token
contexts:
- name: default
  context:
    cluster: k3s
    user: admin
current-context: default
"""

_EXEC_KUBECONFIG = """\
apiVersion: v1
kind: Config
clusters:
- name: k3s
  cluster:
    server: https://127.0.0.1:6443
users:
- name: attacker
  user:
    exec:
      apiVersion: client.authentication.k8s.io/v1
      command: /bin/sh
      args: ["-c", "touch /tmp/pwned"]
contexts:
- name: default
  context:
    cluster: k3s
    user: attacker
current-context: default
"""

# Legacy client-go credential command mechanism (GCP): auth-provider cmd-path also
# executes a command, so Control B must reject it too, not only `exec`.
_AUTH_PROVIDER_KUBECONFIG = """\
apiVersion: v1
kind: Config
clusters:
- name: k3s
  cluster:
    server: https://127.0.0.1:6443
users:
- name: attacker
  user:
    auth-provider:
      name: gcp
      config:
        cmd-path: /bin/sh
        cmd-args: -c "touch /tmp/pwned"
contexts:
- name: default
  context:
    cluster: k3s
    user: attacker
current-context: default
"""


# ---- Control A: reject kubeconfigs inside the attacker-writable upload folder ----

def test_reject_kubeconfig_inside_upload_folder(monkeypatch):
    """Control A (isolated: BENIGN content, so only the upload-folder path check can reject it):
    a kubeconfig planted in the upload folder must be refused with a non-zero exit."""
    upload_dir = _upload_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)
    evil = upload_dir / "tpsec163_evil_kubeconfig.yaml"
    evil.write_text(_BENIGN_KUBECONFIG)
    try:
        monkeypatch.setenv("TP_AUTO_KUBECONFIG", str(evil))
        with pytest.raises(SystemExit) as exc:
            Helper.get_env_vars()
        assert exc.value.code not in (0, None)  # a security refusal must be a non-zero failure
    finally:
        evil.unlink(missing_ok=True)


def test_reject_kubeconfig_inside_upload_folder_via_traversal(monkeypatch):
    """Control A must realpath so `<upload>/../upload/evil.yaml` is still caught."""
    upload_dir = _upload_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)
    evil = upload_dir / "tpsec163_evil_trav.yaml"
    evil.write_text(_BENIGN_KUBECONFIG)  # benign content so ONLY Control A can reject it
    traversal = str(upload_dir / ".." / "upload" / "tpsec163_evil_trav.yaml")
    try:
        monkeypatch.setenv("TP_AUTO_KUBECONFIG", traversal)
        with pytest.raises(SystemExit):
            Helper.get_env_vars()
    finally:
        evil.unlink(missing_ok=True)


def test_reject_kubeconfig_symlink_into_upload(monkeypatch, tmp_path):
    """Control A must realpath the CANDIDATE: a symlink OUTSIDE upload pointing INTO upload
    (benign target content, so only Control A can reject) must still be refused."""
    upload_dir = _upload_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / "tpsec163_symlink_target.yaml"
    target.write_text(_BENIGN_KUBECONFIG)
    link = tmp_path / "link.yaml"
    try:
        try:
            os.symlink(str(target), str(link))
        except (OSError, NotImplementedError):
            pytest.skip("symlink not supported on this runner")
        monkeypatch.setenv("TP_AUTO_KUBECONFIG", str(link))
        with pytest.raises(SystemExit):
            Helper.get_env_vars()
    finally:
        target.unlink(missing_ok=True)


# ---- Control B (mandatory): reject credential-plugin command execution anywhere ----

def test_reject_kubeconfig_with_exec_credential_plugin(monkeypatch, tmp_path):
    """Control B: users[].user.exec is refused even outside the upload folder
    (covers the TPSEC-128 out-of-upload plant)."""
    kube = tmp_path / "exec_config.yaml"
    kube.write_text(_EXEC_KUBECONFIG)
    monkeypatch.setenv("TP_AUTO_KUBECONFIG", str(kube))
    with pytest.raises(SystemExit):
        Helper.get_env_vars()


def test_reject_kubeconfig_with_auth_provider(monkeypatch, tmp_path):
    """Control B: legacy users[].user.auth-provider cmd-path also executes commands -> refused."""
    kube = tmp_path / "authprovider_config.yaml"
    kube.write_text(_AUTH_PROVIDER_KUBECONFIG)
    monkeypatch.setenv("TP_AUTO_KUBECONFIG", str(kube))
    with pytest.raises(SystemExit):
        Helper.get_env_vars()


def test_reject_malformed_kubeconfig_fail_closed(monkeypatch, tmp_path):
    """Control B must fail-closed on a non-dict / unparseable kubeconfig (no AttributeError escape)."""
    kube = tmp_path / "not_a_config.yaml"
    kube.write_text("just a scalar string, not a mapping\n")
    monkeypatch.setenv("TP_AUTO_KUBECONFIG", str(kube))
    with pytest.raises(SystemExit):
        Helper.get_env_vars()


# ---- effective KUBECONFIG: validation must cover a bare KUBECONFIG, not only TP_AUTO_KUBECONFIG ----

def test_reject_effective_bare_kubeconfig_exec(monkeypatch, tmp_path):
    """Defense-in-depth: a bare KUBECONFIG (no TP_AUTO_KUBECONFIG) with an exec plugin is
    the effective KUBECONFIG and must also be refused."""
    kube = tmp_path / "bare_exec_config.yaml"
    kube.write_text(_EXEC_KUBECONFIG)
    monkeypatch.delenv("TP_AUTO_KUBECONFIG", raising=False)
    monkeypatch.setenv("KUBECONFIG", str(kube))
    with pytest.raises(SystemExit):
        Helper.get_env_vars()


# ---- no regression: legitimate cert/token kubeconfigs still work (both sources) ----

def test_allow_legitimate_kubeconfig_via_tp_auto(monkeypatch, tmp_path):
    kube = tmp_path / "config"
    kube.write_text(_BENIGN_KUBECONFIG)
    monkeypatch.setenv("TP_AUTO_KUBECONFIG", str(kube))
    env = Helper.get_env_vars()
    assert env["KUBECONFIG"] == str(kube)


def test_allow_legitimate_bare_kubeconfig(monkeypatch, tmp_path):
    kube = tmp_path / "config"
    kube.write_text(_BENIGN_KUBECONFIG)
    monkeypatch.delenv("TP_AUTO_KUBECONFIG", raising=False)
    monkeypatch.setenv("KUBECONFIG", str(kube))
    env = Helper.get_env_vars()
    assert env["KUBECONFIG"] == str(kube)


# ---- fail-closed shape hardening (round-2 review): malformed structures must sys.exit,
#      never raise an uncaught AttributeError (which an implementer might "fix" into fail-open) ----

def test_reject_malformed_users_mapping(monkeypatch, tmp_path):
    """`users:` as a mapping (not a list) must fail-closed, not AttributeError."""
    kube = tmp_path / "users_map.yaml"
    kube.write_text(
        "apiVersion: v1\nkind: Config\nusers:\n  attacker:\n    user:\n      exec:\n        command: /bin/sh\n"
    )
    monkeypatch.setenv("TP_AUTO_KUBECONFIG", str(kube))
    with pytest.raises(SystemExit):
        Helper.get_env_vars()


def test_reject_malformed_users_scalar_entry(monkeypatch, tmp_path):
    """A `users` list whose entries are scalars must fail-closed, not AttributeError."""
    kube = tmp_path / "users_scalar.yaml"
    kube.write_text("apiVersion: v1\nkind: Config\nusers:\n- just-a-string\n")
    monkeypatch.setenv("TP_AUTO_KUBECONFIG", str(kube))
    with pytest.raises(SystemExit):
        Helper.get_env_vars()


def test_reject_unparseable_yaml(monkeypatch, tmp_path):
    """Unparseable YAML must fail-closed."""
    kube = tmp_path / "bad.yaml"
    kube.write_text("key: [1, 2\n  broken: : :\n")
    monkeypatch.setenv("TP_AUTO_KUBECONFIG", str(kube))
    with pytest.raises(SystemExit):
        Helper.get_env_vars()


def test_missing_bare_kubeconfig_is_skipped_not_hard_exit(monkeypatch, tmp_path):
    """AC7: a stale bare KUBECONFIG pointing at a non-existent file must NOT hard-exit
    (prior behavior preserved) — it is skipped, not rejected."""
    missing = tmp_path / "gone.yaml"
    monkeypatch.delenv("TP_AUTO_KUBECONFIG", raising=False)
    monkeypatch.setenv("KUBECONFIG", str(missing))
    env = Helper.get_env_vars()  # must NOT raise SystemExit
    assert env["KUBECONFIG"] == str(missing)


# ---- 7b review additions: multi-path KUBECONFIG list, non-current-user exec, non-dict user,
#      non-zero exit on refusal, and preserved TP_AUTO_KUBECONFIG-missing behavior ----

def test_reject_multipath_kubeconfig_with_evil_component(monkeypatch, tmp_path):
    """kubectl treats KUBECONFIG as an os.pathsep-joined LIST it MERGES; a benign first
    component must not let an exec component through in a later position (7b HIGH bypass)."""
    good = tmp_path / "good.yaml"
    good.write_text(_BENIGN_KUBECONFIG)
    evil = tmp_path / "evil.yaml"
    evil.write_text(_EXEC_KUBECONFIG)
    monkeypatch.delenv("TP_AUTO_KUBECONFIG", raising=False)
    monkeypatch.setenv("KUBECONFIG", os.pathsep.join([str(good), str(evil)]))
    with pytest.raises(SystemExit) as exc:
        Helper.get_env_vars()
    assert exc.value.code not in (0, None)


def test_allow_multipath_kubeconfig_all_benign(monkeypatch, tmp_path):
    """A multi-path KUBECONFIG of only benign components is accepted unchanged."""
    a = tmp_path / "a.yaml"
    a.write_text(_BENIGN_KUBECONFIG)
    b = tmp_path / "b.yaml"
    b.write_text(_BENIGN_KUBECONFIG)
    joined = os.pathsep.join([str(a), str(b)])
    monkeypatch.delenv("TP_AUTO_KUBECONFIG", raising=False)
    monkeypatch.setenv("KUBECONFIG", joined)
    env = Helper.get_env_vars()
    assert env["KUBECONFIG"] == joined


def test_reject_exec_on_non_current_context_user(monkeypatch, tmp_path):
    """Control B must reject an exec plugin on ANY user, not just the current-context user."""
    kube = tmp_path / "noncurrent_exec.yaml"
    kube.write_text(
        "apiVersion: v1\nkind: Config\n"
        "current-context: safe\n"
        "contexts:\n- name: safe\n  context:\n    cluster: c\n    user: safe-user\n"
        "users:\n"
        "- name: safe-user\n  user:\n    token: t\n"
        "- name: attacker\n  user:\n    exec:\n      command: /bin/sh\n"
    )
    monkeypatch.setenv("TP_AUTO_KUBECONFIG", str(kube))
    with pytest.raises(SystemExit):
        Helper.get_env_vars()


def test_reject_user_not_a_mapping(monkeypatch, tmp_path):
    """Fail-closed: a users[] entry whose `user` is a non-dict scalar is malformed."""
    kube = tmp_path / "user_scalar.yaml"
    kube.write_text("apiVersion: v1\nkind: Config\nusers:\n- name: x\n  user: not-a-mapping\n")
    monkeypatch.setenv("TP_AUTO_KUBECONFIG", str(kube))
    with pytest.raises(SystemExit):
        Helper.get_env_vars()


def test_tp_auto_kubeconfig_missing_still_hard_exits(monkeypatch, tmp_path):
    """Pre-existing behavior preserved: a MISSING TP_AUTO_KUBECONFIG still hard-exits
    (unlike a missing *bare* KUBECONFIG, which is skipped — AC7)."""
    missing = tmp_path / "gone.yaml"
    monkeypatch.setenv("TP_AUTO_KUBECONFIG", str(missing))
    with pytest.raises(SystemExit) as exc:
        Helper.get_env_vars()
    assert exc.value.code not in (0, None)  # a bad kubeconfig is a non-zero failure, not false-green


def test_reject_kubeconfig_component_with_trailing_whitespace(monkeypatch, tmp_path):
    """kubectl uses KUBECONFIG components VERBATIM (no trim); validation must not strip, or a
    trailing-whitespace filename bypasses it. Linux-only — Windows trims filename whitespace."""
    ws_name = str(tmp_path / "evil.yaml") + " "  # trailing space in the actual filename
    try:
        with open(ws_name, "w", encoding="utf-8") as f:
            f.write(_EXEC_KUBECONFIG)
    except OSError:
        pytest.skip("cannot create a trailing-whitespace filename on this OS")
    if not os.path.exists(ws_name):
        pytest.skip("OS trims trailing whitespace in filenames (e.g. Windows)")
    monkeypatch.delenv("TP_AUTO_KUBECONFIG", raising=False)
    monkeypatch.setenv("KUBECONFIG", ws_name)  # the verbatim value kubectl would open
    with pytest.raises(SystemExit):
        Helper.get_env_vars()


def test_reject_kubeconfig_with_quote_char(monkeypatch, tmp_path):
    """Windows filepath.SplitList strips/honors double-quotes that Python's str.split does not
    mirror; a quoted KUBECONFIG is fail-closed to avoid a parsing-differential bypass."""
    evil = tmp_path / "evil.yaml"
    evil.write_text(_EXEC_KUBECONFIG)
    monkeypatch.delenv("TP_AUTO_KUBECONFIG", raising=False)
    monkeypatch.setenv("KUBECONFIG", '"' + str(evil) + '"')
    with pytest.raises(SystemExit) as exc:
        Helper.get_env_vars()
    assert exc.value.code not in (0, None)
