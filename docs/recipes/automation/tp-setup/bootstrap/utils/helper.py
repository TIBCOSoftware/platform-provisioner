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
import base64
import subprocess
import os
import sys
import json
import platform
import zipfile
from pathlib import Path

from utils.color_logger import ColorLogger

# do not import env.py or util.py in this file
class Helper:
    @staticmethod
    def is_headless():
        # headless mode is enabled in docker
        if os.path.exists("/.dockerenv"):
            return True
        return os.environ.get("HEADLESS", "true").lower() == "true"

    @staticmethod
    def get_windows_bash():
        bash_path = Path(r"C:\Program Files\Git\bin\bash.exe")
        if not bash_path.exists():
            ColorLogger.error(f"The git bash '{bash_path}' does not exist.")
            sys.exit()
        return bash_path

    @staticmethod
    def run_shell_file(script_path, custom_env_dict=None):
        # Check if the script file exists
        if not os.path.exists(script_path):
            raise FileNotFoundError(f"Script file not found: {script_path}")

        # Set execute permissions for the script
        os.chmod(script_path, 0o755)

        try:
            command = [script_path]
            if platform.system() == "Windows":
                bash_path = Helper.get_windows_bash()
                print(f"Run Windows command: {bash_path} -c {script_path}")
                command = [bash_path, script_path]
            # Execute the shell script using subprocess
            print(f"Running script: {script_path}")
            env_vars = {
                **Helper.get_env_vars(),
                **(custom_env_dict or {})
            }
            result = subprocess.run(
                command,             # Path to the script
                shell=False,               # Run without invoking the shell for added security
                check=True,                # Raise an error if the script exits with a non-zero status
                capture_output=True,       # Capture standard output and standard error
                text=True,                 # Decode the output as text (not bytes)
                env=env_vars
            )
            if result.stderr:
                print(f"Command stderr: {result.stderr.strip()}")
            # Print the script's standard output
            print(f"Script output:\n{result.stdout}")
            return result.stdout
        except subprocess.CalledProcessError as e:
            # Handle errors during script execution
            print(f"Error while executing script: {e}")
            print(f"Script stderr:\n{e.stderr}")
        except Exception as e:
            # Handle any unexpected exceptions
            print(f"An unexpected error occurred: {e}")
        return ""

    @staticmethod
    def get_command_output(command, is_print_cmd=False, is_print_error=True):
        if command is None or command.strip() == "":
            return None
        try:
            if platform.system() == "Windows":
                bash_path = Helper.get_windows_bash()
                if is_print_cmd:
                    print(f"Run Windows command: {bash_path} -c {command}")
                # For Windows, use '-c' to run the command
                command = [bash_path, "-c", command]
            else:
                if is_print_cmd:
                    print(f"Run command: {command}")
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                check=True,
                env=Helper.get_env_vars()
            )
            if result.stderr and is_print_error:
                print(f"Run command: {command}")
                print(f"Command stderr: {result.stderr.strip()}")
            return result.stdout.strip()  # Return standard output
        except subprocess.CalledProcessError as e:
            if is_print_error:
                print(f"Failed command: {command}")
                print(f"Command failed with error: {e.stderr.strip()}")
            return None

    @staticmethod
    def get_env_vars():
        env_vars = os.environ.copy()
        tp_auto_kubeconfig = os.environ.get("TP_AUTO_KUBECONFIG")
        if tp_auto_kubeconfig:
            tp_auto_kubeconfig = os.path.expanduser(tp_auto_kubeconfig)
            if not os.path.exists(tp_auto_kubeconfig):
                ColorLogger.error(f"TP_AUTO_KUBECONFIG does not exist: {tp_auto_kubeconfig}.")
                sys.exit()

            env_vars["KUBECONFIG"] = tp_auto_kubeconfig
        return env_vars

    @staticmethod
    def get_cp_dns_domain():
        return Helper.get_command_output("helm get values platform-base -n cp1-ns -o json 2>/dev/null | jq -r '.global.external.dnsDomain // empty' | cut -d. -f2-", is_print_error=False)

    @staticmethod
    def get_elastic_password():
        return Helper.get_command_output("kubectl get secret -n elastic-system dp-config-es-es-elastic-user -o=jsonpath='{.data.elastic}' | base64 --decode; echo", is_print_error=False)

    @staticmethod
    def get_cp_version():
        return Helper.get_command_output("helm ls -A | grep platform-base | awk '{print $9}' | awk -F 'platform-base-' '{print $2}' | cut -d'.' -f1,2", is_print_error=False)

    @staticmethod
    def get_cp_platform_bootstrap_version():
        return Helper.get_command_output(r"helm list --all-namespaces | grep platform-bootstrap | sed -n 's/.*platform-bootstrap-\(.*\)[[:space:]].*/\1/p' | sed 's/[[:space:]].*//'", is_print_error=False)

    @staticmethod
    def get_cp_platform_base_version():
        return Helper.get_command_output(r"helm list --all-namespaces | grep platform-base | sed -n 's/.*platform-base-\(.*\)[[:space:]].*/\1/p' | sed 's/[[:space:]].*//'", is_print_error=False)

    @staticmethod
    def get_all_tibco_cp_version():
        return Helper.get_command_output("helm list --all-namespaces -o json | jq -r '.[].chart' | grep tibco-cp", is_print_error=False)

    @staticmethod
    def get_node_name():
        return Helper.get_command_output("kubectl get nodes | grep ' Ready ' | awk '{print $1}' | awk -F '.' '{print $1}'", is_print_error=False)

    @staticmethod
    def get_node_ip():
        # return requests.get("https://ifconfig.me").text
        return Helper.get_command_output("curl ifconfig.me", is_print_error=False)

    @staticmethod
    def get_deployment_images(namespace):
        return Helper.get_command_output(f"kubectl get deployment -n {namespace} -o json | jq -r '.items[] | .metadata.name as $name | .spec.template.spec.containers[0].image | (split(\"/\")[-1])' | sort", is_print_error=False)

    @staticmethod
    def get_auto_token_creation():
        return Helper.get_command_output("kubectl get secret auto-token -n automation -o jsonpath='{.metadata.creationTimestamp}'", is_print_error=False)

    @staticmethod
    def get_auto_token():
        return Helper.get_command_output("kubectl get secret auto-token -n automation -o jsonpath=\"{.data['auto-token']}\" | base64 --decode", is_print_error=False)

    @staticmethod
    def get_storage_class():
        return Helper.get_command_output("kubectl get sc | awk '/\\(default\\)/ {print $1}'", is_print_error=False)

    @staticmethod
    def get_file_fullpath_in_upload_folder(file_name: str) -> str:
        return str(Path(__file__).resolve().parent.parent / "upload" / file_name)

    @staticmethod
    def extract_activation_license(zip_path):
        """Unzip an activation zip and rename the contained .bin to license-file.bin
        (placed next to the zip). Returns True on success."""
        upload_dir = os.path.dirname(zip_path)
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(upload_dir)

            # Find and rename .bin file to license-file.bin
            for item in os.listdir(upload_dir):
                if item.endswith('.bin'):
                    old_path = os.path.join(upload_dir, item)
                    new_path = os.path.join(upload_dir, 'license-file.bin')
                    os.rename(old_path, new_path)
                    return True
        except Exception as e:
            ColorLogger.error(f"Failed to unzip or process license file: {e}")
            return False

        ColorLogger.error("No .bin license file found in the uploaded activation zip.")
        return False

    @staticmethod
    def save_activation_file(base64_string, filename):
        if not base64_string or not filename:
            return False

        # remove whitespaces/newlines
        b64 = "".join(base64_string.split())

        # handle "data:application/zip;base64,xxxx"
        if "base64," in b64:
            b64 = b64.split("base64,", 1)[1]

        zip_bytes = base64.b64decode(b64, validate=True)

        out_path = str(Path(__file__).resolve().parent.parent / "upload" / filename)
        with open(out_path, "wb") as f:
            f.write(zip_bytes)

        # Unzip the file and rename .bin file to license-file.bin
        return Helper.extract_activation_license(out_path)

    @staticmethod
    def get_app_file_fullpath(app_file_name, repo="", tag=""):
        file_path = Helper.get_file_fullpath_in_upload_folder(app_file_name)

        if not os.path.isfile(file_path):
            ColorLogger.warning(f"App file not found locally: {file_path}. Attempting download from GitHub Release...")
            file_path = Helper._download_app_from_release(app_file_name, file_path, repo, tag)

        return file_path

    @staticmethod
    def resolve_github_token(secret_path="/tmp/secret-github/GITHUB_TOKEN"):
        # Mirror common-dependency/scripts/_functions.sh git_clone() token precedence:
        # env GITHUB_TOKEN first, otherwise the pipeline-mounted secret volume. This is
        # the same source/boundary as the pipeline's own git checkout, so app-asset
        # downloads reuse the token that cloned the repo (SaaS pipeline path), while
        # on-prem still relies on the env var passed via `docker run -e GITHUB_TOKEN`.
        token = os.getenv("GITHUB_TOKEN", "")
        if not token and os.path.isfile(secret_path):
            with open(secret_path) as f:
                token = f.read().strip()
        return token

    @staticmethod
    def _download_app_from_release(app_file_name, dest_path, repo="", tag=""):
        if not repo or not tag:
            ColorLogger.error("TP_AUTO_APP_RELEASE_REPO and TP_AUTO_APP_RELEASE_TAG must be set to download app files from GitHub Release.")
            sys.exit()

        # Both download branches must authenticate to private releases. The `gh` CLI
        # reads its token from the environment, so export the resolved token (env or
        # mounted secret) when GITHUB_TOKEN is not already set in the env.
        _token = Helper.resolve_github_token()
        if _token and not os.getenv("GITHUB_TOKEN"):
            os.environ["GITHUB_TOKEN"] = _token

        dest_dir = os.path.dirname(dest_path)
        os.makedirs(dest_dir, exist_ok=True)

        has_gh = Helper.get_command_output("which gh", is_print_error=False) is not None
        if has_gh:
            cmd = f"gh release download {tag} --repo {repo} --pattern {app_file_name} --dir {dest_dir}"
            ColorLogger.info(f"Downloading via gh: {cmd}")
            Helper.get_command_output(cmd, is_print_cmd=True)
        else:
            Helper._download_via_curl(repo, tag, app_file_name, dest_path)

        if not os.path.isfile(dest_path):
            ColorLogger.error(f"Failed to download '{app_file_name}' from GitHub Release {repo}@{tag}.")
            sys.exit()

        ColorLogger.success(f"Downloaded '{app_file_name}' to {dest_path}")
        return dest_path

    @staticmethod
    def _download_via_curl(repo, tag, app_file_name, dest_path):
        token = Helper.resolve_github_token()
        api_url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
        ColorLogger.info(f"Downloading via curl from GitHub Release {repo}@{tag}...")

        curl_headers = ["-H", "Accept: application/vnd.github+json"]
        if token:
            curl_headers.extend(["-H", f"Authorization: token {token}"])

        try:
            # -f: fail (non-zero exit) on HTTP errors instead of writing the error body
            # to stdout and exiting 0, which would otherwise be parsed as a valid release.
            cmd = ["curl", "-fsSL"] + curl_headers + [api_url]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            assets_json = result.stdout
        except subprocess.CalledProcessError as e:
            ColorLogger.error(f"Failed to fetch release info: {e.stderr}")
            return

        try:
            release = json.loads(assets_json)
        except json.JSONDecodeError:
            ColorLogger.error("Invalid JSON response from GitHub API")
            return

        asset_api_url = None
        for asset in release.get("assets", []):
            if asset.get("name") == app_file_name:
                asset_api_url = asset.get("url")
                break

        if not asset_api_url:
            ColorLogger.error(f"Asset '{app_file_name}' not found in release {repo}@{tag}")
            return

        ColorLogger.info(f"Downloading asset: {app_file_name} ({os.path.basename(asset_api_url)})")
        try:
            dl_headers = ["-H", "Accept: application/octet-stream"]
            if token:
                dl_headers.extend(["-H", f"Authorization: token {token}"])
            # -f: fail on HTTP errors so a 404/401 aborts with a non-zero exit instead of
            # silently writing the error body into dest_path (a corrupt JAR that would
            # then pass the downstream os.path.isfile() check and get deployed).
            cmd = ["curl", "-fsSL"] + dl_headers + ["-o", dest_path, asset_api_url]
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            ColorLogger.error(f"Failed to download asset: {e}")

    @staticmethod
    def get_app_name(app_file_name):
        file_path = Helper.get_app_file_fullpath(app_file_name)
        with open(file_path, "r") as f:
            flogo_json = json.load(f)
            app_name = flogo_json["name"]

        if app_name == "":
            ColorLogger.error(f"The app name is empty in file {file_path}.")
            sys.exit()
        return app_name

    @staticmethod
    def get_o11y_sub_name_input(dp_name, menu_name, tab_name, tab_sub_name=""):
        tab_name = tab_name if tab_sub_name == "" else f"{tab_name} {tab_sub_name}"
        tab = tab_name.lower()
        words = tab_name.split()
        if len(words) > 1:
            tab = ''.join(word[0].lower() for word in words)

        index = 1
        if dp_name == "":
            name_input = f"GLOBAL_{menu_name}-{tab}".upper()
        else:
            name_input = f"{dp_name}-{menu_name}-{tab}-{index}".lower()
        return name_input
