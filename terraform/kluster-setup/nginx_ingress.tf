# Pin ingress controller to single node.
# Servicelb will bind host port 80 and 443 to the ingress controller.
resource "helm_release" "nginx_ingress" {
  name             = "ingress-nginx"
  namespace        = "ingress-nginx"
  create_namespace = true

  repository = "https://kubernetes.github.io/ingress-nginx"
  chart      = "ingress-nginx"
  version    = "4.12.0"

  values = [
    <<-EOF
      controller:
        nodeSelector:
          nginx-ingress: "yes"
    EOF
  ]
}

