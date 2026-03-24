# Platform Provisioner by TIBCO®

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Helm Charts](https://img.shields.io/badge/Helm%20Charts-published-green.svg)](https://tibcosoftware.github.io/platform-provisioner)

Platform Provisioner by TIBCO® is a lightweight, extensible, and easy to use recipe based provisioning system for cloud native platforms.
It consists of the following components:
* **Recipes**: YAML files containing all the information to provision platform infrastructure and applications.
* **Pipelines**: Scripts that run inside a Docker image to parse and execute recipes.
* **Runtime Docker Image**: A Docker image containing all the supporting tools (`bash`, `yq`, `helm`, `kubectl`, etc.) to run a pipeline with a given recipe.

## Why Platform Provisioner?

The Platform Provisioner is designed for the following use cases:
* Developer/DevOps engineer wants to provision platform infrastructure and applications in both cloud and on-premises.
* SRE/DevOps engineer has code snippets to run periodically for operational tasks.
* Platform team wants to provide a zero-trust provisioning system for multi-cloud environments.
* Platform team wants to dynamically provision platform infrastructure and applications on demand.
* Platform team wants to provide a self-service provisioning system for developers.

The Platform Provisioner does not create another layer of abstraction on top of existing tools. It provides 2 kinds of pipelines: `generic-runner` and `helm-install`.
The pipelines are focused on workflow orchestration and recipe parsing, so that users can put their favorite tools in the Docker image and use recipes to manage their workflow.

## Getting Started

The platform-provisioner can be run in headless mode with a Docker container as well as in a Kubernetes cluster.
For more information see: [Architecture Documentation](docs/design/README.md)

### Prerequisites

* Docker installed
* Bash shell
* [yq](https://mikefarah.gitbook.io/yq) version 4 installed

### Run the Platform Provisioner

Go to the project root directory and run the following command:
```bash
export PIPELINE_INPUT_RECIPE="docs/recipes/tests/test-container-binaries.yaml"
./dev/platform-provisioner.sh
```

For this sample pipeline:
* The recipe is `docs/recipes/tests/test-container-binaries.yaml`
* The pipeline is called `generic-runner`
* The runtime Docker image is `ghcr.io/tibcosoftware/platform-provisioner/platform-provisioner:latest`

The platform provisioner script [platform-provisioner.sh](dev/platform-provisioner.sh) will:
* Parse the recipe and copy it to the Docker container
* Load the pipeline script `generic-runner` into the Docker container
* Run the pipeline script with the recipe inside the Docker container

## Documentation

* [Architecture & Design](docs/design/README.md)
* [On-Premises Deployment](docs/recipes/k8s/on-prem/README.md)
* [Cloud Deployment Recipes](docs/recipes/k8s/cloud/)

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Security

To report a security vulnerability, please see [SECURITY.md](SECURITY.md).

## Versioning

We use [SemVer](http://semver.org/) for versioning. For the versions available, see the [tags on this repository](https://github.com/TIBCOSoftware/platform-provisioner/tags).

## License

Copyright 2025 Cloud Software Group, Inc.

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for the full license text.
