# On-Premises automation

The goal of this automation is to create full running TP on-perm environment from scratch with one script. 

In the on-perm use case; we assume there will be a on-perm cluster running. The default target is Docker for Desktop.  

Basically the `run.sh` script will: 
* Deploy on-perm tools like ingress, Postgres
* Deploy TIBCO Platform Control Plane
* Adjust resource and DNS for local on-perm use case
* Register admin user
* Create a new CP subscription
* Deploy a DP
* Deploy a capability

We can copy the following recipes from provisioner GUI. 
```
01-tp-on-perm.yaml
02-tp-cp-on-perm.yaml
03-tp-adjust-dns.yaml
04-tp-adjust-resource.yaml
05-tp-auto-deploy-dp.yaml
```

Or use the `generate-recipe.sh` script to generate the skeleton and manually modify. (Adding tokens and certificates)
