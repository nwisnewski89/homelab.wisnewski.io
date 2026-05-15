# Drupal S3 File Proxy

This directory contains a Kubernetes deployment for serving Drupal public files from S3 while keeping the browser URL on the Drupal domain.

The goal is for clients to request files from the normal Drupal path:

```text
https://sample.com/sites/default/files/example.pdf
```

Nginx receives that request inside Kubernetes and proxies it to S3:

```text
https://drupal-files-prod.s3.us-east-1.amazonaws.com/sites/default/files/example.pdf
```

The client never receives the S3 URL and does not need to know the bucket name.

## Architecture

```text
Client
  -> sample.com/sites/default/files/*
  -> Kubernetes Ingress
  -> drupal-file-proxy Nginx deployment
  -> S3 regional endpoint over the S3 VPC endpoint
  -> S3 bucket object
```

All other paths are proxied to the Drupal service configured by `DRUPAL_UPSTREAM`.

## Files

- `kubernetes.yaml` creates the namespace, Nginx ConfigMap, Deployment, Service, and Ingress.

## Values To Update

Update these environment variables in `kubernetes.yaml` before applying it:

```yaml
- name: SERVER_NAME
  value: sample.com
- name: S3_BUCKET
  value: drupal-files-prod
- name: AWS_REGION
  value: us-east-1
- name: DRUPAL_UPSTREAM
  value: drupal.default.svc.cluster.local:80
```

The S3 object keys are expected to match the Drupal URL path. For example:

```text
/sites/default/files/example.pdf
```

maps to:

```text
s3://drupal-files-prod/sites/default/files/example.pdf
```

## S3 VPC Endpoint Requirement

The Kubernetes nodes or pods running this proxy must reach S3 through an S3 VPC endpoint.

For a Gateway Endpoint, attach the endpoint to the route tables used by the EKS worker node subnets. With private EKS nodes, confirm the route table for those subnets has the S3 prefix list route created by the endpoint.

## Bucket Policy

This pure Nginx proxy does not sign S3 requests. The bucket policy must allow `s3:GetObject` from the S3 VPC endpoint.

Replace:

- `drupal-files-prod` with the bucket name
- `vpce-0123456789abcdef0` with the S3 VPC endpoint ID

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowPublicFileReadsOnlyFromS3VpcEndpoint",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::drupal-files-prod/sites/default/files/*",
      "Condition": {
        "StringEquals": {
          "aws:SourceVpce": "vpce-0123456789abcdef0"
        }
      }
    },
    {
      "Sid": "DenyInsecureTransport",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": [
        "arn:aws:s3:::drupal-files-prod",
        "arn:aws:s3:::drupal-files-prod/*"
      ],
      "Condition": {
        "Bool": {
          "aws:SecureTransport": "false"
        }
      }
    }
  ]
}
```

This policy allows anonymous object reads only when the request arrives through the named S3 VPC endpoint. It does not expose the objects directly to the public internet.

## Bucket Name

The bucket name does not need to match the domain name.

For this proxy pattern, `sample.com` is only the client-facing host. Nginx maps the request to whichever bucket is configured with `S3_BUCKET`.

Prefer a DNS-safe bucket name without dots, such as:

```text
drupal-files-prod
```

## Notes

- This is intended for Drupal public files, not private per-user downloads.
- If the content requires application authorization, use a signed application proxy instead of anonymous S3 reads through a VPC endpoint.
- The current config supports `GET` and `HEAD` only for `/sites/default/files/*`.
- Drupal must generate file URLs that remain on `/sites/default/files/*`; do not configure Drupal to emit direct S3 or CloudFront URLs for these public files.
