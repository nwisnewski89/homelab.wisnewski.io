locals {
  pool_name = "kluster-ip-pool"
}

resource "kubectl_manifest" "metallb_ip_pool" {
  yaml_body = <<YAML
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata:
  name: ${local.pool_name}
  namespace: metallb-system
spec:
  addresses:
  - ${var.metallb_ip_pool}
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
  name: ${local.pool_name}
  namespace: metallb-system
spec:
  ipAddressPools:
    - kluster-ip-pool
  nodeSelectors:
    - matchLabels:
        ingress-nginx: "yes"
YAML

  depends_on = [
    helm_release.metallb,
    kubectl_manifest.metallb_ip_pool
  ]
} 