# Homelab Set Up

- K3 cluster running on 3 Raspberry Pi 4 Running Ubuntu Server 24.04.2 64-bit LTS.

1. Deploy AWS DNS and S3 backups:
```
cd terraform/aws-resources
    terraform init
    terraform plan
    terraform apply --auto-approve
```
2. Set ansible environment variables:
```
    AWS_REGION=""
    GHCR_TOKEN=""
    K3S_TOKEN=""
    ETCD_BACKUPS_ACCESS_KEY=""
    ETCD_BACKUPS_SECRET_KEY=""
    ETCD_BACKUPS_BUCKET_NAME=""
    NETWORK_CIDR=""
    NETWORK_CIDR_IPV6=""
```
3. Run ansible setup playbook:
```
cd ansible
    ansible-playbook -i inventory kluster-setup.yml
```
4. SCP k3 config.
5. Run ansible playbook to set node labels:
```
cd ansible
    ansible-playbook -i inventory label-nodes.yml
```
6. Deploy ArgoCD, Cert-Manager, Nginx Ingress
```
cd terraform/kluster-resources
    terraform init
    terraform plan
    terraform apply --auto-approve
```
 

