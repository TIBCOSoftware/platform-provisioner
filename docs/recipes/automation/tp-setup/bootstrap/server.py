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

import json
import re
import subprocess
import sys
import os
import time
import shutil
import uuid
from urllib.parse import urlsplit, urlunsplit
from flask import Flask, render_template, Response, request, jsonify, stream_with_context, send_from_directory
from werkzeug.utils import secure_filename
from markupsafe import escape
from typing import Dict

from utils.streaming_runner import StreamingRunner
from cli_object.facade import TibcopCLI
from utils.util import Util
from utils.env import ENV
from utils.helper import Helper
from utils.color_logger import ColorLogger
from api_object import LicenseApi

app = Flask(__name__, template_folder="templates")
HEADER_ONE_CLICK_JOB_ID = "one_click_job_id"
# TPSEC-124 (f024): no blanket CORS. This app serves its own Web UI same-origin, so it needs no
# cross-origin grant; the previous wildcard `Access-Control-Allow-Origin: *` let any website read
# these (formerly secret-bearing) endpoints from a victim's browser. Same-origin JS still reads
# custom response headers (e.g. one_click_job_id) without Access-Control-Expose-Headers. If a
# cross-origin consumer is ever needed, add flask_cors back with an explicit `origins` allowlist.
app.config['TEMPLATES_AUTO_RELOAD'] = True

running_processes: Dict[str, subprocess.Popen] = {}

# Single source of truth for the /upload endpoint: maps each accepted extension to
# its filetype. The keys ARE the allowlist used to sanitize the extension taken from
# the raw (attacker-controlled) filename — so a client cannot smuggle an arbitrary
# extension, and the allowlist can never drift from the classifier (TPSEC-128).
UPLOAD_EXTENSION_FILETYPE = {
    '.ear': 'BWCE',
    '.json': 'FLOGO',
    '.flogo': 'FLOGO',
    '.jar': 'SPRINGBOOT',
    '.zip': 'ACTIVATION',
}
ALLOWED_UPLOAD_EXTENSIONS = set(UPLOAD_EXTENSION_FILETYPE)

# --- Security: /run-gui-script case allow-list (TPSEC-135 / finding f026) -----
# /run-gui-script runs `python -u -m <case>`. `case` MUST be constrained to a
# server-side allowlist of first-party automation entry points; otherwise any
# importable module (or an uploaded one) can be executed. Mirrors /run-cli-script's
# case_function_map. THIS IS THE SECURITY BOUNDARY: when a new GUI/MCP automation
# case is added, add it here too (a missing entry fails safe with 404, never RCE).
# Source of truth: templates/index.html #guiAutoCase options AFTER the
# static/index.js handleGuiSpecialCase() rewrites, plus the
# mcps/tp_automation_mcp_server run_automation_task(...) call sites.
ALLOWED_GUI_CASES = frozenset({
    "page_env", "page_setting", "page_auth", "page_o11y",
    "case.create_global_config",
    "case.k8s_create_dp", "case.k8s_config_dp_o11y", "case.k8s_delete_dp",
    "case.k8s_provision_capability",
    "case.k8s_create_and_start_bwce_app",
    "case.k8s_create_and_start_flogo_app",
    "case.k8s_create_and_start_springboot_app",
    "case.k8s_deploy_mcp_hub", "case.k8s_delete_app",
    "case.bmdp_create_dp", "case.bmdp_config_dp_o11y", "case.bmdp_create_bw5dm",
    "case.bmdp_provision_capability", "case.bmdp_delete_dp", "case.bmdp_delete_bw5dm",
})

# Environment variables that must NEVER be settable from an (unauthenticated) HTTP
# request: they control the process / interpreter / dynamic loader and would allow
# code execution in the child even when the command runs without a shell
# (TPSEC-134/f023 + TPSEC-135/f026). e.g. tibcop is a Node process
# (NODE_OPTIONS=--require/--inspect); any glibc binary honors GCONV_PATH/LOCPATH/
# NLSPATH; `python -m` honors PYTHON*; java/perl/ruby honor *_OPTIONS/*OPT; kubeconfig
# and git can execute an attacker binary via an exec credential plugin / custom ssh /
# diff command. None are legitimate automation inputs (the legit kubeconfig knob is
# TP_AUTO_KUBECONFIG, promoted to KUBECONFIG internally), so dropping them from request
# params has no functional impact. Matched case-insensitively. Shared sink for BOTH
# /run-gui-script and /run-cli-script (set_env_vars_from_request).
_BLOCKED_REQUEST_ENV_KEYS = {
    "PATH", "BASH_ENV", "ENV", "IFS", "SHELL", "HOME",
    "GCONV_PATH", "LOCPATH", "NLSPATH",
    "KUBECONFIG", "GIT_SSH", "GIT_SSH_COMMAND", "GIT_EXTERNAL_DIFF",
    "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM",
    "JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS", "JDK_JAVA_OPTIONS",
    "PERL5OPT", "RUBYOPT",
    "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE",
    # not exploitable (the /get_env gate reads os.environ, which requests never mutate) —
    # defense-in-depth so a request arg of this name can't ride into a child script's env.
    "TP_AUTO_GET_ENV_EXPOSE_SECRETS",
}
_BLOCKED_REQUEST_ENV_PREFIXES = ("NODE_", "LD_", "DYLD_", "PYTHON", "BASH_FUNC_")


def _is_blocked_request_env_key(key):
    k = key.upper()
    if k in _BLOCKED_REQUEST_ENV_KEYS:
        return True
    return k.startswith(_BLOCKED_REQUEST_ENV_PREFIXES)


