# Vault server configuration
# - S3 storage backend
# - AWS KMS seal (auto-unseal)

ui = true

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = 1
}

storage "s3" {
  bucket     = "YOUR_VAULT_BUCKET_NAME"
  region     = "us-east-1"
  # Optional: use a custom path prefix inside the bucket
  # path       = "vault/data"
  #
  # Optional: use KMS for server-side encryption of objects (recommended)
  # kms_key_id = "alias/your-s3-kms-key"
  #
  # Optional: disable SSL for local/minio (e.g. MinIO)
  # disable_ssl = true
  # endpoint    = "http://minio:9000"
}

seal "awskms" {
  region     = "us-east-1"
  kms_key_id = "alias/vault-auto-unseal"
  # Or use key ID: kms_key_id = "12345678-1234-1234-1234-123456789012"
}

api_addr     = "http://0.0.0.0:8200"
cluster_addr = "http://0.0.0.0:8201"
disable_mlock = true
