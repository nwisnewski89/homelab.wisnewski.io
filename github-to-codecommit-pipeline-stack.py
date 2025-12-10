#!/usr/bin/env python3
"""
CDK Stack for CodePipeline that syncs GitHub code to CodeCommit

This stack creates:
- A CodeCommit repository to store the synced code
- A CodePipeline triggered by GitHub pushes via CodeStar Connection
- A CodeBuild project that pushes source code to CodeCommit
"""

from aws_cdk import (
    Stack,
    aws_codepipeline as codepipeline,
    aws_codepipeline_actions as cpactions,
    aws_codebuild as codebuild,
    aws_codecommit as codecommit,
    aws_iam as iam,
    aws_s3 as s3,
    aws_logs as logs,
    CfnOutput,
    Duration,
    RemovalPolicy,
)
from constructs import Construct
from typing import Optional


class GitHubToCodeCommitPipelineStack(Stack):
    """Stack that creates a pipeline to sync GitHub code to CodeCommit"""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        code_star_connection_arn: str,
        github_owner: str,
        github_repo: str,
        github_branch: str = "main",
        codecommit_repo_name: Optional[str] = None,
        codecommit_branch: str = "main",
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Configuration
        self.code_star_connection_arn = code_star_connection_arn
        self.github_owner = github_owner
        self.github_repo = github_repo
        self.github_branch = github_branch
        self.codecommit_repo_name = codecommit_repo_name or f"{github_repo}-synced"
        self.codecommit_branch = codecommit_branch

        # Create CodeCommit repository
        self.codecommit_repo = self.create_codecommit_repo()

        # Create S3 bucket for pipeline artifacts
        self.artifact_bucket = self.create_artifact_bucket()

        # Create CodeBuild project that pushes to CodeCommit
        self.codebuild_project = self.create_codebuild_project()

        # Create CodePipeline
        self.pipeline = self.create_pipeline()

        # Create outputs
        self.create_outputs()

    def create_codecommit_repo(self) -> codecommit.Repository:
        """Create CodeCommit repository to store synced code"""
        return codecommit.Repository(
            self,
            "SyncedCodeCommitRepo",
            repository_name=self.codecommit_repo_name,
            description=f"Repository synced from GitHub {self.github_owner}/{self.github_repo}",
        )

    def create_artifact_bucket(self) -> s3.Bucket:
        """Create S3 bucket for CodePipeline artifacts"""
        return s3.Bucket(
            self,
            "PipelineArtifactBucket",
            bucket_name=f"github-codecommit-sync-artifacts-{self.account}-{self.region}",
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

    def create_codebuild_project(self) -> codebuild.Project:
        """Create CodeBuild project that pushes code to CodeCommit"""
        
        # Create IAM role for CodeBuild
        codebuild_role = iam.Role(
            self,
            "CodeCommitSyncCodeBuildRole",
            assumed_by=iam.ServicePrincipal("codebuild.amazonaws.com"),
            description="Role for CodeBuild to sync code to CodeCommit",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "CloudWatchLogsFullAccess"
                )
            ]
        )

        # Grant CodeBuild permissions to push to CodeCommit
        self.codecommit_repo.grant_pull_push(codebuild_role)
        self.codecommit_repo.grant_read(codebuild_role)

        # S3 permissions for artifacts
        self.artifact_bucket.grant_read_write(codebuild_role)

        # Build environment variables
        environment_variables = {
            "CODECOMMIT_REPO_NAME": codebuild.BuildEnvironmentVariable(
                value=self.codecommit_repo_name
            ),
            "CODECOMMIT_BRANCH": codebuild.BuildEnvironmentVariable(
                value=self.codecommit_branch
            ),
            "CODECOMMIT_REPO_URL": codebuild.BuildEnvironmentVariable(
                value=self.codecommit_repo.repository_clone_url_http
            ),
            "GITHUB_REPO": codebuild.BuildEnvironmentVariable(
                value=f"{self.github_owner}/{self.github_repo}"
            ),
            "GITHUB_BRANCH": codebuild.BuildEnvironmentVariable(
                value=self.github_branch
            ),
        }

        project = codebuild.Project(
            self,
            "CodeCommitSyncBuildProject",
            project_name=f"github-to-codecommit-sync-{self.region}",
            description="CodeBuild project to sync GitHub code to CodeCommit",
            role=codebuild_role,
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                compute_type=codebuild.ComputeType.SMALL,
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
                            "echo 'Installing Git and AWS CLI...'",
                            "yum update -y",
                            "yum install -y git",
                            "git --version",
                            "aws --version",
                            "echo 'Dependencies installed successfully'"
                        ]
                    },
                    "pre_build": {
                        "commands": [
                            "echo 'Pre-build phase: Setting up Git configuration'",
                            "echo 'CodeCommit Repo: $CODECOMMIT_REPO_NAME'",
                            "echo 'CodeCommit Branch: $CODECOMMIT_BRANCH'",
                            "echo 'CodeCommit URL: $CODECOMMIT_REPO_URL'",
                            "echo 'GitHub Repo: $GITHUB_REPO'",
                            "echo 'GitHub Branch: $GITHUB_BRANCH'",
                            # Configure Git
                            "git config --global user.name 'CodeBuild'",
                            "git config --global user.email 'codebuild@aws.amazon.com'",
                            # Store current directory (where GitHub source code is)
                            "SOURCE_DIR=$(pwd)",
                            "echo 'Source directory: $SOURCE_DIR'",
                            # Clone CodeCommit repo (or initialize if empty)
                            "if git ls-remote --heads $CODECOMMIT_REPO_URL $CODECOMMIT_BRANCH 2>/dev/null | grep -q .; then",
                            "  echo 'CodeCommit branch exists, cloning...'",
                            "  git clone -b $CODECOMMIT_BRANCH $CODECOMMIT_REPO_URL codecommit-repo 2>/dev/null || git clone $CODECOMMIT_REPO_URL codecommit-repo",
                            "else",
                            "  echo 'CodeCommit branch does not exist, initializing new repo...'",
                            "  mkdir -p codecommit-repo",
                            "  cd codecommit-repo",
                            "  git init",
                            "  git remote add origin $CODECOMMIT_REPO_URL",
                            "  cd $SOURCE_DIR",
                            "fi"
                        ]
                    },
                    "build": {
                        "commands": [
                            "echo 'Build phase: Syncing code from GitHub to CodeCommit'",
                            "SOURCE_DIR=$(pwd)",
                            "cd codecommit-repo",
                            # Ensure we're on the correct branch
                            "git checkout -b $CODECOMMIT_BRANCH 2>/dev/null || git checkout $CODECOMMIT_BRANCH 2>/dev/null || true",
                            # Copy all files from GitHub source, excluding .git and codecommit-repo
                            "echo 'Copying files from GitHub source...'",
                            "for item in $SOURCE_DIR/* $SOURCE_DIR/.[!.]*; do",
                            "  if [ -e \"$item\" ]; then",
                            "    item_name=$(basename \"$item\")",
                            "    if [ \"$item_name\" != \".git\" ] && [ \"$item_name\" != \"codecommit-repo\" ] && [ \"$item_name\" != \".codebuild\" ]; then",
                            "      cp -r \"$item\" . 2>/dev/null || true",
                            "    fi",
                            "  fi",
                            "done",
                            # Remove .git if it was copied from source (shouldn't happen with rsync, but just in case)
                            "rm -rf .git 2>/dev/null || true",
                            # Initialize git if needed
                            "if [ ! -d .git ]; then",
                            "  git init",
                            "  git remote add origin $CODECOMMIT_REPO_URL || git remote set-url origin $CODECOMMIT_REPO_URL",
                            "fi",
                            # Add all files
                            "git add -A",
                            # Check if there are changes
                            "if git diff --staged --quiet && git diff --quiet; then",
                            "  echo 'No changes to commit'",
                            "else",
                            "  echo 'Committing changes...'",
                            "  COMMIT_MSG=\"Sync from GitHub $GITHUB_REPO branch $GITHUB_BRANCH - $(date -u +%Y-%m-%dT%H:%M:%SZ)\"",
                            "  git commit -m \"$COMMIT_MSG\" || echo 'Commit failed or nothing to commit'",
                            "  echo 'Pushing to CodeCommit...'",
                            "  git push -u origin $CODECOMMIT_BRANCH 2>&1 || git push origin $CODECOMMIT_BRANCH 2>&1",
                            "  echo 'Code successfully synced to CodeCommit'",
                            "fi"
                        ]
                    },
                    "post_build": {
                        "commands": [
                            "echo 'Post-build phase: Sync completed'",
                            "echo 'Sync finished on $(date)'"
                        ]
                    }
                },
                "artifacts": {
                    "files": [
                        "**/*"
                    ],
                    "name": "sync-artifacts"
                }
            }),
            logging=codebuild.LoggingOptions(
                cloud_watch=codebuild.CloudWatchLoggingOptions(
                    log_group=logs.LogGroup(
                        self,
                        "CodeBuildLogGroup",
                        log_group_name=f"/aws/codebuild/github-codecommit-sync-{self.region}",
                        retention=logs.RetentionDays.ONE_WEEK,
                        removal_policy=RemovalPolicy.DESTROY
                    )
                )
            ),
            timeout=Duration.minutes(30),
        )

        return project

    def create_pipeline(self) -> codepipeline.Pipeline:
        """Create CodePipeline with CodeStar Connection source"""
        
        # Source artifact
        source_output = codepipeline.Artifact("SourceOutput")

        # Create the pipeline
        pipeline = codepipeline.Pipeline(
            self,
            "GitHubToCodeCommitPipeline",
            pipeline_name=f"github-to-codecommit-sync-{self.region}",
            artifact_bucket=self.artifact_bucket,
            restart_execution_on_update=True,
        )

        # Source stage with CodeStar Connection
        pipeline.add_stage(
            stage_name="Source",
            actions=[
                cpactions.CodeStarConnectionsSourceAction(
                    action_name="GitHub_Source",
                    owner=self.github_owner,
                    repo=self.github_repo,
                    branch=self.github_branch,
                    connection_arn=self.code_star_connection_arn,
                    output=source_output,
                    trigger_on_push=True,  # Automatically trigger on GitHub pushes
                )
            ]
        )

        # Build stage that syncs to CodeCommit
        pipeline.add_stage(
            stage_name="SyncToCodeCommit",
            actions=[
                cpactions.CodeBuildAction(
                    action_name="Sync_To_CodeCommit",
                    project=self.codebuild_project,
                    input=source_output,
                    outputs=[codepipeline.Artifact("SyncOutput")],
                )
            ]
        )

        return pipeline

    def create_outputs(self):
        """Create CloudFormation outputs"""
        CfnOutput(
            self,
            "PipelineName",
            value=self.pipeline.pipeline_name,
            description="Name of the CodePipeline"
        )

        CfnOutput(
            self,
            "PipelineArn",
            value=self.pipeline.pipeline_arn,
            description="ARN of the CodePipeline"
        )

        CfnOutput(
            self,
            "CodeCommitRepositoryName",
            value=self.codecommit_repo.repository_name,
            description="Name of the CodeCommit repository"
        )

        CfnOutput(
            self,
            "CodeCommitRepositoryArn",
            value=self.codecommit_repo.repository_arn,
            description="ARN of the CodeCommit repository"
        )

        CfnOutput(
            self,
            "CodeCommitCloneUrlHttp",
            value=self.codecommit_repo.repository_clone_url_http,
            description="HTTP clone URL for the CodeCommit repository"
        )

        CfnOutput(
            self,
            "CodeBuildProjectName",
            value=self.codebuild_project.project_name,
            description="Name of the CodeBuild project"
        )

        CfnOutput(
            self,
            "ArtifactBucketName",
            value=self.artifact_bucket.bucket_name,
            description="S3 bucket for pipeline artifacts"
        )

        CfnOutput(
            self,
            "PipelineUrl",
            value=(
                f"https://{self.region}.console.aws.amazon.com/codesuite/codepipeline/"
                f"pipelines/{self.pipeline.pipeline_name}/view"
            ),
            description="URL to view the pipeline in AWS Console"
        )

        CfnOutput(
            self,
            "CodeCommitUrl",
            value=(
                f"https://{self.region}.console.aws.amazon.com/codesuite/codecommit/"
                f"repositories/{self.codecommit_repo.repository_name}/browse"
            ),
            description="URL to view the CodeCommit repository in AWS Console"
        )

