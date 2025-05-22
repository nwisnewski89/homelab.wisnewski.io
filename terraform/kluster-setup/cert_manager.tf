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