#!/usr/bin/env python3
"""
AWS CDK example for EBS volume backup using AWS Backup service.
This demonstrates how to set up automated backup for EBS volumes based on tags
with lifecycle management: 7 days hot storage, 30 days cold storage, then deletion.
"""

from aws_cdk import (
    Stack,
    Duration,
    aws_backup as backup,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_events as events,
    aws_events_targets as targets,
    CfnOutput,
)
from constructs import Construct


class EbsBackupStack(Stack):
    """Stack demonstrating EBS volume backup with AWS Backup service."""
    
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # Create VPC for demonstration
        vpc = ec2.Vpc(self, "BackupVpc", max_azs=2)
        
        # Create security group
        sg = ec2.SecurityGroup(
            self, "BackupSg",
            vpc=vpc,
            description="Security group for backup example instance"
        )
        sg.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(22),
            description="SSH access"
        )
        
        # Create IAM role for EC2 instance
        ec2_role = iam.Role(
            self, "Ec2Role",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore")
            ]
        )
        
        # Create EC2 instance with EBS volumes
        instance = ec2.Instance(
            self, "BackupInstance",
            instance_type=ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.MICRO),
            machine_image=ec2.MachineImage.latest_amazon_linux2(),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_group=sg,
            role=ec2_role,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(
                        volume_size=8,
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                        delete_on_termination=True,
                        encrypted=True,
                    )
                )
            ]
        )
        
        # Create EBS volumes with backup tags
        data_volume = ec2.Volume(
            self, "DataVolume",
            availability_zone=instance.instance_availability_zone,
            size=ec2.Size.gibibytes(20),
            volume_type=ec2.EbsDeviceVolumeType.GP3,
            encrypted=True,
        )
        
        # Tag the volume for backup selection
        data_volume.node.add_metadata("Tags", {
            "Backup": "true",
            "Environment": "production",
            "Application": "data-storage"
        })
        
        # Grant permissions to attach the volume
        data_volume.grant_attach_volume(ec2_role, [instance])
        
        # Create AWS Backup Vault
        backup_vault = backup.BackupVault(
            self, "BackupVault",
            backup_vault_name="ebs-backup-vault",
            removal_policy=self.removal_policy,
        )
        
        # Create IAM role for AWS Backup service
        backup_role = iam.Role(
            self, "BackupRole",
            assumed_by=iam.ServicePrincipal("backup.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AWSBackupServiceRolePolicyForBackup"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AWSBackupServiceRolePolicyForRestores"),
            ]
        )
        
        # Add additional permissions for EBS backup
        backup_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ec2:CreateSnapshot",
                    "ec2:DeleteSnapshot",
                    "ec2:DescribeSnapshots",
                    "ec2:DescribeVolumes",
                    "ec2:CreateTags",
                    "ec2:DeleteTags",
                ],
                resources=["*"]
            )
        )
        
        # Create backup plan with lifecycle rules
        backup_plan = backup.BackupPlan(
            self, "BackupPlan",
            backup_plan_name="ebs-backup-plan",
            backup_plan_rules=[
                backup.BackupPlanRule(
                    rule_name="ebs-backup-rule",
                    schedule_expression=events.Schedule.cron(
                        minute="0",
                        hour="2",  # 2 AM daily
                        day="*",
                        month="*",
                        year="*"
                    ),
                    start_backup_window=Duration.hours(1),
                    complete_backup_window=Duration.hours(2),
                    enable_continuous_backup=False,
                    delete_after=Duration.days(37),  # 7 days hot + 30 days cold
                    move_to_cold_storage_after=Duration.days(7),
                    recovery_point_tags={
                        "Environment": "production",
                        "BackupType": "automated"
                    }
                )
            ]
        )
        
        # Create resource selection for EBS volumes with specific tags
        backup_selection = backup.BackupSelection(
            self, "BackupSelection",
            backup_plan=backup_plan,
            backup_selection_name="ebs-volume-selection",
            role=backup_role,
            resources=[
                backup.BackupResource.from_tag("Backup", "true"),
                backup.BackupResource.from_tag("Environment", "production")
            ],
            resource_type=backup.BackupResourceType.EBS,
        )
        
        # Alternative: More specific resource selection using ARN patterns
        # This would select specific EBS volumes by their ARN pattern
        backup_selection_arn = backup.BackupSelection(
            self, "BackupSelectionArn",
            backup_plan=backup_plan,
            backup_selection_name="ebs-volume-selection-arn",
            role=backup_role,
            resources=[
                backup.BackupResource.from_arn(
                    f"arn:aws:ec2:{self.region}:{self.account}:volume/*"
                )
            ],
            resource_type=backup.BackupResourceType.EBS,
            conditions={
                "StringEquals": {
                    "aws:ResourceTag/Backup": "true"
                }
            }
        )
        
        # Create backup vault notifications (optional)
        backup_vault.add_notification(
            backup.BackupVaultNotification(
                backup_vault_events=[
                    backup.BackupVaultEvents.BACKUP_JOB_STARTED,
                    backup.BackupVaultEvents.BACKUP_JOB_COMPLETED,
                    backup.BackupVaultEvents.BACKUP_JOB_FAILED,
                    backup.BackupVaultEvents.RECOVERY_POINT_EXPIRED,
                ]
            )
        )
        
        # Outputs
        CfnOutput(
            self, "BackupVaultArn",
            value=backup_vault.backup_vault_arn,
            description="ARN of the backup vault"
        )
        
        CfnOutput(
            self, "BackupPlanId",
            value=backup_plan.backup_plan_id,
            description="ID of the backup plan"
        )
        
        CfnOutput(
            self, "InstanceId",
            value=instance.instance_id,
            description="EC2 instance ID"
        )
        
        CfnOutput(
            self, "DataVolumeId",
            value=data_volume.volume_id,
            description="EBS volume ID for backup"
        )


