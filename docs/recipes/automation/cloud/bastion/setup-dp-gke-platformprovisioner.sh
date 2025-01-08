#!/bin/bash
# Note: Run ths script with -x for debugging
# Version: 20241217

source _common.sh

function main() {

    init

    if [ -z "${1}" ] ; then
        # No arguments supplied
        if [ "${INSTALL_PREREQ}" == true ]; then common::install_prereq; install_gcp_prereq; fi
        check_gcp_access
        
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
# Replacement for recipe globalEnvVariable below
export PIPELINE_LOG_DEBUG=true
export ACCOUNT="gcp-822123456789"
export GCP_PROJECT_ID="psg-us"
export GCP_REGION="us-central1" # currently us-east1 cannot be used because it does not have a zone a which is hard coded in create-gke.sh
export TP_CLUSTER_NAME="tp-cluster"
export TP_CLUSTER_VERSION="1.31"
export TP_AUTHORIZED_IP="<<Your public ip address eg: x.x.x.x/32>>
export TP_TOP_LEVEL_DOMAIN="gcp.dataplanes.pro"
export TP_SANDBOX="psa"
export TP_MAIN_INGRESS_SANDBOX_SUBDOMAIN="gke-dp"
export TP_INSTALL_O11Y=true
EOT
        exit 0
    else
        # Load properties from config.props file
        source ${HOME}/config.props

        # Check for required environment variables   
        if [ -z "${INSTALL_PREREQ}" ]; then echo "INSTALL_PREREQ is not set in config.props. Please set value."; exit 0; fi
        if [ -z "${PIPELINE_LOG_DEBUG}" ]; then echo "PIPELINE_LOG_DEBUG is not set in config.props. Please set value."; exit 0; fi
        if [ -z "${GCP_PROJECT_ID}" ]; then echo "GCP_PROJECT_ID is not set in config.props. Please set value."; exit 0; fi        
        if [ -z "${GCP_REGION}" ]; then echo "GCP_REGION is not set in config.props. Please set value."; exit 0; fi        
        if [ -z "${TP_CLUSTER_NAME}" ]; then echo "TP_CLUSTER_NAME is not set in config.props. Please set value."; exit 0; fi        
        if [ -z "${TP_CLUSTER_VERSION}" ]; then echo "TP_CLUSTER_VERSION is not set in config.props. Please set value."; exit 0; fi        
        if [ -z "${TP_AUTHORIZED_IP}" ]; then echo "TP_AUTHORIZED_IP is not set in config.props. Please set value."; exit 0; fi        
        if [ -z "${TP_TOP_LEVEL_DOMAIN}" ]; then echo "TP_TOP_LEVEL_DOMAIN is not set in config.props. Please set value."; exit 0; fi        
        if [ -z "${TP_SANDBOX}" ]; then echo "TP_SANDBOX is not set in config.props. Please set value."; exit 0; fi        
        if [ -z "${TP_MAIN_INGRESS_SANDBOX_SUBDOMAIN}" ]; then echo "TP_MAIN_INGRESS_SANDBOX_SUBDOMAIN is not set in config.props. Please set value."; exit 0; fi        
        if [ -z "${TP_INSTALL_O11Y}" ]; then echo "TP_INSTALL_O11Y is not set in config.props. Please set value."; exit 0; fi        

        export SLEEP_BETWEEN_TASK_SEC=5

        # Below is to compensate for the error "PIPELINE_NAME can not be empty" after platform-provisioner checkin on 12/18/2024
        export PIPELINE_CMD_NAME_YQ="yq"
		# Below is to compensate for the error "docker: Error response from daemon: invalid mount config for type "bind": bind source path does not exist: /home/ubuntu/.kube/config."
		mkdir -p ${HOME}/.kube/config

        export SP_DISTRO=$(awk -F= '/^ID=/{print $2}' /etc/os-release | tr "[:upper:]" "[:lower:]" | tr -d '"')
        if [[ "${SP_DISTRO}" == *"ubuntu"* ]]; then export SP_UBUNTU=true ; else export export SP_UBUNTU=false ; fi
        if [[ "${SP_DISTRO}" == *"rhel"* ]]; then export SP_RHEL=true ; else export export SP_RHEL=false ; fi
        if [[ "${SP_DISTRO}" == *"amzn"* ]]; then export SP_AMZN=true ; else export export SP_AMZN=false ; fi # For Amazon Linux

        echo "SP_UBUNTU: ${SP_UBUNTU}"
        echo "SP_RHEL: ${SP_RHEL}"
        echo "SP_AMZN: ${SP_AMZN}"

        cat <<PACKAGE > ${HOME}/setenv.sh
export GCP_PROJECT_ID=${GCP_PROJECT_ID} # used for teardown
export GCP_REGION=${GCP_REGION} # used for teardown
export TP_CLUSTER_NAME=${TP_CLUSTER_NAME} # used for teardown
PACKAGE

        cat <<'PACKAGE' >> ${HOME}/setenv.sh
export KUBECONFIG=${HOME}/${TP_CLUSTER_NAME}.yml
gcloud container clusters get-credentials --zone ${GCP_REGION} ${TP_CLUSTER_NAME}
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

function install_gcp_prereq() {
	gcloud --version &> /dev/null
	RESULT=$?
	if [ "${RESULT}" -ne 0 ]; then
		echo "########## Installing gcloud CLI ##########"
		echo "Not implemented because gcloud should be available by default"
		sleep ${SLEEP_BETWEEN_TASK_SEC}
		gcloud --version
		# Sample Output: 
		# Google Cloud SDK 501.0.0
		# alpha 2024.11.08
		# beta 2024.11.08
		# bq 2.1.9
		# bundled-python3-unix 3.11.9
		# core 2024.11.08
		# gcloud-crc32c 1.0.0
		# gsutil 5.31
		# minikube 1.34.0
		# skaffold 2.13.1
	fi

	##### CONTINUE HERE.... UNABLE TO CONNECT TO GKE.... 
	gke-gcloud-auth-plugin --version &> /dev/null
	RESULT=$?
	if [ "${RESULT}" -ne 0 ]; then
		echo "########## Install GKE GCloud Auth Plugin ##########"
		if [ "${SP_UBUNTU}" == true ]; then
			sudo apt-get -y install apt-transport-https ca-certificates gnupg curl
			curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg
			echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | sudo tee -a /etc/apt/sources.list.d/google-cloud-sdk.list
			sudo apt-get -y update 
			#sudo apt-get -y install google-cloud-cli
			sudo apt-get -y install google-cloud-sdk-gke-gcloud-auth-plugin	
		fi
		if [ "${SP_RHEL}" == true ] || [ "${SP_AMZN}" == true ]; then    
			echo "Not Implemented"
		fi
		sleep ${SLEEP_BETWEEN_TASK_SEC}
		gke-gcloud-auth-plugin --version
		# Sample Output:
		# Kubernetes v1.28.2-alpha+2291a60496d419da95186fa76128c72fa8e3410d
	fi
}

function check_gcp_access() {
	ACTIVE_ACCOUNT=$(gcloud auth list --filter=status:ACTIVE --format="value(account)")
	if [[ $ACTIVE_ACCOUNT == *"serviceaccount"* ]]; then
		echo "########## Logging in gcloud CLI ##########"
		sudo chown -R $USER:$USER ${HOME}/.config
		gcloud auth login
		sleep ${SLEEP_BETWEEN_TASK_SEC}
		gcloud auth list --filter=status:ACTIVE --format="value(account)"	
		# Sample Output: 
		# <<tom>>@cloud.com
	fi
}

function platform_provisioner_verify_access() {

    cd ${HOME}/platform-provisioner
    echo "########## Verify GCP Account Access ##########"
    export PIPELINE_INPUT_RECIPE="docs/recipes/tests/test-gcp.yaml"
    ./dev/platform-provisioner.sh 

}

function platform_provisioner_create() {

    cd ${HOME}/platform-provisioner
    echo "########## Create EKS Cluster With Dataplane Components ##########"
    # Note: Do not use envsubst because that would replace the rest of the ${...} references which we do not want. We want a more targeted replacement only in the "globalEnvVariable:" section.
	export PIPELINE_INPUT_RECIPE="docs/recipes/k8s/cloud/deploy-tp-gke_with_values.yaml"
    cp docs/recipes/k8s/cloud/deploy-tp-gke.yaml ${PIPELINE_INPUT_RECIPE}

    if [[ "${PIPELINE_LOG_DEBUG}" != "" ]]; then yq eval -i '.meta.globalEnvVariable.PIPELINE_LOG_DEBUG = env(PIPELINE_LOG_DEBUG)' ${PIPELINE_INPUT_RECIPE} ; fi
	
    if [[ "${GCP_PROJECT_ID}" != "" ]]; then yq eval -i '.meta.globalEnvVariable.GCP_PROJECT_ID = env(GCP_PROJECT_ID)' ${PIPELINE_INPUT_RECIPE} ; fi
    if [[ "${GCP_REGION}" != "" ]]; then yq eval -i '.meta.globalEnvVariable.GCP_REGION = env(GCP_REGION)' ${PIPELINE_INPUT_RECIPE} ; fi
    if [[ "${TP_CLUSTER_NAME}" != "" ]]; then yq eval -i '.meta.globalEnvVariable.TP_CLUSTER_NAME = env(TP_CLUSTER_NAME)' ${PIPELINE_INPUT_RECIPE} ; fi
    if [[ "${TP_CLUSTER_VERSION}" != "" ]]; then yq eval -i '.meta.globalEnvVariable.TP_CLUSTER_VERSION = env(TP_CLUSTER_VERSION)' ${PIPELINE_INPUT_RECIPE} ; fi
    if [[ "${GCP_REGION}" != "" ]]; then yq eval -i '.meta.globalEnvVariable.TP_CLUSTER_REGION = env(GCP_REGION)' ${PIPELINE_INPUT_RECIPE} ; fi
    if [[ "${TP_AUTHORIZED_IP}" != "" ]]; then yq eval -i '.meta.globalEnvVariable.TP_AUTHORIZED_IP = env(TP_AUTHORIZED_IP)' ${PIPELINE_INPUT_RECIPE} ; fi
    if [[ "${TP_TOP_LEVEL_DOMAIN}" != "" ]]; then yq eval -i '.meta.globalEnvVariable.TP_TOP_LEVEL_DOMAIN = env(TP_TOP_LEVEL_DOMAIN)' ${PIPELINE_INPUT_RECIPE} ; fi
    if [[ "${TP_SANDBOX}" != "" ]]; then yq eval -i '.meta.globalEnvVariable.TP_SANDBOX = env(TP_SANDBOX)' ${PIPELINE_INPUT_RECIPE} ; fi
    if [[ "${TP_MAIN_INGRESS_SANDBOX_SUBDOMAIN}" != "" ]]; then yq eval -i '.meta.globalEnvVariable.TP_MAIN_INGRESS_SANDBOX_SUBDOMAIN = env(TP_MAIN_INGRESS_SANDBOX_SUBDOMAIN)' ${PIPELINE_INPUT_RECIPE} ; fi
    if [[ "${TP_INSTALL_O11Y}" != "" ]]; then yq eval -i '.meta.globalEnvVariable.TP_INSTALL_O11Y = env(TP_INSTALL_O11Y)' ${PIPELINE_INPUT_RECIPE} ; fi

    ./dev/platform-provisioner.sh

}

function platform_provisioner_teardown() {

    echo "########## Tear Down GKE Cluster With Dataplane Components ##########"
    source ${HOME}/setenv.sh        
    cd ${HOME}/platform-provisioner
    ./docs/recipes/k8s/cloud/scripts/gke/delete-gke.sh  

}

function platform_provisioner_cleanup() {
   echo "No additional cleanup neeeded"
}

main "$@"; exit

# Test Commands
# kubectl get ingress -A
