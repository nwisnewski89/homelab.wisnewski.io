resource "kubectl_manifest" "argocd_cert" {
  yaml_body = <<YAML
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: argocdcd-tls
  namespace: argocd
spec:
  secretName: argocd-tls
  issuerRef:
    name: letsencrypt-dns
    kind: ClusterIssuer
  commonName: ${var.argocd_domain}
  dnsNames:
    - ${var.argocd_domain}
YAML

  depends_on = [
    helm_release.cert_manager,
    helm_release.argocd,
    kubectl_manifest.kluster_issuer
  ]
}

resource "kubectl_manifest" "argocd_ingress" {
  yaml_body = <<YAML
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: argo-cd-argocd-server
  namespace: argocd
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-dns"
    nginx.ingress.kubernetes.io/backend-protocol: "HTTPS"
    nginx.ingress.kubernetes.io/ssl-passthrough: "true"
    nginx.ingress.kubernetes.io/force-ssl-redirect: "true"
spec:
  tls:
  - hosts:
    - ${var.argocd_domain}
    secretName: argocd-tls
  ingressClassName: nginx
  rules:
  - host: ${var.argocd_domain}
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: argo-cd-argocd-server
            port:
              number: 443
YAML

  depends_on = [
    helm_release.nginx_ingress,
    helm_release.argocd,
    kubectl_manifest.argocd_cert
  ]
}