# Setup Data Plane

The following instructions is for setting up a data plane in your Kubernetes cluster.

> [!NOTE]
> The steps below assumes that you have a Kubernetes cluster ready. If not, please follow the steps in <a href="README.md">README.md</a> to create your Kubernetes cluster.

> [!NOTE]
> All value within \<\< >> is replacable.

#### Table of Contents

1. [Step 1 - Register Data Plane](#step1)
2. [Step 2 - Setup Data Plane In Control Plane](#step2)

# Steps

<a name="step1" />

## Step 1 - Register Data Plane

1. Use a browser and login to TIBCO Platform Control Plane (e.g., https://\<\<...>>.tibco.com)

2. Register a Data Plane > Existing Kubernetes Cluster - Start
    - Data Plane Name: \<\<dev-dp-eks>>
    - Provider: AWS
    - Region: \<\<N. Virginia (us-east-1)>>
    - I have read and accepted the TIBCO End User Agreement (EUA): [Checked]
    - Select *Next*
    - Namespace: \<\<tibco-ns>>
    - Service Account: \<\<tibco-sa>>
    - Allow cluster scoped permissions: [Enabled]
    - Select *Next*
    - Deployment of fluentbit sidecar for Services logs: [Checked]
    - Select *Next*
    - Capture the commands below to be run from the Bastion host (remember to run "source ${HOME}/setenv.sh" first if you have not done so already). \
      Note: The below is just a sample. Do not run as-is. 

        ```
        === Namespace Creation ===
        kubectl apply -f - <<EOF
        apiVersion: v1
        kind: Namespace
        metadata:
          name: tibco-ns
          labels:
            platform.tibco.com/dataplane-id: csuhcc6h8mo4uiepu5b0
        EOF

        === Service Account Creation ===
        helm upgrade --install -n tibco-ns dp-configure-namespace dp-configure-namespace --repo https://tibcosoftware.github.io/tp-helm-charts --version 1.3.4 --set global.tibco.dataPlaneId=<<...>> --set global.tibco.primaryNamespaceName=tibco-ns --set global.tibco.serviceAccount=tibco-sa --set global.tibco.enableClusterScopedPerm=true

        === Cluster Registration ===
        helm upgrade --install dp-core-infrastructure dp-core-infrastructure -n tibco-ns --repo https://tibcosoftware.github.io/tp-helm-charts --version 1.3.16 --set global.tibco.dataPlaneId=<<...>> --set global.tibco.subscriptionId=cn1r99d8el1deih7pkt0 --set tp-tibtunnel.configure.accessKey=<<...>> --set tp-tibtunnel.connect.url=<<...>> --set global.tibco.containerRegistry.url=csgprduswrepoedge.jfrog.io --set global.tibco.serviceAccount=tibco-sa --set global.tibco.containerRegistry.username=<<...>> --set global.tibco.containerRegistry.password=<<...>> --set global.tibco.containerRegistry.repository=tibco-platform-docker-prod --set global.tibco.containerRegistry.email=tibco-plt@cloud.com --set global.proxy.noProxy='' --set global.logging.fluentbit.enabled=true
        ```

    - Select *Done*

<a name="step2" />

## Step 2 - Setup Data Plane In Control Plane

### Configure Storage Class and Ingress Controller

1. Go to Data Plane > Data Plane configuration > Add Storage Class
    - Resource Name: diskstorageclass
    - Description: disk storage class
    - Storage Class Name: ebs-gp3
    - Select *Add*

2. Go to Data Plane > Data Plane configuration > Add Ingress Controller
    - Ingress Controller: nginx
    - Resource Name: bwce
    - Ingress Class Name: nginx
    - FQDN: bwce.tp-ingress.cs-nam.dataplanes.pro
    - Select *Add*

3. Go to Data Plane > Data Plane configuration > Add Ingress Controller
    - Ingress Controller: nginx
    - Resource Name: flogo
    - Ingress Class Name: nginx
    - FQDN: flogo.tp-ingress.cs-nam.dataplanes.pro
    - Select *Add*

### Configure Observability 

1. Go to Data Plane > Data Plane configuration > Observability > Add new resource
2. Configure Log Server
    - Data plane resource name: user-app-log
    - User Apps
        - Query Service enabled: [Enabled]
        - Query Service configurations > Add Query Service Configuration 
            - Query Service name: user-app-query-service
            - Query Service type: ElasticSearch
            - Log Index: user-app-dp 
            - Endpoint: https://dp-config-es-es-http.elastic-system.svc.cluster.local:9200
            - Username: elastic
            - Password: \<\<...>> (Use kubectl get secret dp-config-es-es-elastic-user -n elastic-system -o jsonpath="{.data.elastic}" | base64 --decode; echo)
            - Select *Save Query Service*
        - Exporter enabled: [Enabled]
        - Exporter configurations > Add Exporter configuration
            - Exporter name: user-app-exporter
            - Exporter type: ElasticSearch
            - Log Index: user-app-dp 
            - Endpoint: https://dp-config-es-es-http.elastic-system.svc.cluster.local:9200
            - Username: elastic
            - Password: \<\<...>> (Use kubectl get secret dp-config-es-es-elastic-user -n elastic-system -o jsonpath="{.data.elastic}" | base64 --decode; echo)        
            - Select *Save Exporter*
        - Services
        - Exporter enabled: [Enabled]
        - Exporter configurations > Add Exporter Configuration
            - Exporter name: service-exporter
            - Exporter type: ElasticSearch
            - Log Index: tibco-services-dp 
            - Endpoint: https://dp-config-es-es-http.elastic-system.svc.cluster.local:9200
            - Username: elastic
            - Password: \<\<...>> (Use kubectl get secret dp-config-es-es-elastic-user -n elastic-system -o jsonpath="{.data.elastic}" | base64 --decode; echo)        
            - Select *Save Exporter*
        - [Select All] > Next 

3. Configure Metrics Server
    - Query Service configurations > Add Query Service Configuration 
        - Query Service name: metrics-query-service
        - Query Service type: Prometheus
        - Endpoint: http://kube-prometheus-stack-prometheus.prometheus-system.svc.cluster.local:9090
        - Username: 
        - Password: 
        - Select *Save Query Service*
    - Exporter enabled: [Enabled]
    - Exporter configurations > Add Exporter configuration
        - Exporter name: metrics-exporter
        - Exporter type: Prometheus
        - Select *Save Exporter*
    - [Select All] > Next

4. Configure Traces Server
    - Query Service enabled: [Enabled]
    - Query Service configurations > Add Query Service Configuration 
        - Query Service name: traces-query-service
        - Query Service type: ElasticSearch
        - Endpoint: https://dp-config-es-es-http.elastic-system.svc.cluster.local:9200
        - Username: elastic
        - Password: \<\<...>> (Use kubectl get secret dp-config-es-es-elastic-user -n elastic-system -o jsonpath="{.data.elastic}" | base64 --decode; echo)
        - Select *Save Query Service*
    - Exporter enabled: [Enabled]
    - Exporter configurations > Add Exporter configuration
        - Exporter name: traces-exporter
        - Exporter type: ElasticSearch
        - Endpoint: https://dp-config-es-es-http.elastic-system.svc.cluster.local:9200
        - Username: elastic
        - Password: \<\<...>> (Use kubectl get secret dp-config-es-es-elastic-user -n elastic-system -o jsonpath="{.data.elastic}" | base64 --decode; echo)        
        - Select *Save Exporter*
    - [Select All] > Save
  
### Provision Capabilities

> [!NOTE]
> After provisioning each capabilities below, you might have to wait a little while for it to detect the status and turn green.

#### Provision BWCE

1. Go to Data Plane > Provision a capability > Provision TIBCO BusinessWorks Container Edition > Start
    - Storage Class (1): diskstorageclass
    - Ingress Controller (2): bwce
2. Select *Next* 
    - Path Prefix (leave this as-is, else provisioning will fail): /tibco/bw/\<\<...>>
    - I have read and accepted the TIBCO End User Agreement (EUA): [Checked]
3. Select *BWCE Provision Capability*

#### Provision Flogo

1. Go to Data Plane > Provision a capability > Provision TIBCO Flogo Enterprise > Start
    - Storage Class (1)
    - Ingress Controller (2): flogo
2. Select *Next*
    - Path Prefix (leave this as-is): /tibco/flogo/\<\<...>>
    - I have read and accepted the TIBCO End User Agreement (EUA): [Checked]
3. Select *Provision Flogo Version*

#### Provision EMS

1. Go to Data Plane > Provision a capability > Provision TIBCO Enterprise Message Service > Start
    - Message Storage 1: diskstorageclass
    - Log Storage 1: diskstorageclass
2. Select *Next*
    - Server Name: \<\<ems1>>
    - Server Environment: \<\<dev>>
    - Server Sizing: \<\<small>>
    - Capability is for production: [Unchecked]
    - Logs storage is shared: [Unchecked]
    - Use Custom Config: [Unchecked]
    - I have read and accepted the TIBCO End User Agreement (EUA): [Checked]
3. Select *Next*
4. Select *Provision TIBCO Enterprise Message Service*

#### Provision Service Mesh

1. Go to Data Plane > Provision a capability > Provision Service Mesh > Start
    - I have read and accepted the TIBCO End User Agreement (EUA): [Checked]
2. Select *Provision capability*

#### Provision Quasar

1. Go to Data Plane > Provision a capability > Provision TIBCO Messaging Quasar - Powered by Apache Pulsar > Start
    - Message Storage: diskstorageclass
    - Journal Storage: diskstorageclass
    - Log Storage: diskstorageclass
2. Select *Next*
    - Server Name: \<\<pulsar1>>
    - Server Environment: \<\<dev>>
    - Server Sizing: \<\<small>>
    - Capability is for production: [Unchecked]
    - Logs storage is shared: [Unchecked]
    - Use Custom Config: [Unchecked]
    - I have read and accepted the TIBCO End User Agreement (EUA): [Checked]
3. Selext *Next*
3. Select *Provision TIBCO Messaging Quasar - Powered by Apache Pulsar*

#### Provision Developer Hub

1. Go to Data Plane > Provision a capability > Provision TIBCO Developer Hub > Start
...