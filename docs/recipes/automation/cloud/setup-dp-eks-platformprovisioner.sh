#!/bin/bash
# Note: Run ths script with -x for debugging
# Version: 20241217

source _common.sh

function main() {

    init

    if [ -z "${1}" ] ; then
        # No arguments supplied
        if [ "${INSTALL_PREREQ}" == true ]; then common::install_prereq; install_aws_prereq; fi
        check_aws_access
        
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
export ACCOUNT=<<e.g., 334987654321>>
export REGION=us-east-1
export PIPELINE_LOG_DEBUG=true
export TP_CLUSTER_NAME=tp-cluster
export TP_DOMAIN=tp-ingress.dataplanes.pro
export TP_INSTALL_K8S=true
export TP_INSTALL_EFS=true
export TP_INSTALL_POSTGRES=true
export TP_INSTALL_O11Y=true
export PIPELINE_AWS_MANAGED_ACCOUNT_ROLE="platform-provisioner" # AWS Role to assume to with needed permissions
export PIPELINE_INITIAL_ASSUME_ROLE="true" # Default value is false. Set this to true to assume role to PIPELINE_AWS_MANAGED_ACCOUNT_ROLE
export PIPELINE_USE_LOCAL_CREDS="false" # Default value is true.Set this to false to assume role to PIPELINE_AWS_MANAGED_ACCOUNT_ROLE
EOT
        exit 0
    else
        # Load properties from config.props file
        source ${HOME}/config.props

        # Check for required environment variables   
        if [ -z "${ACCOUNT}" ]; then echo "ACCOUNT is not set in config.props. Please set value."; exit 0; fi
        if [ -z "${REGION}" ]; then echo "REGION is not set in config.props. Please set value."; exit 0; fi        
        if [ -z "${INSTALL_PREREQ}" ]; then echo "INSTALL_PREREQ is not set in config.props. Please set value."; exit 0; fi
        if [ -z "${PIPELINE_LOG_DEBUG}" ]; then echo "PIPELINE_LOG_DEBUG is not set in config.props. Please set value."; exit 0; fi
        if [ -z "${TP_CLUSTER_NAME}" ]; then echo "TP_CLUSTER_NAME is not set in config.props. Please set value."; exit 0; fi
        if [ -z "${TP_DOMAIN}" ]; then echo "TP_DOMAIN is not set in config.props. Please set value."; exit 0; fi
        if [ -z "${TP_INSTALL_K8S}" ]; then echo "TP_INSTALL_K8S is not set in config.props. Please set value."; exit 0; fi
        if [ -z "${TP_INSTALL_EFS}" ]; then echo "TP_INSTALL_EFS is not set in config.props. Please set value."; exit 0; fi
        if [ -z "${TP_INSTALL_POSTGRES}" ]; then echo "TP_INSTALL_POSTGRES is not set in config.props. Please set value."; exit 0; fi
        if [ -z "${TP_INSTALL_O11Y}" ]; then echo "TP_INSTALL_O11Y is not set in config.props. Please set value."; exit 0; fi
        if [ -z "${PIPELINE_AWS_MANAGED_ACCOUNT_ROLE}" ]; then echo "PIPELINE_AWS_MANAGED_ACCOUNT_ROLE is not set in config.props. Please set value."; exit 0; fi
        if [ -z "${PIPELINE_INITIAL_ASSUME_ROLE}" ]; then echo "PIPELINE_INITIAL_ASSUME_ROLE is not set in config.props. Please set value."; exit 0; fi
        if [ -z "${PIPELINE_USE_LOCAL_CREDS}" ]; then echo "PIPELINE_USE_LOCAL_CREDS is not set in config.props. Please set value."; exit 0; fi

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
export ACCOUNT="334701562263" # used for teardown
export TP_CLUSTER_NAME=${TP_CLUSTER_NAME} # used for teardown
export AWS_PROFILE="main-${ACCOUNT}-assumerole"    
export AWS_REGION=${AWS_REGION}
unset AWS_ACCESS_KEY_ID # needs to be unset for AWS_PROFILE to take effect
unset AWS_SECRET_ACCESS_KEY # needs to be unset for AWS_PROFILE to take effect
unset AWS_SESSION_TOKEN # needs to be unset for AWS_PROFILE to take effect
PACKAGE

        cat <<'PACKAGE' >> ${HOME}/setenv.sh
aws eks describe-cluster --name ${TP_CLUSTER_NAME} &> /dev/null
RESULT=$?
if [ "${RESULT}" -ne 0 ]; then
    echo "Cluster ${TP_CLUSTER_NAME} not found. Skip configure Kubectl."
else
    aws eks update-kubeconfig --name ${TP_CLUSTER_NAME} --kubeconfig "${HOME}/${TP_CLUSTER_NAME}.yml"
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
alias agetidmain="aws --profile main-${ACCOUNT} sts get-caller-identity"
alias agetidassume="aws --profile main-${ACCOUNT}-assumerole sts get-caller-identity"
alias agetid="aws sts get-caller-identity"
alias aidassume="aws sts assume-role --role-arn ${ROLE_ARN} --role-session-name AWSCLI-Session"

PACKAGE

    fi

}

