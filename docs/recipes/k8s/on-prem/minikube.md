## Prepare minikube

Install minikube [link](https://minikube.sigs.k8s.io/docs/start/)

command to start minikube:

in Mac:
```bash
minikube start --cpus=4 --memory 20480 --disk-size "40g" \
--driver=docker \
--addons storage-provisioner
```

in linux:
This 20G memory with 24 cores can run DP with flogo, bwce, messaging and tibco-hub
```bash
minikube start --memory 20480 --disk-size "40g" \
--driver=docker \
--addons storage-provisioner
```

We need to also start another terminal to run the following command to enable ingress:
(Otherwise the main ingress will not be ready, and the TP infra chart deployment might have problem)

```bash
sudo nohup minikube tunnel --cleanup &
```

in linux:
```bash
minikube tunnel --bind-address 0.0.0.0
```

After all these steps; we should have a minikube cluster ready to install CP. We also have a minikube tunnel running to expose the ingress to the outside world.

## Prepare TIBCO Platform for minikube

After setting up [Platform Provisioner Prerequisite](https://github.com/TIBCOSoftware/platform-provisioner?tab=readme-ov-file#install-tekton-with-tekton-dashboard); 
we have Platform Provisioner installed in minikube.

Now we can run the following command under the project root to install third party tools for CP on minikube:

```bash
export PIPELINE_INPUT_RECIPE="docs/recipes/tp-base/tp-base-on-prem.yaml"
./dev/platform-provisioner-pipelinerun.sh
```

If we don't want to use minikube tunnel; then after installing the main ingress, we can forward the ingress port locally:
```bash
kubectl port-forward -n ingress-system --address 0.0.0.0 service/ingress-nginx-controller 80:http 443:https
```

## Deploy TIBCO Control Plane on minikube

Then we can install CP on minikube with the following command:

```bash
export PIPELINE_INPUT_RECIPE="docs/recipes/controlplane/tp-cp.yaml"
./dev/platform-provisioner-pipelinerun.sh
```

By default; maildev will be installed. You can access maildev using: http://maildev.localhost.dataplanes.pro

Environment variables that need to set in the recipe:
```yaml
meta:
  globalEnvVariable:
    # container registry
    CP_CONTAINER_REGISTRY: "csgprduswrepoedge.jfrog.io" # use jFrog for CP production deployment
    CP_CONTAINER_REGISTRY_USERNAME: ""
    CP_CONTAINER_REGISTRY_PASSWORD: ""
```

## Deploy TIBCO Data Plane on minikube

We can also use the same cluster for TIBCO Data Plane. 
