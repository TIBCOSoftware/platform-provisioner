#
# Copyright (c) 2024-2025 TIBCO Software Inc.
# All Rights Reserved. Confidential & Proprietary.
#

#---------------------------------------------------------------------------------------------
# BUILD AWSCLI V2 offical doc:
# https://docs.aws.amazon.com/cli/latest/userguide/getting-started-source-install.html#source-getting-started-install-workflows-alpine
# release notes: https://raw.githubusercontent.com/aws/aws-cli/v2/CHANGELOG.rst

FROM python:3.12.11-alpine3.22 AS builder-aws
ARG AWS_CLI_VERSION
ENV AWS_CLI_VERSION=${AWS_CLI_VERSION:-"2.28.11"}

# Install build dependencies
RUN apk add --no-cache \
    curl \
    make \
    cmake \
    gcc \
    g++ \
    libc-dev \
    libffi-dev \
    openssl-dev \
    && curl https://awscli.amazonaws.com/awscli-${AWS_CLI_VERSION}.tar.gz | tar -xz \
    && cd awscli-${AWS_CLI_VERSION} \
    && ./configure --prefix=/opt/aws-cli/ --with-download-deps \
    && make \
    && make install

#---------------------------------------------------------------------------------------------
# install Azure CLI
# https://github.com/Azure/azure-cli/issues/19591
# https://github.com/Azure/azure-cli/releases
# https://learn.microsoft.com/en-us/cli/azure/run-azure-cli-docker?view=azure-cli-latest

FROM python:3.12.11-alpine3.22 AS builder-azure
ARG AZURE_CLI_VERSION
ENV AZURE_CLI_VERSION=${AZURE_CLI_VERSION:-"2.76.0"}
WORKDIR /azure
RUN apk add --no-cache --update python3 py3-pip && \
    apk add --no-cache --update --virtual=build gcc musl-dev python3-dev libffi-dev openssl-dev cargo make && \
    python -m venv .venv && .venv/bin/pip install -U pip && \
    .venv/bin/pip --no-cache-dir install azure-cli==${AZURE_CLI_VERSION} && \
    find / -name __pycache__ | xargs -r rm -rf

#---------------------------------------------------------------------------------------------
# actual run time docker image
FROM alpine:3.22

LABEL maintainer="cloud@tibco.com"
# labels see: https://github.com/opencontainers/image-spec/blob/56fb7838abe52ee259e37ece4b314c08bd45997f/annotations.md#annotations
LABEL org.opencontainers.image.title="platform-provisioner"
LABEL org.opencontainers.image.description="This provide basic tools for platform provisioner pipelines."
LABEL org.opencontainers.image.source="https://github.com/TIBCOSoftware/tp-helm-charts"
LABEL org.opencontainers.image.vendor="Cloud Software Group"

ARG TARGETOS TARGETARCH

