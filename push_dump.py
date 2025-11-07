#!/usr/bin/env python3
import boto3
import os
from dotenv import load_dotenv
from botocore.exceptions import ClientError

session = boto3.Session()

def main() -> None:
    load_dotenv()
    drop_directory = os.getenv('DATA_DIR', '/home/miaxbus/bsx-mis/input')
    message = ''
    for file in os.listdir(drop_directory):
        print(file)
        file_path = os.path.join(drop_directory, file)
        if file.startswith('bsxmisdataschema_'):
            message = f"Updated schema available {file_path}."
        elif file.startswith('bsxmisdata_'):
            success = s3_upload(file_path, file)
            if not success:
                message = f"Failed to upload {file} bsx data dump."
    
    if message:
        try:
            sns_client = session.client('sns')
            sns_client.publish(
                TopicArn=os.environ.get('TOPIC_ARN'),
                Message=message
            )
        except ClientError as e:
            print(message)
        
def s3_upload(file_path: str, file_name: str) -> bool:
    s3 = session.client('s3')
    i = 0
    success = False

    while i < 3 and not success:
        try:
            print(f"Path {file_path} name {file_name}")
            s3.upload_file(file_path, os.environ.get('BUCKET_NAME'), file_name)
            success = True
        except ClientError as e:
            i += 1

    return success

if __name__ == "__main__":
    main()
