#!/bin/sh
set -e

VAULT_ADDR="${VAULT_ADDR:-http://vault:8200}"
OUTPUT_DIR="${VAULT_INIT_OUTPUT_DIR:-/vault/init-keys}"
INIT_OUTPUT_FILE="${OUTPUT_DIR}/vault-keys.txt"

echo "Waiting for Vault at ${VAULT_ADDR}..."
while true; do
  out=$(vault status 2>&1) || true
  if echo "$out" | grep -q "Connection refused\|connection refused"; then
    sleep 2
    continue
  fi
  break
done

echo "Checking if Vault is initialized..."
vault status 2>/dev/null || true
status=$?
if [ "$status" -eq 2 ]; then
    echo "Vault is not initialized. Running vault operator init..."
    mkdir -p "${OUTPUT_DIR}"
    vault operator init -key-shares=5 -key-threshold=3 > "${INIT_OUTPUT_FILE}" 2>&1
  echo "Init complete. Keys written to ${INIT_OUTPUT_FILE}"
  echo "SECURITY: Copy these keys to a secure location and remove them from this volume."
else
  echo "Vault is already initialized (exit code ${status})."
fi
