#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary

import subprocess
import sys
import os
import time
import shutil
import uuid
from flask_cors import CORS
from flask import Flask, render_template, Response, request, jsonify, stream_with_context
from typing import Dict

from utils.streaming_runner import StreamingRunner
from utils.tibcop_cli import TibcopCliHandler
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
            env_vars[key] = value

    env_vars_to_print = {}
    for key in request_args:
        if key in os.environ:
            env_vars_to_print[key] = os.environ[key]

    if env_vars_to_print:
        print("Environment Variables Set:")
        for key, value in env_vars_to_print.items():
            print(f"{key} = {value}")
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
    other_args = request.args.get('TIBCOP_CLI_OTHER_ARGS')
    if not auto_case:
        return "Missing 'case' parameter", 400

    env_vars = set_env_vars_from_request(request.args, False)
    cli_handler = TibcopCliHandler(env_vars)

    case_function_map = {
        "tplatform:list-dataplanes": lambda: cli_handler.tplatform_list_dataplane(other_args=other_args),
        "tplatform:register-k8s-dataplane": lambda: cli_handler.tplatform_register_k8s_dataplane(dp_name, other_args=other_args),
        "tplatform:unregister-dataplane": lambda: cli_handler.tplatform_unregister_dataplane(dp_name, other_args=other_args),
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

    merged = {**env_vars, **env_dict}
    return jsonify(merged)

@app.route('/upload', methods=['POST'])
def upload_file():
    file = request.files.get('file')
    upload_folder = 'upload'
    os.makedirs(upload_folder, exist_ok=True)
    if file:
        original_filename = os.path.splitext(file.filename)[0]
        ext = os.path.splitext(file.filename)[1]
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        safe_name = f"{original_filename}_{timestamp}{ext}"
        save_path = os.path.join(upload_folder, safe_name)
        file.save(save_path)

        return jsonify({
            'message': 'Upload successful',
            'filename': safe_name,
            'filetype': 'BWCE' if ext == '.ear' else 'FLOGO'
        })
    else:
        return jsonify({'message': 'No file uploaded'})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3120)

