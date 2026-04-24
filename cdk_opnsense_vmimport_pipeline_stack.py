#!/usr/bin/env python3
"""
CDK stack to build an OPNsense VM import pipeline with CodeBuild.

What this stack provisions:
1) Private S3 bucket to store imported disk images
2) IAM role named "vmimport" for EC2 VM Import/Export service
3) CodeBuild project that:
   - Downloads the OPNsense nano image
   - Decompresses it to RAW
   - Uploads it to S3
   - Calls EC2 import-image and waits for completion
"""

from __future__ import annotations

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_codebuild as codebuild,
    aws_iam as iam,
    aws_s3 as s3,
)
from constructs import Construct


class OpnSenseVmImportPipelineStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        image_url = self.node.try_get_context("imageUrl") or (
            "https://mirrors.nycbug.org/pub/opnsense/releases/mirror/"
            "OPNsense-24.7-nano-amd64.img.bz2"
        )
        image_key = self.node.try_get_context("imageKey") or "opnsense/opnsense-nano-amd64.raw"
        import_description = self.node.try_get_context("importDescription") or "OPNsense nano import"

        import_bucket = s3.Bucket(
            self,
            "VmImportBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            versioned=True,
            removal_policy=RemovalPolicy.RETAIN,
            auto_delete_objects=False,
        )

        vmimport_role = iam.Role(
            self,
            "VmImportServiceRole",
            role_name="vmimport",
            assumed_by=iam.ServicePrincipal(
                "vmie.amazonaws.com",
                conditions={"StringEquals": {"sts:Externalid": "vmimport"}},
            ),
            description="Service role for EC2 VM Import/Export",
        )

        vmimport_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ec2:ModifySnapshotAttribute",
                    "ec2:CopySnapshot",
                    "ec2:RegisterImage",
                    "ec2:Describe*",
                ],
                resources=["*"],
            )
        )
        vmimport_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["s3:GetBucketLocation", "s3:ListBucket"],
                resources=[import_bucket.bucket_arn],
            )
        )
        vmimport_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["s3:GetObject"],
                resources=[import_bucket.arn_for_objects(image_key)],
            )
        )

        build_project = codebuild.Project(
            self,
            "OpnSenseImportProject",
            description=(
                "Downloads OPNsense image, uploads to S3, then performs EC2 import-image "
                "to create an AMI and backing snapshot."
            ),
            timeout=Duration.hours(8),
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                compute_type=codebuild.ComputeType.LARGE,
                privileged=False,
            ),
            environment_variables={
                "IMAGE_URL": codebuild.BuildEnvironmentVariable(value=image_url),
                "IMAGE_KEY": codebuild.BuildEnvironmentVariable(value=image_key),
                "IMPORT_BUCKET": codebuild.BuildEnvironmentVariable(value=import_bucket.bucket_name),
                "IMPORT_DESCRIPTION": codebuild.BuildEnvironmentVariable(value=import_description),
                "VMIMPORT_ROLE_NAME": codebuild.BuildEnvironmentVariable(value=vmimport_role.role_name),
                "AWS_REGION": codebuild.BuildEnvironmentVariable(value=self.region),
            },
            source=codebuild.Source.no_source(),
            build_spec=codebuild.BuildSpec.from_object(
                {
                    "version": "0.2",
                    "phases": {
                        "install": {
                            "commands": [
                                "set -euo pipefail",
                                "echo Installing required tools...",
                                "yum install -y bzip2 xz curl",
                            ]
                        },
                        "build": {
                            "commands": [
                                "set -euo pipefail",
                                "echo Downloading image from ${IMAGE_URL}",
                                "curl -fL --retry 5 --retry-delay 5 -o /tmp/opnsense.img.bz2 ${IMAGE_URL}",
                                "echo Decompressing image...",
                                "bzip2 -d -f /tmp/opnsense.img.bz2",
                                "mv /tmp/opnsense.img /tmp/opnsense.raw",
                                "echo Uploading image to s3://${IMPORT_BUCKET}/${IMAGE_KEY}",
                                "aws s3 cp /tmp/opnsense.raw s3://${IMPORT_BUCKET}/${IMAGE_KEY}",
                                (
                                    "IMPORT_TASK_ID=$(aws ec2 import-image "
                                    "--region ${AWS_REGION} "
                                    "--description \"${IMPORT_DESCRIPTION}\" "
                                    "--role-name ${VMIMPORT_ROLE_NAME} "
                                    "--disk-containers "
                                    "\"Format=RAW,UserBucket={S3Bucket=${IMPORT_BUCKET},S3Key=${IMAGE_KEY}}\" "
                                    "--query ImportTaskId --output text)"
                                ),
                                "echo Import task started: ${IMPORT_TASK_ID}",
                                "for i in $(seq 1 240); do "
                                "STATUS=$(aws ec2 describe-import-image-tasks --region ${AWS_REGION} "
                                "--import-task-ids ${IMPORT_TASK_ID} "
                                "--query 'ImportImageTasks[0].Status' --output text); "
                                "if [ \"${STATUS}\" = \"completed\" ]; then "
                                "AMI_ID=$(aws ec2 describe-import-image-tasks --region ${AWS_REGION} "
                                "--import-task-ids ${IMPORT_TASK_ID} "
                                "--query 'ImportImageTasks[0].ImageId' --output text); "
                                "echo \"AMI_ID=${AMI_ID}\" > ami-output.env; "
                                "echo \"Import completed with AMI: ${AMI_ID}\"; exit 0; "
                                "fi; "
                                "if [ \"${STATUS}\" = \"deleted\" ]; then "
                                "echo Import task failed or was deleted; exit 1; "
                                "fi; "
                                "echo \"Current status: ${STATUS} (attempt ${i}/240)\"; "
                                "sleep 60; "
                                "done",
                                "echo Timed out waiting for import-image completion; exit 1",
                            ]
                        },
                    },
                    "artifacts": {"files": ["ami-output.env"], "discard-paths": "yes"},
                }
            ),
        )

        import_bucket.grant_read_write(build_project)
        build_project.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ec2:ImportImage",
                    "ec2:DescribeImportImageTasks",
                    "ec2:DescribeImages",
                    "ec2:DescribeSnapshots",
                ],
                resources=["*"],
            )
        )
        build_project.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["iam:PassRole"],
                resources=[vmimport_role.role_arn],
            )
        )

        CfnOutput(self, "VmImportBucketName", value=import_bucket.bucket_name)
        CfnOutput(self, "VmImportRoleArn", value=vmimport_role.role_arn)
        CfnOutput(self, "CodeBuildProjectName", value=build_project.project_name)
