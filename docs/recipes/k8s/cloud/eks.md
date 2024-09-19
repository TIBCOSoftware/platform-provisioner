## Prepare EKS

### Verify if we can access the AWS account

Under the project root; run the following command to test the pipeline and aws role. Use your own AWS account and AWS profile.
You need to make sure that you have login to your AWS account. The platform provisioner script will create a docker container to run the pipeline scripts with the given recipe.
It will mount `"${HOME}"/.aws` folder to the docker container to access the AWS profile.

```bash
export ACCOUNT=""
export AWS_PROFILE=""
export PIPELINE_INPUT_RECIPE="docs/recipes/tests/test-aws.yaml"

./dev/platform-provisioner.sh
```

### Create EKS cluster

After making sure that the pipeline can access the AWS account, we can now use deploy-tp-eks.yaml recipe to create a new EKS for TIBCO Platform.

```bash
export ACCOUNT=""
export AWS_PROFILE=""
export PIPELINE_INPUT_RECIPE="docs/recipes/k8s/cloud/deploy-tp-eks.yaml"

./dev/platform-provisioner.sh
```

We now have a new EKS to be ready to deploy TIBCO Platform.

Environment variables that need to set in the recipe:
```yaml
meta:
  globalEnvVariable:
    PIPELINE_AWS_MANAGED_ACCOUNT_ROLE: "" #AWS Role which needs to be assumed
    TP_CLUSTER_NAME: ""
    TP_DOMAIN: ""
```

## Deploy TIBCO Control Plane on EKS

Make sure that your kubeconfig can connect to the target EKS cluster. Then we can install CP on EKS with the following command:

```bash
export ACCOUNT=""
export AWS_PROFILE=""
export PIPELINE_INPUT_RECIPE="docs/recipes/controlplane/tp-cp.yaml"

./dev/platform-provisioner.sh
```

By default; maildev will be installed. You can access maildev using: http://mail.<CP_DNS_DOMAIN>

Environment variables that need to set in the recipe:
```yaml
meta:
  globalEnvVariable:
    PIPELINE_AWS_MANAGED_ACCOUNT_ROLE: "" #AWS Role which needs to be assumed
    # container registry
    CP_CONTAINER_REGISTRY: "" # use jFrog for CP production deployment 
    CP_CONTAINER_REGISTRY_USERNAME: ""
    CP_CONTAINER_REGISTRY_PASSWORD: ""

    CP_CLUSTER_NAME: ""
    CP_DNS_DOMAIN: ""
    CP_STORAGE_CLASS: "" 

    CP_INGRESS_CLASSNAME: "nginx" 
    CP_SKIP_BOOTSTRAP_INGRESS: true #This bootstrap ingress is needed in case of onprem minikube etc, needs to be skipped for aws
```
