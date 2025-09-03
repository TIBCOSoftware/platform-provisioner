## Prepare ARO

### Verify if we can access the Azure account

Under the project root; run the following command to test the pipeline and Azure role. Use your own Azure account.
You need to make sure that you have log in to your Azure account. The platform provisioner script will create a docker container to run the pipeline scripts with the given recipe.
It will mount `"${HOME}"/.azure` folder to the docker container to access the Azure config.

```bash
export PIPELINE_INPUT_RECIPE="docs/recipes/tests/test-azure.yaml"

./dev/platform-provisioner.sh
```

### Create ARO cluster

After making sure that the pipeline can access the Azure account, we can now use deploy-tp-aro.yaml recipe to create a new ARO for TIBCO Platform.
Please make sure that you if you are using custom domain (recommended for CP), you create the certificates for your Apps and API Domains. 

```bash
export ACCOUNT="azure-" # Azure account prefix to trigger authenticating with Azure
export RED_HAT_OFFLINE_ACCESS_TOKEN="" # Input your Red Hat offline access token: Download it from https://access.redhat.com/management/api (you need to login to Red Hat account and generate the token)

# following are required for custom domain
export TP_CLUSTER_API_DOMAIN_TLS_CRT_BASE64="" # base64 encoded value of tls crt for api domain
export TP_CLUSTER_API_DOMAIN_TLS_KEY_BASE64="" # base64 encoded value of tls key for api domain
export TP_CLUSTER_APPS_DOMAIN_TLS_CRT_BASE64="" # base64 encoded value of tls crt for apps domain
export TP_CLUSTER_APPS_DOMAIN_TLS_KEY_BASE64="" # base64 encoded value of tls key for apps domain

# pipeline
export PIPELINE_INPUT_RECIPE="docs/recipes/k8s/cloud/deploy-tp-aro.yaml"

./dev/platform-provisioner.sh
```

We now have a new ARO to be ready to deploy TIBCO Platform.
Please make sure that you if you are using custom domain (recommended for CP), you create the certificates for your CP Domains. 

Environment variables that need to set in the recipe:
```yaml
meta:
  globalEnvVariable:
    TP_RESOURCE_GROUP: ""
    TP_CLUSTER_NAME: ""
    TP_TOP_LEVEL_DOMAIN: "" # Your top level domain name eg: azure.dataplanes.pro
    TP_SANDBOX: "" # Your sandbox name
    TP_MAIN_INGRESS_SANDBOX_SUBDOMAIN: "" # Your main ingress subdomain name. full domain will be: <TP_MAIN_INGRESS_SANDBOX_SUBDOMAIN>.<TP_SANDBOX>.<TP_TOP_LEVEL_DOMAIN>
    TP_DNS_RESOURCE_GROUP: "" # The resource group for the DNS zone
    # CP specific variables
    CP_INSTANCE_ID: "" # Your CP Instance Id, your domain will have this prefixed
    CP_SERVICE_DNS_DOMAIN_TLS_CRT_BASE64: "" # base64 encoded value of tls crt for CP My domain
    CP_SERVICE_DNS_DOMAIN_TLS_KEY_BASE64: "" # base64 encoded value of tls key for CP My domain
    CP_TUNNEL_DNS_DOMAIN_TLS_CRT_BASE64: "" # base64 encoded value of tls crt for CP Tunnel domain
    CP_TUNNEL_DNS_DOMAIN_TLS_KEY_BASE64: "" # base64 encoded value of tls crt for CP Tunnel domain
    # flow control
    TP_CREATE_ARO_CLUSTER: "false"
    TP_CLEAN_UP: "false"
    INSTALL_ARO_CP: "true"
```

## Deploy TIBCO Control Plane on ARO

Make sure that your kubeconfig can connect to the target ARO cluster. Then we can install CP on ARO with the following command:

```bash
export ACCOUNT="azure-" # Azure account prefix to trigger authenticating with Azure
export PIPELINE_INPUT_RECIPE="docs/recipes/controlplane/tp-cp.yaml"
export IS_AZURE_RED_HAT_OPENSHIFT_CLUSTER="true"

./dev/platform-provisioner.sh
```

By default; maildev will be NOT be installed. You can use Sendgrid API Key for your installation. 