# On-Premises Setup Automation

## Overview

This automation provides a complete, script-driven workflow to deploy a full TIBCO Platform (TP) on-premises environment from scratch. The automation generates recipe files from a Helm chart and executes them in sequence to set up infrastructure, deploy the Control Plane (CP), configure networking, and optionally deploy Data Planes (DP) and supporting services.

**Key Features:**
- **Recipe-based deployment**: All configuration is defined in declarative YAML recipe files
- **Modular approach**: Each recipe handles a specific part of the deployment
- **Flexible execution**: Run individual recipes or the complete automation
- **Environment agnostic**: Supports Docker Desktop, minikube, kind, MicroK8s, and OpenShift

**Prerequisites:**
- A running Kubernetes cluster (default target: Docker Desktop)
- `yq` installed for YAML processing
- `helm` installed for chart operations
- Access to TIBCO container registries (jFrog)

## Generated Recipe Files

The `generate-recipe.sh` script extracts recipe definitions from the `provisioner-config-local` Helm chart and generates up to 7 YAML recipe files:

| Recipe File | Purpose | Source Template |
|------------|---------|-----------------|
| **01-tp-on-prem.yaml** | Deploy base infrastructure (Ingress, PostgreSQL, certificates, storage) | `pp-deploy-tp-base-on-prem-cert.yaml` |
| **02-tp-cp-on-prem.yaml** | Deploy TIBCO Platform Control Plane | `pp-deploy-cp-core-on-prem.yaml` |
| **03-tp-adjust-dns.yaml** | Configure CoreDNS for local domain resolution | `pp-maintain-tp-config-coredns.yaml` |
| **04-tp-adjust-resource.yaml** | Remove resource limits for local development | `pp-maintain-tp-remove-resource.yaml` |
| **05-tp-auto-deploy-dp.yaml** | Automated DP deployment and capability configuration | `pp-maintain-tp-automation-o11y.yaml` |
| **06-tp-o11y-stack.yaml** | Deploy observability stack (Elasticsearch, Prometheus, Kibana, APM) | `pp-o11y-full.yaml` |
| **07-tp-bw5-stack.yaml** | Deploy BusinessWorks 5 stack (RVDM, EMS, Hawk, BW5) | `pp-maintain-tp-deploy-bw5dm.yaml` |

See [RECIPES.md](RECIPES.md) for detailed documentation of each recipe file.

## Setup flow for local on-prem use case

After changing the provisioner-config-local helm chart, you can follow the steps below to validate the changes.

### 0. check out the project and navigate to current folder

### 1. Generate recipe from provisioner-config-local helm chart
```bash
# generate all recipes from local provisioner-config-local helm chart
./generate-recipe.sh 2 1
```

### 2. Adjust recipe for your k8s environment
```bash
# choose the environment you will deploy to (default is Docker for Desktop)
./adjust-recipe.sh
```

### 3. (Optional) Adjust ingress for your k8s environment
```bash
# 1 for nginx, 2 for traefik
./adjust-ingress.sh
```

### 4. (Optional) Update recipe tokens
```bash
./update-recipe-tokens.sh
```

### 4. Install the full TP on-prem environment
Before trigger the run.sh script; you can manually set TP versions that you want to install on 02-tp-cp-on-prem.yaml file.
```bash
./run.sh 1
```

## What happens in the run.sh script?

The `run.sh` script orchestrates the complete deployment by executing recipes in the correct sequence.

**Full Deployment (Option 1)** executes in this order:
1. **Deploy base infrastructure** (recipe 01) - Ingress controller, PostgreSQL, certificates, storage
2. **Deploy O11y stack** (recipe 06) - Elasticsearch, Prometheus, Kibana for observability
3. **Cleanup resources** (recipe 04) - Remove resource limits for local development
4. **Deploy Control Plane** (recipe 02) - TIBCO Platform CP with platform-bootstrap and platform-base
5. **Adjust DNS** (recipe 03) - Configure CoreDNS for `*.localhost.dataplanes.pro` domain
6. **Cleanup resources again** (recipe 04) - Ensure all new resources have limits removed
7. **Deploy DP automation** (recipe 05) - Register admin user, create subscription, deploy DP, configure capabilities

**Individual deployment options** are also available:
- Option 2: Deploy only base infrastructure (recipe 01)
- Option 3: Deploy only Control Plane with all capabilities (recipe 02)
- Option 4: Deploy only CP subscription and DP automation (recipe 05)
- Option 5: Deploy only O11y stack (recipe 06)
- Option 6: Run resource cleanup (recipe 04)
- Option 7: Redeploy O11y stack for troubleshooting (recipe 06)
- Option 8: Deploy BW5 stack (recipe 07)

**Retry Logic**: The subscription deployment (recipe 05) includes automatic retry logic with configurable retry count (`TP_SUBSCRIPTION_DEPLOY_RETRY_COUNT`, default: 10) to handle transient failures during DP provisioning.

**Note**: Recipe 02 deploys the complete Control Plane including tibco-cp-base, tibco-cp-bw, tibco-cp-flogo, tibco-cp-devhub, tibco-cp-messaging, tibco-cp-hawk, and tibco-cp-addon-eventprocessing charts. See [RECIPES.md](RECIPES.md) for details.

## Local development process for python automation

* Use local repo to generate recipe `./generate-recipe.sh 2 1`
* Deploy CP subscription normally `./run.sh 1`
* In this case the setup automation will mount `../tp-setup/bootstrap/` folder to the automation container. So you can edit the python automation code in your local machine and run the automation script in the container.
