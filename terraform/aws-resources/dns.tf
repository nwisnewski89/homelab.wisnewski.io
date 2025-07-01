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

resource "aws_route53_record" "argocd" {
  zone_id = aws_route53_zone.dns_zone.zone_id
  name    = "argocd"
  type    = "A"
  ttl     = 60
  records = ["10.43.0.1"] 
}

resource "aws_route53_record" "pihole" {
  zone_id = aws_route53_zone.dns_zone.zone_id
  name    = "pihole"
  type    = "A"
  ttl     = 60
  records = ["10.43.0.2"]
}

resource "aws_route53_record" "nick" {
  zone_id = aws_route53_zone.dns_zone.zone_id
  name    = "nick"
  type    = "A"
  ttl     = 60
  records = ["10.43.0.3"]
}
