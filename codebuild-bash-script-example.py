#!/usr/bin/env python3
"""
Example: Loading bash scripts into CodeBuild pipeline using AWS Python CDK

This example demonstrates three approaches:
1. Script from source repository (most common)
2. Buildspec file from source repository
3. Script bundled as CDK asset
"""

from aws_cdk import (
    Stack,
    aws_codebuild as codebuild,
    aws_codepipeline as codepipeline,
    aws_codepipeline_actions as cpactions,
    aws_iam as iam,
    aws_s3 as s3,
    aws_logs as logs,
    Duration,
    RemovalPolicy,
)
from constructs import Construct
from pathlib import Path


class CodeBuildWithBashScriptStack(Stack):
    """Stack demonstrating different ways to use bash scripts in CodeBuild"""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Approach 1: Script from source repository
        self.project_with_source_script = self.create_project_with_source_script()

        # Approach 2: Buildspec file from source repository
        self.project_with_buildspec_file = self.create_project_with_buildspec_file()

        # Approach 3: Script bundled as CDK asset
        self.project_with_asset_script = self.create_project_with_asset_script()

    # ============================================================================
    # Approach 1: Script from Source Repository (RECOMMENDED)
    # ============================================================================
    # If your bash script is in your source repository (GitHub, CodeCommit, etc.),
    # you can simply reference it in the buildspec commands. The script will be
    # available in the CodeBuild environment when the source is checked out.

    def create_project_with_source_script(self) -> codebuild.Project:
        """
        Example: Using a bash script from the source repository
        
        Assumes your repository has a script at: scripts/build.sh
        """
        return codebuild.Project(
            self,
            "ProjectWithSourceScript",
            project_name="example-source-script",
            description="CodeBuild project using bash script from source repo",
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                compute_type=codebuild.ComputeType.SMALL,
            ),
            build_spec=codebuild.BuildSpec.from_object({
                "version": "0.2",
                "phases": {
                    "pre_build": {
                        "commands": [
                            "echo 'Making script executable'",
                            "chmod +x scripts/build.sh",
                            "echo 'Running script from source repository'",
                        ]
                    },
                    "build": {
                        "commands": [
                            # Run the script directly (it's in the source repo)
                            "bash scripts/build.sh",
                            # Or if you need to pass environment variables:
                            "CODECOMMIT_REPO=$CODECOMMIT_REPO bash scripts/build.sh",
                            # Or source it if it exports variables:
                            "source scripts/setup.sh && echo 'Setup complete'",
                        ]
                    }
                }
            }),
        )

    # ============================================================================
    # Approach 2: Buildspec File from Source Repository
    # ============================================================================
    # If you prefer to keep your buildspec separate (in a file in your repo),
    # you can reference it instead of defining it inline.

    def create_project_with_buildspec_file(self) -> codebuild.Project:
        """
        Example: Using a buildspec file from the source repository
        
        Assumes your repository has a buildspec file at: buildspec.yml
        The buildspec.yml can then reference bash scripts in your repo.
        """
        return codebuild.Project(
            self,
            "ProjectWithBuildspecFile",
            project_name="example-buildspec-file",
            description="CodeBuild project using buildspec file from source repo",
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                compute_type=codebuild.ComputeType.SMALL,
            ),
            # Reference buildspec file from source (defaults to buildspec.yml in repo root)
            build_spec=codebuild.BuildSpec.from_source_filename("buildspec.yml"),
            
            # Alternative: if your buildspec is in a different location:
            # build_spec=codebuild.BuildSpec.from_source_filename("build/buildspec.yml"),
        )

    # ============================================================================
    # Approach 3: Script Bundled as CDK Asset
    # ============================================================================
    # If you want the script to be part of the CDK stack (not in source repo),
    # you can bundle it as an asset and copy it to S3, then download it in CodeBuild.

    def create_project_with_asset_script(self) -> codebuild.Project:
        """
        Example: Using a bash script bundled as a CDK asset
        
        This approach bundles a local script file with the CDK stack.
        The script is uploaded to S3 and can be downloaded during build.
        """
        from aws_cdk.aws_s3_assets import Asset
        
        # Create an S3 asset from a local script file
        # This script would be in your CDK project directory
        script_asset = Asset(
            self,
            "BuildScriptAsset",
            path=str(Path(__file__).parent / "scripts" / "build.sh"),  # Adjust path as needed
        )

        # Create S3 bucket for CodeBuild artifacts
        artifact_bucket = s3.Bucket(
            self,
            "AssetScriptArtifactBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        project = codebuild.Project(
            self,
            "ProjectWithAssetScript",
            project_name="example-asset-script",
            description="CodeBuild project using bash script from CDK asset",
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                compute_type=codebuild.ComputeType.SMALL,
            ),
            build_spec=codebuild.BuildSpec.from_object({
                "version": "0.2",
                "phases": {
                    "pre_build": {
                        "commands": [
                            "echo 'Downloading script from S3'",
                            # Download the script from S3 (asset provides the S3 location)
                            f"aws s3 cp s3://${{SCRIPT_BUCKET}}/${{SCRIPT_KEY}} ./build.sh",
                            "chmod +x ./build.sh",
                            "echo 'Script downloaded and made executable'",
                        ]
                    },
                    "build": {
                        "commands": [
                            "echo 'Running script from CDK asset'",
                            "bash ./build.sh",
                        ]
                    }
                }
            }),
            environment_variables={
                "SCRIPT_BUCKET": codebuild.BuildEnvironmentVariable(
                    value=script_asset.s3_bucket_name
                ),
                "SCRIPT_KEY": codebuild.BuildEnvironmentVariable(
                    value=script_asset.s3_object_key
                ),
            },
        )

        # Grant CodeBuild permission to read the asset
        script_asset.grant_read(project.role)

        return project

    # ============================================================================
    # Approach 4: Inline Script in Buildspec (Alternative)
    # ============================================================================
    # You can also define small scripts inline in the buildspec itself.
    # This is useful for simple scripts that don't need to be separate files.

    def create_project_with_inline_script(self) -> codebuild.Project:
        """
        Example: Inline bash script in buildspec
        
        For simple scripts, you can define them inline.
        """
        return codebuild.Project(
            self,
            "ProjectWithInlineScript",
            project_name="example-inline-script",
            description="CodeBuild project with inline bash script",
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                compute_type=codebuild.ComputeType.SMALL,
            ),
            build_spec=codebuild.BuildSpec.from_object({
                "version": "0.2",
                "phases": {
                    "build": {
                        "commands": [
                            # Inline script using heredoc
                            """bash << 'EOF'
                            #!/bin/bash
                            set -e
                            
                            echo "Running inline script"
                            echo "Environment: $ENVIRONMENT"
                            
                            # Your script logic here
                            if [ "$ENVIRONMENT" = "production" ]; then
                                echo "Deploying to production"
                            else
                                echo "Deploying to staging"
                            fi
                            
                            echo "Script completed"
                            EOF""",
                        ]
                    }
                }
            }),
        )


