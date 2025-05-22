
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