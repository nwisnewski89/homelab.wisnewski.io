#!/usr/bin/env python3
"""
CDK Stack: CloudFront distribution serving S3 static content.

- S3 bucket with block public access; only CloudFront can read (via Origin Access Identity).
- CloudFront distribution with the bucket as origin.
"""

from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_s3 as s3
from constructs import Construct


class CloudFrontS3Stack(Stack):
    """CloudFront distribution serving static content from a private S3 bucket."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        bucket_name: str | None = None,
        enable_removal_policy_destroy: bool = False,
        **kwargs,
    ) -> None:
        """
        Args:
            scope: CDK app scope.
            construct_id: Stack id.
            bucket_name: Optional S3 bucket name (default: auto-generated).
            enable_removal_policy_destroy: If True, bucket and logs can be deleted with the stack.
            **kwargs: Additional stack props.
        """
        super().__init__(scope, construct_id, **kwargs)

        removal = (
            RemovalPolicy.DESTROY
            if enable_removal_policy_destroy
            else RemovalPolicy.RETAIN
        )

        # S3 bucket: no public access; only CloudFront will read via OAI
        self.bucket = s3.Bucket(
            self,
            "StaticBucket",
            bucket_name=bucket_name,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=removal,
            auto_delete_objects=enable_removal_policy_destroy,
        )

        # Origin uses OAI: CDK grants CloudFront (and only CloudFront) s3:GetObject on the bucket
        s3_origin = origins.S3Origin(self.bucket)

        self.distribution = cloudfront.Distribution(
            self,
            "Distribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=s3_origin,
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_GET_HEAD_OPTIONS,
                cached_methods=cloudfront.CachedMethods.CACHE_GET_HEAD_OPTIONS,
            ),
            default_root_object="index.html",
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=404,
                    response_page_path="/404.html",
                    ttl=cloudfront.Duration.minutes(5),
                ),
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=404,
                    response_page_path="/404.html",
                    ttl=cloudfront.Duration.minutes(5),
                ),
            ],
            minimum_protocol_version=cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
            comment="Serves static content from S3",
        )

        CfnOutput(
            self,
            "BucketName",
            value=self.bucket.bucket_name,
            description="S3 bucket for static content",
        )
        CfnOutput(
            self,
            "DistributionId",
            value=self.distribution.distribution_id,
            description="CloudFront distribution ID",
        )
        CfnOutput(
            self,
            "DistributionDomainName",
            value=self.distribution.distribution_domain_name,
            description="CloudFront domain (e.g. for CNAME or browser)",
        )
        CfnOutput(
            self,
            "DistributionUrl",
            value=f"https://{self.distribution.distribution_domain_name}",
            description="CloudFront URL (HTTPS)",
        )
