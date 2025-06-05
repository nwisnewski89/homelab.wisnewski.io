resource "vault_mount" "secrets_engine" {
  path    = "secrets"
  type    = "kv"
  options = { version = "2" }
}

resource "vault_policy" "argocd" {
  name = "argocd"

  policy = <<EOT
path "secrets/*" {
  capabilities = ["read", "list"]
}
EOT
}

resource "vault_auth_backend" "approle" {
  type = "approle"
}

resource "vault_approle_auth_backend_role" "argocd" {
  backend        = vault_auth_backend.approle.path
  role_name      = "argocd"
  bind_secret_id = true
  token_policies = [vault_policy.argocd.name]
}

resource "vault_approle_auth_backend_role_secret_id" "argocd" {
  backend        = vault_auth_backend.approle.path
  role_name      = vault_approle_auth_backend_role.argocd.role_name
}

resource "kubernetes_secret" "argocd_vault_credentials" {
  metadata {
    name      = "argocd-vault-plugin-credentials"
    namespace = "argocd"
  }

  data = {
    VAULT_ADDR    = "http://vault.vault.svc.cluster.local:8200"
    AVP_TYPE      = "vault"
    AVP_AUTH_TYPE = "approle"
    AVP_ROLE_ID   = vault_approle_auth_backend_role.argocd.role_id
    AVP_SECRET_ID = vault_approle_auth_backend_role_secret_id.argocd.secret_id
  }
}