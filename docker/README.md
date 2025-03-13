# Dockerfiles
 
The 4 docker files are used to build the following images:
* `platform-provisioner:v1.0.0` or `platform-provisioner:latest` uses the `Dockerfile` to build the image.
  * This image is alpine based.
  * This is the default image contains tools and cloud binaries for provisioning the platform on SaaS environment.
  * The size of this image is around 3.16GB.
* `platform-provisioner:v1.0.0-on-prem` or `platform-provisioner:on-prem` uses the `Dockerfile-on-prem` to build the image.
  * This image is alpine based.
  * This image contains tools for provisioning the platform on on-prem environment. (remove the cloud binaries)
  * The size of this image is around 387MB.
* `platform-provisioner:v1.0.0-tester` or `platform-provisioner:tester` uses the `Dockerfile-tester` to build the image.
  * This image is ubuntu based.
  * This image contains tools and cloud binaries for provisioning the platform on SaaS environment and also contains the playwright python image.
  * The size of this image is around 6.4GB.
* `platform-provisioner:v1.0.0-tester-on-prem` or `platform-provisioner:tester-on-prem` uses the `Dockerfile-tester-on-prem` to build the image.
  * This image is ubuntu based.
  * This image contains tools for provisioning the platform on on-prem environment and also contains the playwright python image. (remove the cloud binaries)
  * The size of this image is around 3.77GB.

## Docker image for Platform Provisioner

We provide a Dockerfile to build the Docker image. The Docker image is used to run the pipeline. It contains the necessary tools to run the pipeline scripts.

<details>
<summary>Steps to build Docker image</summary>
To build Docker image locally, run the following command:

```bash
cd docker
./build.sh
```

This will build the Docker image called `platform-provisioner:latest`.

To build multi-arch Docker image and push to remote Docker registry, run the following command:

```bash
export DOCKER_REGISTRY="<your Docker registry repo>"
export PUSH_DOCKER_IMAGE=true
cd docker
./build.sh
```
This will build the Docker image called `<your Docker registry repo>/platform-provisioner:latest` and push to remote Docker registry.

</details>

> [!Note]
> For other options, please see [docker/build.sh](docker/build.sh).