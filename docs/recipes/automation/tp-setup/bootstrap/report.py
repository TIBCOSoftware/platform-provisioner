import os
import subprocess
from env import ENV
import json

class ReportYamlHandler:
    def __init__(self, env):
        self.yaml_folder = env.TP_AUTO_REPORT_PATH
        self.yaml_file_path = os.path.join(self.yaml_folder, env.TP_AUTO_REPORT_YAML_FILE)
        os.makedirs(self.yaml_folder, exist_ok=True)

        if not os.path.exists(self.yaml_file_path):
            with open(self.yaml_file_path, "w") as f:
                f.write("\n")

    def set(self, key, value=None):
        command = key if value is None else f'{key}={self.format_value(value)}'
        print(f"Setting YAML key-value pair: {command}")
        self._run_yq_command(["-i", command])

    def get(self, key):
        """Retrieve the value of a given key from the YAML file."""
        output = self._run_yq_command([key])
        if not output or output.strip() == "null":
            return None
        return output.strip()

    def set_dataplane(self, dp_name):
        if dp_name in self.get_dataplanes():
            return
        self.set(f"""
            .dataPlane |= (
                map(select(.name != "{dp_name}")) + [{{"name": "{dp_name}"}} | select(map(.name))]
            )
        """)

    def get_dataplanes(self):
        dps = self.get("(.dataPlane[].name)")
        return dps.split("\n") if dps else []

    def set_dataplane_info(self, dp_name, dp_key, dp_value):
        dp_value = self.format_value(dp_value)
        self.set(f"""
            (.dataPlane[] 
                | select(.name == "{dp_name}") 
            ) += {{"{dp_key}": {dp_value}}}
        """)

    def get_dataplane_info(self, dp_name, dp_key):
        return self.get(f"""
            (.dataPlane[] 
               | select(.name == "{dp_name}").{dp_key}
            )
        """)

    def set_capability(self, dp_name, capability):
        if dp_name in self.get_capabilities(dp_name):
            return
        self.set(f"""
            (.dataPlane[] 
                | select(.name == "{dp_name}") 
                | .capability
            ) |= (map(select(.name != "{capability}")) + [{{"name": "{capability}"}}])
        """)

    def get_capabilities(self, dp_name):
        capabilities = self.get(f"""
            (.dataPlane[] 
                | select(.name == "{dp_name}") 
                | .capability[].name
            )
        """)
        return capabilities.split("\n") if capabilities else []

    def set_capability_info(self, dp_name, capability, app_key, app_value):
        app_value = self.format_value(app_value)
        self.set(f"""
            (.dataPlane[] 
                | select(.name == "{dp_name}") 
                | .capability[] 
                | select(.name == "{capability}")
            ) += {{"{app_key}": {app_value}}}
        """)

    def set_capability_app(self, dp_name, capability, app_name):
        if app_name in self.get_capability_apps(dp_name, capability):
            return
        self.set(f"""
           (.dataPlane[] 
               | select(.name == "{dp_name}") 
               | .capability[] 
               | select(.name == "{capability}").app
           ) |= (map(select(.name != "{app_name}")) + [{{"name": "{app_name}"}}])
        """)

    def get_capability_apps(self, dp_name, capability):
        apps = self.get(f"""
           (.dataPlane[] 
               | select(.name == "{dp_name}") 
               | .capability[] 
               | select(.name == "{capability}").app[].name
           )
        """)
        return apps.split("\n") if apps else []

    def set_capability_app_info(self, dp_name, capability, app_name, app_key, app_value):
        app_value = self.format_value(app_value)
        self.set(f"""
            (.dataPlane[]
                | select(.name == "{dp_name}")
                | .capability[]
                | select(.name == "{capability}")
                | .app[]
                | select(.name == "{app_name}")
            ) |= . + {{"{app_key}": {app_value}}}
        """)

    def get_capability_app_info(self, dp_name, capability, app_name, app_key):
        return self.get(f"""
            (.dataPlane[]
                | select(.name == "{dp_name}")
                | .capability[]
                | select(.name == "{capability}")
                | .app[]
                | select(.name == "{app_name}").{app_key}
            )
        """)

    @staticmethod
    def format_value(value):
        if isinstance(value, bool):
            value = "true" if value else "false"
        elif isinstance(value, (int, float)):
            value = str(value)
        elif isinstance(value, str):
            # Use json.dumps to ensure the string format is correct (with quotes)
            value = json.dumps(value)
        elif isinstance(value, list):
            value = "[" + ", ".join(json.dumps(item) for item in value) + "]"
        elif isinstance(value, dict):
            # Use json.dumps to ensure the string format is correct (with quotes)
            value = json.dumps(value)

        return value

    def sort_yaml_order(self):
        self.set(f"""
            {{"ENV": .ENV, "dataPlane": .dataPlane}}
        """)
        self.set(f"""
            .dataPlane[] |= (
              {{"name": .name, "storage": .storage, "o11yConfig": .o11yConfig, "nginx-flogo": ."nginx-flogo", "nginx-bwce": ."nginx-bwce", "capability": .capability}}
            )
        """)


    def _run_yq_command(self, args):
        """Run a yq command with the given arguments."""
        try:
            result = subprocess.run(
                ["yq", *args, self.yaml_file_path],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            print(f"Error running yq command: {e}")
            return None

ReportYaml = ReportYamlHandler(ENV)
