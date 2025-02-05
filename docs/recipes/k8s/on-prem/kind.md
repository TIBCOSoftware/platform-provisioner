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

Now we can use the recipe `tp-base-on-prem-https.yaml` to install third party tools for CP on minikube. Before we run the recipe; we need to set the following environment variables in the recipe:

> [!Note]
> You can use your own domain with public validate certificate.
> TIBCO Control Plane currently only works with domain that has public validate certificate.

```yaml
meta:
  guiEnv:
    note: "deploy-tp-base-on-prem-cert"
    GUI_TP_DNS_DOMAIN: localhost.dataplanes.pro
    GUI_TP_TLS_CERT: ""
    GUI_TP_TLS_KEY: ""
    GUI_TP_INSTALL_NGINX_INGRESS: true
    GUI_TP_INGRESS_SERVICE_TYPE: ClusterIP
    GUI_TP_STORAGE_CLASS: standard
    GUI_TP_INSTALL_POSTGRES: true
    GUI_PIPELINE_LOG_DEBUG: false
```

Now we can run the following command under the project root to install third party tools for CP on minikube:

```bash
export PIPELINE_INPUT_RECIPE="docs/recipes/tp-base/tp-base-on-prem-https.yaml"
./dev/platform-provisioner-pipelinerun.sh
```

After installing the main ingress, we can forward the ingress port locally:
```bash
kubectl port-forward -n ingress-system --address 0.0.0.0 service/ingress-nginx-controller 80:http 443:https
```

## Deploy TIBCO Control Plane on kind

Then we can install CP on kind with the following command:

Environment variables that need to set in the recipe:
```yaml
meta:
  guiEnv:
    note: "deploy-cp-on-prem"
    # github
    GUI_GITHUB_TOKEN: ""
    GUI_CP_CHART_REPO: "https://tibcosoftware.github.io/tp-helm-charts"
    GUI_CP_ADMIN_EMAIL: "cp-test@tibco.com"
    GUI_DP_CHART_REPO: "https://tibcosoftware.github.io/tp-helm-charts"
    GUI_DP_CHART_REPO_TOKEN: ""
    # env
    GUI_CP_INSTANCE_ID: cp1
    # container registry
    GUI_CP_CONTAINER_REGISTRY: csgprduswrepoedge.jfrog.io
    GUI_CP_CONTAINER_REGISTRY_USERNAME: ""
    GUI_CP_CONTAINER_REGISTRY_PASSWORD: ""
    GUI_CP_CONTAINER_REGISTRY_REPOSITORY: tibco-platform-docker-prod
    # TLS
    GUI_TP_TLS_CERT: ""
    GUI_TP_TLS_KEY: ""
    # version
    GUI_CP_PLATFORM_BOOTSTRAP_VERSION: 1.4.85
    GUI_CP_PLATFORM_BASE_VERSION: 1.4.280
    # storage
    GUI_CP_STORAGE_CLASS: standard
    GUI_CP_STORAGE_CREATE_PV: true
    GUI_CP_STORAGE_PV_NAME: "control-plane-pv" # control-plane-pv the name of PV for kind
```

For the CP public repo, we only need to provide the following:
* `GUI_CP_CONTAINER_REGISTRY_USERNAME`
* `GUI_CP_CONTAINER_REGISTRY_PASSWORD`
* `GUI_CP_STORAGE_CREATE_PV`: We need to set to true for kind. It will create PV for kind. Kind don't support to create dynamic PV with ReadWriteMany. [GitHub issue](https://github.com/kubernetes-sigs/kind/issues/1487)

```bash
export PIPELINE_INPUT_RECIPE="docs/recipes/controlplane/tp-cp.yaml"
./dev/platform-provisioner-pipelinerun.sh
```

By default; maildev will be installed. You can access maildev using: http://mail.localhost.dataplanes.pro

## Deploy TIBCO Data Plane on minikube

We can also use the same cluster for TIBCO Data Plane. 
