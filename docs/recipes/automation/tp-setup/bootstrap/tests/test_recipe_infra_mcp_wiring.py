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
# PCP-20335 — recipe wiring guard for the K8s MCP Server -> Infra MCP Server rename.
#
# The core guarantee of this ticket is the backward-compatible fallthrough: a
# recipe run that only sets the legacy GUI producer key
# GUI_TP_AUTO_ENABLE_K8S_MCP_SERVER must still enable the (renamed) capability.
# String-presence checks alone would false-GREEN here, because the whole point
# is the *bash render semantics* of the nested ${VAR:-default} expression — in
# particular that the new guiEnv default is the empty string (NOT "false"), so
# ${GUI_..._INFRA...:-${GUI_..._K8S...:-false}} falls through to the legacy key.
# So we extract the real expression from the recipe and render it with bash.

import os
import shutil
import subprocess
import sys

import pytest
import yaml


def _is_wsl_launcher(path):
    # On Windows, System32\bash.exe / WindowsApps\bash are the WSL launcher, not
    # a POSIX bash: they emit UTF-16 and exit non-zero when no distro is present.
    low = path.replace("/", "\\").lower()
    return "system32" in low or "windowsapps" in low


def _find_bash():
    """Locate a real POSIX bash. On Linux/CI the bare 'bash' on PATH is correct;
    on a Windows dev box that resolves to the WSL launcher, so prefer a
    Git-for-Windows bash and never the WSL shim."""
    for p in (
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
    ):
        if os.path.isfile(p):
            return p
    found = shutil.which("bash")
    if found and not _is_wsl_launcher(found):
        return found
    env_bash = os.environ.get("BASH")
    if env_bash and os.path.isfile(env_bash) and not _is_wsl_launcher(env_bash):
        return env_bash
    return None


BASH = _find_bash()


def _repo_root():
    """Walk up from this test file to the repo root (the dir that contains
    charts/provisioner-config-local/recipes/tp-automation-o11y.yaml)."""
    rel = os.path.join("charts", "provisioner-config-local", "recipes", "tp-automation-o11y.yaml")
    here = os.path.dirname(os.path.abspath(__file__))
    cur = here
    while True:
        if os.path.isfile(os.path.join(cur, rel)):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            raise FileNotFoundError(f"Could not locate {rel} walking up from {here}")
        cur = parent


RECIPE_PATH = os.path.join(
    _repo_root(), "charts", "provisioner-config-local", "recipes", "tp-automation-o11y.yaml"
)


def _bootstrap_dir():
    """Walk up from this test file to the bootstrap dir (the dir that holds the
    GUI producer/consumer pair static/index.js + templates/index.html). Same
    walk-up-to-a-marker convention as _repo_root() above."""
    marker = os.path.join("static", "index.js")
    here = os.path.dirname(os.path.abspath(__file__))
    cur = here
    while True:
        if os.path.isfile(os.path.join(cur, marker)):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            raise FileNotFoundError(f"Could not locate {marker} walking up from {here}")
        cur = parent


BOOTSTRAP_DIR = _bootstrap_dir()
STATIC_INDEX_JS = os.path.join(BOOTSTRAP_DIR, "static", "index.js")
TEMPLATES_INDEX_HTML = os.path.join(BOOTSTRAP_DIR, "templates", "index.html")


