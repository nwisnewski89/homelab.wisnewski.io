resource "vault_kv_secret_v2" "pihole_password" {
  name = "pihole"
  options = { version = "2" }
  mount = vault_mount.secrets_engine.path
  data_json = jsonencode({
    password = base64encode(var.pihole_password)
  })
}

locals {
  pihole_dnsmasq_custom_config = <<-EOF
    address=/pihole.${var.domain}/${var.ingress_ip}
    address=/argocd.${var.domain}/${var.ingress_ip}
    address=/vault.${var.domain}/${var.ingress_ip}
  EOF
  pihole_dnsmasq_base_config = <<-EOF
    bind-interfaces
    except-interface=nonexist
    local-service=no
    interface=* 
    local-network=${var.network_cidr}
    local-network=10.0.0.0/8
    local-network=${var.network_cidr_ipv6}
    local-network=${var.network_cidr_ipv6_v2}
  EOF
}

resource "vault_kv_secret_v2" "pihole_dnsmasq" {
  name = "pihole/dnsmasq"
  options = { version = "2" }
  mount = vault_mount.secrets_engine.path
  data_json = jsonencode({
    "02-custom.conf" = base64encode(local.pihole_dnsmasq_custom_config)
    "01-pihole.conf" = base64encode(local.pihole_dnsmasq_base_config)
  })
}