<!-- TOC -->
* [Platform Provisioner by TIBCO®](#platform-provisioner-by-tibco)
  * [Get recipes from TIBCO GitHub](#get-recipes-from-tibco-github)
  * [Run the Platform Provisioner in headless mode with Docker container](#run-the-platform-provisioner-in-headless-mode-with-docker-container)
    * [Prerequisite](#prerequisite)
    * [Run the Platform Provisioner](#run-the-platform-provisioner)
  * [Run the Platform Provisioner in headless mode with the Tekton pipeline](#run-the-platform-provisioner-in-headless-mode-with-the-tekton-pipeline)
    * [Prerequisite](#prerequisite-1)
      * [Install Tekton with Tekton dashboard](#install-tekton-with-tekton-dashboard)
    * [Run the platform-provisioner in headless mode](#run-the-platform-provisioner-in-headless-mode)
  * [Docker image for Platform Provisioner](#docker-image-for-platform-provisioner)
<!-- TOC -->

# Platform Provisioner by TIBCO®

Platform Provisioner by TIBCO® is a system that can provision a platform on any cloud provider (AWS, Azure) or on-prem. It consists of the following components:
* Recipes: contains all the information to provision a platform.
* Pipelines: The script that can run inside the Docker image to parse and run the recipe. Normally, the pipelines encapsulate as a helm chart.
* A runtime Docker image: The Docker image that contains all the supporting tools to run a pipeline with given recipe.

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
```bash
export PIPELINE_INPUT_RECIPE=""
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/TIBCOSoftware/platform-provisioner/main/dev/platform-provisioner.sh)"
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
export PIPELINE_SKIP_TEKTON_DASHBOARD=false
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/TIBCOSoftware/platform-provisioner/main/dev/platform-provisioner-install.sh)"
```

After the installation, you can run the following command to port-forward the Tekton dashboard to local machine.
```bash
kubectl port-forward -n tekton-pipelines service/tekton-dashboard 8080:9097
```

We can now access Tekton provided dashboard: http://localhost:8080

### Run the platform-provisioner in headless mode

Go to the directory where you save the recipe and run the following command
```bash
export PIPELINE_INPUT_RECIPE="<path to recipe>"
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/TIBCOSoftware/platform-provisioner/main/dev/platform-provisioner-pipelinerun.sh)"
```

You will be able to see the running pipelinerun on Tekton Dashboard by clicking the PipelineRuns on the left.

## Docker image for Platform Provisioner

We provide a Dockerfile to build the Docker image. The Docker image is used to run the pipeline. It contains the necessary tools to run the pipeline scripts.

<details>
<summary>Steps to build Docker image</summary>
To build Docker image locally, run the following command:

```bash
cd docker
./build.sh
```

This will build the Docker image called `platform-provisioner:latest`.

To build multi-arch Docker image and push to remote Docker registry, run the following command:

```bash
export DOCKER_REGISTRY="<your Docker registry repo>"
export PUSH_DOCKER_IMAGE=true
cd docker
./build.sh
```
This will build the Docker image called `<your Docker registry repo>/platform-provisioner:latest` and push to remote Docker registry.

</details>

> [!Note]
> For other options, please see [docker/build.sh](docker/build.sh).

---
Copyright 2024 Cloud Software Group, Inc.

License. This project is Licensed under the Apache License, Version 2.0 (the "License").
You may not use this file except in compliance with the License. You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing,
software distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and limitations under the License.
