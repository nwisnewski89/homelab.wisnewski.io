#!/usr/bin/env python3
"""List IAM users, their groups, and user inline policy documents (boto3)."""

from __future__ import annotations

import argparse
import json
import sys

import boto3
from botocore.exceptions import BotoCoreError, ClientError


def list_users(client) -> list[str]:
    names: list[str] = []
    paginator = client.get_paginator("list_users")
    for page in paginator.paginate():
        for user in page.get("Users", []):
            names.append(user["UserName"])
    return names


def list_groups_for_user(client, user_name: str) -> list[str]:
    groups: list[str] = []
    paginator = client.get_paginator("list_groups_for_user")
    for page in paginator.paginate(UserName=user_name):
        for g in page.get("Groups", []):
            groups.append(g["GroupName"])
    return groups


def list_inline_policies_for_user(client, user_name: str) -> list[dict]:
    policies: list[dict] = []
    paginator = client.get_paginator("list_user_policies")
    for page in paginator.paginate(UserName=user_name):
        for policy_name in page.get("PolicyNames", []):
            resp = client.get_user_policy(
                UserName=user_name,
                PolicyName=policy_name,
            )
            policies.append({k: v for k, v in resp.items() if k != "ResponseMetadata"})
    return policies


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List IAM users, groups, and inline policies.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a JSON array: UserName, Groups, InlinePolicies (full get_user_policy shapes).",
    )
    args = parser.parse_args()

    try:
        client = boto3.client("iam")
        users = list_users(client)
    except (BotoCoreError, ClientError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    rows: list[dict] = []
    for user_name in users:
        try:
            groups = list_groups_for_user(client, user_name)
            inline = list_inline_policies_for_user(client, user_name)
        except (BotoCoreError, ClientError) as e:
            print(f"error for user {user_name!r}: {e}", file=sys.stderr)
            return 1
        rows.append(
            {
                "UserName": user_name,
                "Groups": groups,
                "InlinePolicies": inline,
            }
        )

    if args.json:
        print(json.dumps(rows, indent=2, default=str))
        return 0

    for row in rows:
        print(f"=== User: {row['UserName']} ===")
        print("  Groups:")
        if row["Groups"]:
            for g in row["Groups"]:
                print(f"    - {g}")
        else:
            print("    (none)")
        print("  Inline policies:")
        if not row["InlinePolicies"]:
            print("    (none)")
        else:
            for pol in row["InlinePolicies"]:
                name = pol.get("PolicyName", "")
                doc = pol.get("PolicyDocument", {})
                print(f"    --- {name} ---")
                print(json.dumps(doc, indent=6))
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
