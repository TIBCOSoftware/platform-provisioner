FROM ghcr.io/tibcosoftware/platform-provisioner/platform-provisioner:1.2.0-tester-on-prem-jammy

ENV TP_AUTO_SCRIPT_PY_ENV_FOLDER=/tmp/auto-py-env

WORKDIR /app

COPY . .

SHELL ["/bin/bash", "-c"]

RUN python3 -m venv ${TP_AUTO_SCRIPT_PY_ENV_FOLDER} && \
    source "${TP_AUTO_SCRIPT_PY_ENV_FOLDER}/bin/activate" && \
    pip install --upgrade pip && \
    pip install -r requirements.txt

EXPOSE 3120

ENV PATH="${TP_AUTO_SCRIPT_PY_ENV_FOLDER}/bin:$PATH"

CMD ["python", "-m", "waitress", "--port=3120", "server:app"]