function install_aws_prereq() {
    /usr/local/bin/aws --version &> /dev/null
    RESULT=$?
    if [ "${RESULT}" -ne 0 ]; then
        echo "########## Installing AWS CLI ##########"
        curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
        unzip -o awscliv2.zip
        sudo ./aws/install
        sleep ${SLEEP_BETWEEN_TASK_SEC}
        /usr/local/bin/aws --version
        # Sample Output: aws-cli/2.16.9 Python/3.11.8 Linux/6.8.0-1008-aws exe/x86_64.ubuntu.24
    fi

    eksctl version &> /dev/null
    RESULT=$?
    if [ "${RESULT}" -ne 0 ]; then
        echo "########## Install eksctl ##########"
        # for ARM systems, set ARCH to: `arm64`, `armv6` or `armv7`
        ARCH=amd64
        PLATFORM=$(uname -s)_$ARCH
        curl -sLO "https://github.com/eksctl-io/eksctl/releases/latest/download/eksctl_$PLATFORM.tar.gz"
        tar -xzf eksctl_$PLATFORM.tar.gz -C /tmp && rm eksctl_$PLATFORM.tar.gz
        sudo mv /tmp/eksctl /usr/local/bin
        sleep ${SLEEP_BETWEEN_TASK_SEC}    
        eksctl version
    fi 
}

function check_aws_access() {
    # Check if still able to access AWS    
    export AWS_PROFILE="main-${ACCOUNT}"
    aws sts get-caller-identity &> /dev/null
    RESULT=$?
    if [ "${RESULT}" -ne 0 ]; then
        echo "########## Unable to connect to AWS, setting up credentials ##########"
        if [ -z ${AWS_ACCESS_KEY_ID+x} ]; then echo "AWS_ACCESS_KEY_ID is unset"; exit 1; fi
        if [ -z ${AWS_SECRET_ACCESS_KEY+x} ]; then echo "AWS_SECRET_ACCESS_KEY is unset"; exit 1; fi
        if [ -z ${AWS_SESSION_TOKEN+x} ]; then echo "AWS_SESSION_TOKEN is unset"; exit 1; fi     
        mkdir -p ${HOME}/.aws
        cat <<EOT > ${HOME}/.aws/credentials
[main-${ACCOUNT}]
aws_access_key_id=${AWS_ACCESS_KEY_ID}
aws_secret_access_key=${AWS_SECRET_ACCESS_KEY}
aws_session_token=${AWS_SESSION_TOKEN}
EOT
        cat <<EOT > ${HOME}/.aws/config
[profile main-${ACCOUNT}]
region=${REGION}
output=json

[profile main-${ACCOUNT}-assumerole]
source_profile=main-${ACCOUNT}
role_arn=${ROLE_ARN}
EOT

    fi
}

function platform_provisioner_verify_access() {

    cd ${HOME}/platform-provisioner
    echo "########## Verify AWS Account Access ##########"
    export PIPELINE_INPUT_RECIPE="docs/recipes/tests/test-aws.yaml"
    ./dev/platform-provisioner.sh 

}

