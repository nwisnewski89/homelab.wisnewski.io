#!/usr/bin/env python3

import aws_cdk as cdk
from aws_cdk import (
    Stack,
    aws_s3 as s3,
    aws_sqs as sqs,
    aws_lambda as _lambda,
    aws_s3_notifications as s3n,
    aws_lambda_event_sources as lambda_event_sources,
    aws_iam as iam,
    Duration,
    RemovalPolicy,
)
from constructs import Construct


class S3TarProcessorStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create S3 bucket
        self.bucket = s3.Bucket(
            self, "TarProcessorBucket",
            bucket_name=f"tar-processor-bucket-{self.account}-{self.region}",
            versioned=True,
            removal_policy=RemovalPolicy.DESTROY,  # For demo purposes
            auto_delete_objects=True,  # For demo purposes
        )

        # Create SQS queue for S3 notifications
        self.dlq = sqs.Queue(
            self, "TarProcessorDLQ",
            queue_name="tar-processor-dlq",
            retention_period=Duration.days(14)
        )

        self.queue = sqs.Queue(
            self, "TarProcessorQueue",
            queue_name="tar-processor-queue",
            visibility_timeout=Duration.minutes(15),  # Lambda timeout + buffer
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=self.dlq
            )
        )

        # Create Lambda function
        self.lambda_function = _lambda.Function(
            self, "TarProcessorFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="lambda_function.lambda_handler",
            code=_lambda.Code.from_asset("lambda"),
            timeout=Duration.minutes(15),
            memory_size=1024,
            environment={
                "BUCKET_NAME": self.bucket.bucket_name,
                "QUEUE_URL": self.queue.queue_url,
            }
        )

        # Grant permissions
        self.bucket.grant_read_write(self.lambda_function)
        self.queue.grant_consume_messages(self.lambda_function)

        # Add additional IAM permissions for Lambda
        self.lambda_function.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:DeleteObject",
                    "s3:ListBucket"
                ],
                resources=[
                    self.bucket.bucket_arn,
                    f"{self.bucket.bucket_arn}/*"
                ]
            )
        )

        # Configure S3 bucket notifications to SQS
        self.bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.SqsDestination(self.queue),
            s3.NotificationKeyFilter(suffix=".tar.gz")
        )

        # Add SQS as event source for Lambda
        self.lambda_function.add_event_source(
            lambda_event_sources.SqsEventSource(
                self.queue,
                batch_size=1,  # Process one message at a time
                report_batch_item_failures=True
            )
        )

        # Outputs
        cdk.CfnOutput(
            self, "BucketName",
            value=self.bucket.bucket_name,
            description="Name of the S3 bucket"
        )

        cdk.CfnOutput(
            self, "QueueUrl",
            value=self.queue.queue_url,
            description="URL of the SQS queue"
        )

        cdk.CfnOutput(
            self, "LambdaFunctionName",
            value=self.lambda_function.function_name,
            description="Name of the Lambda function"
        )
