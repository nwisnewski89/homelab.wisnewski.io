#!/usr/bin/env python3
"""
CDK Stack for CodeBuild Project that runs Packer builds

This stack creates a CodeBuild project configured to run Packer builds
for creating AMIs. The project includes:
- Packer installation
- IAM permissions for EC2, AMI creation, KMS
- Environment variables for Packer configuration
- Build commands to execute Packer
"""

from aws_cdk import (
    Stack,
    aws_codebuild as codebuild,
    aws_iam as iam,
    aws_s3 as s3,
    aws_kms as kms,
    aws_logs as logs,
    CfnOutput,
    Duration,
    RemovalPolicy,
)
from constructs import Construct
from typing import Optional


class PackerCodeBuildStack(Stack):
    """Stack that creates a CodeBuild project for Packer AMI builds"""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        packer_file_path: str = "packer-alma-linux.pkr.hcl",
        kms_key_id: Optional[str] = None,
        aws_region: Optional[str] = None,
        target_accounts: Optional[list] = None,
        ami_name_prefix: str = "alma-linux-provisioned",
        instance_type: str = "t3.medium",
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Configuration
        self.packer_file_path = packer_file_path
        self.kms_key_id = kms_key_id
        self.aws_region = aws_region or self.region
        self.target_accounts = target_accounts or []
        self.ami_name_prefix = ami_name_prefix
        self.instance_type = instance_type

        # Create S3 bucket for build artifacts
        self.artifact_bucket = self.create_artifact_bucket()

        # Create IAM role for CodeBuild
        self.codebuild_role = self.create_codebuild_role()

        # Create CodeBuild project
        self.codebuild_project = self.create_codebuild_project()

        # Create outputs
        self.create_outputs()

    def create_artifact_bucket(self) -> s3.Bucket:
        """Create S3 bucket for CodeBuild artifacts"""
        return s3.Bucket(
            self,
            "CodeBuildArtifactBucket",
            bucket_name=f"packer-codebuild-artifacts-{self.account}-{self.region}",
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            removal_policy=RemovalPolicy.DESTROY,  # Change for production
            auto_delete_objects=True,  # Change for production
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="DeleteOldArtifacts",
                    expiration=Duration.days(30),
                    enabled=True
                )
            ]
        )

    def create_codebuild_role(self) -> iam.Role:
        """Create IAM role for CodeBuild with necessary permissions"""
        role = iam.Role(
            self,
            "CodeBuildRole",
            assumed_by=iam.ServicePrincipal("codebuild.amazonaws.com"),
            description="Role for CodeBuild to run Packer builds",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "CloudWatchLogsFullAccess"
                )
            ]
        )

        # EC2 permissions for Packer
        role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ec2:DescribeImages",
                    "ec2:DescribeInstances",
                    "ec2:DescribeInstanceStatus",
                    "ec2:DescribeSnapshots",
                    "ec2:DescribeVolumes",
                    "ec2:DescribeVpcs",
                    "ec2:DescribeSubnets",
                    "ec2:DescribeSecurityGroups",
                    "ec2:CreateTags",
                    "ec2:DeleteTags",
                    "ec2:RunInstances",
                    "ec2:TerminateInstances",
                    "ec2:CreateSnapshot",
                    "ec2:DeleteSnapshot",
                    "ec2:CreateVolume",
                    "ec2:DeleteVolume",
                    "ec2:AttachVolume",
                    "ec2:DetachVolume",
                    "ec2:ModifyInstanceAttribute",
                    "ec2:ModifyVolume",
                ],
                resources=["*"]
            )
        )

        # AMI permissions
        role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ec2:CreateImage",
                    "ec2:CopyImage",
                    "ec2:RegisterImage",
                    "ec2:DeregisterImage",
                    "ec2:DescribeImageAttribute",
                    "ec2:ModifyImageAttribute",
                ],
                resources=["*"]
            )
        )

        # KMS permissions for encrypted AMIs
        if self.kms_key_id:
            role.add_to_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "kms:Decrypt",
                        "kms:Encrypt",
                        "kms:ReEncrypt*",
                        "kms:GenerateDataKey*",
                        "kms:DescribeKey",
                    ],
                    resources=[f"arn:aws:kms:{self.region}:{self.account}:key/{self.kms_key_id}"]
                )
            )
        else:
            # Allow access to default KMS keys if no specific key provided
            role.add_to_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "kms:Decrypt",
                        "kms:Encrypt",
                        "kms:ReEncrypt*",
                        "kms:GenerateDataKey*",
                        "kms:DescribeKey",
                    ],
                    resources=[f"arn:aws:kms:{self.region}:*:key/*"]
                )
            )

        # S3 permissions for artifacts
        self.artifact_bucket.grant_read_write(role)

        # SSM permissions (if using SSM for instance access)
        role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ssm:SendCommand",
                    "ssm:GetCommandInvocation",
                    "ssm:DescribeInstanceInformation",
                ],
                resources=["*"]
            )
        )

        return role

    def create_codebuild_project(self) -> codebuild.Project:
        """Create CodeBuild project configured for Packer builds"""
        
        # Build environment variables
        environment_variables = {
            "PACKER_FILE": codebuild.BuildEnvironmentVariable(
                value=self.packer_file_path
            ),
            "AWS_REGION": codebuild.BuildEnvironmentVariable(
                value=self.aws_region
            ),
            "AMI_NAME_PREFIX": codebuild.BuildEnvironmentVariable(
                value=self.ami_name_prefix
            ),
            "INSTANCE_TYPE": codebuild.BuildEnvironmentVariable(
                value=self.instance_type
            ),
        }

        # Add KMS key if provided
        if self.kms_key_id:
            environment_variables["KMS_KEY_ID"] = codebuild.BuildEnvironmentVariable(
                value=self.kms_key_id,
                type=codebuild.BuildEnvironmentVariableType.SECRETS_MANAGER
            )

        # Add target accounts if provided
        if self.target_accounts:
            environment_variables["TARGET_ACCOUNTS"] = codebuild.BuildEnvironmentVariable(
                value=",".join(self.target_accounts)
            )

        project = codebuild.Project(
            self,
            "PackerBuildProject",
            project_name=f"packer-ami-build-{self.region}",
            description="CodeBuild project for building AMIs with Packer",
            role=self.codebuild_role,
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.STANDARD_7_0,  # Amazon Linux 2023
                compute_type=codebuild.ComputeType.LARGE,  # Use LARGE for Packer builds
                privileged=True,  # Required for Docker if needed
            ),
            environment_variables=environment_variables,
            build_spec=codebuild.BuildSpec.from_object({
                "version": "0.2",
                "phases": {
                    "install": {
                        "runtime-versions": {
                            "python": "3.11"
                        },
                        "commands": [
                            "echo 'Installing Packer...'",
                            "PACKER_VERSION=1.10.0",
                            "wget -q https://releases.hashicorp.com/packer/${PACKER_VERSION}/packer_${PACKER_VERSION}_linux_amd64.zip",
                            "unzip -q packer_${PACKER_VERSION}_linux_amd64.zip",
                            "sudo mv packer /usr/local/bin/",
                            "rm packer_${PACKER_VERSION}_linux_amd64.zip",
                            "packer version",
                            "echo 'Packer installed successfully'"
                        ]
                    },
                    "pre_build": {
                        "commands": [
                            "echo 'Pre-build phase: Validating Packer configuration'",
                            "echo 'Packer file: $PACKER_FILE'",
                            "echo 'AWS Region: $AWS_REGION'",
                            "echo 'AMI Name Prefix: $AMI_NAME_PREFIX'",
                            "ls -la",
                            "if [ ! -f \"$PACKER_FILE\" ]; then",
                            "  echo 'Error: Packer file not found: $PACKER_FILE'",
                            "  exit 1",
                            "fi",
                            "packer validate $PACKER_FILE || exit 1",
                            "echo 'Packer configuration is valid'"
                        ]
                    },
                    "build": {
                        "commands": [
                            "echo 'Build phase: Running Packer build'",
                            "echo 'Building AMI with Packer...'",
                            # Build Packer command with variables
                            "PACKER_CMD=\"packer build -var 'aws_region=$AWS_REGION' -var 'ami_name_prefix=$AMI_NAME_PREFIX' -var 'instance_type=$INSTANCE_TYPE'\"",
                            # Add KMS key if provided
                            "if [ -n \"$KMS_KEY_ID\" ]; then",
                            "  PACKER_CMD=\"$PACKER_CMD -var 'kms_key_id=$KMS_KEY_ID'\"",
                            "fi",
                            # Add target accounts if provided
                            "if [ -n \"$TARGET_ACCOUNTS\" ]; then",
                            "  PACKER_CMD=\"$PACKER_CMD -var 'target_accounts=[\\\"$(echo $TARGET_ACCOUNTS | sed 's/,/\\\",\\\"/g')\\\"]'\"",
                            "fi",
                            "PACKER_CMD=\"$PACKER_CMD $PACKER_FILE\"",
                            "echo 'Executing: $PACKER_CMD'",
                            "eval $PACKER_CMD",
                            "echo 'Packer build completed successfully'"
                        ]
                    },
                    "post_build": {
                        "commands": [
                            "echo 'Post-build phase: Build artifacts and cleanup'",
                            "echo 'AMI build completed'",
                            "echo 'Build finished on $(date)'"
                        ]
                    }
                },
                "artifacts": {
                    "files": [
                        "**/*"
                    ],
                    "name": "packer-build-artifacts"
                }
            }),
            logging=codebuild.LoggingOptions(
                cloud_watch=codebuild.CloudWatchLoggingOptions(
                    log_group=logs.LogGroup(
                        self,
                        "CodeBuildLogGroup",
                        log_group_name=f"/aws/codebuild/packer-ami-build-{self.region}",
                        retention=logs.RetentionDays.ONE_WEEK,
                        removal_policy=RemovalPolicy.DESTROY
                    )
                )
            ),
            timeout=Duration.hours(2),  # Packer builds can take time
            concurrent_build_limit=1,  # Limit concurrent builds
        )

        return project

    def create_outputs(self):
        """Create CloudFormation outputs"""
        CfnOutput(
            self,
            "CodeBuildProjectName",
            value=self.codebuild_project.project_name,
            description="Name of the CodeBuild project"
        )

        CfnOutput(
            self,
            "CodeBuildProjectArn",
            value=self.codebuild_project.project_arn,
            description="ARN of the CodeBuild project"
        )

        CfnOutput(
            self,
            "ArtifactBucketName",
            value=self.artifact_bucket.bucket_name,
            description="S3 bucket for build artifacts"
        )

