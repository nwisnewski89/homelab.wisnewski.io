#!/usr/bin/env python3
"""
AWS WAF v2 Web ACL with Bot Control and SEO/indexing bot blocking.

This stack adds:
1. AWS Managed Bot Control rule group (blocks unverified bots by default)
2. Custom rules that block verified search-engine bots (e.g. Googlebot)
3. Optional S3 logging via WafLoggingIntegration from waf-v2-logging-integration.py

Rule evaluation order (lower priority number runs first):
  10  Bot Control managed rule group (blocks unverified bots by default)
  20  Block verified search-engine bots on matching hostnames only
      (Googlebot + search_engine + seo labels, combined with Host header match)

Usage:
    cdk deploy -c no_index_hostnames=admin.example.com,internal.example.com WafBotControlStack

    # Attach to an existing ALB
    cdk deploy -c alb_arn=arn:aws:elasticloadbalancing:... WafBotControlStack
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence

from aws_cdk import (
    CfnOutput,
    Stack,
    aws_wafv2 as wafv2,
)
from constructs import Construct

# Reuse the logging helper from waf-v2-logging-integration.py (hyphenated filename).
_logging_spec = importlib.util.spec_from_file_location(
    "waf_v2_logging_integration",
    Path(__file__).parent / "waf-v2-logging-integration.py",
)
_logging_module = importlib.util.module_from_spec(_logging_spec)
_logging_spec.loader.exec_module(_logging_module)
WafLoggingIntegration = _logging_module.WafLoggingIntegration


BotControlInspectionLevel = Literal["COMMON", "TARGETED"]
WafScope = Literal["REGIONAL", "CLOUDFRONT"]

# Labels applied by AWS Bot Control. See:
# https://docs.aws.amazon.com/waf/latest/developerguide/aws-managed-rule-groups-bot.html
LABEL_GOOGLEBOT = "awswaf:managed:aws:bot-control:bot:name:googlebot"
LABEL_CATEGORY_SEARCH_ENGINE = "awswaf:managed:aws:bot-control:bot:category:search_engine"
LABEL_CATEGORY_SEO = "awswaf:managed:aws:bot-control:bot:category:seo"

HostnameMatchType = Literal["EXACTLY", "STARTS_WITH", "ENDS_WITH", "CONTAINS"]


@dataclass(frozen=True)
class WafBotControlConfig:
    """Configuration for the Bot Control Web ACL."""

    name: str = "BotControlWebACL"
    description: str = "Block bots by default; block search-engine bots only on selected hostnames"
    scope: WafScope = "REGIONAL"
    inspection_level: BotControlInspectionLevel = "COMMON"
    enable_machine_learning: bool = False
    bot_control_count_mode: bool = False
    no_index_hostnames: Sequence[str] = ()
    hostname_match_type: HostnameMatchType = "EXACTLY"
    enable_s3_logging: bool = True
    log_prefix: str = "bot-control-waf-logs"
    associate_resource_arn: str | None = None


def _visibility_config(metric_name: str) -> wafv2.CfnWebACL.VisibilityConfigProperty:
    return wafv2.CfnWebACL.VisibilityConfigProperty(
        sampled_requests_enabled=True,
        cloud_watch_metrics_enabled=True,
        metric_name=metric_name,
    )


def create_bot_control_managed_rule(
    *,
    priority: int,
    inspection_level: BotControlInspectionLevel = "COMMON",
    enable_machine_learning: bool = False,
    count_mode: bool = False,
    metric_name: str = "AWSManagedRulesBotControlRuleSet",
) -> wafv2.CfnWebACL.RuleProperty:
    """
    Create the AWS Bot Control managed rule group.

    In default mode, unverified bots (including fake crawlers) are blocked.
    Verified bots such as Googlebot are labeled but allowed through Bot Control;
    use the custom label rules below to block them explicitly.
    """
    override_action = (
        wafv2.CfnWebACL.OverrideActionProperty(count={})
        if count_mode
        else wafv2.CfnWebACL.OverrideActionProperty(none={})
    )

    return wafv2.CfnWebACL.RuleProperty(
        name="AWSManagedRulesBotControlRuleSet",
        priority=priority,
        override_action=override_action,
        statement=wafv2.CfnWebACL.StatementProperty(
            managed_rule_group_statement=wafv2.CfnWebACL.ManagedRuleGroupStatementProperty(
                vendor_name="AWS",
                name="AWSManagedRulesBotControlRuleSet",
                managed_rule_group_configs=[
                    wafv2.CfnWebACL.ManagedRuleGroupConfigProperty(
                        aws_managed_rules_bot_control_rule_set=(
                            wafv2.CfnWebACL.AWSManagedRulesBotControlRuleSetProperty(
                                inspection_level=inspection_level,
                                enable_machine_learning=enable_machine_learning,
                            )
                        )
                    )
                ],
            )
        ),
        visibility_config=_visibility_config(metric_name),
    )


def create_hostname_match_statement(
    hostname: str,
    *,
    match_type: HostnameMatchType = "EXACTLY",
) -> wafv2.CfnWebACL.StatementProperty:
    """Match the HTTP Host header against a hostname."""
    return wafv2.CfnWebACL.StatementProperty(
        byte_match_statement=wafv2.CfnWebACL.ByteMatchStatementProperty(
            search_string=hostname,
            field_to_match=wafv2.CfnWebACL.FieldToMatchProperty(
                single_header=wafv2.CfnWebACL.SingleHeaderProperty(name="host")
            ),
            positional_constraint=match_type,
            text_transformations=[
                wafv2.CfnWebACL.TextTransformationProperty(
                    priority=0,
                    type="LOWERCASE",
                )
            ],
        )
    )


def create_hostnames_match_statement(
    hostnames: Sequence[str],
    *,
    match_type: HostnameMatchType = "EXACTLY",
) -> wafv2.CfnWebACL.StatementProperty:
    """Match if the Host header matches any hostname in the list."""
    if not hostnames:
        raise ValueError("At least one hostname is required")

    if len(hostnames) == 1:
        return create_hostname_match_statement(hostnames[0], match_type=match_type)

    return wafv2.CfnWebACL.StatementProperty(
        or_statement=wafv2.CfnWebACL.OrStatementProperty(
            statements=[
                create_hostname_match_statement(hostname, match_type=match_type)
                for hostname in hostnames
            ]
        )
    )


def create_search_engine_bot_labels_statement() -> wafv2.CfnWebACL.StatementProperty:
    """Match verified Googlebot or bots in the search_engine / seo categories."""
    return wafv2.CfnWebACL.StatementProperty(
        or_statement=wafv2.CfnWebACL.OrStatementProperty(
            statements=[
                wafv2.CfnWebACL.StatementProperty(
                    label_match_statement=wafv2.CfnWebACL.LabelMatchStatementProperty(
                        scope="LABEL",
                        key=LABEL_GOOGLEBOT,
                    )
                ),
                wafv2.CfnWebACL.StatementProperty(
                    label_match_statement=wafv2.CfnWebACL.LabelMatchStatementProperty(
                        scope="LABEL",
                        key=LABEL_CATEGORY_SEARCH_ENGINE,
                    )
                ),
                wafv2.CfnWebACL.StatementProperty(
                    label_match_statement=wafv2.CfnWebACL.LabelMatchStatementProperty(
                        scope="LABEL",
                        key=LABEL_CATEGORY_SEO,
                    )
                ),
            ]
        )
    )


def create_hostname_scoped_search_engine_block_rule(
    *,
    priority: int,
    hostnames: Sequence[str],
    match_type: HostnameMatchType = "EXACTLY",
    count_mode: bool = False,
) -> wafv2.CfnWebACL.RuleProperty:
    """
    Block verified search-engine bots only when the Host header matches.

    Logic: (Googlebot OR search_engine category OR seo category) AND hostname match.
    Unverified bots are still blocked earlier by the Bot Control managed rule group.
    """
    action = (
        wafv2.CfnWebACL.RuleActionProperty(count={})
        if count_mode
        else wafv2.CfnWebACL.RuleActionProperty(block={})
    )

    return wafv2.CfnWebACL.RuleProperty(
        name="BlockSearchEngineBotsOnHostname",
        priority=priority,
        action=action,
        statement=wafv2.CfnWebACL.StatementProperty(
            and_statement=wafv2.CfnWebACL.AndStatementProperty(
                statements=[
                    create_hostnames_match_statement(hostnames, match_type=match_type),
                    create_search_engine_bot_labels_statement(),
                ]
            )
        ),
        visibility_config=_visibility_config("BlockSearchEngineBotsOnHostname"),
    )


def build_bot_control_web_acl_rules(
    config: WafBotControlConfig,
    *,
    start_priority: int = 10,
) -> list[wafv2.CfnWebACL.RuleProperty]:
    """Build Bot Control and hostname-scoped search-engine bot block rules."""
    rules: list[wafv2.CfnWebACL.RuleProperty] = []
    priority = start_priority

    rules.append(
        create_bot_control_managed_rule(
            priority=priority,
            inspection_level=config.inspection_level,
            enable_machine_learning=config.enable_machine_learning,
            count_mode=config.bot_control_count_mode,
        )
    )
    priority += 1

    if config.no_index_hostnames:
        rules.append(
            create_hostname_scoped_search_engine_block_rule(
                priority=priority,
                hostnames=config.no_index_hostnames,
                match_type=config.hostname_match_type,
                count_mode=config.bot_control_count_mode,
            )
        )

    return rules


class WafBotControlStack(Stack):
    """
    CDK stack that provisions a WAF v2 Web ACL with Bot Control and indexing-bot blocks.

    Bot Control blocks unverified bots globally. Verified search-engine bots are only
    blocked on hostnames listed in config.no_index_hostnames.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        config: WafBotControlConfig | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.config = config or WafBotControlConfig()
        rules = build_bot_control_web_acl_rules(self.config)

        self.web_acl = wafv2.CfnWebACL(
            self,
            "BotControlWebACL",
            scope=self.config.scope,
            name=self.config.name,
            description=self.config.description,
            default_action=wafv2.CfnWebACL.DefaultActionProperty(allow={}),
            rules=rules,
            visibility_config=_visibility_config(self.config.name),
        )

        if self.config.enable_s3_logging:
            waf_logging = WafLoggingIntegration(self, "WafLogging")
            self.logging_config = waf_logging.add_logging_to_waf(
                self.web_acl,
                log_prefix=self.config.log_prefix,
            )

        if self.config.associate_resource_arn:
            self.waf_association = wafv2.CfnWebACLAssociation(
                self,
                "WafAssociation",
                resource_arn=self.config.associate_resource_arn,
                web_acl_arn=self.web_acl.attr_arn,
            )

        CfnOutput(
            self,
            "WebAclArn",
            value=self.web_acl.attr_arn,
            description="ARN of the Bot Control Web ACL",
            export_name=f"{construct_id}-WebAclArn",
        )

        CfnOutput(
            self,
            "WebAclId",
            value=self.web_acl.attr_id,
            description="ID of the Bot Control Web ACL",
        )


# ---------------------------------------------------------------------------
# Example CDK app entry point
# ---------------------------------------------------------------------------
def _hostnames_from_context(app) -> list[str]:
    raw = app.node.try_get_context("no_index_hostnames") or ""
    if isinstance(raw, list):
        return [hostname.strip() for hostname in raw if str(hostname).strip()]
    return [hostname.strip() for hostname in str(raw).split(",") if hostname.strip()]


if __name__ == "__main__":
    from aws_cdk import App

    app = App()

    alb_arn = app.node.try_get_context("alb_arn")

    WafBotControlStack(
        app,
        "WafBotControlStack",
        config=WafBotControlConfig(
            name=app.node.try_get_context("waf_name") or "BotControlWebACL",
            scope=app.node.try_get_context("waf_scope") or "REGIONAL",
            bot_control_count_mode=app.node.try_get_context("count_mode") == "true",
            no_index_hostnames=_hostnames_from_context(app),
            hostname_match_type=app.node.try_get_context("hostname_match_type") or "EXACTLY",
            associate_resource_arn=alb_arn,
        ),
    )

    app.synth()