class EbsBackupAdvancedStack(Stack):
    """Advanced stack with multiple backup plans and cross-region backup."""
    
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # Create backup vault
        backup_vault = backup.BackupVault(
            self, "AdvancedBackupVault",
            backup_vault_name="advanced-ebs-backup-vault",
            removal_policy=self.removal_policy,
        )
        
        # Create IAM role for backup
        backup_role = iam.Role(
            self, "AdvancedBackupRole",
            assumed_by=iam.ServicePrincipal("backup.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AWSBackupServiceRolePolicyForBackup"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AWSBackupServiceRolePolicyForRestores"),
            ]
        )
        
        # Add cross-region backup permissions
        backup_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "backup:CopyIntoBackupVault",
                    "backup:StartCopyJob",
                    "backup:DescribeCopyJob",
                ],
                resources=["*"]
            )
        )
        
        # Create multiple backup plans for different environments
        production_plan = backup.BackupPlan(
            self, "ProductionBackupPlan",
            backup_plan_name="production-ebs-backup",
            backup_plan_rules=[
                backup.BackupPlanRule(
                    rule_name="daily-backup",
                    schedule_expression=events.Schedule.cron(
                        minute="0",
                        hour="2",
                        day="*",
                        month="*",
                        year="*"
                    ),
                    start_backup_window=Duration.hours(1),
                    complete_backup_window=Duration.hours(2),
                    delete_after=Duration.days(37),
                    move_to_cold_storage_after=Duration.days(7),
                ),
                backup.BackupPlanRule(
                    rule_name="weekly-backup",
                    schedule_expression=events.Schedule.cron(
                        minute="0",
                        hour="3",
                        day="0",  # Sunday
                        month="*",
                        year="*"
                    ),
                    start_backup_window=Duration.hours(1),
                    complete_backup_window=Duration.hours(4),
                    delete_after=Duration.days(90),
                    move_to_cold_storage_after=Duration.days(30),
                )
            ]
        )
        
        # Create backup selection for production volumes
        backup.BackupSelection(
            self, "ProductionBackupSelection",
            backup_plan=production_plan,
            backup_selection_name="production-ebs-selection",
            role=backup_role,
            resources=[
                backup.BackupResource.from_tag("Environment", "production"),
                backup.BackupResource.from_tag("Backup", "true")
            ],
            resource_type=backup.BackupResourceType.EBS,
        )
        
        # Create development backup plan with shorter retention
        development_plan = backup.BackupPlan(
            self, "DevelopmentBackupPlan",
            backup_plan_name="development-ebs-backup",
            backup_plan_rules=[
                backup.BackupPlanRule(
                    rule_name="dev-daily-backup",
                    schedule_expression=events.Schedule.cron(
                        minute="0",
                        hour="4",
                        day="*",
                        month="*",
                        year="*"
                    ),
                    start_backup_window=Duration.hours(1),
                    complete_backup_window=Duration.hours(2),
                    delete_after=Duration.days(14),  # Shorter retention for dev
                    move_to_cold_storage_after=Duration.days(3),
                )
            ]
        )
        
        # Create backup selection for development volumes
        backup.BackupSelection(
            self, "DevelopmentBackupSelection",
            backup_plan=development_plan,
            backup_selection_name="development-ebs-selection",
            role=backup_role,
            resources=[
                backup.BackupResource.from_tag("Environment", "development"),
                backup.BackupResource.from_tag("Backup", "true")
            ],
            resource_type=backup.BackupResourceType.EBS,
        )


if __name__ == "__main__":
    print("""
    AWS CDK EBS Backup Service Example
    
    This example demonstrates how to set up AWS Backup service for EBS volumes with:
    
    1. Tag-based resource selection
    2. Lifecycle management (7 days hot, 30 days cold, then delete)
    3. Automated backup scheduling
    4. Proper IAM roles and permissions
    
    Key Features:
    - Backup vault for storing recovery points
    - Backup plan with lifecycle rules
    - Resource selection based on tags
    - Cross-region backup support (advanced)
    - Multiple backup plans for different environments
    
    Usage:
    1. Tag your EBS volumes with "Backup": "true"
    2. Deploy the stack
    3. Volumes will be automatically backed up according to the schedule
    
    Example tagging:
    aws ec2 create-tags --resources vol-1234567890abcdef0 --tags Key=Backup,Value=true Key=Environment,Value=production
    """)
