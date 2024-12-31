import subprocess
import os
import sys

from color_logger import ColorLogger

class Util:
    @staticmethod
    def dp_step_file(filename=None, step=1):
        filename = f"{filename}_{step}.sh"
        # create steps folder if not exist
        steps_dir = os.path.join(os.getcwd(), "steps")
        os.makedirs(steps_dir, exist_ok=True)
        return os.path.join(steps_dir, filename)

    @staticmethod
    def run_shell_script(script_path):
        # Check if the script file exists
        if not os.path.exists(script_path):
            raise FileNotFoundError(f"Script file not found: {script_path}")

        # Set execute permissions for the script
        os.chmod(script_path, 0o755)

        try:
            # Execute the shell script using subprocess
            result = subprocess.run(
                [script_path],             # Path to the script
                shell=False,               # Run without invoking the shell for added security
                check=True,                # Raise an error if the script exits with a non-zero status
                capture_output=True,       # Capture standard output and standard error
                text=True                  # Decode the output as text (not bytes)
            )
            # Print the script's standard output
            print(f"Script output:\n{result.stdout}")
        except subprocess.CalledProcessError as e:
            # Handle errors during script execution
            print(f"Error while executing script: {e}")
            print(f"Script stderr:\n{e.stderr}")
        except Exception as e:
            # Handle any unexpected exceptions
            print(f"An unexpected error occurred: {e}")

    @staticmethod
    def get_command_output_with_error(command):
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()  # Return standard output
        except subprocess.CalledProcessError as e:
            print(f"Command failed with error: {e.stderr.strip()}")
            return None

    @staticmethod
    def get_elastic_password():
        return Util.get_command_output_with_error("kubectl get secret -n elastic-system dp-config-es-es-elastic-user -o=jsonpath='{.data.elastic}' | base64 --decode; echo")

    @staticmethod
    def get_resource_name():
        output = Util.get_command_output_with_error("kubectl get sc")
        if "hostpath" in output:
            return "hostpath"
        elif "standard" in output:
            return "standard"
        else:
            return ""

    @staticmethod
    def is_headless():
        # headless mode is enabled in docker
        if os.path.exists("/.dockerenv"):
            return True

        is_headless = os.environ.get("HEADLESS", "true")

        return is_headless.lower() == "true"

    @staticmethod
    def get_env_info():
        github_token = os.environ.get("GITHUB_TOKEN", "")
        host_prefix = os.environ.get("DP_HOST_PREFIX", "cp-sub1")
        user_email = os.environ.get("DP_USER_EMAIL", "cp-sub1@tibco.com")
        user_password = os.environ.get("DP_USER_PASSWORD", "Tibco@123")
        admin_email = os.environ.get("CP_ADMIN_EMAIL", "cp-test@tibco.com")
        admin_password = os.environ.get("GUI_CP_ADMIN_PASSWORD", "Tibco@123")
        if not github_token:
            ColorLogger.warning(f"GITHUB_TOKEN is not set, DataPlane Helm Chart Repository Only support for 'Global Repository'.")
        if not os.environ.get("DP_HOST_PREFIX"):
            ColorLogger.warning(f"DP_HOST_PREFIX is not set, will use default: {host_prefix}")
        if not os.environ.get("DP_USER_EMAIL"):
            ColorLogger.warning(f"DP_USER_EMAIL is not set, will use default: {user_email}")
        if not os.environ.get("DP_USER_PASSWORD"):
            ColorLogger.warning(f"DP_USER_PASSWORD is not set, will use default: {user_password}")
        if not os.environ.get("CP_ADMIN_EMAIL"):
            ColorLogger.warning(f"CP_ADMIN_EMAIL is not set, will use default: {admin_email}")
        if not os.environ.get("GUI_CP_ADMIN_PASSWORD"):
            ColorLogger.warning(f"GUI_CP_ADMIN_PASSWORD is not set, will use default: {admin_password}")

        return github_token, host_prefix, user_email, user_password, admin_email, admin_password
