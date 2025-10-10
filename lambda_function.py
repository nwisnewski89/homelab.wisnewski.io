#!/usr/bin/env python3
"""
CDK Stack for generating IAM Access Keys and sending details to SNS
This uses a Custom Resource Lambda to publish actual key values (not tokens) to SNS.
"""

from aws_cdk import (
    Stack,
    aws_iam as iam,
    aws_sns as sns,
    aws_sns_subscriptions as sns_subs,
    aws_lambda as lambda_,
    CustomResource,
    Duration,
    CfnOutput,
    custom_resources as cr,
)
from constructs import Construct
import json


class AccessKeySnsNotificationStack(Stack):
    """CDK Stack that creates IAM access keys and sends details to SNS"""

    def __init__(
        self, 
        scope: Construct, 
        construct_id: str,
        email_address: str = "admin@example.com",
        user_name: str = "cdk-notification-user",
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create SNS topic
        self.topic = sns.Topic(
            self, "AccessKeyNotificationTopic",
            display_name="IAM Access Key Notifications",
            topic_name="iam-access-key-notifications"
        )

        # Add email subscription
        self.topic.add_subscription(
            sns_subs.EmailSubscription(email_address)
        )

        # Create IAM user
        self.user = iam.User(
            self, "NotificationUser",
            user_name=user_name,
            description="User created by CDK with SNS notification"
        )

        # Create access key for the user
        self.access_key = iam.AccessKey(
            self, "NotificationUserAccessKey",
            user=self.user,
            description="Access key for notification user"
        )

        # Add some policies to the user
        self.user.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonS3ReadOnlyAccess")
        )

        # Create the Lambda function that will publish to SNS
        notification_lambda = lambda_.Function(
            self, "AccessKeyNotificationFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=lambda_.Code.from_inline(self._get_lambda_code()),
            timeout=Duration.seconds(30),
            description="Publishes access key details to SNS topic"
        )

        # Grant the Lambda permission to publish to SNS
        self.topic.grant_publish(notification_lambda)

        # Create Custom Resource Provider
        provider = cr.Provider(
            self, "AccessKeyNotificationProvider",
            on_event_handler=notification_lambda
        )

        # Create Custom Resource that triggers the Lambda
        # The Lambda will receive the actual access key values
        custom_resource = CustomResource(
            self, "AccessKeyNotificationCustomResource",
            service_token=provider.service_token,
            properties={
                "TopicArn": self.topic.topic_arn,
                "UserName": self.user.user_name,
                "AccessKeyId": self.access_key.access_key_id,
                "SecretAccessKey": self.access_key.secret_access_key.unsafe_unwrap(),
                # Trigger update on every deployment
                "Timestamp": self.node.try_get_context("timestamp") or "default"
            }
        )

        # Make sure the custom resource runs after the access key is created
        custom_resource.node.add_dependency(self.access_key)

        # Outputs
        CfnOutput(
            self, "TopicArn",
            value=self.topic.topic_arn,
            description="ARN of the SNS topic for access key notifications"
        )

        CfnOutput(
            self, "UserName",
            value=self.user.user_name,
            description="Name of the IAM user created"
        )

        CfnOutput(
            self, "AccessKeyId",
            value=self.access_key.access_key_id,
            description="Access Key ID (also sent to SNS)"
        )

    def _get_lambda_code(self) -> str:
        """Returns the inline Lambda code for publishing to SNS"""
        return '''
import json
import boto3
import logging
from datetime import datetime

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sns_client = boto3.client('sns')

def handler(event, context):
    """
    Custom Resource handler that publishes access key details to SNS
    """
    logger.info(f"Received event: {json.dumps(event, default=str)}")
    
    request_type = event['RequestType']
    
    # Only send notification on Create and Update
    if request_type in ['Create', 'Update']:
        try:
            # Extract properties from the event
            props = event['ResourceProperties']
            topic_arn = props['TopicArn']
            user_name = props['UserName']
            access_key_id = props['AccessKeyId']
            secret_access_key = props['SecretAccessKey']
            
            # Create the message with access key details
            message_data = {
                "username": user_name,
                "access_key_id": access_key_id,
                "secret_access_key": secret_access_key,
                "create_date": datetime.utcnow().isoformat() + "Z"
            }
            
            # Create a formatted message for email
            email_message = f"""
IAM Access Key Created
======================

User Name: {user_name}
Access Key ID: {access_key_id}
Secret Access Key: {secret_access_key}
Create Date: {message_data['create_date']}

IMPORTANT: Store these credentials securely. The secret access key will not be shown again.

Configure AWS CLI:
------------------
aws configure set aws_access_key_id {access_key_id}
aws configure set aws_secret_access_key {secret_access_key}

Or set environment variables:
-----------------------------
export AWS_ACCESS_KEY_ID={access_key_id}
export AWS_SECRET_ACCESS_KEY={secret_access_key}
"""
            
            # Publish to SNS with both JSON and formatted text
            response = sns_client.publish(
                TopicArn=topic_arn,
                Subject=f"New IAM Access Key Created: {user_name}",
                Message=email_message,
                MessageAttributes={
                    'username': {'DataType': 'String', 'StringValue': user_name},
                    'access_key_id': {'DataType': 'String', 'StringValue': access_key_id},
                    'create_date': {'DataType': 'String', 'StringValue': message_data['create_date']}
                }
            )
            
            logger.info(f"Successfully published to SNS. MessageId: {response['MessageId']}")
            logger.info(f"Message data: {json.dumps(message_data)}")
            
            return {
                'PhysicalResourceId': f"AccessKeyNotification-{user_name}",
                'Data': {
                    'MessageId': response['MessageId']
                }
            }
            
        except Exception as e:
            logger.error(f"Error publishing to SNS: {str(e)}")
            raise
    
    elif request_type == 'Delete':
        logger.info("Delete request - no action needed")
        return {
            'PhysicalResourceId': event.get('PhysicalResourceId', 'AccessKeyNotification')
        }
    
    return {
        'PhysicalResourceId': event.get('PhysicalResourceId', 'AccessKeyNotification')
    }
'''


