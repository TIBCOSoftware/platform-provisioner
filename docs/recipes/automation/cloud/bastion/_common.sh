#!/bin/bash
#
# © 2019 - 2024 Cloud Software Group, Inc.
# All Rights Reserved. Confidential & Proprietary.
#

export SLEEP_BETWEEN_TASK_SEC=5

function common::install_prereq() {

    if [ ! -x "$(command -v docker)" ] ; then
        echo "########## Installing Docker ##########"
        if [ "${SP_UBUNTU}" == true ]; then
            sudo NEEDRESTART_MODE=a apt-get -y update
            sudo NEEDRESTART_MODE=a apt-get -y upgrade
            sudo NEEDRESTART_MODE=a apt-get -y remove docker
            sudo NEEDRESTART_MODE=a apt-get -y remove docker-engine
            sudo NEEDRESTART_MODE=a apt-get -y remove docker.io
            sudo NEEDRESTART_MODE=a apt-get -y remove containerd
            sudo NEEDRESTART_MODE=a apt-get -y remove runc
            sudo NEEDRESTART_MODE=a apt-get -y install ca-certificates 
            sudo NEEDRESTART_MODE=a apt-get -y install curl
            sudo NEEDRESTART_MODE=a apt-get -y install gnupg
            sudo NEEDRESTART_MODE=a apt-get -y install lsb-release
            sudo mkdir -p /etc/apt/keyrings
            curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
            echo \
              "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
              $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
            sudo NEEDRESTART_MODE=a apt-get -y update
            sudo NEEDRESTART_MODE=a apt-get -y upgrade
            sudo NEEDRESTART_MODE=a apt-get -y install docker-ce 
            sudo NEEDRESTART_MODE=a apt-get -y install docker-ce-cli 
            sudo NEEDRESTART_MODE=a apt-get -y install containerd.io 
            sudo NEEDRESTART_MODE=a apt-get -y install docker-compose-plugin
        fi
        if [ "${SP_AMZN}" == true ]; then
            sudo yum -y install docker
            sudo systemctl enable docker
            sudo systemctl start docker
        fi

        echo "########## Add user to docker group ##########"
        sudo usermod -aG docker $USER
        # Note: Do not use "newgrp docker" method. This way will bump into a new child bash session and break the current bash execution. Better to reboot. 

        sleep ${SLEEP_BETWEEN_TASK_SEC}

        sudo reboot now

        echo "Please note that it might take a couple minutes before the system reboot..."
        
        exit 0
    fi

    snap --version &> /dev/null
    RESULT=$?
    if [ "${RESULT}" -ne 0 ]; then
        echo "########## Installing snap (needed to install yq later) ##########"
        if [ "${SP_UBUNTU}" == true ]; then
            sudo apt-get -y update
            sudo apt -y install snapd
        fi
        if [ "${SP_RHEL}" == true ]; then
            sudo dnf -y install https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm
            sudo dnf -y upgrade
            sudo yum -y install snapd
            sudo systemctl enable --now snapd.socket
            sudo ln -s /var/lib/snapd/snap /snap
        fi
        sleep ${SLEEP_BETWEEN_TASK_SEC} # This should prevent "error: too early for operation, device not yet seeded or device model not acknowledged" when using snap next
        snap --version
    fi

    unzip &> /dev/null
    RESULT=$?
    if [ "${RESULT}" -ne 0 ]; then
        echo "########## Installing unzip ##########"
        if [ "${SP_RHEL}" == true ] || [ "${SP_AMZN}" == true ]; then
            sudo yum -y install unzip
        fi
        if [ "${SP_UBUNTU}" == true ]; then
            sudo apt install -y unzip
        fi
        sleep ${SLEEP_BETWEEN_TASK_SEC}
    fi

    kubectl version --client=true &> /dev/null
    RESULT=$?
    if [ "${RESULT}" -ne 0 ]; then
        echo "########## Install kubectl ##########"
        curl -LO https://storage.googleapis.com/kubernetes-release/release/`curl -s https://storage.googleapis.com/kubernetes-release/release/stable.txt`/bin/linux/amd64/kubectl
        chmod +x kubectl
        sudo mv kubectl /usr/local/bin/
        sleep ${SLEEP_BETWEEN_TASK_SEC}
        kubectl version --client=true
        # Output: 
        # Client Version: v1.29.2
        # Kustomize Version: v5.0.4-0.20230601165947-6ce0bf390ce3
    fi

    helm version &> /dev/null
    RESULT=$?
    if [ "${RESULT}" -ne 0 ]; then
        echo "########## Install Helm ##########"
        if [ "${SP_UBUNTU}" == true ]; then
            curl https://baltocdn.com/helm/signing.asc | gpg --dearmor | sudo tee /usr/share/keyrings/helm.gpg > /dev/null
            sudo apt-get install apt-transport-https --yes
            echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/helm.gpg] https://baltocdn.com/helm/stable/debian/ all main" | sudo tee /etc/apt/sources.list.d/helm-stable-debian.list
            sudo apt-get -y update
            sudo apt-get -y install helm
        fi
        if [ "${SP_RHEL}" == true ] || [ "${SP_AMZN}" == true ]; then    
            curl -sSL https://raw.githubusercontent.com/helm/helm/master/scripts/get-helm-3 | bash
        fi
        sleep ${SLEEP_BETWEEN_TASK_SEC}
        helm version
        # Sample Output:
        # version.BuildInfo{Version:"v3.14.2", GitCommit:"c309b6f0ff63856811846ce18f3bdc93d2b4d54b", GitTreeState:"clean", GoVersion:"go1.21.7"}
    fi

    yq --version &> /dev/null
    RESULT=$?
    if [ "${RESULT}" -ne 0 ]; then
        echo "########## Installing yq ##########"
        if [ "${SP_AMZN}" == true ]; then
            sudo wget -qO /usr/local/bin/yq https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64
            sudo chmod a+x /usr/local/bin/yq
        fi
        if [ "${SP_UBUNTU}" == true ] || [ "${SP_RHEL}" == true ]; then
            sudo snap install yq
        fi
        sleep ${SLEEP_BETWEEN_TASK_SEC}    
        yq --version
    fi

    git --version &> /dev/null
    RESULT=$?
    if [ "${RESULT}" -ne 0 ]; then
        echo "########## Installing Git ##########"
        if [ "${SP_AMZN}" == true ]; then
            sudo yum -y install git
        fi
        sleep ${SLEEP_BETWEEN_TASK_SEC}
        git --version
        # Sample Output: git version 2.43.0
    fi

    if [ -d "${HOME}/platform-provisioner" ] && [ "$(ls -A ${HOME}/platform-provisioner)" ]; then
        echo "Platform Provisioner files found. Not cloning from github."
    else
        echo "########## Clone Platform Provisioner ##########"
        git clone https://github.com/TIBCOSoftware/platform-provisioner ${HOME}/platform-provisioner
    fi

}