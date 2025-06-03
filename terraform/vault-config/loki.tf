resource "vault_kv_secret_v2" "loki" {
  name = "monitoring/loki"
  options = { version = "2" }
  mount = vault_mount.secrets_engine.path
  data_json = jsonencode(var.loki_credentials)
}