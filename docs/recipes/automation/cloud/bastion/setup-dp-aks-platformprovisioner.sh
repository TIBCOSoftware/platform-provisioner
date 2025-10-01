#!/bin/bash
# Note: Run ths script with -x for debugging
# Version: 20250327

source _common.sh

function main() {

    init

    if [ -z "${1}" ] ; then
        # No arguments supplied
        if [ "${INSTALL_PREREQ}" == true ]; then common::install_prereq; install_azure_prereq; fi
        check_azure_access
        
        read -p "Start Type [1-Verify Access (default), 2-Create, 3-Teardown, 4-Cleanup]: " INPUT_RUN_TYPE
        INPUT_RUN_TYPE=${INPUT_RUN_TYPE:-1}
        INPUT_RUN_TYPE=${INPUT_RUN_TYPE^^}

        echo "INPUT_RUN_TYPE: ${INPUT_RUN_TYPE}"        

        sleep ${SLEEP_BETWEEN_TASK_SEC}

        case ${INPUT_RUN_TYPE} in
        "1")
            platform_provisioner_verify_access
        ;;
        "2")
            platform_provisioner_create
        ;;
        "3")
            platform_provisioner_teardown
        ;;
        "4")
            platform_provisioner_cleanup
        ;;    
          *)
            echo "Unknown run type"
            exit 1
        ;;
        esac
    else
        FUNCTION_NAME=${1}
        ${FUNCTION_NAME}
    fi

}

