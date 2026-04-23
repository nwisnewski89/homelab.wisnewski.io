#!/usr/bin/env python3
"""
Create a private S3 bucket and vmimport service role for EC2 VM Import.

This script prepares AWS resources needed to import a RAW disk image into EC2:
1) Creates (or verifies) a private S3 bucket
2) Enables S3 block-public-access settings
3) Creates (or updates) the IAM role named "vmimport"
4) Attaches/updates an inline IAM policy that allows VM Import to read your bucket

Example:
    python setup_vmimport_private_bucket.py \
      --bucket-name my-private-vmimport-bucket-123456 \
      --region us-east-1 \
      --image-key opnsense/opnsense-nano-amd64.raw
"""

from __future__ import annotations

import argparse
import json
import sys

import boto3
from botocore.exceptions import ClientError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Set up private S3 bucket + vmimport role for EC2 VM Import."
    )
    parser.add_argument(
        "--bucket-name",
        required=True,
        help="Globally unique S3 bucket name for VM images.",
    )
    parser.add_argument(
        "--region",
        default="us-east-1",
        help="AWS region for resources (default: us-east-1).",
    )
    parser.add_argument(
        "--role-name",
        default="vmimport",
        help='IAM role name for VM Import (default: "vmimport").',
    )
    parser.add_argument(
        "--policy-name",
        default="vmimport",
        help='Inline IAM policy name on the vmimport role (default: "vmimport").',
    )
    parser.add_argument(
        "--image-key",
        default="opnsense/opnsense-nano-amd64.raw",
        help="Expected object key in S3 for your RAW image.",
    )
    return parser.parse_args()


def ensure_bucket(s3_client, bucket_name: str, region: str) -> None:
    try:
        s3_client.head_bucket(Bucket=bucket_name)
        print(f"[OK] Bucket already exists and is accessible: {bucket_name}")
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        if error_code in {"404", "NoSuchBucket"}:
            create_params = {"Bucket": bucket_name}
            if region != "us-east-1":
                create_params["CreateBucketConfiguration"] = {
                    "LocationConstraint": region
                }
            s3_client.create_bucket(**create_params)
            print(f"[CREATED] Bucket: {bucket_name}")
        else:
            raise

    s3_client.put_public_access_block(
        Bucket=bucket_name,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    )
    print(f"[OK] Enforced bucket-level public access block on: {bucket_name}")


def ensure_vmimport_role(iam_client, role_name: str) -> None:
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "vmie.amazonaws.com"},
                "Action": "sts:AssumeRole",
                "Condition": {
                    "StringEquals": {"sts:Externalid": "vmimport"},
                },
            }
        ],
    }

    try:
        iam_client.get_role(RoleName=role_name)
        print(f"[OK] IAM role already exists: {role_name}")
    except iam_client.exceptions.NoSuchEntityException:
        iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="Service role for EC2 VM Import/Export.",
        )
        print(f"[CREATED] IAM role: {role_name}")

    # Always update trust policy to keep it correct/idempotent.
    iam_client.update_assume_role_policy(
        RoleName=role_name,
        PolicyDocument=json.dumps(trust_policy),
    )
    print(f"[OK] Updated trust policy for role: {role_name}")


def put_vmimport_policy(
    iam_client,
    role_name: str,
    policy_name: str,
    bucket_name: str,
    image_key: str,
) -> None:
    policy_document = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "VMImportEC2Permissions",
                "Effect": "Allow",
                "Action": [
                    "ec2:ModifySnapshotAttribute",
                    "ec2:CopySnapshot",
                    "ec2:RegisterImage",
                    "ec2:Describe*",
                ],
                "Resource": "*",
            },
            {
                "Sid": "VMImportReadBucket",
                "Effect": "Allow",
                "Action": [
                    "s3:GetBucketLocation",
                    "s3:ListBucket",
                ],
                "Resource": f"arn:aws:s3:::{bucket_name}",
            },
            {
                "Sid": "VMImportReadObject",
                "Effect": "Allow",
                "Action": [
                    "s3:GetObject",
                ],
                "Resource": f"arn:aws:s3:::{bucket_name}/{image_key}",
            },
        ],
    }

    iam_client.put_role_policy(
        RoleName=role_name,
        PolicyName=policy_name,
        PolicyDocument=json.dumps(policy_document),
    )
    print(
        f"[OK] Applied inline policy '{policy_name}' to role '{role_name}' "
        f"for bucket '{bucket_name}' and key '{image_key}'"
    )


def main() -> int:
    args = parse_args()
    session = boto3.session.Session(region_name=args.region)
    sts = session.client("sts")
    s3 = session.client("s3")
    iam = session.client("iam")

    try:
        account_id = sts.get_caller_identity()["Account"]
        print(f"[OK] Caller account: {account_id}")

        ensure_bucket(s3, args.bucket_name, args.region)
        ensure_vmimport_role(iam, args.role_name)
        put_vmimport_policy(
            iam_client=iam,
            role_name=args.role_name,
            policy_name=args.policy_name,
            bucket_name=args.bucket_name,
            image_key=args.image_key,
        )

        print("\nSetup complete.")
        print("Next steps:")
        print(
            f"1) Upload your RAW image to s3://{args.bucket_name}/{args.image_key}"
        )
        print("2) Run EC2 import-image using the vmimport role.")
        print("Example import command:")
        print(
            "aws ec2 import-image "
            "--description \"OPNsense nano amd64\" "
            "--disk-containers "
            f"'Format=RAW,UserBucket={{S3Bucket={args.bucket_name},S3Key={args.image_key}}}' "
            f"--region {args.region}"
        )
        return 0
    except ClientError as exc:
        print(f"[ERROR] AWS API call failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] Unexpected failure: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
