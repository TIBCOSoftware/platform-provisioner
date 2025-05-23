FROM ghcr.io/tibcosoftware/platform-provisioner/platform-provisioner:1.3.1-tester-on-prem-jammy

ENV TP_AUTO_SCRIPT_PY_ENV_FOLDER=/tmp/auto-py-env

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC

RUN apt-get update && \
    apt-get install -y software-properties-common && \
    add-apt-repository -y ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y python3.11 python3.11-venv python3.11-dev supervisor

WORKDIR /app

COPY . .
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

SHELL ["/bin/bash", "-c"]

RUN python3.11 -m venv ${TP_AUTO_SCRIPT_PY_ENV_FOLDER} && \
    ${TP_AUTO_SCRIPT_PY_ENV_FOLDER}/bin/pip install --upgrade pip && \
    ${TP_AUTO_SCRIPT_PY_ENV_FOLDER}/bin/pip install -r requirements.txt && \
    ${TP_AUTO_SCRIPT_PY_ENV_FOLDER}/bin/pip install supervisor

ENV PATH="${TP_AUTO_SCRIPT_PY_ENV_FOLDER}/bin:$PATH"

EXPOSE 3120 8090 8091

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
