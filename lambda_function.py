#!/usr/bin/env python3
"""
CDK Stack for IAM Access Key Rotation with SNS Notifications

This stack creates:
- Lambda function that checks all IAM users for access keys older than 90 days
- Automatically rotates old access keys
- Publishes notifications to SNS topic
- Optional EventBridge rule to run on a schedule
"""

from aws_cdk import (
    Stack,
    Duration,
    CfnOutput,
    aws_lambda as lambda_,
    aws_sns as sns,
    aws_sns_subscriptions as sns_subs,
    aws_iam as iam,
    aws_events as events,
    aws_events_targets as targets,
    aws_logs as logs,
)
from constructs import Construct


class AccessKeyRotationStack(Stack):
    """
    CDK Stack for automated IAM access key rotation
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        email_address: str = "admin@example.com",
        rotation_days: int = 90,
        enable_schedule: bool = False,
        schedule_expression: str = "rate(1 day)",
        **kwargs
    ) -> None:
        """
        Initialize the Access Key Rotation Stack

        Args:
            scope: CDK scope
            construct_id: Construct ID
            email_address: Email address for SNS notifications
            rotation_days: Number of days before rotating keys (default: 90)
            enable_schedule: Whether to enable scheduled execution
            schedule_expression: CloudWatch Events schedule expression
            **kwargs: Additional CDK stack arguments
        """
        super().__init__(scope, construct_id, **kwargs)

        # Create SNS topic for notifications
        self.notification_topic = sns.Topic(
            self,
            "AccessKeyRotationTopic",
            display_name="IAM Access Key Rotation Notifications",
            topic_name="iam-access-key-rotation-notifications",
        )

        # Add email subscription
        self.notification_topic.add_subscription(
            sns_subs.EmailSubscription(email_address)
        )

        # Create Lambda execution role with necessary permissions
        lambda_role = iam.Role(
            self,
            "AccessKeyRotationLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Role for IAM access key rotation Lambda function",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )

        # Add IAM permissions for listing users and managing access keys
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "iam:ListUsers",
                    "iam:ListAccessKeys",
                    "iam:GetAccessKeyLastUsed",
                    "iam:CreateAccessKey",
                    "iam:DeleteAccessKey",
                    "iam:UpdateAccessKey",
                ],
                resources=["*"],
            )
        )

        # Grant permission to publish to SNS
        self.notification_topic.grant_publish(lambda_role)

        # Create Lambda function for access key rotation
        self.rotation_function = lambda_.Function(
            self,
            "AccessKeyRotationFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=lambda_.Code.from_inline(self._get_lambda_code()),
            timeout=Duration.minutes(15),
            memory_size=256,
            role=lambda_role,
            description="Rotates IAM access keys older than specified days",
            environment={
                "SNS_TOPIC_ARN": self.notification_topic.topic_arn,
                "ROTATION_DAYS": str(rotation_days),
                "DRY_RUN": "false",  # Set to "true" to test without actually rotating
            },
            log_retention=logs.RetentionDays.ONE_WEEK,
        )

        # Optionally create EventBridge rule for scheduled execution
        if enable_schedule:
            rotation_rule = events.Rule(
                self,
                "AccessKeyRotationSchedule",
                description=f"Triggers access key rotation check every {schedule_expression}",
                schedule=events.Schedule.expression(schedule_expression),
            )

            rotation_rule.add_target(targets.LambdaFunction(self.rotation_function))

            CfnOutput(
                self,
                "ScheduleEnabled",
                value="true",
                description="Scheduled execution is enabled",
            )

            CfnOutput(
                self,
                "ScheduleExpression",
                value=schedule_expression,
                description="Schedule expression for rotation checks",
            )

        # Outputs
        CfnOutput(
            self,
            "FunctionName",
            value=self.rotation_function.function_name,
            description="Name of the Lambda function",
        )

        CfnOutput(
            self,
            "FunctionArn",
            value=self.rotation_function.function_arn,
            description="ARN of the Lambda function",
        )

        CfnOutput(
            self,
            "TopicArn",
            value=self.notification_topic.topic_arn,
            description="ARN of the SNS notification topic",
        )

        CfnOutput(
            self,
            "RotationDays",
            value=str(rotation_days),
            description="Access keys older than this many days will be rotated",
        )

        CfnOutput(
            self,
            "ManualInvoke",
            value=f"aws lambda invoke --function-name {self.rotation_function.function_name} response.json",
            description="Command to manually invoke the rotation function",
        )

    def _get_lambda_code(self) -> str:
        """Returns the inline Lambda code for access key rotation"""
        return '''
import json
import boto3
import os
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
iam_client = boto3.client('iam')
sns_client = boto3.client('sns')

# Configuration from environment variables
SNS_TOPIC_ARN = os.environ['SNS_TOPIC_ARN']
ROTATION_DAYS = int(os.environ.get('ROTATION_DAYS', '90'))
DRY_RUN = os.environ.get('DRY_RUN', 'false').lower() == 'true'


def handler(event, context):
    """
    Main Lambda handler for IAM access key rotation
    
    This function:
    1. Lists all IAM users
    2. Checks each user's access keys
    3. Rotates keys older than ROTATION_DAYS
    4. Sends notifications to SNS
    """
    logger.info(f"Starting access key rotation check (Rotation threshold: {ROTATION_DAYS} days, Dry run: {DRY_RUN})")
    
    try:
        # Get all IAM users
        users = get_all_users()
        logger.info(f"Found {len(users)} IAM users")
        
        # Track rotation results
        results = {
            'users_checked': len(users),
            'keys_checked': 0,
            'keys_rotated': 0,
            'keys_old': 0,
            'rotation_details': [],
            'errors': []
        }
        
        # Check each user's access keys
        for user in users:
            user_name = user['UserName']
            logger.info(f"Checking user: {user_name}")
            
            try:
                access_keys = get_user_access_keys(user_name)
                results['keys_checked'] += len(access_keys)
                
                for key in access_keys:
                    key_id = key['AccessKeyId']
                    create_date = key['CreateDate']
                    key_age_days = get_key_age_days(create_date)
                    status = key['Status']
                    
                    logger.info(f"  Key {key_id}: Age={key_age_days} days, Status={status}")
                    
                    # Check if key needs rotation
                    if status == 'Active' and key_age_days > ROTATION_DAYS:
                        results['keys_old'] += 1
                        logger.warning(f"  Key {key_id} is {key_age_days} days old and needs rotation")
                        
                        # Rotate the key
                        rotation_result = rotate_access_key(user_name, key_id, key_age_days)
                        
                        if rotation_result['success']:
                            results['keys_rotated'] += 1
                            results['rotation_details'].append({
                                'user': user_name,
                                'old_key_id': key_id,
                                'new_key_id': rotation_result.get('new_key_id'),
                                'key_age_days': key_age_days,
                                'rotated_at': datetime.now(timezone.utc).isoformat(),
                                'dry_run': DRY_RUN
                            })
                        else:
                            results['errors'].append({
                                'user': user_name,
                                'key_id': key_id,
                                'error': rotation_result.get('error')
                            })
                            
            except Exception as e:
                error_msg = f"Error processing user {user_name}: {str(e)}"
                logger.error(error_msg)
                results['errors'].append({
                    'user': user_name,
                    'error': str(e)
                })
        
        # Send notification to SNS
        send_notification(results)
        
        # Log summary
        logger.info(f"Rotation complete: {results['keys_rotated']} keys rotated out of {results['keys_old']} old keys")
        logger.info(f"Summary: {json.dumps(results, indent=2, default=str)}")
        
        return {
            'statusCode': 200,
            'body': json.dumps(results, default=str)
        }
        
    except Exception as e:
        error_msg = f"Fatal error in rotation handler: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        # Send error notification
        send_error_notification(error_msg)
        
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


def get_all_users() -> List[Dict]:
    """Get all IAM users using pagination"""
    users = []
    paginator = iam_client.get_paginator('list_users')
    
    for page in paginator.paginate():
        users.extend(page['Users'])
    
    return users


def get_user_access_keys(user_name: str) -> List[Dict]:
    """Get all access keys for a specific user"""
    response = iam_client.list_access_keys(UserName=user_name)
    return response['AccessKeyMetadata']


def get_key_age_days(create_date) -> int:
    """Calculate the age of an access key in days"""
    now = datetime.now(timezone.utc)
    
    # Ensure create_date is timezone-aware
    if create_date.tzinfo is None:
        create_date = create_date.replace(tzinfo=timezone.utc)
    
    age = now - create_date
    return age.days


def rotate_access_key(user_name: str, old_key_id: str, key_age_days: int) -> Dict:
    """
    Rotate an IAM access key
    
    Steps:
    1. Create a new access key
    2. Delete the old access key
    
    Returns dict with success status and new key info
    """
    logger.info(f"Rotating key {old_key_id} for user {user_name} (Age: {key_age_days} days)")
    
    if DRY_RUN:
        logger.info("DRY RUN: Would rotate key but skipping actual rotation")
        return {
            'success': True,
            'new_key_id': 'DRY_RUN_KEY_ID',
            'dry_run': True
        }
    
    try:
        # Check if user already has 2 access keys (AWS limit)
        existing_keys = get_user_access_keys(user_name)
        
        if len(existing_keys) >= 2:
            # Delete the old key first to make room
            logger.info(f"User has {len(existing_keys)} keys, deleting old key first")
            iam_client.delete_access_key(UserName=user_name, AccessKeyId=old_key_id)
            logger.info(f"Deleted old key: {old_key_id}")
        
        # Create new access key
        response = iam_client.create_access_key(UserName=user_name)
        new_key = response['AccessKey']
        new_key_id = new_key['AccessKeyId']
        new_secret_key = new_key['SecretAccessKey']
        
        logger.info(f"Created new key: {new_key_id}")
        
        # If we didn't delete the old key earlier, delete it now
        if len(existing_keys) < 2:
            iam_client.delete_access_key(UserName=user_name, AccessKeyId=old_key_id)
            logger.info(f"Deleted old key: {old_key_id}")
        
        return {
            'success': True,
            'new_key_id': new_key_id,
            'new_secret_key': new_secret_key,
            'old_key_id': old_key_id,
            'dry_run': False
        }
        
    except Exception as e:
        logger.error(f"Error rotating key {old_key_id} for user {user_name}: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'old_key_id': old_key_id
        }


def send_notification(results: Dict):
    """Send rotation summary notification to SNS"""
    try:
        # Create detailed message
        message_lines = [
            "IAM Access Key Rotation Report",
            "=" * 50,
            "",
            f"Rotation Threshold: {ROTATION_DAYS} days",
            f"Dry Run Mode: {'Yes' if DRY_RUN else 'No'}",
            f"Execution Time: {datetime.now(timezone.utc).isoformat()}",
            "",
            "Summary:",
            f"  - Users Checked: {results['users_checked']}",
            f"  - Keys Checked: {results['keys_checked']}",
            f"  - Keys Found Older Than {ROTATION_DAYS} Days: {results['keys_old']}",
            f"  - Keys Rotated: {results['keys_rotated']}",
            f"  - Errors: {len(results['errors'])}",
            "",
        ]
        
        # Add rotation details
        if results['rotation_details']:
            message_lines.append("Rotated Keys:")
            message_lines.append("-" * 50)
            for detail in results['rotation_details']:
                message_lines.extend([
                    f"  User: {detail['user']}",
                    f"  Old Key: {detail['old_key_id']}",
                    f"  New Key: {detail.get('new_key_id', 'N/A')}",
                    f"  Age: {detail['key_age_days']} days",
                    f"  Rotated At: {detail['rotated_at']}",
                    ""
                ])
        
        # Add errors if any
        if results['errors']:
            message_lines.append("Errors:")
            message_lines.append("-" * 50)
            for error in results['errors']:
                message_lines.extend([
                    f"  User: {error.get('user', 'N/A')}",
                    f"  Key: {error.get('key_id', 'N/A')}",
                    f"  Error: {error.get('error')}",
                    ""
                ])
        
        message = "\\n".join(message_lines)
        
        # Determine subject based on results
        if results['keys_rotated'] > 0:
            subject = f"IAM Access Key Rotation: {results['keys_rotated']} Keys Rotated"
        elif results['keys_old'] > 0:
            subject = f"IAM Access Key Rotation: {results['keys_old']} Old Keys Found (No Rotation)"
        else:
            subject = "IAM Access Key Rotation: No Action Needed"
        
        # Publish to SNS
        response = sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=subject,
            Message=message
        )
        
        logger.info(f"Notification sent to SNS. MessageId: {response['MessageId']}")
        
    except Exception as e:
        logger.error(f"Error sending notification: {str(e)}")


def send_error_notification(error_message: str):
    """Send error notification to SNS"""
    try:
        message = f"""