function platform_provisioner_create() {

    cd ${HOME}/platform-provisioner
    echo "########## Create EKS Cluster With Dataplane Components ##########"
    # Note: Do not use envsubst because that would replace the rest of the ${...} references which we do not want. We want a more targeted replacement only in the "globalEnvVariable:" section.
    export PIPELINE_INPUT_RECIPE="docs/recipes/k8s/cloud/deploy-tp-eks_with_values.yaml"
    cp docs/recipes/k8s/cloud/deploy-tp-eks.yaml ${PIPELINE_INPUT_RECIPE}

    if [[ "${PIPELINE_LOG_DEBUG}" != "" ]]; then yq eval -i '.meta.globalEnvVariable.PIPELINE_LOG_DEBUG = env(PIPELINE_LOG_DEBUG)' ${PIPELINE_INPUT_RECIPE} ; fi
    if [[ "${TP_CLUSTER_NAME}" != "" ]]; then yq eval -i '.meta.globalEnvVariable.TP_CLUSTER_NAME = env(TP_CLUSTER_NAME)' ${PIPELINE_INPUT_RECIPE} ; fi
    if [[ "${TP_DOMAIN}" != "" ]]; then yq eval -i '.meta.globalEnvVariable.TP_DOMAIN = env(TP_DOMAIN)' ${PIPELINE_INPUT_RECIPE} ; fi
    if [[ "${TP_CLUSTER_REGION}" != "" ]]; then yq eval -i '.meta.globalEnvVariable.TP_CLUSTER_REGION = env(REGION)' ${PIPELINE_INPUT_RECIPE} ; fi
    if [[ "${TP_INSTALL_K8S}" != "" ]]; then yq eval -i '.meta.globalEnvVariable.TP_INSTALL_K8S = env(TP_INSTALL_K8S)' ${PIPELINE_INPUT_RECIPE} ; fi
    if [[ "${TP_INSTALL_EFS}" != "" ]]; then yq eval -i '.meta.globalEnvVariable.TP_INSTALL_EFS = env(TP_INSTALL_EFS)' ${PIPELINE_INPUT_RECIPE} ; fi
    if [[ "${TP_INSTALL_POSTGRES}" != "" ]]; then yq eval -i '.meta.globalEnvVariable.TP_INSTALL_POSTGRES = env(TP_INSTALL_POSTGRES)' ${PIPELINE_INPUT_RECIPE} ; fi
    if [[ "${TP_INSTALL_O11Y}" != "" ]]; then yq eval -i '.meta.globalEnvVariable.TP_INSTALL_O11Y = env(TP_INSTALL_O11Y)' ${PIPELINE_INPUT_RECIPE} ; fi
    if [[ "${PIPELINE_AWS_MANAGED_ACCOUNT_ROLE}" != "" ]]; then yq eval -i '.meta.globalEnvVariable.PIPELINE_AWS_MANAGED_ACCOUNT_ROLE = env(PIPELINE_AWS_MANAGED_ACCOUNT_ROLE)' ${PIPELINE_INPUT_RECIPE} ; fi
    if [[ "${PIPELINE_INITIAL_ASSUME_ROLE}" != "" ]]; then yq eval -i '.meta.globalEnvVariable.PIPELINE_INITIAL_ASSUME_ROLE = env(PIPELINE_INITIAL_ASSUME_ROLE)' ${PIPELINE_INPUT_RECIPE} ; fi
    if [[ "${PIPELINE_USE_LOCAL_CREDS}" != "" ]]; then yq eval -i '.meta.globalEnvVariable.PIPELINE_USE_LOCAL_CREDS = env(PIPELINE_USE_LOCAL_CREDS)' ${PIPELINE_INPUT_RECIPE} ; fi

    ./dev/platform-provisioner.sh

}

function platform_provisioner_teardown() {

    cd ${HOME}/platform-provisioner
    echo "########## Tear Down EKS Cluster With Dataplane Components ##########"
    #export AWS_PROFILE="main-${ACCOUNT}-assumerole"
    source ${HOME}/setenv.sh        
    #aws eks update-kubeconfig --region ${REGION} --name ${GUI_TP_CLUSTER_NAME} --kubeconfig "${HOME}/${GUI_TP_CLUSTER_NAME}.yml" --role-arn "${ROLE_ARN}"
    #export KUBECONFIG=${HOME}/${GUI_TP_CLUSTER_NAME}.yml
    cd ${HOME}/platform-provisioner
    #export TP_CLUSTER_NAME=${GUI_TP_CLUSTER_NAME}
    ./docs/recipes/k8s/cloud/scripts/eks/clean-up-tp-eks.sh

}

