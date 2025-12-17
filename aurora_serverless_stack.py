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
)
from constructs import Construct


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

# For Aurora MySQL
AuroraServerlessStack(
    app,
    "AuroraServerlessMysqlStack",
    database_name="mydatabase",
    engine=rds.DatabaseClusterEngine.aurora_mysql(
        version=rds.AuroraMysqlEngineVersion.VER_3_04_0
    ),
    env=Environment(account="123456789012", region="us-east-1")
)

app.synth()
"""