# Characters that enable shell command substitution / chaining / redirection. Request
# params on the unauthenticated /run-cli-script flow reach tibcop and, for the
# register/unregister cases, are embedded by tibcop into a script executed via a real
# shell (Helper.run_shell_file). The first-order sink is already de-shelled
# (cli_object/base.py); this boundary check is defense-in-depth for that second stage.
# None of these characters are legitimate in tibcop args, k8s names, FQDNs, versions,
# or resource descriptions (TPSEC-134/f023).
_SHELL_DANGEROUS_CHARS = frozenset('$`;|&<>\n\r')

# RFC 1123 label — the format Kubernetes namespaces / names / service-account names
# must take. The register cases embed these into kubectl/helm in the generated script,
# so validate them positively (not merely metacharacter-reject).
_K8S_LABEL_RE = re.compile(r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?$')


def _has_shell_dangerous_chars(value):
    return any(c in _SHELL_DANGEROUS_CHARS for c in value)


def set_env_vars_from_request(request_args, include_system_env=True, allowed_prefixes=None):
    # Build the child-process environment from request parameters.
    #
    # Security (TPSEC-134): request params are attacker-controlled on the
    # unauthenticated helper server, so (1) never copy a process/interpreter control
    # var (_is_blocked_request_env_key), and (2) when allowed_prefixes is given, only
    # copy request keys within that namespace (e.g. ("TIBCOP_CLI_",) for /run-cli-script,
    # whose tibcop child only needs TIBCOP_CLI_* from the request). The trusted system
    # env (os.environ) is used as-is; only REQUEST keys are filtered.
    if include_system_env:
        env_vars = os.environ.copy()
    else:
        env_vars = {}

    env_vars["PYTHONIOENCODING"] = "utf-8"
    # Accept a bare string prefix without turning it into a tuple of characters.
    if isinstance(allowed_prefixes, str):
        allowed_prefixes = (allowed_prefixes,)
    allowed = tuple(allowed_prefixes) if allowed_prefixes else None
    for key, value in request_args.items():
        if key == "case" or not value:
            continue
        if _is_blocked_request_env_key(key):
            continue
        if allowed is not None and not key.startswith(allowed):
            continue
        env_vars[key] = value

    return env_vars

@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.route('/')
def home():
    """ Render the main HTML page """
    return render_template('index.html')

@app.route('/upload/<path:filename>')
def serve_upload_file(filename):
    """ Serve files from upload folder """
    upload_folder = Util.get_upload_folder()
    return send_from_directory(upload_folder, filename)

@app.route('/cp_api')
def call_cp_api():
    api_path = request.args.get("api_path")
    if not api_path:
        return jsonify({"error": "Missing 'api_path' parameter"}), 400

    api_method = request.args.get("api_method", "GET")
    api_data = request.get_json(silent=True)

    base_url = f"https://{ENV.DP_HOST_PREFIX}.{ENV.TP_AUTO_CP_SERVICE_DNS_DOMAIN}"

    # Security: host-suffix / userinfo SSRF guard (TPSEC-116 / finding f027).
    # base_url ends at a bare host (no trailing slash) and curl is invoked below with a
    # live CP bearer token. Without validation, an api_path that does not start with a
    # single "/" rewrites the URL authority and exfiltrates the token, e.g.
    #   "@evil.com/x"  -> https://<cp-host>@evil.com/x   (<cp-host> becomes userinfo)
    #   ".evil.com/x"  -> https://<cp-host>.evil.com/x   (host suffix)
    # Require an absolute path (exactly one leading "/"): this forces every
    # attacker-controlled byte AFTER the authority-terminating slash, so neither urlsplit
    # nor curl can be steered to another host. The netloc equality check is defense in
    # depth (guards a future refactor that gives base_url a path or relaxes the slash rule).
    # Reject with 400 BEFORE the token is fetched or any curl runs (no token leaves).
    if not api_path.startswith("/") or api_path.startswith("//"):
        return jsonify({"error": "Invalid 'api_path' parameter"}), 400

    url = base_url + api_path
    if urlsplit(url).netloc != urlsplit(base_url).netloc:
        return jsonify({"error": "Invalid 'api_path' parameter"}), 400

    # Fetch the CP bearer token only after api_path is validated (don't do the sensitive
    # k8s-secret read for a request we are about to reject).
    token = Helper.get_auto_token()

    print(f"[INFO] Calling CP API: {api_method} {url}", api_data)
    # NOTE: intentionally no `-L`/`--location`. The guard above pins the *request* URL to
    # the CP host; following a CP-returned 3xx would let a redirect bounce the bearer token
    # to an attacker host, re-opening this SSRF (TPSEC-116). Do not add --location here.
    curl_cmd = [
        "curl",
        "--no-progress-meter",
        "-X", api_method,
        "-H", "Content-Type: application/json",
        url
    ]
    if token:
        curl_cmd.extend(["-H", f"Authorization: Bearer {token}"])
    if api_data is not None and api_method.upper() in ["POST", "PUT", "PATCH"]:
        curl_cmd.extend(["-d", api_data])

    process = subprocess.Popen(
        curl_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout, stderr = process.communicate()
    if stderr:
        return jsonify({"error": stderr.decode()}), 500

    return Response(stdout.decode(), mimetype="application/json")

@app.route('/stop-script')
def stop_script():
    """ Stop the currently running script """
    job_id = request.args.get("jobId")
    process = running_processes.get(job_id)
    if process and process.poll() is None:  # Ensure the process is assigned
        print(f"[INFO] Stopping process (PID: {process.pid})...")
        process.terminate()  # Try to terminate gracefully
        try:
            process.wait(timeout=2)  # Wait up to 2 seconds
        except subprocess.TimeoutExpired:
            process.kill()  # Force kill if termination fails
        running_processes.pop(job_id, None)
        return jsonify({"status": "stopped", "message": "Process terminated successfully"})

    return jsonify({"status": "no_process", "message": "No process running"})

@app.route('/run-gui-script')
def run_gui_script():
    """ Execute a Python script and stream real-time output """
    # case is from query parameter
    auto_case = request.args.get('case')
    is_clean_report = request.args.get('IS_CLEAN_REPORT')
    if not auto_case:
        return "Error: Missing 'case' parameter", 400

    # Security (TPSEC-135 / f026): only run first-party allowlisted automation
    # cases — never an arbitrary importable module. Mirrors /run-cli-script's
    # 404-on-unknown-case; escape() keeps the 404 body from reflecting raw input.
    if auto_case not in ALLOWED_GUI_CASES:
        return f"{escape(auto_case)} not found", 404

    report_folder = os.path.join(os.getcwd(), "report")
    if is_clean_report == "true":
        if os.path.exists(report_folder) and os.path.isdir(report_folder):
            shutil.rmtree(report_folder)
            print(f"Removed {report_folder}")
    else:
        report_yaml_file = os.path.join(report_folder, "report.yaml")
        report_txt_file = os.path.join(report_folder, "report.txt")
        if os.path.exists(report_yaml_file):
            os.remove(report_yaml_file)
            print(f"Removed {report_yaml_file}")
        if os.path.exists(report_txt_file):
            os.remove(report_txt_file)
            print(f"Removed {report_txt_file}")

    # Set request parameters as environment variables
    env_vars = set_env_vars_from_request(request.args)

    job_id = str(uuid.uuid4())
    def generate():
        # Start the script using unbuffered output
        print(f'{sys.executable}, "-u", "-m", {auto_case}')
        process = subprocess.Popen(
            [sys.executable, "-u", "-m", auto_case],  # `-u` ensures unbuffered output
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env_vars
        )
        running_processes[job_id] = process

        # Stream output line by line
        try:
            yield '<pre>\n'
            for line in iter(lambda: process.stdout.readline() if process and process.poll() is None else None, None):
                if line and line.strip():
                    yield Util.clean_ansi_escape(line) + '\n'
            yield '</pre>\n'

        except Exception as e:
            print(f"[ERROR] Exception in generate(): {e}")

        finally:
            if process:
                process.stdout.close()
                process.wait()
            running_processes.pop(job_id, None)

    headers = {
        HEADER_ONE_CLICK_JOB_ID: job_id
    }
    return Response(generate(), headers=headers, content_type='text/html; charset=utf-8')

def create_activation_file_resource(cli_handler, dp_name):
    """Upload the activation license file via the CP REST API.

    Reuses the existing activation-file mechanism (LicenseApi.upload_license_file)
    used by page_cli.py: the license .bin (extracted from the uploaded activation
    .zip into upload/license-file.bin) is PUT to the subscription-scoped license
    endpoint, or the DataPlane-scoped one when a DataPlane name is provided.
    """
    license_path = ENV.TP_AUTO_LICENSE_FILE_PATH
    if not (license_path and os.path.isfile(license_path)):
        ColorLogger.error(f"Activation license file not found at '{license_path}'. Upload the activation .zip first.")
        return None

    # Resolve CP URL + token from the CLI environment (same precedence as page_cli.py)
    custom_env = getattr(cli_handler.base, "CUSTOM_ENV", {}) or {}
    cp_url = (custom_env.get("TIBCOP_CLI_CPURL") or os.environ.get("TIBCOP_CLI_CPURL", "")).rstrip("/")
    token = custom_env.get("TIBCOP_CLI_OAUTH_TOKEN") or os.environ.get("TIBCOP_CLI_OAUTH_TOKEN") or Helper.get_auto_token()
    if not (cp_url and token):
        ColorLogger.error("TIBCOP_CLI_CPURL or OAuth token missing — cannot upload activation file")
        return None

    # DataPlane scope when a DP name is given; subscription (global) scope otherwise
    dp_id = None
    if dp_name and dp_name.lower() != "global":
        dp_id = cli_handler.dataplane.get_dataplane_id(dp_name)
        if not dp_id:
            ColorLogger.error(f"Could not resolve DataPlane ID for '{dp_name}'")
            return None

    return LicenseApi(cp_url, token).upload_license_file(license_path, dp_id)


@app.route('/run-cli-script')
def run_cli_script():
    auto_case = request.args.get('case')
    dp_name = request.args.get('TIBCOP_CLI_DP_NAME')
    app_id = request.args.get('TIBCOP_CLI_APP_ID')
    capability_id = request.args.get('TIBCOP_CLI_CAPABILITY_ID')
    storage_resource_id = request.args.get('TIBCOP_CLI_STORAGE_RESOURCE_ID')
    ingress_resource_id = request.args.get('TIBCOP_CLI_INGRESS_RESOURCE_ID')
    devhub_name = request.args.get('TIBCOP_CLI_DEVHUB_NAME')
    k8s_secret = request.args.get('TIBCOP_CLI_K8S_SECRET')
    resource_name = request.args.get('TIBCOP_CLI_RESOURCE_NAME')
    resource_instance_id = request.args.get('TIBCOP_CLI_RESOURCE_INSTANCE_ID')
    fqdn = request.args.get('TIBCOP_CLI_FQDN')
    storage_class_name = request.args.get('TIBCOP_CLI_STORAGE_CLASS_NAME')
    ingress_class_name = request.args.get('TIBCOP_CLI_INGRESS_CLASS_NAME')
    ingress_controller = request.args.get('TIBCOP_CLI_INGRESS_CONTROLLER')
    ear_file_path = request.args.get('TIBCOP_CLI_EAR_FILE_PATH')
    deploy_config_file = request.args.get('TIBCOP_CLI_DEPLOY_CONFIG_FILE')
    bwce_version = request.args.get('TIBCOP_CLI_BWCE_VERSION')
    flogo_version = request.args.get('TIBCOP_CLI_FLOGO_VERSION')
    base_image_tag = request.args.get('TIBCOP_CLI_BASE_IMAGE_TAG')
    # Use default namespace pattern if not provided
    dp_namespace = request.args.get('TIBCOP_CLI_DP_NAMESPACE') or (f"{dp_name}ns" if dp_name else None)
    dp_service_account_name = request.args.get('TIBCOP_CLI_DP_SERVICE_ACCOUNT_NAME') or (f"{dp_name}sa" if dp_name else None)
    storage_resource_name = request.args.get('TIBCOP_CLI_STORAGE_RESOURCE_NAME')
    storage_resource_description = request.args.get('TIBCOP_CLI_STORAGE_RESOURCE_DESCRIPTION')
    ingress_resource_name = request.args.get('TIBCOP_CLI_INGRESS_RESOURCE_NAME')
    ingress_resource_description = request.args.get('TIBCOP_CLI_INGRESS_RESOURCE_DESCRIPTION')
    other_args = request.args.get('TIBCOP_CLI_OTHER_ARGS')

    if not auto_case:
        return "Missing 'case' parameter", 400

    # Defense-in-depth (TPSEC-134/f023): the register/unregister cases embed request
    # values into a tibcop-generated script executed via a shell (Helper.run_shell_file).
    # The first-order sink is de-shelled; here we (a) reject shell-dangerous characters in
    # every request value so a caller cannot inject a second-stage *command*, and (b)
    # require the k8s identifiers (dp name / namespace / service-account) to be valid
    # RFC-1123 labels so they cannot break out of quoting to smuggle an extra flag
    # (e.g. helm --post-renderer). Residual argument-injection via free-text params
    # (descriptions) or arbitrary `other_args` reaching tibcop's generated scripts is
    # bounded and depends on tibcop's own escaping; the holistic fix is authenticating
    # this endpoint (tracked separately). `case` is validated by the case allow-list.
    for _param_key, _param_value in request.args.items():
        if _param_key == "case" or not _param_value:
            continue
        if _has_shell_dangerous_chars(_param_value):
            return f"Invalid characters in parameter '{_param_key}'", 400
    for _label in (dp_name, dp_namespace, dp_service_account_name):
        if _label and not _K8S_LABEL_RE.match(_label):
            return "Invalid dataplane name / namespace / service-account (must be a valid Kubernetes RFC-1123 label)", 400

    # Include system environment variables to get TIBCOP_CLI_CPURL and TIBCOP_CLI_OAUTH_TOKEN.
    # Restrict request-supplied env to the TIBCOP_CLI_* namespace (all the tibcop child needs
    # from the request) so an unauthenticated caller cannot inject process-control env vars
    # such as NODE_OPTIONS into the child process (TPSEC-134/f023).
    env_vars = set_env_vars_from_request(request.args, True, allowed_prefixes=("TIBCOP_CLI_",))
    cli_handler = TibcopCLI(env_vars)

    case_function_map = {
        "kubectl:list-cluster-resources": lambda: cli_handler.kubectl.list_cluster_resources(),
        "tplatform:list-dataplanes": lambda: cli_handler.dataplane.list_dataplanes(other_args=other_args),
        "tplatform:register-k8s-dataplane": lambda: cli_handler.dataplane.register_k8s_dataplane(dp_name, other_args=other_args),
        "tplatform:register-control-tower-dataplane": lambda: cli_handler.dataplane.register_control_tower_dataplane(
            dp_name, dp_namespace, dp_service_account_name,
            storage_resource_name, storage_class_name, storage_resource_description,
            ingress_resource_name, ingress_controller, ingress_class_name,
            ingress_resource_description, fqdn, other_args
        ),
        "tplatform:unregister-dataplane": lambda: cli_handler.dataplane.unregister_dataplane(dp_name, other_args=other_args),
        "tplatform:list-apps": lambda: cli_handler.app.list_apps(dp_name, other_args=other_args),
        "tplatform:list-capabilities": lambda: cli_handler.capability.list_capabilities(dp_name, other_args=other_args),
        "tplatform:list-resource-instances": lambda: cli_handler.resource.list_resource_instances(dp_name, other_args=other_args),
        "delete-app": lambda: cli_handler.app.delete_app(dp_name, capability_id, app_id, other_args=other_args),
        "provision-capability": lambda: cli_handler.capability.provision_capability(
            dp_name, capability_id, storage_resource_id, ingress_resource_id,
            None, devhub_name, k8s_secret, other_args
        ),
        "delete-capability-instance": lambda: cli_handler.capability.delete_capability_instance(
            dp_name, capability_id, other_args
        ),
        "create-storage-resource": lambda: cli_handler.resource.create_storage_resource(
            dp_name, resource_name, storage_class_name, "Storage_For_Integration", other_args
        ),
        "create-ingress-resource": lambda: cli_handler.resource.create_ingress_resource(
            dp_name, resource_name, fqdn, ingress_class_name, ingress_controller, other_args
        ),
        "delete-resource-instance": lambda: cli_handler.resource.delete_resource(
            dp_name, resource_instance_id, other_args
        ),
        "create-activation-file-resource": lambda: create_activation_file_resource(cli_handler, dp_name),
        "bwce:list-versions": lambda: cli_handler.bwce.list_versions(dp_name, other_args),
        "bwce:provision-version": lambda: cli_handler.bwce.provision_version(dp_name, bwce_version, other_args),
        "bwce:create-build": lambda: cli_handler.bwce.create_build(
            dp_name, ear_file_path, bwce_version or None, base_image_tag or None, other_args
        ),
        "bwce:deploy-app": lambda: cli_handler.bwce.deploy_app(
            dp_name, dp_namespace or f"{dp_name}ns", deploy_config_file, other_args
        ),
        "bwce-build-and-deploy": lambda: cli_handler.bwce.build_and_deploy_app(
            dp_name, ear_file_path, deploy_config_file, dp_namespace, other_args
        ),
        "flogo:list-versions": lambda: cli_handler.flogo.list_versions(dp_name, other_args),
        "flogo:provision-version": lambda: cli_handler.flogo.provision_version(dp_name, flogo_version, other_args),
        "flogo:create-build": lambda: cli_handler.flogo.create_build(
            dp_name, ear_file_path, bwce_version or None, "linux", "amd64", other_args
        ),
        "flogo:deploy-app": lambda: cli_handler.flogo.deploy_app(
            dp_name, dp_namespace or f"{dp_name}ns", deploy_config_file, None, other_args
        ),
        "flogo-build-and-deploy": lambda: cli_handler.flogo.build_and_deploy_app(
            dp_name, ear_file_path, deploy_config_file, dp_namespace, other_args
        ),
        "bw5ce:list-versions": lambda: cli_handler.bw5ce.list_versions(dp_name, other_args),
        "bw5ce:provision-version": lambda: cli_handler.bw5ce.provision_version(dp_name, bwce_version, other_args),
        "bw5ce:create-build": lambda: cli_handler.bw5ce.create_build(
            dp_name, ear_file_path, bwce_version or None, base_image_tag or None, other_args
        ),
        "bw5ce:deploy-app": lambda: cli_handler.bw5ce.deploy_app(
            dp_name, dp_namespace or f"{dp_name}ns", deploy_config_file, other_args
        ),
        "bw5ce-build-and-deploy": lambda: cli_handler.bw5ce.build_and_deploy_app(
            dp_name, ear_file_path, deploy_config_file, dp_namespace, other_args
        )
    }
    case_func = case_function_map.get(auto_case)

    if case_func:
        runner = StreamingRunner()
        runner.start_thread(case_func)

        # Use runner.q as queue，generate stream:
        @stream_with_context
        def generate():
            while True:
                line = runner.q.get()
                if line is None:
                    break
                yield Util.clean_ansi_escape(line, False) + '\n'

        return Response(generate(), content_type='text/html; charset=utf-8')
    else:
        return f"{escape(auto_case)} not found", 404

# --- TPSEC-124 (f024): /get_env non-secret allowlist ----------------------------------------
# /get_env exists ONLY to pre-fill the Web UI form with the deployment's NON-secret config.
# Before this fix it returned {**os.environ, **env_dict} plus a freshly fetched cluster-admin
# OAuth token, unauthenticated — a full credential dump. It is now a strict default-deny
# allowlist: ONLY the keys below (all non-secret, all consumed by templates/index.html) are ever
# returned. Add a key here ONLY when a NEW non-secret UI pre-fill field is introduced; NEVER add
# a secret-bearing key (passwords, tokens, the OAuth bearer, license blobs). Secrets are excluded
# by omission — the whole point of default-deny.
GET_ENV_SAFE_KEYS = frozenset({
    # URLs / domains (user:pass@ userinfo stripped before returning — see _GET_ENV_URL_KEYS)
    "TP_AUTO_LOGIN_URL", "TP_AUTO_ADMIN_URL", "TP_AUTO_MAIL_URL",
    "TP_AUTO_CP_DNS_DOMAIN", "TP_AUTO_CP_SERVICE_DNS_DOMAIN",
    "TP_AUTO_FQDN_BWCE", "TP_AUTO_FQDN_BW5CE", "TP_AUTO_FQDN_FLOGO",
    "TP_AUTO_FQDN_TIBCOHUB", "TP_AUTO_FQDN_SPRINGBOOT",
    "TIBCOP_CLI_CPURL", "TIBCOP_CLI_FQDN",
    # identifiers / non-secret config
    "CP_ADMIN_EMAIL", "DP_USER_EMAIL", "DP_HOST_PREFIX",
    "TP_AUTO_CP_INSTANCE_ID", "TP_AUTO_K8S_DP_NAME", "TP_AUTO_K8S_BMDP_NAME",
    "TP_AUTO_TOKEN_NAME", "TP_AUTO_KUBECONFIG",
    "TP_AUTO_DATA_PLANE_O11Y_SYSTEM_CONFIG",
    "TP_BW5_CHART_REPO_USER_NAME",
    # NOTE: free-form arg fields (TP_AUTO_K8S_DP_SERVICE_ACCOUNT_CREATION_ADDITIONAL_SETTINGS,
    # TIBCOP_CLI_OTHER_ARGS) are deliberately NOT allowlisted — they carry arbitrary operator
    # Helm/CLI flags that can contain secrets (e.g. --set password=...), so returning them would
    # re-open the disclosure. The operator re-enters them in the UI.
    # app names / file names / image tags
    "BWCE_APP_NAME", "BW5CE_APP_NAME", "FLOGO_APP_NAME", "SPRINGBOOT_APP_NAME",
    "BWCE_APP_FILE_NAME", "BW5CE_APP_FILE_NAME", "FLOGO_APP_FILE_NAME", "SPRINGBOOT_APP_FILE_NAME",
    "TP_BMDP_IMAGE_TAG_EMS", "TP_BMDP_IMAGE_TAG_BW5EMSDM",
    "TP_BMDP_IMAGE_TAG_BW5RVDM", "TP_BMDP_IMAGE_TAG_BW6DM",
    # version (computed from version.txt)
    "TP_AUTOMATION_TASK_RELEASE_VERSION",
    # runtime flags (sourced from os.environ, not EnvConfig)
    "HEADLESS", "FORCE_RUN_AUTOMATION", "IS_CLEAN_REPORT", "TP_AUTO_TASK_FROM_LOCAL_SOURCE",
    # tibcop CLI operational inputs (non-secret)
    "TIBCOP_CLI_DP_NAME", "TIBCOP_CLI_CAPABILITY_ID", "TIBCOP_CLI_APP_ID",
    "TIBCOP_CLI_RESOURCE_NAME", "TIBCOP_CLI_INGRESS_CONTROLLER",
    "TIBCOP_CLI_STORAGE_CLASS_NAME", "TIBCOP_CLI_INGRESS_CLASS_NAME",
    "TIBCOP_CLI_RESOURCE_INSTANCE_ID", "TIBCOP_CLI_EAR_FILE_PATH",
    "TIBCOP_CLI_BWCE_VERSION", "TIBCOP_CLI_FLOGO_VERSION", "TIBCOP_CLI_BASE_IMAGE_TAG",
    "TIBCOP_CLI_STORAGE_RESOURCE_ID",
    "TIBCOP_CLI_INGRESS_RESOURCE_ID", "TIBCOP_CLI_DEVHUB_NAME",
    "TIBCOP_CLI_DEPLOY_CONFIG_FILE", "TIBCOP_CLI_FILE_UPLOAD_LABEL",
})

# --- DEV opt-in: expose the Automation Hub pre-fill secrets in /get_env ----------------------
# Default OFF preserves the TPSEC-124 default-deny above (secrets are NEVER served) — which is
# what the public repo and any non-dev deployment ship. When TP_AUTO_GET_ENV_EXPOSE_SECRETS is
# set to "true" on a TRUSTED local/dev instance, /get_env ALSO returns the keys below so the UI
# Admin/User Password + CLI Token fields populate on load. This re-enables the exact behaviour
# TPSEC-124 removed, so it is gated behind an explicit, default-off flag and must only be turned
# on where the credentials are throwaway dev creds (a live CP OAuth bearer is still a real
# credential — do NOT enable this on a shared/production instance).
GET_ENV_SECRET_KEYS = frozenset({
    "CP_ADMIN_PASSWORD", "DP_USER_PASSWORD", "TIBCOP_CLI_OAUTH_TOKEN",
})

def _expose_get_env_secrets():
    """True only when the operator explicitly opts in (dev-only). Read at request time."""
    return os.environ.get("TP_AUTO_GET_ENV_EXPOSE_SECRETS", "").strip().lower() == "true"

# One-shot latch so the "secrets are being served" WARN is logged once per process, not per
# request — makes an accidental enable on a non-dev box detectable in the logs after the fact.
_EXPOSE_SECRETS_WARNED = {"done": False}

# Allowlisted keys whose values are URLs — strip any user:pass@ userinfo before returning so an
# operator-injected credential in a URL cannot leak to the browser.
_GET_ENV_URL_KEYS = frozenset({
    "TP_AUTO_LOGIN_URL", "TP_AUTO_ADMIN_URL", "TP_AUTO_MAIL_URL",
    "TIBCOP_CLI_CPURL", "TIBCOP_CLI_FQDN",
})


def _strip_url_userinfo(value):
    """Return the URL with any user:pass@ userinfo removed; non-URL strings pass through.

    Operates on the raw netloc (minus userinfo) so host:port is preserved verbatim — including
    IPv6 brackets — and a malformed port never raises (parts.port is never accessed). Also handles
    scheme-relative URLs (//user:pass@host/...), which an early scheme check would have skipped.
    """
    if not isinstance(value, str):
        return value
    try:
        parts = urlsplit(value)
        if "@" not in parts.netloc:
            return value
        netloc = parts.netloc.rsplit("@", 1)[-1]  # drop userinfo, keep host[:port] verbatim
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    except ValueError:
        return value


@app.route('/get_env')
def get_env():
    env_vars = os.environ.copy()
    env_dict = {
        key: getattr(ENV, key)
        for key in dir(ENV)
        if not key.startswith("_") and not callable(getattr(ENV, key))
    }
    # if version.txt exist, get content of version.txt
    version_file = os.path.join(os.getcwd(), "version.txt")
    if os.path.exists(version_file):
        with open(version_file, "r") as f:
            version = f.read().strip()
        env_dict["TP_AUTOMATION_TASK_RELEASE_VERSION"] = version
    # Re-detect CP DNS domain dynamically if the cached ENV value is the hardcoded default.
    # This handles the case where Helper.get_cp_dns_domain() returned empty at server startup
    # (e.g., k8s ingress not ready yet) and the default "localhost.dataplanes.pro" was cached.

    cp_dns_domain = env_dict.get("TP_AUTO_CP_DNS_DOMAIN", "")
    if not cp_dns_domain or cp_dns_domain == "localhost.dataplanes.pro":
        detected = Helper.get_cp_dns_domain()
        # Fallback: extract domain from request host (e.g., automation.dev.localhost -> dev.localhost)
        if not detected:
            request_host = request.host.split(':')[0]
            parts = request_host.split('.', 1)
            if len(parts) == 2 and parts[0] == 'automation':
                detected = parts[1]
        if detected:
            cp_dns_domain = detected
            cp_instance_id = env_dict.get("TP_AUTO_CP_INSTANCE_ID", "cp1")
            dp_host_prefix = env_dict.get("DP_HOST_PREFIX", "cp-sub1")
            service_dns = f"{cp_instance_id}-my.{cp_dns_domain}"
            env_dict["TP_AUTO_CP_DNS_DOMAIN"] = cp_dns_domain
            env_dict["TP_AUTO_CP_SERVICE_DNS_DOMAIN"] = service_dns
            env_dict["TP_AUTO_LOGIN_URL"] = f"https://{dp_host_prefix}.{service_dns}/cp/login"
            env_dict["TP_AUTO_ADMIN_URL"] = f"https://admin.{service_dns}/admin"
            env_dict["TP_AUTO_MAIL_URL"] = f"https://mail.{cp_dns_domain}/#/"
            # Update capability FQDNs
            for prefix_key, fqdn_key in [
                ("TP_AUTO_CP_DNS_DOMAIN_PREFIX_BWCE", "TP_AUTO_FQDN_BWCE"),
                ("TP_AUTO_CP_DNS_DOMAIN_PREFIX_BW5CE", "TP_AUTO_FQDN_BW5CE"),
                ("TP_AUTO_CP_DNS_DOMAIN_PREFIX_FLOGO", "TP_AUTO_FQDN_FLOGO"),
                ("TP_AUTO_CP_DNS_DOMAIN_PREFIX_TIBCOHUB", "TP_AUTO_FQDN_TIBCOHUB"),
                ("TP_AUTO_CP_DNS_DOMAIN_PREFIX_SPRINGBOOT", "TP_AUTO_FQDN_SPRINGBOOT"),
            ]:
                prefix = env_dict.get(prefix_key, "")
                if prefix:
                    env_dict[fqdn_key] = f"{prefix}.{cp_dns_domain}"

    # Derive the CLI Control Plane URL (scheme://host[:port] only) from the login URL when not
    # already provided. Use urlsplit (not a greedy regex) so any user:pass@ userinfo is dropped
    # rather than carried into the response.
    if not env_vars.get("TIBCOP_CLI_CPURL"):
        cp_url = env_dict.get("TP_AUTO_LOGIN_URL", "")
        if cp_url:
            try:
                parts = urlsplit(cp_url)
                if parts.scheme and parts.netloc:
                    # scheme://host[:port] only; rsplit drops any user:pass@ userinfo and keeps the
                    # host (incl. IPv6 brackets) and port verbatim — no parts.port access (never raises).
                    netloc = parts.netloc.rsplit("@", 1)[-1]
                    env_dict["TIBCOP_CLI_CPURL"] = urlunsplit((parts.scheme, netloc, "", "", ""))
            except ValueError:
                pass

    # TPSEC-124 (f024): default-deny. Build the candidate map, then keep ONLY the non-secret
    # allowlisted keys — never the os.environ dump, secrets, or the cluster-admin OAuth token
    # (which is no longer fetched at all). The allowlist filter runs LAST, after every computed
    # key above, so nothing can bypass it. URL values then have any userinfo stripped.
    merged = {**env_vars, **env_dict}
    safe = {key: merged[key] for key in GET_ENV_SAFE_KEYS if key in merged}
    # DEV opt-in (TP_AUTO_GET_ENV_EXPOSE_SECRETS=true): additionally serve the pre-fill secrets
    # so the UI Admin/User Password + CLI Token fields populate on load. Default OFF keeps the
    # TPSEC-124 default-deny for the public repo / non-dev deployments.
    if _expose_get_env_secrets():
        # Announce (once per process) that the opt-in is live and secrets are on the wire, so an
        # accidental enable on a shared/non-dev host is detectable in the logs.
        if not _EXPOSE_SECRETS_WARNED["done"]:
            print("[WARN] TP_AUTO_GET_ENV_EXPOSE_SECRETS=true: /get_env is serving Admin/User "
                  "Password + the live CP OAuth bearer UNAUTHENTICATED — intended for trusted DEV "
                  "instances only. Disable it on any shared/non-dev host.")
            _EXPOSE_SECRETS_WARNED["done"] = True
        # The CLI OAuth token is not in os.environ/ENV by default; re-fetch it on demand (this
        # is the fetch TPSEC-124 removed — re-enabled ONLY under the opt-in flag).
        if not merged.get("TIBCOP_CLI_OAUTH_TOKEN"):
            try:
                token = Helper.get_auto_token()
                if token:
                    merged["TIBCOP_CLI_OAUTH_TOKEN"] = token
            except Exception as e:
                print(f"[WARN] Failed to get auto token for /get_env: {e}")
        for key in GET_ENV_SECRET_KEYS:
            if merged.get(key):
                safe[key] = merged[key]
    for key in _GET_ENV_URL_KEYS:
        if key in safe:
            safe[key] = _strip_url_userinfo(safe[key])
    return jsonify(safe)

@app.route('/upload', methods=['POST'])
def upload_file():
    file = request.files.get('file')
    upload_folder = Util.get_upload_folder()
    os.makedirs(upload_folder, exist_ok=True)
    if file:
        # Sanitize the client-supplied filename to prevent path traversal /
        # absolute-path writes (TPSEC-128 / finding f025). The raw file.filename
        # is attacker-controlled: os.path.splitext preserves directory separators,
        # so "../../etc/cron.d/evil.sh" or an absolute path would escape
        # upload_folder via os.path.join. secure_filename strips directory
        # components, parent references, and leading drive/root markers.
        raw_name = file.filename or ""
        if not raw_name.strip():
            return jsonify({'message': 'No filename provided'}), 400
        # Take the extension from the ORIGINAL name, then allowlist it. Deriving
        # the extension from the secure_filename() output loses it for non-ASCII
        # names (secure_filename ASCII-strips, so "名字.flogo" -> "flogo" and the
        # ".flogo" is gone), which broke filetype classification / activation-zip
        # extraction for CJK app names. Allowlisting the raw extension keeps that
        # working without letting an attacker smuggle back an arbitrary extension.
        raw_ext = os.path.splitext(raw_name)[1].lower()
        ext = raw_ext if raw_ext in ALLOWED_UPLOAD_EXTENSIONS else ""
        # Sanitize the stem to strip any directory components / traversal, and
        # fall back to a safe default when secure_filename reduces it to nothing.
        original_filename = os.path.splitext(secure_filename(raw_name))[0] or "upload"
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        safe_name = f"{original_filename}_{timestamp}{ext}"
        save_path = os.path.join(upload_folder, safe_name)
        # Defense in depth: ensure the resolved path never escapes upload_folder.
        # Same containment predicate as the zip-slip guard (Helper.is_within).
        if not Helper.is_within(upload_folder, save_path):
            return jsonify({'message': 'Invalid or unsafe filename'}), 400
        file.save(save_path)

        # Determine file type based on extension
        filetype = UPLOAD_EXTENSION_FILETYPE.get(ext, 'UNKNOWN')
        if filetype == 'ACTIVATION':
            # Activation license zip: extract the .bin to upload/license-file.bin
            if not Helper.extract_activation_license(save_path):
                return jsonify({'message': 'Failed to extract license file from activation zip'}), 400

        return jsonify({
            'message': 'Upload successful',
            'filename': safe_name,
            'filetype': filetype
        })
    else:
        return jsonify({'message': 'No file uploaded'})

@app.route('/save-deploy-config', methods=['POST'])
def save_deploy_config():
    try:
        data = request.get_json()
        config_content = data.get('config')

        if not config_content:
            return jsonify({'error': 'No config provided'}), 400

        upload_folder = Util.get_upload_folder()
        os.makedirs(upload_folder, exist_ok=True)

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"deploy_config_{timestamp}.json"
        save_path = os.path.join(upload_folder, filename)

        with open(save_path, 'w') as f:
            f.write(config_content)

        return jsonify({
            'message': 'Config saved successfully',
            'filename': save_path
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/save-bwce-payload', methods=['POST'])
def save_bwce_payload():
    """Save user-edited JSON content to bwce-payload.json"""
    try:
        data = request.get_json()
        config_content = data.get('config')

        if not config_content:
            return jsonify({'success': False, 'message': 'No config provided'}), 400

        # Validate JSON format
        try:

            json.loads(config_content)
        except json.JSONDecodeError as e:
            return jsonify({'success': False, 'message': f'Invalid JSON: {str(e)}'}), 400

        upload_folder = Util.get_upload_folder()
        os.makedirs(upload_folder, exist_ok=True)

        # Save to bwce-payload.json (overwrite)
        payload_file = os.path.join(upload_folder, 'bwce-payload.json')
        with open(payload_file, 'w') as f:
            f.write(config_content)

        print(f"[INFO] Updated {payload_file} with user edits")

        return jsonify({
            'success': True,
            'message': 'BWCE payload saved successfully',
            'filename': payload_file
        })
    except Exception as e:
        print(f"[ERROR] Failed to save bwce-payload.json: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/save-flogo-payload', methods=['POST'])
def save_flogo_payload():
    """Save user-edited JSON content to flogo-payload.json"""
    try:
        data = request.get_json()
        config_content = data.get('config')

        if not config_content:
            return jsonify({'success': False, 'message': 'No config provided'}), 400

        # Validate JSON format
        try:

            json.loads(config_content)
        except json.JSONDecodeError as e:
            return jsonify({'success': False, 'message': f'Invalid JSON: {str(e)}'}), 400

        upload_folder = Util.get_upload_folder()
        os.makedirs(upload_folder, exist_ok=True)

        # Save to flogo-payload.json (overwrite)
        payload_file = os.path.join(upload_folder, 'flogo-payload.json')
        with open(payload_file, 'w') as f:
            f.write(config_content)

        print(f"[INFO] Updated {payload_file} with user edits")

        return jsonify({
            'success': True,
            'message': 'Flogo payload saved successfully',
            'filename': payload_file
        })
    except Exception as e:
        print(f"[ERROR] Failed to save flogo-payload.json: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/save-bw5ce-payload', methods=['POST'])
def save_bw5ce_payload():
    """Save user-edited JSON content to bw5ce-payload.json"""
    try:
        data = request.get_json()
        config_content = data.get('config')

        if not config_content:
            return jsonify({'success': False, 'message': 'No config provided'}), 400

        # Validate JSON format
        try:

            json.loads(config_content)
        except json.JSONDecodeError as e:
            return jsonify({'success': False, 'message': f'Invalid JSON: {str(e)}'}), 400

        upload_folder = Util.get_upload_folder()
        os.makedirs(upload_folder, exist_ok=True)

        # Save to bw5ce-payload.json (overwrite)
        payload_file = os.path.join(upload_folder, 'bw5ce-payload.json')
        with open(payload_file, 'w') as f:
            f.write(config_content)

        print(f"[INFO] Updated {payload_file} with user edits")

        return jsonify({
            'success': True,
            'message': 'BW5CE payload saved successfully',
            'filename': payload_file
        })
    except Exception as e:
        print(f"[ERROR] Failed to save bw5ce-payload.json: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3120)

