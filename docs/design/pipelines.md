# Platform Provisioner Pipeline Design

## Overview

The Platform Provisioner pipeline is the fundamental building block of the Platform Provisioner. It is a script that runs inside the Docker image to parse and run the recipe.
Internally we have a lot of pipelines that are designed to run different kinds of recipes and purposes. But eventually we find the most common use cases are covered by 2 pipelines: `generic-runner` and `helm-install`.

Pipelines are stored in the `charts` directory as separate helm charts. It will be very easy to create a new pipeline by creating a new helm chart with the pipeline script and the schema.
In the platform provisioner; we provide 3 charts:
* `common-dependency`: contains all the common scripts and schemas that are shared between the pipelines.
* `generic-runner`: contains the script to run the shell scripts and the schema to validate the recipe.
* `helm-install`: contains the script to install the helm chart and the schema to validate the recipe.

The reason we use helm chart to store the pipeline is that we initially design the platform provisioner to run in the Cloud Kubernetes cluster. 
The pipelines should be dynamically created and deleted for different team to use. GitOps tools like ArgoCD can be used to manage the pipelines.
When the tekton pipeline runs; the pod can just mount the pipeline script configmap and run the script.

The platform provisioner uses tekton to run the pipelines in the SaaS use case. The tekton engin will schedule the pipelinerun and taskrun to run the pipeline script with the recipe. 

For the on-prem use case; the platform provisioner uses the docker container to run the pipeline script with the recipe. 
The [platform-provisioner.sh](../../dev/platform-provisioner.sh) script will parse pipeline common-dependency and the pipeline script to the docker container and run the script with the recipe.

## common-dependency chart

The `common-dependency` chart folder and files are as follows:
* `scripts`: contains all the source common scripts and cue files that are shared between the pipelines.
  * `shared.cue`: the schema to validate the recipe. This defines the common schema like meta, task, github etc sections for common use.
* `templates`: contains the kubernetes resources like configmap and secret that are shared between the pipelines.
  * `pipelineConfig.yaml` reads all the files under scripts folder and create a configmap.
  * `secret-github.yaml` the secrets that are used inside pipeline pods.

## generic-runner chart

The `generic-runner` chart folder and files are as follows:
* `scripts`: contains the source script and cue files that are used to run the shell scripts.
  * `check.cue`: the schema to validate the recipe.
  * `run.sh`: the entrypoint script to run the shell scripts.
* `templates`: contains the kubernetes resources like configmap and secret that are used to run the pipeline.
  * `pipelineScripts.yaml` reads all the files under scripts folder and create a configmap.
  * `pipelineConfig.yaml`, `pipeline.yaml` and `task.yaml` are the tekton resources (PipelineRun, Pipeline and Task) to run the pipeline. 
  * `task.yaml` contains the details of the pod that mount the pipeline script configmap and run the script.
* `docs`: contains the documentation of the pipeline for the platform provisioner UI. This will act as default value and document for the pipeline.

## helm-install chart

The `helm-install` chart has exactly the same structure as the `generic-runner` chart. The only difference is the script and schema are used to install the helm chart.

For more information about the recipe; see [recipes.md](recipes.md)
