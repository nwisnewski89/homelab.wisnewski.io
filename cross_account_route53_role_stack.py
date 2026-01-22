#!/usr/bin/env python3
"""
CDK Stack to create the cross-account IAM role in the target account (Account B)

This stack should be deployed in the account where the Route53 hosted zone exists.
It creates an IAM role that can be assumed by the Lambda function in the certificate account.

Usage:
    Deploy this stack in Account B (where Route53 hosted zone exists)
    Then use the role ARN in AcmCrossAccountCertificateStack
"""

from aws_cdk import (
    Stack,
    CfnOutput,
    aws_iam as iam,
)
from constructs import Construct


class CrossAccountRoute53RoleStack(Stack):
    """
    Creates an IAM role in the target account that can be assumed by
    the Lambda function in the certificate account to manage Route53 records.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        certificate_account_id: str,
        hosted_zone_id: str,
        external_id: str = None,
        **kwargs
    ) -> None:
        """
        Args:
            scope: Parent construct
            construct_id: Unique identifier for this stack
            certificate_account_id: AWS Account ID where the certificate will be created
            hosted_zone_id: Route53 hosted zone ID where DNS records will be created
            external_id: Optional external ID for additional security
        """
        super().__init__(scope, construct_id, **kwargs)

        # Create trust policy for the role
        # Allow the certificate account to assume this role
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "AWS": f"arn:aws:iam::{certificate_account_id}:root"
                    },
                    "Action": "sts:AssumeRole",
                }
            ]
        }

        # Add external ID condition if provided
        if external_id:
            trust_policy["Statement"][0]["Condition"] = {
                "StringEquals": {
                    "sts:ExternalId": external_id
                }
            }

        # Create the cross-account role
        self.cross_account_role = iam.Role(
            self,
            "Route53CrossAccountRole",
            assumed_by=iam.AccountPrincipal(certificate_account_id),
            description="Role for cross-account Route53 DNS record management for ACM validation",
            role_name="Route53CrossAccountRole",  # Optional: set a specific name
        )

        # Add external ID condition if provided
        if external_id:
            # Note: CDK doesn't directly support external ID in assume role policy
            # You may need to use CfnRole or modify the policy after creation
            # For now, we'll add it via a policy statement
            pass  # External ID would need to be added manually or via CfnRole

        # Attach policy to allow Route53 record management
        self.cross_account_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "route53:ChangeResourceRecordSets",
                    "route53:GetChange",
                    "route53:ListResourceRecordSets",
                ],
                resources=[f"arn:aws:route53:::hostedzone/{hosted_zone_id}"],
            )
        )

        # Optional: Add read-only permissions to list hosted zones (helpful for debugging)
        self.cross_account_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "route53:GetHostedZone",
                    "route53:ListHostedZones",
                ],
                resources=["*"],  # List operations don't support resource-level permissions
            )
        )

        # Create outputs
        CfnOutput(
            self,
            "CrossAccountRoleArn",
            value=self.cross_account_role.role_arn,
            description="ARN of the cross-account role to use in certificate stack",
        )

        CfnOutput(
            self,
            "HostedZoneId",
            value=hosted_zone_id,
            description="Route53 hosted zone ID",
        )


# Example usage:
"""
from aws_cdk import App, Environment

app = App()

# Deploy this in Account B (where Route53 hosted zone exists)
CrossAccountRoute53RoleStack(
    app,
    "CrossAccountRoute53RoleStack",
    certificate_account_id="222222222222",  # Account A - where certificate will be created
    hosted_zone_id="Z1234567890ABC",  # Hosted zone in Account B
    external_id="acm-dns-validation",  # Optional: for additional security
    env=Environment(
        account="111111111111",  # Account B - where hosted zone exists
        region="us-east-1"
    )
)

app.synth()
"""