function platform_provisioner_cleanup() {

    echo "########## Cleanup AWS Components ##########"
    source ${HOME}/setenv.sh

    echo "Searching remnant EFS file systems..."
    while FILE_SYSTEM_ID=$(aws efs describe-file-systems --query "FileSystems[?Tags[?(Value=='${TP_CLUSTER_NAME}')]].FileSystemI | [0]" --output text)
    do
        if [[ "${FILE_SYSTEM_ID}" == "None" ]]; then echo "No more file system found..."; break; fi
        echo "File system ${FILE_SYSTEM_ID}"
        echo "Deleting associated mount targets..."
        while MOUNT_TARGET_ID=$(aws efs describe-mount-targets --file-system-id ${FILE_SYSTEM_ID} --query 'MountTargets[*].MountTargetId | [0]' --output text)
        do
            if [[ "${MOUNT_TARGET_ID}" == "None" ]]; then echo "No more mount target found..."; break; fi    
            echo "Deleting mount target ${MOUNT_TARGET_ID}"
            aws efs delete-mount-target --mount-target-id ${MOUNT_TARGET_ID}
            sleep ${SLEEP_BETWEEN_TASK_SEC}
        done
        echo "Deleting file system ${FILE_SYSTEM_ID}"
        aws efs delete-file-system --file-system-id ${FILE_SYSTEM_ID}
        sleep ${SLEEP_BETWEEN_TASK_SEC}
    done

    echo "Searching remnant VPC..."
    while VPC_ID=$(aws ec2 describe-vpcs --query "Vpcs[?Tags[?Value=='${TP_CLUSTER_NAME}']].VpcId | [0]" --output text)
    do
        if [[ "${VPC_ID}" == "None" ]]; then echo "No more VPC found..."; break; fi
        echo "VPC ${VPC_ID}"
      
        echo "Deleting associated load balancers..."
        while LB_ARN=$(aws elbv2 describe-load-balancers --query "LoadBalancers[?VpcId=='${VPC_ID}'].LoadBalancerArn | [0]" --output text)
        do
            if [[ "${LB_ARN}" == "None" ]]; then echo "No more load balancer found..."; break; fi    
            echo "Deleting load balancer ${LB_ARN}"
            aws elbv2 delete-load-balancer --load-balancer-arn ${LB_ARN}
            sleep ${SLEEP_BETWEEN_TASK_SEC}
        done

        echo "Deleting associated target groups..."
        while TARGET_GROUP_ARN=$(aws elbv2 describe-target-groups --query "TargetGroups[?VpcId=='${VPC_ID}'].TargetGroupArn | [0]" --output text)
        do
            if [[ "${TARGET_GROUP_ARN}" == "None" ]]; then echo "No more target groups found..."; break; fi    
            echo "Deleting target groups ${TARGET_GROUP_ARN}"
            aws elbv2 delete-target-group --target-group-arn ${TARGET_GROUP_ARN}
            sleep ${SLEEP_BETWEEN_TASK_SEC}
        done

        echo "Deleting associated internet gateways..."
        echo "Note: If you encounter the error '(DependencyViolation) when calling the DetachInternetGateway operation: ... has some mapped public address(es). Please unmap those public address(es) before detaching the gateway.', just let this run and it will eventually detach the internet gateway because it takes time for the public address(es) to be released from deleting the load balancer."
        while INTERNET_GATEWAY_ID=$(aws ec2 describe-internet-gateways --query "InternetGateways[?Attachments[?VpcId=='${VPC_ID}']].InternetGatewayId | [0]" --output text)
        do
            if [[ "${INTERNET_GATEWAY_ID}" == "None" ]]; then echo "No more internet gateway found..."; break; fi  
            echo "Detaching and deleting internet gateway ${INTERNET_GATEWAY_ID}"
            aws ec2 detach-internet-gateway --internet-gateway-id ${INTERNET_GATEWAY_ID} --vpc-id ${VPC_ID}
            sleep ${SLEEP_BETWEEN_TASK_SEC}
            aws ec2 delete-internet-gateway --internet-gateway-id ${INTERNET_GATEWAY_ID}
            sleep ${SLEEP_BETWEEN_TASK_SEC}
        done        
        
        echo "Deleting associated security groups..."
        while SECURITY_GROUP_ID=$(aws ec2 describe-security-groups --query "SecurityGroups[?(VpcId=='${VPC_ID}' && GroupName!='default')].GroupId | [0]" --output text)
        do
            if [[ "${SECURITY_GROUP_ID}" == "None" ]]; then echo "No more security group found..."; break; fi  
            echo "Deleting security group ${SECURITY_GROUP_ID}"
            aws ec2 delete-security-group --group-id ${SECURITY_GROUP_ID}
            sleep ${SLEEP_BETWEEN_TASK_SEC}
        done
        
        echo "Deleting associated subnets..."
        while SUBNET_ID=$(aws ec2 describe-subnets --query "Subnets[?VpcId=='${VPC_ID}'].SubnetId | [0]" --output text)
        do
            if [[ "${SUBNET_ID}" == "None" ]]; then echo "No more subnet found..."; break; fi  
            echo "Deleting subnet ${SUBNET_ID}"
            aws ec2 delete-subnet --subnet-id ${SUBNET_ID}
            sleep ${SLEEP_BETWEEN_TASK_SEC}
        done
        
        echo "Deleting VPC ${VPC_ID}"
        aws ec2 delete-vpc --vpc-id ${VPC_ID}
        sleep ${SLEEP_BETWEEN_TASK_SEC}
    done

    echo "Searching remnant volume..."
    while VOLUME_ID=$(aws ec2 describe-volumes --query "Volumes[?Tags[?Value=='${TP_CLUSTER_NAME}']].VolumeId | [0]" --output text)
    do
            if [[ "${VOLUME_ID}" == "None" ]]; then echo "No more volume found..."; break; fi  
            echo "Deleting volume ${VOLUME_ID}"
            aws ec2 delete-volume --volume-id ${VOLUME_ID}
            sleep ${SLEEP_BETWEEN_TASK_SEC}
    done

}

main "$@"; exit
