## Pre-requisites
* Install pyenv and python >= 3.12.8 if you don't have it (Only need to run once)
* For Windows: Install [Git Bash](https://git-scm.com/downloads)

### 1. Install pyenv
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
### 2. Install python 3.12.8
```shell
pyenv install 3.12.8
pyenv global 3.12.8
python --version
```

## One-Click Configuration - Supported Features


| Category                                    | Supported Features                                                                                                                                                                                                                                                                                                |
|:--------------------------------------------|:------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Display Current Environment Information** | ✅ Show Control Plane `platform-bootstrap` version<br>✅ Show Control Plane `platform-base` version<br>✅ Display Mail Server URL<br>✅ Display CP Admin Server URL, Admin Email, and Password<br>✅ Display CP Server URL, User Email, and Password<br>✅ Display Elastic, Kibana, and Prometheus URLs and Credentials |
| **Create a New Subscription**               | ✅ Provision a new subscription using the User Email by an Admin<br>✅ Activate the user via the `maildev` server<br>✅ Set the user's password and complete the login process                                                                                                                                       |
| **Configure Observability Widget**          | ✅ Automatically add widget cards for Kubernetes or Control Tower                                                                                                                                                                                                                                                  |
| **Configure Global Observability**          | ✅ Automatically create global Logs, Metrics, and Traces<br>✅ Support using system configuration for Metrics and Traces                                                                                                                                                                                            |
| **Create K8S DataPlane**                    | ✅ Run `create dp` command                                                                                                                                                                                                                                                                                         |
| **Configure DataPlane Observability**       | ✅ Automatically create DataPlane-level Logs, Metrics, and Traces<br>✅ Support using system configuration for Metrics and Traces                                                                                                                                                                                   |
| **Delete DataPlane**                        | ✅ Delete the specified DataPlane<br>✅ Run `delete dp` command                                                                                                                                                                                                                                                     |
| **Provision Capabilities**                  | ✅ Provision BWCE / EMS / Flogo / Pulsar / TibcoHub                                                                                                                                                                                                                                                                |
| **Create and Start Applications**           | ✅ Create a Flogo or BWCE application with a default file<br>✅ Upload a specified Flogo or BWCE app file<br>✅ Set up application environment variables<br>✅ Configure app endpoint visibility to public<br>✅ Start the application<br>✅ Test application via Swagger API                                           |
| **Delete Applications**                     | ✅ Delete the specified application by name                                                                                                                                                                                                                                                                        |

## One-Click Setup of the Control Plane
### 1. Run from Source Code

* Support for setting the KUBECONFIG path.

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
# Optional, if you want to use a different kubeconfig path, you can set it here
export TP_AUTO_KUBECONFIG=~/.kube/tp-cluster.yaml
python -m waitress --host=127.0.0.1 --port=3120 server:app
open http://127.0.0.1:3120/
```
### 2. Access the One-Click Setup of the CP System Server installed along with CP

* [One-Click Setup of the CP System Server](https://automation.localhost.dataplanes.pro/)
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


## FAQ
1. If pod `dp-config-es-es-default-0` is pending, run the following command to fix it.
    ```shell
    cd docs/recipes/automation/on-prem
    # Undeploy o11y stack then Redeploy o11y stack 
    ./generate-recipe.sh 1 1 && ./run.sh 7
    ```
2. If you want to use a different **KUBECONFIG** path for the automation task UI
   * Must run it from source code mode, then UI will share the same environment as your local settings.
   * Follow the step: [One-Click Setup of the Control Plane](#One-Click-Setup-of-the-Control-Plane)
3. Within customized **KUBECONFIG** path, if `Mail Server URL` can not be accessed.
   * port forwarding the `maildev` pod to your local machine.
   * put `http://localhost:YOUR_FORWARD_PORT` in the `Mail Server URL` field.
