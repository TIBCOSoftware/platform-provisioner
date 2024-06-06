#
# Copyright (c) 2024 TIBCO Software Inc.
# All Rights Reserved. Confidential & Proprietary.
#

#---------------------------------------------------------------------------------------------
# BUILD AWSCLI V2 offical doc:
# https://docs.aws.amazon.com/cli/latest/userguide/getting-started-source-install.html#source-getting-started-install-workflows-alpine
# release notes: https://raw.githubusercontent.com/aws/aws-cli/v2/CHANGELOG.rst

FROM python:3.11.7-alpine3.19 as builder-aws
ARG AWS_CLI_VERSION
ENV AWS_CLI_VERSION=${AWS_CLI_VERSION:-"2.15.48"}

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

FROM python:3.11.7-alpine3.19 as builder-azure
ARG AZURE_CLI_VERSION
ENV AZURE_CLI_VERSION=${AZURE_CLI_VERSION:-"2.60.0"}
WORKDIR /azure
RUN apk add --no-cache --update python3 py3-pip && \
    apk add --no-cache --update --virtual=build gcc musl-dev python3-dev libffi-dev openssl-dev cargo make && \
    python -m venv .venv && .venv/bin/pip install -U pip && \
    .venv/bin/pip --no-cache-dir install azure-cli==${AZURE_CLI_VERSION} && \
    find / -name __pycache__ | xargs -r rm -rf

#---------------------------------------------------------------------------------------------
# actual run time docker image
FROM alpine:3.19

LABEL maintainer="cloud@tibco.com"
# labels see: https://github.com/opencontainers/image-spec/blob/56fb7838abe52ee259e37ece4b314c08bd45997f/annotations.md#annotations
LABEL org.opencontainers.image.title="platform-provisioner"
LABEL org.opencontainers.image.description="This provide basic tools for platform provisioner pipelines."
LABEL org.opencontainers.image.source="https://github.com/TIBCOSoftware/tp-helm-charts"
LABEL org.opencontainers.image.vendor="Cloud Software Group"

ARG TARGETOS TARGETARCH

