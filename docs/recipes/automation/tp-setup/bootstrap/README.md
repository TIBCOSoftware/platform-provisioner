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

# GITHUB_TOKEN is required for private repo, better to set it
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

# GITHUB_TOKEN is required for private repo, better to set it
export GITHUB_TOKEN=""
python run.py
```

## Setup local environment from scratch for Local Machine

1. **Reset Kubernetes cluster** from Docker Desktop, or **Clean / Purge data** from Docker Desktop.
2. Pre-set the environment variables in `env.sh` file.
   * Edit `~/docs/recipes/automation/on-perm/env.sh` file and set the following environment variables, then save the file.
    ```shell
    # get TLS cert and key from https://docs.google.com/document/d/1f39d0_L6iRpEPjJggYFJrL3oVAtDyPdVbOnjmzU7E0E/edit?pli=1&tab=t.l6dihjhx60qc#heading=h.8ir76m4dmdxu
    export GUI_TP_TLS_CERT=""
    export GUI_TP_TLS_KEY=""
    
    # get GITHUB_TOKEN for your GitHub account
    export GITHUB_TOKEN=""
        
    # get password from https://docs.google.com/document/d/1f39d0_L6iRpEPjJggYFJrL3oVAtDyPdVbOnjmzU7E0E/edit?pli=1&tab=t.l6dihjhx60qc
    export GUI_CP_CONTAINER_REGISTRY_PASSWORD=""
    ```
3. Install the environment from scratch.
    ```shell
    cd docs/recipes/automation/on-perm
    # generate all recipes, and install environment from scratch
    rm *.yaml && ./generate-recipe.sh 2 1 && ./update-recipe-tokens.sh && ./run.sh 1
    ```

## Setup Cloud(EKS, AKS, GCP) environment from scratch

  Follow the Doc: https://docs.google.com/document/d/16cynZZOnWeLpNEeuNDWejyhXPjhFGX1WHNO86WCM_GI/edit?tab=t.0#heading=h.1mg93dxnj5je

  **Below steps are for GCP environment installation**

1. Open Platform Provisioner, both works.
   * Staging: https://provisioner-staging.cic2.tibcocloud.com/pipelines/generic-runner?title=deploy-tp-on-prem-gcp-k3s
   * Production: https://provisioner.cic2.tibcocloud.com/pipelines/generic-runner?title=deploy-tp-on-prem-gcp-k3s

2. Pre-set the environment variables in `env.sh` file(Same as above step.2 for Local).
3. Generate the recipe and update the recipe tokens.
    ```shell
    cd docs/recipes/automation/on-perm
    rm *.yaml && ./generate-recipe.sh 2 1 && ./adjust-recipe.sh 1 && ./update-recipe-tokens.sh
    ```
4. Set Control Platform version as needed, otherwise it will use the version in the YAML `02-tp-cp-on-perm.yaml`.
   * Set CP version in Platform Provisioner UI is highest priority than zip file.
   * Set CP Configuration -> CP platform bootstrap version to `1.x.x`.
   * Set CP Configuration -> CP platform base version to `1.x.x`.
5. Optional, disable BWCE installation. Edit YAML file `02-tp-cp-on-perm.yaml` as needed.
    ```yaml
    # disable BWCE installation as needed
    GUI_CP_INSTALL_INTEGRATION_BWCE: false
    GUI_CP_INSTALL_INTEGRATION_BWCE_UTILITIES: false
    GUI_CP_INSTALL_INTEGRATION_BW5: false
    ```
6. Zip *.yaml files and upload to the Platform Provisioner(MUST unselect `CP Configuration -> Use pipeline generated recipe`).
7. Optional, use different branch.
   * change `main` to `your_branch` at input field `TP Automation Config -> Automation script branch`.
8. Click `Run` button to start the installation.

## FAQ
1. If pod `dp-config-es-es-default-0` is pending, run the following command to fix it.
    ```shell
    cd docs/recipes/automation/on-perm
    # Undeploy o11y stack then Redeploy o11y stack 
    ./run.sh 7
    ```
