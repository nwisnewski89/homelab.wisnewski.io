# ACM Certificate with Cross-Account Route53 DNS Validation

This solution allows you to create an ACM certificate in one AWS account and automatically add DNS validation records to a Route53 hosted zone in a different account using a custom resource.

## Overview

When you create an ACM certificate with DNS validation, AWS requires you to add specific DNS records to prove domain ownership. Normally, CDK's `CertificateValidation.from_dns()` handles this automatically, but it only works when the certificate and hosted zone are in the same account.

This stack uses a custom resource (Lambda function) to:
1. Create the ACM certificate in Account A
2. Retrieve the DNS validation records from ACM
3. Create those records in the Route53 hosted zone in Account B

## Prerequisites

1. **Route53 Hosted Zone** must exist in the target account (Account B)
2. **Cross-Account IAM Permissions** - Choose one of the following approaches:

### Option 1: Cross-Account IAM Role (Recommended)

Create an IAM role in the target account (Account B) that can be assumed by the Lambda function in Account A.

#### Step 1: Create IAM Role in Target Account (Account B)

**Option A: Using the provided CDK stack (Recommended)**

Deploy the `cross_account_route53_role_stack.py` in Account B:

```python
from aws_cdk import App, Environment
from cross_account_route53_role_stack import CrossAccountRoute53RoleStack

app = App()

CrossAccountRoute53RoleStack(
    app,
    "CrossAccountRoute53RoleStack",
    certificate_account_id="222222222222",  # Account A - where certificate will be created
    hosted_zone_id="Z1234567890ABC",  # Your hosted zone ID
    env=Environment(
        account="111111111111",  # Account B - where hosted zone exists
        region="us-east-1"
    )
)

app.synth()
```

**Option B: Manual CloudFormation/CDK**

Create a CloudFormation/CDK stack or use AWS CLI to create this role:

Trust Policy:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::CERT_ACCOUNT_ID:root"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

Attach this policy to the role:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "route53:ChangeResourceRecordSets",
        "route53:GetChange",
        "route53:ListResourceRecordSets"
      ],
      "Resource": "arn:aws:route53:::hostedzone/YOUR_HOSTED_ZONE_ID"
    }
  ]
}
```

#### Step 2: Use the Role ARN in Your Stack

```python
AcmCrossAccountCertificateStack(
    app,
    "AcmCertificateStack",
    domain_name="example.com",
    subject_alternative_names=["*.example.com"],
    target_hosted_zone_id="Z1234567890ABC",
    cross_account_role_arn="arn:aws:iam::TARGET_ACCOUNT_ID:role/Route53CrossAccountRole",
    env=Environment(account="CERT_ACCOUNT_ID", region="us-east-1")
)
```

### Option 2: Same Credentials with Cross-Account Permissions

If your AWS credentials have cross-account Route53 permissions, you can omit the `cross_account_role_arn` parameter:

```python
AcmCrossAccountCertificateStack(
    app,
    "AcmCertificateStack",
    domain_name="example.com",
    subject_alternative_names=["*.example.com"],
    target_hosted_zone_id="Z1234567890ABC",
    # cross_account_role_arn not provided
    env=Environment(account="CERT_ACCOUNT_ID", region="us-east-1")
)
```

**Note:** This requires your Lambda execution role to have direct Route53 permissions in the target account, which is less secure.

## Usage

### Basic Example

```python
from aws_cdk import App, Environment
from acm_cross_account_stack import AcmCrossAccountCertificateStack

app = App()

stack = AcmCrossAccountCertificateStack(
    app,
    "AcmCertificateStack",
    domain_name="example.com",
    subject_alternative_names=["*.example.com"],
    target_hosted_zone_id="Z1234567890ABC",  # Hosted zone in Account B
    cross_account_role_arn="arn:aws:iam::TARGET_ACCOUNT_ID:role/Route53CrossAccountRole",
    env=Environment(
        account="CERT_ACCOUNT_ID",  # Account A - where certificate is created
        region="us-east-1"
    )
)

