#!/bin/bash
#
# Bash script equivalent of push_dump.py
# Uploads files to S3 and sends SNS notifications
#
# Usage:
#   ./push_dump.sh
#
# Environment variables (can be set via .env file):
#   DATA_DIR - Directory to scan for files (default: /home/miaxbus/bsx-mis/input)
#   BUCKET_NAME - S3 bucket name
#   TOPIC_ARN - SNS topic ARN for notifications

set -uo pipefail

# Load environment variables from .env file if it exists
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# Set default DATA_DIR if not provided
DATA_DIR="${DATA_DIR:-/home/miaxbus/bsx-mis/input}"
BUCKET_NAME="${BUCKET_NAME:-}"
TOPIC_ARN="${TOPIC_ARN:-}"

# Initialize message variable
message=""

# Function to upload file to S3 with retry logic
s3_upload() {
    local file_path="$1"
    local file_name="$2"
    local max_attempts=3
    local attempt=0
    local success=false

    while [ $attempt -lt $max_attempts ] && [ "$success" = false ]; do
        echo "Path $file_path name $file_name"
        if aws s3 cp "$file_path" "s3://${BUCKET_NAME}/${file_name}"; then
            success=true
        else
            attempt=$((attempt + 1))
            if [ $attempt -lt $max_attempts ]; then
                echo "Upload attempt $attempt failed, retrying..."
                sleep 1
            fi
        fi
    done

    if [ "$success" = false ]; then
        return 1
    fi
    return 0
}

# Function to publish message to SNS
publish_sns() {
    local msg="$1"
    
    if [ -z "$TOPIC_ARN" ]; then
        echo "Error: TOPIC_ARN not set. Message: $msg"
        return 1
    fi

    if aws sns publish \
        --topic-arn "$TOPIC_ARN" \
        --message "$msg"; then
        echo "SNS notification sent: $msg"
        return 0
    else
        echo "Failed to send SNS notification. Message: $msg"
        return 1
    fi
}

# Check if DATA_DIR exists
if [ ! -d "$DATA_DIR" ]; then
    echo "Error: Directory $DATA_DIR does not exist"
    exit 1
fi

# Check required environment variables
if [ -z "$BUCKET_NAME" ]; then
    echo "Error: BUCKET_NAME environment variable is not set"
    exit 1
fi

# Process files in the directory
for file_path in "$DATA_DIR"/*; do
    # Skip if no files match the pattern
    [ -e "$file_path" ] || continue
    
    # Skip if it's a directory (only process regular files)
    [ -f "$file_path" ] || continue
    
    # Get just the filename
    file=$(basename "$file_path")
    echo "$file"
    
    # Check if it's a schema file
    if [[ $file == bsxmisdataschema_* ]]; then
        message="Updated schema available ${file_path}."
    # Check if it's a data file
    elif [[ $file == bsxmisdata_* ]]; then
        # Capture upload result without exiting on failure
        if s3_upload "$file_path" "$file"; then
            : # Upload succeeded, continue
        else
            message="Failed to upload ${file} bsx data dump."
        fi
    fi
done

# Send SNS notification if there's a message
if [ -n "$message" ]; then
    # Try to publish, but don't exit on failure (matches Python behavior)
    if ! publish_sns "$message"; then
        # If publish fails, just print the message (like Python script does)
        echo "$message"
    fi
fi

echo "Script completed"

