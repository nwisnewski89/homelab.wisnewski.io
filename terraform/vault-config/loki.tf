resource "vault_kv_secret_v2" "loki" {
  name      = "monitoring/loki"
  options   = { version = "2" }
  mount     = vault_mount.secrets_engine.path
  data_json = jsonencode({ for k, v in var.loki_credentials : k => base64encode(v) })
}