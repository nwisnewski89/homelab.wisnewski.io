resource "aws_s3_bucket" "etcd_backups" {
  bucket = "etcd-backups-${var.project_id}"
}

resource "aws_s3_bucket_versioning" "etcd_backups_versioning" {
  bucket = aws_s3_bucket.etcd_backups.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "etcd_backups_encryption" {
  bucket = aws_s3_bucket.etcd_backups.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "etcd_backups_public_access_block" {
  bucket = aws_s3_bucket.etcd_backups.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "etcd_backups_ownership_controls" {
  bucket = aws_s3_bucket.etcd_backups.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

data "aws_iam_policy_document" "etcd_backups_policy" {
  statement {
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.etcd_backups.arn}/*"]
  }
  statement {
    actions   = ["s3:List*"]
    resources = ["*"]
  }
}

data "aws_iam_policy_document" "dns_policy" {
  statement {
    actions   = ["route53:ChangeResourceRecordSets"]
    resources = [aws_route53_zone.dns_zone.arn]
  }
  statement {
    actions   = ["route53:List*", "route53:Get*"]
    resources = ["*"]
  }
}

resource "aws_iam_user" "etcd_backups_user" {
  name = "etcd-backups-${var.project_id}"
}

resource "aws_iam_access_key" "etcd_backups_access_key" {
  user = aws_iam_user.etcd_backups_user.name
}

resource "aws_iam_policy" "etcd_backups_policy" {
  name   = "etcd-backups-${var.project_id}"
  policy = data.aws_iam_policy_document.etcd_backups_policy.json
}

resource "aws_iam_user_policy_attachment" "etcd_backups_policy_attachment" {
  user       = aws_iam_user.etcd_backups_user.name
  policy_arn = aws_iam_policy.etcd_backups_policy.arn
}

resource "aws_iam_policy" "dns_policy" {
  name   = "dns-${var.project_id}"
  policy = data.aws_iam_policy_document.dns_policy.json
}

resource "aws_iam_user_policy_attachment" "dns_policy_attachment" {
  user       = aws_iam_user.etcd_backups_user.name
  policy_arn = aws_iam_policy.dns_policy.arn
}

resource "aws_route53_zone" "dns_zone" {
  name = var.route53_zone_name
}

resource "aws_cloudwatch_log_group" "dns_query_logs" {
  name              = "/aws/route53/${aws_route53_zone.dns_zone.name}"
  retention_in_days = 7
}

data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "route53_query_logging_policy_doc" {
  statement {
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["route53.amazonaws.com"]
    }
    resources = ["${aws_cloudwatch_log_group.dns_query_logs.arn}:*"]
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_cloudwatch_log_resource_policy" "route53_query_logging_policy" {
  policy_name     = "route53-query-logging-policy"
  policy_document = data.aws_iam_policy_document.route53_query_logging_policy_doc.json
}

resource "aws_route53_query_log" "dns_query_logging" {
  depends_on = [
    aws_cloudwatch_log_group.dns_query_logs,
    aws_cloudwatch_log_resource_policy.route53_query_logging_policy
  ]

  cloudwatch_log_group_arn = aws_cloudwatch_log_group.dns_query_logs.arn
  zone_id                  = aws_route53_zone.dns_zone.zone_id
}

