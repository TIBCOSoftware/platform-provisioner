## Prepare AKS

### Verify if we can access the Azure account

Under the project root; run the following command to test the pipeline and Azure role. Use your own Azure account.
You need to make sure that you have log in to your Azure account. The platform provisioner script will create a docker container to run the pipeline scripts with the given recipe.
It will mount `.azure` folder to the docker container to access the Azure config.

```bash
export PIPELINE_INPUT_RECIPE="docs/recipes/tests/test-azure.yaml"

./dev/platform-provisioner.sh
```

### Create AKS cluster

After making sure that the pipeline can access the AWS account, we can now use deploy-tp-aks.yaml recipe to create a new AKS for TIBCO Platform.

```bash
export PIPELINE_INPUT_RECIPE="docs/recipes/k8s/cloud/deploy-tp-aks.yaml"

./dev/platform-provisioner.sh
```

We now have a new AKS to be ready to deploy TIBCO Platform.

Environment variables that need to set in the recipe:
```yaml
meta:
  globalEnvVariable:
    TP_RESOURCE_GROUP: ""
    TP_AUTHORIZED_IP: "" # Your public IP
    TP_CLUSTER_NAME: ""
    TP_DOMAIN: ""
```

## Deploy TIBCO Control Plane on AKS

Make sure that your kubeconfig can connect to the target AKS cluster. Then we can install CP on minikube with the following command:

```bash
export PIPELINE_INPUT_RECIPE="docs/recipes/controlplane/tp-cp.yaml"

./dev/platform-provisioner.sh
```

By default; maildev will be installed. You can access maildev using: http://maildev.localhost.dataplanes.pro

Environment variables that need to set in the recipe:
```yaml
meta:
  globalEnvVariable:
    CP_PROVIDER: "azure"
    CP_CLUSTER_NAME: ""
    CP_DNS_DOMAIN: ""
    CP_STORAGE_CLASS: ""

    # container registry
    CP_CONTAINER_REGISTRY: "" # use jFrog for CP production deployment
    CP_CONTAINER_REGISTRY_USERNAME: ""
    CP_CONTAINER_REGISTRY_PASSWORD: ""
```

