# ArgoCD Post-Sync Hook: Post to Message Queue

After a successful Argo CD sync, these hooks send a single message to a message queue so downstream systems (CI, workers, other clusters) can react to deployments.

## Options

| File | Queue | Image |
|------|--------|--------|
| **job-sqs.yaml** | AWS SQS | `amazon/aws-cli` |
| **job-rabbitmq.yaml** | RabbitMQ | `curlimages/curl` (Management HTTP API) |

## Usage

1. **Include the Job in your Application source**  
   Add the chosen manifest to the directory your Argo CD Application syncs (e.g. a kustomize base, or a raw manifest next to your other resources). Only one of the jobs should run per app (SQS or RabbitMQ, not both unless you want two notifications).

2. **Create the Secret** in the same namespace as the synced resources (the namespace the Application deploys into).

3. **Set `APP_NAME`** in the Job’s `env` to your Argo CD Application name so the message body is useful for routing or logging.

---

## SQS (job-sqs.yaml)

### Secret

Create a Secret with the queue URL and AWS identity. Either use static credentials or IRSA.

**Static credentials (e.g. for testing):**

```bash
kubectl create secret generic argocd-postsync-sqs-secret -n YOUR_NAMESPACE \
  --from-literal=SQS_QUEUE_URL=https://sqs.REGION.amazonaws.com/ACCOUNT/QUEUE_NAME \
  --from-literal=AWS_REGION=us-east-1 \
  --from-literal=AWS_ACCESS_KEY_ID=AKIA... \
  --from-literal=AWS_SECRET_ACCESS_KEY=...
```

**IRSA (recommended in EKS):**  
Create an IAM role with `sqs:SendMessage` on the queue, associate it with a service account, and in the Job spec set `serviceAccountName` to that service account. In the Secret, only include `SQS_QUEUE_URL` and `AWS_REGION`; the two key refs for `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` are marked `optional: true`, so they can be omitted when using IRSA.

### Message body

The hook sends one SQS message per sync with a JSON body, for example:

```json
{
  "event": "argocd.postsync",
  "app": "my-app",
  "namespace": "my-namespace",
  "timestamp": "2025-02-25T12:00:00Z"
}
```

Message attributes `EventType` and `App` are set for filtering.

---

## RabbitMQ (job-rabbitmq.yaml)

### Prerequisites

- RabbitMQ Management plugin enabled.
- Queue created (or permissions to declare it).
- User with permission to publish to the default exchange and the target queue.

### Secret

```bash
kubectl create secret generic argocd-postsync-rabbitmq-secret -n YOUR_NAMESPACE \
  --from-literal=RABBITMQ_URL=https://rabbitmq.example.com \
  --from-literal=VHOST=/ \
  --from-literal=QUEUE=argocd.sync.events \
  --from-literal=USERNAME=notify \
  --from-literal=PASSWORD=...
```

`RABBITMQ_URL` is the Management API base (e.g. `https://host:15672`). The job publishes to the **default exchange** with `routing_key` = `QUEUE`.

### Message body

Same JSON shape as SQS (e.g. `event`, `app`, `namespace`, `timestamp`).

---

## Hook behavior

- **When it runs:** After all sync resources are applied successfully (PostSync phase).
- **Deletion:** `hook-delete-policy: BeforeHookCreation` removes the previous Job before creating the new one on the next sync, so you don’t accumulate finished Jobs.
- **Failure:** If the Job fails (e.g. queue unreachable), the sync is reported as failed. Tune `backoffLimit` and ensure the queue and credentials are correct.

## One hook per app

These manifests define a single Job name. If you add the same manifest to multiple Applications (e.g. via a shared kustomize base), every app will create a Job named `argocd-postsync-notify-sqs` (or `-rabbitmq`) in **its own** namespace, so they don’t conflict. For per-app queue or routing, set `APP_NAME` (and optionally different Secrets per app).
