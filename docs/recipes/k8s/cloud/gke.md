## Prepare GKE

### Verify if we can access the GCP account

Under the project root; run the following command to test the pipeline and GCP permission. Use your own GCP project and GCP profile.
You need to make sure that you have log in to your GCP account. The platform provisioner script will create a docker container to run the pipeline scripts with the given recipe.
It will mount `"${HOME}"/.config/gcloud` folder to the docker container to access the GCP profile.

```bash
export ACCOUNT="" # starts with gcp-
export PIPELINE_INPUT_RECIPE="docs/recipes/tests/test-gcp.yaml"

./dev/platform-provisioner.sh
```

### Create GKE cluster

After making sure that the pipeline can access the GCP project, we can now use deploy-tp-gke.yaml recipe to create a new GKE for TIBCO Platform.

```bash
export ACCOUNT=""
export PIPELINE_INPUT_RECIPE="docs/recipes/k8s/cloud/deploy-tp-gke.yaml"

./dev/platform-provisioner.sh
```

We now have a new GKE to be ready to deploy TIBCO Platform.

Environment variables that need to set in the recipe:
```yaml
meta:
  globalEnvVariable:
    # GCP settings
    GCP_PROJECT_ID: ""
    # TP cluster
    TP_CLUSTER_NAME: ""
    TP_CLUSTER_REGION: "us-west1"
    # domain
    TP_TOP_LEVEL_DOMAIN: ""
    TP_SANDBOX: ""
    TP_MAIN_INGRESS_SANDBOX_SUBDOMAIN: ""
    TP_AUTHORIZED_IP: "" # Your public ip address eg: x.x.x.x/32
```

## Deploy TIBCO Control Plane on GKE

Make sure that your kubeconfig can connect to the target GKE cluster. Then we can install CP on GKE with the following command:

```bash
export ACCOUNT=""
export PIPELINE_INPUT_RECIPE="docs/recipes/controlplane/tp-cp.yaml"

./dev/platform-provisioner.sh
```

By default; maildev will be installed. You can access maildev using: http://mail.<CP_DNS_DOMAIN>

Environment variables that need to set in the recipe:
```yaml
meta:
  globalEnvVariable:
    # GCP settings
    GCP_PROJECT_ID: ""
    GCP_REGION: "" # GCP region
    # container registry
    CP_CONTAINER_REGISTRY: "" # use jFrog for CP production deployment 
    CP_CONTAINER_REGISTRY_USERNAME: ""
    CP_CONTAINER_REGISTRY_PASSWORD: ""

    CP_CLUSTER_NAME: ""
    CP_DNS_DOMAIN: ""
    CP_STORAGE_CLASS: "standard-rwx-tp" # We create a new storage class for CP
    CP_STORAGE_PV_SIZE: "1Ti" # minimum 1Ti
    TP_CLUSTER_CIDR: "10.1.0.0/16" # match with deploy-tp-gke.yaml recipe

    CP_INGRESS_CLASSNAME: "nginx" 
```