function init() {

    if ! [ -f ${HOME}/config.props ]; then
        echo "####################################################################################################################"
        echo "########## Property file not found.                                                                       ##########"
        echo "########## Creating default config.props...                                                               ##########"
        echo "########## Please modify environment variables in config.props as needed prior to running script again.   ##########"
        echo "####################################################################################################################"
        cat <<EOT > ${HOME}/config.props
export INSTALL_PREREQ=true
export SKIP_HELM_CHARTS=false # Set to true to set all .helmCharts[].condition to false so that only K8s is setup
# Replacement for recipe globalEnvVariable below
export PIPELINE_LOG_DEBUG=true
export ACCOUNT="<<e.g., 123abc12-0abc-12ab-a1b2-123a123ab12a>>" # This is the subscription id from your azure subscription.
export TP_RESOURCE_GROUP="tp-rg"
export TP_AZURE_REGION="eastus"
export TP_CLUSTER_NAME="<<tp-cluster>>"
export TP_AUTHORIZED_IP="77.185.75.24/32" # Your public IP CIDR
export TP_TOP_LEVEL_DOMAIN="azure.dataplanes.pro" # Your top level domain name eg: azure.dataplanes.pro
export TP_SANDBOX="cs-nam" # Your sandbox name
export TP_MAIN_INGRESS_SANDBOX_SUBDOMAIN="aks-dp" # Your main ingress subdomain name. full domain will be: <TP_MAIN_INGRESS_SANDBOX_SUBDOMAIN>.<TP_SANDBOX>.<TP_TOP_LEVEL_DOMAIN>
export TP_DNS_RESOURCE_GROUP="cic-dns" # The resource group for the DNS zone
export TP_INSTALL_O11Y=true
export TP_CLUSTER_INSTANCE_TYPE=Standard_D8s_v5 # default is Standard_D8_v5 (does not support Premium_LRS), using D8s does.
EOT
        exit 0
    else
        # Load properties from config.props file
        source ${HOME}/config.props

        # Check for required environment variables   
        if [ -z "${INSTALL_PREREQ}" ]; then echo "INSTALL_PREREQ is not set in config.props. Please set value."; exit 0; fi
        if [ -z "${SKIP_HELM_CHARTS}" ]; then echo "SKIP_HELM_CHARTS is not set in config.props. Please set value."; exit 0; fi
        if [ -z "${PIPELINE_LOG_DEBUG}" ]; then echo "PIPELINE_LOG_DEBUG is not set in config.props. Please set value."; exit 0; fi
        if [ -z "${ACCOUNT}" ]; then echo "ACCOUNT is not set in config.props. Please set value."; exit 0; fi
        if [ -z "${TP_RESOURCE_GROUP}" ]; then echo "TP_RESOURCE_GROUP is not set in config.props. Please set value."; exit 0; fi
        if [ -z "${TP_AZURE_REGION}" ]; then echo "TP_AZURE_REGION is not set in config.props. Please set value."; exit 0; fi
        if [ -z "${TP_CLUSTER_NAME}" ]; then echo "TP_CLUSTER_NAME is not set in config.props. Please set value."; exit 0; fi
        if [ -z "${TP_AUTHORIZED_IP}" ]; then echo "TP_AUTHORIZED_IP is not set in config.props. Please set value."; exit 0; fi        
        if [ -z "${TP_TOP_LEVEL_DOMAIN}" ]; then echo "TP_TOP_LEVEL_DOMAIN is not set in config.props. Please set value."; exit 0; fi
        if [ -z "${TP_SANDBOX}" ]; then echo "TP_SANDBOX is not set in config.props. Please set value."; exit 0; fi
        if [ -z "${TP_MAIN_INGRESS_SANDBOX_SUBDOMAIN}" ]; then echo "TP_MAIN_INGRESS_SANDBOX_SUBDOMAIN is not set in config.props. Please set value."; exit 0; fi
        if [ -z "${TP_DNS_RESOURCE_GROUP}" ]; then echo "TP_DNS_RESOURCE_GROUP is not set in config.props. Please set value."; exit 0; fi
        if [ -z "${TP_INSTALL_O11Y}" ]; then echo "TP_INSTALL_O11Y is not set in config.props. Please set value."; exit 0; fi

        export SLEEP_BETWEEN_TASK_SEC=5
        export AWS_REGION=${REGION}
        export ROLE_ARN="arn:aws:iam::${ACCOUNT}:role/${PIPELINE_AWS_MANAGED_ACCOUNT_ROLE}"

        # Below is to compensate for the error "PIPELINE_NAME can not be empty" after platform-provisioner checkin on 12/18/2024
        export PIPELINE_CMD_NAME_YQ="yq"

        export SP_DISTRO=$(awk -F= '/^ID=/{print $2}' /etc/os-release | tr "[:upper:]" "[:lower:]" | tr -d '"')
        if [[ "${SP_DISTRO}" == *"ubuntu"* ]]; then export SP_UBUNTU=true ; else export export SP_UBUNTU=false ; fi
        if [[ "${SP_DISTRO}" == *"rhel"* ]]; then export SP_RHEL=true ; else export export SP_RHEL=false ; fi
        if [[ "${SP_DISTRO}" == *"amzn"* ]]; then export SP_AMZN=true ; else export export SP_AMZN=false ; fi # For Amazon Linux

        echo "SP_UBUNTU: ${SP_UBUNTU}"
        echo "SP_RHEL: ${SP_RHEL}"
        echo "SP_AMZN: ${SP_AMZN}"

        cat <<PACKAGE > ${HOME}/setenv.sh
export ACCOUNT=${ACCOUNT} # used for teardown
export TP_RESOURCE_GROUP=${TP_RESOURCE_GROUP} # used for teardown
export TP_AZURE_REGION=${TP_AZURE_REGION}
export TP_CLUSTER_NAME=${TP_CLUSTER_NAME} # used for teardown
PACKAGE

        cat <<'PACKAGE' >> ${HOME}/setenv.sh
az config set defaults.location=${REGION}
az aks get-credentials --resource-group ${TP_RESOURCE_GROUP} --name ${TP_CLUSTER_NAME} --file ${HOME}/${TP_CLUSTER_NAME}.yml --overwrite-existing
RESULT=$?
if [ "${RESULT}" -ne 0 ]; then
    echo "Cluster ${TP_CLUSTER_NAME} not found. Skip configure Kubectl."
else
    export KUBECONFIG=${HOME}/${TP_CLUSTER_NAME}.yml
fi

# Helpful aliases below
alias kns="kubectl get namespaces"
alias ktt="kubectl get all --namespace tekton-tasks"
alias kin="kubectl get ingress -A"
alias ktn="kubectl top nodes"
alias ktp="kubectl top pods -A"
alias kdn="kubectl describe nodes"
alias kpod="kubectl get pods -A"
alias kevents="kubectl get events -A -w"
alias kclasses="kubectl get storageclass && kubectl get ingressclass"
PACKAGE

    fi

}

