## Run Control Plane Automation Task Server

```shell
cd docs/recipes/automation/tp-setup/bootstrap
python -m venv .venv
# For Mac
source .venv/bin/activate
# For windows
# source .venv/Scripts/activate
pip install -r requirements.txt
playwright install
python -m waitress --host=127.0.0.1 --port=3120 server:app
open http://127.0.0.1:3120/
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

#Optional, if user have been active, set it to false
# export TP_AUTO_ACTIVE_USER="false"

# Optional, GITHUB_TOKEN is for private repo, no need to set it and use global repository by default
export GITHUB_TOKEN=""
cd docs/recipes/automation/on-prem
# only generate recipe 05-tp-auto-deploy-dp.yaml, and run python automation script only
./generate-recipe.sh 2 3 && ./run.sh 4
```

## Test Python Automation script in Mac

```shell

# Install pyenv and python 3.12.8 if you don't have it(Only need to run once)
brew update && brew install pyenv
pyenv install 3.12.8
pyenv global 3.12.8
python --version

cd docs/recipes/automation/tp-setup/bootstrap
python -m venv .venv
# For Mac
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

## Run Python Automation case/e2e individually

```shell
# set HEADLESS to false will popup browser window, true will use headless mode.
export HEADLESS="false"
python -u -m case.k8s_config_dp_o11y

# "-n auto" will automatically select the number of concurrent tasks based on your CPU cores.
# "--dist=loadfile" Distribute strategy, distribute by file
pytest -n auto -v --tb=long --dist=loadfile --html=report/report.html --self-contained-html e2e/**/*.py
pytest -v --tb=long --html=report/report.html --self-contained-html e2e/dataplane/configuration/o11y/test_test_connection_button.py
pytest -v --tb=long --html=report/report.html --self-contained-html e2e/observability/test_observability_list.py

# run last failed test cases only
pytest --lf
```

## FAQ
1. If pod `dp-config-es-es-default-0` is pending, run the following command to fix it.
    ```shell
    cd docs/recipes/automation/on-prem
    # Undeploy o11y stack then Redeploy o11y stack 
    ./run.sh 7
    ```
