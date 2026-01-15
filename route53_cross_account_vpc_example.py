#!/usr/bin/env python3
"""
Example CDK App for Cross-Account VPC Association with Route53 Private Hosted Zone

This demonstrates how to associate a VPC from a network account with a Route53
private hosted zone in a different account using CDK.

Scenario:
- Network Account (111111111111): Contains the VPC
- DNS Account (222222222222): Contains the Route53 private hosted zone
- VPC is shared via RAM from network account to DNS account

Steps:
1. Deploy Route53VpcAssociationAuthorizationStack in DNS account (Account B)
2. Deploy Route53VpcAssociationStack in Network account (Account A)
"""

from aws_cdk import App, Environment
from route53_cross_account_vpc_association import (
    Route53VpcAssociationAuthorizationStack,
    Route53VpcAssociationStack,
)

app = App()

# Configuration
HOSTED_ZONE_ID = "Z1234567890ABC"  # Replace with your hosted zone ID
VPC_ID = "vpc-12345678"  # Replace with your VPC ID
VPC_REGION = "us-east-1"
NETWORK_ACCOUNT_ID = "111111111111"  # Network account ID
DNS_ACCOUNT_ID = "222222222222"  # DNS account ID (where hosted zone exists)

# Step 1: Deploy authorization stack in the DNS account (where hosted zone exists)
# This authorizes the VPC from the network account to be associated
authorization_stack = Route53VpcAssociationAuthorizationStack(
    app,
    "Route53VpcAuthStack",
    hosted_zone_id=HOSTED_ZONE_ID,
    vpc_id=VPC_ID,
    vpc_region=VPC_REGION,
    vpc_account_id=NETWORK_ACCOUNT_ID,
    env=Environment(
        account=DNS_ACCOUNT_ID,  # Deploy in DNS account
        region=VPC_REGION
    )
)

# Step 2: Deploy association stack in the network account (where VPC exists)
# This actually associates the VPC with the hosted zone
# Note: This should be deployed AFTER the authorization stack
association_stack = Route53VpcAssociationStack(
    app,
    "Route53VpcAssocStack",
    hosted_zone_id=HOSTED_ZONE_ID,
    vpc_id=VPC_ID,
    vpc_region=VPC_REGION,
    env=Environment(
        account=NETWORK_ACCOUNT_ID,  # Deploy in network account
        region=VPC_REGION
    )
)

# Add dependency to ensure authorization happens before association
association_stack.add_dependency(authorization_stack)

app.synth()

