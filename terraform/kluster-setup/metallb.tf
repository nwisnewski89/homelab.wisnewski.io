locals {
  ingress_pool = "ingress-ip-pool"
  pihole_pool = "pihole-ip-pool"
}

resource "kubectl_manifest" "metallb_ip_pool" {
  yaml_body = <<YAML
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata:
  name: ${local.ingress_pool}
  namespace: metallb-system
spec:
  addresses:
  - ${var.ingress_ip_pool}
YAML

  depends_on = [
    helm_release.metallb
  ]
}

resource "kubectl_manifest" "metallb_l2_advertisement" {
  yaml_body = <<YAML
apiVersion: metallb.io/v1beta1
kind: L2Advertisement
metadata:
  name: ${local.ingress_pool}
  namespace: metallb-system
spec:
  ipAddressPools:
    - ${local.ingress_pool}
  nodeSelectors:
    - matchLabels:
        nginx-ingress: "yes"
YAML

  depends_on = [
    helm_release.metallb,
    kubectl_manifest.metallb_ip_pool
  ]
}

resource "kubectl_manifest" "pihole" {
  yaml_body = <<YAML
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata:
  name: ${local.pihole_pool}
  namespace: metallb-system
spec:
  addresses:
  - ${var.pihole_ip_pool}
YAML  

  depends_on = [
    helm_release.metallb,
    kubectl_manifest.metallb_ip_pool
  ]
}

resource "kubectl_manifest" "pihole_l2_advertisement" {
  yaml_body = <<YAML
apiVersion: metallb.io/v1beta1
kind: L2Advertisement
metadata:
  name: ${local.pihole_pool}
  namespace: metallb-system
spec:
  ipAddressPools:
    - ${local.pihole_pool}
  nodeSelectors:
    - matchLabels:
        pihole: "yes"
YAML

  depends_on = [
    helm_release.metallb,
    kubectl_manifest.metallb_ip_pool
  ]
}