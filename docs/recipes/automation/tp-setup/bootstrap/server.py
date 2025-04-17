import subprocess
import sys
import os
import re
import time
from flask import Flask, render_template, Response, request, jsonify
from typing import Optional

app = Flask(__name__, template_folder="templates")
app.config['TEMPLATES_AUTO_RELOAD'] = True

process: Optional[subprocess.Popen] = None
@app.route('/')
def home():
    """ Render the main HTML page """
    return render_template('index.html')

@app.route('/get-kube-config')
def get_kube_config():
    kube_config_dir = os.path.expanduser("~/.kube")
    kube_config_map = {}

    if os.path.exists(kube_config_dir):
        for f in os.listdir(kube_config_dir):
            if f.startswith("ins-") and f.endswith(".yaml"):
                ip_address = f[4:-5]  # get IP Address from filename
                kube_config_map[ip_address] = os.path.join(kube_config_dir, f)

    return jsonify(kube_config_map)

@app.route('/stop-script')
def stop_script():
    """ Stop the currently running script """
    global process

    if process is not None:  # Ensure the process is assigned
        if process.poll() is None:  # Ensure the process is running
            print(f"[INFO] Stopping process (PID: {process.pid})...")
            process.terminate()  # Try to terminate gracefully
            try:
                process.wait(timeout=2)  # Wait up to 2 seconds
            except subprocess.TimeoutExpired:
                process.kill()  # Force kill if termination fails
            process = None  # Reset the process after stopping
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
    if is_clean_report == "true":
        report_folder = os.path.join(os.getcwd(), "report")
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
    for key, value in request.args.items():
        if key != "case":
            env_vars[key] = value

    print("Environment Variables Set:")
    for key, value in os.environ.items():
        if key in request.args:
            print(f"{key} = {value}")

    def generate():
        global process
        # Start the script using unbuffered output
        print(f'{sys.executable}, "-u", "-m", {auto_case}')
        process = subprocess.Popen(
            [sys.executable, "-u", "-m", auto_case],  # `-u` ensures unbuffered output
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env_vars
        )

        # Stream output line by line
        try:
            ansi_escape = re.compile(r'\x1B[@-_][0-?]*[ -/]*[@-~]')
            yield '<pre>\n'
            for line in iter(lambda: process.stdout.readline() if process and process.poll() is None else None, None):
                if line and line.strip():
                    clean_line = ansi_escape.sub('', line)      # Remove ANSI escape codes, remove color codes
                    yield clean_line.strip() + '\n'
            yield '</pre>\n'

            if process:
                process.stdout.close()
                process.wait()

        except Exception as e:
            print(f"[ERROR] Exception in generate(): {e}")

    return Response(generate(), content_type='text/html; charset=utf-8')

@app.route('/get_env')
def get_env():
    from utils.env import ENV
    env_dict = {
        key: getattr(ENV, key)
        for key in dir(ENV)
        if not key.startswith("_") and not callable(getattr(ENV, key))
    }
    return jsonify(env_dict)

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

