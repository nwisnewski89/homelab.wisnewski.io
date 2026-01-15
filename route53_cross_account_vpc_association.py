#!/usr/bin/env python3
"""
CDK Stacks for Cross-Account VPC Association with Route53 Private Hosted Zone

This module provides two stacks:
1. Route53VpcAssociationAuthorizationStack - Deploy in the hosted zone account to authorize VPC associations
2. Route53VpcAssociationStack - Deploy in the VPC account to associate the VPC with the hosted zone

Usage:
    Stack 1 (Hosted Zone Account):
        Route53VpcAssociationAuthorizationStack(
            app, "Route53VpcAuthStack",
            hosted_zone_id="Z1234567890ABC",
            vpc_id="vpc-12345678",  # VPC ID from network account
            vpc_region="us-east-1",
            vpc_account_id="111111111111",  # Network account ID
            env=Environment(account="222222222222", region="us-east-1")  # Hosted zone account
        )

    Stack 2 (VPC Account):
        Route53VpcAssociationStack(
            app, "Route53VpcAssocStack",
            hosted_zone_id="Z1234567890ABC",
            vpc_id="vpc-12345678",
            vpc_region="us-east-1",
            env=Environment(account="111111111111", region="us-east-1")  # Network account
        )
"""

from aws_cdk import (
    Stack,
    CfnOutput,
    aws_route53 as route53,
    aws_ec2 as ec2,
)
from constructs import Construct


class Route53VpcAssociationAuthorizationStack(Stack):
    """
    Stack to authorize a VPC from another account to be associated with a Route53 private hosted zone.
    
    This stack should be deployed in the account that owns the Route53 private hosted zone.
    It creates an authorization that allows the VPC account to associate the VPC.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        hosted_zone_id: str,
        vpc_id: str,
        vpc_region: str,
        vpc_account_id: str,
        **kwargs
    ) -> None:
        """
        Args:
            scope: Parent construct
            construct_id: Unique identifier for this stack
            hosted_zone_id: Route53 private hosted zone ID (in this account)
            vpc_id: VPC ID from the network account to authorize
            vpc_region: AWS region where the VPC exists
            vpc_account_id: AWS Account ID where the VPC exists (network account)
        """
        super().__init__(scope, construct_id, **kwargs)

        # Use CfnVPCAssociationAuthorization to authorize the cross-account VPC association
        # This is a CloudFormation resource since high-level CDK constructs don't support this
        self.vpc_authorization = route53.CfnVPCAssociationAuthorization(
            self,
            "VpcAssociationAuthorization",
            hosted_zone_id=hosted_zone_id,
            vpc=route53.CfnVPCAssociationAuthorization.VpcProperty(
                vpc_id=vpc_id,
                vpc_region=vpc_region,
            ),
        )

        # Create outputs
        CfnOutput(
            self,
            "HostedZoneId",
            value=hosted_zone_id,
            description="Route53 private hosted zone ID",
        )

        CfnOutput(
            self,
            "AuthorizedVpcId",
            value=vpc_id,
            description="VPC ID that has been authorized for association",
        )

        CfnOutput(
            self,
            "AuthorizedVpcAccountId",
            value=vpc_account_id,
            description="Account ID where the authorized VPC exists",
        )

        CfnOutput(
            self,
            "AuthorizationComplete",
            value="true",
            description="Authorization created. Deploy Route53VpcAssociationStack in the VPC account.",
        )


class Route53VpcAssociationStack(Stack):
    """
    Stack to associate a VPC with a Route53 private hosted zone in another account.
    
    This stack should be deployed in the account that owns the VPC (network account).
    The VPC must have been authorized by the hosted zone account first.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        hosted_zone_id: str,
        vpc_id: str,
        vpc_region: str = None,
        **kwargs
    ) -> None:
        """
        Args:
            scope: Parent construct
            construct_id: Unique identifier for this stack
            hosted_zone_id: Route53 private hosted zone ID (in another account)
            vpc_id: VPC ID in this account to associate with the hosted zone
            vpc_region: AWS region where the VPC exists (defaults to stack region)
        """
        super().__init__(scope, construct_id, **kwargs)

        # Use the stack region if vpc_region not specified
        if vpc_region is None:
            vpc_region = self.region

        # Use CfnHostedZoneVPCAssociation to associate the VPC with the hosted zone
        # This is a CloudFormation resource since high-level CDK constructs don't support cross-account
        self.vpc_association = route53.CfnHostedZoneVPCAssociation(
            self,
            "VpcAssociation",
            hosted_zone_id=hosted_zone_id,
            vpc=route53.CfnHostedZoneVPCAssociation.VpcProperty(
                vpc_id=vpc_id,
                vpc_region=vpc_region,
            ),
        )

        # Create outputs
        CfnOutput(
            self,
            "HostedZoneId",
            value=hosted_zone_id,
            description="Route53 private hosted zone ID (in another account)",
        )

        CfnOutput(
            self,
            "AssociatedVpcId",
            value=vpc_id,
            description="VPC ID that has been associated with the hosted zone",
        )

        CfnOutput(
            self,
            "VpcRegion",
            value=vpc_region,
            description="Region where the VPC exists",
        )

        CfnOutput(
            self,
            "AssociationComplete",
            value="true",
            description="VPC successfully associated with the private hosted zone",
        )


# Example usage:
"""
from aws_cdk import App, Environment

app = App()

# Example 1: Deploy authorization stack in the hosted zone account (Account B)
# This authorizes a VPC from the network account (Account A) to be associated
Route53VpcAssociationAuthorizationStack(
    app,
    "Route53VpcAuthStack",
    hosted_zone_id="Z1234567890ABC",  # Hosted zone in Account B
    vpc_id="vpc-12345678",  # VPC ID from network account (Account A)
    vpc_region="us-east-1",
    vpc_account_id="111111111111",  # Network account ID (Account A)
    env=Environment(
        account="222222222222",  # Hosted zone account (Account B)
        region="us-east-1"
    )
)

# Example 2: Deploy association stack in the network account (Account A)
# This actually associates the VPC with the hosted zone
Route53VpcAssociationStack(
    app,
    "Route53VpcAssocStack",
    hosted_zone_id="Z1234567890ABC",  # Hosted zone in Account B
    vpc_id="vpc-12345678",  # VPC ID in this account (Account A)
    vpc_region="us-east-1",
    env=Environment(
        account="111111111111",  # Network account (Account A)
        region="us-east-1"
    )
)

app.synth()
"""

