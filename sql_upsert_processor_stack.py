#!/usr/bin/env python3

import aws_cdk as cdk
from aws_cdk import (
    Stack,
    aws_s3 as s3,
    aws_sqs as sqs,
    aws_lambda as _lambda,
    aws_rds as rds,
    aws_ec2 as ec2,
    aws_s3_notifications as s3n,
    aws_lambda_event_sources as lambda_event_sources,
    aws_iam as iam,
    aws_secretsmanager as secretsmanager,
    Duration,
    RemovalPolicy,
    SecretValue,
)
from constructs import Construct


class SqlUpsertProcessorStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create VPC for RDS
        self.vpc = ec2.Vpc(
            self, "SqlUpsertVPC",
            max_azs=2,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24
                ),
                ec2.SubnetConfiguration(
                    name="private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24
                ),
                ec2.SubnetConfiguration(
                    name="isolated",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24
                )
            ]
        )

        # Create S3 bucket for SQL tar files
        self.bucket = s3.Bucket(
            self, "SqlUpsertBucket",
            bucket_name=f"sql-upsert-bucket-{self.account}-{self.region}",
            versioned=True,
            removal_policy=RemovalPolicy.DESTROY,  # For demo purposes
            auto_delete_objects=True,  # For demo purposes
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="DeleteOldVersions",
                    noncurrent_version_expiration=Duration.days(30),
                    enabled=True
                )
            ]
        )

        # Create SQS queues
        self.dlq = sqs.Queue(
            self, "SqlUpsertDLQ",
            queue_name="sql-upsert-dlq",
            retention_period=Duration.days(14)
        )

        self.queue = sqs.Queue(
            self, "SqlUpsertQueue",
            queue_name="sql-upsert-queue",
            visibility_timeout=Duration.minutes(15),  # Lambda timeout + buffer
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=self.dlq
            )
        )

        # Create RDS security group
        self.rds_security_group = ec2.SecurityGroup(
            self, "RDSSecurityGroup",
            vpc=self.vpc,
            description="Security group for RDS MySQL instance",
            allow_all_outbound=False
        )

        # Create Lambda security group
        self.lambda_security_group = ec2.SecurityGroup(
            self, "LambdaSecurityGroup",
            vpc=self.vpc,
            description="Security group for Lambda function",
            allow_all_outbound=True
        )

        # Allow Lambda to connect to RDS
        self.rds_security_group.add_ingress_rule(
            peer=self.lambda_security_group,
            connection=ec2.Port.tcp(3306),
            description="Allow Lambda to connect to MySQL"
        )

        # Create RDS subnet group
        self.db_subnet_group = rds.SubnetGroup(
            self, "RDSSubnetGroup",
            description="Subnet group for RDS MySQL instance",
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            )
        )

        # Create RDS parameter group for IAM authentication
        self.parameter_group = rds.ParameterGroup(
            self, "MySQLParameterGroup",
            engine=rds.DatabaseInstanceEngine.mysql(
                version=rds.MysqlEngineVersion.VER_8_0_35
            ),
            parameters={
                "rds.force_ssl": "1"
            }
        )

        # Create database credentials secret
        self.db_secret = secretsmanager.Secret(
            self, "RDSSecret",
            description="RDS MySQL master credentials",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"username": "admin"}',
                generate_string_key="password",
                exclude_characters=" %+~`#$&*()|[]{}:;<>?!'/\"\\",
                password_length=32
            )
        )

        # Create RDS MySQL instance
        self.database = rds.DatabaseInstance(
            self, "MySQLDatabase",
            engine=rds.DatabaseInstanceEngine.mysql(
                version=rds.MysqlEngineVersion.VER_8_0_35
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.BURSTABLE3, 
                ec2.InstanceSize.MICRO
            ),
            vpc=self.vpc,
            subnet_group=self.db_subnet_group,
            security_groups=[self.rds_security_group],
            credentials=rds.Credentials.from_secret(self.db_secret),
            database_name="upsertdb",
            allocated_storage=20,
            max_allocated_storage=100,
            storage_encrypted=True,
            multi_az=False,  # For cost optimization in demo
            parameter_group=self.parameter_group,
            iam_authentication=True,  # Enable IAM authentication
            backup_retention=Duration.days(7),
            deletion_protection=False,  # For demo purposes
            removal_policy=RemovalPolicy.DESTROY  # For demo purposes
        )

        # Create Lambda execution role with enhanced permissions
        self.lambda_role = iam.Role(
            self, "SqlUpsertLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaVPCAccessExecutionRole")
            ]
        )

        # Add RDS IAM authentication policy
        self.lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "rds-db:connect"
                ],
                resources=[
                    f"arn:aws:rds-db:{self.region}:{self.account}:dbuser:{self.database.instance_resource_id}/*"
                ]
            )
        )

        # Add Secrets Manager permissions
        self.lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "secretsmanager:GetSecretValue",
                    "secretsmanager:DescribeSecret"
                ],
                resources=[self.db_secret.secret_arn]
            )
        )

        # Create Lambda function
        self.lambda_function = _lambda.Function(
            self, "SqlUpsertFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="lambda_function.lambda_handler",
            code=_lambda.Code.from_asset("lambda_sql_upsert"),
            timeout=Duration.minutes(15),
            memory_size=1024,
            role=self.lambda_role,
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_groups=[self.lambda_security_group],
            environment={
                "BUCKET_NAME": self.bucket.bucket_name,
                "QUEUE_URL": self.queue.queue_url,
                "DB_ENDPOINT": self.database.instance_endpoint.hostname,
                "DB_PORT": str(self.database.instance_endpoint.port),
                "DB_NAME": "upsertdb",
                "DB_SECRET_ARN": self.db_secret.secret_arn,
                "DB_RESOURCE_ID": self.database.instance_resource_id
            }
        )

        # Grant S3 permissions to Lambda
        self.bucket.grant_read_write(self.lambda_function)

        # Grant SQS permissions to Lambda
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
            s3.NotificationKeyFilter(suffix=".tar")
        )

        # Also listen for .tar.gz files
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
            description="Name of the S3 bucket for SQL tar files"
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

        cdk.CfnOutput(
            self, "DatabaseEndpoint",
            value=self.database.instance_endpoint.hostname,
            description="RDS MySQL database endpoint"
        )

        cdk.CfnOutput(
            self, "DatabaseSecretArn",
            value=self.db_secret.secret_arn,
            description="ARN of the database credentials secret"
        )

        cdk.CfnOutput(
            self, "DatabaseResourceId",
            value=self.database.instance_resource_id,
            description="RDS instance resource ID for IAM authentication"
        )

        cdk.CfnOutput(
            self, "VPCId",
            value=self.vpc.vpc_id,
            description="VPC ID"
        )
