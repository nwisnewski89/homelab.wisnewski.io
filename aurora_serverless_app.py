#!/usr/bin/env python3
"""
CDK App for Aurora Serverless Database Stack

This is the entry point for deploying a serverless Aurora database with:
- Multi-AZ replication
- Point-in-time recovery
- Enhanced CloudWatch logging

Usage:
    # Deploy with default settings (Aurora PostgreSQL)
    cdk deploy AuroraServerlessStack
    
    # Deploy with Aurora MySQL
    cdk deploy AuroraServerlessMysqlStack
    
    # Deploy with custom database name
    cdk deploy AuroraServerlessStack --context databaseName=mydatabase
"""

from aws_cdk import App, Environment
import aws_cdk.aws_rds as rds
from aurora_serverless_stack import AuroraServerlessStack


def main():
    """Main application entry point"""
    app = App()

    # Get configuration from context
    database_name = app.node.try_get_context("databaseName") or "auroradatabase"
    engine_type = app.node.try_get_context("engineType") or "postgres"  # postgres or mysql
    
    # Get account and region from context or use defaults
    account = app.node.try_get_context("account")
    region = app.node.try_get_context("region") or "us-east-1"

    # Create environment
    env = Environment(account=account, region=region) if account else None

    # Create Aurora PostgreSQL stack (default)
    if engine_type.lower() == "postgres" or engine_type.lower() == "postgresql":
        AuroraServerlessStack(
            app,
            "AuroraServerlessStack",
            description="Serverless Aurora PostgreSQL cluster with multi-AZ, PITR, and CloudWatch logging",
            database_name=database_name,
            # engine defaults to Aurora PostgreSQL 15.4
            env=env,
        )
    else:
        # Create Aurora MySQL stack
        AuroraServerlessStack(
            app,
            "AuroraServerlessMysqlStack",
            description="Serverless Aurora MySQL cluster with multi-AZ, PITR, and CloudWatch logging",
            database_name=database_name,
            engine=rds.DatabaseClusterEngine.aurora_mysql(
                version=rds.AuroraMysqlEngineVersion.VER_3_04_0
            ),
            env=env,
        )

    app.synth()


if __name__ == "__main__":
    main()

