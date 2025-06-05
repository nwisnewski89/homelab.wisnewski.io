resource "kubectl_manifest" "argocd_cert" {
  yaml_body = <<YAML
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: argocd-tls
  namespace: argocd
spec:
  secretName: argocd-tls
  issuerRef:
    name: letsencrypt-dns
    kind: ClusterIssuer
  commonName: argocd.${var.domain}
  dnsNames:
    - argocd.${var.domain}
YAML

  depends_on = [
    helm_release.cert_manager,
    kubectl_manifest.kluster_issuer
  ]
}

resource "kubectl_manifest" "argocd_ingress" {
  yaml_body = <<YAML
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: argocd-server
  namespace: argocd
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-dns"
    nginx.ingress.kubernetes.io/backend-protocol: "HTTPS"
    nginx.ingress.kubernetes.io/ssl-passthrough: "true"
    nginx.ingress.kubernetes.io/force-ssl-redirect: "true"
spec:
  tls:
  - hosts:
    - argocd.${var.domain}
    secretName: argocd-tls
  ingressClassName: nginx
  rules:
  - host: argocd.${var.domain}
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: argocd-server
            port:
              number: 443
YAML

  depends_on = [
    helm_release.nginx_ingress,
    kubectl_manifest.argocd_cert
  ]
}
