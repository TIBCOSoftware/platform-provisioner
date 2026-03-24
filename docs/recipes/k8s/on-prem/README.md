# TIBCO Platform On-Premises Deployment Guide

## Introduction

This documents the steps to create on-prem Kubernetes cluster and deploy TIBCO Platform on top of it. This document will use headless mode to run the Platform Provisioner.
We do have a Platform Provisioner UI which will open source soon. The UI will help to set the environment variables for the recipe.

## Prerequisites

- **Docker**, **yq (v4)**, **Helm**, **kubectl**, **mkcert**, **zip**
- A running Kubernetes cluster (Docker Desktop, minikube, kind, k3s, etc.) with `kubectl` configured

## Basic information and assumptions

### Domain
For the on-prem use case, we use `dev.localhost` which point to `127.0.0.1` and use it as the domain for the TIBCO Platform.
The following domains are used:
* `mail.dev.localhost`: the self-hosted mail server for TIBCO Platform activation emails.
* `admin.cp1-my.dev.localhost`: the TIBCO Control Plane admin console.
* `cp-sub1.cp1-my.dev.localhost`: the TIBCO Control Plane subscription console.
* `cp-sub1.cp1-tunnel.dev.localhost`: hostname for tibtunnel to connect to the Control Plane. Required in TP 1.14.0. Optional in TP 1.15.0 and above.

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

## Step 1: Prepare Kubernetes Cluster

### minikube

