## Prepare MicroK8s

Install MicroK8s [link](https://microk8s.io/docs/install-alternatives)

command to start MicroK8s:

in Mac:
```bash
microk8s install --cpu 4 --mem 15 --disk 40 && \
microk8s enable hostpath-storage && \
microk8s enable dns
```

We can use the following command to get the MicroK8s cluster config: 
```bash
microk8s config > ~/.kube/microk8s.yaml
export KUBECONFIG=~/.kube/microk8s.yaml
```

## Prepare TIBCO Platform for MicroK8s

After setting up [Platform Provisioner Prerequisite](https://github.com/TIBCOSoftware/platform-provisioner?tab=readme-ov-file#install-tekton-with-tekton-dashboard);
we have Platform Provisioner installed in MicroK8s.

Now we can run the following command under the project root to install third party tools for CP on MicroK8s:

```bash
export PIPELINE_INPUT_RECIPE="docs/recipes/tp-base/tp-base-on-prem.yaml"
./dev/platform-provisioner-pipelinerun.sh
```

Environment variables that need to set in the recipe:
```yaml
meta:
  globalEnvVariable:
    CP_STORAGE_CLASS: "microk8s-hostpath"
```

After installing the main ingress, we can forward the ingress port locally:
```bash
kubectl port-forward -n ingress-system --address 0.0.0.0 service/ingress-nginx-controller 80:http 443:https
```

## Deploy TIBCO Control Plane on MicroK8s

Then we can install CP on MicroK8s with the following command:

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
    CP_STORAGE_CLASS: "microk8s-hostpath"
    CP_STORAGE_CREATE_PV: true
    CP_STORAGE_PV_NAME: "control-plane-pv"
```

## Deploy TIBCO Data Plane on MicroK8s

We can also use the same cluster for TIBCO Data Plane. 
