#  Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary

import subprocess
import sys
import os
import re
import time
import shutil
import uuid
from flask_cors import CORS
from flask import Flask, render_template, Response, request, jsonify
from typing import Dict

app = Flask(__name__, template_folder="templates")
HEADER_ONE_CLICK_JOB_ID = "one_click_job_id"
CORS(app, expose_headers=[HEADER_ONE_CLICK_JOB_ID])
app.config['TEMPLATES_AUTO_RELOAD'] = True

running_processes: Dict[str, subprocess.Popen] = {}
@app.route('/')
def home():
    """ Render the main HTML page """
    return render_template('index.html')

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

@app.route('/run-script')
def run_script():
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
    env_vars = os.environ.copy()
    env_vars["PYTHONIOENCODING"] = "utf-8"
    for key, value in request.args.items():
        if key != "case":
            env_vars[key] = value

    print("Environment Variables Set:")
    for key, value in os.environ.items():
        if key in request.args:
            print(f"{key} = {value}")

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
            ansi_escape = re.compile(r'\x1B[@-_][0-?]*[ -/]*[@-~]')
            yield '<pre>\n'
            for line in iter(lambda: process.stdout.readline() if process and process.poll() is None else None, None):
                if line and line.strip():
                    decoded_line = line.decode("utf-8", errors="replace")
                    clean_line = ansi_escape.sub('', decoded_line)      # Remove ANSI escape codes, remove color codes
                    yield clean_line.strip() + '\n'
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

@app.route('/get_env')
def get_env():
    from utils.env import ENV
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
    UPLOAD_FOLDER = 'upload'
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    if file:
        original_filename = os.path.splitext(file.filename)[0]
        ext = os.path.splitext(file.filename)[1]
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        safe_name = f"{original_filename}_{timestamp}{ext}"
        save_path = os.path.join(UPLOAD_FOLDER, safe_name)
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

