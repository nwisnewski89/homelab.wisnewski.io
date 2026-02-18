"""
Apply the same ECR lifecycle policy to repos created by a CfnPullThroughCacheRule.

Use a Repository Creation Template: same prefix as the pull-through cache rule,
applied_for=["PULL_THROUGH_CACHE"], and lifecycle_policy set to your policy JSON.
Repos created by the pull-through cache (on first pull) will then get this policy
at creation time. Existing repos are not updated by the template.
"""

import json
from pathlib import Path

from aws_cdk import Stack
from aws_cdk import aws_ecr as ecr
from constructs import Construct


# Must match the ecr_repository_prefix on your CfnPullThroughCacheRule.
# ECR treats the prefix as having a trailing "/" (e.g. "docker-hub" -> "docker-hub/").
PULL_THROUGH_CACHE_PREFIX = "docker-hub"


def load_lifecycle_policy_json() -> str:
    """Load lifecycle policy from ecr-policy.json (same dir as this file)."""
    path = Path(__file__).parent / "ecr-policy.json"
    with open(path) as f:
        doc = json.load(f)
    return json.dumps(doc)


def build_lifecycle_policy_inline() -> str:
    """Same policy as ecr-policy.json, built inline (no file dependency)."""
    policy = {
        "rules": [
            {
                "rulePriority": 1,
                "description": "Keep only 5 most recent images tagged main*",
                "selection": {
                    "tagStatus": "tagged",
                    "tagPatternList": ["main*"],
                    "countType": "imageCountMoreThan",
                    "countNumber": 5,
                },
                "action": {"type": "expire"},
            },
            {
                "rulePriority": 2,
                "description": "Expire untagged images older than 1 day",
                "selection": {
                    "tagStatus": "untagged",
                    "countType": "sinceImagePushed",
                    "countUnit": "days",
                    "countNumber": 1,
                },
                "action": {"type": "expire"},
            },
            {
                "rulePriority": 3,
                "description": "Expire any image older than 7 days",
                "selection": {
                    "tagStatus": "any",
                    "countType": "sinceImagePushed",
                    "countUnit": "days",
                    "countNumber": 7,
                },
                "action": {"type": "expire"},
            },
        ]
    }
    return json.dumps(policy)


class EcrPullThroughLifecycleStack(Stack):
    """Stack that adds a Repository Creation Template so pull-through cache repos get the lifecycle policy."""

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # Optional: create the pull-through cache rule if you don't have one yet.
        # For Docker Hub public: upstream_registry="docker-hub", upstream_registry_url="registry-1.docker.io".
        ecr.CfnPullThroughCacheRule(
            self,
            "PullThroughCache",
            ecr_repository_prefix=PULL_THROUGH_CACHE_PREFIX,
            upstream_registry="docker-hub",
            upstream_registry_url="https://registry-1.docker.io",
            upstream_repository_prefix="",
        )

        # Repository Creation Template: same prefix as the rule, lifecycle policy applied on repo creation.
        lifecycle_policy_text = load_lifecycle_policy_json()
        # Or use inline: lifecycle_policy_text = build_lifecycle_policy_inline()

        ecr.CfnRepositoryCreationTemplate(
            self,
            "PullThroughLifecycleTemplate",
            prefix=PULL_THROUGH_CACHE_PREFIX,
            applied_for=["PULL_THROUGH_CACHE"],
            description="Lifecycle policy for pull-through cache repos (untagged 1d, any 7d, keep 5 main*)",
            lifecycle_policy=lifecycle_policy_text,
        )


# To use in your app:
#
# from ecr_pull_through_lifecycle_example import EcrPullThroughLifecycleStack
#
# app = cdk.App()
# EcrPullThroughLifecycleStack(app, "EcrPullThroughLifecycle", env=...)
# app.synth()
#
# If the pull-through cache rule already exists elsewhere, remove the
# CfnPullThroughCacheRule block above and set PULL_THROUGH_CACHE_PREFIX
# to the same ecr_repository_prefix used there. Only the
# CfnRepositoryCreationTemplate is required to apply the lifecycle policy.
