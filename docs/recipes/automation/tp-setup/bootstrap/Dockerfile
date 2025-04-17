FROM ghcr.io/tibcosoftware/platform-provisioner/platform-provisioner:1.3.1-tester-on-prem-jammy

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

CMD ["python", "-m", "waitress", "--host=0.0.0.0", "--port=3120", "server:app"]
