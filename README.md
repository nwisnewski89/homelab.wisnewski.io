# Homelab Set Up

- 3 Raspberry Pi 4 8GB Running Ubuntu Server 24.04.2 64-bit LTS


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
    MY_MACBOOK_IP=""
```
3. Run ansible playbook:
```
cd ansible
    ansible-playbook -i inventory main.yml
```
4. Deploy ArgoCD, Cert-Manager, Nginx Ingress
```
cd terraform/kluster-resources
    terraform init
    terraform plan
    terraform apply --auto-approve
```
5. SCP k3 config.
6. Create ClusterIssuer, ArgoCD Ingress and Cert, Metallb IPPool
```
kubectl apply -f apps/argocd/
kubectl apply -f apps/dns/
kubectl apply -f apps/metallb/
```


