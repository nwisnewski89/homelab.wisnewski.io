import json
from aws_cdk import aws_ecr as ecr

# Same prefix as your CfnPullThroughCacheRule.ecr_repository_prefix
PREFIX = "docker-hub"

lifecycle_policy_text = json.dumps({
    "rules": [
        {"rulePriority": 1, "description": "Keep 5 main*", "selection": {"tagStatus": "tagged", "tagPatternList": ["main*"], "countType": "imageCountMoreThan", "countNumber": 5}, "action": {"type": "expire"}},
        {"rulePriority": 2, "description": "Untagged > 1 day", "selection": {"tagStatus": "untagged", "countType": "sinceImagePushed", "countUnit": "days", "countNumber": 1}, "action": {"type": "expire"}},
        {"rulePriority": 3, "description": "Any > 7 days", "selection": {"tagStatus": "any", "countType": "sinceImagePushed", "countUnit": "days", "countNumber": 7}, "action": {"type": "expire"}},
    ]
})

ecr.CfnRepositoryCreationTemplate(
    self, "PullThroughLifecycle",
    prefix=PREFIX,
    applied_for=["PULL_THROUGH_CACHE"],
    lifecycle_policy=lifecycle_policy_text,
)