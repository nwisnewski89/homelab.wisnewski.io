# Push Dump Script Conversion: Python to Bash

This document explains the conversion of `push_dump.py` (Python/boto3) to `push_dump.sh` (Bash/AWS CLI).

## Overview

Both scripts perform the same functionality:
1. Scan a directory for files
2. Process files matching specific patterns:
   - `bsxmisdataschema_*` → Generate notification message
   - `bsxmisdata_*` → Upload to S3 with retry logic
3. Send SNS notification if there's a message

## Key Conversions

### Environment Variables

**Python:**
```python
from dotenv import load_dotenv
load_dotenv()
DATA_DIR = os.getenv('DATA_DIR', '/home/miaxbus/bsx-mis/input')
```

**Bash:**
```bash
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi
DATA_DIR="${DATA_DIR:-/home/miaxbus/bsx-mis/input}"
```

### File Listing

**Python:**
```python
for file in os.listdir(drop_directory):
    file_path = os.path.join(drop_directory, file)
```

**Bash:**
```bash
for file_path in "$DATA_DIR"/*; do
    [ -e "$file_path" ] || continue
    [ -f "$file_path" ] || continue  # Only process files
    file=$(basename "$file_path")
```

### Pattern Matching

**Python:**
```python
if file.startswith('bsxmisdataschema_'):
    # ...
elif file.startswith('bsxmisdata_'):
    # ...
```

**Bash:**
```bash
if [[ $file == bsxmisdataschema_* ]]; then
    # ...
elif [[ $file == bsxmisdata_* ]]; then
    # ...
```

### S3 Upload with Retry

**Python:**
```python
def s3_upload(file_path: str, file_name: str) -> bool:
    i = 0
    success = False
    while i < 3 and not success:
        try:
            s3.upload_file(file_path, os.environ.get('BUCKET_NAME'), file_name)
            success = True
        except ClientError as e:
            i += 1
    return success
```

**Bash:**
```bash
s3_upload() {
    local file_path="$1"
    local file_name="$2"
    local max_attempts=3
    local attempt=0
    local success=false

    while [ $attempt -lt $max_attempts ] && [ "$success" = false ]; do
        if aws s3 cp "$file_path" "s3://${BUCKET_NAME}/${file_name}"; then
            success=true
        else
            attempt=$((attempt + 1))
            if [ $attempt -lt $max_attempts ]; then
                sleep 1
            fi
        fi
    done

    [ "$success" = false ] && return 1
    return 0
}
```

### SNS Publish

**Python:**
```python
sns_client = session.client('sns')
sns_client.publish(
    TopicArn=os.environ.get('TOPIC_ARN'),
    Message=message
)
```

**Bash:**
```bash
aws sns publish \
    --topic-arn "$TOPIC_ARN" \
    --message "$msg"
```

## Differences and Considerations

### Error Handling

- **Python**: Uses try/except blocks, continues processing even on errors
- **Bash**: Uses return codes, continues processing (doesn't exit on upload failures)

### Retry Logic

- **Python**: Retries up to 3 times on `ClientError`
- **Bash**: Retries up to 3 times, adds 1 second delay between retries

### Message Handling

- Both scripts: Only the last message is kept (schema message can be overwritten by upload failure message)
- Both scripts: If SNS publish fails, the message is printed to stdout

## Usage

### Prerequisites

1. AWS CLI installed and configured
2. Appropriate IAM permissions for S3 and SNS
3. Environment variables set (via .env file or export)

### Environment Variables

Required:
- `BUCKET_NAME` - S3 bucket name
- `TOPIC_ARN` - SNS topic ARN

Optional:
- `DATA_DIR` - Directory to scan (default: `/home/miaxbus/bsx-mis/input`)

### Running the Script

```bash
# Make executable (if not already)
chmod +x push_dump.sh

# Run the script
./push_dump.sh
```

### Example .env File

```bash
DATA_DIR=/home/miaxbus/bsx-mis/input
BUCKET_NAME=my-s3-bucket
TOPIC_ARN=arn:aws:sns:us-east-1:123456789012:my-topic
```

## Testing

### Test S3 Upload
```bash
# Create a test file
echo "test" > /tmp/test_bsxmisdata_file.txt

# Test upload
aws s3 cp /tmp/test_bsxmisdata_file.txt s3://your-bucket/test_bsxmisdata_file.txt
```

### Test SNS Publish
```bash
aws sns publish \
    --topic-arn "arn:aws:sns:region:account:topic" \
    --message "Test message"
```

### Test Pattern Matching
```bash
# Create test files
touch /path/to/data_dir/bsxmisdataschema_test.sql
touch /path/to/data_dir/bsxmisdata_test.csv
touch /path/to/data_dir/other_file.txt

# Run script - should only process schema and data files
./push_dump.sh
```

## Troubleshooting

### AWS CLI Not Found
```bash
# Install AWS CLI
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install
```

### Permission Denied
```bash
# Check IAM permissions
aws s3 ls s3://your-bucket/
aws sns list-topics
```

### Upload Failures
- Check S3 bucket permissions
- Verify bucket name is correct
- Check network connectivity
- Review CloudWatch logs if using IAM roles

### SNS Publish Failures
- Verify TOPIC_ARN is correct
- Check SNS permissions
- Ensure topic exists in the same region

## Comparison Table

| Feature | Python (boto3) | Bash (AWS CLI) |
|---------|----------------|----------------|
| File Listing | `os.listdir()` | `for file in "$DIR"/*` |
| Pattern Matching | `str.startswith()` | `[[ $var == pattern* ]]` |
| S3 Upload | `s3.upload_file()` | `aws s3 cp` |
| SNS Publish | `sns.publish()` | `aws sns publish` |
| Retry Logic | try/except loop | while loop with return codes |
| Error Handling | Exceptions | Return codes |
| Dependencies | boto3, python-dotenv | AWS CLI, bash |

## Advantages of Each Approach

### Python (boto3)
- Better error handling with exceptions
- Type hints and IDE support
- Easier to extend with complex logic
- Better for programmatic use

### Bash (AWS CLI)
- No Python dependencies
- Simpler deployment (just a script)
- Easier to integrate with shell scripts
- Better for cron jobs and system scripts
- Smaller footprint

## Migration Checklist

- [x] Convert file listing logic
- [x] Convert pattern matching
- [x] Convert S3 upload with retry
- [x] Convert SNS publish
- [x] Handle environment variables
- [x] Match error handling behavior
- [x] Add file type checking (skip directories)
- [x] Make script executable
- [ ] Test with actual files
- [ ] Verify S3 uploads
- [ ] Verify SNS notifications
- [ ] Update deployment/cron jobs
- [ ] Update documentation

