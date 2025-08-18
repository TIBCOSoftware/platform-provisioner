FROM ghcr.io/tibcosoftware/platform-provisioner/platform-provisioner:1.6.0-tester-on-prem-jammy

ENV TP_AUTO_SCRIPT_PY_ENV_FOLDER=/tmp/auto-py-env

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC

RUN apt-get update && \
    apt-get install -y --no-install-recommends software-properties-common gnupg ca-certificates tzdata && \
    ln -fs /usr/share/zoneinfo/$TZ /etc/localtime && \
    dpkg-reconfigure --frontend noninteractive tzdata && \
    add-apt-repository -y ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y --no-install-recommends python3.13 python3.13-venv python3.13-dev supervisor && \
    python3.13 -m ensurepip --upgrade && \
    python3.13 -m pip install --upgrade pip && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . .
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

SHELL ["/bin/bash", "-c"]

RUN python3.13 -m venv ${TP_AUTO_SCRIPT_PY_ENV_FOLDER} && \
    ${TP_AUTO_SCRIPT_PY_ENV_FOLDER}/bin/pip install --upgrade pip && \
    ${TP_AUTO_SCRIPT_PY_ENV_FOLDER}/bin/pip install -r requirements.txt && \
    ${TP_AUTO_SCRIPT_PY_ENV_FOLDER}/bin/pip install supervisor

ENV PATH="${TP_AUTO_SCRIPT_PY_ENV_FOLDER}/bin:$PATH"

EXPOSE 3120 8090

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
