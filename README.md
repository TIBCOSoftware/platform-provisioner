# Platform Provisioner by TIBCO®

Platform Provisioner by TIBCO® is a lightweight, extensible, and easy to use recipe based provisioning system for cloud native platforms.
It consists of the following components:
* Recipes: contains all the information to provision a platform infrastructure and applications. 
* Pipelines: The script that run inside the Docker image to parse and run the recipe.
* A runtime Docker image: The Docker image that contains all the supporting tools to run a pipeline with given recipe.

## Why Platform Provisioner?

The Platform Provisioner is designed the best fit for the following use cases:
* Developer/DevOps engineer wants to provision a platform infrastructure and applications in both cloud and on-premises.
* SRE/DevOps engineer has code snippets to run every 3 month or so for the operation tasks.
* Platform team wants to provide a zero trust provisioning system for multi-cloud environment.
* Platform team wants to dynamically provision a platform infrastructure and applications on demand. 
* Platform team wants to provide a self-service provisioning system for the developers.

The Platform Provisioner does not want to create another layer of abstraction on top of the existing tools. It provides 2 kinds of pipelines: generic-runner and helm-install. 
The pipelines are focused on workflow orchestration and recipe parsing. So that the user can put their favorite tools in the docker image and use the recipe to manage their workflow.
The pipelines are designed to be extensible and easy to use.

## Getting Started

The platform-provisioner can be run in headless mode with Docker container as well as in the Cloud Kubernetes cluster with Tekton.
For more information see: [README.md](docs/design/README.md)

### Prerequisite

* Docker installed
* Bash shell
* [yq](https://mikefarah.gitbook.io/yq) version 4 installed

### Run the Platform Provisioner

Go to the project root directory and run the following command.
```bash
export PIPELINE_INPUT_RECIPE="docs/recipes/tests/test-container-binaries.yaml"
./dev/platform-provisioner.sh
```

For this sample pipeline: 
* The recipe is `docs/recipes/tests/test-container-binaries.yaml`
* The pipeline is called `generic-runner`
* The runtime Docker image is `ghcr.io/tibcosoftware/platform-provisioner/platform-provisioner:latest`

The platform provisioner script [platform-provisioner.sh](dev/platform-provisioner.sh) will 
* Parse the recipe and copy the recipe to the Docker container
* Load pipeline script `generic-runner` to the Docker container
* Run the pipeline script with the recipe inside the Docker container


## Versioning

We use [SemVer](http://semver.org/) for versioning. For the versions available, see the [tags on this repository](https://github.com/your/project/tags). 

---
Copyright 2024 Cloud Software Group, Inc.

License. This project is Licensed under the Apache License, Version 2.0 (the "License").
You may not use this file except in compliance with the License. You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing,
software distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and limitations under the License.
