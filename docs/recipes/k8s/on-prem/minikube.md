## Prepare minikube

Install minikube [link](https://minikube.sigs.k8s.io/docs/start/)

command to start minikube:

in Mac:
```bash
minikube start --memory 28672 --disk-size "40g" \
--driver=docker \
--addons storage-provisioner
```

in linux:
This 28G memory with 24 cores can run DP with flogo, bwce, messaging and tibco-hub
```bash
minikube start --memory 28672 --disk-size "40g" \
--driver=docker \
--addons storage-provisioner
```

Now we should have a minikube cluster ready to install CP.

## Install TIBCO Platform for minikube

```bash
./tp-install-on-prem.sh
```

Choose minikube as option to install TIBCO Platform. For more details, see [README.md](README.md)

## Use minikube tunnel

If you want to expose the service to the public, you can use minikube tunnel to expose the service to the public. You can use the following command to start the tunnel:

```bash
sudo nohup minikube tunnel --cleanup &
minikube tunnel --bind-address 0.0.0.0
```
