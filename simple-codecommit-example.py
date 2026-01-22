#!/usr/bin/env python3
"""
Simple example: Creating a CodeCommit repository with a default branch name

This is the simplest approach using CfnRepository (L1 construct).
"""

from aws_cdk import Stack, aws_codecommit as codecommit
from constructs import Construct


class SimpleCodeCommitStack(Stack):
    """Simple stack that creates a CodeCommit repository with a default branch"""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        repository_name: str,
        default_branch: str = "main",
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create CodeCommit repository with default branch
        self.repo = codecommit.CfnRepository(
            self,
            "MyCodeCommitRepo",
            repository_name=repository_name,
            repository_description=f"Repository with default branch: {default_branch}",
            default_branch=default_branch,  # This sets the default branch name
        )

        # Note: If you need to use the L2 Repository construct methods later,
        # you can reference it like this:
        # repo_l2 = codecommit.Repository.from_repository_name(
        #     self, "RepoRef", repository_name
        # )


