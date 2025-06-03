resource "vault_kv_secret_v2" "pihole_password" {
  name = "pihole/password"
  options = { version = "2" }
  mount = vault_mount.secrets_engine.path
  data_json = jsonencode({
    content = var.pihole_password
  })
}

resource "vault_kv_secret_v2" "pihole_dnsmasq" {
  name = "pihole/dnsmasq/02-custom.conf"
  options = { version = "2" }
  mount = vault_mount.secrets_engine.path
  data_json = jsonencode({
    content = <<-EOF
      address=/pihole.${var.domain}/${var.ingress_ip}
      address=/argocd.${var.domain}/${var.ingress_ip}
      address=/vault.${var.domain}/${var.ingress_ip}
    EOF
  })
}

resource "vault_kv_secret_v2" "pihole_dnsmasq_02" {
  name = "pihole/dnsmasq/01-pihole.conf"
  options = { version = "2" }
  mount = vault_mount.secrets_engine.path
  data_json = jsonencode({
    content = <<-EOF
        bind-interfaces
        except-interface=nonexist
        local-service=no
        interface=* 
        local-network=${var.network_cidr}
        local-network=10.0.0.0/8
        local-network=${var.network_cidr_ipv6}
        local-network=${var.network_cidr_ipv6_v2}
    EOF
  })
}