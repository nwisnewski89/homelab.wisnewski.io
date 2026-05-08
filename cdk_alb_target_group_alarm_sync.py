#!/usr/bin/env python3
"""
CDK stack that keeps hostname-specific ALB target health alarms in sync.

The stack creates:
- One CloudWatch alarm named <hostname>-ALBTargetHealth for each hostname.
- A Lambda function that maps host-header listener rules to target groups.
- An EventBridge rule that invokes the Lambda after ELBv2 listener/rule/target
  group updates are observed through CloudTrail.
- A deploy-time custom resource invocation so alarms are synced on deployment.

Example:
    cdk deploy -a "python cdk_alb_target_group_alarm_sync.py" \
      -c listener_arns='["arn:aws:elasticloadbalancing:us-east-1:123456789012:listener/app/my-alb/abc/def"]' \
      -c hostnames='["app.example.com","api.example.com"]' \
      -c notification_emails='["ops@example.com"]'
"""

from __future__ import annotations

import json
import re
from typing import Any

from aws_cdk import (
    App,
    CfnOutput,
    CustomResource,
    Duration,
    Stack,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cloudwatch_actions,
    aws_custom_resources as cr,
    aws_events as events,
    aws_events_targets as events_targets,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_sns as sns,
    aws_sns_subscriptions as sns_subscriptions,
)
from constructs import Construct


