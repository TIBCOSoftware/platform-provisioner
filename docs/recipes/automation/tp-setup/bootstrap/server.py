#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary

import subprocess
import sys
import os
import time
import shutil
import uuid
from flask_cors import CORS
from flask import Flask, render_template, Response, request, jsonify, stream_with_context, send_from_directory
from typing import Dict

from utils.streaming_runner import StreamingRunner
from cli_object.facade import TibcopCLI
from utils.util import Util
from utils.env import ENV
from utils.helper import Helper

app = Flask(__name__, template_folder="templates")
HEADER_ONE_CLICK_JOB_ID = "one_click_job_id"
CORS(app, expose_headers=[HEADER_ONE_CLICK_JOB_ID])
app.config['TEMPLATES_AUTO_RELOAD'] = True

running_processes: Dict[str, subprocess.Popen] = {}

def set_env_vars_from_request(request_args, include_system_env=True):
    # Set request parameters as environment variables
    if include_system_env:
        env_vars = os.environ.copy()
    else:
        env_vars = {}

    env_vars["PYTHONIOENCODING"] = "utf-8"
    for key, value in request_args.items():
        if key != "case":
            # Only override if the value is not empty (preserve system env vars)
            if value:
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
    token = Helper.get_auto_token()

    base_url = f"https://{ENV.DP_HOST_PREFIX}.{ENV.TP_AUTO_CP_SERVICE_DNS_DOMAIN}"
    url = base_url + api_path
    print(f"[INFO] Calling CP API: {api_method} {url}", api_data)
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
    activation_server_url = request.args.get('TIBCOP_CLI_ACTIVATION_SERVER_URL')
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

    # Include system environment variables to get TIBCOP_CLI_CPURL and TIBCOP_CLI_OAUTH_TOKEN
    env_vars = set_env_vars_from_request(request.args, True)
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
            None, devhub_name, k8s_secret, False, other_args
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
        "create-activation-server": lambda: cli_handler.resource.create_activation_server(
            dp_name, resource_name, activation_server_url or None, "DATAPLANE", None, None, other_args
        ),
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
        return f"{auto_case} not found", 404

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
    # Add CLI default values (only if not already set in environment)
    # Priority: 1) Environment variable, 2) k8s secret/TP_AUTO_LOGIN_URL fallback
    if not env_vars.get("TIBCOP_CLI_OAUTH_TOKEN"):
        try:
            # Get OAuth token from k8s secret as fallback
            token = Helper.get_auto_token()
            if token:
                env_dict["TIBCOP_CLI_OAUTH_TOKEN"] = token
        except Exception as e:
            print(f"[WARN] Failed to get auto token: {e}")

    if not env_vars.get("TIBCOP_CLI_CPURL"):
        # Extract domain from TP_AUTO_LOGIN_URL for TIBCOP_CLI_CPURL as fallback
        cp_url = env_dict.get("TP_AUTO_LOGIN_URL", "")
        if cp_url:
            # Extract protocol and domain (e.g., "https://cp.example.com/path" -> "https://cp.example.com")
            import re
            match = re.match(r'^(https?://[^/]+)', cp_url)
            if match:
                env_dict["TIBCOP_CLI_CPURL"] = match.group(1)

    merged = {**env_vars, **env_dict}
    return jsonify(merged)

@app.route('/upload', methods=['POST'])
def upload_file():
    file = request.files.get('file')
    upload_folder = Util.get_upload_folder()
    os.makedirs(upload_folder, exist_ok=True)
    if file:
        original_filename = os.path.splitext(file.filename)[0]
        ext = os.path.splitext(file.filename)[1]
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        safe_name = f"{original_filename}_{timestamp}{ext}"
        save_path = os.path.join(upload_folder, safe_name)
        file.save(save_path)

        # Determine file type based on extension
        if ext == '.ear':
            filetype = 'BWCE'
        elif ext in ['.json', '.flogo']:
            filetype = 'FLOGO'
        else:
            filetype = 'UNKNOWN'

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
            import json
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
            import json
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
            import json
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

