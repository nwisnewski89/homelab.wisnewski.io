#!/usr/bin/env python3
"""
AWS CDK Stack for Serverless Aurora Database

This stack creates a serverless Aurora database with:
- Multi-AZ replication for high availability
- Point-in-time recovery enabled
- Enhanced CloudWatch logging
- VPC with isolated subnets for database
- Security groups for database access
- Secrets Manager for credential management
"""

from aws_cdk import (
    Stack,
    CfnOutput,
    Duration,
    RemovalPolicy,
    aws_ec2 as ec2,
    aws_rds as rds,
    aws_logs as logs,
    aws_lambda as _lambda,
    aws_iam as iam,
    aws_s3 as s3,
    custom_resources as cr,
)
from constructs import Construct
import os


class AuroraServerlessStack(Stack):
    """
    Stack that creates a serverless Aurora database with multi-AZ, 
    point-in-time recovery, and enhanced CloudWatch logging
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        database_name: str = "auroradatabase",
        engine: rds.DatabaseClusterEngine = None,
        enable_performance_insights: bool = True,
        schema_s3_bucket: str = None,
        schema_s3_key: str = None,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Default to Aurora PostgreSQL if no engine specified
        if engine is None:
            engine = rds.DatabaseClusterEngine.aurora_postgres(
                version=rds.AuroraPostgresEngineVersion.VER_15_4
            )

        # Create VPC with multi-AZ support
        self.vpc = self.create_vpc()

        # Create security group for Aurora
        self.db_security_group = self.create_security_group()

        # Create serverless Aurora cluster
        # Note: CloudWatch log groups are created automatically when cloudwatch_logs_exports is specified
        self.aurora_cluster = self.create_aurora_cluster(
            database_name=database_name,
            engine=engine,
            enable_performance_insights=enable_performance_insights,
        )

        # Create schema import custom resource if S3 location provided
        if schema_s3_bucket and schema_s3_key:
            self.create_schema_import(
                database_name=database_name,
                s3_bucket=schema_s3_bucket,
                s3_key=schema_s3_key,
                engine=engine,
            )

        # Create outputs
        self.create_outputs()

    def create_vpc(self) -> ec2.Vpc:
        """Create VPC with multi-AZ configuration"""
        return ec2.Vpc(
            self,
            "AuroraVpc",
            max_azs=3,  # Multi-AZ across 3 availability zones
            nat_gateways=1,  # Single NAT gateway (increase for production)
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="isolated",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
        )

    def create_security_group(self) -> ec2.SecurityGroup:
        """Create security group for Aurora database"""
        return ec2.SecurityGroup(
            self,
            "AuroraSecurityGroup",
            vpc=self.vpc,
            description="Security group for Aurora serverless cluster",
            allow_all_outbound=False,
        )

    def create_aurora_cluster(
        self,
        database_name: str,
        engine: rds.DatabaseClusterEngine,
        enable_performance_insights: bool,
    ) -> rds.DatabaseCluster:
        """
        Create serverless Aurora cluster with all required features:
        - Multi-AZ replication (writer + reader instances)
        - Point-in-time recovery (enabled via backup retention)
        - Enhanced CloudWatch logging
        """
        # Create serverless v2 Aurora cluster
        # Determine log export types based on engine family
        # Check engine family: 'aurora-postgresql' or 'aurora-mysql'
        engine_family = engine.engine_family
        if engine_family == rds.DatabaseClusterEngineFamily.AURORA_POSTGRESQL:
            log_exports = [
                rds.CloudwatchLogsExportType.POSTGRESQL,
                rds.CloudwatchLogsExportType.UPGRADE,
            ]
        else:
            # Default to MySQL log types
            log_exports = [
                rds.CloudwatchLogsExportType.MYSQL,
                rds.CloudwatchLogsExportType.GENERAL,
                rds.CloudwatchLogsExportType.SLOW_QUERY,
                rds.CloudwatchLogsExportType.ERROR,
            ]

        cluster = rds.DatabaseCluster(
            self,
            "AuroraServerlessCluster",
            engine=engine,
            cluster_identifier=f"{self.stack_name}-aurora-cluster",
            database_name=database_name,
            
            # Serverless v2 configuration - Multi-AZ is achieved by having writer + reader
            writer=rds.ClusterInstance.serverless_v2(
                "writer",
                scale_with_writer=True,
            ),
            # Add reader instance in different AZ for multi-AZ replication
            readers=[
                rds.ClusterInstance.serverless_v2(
                    "reader",
                    scale_with_writer=True,
                ),
            ],
            
            # Serverless v2 capacity configuration
            serverless_v2_min_capacity=rds.AuroraCapacityUnit.ACU_0_5,  # Minimum 0.5 ACU
            serverless_v2_max_capacity=rds.AuroraCapacityUnit.ACU_16,   # Maximum 16 ACU
            
            # VPC and networking
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            security_groups=[self.db_security_group],
            
            # Backup and point-in-time recovery
            backup=rds.BackupProps(
                retention=Duration.days(7),  # 7-day backup retention (required for PITR)
                preferred_window="03:00-04:00",  # Backup window in UTC
            ),
            # Point-in-time recovery is automatically enabled with backup retention > 0
            
            # Enhanced CloudWatch logging
            cloudwatch_logs_exports=log_exports,
            cloudwatch_logs_retention=logs.RetentionDays.ONE_MONTH,
            
            # Performance Insights
            enable_performance_insights=enable_performance_insights,
            
            # Encryption at rest
            storage_encrypted=True,
            
            # Removal policy (change for production)
            removal_policy=RemovalPolicy.DESTROY,  # Use RETAIN for production
            
            # Deletion protection (enable for production)
            deletion_protection=False,  # Set to True for production
            
            # Monitoring
            monitoring_interval=Duration.seconds(60),
        )

        return cluster

    def create_schema_import(
        self,
        database_name: str,
        s3_bucket: str,
        s3_key: str,
        engine: rds.DatabaseClusterEngine,
    ) -> None:
        """
        Create a Custom Resource that imports database schema from S3.
        
        This uses a Lambda function to:
        1. Download SQL file from S3
        2. Connect to Aurora database
        3. Execute the SQL schema
        """
        # Determine database port based on engine
        if engine.engine_family == rds.DatabaseClusterEngineFamily.AURORA_POSTGRESQL:
            db_port = 5432
            # Note: For PostgreSQL, you'd need psycopg2 instead of pymysql
            # This example focuses on MySQL
            raise ValueError("PostgreSQL schema import not yet implemented. Use MySQL engine.")
        else:
            db_port = 3306
        
        # Create security group for Lambda
        lambda_security_group = ec2.SecurityGroup(
            self,
            "SchemaImportLambdaSecurityGroup",
            vpc=self.vpc,
            description="Security group for schema import Lambda",
            allow_all_outbound=True,
        )
        
        # Create Lambda function for schema import
        schema_import_lambda = _lambda.Function(
            self,
            "SchemaImportLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="lambda_function.lambda_handler",
            code=_lambda.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "lambda_schema_import")
            ),
            timeout=Duration.minutes(15),
            memory_size=512,
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[lambda_security_group],
            environment={
                "PYTHONUNBUFFERED": "1",
            },
        )
        
        # Allow Lambda to access S3 bucket
        if s3_bucket.startswith("arn:"):
            # If bucket is specified as ARN, grant permissions to that bucket
            bucket = s3.Bucket.from_bucket_arn(self, "SchemaS3Bucket", s3_bucket)
        else:
            # If bucket is specified as name, grant permissions to that bucket
            bucket = s3.Bucket.from_bucket_name(self, "SchemaS3Bucket", s3_bucket)
        
        bucket.grant_read(schema_import_lambda)
        
        # Allow Lambda to read from Secrets Manager
        schema_import_lambda.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "secretsmanager:GetSecretValue",
                    "secretsmanager:DescribeSecret",
                ],
                resources=[self.aurora_cluster.secret.secret_arn],
            )
        )
        
        # Allow Lambda to connect to database
        # Add ingress rule to Aurora security group to allow Lambda
        self.db_security_group.add_ingress_rule(
            peer=lambda_security_group,
            connection=ec2.Port.tcp(db_port),
            description="Allow schema import Lambda to access Aurora",
        )
        
        # Create Custom Resource provider
        provider = cr.Provider(
            self,
            "SchemaImportProvider",
            on_event_handler=schema_import_lambda,
        )
        
        # Create Custom Resource
        schema_import_resource = cr.CustomResource(
            self,
            "SchemaImportResource",
            service_token=provider.service_token,
            properties={
                "S3Bucket": s3_bucket,
                "S3Key": s3_key,
                "SecretArn": self.aurora_cluster.secret.secret_arn,
                "ClusterEndpoint": self.aurora_cluster.cluster_endpoint.hostname,
                "Port": str(db_port),
                "DatabaseName": database_name,
            },
        )
        
        # Ensure schema import happens after cluster is ready
        schema_import_resource.node.add_dependency(self.aurora_cluster)

    def create_outputs(self) -> None:
        """Create CloudFormation outputs"""
        CfnOutput(
            self,
            "ClusterEndpoint",
            value=self.aurora_cluster.cluster_endpoint.hostname,
            description="Aurora cluster endpoint",
        )

        CfnOutput(
            self,
            "ClusterReadEndpoint",
            value=self.aurora_cluster.cluster_read_endpoint.hostname,
            description="Aurora cluster read endpoint",
        )

        CfnOutput(
            self,
            "SecretArn",
            value=self.aurora_cluster.secret.secret_arn,
            description="ARN of the secret containing database credentials",
        )

        CfnOutput(
            self,
            "VpcId",
            value=self.vpc.vpc_id,
            description="VPC ID where Aurora is deployed",
        )

        CfnOutput(
            self,
            "SecurityGroupId",
            value=self.db_security_group.security_group_id,
            description="Security group ID for Aurora cluster",
        )


# Example usage in an app:
"""
from aws_cdk import App, Environment
import aws_cdk.aws_rds as rds

