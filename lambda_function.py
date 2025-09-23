import json
import boto3
import tarfile
import tempfile
import os
import logging
import pymysql
import ssl
from urllib.parse import unquote_plus
from typing import Dict, Any, List
import botocore.session
from botocore.credentials import Credentials

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
s3_client = boto3.client('s3')
secrets_client = boto3.client('secretsmanager')
rds_client = boto3.client('rds')


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda function to process SQS messages containing S3 event notifications
    for tar/tar.gz files, extract SQL files, and execute upserts against MySQL RDS.
    """
    
    # Get environment variables
    bucket_name = os.environ.get('BUCKET_NAME')
    db_endpoint = os.environ.get('DB_ENDPOINT')
    db_port = int(os.environ.get('DB_PORT', '3306'))
    db_name = os.environ.get('DB_NAME')
    db_secret_arn = os.environ.get('DB_SECRET_ARN')
    db_resource_id = os.environ.get('DB_RESOURCE_ID')
    
    if not all([bucket_name, db_endpoint, db_name, db_secret_arn, db_resource_id]):
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
                        result = process_s3_object(
                            s3_record, 
                            bucket_name, 
                            db_endpoint, 
                            db_port, 
                            db_name, 
                            db_secret_arn,
                            db_resource_id
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


def process_s3_object(s3_record: Dict[str, Any], bucket_name: str, db_endpoint: str, 
                     db_port: int, db_name: str, db_secret_arn: str, db_resource_id: str) -> Dict[str, Any]:
    """
    Process a single S3 object from the event notification.
    
    Args:
        s3_record: S3 event record
        bucket_name: Name of the S3 bucket
        db_endpoint: RDS endpoint
        db_port: RDS port
        db_name: Database name
        db_secret_arn: ARN of the database credentials secret
        db_resource_id: RDS instance resource ID
        
    Returns:
        Dict with success status and error message if applicable
    """
    
    try:
        # Extract object information
        object_key = unquote_plus(s3_record['s3']['object']['key'])
        object_size = s3_record['s3']['object']['size']
        
        logger.info(f"Processing object: {object_key} (size: {object_size} bytes)")
        
        # Check if it's a tar or tar.gz file
        if not (object_key.lower().endswith('.tar') or object_key.lower().endswith('.tar.gz')):
            logger.info(f"Skipping non-tar file: {object_key}")
            return {'success': True, 'message': 'Skipped non-tar file'}
        
        # Download and extract the tar file, then execute SQL
        return extract_and_execute_sql(
            bucket_name, 
            object_key, 
            db_endpoint, 
            db_port, 
            db_name, 
            db_secret_arn,
            db_resource_id
        )
        
    except Exception as e:
        error_msg = f"Error processing S3 object: {str(e)}"
        logger.error(error_msg)
        return {'success': False, 'error': error_msg}


def extract_and_execute_sql(bucket_name: str, object_key: str, db_endpoint: str, 
                           db_port: int, db_name: str, db_secret_arn: str, db_resource_id: str) -> Dict[str, Any]:
    """
    Download tar file from S3, extract SQL files, and execute them against RDS MySQL.
    
    Args:
        bucket_name: Name of the S3 bucket
        object_key: Key of the tar file in S3
        db_endpoint: RDS endpoint
        db_port: RDS port
        db_name: Database name
        db_secret_arn: ARN of the database credentials secret
        db_resource_id: RDS instance resource ID
        
    Returns:
        Dict with success status and error message if applicable
    """
    
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            # Download the tar file
            tar_path = os.path.join(temp_dir, 'archive.tar')
            
            logger.info(f"Downloading {object_key} from bucket {bucket_name}")
            s3_client.download_file(bucket_name, object_key, tar_path)
            
            # Extract the tar file
            extract_dir = os.path.join(temp_dir, 'extracted')
            os.makedirs(extract_dir, exist_ok=True)
            
            logger.info(f"Extracting {tar_path}")
            
            # Determine compression type
            if object_key.lower().endswith('.tar.gz'):
                tar_mode = 'r:gz'
            else:
                tar_mode = 'r'
            
            with tarfile.open(tar_path, tar_mode) as tar:
                # Security check: prevent path traversal attacks
                def is_safe_path(path: str) -> bool:
                    return not (path.startswith('/') or '..' in path or path.startswith('..'))
                
                safe_members = [member for member in tar.getmembers() 
                              if is_safe_path(member.name)]
                
                if len(safe_members) != len(tar.getmembers()):
                    logger.warning(f"Filtered out {len(tar.getmembers()) - len(safe_members)} unsafe paths")
                
                tar.extractall(path=extract_dir, members=safe_members)
            
            # Find and execute SQL files
            sql_files = find_sql_files(extract_dir)
            
            if not sql_files:
                logger.warning(f"No SQL files found in {object_key}")
                return {'success': True, 'message': 'No SQL files found in archive'}
            
            # Execute SQL files against RDS
            execution_results = execute_sql_files(
                sql_files, 
                db_endpoint, 
                db_port, 
                db_name, 
                db_secret_arn,
                db_resource_id
            )
            
            logger.info(f"Successfully processed {len(sql_files)} SQL files from {object_key}")
            
            return {
                'success': True, 
                'message': f'Executed {len(sql_files)} SQL files',
                'sql_files': [os.path.basename(f) for f in sql_files],
                'execution_results': execution_results
            }
            
        except tarfile.TarError as e:
            error_msg = f"Error extracting tar file {object_key}: {str(e)}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
            
        except Exception as e:
            error_msg = f"Error processing tar file {object_key}: {str(e)}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}


def find_sql_files(directory: str) -> List[str]:
    """
    Recursively find all SQL files in the extracted directory.
    
    Args:
        directory: Directory to search
        
    Returns:
        List of SQL file paths
    """
    sql_files = []
    
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.lower().endswith('.sql'):
                sql_files.append(os.path.join(root, file))
    
    # Sort files to ensure consistent execution order
    sql_files.sort()
    return sql_files


def get_db_credentials(secret_arn: str) -> Dict[str, str]:
    """
    Retrieve database credentials from AWS Secrets Manager.
    
    Args:
        secret_arn: ARN of the secret containing database credentials
        
    Returns:
        Dictionary with username and password
    """
    try:
        response = secrets_client.get_secret_value(SecretId=secret_arn)
        secret_data = json.loads(response['SecretString'])
        return {
            'username': secret_data['username'],
            'password': secret_data['password']
        }
    except Exception as e:
        logger.error(f"Error retrieving database credentials: {str(e)}")
        raise


def generate_iam_auth_token(db_endpoint: str, db_port: int, username: str, region: str) -> str:
    """
    Generate an IAM authentication token for RDS.
    
    Args:
        db_endpoint: RDS endpoint
        db_port: RDS port
        username: Database username
        region: AWS region
        
    Returns:
        IAM authentication token
    """
    try:
        session = botocore.session.get_session()
        client = session.create_client('rds', region_name=region)
        
        token = client.generate_db_auth_token(
            DBHostname=db_endpoint,
            Port=db_port,
            DBUsername=username,
            Region=region
        )
        
        return token
    except Exception as e:
        logger.error(f"Error generating IAM auth token: {str(e)}")
        raise


def execute_sql_files(sql_files: List[str], db_endpoint: str, db_port: int, 
                     db_name: str, db_secret_arn: str, db_resource_id: str) -> List[Dict[str, Any]]:
    """
    Execute SQL files against the MySQL RDS instance using IAM authentication.
    
    Args:
        sql_files: List of SQL file paths
        db_endpoint: RDS endpoint
        db_port: RDS port
        db_name: Database name
        db_secret_arn: ARN of the database credentials secret
        db_resource_id: RDS instance resource ID
        
    Returns:
        List of execution results
    """
    results = []
    
    # Get AWS region
    region = os.environ.get('AWS_REGION', 'us-east-1')
    
    # Get database credentials for IAM user creation (if needed)
    credentials = get_db_credentials(db_secret_arn)
    master_username = credentials['username']
    master_password = credentials['password']
    
    # Create IAM database user if it doesn't exist
    iam_username = 'lambda_user'
    
    try:
        # First, connect as master user to create IAM user if needed
        logger.info("Connecting as master user to set up IAM authentication")
        
        connection = pymysql.connect(
            host=db_endpoint,
            port=db_port,
            user=master_username,
            password=master_password,
            database=db_name,
            ssl_ca='/opt/rds-ca-2019-root.pem',
            ssl_verify_cert=True,
            ssl_verify_identity=True
        )
        
        with connection.cursor() as cursor:
            # Create IAM user if it doesn't exist
            cursor.execute(f"SELECT User FROM mysql.user WHERE User = '{iam_username}'")
            if not cursor.fetchone():
                logger.info(f"Creating IAM user: {iam_username}")
                cursor.execute(f"CREATE USER '{iam_username}' IDENTIFIED WITH AWSAuthenticationPlugin AS 'RDS'")
                cursor.execute(f"GRANT ALL PRIVILEGES ON {db_name}.* TO '{iam_username}'")
                cursor.execute("FLUSH PRIVILEGES")
                connection.commit()
                logger.info(f"IAM user {iam_username} created successfully")
        
        connection.close()
        
        # Now connect using IAM authentication
        logger.info("Connecting using IAM authentication")
        
        iam_token = generate_iam_auth_token(db_endpoint, db_port, iam_username, region)
        
        iam_connection = pymysql.connect(
            host=db_endpoint,
            port=db_port,
            user=iam_username,
            password=iam_token,
            database=db_name,
            ssl_ca='/opt/rds-ca-2019-root.pem',
            ssl_verify_cert=True,
            ssl_verify_identity=True
        )
        
        # Execute each SQL file
        for sql_file in sql_files:
            try:
                logger.info(f"Executing SQL file: {os.path.basename(sql_file)}")
                
                with open(sql_file, 'r', encoding='utf-8') as f:
                    sql_content = f.read()
                
                # Split SQL content into individual statements
                statements = [stmt.strip() for stmt in sql_content.split(';') if stmt.strip()]
                
                with iam_connection.cursor() as cursor:
                    executed_statements = 0
                    for statement in statements:
                        if statement:
                            cursor.execute(statement)
                            executed_statements += 1
                    
                    iam_connection.commit()
                
                results.append({
                    'file': os.path.basename(sql_file),
                    'success': True,
                    'statements_executed': executed_statements,
                    'message': f'Successfully executed {executed_statements} statements'
                })
                
                logger.info(f"Successfully executed {executed_statements} statements from {os.path.basename(sql_file)}")
                
            except Exception as e:
                error_msg = f"Error executing SQL file {os.path.basename(sql_file)}: {str(e)}"
                logger.error(error_msg)
                results.append({
                    'file': os.path.basename(sql_file),
                    'success': False,
                    'error': error_msg
                })
                # Continue with next file even if one fails
        
        iam_connection.close()
        
    except Exception as e:
        error_msg = f"Database connection error: {str(e)}"
        logger.error(error_msg)
        results.append({
            'success': False,
            'error': error_msg
        })
    
    return results
