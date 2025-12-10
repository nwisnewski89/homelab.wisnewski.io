#!/usr/bin/env python3
"""
AWS CDK Stack for Ubuntu EC2 instance with CloudWatch monitoring
- EC2 instance with Ubuntu
- IAM policies: AmazonSSMManagedInstanceCore and CloudWatchAgentServerPolicy
- CloudWatch agent configured to monitor CPU, memory, and disk
- Config stored in SSM Parameter Store
- Userdata script fetches config and starts CloudWatch agent
- CloudWatch alarms for 90% thresholds on CPU, memory, and disk
"""

import json
from aws_cdk import (
    Stack,
    CfnOutput,
    Duration,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_ssm as ssm,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_sns as sns,
    aws_sns_subscriptions as sns_subscriptions,
    aws_elasticloadbalancingv2 as elbv2,
)
from constructs import Construct


class CloudWatchMonitoredEc2Stack(Stack):
    """
    Stack that creates an Ubuntu EC2 instance with CloudWatch monitoring
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Configuration
        instance_name = self.node.try_get_context("instance_name") or "monitored-ubuntu-instance"
        instance_type = self.node.try_get_context("instance_type") or "t3.micro"
        alarm_email = self.node.try_get_context("alarm_email")  # Optional email for alarms
        target_group_arn = self.node.try_get_context("target_group_arn")  # Optional target group ARN to monitor

        # Lookup existing VPC or create new one
        vpc = ec2.Vpc.from_lookup(self, "VPC", is_default=True)

        # Security Group for instance
        instance_sg = ec2.SecurityGroup(
            self,
            "InstanceSecurityGroup",
            vpc=vpc,
            description=f"Security group for {instance_name}",
            allow_all_outbound=True,
        )

        # Create IAM role for EC2 instance
        instance_role = iam.Role(
            self,
            "InstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            description=f"Role for {instance_name} with SSM and CloudWatch permissions",
        )

        # Add required managed policies
        instance_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "AmazonSSMManagedInstanceCore"
            )
        )
        instance_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "CloudWatchAgentServerPolicy"
            )
        )

        # Additional permissions for SSM Parameter Store access
        instance_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "ssm:GetParameter",
                    "ssm:GetParameters",
                ],
                resources=[
                    f"arn:aws:ssm:{self.region}:{self.account}:parameter/cloudwatch-agent-config/*",
                ],
            )
        )

        # Create CloudWatch agent configuration JSON
        cloudwatch_config = self._create_cloudwatch_config()

        # Store CloudWatch agent config in SSM Parameter Store
        ssm_parameter = ssm.StringParameter(
            self,
            "CloudWatchAgentConfig",
            parameter_name="/cloudwatch-agent-config/ec2-monitoring",
            string_value=json.dumps(cloudwatch_config, indent=2),
            description="CloudWatch agent configuration for EC2 monitoring",
        )

        # Create user data script
        user_data = self._create_user_data(ssm_parameter.parameter_name)

        # Create EC2 instance with Ubuntu
        instance = ec2.Instance(
            self,
            "UbuntuInstance",
            vpc=vpc,
            instance_type=ec2.InstanceType(instance_type),
            machine_image=ec2.MachineImage.latest_ubuntu(
                version=ec2.UbuntuVersion.VERSION_22_04_LTS
            ),
            security_group=instance_sg,
            role=instance_role,
            user_data=user_data,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PUBLIC,
            ),
        )

        # Create SNS topic for alarms (optional, if email provided)
        alarm_topic = None
        if alarm_email:
            alarm_topic = sns.Topic(
                self,
                "AlarmTopic",
                display_name="EC2 Monitoring Alarms",
            )
            alarm_topic.add_subscription(
                sns_subscriptions.EmailSubscription(alarm_email)
            )

        # Create CloudWatch alarms for 90% thresholds
        self._create_cloudwatch_alarms(
            instance, alarm_topic, instance_name
        )

        # Create CloudWatch alarm for unhealthy target groups (if target group ARN provided)
        if target_group_arn:
            self._create_target_group_health_alarm(
                target_group_arn, alarm_topic
            )

        # Outputs
        CfnOutput(
            self,
            "InstanceId",
            value=instance.instance_id,
            description="EC2 Instance ID",
        )

        CfnOutput(
            self,
            "InstancePublicIP",
            value=instance.instance_public_ip,
            description="EC2 Instance Public IP",
        )

        CfnOutput(
            self,
            "SSMParameterName",
            value=ssm_parameter.parameter_name,
            description="SSM Parameter name for CloudWatch agent config",
        )

        if alarm_topic:
            CfnOutput(
                self,
                "AlarmTopicArn",
                value=alarm_topic.topic_arn,
                description="SNS Topic ARN for alarm notifications",
            )

    def _create_cloudwatch_config(self) -> dict:
        """
        Create CloudWatch agent configuration JSON
        Monitors CPU, memory, and disk usage
        """
        return {
            "agent": {
                "metrics_collection_interval": 60,
                "run_as_user": "root"
            },
            "metrics": {
                "namespace": "CWAgent",
                "metrics_collected": {
                    "cpu": {
                        "measurement": [
                            {
                                "name": "cpu_usage_idle",
                                "rename": "CPU_USAGE_IDLE",
                                "unit": "Percent"
                            },
                            {
                                "name": "cpu_usage_iowait",
                                "rename": "CPU_USAGE_IOWAIT",
                                "unit": "Percent"
                            },
                            {
                                "name": "cpu_usage_user",
                                "rename": "CPU_USAGE_USER",
                                "unit": "Percent"
                            },
                            {
                                "name": "cpu_usage_system",
                                "rename": "CPU_USAGE_SYSTEM",
                                "unit": "Percent"
                            }
                        ],
                        "totalcpu": False,
                        "metrics_collection_interval": 60
                    },
                    "disk": {
                        "measurement": [
                            {
                                "name": "used_percent",
                                "rename": "DISK_USED_PERCENT",
                                "unit": "Percent"
                            }
                        ],
                        "metrics_collection_interval": 60,
                        "resources": [
                            "*"
                        ]
                    },
                    "mem": {
                        "measurement": [
                            {
                                "name": "mem_used_percent",
                                "rename": "MEM_USED_PERCENT",
                                "unit": "Percent"
                            }
                        ],
                        "metrics_collection_interval": 60
                    }
                }
            }
        }

    def _create_user_data(self, ssm_parameter_name: str) -> ec2.UserData:
        """
        Create user data script that:
        1. Installs CloudWatch agent
        2. Fetches config from SSM Parameter Store
        3. Starts CloudWatch agent
        """
        user_data = ec2.UserData.for_linux()
        user_data.add_commands("#!/bin/bash")
        user_data.add_commands("set -e")
        user_data.add_commands("")
        user_data.add_commands("# Get AWS region from instance metadata")
        user_data.add_commands("export AWS_REGION=$(curl -s http://169.254.169.254/latest/meta-data/placement/region)")
        user_data.add_commands("")
        user_data.add_commands("# Update system")
        user_data.add_commands("apt-get update -y")
        user_data.add_commands("")
        user_data.add_commands("# Install CloudWatch agent")
        user_data.add_commands("wget https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb")
        user_data.add_commands("dpkg -i -E ./amazon-cloudwatch-agent.deb")
        user_data.add_commands("")
        user_data.add_commands("# Create directory for CloudWatch agent config if it doesn't exist")
        user_data.add_commands("mkdir -p /opt/aws/amazon-cloudwatch-agent/etc")
        user_data.add_commands("")
        user_data.add_commands("# Fetch CloudWatch agent config from SSM Parameter Store")
        user_data.add_commands(f"aws ssm get-parameter --name {ssm_parameter_name} --region $AWS_REGION --with-decryption --query 'Parameter.Value' --output text > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json")
        user_data.add_commands("")
        user_data.add_commands("# Start CloudWatch agent")
        user_data.add_commands("/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json -s")
        user_data.add_commands("")
        user_data.add_commands("# Verify agent is running")
        user_data.add_commands("/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -m ec2 -a status")
        user_data.add_commands("")
        user_data.add_commands("echo 'CloudWatch agent installation and configuration complete'")

        return user_data

    def _create_cloudwatch_alarms(
        self,
        instance: ec2.Instance,
        alarm_topic: sns.Topic | None,
        instance_name: str,
    ) -> None:
        """
        Create CloudWatch alarms for CPU, memory, and disk at 90% thresholds
        """
        # CPU Usage Alarm (using CPUUtilization metric)
        cpu_alarm = cloudwatch.Alarm(
            self,
            "CpuUsageAlarm",
            alarm_name=f"{instance_name}-cpu-usage-high",
            metric=cloudwatch.Metric(
                namespace="AWS/EC2",
                metric_name="CPUUtilization",
                dimensions_map={
                    "InstanceId": instance.instance_id,
                },
                statistic="Average",
                period=Duration.minutes(5),
            ),
            threshold=90.0,
            evaluation_periods=2,
            datapoints_to_alarm=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
            alarm_description="Alarm when CPU usage exceeds 90%",
        )

        # Memory Usage Alarm (using CWAgent namespace)
        # Note: CloudWatch agent publishes as MEM_USED_PERCENT based on our config rename
        memory_alarm = cloudwatch.Alarm(
            self,
            "MemoryUsageAlarm",
            alarm_name=f"{instance_name}-memory-usage-high",
            metric=cloudwatch.Metric(
                namespace="CWAgent",
                metric_name="MEM_USED_PERCENT",
                dimensions_map={
                    "InstanceId": instance.instance_id,
                },
                statistic="Average",
                period=Duration.minutes(5),
            ),
            threshold=90.0,
            evaluation_periods=2,
            datapoints_to_alarm=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
            alarm_description="Alarm when memory usage exceeds 90%",
        )

        # Disk Usage Alarm (using CWAgent namespace)
        # Note: CloudWatch agent publishes as DISK_USED_PERCENT based on our config rename
        # We'll monitor the root filesystem (/)
        # Note: Adjust 'fstype' dimension if your filesystem is not ext4 (e.g., xfs, btrfs)
        # You can check the actual dimensions in CloudWatch Metrics console after deployment
        disk_alarm = cloudwatch.Alarm(
            self,
            "DiskUsageAlarm",
            alarm_name=f"{instance_name}-disk-usage-high",
            metric=cloudwatch.Metric(
                namespace="CWAgent",
                metric_name="DISK_USED_PERCENT",
                dimensions_map={
                    "InstanceId": instance.instance_id,
                    "device": "/",
                    "fstype": "ext4",  # Common for Ubuntu, adjust if needed (xfs, btrfs, etc.)
                },
                statistic="Average",
                period=Duration.minutes(5),
            ),
            threshold=90.0,
            evaluation_periods=2,
            datapoints_to_alarm=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
            alarm_description="Alarm when disk usage exceeds 90%",
        )

        # Add SNS actions if topic is provided
        if alarm_topic:
            cpu_alarm.add_alarm_action(cw_actions.SnsAction(alarm_topic))
            memory_alarm.add_alarm_action(cw_actions.SnsAction(alarm_topic))
            disk_alarm.add_alarm_action(cw_actions.SnsAction(alarm_topic))

    def _create_target_group_health_alarm(
        self,
        target_group_arn: str,
        alarm_topic: sns.Topic | None,
    ) -> None:
        """
        Create CloudWatch alarm for unhealthy target groups.
        
        Args:
            target_group_arn: ARN of the target group to monitor
            alarm_topic: Optional SNS topic for alarm notifications
        """
        # Parse target group ARN to extract dimensions
        # Format: arn:aws:elasticloadbalancing:region:account:targetgroup/name/id
        arn_parts = target_group_arn.split(':')
        if len(arn_parts) < 6:
            raise ValueError(f"Invalid target group ARN format: {target_group_arn}")
        
        # The last part contains targetgroup/name/id
        target_group_full_name = arn_parts[-1]
        # Extract just the name part (the part between targetgroup/ and /id)
        # Split by '/' and get the name (index 1)
        name_parts = target_group_full_name.split('/')
        if len(name_parts) < 3 or name_parts[0] != 'targetgroup':
            raise ValueError(f"Invalid target group ARN format: {target_group_arn}")
        
        target_group_name = name_parts[1]  # The name is the second part
        
        # Note: For Application Load Balancer metrics, the LoadBalancer dimension
        # is optional. The metric will aggregate across all load balancers if not specified.
        # If you need to monitor a specific load balancer, you can add the LoadBalancer
        # dimension by looking up the target group or providing it separately.
        
        # Create CloudWatch alarm for unhealthy host count
        unhealthy_alarm = cloudwatch.Alarm(
            self,
            "UnhealthyTargetGroupAlarm",
            alarm_name="alb-unhealthy-targets",
            metric=cloudwatch.Metric(
                namespace="AWS/ApplicationELB",
                metric_name="UnHealthyHostCount",
                dimensions_map={
                    "TargetGroup": target_group_name,
                },
                period=Duration.minutes(1),
                statistic="Average",
            ),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            alarm_description="Alarm when ALB target group has unhealthy targets",
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )

        # Add SNS action if topic is provided
        if alarm_topic:
            unhealthy_alarm.add_alarm_action(cw_actions.SnsAction(alarm_topic))

        # Output alarm information
        CfnOutput(
            self,
            "UnhealthyTargetGroupAlarmArn",
            value=unhealthy_alarm.alarm_arn,
            description="ARN of the CloudWatch alarm for unhealthy target groups",
        )