function install_azure_prereq() {
    az --version &> /dev/null
    RESULT=$?
    if [ "${RESULT}" -ne 0 ]; then
        echo "########## Installing Azure CLI ##########"
        curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
        sleep ${SLEEP_BETWEEN_TASK_SEC}
        az --version
        # Sample Output: 
        # azure-cli                         2.67.0
        # core                              2.67.0
        # telemetry                          1.1.0
        # Dependencies:
        # msal                              1.31.0
        # azure-mgmt-resource               23.1.1
        # Python location '/opt/az/bin/python3'
        # Extensions directory '/home/azureuser/.azure/cliextensions'
        # Python (Linux) 3.12.7 (main, Nov 13 2024, 04:06:34) [GCC 13.2.0]
        # Legal docs and information: aka.ms/AzureCliLegal
        # Your CLI is up-to-date.
    fi

}

function check_azure_access() {
    az account show &> /dev/null
    RESULT=$?
    if [ "${RESULT}" -ne 0 ]; then
        echo "########## Installing Azure CLI ##########"
        az login
        #az login --service-principal --username "${applicationId}" --password "${password}" --tenant "${tenantID}"
        sleep ${SLEEP_BETWEEN_TASK_SEC}
        az account show 
        # Sample Output: 
        # azure-cli                         2.67.0
        # core                              2.67.0
        # telemetry                          1.1.0
        # Dependencies:
        # msal                              1.31.0
        # azure-mgmt-resource               23.1.1
        # Python location '/opt/az/bin/python3'
        # Extensions directory '/home/azureuser/.azure/cliextensions'
        # Python (Linux) 3.12.7 (main, Nov 13 2024, 04:06:34) [GCC 13.2.0]
        # Legal docs and information: aka.ms/AzureCliLegal
        # Your CLI is up-to-date.
    fi
}

