resource "vault_auth_backend" "kubernetes" {
  type = "kubernetes"
}

data "kubernetes_secret_v1" "vault_sa" {
  metadata {
    name      = "vault-auth"
    namespace = "vault"
  }
}

resource "vault_kubernetes_auth_backend_config" "config" {
  backend            = vault_auth_backend.kubernetes.path
  kubernetes_host    = "https://${var.kubernetes_host}:443"
  kubernetes_ca_cert = data.kubernetes_secret_v1.vault_sa.data["ca.crt"]
  token_reviewer_jwt = data.kubernetes_secret_v1.vault_sa.data["token"]
}

resource "vault_mount" "secrets_engine" {
  path        = "secrets"
  type        = "kv"
  options     = { version = "2" }
}

resource "vault_policy" "argocd" {
  name = "argocd"

  policy = <<EOT
path "secrets/*" {
  capabilities = ["read", "list"]
}
EOT
}

resource "vault_kubernetes_auth_backend_role" "argocd" {
  backend                          = vault_auth_backend.kubernetes.path
  role_name                       = "argocd-plugin"
  bound_service_account_names     = ["argocd-repo-server"]
  bound_service_account_namespaces = ["argocd"]
  token_ttl                       = 3600
  token_policies                  = [vault_policy.argocd.name]
}