LAMBDA_CODE = r"""
import fnmatch
import json
import logging
import os
from typing import Any

import boto3

LOG = logging.getLogger()
LOG.setLevel(logging.INFO)

cloudwatch = boto3.client("cloudwatch")
elbv2 = boto3.client("elbv2")


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    LOG.info("Received event: %s", json.dumps(event, default=str))

    if event.get("RequestType") == "Delete":
        return {"PhysicalResourceId": physical_resource_id()}

    hostnames = json.loads(os.environ["HOSTNAMES"])
    listener_arns = json.loads(os.environ["LISTENER_ARNS"])
    alarm_actions = json.loads(os.environ.get("ALARM_ACTIONS", "[]"))

    hostname_targets = find_hostname_target_groups(hostnames, listener_arns)
    updated_alarms = []
    missing_hostnames = []

    for hostname in hostnames:
        target_group_arn = hostname_targets.get(hostname)
        if not target_group_arn:
            missing_hostnames.append(hostname)
            LOG.warning("No listener rule target group found for hostname %s", hostname)
            continue

        dimensions = metric_dimensions_for_target_group(target_group_arn)
        put_target_health_alarm(hostname, dimensions, alarm_actions)
        updated_alarms.append(hostname)

    LOG.info(
        "Updated %d alarms; missing hostnames: %s",
        len(updated_alarms),
        ", ".join(missing_hostnames) or "none",
    )

    return {
        "PhysicalResourceId": physical_resource_id(),
        "Data": {
            "UpdatedAlarms": ",".join(updated_alarms),
            "MissingHostnames": ",".join(missing_hostnames),
        },
    }


def physical_resource_id() -> str:
    return "alb-target-health-alarm-sync"


def find_hostname_target_groups(
    hostnames: list[str], listener_arns: list[str]
) -> dict[str, str]:
    remaining = {hostname.lower(): hostname for hostname in hostnames}
    matches: dict[str, str] = {}

    for listener_arn in listener_arns:
        paginator = elbv2.get_paginator("describe_rules")
        for page in paginator.paginate(ListenerArn=listener_arn):
            for rule in page["Rules"]:
                host_values = host_header_values(rule)
                if not host_values:
                    continue

                target_group_arn = target_group_for_rule(rule)
                if not target_group_arn:
                    continue

                for requested_lower, requested_hostname in list(remaining.items()):
                    if any(host_matches(requested_lower, value) for value in host_values):
                        matches[requested_hostname] = target_group_arn
                        del remaining[requested_lower]

            if not remaining:
                return matches

    return matches


def host_header_values(rule: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for condition in rule.get("Conditions", []):
        if condition.get("Field") != "host-header":
            continue

        values.extend(condition.get("Values", []))
        values.extend(condition.get("HostHeaderConfig", {}).get("Values", []))

    return values


def target_group_for_rule(rule: dict[str, Any]) -> str | None:
    for action in sorted(rule.get("Actions", []), key=lambda item: item.get("Order", 1)):
        if action.get("Type") != "forward":
            continue

        if action.get("TargetGroupArn"):
            return action["TargetGroupArn"]

        forward_config = action.get("ForwardConfig", {})
        target_groups = forward_config.get("TargetGroups", [])
        if target_groups:
            return max(
                target_groups,
                key=lambda item: item.get("Weight", 1),
            ).get("TargetGroupArn")

    return None


def host_matches(requested_hostname: str, rule_value: str) -> bool:
    return fnmatch.fnmatch(requested_hostname, rule_value.lower())


def metric_dimensions_for_target_group(target_group_arn: str) -> dict[str, str]:
    response = elbv2.describe_target_groups(TargetGroupArns=[target_group_arn])
    target_group = response["TargetGroups"][0]

    load_balancer_arns = target_group.get("LoadBalancerArns", [])
    if not load_balancer_arns:
        raise ValueError(f"Target group {target_group_arn} is not attached to a load balancer")

    return {
        "TargetGroup": target_group_metric_name(target_group_arn),
        "LoadBalancer": load_balancer_metric_name(load_balancer_arns[0]),
    }


def target_group_metric_name(target_group_arn: str) -> str:
    return target_group_arn.split(":", 5)[5]


def load_balancer_metric_name(load_balancer_arn: str) -> str:
    resource_name = load_balancer_arn.split(":", 5)[5]
    return resource_name.removeprefix("loadbalancer/")


def put_target_health_alarm(
    hostname: str, dimensions: dict[str, str], alarm_actions: list[str]
) -> None:
    alarm_name = f"{hostname}-ALBTargetHealth"

    cloudwatch.put_metric_alarm(
        AlarmName=alarm_name,
        AlarmDescription=(
            f"Alarm when the ALB target group serving {hostname} reports "
            "one or more unhealthy targets."
        ),
        Namespace="AWS/ApplicationELB",
        MetricName="UnHealthyHostCount",
        Dimensions=[
            {"Name": "TargetGroup", "Value": dimensions["TargetGroup"]},
            {"Name": "LoadBalancer", "Value": dimensions["LoadBalancer"]},
        ],
        Statistic="Average",
        Period=60,
        EvaluationPeriods=1,
        DatapointsToAlarm=1,
        Threshold=1,
        ComparisonOperator="GreaterThanOrEqualToThreshold",
        TreatMissingData="notBreaching",
        ActionsEnabled=bool(alarm_actions),
        AlarmActions=alarm_actions,
        OKActions=alarm_actions,
    )
"""


