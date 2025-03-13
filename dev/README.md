## Get recipes from TIBCO GitHub

This repo provides some recipes to test the pipeline and cloud connection. It is located under [recipes](docs/recipes) folder.
* tp-base: contains the base recipe to provision TIBCO Platform.
* controplane: contains the recipe to provision TIBCO® Control Plane.
* k8s: contains the recipe to provision Kubernetes cluster.

## Run the Platform Provisioner in headless mode with Docker container

The platform-provisioner can be run in headless mode with Docker container. The Docker container contains all the necessary tools to run the pipeline scripts.
The `platform-provisioner.sh` script will create a Docker container and run the pipeline scripts with a given recipe.

### Prerequisite

* Docker installed
* Bash shell

### Run the Platform Provisioner

Go to the directory where you save the recipe and run the following command.
We need to set `GITHUB_TOKEN` to access the pipeline private repo
```bash
export GITHUB_TOKEN=""
export PIPELINE_INPUT_RECIPE=""
export PIPELINE_CHART_REPO="${GITHUB_TOKEN}@raw.githubusercontent.com/tibco/platform-provisioner/gh-pages/"
/bin/bash -c "$(curl -fsSL https://${GITHUB_TOKEN}@raw.githubusercontent.com/tibco/platform-provisioner/main/dev/platform-provisioner.sh)"
```

## Run the Platform Provisioner in headless mode with the Tekton pipeline

The platform-provisioner can be run in headless mode with Tekton installed in the target Kubernetes cluster. 
In this case, the recipe and pipeline will be scheduled by Tekton and run in the target Kubernetes cluster.

### Prerequisite

* Docker installed
* Bash shell
* yq version 4 installed

#### Install Tekton with Tekton dashboard
```bash
export GITHUB_TOKEN=""
export PIPELINE_SKIP_TEKTON_DASHBOARD=false
export PLATFORM_PROVISIONER_PIPELINE_REPO="https://${GITHUB_TOKEN}@raw.githubusercontent.com/tibco/platform-provisioner/gh-pages/"
/bin/bash -c "$(curl -fsSL https://${GITHUB_TOKEN}@raw.githubusercontent.com/tibco/platform-provisioner/main/dev/platform-provisioner-install.sh)"
```

After the installation, you can run the following command to port-forward the Tekton dashboard to local machine.
```bash
kubectl port-forward -n tekton-pipelines service/tekton-dashboard 8080:9097
```

We can now access Tekton provided dashboard: http://localhost:8080

### Run the platform-provisioner in headless mode

Go to the directory where you save the recipe and run the following command
```bash
export GITHUB_TOKEN=""
export PIPELINE_INPUT_RECIPE="<path to recipe>"
/bin/bash -c "$(curl -fsSL https://${GITHUB_TOKEN}@raw.githubusercontent.com/tibco/platform-provisioner/main/dev/platform-provisioner-pipelinerun.sh)"
```

You will be able to see the running pipelinerun on Tekton Dashboard by clicking the PipelineRuns on the left.
