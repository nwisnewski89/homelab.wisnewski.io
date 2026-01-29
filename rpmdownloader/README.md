# Aurora Cross-Account Environment Refresh

Python script to propagate data from a production Aurora MySQL cluster to dev/staging environments across AWS accounts.

## Features

- **Cross-account snapshot sharing** with KMS re-encryption
- **Full cluster refresh** - Restores entire cluster with all databases
- **Environment-specific configuration** - Parameter groups, KMS keys, monitoring
- **Credential reset** - Automatically resets MySQL user passwords from Secrets Manager
- **DNS update** - Updates Route 53 CNAME to point to new cluster endpoint
- **Cleanup automation** - Optionally deletes old cluster after successful refresh

## Prerequisites

### 1. AWS CLI Profiles
Configure named profiles for each account:
```bash
# ~/.aws/credentials
[production]
aws_access_key_id = ...
aws_secret_access_key = ...

[staging]
aws_access_key_id = ...
aws_secret_access_key = ...
```

### 2. IAM Permissions

**Production Account:**
- `rds:CreateDBClusterSnapshot`
- `rds:DescribeDBClusterSnapshots`
- `rds:ModifyDBClusterSnapshotAttribute`

**Target Account (staging/dev):**
- `rds:CopyDBClusterSnapshot`
- `rds:RestoreDBClusterFromSnapshot`
- `rds:CreateDBInstance`
- `rds:ModifyDBCluster`
- `rds:DeleteDBCluster`
- `rds:DeleteDBInstance`
- `rds:DescribeDBClusters`
- `rds:DescribeDBClusterSnapshots`
- `secretsmanager:GetSecretValue`
- `route53:ChangeResourceRecordSets`
- `route53:GetChange`
- `kms:CreateGrant` (for the target KMS key)
- `kms:Decrypt` (for the source KMS key - via cross-account policy)

### 3. KMS Key Setup (CRITICAL for Encrypted Clusters)

**Source KMS Key (Production Account):**

The KMS key encrypting your production cluster must allow the target account to decrypt. Add this to the key policy:

```json
{
  "Sid": "Allow target account to use this key for RDS snapshots",
  "Effect": "Allow",
  "Principal": {
    "AWS": "arn:aws:iam::222222222222:root"
  },
  "Action": [
    "kms:Decrypt",
    "kms:DescribeKey"
  ],
  "Resource": "*",
  "Condition": {
    "StringEquals": {
      "kms:ViaService": "rds.us-east-1.amazonaws.com",
      "kms:CallerAccount": "222222222222"
    }
  }
}
```

**Target KMS Key (Staging/Dev Account):**

Create a KMS key in the target account for re-encrypting the snapshot. The key policy must allow RDS to use it:

```json
{
  "Sid": "Allow RDS to use this key",
  "Effect": "Allow",
  "Principal": {
    "Service": "rds.amazonaws.com"
  },
  "Action": [
    "kms:Encrypt",
    "kms:Decrypt",
    "kms:ReEncrypt*",
    "kms:GenerateDataKey*",
    "kms:CreateGrant",
    "kms:DescribeKey"
  ],
  "Resource": "*"
}
```

### 4. Parameter Groups

Create environment-specific parameter groups before running. These don't transfer with snapshots:

```bash
# Example: Create staging cluster parameter group
aws rds create-db-cluster-parameter-group \
  --db-cluster-parameter-group-name staging-aurora-mysql8-cluster-params \
  --db-parameter-group-family aurora-mysql8.0 \
  --description "Staging cluster parameters"

# Example: Create staging DB parameter group  
aws rds create-db-parameter-group \
  --db-parameter-group-name staging-aurora-mysql8-db-params \
  --db-parameter-group-family aurora-mysql8.0 \
  --description "Staging DB parameters"
```

### 5. Enhanced Monitoring Role (if using monitoring_interval > 0)

Create an IAM role with the `AmazonRDSEnhancedMonitoringRole` managed policy:

```bash
aws iam create-role \
  --role-name rds-monitoring-role \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "monitoring.rds.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }'

aws iam attach-role-policy \
  --role-name rds-monitoring-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole
```

### 6. Secrets Manager

Set up secrets in target accounts:

**Admin secret** (`staging/aurora/admin`):
```json
{
  "username": "admin",
  "password": "your-admin-password"
}
```

**App credentials secret** (`staging/aurora/app-credentials`):
```json
{
  "app_user_password": "password-for-app-user",
  "readonly_user_password": "password-for-readonly-user",
  "api_user_password": "password-for-api-user"
}
```

## Installation

```bash
pip install -r requirements.txt
```

## Configuration Reference

Edit `config.json` with your values:

