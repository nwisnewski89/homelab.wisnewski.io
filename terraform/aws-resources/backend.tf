terraform {
  backend "gcs" {
    bucket = "nick-wisnewski-io-terraform-state"
    prefix = "k3-etcd-backups"
  }
}