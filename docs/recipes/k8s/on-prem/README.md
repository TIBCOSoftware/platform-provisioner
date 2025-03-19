# TIBCO Platform On-Premises Deployment Guide

## Introduction

This documents the steps to create on-prem Kubernetes cluster and deploy TIBCO Platform on top of it. This document will use headless mode to run the Platform Provisioner. 
We do have a Platform Provisioner UI which will open source soon. The UI will help to set the environment variables for the recipe.

## Basic information and assumptions

### Domain
For the on-prem use case, we create a domain `*.localhost.dataplanes.pro` which point to `127.0.0.1` and use it as the domain for the TIBCO Platform.
For the on-prem set up the following domains are used:
* `mail.localhost.dataplanes.pro`: the self-hosted mail server for TIBCO Platform activation emails.
* `admin.cp1-my.localhost.dataplanes.pro`: the TIBCO Control Plane admin console.
* `cp-sub1.cp1-my.localhost.dataplanes.pro`: the TIBCO Control Plane subscription console.

### Environment variables
In the recipe the section `meta.guiEnv` is used to set environment variables for the recipe. The environment variables starts with `GUI_`. It is designed to work with Platform Provisioner UI.
For the headless mode; we can re-use the environment variables with the prefix `GUI_` to set the environment variables in the recipe.

### Pipeline and recipe
Platform Provisioner uses the Tekton pipeline to run the recipe. The script `platform-provisioner-pipelinerun.sh` will schedule a Tekton Pipelinerun to run the recipe.
You can use the Tekton dashboard to monitor the progress.

### Notes for VM

Kubernetes only works on linux. So for Mac and Windows we always need to use VM. Ideally we should use official VM technology:
* Mac: Apple's [Virtualization framework](https://developer.apple.com/documentation/hypervisor) or the new [Docker VMM](https://docs.docker.com/desktop/features/vmm/) for Apple Silicon chip.
* Windows: Microsoft's [Hyper-V](https://docs.microsoft.com/en-us/virtualization/hyper-v-on-windows/quick-start/enable-hyper-v) with [WSL2](https://learn.microsoft.com/en-us/windows/wsl/install)

Third party tools like multipass, virtualbox are not recommended. 

For Mac, we suggest to use minikube with docker desktop. For Windows, we suggest to use kubernetes on docker desktop to get the best performance.

> [!Note]
> MicroK8s use mulitpass which is using QEMU on Mac. For Apple Silicon chip or new macOS like Sequoia; the multipass might not work properly. 
> We don't recommend to use MicroK8s on Mac.

## Headless helper script

We have a helper script [tp-install-on-prem.sh](scripts/headless/tp-install-on-prem.sh) to install TIBCO Platform on-premises.
This script will act as entrypoint to download a set of recipes and other helper scripts to install TIBCO Platform on-premises.

The helper script will download a set of recipes for TIBCO Platform. For example
* `01-tp-on-prem.yaml`: this recipe will install third party tools like nginx/traefik ingress, cert-manager, metrics-server, postgresql.
* `02-tp-cp-on-prem.yaml`: this recipe will install TIBCO Control Plane.
* `06-tp-o11y-stack.yaml`: this recipe will install Observability stack.
* `05-tp-auto-deploy-dp.yaml`: this recipe will create subscription on CP and deploy Data Plane. And deploy capabilities to the Data Plane.

The headless script will run inside a docker container and connect to the local kubernetes cluster to install TIBCO Platform on-premises.
So you have to make sure the `kubeconfig` is pointing to the local kubernetes cluster. For more information see [README.md](../../../design/README.md)

### Credentials

Before running the headless script, it is better to set the credentials as environment variables.
```bash
export GUI_TP_TLS_CERT=""
export GUI_TP_TLS_KEY=""

export GUI_CP_CONTAINER_REGISTRY: csgprduswrepoedge.jfrog.io
export GUI_CP_CONTAINER_REGISTRY_REPOSITORY: tibco-platform-docker-prod
export GUI_CP_CONTAINER_REGISTRY_USERNAME=""
export GUI_CP_CONTAINER_REGISTRY_PASSWORD=""
```

If you don't set; the script will prompt you to input the credentials.

### How to use the headless script

```bash
./tp-install-on-prem.sh
```

The above command will ask you a few questions and then run the recipes to install TIBCO Platform on-premises.
* Choose the target Kubernetes cluster
* Choose the ingress to use
* Update the tokens if not set in environment variables. (You can skip the GitHub token if using public repo)
* Choose the deployment options
  * Choose to deploy all the recipes or select the specific recipe to run.

The recipes are downloaded to the current directory. We can future customize the recipes to suit our needs. 
And then use `./run.sh` to trigger the recipe to install TIBCO Platform on-premises.

### Sample Kubernetes cluster environments

* [minikube](minikube.md)
* [kind](kind.md)
