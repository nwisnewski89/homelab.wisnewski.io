#!/usr/bin/env python3
"""
Example CDK App using AcmCrossAccountCertificateStack

This demonstrates how to create an ACM certificate in one account
and add DNS validation records to a Route53 hosted zone in a different account.
"""

from aws_cdk import App, Environment
from acm_cross_account_stack import AcmCrossAccountCertificateStack

app = App()

# Example 1: Using cross-account IAM role (recommended)
# Certificate in Account A (222222222222), DNS in Account B (111111111111)
cert_stack = AcmCrossAccountCertificateStack(
    app,
    "AcmCertificateStack",
    domain_name="example.com",
    subject_alternative_names=["*.example.com"],  # Wildcard for subdomains
    target_hosted_zone_id="Z1234567890ABC",  # Hosted zone ID in Account B
    cross_account_role_arn="arn:aws:iam::111111111111:role/Route53CrossAccountRole",
    env=Environment(
        account="222222222222",  # Account where certificate is created
        region="us-east-1"  # Use us-east-1 for CloudFront certificates
    )
)

# Example 2: Using same credentials (if they have cross-account permissions)
# cert_stack = AcmCrossAccountCertificateStack(
#     app,
#     "AcmCertificateStack",
#     domain_name="example.com",
#     subject_alternative_names=["*.example.com"],
#     target_hosted_zone_id="Z1234567890ABC",
#     # cross_account_role_arn not provided
#     env=Environment(
#         account="222222222222",
#         region="us-east-1"
#     )
# )

app.synth()
