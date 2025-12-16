## Prepare minikube

Install kind [link](https://kind.sigs.k8s.io/docs/user/quick-start/)

command to start kind:

in Mac:
```bash
kind create cluster --config - <<EOF
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: tp
nodes:
- role: control-plane
  kubeadmConfigPatches:
  - |
    kind: InitConfiguration
    nodeRegistration:
      kubeletExtraArgs:
        node-labels: "ingress-ready=true"
  extraPortMappings:
  - containerPort: 80
    hostPort: 80
    protocol: TCP
  - containerPort: 443
    hostPort: 443
    protocol: TCP
EOF
```

```bash
kubectl apply -f https://projectcontour.io/quickstart/contour.yaml
```

To delete kind cluster:
```bash
kind delete cluster -n tp
```

## Install TIBCO Platform for kind

```bash
./tp-install-on-prem.sh
```

Choose minikube as option to install TIBCO Platform. For more details, see [README.md](README.md)

## Access the TIBCO Platform

After installing the main ingress, we can forward the ingress port locally:
```bash
kubectl port-forward -n ingress-system --address 0.0.0.0 service/traefik 80:web 443:websecure
```