# base packages
RUN apk add --no-cache --upgrade coreutils util-linux gettext bash curl wget envsubst jq openssl git python3 yq kubectl helm postgresql-client && rm -rf /var/cache/apk/*

# COPY AWSCLI V2 to BASE_IMAGE
COPY --from=builder-aws /opt/aws-cli/ /opt/aws-cli/
RUN ln -s /opt/aws-cli/bin/aws /usr/local/bin/aws

# COPY azure cli to BASE_IMAGE
COPY --from=builder-azure /azure /azure
RUN ln -s /usr/bin/python3 /usr/local/bin/python && ln -s /azure/.venv/bin/az /usr/local/bin/az

# eksctl https://github.com/eksctl-io/eksctl/releases
ARG EKSCTL_VERSION
ENV EKSCTL_VERSION=${EKSCTL_VERSION:-"0.176"}
RUN CMD_NAME=eksctl && \
    curl --silent --location "https://github.com/eksctl-io/eksctl/releases/download/v${EKSCTL_VERSION}.0/${CMD_NAME}_$(uname -s)_${TARGETARCH}.tar.gz" | tar xz -C /tmp && \
    chmod +x /tmp/${CMD_NAME} && mv /tmp/${CMD_NAME} /usr/local/bin/${CMD_NAME}-${EKSCTL_VERSION} && \
    ln -sf /usr/local/bin/${CMD_NAME}-${EKSCTL_VERSION} /usr/local/bin/${CMD_NAME} && \
    ${CMD_NAME} version

# calicoctl https://github.com/projectcalico/calico/releases
ARG CALICOCTL_VERSION
ENV CALICOCTL_VERSION=${CALICOCTL_VERSION:-"v3.28.0"}
RUN CMD_NAME=calicoctl && \
    curl -sLO https://github.com/projectcalico/calico/releases/download/${CALICOCTL_VERSION}/calicoctl-${TARGETOS}-${TARGETARCH} && \
    chmod +x ./${CMD_NAME}-${TARGETOS}-${TARGETARCH} && mv -f ./${CMD_NAME}-${TARGETOS}-${TARGETARCH} /usr/local/bin/${CMD_NAME}-3.23 && \
    ln -sf /usr/local/bin/${CMD_NAME}-3.23 /usr/local/bin/${CMD_NAME} && \
    { CALICO_DATASTORE_TYPE=${CALICO_DATASTORE_TYPE} ${CMD_NAME} version 2>/dev/null || echo -n ""; }

# aws ecr credentials helper
# https://github.com/awslabs/amazon-ecr-credential-helper/releases
ARG ECR_LOGIN_VERSION
ENV ECR_LOGIN_VERSION=${ECR_LOGIN_VERSION:-"0.7.1"}
RUN echo "/${ECR_LOGIN_VERSION}/${TARGETARCH}/docker-credential-ecr-login" && \
    CMD_NAME=docker-credential-ecr-login && \
    curl --silent --location "https://amazon-ecr-credential-helper-releases.s3.us-east-2.amazonaws.com/${ECR_LOGIN_VERSION}/${TARGETOS}-${TARGETARCH}/docker-credential-ecr-login" -o /tmp/${CMD_NAME} && \
    chmod +x /tmp/${CMD_NAME} && mv /tmp/${CMD_NAME} /usr/local/bin/${CMD_NAME}-${ECR_LOGIN_VERSION} && \
    ln -sf /usr/local/bin/${CMD_NAME}-${ECR_LOGIN_VERSION} /usr/local/bin/${CMD_NAME} && \
    ${CMD_NAME} -v

# cue for yaml validation https://github.com/cue-lang/cue/releases
ARG CUE_VERSION
ENV CUE_VERSION=${CUE_VERSION:-"0.8"}
RUN CMD_NAME=cue && \
    curl --silent --location "https://github.com/cue-lang/cue/releases/download/v${CUE_VERSION}.0/${CMD_NAME}_v${CUE_VERSION}.0_${TARGETOS}_${TARGETARCH}.tar.gz" | tar xz -C /tmp && \
    chmod +x /tmp/${CMD_NAME} && mv /tmp/${CMD_NAME} /usr/local/bin/${CMD_NAME}-${CUE_VERSION} && \
    ln -sf /usr/local/bin/${CMD_NAME}-${CUE_VERSION} /usr/local/bin/${CMD_NAME} && \
    ${CMD_NAME} version

# Azure CLI Bicep https://github.com/Azure/bicep/releases
ARG AZURE_CLI_BICEP_VERSION
ENV AZURE_CLI_BICEP_VERSION=${AZURE_CLI_BICEP_VERSION:-"v0.27.1"}
RUN echo "AZURE_CLI_BICEP_VERSION=${AZURE_CLI_BICEP_VERSION}" && \
    az --version && \
    az bicep install --version ${AZURE_CLI_BICEP_VERSION} && \
    az extension add --name aks-preview && \
    az extension update --name aks-preview

# for pipeline compatibility
RUN ln -sf /usr/bin/yq /usr/local/bin/yq4

# The following are for recipe meta.tools compatibility
# yq 4 utility https://github.com/mikefarah/yq/releases
ENV YQ_VERSION_440=${YQ_VERSION_440:-"v4.44.1"}
RUN CMD_NAME=yq && \
    curl -sSLo /usr/local/bin/${CMD_NAME}-4.40 "https://github.com/mikefarah/${CMD_NAME}/releases/download/${YQ_VERSION_440}/${CMD_NAME}_${TARGETOS}_${TARGETARCH}" && \
    chmod +x /usr/local/bin/${CMD_NAME}-4.40

# helm https://github.com/helm/helm/releases
ENV HELM_VERSION_313=${HELM_VERSION_313:-"v3.13.3"}
RUN CMD_NAME=helm && \
    curl --silent --location "https://get.helm.sh/${CMD_NAME}-${HELM_VERSION_313}-${TARGETOS}-${TARGETARCH}.tar.gz" | tar xz -C /tmp && \
    chmod +x /tmp/${TARGETOS}-${TARGETARCH}/${CMD_NAME} && mv -f /tmp/${TARGETOS}-${TARGETARCH}/${CMD_NAME} /usr/local/bin/${CMD_NAME}-3.13

ENV HELM_VERSION_314=${HELM_VERSION_314:-"v3.14.4"}
RUN CMD_NAME=helm && \
    curl --silent --location "https://get.helm.sh/${CMD_NAME}-${HELM_VERSION_314}-${TARGETOS}-${TARGETARCH}.tar.gz" | tar xz -C /tmp && \
    chmod +x /tmp/${TARGETOS}-${TARGETARCH}/${CMD_NAME} && mv -f /tmp/${TARGETOS}-${TARGETARCH}/${CMD_NAME} /usr/local/bin/${CMD_NAME}-3.14

# kubectl https://kubernetes.io/releases/
ENV KUBECTL_VERSION_128=${KUBECTL_VERSION_128:-"v1.28.7"}
RUN CMD_NAME=kubectl && \
    curl -sLO https://storage.googleapis.com/kubernetes-release/release/${KUBECTL_VERSION_128}/bin/${TARGETOS}/${TARGETARCH}/${CMD_NAME} && \
    chmod +x ./${CMD_NAME} && mv -f ./${CMD_NAME} /usr/local/bin/${CMD_NAME}-1.28

ENV KUBECTL_VERSION_129=${KUBECTL_VERSION_129:-"v1.29.4"}
RUN CMD_NAME=kubectl && \
    curl -sLO https://storage.googleapis.com/kubernetes-release/release/${KUBECTL_VERSION_129}/bin/${TARGETOS}/${TARGETARCH}/${CMD_NAME} && \
    chmod +x ./${CMD_NAME} && mv -f ./${CMD_NAME} /usr/local/bin/${CMD_NAME}-1.29

ENV KUBECTL_VERSION_130=${KUBECTL_VERSION_130:-"v1.30.0"}
RUN CMD_NAME=kubectl && \
    curl -sLO https://storage.googleapis.com/kubernetes-release/release/${KUBECTL_VERSION_130}/bin/${TARGETOS}/${TARGETARCH}/${CMD_NAME} && \
    chmod +x ./${CMD_NAME} && mv -f ./${CMD_NAME} /usr/local/bin/${CMD_NAME}-1.30

CMD ["/bin/bash"]
