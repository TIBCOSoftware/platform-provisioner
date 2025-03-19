# On-Premises setup automation

The goal of this automation is to create full running TP on-prem environment from scratch with one script. 

In the on-prem use case; we assume there will be an on-prem cluster running. The default target is Docker for Desktop.

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
Basically the `run.sh` script will: 
* Deploy on-prem tools like ingress, Postgres
* Deploy TIBCO Platform Control Plane
* Adjust resource and DNS for local on-prem use case
* Register admin user
* Create a new CP subscription
* Deploy a DP
* Deploy a capability

## Local development process for python automation

* Use local repo to generate recipe `./generate-recipe.sh 2 1`
* Deploy CP subscription normally `./run.sh 1`
* In this case the setup automation will mount `../tp-setup/bootstrap/` folder to the automation container. So you can edit the python automation code in your local machine and run the automation script in the container.