app = App()

# For Aurora PostgreSQL (default)
AuroraServerlessStack(
    app,
    "AuroraServerlessPostgresStack",
    database_name="mydatabase",
    # engine defaults to Aurora PostgreSQL 15.4
    env=Environment(account="123456789012", region="us-east-1")
)

# For Aurora MySQL - specify the version
AuroraServerlessStack(
    app,
    "AuroraServerlessMysqlStack",
    database_name="mydatabase",
    engine=rds.DatabaseClusterEngine.aurora_mysql(
        version=rds.AuroraMysqlEngineVersion.VER_3_10_0  # MySQL 8.0.42 compatible (LTS)
        # Or use: VER_3_04_0 for older MySQL 8.0 compatible version
    ),
    env=Environment(account="123456789012", region="us-east-1")
)

# For Aurora MySQL with schema import from S3
# The schema SQL file will be automatically imported during stack deployment
AuroraServerlessStack(
    app,
    "AuroraServerlessMysqlWithSchemaStack",
    database_name="mydatabase",
    engine=rds.DatabaseClusterEngine.aurora_mysql(
        version=rds.AuroraMysqlEngineVersion.VER_3_10_0
    ),
    schema_s3_bucket="my-schema-bucket",  # S3 bucket containing schema SQL file
    schema_s3_key="schema/initial-schema.sql",  # Path to SQL file in S3
    env=Environment(account="123456789012", region="us-east-1")
)