IAM Access Key Rotation - ERROR

An error occurred during the access key rotation process:

{error_message}

Timestamp: {datetime.now(timezone.utc).isoformat()}

Please check CloudWatch Logs for more details.
"""
        
        sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject="ERROR: IAM Access Key Rotation Failed",
            Message=message
        )
        
    except Exception as e:
        logger.error(f"Error sending error notification: {str(e)}")
'''


class AccessKeyRotationWithSecretsManagerStack(Stack):
    """
    Enhanced version that stores new access keys in AWS Secrets Manager
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        email_address: str = "admin@example.com",
        rotation_days: int = 90,
        enable_schedule: bool = False,
        schedule_expression: str = "rate(1 day)",
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create SNS topic
        self.notification_topic = sns.Topic(
            self,
            "AccessKeyRotationTopic",
            display_name="IAM Access Key Rotation with Secrets Manager",
            topic_name="iam-access-key-rotation-secrets-manager",
        )

        self.notification_topic.add_subscription(
            sns_subs.EmailSubscription(email_address)
        )

        # Create Lambda role with Secrets Manager permissions
        lambda_role = iam.Role(
            self,
            "AccessKeyRotationLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Role for IAM access key rotation with Secrets Manager",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )

        # Add IAM permissions
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "iam:ListUsers",
                    "iam:ListAccessKeys",
                    "iam:GetAccessKeyLastUsed",
                    "iam:CreateAccessKey",
                    "iam:DeleteAccessKey",
                    "iam:UpdateAccessKey",
                ],
                resources=["*"],
            )
        )

        # Add Secrets Manager permissions
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "secretsmanager:CreateSecret",
                    "secretsmanager:UpdateSecret",
                    "secretsmanager:PutSecretValue",
                    "secretsmanager:TagResource",
                ],
                resources=["*"],
            )
        )

        self.notification_topic.grant_publish(lambda_role)

        # Create Lambda function
        self.rotation_function = lambda_.Function(
            self,
            "AccessKeyRotationSecretsFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=lambda_.Code.from_inline(self._get_secrets_manager_lambda_code()),
            timeout=Duration.minutes(15),
            memory_size=256,
            role=lambda_role,
            description="Rotates IAM access keys and stores in Secrets Manager",
            environment={
                "SNS_TOPIC_ARN": self.notification_topic.topic_arn,
                "ROTATION_DAYS": str(rotation_days),
                "DRY_RUN": "false",
                "STORE_IN_SECRETS_MANAGER": "true",
            },
            log_retention=logs.RetentionDays.ONE_WEEK,
        )

        # Optionally create EventBridge rule
        if enable_schedule:
            rotation_rule = events.Rule(
                self,
                "AccessKeyRotationSchedule",
                description=f"Triggers access key rotation with Secrets Manager",
                schedule=events.Schedule.expression(schedule_expression),
            )

            rotation_rule.add_target(targets.LambdaFunction(self.rotation_function))

        # Outputs
        CfnOutput(
            self,
            "FunctionName",
            value=self.rotation_function.function_name,
            description="Name of the Lambda function",
        )

        CfnOutput(
            self,
            "TopicArn",
            value=self.notification_topic.topic_arn,
            description="ARN of the SNS notification topic",
        )

        CfnOutput(
            self,
            "SecretsManagerEnabled",
            value="true",
            description="New access keys are stored in Secrets Manager",
        )

    def _get_secrets_manager_lambda_code(self) -> str:
        """Returns Lambda code with Secrets Manager integration"""
        return '''
import json
import boto3
import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger()
logger.setLevel(logging.INFO)

iam_client = boto3.client('iam')
sns_client = boto3.client('sns')
secrets_client = boto3.client('secretsmanager')

SNS_TOPIC_ARN = os.environ['SNS_TOPIC_ARN']
ROTATION_DAYS = int(os.environ.get('ROTATION_DAYS', '90'))
DRY_RUN = os.environ.get('DRY_RUN', 'false').lower() == 'true'
STORE_IN_SECRETS_MANAGER = os.environ.get('STORE_IN_SECRETS_MANAGER', 'true').lower() == 'true'


def handler(event, context):
    """Handler with Secrets Manager integration"""
    logger.info(f"Starting access key rotation (Secrets Manager: {STORE_IN_SECRETS_MANAGER})")
    
    try:
        users = get_all_users()
        logger.info(f"Found {len(users)} IAM users")
        
        results = {
            'users_checked': len(users),
            'keys_checked': 0,
            'keys_rotated': 0,
            'keys_old': 0,
            'secrets_created': 0,
            'rotation_details': [],
            'errors': []
        }
        
        for user in users:
            user_name = user['UserName']
            
            try:
                access_keys = get_user_access_keys(user_name)
                results['keys_checked'] += len(access_keys)
                
                for key in access_keys:
                    key_id = key['AccessKeyId']
                    create_date = key['CreateDate']
                    key_age_days = get_key_age_days(create_date)
                    status = key['Status']
                    
                    if status == 'Active' and key_age_days > ROTATION_DAYS:
                        results['keys_old'] += 1
                        
                        rotation_result = rotate_access_key(user_name, key_id, key_age_days)
                        
                        if rotation_result['success']:
                            results['keys_rotated'] += 1
                            
                            # Store in Secrets Manager
                            if STORE_IN_SECRETS_MANAGER and not DRY_RUN:
                                secret_arn = store_in_secrets_manager(
                                    user_name,
                                    rotation_result['new_key_id'],
                                    rotation_result['new_secret_key']
                                )
                                rotation_result['secret_arn'] = secret_arn
                                results['secrets_created'] += 1
                            
                            results['rotation_details'].append({
                                'user': user_name,
                                'old_key_id': key_id,
                                'new_key_id': rotation_result.get('new_key_id'),
                                'key_age_days': key_age_days,
                                'secret_arn': rotation_result.get('secret_arn'),
                                'rotated_at': datetime.now(timezone.utc).isoformat(),
                                'dry_run': DRY_RUN
                            })
                        else:
                            results['errors'].append({
                                'user': user_name,
                                'key_id': key_id,
                                'error': rotation_result.get('error')
                            })
                            
            except Exception as e:
                logger.error(f"Error processing user {user_name}: {str(e)}")
                results['errors'].append({
                    'user': user_name,
                    'error': str(e)
                })
        
        send_notification(results)
        
        return {
            'statusCode': 200,
            'body': json.dumps(results, default=str)
        }
        
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}", exc_info=True)
        send_error_notification(str(e))
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


def get_all_users():
    users = []
    paginator = iam_client.get_paginator('list_users')
    for page in paginator.paginate():
        users.extend(page['Users'])
    return users


def get_user_access_keys(user_name):
    response = iam_client.list_access_keys(UserName=user_name)
    return response['AccessKeyMetadata']


def get_key_age_days(create_date):
    now = datetime.now(timezone.utc)
    if create_date.tzinfo is None:
        create_date = create_date.replace(tzinfo=timezone.utc)
    age = now - create_date
    return age.days


def rotate_access_key(user_name, old_key_id, key_age_days):
    if DRY_RUN:
        return {
            'success': True,
            'new_key_id': 'DRY_RUN_KEY_ID',
            'new_secret_key': 'DRY_RUN_SECRET',
            'dry_run': True
        }
    
    try:
        existing_keys = get_user_access_keys(user_name)
        
        if len(existing_keys) >= 2:
            iam_client.delete_access_key(UserName=user_name, AccessKeyId=old_key_id)
        
        response = iam_client.create_access_key(UserName=user_name)
        new_key = response['AccessKey']
        
        if len(existing_keys) < 2:
            iam_client.delete_access_key(UserName=user_name, AccessKeyId=old_key_id)
        
        return {
            'success': True,
            'new_key_id': new_key['AccessKeyId'],
            'new_secret_key': new_key['SecretAccessKey'],
            'old_key_id': old_key_id,
            'dry_run': False
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'old_key_id': old_key_id
        }


def store_in_secrets_manager(user_name, access_key_id, secret_access_key):
    """Store the new access key in AWS Secrets Manager"""
    secret_name = f"iam-user/{user_name}/access-key"
    
    secret_value = {
        'AccessKeyId': access_key_id,
        'SecretAccessKey': secret_access_key,
        'UserName': user_name,
        'CreatedAt': datetime.now(timezone.utc).isoformat()
    }
    
    try:
        # Try to update existing secret
        response = secrets_client.put_secret_value(
            SecretId=secret_name,
            SecretString=json.dumps(secret_value)
        )
        logger.info(f"Updated secret: {secret_name}")
        return response['ARN']
        
    except secrets_client.exceptions.ResourceNotFoundException:
        # Create new secret if it doesn't exist
        response = secrets_client.create_secret(
            Name=secret_name,
            Description=f"IAM access key for user {user_name}",
            SecretString=json.dumps(secret_value),
            Tags=[
                {'Key': 'User', 'Value': user_name},
                {'Key': 'ManagedBy', 'Value': 'AccessKeyRotationLambda'},
                {'Key': 'CreatedAt', 'Value': datetime.now(timezone.utc).isoformat()}
            ]
        )
        logger.info(f"Created secret: {secret_name}")
        return response['ARN']


def send_notification(results):
    message_lines = [
        "IAM Access Key Rotation Report (with Secrets Manager)",
        "=" * 60,
        "",
        f"Rotation Threshold: {ROTATION_DAYS} days",
        f"Dry Run Mode: {'Yes' if DRY_RUN else 'No'}",
        f"Secrets Manager Storage: {'Enabled' if STORE_IN_SECRETS_MANAGER else 'Disabled'}",
        f"Execution Time: {datetime.now(timezone.utc).isoformat()}",
        "",
        "Summary:",
        f"  - Users Checked: {results['users_checked']}",
        f"  - Keys Checked: {results['keys_checked']}",
        f"  - Keys Rotated: {results['keys_rotated']}",
        f"  - Secrets Created/Updated: {results['secrets_created']}",
        f"  - Errors: {len(results['errors'])}",
        "",
    ]
    
    if results['rotation_details']:
        message_lines.append("Rotated Keys:")
        message_lines.append("-" * 60)
        for detail in results['rotation_details']:
            message_lines.extend([
                f"  User: {detail['user']}",
                f"  Old Key: {detail['old_key_id']}",
                f"  New Key: {detail.get('new_key_id', 'N/A')}",
                f"  Secret ARN: {detail.get('secret_arn', 'N/A')}",
                f"  Age: {detail['key_age_days']} days",
                ""
            ])
    
    if results['errors']:
        message_lines.append("Errors:")
        message_lines.append("-" * 60)
        for error in results['errors']:
            message_lines.extend([
                f"  User: {error.get('user', 'N/A')}",
                f"  Error: {error.get('error')}",
                ""
            ])
    
    message = "\\n".join(message_lines)
    
    if results['keys_rotated'] > 0:
        subject = f"IAM Access Key Rotation: {results['keys_rotated']} Keys Rotated"
    else:
        subject = "IAM Access Key Rotation: No Action Needed"
    
    try:
        response = sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=subject,
            Message=message
        )
        logger.info(f"Notification sent. MessageId: {response['MessageId']}")
    except Exception as e:
        logger.error(f"Error sending notification: {str(e)}")


def send_error_notification(error_message):
    try:
        message = f"""
IAM Access Key Rotation - ERROR

{error_message}

Timestamp: {datetime.now(timezone.utc).isoformat()}
"""
        sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject="ERROR: IAM Access Key Rotation Failed",
            Message=message
        )
    except Exception as e:
        logger.error(f"Error sending error notification: {str(e)}")
'''

