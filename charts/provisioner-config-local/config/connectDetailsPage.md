# Deploy TIBCO Platform using Platform Provisioner

The following steps will guide you to deploy TIBCO Platform using Platform Provisioner and Automation UI. 

## 1. Deploy Third Party supporting tools

Go to Deploy --> TP Cluster --> TP based on-perm with certificate

In #10 flow control; select `Install Automation UI`. 

## 2. Deploy TIBCO Platform

Go to Deploy --> Control Plane --> Standard Control Plane

After the deployment is completed; use TIBCO Platform Console link to reset admin password and login to TIBCO Platform Console.

## 3. Adjust DNS settings

Go to Maintenance --> TP Cluster --> Adjust CoreDNS Settings

This is needed as we will deploy DataPlane in the same cluster with ControlPlane.

## 4. Use Automation UI to deploy TIBCO Platform subscriptions and capabilities

Go to Automation UI and use following automation cases to deploy TIBCO Platform subscriptions and capabilities.
* Create new subscription with User Email. 
* Create K8s DataPlane
* Provision Flogo
* Create And Start Flogo App

## Default links

The following are the default links to access TIBCO Platform components:

* [TIBCO Platform Console](https://admin.cp1-my.localhost.dataplanes.pro)
* [TIBCO Platform](https://cp-sub1.cp1-my.localhost.dataplanes.pro)
* [E-mail server](https://mail.localhost.dataplanes.pro)
* [Automation UI](https://automation.localhost.dataplanes.pro)
