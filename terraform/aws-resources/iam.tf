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

data "aws_iam_policy_document" "ses_policy_doc" {
  statement {
    actions = [
      "ses:SendEmail",
      "ses:SendRawEmail"
    ]
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

resource "aws_iam_policy" "ses_policy" {
  name   = "ses-${var.project_id}"
  policy = data.aws_iam_policy_document.ses_policy_doc.json
}

resource "aws_iam_user_policy_attachment" "ses_policy_attachment" {
  user       = aws_iam_user.etcd_backups_user.name
  policy_arn = aws_iam_policy.ses_policy.arn
}

# OIDC Identity Provider for Keycloak
resource "aws_iam_openid_connect_provider" "keycloak" {
  url = "https://your-keycloak-domain/auth/realms/your-realm"

  client_id_list = [
    "jenkins-client-id"  # Replace with your Jenkins OIDC client ID
  ]

  thumbprint_list = [
    "YOUR_KEYCLOAK_THUMBPRINT"  # Replace with your Keycloak server's SSL certificate thumbprint
  ]
}

# IAM Policy for Jenkins web identity role
data "aws_iam_policy_document" "jenkins_web_identity_policy" {
  statement {
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket"
    ]
    resources = [
      aws_s3_bucket.etcd_backups.arn,
      "${aws_s3_bucket.etcd_backups.arn}/*"
    ]
  }
  
  statement {
    effect = "Allow"
    actions = [
      "route53:ChangeResourceRecordSets",
      "route53:List*",
      "route53:Get*"
    ]
    resources = ["*"]
  }
  
  statement {
    effect = "Allow"
    actions = [
      "ses:SendEmail",
      "ses:SendRawEmail"
    ]
    resources = ["*"]
  }
}

# IAM Role for Jenkins web identity
data "aws_iam_policy_document" "jenkins_web_identity_assume_role_policy" {
  statement {
    effect = "Allow"
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.keycloak.arn]
    }
    actions = ["sts:AssumeRoleWithWebIdentity"]
    condition {
      test     = "StringEquals"
      variable = "${aws_iam_openid_connect_provider.keycloak.url}:aud"
      values   = ["jenkins-client-id"]  # Must match your Jenkins OIDC client ID
    }
    condition {
      test     = "StringLike"
      variable = "${aws_iam_openid_connect_provider.keycloak.url}:sub"
      values   = ["*:jenkins:*"]  # Adjust based on your Keycloak user mapping
    }
  }
}

resource "aws_iam_role" "jenkins_web_identity_role" {
  name               = "jenkins-web-identity-role-${var.project_id}"
  assume_role_policy = data.aws_iam_policy_document.jenkins_web_identity_assume_role_policy.json
}

resource "aws_iam_role_policy" "jenkins_web_identity_policy" {
  name   = "jenkins-web-identity-policy-${var.project_id}"
  role   = aws_iam_role.jenkins_web_identity_role.id
  policy = data.aws_iam_policy_document.jenkins_web_identity_policy.json
}


