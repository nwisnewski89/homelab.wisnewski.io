import json
import boto3
import tarfile
import tempfile
import os
import logging
from urllib.parse import unquote_plus
from typing import Dict, Any, List

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
s3_client = boto3.client('s3')

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda function to process SQS messages containing S3 event notifications
    for tar.gz files, extract them, and upload the contents back to S3.
    """
    
    # Get environment variables
    bucket_name = os.environ.get('BUCKET_NAME')
    
    if not bucket_name:
        logger.error("BUCKET_NAME environment variable not set")
        return {
            'statusCode': 500,
            'body': json.dumps('Configuration error: BUCKET_NAME not set')
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
                        result = process_s3_object(s3_record, bucket_name)
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

def process_s3_object(s3_record: Dict[str, Any], bucket_name: str) -> Dict[str, Any]:
    """
    Process a single S3 object from the event notification.
    
    Args:
        s3_record: S3 event record
        bucket_name: Name of the S3 bucket
        
    Returns:
        Dict with success status and error message if applicable
    """
    
    try:
        # Extract object information
        object_key = unquote_plus(s3_record['s3']['object']['key'])
        object_size = s3_record['s3']['object']['size']
        
        logger.info(f"Processing object: {object_key} (size: {object_size} bytes)")
        
        # Check if it's a tar.gz file
        if not object_key.lower().endswith('.tar.gz'):
            logger.info(f"Skipping non-tar.gz file: {object_key}")
            return {'success': True, 'message': 'Skipped non-tar.gz file'}
        
        # Download and extract the tar.gz file
        return extract_and_upload_tar_gz(bucket_name, object_key)
        
    except Exception as e:
        error_msg = f"Error processing S3 object: {str(e)}"
        logger.error(error_msg)
        return {'success': False, 'error': error_msg}

def extract_and_upload_tar_gz(bucket_name: str, object_key: str) -> Dict[str, Any]:
    """
    Download tar.gz file from S3, extract it, and upload contents back to S3.
    
    Args:
        bucket_name: Name of the S3 bucket
        object_key: Key of the tar.gz file in S3
        
    Returns:
        Dict with success status and error message if applicable
    """
    
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            # Download the tar.gz file
            tar_gz_path = os.path.join(temp_dir, 'archive.tar.gz')
            
            logger.info(f"Downloading {object_key} from bucket {bucket_name}")
            s3_client.download_file(bucket_name, object_key, tar_gz_path)
            
            # Extract the tar.gz file
            extract_dir = os.path.join(temp_dir, 'extracted')
            os.makedirs(extract_dir, exist_ok=True)
            
            logger.info(f"Extracting {tar_gz_path}")
            with tarfile.open(tar_gz_path, 'r:gz') as tar:
                # Security check: prevent path traversal attacks
                def is_safe_path(path: str) -> bool:
                    return not (path.startswith('/') or '..' in path or path.startswith('..'))
                
                safe_members = [member for member in tar.getmembers() 
                              if is_safe_path(member.name)]
                
                if len(safe_members) != len(tar.getmembers()):
                    logger.warning(f"Filtered out {len(tar.getmembers()) - len(safe_members)} unsafe paths")
                
                tar.extractall(path=extract_dir, members=safe_members)
            
            # Upload extracted files back to S3
            uploaded_files = []
            base_key_prefix = object_key.replace('.tar.gz', '/')
            
            for root, dirs, files in os.walk(extract_dir):
                for file in files:
                    local_file_path = os.path.join(root, file)
                    
                    # Calculate relative path from extract_dir
                    relative_path = os.path.relpath(local_file_path, extract_dir)
                    
                    # Create S3 key (normalize path separators)
                    s3_key = base_key_prefix + relative_path.replace(os.sep, '/')
                    
                    logger.info(f"Uploading {relative_path} to {s3_key}")
                    
                    # Upload file to S3
                    s3_client.upload_file(local_file_path, bucket_name, s3_key)
                    uploaded_files.append(s3_key)
            
            logger.info(f"Successfully extracted and uploaded {len(uploaded_files)} files from {object_key}")
            
            return {
                'success': True, 
                'message': f'Extracted {len(uploaded_files)} files',
                'uploaded_files': uploaded_files
            }
            
        except tarfile.TarError as e:
            error_msg = f"Error extracting tar.gz file {object_key}: {str(e)}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
            
        except Exception as e:
            error_msg = f"Error processing tar.gz file {object_key}: {str(e)}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