# ============================================================================
# Example: Integration with CodePipeline
# ============================================================================
# Here's how you would use one of these approaches in a CodePipeline

class CodePipelineWithScriptStack(Stack):
    """Example stack showing CodePipeline with CodeBuild using bash scripts"""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create artifact bucket
        artifact_bucket = s3.Bucket(
            self,
            "PipelineArtifactBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # Create CodeBuild project that uses a script from source
        build_project = codebuild.Project(
            self,
            "BuildProject",
            project_name="pipeline-build-project",
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                compute_type=codebuild.ComputeType.SMALL,
            ),
            build_spec=codebuild.BuildSpec.from_object({
                "version": "0.2",
                "phases": {
                    "pre_build": {
                        "commands": [
                            "echo 'Setting up environment'",
                            "chmod +x scripts/*.sh",  # Make all scripts executable
                        ]
                    },
                    "build": {
                        "commands": [
                            # Run your bash script from source
                            "bash scripts/build.sh",
                            # Or use buildspec file approach:
                            # The buildspec.yml in your repo will be used automatically
                        ]
                    },
                    "post_build": {
                        "commands": [
                            "bash scripts/post-build.sh || true",  # Run if exists
                        ]
                    }
                },
                "artifacts": {
                    "files": ["**/*"],
                }
            }),
        )

        # Grant S3 permissions
        artifact_bucket.grant_read_write(build_project.role)

        # Create pipeline
        source_output = codepipeline.Artifact("SourceOutput")

        pipeline = codepipeline.Pipeline(
            self,
            "Pipeline",
            pipeline_name="example-pipeline",
            artifact_bucket=artifact_bucket,
        )

        # Source stage (example with CodeCommit)
        pipeline.add_stage(
            stage_name="Source",
            actions=[
                cpactions.CodeCommitSourceAction(
                    action_name="Source",
                    repository=codecommit.Repository.from_repository_name(
                        self,
                        "SourceRepo",
                        repository_name="my-repo"
                    ),
                    output=source_output,
                    branch="main",
                )
            ]
        )

        # Build stage
        pipeline.add_stage(
            stage_name="Build",
            actions=[
                cpactions.CodeBuildAction(
                    action_name="Build",
                    project=build_project,
                    input=source_output,
                    outputs=[codepipeline.Artifact("BuildOutput")],
                )
            ]
        )


# ============================================================================
# Example buildspec.yml (for Approach 2)
# ============================================================================
"""
# buildspec.yml (place this in your source repository root)
version: 0.2

phases:
  pre_build:
    commands:
      - echo "Making scripts executable"
      - chmod +x scripts/*.sh
      - echo "Pre-build phase complete"
  
  build:
    commands:
      - echo "Running build script"
      - bash scripts/build.sh
      - |
        # You can also run multiple commands
        bash scripts/test.sh
        bash scripts/package.sh
  
  post_build:
    commands:
      - echo "Running post-build cleanup"
      - bash scripts/cleanup.sh || true

artifacts:
  files:
    - '**/*'
  name: build-artifacts
"""


# ============================================================================
# Recommendations
# ============================================================================
"""
1. **Script from Source Repository (Approach 1)** - RECOMMENDED
   - Best for scripts that are versioned with your code
   - Simplest to maintain
   - Scripts are in your Git history
   - Use this for most cases

2. **Buildspec File (Approach 2)**
   - Good if you prefer YAML syntax
   - Separates build logic from CDK code
   - Makes it easier for non-CDK developers to modify builds

3. **CDK Asset (Approach 3)**
   - Use when script needs to be part of the CDK stack definition
   - Less common, but useful for CDK-specific scripts
   - Script is managed separately from source code

4. **Inline Script (Approach 4)**
   - Good for very simple, one-off scripts
   - Not recommended for complex logic (use separate files)

Best Practice:
- Keep build scripts in your source repository (scripts/ directory)
- Reference them in your buildspec
- Make them executable: chmod +x scripts/build.sh
- Use environment variables to pass configuration
"""