function platform_provisioner_update_deploy_recipe() {

    cd ${HOME}/platform-provisioner
    export PIPELINE_INPUT_RECIPE="docs/recipes/k8s/cloud/deploy-tp-aks_with_values.yaml"
    cp docs/recipes/k8s/cloud/deploy-tp-aks.yaml ${PIPELINE_INPUT_RECIPE}

    # Note: Do not use envsubst because that would replace the rest of the ${...} references which we do not want. We want a more targeted replacement only in the "globalEnvVariable:" section.
    # The below are no longer needed because the new code block will match and replace based on what are provided in config.props
    #if [[ "${PIPELINE_LOG_DEBUG}" != "" ]]; then yq eval -i '.meta.globalEnvVariable.PIPELINE_LOG_DEBUG = env(PIPELINE_LOG_DEBUG)' ${PIPELINE_INPUT_RECIPE} ; fi
    #if [[ "${ACCOUNT}" != "" ]]; then yq eval -i '.meta.globalEnvVariable.ACCOUNT = env(ACCOUNT)' ${PIPELINE_INPUT_RECIPE} ; fi
    #if [[ "${TP_RESOURCE_GROUP}" != "" ]]; then yq eval -i '.meta.globalEnvVariable.TP_RESOURCE_GROUP = env(TP_RESOURCE_GROUP)' ${PIPELINE_INPUT_RECIPE} ; fi
    #if [[ "${TP_AZURE_REGION}" != "" ]]; then yq eval -i '.meta.globalEnvVariable.TP_AZURE_REGION = env(TP_AZURE_REGION)' ${PIPELINE_INPUT_RECIPE} ; fi
    #if [[ "${TP_CLUSTER_NAME}" != "" ]]; then yq eval -i '.meta.globalEnvVariable.TP_CLUSTER_NAME = env(TP_CLUSTER_NAME)' ${PIPELINE_INPUT_RECIPE} ; fi
    #if [[ "${TP_AUTHORIZED_IP}" != "" ]]; then yq eval -i '.meta.globalEnvVariable.TP_AUTHORIZED_IP = env(TP_AUTHORIZED_IP)' ${PIPELINE_INPUT_RECIPE} ; fi
    #if [[ "${TP_TOP_LEVEL_DOMAIN}" != "" ]]; then yq eval -i '.meta.globalEnvVariable.TP_TOP_LEVEL_DOMAIN = env(TP_TOP_LEVEL_DOMAIN)' ${PIPELINE_INPUT_RECIPE} ; fi
    #if [[ "${TP_SANDBOX}" != "" ]]; then yq eval -i '.meta.globalEnvVariable.TP_SANDBOX = env(TP_SANDBOX)' ${PIPELINE_INPUT_RECIPE} ; fi
    #if [[ "${TP_MAIN_INGRESS_SANDBOX_SUBDOMAIN}" != "" ]]; then yq eval -i '.meta.globalEnvVariable.TP_MAIN_INGRESS_SANDBOX_SUBDOMAIN = env(TP_MAIN_INGRESS_SANDBOX_SUBDOMAIN)' ${PIPELINE_INPUT_RECIPE} ; fi
    #if [[ "${TP_DNS_RESOURCE_GROUP}" != "" ]]; then yq eval -i '.meta.globalEnvVariable.TP_DNS_RESOURCE_GROUP = env(TP_DNS_RESOURCE_GROUP)' ${PIPELINE_INPUT_RECIPE} ; fi
    #if [[ "${TP_INSTALL_O11Y}" != "" ]]; then yq eval -i '.meta.globalEnvVariable.TP_INSTALL_O11Y = env(TP_INSTALL_O11Y)' ${PIPELINE_INPUT_RECIPE} ; fi

    CONFIG_DELIMITER="="
    while IFS=${CONFIG_DELIMITER} read -r KEY VALUE; do
	    if [[ ${KEY} != \#* ]] ; then
		    if [ -z "${KEY}" ] || [ -z "${VALUE}" ]; then echo "Skipping Key: '${KEY}' Value: '${VALUE}'"; continue; fi	
            KEY=${KEY#"export "} # removes export if exists
			KEY=$(common::trim_string_remove_comment ${KEY})
            YAML_KEY_PATH=".meta.globalEnvVariable.${KEY}"
			VALUE=$(common::trim_string_remove_comment ${VALUE})			
            echo "Updating recipe '${PIPELINE_INPUT_RECIPE}' YAML path '${YAML_KEY_PATH}' with value '${VALUE}' ..."
	        common::update_yaml_value ${PIPELINE_INPUT_RECIPE} ${YAML_KEY_PATH} ${VALUE}
		else
		    echo "Skipping commented ${KEY}"
		fi
    done < ${HOME}/config.props

    if [ "${SKIP_HELM_CHARTS}" == true ]; then yq -i '.helmCharts[].condition = false' ${PIPELINE_INPUT_RECIPE}; fi

    echo "Updated deploy recipe file at ${HOME}/platform-provisioner/${PIPELINE_INPUT_RECIPE}"
	
}

function platform_provisioner_verify_access() {

    cd ${HOME}/platform-provisioner
    echo "########## Verify Azure Account Access ##########"
    export PIPELINE_INPUT_RECIPE="docs/recipes/tests/test-azure.yaml"
    ./dev/platform-provisioner.sh 
    platform_provisioner_update_deploy_recipe

}

function platform_provisioner_create() {

    cd ${HOME}/platform-provisioner
    echo "########## Create AKS Cluster With Dataplane Components ##########"
    export PIPELINE_INPUT_RECIPE="docs/recipes/k8s/cloud/deploy-tp-aks_with_values.yaml"
    platform_provisioner_update_deploy_recipe
    ./dev/platform-provisioner.sh

}

function platform_provisioner_teardown() {

    cd ${HOME}/platform-provisioner
    echo "########## Tear Down AKS Cluster With Dataplane Components ##########"
    source ${HOME}/setenv.sh        
    az config set defaults.location=${REGION}
    az aks get-credentials --resource-group ${TP_RESOURCE_GROUP} --name ${TP_CLUSTER_NAME} --file ${HOME}/${TP_CLUSTER_NAME}.yml --overwrite-existing
    export KUBECONFIG=${HOME}/${TP_CLUSTER_NAME}.yml
    cd ${HOME}/platform-provisioner
    #export TP_CLUSTER_NAME=${GUI_TP_CLUSTER_NAME}
    ./docs/recipes/k8s/cloud/scripts/aks/clean-up-tp-azure.sh   

}

function platform_provisioner_cleanup() {

   rm -rf ${HOME}/.kube

}

main "$@"; exit


