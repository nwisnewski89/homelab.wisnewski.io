resource "kubernetes_namespace" "pihole" {
  metadata {
    name = "pihole"
  }
}

resource "random_password" "pihole_password" {
  length  = 16
  special = true
}


resource "kubernetes_secret" "pihole_password" {
  metadata {
    name      = "pihole-password"
    namespace = "pihole"
  }

  data = {
    PASSWORD   = random_password.pihole_password.result
  }

  type = "Opaque"

  depends_on = [kubernetes_namespace.pihole]
}
