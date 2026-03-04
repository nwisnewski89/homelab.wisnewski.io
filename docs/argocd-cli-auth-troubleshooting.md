# Argo CD CLI auth troubleshooting

If sync works in the **web UI** but you get **unauthorized** with the **CLI** (auth token or username/password), it’s usually RBAC or how the CLI talks to the server.

## 1. RBAC (most common)

The UI uses your **session**; the CLI uses **token or password** and is subject to Argo CD RBAC. If `policy.default` is empty, local accounts can log in but have no role, so API/CLI calls are denied.

**Fix (already in Terraform):** `configs.rbac.policy.default: role:admin` so any local user (including your service account) gets full access. Apply the Terraform change and restart the Argo CD server (or let the Helm release roll the pods).

**Optional – restrict to one account:** In `configs.rbac.policy.csv` grant admin only to that user:

```yaml
configs:
  rbac:
    policy.default: ""   # no default
    policy.csv: |
      g, your-service-account-username, role:admin
```

Then only that account gets full access via CLI/API.

## 2. CLI login and connection

Use the same server URL as the UI and, if you use TLS passthrough or self-signed certs, add `--grpc-web` and `--insecure`:

```bash
# Token (e.g. from Settings → Accounts → Generate new token)
argocd login argocd.${var.domain} \
  --auth-token YOUR_TOKEN \
  --grpc-web \
  --insecure

# Username/password (e.g. admin)
argocd login argocd.${var.domain} \
  --username admin \
  --password YOUR_PASSWORD \
  --grpc-web \
  --insecure
```

- **`--grpc-web`** – required when the server is behind an ingress/proxy (like your nginx TLS passthrough).
- **`--insecure`** – skip TLS verification (only for dev/homelab; use proper certs in production).

Without `--grpc-web`, the CLI may fail or get 401/403 even with a valid token.

## 3. Verify identity after login

```bash
argocd account get-user-info
```

If this works, auth is fine and the problem was RBAC. If it returns unauthorized, the token or URL/connection is wrong.

## 4. Token type

Use a token generated from **Settings → Accounts → [your account] → Generate new token**. The initial admin secret from `argocd-initial-admin-secret` is a **password**, not a JWT; for token auth you must use a token generated in the UI (or API) for that account.

## Summary

1. Set RBAC so the service account has a role (e.g. `policy.default: role:admin` or `policy.csv` with `g, <account>, role:admin`).
2. Use `--grpc-web` and `--insecure` when logging in via CLI to your ingress URL.
3. Use a proper **token** for token auth, not the initial admin password.
