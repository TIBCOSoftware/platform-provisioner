## Pre-requisites
* Install pyenv and python >= 3.13 if you don't have it (Only need to run once)
* For Windows: Install [Git Bash](https://git-scm.com/downloads)

### 1. Install environment tools

#### Install uv
1. For Mac & Linux
   ```shell
   curl -fsSL https://uv.io/install.sh | sh
   ```
2. For Windows
   ```shell
   scoop install main/uv
   ```
   
#### or Install pyenv
1. For Mac & Linux
   ```shell
   curl https://pyenv.run | bash
   ```
2. For Windows
   ```shell
   git clone https://github.com/pyenv-win/pyenv-win.git "$HOME/.pyenv"
   # You can add these two lines to your ~/.bashrc or ~/.bash_profile, so that they take effect automatically every time you open Git Bash.
   export PYENV="$HOME/.pyenv/pyenv-win"
   export PATH="$PYENV/bin:$PYENV/shims:$PATH"
   ```
### 2. Install python 3.13
```shell
pyenv install 3.13
pyenv global 3.13
python --version
```

### 3. Install required packages for local development
* Set PYTHONPATH for bootstrap folder
  * For IntelliJ IDEA:
    * Right click folder `docs/recipes/automation/tp-setup/bootstrap`, then select `Mark Directory as` -> `Sources Root`
  * For Git Bash on Windows, or bash on Mac:
    * `export PYTHONPATH="$PWD/docs/recipes/automation/tp-setup/bootstrap"`

```shell
cd docs/recipes/automation/tp-setup/bootstrap

uv sync
uv run playwright install
```

## Platform Automation Hub - GUI Features

| Category                                    | Supported Features                                                                                                                                                                                                                                                                                                                                  |
|:--------------------------------------------|:----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Display Current Environment Information** | ✅ Show Control Plane `platform-bootstrap` version<br>✅ Show Control Plane `platform-base` version<br>✅ Display Mail Server URL<br>✅ Display CP Admin Server URL, Admin Email, and Password<br>✅ Display CP Server URL, User Email, and Password<br>✅ Display Elastic, Kibana, and Prometheus URLs and Credentials                                   |
| **Create a OAuth Token**                    | ✅ Support for creating OAuth Token and saving it to kubernetes secret.<br>✅ If the token only exists in the Kubernetes Secret or only in the UI, it will be deleted and a new one will be created. The token must exist in both places at the same time.                                                                                            |
| **Create a New Subscription**               | ✅ Provision a new subscription using the User Email by an Admin<br>✅ Activate the user via the `maildev` server<br>✅ Set the user's password and complete the login process                                                                                                                                                                         |
| **Configure Observability Widget**          | ✅ Automatically add widget cards for Kubernetes or Control Tower                                                                                                                                                                                                                                                                                    |
| **Configure Global Observability**          | ✅ Automatically create global Logs, Metrics, and Traces<br>✅ Support using system configuration for Metrics and Traces<br>✅ Support for config activation url                                                                                                                                                                                       |
| **Create K8S DataPlane**                    | ✅ Create the specified DataPlane<br>✅ Run `create dp` command                                                                                                                                                                                                                                                                                       |
| **Configure DataPlane Observability**       | ✅ Automatically create DataPlane-level Logs, Metrics, and Traces<br>✅ Support using system configuration for Metrics and Traces<br>✅ Support for config activation url                                                                                                                                                                              |
| **Delete DataPlane**                        | ✅ Delete the specified DataPlane<br>✅ Run `delete dp` command                                                                                                                                                                                                                                                                                       |
| **Provision Capabilities**                  | ✅ Provision BW6(BWCE) / BW5 / EMS / Flogo / Pulsar / TibcoHub                                                                                                                                                                                                                                                                                       |
| **Create and Start Applications**           | ✅ Create a BW6(BWCE)/BW5/Flogo application with a default file<br>✅ Upload a specified BW6(BWCE)/BW5/Flogo app file<br>✅ Set up application environment variables<br>✅ Configure app endpoint visibility to public<br>✅ Start the application<br>✅ Test application via Swagger API                                                                 |
| **Delete Applications**                     | ✅ Delete the specified application by name                                                                                                                                                                                                                                                                                                          |
| **DataPlane(Control Tower)**                | ✅ Create Control Tower Data Plane<br> ✅ Config Control Tower DataPlane O11y<br>✅ Deploy BW5 domain(Include rvdm, emsdm, bw6dm, emsserver)<br>✅ Auto-prefill activation server fields when selecting "Deploy BW5 domain"<br>✅ Register BW5 domain<br>✅ Delete Control Tower Data Plane<br>✅ Delete BW5 domain(Include rvdm, emsdm, bw6dm, emsserver) |
| **API Integration**                         | ✅ `/cp_api` endpoint for calling CP API directly from UI<br>✅ Supports GET, POST, DELETE methods<br>✅ Auto-handles authentication with Bearer token<br>✅ Parameters: `api_path` (e.g., `/cp/v1/dataplanes`), `api_method`, `api_data`                                                                                                               |
## Platform Automation Hub - CLI Features

The CLI features are powered by the modular `cli_object/` architecture, providing comprehensive automation capabilities via the `tibcop` CLI since version **1.8.1-auto-on-prem-jammy**.

| Category                     | Supported Features                                                                                                                                                                                              |
|:-----------------------------|:----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **DataPlane Management**     | ✅ List all DataPlanes (name, id, status)<br>✅ Register K8S DataPlane<br>✅ Unregister/Delete DataPlane<br>✅ Register Control Tower DataPlane (CTDP)                                                              |
| **Resource Management**      | ✅ List resource instances<br>✅ Create Storage resource<br>✅ Create Ingress resource<br>✅ Create Activation Server resource<br>✅ Delete resource instance                                                        |
| **Capability Management**    | ✅ List capabilities<br>✅ Provision capabilities (BWCE, Flogo, BW5CE, EMS, Pulsar, TibcoHub)                                                                                                                      |
| **Application Management**   | ✅ List applications<br>✅ Delete application by name                                                                                                                                                             |
| **BWCE Operations**          | ✅ List BWCE versions<br>✅ Provision BWCE version<br>✅ Create BWCE build<br>✅ Deploy BWCE application<br>✅ Build and deploy BWCE app (all-in-one)                                                                 |
| **Flogo Operations**         | ✅ List Flogo versions<br>✅ Provision Flogo version<br>✅ Create Flogo build<br>✅ Deploy Flogo application<br>✅ Build and deploy Flogo app (all-in-one)                                                           |
| **BW5CE Operations**         | ✅ List BW5CE versions<br>✅ Provision BW5CE version<br>✅ Create BW5CE build<br>✅ Deploy BW5CE application<br>✅ Build and deploy BW5CE app (all-in-one)                                                           |
| **CP REST API**              | ✅ Call Control Plane REST API directly<br>✅ Supports GET, POST, DELETE methods<br>✅ Auto-handles authentication with Bearer token                                                                              |

## Platform Automation Hub
### 1. Run from Source Code

* Support for setting the KUBECONFIG path.

uv way of running the server from source code (Recommended):

```shell
cd docs/recipes/automation/tp-setup/bootstrap

uv sync
uv run playwright install
export TP_AUTO_TASK_FROM_LOCAL_SOURCE=true
# Optional, for connecting to GCP instance or other cluster
export TP_AUTO_KUBECONFIG=~/.kube/ins-{GCP_IP}.yaml
./run-auo.sh
```

old pip way:

```shell
cd docs/recipes/automation/tp-setup/bootstrap
python -m venv .venv

# For Mac & Linux
source .venv/bin/activate

# For windows
# source .venv/Scripts/activate

pip install -r requirements.txt
playwright install
export TP_AUTO_TASK_FROM_LOCAL_SOURCE=true
# Optional, for connecting to GCP instance or other cluster
export TP_AUTO_KUBECONFIG=~/.kube/ins-{GCP_IP}.yaml
python -m waitress --host=127.0.0.1 --port=3120 server:app
open http://127.0.0.1:3120/
```
### 2. Access the Platform Automation Hub installed along with CP

* [Platform Automation Hub](https://automation.localhost.dataplanes.pro/)
* No configuration is required. You can access the URL directly.
* Does not support for setting the KUBECONFIG path.


## Run Python Automation case/e2e individually

1. Run an individual test case
    ```shell
    # set HEADLESS to false will pop up a browser window, true will use headless mode.
    export HEADLESS="false"
    python -u -m case.k8s_config_dp_o11y
    ```
2. Run an individual e2e test
    ```shell
    export HEADLESS="false"
    pytest -v --tb=long --html=report/report.html --self-contained-html e2e/dataplane/configuration/o11y/test_test_connection_button.py
    pytest -v --tb=long --html=report/report.html --self-contained-html e2e/observability/test_o11y_list.py
    ```
3. Run all e2e test cases in parallel simultaneously based on the number of CPU cores of the current system
    ```shell
    # "-n auto" will automatically select the number of concurrent tasks based on your CPU cores.
    # "--dist=loadfile" Distribute strategy, distribute by file
    pytest -n auto -v --tb=long --dist=loadfile --html=report/report.html --self-contained-html e2e/**/*.py
    
    # run last failed test cases only
    pytest --lf
    ```


## Test Automation script in Docker container (Dev)

* Run local python automation script(`docs/recipes/automation/tp-setup/bootstrap`) in the Docker container.

```shell
# Optional, set it to true if you want to stay in the container after the pipeline fails
# export PIPELINE_FAIL_STAY_IN_CONTAINER=true

# Optional, if you want to use different host prefix, email and password, you can set them here
# export HOST_PREFIX="cp-sub1"
# export USER_EMAIL="cp-sub1@tibco.com"
# export USER_PASSWORD="Tibco@123"

# Optional, if you want to use different admin email and password, you can set them here
# export ADMIN_EMAIL="cp-test@tibco.com"
# export ADMIN_PASSWORD="Tibco@123"

# Optional, if user has been active, set it to false
# export TP_AUTO_ACTIVE_USER="false"

# Optional, GITHUB_TOKEN is for private repo, no need to set it and use global repository by default
export GITHUB_TOKEN=""
cd docs/recipes/automation/on-prem
# only generate recipe 05-tp-auto-deploy-dp.yaml, and run python automation script only
./generate-recipe.sh 2 3 && ./run.sh 4
```

## Test Python Automation script

```shell
cd docs/recipes/automation/tp-setup/bootstrap
python -m venv .venv
# For Mac & Linux
source .venv/bin/activate
# For windows
# source .venv/Scripts/activate
pip install -r requirements.txt

# Install playwright (Only need to run once)
playwright install

# Optional, if you want to use different host prefix, email and password, you can set them here
export HOST_PREFIX="cp-sub1"
export USER_EMAIL="cp-sub1@tibco.com"
export USER_PASSWORD="Tibco@123"

# Optional, if you want to use different admin email and password, you can set them here
export ADMIN_EMAIL="cp-test@tibco.com"
export ADMIN_PASSWORD="Tibco@123"

# Optional, if you want to see the browser UI during the test
export HEADLESS="false"

# Optional, GITHUB_TOKEN is for private repo, no need to set it and use global repository by default
export GITHUB_TOKEN=""
python page_dp.py
```

## Build and push docker image to GHCR Public repo (Publish a new version)
1. Go to [github Actions page](https://github.com/TIBCOSoftware/platform-provisioner/actions/workflows/docker-image-ghcr-build-push-public.yml)
   Run change version script to update all related files
   ```shell
   ./docs/recipes/automation/tp-setup/bootstrap/bump_version.sh
   ```
   * change `version` in `charts/provisioner-config-local/Chart.yaml` file
   * change `1.x.x-auto-on-prem-jammy` in `docs/recipes/automation/tp-setup/bootstrap/version.txt` file
   * search `-auto-on-prem-jammy` in the specified file, then update it, currently in the following files:
     * in `charts/provisioner-config-local/recipes/tp-base-on-prem-https.yaml` file
     * in `charts/provisioner-config-local/recipes/tp-base-on-prem.yaml` file
     * in `docs/recipes/tp-base/tp-base-on-prem-https.yaml` file
     * in `docs/recipes/tp-base/tp-base-on-prem.yaml` file
2. Commit and push the `version.txt` file changes to your branch.
3. Run the workflow manually
   1. update image tag: 1.x.x-auto-on-prem-jammy
   2. git branch name: your_branch_name
   3. click "Run workflow" button
4. After the workflow is done
   * Commit and push the `*.yaml` file changes to your branch.

## FAQ
1. If pod `dp-config-es-es-default-0` is pending.
   * CP was installed: run the following command to fix it.
    ```shell
    cd docs/recipes/automation/on-prem
    # Undeploy o11y stack then Redeploy o11y stack 
    ./generate-recipe.sh 1 1 && ./run.sh 7
    ```
   * CP is being installed in the VDI.
     1. Reset Docker to factory defaults.
     2. Restart VDI.
     3. Start docker and enable Kubernetes.
     4. Run CP installation command.
2. If you want to use a different **KUBECONFIG** path for the automation task UI
   * Must run it from source code mode, then UI will share the same environment as your local settings.
   * Follow the step: [Platform Automation Hub](#Platform-Automation-Hub)
3. Within customized **KUBECONFIG** path, if `Mail Server URL` can not be accessed.
   * port forwarding the `maildev` pod to your local machine.
   * put `http://localhost:YOUR_FORWARD_PORT` in the `Mail Server URL` field.
4. CP GUI can not be accessed: "Your connection is not private"
   * Go to CP installation folder
   * Copy certificate key to 01-tp-on-prem.yaml from [TP Token](https://docs.google.com/document/d/1f39d0_L6iRpEPjJggYFJrL3oVAtDyPdVbOnjmzU7E0E/edit?pli=1&tab=t.l6dihjhx60qc#heading=h.8ir76m4dmdxu)
   * Then run `./run.sh 2`
5. Get stored OAuth token from kubernetes secret
   ```shell
   kubectl get secret auto-token -n automation -o jsonpath="{.data['auto-token']}" | base64 --decode
   ```