```json
{
  "production": {
    "account_id": "111111111111",
    "cluster_identifier": "prod-aurora-cluster",
    "aws_profile": "production"
  },
  "environments": {
    "staging": {
      // Required - Account & Identity
      "account_id": "222222222222",
      "cluster_identifier": "staging-aurora-cluster",
      "aws_profile": "staging",

      // Required - Networking
      "db_subnet_group": "staging-db-subnet-group",
      "security_group_ids": ["sg-staging123"],
      "port": 3306,

      // Required - Compute
      "instance_class": "db.r6g.large",
      "instance_count": 2,

      // Required for Encrypted Clusters - KMS
      "kms_key_id": "arn:aws:kms:us-east-1:222222222222:key/xxx",

      // Recommended - Parameter Groups
      "db_cluster_parameter_group": "staging-aurora-mysql8-cluster-params",
      "db_parameter_group": "staging-aurora-mysql8-db-params",

      // Optional - Backup & Maintenance
      "backup_retention_period": 7,
      "preferred_backup_window": "03:00-04:00",
      "preferred_maintenance_window": "sun:04:00-sun:05:00",
      "deletion_protection": false,

      // Optional - IAM Authentication
      "enable_iam_database_authentication": false,

      // Required - Credentials
      "secrets_admin": "staging/aurora/admin",
      "secrets_app": "staging/aurora/app-credentials",

      // Optional - Monitoring
      "enable_performance_insights": true,
      "performance_insights_retention_period": 7,
      "performance_insights_kms_key_id": "arn:aws:kms:...",
      "monitoring_interval": 60,
      "monitoring_role_arn": "arn:aws:iam::222222222222:role/rds-monitoring-role",

      // Optional - CloudWatch Logs
      "enable_cloudwatch_logs_exports": ["error", "slowquery"],

      // Optional - Serverless v2 (omit for provisioned)
      "serverless_v2_scaling_config": {
        "MinCapacity": 0.5,
        "MaxCapacity": 16
      },

      // Required - DNS
      "hosted_zone_id": "Z1234567890ABC",
      "dns_record_name": "db.staging.example.com"
    }
  }
}
```

## Usage

### Refresh staging environment

```bash
python refresh_aurora_env.py staging
```

### Refresh dev environment

```bash
python refresh_aurora_env.py dev
```

### Options

```bash
# Dry run - show configuration without making changes
python refresh_aurora_env.py staging --dry-run

# Keep old cluster (don't delete after refresh)
python refresh_aurora_env.py staging --no-cleanup

# Create final snapshot before deleting old cluster
python refresh_aurora_env.py staging --keep-final-snapshot

# Use different region
python refresh_aurora_env.py staging --region us-west-2

# Use different config file
python refresh_aurora_env.py staging --config /path/to/config.json
```

## Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                    PRODUCTION ACCOUNT (A)                        │
├─────────────────────────────────────────────────────────────────┤
│  1. Create snapshot of prod cluster                              │
│  2. Share snapshot with target account                           │
│     (ModifyDBClusterSnapshotAttribute)                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    TARGET ACCOUNT (B)                            │
├─────────────────────────────────────────────────────────────────┤
│  3. Copy snapshot (re-encrypts with target KMS key)              │
│  4. Restore cluster from snapshot                                │
│     - Apply parameter groups                                     │
│     - Configure monitoring, logs, etc.                           │
│  5. Create DB instances                                          │
│  6. Reset credentials from Secrets Manager                       │
│  7. Update Route 53 DNS CNAME                                    │
│  8. Delete old cluster (optional)                                │
│  9. Rename new cluster to original name                          │
└─────────────────────────────────────────────────────────────────┘
```

## Key Considerations

### KMS Keys (Most Important!)

| Scenario | Action |
|----------|--------|
| Unencrypted prod cluster | No KMS config needed |
| Encrypted prod, same KMS key for target | Specify `kms_key_id` with same key ARN |
| Encrypted prod, different KMS key for target (recommended) | 1. Update source key policy to allow target account<br>2. Set `kms_key_id` to target account's key |

### Parameter Groups

Parameter groups are **not** copied with snapshots. You should:
1. Create environment-specific parameter groups ahead of time
2. Specify them in config (`db_cluster_parameter_group`, `db_parameter_group`)
3. Otherwise, the default parameter group is used

### Engine Version

The script uses the same engine version as the source snapshot. If you need to upgrade:
1. Upgrade production first, or
2. Modify the cluster after restore

### Network Connectivity for Credential Reset

The script uses `pymysql` to reset credentials. The machine running the script must be able to connect to the Aurora cluster endpoint on port 3306 (or your configured port). Options:
- Run from an EC2 instance in the target VPC
- Use VPN/Direct Connect
- Use a bastion host
- If connectivity isn't available, the script will print SQL statements to run manually

## Logging

Logs are written to both stdout and a timestamped file:
```
aurora_refresh_YYYYMMDD_HHMMSS.log
```

## Troubleshooting

### "KMS key not accessible" during snapshot copy

1. Verify source KMS key policy allows target account
2. Check the `kms:ViaService` condition matches your region
3. Ensure `kms_key_id` in config is a full ARN

### "DBSubnetGroupNotFoundFault"

The subnet group doesn't exist in the target account. Create it:
```bash
aws rds create-db-subnet-group \
  --db-subnet-group-name staging-db-subnet-group \
  --db-subnet-group-description "Staging subnets" \
  --subnet-ids subnet-xxx subnet-yyy
```

### "DBClusterParameterGroupNotFound"

Create the parameter group before running:
```bash
aws rds create-db-cluster-parameter-group \
  --db-cluster-parameter-group-name staging-aurora-mysql8-cluster-params \
  --db-parameter-group-family aurora-mysql8.0 \
  --description "Staging parameters"
```

### Credential reset fails

- Check network connectivity to Aurora endpoint
- Verify admin credentials in Secrets Manager are correct
- Ensure `pymysql` is installed: `pip install pymysql`
- Check security group allows inbound on port 3306

### DNS update fails

- Verify `hosted_zone_id` is correct
- Ensure IAM has `route53:ChangeResourceRecordSets` permission
- Check the DNS record name ends with a period if it's an FQDN