# base packages
RUN apk add --no-cache --upgrade coreutils util-linux gettext bash gcompat curl wget envsubst jq \
        openssl openssh git python3 yq kubectl helm postgresql-client docker-cli && rm -rf /var/cache/apk/*

# COPY AWSCLI V2 to BASE_IMAGE
COPY --from=builder-aws /opt/aws-cli/ /opt/aws-cli/
RUN ln -s /opt/aws-cli/bin/aws /usr/local/bin/aws && \
    aws --version

# eksctl https://github.com/eksctl-io/eksctl/releases
ARG EKSCTL_VERSION
ENV EKSCTL_VERSION=${EKSCTL_VERSION:-"v0.212.0"}
RUN CMD_NAME=eksctl && \
    curl --silent --location "https://github.com/eksctl-io/eksctl/releases/download/${EKSCTL_VERSION}/${CMD_NAME}_$(uname -s)_${TARGETARCH}.tar.gz" | tar xz -C /tmp && \
    chmod +x /tmp/${CMD_NAME} && mv /tmp/${CMD_NAME} /usr/local/bin/${CMD_NAME}-${EKSCTL_VERSION} && \
    ln -sf /usr/local/bin/${CMD_NAME}-${EKSCTL_VERSION} /usr/local/bin/${CMD_NAME} && \
    ${CMD_NAME} version

# aws ecr credentials helper
# https://github.com/awslabs/amazon-ecr-credential-helper/releases
ARG ECR_LOGIN_VERSION
ENV ECR_LOGIN_VERSION=${ECR_LOGIN_VERSION:-"0.9.0"}
RUN CMD_NAME=docker-credential-ecr-login && \
    curl --silent --location "https://amazon-ecr-credential-helper-releases.s3.us-east-2.amazonaws.com/${ECR_LOGIN_VERSION}/${TARGETOS}-${TARGETARCH}/docker-credential-ecr-login" -o /tmp/${CMD_NAME} && \
    chmod +x /tmp/${CMD_NAME} && mv /tmp/${CMD_NAME} /usr/local/bin/${CMD_NAME}-${ECR_LOGIN_VERSION} && \
    ln -sf /usr/local/bin/${CMD_NAME}-${ECR_LOGIN_VERSION} /usr/local/bin/${CMD_NAME} && \
    ${CMD_NAME} -v

# COPY azure cli to BASE_IMAGE
COPY --from=builder-azure /azure /azure
RUN ln -s /usr/bin/python3 /usr/local/bin/python && ln -s /azure/.venv/bin/az /usr/local/bin/az && \
    az version

# Azure CLI Bicep https://github.com/Azure/bicep/releases
ARG AZURE_CLI_BICEP_VERSION
ENV AZURE_CLI_BICEP_VERSION=${AZURE_CLI_BICEP_VERSION:-"v0.37.4"}
RUN echo "AZURE_CLI_BICEP_VERSION=${AZURE_CLI_BICEP_VERSION}" && \
    az --version && \
    az bicep install --version ${AZURE_CLI_BICEP_VERSION} && \
    az extension add --name aks-preview && \
    az extension update --name aks-preview

# gcloud cli https://cloud.google.com/sdk/docs/release-notes
ARG CLOUD_SDK_VERSION
ENV CLOUD_SDK_VERSION=${CLOUD_SDK_VERSION:-"534.0.0"}
ENV PATH=/google-cloud-sdk/bin:$PATH
RUN if [ `uname -m` = 'x86_64' ]; then echo -n "x86_64" > /tmp/arch; else echo -n "arm" > /tmp/arch; fi;
RUN ARCH=`cat /tmp/arch` && \
    curl -O https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-${CLOUD_SDK_VERSION}-linux-${ARCH}.tar.gz && \
    tar xzf google-cloud-cli-${CLOUD_SDK_VERSION}-linux-${ARCH}.tar.gz && \
    rm google-cloud-cli-${CLOUD_SDK_VERSION}-linux-${ARCH}.tar.gz && \
    export CLOUDSDK_CORE_DISABLE_PROMPTS=1 && \
    gcloud components install beta gke-gcloud-auth-plugin && \
    gcloud config set core/disable_usage_reporting true && \
    gcloud config set component_manager/disable_update_check true && \
    gcloud config set metrics/environment docker_image_alpine && \
    gcloud --version

# cue for yaml validation https://github.com/cue-lang/cue/releases
ARG CUE_VERSION
ENV CUE_VERSION=${CUE_VERSION:-"v0.14.1"}
RUN CMD_NAME=cue && \
    curl --silent --location "https://github.com/cue-lang/cue/releases/download/${CUE_VERSION}/${CMD_NAME}_${CUE_VERSION}_${TARGETOS}_${TARGETARCH}.tar.gz" | tar xz -C /tmp && \
    chmod +x /tmp/${CMD_NAME} && mv /tmp/${CMD_NAME} /usr/local/bin/${CMD_NAME}-${CUE_VERSION} && \
    ln -sf /usr/local/bin/${CMD_NAME}-${CUE_VERSION} /usr/local/bin/${CMD_NAME} && \
    ${CMD_NAME} version

# for pipeline compatibility
RUN ln -sf /usr/bin/yq /usr/local/bin/yq4

# The following are for recipe meta.tools compatibility
# yq 4 utility https://github.com/mikefarah/yq/releases
ARG YQ_VERSION_440
ENV YQ_VERSION_440=${YQ_VERSION_440:-"v4.47.1"}
RUN CMD_NAME=yq && \
    curl -sSLo /usr/local/bin/${CMD_NAME}-4.40 "https://github.com/mikefarah/${CMD_NAME}/releases/download/${YQ_VERSION_440}/${CMD_NAME}_${TARGETOS}_${TARGETARCH}" && \
    chmod +x /usr/local/bin/${CMD_NAME}-4.40

# vcluster for vcluster https://github.com/loft-sh/vcluster/releases
ARG VCLUSTER_VERSION=v0.27.0
RUN export CMD_NAME=vcluster && \
    curl --silent --location -o /tmp/${CMD_NAME} "https://github.com/loft-sh/vcluster/releases/download/${VCLUSTER_VERSION}/${CMD_NAME}-${TARGETOS}-${TARGETARCH}" && \
    chmod +x /tmp/${CMD_NAME} && mv /tmp/${CMD_NAME} /usr/local/bin/${CMD_NAME}-${VCLUSTER_VERSION} && \
    ln -sf /usr/local/bin/${CMD_NAME}-${VCLUSTER_VERSION} /usr/local/bin/${CMD_NAME} && \
    ${CMD_NAME} version

# helm https://github.com/helm/helm/releases
ARG HELM_VERSION_317
ENV HELM_VERSION_317=${HELM_VERSION_317:-"v3.17.1"}
RUN CMD_NAME=helm && \
    curl --silent --location "https://get.helm.sh/${CMD_NAME}-${HELM_VERSION_317}-${TARGETOS}-${TARGETARCH}.tar.gz" | tar xz -C /tmp && \
    chmod +x /tmp/${TARGETOS}-${TARGETARCH}/${CMD_NAME} && mv -f /tmp/${TARGETOS}-${TARGETARCH}/${CMD_NAME} /usr/local/bin/${CMD_NAME}-3.17 && \
    ln -sf /usr/local/bin/${CMD_NAME}-3.17 /usr/local/bin/helm

# helm https://github.com/helm/helm/releases
ARG HELM_VERSION_318
ENV HELM_VERSION_318=${HELM_VERSION_318:-"v3.18.5"}
RUN CMD_NAME=helm && \
    curl -k --silent --location "https://get.helm.sh/${CMD_NAME}-${HELM_VERSION_318}-${TARGETOS}-${TARGETARCH}.tar.gz" | tar xz -C /tmp && \
    chmod +x /tmp/${TARGETOS}-${TARGETARCH}/${CMD_NAME} && mv -f /tmp/${TARGETOS}-${TARGETARCH}/${CMD_NAME} /usr/local/bin/${CMD_NAME}-3.18 && \
    ln -sf /usr/local/bin/${CMD_NAME}-3.18 /usr/local/bin/helm

# kubectl https://kubernetes.io/releases/
ARG KUBECTL_VERSION_132
ENV KUBECTL_VERSION_132=${KUBECTL_VERSION_132:-"v1.32.5"}
RUN CMD_NAME=kubectl && \
    curl -sLO https://dl.k8s.io/release/${KUBECTL_VERSION_132}/bin/${TARGETOS}/${TARGETARCH}/${CMD_NAME} && \
    chmod +x ./${CMD_NAME} && mv -f ./${CMD_NAME} /usr/local/bin/${CMD_NAME}-1.32 && \
    ln -sf /usr/local/bin/${CMD_NAME}-1.32 /usr/local/bin/kubectl

# kubectl https://kubernetes.io/releases/
ARG KUBECTL_VERSION_133
ENV KUBECTL_VERSION_133=${KUBECTL_VERSION_133:-"v1.33.4"}
RUN CMD_NAME=kubectl && \
    curl -sLO https://dl.k8s.io/release/${KUBECTL_VERSION_133}/bin/${TARGETOS}/${TARGETARCH}/${CMD_NAME} && \
    chmod +x ./${CMD_NAME} && mv -f ./${CMD_NAME} /usr/local/bin/${CMD_NAME}-1.33

# OpenShift CLI
ARG OC_VERSION
ENV OC_VERSION=${OC_VERSION:-"4.18.17"}
RUN if [ "${TARGETARCH}" == "arm64" ]; then \
        curl --silent --location "https://mirror.openshift.com/pub/openshift-v4/clients/ocp/${OC_VERSION}/openshift-client-$(uname -s | awk '{print tolower($0)}')-${TARGETARCH}-${OC_VERSION}.tar.gz" | tar xz -C /tmp; \
    else \
        curl --silent --location "https://mirror.openshift.com/pub/openshift-v4/clients/ocp/${OC_VERSION}/openshift-client-$(uname -s | awk '{print tolower($0)}')-${OC_VERSION}.tar.gz" | tar xz -C /tmp; \
    fi && \
    chmod +x /tmp/oc && mv -f /tmp/oc /usr/local/bin/oc && \
    oc version --client=true

CMD ["/bin/bash"]
