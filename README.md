# Homelab Set Up

- K3 cluster running on 3 Raspberry Pi 4 Running Ubuntu Server 24.04.2 64-bit LTS.
- ArgoCD for managing applications [argocd.wisnewski.io](https://github.com/nwisnewski89/argocd.wisnewski.io). 
- Vault for secrets management.
- Nginx for ingress.
- Cert-Manager for TLS certificates.

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
6. Deploy argocd with vault plugin using the [kustomzie-app](https://argocd-vault-plugin.readthedocs.io/en/stable/installation/) installed to default namespace:
```
cd argocd-install
    ./argocd_install
```
7. Deploy Cert-Manager, Nginx Ingress, Vault:
```
cd terraform/kluster-resources
    terraform init
    terraform plan
    terraform apply --auto-approve
```
8. Deploy Vault Config, terraform creates the app role, and k8s secret utilized by argocd vault plugin:
```
cd terraform/vault-config
    terraform init
    terraform plan
    terraform apply --auto-approve
```
9. Restart argocd repo server `kubectl rollout restart deployment argocd-repo-server`.