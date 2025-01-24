import subprocess
import os
import sys
import json

from color_logger import ColorLogger

# do not import env.py or util.py in this file
class Helper:
    @staticmethod
    def is_headless():
        # headless mode is enabled in docker
        if os.path.exists("/.dockerenv"):
            return True
        return os.environ.get("HEADLESS", "true").lower() == "true"

    @staticmethod
    def download_file(file_obj, filename):
        """
        Downloads a file and saves it to the 'downloads' directory.

        Args:
            file_obj: The content of the file to be saved. It should have a `save_as` method.
            filename (str): The name of the file to be saved.

        Returns:
            str: The path to the saved file.
        """
        # Create 'downloads' folder if it does not exist
        steps_dir = os.path.join(os.getcwd(), "downloads")
        os.makedirs(steps_dir, exist_ok=True)
        # Define the full file path
        file_path = os.path.join(steps_dir, filename)
        # Save the file content to the specified path
        file_obj.save_as(file_path)
        return file_path

    @staticmethod
    def run_shell_file(script_path):
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
    def get_command_output(command):
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
        return Helper.get_command_output("kubectl get secret -n elastic-system dp-config-es-es-elastic-user -o=jsonpath='{.data.elastic}' | base64 --decode; echo")

    @staticmethod
    def get_cp_version():
        return Helper.get_command_output("helm ls -A | grep platform-base | awk '{print $9}' | awk -F 'platform-base-' '{print $2}' | cut -d'.' -f1,2")

    @staticmethod
    def get_storage_class():
        output = Helper.get_command_output("kubectl get sc")
        if "hostpath" in output:
            return "hostpath"
        elif "standard" in output:
            return "standard"
        else:
            return ""

    @staticmethod
    def get_app_name(app_file_name):
        file_path = os.path.join(os.path.dirname(__file__), app_file_name)
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