Install minikube [link](https://minikube.sigs.k8s.io/docs/start/)

Command to start minikube:

in Mac:
```bash
minikube start --memory 28672 --disk-size "40g" \
--driver=docker \
--addons storage-provisioner
```

in linux:
This 28G memory with 24 cores can run DP with flogo, bwce, messaging and tibco-hub
```bash
minikube start --memory 28672 --disk-size "40g" \
--driver=docker \
--addons storage-provisioner
```

#### Use minikube tunnel

If you want to expose the service to the public, you can use minikube tunnel to expose the service to the public. You can use the following command to start the tunnel:

```bash
sudo nohup minikube tunnel --cleanup &
minikube tunnel --bind-address 0.0.0.0
```

### kind

Install kind [link](https://kind.sigs.k8s.io/docs/user/quick-start/)

Command to start kind:

in Mac:
```bash
kind create cluster --config - <<EOF
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: tp
nodes:
- role: control-plane
  kubeadmConfigPatches:
  - |
    kind: InitConfiguration
    nodeRegistration:
      kubeletExtraArgs:
        node-labels: "ingress-ready=true"
  extraPortMappings:
  - containerPort: 80
    hostPort: 80
    protocol: TCP
  - containerPort: 443
    hostPort: 443
    protocol: TCP
EOF
```

```bash
kubectl apply -f https://projectcontour.io/quickstart/contour.yaml
```

To delete kind cluster:
```bash
kind delete cluster -n tp
```

#### Access the TIBCO Platform with kind

After installing the main ingress, we can forward the ingress port locally:
```bash
kubectl port-forward -n ingress-system --address 0.0.0.0 service/traefik 80:web 443:websecure
```

### Docker Desktop / Other

For Docker Desktop or other Kubernetes distributions, ensure `kubectl` is configured and pointing to your cluster. For more information see [design README](../../../design/README.md).

## Step 2: Run the Headless Script

We have a helper script [tp-install-on-prem.sh](scripts/headless/tp-install-on-prem.sh) to install TIBCO Platform on-premises.
This script will act as entrypoint to download a set of recipes and other helper scripts to install TIBCO Platform on-premises.

The helper script will download a set of recipes for TIBCO Platform. For example
* `01-tp-on-prem.yaml`: this recipe will install third party tools like nginx/traefik ingress, cert-manager, metrics-server, postgresql.
* `02-tp-cp-on-prem.yaml`: this recipe will install TIBCO Control Plane.
* `06-tp-o11y-stack.yaml`: this recipe will install Observability stack.
* `05-tp-auto-deploy-dp.yaml`: this recipe will create subscription on CP and deploy Data Plane. And deploy capabilities to the Data Plane.

The headless script will run inside a docker container and connect to the local kubernetes cluster to install TIBCO Platform on-premises.
So you have to make sure the `kubeconfig` is pointing to the local kubernetes cluster.

### Quick Start

```bash
./tp-install-on-prem.sh
```

The script will interactively prompt you for cluster type, ingress, and registry credentials, then deploy everything.

* Choose the target Kubernetes cluster
* Choose the ingress to use
* Update the tokens if not set in environment variables. (You can skip the GitHub token if using public repo)
* Choose the deployment options
  * Choose to deploy all the recipes or select the specific recipe to run.

The recipes are downloaded to the current directory. We can future customize the recipes to suit our needs.
And then use `./run.sh` to trigger the recipe to install TIBCO Platform on-premises.

### Non-interactive Deployment

Set environment variables to skip all prompts:

```bash
export TP_K8S_CLUSTER_TYPE_CODE=4          # 1=k3s, 2=OpenShift, 3=Docker Desktop, 4=minikube, 5=kind, 6=MicroK8s
export TP_AUTOMATION_SCRIPT_OPTIONS=1      # 1=deploy all (see run.sh for other options)
./tp-install-on-prem.sh
```

### Generate Recipes Only (Skip Deployment)

To generate all recipes without running `./run.sh`:

```bash
export TP_SKIP_DEPLOY=true
./tp-install-on-prem.sh
```

Recipes are saved to the current directory. You can then run them individually:
```bash
./run.sh 8    # deploy BW5 stack
./run.sh 1    # deploy all
```

## Configuration

### Custom Domain

Defaults to `dev.localhost` if not set.

```bash
export TP_TOP_DOMAIN="my-domain.example.com"
```

### Container Registry Credentials

Before running the headless script, it is better to set the credentials as environment variables.
```bash
export GUI_CP_CONTAINER_REGISTRY=csgprduswrepoedge.jfrog.io
export GUI_CP_CONTAINER_REGISTRY_REPOSITORY=tibco-platform-docker-prod
export GUI_CP_CONTAINER_REGISTRY_USERNAME=""
export GUI_CP_CONTAINER_REGISTRY_PASSWORD=""
```

If you don't set them, the script will prompt you to input the credentials.

### License Activation

**License file (download from [TIBCO support portal](https://ui.licensingprod-int.tibco.com/ui))**

```bash
export GUI_TP_LICENSE_FILE_PATH="/path/to/license.bin"
```

The script will zip and base64-encode the file for injection into the deployment recipe.

### Custom TLS Certificate

If `GUI_TP_TLS_CERT` and `GUI_TP_TLS_KEY` are not set, the script will automatically generate a self-signed certificate using `mkcert` for the configured domain (`TP_TOP_DOMAIN`). You can also provide your own certificate:

```bash
export GUI_TP_TLS_CERT=$(base64 < /path/to/cert.pem | tr -d '\n\r')
export GUI_TP_TLS_KEY=$(base64 < /path/to/key.pem | tr -d '\n\r')
export GUI_TP_IS_CERT_SELF_SIGNED=true  # set if your cert is self-signed
```

## Environment Variables Reference

### Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `TP_TOP_DOMAIN` | `dev.localhost` | Top-level domain |
| `TP_K8S_CLUSTER_TYPE_CODE` | (interactive) | K8s cluster type: 1=k3s, 2=OpenShift, 3=Docker Desktop, 4=minikube, 5=kind |
| `TP_K8S_INGRESS_TYPE_CODE` | `2` | 1=nginx, 2=traefik, 3=nginx gateway fabric |
| `TP_AUTOMATION_SCRIPT_OPTIONS` | `1` | 1=deploy all (see run.sh for other options) |
| `TP_SKIP_DEPLOY` | `false` | When `true`, generate recipes only without running `./run.sh` |
| `GITHUB_BRANCH` | `main` | Branch for downloading automation scripts |
| `GITHUB_TOKEN` | (optional) | GitHub token for private repo access. When set, private repos/images are used; otherwise public defaults |
| `GITHUB_PATH` | (optional) | Base URL for downloading automation scripts. Auto-set based on `GITHUB_BRANCH` and `GITHUB_TOKEN` |
| `GUI_TP_LICENSE_FILE_PATH` | `/path/to/license.bin` | Path to `.bin` license file |
| `GUI_TP_TLS_CERT` | (auto-generated) | Base64-encoded TLS certificate |
| `GUI_TP_TLS_KEY` | (auto-generated) | Base64-encoded TLS key |
| `GUI_TP_IS_CERT_SELF_SIGNED` | (auto) | Set to `true` for self-signed certs |
| `GUI_CP_CONTAINER_REGISTRY` | `csgprduswrepoedge.jfrog.io` | Container registry URL |
| `GUI_CP_CONTAINER_REGISTRY_REPOSITORY` | `tibco-platform-docker-prod` | Container registry repository |
| `GUI_CP_CONTAINER_REGISTRY_USERNAME` | | Registry username |
| `GUI_CP_CONTAINER_REGISTRY_PASSWORD` | | Registry password |
| `GUI_CP_PLATFORM_*_VERSION` | The TIBCO Platform release | Override platform chart versions (e.g., `GUI_CP_PLATFORM_TIBCO_CP_BASE_VERSION=1.15.0`) |

### Feature Flags

| Variable | Default | Description |
|----------|---------|-------------|
| `GUI_TP_AUTO_USE_CLI` | `true` | Use CLI mode for DP operations |
| `GUI_TP_AUTO_ACTIVE_USER` | `true` | Activate user automatically |
| `GUI_TP_AUTO_ENABLE_DP` | `true` | Enable Data Plane deployment |
| `GUI_TP_AUTO_ENABLE_BWCE` | `true` | Enable BWCE |
| `GUI_TP_AUTO_ENABLE_FLOGO` | `true` | Enable Flogo |
| `GUI_TP_AUTO_ENABLE_CONFIG_O11Y` | `true` | Enable O11y configuration |
| `GUI_TP_AUTO_ENABLE_O11Y_WIDGET` | `true` | Enable O11y widget |
| `GUI_TP_AUTO_ENABLE_BW5CE` | `false` | Enable BW5CE |
| `GUI_TP_AUTO_ENABLE_TIBCOHUB` | `false` | Enable TIBCO Hub |
| `GUI_TP_AUTO_ENABLE_EMS` | `false` | Enable EMS |
| `GUI_TP_AUTO_ENABLE_BMDP` | `false` | Enable BMDP |
| `GUI_TP_AUTO_IS_ENABLE_RVDM` | `true` | Enable RV domain model |
| `GUI_TP_AUTO_IS_ENABLE_EMSDM` | `true` | Enable EMS domain model |
| `GUI_TP_AUTO_IS_ENABLE_BW6DM` | `true` | Enable BW6 domain model |
| `GUI_TP_AUTO_ENABLE_E2E_TEST` | `false` | Enable E2E test |

## Deployment Reports

After deployment, reports are saved to the `./report/` directory.
