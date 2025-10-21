#!/usr/bin/env python3
"""
CDK Stack for SES Domain Identity with SMTP IAM User

This stack creates:
- SES Domain Identity with DKIM verification
- IAM User with SES SMTP permissions
- Access Key for SMTP authentication
- Outputs for SMTP configuration
"""

from aws_cdk import (
    Stack,
    CfnOutput,
    RemovalPolicy,
    aws_ses as ses,
    aws_iam as iam,
)
from constructs import Construct


class SesSMTPStack(Stack):
    """Stack to create SES domain identity and IAM user with SMTP access."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        domain_name: str,
        **kwargs
    ) -> None:
        """
        Initialize the SES SMTP Stack.
        
        Args:
            scope: CDK app scope
            construct_id: Unique identifier for this stack
            domain_name: The domain name to configure for SES (e.g., example.com)
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        # Create SES Domain Identity
        domain_identity = ses.EmailIdentity(
            self,
            "SESEmailIdentity",
            identity=ses.Identity.domain(domain_name),
            # Enable DKIM signing for better deliverability
            dkim_signing=True,
            # Configure DKIM with easy_dkim (AWS managed)
            dkim_identity=ses.DkimIdentity.easy_dkim(),
        )

        # Create IAM user for SMTP access
        smtp_user = iam.User(
            self,
            "SESSmtpUser",
            user_name=f"ses-smtp-user-{domain_name.replace('.', '-')}",
        )

        # Create inline policy for SES sending permissions
        ses_send_policy = iam.Policy(
            self,
            "SESSendPolicy",
            policy_name="SESSendEmailPolicy",
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "ses:SendEmail",
                        "ses:SendRawEmail",
                    ],
                    resources=["*"],  # Can be restricted to specific identities
                    conditions={
                        "StringEquals": {
                            "ses:FromAddress": [
                                f"*@{domain_name}",
                            ]
                        }
                    }
                )
            ],
            users=[smtp_user],
        )

        # Create access key for SMTP authentication
        # Note: The secret access key will only be available in CloudFormation outputs
        # once. Store it securely immediately after stack creation.
        access_key = iam.CfnAccessKey(
            self,
            "SESSmtpAccessKey",
            user_name=smtp_user.user_name,
        )

        # Outputs for DNS configuration
        CfnOutput(
            self,
            "DomainName",
            value=domain_name,
            description="SES Domain Identity",
        )

        CfnOutput(
            self,
            "DkimTokens",
            value=domain_identity.dkim_records.to_string(),
            description="DKIM DNS records to add to your domain (TXT records)",
        )

        # SMTP Configuration Outputs
        CfnOutput(
            self,
            "SmtpUsername",
            value=access_key.ref,
            description="SMTP Username (IAM Access Key ID)",
        )

        CfnOutput(
            self,
            "SmtpPassword",
            value=access_key.attr_secret_access_key,
            description="SMTP Password (IAM Secret Access Key - STORE SECURELY!)",
        )

        # SMTP endpoint varies by region
        CfnOutput(
            self,
            "SmtpEndpoint",
            value=f"email-smtp.{self.region}.amazonaws.com",
            description="SMTP Server Endpoint",
        )

        CfnOutput(
            self,
            "SmtpPort",
            value="587",
            description="SMTP Port (use 587 for TLS or 465 for SSL)",
        )

        # Additional helpful outputs
        CfnOutput(
            self,
            "IamUserName",
            value=smtp_user.user_name,
            description="IAM User Name for SMTP",
        )

        CfnOutput(
            self,
            "SesIdentityArn",
            value=domain_identity.email_identity_arn,
            description="SES Email Identity ARN",
        )

        # Configuration instructions
        CfnOutput(
            self,
            "NextSteps",
            value=(
                f"1. Add DKIM DNS records to {domain_name} "
                "2. Verify domain in SES console "
                "3. If in SES sandbox, verify recipient addresses "
                "4. Store SMTP credentials securely "
                "5. Configure your application with SMTP settings"
            ),
            description="Post-deployment configuration steps",
        )

