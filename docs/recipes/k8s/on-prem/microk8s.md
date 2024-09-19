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

Now we can use the recipe `tp-base-on-prem-https.yaml` to install third party tools for CP on MicroK8s. Before we run the recipe; we need to set the following environment variables in the recipe:

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
    GUI_TP_STORAGE_CLASS: microk8s-hostpath
    GUI_TP_INSTALL_POSTGRES: true
    GUI_PIPELINE_LOG_DEBUG: false
```

Now we can run the following command under the project root to install third party tools for CP on MicroK8s:

```bash
export PIPELINE_INPUT_RECIPE="docs/recipes/tp-base/tp-base-on-prem-https.yaml"
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
    GUI_CP_ENV: vagrant
    # container registry
    GUI_CP_CONTAINER_REGISTRY: csgprduswrepoedge.jfrog.io
    GUI_CP_CONTAINER_REGISTRY_USERNAME: ""
    GUI_CP_CONTAINER_REGISTRY_PASSWORD: ""
    GUI_CP_CONTAINER_REGISTRY_REPOSITORY: tibco-platform-docker-prod
    # TLS
    GUI_TP_TLS_CERT: ""
    GUI_TP_TLS_KEY: ""
    # version
    GUI_CP_PLATFORM_BOOTSTRAP_VERSION: 1.3.36
    GUI_CP_PLATFORM_BASE_VERSION: 1.3.337
    # storage
    GUI_CP_STORAGE_CLASS: microk8s-hostpath
    GUI_CP_STORAGE_CREATE_PV: false
    GUI_CP_STORAGE_PV_NAME: "" # control-plane-pv the name of PV for kind
```

For the CP public repo, we only need to provide the following:
* `GUI_CP_CONTAINER_REGISTRY_USERNAME`
* `GUI_CP_CONTAINER_REGISTRY_PASSWORD`

```bash
export PIPELINE_INPUT_RECIPE="docs/recipes/controlplane/tp-cp.yaml"
./dev/platform-provisioner-pipelinerun.sh
```

By default; maildev will be installed. You can access maildev using: http://maildev.localhost.dataplanes.pro

## Deploy TIBCO Data Plane on MicroK8s

We can also use the same cluster for TIBCO Data Plane. 