class AccessKeySnsNotificationWithJsonStack(Stack):
    """
    Alternative stack that sends pure JSON to SNS (useful for Lambda subscribers)
    """

    def __init__(
        self, 
        scope: Construct, 
        construct_id: str,
        email_address: str = "admin@example.com",
        user_name: str = "cdk-json-notification-user",
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create SNS topic
        self.topic = sns.Topic(
            self, "AccessKeyJsonTopic",
            display_name="IAM Access Key JSON Notifications",
            topic_name="iam-access-key-json-notifications"
        )

        # Add email subscription
        self.topic.add_subscription(
            sns_subs.EmailSubscription(email_address)
        )

        # Create IAM user
        self.user = iam.User(
            self, "JsonNotificationUser",
            user_name=user_name,
            description="User created by CDK with JSON SNS notification"
        )

        # Create access key
        self.access_key = iam.AccessKey(
            self, "JsonNotificationAccessKey",
            user=self.user
        )

        # Lambda for JSON notification
        notification_lambda = lambda_.Function(
            self, "JsonNotificationFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=lambda_.Code.from_inline(self._get_json_lambda_code()),
            timeout=Duration.seconds(30)
        )

        self.topic.grant_publish(notification_lambda)

        # Custom Resource Provider
        provider = cr.Provider(
            self, "JsonNotificationProvider",
            on_event_handler=notification_lambda
        )

        # Custom Resource
        custom_resource = CustomResource(
            self, "JsonNotificationCustomResource",
            service_token=provider.service_token,
            properties={
                "TopicArn": self.topic.topic_arn,
                "UserName": self.user.user_name,
                "AccessKeyId": self.access_key.access_key_id,
                "SecretAccessKey": self.access_key.secret_access_key.unsafe_unwrap(),
                "Timestamp": self.node.try_get_context("timestamp") or "default"
            }
        )

        custom_resource.node.add_dependency(self.access_key)

        # Outputs
        CfnOutput(
            self, "TopicArn",
            value=self.topic.topic_arn,
            description="ARN of the SNS topic"
        )

        CfnOutput(
            self, "UserName",
            value=self.user.user_name,
            description="IAM user name"
        )

    def _get_json_lambda_code(self) -> str:
        """Returns Lambda code that sends pure JSON to SNS"""
        return '''
import json
import boto3
import logging
from datetime import datetime

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sns_client = boto3.client('sns')

def handler(event, context):
    """Publishes access key details as JSON to SNS"""
    logger.info(f"Received event: {json.dumps(event, default=str)}")
    
    request_type = event['RequestType']
    
    if request_type in ['Create', 'Update']:
        try:
            props = event['ResourceProperties']
            
            # Create JSON message
            message_data = {
                "username": props['UserName'],
                "access_key_id": props['AccessKeyId'],
                "secret_access_key": props['SecretAccessKey'],
                "create_date": datetime.utcnow().isoformat() + "Z",
                "event_type": "access_key_created"
            }
            
            # Publish as pure JSON
            response = sns_client.publish(
                TopicArn=props['TopicArn'],
                Subject=f"IAM Access Key Created: {props['UserName']}",
                Message=json.dumps(message_data, indent=2)
            )
            
            logger.info(f"Published to SNS. MessageId: {response['MessageId']}")
            logger.info(f"Message: {json.dumps(message_data, indent=2)}")
            
            return {
                'PhysicalResourceId': f"JsonNotification-{props['UserName']}",
                'Data': {'MessageId': response['MessageId']}
            }
            
        except Exception as e:
            logger.error(f"Error: {str(e)}")
            raise
    
    return {'PhysicalResourceId': event.get('PhysicalResourceId', 'JsonNotification')}
'''