class AlbTargetGroupAlarmSyncStack(Stack):
    """Create hostname-specific ALB target health alarms and keep them synced."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        listener_arns: list[str],
        hostnames: list[str],
        notification_emails: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        if not listener_arns:
            raise ValueError("listener_arns must contain at least one ALB listener ARN")
        if not hostnames:
            raise ValueError("hostnames must contain at least one hostname")

        notification_emails = notification_emails or []

        alert_topic = sns.Topic(
            self,
            "AlbTargetHealthAlertTopic",
            display_name="ALB Target Health Alerts",
        )

        for email in notification_emails:
            alert_topic.add_subscription(
                sns_subscriptions.EmailSubscription(email_address=email)
            )

        alarm_actions = [alert_topic.topic_arn]
        alarms = [
            self._create_placeholder_alarm(hostname, alert_topic)
            for hostname in hostnames
        ]

        sync_function = lambda_.Function(
            self,
            "AlbTargetHealthAlarmSyncFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.handler",
            timeout=Duration.minutes(5),
            code=lambda_.Code.from_inline(LAMBDA_CODE),
            environment={
                "HOSTNAMES": json.dumps(hostnames),
                "LISTENER_ARNS": json.dumps(listener_arns),
                "ALARM_ACTIONS": json.dumps(alarm_actions),
            },
        )

        sync_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "elasticloadbalancing:DescribeRules",
                    "elasticloadbalancing:DescribeTargetGroups",
                ],
                resources=["*"],
            )
        )
        sync_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=["cloudwatch:PutMetricAlarm"],
                resources=["*"],
            )
        )

        event_rule = events.Rule(
            self,
            "AlbTargetGroupUpdatedRule",
            description=(
                "Invoke alarm sync when ALB target groups, listeners, or "
                "listener rules are updated."
            ),
            event_pattern=events.EventPattern(
                source=["aws.elasticloadbalancing"],
                detail_type=["AWS API Call via CloudTrail"],
                detail={
                    "eventSource": ["elasticloadbalancing.amazonaws.com"],
                    "eventName": [
                        "CreateListener",
                        "DeleteListener",
                        "ModifyListener",
                        "CreateRule",
                        "DeleteRule",
                        "ModifyRule",
                        "ModifyTargetGroup",
                        "ModifyTargetGroupAttributes",
                        "RegisterTargets",
                        "DeregisterTargets",
                    ],
                },
            ),
        )
        event_rule.add_target(events_targets.LambdaFunction(sync_function))

        sync_provider = cr.Provider(
            self,
            "AlbTargetHealthAlarmSyncProvider",
            on_event_handler=sync_function,
        )

        initial_sync = CustomResource(
            self,
            "InitialAlbTargetHealthAlarmSync",
            service_token=sync_provider.service_token,
            properties={
                "Hostnames": hostnames,
                "ListenerArns": listener_arns,
            },
        )

        for alarm in alarms:
            initial_sync.node.add_dependency(alarm)

        CfnOutput(
            self,
            "AlertTopicArn",
            value=alert_topic.topic_arn,
            description="SNS topic used by ALB target health alarms.",
        )
        CfnOutput(
            self,
            "AlarmSyncFunctionName",
            value=sync_function.function_name,
            description="Lambda function that syncs alarm target group dimensions.",
        )

    def _create_placeholder_alarm(
        self, hostname: str, alert_topic: sns.Topic
    ) -> cloudwatch.Alarm:
        """Create the named alarm; Lambda replaces placeholder dimensions."""
        alarm = cloudwatch.Alarm(
            self,
            f"{_construct_id_for_hostname(hostname)}AlbTargetHealthAlarm",
            alarm_name=f"{hostname}-ALBTargetHealth",
            alarm_description=(
                f"Alarm when the ALB target group serving {hostname} reports "
                "one or more unhealthy targets."
            ),
            metric=cloudwatch.Metric(
                namespace="AWS/ApplicationELB",
                metric_name="UnHealthyHostCount",
                dimensions_map={
                    "TargetGroup": "targetgroup/pending-alarm-sync/pending",
                    "LoadBalancer": "app/pending-alarm-sync/pending",
                },
                period=Duration.minutes(1),
                statistic="Average",
            ),
            threshold=1,
            evaluation_periods=1,
            datapoints_to_alarm=1,
            comparison_operator=(
                cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD
            ),
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        alarm.add_alarm_action(cloudwatch_actions.SnsAction(alert_topic))
        alarm.add_ok_action(cloudwatch_actions.SnsAction(alert_topic))

        return alarm


def _construct_id_for_hostname(hostname: str) -> str:
    construct_id = re.sub(r"[^A-Za-z0-9]", "", hostname.title())
    return construct_id or "Hostname"


def _context_list(app: App, key: str) -> list[str]:
    value = app.node.try_get_context(key)
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            return [str(item) for item in json.loads(stripped)]
        return [item.strip() for item in stripped.split(",") if item.strip()]
    return [str(value)]


app = App()

AlbTargetGroupAlarmSyncStack(
    app,
    "AlbTargetGroupAlarmSyncStack",
    listener_arns=_context_list(app, "listener_arns"),
    hostnames=_context_list(app, "hostnames"),
    notification_emails=_context_list(app, "notification_emails"),
)

app.synth()
