resource "kubectl_manifest" "kluster_issuer" {
  yaml_body = <<YAML
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-dns
  namespace: cert-manager
spec:
  acme:
    email: "${var.letsencrypt_email}"
    server: https://acme-v02.api.letsencrypt.org/directory
    privateKeySecretRef:
      name: letsencrypt-dns-private-key
    solvers:
      - dns01:
          route53:
            region: ${var.aws_region}
            accessKeyIDSecretRef:
              name: route53-credentials-secret
              key: AWS_ACCESS_KEY_ID
            secretAccessKeySecretRef:
              name: route53-credentials-secret
              key: AWS_SECRET_ACCESS_KEY
YAML

  depends_on = [
    helm_release.cert_manager,
    kubernetes_secret.route53
  ]
}

resource "kubernetes_secret" "route53" {
  metadata {
    name      = "route53-credentials-secret"
    namespace = "cert-manager"
  }

  data = {
    AWS_ACCESS_KEY_ID     = var.aws_access_key_id
    AWS_SECRET_ACCESS_KEY = var.aws_secret_access_key
  }

  type = "Opaque"

  depends_on = [helm_release.cert_manager]
}

resource "helm_release" "cert_manager" {
  name             = "cert-manager"
  namespace        = "cert-manager"
  create_namespace = true

  repository = "https://charts.jetstack.io"
  chart      = "cert-manager"
  version    = "1.17.2"

  values = [
    <<-EOF
      installCRDs: true
    EOF
  ]
}