app.synth()
```

### With CloudFront (us-east-1 Required)

CloudFront requires certificates to be in `us-east-1`:

```python
stack = AcmCrossAccountCertificateStack(
    app,
    "CloudFrontCertificate",
    domain_name="example.com",
    subject_alternative_names=["*.example.com"],
    target_hosted_zone_id="Z1234567890ABC",
    cross_account_role_arn="arn:aws:iam::TARGET_ACCOUNT_ID:role/Route53CrossAccountRole",
    env=Environment(
        account="CERT_ACCOUNT_ID",
        region="us-east-1"  # Required for CloudFront
    )
)
```

## How It Works

1. **Certificate Creation**: The stack creates an ACM certificate with email validation (as a placeholder).

2. **Custom Resource**: A Lambda function is triggered that:
   - Calls `DescribeCertificate` to get DNS validation records
   - Assumes the cross-account role (if provided) or uses same credentials
   - Creates DNS validation records in the target hosted zone
   - Waits for Route53 changes to propagate

3. **Certificate Validation**: Once DNS records are created, ACM automatically validates the certificate (usually within a few minutes).

## IAM Permissions Required

### In Certificate Account (Account A)

The Lambda execution role needs:
- `acm:DescribeCertificate` on the certificate
- `route53:ChangeResourceRecordSets` on the target hosted zone (or assume role permission)
- `sts:AssumeRole` on the cross-account role (if using Option 1)

### In Target Account (Account B)

The cross-account role (or direct permissions) needs:
- `route53:ChangeResourceRecordSets` on the hosted zone
- `route53:GetChange` on the hosted zone
- `route53:ListResourceRecordSets` on the hosted zone

## Troubleshooting

### Certificate Not Validating

1. **Check DNS Records**: Verify the DNS validation records were created in the target hosted zone
2. **Check Propagation**: DNS changes can take a few minutes to propagate
3. **Check Logs**: Review CloudWatch logs for the Lambda function
4. **Verify Permissions**: Ensure the cross-account role has correct permissions

### Lambda Function Errors

1. **Check CloudWatch Logs**: The function logs all operations
2. **Verify Role Assumption**: If using cross-account role, verify the trust relationship
3. **Check Hosted Zone ID**: Ensure the hosted zone ID is correct

### Cross-Account Access Denied

1. **Verify Trust Policy**: Ensure the role in Account B trusts Account A
2. **Check Resource ARNs**: Ensure the hosted zone ARN is correct
3. **Verify External ID**: If using external ID, ensure it matches

## Security Considerations

1. **Least Privilege**: Grant only the minimum permissions needed
2. **Use Cross-Account Roles**: Prefer cross-account roles over shared credentials
3. **External ID**: Consider using External ID for additional security
4. **Resource-Specific Permissions**: Limit permissions to specific hosted zones

## Cleanup

When you delete the stack:
- The custom resource will attempt to delete DNS validation records
- The ACM certificate will be deleted (if not in use)
- The Lambda function and logs will be cleaned up

**Note**: If the certificate is already deleted, the DNS record deletion may fail, but this is harmless.

## Example: Complete CDK App

```python
#!/usr/bin/env python3
from aws_cdk import App, Environment
from acm_cross_account_stack import AcmCrossAccountCertificateStack

app = App()

# Certificate in Account A, DNS in Account B
cert_stack = AcmCrossAccountCertificateStack(
    app,
    "AcmCertificateStack",
    domain_name="example.com",
    subject_alternative_names=["*.example.com"],
    target_hosted_zone_id="Z1234567890ABC",
    cross_account_role_arn="arn:aws:iam::111111111111:role/Route53CrossAccountRole",
    env=Environment(
        account="222222222222",  # Certificate account
        region="us-east-1"
    )
)

app.synth()
```

## Related Resources

- [AWS Certificate Manager Documentation](https://docs.aws.amazon.com/acm/)
- [Route53 Documentation](https://docs.aws.amazon.com/route53/)
- [CDK Custom Resources](https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.custom_resources.html)
