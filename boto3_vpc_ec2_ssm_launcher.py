#!/usr/bin/env python3
"""
Launch one Amazon Linux t3.micro instance per subnet in a VPC.

This script:
1) Accepts a VPC ID and name prefix.
2) Creates a security group in the VPC.
3) Allows all inbound traffic from the VPC CIDR.
4) Allows all outbound traffic.
5) Creates/uses an IAM role + instance profile with AmazonSSMManagedInstanceCore.
6) Launches one t3.micro Amazon Linux instance in each subnet.
7) Creates Route53 A records in homelab.wisnewski.io using the name prefix.

Example:
    python boto3_vpc_ec2_ssm_launcher.py \
      --vpc-id vpc-0123456789abcdef0 \
      --name-prefix app
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Dict, List

import boto3
from botocore.exceptions import ClientError


HOSTED_ZONE_NAME = "homelab.wisnewski.io."
SSM_POLICY_ARN = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create SG + IAM profile, launch EC2 in each subnet, and add Route53 records."
    )
    parser.add_argument("--vpc-id", required=True, help="Target VPC ID (example: vpc-abc123)")
    parser.add_argument(
        "--name-prefix",
        required=True,
        help="Prefix for instance names and DNS records (example: app)",
    )
    parser.add_argument(
        "--region",
        default=None,
        help="AWS region override (default: boto3 resolution chain)",
    )
    return parser.parse_args()


def get_vpc(ec2_client, vpc_id: str) -> Dict:
    response = ec2_client.describe_vpcs(VpcIds=[vpc_id])
    vpcs = response.get("Vpcs", [])
    if not vpcs:
        raise RuntimeError(f"VPC not found: {vpc_id}")
    return vpcs[0]


def get_subnets(ec2_client, vpc_id: str) -> List[Dict]:
    response = ec2_client.describe_subnets(
        Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]
    )
    subnets = response.get("Subnets", [])
    if not subnets:
        raise RuntimeError(f"No subnets found in VPC: {vpc_id}")
    return sorted(subnets, key=lambda s: s["SubnetId"])


def create_security_group(ec2_client, vpc_id: str, vpc_cidr: str, name_prefix: str) -> str:
    group_name = f"{name_prefix}-vpc-internal-all"
    description = f"Inbound from {vpc_cidr}, outbound all"

    try:
        response = ec2_client.create_security_group(
            GroupName=group_name,
            Description=description,
            VpcId=vpc_id,
            TagSpecifications=[
                {
                    "ResourceType": "security-group",
                    "Tags": [{"Key": "Name", "Value": group_name}],
                }
            ],
        )
        sg_id = response["GroupId"]
        print(f"Created security group: {sg_id}")
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "InvalidGroup.Duplicate":
            raise
        existing = ec2_client.describe_security_groups(
            Filters=[
                {"Name": "group-name", "Values": [group_name]},
                {"Name": "vpc-id", "Values": [vpc_id]},
            ]
        )["SecurityGroups"]
        if not existing:
            raise
        sg_id = existing[0]["GroupId"]
        print(f"Using existing security group: {sg_id}")

    # Ingress: all protocols/ports from VPC CIDR
    try:
        ec2_client.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    "IpProtocol": "-1",
                    "IpRanges": [{"CidrIp": vpc_cidr, "Description": "Allow all from VPC"}],
                }
            ],
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "InvalidPermission.Duplicate":
            raise

    # Egress: all outbound
    try:
        ec2_client.authorize_security_group_egress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    "IpProtocol": "-1",
                    "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "Allow all outbound"}],
                }
            ],
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "InvalidPermission.Duplicate":
            raise

    return sg_id


def ensure_iam_instance_profile(iam_client, name_prefix: str) -> str:
    role_name = f"{name_prefix}-ssm-role"
    profile_name = f"{name_prefix}-ssm-instance-profile"

    assume_role_doc = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "ec2.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }

    try:
        iam_client.get_role(RoleName=role_name)
        print(f"Using existing IAM role: {role_name}")
    except iam_client.exceptions.NoSuchEntityException:
        iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(assume_role_doc),
            Description="EC2 role for SSM managed instance access",
            Tags=[{"Key": "Name", "Value": role_name}],
        )
        print(f"Created IAM role: {role_name}")

    # Attach managed policy (idempotent)
    iam_client.attach_role_policy(RoleName=role_name, PolicyArn=SSM_POLICY_ARN)

    try:
        iam_client.get_instance_profile(InstanceProfileName=profile_name)
        print(f"Using existing instance profile: {profile_name}")
    except iam_client.exceptions.NoSuchEntityException:
        iam_client.create_instance_profile(InstanceProfileName=profile_name)
        print(f"Created instance profile: {profile_name}")

    # Add role to profile if missing
    profile = iam_client.get_instance_profile(InstanceProfileName=profile_name)["InstanceProfile"]
    role_names = {role["RoleName"] for role in profile.get("Roles", [])}
    if role_name not in role_names:
        iam_client.add_role_to_instance_profile(
            InstanceProfileName=profile_name,
            RoleName=role_name,
        )
        print(f"Added role {role_name} to instance profile {profile_name}")

    return profile_name


def get_latest_amazon_linux_ami(ssm_client) -> str:
    response = ssm_client.get_parameter(
        Name="/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
    )
    return response["Parameter"]["Value"]


def get_hosted_zone_id(route53_client, zone_name: str) -> str:
    paginator = route53_client.get_paginator("list_hosted_zones")
    for page in paginator.paginate():
        for zone in page.get("HostedZones", []):
            if zone["Name"] == zone_name:
                return zone["Id"].split("/")[-1]
    raise RuntimeError(f"Hosted zone not found: {zone_name}")


def create_dns_record(route53_client, hosted_zone_id: str, fqdn: str, ip: str) -> None:
    route53_client.change_resource_record_sets(
        HostedZoneId=hosted_zone_id,
        ChangeBatch={
            "Comment": "Managed by boto3_vpc_ec2_ssm_launcher.py",
            "Changes": [
                {
                    "Action": "UPSERT",
                    "ResourceRecordSet": {
                        "Name": fqdn,
                        "Type": "A",
                        "TTL": 60,
                        "ResourceRecords": [{"Value": ip}],
                    },
                }
            ],
        },
    )


def launch_instances(
    ec2_resource,
    subnets: List[Dict],
    image_id: str,
    security_group_id: str,
    instance_profile_name: str,
    name_prefix: str,
) -> List[Dict]:
    launched = []
    for index, subnet in enumerate(subnets, start=1):
        subnet_id = subnet["SubnetId"]
        az = subnet["AvailabilityZone"]
        instance_name = f"{name_prefix}-{index}"

        instances = ec2_resource.create_instances(
            ImageId=image_id,
            MinCount=1,
            MaxCount=1,
            InstanceType="t3.micro",
            SubnetId=subnet_id,
            SecurityGroupIds=[security_group_id],
            IamInstanceProfile={"Name": instance_profile_name},
            TagSpecifications=[
                {
                    "ResourceType": "instance",
                    "Tags": [
                        {"Key": "Name", "Value": instance_name},
                        {"Key": "NamePrefix", "Value": name_prefix},
                    ],
                }
            ],
        )

        instance = instances[0]
        launched.append(
            {
                "InstanceId": instance.id,
                "InstanceName": instance_name,
                "SubnetId": subnet_id,
                "AvailabilityZone": az,
            }
        )
        print(
            f"Launched instance {instance.id} in {subnet_id} ({az}) "
            f"with name {instance_name}"
        )
    return launched


def wait_for_running_and_collect_ips(ec2_resource, launched: List[Dict]) -> List[Dict]:
    for item in launched:
        instance = ec2_resource.Instance(item["InstanceId"])
        instance.wait_until_running()
        instance.reload()
        item["PrivateIpAddress"] = instance.private_ip_address
        item["PublicIpAddress"] = instance.public_ip_address
    return launched


def main() -> int:
    args = parse_args()

    session = boto3.Session(region_name=args.region)
    ec2_client = session.client("ec2")
    ec2_resource = session.resource("ec2")
    iam_client = session.client("iam")
    ssm_client = session.client("ssm")
    route53_client = session.client("route53")

    vpc = get_vpc(ec2_client, args.vpc_id)
    vpc_cidr = vpc["CidrBlock"]
    subnets = get_subnets(ec2_client, args.vpc_id)

    sg_id = create_security_group(ec2_client, args.vpc_id, vpc_cidr, args.name_prefix)
    profile_name = ensure_iam_instance_profile(iam_client, args.name_prefix)
    ami_id = get_latest_amazon_linux_ami(ssm_client)
    hosted_zone_id = get_hosted_zone_id(route53_client, HOSTED_ZONE_NAME)

    launched = launch_instances(
        ec2_resource=ec2_resource,
        subnets=subnets,
        image_id=ami_id,
        security_group_id=sg_id,
        instance_profile_name=profile_name,
        name_prefix=args.name_prefix,
    )
    launched = wait_for_running_and_collect_ips(ec2_resource, launched)

    for item in launched:
        fqdn = f"{item['InstanceName']}.{HOSTED_ZONE_NAME}".rstrip(".")
        create_dns_record(route53_client, hosted_zone_id, fqdn, item["PrivateIpAddress"])
        item["DnsName"] = fqdn
        print(f"Upserted Route53 A record: {fqdn} -> {item['PrivateIpAddress']}")

    print("\nLaunch complete:")
    print(json.dumps(launched, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ClientError as exc:
        print(f"AWS API error: {exc}", file=sys.stderr)
        raise SystemExit(1)
    except Exception as exc:  # pylint: disable=broad-except
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
