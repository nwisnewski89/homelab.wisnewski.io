#!/usr/bin/env python3
"""
CDK App for GitHub to CodeCommit Sync Pipeline

This is the entry point for deploying a CodePipeline that:
- Uses CodeStar Connection to GitHub
- Automatically syncs code from GitHub to CodeCommit on pushes

Usage:
    cdk deploy GitHubToCodeCommitPipelineStack \
      --context codeStarConnectionArn=arn:aws:codeconnections:... \
      --context githubOwner=your-org \
      --context githubRepo=your-repo
"""

import importlib.util
import sys
from pathlib import Path
from aws_cdk import App, Environment

# Import the stack module (handling hyphenated filename)
stack_file = Path(__file__).parent / "github-to-codecommit-pipeline-stack.py"
spec = importlib.util.spec_from_file_location("github_to_codecommit_pipeline_stack", stack_file)
stack_module = importlib.util.module_from_spec(spec)
sys.modules["github_to_codecommit_pipeline_stack"] = stack_module
spec.loader.exec_module(stack_module)
GitHubToCodeCommitPipelineStack = stack_module.GitHubToCodeCommitPipelineStack


def main():
    """Main application entry point"""
    app = App()

    # Get configuration from context
    code_star_connection_arn = app.node.try_get_context("codeStarConnectionArn")
    github_owner = app.node.try_get_context("githubOwner")
    github_repo = app.node.try_get_context("githubRepo")
    github_branch = app.node.try_get_context("githubBranch") or "main"
    
    # CodeCommit configuration
    codecommit_repo_name = app.node.try_get_context("codecommitRepoName") or None
    codecommit_branch = app.node.try_get_context("codecommitBranch") or "main"

    # Validate required parameters
    if not code_star_connection_arn:
        raise ValueError(
            "codeStarConnectionArn is required. "
            "Provide it via --context codeStarConnectionArn=arn:aws:codeconnections:..."
        )
    
    if not github_owner or not github_repo:
        raise ValueError(
            "githubOwner and githubRepo are required. "
            "Provide them via --context githubOwner=your-org --context githubRepo=your-repo"
        )

    # Get account and region from context or use defaults
    account = app.node.try_get_context("account")
    region = app.node.try_get_context("region") or "us-east-1"

    # Create the pipeline stack
    GitHubToCodeCommitPipelineStack(
        app,
        "GitHubToCodeCommitPipelineStack",
        description="CodePipeline to sync GitHub code to CodeCommit",
        code_star_connection_arn=code_star_connection_arn,
        github_owner=github_owner,
        github_repo=github_repo,
        github_branch=github_branch,
        codecommit_repo_name=codecommit_repo_name,
        codecommit_branch=codecommit_branch,
        env=Environment(
            account=account,
            region=region
        ) if account else None
    )

    app.synth()


if __name__ == "__main__":
    main()

