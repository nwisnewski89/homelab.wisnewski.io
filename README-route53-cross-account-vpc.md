# Cross-Account VPC Association with Route53 Private Hosted Zone

This solution demonstrates how to associate a VPC from one AWS account with a Route53 private hosted zone in a different account using AWS CDK.

## Overview

When you have:
- A VPC in a **network account** (shared via AWS Resource Access Manager)
- A Route53 private hosted zone in a **DNS account**

You can associate the VPC with the hosted zone, even though they're in different accounts. This requires a two-step process:

1. **Authorization** (from hosted zone account)
2. **Association** (from VPC account)

## Architecture

```
┌─────────────────────────────────┐         ┌─────────────────────────────────┐
│   Network Account (Account A)   │         │    DNS Account (Account B)       │
│                                 │         │                                 │
│  ┌──────────────────────────┐  │         │  ┌──────────────────────────┐  │
│  │   VPC (vpc-12345678)     │  │         │  │  Route53 Private Hosted   │  │
│  │   Shared via RAM         │  │         │  │  Zone (Z1234567890ABC)    │  │
│  └──────────────────────────┘  │         │  └──────────────────────────┘  │
│           │                      │         │           │                      │
│           │                      │         │           │                      │
│           │  Step 2: Associate   │         │  Step 1: Authorize              │
│           └──────────────────────┼─────────┼───────────┘                      │
│                                  │         │                                  │
└──────────────────────────────────┘         └──────────────────────────────────┘
```

## Prerequisites

1. **Route53 Private Hosted Zone** must exist in the DNS account
   - The hosted zone must have at least one VPC associated at creation (in the same account)
   - After creation, you can associate VPCs from other accounts

2. **VPC** must exist in the network account
   - VPC can be shared via RAM, but RAM sharing doesn't automatically associate it with the hosted zone
   - You still need explicit authorization and association steps

3. **IAM Permissions**
   - In DNS account: `route53:CreateVPCAssociationAuthorization`
   - In Network account: `route53:AssociateVPCWithHostedZone`

## Implementation Details

These stacks use **custom resources with Lambda functions** to call the Route53 APIs directly, following the same pattern as the ACM cross-account certificate validation solution.

### Architecture
- **Authorization Stack**: Uses a Lambda custom resource to call `CreateVPCAssociationAuthorization`
- **Association Stack**: Uses a Lambda custom resource to call `AssociateVPCWithHostedZone`

Both stacks handle Create, Update, and Delete operations properly, with error handling for edge cases (e.g., already associated, already authorized).

## Deployment Steps

### Step 1: Deploy Authorization Stack (DNS Account)

Deploy `Route53VpcAssociationAuthorizationStack` in the account that owns the hosted zone:

```python
from aws_cdk import App, Environment
from route53_cross_account_vpc_association import Route53VpcAssociationAuthorizationStack

app = App()

Route53VpcAssociationAuthorizationStack(
    app,
    "Route53VpcAuthStack",
    hosted_zone_id="Z1234567890ABC",
    vpc_id="vpc-12345678",
    vpc_region="us-east-1",
    vpc_account_id="111111111111",  # Network account ID
    env=Environment(
        account="222222222222",  # DNS account (where hosted zone exists)
        region="us-east-1"
    )
)

app.synth()
```

Deploy with:
```bash
cdk deploy Route53VpcAuthStack --profile dns-account-profile
```

### Step 2: Deploy Association Stack (Network Account)

Deploy `Route53VpcAssociationStack` in the account that owns the VPC:

```python
from aws_cdk import App, Environment
from route53_cross_account_vpc_association import Route53VpcAssociationStack

app = App()

Route53VpcAssociationStack(
    app,
    "Route53VpcAssocStack",
    hosted_zone_id="Z1234567890ABC",
    vpc_id="vpc-12345678",
    vpc_region="us-east-1",
    env=Environment(
        account="111111111111",  # Network account (where VPC exists)
        region="us-east-1"
    )
)

app.synth()
```

Deploy with:
```bash
cdk deploy Route53VpcAssocStack --profile network-account-profile
```

**Note**: You can also use the example file `route53_cross_account_vpc_example.py` which includes both stacks with proper configuration.

## Important Notes

### Console Limitation
⚠️ **Cross-account VPC associations cannot be done via the AWS Console**. You must use:
- AWS CLI
- AWS SDK
- CloudFormation/CDK (as shown here)

### Authorization vs Association
- **Authorization** can be deleted after association without breaking the association
- Once associated, the VPC will remain associated even if the authorization is removed
- However, if you need to re-associate later, you'll need to create a new authorization

### Same AWS Partition
Both the VPC and hosted zone must be in the same AWS partition:
- Both in standard AWS
- Both in AWS GovCloud
- Both in AWS China

### Domain Name Uniqueness
A VPC cannot be associated with more than one private hosted zone with the same domain name, even across different accounts.

## Verification

After deployment, verify the association:

```bash
# From DNS account
aws route53 list-hosted-zones-by-vpc \
  --vpc-id vpc-12345678 \
  --vpc-region us-east-1 \
  --profile dns-account-profile

# From Network account
aws route53 get-hosted-zone \
  --id Z1234567890ABC \
  --profile network-account-profile
```

## Troubleshooting

### Error: "No authorization found"
- Ensure Step 1 (authorization) is deployed before Step 2 (association)
- Verify the VPC ID, region, and account ID are correct

### Error: "VPC and hosted zone must be in the same partition"
- Ensure both resources are in the same AWS partition (standard AWS, GovCloud, etc.)

### Error: "VPC is already associated with another hosted zone"
- A VPC can only be associated with one hosted zone per domain name
- Check if the VPC is already associated with another hosted zone for the same domain

## Example Files

- `route53_cross_account_vpc_association.py` - CDK stack definitions
- `route53_cross_account_vpc_example.py` - Example app showing both stacks
- This README - Documentation

## Related Resources

- [AWS Documentation: Associating VPCs with Private Hosted Zones](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/hosted-zone-private-associate-vpcs-different-accounts.html)
- [AWS CLI: associate-vpc-with-hosted-zone](https://docs.aws.amazon.com/cli/latest/reference/route53/associate-vpc-with-hosted-zone.html)
- [AWS CLI: create-vpc-association-authorization](https://docs.aws.amazon.com/cli/latest/reference/route53/create-vpc-association-authorization.html)

