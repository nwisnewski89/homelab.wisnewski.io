# SQS Volume Writer

Python application that continuously polls an AWS SQS queue and writes each message to a file on a shared volume (e.g. for Kubernetes, Docker, or host use).

## Behavior

- Long-polls the queue (configurable wait time).
- For each message: writes the message body to a unique file under `OUTPUT_DIR`, then deletes the message from the queue.
- Runs until interrupted (e.g. `SIGINT`).

## Configuration (environment variables)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SQS_QUEUE_URL` | Yes | — | Full URL of the SQS queue to poll |
| `OUTPUT_DIR` | No | `/data` | Directory on the shared volume where message files are written |
| `AWS_REGION` | No | `us-east-1` | AWS region for the SQS client |
| `SQS_WAIT_TIME_SECONDS` | No | `20` | Long-poll wait time (1–20) |
| `SQS_VISIBILITY_TIMEOUT` | No | `60` | Visibility timeout in seconds after receive |

AWS credentials are taken from the usual sources (env vars `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`, IAM role, `~/.aws/credentials`, etc.).

## Local run

```bash
cd sqs-volume-writer
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt

export SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123456789012/my-queue
export OUTPUT_DIR=./out
python main.py
```

## Docker

```bash
docker build -t sqs-volume-writer .
docker run --rm \
  -e SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123456789012/my-queue \
  -e AWS_REGION=us-east-1 \
  -v /host/path/to/data:/data \
  sqs-volume-writer
```

## Output files

Each message is written to a single file under `OUTPUT_DIR`. Filenames are derived from the SQS message ID plus a short random suffix (e.g. `abc123_1a2b3c4d.json`). The file content is the raw message body (unchanged).
