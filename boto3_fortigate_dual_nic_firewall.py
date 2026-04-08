#!/usr/bin/env python3
"""
Deploy a FortiGate VM in AWS with dual NICs for firewall + SNAT.

Topology:
- NIC0 (public): in public subnet (toward IGW)
- NIC1 (private): in private subnet (default gateway for private workloads)

This script:
1) Creates/uses security groups for public/private FortiGate interfaces.
2) Creates two ENIs (public + private) and disables source/destination check.
3) Launches one FortiGate EC2 instance with both ENIs attached.
4) Optionally allocates/associates an Elastic IP to the public ENI.
5) Updates private route table default route (0.0.0.0/0) to FortiGate private ENI.
6) Supports cleanup of resources created by this script.

Example:
    python boto3_fortigate_dual_nic_firewall.py \
      --action create \
      --vpc-id vpc-0123456789abcdef0 \
      --public-subnet-id subnet-public123 \
      --private-subnet-id subnet-private456 \
      --fortigate-ami-id ami-0abc123def4567890 \
      --name-prefix fgt \
      --allocate-eip
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import sys
from typing import Dict, List, Optional

import boto3
from botocore.exceptions import ClientError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deploy/cleanup FortiGate dual-NIC firewall with private subnet default route."
    )
    parser.add_argument("--action", choices=["create", "cleanup"], default="create")
    parser.add_argument("--vpc-id", required=True, help="VPC ID")
    parser.add_argument("--public-subnet-id", required=True, help="Public subnet ID")
    parser.add_argument("--private-subnet-id", required=True, help="Private subnet ID")
    parser.add_argument(
        "--fortigate-ami-id",
        default=None,
        help="FortiGate AMI ID (required for create)",
    )
    parser.add_argument("--name-prefix", default="fortigate", help="Name prefix for tags")
    parser.add_argument("--instance-type", default="c6i.large", help="EC2 instance type")
    parser.add_argument("--key-name", default=None, help="Optional EC2 key pair")
    parser.add_argument(
        "--user-data-file",
        default=None,
        help="Optional file path containing FortiGate bootstrap CLI config",
    )
    parser.add_argument(
        "--public-route-table-id",
        default=None,
        help="Optional public route table ID; auto-discovered from public subnet if omitted",
    )
    parser.add_argument(
        "--private-route-table-id",
        default=None,
        help="Optional private route table ID; auto-discovered from private subnet if omitted",
    )
    parser.add_argument(
        "--allocate-eip",
        action="store_true",
        help="Allocate and associate Elastic IP to the public ENI",
    )
    parser.add_argument("--region", default=None, help="AWS region override")
    return parser.parse_args()


def ensure_subnet_in_vpc(ec2_client, subnet_id: str, vpc_id: str) -> Dict:
    response = ec2_client.describe_subnets(SubnetIds=[subnet_id])
    subnets = response.get("Subnets", [])
    if not subnets:
        raise RuntimeError(f"Subnet not found: {subnet_id}")
    subnet = subnets[0]
    if subnet["VpcId"] != vpc_id:
        raise RuntimeError(f"Subnet {subnet_id} is not in VPC {vpc_id}")
    return subnet


def get_route_table_for_subnet(ec2_client, subnet_id: str, vpc_id: str) -> str:
    explicit = ec2_client.describe_route_tables(
        Filters=[
            {"Name": "vpc-id", "Values": [vpc_id]},
            {"Name": "association.subnet-id", "Values": [subnet_id]},
        ]
    )["RouteTables"]
    if explicit:
        return explicit[0]["RouteTableId"]

    main = ec2_client.describe_route_tables(
        Filters=[
            {"Name": "vpc-id", "Values": [vpc_id]},
            {"Name": "association.main", "Values": ["true"]},
        ]
    )["RouteTables"]
    if main:
        return main[0]["RouteTableId"]

    raise RuntimeError(f"Could not find route table for subnet {subnet_id}")


def create_or_get_security_group(
    ec2_client,
    vpc_id: str,
    group_name: str,
    description: str,
    ingress_permissions: List[Dict],
) -> str:
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
        print(f"Created security group: {group_name} ({sg_id})")
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "InvalidGroup.Duplicate":
            raise
        existing = ec2_client.describe_security_groups(
            Filters=[
                {"Name": "vpc-id", "Values": [vpc_id]},
                {"Name": "group-name", "Values": [group_name]},
            ]
        )["SecurityGroups"]
        if not existing:
            raise
        sg_id = existing[0]["GroupId"]
        print(f"Using existing security group: {group_name} ({sg_id})")

    try:
        ec2_client.authorize_security_group_ingress(
            GroupId=sg_id, IpPermissions=ingress_permissions
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "InvalidPermission.Duplicate":
            raise

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


def create_eni(
    ec2_client,
    subnet_id: str,
    sg_id: str,
    name: str,
    name_prefix: str,
) -> str:
    response = ec2_client.create_network_interface(
        SubnetId=subnet_id,
        Groups=[sg_id],
        TagSpecifications=[
            {
                "ResourceType": "network-interface",
                "Tags": [
                    {"Key": "Name", "Value": name},
                    {"Key": "NamePrefix", "Value": name_prefix},
                ],
            }
        ],
    )
    eni_id = response["NetworkInterface"]["NetworkInterfaceId"]
    print(f"Created ENI {name}: {eni_id}")

    ec2_client.modify_network_interface_attribute(
        NetworkInterfaceId=eni_id, SourceDestCheck={"Value": False}
    )
    print(f"Disabled source/destination check on ENI: {eni_id}")
    return eni_id


def replace_default_route_to_eni(ec2_client, route_table_id: str, eni_id: str) -> None:
    try:
        ec2_client.replace_route(
            RouteTableId=route_table_id,
            DestinationCidrBlock="0.0.0.0/0",
            NetworkInterfaceId=eni_id,
        )
        print(f"Replaced default route in {route_table_id} to ENI {eni_id}")
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "InvalidRoute.NotFound":
            ec2_client.create_route(
                RouteTableId=route_table_id,
                DestinationCidrBlock="0.0.0.0/0",
                NetworkInterfaceId=eni_id,
            )
            print(f"Created default route in {route_table_id} to ENI {eni_id}")
        else:
            raise


def build_default_fortigate_userdata(name_prefix: str, private_cidr: str) -> str:
    # FortiGate bootstrap CLI delivered via EC2 user data.
    network = ipaddress.ip_network(private_cidr, strict=False)
    subnet_ip = str(network.network_address)
    subnet_mask = str(network.netmask)

    return f"""config system global
    set hostname {name_prefix}-fw
