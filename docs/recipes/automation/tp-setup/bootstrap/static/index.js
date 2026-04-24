/*
 * Copyright 2025 Cloud Software Group, Inc.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

let ENV;
window.onload = function () {
  $(".is_loading").show();
  loadData().then(res => {
    ENV = res;
    $(".is_loading").hide();
    hideFields();
    // Load deploy config after ENV is loaded
    loadDefaultDeployConfig();
  });
  handleFieldsAction();

  initTab();
  loadCliSetting();
  initAdvancedModeToggle();
};

async function loadData() {
  try {
    let response = await fetch('/get_env');
    let data = await response.json();
    initInputValue(data);

    // Update EAR file default hint with actual defaults from ENV
    const defaultBwceFile = data.BWCE_APP_FILE_NAME || 'rest-bwce-1.ear';
    const defaultFlogoFile = data.FLOGO_APP_FILE_NAME || 'rest-flogo-1.json';
    const defaultBw5ceFile = data.BW5CE_APP_FILE_NAME || 'bw5ce-dynamicheaders.ear';
    const hintElement = document.getElementById('TIBCOP_CLI_EAR_FILE_DEFAULT_HINT');
    if (hintElement) {
      hintElement.textContent = `Upload a file or leave empty to use default (BWCE: upload/${defaultBwceFile}, Flogo: upload/${defaultFlogoFile}, BW5CE: upload/${defaultBw5ceFile})`;
    }

    return data;
  } catch (error) {
    console.error("Error loading config:", error);
  }
}

async function loadCPAPI(url, data= "", method = 'GET') {
  try {
    const options = {
      method: method,
      headers: {
        'Content-Type': 'application/json'
      }
    }
    if (data && (method === 'POST' || method === 'PUT' || method === 'PATCH')) {
      options.body = JSON.stringify(data);
    }
    const response = await fetch('/cp_api?api_path=' + encodeURIComponent(url), options);
    return await response.json();
  } catch (error) {
    console.error("Error loading config:", error);
  }
}

async function handleFileUpload() {
  const fileInput = document.getElementById("app_file");
  if (!fileInput.value) return;

  const formData = new FormData();
  const file = fileInput.files[0];
  formData.append('file', file);

  return new Promise((resolve, reject) => {
    $.ajax({
      url: '/upload',
      type: 'POST',
      data: formData,
      contentType: false,
      processData: false,
      success: function (response) {
        resolve(response);
      },
      error: function (err) {
        reject(err);
      }
    });
  });
}

async function runGuiScript(currentElement) {
  const formElement = $(currentElement).closest('form');

  const additionalParams = {
    TP_AUTO_IS_CONFIG_O11Y: true,
    case: document.getElementById("guiAutoCase").value,
    HEADLESS: !document.getElementById("HEADLESS").checked,
    FORCE_RUN_AUTOMATION: document.getElementById("FORCE_RUN_AUTOMATION").checked,
    IS_CLEAN_REPORT: document.getElementById("IS_CLEAN_REPORT").checked,

    TP_AUTO_LOGIN_URL: document.getElementById("TP_AUTO_LOGIN_URL").value,
    DP_HOST_PREFIX: document.getElementById("DP_HOST_PREFIX").value,
    DP_USER_EMAIL: document.getElementById("DP_USER_EMAIL").value,
    DP_USER_PASSWORD: document.getElementById("DP_USER_PASSWORD").value,
    TP_AUTO_MAIL_URL: document.getElementById("TP_AUTO_MAIL_URL").value,
    TP_AUTO_K8S_DP_NAME: document.getElementById("TP_AUTO_K8S_DP_NAME").value,
    TP_AUTO_K8S_BMDP_NAME: document.getElementById("TP_AUTO_K8S_BMDP_NAME").value,
    TP_AUTO_KUBECONFIG: document.getElementById("TP_AUTO_KUBECONFIG").value,
    TP_AUTO_DATA_PLANE_O11Y_SYSTEM_CONFIG: document.getElementById("TP_AUTO_DATA_PLANE_O11Y_SYSTEM_CONFIG").checked,
    TP_AUTO_K8S_DP_SERVICE_ACCOUNT_CREATION_ADDITIONAL_SETTINGS: document.getElementById("TP_AUTO_K8S_DP_SERVICE_ACCOUNT_CREATION_ADDITIONAL_SETTINGS").value,
    BWCE_APP_NAME: document.getElementById("BWCE_APP_NAME").value,
    BW5CE_APP_NAME: document.getElementById("BW5CE_APP_NAME").value,
    FLOGO_APP_NAME: document.getElementById("FLOGO_APP_NAME").value,
    GITHUB_TOKEN: document.getElementById("GITHUB_TOKEN").value,
    TP_ACTIVATION_SERVER_IP: document.getElementById("TP_ACTIVATION_SERVER_IP").value,
    TP_ACTIVATION_SERVER_PORT: document.getElementById("TP_ACTIVATION_SERVER_PORT").value,
    TP_ACTIVATION_SERVER_CERT_HOSTNAME: document.getElementById("TP_ACTIVATION_SERVER_CERT_HOSTNAME").value,
    TP_ACTIVATION_SERVER_FINGER_PRINT: document.getElementById("TP_ACTIVATION_SERVER_FINGER_PRINT").value,
    TP_BMDP_IMAGE_TAG_EMS: document.getElementById("TP_BMDP_IMAGE_TAG_EMS").value,
    TP_BMDP_IMAGE_TAG_BW5EMSDM: document.getElementById("TP_BMDP_IMAGE_TAG_BW5EMSDM").value,
    TP_BMDP_IMAGE_TAG_BW5RVDM: document.getElementById("TP_BMDP_IMAGE_TAG_BW5RVDM").value,
    TP_BMDP_IMAGE_TAG_BW6DM: document.getElementById("TP_BMDP_IMAGE_TAG_BW6DM").value,
  };
  const file_response = await handleFileUpload();
  if (file_response) {
    const filename = file_response.filename;
    const filetype = file_response.filetype;
    if (filetype === "FLOGO") {
      additionalParams.TP_AUTO_FLOGO_APP_FILE_NAME = filename;
    } else if (filetype === "BWCE") {
      // In file server.py, API /upload, all .ear file is treated as BWCE file type
      additionalParams.TP_AUTO_BWCE_APP_FILE_NAME = filename;
      additionalParams.TP_AUTO_BW5CE_APP_FILE_NAME = filename;
    }
  }
  const params = new URLSearchParams({ ...handleGuiSpecialCase(additionalParams) });
  runScript(`/run-gui-script?${params.toString()}`, formElement);
}

function getSelectedCapabilities() {
  const capabilities = [];
  if (document.getElementById("capability_bwce")?.checked) capabilities.push("BWCE");
  if (document.getElementById("capability_bw5ce")?.checked) capabilities.push("BW5CE");
  if (document.getElementById("capability_flogo")?.checked) capabilities.push("FLOGO");
  if (document.getElementById("capability_devhub")?.checked) capabilities.push("DEVHUB");
  return capabilities.join(",");
}

async function runCliScript(currentElement) {
  const formElement = $(currentElement).closest('form');

  // Handle EAR file upload if file is selected
  const earFileInput = document.getElementById("TIBCOP_CLI_EAR_FILE_UPLOAD");
  let earFilePath = document.getElementById("TIBCOP_CLI_EAR_FILE_PATH").value.trim();

  if (earFileInput && earFileInput.files && earFileInput.files.length > 0) {
    const file = earFileInput.files[0];
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch('/upload', {
        method: 'POST',
        body: formData
      });

      const result = await response.json();
      if (result.filename) {
        earFilePath = `upload/${result.filename}`;
        document.getElementById("TIBCOP_CLI_EAR_FILE_PATH").value = earFilePath;
        console.log(`File uploaded: ${earFilePath}`);
      } else {
        alert('File upload failed: ' + (result.message || 'Unknown error'));
        return;
      }
    } catch (error) {
      alert('File upload error: ' + error.message);
      return;
    }
  }

  // If no file uploaded and path is empty, use default from ENV
  if (!earFilePath) {
    // Determine which default file to use based on selected case
    const selectedCase = document.getElementById("cliAutoCase").value;
    const isFlogoCase = selectedCase.includes('flogo');
    const isBw5ceCase = selectedCase.includes('bw5ce');

    const defaultFile = isFlogoCase
      ? (ENV?.FLOGO_APP_FILE_NAME || 'rest-flogo-1.json')
      : isBw5ceCase
        ? (ENV?.BW5CE_APP_FILE_NAME || 'bw5ce-dynamicHeaders.ear')
        : (ENV?.BWCE_APP_FILE_NAME || 'rest-bwce-1.ear');
    earFilePath = `upload/${defaultFile}`;
  }

  // Handle deploy config - save textarea content to bwce-payload.json or flogo-payload.json
  const deployConfigTextarea = document.getElementById("TIBCOP_CLI_DEPLOY_CONFIG_FILE");
  const selectedCase = document.getElementById("cliAutoCase").value;

  // Determine which payload file to save based on selected case
  const isBwceOperation = selectedCase === 'bwce:deploy-app' || selectedCase === 'bwce-build-and-deploy';
  const isFlogoOperation = selectedCase === 'flogo:deploy-app' || selectedCase === 'flogo-build-and-deploy';
  const isBw5ceOperation = selectedCase === 'bw5ce:deploy-app' || selectedCase === 'bw5ce-build-and-deploy';

  // Only save when running deploy operations
  if (deployConfigTextarea && deployConfigTextarea.value.trim() && (isBwceOperation || isFlogoOperation || isBw5ceOperation)) {
    try {
      // Validate JSON
      JSON.parse(deployConfigTextarea.value);

      // Show saving message
      const outputElement = formElement.find('.output')[0];
      const payloadType = isBwceOperation ? 'bwce' : (isFlogoOperation ? 'flogo' : 'bw5ce');
      const payloadFile = `upload/${payloadType}-payload.json`;
      outputElement.innerHTML = `[INFO] Saving deploy config to ${payloadFile}...\n`;

      // Save to appropriate payload file
      const endpoint = isBwceOperation ? '/save-bwce-payload' : (isFlogoOperation ? '/save-flogo-payload' : '/save-bw5ce-payload');
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ config: deployConfigTextarea.value })
      });

      const result = await response.json();
      if (!result.success) {
        alert('Failed to save deploy config: ' + (result.message || 'Unknown error'));
        return;
      }
      console.log(`Deploy config saved to ${payloadFile}`);
      outputElement.innerHTML += "[SUCCESS] Deploy config saved successfully\n\n";
    } catch (error) {
      alert('Invalid JSON in Deploy Config File: ' + error.message);
      return;
    }
  }

  const additionalParams = {
    TP_AUTO_IS_CONFIG_O11Y: true,
    case: document.getElementById("cliAutoCase").value,

    TIBCOP_CLI_CPURL: document.getElementById("TIBCOP_CLI_CPURL").value,
    TIBCOP_CLI_OAUTH_TOKEN: document.getElementById("TIBCOP_CLI_OAUTH_TOKEN").value,
    TIBCOP_CLI_DP_NAME: document.getElementById("TIBCOP_CLI_DP_NAME").value,
    TIBCOP_CLI_CAPABILITY_ID: document.getElementById("TIBCOP_CLI_CAPABILITY_ID").value,
    TIBCOP_CLI_APP_ID: document.getElementById("TIBCOP_CLI_APP_ID").value,
    TIBCOP_CLI_STORAGE_RESOURCE_ID: document.getElementById("TIBCOP_CLI_STORAGE_RESOURCE_ID").value,
    TIBCOP_CLI_INGRESS_RESOURCE_ID: document.getElementById("TIBCOP_CLI_INGRESS_RESOURCE_ID").value,
    TIBCOP_CLI_DEVHUB_NAME: document.getElementById("TIBCOP_CLI_DEVHUB_NAME").value,
    TIBCOP_CLI_K8S_SECRET: document.getElementById("TIBCOP_CLI_K8S_SECRET").value,
    TIBCOP_CLI_RESOURCE_NAME: document.getElementById("TIBCOP_CLI_RESOURCE_NAME").value,
    TIBCOP_CLI_ACTIVATION_SERVER_URL: document.getElementById("TIBCOP_CLI_ACTIVATION_SERVER_URL").value,
    TIBCOP_CLI_STORAGE_CLASS_NAME: document.getElementById("TIBCOP_CLI_STORAGE_CLASS_NAME").value,
    TIBCOP_CLI_INGRESS_CLASS_NAME: document.getElementById("TIBCOP_CLI_INGRESS_CLASS_NAME").value,
    TIBCOP_CLI_INGRESS_CONTROLLER: document.getElementById("TIBCOP_CLI_INGRESS_CONTROLLER").value,
    TIBCOP_CLI_FQDN: document.getElementById("TIBCOP_CLI_FQDN").value,
    TIBCOP_CLI_RESOURCE_INSTANCE_ID: document.getElementById("TIBCOP_CLI_RESOURCE_INSTANCE_ID").value,
    TIBCOP_CLI_EAR_FILE_PATH: earFilePath || '',
    TIBCOP_CLI_DEPLOY_CONFIG_FILE: isFlogoOperation ? 'upload/flogo-payload.json' : (isBw5ceOperation ? 'upload/bw5ce-payload.json' : 'upload/bwce-payload.json'),  // Use appropriate payload file
    TIBCOP_CLI_BWCE_VERSION: document.getElementById("TIBCOP_CLI_BWCE_VERSION").value,
    TIBCOP_CLI_FLOGO_VERSION: document.getElementById("TIBCOP_CLI_FLOGO_VERSION").value,
    TIBCOP_CLI_BASE_IMAGE_TAG: document.getElementById("TIBCOP_CLI_BASE_IMAGE_TAG").value,
    TIBCOP_CLI_OTHER_ARGS: document.getElementById("TIBCOP_CLI_OTHER_ARGS").value,
    TIBCOP_CLI_CAPABILITIES: getSelectedCapabilities(),
  };

  const params = new URLSearchParams({ ...handleCliSpecialCase(additionalParams) });
  runScript(`/run-cli-script?${params.toString()}`, formElement);
}

function runScript(apiUrl, formElement) {
  const outputElement = formElement.find('.output')[0];
  const preElement = formElement.find('.logs')[0];

  outputElement.innerHTML = "Running script...\n";
  const runButton = formElement.find('.runBtn')[0];
  const stopButton = formElement.find('.stopBtn')[0];

  runButton.disabled = true;
  stopButton.disabled = false;
  toggleProgress(formElement, true);  // Show progress indicator

  fetch(apiUrl)
    .then(response => {
      window.currentJobId = response.headers.get("one_click_job_id");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      function readStream() {
        reader.read().then(({ done, value }) => {
          if (done) {
            Prism.highlightElement(outputElement);
            runButton.disabled = false;
            stopButton.disabled = true;
            toggleProgress(formElement, false);  // Hide progress indicator
            return
          }
          outputElement.innerHTML += decoder.decode(value, { stream: true });

          setTimeout(() => {
            Prism.highlightElement(outputElement);
            preElement.scrollTop = preElement.scrollHeight;
          }, 50);
          readStream();  // Continue reading
        });
      }
      readStream();
    })
    .catch(error => {
      console.error('Error:', error);
      toggleProgress(formElement, false);  // Hide progress indicator on error
    });
}

function stopScript(currentElement) {
  const formElement = $(currentElement).closest('form');

  const outputElement = formElement.find('.output')[0];
  const preElement = formElement.find('.logs')[0];
  const runButton = formElement.find('.runBtn')[0];
  const stopButton = formElement.find('.stopBtn')[0];

  fetch('/stop-script' + (window.currentJobId ? `?jobId=${window.currentJobId}` : ""))
    .then(response => response.json())
    .then(data => {
      outputElement.innerHTML += `\n[INFO] ${data.message}\n`;
      preElement.scrollTop = preElement.scrollHeight;

      runButton.disabled = false;
      stopButton.disabled = true;
      toggleProgress(formElement, false);  // Hide progress indicator
    })
    .catch(error => {
      console.error('Error stopping script:', error);
      outputElement.innerHTML += `\n[ERROR] Failed to stop script: ${error.message}\n`;
      preElement.scrollTop = preElement.scrollHeight;

      runButton.disabled = false;
      stopButton.disabled = true;
      toggleProgress(formElement, false);  // Hide progress indicator
    });
}

function handleGuiSpecialCase(params) {
  const provisionCaseMapping = {
    "provision_bwce": "TP_AUTO_IS_PROVISION_BWCE",
    "provision_bw5ce": "TP_AUTO_IS_PROVISION_BW5CE",
    "provision_ems": "TP_AUTO_IS_PROVISION_EMS",
    "provision_flogo": "TP_AUTO_IS_PROVISION_FLOGO",
    "provision_pulsar": "TP_AUTO_IS_PROVISION_PULSAR",
    "provision_tibcohub": "TP_AUTO_IS_PROVISION_TIBCOHUB"
  };

  if (provisionCaseMapping[params.case]) {
    params[provisionCaseMapping[params.case]] = true;
    params.case = "case.k8s_provision_capability";
  }

  const createCaseMapping = {
    "case.k8s_create_and_start_bwce_app": "bwce",
    "case.k8s_create_and_start_bw5ce_app": "bw5ce",
  };
  // above two cases use same case file
  if (createCaseMapping[params.case]) {
    params.CAPABILITY = createCaseMapping[params.case];
    params.case = "case.k8s_create_and_start_bwce_app";
  }

  const deleteCaseMapping = {
    "delete_bwce_app": "bwce",
    "delete_bw5ce_app": "bw5ce",
    "delete_flogo_app": "flogo",
  };

  if (deleteCaseMapping[params.case]) {
    params.CAPABILITY = deleteCaseMapping[params.case];
    params.case = "case.k8s_delete_app";
  }

  // MCP Hub: set the flag so the case script knows it's explicitly requested
  if (params.case === "case.k8s_deploy_mcp_hub") {
    params.TP_AI_ENABLE_MCP_HUB = "true";
  }

  return params;
}

function handleCliSpecialCase(params) {
  const prefix = "tplatform:provision-capability"
  if (params.case.startsWith(prefix)) {
    params.CAPABILITY = params.case.split(prefix + ":")[1];
    params.case = prefix;
  }
  return params;
}

function handleFieldsAction() {
  $("#guiAutoCase").on("change", function (e) {
    const selectedValue = e.target.value;
    let fieldsSelector = [];
    // hide all optional fields, then show required fields for a selected case
    hideFields();
    toggleField(['.TP_AUTO_LOGIN_URL', '.TP_AUTO_K8S_DP_NAME'], true);
    switch (selectedValue) {
      case "page_env":
        fieldsSelector = [
          ".TP_AUTO_ADMIN_URL",
          ".CP_ADMIN_EMAIL",
          ".CP_ADMIN_PASSWORD",
          ".TP_AUTO_MAIL_URL",
        ];
        toggleField(fieldsSelector, true);
        toggleField(['.TP_AUTO_K8S_DP_NAME'], false);
        break;
      case "page_setting":
        fieldsSelector = [
          ".TP_AUTO_TOKEN_NAME",
        ];
        toggleField(fieldsSelector, true);
        toggleField(['.TP_AUTO_K8S_DP_NAME'], false);
        break;
      case "page_auth":
        fieldsSelector = [
          ".TP_AUTO_ADMIN_URL",
          ".CP_ADMIN_EMAIL",
          ".CP_ADMIN_PASSWORD",
          ".DP_HOST_PREFIX",
          ".TP_AUTO_MAIL_URL",
        ];
        toggleField(fieldsSelector, true);
        toggleField(['.TP_AUTO_LOGIN_URL', '.TP_AUTO_K8S_DP_NAME'], false);
        break;
      case "page_o11y":
        fieldsSelector = [
          ".TP_AUTO_K8S_BMDP_NAME",
        ];
        toggleField(fieldsSelector, true);
        break;
      case "case.create_global_config":
        toggleField([".TP_AUTO_DATA_PLANE_O11Y_SYSTEM_CONFIG"], true);
        toggleField(['.TP_AUTO_K8S_DP_NAME'], false);
        break;
      case "case.k8s_config_dp_o11y":
        toggleField([".TP_AUTO_DATA_PLANE_O11Y_SYSTEM_CONFIG"], true);
        break;
      case "case.k8s_create_dp":
        toggleField([".TP_AUTO_K8S_DP_SERVICE_ACCOUNT_CREATION_ADDITIONAL_SETTINGS"], true);
        break;
      case "case.k8s_create_and_start_bwce_app":
        toggleField([".BWCE_APP_NAME"], true);
        toggleField([".app_file"], true);
        cleanAppFileInput();
        break;
      case "case.k8s_create_and_start_bw5ce_app":
        toggleField([".BW5CE_APP_NAME"], true);
        toggleField([".app_file"], true);
        cleanAppFileInput();
        break;
      case "case.k8s_create_and_start_flogo_app":
        toggleField([".FLOGO_APP_NAME"], true);
        toggleField([".app_file"], true);
        cleanAppFileInput();
        break;
      case "delete_bwce_app":
        toggleField([".BWCE_APP_NAME"], true);
        break;
      case "delete_bw5ce_app":
        toggleField([".BW5CE_APP_NAME"], true);
        break;
      case "delete_flogo_app":
        toggleField([".FLOGO_APP_NAME"], true);
        break;
      case "case.bmdp_create_dp":
        toggleField([".TP_AUTO_K8S_BMDP_NAME", ".TP_AUTO_K8S_DP_SERVICE_ACCOUNT_CREATION_ADDITIONAL_SETTINGS"], true);
        toggleField([".TP_AUTO_K8S_DP_NAME"], false);
        break;
      case "case.bmdp_delete_dp":
        toggleField([".TP_AUTO_K8S_BMDP_NAME"], true);
        toggleField([".TP_AUTO_K8S_DP_NAME"], false);
        break;
      case "case.bmdp_config_dp_o11y":
        toggleField([".TP_AUTO_K8S_BMDP_NAME", ".TP_AUTO_DATA_PLANE_O11Y_SYSTEM_CONFIG"], true);
        toggleField([".TP_AUTO_K8S_DP_NAME"], false);
        break;
      case "case.bmdp_create_bw5dm":
        toggleField([".TP_AUTO_K8S_DP_NAME"], false);
        toggleField([
          ".TP_AUTO_K8S_BMDP_NAME",
          ".GITHUB_TOKEN",
          ".TP_ACTIVATION_SERVER_IP",
          ".TP_ACTIVATION_SERVER_PORT",
          ".TP_ACTIVATION_SERVER_CERT_HOSTNAME",
          ".TP_ACTIVATION_SERVER_FINGER_PRINT",
          ".TP_BMDP_IMAGE_TAG_EMS",
          ".TP_BMDP_IMAGE_TAG_BW5EMSDM",
          ".TP_BMDP_IMAGE_TAG_BW5RVDM",
          ".TP_BMDP_IMAGE_TAG_BW6DM"
        ], true);
        preLoadBMDPCreateBW5DMData();
        break;
      case "case.bmdp_provision_capability":
        toggleField([".TP_AUTO_K8S_BMDP_NAME"], true);
        toggleField(['.TP_AUTO_K8S_DP_NAME'], false);
        break;
      case "case.bmdp_delete_bw5dm":
        toggleField([".TP_AUTO_K8S_BMDP_NAME", '.TP_AUTO_K8S_DP_NAME'], false);
        break;
    }
  });

  // Handle CLI automation case selection
  $("#cliAutoCase").on("change", function (e) {
    const selectedValue = e.target.value;
    // Hide all optional fields by default
    toggleField([
      '.TIBCOP_CLI_CAPABILITY_ID',
      '.TIBCOP_CLI_APP_ID',
      '.TIBCOP_CLI_STORAGE_RESOURCE_ID',
      '.TIBCOP_CLI_INGRESS_RESOURCE_ID',
      '.TIBCOP_CLI_DEVHUB_NAME',
      '.TIBCOP_CLI_K8S_SECRET',
      '.TIBCOP_CLI_RESOURCE_NAME',
      '.TIBCOP_CLI_ACTIVATION_SERVER_URL',
      '.TIBCOP_CLI_STORAGE_CLASS_NAME',
      '.TIBCOP_CLI_INGRESS_CLASS_NAME',
      '.TIBCOP_CLI_INGRESS_CONTROLLER',
      '.TIBCOP_CLI_FQDN',
      '.TIBCOP_CLI_RESOURCE_INSTANCE_ID',
      '.TIBCOP_CLI_EAR_FILE_PATH',
      '.TIBCOP_CLI_DEPLOY_CONFIG_FILE',
      '.TIBCOP_CLI_BWCE_VERSION',
      '.TIBCOP_CLI_FLOGO_VERSION',
      '.TIBCOP_CLI_BASE_IMAGE_TAG',
      '.TIBCOP_CLI_CAPABILITIES',
      '.build-and-deploy-note'
    ], false);

    // Show fields for tplatform:list-apps operation
    if (selectedValue === "tplatform:list-apps") {

    }

    // Show CAPABILITY_ID and APP_ID fields for delete operation
    if (selectedValue === "delete-app") {
      toggleField(['.TIBCOP_CLI_CAPABILITY_ID', '.TIBCOP_CLI_APP_ID'], true);
    }

    // Show fields for tplatform:list-capabilities operation
    if (selectedValue === "tplatform:list-capabilities") {

    }

    // Show fields for provision-capability operation
    if (selectedValue === "provision-capability") {
      toggleField(['.TIBCOP_CLI_CAPABILITY_ID'], true);
      // Fields will be shown/hidden based on capability selection (handled by capability change event)
    }

    // Show fields for delete-capability-instance operation
    if (selectedValue === "delete-capability-instance") {
      toggleField(['.TIBCOP_CLI_CAPABILITY_ID'], true);
    }

    // Show fields for tplatform:list-resource-instances operation
    if (selectedValue === "tplatform:list-resource-instances") {

    }

    // Show fields for create-storage-resource operation
    if (selectedValue === "create-storage-resource") {
      toggleField(['.TIBCOP_CLI_RESOURCE_NAME', '.TIBCOP_CLI_STORAGE_CLASS_NAME'], true);
    }

    // Show fields for create-ingress-resource operation
    if (selectedValue === "create-ingress-resource") {
      toggleField([
        '.TIBCOP_CLI_RESOURCE_NAME',
        '.TIBCOP_CLI_FQDN',
        '.TIBCOP_CLI_INGRESS_CLASS_NAME',
        '.TIBCOP_CLI_INGRESS_CONTROLLER'
      ], true);
    }

    // Show fields for create-activation-server operation
    if (selectedValue === "create-activation-server") {
      toggleField(['.TIBCOP_CLI_RESOURCE_NAME', '.TIBCOP_CLI_ACTIVATION_SERVER_URL'], true);
    }

    // Show fields for delete-resource-instance operation
    if (selectedValue === "delete-resource-instance") {
      toggleField(['.TIBCOP_CLI_RESOURCE_INSTANCE_ID'], true);
    }

    // Show fields for register-control-tower-dataplane operation (only in advanced mode)
    if (selectedValue === "tplatform:register-control-tower-dataplane") {
      const isAdvancedMode = document.getElementById('advancedModeToggle')?.checked || false;
      if (isAdvancedMode) {
        toggleField([
          '.TIBCOP_CLI_STORAGE_CLASS_NAME',
          '.TIBCOP_CLI_INGRESS_CLASS_NAME',
          '.TIBCOP_CLI_FQDN'
        ], true);
      }
    }

    // Show fields for bwce:list-versions operation
    if (selectedValue === "bwce:list-versions") {

    }

    // Show fields for bwce:provision-version operation
    if (selectedValue === "bwce:provision-version") {
      toggleField(['.TIBCOP_CLI_BWCE_VERSION'], true);
    }

    // Show fields for bwce:create-build operation
    // Note: BWCE version and base image tag are auto-fetched, so not shown
    if (selectedValue === "bwce:create-build") {
      toggleField([
        '.TIBCOP_CLI_EAR_FILE_PATH'
      ], true);
      updateFileUploadLabel('BWCE EAR File (.ear)');
    }

    // Show fields for bwce:deploy-app operation
    if (selectedValue === "bwce:deploy-app") {
      toggleField([
        '.TIBCOP_CLI_DEPLOY_CONFIG_FILE'
      ], true);
      loadPayloadConfig('bwce');
    }

    // Show fields for bwce-build-and-deploy operation (all fields)
    if (selectedValue === "bwce-build-and-deploy") {
      toggleField([
        '.TIBCOP_CLI_EAR_FILE_PATH',
        '.TIBCOP_CLI_DEPLOY_CONFIG_FILE',
          '.build-and-deploy-note'
      ], true);
      loadPayloadConfig('bwce');
      updateFileUploadLabel('BWCE EAR File (.ear)');
    }

    // Show fields for flogo:list-versions operation
    if (selectedValue === "flogo:list-versions") {

    }

    // Show fields for flogo:provision-version operation
    if (selectedValue === "flogo:provision-version") {
      toggleField(['.TIBCOP_CLI_FLOGO_VERSION'], true);
    }

    // Show fields for flogo:create-build operation
    if (selectedValue === "flogo:create-build") {
      toggleField([
        '.TIBCOP_CLI_EAR_FILE_PATH'
      ], true);
      updateFileUploadLabel('Flogo App File (.json, .flogo)');
    }

    // Show fields for flogo:deploy-app operation
    if (selectedValue === "flogo:deploy-app") {
      toggleField([
        '.TIBCOP_CLI_DEPLOY_CONFIG_FILE'
      ], true);
      loadPayloadConfig('flogo');
    }

    // Show fields for flogo-build-and-deploy operation (all fields)
    if (selectedValue === "flogo-build-and-deploy") {
      toggleField([
        '.TIBCOP_CLI_EAR_FILE_PATH',
        '.TIBCOP_CLI_DEPLOY_CONFIG_FILE',
          '.build-and-deploy-note'
      ], true);
      loadPayloadConfig('flogo');
      updateFileUploadLabel('Flogo App File (.json, .flogo)');
    }

    // ========== BW5CE Operations ==========
    // Show fields for bw5ce:list-versions operation
    if (selectedValue === "bw5ce:list-versions") {

    }

    // Show fields for bw5ce:provision-version operation
    if (selectedValue === "bw5ce:provision-version") {
      toggleField(['.TIBCOP_CLI_BWCE_VERSION'], true);
    }

    // Show fields for bw5ce:create-build operation
    if (selectedValue === "bw5ce:create-build") {
      toggleField([
        '.TIBCOP_CLI_EAR_FILE_PATH'
      ], true);
      updateFileUploadLabel('BW5CE EAR File');
    }

    // Show fields for bw5ce:deploy-app operation
    if (selectedValue === "bw5ce:deploy-app") {
      toggleField([
        '.TIBCOP_CLI_DEPLOY_CONFIG_FILE'
      ], true);
      loadPayloadConfig('bw5ce');
    }

    // Show fields for bw5ce-build-and-deploy operation (all fields)
    if (selectedValue === "bw5ce-build-and-deploy") {
      toggleField([
        '.TIBCOP_CLI_EAR_FILE_PATH',
        '.TIBCOP_CLI_DEPLOY_CONFIG_FILE',
          '.build-and-deploy-note'
      ], true);
      loadPayloadConfig('bw5ce');
      updateFileUploadLabel('BW5CE EAR File');
    }
  });

  // Handle capability selection for provision-capability
  $("#TIBCOP_CLI_CAPABILITY_ID").on("change", function (e) {
    const capability = e.target.value;
    const selectedCase = document.getElementById("cliAutoCase").value;

    // Only handle field visibility if we're in provision-capability mode
    if (selectedCase !== "provision-capability") {
      return;
    }

    // Hide all provision fields first
    toggleField([
      '.TIBCOP_CLI_STORAGE_RESOURCE_ID',
      '.TIBCOP_CLI_INGRESS_RESOURCE_ID',
      '.TIBCOP_CLI_DEVHUB_NAME',
      '.TIBCOP_CLI_K8S_SECRET'
    ], false);

    if (capability === "TIBCOHUB") {
      // Show TIBCOHUB-specific fields
      toggleField([
        '.TIBCOP_CLI_STORAGE_RESOURCE_ID',
        '.TIBCOP_CLI_INGRESS_RESOURCE_ID',
        '.TIBCOP_CLI_DEVHUB_NAME',
        '.TIBCOP_CLI_K8S_SECRET'
      ], true);
    } else if (capability === "BWCE" || capability === "BW5CE" || capability === "FLOGO") {
      // Show BWCE/BW5CE/FLOGO-specific fields
      // Note: Path prefix is now auto-calculated as /tibco/{capability}/{dataplane_id}
      toggleField([
        '.TIBCOP_CLI_STORAGE_RESOURCE_ID',
        '.TIBCOP_CLI_INGRESS_RESOURCE_ID'
      ], true);
    }
  });

  $('#DP_HOST_PREFIX').on('input', function () {
    const value = $(this).val();
    if (value) {
      $('#TP_AUTO_LOGIN_URL').val(replaceSubdomain(ENV.TP_AUTO_LOGIN_URL, value));
      $('#DP_USER_EMAIL').val(replaceEmailPrefix(ENV.DP_USER_EMAIL, value));
    }
  });

  $('#TIBCOP_CLI_CPURL').on('change', function () {
    const value = $(this).val();
    if (value) {
      // Remove everything after the domain in the URL
      const match = value.match(/^(https?:\/\/[^\/]+)/);
      if (match) {
        $(this).val(match[1]);
      }
    }
  });

  // Handle EAR file upload - show filename when selected
  $('#TIBCOP_CLI_EAR_FILE_UPLOAD').on('change', function () {
    const files = this.files;
    if (files && files.length > 0) {
      const filename = files[0].name;
      $('#TIBCOP_CLI_EAR_FILE_PATH').val(`${filename}`);
    } else {
      $('#TIBCOP_CLI_EAR_FILE_PATH').val('');
    }
  });

  $('#app_file').on('change', function () {
    const value = $(this).val();
    if (value) {
      const fileFullName = value.split('\\').pop().split('/').pop();
      if (!fileFullName) return;
      // filename will become app name, need to replace . and _ with -
      const fileName = fileFullName.split('.').slice(0, -1).join('.').replace(/[._]/g, "-");
      if (!fileName) return;
      const caseValue = document.getElementById("guiAutoCase").value;
      if (!caseValue) return;

      if (caseValue === "case.k8s_create_and_start_bwce_app") {
        $("#BWCE_APP_NAME").val(fileName);
      } else if (caseValue === "case.k8s_create_and_start_bw5ce_app") {
        $("#BW5CE_APP_NAME").val(fileName);
      } else if (caseValue === "case.k8s_create_and_start_flogo_app") {
        $("#FLOGO_APP_NAME").val(fileName);
      }
    }
  });
}

function preLoadBMDPCreateBW5DMData() {
  loadCPAPI("/cp/api/v1/resources/instances?webui=true&type=ACTIVATION_SERVER")
    .then(res => {
      const activationUrl = res.response?.[0]?.name;
      if (activationUrl) {
        const urlObj = new URL(activationUrl);
        const data = {
          "TP_ACTIVATION_SERVER_PORT": urlObj.port,
          "TP_ACTIVATION_SERVER_CERT_HOSTNAME": urlObj.hostname,
          "TP_ACTIVATION_SERVER_FINGER_PRINT": urlObj.searchParams.get("fp") || "",
        }
        initInputValue(data);
      }
    })
}

// Clean the app_file input and reset the app name to default value from ENV
function cleanAppFileInput() {
  $('#app_file').val('');
  const caseValue = document.getElementById("guiAutoCase").value;
  if (!caseValue) return;

  if (caseValue === "case.k8s_create_and_start_bwce_app") {
    $("#BWCE_APP_NAME").val(ENV.BWCE_APP_NAME);
  } else if (caseValue === "case.k8s_create_and_start_bw5ce_app") {
    $("#BW5CE_APP_NAME").val(ENV.BW5CE_APP_NAME);
  } else if (caseValue === "case.k8s_create_and_start_flogo_app") {
    $("#FLOGO_APP_NAME").val(ENV.FLOGO_APP_NAME);
  }
}

function initInputValue(data) {
  Object.keys(data).forEach(key => {
    let element = document.getElementById(key);
    if (element) {
      const tagName = element.tagName.toUpperCase();
      // for input elements
      if (tagName === "INPUT") {
        switch (element.type) {
          case "checkbox":
            element.checked = data[key] === "true" || data[key] === true;
            break;
          default:
            element.value = data[key];
        }
      } else {
        element.textContent = data[key];
      }
    }
  });
}

function replaceSubdomain(url, newSubdomain) {
  return url.replace(/\/\/[^./]+/, `//${newSubdomain}`);
}
function replaceEmailPrefix(email, newPrefix) {
  return email.replace(/^[^@]+/, newPrefix);
}

function toggleField(fieldsSelector, isVisible) {
  fieldsSelector.forEach(selector => {
    $(selector).css("display", isVisible ? "flex" : "none");
  });
}
// Hide fields by default
function hideFields() {
  const fieldsSelector = [
    ".TP_AUTO_ADMIN_URL",
    ".CP_ADMIN_EMAIL",
    ".CP_ADMIN_PASSWORD",
    ".DP_HOST_PREFIX",
    ".TP_AUTO_MAIL_URL",
    ".TP_AUTO_TOKEN_NAME",
    ".TP_AUTO_K8S_BMDP_NAME",
    ".TP_AUTO_DATA_PLANE_O11Y_SYSTEM_CONFIG",
    ".TP_AUTO_K8S_DP_SERVICE_ACCOUNT_CREATION_ADDITIONAL_SETTINGS",
    ".BWCE_APP_NAME",
    ".BW5CE_APP_NAME",
    ".FLOGO_APP_NAME",
    ".app_file",
    ".GITHUB_TOKEN",
    ".TP_ACTIVATION_SERVER_IP",
    ".TP_ACTIVATION_SERVER_PORT",
    ".TP_ACTIVATION_SERVER_CERT_HOSTNAME",
    ".TP_ACTIVATION_SERVER_FINGER_PRINT",
    ".TP_BMDP_IMAGE_TAG_EMS",
    ".TP_BMDP_IMAGE_TAG_BW5EMSDM",
    ".TP_BMDP_IMAGE_TAG_BW5RVDM",
    ".TP_BMDP_IMAGE_TAG_BW6DM"
  ];
  // if TP_AUTO_TASK_FROM_LOCAL_SOURCE is not true, hide .TP_AUTO_KUBECONFIG, .IS_CLEAN_REPORT, .HEADLESS
  if (ENV?.["TP_AUTO_TASK_FROM_LOCAL_SOURCE"] !== "true") {
    fieldsSelector.push(".TP_AUTO_KUBECONFIG", ".IS_CLEAN_REPORT", ".HEADLESS");
  }
  toggleField(fieldsSelector, false);
}

function initTab() {
  const initialHash = window.location.hash;
  if (initialHash) {
    const tabId = initialHash.substring(1);
    if ($('#' + tabId).length) {
      activateTab(tabId);
    } else {
      activateTab('tab1');
    }
  } else {
    activateTab('tab1');
  }

  $('.tab-button').click(function () {
    const target = $(this).data('target');
    const tabId = target.substring(1);
    window.location.hash = tabId;
    activateTab(tabId);
  });

  $(window).on('hashchange', function () {
    const newHash = window.location.hash;
    const tabId = newHash.substring(1);
    if ($('#' + tabId).length) {
      activateTab(tabId);
    }
  });
}

function activateTab(tabId) {
  $('.tab-button').removeClass('active');
  $('.tab-button[data-target="#' + tabId + '"]').addClass('active');

  $('.tab-content').removeClass('active');
  $('#' + tabId).addClass('active');
}

const cliSettingKeys = [
  "TIBCOP_CLI_CPURL",
  "TIBCOP_CLI_OAUTH_TOKEN"
];
const CLI_SETTING_KEY = "tibcoCliSettings";

function saveCliSetting(currentElement) {
  let settings = {};
  settings = Object.fromEntries(
    cliSettingKeys.map(key => {
      const element = document.getElementById(key);
      if (!element) return [key, ''];

      return [key, element.value || ''];
    })
  );

  localStorage.setItem(CLI_SETTING_KEY, JSON.stringify(settings));
}
function loadCliSetting() {
  const settings = localStorage.getItem(CLI_SETTING_KEY);
  if (settings) {
    const parsedSettings = JSON.parse(settings);
    initInputValue(parsedSettings);
  }
}

// Show/hide progress indicator
function toggleProgress(formElement, show) {
  const progressContainer = formElement.find('.progress-container')[0];
  if (progressContainer) {
    if (show) {
      progressContainer.classList.add('active');
    } else {
      progressContainer.classList.remove('active');
    }
  }
}

// Load default deploy config from bwce-payload.json on page load
async function loadDefaultDeployConfig() {
  // Load BWCE config by default
  await loadPayloadConfig('bwce');
}

async function loadPayloadConfig(type) {
  try {
    // Determine which payload file to load
    const payloadFile = type === 'flogo' ? 'flogo-payload.json' : (type === 'bw5ce' ? 'bw5ce-payload.json' : 'bwce-payload.json');
    const jsonPath = `/upload/${payloadFile}`;

    console.log(`Loading ${type.toUpperCase()} deploy config from: ${jsonPath}`);

    const response = await fetch(jsonPath);
    if (response.ok) {
      const jsonContent = await response.text();
      // Pretty print JSON with 2-space indentation
      const jsonObject = JSON.parse(jsonContent);
      const formattedJson = JSON.stringify(jsonObject, null, 2);
      const textarea = document.getElementById("TIBCOP_CLI_DEPLOY_CONFIG_FILE");
      if (textarea) {
        textarea.value = formattedJson;
        console.log(`${type.toUpperCase()} deploy config loaded successfully`);

        // Add simple syntax highlighting on input (only once)
        textarea.removeEventListener('input', handleJSONInput);
        textarea.addEventListener('input', handleJSONInput);
      } else {
        console.warn('TIBCOP_CLI_DEPLOY_CONFIG_FILE textarea not found');
      }
    } else {
      console.warn(`Could not load ${payloadFile}, status: ${response.status}`);
    }
  } catch (error) {
    console.error(`Error loading ${type} deploy config:`, error);
  }
}

function handleJSONInput() {
  highlightJSON(this);
}

// Simple JSON syntax highlighting
function highlightJSON(textarea) {
  try {
    // Validate JSON
    const jsonObject = JSON.parse(textarea.value);
    // If valid, remove any error styling
    textarea.classList.remove('invalid');
  } catch (e) {
    // If invalid, add error styling
    textarea.classList.add('invalid');
  }
}

// Update file upload label based on operation type
function updateFileUploadLabel(labelText) {
  const labelElement = document.getElementById('TIBCOP_CLI_FILE_UPLOAD_LABEL');
  if (labelElement) {
    labelElement.textContent = labelText;
  }
}

// Initialize Advanced Mode Toggle
// Uses DOM removal/insertion instead of CSS display:none because
// browsers do not reliably support hiding <optgroup>/<option> via CSS.
function initAdvancedModeToggle() {
  const advancedModeToggle = document.getElementById('advancedModeToggle');
  if (!advancedModeToggle) return;

  const cliSelect = document.getElementById('cliAutoCase');
  if (!cliSelect) return;

  // Snapshot elements and create comment markers so we know where to re-insert.
  const advancedGroups = [];  // { element, marker }
  const simpleModeOpts = [];  // { element, marker }

  cliSelect.querySelectorAll('.advanced-optgroup').forEach(el => {
    const marker = document.createComment('advanced-optgroup:' + el.label);
    el.parentNode.insertBefore(marker, el);
    advancedGroups.push({ element: el, marker });
  });

  cliSelect.querySelectorAll('.simple-mode-option').forEach(el => {
    const marker = document.createComment('simple-mode-option:' + el.value);
    el.parentNode.insertBefore(marker, el);
    simpleModeOpts.push({ element: el, marker });
  });

  let isInitialLoad = true;

  advancedModeToggle.addEventListener('change', function () {
    const isAdvancedMode = this.checked;

    // Visual feedback (skip on initial load)
    if (!isInitialLoad) {
      cliSelect.classList.add('mode-switching');
      setTimeout(() => cliSelect.classList.remove('mode-switching'), 600);
    }
    cliSelect.classList.toggle('advanced-mode-active', isAdvancedMode);
    isInitialLoad = false;

    // Toggle advanced optgroups via DOM removal/insertion
    advancedGroups.forEach(({ element, marker }) => {
      if (isAdvancedMode) {
        // Re-insert after its marker
        marker.parentNode.insertBefore(element, marker.nextSibling);
      } else {
        // Remove from DOM; reset selection if needed
        if (element.parentNode) {
          element.querySelectorAll('option').forEach(opt => {
            if (cliSelect.value === opt.value) {
              cliSelect.value = '--Select Case--';
            }
          });
          element.remove();
        }
      }
    });

    // Toggle simple-mode options (visible in simple mode, hidden in advanced)
    simpleModeOpts.forEach(({ element, marker }) => {
      if (isAdvancedMode) {
        if (element.parentNode) {
          if (cliSelect.value === element.value) {
            cliSelect.value = '--Select Case--';
          }
          element.remove();
        }
      } else {
        marker.parentNode.insertBefore(element, marker.nextSibling);
      }
    });

    // Re-trigger case selection change to update field visibility
    $(cliSelect).trigger('change');
  });

  // Set initial state: advanced mode OFF
  advancedModeToggle.checked = false;
  advancedModeToggle.dispatchEvent(new Event('change'));
}
