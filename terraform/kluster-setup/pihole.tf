resource "kubernetes_namespace" "pihole" {
  metadata {
    name = "pihole"
  }
}

resource "kubernetes_secret" "pihole_password" {
  metadata {
    name      = "pihole-password"
    namespace = "pihole"
  }

  data = {
    PASSWORD   = var.pihole_password
  }

  type = "Opaque"

  depends_on = [kubernetes_namespace.pihole]
}

resource "kubernetes_config_map" "pihole_dnsmasq" {
  metadata {
    name      = "pihole-dnsmasq"
    namespace = "pihole"
  }

  data = {
    "02-custom.conf" = <<-EOF
      address=/${var.domain}/${var.pihole_ip}
    EOF
  }

  depends_on = [kubernetes_namespace.pihole]
}
