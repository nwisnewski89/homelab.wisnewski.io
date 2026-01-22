#!/usr/bin/env python3
"""
CDK Stacks for Cross-Account VPC Association with Route53 Private Hosted Zone

This module provides two stacks using custom resources with Lambda functions:
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
    Duration,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_logs as logs,
    custom_resources as cr,
)
from constructs import Construct


class Route53VpcAssociationAuthorizationStack(Stack):
    """
    Stack to authorize a VPC from another account to be associated with a Route53 private hosted zone.
    
    This stack should be deployed in the account that owns the Route53 private hosted zone.
    It creates an authorization that allows the VPC account to associate the VPC.
    
    Uses a custom resource with Lambda to call CreateVPCAssociationAuthorization API.
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

        self.hosted_zone_id = hosted_zone_id
        self.vpc_id = vpc_id
        self.vpc_region = vpc_region
        self.vpc_account_id = vpc_account_id

        # Create custom resource to authorize VPC association
        self.authorization = self.create_authorization_custom_resource()

        # Create outputs
        self.create_outputs()

    def create_authorization_custom_resource(self) -> cr.CustomResource:
        """Create custom resource Lambda to authorize VPC association"""

        # Lambda function code to handle VPC association authorization
        lambda_code = """
import boto3
import json
import urllib.request
import urllib.error

def send_response(event, context, response_status, response_data, physical_resource_id=None):
    '''Send response to CloudFormation using standard library'''
    response_url = event['ResponseURL']
    
    response_body = {
        'Status': response_status,
        'Reason': f'See the details in CloudWatch Log Stream: {context.log_stream_name}',
        'PhysicalResourceId': physical_resource_id or context.log_stream_name,
        'StackId': event['StackId'],
        'RequestId': event['RequestId'],
        'LogicalResourceId': event['LogicalResourceId'],
        'Data': response_data
    }
    
    json_response_body = json.dumps(response_body)
    
    try:
        req = urllib.request.Request(
            response_url,
            data=json_response_body.encode('utf-8'),
            headers={'Content-Type': '', 'Content-Length': str(len(json_response_body))},
            method='PUT'
        )
        with urllib.request.urlopen(req) as response:
            print(f"Response sent: {response.status}")
    except urllib.error.HTTPError as e:
        print(f"Failed to send response: {str(e)}")
        raise

def handler(event, context):
    print(f"Event: {json.dumps(event)}")
    
    request_type = event['RequestType']
    properties = event.get('ResourceProperties', {})
    
    hosted_zone_id = properties['HostedZoneId']
    vpc_id = properties['VpcId']
    vpc_region = properties['VpcRegion']
    
    physical_resource_id = f"vpc-auth-{hosted_zone_id}-{vpc_id}"
    response_data = {}
    
    try:
        route53_client = boto3.client('route53')
        
        if request_type in ['Create', 'Update']:
            # Create VPC association authorization
            print(f"Authorizing VPC {vpc_id} in region {vpc_region} for hosted zone {hosted_zone_id}")
            
            route53_client.create_vpc_association_authorization(
                HostedZoneId=hosted_zone_id,
                VPC={
                    'VPCRegion': vpc_region,
                    'VPCId': vpc_id
                }
            )
            
            print(f"Successfully authorized VPC {vpc_id} for hosted zone {hosted_zone_id}")
            
            response_data = {
                'HostedZoneId': hosted_zone_id,
                'VpcId': vpc_id,
                'VpcRegion': vpc_region,
                'Status': 'Authorized'
            }
            
            send_response(event, context, 'SUCCESS', response_data, physical_resource_id)
            
        elif request_type == 'Delete':
            # Delete VPC association authorization
            # Note: This is optional - authorization can remain after association
            try:
                print(f"Deleting authorization for VPC {vpc_id} and hosted zone {hosted_zone_id}")
                route53_client.delete_vpc_association_authorization(
                    HostedZoneId=hosted_zone_id,
                    VPC={
                        'VPCRegion': vpc_region,
                        'VPCId': vpc_id
                    }
                )
                print(f"Successfully deleted authorization")
            except route53_client.exceptions.InvalidInput as e:
                # Authorization may have already been deleted or association may exist
                print(f"Authorization may not exist or VPC is already associated: {str(e)}")
            except Exception as e:
                print(f"Error deleting authorization (may not exist): {str(e)}")
            
            send_response(event, context, 'SUCCESS', {}, physical_resource_id)
        
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        send_response(event, context, 'FAILED', {'Error': str(e)}, physical_resource_id)
        raise
"""

        # Create Lambda function
        auth_function = _lambda.Function(
            self,
            "VpcAssociationAuthorizationFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="index.handler",
            code=_lambda.Code.from_inline(lambda_code),
            timeout=Duration.minutes(5),
            log_retention=logs.RetentionDays.ONE_WEEK,
            description="Authorizes cross-account VPC association with Route53 private hosted zone",
        )

        # Grant permissions to Lambda function
        auth_function.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "route53:CreateVPCAssociationAuthorization",
                    "route53:DeleteVPCAssociationAuthorization",
                    "route53:ListVPCAssociationAuthorizations",
                ],
                resources=[f"arn:aws:route53:::hostedzone/{self.hosted_zone_id}"],
            )
        )

        # Create Provider for custom resource
        provider = cr.Provider(
            self,
            "VpcAssociationAuthorizationProvider",
            on_event_handler=auth_function,
        )

        # Create custom resource
        custom_resource = cr.CustomResource(
            self,
            "VpcAssociationAuthorization",
            service_token=provider.service_token,
            properties={
                "HostedZoneId": self.hosted_zone_id,
                "VpcId": self.vpc_id,
                "VpcRegion": self.vpc_region,
            },
        )

        return custom_resource

    def create_outputs(self) -> None:
        """Create CloudFormation outputs"""
        CfnOutput(
            self,
            "HostedZoneId",
            value=self.hosted_zone_id,
            description="Route53 private hosted zone ID",
        )

        CfnOutput(
            self,
            "AuthorizedVpcId",
            value=self.vpc_id,
            description="VPC ID that has been authorized for association",
        )

        CfnOutput(
            self,
            "AuthorizedVpcAccountId",
            value=self.vpc_account_id,
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
    
    Uses a custom resource with Lambda to call AssociateVPCWithHostedZone API.
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

        self.hosted_zone_id = hosted_zone_id
        self.vpc_id = vpc_id
        self.vpc_region = vpc_region

        # Create custom resource to associate VPC with hosted zone
        self.association = self.create_association_custom_resource()

        # Create outputs
        self.create_outputs()

    def create_association_custom_resource(self) -> cr.CustomResource:
        """Create custom resource Lambda to associate VPC with hosted zone"""

        # Lambda function code to handle VPC association
        lambda_code = """
import boto3
import json
import urllib.request
import urllib.error

def send_response(event, context, response_status, response_data, physical_resource_id=None):
    '''Send response to CloudFormation using standard library'''
    response_url = event['ResponseURL']
    
    response_body = {
        'Status': response_status,
        'Reason': f'See the details in CloudWatch Log Stream: {context.log_stream_name}',
        'PhysicalResourceId': physical_resource_id or context.log_stream_name,
        'StackId': event['StackId'],
        'RequestId': event['RequestId'],
        'LogicalResourceId': event['LogicalResourceId'],
        'Data': response_data
    }
    
    json_response_body = json.dumps(response_body)
    
    try:
        req = urllib.request.Request(
            response_url,
            data=json_response_body.encode('utf-8'),
            headers={'Content-Type': '', 'Content-Length': str(len(json_response_body))},
            method='PUT'
        )
        with urllib.request.urlopen(req) as response:
            print(f"Response sent: {response.status}")
    except urllib.error.HTTPError as e:
        print(f"Failed to send response: {str(e)}")
        raise

def handler(event, context):
    print(f"Event: {json.dumps(event)}")
    
    request_type = event['RequestType']
    properties = event.get('ResourceProperties', {})
    
    hosted_zone_id = properties['HostedZoneId']
    vpc_id = properties['VpcId']
    vpc_region = properties['VpcRegion']
    
    physical_resource_id = f"vpc-assoc-{hosted_zone_id}-{vpc_id}"
    response_data = {}
    
    try:
        route53_client = boto3.client('route53')
        
        if request_type in ['Create', 'Update']:
            # Associate VPC with hosted zone
            print(f"Associating VPC {vpc_id} in region {vpc_region} with hosted zone {hosted_zone_id}")
            
            try:
                response = route53_client.associate_vpc_with_hosted_zone(
                    HostedZoneId=hosted_zone_id,
                    VPC={
                        'VPCRegion': vpc_region,
                        'VPCId': vpc_id
                    }
                )
                
                change_id = response['ChangeInfo']['Id']
                print(f"Successfully associated VPC {vpc_id} with hosted zone {hosted_zone_id}")
                print(f"Change ID: {change_id}")
                
                # Wait for change to propagate
                waiter = route53_client.get_waiter('resource_record_sets_changed')
                waiter.wait(Id=change_id)
                print("Association change has propagated")
                
                response_data = {
                    'HostedZoneId': hosted_zone_id,
                    'VpcId': vpc_id,
                    'VpcRegion': vpc_region,
                    'ChangeId': change_id,
                    'Status': 'Associated'
                }
                
            except route53_client.exceptions.InvalidVPCId as e:
                error_msg = str(e)
                if "already associated" in error_msg.lower():
                    print(f"VPC {vpc_id} is already associated with hosted zone {hosted_zone_id}")
                    response_data = {
                        'HostedZoneId': hosted_zone_id,
                        'VpcId': vpc_id,
                        'VpcRegion': vpc_region,
                        'Status': 'AlreadyAssociated'
                    }
                else:
                    raise
            
            send_response(event, context, 'SUCCESS', response_data, physical_resource_id)
            
        elif request_type == 'Delete':
            # Disassociate VPC from hosted zone
            try:
                print(f"Disassociating VPC {vpc_id} from hosted zone {hosted_zone_id}")
                response = route53_client.disassociate_vpc_from_hosted_zone(
                    HostedZoneId=hosted_zone_id,
                    VPC={
                        'VPCRegion': vpc_region,
                        'VPCId': vpc_id
                    }
                )
                
                change_id = response['ChangeInfo']['Id']
                print(f"Successfully disassociated VPC {vpc_id} from hosted zone {hosted_zone_id}")
                print(f"Change ID: {change_id}")
                
                # Wait for change to propagate
                waiter = route53_client.get_waiter('resource_record_sets_changed')
                waiter.wait(Id=change_id)
                print("Disassociation change has propagated")
                
            except route53_client.exceptions.InvalidVPCId as e:
                # VPC may not be associated or may have been already disassociated
                print(f"VPC may not be associated: {str(e)}")
            except Exception as e:
                print(f"Error during disassociation (VPC may already be disassociated): {str(e)}")
            
            send_response(event, context, 'SUCCESS', {}, physical_resource_id)
        
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        send_response(event, context, 'FAILED', {'Error': str(e)}, physical_resource_id)
        raise
"""

        # Create Lambda function
        assoc_function = _lambda.Function(
            self,
            "VpcAssociationFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="index.handler",
            code=_lambda.Code.from_inline(lambda_code),
            timeout=Duration.minutes(5),
            log_retention=logs.RetentionDays.ONE_WEEK,
            description="Associates VPC with Route53 private hosted zone across accounts",
        )

        # Grant permissions to Lambda function
        # Note: These permissions work across accounts when the hosted zone is in another account
        assoc_function.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "route53:AssociateVPCWithHostedZone",
                    "route53:DisassociateVPCFromHostedZone",
                    "route53:GetChange",
                ],
                resources=[
                    f"arn:aws:route53:::hostedzone/{self.hosted_zone_id}",
                    "arn:aws:route53:::change/*",
                ],
            )
        )

        # Create Provider for custom resource
        provider = cr.Provider(
            self,
            "VpcAssociationProvider",
            on_event_handler=assoc_function,
        )

        # Create custom resource
        custom_resource = cr.CustomResource(
            self,
            "VpcAssociation",
            service_token=provider.service_token,
            properties={
                "HostedZoneId": self.hosted_zone_id,
                "VpcId": self.vpc_id,
                "VpcRegion": self.vpc_region,
            },
        )

        return custom_resource

    def create_outputs(self) -> None:
        """Create CloudFormation outputs"""
        CfnOutput(
            self,
            "HostedZoneId",
            value=self.hosted_zone_id,
            description="Route53 private hosted zone ID (in another account)",
        )

        CfnOutput(
            self,
            "AssociatedVpcId",
            value=self.vpc_id,
            description="VPC ID that has been associated with the hosted zone",
        )

        CfnOutput(
            self,
            "VpcRegion",
            value=self.vpc_region,
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

