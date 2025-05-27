resource "kubernetes_namespace" "pihole" {
  metadata {
    name = "pihole"
  }
}

resource "kubernetes_secret" "pihole_ip" {
  metadata {
    name      = "pihole-secrets"
    namespace = "pihole"
  }

  data = {
    PIHOLE_IP         = var.pihole_ip
    PIHOLE_PASSWORD   = var.pihole_password
  }

  type = "Opaque"

  depends_on = [kubernetes_namespace.pihole]
}
