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
import yaml
from pathlib import Path

from utils.color_logger import ColorLogger

# Fixed prefix prepended to every o11y Elasticsearch log index, on BOTH the UI
# wizard and the CLI/API path. Single source of truth so a future change is one
# edit — used by page_object/po_dp_config.py, po_bmdp_config.py, api_object/resources.py.
O11Y_LOG_INDEX_PREFIX = "user-app-"

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
            env_vars = {
                **Helper.get_env_vars(),
                **(custom_env_dict or {})
            }
            if platform.system() == "Windows":
                bash_path = Helper.get_windows_bash()
                print(f"Run Windows command: {bash_path} -c {script_path}")
                command = [bash_path, script_path]
                # Disable MSYS (Git Bash) automatic Unix->Windows path conversion so that
                # argument values beginning with '/' are passed through verbatim. Otherwise a
                # helm '--set ...accessKey=/<base64>' whose key starts with '/' is mistaken for
                # a Unix path and rewritten to 'accessKey=C:/Program Files/Git/<base64>',
                # corrupting the tp-tibtunnel access key and breaking the DataPlane tunnel
                # (PCP-20701). Scripts that must hand a Unix path to a native Windows exe
                # convert it explicitly with `cygpath -w` (see the self-signed cert secret).
                env_vars["MSYS_NO_PATHCONV"] = "1"
                env_vars["MSYS2_ARG_CONV_EXCL"] = "*"
            # Execute the shell script using subprocess
            print(f"Running script: {script_path}")
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
                sys.exit(1)  # non-zero so a bad kubeconfig is a failure, not a false-green success

            env_vars["KUBECONFIG"] = tp_auto_kubeconfig
        # TPSEC-163: validate the EFFECTIVE kubeconfig (set via TP_AUTO_KUBECONFIG above, or a
        # pre-existing / request-injected KUBECONFIG) before it is handed to kubectl/helm, so an
        # attacker-controllable kubeconfig cannot trigger a credential-plugin exec RCE.
        effective_kubeconfig = env_vars.get("KUBECONFIG")
        if effective_kubeconfig:
            Helper._validate_kubeconfig(effective_kubeconfig)
        return env_vars

    @staticmethod
    def _validate_kubeconfig(kubeconfig_value):
        """TPSEC-163: refuse an attacker-controllable kubeconfig before it becomes KUBECONFIG.

        KUBECONFIG may be an os.pathsep-separated LIST of files that kubectl/helm MERGE, so
        every existing component is validated (a single-path value is a one-element list).
        Two layered, fail-closed controls (ColorLogger.error + sys.exit(1) so a refusal is a
        non-zero failure, not a false-green success):
          A. reject a component resolving inside the unauthenticated-writable upload folder;
          B. reject a component declaring a credential-plugin that executes a command
             (users[].user.exec, or the legacy users[].user.auth-provider cmd-path).
        A missing component is skipped (it cannot exec; kubectl ignores/errs on it), so a stale
        bare KUBECONFIG is not newly hard-exited. Malformed YAML / shape fails closed.

        Scope: this is the sink for /run-gui-script and every Helper kubectl/helm call (and the
        MCP automation_executor, which spawns the same case modules). The bare-KUBECONFIG
        request-param denylist and the /run-cli-script env restriction are TPSEC-134 (#393);
        /upload path traversal is TPSEC-128. Exec-based (cloud) kubeconfigs are unsupported here.
        """
        # A KUBECONFIG value never legitimately contains a double-quote in this automation. On
        # Windows, Go's filepath.SplitList (used by kubectl/client-go) strips surrounding quotes
        # and treats a quoted os.pathsep as non-separating — which Python's str.split does not
        # mirror — so a quoted value could be validated differently than kubectl parses it. Fail
        # closed on any quote to remove that parsing-differential bypass on all platforms. (On
        # Linux, the deploy target, unquoted split(os.pathsep) already matches SplitList exactly.)
        if '"' in kubeconfig_value:
            ColorLogger.error(f"Refusing KUBECONFIG containing a quote character: {kubeconfig_value}")
            sys.exit(1)
        # Do NOT strip components: kubectl/helm use each os.pathsep-separated entry as a
        # VERBATIM path (Go filepath.SplitList does not trim), so stripping here would let a
        # file named with surrounding whitespace be validated as a different (missing) path
        # while kubectl opens the real one. Skip only truly-empty entries (kubectl ignores those).
        for component in kubeconfig_value.split(os.pathsep):
            if component:
                Helper._validate_kubeconfig_file(component)

    @staticmethod
    def _validate_kubeconfig_file(path):
        real = os.path.realpath(path)
        if not os.path.exists(real):
            return
        real_path = Path(real)
        # Control A (defense-in-depth) first: a path check, before parsing any file content.
        upload_dir = Path(os.path.realpath(Path(__file__).resolve().parent.parent / "upload"))
        if real_path == upload_dir or upload_dir in real_path.parents:
            ColorLogger.error(
                f"Refusing kubeconfig inside the upload folder: {path}. "
                f"TP_AUTO_KUBECONFIG/KUBECONFIG must not point into {upload_dir}."
            )
            sys.exit(1)
        # Control B (mandatory): reject credential-plugin command execution, wherever the file lives.
        try:
            with open(real, "r", encoding="utf-8") as fh:
                doc = yaml.safe_load(fh)
        except Exception as e:
            ColorLogger.error(f"Refusing unparseable kubeconfig {path}: {e}")
            sys.exit(1)
        if not isinstance(doc, dict):
            ColorLogger.error(f"Refusing malformed kubeconfig (not a mapping): {path}")
            sys.exit(1)
        users = doc.get("users")
        if users is not None and not isinstance(users, list):
            ColorLogger.error(f"Refusing malformed kubeconfig ('users' is not a list): {path}")
            sys.exit(1)
        for entry in (users or []):
            if not isinstance(entry, dict):
                ColorLogger.error(f"Refusing malformed kubeconfig ('users' entry is not a mapping): {path}")
                sys.exit(1)
            user = entry.get("user")
            if user is None:
                continue
            if not isinstance(user, dict):
                ColorLogger.error(f"Refusing malformed kubeconfig ('user' is not a mapping): {path}")
                sys.exit(1)
            if "exec" in user or "auth-provider" in user:
                ColorLogger.error(
                    f"Refusing kubeconfig with a credential-plugin (exec/auth-provider): {path}. "
                    f"Exec-based kubeconfigs are not supported (potential command execution)."
                )
                sys.exit(1)

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
    def is_within(base, target):
        """Return True iff `target` resolves inside `base` (both realpath'd first).

        Single source of truth for the TPSEC-128 containment guard used by BOTH the
        /upload save-path check (server.py) and the zip-slip member check below, so the
        security-critical predicate can't drift between the two. A cross-drive/-root
        pair (e.g. Windows "C:\\.." vs "D:\\") makes os.path.commonpath raise
        ValueError — treat that as "outside". Lives on Helper (not Util) because
        helper.py must not import util.py (util already imports helper).
        """
        real_base = os.path.realpath(base)
        real_target = os.path.realpath(target)
        try:
            return os.path.commonpath([real_base, real_target]) == real_base
        except ValueError:
            return False

    @staticmethod
    def extract_activation_license(zip_path):
        """Unzip an activation zip and rename the contained .bin to license-file.bin
        (placed next to the zip). Returns True on success."""
        upload_dir = os.path.dirname(zip_path)
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # Guard against zip-slip (TPSEC-128): ZipFile.extractall() blindly
                # honors entry names, so a member like "../../etc/cron.d/evil" or an
                # absolute path escapes upload_dir and writes an arbitrary file. Verify
                # every member resolves inside upload_dir before extracting anything.
                real_dir = os.path.realpath(upload_dir)
                for info in zip_ref.infolist():
                    # Reject symlink members (S_IFLNK in the top 16 bits of external_attr).
                    # Python's zipfile currently extracts these as regular files (it does
                    # not restore symlinks), but rejecting them keeps the guard correct
                    # regardless of the extractor and blocks the symlink-then-write-through
                    # escape a symlink-honoring extractor would allow.
                    if (info.external_attr >> 16) & 0o170000 == 0o120000:
                        # !r quotes/escapes the attacker-controlled member name so an
                        # embedded newline/control char cannot forge or split log lines.
                        ColorLogger.error(f"Refusing to extract symlink zip entry: {info.filename!r}")
                        return False
                    if not Helper.is_within(real_dir, os.path.join(real_dir, info.filename)):
                        ColorLogger.error(f"Refusing to extract unsafe zip entry (path traversal): {info.filename!r}")
                        return False
                zip_ref.extractall(real_dir)

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
