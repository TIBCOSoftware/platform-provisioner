## Prepare minikube

Install kind [link](https://kind.sigs.k8s.io/docs/user/quick-start/)

command to start kind:

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

## Prepare TIBCO Platform for kind

After setting up [Platform Provisioner Prerequisite](https://github.com/TIBCOSoftware/platform-provisioner?tab=readme-ov-file#install-tekton-with-tekton-dashboard);
we have Platform Provisioner installed in minikube.

Now we can run the following command under the project root to install third party tools for CP on minikube:

```bash
export PIPELINE_INPUT_RECIPE="docs/recipes/tp-base/tp-base-on-prem.yaml"
./dev/platform-provisioner-pipelinerun.sh
```
Environment variables that need to set in the recipe:
```yaml
meta:
  globalEnvVariable:
    CP_INGRESS_SERVICE_TYPE: NodePort # LoadBalancer, NodePort kind only work with NodePort
    CP_INGRESS_USE_HOSTPORT: false # true for kind
```

If we don't want to use NodePort for kind; then after installing the main ingress, we can forward the ingress port locally:
```bash
kubectl port-forward -n ingress-system --address 0.0.0.0 service/ingress-nginx-controller 80:http 443:https
```

## Deploy TIBCO Control Plane on kind

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
    CP_STORAGE_CREATE_PV: true
    CP_STORAGE_PV_NAME: "control-plane-pv" # control-plane-pv the name of PV for kind
```

* `CP_STORAGE_CREATE_PV`: We need to set to true for kind. It will create PV for kind. Kind don't support to create dynamic PV with ReadWriteMany. [GitHub issue](https://github.com/kubernetes-sigs/kind/issues/1487)

## Deploy TIBCO Data Plane on minikube

We can also use the same cluster for TIBCO Data Plane. 
