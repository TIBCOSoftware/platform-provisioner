FROM --platform=${BUILDPLATFORM} ghcr.io/tibcosoftware/platform-provisioner/platform-provisioner:1.6.1-tester-on-prem-jammy

ENV TP_AUTO_SCRIPT_PY_ENV_FOLDER=/tmp/auto-py-env
ENV UV_PROJECT_ENVIRONMENT=${TP_AUTO_SCRIPT_PY_ENV_FOLDER}

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=Etc/UTC \
    PIP_NO_CACHE_DIR=1

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
SHELL ["/bin/bash", "-c"]

COPY pyproject.toml poetry.lock* uv.lock* requirements*.txt* ./
RUN set -eux; \
    if [ -f "uv.lock" ] || [ -f "poetry.lock" ] || ls requirements*.txt >/dev/null 2>&1; then \
      uv venv ${UV_PROJECT_ENVIRONMENT} --python python3.13; \
      uv sync --frozen || uv sync; \
    else \
      true; \
    fi

# add pip to the venv
RUN "${UV_PROJECT_ENVIRONMENT}/bin/python" -m ensurepip --upgrade; \
    ln -sf "${UV_PROJECT_ENVIRONMENT}/bin/pip3" "${UV_PROJECT_ENVIRONMENT}/bin/pip"

COPY . .
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

ENV PATH="${TP_AUTO_SCRIPT_PY_ENV_FOLDER}/bin:$PATH"

EXPOSE 3120 8090

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