end
config firewall address
    edit "private-subnet-src"
        set subnet {subnet_ip} {subnet_mask}
    next
    edit "allow-google-com"
        set type fqdn
        set fqdn "google.com"
    next
    edit "allow-ifconfig-me"
        set type fqdn
        set fqdn "ifconfig.me"
    next
    edit "allow-amazonaws-wildcard"
        set type wildcard-fqdn
        set wildcard-fqdn "*.amazonaws.com"
    next
end
config firewall addrgrp
    edit "allowed-egress-fqdns"
        set member "allow-google-com" "allow-ifconfig-me" "allow-amazonaws-wildcard"
    next
end
config firewall policy
    edit 0
        set name "allow-private-to-approved-fqdns-nat"
        set srcintf "port2"
        set dstintf "port1"
        set srcaddr "private-subnet-src"
        set dstaddr "allowed-egress-fqdns"
        set action accept
        set schedule "always"
        set service "ALL"
        set nat enable
        set logtraffic all
    next
    edit 0
        set name "deny-private-to-internet-default"
        set srcintf "port2"
        set dstintf "port1"
        set srcaddr "private-subnet-src"
        set dstaddr "all"
        set action deny
        set schedule "always"
        set service "ALL"
        set logtraffic all
    next
end
"""


def load_userdata(args: argparse.Namespace, private_cidr: str) -> str:
    if args.user_data_file:
        with open(args.user_data_file, "r", encoding="utf-8") as infile:
            return infile.read()
    return build_default_fortigate_userdata(args.name_prefix, private_cidr)


def launch_fortigate_instance(
    ec2_resource,
    image_id: str,
    instance_type: str,
    public_eni_id: str,
    private_eni_id: str,
    name_prefix: str,
    key_name: Optional[str],
    user_data: str,
) -> str:
    params: Dict = {
        "ImageId": image_id,
        "MinCount": 1,
        "MaxCount": 1,
        "InstanceType": instance_type,
        "NetworkInterfaces": [
            {"DeviceIndex": 0, "NetworkInterfaceId": public_eni_id},
            {"DeviceIndex": 1, "NetworkInterfaceId": private_eni_id},
        ],
        "TagSpecifications": [
            {
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "Name", "Value": f"{name_prefix}-fw"},
                    {"Key": "NamePrefix", "Value": name_prefix},
                    {"Key": "Role", "Value": "fortigate-firewall"},
                ],
            }
        ],
        "UserData": user_data,
    }
    if key_name:
        params["KeyName"] = key_name

    instances = ec2_resource.create_instances(**params)
    instance_id = instances[0].id
    print(f"Launched FortiGate instance: {instance_id}")
    return instance_id


def allocate_and_associate_eip(ec2_client, public_eni_id: str, name_prefix: str) -> str:
    alloc = ec2_client.allocate_address(Domain="vpc")
    alloc_id = alloc["AllocationId"]
    public_ip = alloc["PublicIp"]

    ec2_client.associate_address(
        AllocationId=alloc_id,
        NetworkInterfaceId=public_eni_id,
        AllowReassociation=True,
    )

    ec2_client.create_tags(
        Resources=[alloc_id],
        Tags=[
            {"Key": "Name", "Value": f"{name_prefix}-public-eip"},
            {"Key": "NamePrefix", "Value": name_prefix},
        ],
    )

    print(f"Allocated and associated EIP {public_ip} ({alloc_id}) to {public_eni_id}")
    return public_ip


def create_stack(ec2_client, ec2_resource, args: argparse.Namespace) -> int:
    if not args.fortigate_ami_id:
        raise RuntimeError("--fortigate-ami-id is required for create action")

    public_subnet = ensure_subnet_in_vpc(ec2_client, args.public_subnet_id, args.vpc_id)
    private_subnet = ensure_subnet_in_vpc(ec2_client, args.private_subnet_id, args.vpc_id)
    if public_subnet["AvailabilityZone"] != private_subnet["AvailabilityZone"]:
        raise RuntimeError("Public and private subnets must be in the same AZ for one instance")

    private_rt = args.private_route_table_id or get_route_table_for_subnet(
        ec2_client, args.private_subnet_id, args.vpc_id
    )
    public_rt = args.public_route_table_id or get_route_table_for_subnet(
        ec2_client, args.public_subnet_id, args.vpc_id
    )

    public_sg_id = create_or_get_security_group(
        ec2_client=ec2_client,
        vpc_id=args.vpc_id,
        group_name=f"{args.name_prefix}-fgt-public-sg",
        description="FortiGate public interface SG",
        ingress_permissions=[
            {
                "IpProtocol": "tcp",
                "FromPort": 443,
                "ToPort": 443,
                "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "HTTPS management"}],
            },
            {
                "IpProtocol": "tcp",
                "FromPort": 22,
                "ToPort": 22,
                "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "SSH management"}],
            },
            {
                "IpProtocol": "udp",
                "FromPort": 500,
                "ToPort": 500,
                "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "IPsec IKE"}],
            },
            {
                "IpProtocol": "udp",
                "FromPort": 4500,
                "ToPort": 4500,
                "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "IPsec NAT-T"}],
            },
        ],
    )

    private_sg_id = create_or_get_security_group(
        ec2_client=ec2_client,
        vpc_id=args.vpc_id,
        group_name=f"{args.name_prefix}-fgt-private-sg",
        description="FortiGate private interface SG",
        ingress_permissions=[
            {
                "IpProtocol": "-1",
                "IpRanges": [
                    {
                        "CidrIp": private_subnet["CidrBlock"],
                        "Description": "All from private subnet",
                    }
                ],
            }
        ],
    )

    public_eni_id = create_eni(
        ec2_client=ec2_client,
        subnet_id=args.public_subnet_id,
        sg_id=public_sg_id,
        name=f"{args.name_prefix}-fgt-public-eni",
        name_prefix=args.name_prefix,
    )
    private_eni_id = create_eni(
        ec2_client=ec2_client,
        subnet_id=args.private_subnet_id,
        sg_id=private_sg_id,
        name=f"{args.name_prefix}-fgt-private-eni",
        name_prefix=args.name_prefix,
    )

    instance_id = launch_fortigate_instance(
        ec2_resource=ec2_resource,
        image_id=args.fortigate_ami_id,
        instance_type=args.instance_type,
        public_eni_id=public_eni_id,
        private_eni_id=private_eni_id,
        name_prefix=args.name_prefix,
        key_name=args.key_name,
        user_data=load_userdata(args=args, private_cidr=private_subnet["CidrBlock"]),
    )

    instance = ec2_resource.Instance(instance_id)
    instance.wait_until_running()
    instance.reload()
    print(f"Instance running: {instance_id}")

    replace_default_route_to_eni(ec2_client, private_rt, private_eni_id)

    eip = None
    if args.allocate_eip:
        eip = allocate_and_associate_eip(ec2_client, public_eni_id, args.name_prefix)

    output = {
        "InstanceId": instance_id,
        "PublicEniId": public_eni_id,
        "PrivateEniId": private_eni_id,
        "PublicRouteTableId": public_rt,
        "PrivateRouteTableId": private_rt,
        "PublicEip": eip,
        "NextStep": "Confirm FortiGate bootstrap applied and test egress to allowed FQDNs",
    }
    print(json.dumps(output, indent=2))
    return 0


def cleanup_by_name_prefix(ec2_client, ec2_resource, vpc_id: str, name_prefix: str) -> int:
    reservations = ec2_client.describe_instances(
        Filters=[
            {"Name": "vpc-id", "Values": [vpc_id]},
            {"Name": "tag:NamePrefix", "Values": [name_prefix]},
            {
                "Name": "instance-state-name",
                "Values": ["pending", "running", "stopping", "stopped"],
            },
        ]
    ).get("Reservations", [])

    instance_ids: List[str] = []
    for reservation in reservations:
        for instance in reservation.get("Instances", []):
            instance_ids.append(instance["InstanceId"])
    if instance_ids:
        ec2_client.terminate_instances(InstanceIds=instance_ids)
        print(f"Terminating instances: {', '.join(instance_ids)}")
        ec2_client.get_waiter("instance_terminated").wait(InstanceIds=instance_ids)
        print("Instances terminated.")

    enis = ec2_client.describe_network_interfaces(
        Filters=[
            {"Name": "vpc-id", "Values": [vpc_id]},
            {"Name": "tag:NamePrefix", "Values": [name_prefix]},
        ]
    ).get("NetworkInterfaces", [])

    for eni in enis:
        eni_id = eni["NetworkInterfaceId"]
        for association in [eni.get("Association")] if eni.get("Association") else []:
            alloc_id = association.get("AllocationId")
            assoc_id = association.get("AssociationId")
            if assoc_id:
                ec2_client.disassociate_address(AssociationId=assoc_id)
                print(f"Disassociated EIP association: {assoc_id}")
            if alloc_id:
                ec2_client.release_address(AllocationId=alloc_id)
                print(f"Released EIP allocation: {alloc_id}")
        if eni.get("Status") == "in-use":
            continue
        ec2_client.delete_network_interface(NetworkInterfaceId=eni_id)
        print(f"Deleted ENI: {eni_id}")

    for sg_name in (
        f"{name_prefix}-fgt-public-sg",
        f"{name_prefix}-fgt-private-sg",
    ):
        groups = ec2_client.describe_security_groups(
            Filters=[
                {"Name": "vpc-id", "Values": [vpc_id]},
                {"Name": "group-name", "Values": [sg_name]},
            ]
        ).get("SecurityGroups", [])
        for sg in groups:
            try:
                ec2_client.delete_security_group(GroupId=sg["GroupId"])
                print(f"Deleted SG: {sg['GroupId']}")
            except ClientError as exc:
                print(f"Could not delete SG {sg['GroupId']}: {exc}")

    print("Cleanup complete.")
    return 0


def main() -> int:
    args = parse_args()
    session = boto3.Session(region_name=args.region)
    ec2_client = session.client("ec2")
    ec2_resource = session.resource("ec2")

    if args.action == "cleanup":
        return cleanup_by_name_prefix(
            ec2_client=ec2_client,
            ec2_resource=ec2_resource,
            vpc_id=args.vpc_id,
            name_prefix=args.name_prefix,
        )

    return create_stack(ec2_client=ec2_client, ec2_resource=ec2_resource, args=args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ClientError as exc:
        print(f"AWS API error: {exc}", file=sys.stderr)
        raise SystemExit(1)
    except Exception as exc:  # pylint: disable=broad-except
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