# Common Aurora MySQL versions available:
# - rds.AuroraMysqlEngineVersion.VER_3_10_0 (Aurora MySQL 3.10.0, compatible with MySQL 8.0.42 - LTS release)
# - rds.AuroraMysqlEngineVersion.VER_3_04_0 (Aurora MySQL 3.04.0, compatible with MySQL 8.0)
# - rds.AuroraMysqlEngineVersion.VER_3_03_0 (Aurora MySQL 3.03.0)
# - rds.AuroraMysqlEngineVersion.VER_3_02_0 (Aurora MySQL 3.02.0)
# - rds.AuroraMysqlEngineVersion.VER_2_12_0 (Aurora MySQL 2.12.0, compatible with MySQL 5.7)
# - rds.AuroraMysqlEngineVersion.VER_2_11_0 (Aurora MySQL 2.11.0)
# - rds.AuroraMysqlEngineVersion.VER_2_10_0 (Aurora MySQL 2.10.0)
# - rds.AuroraMysqlEngineVersion.VER_2_09_0 (Aurora MySQL 2.09.0)
# 
# To see all available versions in your CDK environment, you can:
# 1. Use IDE autocomplete: rds.AuroraMysqlEngineVersion.VER_
# 2. Check AWS CDK documentation: https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_rds/AuroraMysqlEngineVersion.html
# 3. List available versions programmatically or check AWS RDS console

app.synth()
"""

