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
  commonName: argocd.${var.domain}
  dnsNames:
    - argocd.${var.domain}
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

resource "helm_release" "argocd" {
  name             = "argo-cd"
  namespace        = "argocd"
  create_namespace = true
  repository       = "https://argoproj.github.io/argo-helm"
  chart            = "argo-cd"
  version          = "8.0.3"

  values = [
    <<-EOF
      global:
        domain: argocd.${var.domain}
      crds:
        keep: false
    EOF
  ]
}

resource "kubernetes_secret" "argocd_github" {
  metadata {
    name      = "argocd-github-secret"
    namespace = "argocd"
    labels = {
      "argocd.argoproj.io/secret-type" = "repository"
    }
  }

  data = {
    type          = "git"
    url           = var.argocd_github_url
    username      = var.argocd_github_username
    password      = var.argocd_github_token
  }

  depends_on = [
    helm_release.argocd
  ]
}

resource "kubectl_manifest" "argocd_app" {
  yaml_body = <<YAML
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: app-of-apps
  namespace: argocd
spec:
  project: default
  source:
    repoURL: ${var.argocd_github_url}
    targetRevision: main
    path: apps
  destination:
    server: https://kubernetes.default.svc
    namespace: default
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
YAML

  depends_on = [
    helm_release.argocd,
    kubernetes_secret.argocd_github
  ]
}
