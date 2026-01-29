#!/usr/bin/env python3
"""
Aurora Cross-Account Environment Refresh Script

Propagates data from production Aurora cluster to dev/staging environments
across AWS accounts, resets credentials from Secrets Manager, and updates DNS.
"""

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import boto3
from botocore.exceptions import ClientError, WaiterError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f'aurora_refresh_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class EnvironmentConfig:
    """Configuration for a target environment."""
    name: str
    account_id: str
    cluster_identifier: str
    instance_class: str
    db_subnet_group: str
    security_group_ids: list[str]
    secrets_admin: str  # Secrets Manager secret name for admin credentials
    secrets_app: str    # Secrets Manager secret name for app credentials
    hosted_zone_id: str
    dns_record_name: str
    aws_profile: Optional[str] = None
    instance_count: int = 1
    
    # KMS encryption settings
    kms_key_id: Optional[str] = None  # KMS key ARN/ID for encryption in target account
    
    # Parameter groups (if not specified, uses defaults)
    db_cluster_parameter_group: Optional[str] = None
    db_parameter_group: Optional[str] = None  # For instances
    
    # Cluster settings
    port: int = 3306
    backup_retention_period: int = 7
    preferred_backup_window: Optional[str] = None  # e.g., "03:00-04:00"
    preferred_maintenance_window: Optional[str] = None  # e.g., "sun:04:00-sun:05:00"
    deletion_protection: bool = False  # Usually False for non-prod
    
    # IAM authentication
    enable_iam_database_authentication: bool = False
    
    # Monitoring
    enable_performance_insights: bool = False
    performance_insights_kms_key_id: Optional[str] = None
    performance_insights_retention_period: int = 7  # days (7 or 731)
    monitoring_interval: int = 0  # 0 to disable, or 1, 5, 10, 15, 30, 60 seconds
    monitoring_role_arn: Optional[str] = None  # Required if monitoring_interval > 0
    
    # CloudWatch Logs
    enable_cloudwatch_logs_exports: Optional[list[str]] = None  # e.g., ["audit", "error", "general", "slowquery"]
    
    # Serverless v2 (if using Aurora Serverless v2)
    serverless_v2_scaling_config: Optional[dict] = None  # {"MinCapacity": 0.5, "MaxCapacity": 16}


@dataclass
class ProductionConfig:
    """Configuration for the production source."""
    account_id: str
    cluster_identifier: str
    aws_profile: Optional[str] = None


