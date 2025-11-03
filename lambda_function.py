import json
import boto3
import os
import logging
from typing import Dict, Any

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
ecs_client = boto3.client('ecs')


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda function to trigger ECS tasks when SQS messages are received.
    This replaces the long-running Lambda with a quick trigger that starts ECS tasks.
    """
    
    # Get environment variables
    cluster_name = os.environ.get('CLUSTER_NAME')
    task_definition_arn = os.environ.get('TASK_DEFINITION_ARN')
    subnet_ids = os.environ.get('SUBNET_IDS', '').split(',')
    security_group_ids = os.environ.get('SECURITY_GROUP_IDS', '').split(',')
    
    if not all([cluster_name, task_definition_arn, subnet_ids, security_group_ids]):
        logger.error("Required environment variables not set")
        return {
            'statusCode': 500,
            'body': json.dumps('Configuration error: Missing required environment variables')
        }
    
    # Process SQS records
    successful_messages = []
    failed_messages = []
    
    for record in event.get('Records', []):
        try:
            # Parse SQS message
            message_body = json.loads(record['body'])
            
            # Handle S3 event notification
            if 'Records' in message_body:
                for s3_record in message_body['Records']:
                    if s3_record.get('eventName', '').startswith('ObjectCreated'):
                        result = trigger_ecs_task(
                            s3_record, 
                            cluster_name,
                            task_definition_arn,
                            subnet_ids,
                            security_group_ids
                        )
                        if result['success']:
                            successful_messages.append(record['messageId'])
                        else:
                            failed_messages.append({
                                'itemIdentifier': record['messageId'],
                                'errorMessage': result['error']
                            })
            else:
                logger.warning(f"Unexpected message format: {message_body}")
                failed_messages.append({
                    'itemIdentifier': record['messageId'],
                    'errorMessage': 'Unexpected message format'
                })
                
        except Exception as e:
            logger.error(f"Error processing record {record.get('messageId', 'unknown')}: {str(e)}")
            failed_messages.append({
                'itemIdentifier': record['messageId'],
                'errorMessage': str(e)
            })
    
    # Return batch failure information for SQS
    response = {
        'statusCode': 200,
        'body': json.dumps({
            'successful': len(successful_messages),
            'failed': len(failed_messages)
        })
    }
    
    if failed_messages:
        response['batchItemFailures'] = failed_messages
    
    return response


def trigger_ecs_task(s3_record: Dict[str, Any], cluster_name: str, 
                    task_definition_arn: str, subnet_ids: list, 
                    security_group_ids: list) -> Dict[str, Any]:
    """
    Trigger an ECS task to process the S3 object.
    
    Args:
        s3_record: S3 event record
        cluster_name: ECS cluster name
        task_definition_arn: ECS task definition ARN
        subnet_ids: List of subnet IDs for the task
        security_group_ids: List of security group IDs for the task
        
    Returns:
        Dict with success status and error message if applicable
    """
    
    try:
        # Extract object information
        bucket_name = s3_record['s3']['bucket']['name']
        object_key = s3_record['s3']['object']['key']
        object_size = s3_record['s3']['object']['size']
        
        logger.info(f"Triggering ECS task for object: {object_key} (size: {object_size} bytes)")
        
        # Check if it's a tar or tar.gz file
        if not (object_key.lower().endswith('.tar') or object_key.lower().endswith('.tar.gz')):
            logger.info(f"Skipping non-tar file: {object_key}")
            return {'success': True, 'message': 'Skipped non-tar file'}
        
        # Prepare task overrides
        task_overrides = {
            'containerOverrides': [
                {
                    'name': 'SqlUpsertContainer',
                    'environment': [
                        {
                            'name': 'S3_BUCKET',
                            'value': bucket_name
                        },
                        {
                            'name': 'S3_KEY',
                            'value': object_key
                        },
                        {
                            'name': 'S3_EVENT_RECORD',
                            'value': json.dumps(s3_record)
                        }
                    ]
                }
            ]
        }
        
        # Run the ECS task
        response = ecs_client.run_task(
            cluster=cluster_name,
            taskDefinition=task_definition_arn,
            launchType='FARGATE',
            networkConfiguration={
                'awsvpcConfiguration': {
                    'subnets': subnet_ids,
                    'securityGroups': security_group_ids,
                    'assignPublicIp': 'DISABLED'
                }
            },
            overrides=task_overrides,
            tags=[
                {
                    'key': 'Source',
                    'value': 'S3Event'
                },
                {
                    'key': 'S3Bucket',
                    'value': bucket_name
                },
                {
                    'key': 'S3Key',
                    'value': object_key
                }
            ]
        )
        
        task_arn = response['tasks'][0]['taskArn']
        logger.info(f"Successfully triggered ECS task: {task_arn}")
        
        return {
            'success': True,
            'message': f'ECS task triggered: {task_arn}',
            'task_arn': task_arn
        }
        
    except Exception as e:
        error_msg = f"Error triggering ECS task: {str(e)}"
        logger.error(error_msg)
        return {'success': False, 'error': error_msg}
