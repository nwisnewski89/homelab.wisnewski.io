from aws_cdk import (
    aws_s3 as s3,
    aws_iam as iam,
    Stack
)
from constructs import Construct

class RestrictedS3Stack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # Create S3 bucket
        self.bucket = s3.Bucket(
            self, "RestrictedBucket",
            bucket_name="my-restricted-bucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED
        )
        
        # Add bucket policy to restrict access to specific IAM principals
        self.bucket.add_to_resource_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                principals=[
                    iam.ArnPrincipal("arn:aws:iam::ACCOUNT-ID:user/specific-user"),
                    iam.ArnPrincipal("arn:aws:iam::ACCOUNT-ID:role/specific-instance-profile")
                ],
                actions=[
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:DeleteObject",
                    "s3:ListBucket"
                ],
                resources=[
                    self.bucket.bucket_arn,
                    f"{self.bucket.bucket_arn}/*"
                ]
            )
        )
        
        # Deny all other access
        self.bucket.add_to_resource_policy(
            iam.PolicyStatement(
                effect=iam.Effect.DENY,
                principals=[iam.AnyPrincipal()],
                actions=["s3:*"],
                resources=[
                    self.bucket.bucket_arn,
                    f"{self.bucket.bucket_arn}/*"
                ],
                conditions={
                    "StringNotEquals": {
                        "aws:PrincipalArn": [
                            "arn:aws:iam::ACCOUNT-ID:user/specific-user",
                            "arn:aws:iam::ACCOUNT-ID:role/specific-instance-profile"
                        ]
                    }
                }
            )
        )