# Platform Provisioner by TIBCO® Helm Charts
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Release Charts](https://github.com/TIBCOSoftware/platform-provisioner/actions/workflows/release-chart.yaml/badge.svg)](https://github.com/TIBCOSoftware/platform-provisioner/actions/workflows/release-chart.yaml)

## Introduction
Platform Provisioner by TIBCO® is a system that can provision a platform on any cloud provider (AWS, Azure) or on-prem. It consists of the following components:
* Recipes: contains all the information to provision a platform.
* Pipelines: The script that can run inside the Docker image to parse and run the recipe. Normally, the pipelines encapsulate as a helm chart.
* A runtime Docker image: The Docker image that contains all the supporting tools to run a pipeline with given recipe.

## Installing

The repo provides some helper scripts to install the platform-provisioner. The scripts are located in the `dev` directory.

### Prerequisites
1. [x] Helm **v3 > 3.12.0** [installed](https://helm.sh/docs/using_helm/#installing-helm): `helm version`
2. [x] Chart repository: `helm repo add platform-provisioner https://tibcosoftware.github.io/platform-provisioner`

## Contributing

The source code is under <https://github.com/TIBCOSoftware/platform-provisioner>

# Licenses

This project (_Helm Charts for TIBCO® Platform_) is licensed under the [Apache 2.0 License](https://github.com/TIBCOSoftware/tp-helm-charts/blob/main/LICENSE).

## Other Software

When you use some of the Helm charts, you fetch and use other charts that might fetch other container images, each with their own licenses.
A partial summary of the third party software and licenses used in this project is available [here](https://github.com/TIBCOSoftware/tp-helm-charts/blob/main/docs/third-party-software-licenses.md).

---
Copyright 2024 Cloud Software Group, Inc.

License. This project is Licensed under the Apache License, Version 2.0 (the "License").
You may not use this file except in compliance with the License. You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing,
software distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and limitations under the License.
