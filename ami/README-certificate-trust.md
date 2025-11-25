# Certificate Trust in RHEL AMI Builds

## Overview

This Packer configuration builds a new RHEL AMI from a base AMI that already has custom certificates installed. The configuration ensures that certificates from the base AMI are properly trusted in the new AMI.

## How Certificate Trust Works in RHEL

RHEL uses the `ca-trust` system to manage certificate trust:

1. **Certificate Storage Locations:**
   - `/etc/pki/ca-trust/source/anchors/` - PEM format certificates (`.crt`, `.pem`)
   - `/etc/pki/ca-trust/source/` - Other certificate formats

2. **Trust Store Update:**
   - When certificates are added to the source directories, you must run `update-ca-trust extract`
   - This command updates `/etc/pki/ca-trust/extracted/` with the trusted certificates
   - Applications then use the extracted trust store

3. **Base AMI Requirements:**
   - Your base RHEL AMI should have custom certificates in `/etc/pki/ca-trust/source/anchors/`
   - The base AMI should have run `update-ca-trust extract` to initialize the trust store

## What This Configuration Does

### 1. Pre-Provisioning (Shell Script)
- **Verifies certificates exist** from the base AMI
- **Lists certificates** in the anchors directory
- **Runs `update-ca-trust extract`** to refresh the trust store
- **Displays trusted certificates** for verification

### 2. Ansible Provisioning
- **Verifies and refreshes certificates** at the start of the playbook
- **Runs `update-ca-trust extract`** again after system updates
- **Performs final refresh** at the end of provisioning

### 3. Post-Provisioning (Cleanup)
- **Final `update-ca-trust extract`** before creating the AMI
- Ensures the trust store is up-to-date in the final image

## Why Multiple `update-ca-trust extract` Calls?

1. **After system updates** - Package updates might affect certificate stores
2. **After any changes** - Ensures trust store reflects current state
3. **Before AMI creation** - Guarantees the final image has the latest trust store

## Certificate Persistence

Certificates from the base AMI are preserved because:
- They're stored in `/etc/pki/ca-trust/source/anchors/` (persistent location)
- The trust store is refreshed during provisioning
- No cleanup steps remove certificate files

## Verifying Certificates in the New AMI

After building, you can verify certificates in instances launched from the new AMI:

```bash
# List certificates in anchors directory
ls -la /etc/pki/ca-trust/source/anchors/

# View trusted certificates
trust list | grep -i "your-cert-name"

# Test certificate trust (example)
openssl s_client -connect your-server:443 -showcerts
```

## Troubleshooting

### Certificates Not Trusted

If certificates aren't trusted in the new AMI:

1. **Check base AMI:**
   ```bash
   # On the base AMI instance
   ls -la /etc/pki/ca-trust/source/anchors/
   update-ca-trust extract
   trust list | grep "your-cert"
   ```

2. **Verify in new AMI:**
   ```bash
   # On instance launched from new AMI
   ls -la /etc/pki/ca-trust/source/anchors/
   update-ca-trust extract
   trust list
   ```

3. **Check Packer logs:**
   - Look for "Verifying custom certificates" output
   - Verify "update-ca-trust extract" ran successfully

### Missing Certificates

If certificates are missing:

1. **Verify base AMI has certificates** before building
2. **Check that certificates are in the correct location** (`/etc/pki/ca-trust/source/anchors/`)
3. **Ensure base AMI ran `update-ca-trust extract`** at least once

## Best Practices

1. **Base AMI Preparation:**
   - Place certificates in `/etc/pki/ca-trust/source/anchors/`
   - Run `update-ca-trust extract` in the base AMI
   - Test certificate trust before creating the base AMI

2. **Packer Build:**
   - Always specify the correct `source_ami_id`
   - Review Packer logs for certificate verification messages
   - Test the new AMI after building

3. **Certificate Management:**
   - Use descriptive filenames for certificates
   - Document which certificates are included
   - Keep certificates up-to-date in the base AMI

## Example: Adding Certificates to Base AMI

If you need to add certificates to your base AMI:

```bash
# Copy certificate to anchors directory
sudo cp your-certificate.crt /etc/pki/ca-trust/source/anchors/

# Update trust store
sudo update-ca-trust extract

# Verify
trust list | grep "your-certificate"
```

Then create the base AMI with these certificates included.