def _read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _load_recipe():
    with open(RECIPE_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _recipe_text():
    with open(RECIPE_PATH, encoding="utf-8") as f:
        return f.read()


def _global_env():
    return _load_recipe()["meta"]["globalEnvVariable"]


def _gui_env():
    return _load_recipe()["meta"]["guiEnv"]


def _deploy_task_content():
    tasks = _load_recipe()["tasks"]
    for task in tasks:
        if task.get("name") == "deploy-infra-mcp-server":
            return task["script"]["content"]
    raise AssertionError("deploy-infra-mcp-server task not found in recipe")


def _render(expr, extra_env):
    """Render a bash ${VAR:-default} expression using a clean base env plus the
    given keys, so unrelated shell vars in the parent process cannot leak in."""
    env = {"PATH": os.environ["PATH"]}
    env.update(extra_env)
    result = subprocess.run(
        [BASH, "-c", f'echo "{expr}"'],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"bash render failed: {result.stderr}"
    return result.stdout.strip()


# --- The provision expression is the load-bearing contract of this ticket. ---

PROVISION_EXPR = _global_env()["TP_AUTO_IS_PROVISION_INFRA_MCP_SERVER"]
GUI_DEFAULT = _gui_env()["GUI_TP_AUTO_ENABLE_INFRA_MCP_SERVER"]


class TestGuiEnvDefault:
    def test_new_gui_default_is_empty_string_not_false(self):
        # A "false" default would break the legacy fallthrough (Case D below);
        # only the empty-string default lets ${VAR:-...} fall through to legacy.
        assert GUI_DEFAULT == "", (
            "GUI_TP_AUTO_ENABLE_INFRA_MCP_SERVER guiEnv default must be the empty "
            f"string for legacy fallthrough, got {GUI_DEFAULT!r}"
        )


@pytest.mark.skipif(BASH is None, reason="no POSIX bash available to render ${VAR:-default} semantics")
class TestProvisionRenderSemantics:
    def test_case_a_legacy_only_falls_through_to_true(self):
        # Legacy producer set, new key UNSET -> must resolve to the legacy value.
        out = _render(PROVISION_EXPR, {"GUI_TP_AUTO_ENABLE_K8S_MCP_SERVER": "true"})
        assert out == "true"

    def test_case_b_neither_set_defaults_to_false(self):
        out = _render(PROVISION_EXPR, {})
        assert out == "false"

    def test_case_c_new_only_is_true(self):
        out = _render(PROVISION_EXPR, {"GUI_TP_AUTO_ENABLE_INFRA_MCP_SERVER": "true"})
        assert out == "true"

    def test_case_d_new_at_gui_default_still_honors_legacy_true(self):
        # New key present but at its guiEnv default (empty string) AND legacy true.
        # This FAILS if the guiEnv default were "false"; PASSES only when empty.
        out = _render(
            PROVISION_EXPR,
            {
                "GUI_TP_AUTO_ENABLE_INFRA_MCP_SERVER": GUI_DEFAULT,
                "GUI_TP_AUTO_ENABLE_K8S_MCP_SERVER": "true",
            },
        )
        assert out == "true"


class TestRecipeVocabulary:
    def test_deploy_task_content_uses_new_names(self):
        content = _deploy_task_content()
        assert 'capability="inframcpserver"' in content
        assert "case.k8s_provision_infra_mcp_server" in content
        assert "deploy-infra-mcp-server" in content

    def test_no_residual_old_tokens(self):
        text = _recipe_text()
        assert "k8smcpserver" not in text
        assert "k8s_provision_k8s_mcp_server" not in text
        assert "deploy-k8s-mcp-server" not in text
        # The forward key must no longer be DEFINED (left of a colon) under the
        # old name. The GUI producer key (GUI_ prefix) and the :- fallback use
        # are the only permitted survivors.
        import re
        assert re.search(r"(?m)^\s*TP_AUTO_ENABLE_K8S_MCP_SERVER\s*:", text) is None
        assert re.search(r"(?m)^\s*TP_AUTO_IS_PROVISION_K8S_MCP_SERVER\s*:", text) is None

    def test_legacy_gui_producer_key_still_present(self):
        text = _recipe_text()
        # The private producer contract key is retained ...
        assert "GUI_TP_AUTO_ENABLE_K8S_MCP_SERVER: false" in text
        # ... and it is still referenced inside the backward-compatible fallback.
        assert "${GUI_TP_AUTO_ENABLE_K8S_MCP_SERVER:-false}" in text


class TestGuiFormRenameResidual:
    # The GUI form is a producer/consumer pair split across two files — the
    # highest-risk one-sided-edit surface, and previously uncovered here.
    # static/index.js maps the <select> option value to the ENV provision flag,
    # and templates/index.html declares the <option value>. A half-rename in
    # either file silently breaks provisioning, so guard both files for the new
    # tokens present AND the old tokens fully gone.
    def test_static_index_js_uses_new_names_only(self):
        text = _read_text(STATIC_INDEX_JS)
        assert "provision_infra_mcp_server" in text
        assert "TP_AUTO_IS_PROVISION_INFRA_MCP_SERVER" in text
        assert "provision_k8s_mcp_server" not in text
        assert "TP_AUTO_IS_PROVISION_K8S_MCP_SERVER" not in text

    def test_templates_index_html_uses_new_option_value_only(self):
        text = _read_text(TEMPLATES_INDEX_HTML)
        assert "provision_infra_mcp_server" in text
        assert "provision_k8s_mcp_server" not in text


class TestBashAvailability:
    def test_bash_present_on_ci_or_non_windows(self):
        # TestProvisionRenderSemantics is skipif(BASH is None). On a bash-less
        # Linux/CI runner that would SILENTLY skip the load-bearing backward-compat
        # render contract. Fail loudly there instead; keep the skip only for local
        # Windows dev boxes without a real POSIX bash.
        if sys.platform != "win32" or os.environ.get("CI"):
            assert BASH is not None, (
                "POSIX bash is required to render the ${VAR:-default} backward-compat "
                "semantics on non-Windows / CI; refusing to silently skip that contract"
            )
