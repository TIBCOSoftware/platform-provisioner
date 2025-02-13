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
cd docs/recipes/automation/on-perm
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

cd charts/provisioner-config-local/scripts/automation
python -m venv .venv
source .venv/bin/activate
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
    cd docs/recipes/automation/on-perm
    # Undeploy o11y stack then Redeploy o11y stack 
    ./run.sh 7
    ```
