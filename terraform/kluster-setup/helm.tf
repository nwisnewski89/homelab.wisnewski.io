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
        domain: ${var.argocd_domain}
      crds:
        keep: false
    EOF
  ]
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

resource "helm_release" "nginx_ingress" {
  name             = "ingress-nginx"
  namespace        = "ingress-nginx"
  create_namespace = true

  repository = "https://kubernetes.github.io/ingress-nginx"
  chart      = "ingress-nginx"
  version    = "4.12.2"

  values = [
    <<-EOF
      controller:
        nodeSelector:
          nginx-ingress: "yes"
    EOF
  ]

  depends_on = [
    helm_release.metallb,
    kubectl_manifest.metallb_ip_pool,
    kubectl_manifest.metallb_l2_advertisement
  ]
}

resource "helm_release" "metallb" {
  name             = "metallb"
  namespace        = "metallb-system"
  create_namespace = true

  repository = "https://metallb.github.io/metallb"
  chart      = "metallb"
  version    = "0.14.9"
}

