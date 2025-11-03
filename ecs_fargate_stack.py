#!/usr/bin/env python3

import aws_cdk as cdk
from aws_cdk import (
    Stack,
    aws_ecs as ecs,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_logs as logs,
    Duration,
    RemovalPolicy,
)
from constructs import Construct


class EcsFargateStack(Stack):
    """ECS Cluster with Fargate Spot enabled and ECS task definition"""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create VPC for ECS
        self.vpc = ec2.Vpc(
            self, "EcsVPC",
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
                )
            ]
        )

        # Create CloudWatch log group
        self.log_group = logs.LogGroup(
            self, "EcsLogGroup",
            log_group_name="/ecs/fargate-task",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY
        )

        # Create ECS cluster with Fargate Spot capacity providers enabled
        # This automatically enables both FARGATE and FARGATE_SPOT capacity providers
        self.cluster = ecs.Cluster(
            self, "EcsCluster",
            cluster_name="fargate-spot-cluster",
            vpc=self.vpc
        )
        
        # Enable Fargate capacity providers (FARGATE and FARGATE_SPOT)
        self.cluster.enable_fargate_capacity_providers()

        # Create ECS task execution role (for pulling images, writing logs, etc.)
        self.task_execution_role = iam.Role(
            self, "TaskExecutionRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                )
            ],
            description="Role for ECS task execution (pulling images, writing logs)"
        )

        # Grant CloudWatch Logs permissions to task execution role
        self.log_group.grant_write(self.task_execution_role)

        # Create ECS task role (for the application running in the container)
        self.task_role = iam.Role(
            self, "TaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            description="Role for the application running in the ECS task"
        )

        # Create Fargate task definition
        self.task_definition = ecs.FargateTaskDefinition(
            self, "FargateTaskDefinition",
            memory_limit_mib=512,
            cpu=256,
            execution_role=self.task_execution_role,
            task_role=self.task_role,
            family="fargate-task"
        )

        # Add container to task definition - builds from Dockerfile in the repo
        self.container = self.task_definition.add_container(
            "AppContainer",
            # Build from Dockerfile in the current directory
            image=ecs.ContainerImage.from_asset(
                directory=".",  # Directory containing Dockerfile
                file="Dockerfile"  # Dockerfile name
            ),
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="ecs",
                log_group=self.log_group
            ),
            environment={
                "AWS_DEFAULT_REGION": self.region
            }
        )

        # Create ECS security group
        self.ecs_security_group = ec2.SecurityGroup(
            self, "EcsSecurityGroup",
            vpc=self.vpc,
            description="Security group for ECS tasks",
            allow_all_outbound=True
        )

        # Optional: Create ECS service using Fargate Spot
        # Uncomment this section if you want a running service instead of manually running tasks
        # self.service = ecs.FargateService(
        #     self, "FargateService",
        #     cluster=self.cluster,
        #     task_definition=self.task_definition,
        #     desired_count=1,
        #     vpc_subnets=ec2.SubnetSelection(
        #         subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
        #     ),
        #     security_groups=[self.ecs_security_group],
        #     assign_public_ip=False,
        #     capacity_provider_strategies=[
        #         ecs.CapacityProviderStrategy(
        #             capacity_provider="FARGATE_SPOT",
        #             weight=1
        #         )
        #     ]
        # )

        # Outputs
        cdk.CfnOutput(
            self, "ClusterName",
            value=self.cluster.cluster_name,
            description="Name of the ECS cluster"
        )

        cdk.CfnOutput(
            self, "TaskDefinitionArn",
            value=self.task_definition.task_definition_arn,
            description="ARN of the ECS task definition"
        )

        cdk.CfnOutput(
            self, "VPCId",
            value=self.vpc.vpc_id,
            description="VPC ID"
        )

        cdk.CfnOutput(
            self, "LogGroupName",
            value=self.log_group.log_group_name,
            description="CloudWatch log group name"
        )

        cdk.CfnOutput(
            self, "TaskExecutionRoleArn",
            value=self.task_execution_role.role_arn,
            description="ARN of the task execution role"
        )

        cdk.CfnOutput(
            self, "TaskRoleArn",
            value=self.task_role.role_arn,
            description="ARN of the task role"
        )

        cdk.CfnOutput(
            self, "SecurityGroupId",
            value=self.ecs_security_group.security_group_id,
            description="Security group ID for ECS tasks"
        )

