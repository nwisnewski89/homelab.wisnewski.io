#!/usr/bin/env python3
"""
AWS WAF v2 Web ACL with Bot Control and SEO/indexing bot blocking.

This stack adds:
1. AWS Managed Bot Control rule group (blocks unverified bots by default)
2. Custom rules that block verified search-engine bots (e.g. Googlebot)
3. Optional S3 logging via WafLoggingIntegration from waf-v2-logging-integration.py

Rule evaluation order (lower priority number runs first):
  10  Bot Control managed rule group (labels bots; blocks unverified crawlers)
  20  Block verified Googlebot (custom label match)
  21  Block verified search-engine / SEO bots (optional, broader block)

Usage:
    cdk deploy -c domain=wisnewski.io WafBotControlStack

    # Attach to an existing ALB
    cdk deploy -c alb_arn=arn:aws:elasticloadbalancing:... WafBotControlStack
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

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


@dataclass(frozen=True)
class WafBotControlConfig:
    """Configuration for the Bot Control Web ACL."""

    name: str = "BotControlWebACL"
    description: str = "Block SEO/indexing bots via Bot Control and custom label rules"
    scope: WafScope = "REGIONAL"
    inspection_level: BotControlInspectionLevel = "COMMON"
    enable_machine_learning: bool = False
    bot_control_count_mode: bool = False
    block_googlebot: bool = True
    block_all_search_engine_bots: bool = False
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


def create_label_block_rule(
    *,
    name: str,
    priority: int,
    label_key: str,
    count_mode: bool = False,
) -> wafv2.CfnWebACL.RuleProperty:
    """Block (or count) requests that match a Bot Control label."""
    action = (
        wafv2.CfnWebACL.RuleActionProperty(count={})
        if count_mode
        else wafv2.CfnWebACL.RuleActionProperty(block={})
    )

    return wafv2.CfnWebACL.RuleProperty(
        name=name,
        priority=priority,
        action=action,
        statement=wafv2.CfnWebACL.StatementProperty(
            label_match_statement=wafv2.CfnWebACL.LabelMatchStatementProperty(
                scope="LABEL",
                key=label_key,
            )
        ),
        visibility_config=_visibility_config(name),
    )


def create_block_search_engine_bots_rule(
    *,
    priority: int,
    count_mode: bool = False,
) -> wafv2.CfnWebACL.RuleProperty:
    """Block verified bots in the search_engine and seo Bot Control categories."""
    action = (
        wafv2.CfnWebACL.RuleActionProperty(count={})
        if count_mode
        else wafv2.CfnWebACL.RuleActionProperty(block={})
    )

    return wafv2.CfnWebACL.RuleProperty(
        name="BlockVerifiedSearchEngineAndSeoBots",
        priority=priority,
        action=action,
        statement=wafv2.CfnWebACL.StatementProperty(
            or_statement=wafv2.CfnWebACL.OrStatementProperty(
                statements=[
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
        ),
        visibility_config=_visibility_config("BlockVerifiedSearchEngineAndSeoBots"),
    )


def build_bot_control_web_acl_rules(
    config: WafBotControlConfig,
    *,
    start_priority: int = 10,
) -> list[wafv2.CfnWebACL.RuleProperty]:
    """Build Bot Control and custom indexing-bot block rules."""
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

    if config.block_googlebot:
        rules.append(
            create_label_block_rule(
                name="BlockGooglebot",
                priority=priority,
                label_key=LABEL_GOOGLEBOT,
                count_mode=config.bot_control_count_mode,
            )
        )
        priority += 1

    if config.block_all_search_engine_bots:
        rules.append(
            create_block_search_engine_bots_rule(
                priority=priority,
                count_mode=config.bot_control_count_mode,
            )
        )

    return rules


class WafBotControlStack(Stack):
    """
    CDK stack that provisions a WAF v2 Web ACL with Bot Control and indexing-bot blocks.

    Bot Control must run before the custom label rules so labels are present when the
    block rules are evaluated.
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
            block_all_search_engine_bots=app.node.try_get_context("block_all_search_bots") == "true",
            associate_resource_arn=alb_arn,
        ),
    )

    app.synth()
