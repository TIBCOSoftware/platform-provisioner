## Introduction

This documents the steps to create on-prem Kubernetes cluster and deploy TIBCO Platform on top of it. This document will use headless mode to run the Platform Provisioner. 
We do have a Platform Provisioner UI which will open source soon. The UI will help to set the environment variables for the recipe.

## Basic information and assumptions

### Domain
For the on-perm use case, we create a domain `*.localhost.dataplanes.pro` which point to `0.0.0.0` and use it as the domain for the TIBCO Platform.

### Environment variables
In the recipe the section `meta.guiEnv` is used to set environment variables for the recipe. The environment variables starts with `GUI_`. It is designed to work with Platform Provisioner UI.
For the headless mode; we can re-use the environment variables with the prefix `GUI_` to set the environment variables in the recipe.

### Pipeline and recipe
Platform Provisioner uses the Tekton pipeline to run the recipe. The script `platform-provisioner-pipelinerun.sh` will schedule a Tekton Pipelinerun to run the recipe.
You can use the Tekton dashboard to monitor the progress.

### Notes for VM

Kubernetes only works on linux. So for Mac and Windows we always need to use VM. Ideally we should use official VM technology:
* Mac: Apple's [Virtualization framework](https://developer.apple.com/documentation/hypervisor)
* Windows: Microsoft's [Hyper-V](https://docs.microsoft.com/en-us/virtualization/hyper-v-on-windows/quick-start/enable-hyper-v) with [WSL2](https://learn.microsoft.com/en-us/windows/wsl/install)

Third party tools like multipass, virtualbox are not recommended. 

For Mac, we suggest to use minikube with docker desktop. For Windows, we suggest to use kubernetes on docker desktop to get the best performance.

> [!Note]
> MicroK8s use mulitpass which is using QEMU on Mac. For Apple Silicon chip or new macOS like Sequoia; the multipass might not work properly. 
> We don't recommend to use MicroK8s on Mac.
