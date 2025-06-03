resource "kubernetes_namespace" "vault" {
  metadata {
    name = "vault"
  }
}

resource "random_password" "unseal_key" {
  length  = 32
  special = true
}

resource "kubernetes_secret" "vault_unseal" {
  metadata {
    name      = "vault-unseal-key"
    namespace = "vault"
  }

  data = {
    "key" = base64encode(random_password.unseal_key.result)
  }

  depends_on = [
    helm_release.vault
  ]
}

resource "helm_release" "vault" {
  name             = "vault"
  namespace        = "vault"
  create_namespace = false
  repository       = "https://helm.releases.hashicorp.com"
  chart            = "vault"
  version          = "0.30.0"

  values = [
    <<EOF
      server:
        dataStorage:
          enabled: true
          size: 1Gi
          storageClass: ""
          accessMode: ReadWriteOnce
        standalone:
          enabled: true
          config: |
            ui = true
            listener "tcp" {
              tls_disable = 1
              address = "[::]:8200"
              cluster_address = "[::]:8201"
            }
            storage "file" {
              path = "/vault/data"
            }
            seal "kubernetes" {
              secret_name = "vault-unseal-key"
              namespace   = "vault"
            }
        service:
          enabled: true
        ingress:
          enabled: true
          ingressClassName: nginx
          hosts:
            - host: vault.${var.domain}
              paths:
                - /
          tls:
            - secretName: vault-tls
              hosts:
                - vault.${var.domain}
    EOF
  ]

  depends_on = [
    helm_release.nginx_ingress
  ]
}

resource "kubectl_manifest" "vault_cert" {
  yaml_body = <<YAML
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: vault-tls
  namespace: vault
spec:
  secretName: vault-tls
  issuerRef:
    name: letsencrypt-dns
    kind: ClusterIssuer
  commonName: vault.${var.domain}
  dnsNames:
    - vault.${var.domain}
YAML

  depends_on = [
    helm_release.cert_manager,
    helm_release.vault
  ]
}

resource "kubernetes_service_account" "vault_auth" {
  metadata {
    name      = "vault-auth"
    namespace = "vault"
  }
}

resource "kubernetes_cluster_role_binding" "vault_auth_delegator" {
  metadata {
    name = "vault-auth-delegator"
  }

  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "ClusterRole"
    name      = "system:auth-delegator"
  }

  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account.vault_auth.metadata[0].name
    namespace = kubernetes_service_account.vault_auth.metadata[0].namespace
  }
}

resource "kubernetes_secret_v1" "vault_auth" {
  type = "kubernetes.io/service-account-token"

  metadata {
    name      = "vault-auth"
    namespace = "vault"
    annotations = {
      "kubernetes.io/service-account.name" = "vault-auth"
    }
  }
}
