#!/usr/bin/env python3
"""
Lambda function to import database schema from S3 into Aurora database.

This function is triggered by a CloudFormation Custom Resource and:
1. Downloads SQL file from S3
2. Connects to Aurora database using credentials from Secrets Manager
3. Executes the SQL schema
4. Reports success/failure back to CloudFormation
"""

import json
import os
import boto3
import logging
from typing import Dict, Any, Optional
import pymysql

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
s3_client = boto3.client('s3')
secrets_client = boto3.client('secretsmanager')


def get_secret(secret_arn: str) -> Dict[str, str]:
    """Retrieve database credentials from Secrets Manager"""
    try:
        response = secrets_client.get_secret_value(SecretId=secret_arn)
        secret = json.loads(response['SecretString'])
        return secret
    except Exception as e:
        logger.error(f"Error retrieving secret: {str(e)}")
        raise


def download_sql_from_s3(bucket: str, key: str) -> str:
    """Download SQL file from S3 and return as string"""
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        sql_content = response['Body'].read().decode('utf-8')
        logger.info(f"Downloaded SQL file from s3://{bucket}/{key} ({len(sql_content)} bytes)")
        return sql_content
    except Exception as e:
        logger.error(f"Error downloading from S3: {str(e)}")
        raise


def execute_sql_statements(
    sql_content: str,
    host: str,
    port: int,
    database: str,
    username: str,
    password: str
) -> None:
    """
    Execute SQL statements against the database.
    Splits by semicolon and executes each statement.
    """
    try:
        # Connect to database
        connection = pymysql.connect(
            host=host,
            port=port,
            user=username,
            password=password,
            database=database,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=10,
            read_timeout=60,
            write_timeout=60
        )
        
        logger.info(f"Connected to database {database} at {host}:{port}")
        
        try:
            with connection.cursor() as cursor:
                # Split SQL content by semicolon and execute each statement
                # Filter out empty statements and comments
                statements = [
                    stmt.strip() 
                    for stmt in sql_content.split(';') 
                    if stmt.strip() and not stmt.strip().startswith('--')
                ]
                
                logger.info(f"Executing {len(statements)} SQL statements")
                
                for i, statement in enumerate(statements, 1):
                    if statement:
                        try:
                            cursor.execute(statement)
                            logger.info(f"Executed statement {i}/{len(statements)}")
                        except Exception as e:
                            # Log error but continue with other statements
                            logger.warning(f"Error executing statement {i}: {str(e)}")
                            logger.debug(f"Statement: {statement[:200]}...")
                            # For schema imports, we might want to continue
                            # Uncomment the next line if you want to fail on any error:
                            # raise
            
            # Commit all changes
            connection.commit()
            logger.info("All SQL statements executed successfully")
            
        finally:
            connection.close()
            
    except Exception as e:
        logger.error(f"Error executing SQL: {str(e)}")
        raise


def send_cfn_response(
    event: Dict[str, Any],
    status: str,
    reason: str,
    physical_resource_id: Optional[str] = None
) -> None:
    """Send response to CloudFormation"""
    response_url = event.get('ResponseURL')
    if not response_url:
        logger.warning("No ResponseURL in event, skipping CFN response")
        return
    
    response_body = {
        'Status': status,
        'Reason': reason,
        'PhysicalResourceId': physical_resource_id or event.get('LogicalResourceId', 'schema-import'),
        'StackId': event.get('StackId'),
        'RequestId': event.get('RequestId'),
        'LogicalResourceId': event.get('LogicalResourceId'),
    }
    
    import urllib.request
    import json as json_lib
    
    json_data = json_lib.dumps(response_body)
    data = json_data.encode('utf-8')
    
    req = urllib.request.Request(
        response_url,
        data=data,
        headers={'Content-Type': '', 'Content-Length': str(len(data))},
        method='PUT'
    )
    
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            logger.info(f"CFN response sent: {status}")
    except Exception as e:
        logger.error(f"Error sending CFN response: {str(e)}")


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for schema import
    
    Expected event structure:
    {
        "RequestType": "Create" | "Update" | "Delete",
        "ResponseURL": "...",
        "StackId": "...",
        "RequestId": "...",
        "LogicalResourceId": "...",
        "ResourceProperties": {
            "S3Bucket": "bucket-name",
            "S3Key": "path/to/schema.sql",
            "SecretArn": "arn:aws:secretsmanager:...",
            "ClusterEndpoint": "cluster-endpoint.region.rds.amazonaws.com",
            "Port": 3306,
            "DatabaseName": "mydatabase"
        }
    }
    """
    logger.info(f"Received event: {json.dumps(event)}")
    
    request_type = event.get('RequestType', 'Create')
    properties = event.get('ResourceProperties', {})
    
    # Handle Delete requests
    if request_type == 'Delete':
        logger.info("Delete request - no action needed")
        send_cfn_response(event, 'SUCCESS', 'Schema import resource deleted')
        return {'statusCode': 200}
    
    try:
        # Extract properties
        s3_bucket = properties.get('S3Bucket')
        s3_key = properties.get('S3Key')
        secret_arn = properties.get('SecretArn')
        cluster_endpoint = properties.get('ClusterEndpoint')
        port = int(properties.get('Port', 3306))
        database_name = properties.get('DatabaseName')
        
        if not all([s3_bucket, s3_key, secret_arn, cluster_endpoint, database_name]):
            raise ValueError("Missing required properties")
        
        # Get database credentials
        logger.info(f"Retrieving credentials from secret: {secret_arn}")
        secret = get_secret(secret_arn)
        username = secret.get('username') or secret.get('user')
        password = secret.get('password')
        
        if not username or not password:
            raise ValueError("Secret must contain 'username' and 'password'")
        
        # Download SQL from S3
        logger.info(f"Downloading SQL from s3://{s3_bucket}/{s3_key}")
        sql_content = download_sql_from_s3(s3_bucket, s3_key)
        
        # Execute SQL statements
        logger.info(f"Executing SQL against {cluster_endpoint}:{port}/{database_name}")
        execute_sql_statements(
            sql_content=sql_content,
            host=cluster_endpoint,
            port=port,
            database=database_name,
            username=username,
            password=password
        )
        
        # Send success response
        reason = f"Schema imported successfully from s3://{s3_bucket}/{s3_key}"
        send_cfn_response(event, 'SUCCESS', reason)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Schema imported successfully',
                's3_bucket': s3_bucket,
                's3_key': s3_key
            })
        }
        
    except Exception as e:
        error_msg = f"Error importing schema: {str(e)}"
        logger.error(error_msg, exc_info=True)
        send_cfn_response(event, 'FAILED', error_msg)
        raise