class AuroraRefreshManager:
    """Manages Aurora cluster refresh from production to lower environments."""

    def __init__(
        self,
        prod_config: ProductionConfig,
        target_config: EnvironmentConfig,
        region: str = 'us-east-1'
    ):
        self.prod_config = prod_config
        self.target_config = target_config
        self.region = region
        self.snapshot_name = f"prod-refresh-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        
        # Initialize boto3 sessions
        self.prod_session = self._create_session(prod_config.aws_profile)
        self.target_session = self._create_session(target_config.aws_profile)
        
        # Initialize clients
        self.prod_rds = self.prod_session.client('rds', region_name=region)
        self.target_rds = self.target_session.client('rds', region_name=region)
        self.target_secrets = self.target_session.client('secretsmanager', region_name=region)
        self.target_route53 = self.target_session.client('route53')

    def _create_session(self, profile_name: Optional[str]) -> boto3.Session:
        """Create a boto3 session with optional profile."""
        if profile_name:
            return boto3.Session(profile_name=profile_name)
        return boto3.Session()

    def create_snapshot(self) -> str:
        """Create a manual snapshot of the production cluster."""
        logger.info(f"Creating snapshot '{self.snapshot_name}' from cluster '{self.prod_config.cluster_identifier}'")
        
        try:
            response = self.prod_rds.create_db_cluster_snapshot(
                DBClusterSnapshotIdentifier=self.snapshot_name,
                DBClusterIdentifier=self.prod_config.cluster_identifier,
                Tags=[
                    {'Key': 'Purpose', 'Value': 'environment-refresh'},
                    {'Key': 'TargetEnvironment', 'Value': self.target_config.name},
                    {'Key': 'CreatedBy', 'Value': 'aurora-refresh-script'}
                ]
            )
            snapshot_arn = response['DBClusterSnapshot']['DBClusterSnapshotArn']
            logger.info(f"Snapshot creation initiated: {snapshot_arn}")
            
            # Wait for snapshot to be available
            logger.info("Waiting for snapshot to become available...")
            waiter = self.prod_rds.get_waiter('db_cluster_snapshot_available')
            waiter.wait(
                DBClusterSnapshotIdentifier=self.snapshot_name,
                WaiterConfig={'Delay': 30, 'MaxAttempts': 60}  # Up to 30 minutes
            )
            logger.info("Snapshot is now available")
            
            return snapshot_arn
            
        except ClientError as e:
            logger.error(f"Failed to create snapshot: {e}")
            raise

    def share_snapshot(self) -> None:
        """Share the snapshot with the target account."""
        logger.info(f"Sharing snapshot with account {self.target_config.account_id}")
        
        try:
            self.prod_rds.modify_db_cluster_snapshot_attribute(
                DBClusterSnapshotIdentifier=self.snapshot_name,
                AttributeName='restore',
                ValuesToAdd=[self.target_config.account_id]
            )
            logger.info("Snapshot shared successfully")
            
        except ClientError as e:
            logger.error(f"Failed to share snapshot: {e}")
            raise

    def copy_snapshot_to_target(self) -> str:
        """
        Copy the shared snapshot to the target account.
        
        IMPORTANT: If the source snapshot is encrypted, this step re-encrypts it
        with the target account's KMS key. This is required because:
        1. The source KMS key (in prod account) may not be accessible long-term
        2. You want each environment to use its own KMS key for isolation
        
        Prerequisites for encrypted snapshots:
        - The source KMS key policy must allow the target account to use kms:Decrypt
        - The target KMS key must exist and allow rds.amazonaws.com to use it
        """
        source_snapshot_arn = (
            f"arn:aws:rds:{self.region}:{self.prod_config.account_id}:"
            f"cluster-snapshot:{self.snapshot_name}"
        )
        local_snapshot_name = f"{self.snapshot_name}-local"
        
        logger.info(f"Copying snapshot to target account as '{local_snapshot_name}'")
        
        # Build copy parameters
        copy_params = {
            'SourceDBClusterSnapshotIdentifier': source_snapshot_arn,
            'TargetDBClusterSnapshotIdentifier': local_snapshot_name,
            'CopyTags': False,  # Don't copy prod tags
            'Tags': [
                {'Key': 'Purpose', 'Value': 'environment-refresh'},
                {'Key': 'SourceSnapshot', 'Value': self.snapshot_name},
                {'Key': 'Environment', 'Value': self.target_config.name},
                {'Key': 'CreatedBy', 'Value': 'aurora-refresh-script'}
            ]
        }
        
        # Re-encrypt with target account's KMS key if specified
        # This is REQUIRED if the source snapshot is encrypted and you want
        # the target to use a different key (recommended for cross-account)
        if self.target_config.kms_key_id:
            copy_params['KmsKeyId'] = self.target_config.kms_key_id
            logger.info(f"Will re-encrypt snapshot with KMS key: {self.target_config.kms_key_id}")
        
        try:
            response = self.target_rds.copy_db_cluster_snapshot(**copy_params)
            logger.info(f"Snapshot copy initiated: {response['DBClusterSnapshot']['DBClusterSnapshotArn']}")
            
            # Check if snapshot is encrypted
            if response['DBClusterSnapshot'].get('StorageEncrypted'):
                logger.info(f"Snapshot is encrypted with KMS key: {response['DBClusterSnapshot'].get('KmsKeyId')}")
            
            # Wait for copy to complete
            logger.info("Waiting for snapshot copy to complete...")
            waiter = self.target_rds.get_waiter('db_cluster_snapshot_available')
            waiter.wait(
                DBClusterSnapshotIdentifier=local_snapshot_name,
                WaiterConfig={'Delay': 30, 'MaxAttempts': 60}
            )
            logger.info("Snapshot copy completed")
            
            return local_snapshot_name
            
        except ClientError as e:
            logger.error(f"Failed to copy snapshot: {e}")
            if 'KMS' in str(e):
                logger.error(
                    "KMS error - ensure:\n"
                    "  1. Source KMS key policy allows target account to kms:Decrypt\n"
                    "  2. Target KMS key exists and RDS service has permissions\n"
                    "  3. KMS key ARN format is correct (arn:aws:kms:region:account:key/id)"
                )
            raise

    def restore_cluster(self, snapshot_identifier: str) -> str:
        """
        Restore a new cluster from the snapshot with environment-specific settings.
        
        Note: Some settings cannot be specified during restore and must be 
        modified after the cluster is available (e.g., backup retention).
        """
        new_cluster_id = f"{self.target_config.cluster_identifier}-new"
        
        logger.info(f"Restoring cluster '{new_cluster_id}' from snapshot '{snapshot_identifier}'")
        
        try:
            # Get the engine version and encryption info from the snapshot
            snapshot_info = self.target_rds.describe_db_cluster_snapshots(
                DBClusterSnapshotIdentifier=snapshot_identifier
            )['DBClusterSnapshots'][0]
            
            engine_version = snapshot_info['EngineVersion']
            engine = snapshot_info['Engine']
            is_encrypted = snapshot_info.get('StorageEncrypted', False)
            snapshot_kms_key = snapshot_info.get('KmsKeyId')
            
            logger.info(f"Snapshot engine: {engine} {engine_version}")
            logger.info(f"Snapshot encrypted: {is_encrypted}")
            if is_encrypted:
                logger.info(f"Snapshot KMS key: {snapshot_kms_key}")
            
            # Build restore parameters
            restore_params = {
                'DBClusterIdentifier': new_cluster_id,
                'SnapshotIdentifier': snapshot_identifier,
                'Engine': engine,
                'EngineVersion': engine_version,
                'DBSubnetGroupName': self.target_config.db_subnet_group,
                'VpcSecurityGroupIds': self.target_config.security_group_ids,
                'Port': self.target_config.port,
                'DeletionProtection': self.target_config.deletion_protection,
                'CopyTagsToSnapshot': True,
                'EnableIAMDatabaseAuthentication': self.target_config.enable_iam_database_authentication,
                'Tags': [
                    {'Key': 'Environment', 'Value': self.target_config.name},
                    {'Key': 'RefreshedFrom', 'Value': 'production'},
                    {'Key': 'RefreshDate', 'Value': datetime.now().isoformat()},
                    {'Key': 'CreatedBy', 'Value': 'aurora-refresh-script'}
                ]
            }
            
            # KMS key - if snapshot is encrypted, the restored cluster will be too
            # The KMS key from the copied snapshot is used by default, but you can
            # specify a different one here (must be in same account)
            if self.target_config.kms_key_id and is_encrypted:
                restore_params['KmsKeyId'] = self.target_config.kms_key_id
                logger.info(f"Using KMS key for restored cluster: {self.target_config.kms_key_id}")
            
            # Parameter group
            if self.target_config.db_cluster_parameter_group:
                restore_params['DBClusterParameterGroupName'] = self.target_config.db_cluster_parameter_group
                logger.info(f"Using cluster parameter group: {self.target_config.db_cluster_parameter_group}")
            
            # CloudWatch Logs exports
            if self.target_config.enable_cloudwatch_logs_exports:
                restore_params['EnableCloudwatchLogsExports'] = self.target_config.enable_cloudwatch_logs_exports
                logger.info(f"Enabling CloudWatch logs: {self.target_config.enable_cloudwatch_logs_exports}")
            
            # Serverless v2 scaling configuration
            if self.target_config.serverless_v2_scaling_config:
                restore_params['ServerlessV2ScalingConfiguration'] = self.target_config.serverless_v2_scaling_config
                logger.info(f"Using Serverless v2 config: {self.target_config.serverless_v2_scaling_config}")
            
            response = self.target_rds.restore_db_cluster_from_snapshot(**restore_params)
            logger.info(f"Cluster restore initiated: {response['DBCluster']['DBClusterArn']}")
            
            # Wait for cluster to be available
            logger.info("Waiting for cluster to become available...")
            self._wait_for_cluster_available(new_cluster_id)
            logger.info("Cluster is now available")
            
            # Apply post-restore modifications (settings that can't be set during restore)
            self._apply_post_restore_settings(new_cluster_id)
            
            return new_cluster_id
            
        except ClientError as e:
            logger.error(f"Failed to restore cluster: {e}")
            if 'KMS' in str(e):
                logger.error(
                    "KMS error during restore. Ensure:\n"
                    "  1. The KMS key exists in the target account\n"
                    "  2. RDS service principal has kms:CreateGrant permission\n"
                    "  3. The snapshot was encrypted with an accessible key"
                )
            raise

    def _apply_post_restore_settings(self, cluster_id: str) -> None:
        """Apply cluster settings that cannot be specified during restore."""
        modify_params = {'DBClusterIdentifier': cluster_id, 'ApplyImmediately': True}
        needs_modify = False
        
        # Backup retention
        if self.target_config.backup_retention_period:
            modify_params['BackupRetentionPeriod'] = self.target_config.backup_retention_period
            needs_modify = True
        
        # Backup window
        if self.target_config.preferred_backup_window:
            modify_params['PreferredBackupWindow'] = self.target_config.preferred_backup_window
            needs_modify = True
        
        # Maintenance window
        if self.target_config.preferred_maintenance_window:
            modify_params['PreferredMaintenanceWindow'] = self.target_config.preferred_maintenance_window
            needs_modify = True
        
        if needs_modify:
            logger.info("Applying post-restore cluster settings...")
            try:
                self.target_rds.modify_db_cluster(**modify_params)
                logger.info("Post-restore settings applied")
            except ClientError as e:
                logger.warning(f"Could not apply some post-restore settings: {e}")

    def _wait_for_cluster_available(self, cluster_id: str, max_attempts: int = 60) -> None:
        """Wait for a cluster to become available."""
        for attempt in range(max_attempts):
            try:
                response = self.target_rds.describe_db_clusters(
                    DBClusterIdentifier=cluster_id
                )
                status = response['DBClusters'][0]['Status']
                logger.debug(f"Cluster status: {status} (attempt {attempt + 1}/{max_attempts})")
                
                if status == 'available':
                    return
                elif status in ['failed', 'deleted', 'deleting']:
                    raise Exception(f"Cluster entered unexpected state: {status}")
                    
                time.sleep(30)
                
            except ClientError as e:
                if 'DBClusterNotFoundFault' in str(e):
                    time.sleep(30)
                    continue
                raise
        
        raise TimeoutError(f"Cluster {cluster_id} did not become available within timeout")

    def create_instances(self, cluster_id: str) -> list[str]:
        """Create DB instances for the restored cluster with monitoring settings."""
        instance_ids = []
        
        # Get engine info from cluster
        cluster_info = self.target_rds.describe_db_clusters(
            DBClusterIdentifier=cluster_id
        )['DBClusters'][0]
        
        for i in range(1, self.target_config.instance_count + 1):
            instance_id = f"{cluster_id}-instance-{i}"
            logger.info(f"Creating instance '{instance_id}'")
            
            try:
                # Build instance parameters
                instance_params = {
                    'DBInstanceIdentifier': instance_id,
                    'DBClusterIdentifier': cluster_id,
                    'DBInstanceClass': self.target_config.instance_class,
                    'Engine': cluster_info['Engine'],
                    'PubliclyAccessible': False,
                    'Tags': [
                        {'Key': 'Environment', 'Value': self.target_config.name},
                        {'Key': 'CreatedBy', 'Value': 'aurora-refresh-script'}
                    ]
                }
                
                # DB parameter group (instance-level)
                if self.target_config.db_parameter_group:
                    instance_params['DBParameterGroupName'] = self.target_config.db_parameter_group
                    logger.info(f"Using DB parameter group: {self.target_config.db_parameter_group}")
                
                # Performance Insights
                if self.target_config.enable_performance_insights:
                    instance_params['EnablePerformanceInsights'] = True
                    instance_params['PerformanceInsightsRetentionPeriod'] = self.target_config.performance_insights_retention_period
                    if self.target_config.performance_insights_kms_key_id:
                        instance_params['PerformanceInsightsKMSKeyId'] = self.target_config.performance_insights_kms_key_id
                    logger.info(f"Enabling Performance Insights (retention: {self.target_config.performance_insights_retention_period} days)")
                
                # Enhanced Monitoring
                if self.target_config.monitoring_interval > 0:
                    if not self.target_config.monitoring_role_arn:
                        logger.warning("monitoring_interval set but monitoring_role_arn not provided - skipping enhanced monitoring")
                    else:
                        instance_params['MonitoringInterval'] = self.target_config.monitoring_interval
                        instance_params['MonitoringRoleArn'] = self.target_config.monitoring_role_arn
                        logger.info(f"Enabling Enhanced Monitoring (interval: {self.target_config.monitoring_interval}s)")
                
                self.target_rds.create_db_instance(**instance_params)
                instance_ids.append(instance_id)
                logger.info(f"Instance creation initiated: {instance_id}")
                
            except ClientError as e:
                logger.error(f"Failed to create instance {instance_id}: {e}")
                raise
        
        # Wait for all instances to be available
        logger.info("Waiting for instances to become available...")
        waiter = self.target_rds.get_waiter('db_instance_available')
        for instance_id in instance_ids:
            try:
                waiter.wait(
                    DBInstanceIdentifier=instance_id,
                    WaiterConfig={'Delay': 30, 'MaxAttempts': 60}
                )
                logger.info(f"Instance {instance_id} is now available")
            except WaiterError as e:
                logger.error(f"Timeout waiting for instance {instance_id}: {e}")
                raise
        
        return instance_ids

    def get_cluster_endpoint(self, cluster_id: str) -> str:
        """Get the writer endpoint for a cluster."""
        response = self.target_rds.describe_db_clusters(
            DBClusterIdentifier=cluster_id
        )
        return response['DBClusters'][0]['Endpoint']

    def get_secret_value(self, secret_name: str) -> dict:
        """Retrieve a secret from Secrets Manager."""
        try:
            response = self.target_secrets.get_secret_value(SecretId=secret_name)
            return json.loads(response['SecretString'])
        except ClientError as e:
            logger.error(f"Failed to retrieve secret {secret_name}: {e}")
            raise

    def reset_credentials(self, cluster_id: str) -> None:
        """Reset database credentials to environment-specific values from Secrets Manager."""
        logger.info("Resetting database credentials from Secrets Manager")
        
        endpoint = self.get_cluster_endpoint(cluster_id)
        
        # Get admin credentials (needed to connect and modify users)
        admin_creds = self.get_secret_value(self.target_config.secrets_admin)
        app_creds = self.get_secret_value(self.target_config.secrets_app)
        
        # Build SQL statements for credential reset
        sql_statements = []
        
        # Reset credentials for each user defined in the app secrets
        for key, value in app_creds.items():
            if key.endswith('_password'):
                username = key.replace('_password', '')
                sql_statements.append(
                    f"ALTER USER '{username}'@'%' IDENTIFIED BY '{value}';"
                )
                logger.info(f"Will reset password for user: {username}")
        
        sql_statements.append("FLUSH PRIVILEGES;")
        
        # Execute using mysql client or pymysql
        self._execute_sql(
            endpoint=endpoint,
            username=admin_creds.get('username', 'admin'),
            password=admin_creds['password'],
            sql_statements=sql_statements
        )
        
        logger.info("Credentials reset successfully")

    def _execute_sql(
        self,
        endpoint: str,
        username: str,
        password: str,
        sql_statements: list[str],
        port: int = 3306
    ) -> None:
        """Execute SQL statements against the database."""
        try:
            import pymysql
        except ImportError:
            logger.error("pymysql not installed. Install with: pip install pymysql")
            logger.info("Alternatively, run these SQL statements manually:")
            for stmt in sql_statements:
                # Mask passwords in log output
                if 'IDENTIFIED BY' in stmt:
                    masked = stmt.split('IDENTIFIED BY')[0] + "IDENTIFIED BY '****';"
                    logger.info(f"  {masked}")
                else:
                    logger.info(f"  {stmt}")
            return
        
        connection = None
        try:
            connection = pymysql.connect(
                host=endpoint,
                user=username,
                password=password,
                port=port,
                connect_timeout=30
            )
            
            with connection.cursor() as cursor:
                for stmt in sql_statements:
                    cursor.execute(stmt)
                    
            connection.commit()
            
        except pymysql.Error as e:
            logger.error(f"Database error: {e}")
            raise
        finally:
            if connection:
                connection.close()

    def update_dns(self, cluster_id: str) -> None:
        """Update Route 53 DNS record to point to the new cluster endpoint."""
        new_endpoint = self.get_cluster_endpoint(cluster_id)
        
        logger.info(
            f"Updating DNS record '{self.target_config.dns_record_name}' "
            f"to point to '{new_endpoint}'"
        )
        
        try:
            response = self.target_route53.change_resource_record_sets(
                HostedZoneId=self.target_config.hosted_zone_id,
                ChangeBatch={
                    'Comment': f'Aurora refresh - updated by aurora-refresh-script at {datetime.now().isoformat()}',
                    'Changes': [
                        {
                            'Action': 'UPSERT',
                            'ResourceRecordSet': {
                                'Name': self.target_config.dns_record_name,
                                'Type': 'CNAME',
                                'TTL': 60,
                                'ResourceRecords': [
                                    {'Value': new_endpoint}
                                ]
                            }
                        }
                    ]
                }
            )
            
            change_id = response['ChangeInfo']['Id']
            logger.info(f"DNS change submitted: {change_id}")
            
            # Wait for DNS change to propagate
            logger.info("Waiting for DNS change to propagate...")
            waiter = self.target_route53.get_waiter('resource_record_sets_changed')
            waiter.wait(Id=change_id)
            logger.info("DNS update completed")
            
        except ClientError as e:
            logger.error(f"Failed to update DNS: {e}")
            raise

    def cleanup_old_cluster(self, skip_final_snapshot: bool = True) -> None:
        """Delete the old cluster after successful refresh."""
        old_cluster_id = self.target_config.cluster_identifier
        
        logger.info(f"Cleaning up old cluster '{old_cluster_id}'")
        
        try:
            # First, get and delete all instances
            cluster_info = self.target_rds.describe_db_clusters(
                DBClusterIdentifier=old_cluster_id
            )['DBClusters'][0]
            
            instance_ids = [m['DBInstanceIdentifier'] for m in cluster_info['DBClusterMembers']]
            
            # Delete instances
            for instance_id in instance_ids:
                logger.info(f"Deleting instance '{instance_id}'")
                self.target_rds.delete_db_instance(
                    DBInstanceIdentifier=instance_id,
                    SkipFinalSnapshot=True
                )
            
            # Wait for instances to be deleted
            for instance_id in instance_ids:
                logger.info(f"Waiting for instance '{instance_id}' to be deleted...")
                waiter = self.target_rds.get_waiter('db_instance_deleted')
                waiter.wait(
                    DBInstanceIdentifier=instance_id,
                    WaiterConfig={'Delay': 30, 'MaxAttempts': 60}
                )
            
            # Now delete the cluster
            logger.info(f"Deleting cluster '{old_cluster_id}'")
            if skip_final_snapshot:
                self.target_rds.delete_db_cluster(
                    DBClusterIdentifier=old_cluster_id,
                    SkipFinalSnapshot=True
                )
            else:
                self.target_rds.delete_db_cluster(
                    DBClusterIdentifier=old_cluster_id,
                    FinalDBSnapshotIdentifier=f"{old_cluster_id}-final-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                )
            
            logger.info("Old cluster cleanup completed")
            
        except ClientError as e:
            if 'DBClusterNotFoundFault' in str(e):
                logger.info("Old cluster not found - may have already been deleted")
            else:
                logger.error(f"Failed to cleanup old cluster: {e}")
                raise

    def rename_cluster(self, old_id: str, new_id: str) -> None:
        """Rename a cluster (modify its identifier)."""
        logger.info(f"Renaming cluster from '{old_id}' to '{new_id}'")
        
        try:
            self.target_rds.modify_db_cluster(
                DBClusterIdentifier=old_id,
                NewDBClusterIdentifier=new_id,
                ApplyImmediately=True
            )
            
            # Wait for rename to complete
            time.sleep(30)
            self._wait_for_cluster_available(new_id)
            logger.info(f"Cluster renamed to '{new_id}'")
            
        except ClientError as e:
            logger.error(f"Failed to rename cluster: {e}")
            raise

    def run_full_refresh(
        self,
        cleanup_old: bool = True,
        skip_final_snapshot: bool = True
    ) -> dict:
        """
        Execute the complete refresh workflow.
        
        Returns a dict with details of what was created.
        """
        logger.info(f"Starting full refresh for environment: {self.target_config.name}")
        logger.info(f"Source: {self.prod_config.cluster_identifier} (Account: {self.prod_config.account_id})")
        logger.info(f"Target: {self.target_config.cluster_identifier} (Account: {self.target_config.account_id})")
        
        result = {
            'snapshot_name': self.snapshot_name,
            'environment': self.target_config.name,
            'started_at': datetime.now().isoformat()
        }
        
        try:
            # Step 1: Create snapshot in production
            snapshot_arn = self.create_snapshot()
            result['source_snapshot_arn'] = snapshot_arn
            
            # Step 2: Share snapshot with target account
            self.share_snapshot()
            
            # Step 3: Copy snapshot to target account
            local_snapshot = self.copy_snapshot_to_target()
            result['local_snapshot_name'] = local_snapshot
            
            # Step 4: Restore new cluster from snapshot
            new_cluster_id = self.restore_cluster(local_snapshot)
            result['new_cluster_id'] = new_cluster_id
            
            # Step 5: Create instances
            instance_ids = self.create_instances(new_cluster_id)
            result['instance_ids'] = instance_ids
            
            # Step 6: Reset credentials from Secrets Manager
            self.reset_credentials(new_cluster_id)
            
            # Step 7: Update DNS to point to new cluster
            self.update_dns(new_cluster_id)
            result['dns_updated'] = True
            
            # Step 8: Cleanup old cluster (optional)
            if cleanup_old:
                self.cleanup_old_cluster(skip_final_snapshot=skip_final_snapshot)
                result['old_cluster_cleaned_up'] = True
                
                # Rename new cluster to original name
                self.rename_cluster(
                    new_cluster_id,
                    self.target_config.cluster_identifier
                )
                result['final_cluster_id'] = self.target_config.cluster_identifier
            else:
                result['final_cluster_id'] = new_cluster_id
            
            result['completed_at'] = datetime.now().isoformat()
            result['status'] = 'success'
            
            logger.info("=" * 60)
            logger.info("REFRESH COMPLETED SUCCESSFULLY")
            logger.info(f"Environment: {self.target_config.name}")
            logger.info(f"Final cluster: {result['final_cluster_id']}")
            logger.info(f"DNS record: {self.target_config.dns_record_name}")
            logger.info("=" * 60)
            
        except Exception as e:
            result['status'] = 'failed'
            result['error'] = str(e)
            result['failed_at'] = datetime.now().isoformat()
            logger.error(f"Refresh failed: {e}")
            raise
        
        return result


def load_config_from_file(config_path: str) -> dict:
    """Load configuration from a JSON file."""
    with open(config_path, 'r') as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(
        description='Refresh Aurora cluster from production to lower environments'
    )
    parser.add_argument(
        'environment',
        choices=['staging', 'dev'],
        help='Target environment to refresh'
    )
    parser.add_argument(
        '--config',
        default='config.json',
        help='Path to configuration file (default: config.json)'
    )
    parser.add_argument(
        '--no-cleanup',
        action='store_true',
        help='Do not delete the old cluster after refresh'
    )
    parser.add_argument(
        '--keep-final-snapshot',
        action='store_true',
        help='Create a final snapshot before deleting old cluster'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Print configuration and exit without making changes'
    )
    parser.add_argument(
        '--region',
        default='us-east-1',
        help='AWS region (default: us-east-1)'
    )
    
    args = parser.parse_args()
    
    # Load configuration
    try:
        config = load_config_from_file(args.config)
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {args.config}")
        logger.info("Creating example configuration file...")
        create_example_config(args.config)
        sys.exit(1)
    
    # Build configuration objects
    prod_config = ProductionConfig(
        account_id=config['production']['account_id'],
        cluster_identifier=config['production']['cluster_identifier'],
        aws_profile=config['production'].get('aws_profile')
    )
    
    env_config = config['environments'][args.environment]
    target_config = EnvironmentConfig(
        name=args.environment,
        account_id=env_config['account_id'],
        cluster_identifier=env_config['cluster_identifier'],
        instance_class=env_config['instance_class'],
        db_subnet_group=env_config['db_subnet_group'],
        security_group_ids=env_config['security_group_ids'],
        secrets_admin=env_config['secrets_admin'],
        secrets_app=env_config['secrets_app'],
        hosted_zone_id=env_config['hosted_zone_id'],
        dns_record_name=env_config['dns_record_name'],
        aws_profile=env_config.get('aws_profile'),
        instance_count=env_config.get('instance_count', 1),
        # KMS and encryption
        kms_key_id=env_config.get('kms_key_id'),
        # Parameter groups
        db_cluster_parameter_group=env_config.get('db_cluster_parameter_group'),
        db_parameter_group=env_config.get('db_parameter_group'),
        # Cluster settings
        port=env_config.get('port', 3306),
        backup_retention_period=env_config.get('backup_retention_period', 7),
        preferred_backup_window=env_config.get('preferred_backup_window'),
        preferred_maintenance_window=env_config.get('preferred_maintenance_window'),
        deletion_protection=env_config.get('deletion_protection', False),
        # IAM auth
        enable_iam_database_authentication=env_config.get('enable_iam_database_authentication', False),
        # Monitoring
        enable_performance_insights=env_config.get('enable_performance_insights', False),
        performance_insights_kms_key_id=env_config.get('performance_insights_kms_key_id'),
        performance_insights_retention_period=env_config.get('performance_insights_retention_period', 7),
        monitoring_interval=env_config.get('monitoring_interval', 0),
        monitoring_role_arn=env_config.get('monitoring_role_arn'),
        # Logs
        enable_cloudwatch_logs_exports=env_config.get('enable_cloudwatch_logs_exports'),
        # Serverless
        serverless_v2_scaling_config=env_config.get('serverless_v2_scaling_config')
    )
    
    if args.dry_run:
        logger.info("DRY RUN - Configuration:")
        logger.info(f"  Production: {prod_config}")
        logger.info(f"  Target: {target_config}")
        logger.info(f"  Region: {args.region}")
        logger.info(f"  Cleanup old cluster: {not args.no_cleanup}")
        logger.info(f"  Keep final snapshot: {args.keep_final_snapshot}")
        return
    
    # Run the refresh
    manager = AuroraRefreshManager(
        prod_config=prod_config,
        target_config=target_config,
        region=args.region
    )
    
    result = manager.run_full_refresh(
        cleanup_old=not args.no_cleanup,
        skip_final_snapshot=not args.keep_final_snapshot
    )
    
    # Output result as JSON for automation
    print(json.dumps(result, indent=2))


def create_example_config(path: str) -> None:
    """Create an example configuration file."""
    example_config = {
        "_comments": {
            "kms_key_id": "IMPORTANT: Required for encrypted clusters. Use target account's KMS key ARN",
            "parameter_groups": "Create environment-specific parameter groups before running",
            "monitoring_role_arn": "Required if monitoring_interval > 0. Create IAM role with AmazonRDSEnhancedMonitoringRole policy"
        },
        "production": {
            "account_id": "111111111111",
            "cluster_identifier": "prod-aurora-cluster",
            "aws_profile": "production"
        },
        "environments": {
            "staging": {
                "account_id": "222222222222",
                "cluster_identifier": "staging-aurora-cluster",
                "aws_profile": "staging",
                
                "_comment_networking": "--- Networking ---",
                "db_subnet_group": "staging-db-subnet-group",
                "security_group_ids": ["sg-staging123"],
                "port": 3306,
                
                "_comment_compute": "--- Compute ---",
                "instance_class": "db.r6g.large",
                "instance_count": 2,
                
                "_comment_encryption": "--- Encryption (CRITICAL for cross-account) ---",
                "kms_key_id": "arn:aws:kms:us-east-1:222222222222:key/12345678-1234-1234-1234-123456789012",
                
                "_comment_parameter_groups": "--- Parameter Groups ---",
                "db_cluster_parameter_group": "staging-aurora-mysql8-cluster-params",
                "db_parameter_group": "staging-aurora-mysql8-db-params",
                
                "_comment_backup": "--- Backup & Maintenance ---",
                "backup_retention_period": 7,
                "preferred_backup_window": "03:00-04:00",
                "preferred_maintenance_window": "sun:04:00-sun:05:00",
                "deletion_protection": false,
                
                "_comment_auth": "--- Authentication ---",
                "enable_iam_database_authentication": false,
                "secrets_admin": "staging/aurora/admin",
                "secrets_app": "staging/aurora/app-credentials",
                
                "_comment_monitoring": "--- Monitoring ---",
                "enable_performance_insights": true,
                "performance_insights_retention_period": 7,
                "performance_insights_kms_key_id": "arn:aws:kms:us-east-1:222222222222:key/12345678-1234-1234-1234-123456789012",
                "monitoring_interval": 60,
                "monitoring_role_arn": "arn:aws:iam::222222222222:role/rds-monitoring-role",
                
                "_comment_logs": "--- CloudWatch Logs ---",
                "enable_cloudwatch_logs_exports": ["error", "slowquery"],
                
                "_comment_dns": "--- DNS ---",
                "hosted_zone_id": "Z1234567890ABC",
                "dns_record_name": "db.staging.example.com"
            },
            "dev": {
                "account_id": "222222222222",
                "cluster_identifier": "dev-aurora-cluster",
                "aws_profile": "dev",
                
                "db_subnet_group": "dev-db-subnet-group",
                "security_group_ids": ["sg-dev456"],
                "port": 3306,
                
                "instance_class": "db.r6g.medium",
                "instance_count": 1,
                
                "kms_key_id": "arn:aws:kms:us-east-1:222222222222:key/dev-key-id-here",
                
                "db_cluster_parameter_group": "dev-aurora-mysql8-cluster-params",
                "db_parameter_group": "dev-aurora-mysql8-db-params",
                
                "backup_retention_period": 1,
                "deletion_protection": false,
                
                "secrets_admin": "dev/aurora/admin",
                "secrets_app": "dev/aurora/app-credentials",
                
                "enable_performance_insights": false,
                "monitoring_interval": 0,
                
                "hosted_zone_id": "Z1234567890ABC",
                "dns_record_name": "db.dev.example.com"
            }
        }
    }
    
    with open(path, 'w') as f:
        json.dump(example_config, f, indent=2)
    
    logger.info(f"Example configuration written to: {path}")
    logger.info("Please edit this file with your actual values and run again.")


if __name__ == '__main__':
    main()
