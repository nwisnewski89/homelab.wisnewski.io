terraform {
  backend "gcs" {
    bucket = "nick-wisnewski-io-terraform-state"
    prefix = "vault-config"
  }
}