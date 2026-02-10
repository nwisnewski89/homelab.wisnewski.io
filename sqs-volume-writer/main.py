j#!/usr/bin/env python3
"""
SQS queue poller that writes each received message to a file on a shared volume.
Configure via environment variables; runs continuously until interrupted.
"""

import os
import sys
import time
import uuid
from pathlib import Path

import boto3
from botocore.exceptions import ClientError


def get_config() -> dict:
    """Load configuration from environment variables."""
    queue_url = os.environ.get("SQS_QUEUE_URL")
    output_dir = os.environ.get("OUTPUT_DIR", "/data")
    region = os.environ.get("AWS_REGION", "us-east-1")
    wait_time = int(os.environ.get("SQS_WAIT_TIME_SECONDS", "20"))
    visibility_timeout = int(os.environ.get("SQS_VISIBILITY_TIMEOUT", "60"))

    if not queue_url:
        print("ERROR: SQS_QUEUE_URL is required", file=sys.stderr)
        sys.exit(1)

    return {
        "queue_url": queue_url,
        "output_dir": Path(output_dir),
        "region": region,
        "wait_time": wait_time,
        "visibility_timeout": visibility_timeout,
    }


def ensure_output_dir(path: Path) -> None:
    """Create output directory and parents if they do not exist."""
    path.mkdir(parents=True, exist_ok=True)


def write_message_to_file(output_dir: Path, message_id: str, body: str) -> Path:
    """
    Write message body to a unique file in the output directory.
    Returns the path of the written file.
    """
    # Use message_id in filename for uniqueness; add short uuid to avoid collisions
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in message_id)
    filename = f"{safe_id}_{uuid.uuid4().hex[:8]}.json"
    filepath = output_dir / filename

    filepath.write_text(body, encoding="utf-8")
    return filepath


def poll_and_process(config: dict) -> None:
    """Continuously poll SQS and write each message to a file."""
    sqs = boto3.client("sqs", region_name=config["region"])
    queue_url = config["queue_url"]
    output_dir = config["output_dir"]
    wait_time = config["wait_time"]
    visibility_timeout = config["visibility_timeout"]

    ensure_output_dir(output_dir)
    print(f"Polling {queue_url}, writing to {output_dir.resolve()}", flush=True)

    while True:
        try:
            response = sqs.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=wait_time,
                VisibilityTimeout=visibility_timeout,
                MessageAttributeNames=["All"],
            )

            messages = response.get("Messages", [])
            for msg in messages:
                receipt_handle = msg["ReceiptHandle"]
                message_id = msg["MessageId"]
                body = msg.get("Body", "")

                try:
                    filepath = write_message_to_file(output_dir, message_id, body)
                    print(f"Wrote message {message_id} -> {filepath}", flush=True)
                except OSError as e:
                    print(f"ERROR writing message {message_id}: {e}", file=sys.stderr)
                    continue

                try:
                    sqs.delete_message(
                        QueueUrl=queue_url,
                        ReceiptHandle=receipt_handle,
                    )
                except ClientError as e:
                    print(
                        f"ERROR deleting message {message_id}: {e}",
                        file=sys.stderr,
                    )

        except ClientError as e:
            print(f"SQS error: {e}", file=sys.stderr)
            time.sleep(5)
        except KeyboardInterrupt:
            print("Stopping.", flush=True)
            break


def main() -> None:
    config = get_config()
    poll_and_process(config)


if __name__ == "__main__":
    main()
