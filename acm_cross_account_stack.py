#!/usr/bin/env python3
"""
AWS CDK Stack for ACM Certificate with Cross-Account Route53 DNS Validation

This stack creates an ACM certificate in one account and uses a custom resource
to add DNS validation records to a Route53 hosted zone in a different account.

Prerequisites:
1. The Route53 hosted zone must exist in the target account
2. You need cross-account IAM permissions to create records in the target account's hosted zone
3. Either:
   - A cross-account role in the target account that can be assumed, OR
   - Direct Route53 permissions if using the same credentials
"""

from aws_cdk import (
    Stack,
    CfnOutput,
    Duration,
    aws_certificatemanager as acm,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_logs as logs,
    custom_resources as cr,
)
from constructs import Construct
import json


class AcmCrossAccountCertificateStack(Stack):
    """
    Stack that creates an ACM certificate and uses a custom resource to add
    DNS validation records to a Route53 hosted zone in a different account.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        domain_name: str,
        subject_alternative_names: list = None,
        # Cross-account Route53 configuration
        target_hosted_zone_id: str,
        target_hosted_zone_account_id: str = None,
        cross_account_role_arn: str = None,
        **kwargs
    ) -> None:
        """
        Args:
            scope: Parent construct
            construct_id: Unique identifier for this stack
            domain_name: Primary domain name for the certificate
            subject_alternative_names: List of additional domain names (e.g., ["*.example.com"])
            target_hosted_zone_id: Route53 hosted zone ID in the target account
            target_hosted_zone_account_id: Account ID where the hosted zone exists (optional, for validation)
            cross_account_role_arn: ARN of IAM role in target account to assume (optional)
                                    If not provided, assumes same credentials have cross-account access
        """
        super().__init__(scope, construct_id, **kwargs)

        self.domain_name = domain_name
        self.target_hosted_zone_id = target_hosted_zone_id
        self.cross_account_role_arn = cross_account_role_arn

        # Create ACM certificate WITHOUT automatic DNS validation
        # We'll handle DNS validation manually via custom resource
        self.certificate = acm.Certificate(
            self,
            "Certificate",
            domain_name=domain_name,
            subject_alternative_names=subject_alternative_names or [],
            # Use email validation as placeholder - we'll override with custom resource
            validation=acm.CertificateValidation.from_email(),
        )

        # Create custom resource to add DNS validation records to cross-account hosted zone
        self.dns_validator = self.create_cross_account_dns_validator()

        # Create outputs
        self.create_outputs()

    def create_cross_account_dns_validator(self) -> cr.CustomResource:
        """Create custom resource Lambda to add DNS validation records to cross-account hosted zone"""

        # Lambda function code to handle cross-account DNS record creation
        # Using Provider pattern - Lambda receives CloudFormation custom resource events
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
    
    certificate_arn = properties['CertificateArn']
    hosted_zone_id = properties['HostedZoneId']
    cross_account_role_arn = properties.get('CrossAccountRoleArn')
    region = properties.get('Region', 'us-east-1')
    
    physical_resource_id = f"dns-validator-{certificate_arn}"
    response_data = {}
    
    try:
        # Get ACM client (in the same account as certificate)
        acm_client = boto3.client('acm', region_name=region)
        
        # Get Route53 client - either assume role or use same credentials
        if cross_account_role_arn and cross_account_role_arn.strip():
            # Assume cross-account role
            sts_client = boto3.client('sts')
            assumed_role = sts_client.assume_role(
                RoleArn=cross_account_role_arn,
                RoleSessionName='acm-dns-validation'
            )
            credentials = assumed_role['Credentials']
            route53_client = boto3.client(
                'route53',
                aws_access_key_id=credentials['AccessKeyId'],
                aws_secret_access_key=credentials['SecretAccessKey'],
                aws_session_token=credentials['SessionToken']
            )
            print(f"Assumed role: {cross_account_role_arn}")
        else:
            # Use same credentials (must have cross-account permissions)
            route53_client = boto3.client('route53')
            print("Using same credentials for Route53")
        
        if request_type in ['Create', 'Update']:
            # Get certificate details to extract DNS validation records
            cert_response = acm_client.describe_certificate(CertificateArn=certificate_arn)
            certificate = cert_response['Certificate']
            
            domain_validation_options = certificate.get('DomainValidationOptions', [])
            
            if not domain_validation_options:
                raise Exception("No domain validation options found for certificate")
            
            # Create DNS validation records for each domain
            changes = []
            for validation_option in domain_validation_options:
                domain_name = validation_option['DomainName']
                resource_record = validation_option.get('ResourceRecord')
                
                if resource_record:
                    record_name = resource_record['Name']
                    record_type = resource_record['Type']
                    record_value = resource_record['Value']
                    
                    changes.append({
                        'Action': 'UPSERT',
                        'ResourceRecordSet': {
                            'Name': record_name,
                            'Type': record_type,
                            'TTL': 300,
                            'ResourceRecords': [{'Value': record_value}]
                        }
                    })
                    
                    print(f"Adding DNS record: {record_name} {record_type} {record_value}")
            
            if not changes:
                raise Exception("No DNS validation records to create")
            
            # Create the DNS records in the target hosted zone
            change_batch = {
                'Changes': changes,
                'Comment': f'ACM certificate validation records for {certificate_arn}'
            }
            
            change_response = route53_client.change_resource_record_sets(
                HostedZoneId=hosted_zone_id,
                ChangeBatch=change_batch
            )
            
            change_id = change_response['ChangeInfo']['Id']
            print(f"DNS records created/updated. Change ID: {change_id}")
            
            # Wait for change to propagate
            waiter = route53_client.get_waiter('resource_record_sets_changed')
            waiter.wait(Id=change_id)
            
            response_data = {
                'ChangeId': change_id,
                'CertificateArn': certificate_arn,
                'HostedZoneId': hosted_zone_id
            }
            
            send_response(event, context, 'SUCCESS', response_data, physical_resource_id)
            
        elif request_type == 'Delete':
            # Get certificate details to extract DNS validation records
            try:
                cert_response = acm_client.describe_certificate(CertificateArn=certificate_arn)
                certificate = cert_response['Certificate']
                domain_validation_options = certificate.get('DomainValidationOptions', [])
                
                # Delete DNS validation records
                changes = []
                for validation_option in domain_validation_options:
                    resource_record = validation_option.get('ResourceRecord')
                    if resource_record:
                        record_name = resource_record['Name']
                        record_type = resource_record['Type']
                        record_value = resource_record['Value']
                        
                        changes.append({
                            'Action': 'DELETE',
                            'ResourceRecordSet': {
                                'Name': record_name,
                                'Type': record_type,
                                'TTL': 300,
                                'ResourceRecords': [{'Value': record_value}]
                            }
                        })
                
                if changes:
                    change_batch = {
                        'Changes': changes,
                        'Comment': f'Deleting ACM certificate validation records for {certificate_arn}'
                    }
                    route53_client.change_resource_record_sets(
                        HostedZoneId=hosted_zone_id,
                        ChangeBatch=change_batch
                    )
                    print("DNS validation records deleted")
            except Exception as e:
                print(f"Error during delete (certificate may already be deleted): {str(e)}")
            
            send_response(event, context, 'SUCCESS', {}, physical_resource_id)
        
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        send_response(event, context, 'FAILED', {'Error': str(e)}, physical_resource_id)
        raise
"""

        # Create Lambda function
        dns_validator_function = _lambda.Function(
            self,
            "CrossAccountDnsValidatorFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="index.handler",
            code=_lambda.Code.from_inline(lambda_code),
            timeout=Duration.minutes(5),
            log_retention=logs.RetentionDays.ONE_WEEK,
        )

        # Grant permissions to Lambda function
        # 1. Permission to describe ACM certificate
        dns_validator_function.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "acm:DescribeCertificate",
                ],
                resources=[self.certificate.certificate_arn],
            )
        )

        # 2. Permission to create/delete Route53 records in target hosted zone
        route53_resources = [f"arn:aws:route53:::hostedzone/{self.target_hosted_zone_id}"]
        dns_validator_function.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "route53:ChangeResourceRecordSets",
                    "route53:GetChange",
                    "route53:ListResourceRecordSets",
                ],
                resources=route53_resources,
            )
        )

        # 3. If using cross-account role, grant permission to assume it
        if self.cross_account_role_arn:
            dns_validator_function.add_to_role_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["sts:AssumeRole"],
                    resources=[self.cross_account_role_arn],
                )
            )

        # Create Provider for custom resource
        provider = cr.Provider(
            self,
            "CrossAccountDnsValidatorProvider",
            on_event_handler=dns_validator_function,
        )

        # Create custom resource
        custom_resource = cr.CustomResource(
            self,
            "CrossAccountDnsValidator",
            service_token=provider.service_token,
            properties={
                "CertificateArn": self.certificate.certificate_arn,
                "HostedZoneId": self.target_hosted_zone_id,
                "CrossAccountRoleArn": self.cross_account_role_arn or "",
                "Region": self.region,
            },
        )

        # Ensure DNS validator runs after certificate is created
        custom_resource.node.add_dependency(self.certificate)

        return custom_resource

    def create_outputs(self) -> None:
        """Create CloudFormation outputs"""
        CfnOutput(
            self,
            "CertificateArn",
            value=self.certificate.certificate_arn,
            description="ARN of the ACM certificate",
        )

        CfnOutput(
            self,
            "DomainName",
            value=self.domain_name,
            description="Primary domain name of the certificate",
        )

        CfnOutput(
            self,
            "TargetHostedZoneId",
            value=self.target_hosted_zone_id,
            description="Route53 hosted zone ID where DNS validation records were created",
        )


# Example usage:
"""
from aws_cdk import App, Environment

app = App()

# Option 1: Using cross-account IAM role (recommended)
AcmCrossAccountCertificateStack(
    app,
    "AcmCertificateStack",
    domain_name="example.com",
    subject_alternative_names=["*.example.com"],
    target_hosted_zone_id="Z1234567890ABC",  # Hosted zone in different account
    cross_account_role_arn="arn:aws:iam::TARGET_ACCOUNT_ID:role/Route53CrossAccountRole",
    env=Environment(account="CERT_ACCOUNT_ID", region="us-east-1")
)

# Option 2: Using same credentials with cross-account permissions
AcmCrossAccountCertificateStack(
    app,
    "AcmCertificateStack",
    domain_name="example.com",
    subject_alternative_names=["*.example.com"],
    target_hosted_zone_id="Z1234567890ABC",  # Hosted zone in different account
    # cross_account_role_arn not provided - assumes same credentials have access
    env=Environment(account="CERT_ACCOUNT_ID", region="us-east-1")
)

app.synth()
"""
