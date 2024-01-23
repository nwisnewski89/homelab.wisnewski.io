# Homelab Set Up
3 Raspberry Pi 4 4GB Running Ubuntu Server 22.04.3 64-bit LTS

![homelab](./images/homelab.png)

## Configure firewall on each server
* `sudo ufw allow from {network_cidr} proto tcp to any port 22`
* `sudo ufw default deny incoming`
* `sudo ufw default allow outgoing`

## Run configure internal domain homelab.wisnewski.io
* `ansible-playbook -i inventory configure-dns-servers.yml`
* `ansible-playbook -i inventory configure-netplan.yml`
    * on each host run:
        * `sudo netplan apply`
        * `sudo resolvectl status`
* Configure router with custom DNS server

## Install MicroK8s Cluster
* 1 API server 2 worker nodes
* `ansible-playbook -i inventory initialize-cluster.yml`
* `ansible-playbook -i inventory cluster-config.yml`
* Copy microk8s config locally 
