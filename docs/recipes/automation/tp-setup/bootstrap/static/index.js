/*
 * Copyright (c) 2025. Cloud Software Group, Inc. All Rights Reserved. Confidential & Proprietary
 */

let ENV;
window.onload = function () {
  $(".is_loading").show();
  loadData().then(res => {
    ENV = res;
    $(".is_loading").hide();
    hideFields();
  });
  handleFieldsAction();

  initTab();
  loadCliSetting()
};

async function loadData() {
  try {
    let response = await fetch('/get_env');
    let data = await response.json();
    initInputValue(data);
    return data;
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

async function runCliScript(currentElement) {
  const formElement = $(currentElement).closest('form');
  const additionalParams = {
    TP_AUTO_IS_CONFIG_O11Y: true,
    case: document.getElementById("cliAutoCase").value,

    TIBCOP_CLI_CPURL: document.getElementById("TIBCOP_CLI_CPURL").value,
    TIBCOP_CLI_OAUTH_TOKEN: document.getElementById("TIBCOP_CLI_OAUTH_TOKEN").value,
    TIBCOP_CLI_DP_NAME: document.getElementById("TIBCOP_CLI_DP_NAME").value,
    TIBCOP_CLI_OTHER_ARGS: document.getElementById("TIBCOP_CLI_OTHER_ARGS").value,
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
    .catch(error => console.error('Error:', error));
}

function stopScript(currentElement) {
  const formElement = $(currentElement).closest('form');

  const preElement = formElement.find('.logs')[0];
  const runButton = formElement.find('.runBtn')[0];
  const stopButton = formElement.find('.stopBtn')[0];

  fetch('/stop-script' + (window.currentJobId ? `?jobId=${window.currentJobId}` : ""))
    .then(response => response.json())
    .then(data => {
      document.getElementById("output").innerHTML += `\n[INFO] ${data.message}\n`;
      preElement.scrollTop = preElement.scrollHeight;

      runButton.disabled = false;
      stopButton.disabled = true;
    })
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
      case "page_token":
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
  "TIBCOP_CLI_OAUTH_TOKEN",
  "SAVE_CLI_SETTING"
];
const CLI_SETTING_KEY = "tibcoCliSettings";

function saveCliSetting(currentElement) {
  let settings = {};
  if (currentElement.checked) {
    settings = Object.fromEntries(
      cliSettingKeys.map(key => {
        const element = document.getElementById(key);
        if (!element) return [key, ''];

        const value = element.type === 'checkbox' ? element.checked : element.value || '';
        return [key, value];
      })
    );
  }

  localStorage.setItem(CLI_SETTING_KEY, JSON.stringify(settings));
}
function loadCliSetting() {
  const settings = localStorage.getItem(CLI_SETTING_KEY);
  if (settings) {
    const parsedSettings = JSON.parse(settings);
    initInputValue(parsedSettings);
  }
}
