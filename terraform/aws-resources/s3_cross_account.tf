# S3 bucket with ACL granting access to a user in another AWS account.
#
# For ACL-based cross-account access you must use the other account's
# canonical user ID (a 64-char hex string). The other account can get it with:
#   aws s3api list-buckets --query Owner.ID --output text
#
# The other account must also grant their IAM user/role permission to use
# this bucket (e.g. s3:GetObject, s3:PutObject on the bucket ARN).

# Only create the bucket when a name and canonical ID are provided
resource "aws_s3_bucket" "cross_account" {
  count  = var.cross_account_s3_bucket_name != "" && var.cross_account_canonical_user_id != "" ? 1 : 0
  bucket = var.cross_account_s3_bucket_name

  tags = {
    Name = var.cross_account_s3_bucket_name
  }
}

# Allow ACLs on the bucket (required for cross-account ACL grants).
# BucketOwnerEnforced would disable ACLs.
resource "aws_s3_bucket_ownership_controls" "cross_account" {
  count  = length(aws_s3_bucket.cross_account)
  bucket = aws_s3_bucket.cross_account[0].id

  rule {
    object_ownership = "BucketOwnerPreferred"
  }
}

# ACL grant: give the other account READ + list on the bucket.
# Use FULL_CONTROL if they need write/delete as well.
resource "aws_s3_bucket_acl" "cross_account" {
  count  = length(aws_s3_bucket.cross_account)
  bucket = aws_s3_bucket.cross_account[0].id

  access_control_policy {
    grant {
      grantee {
        type = "CanonicalUser"
        id   = data.aws_canonical_user_id.current.id
      }
      permission = "FULL_CONTROL"
    }
    grant {
      grantee {
        type = "CanonicalUser"
        id   = var.cross_account_canonical_user_id
      }
      permission = "READ" # or "FULL_CONTROL" for read/write/delete
    }

    owner {
      id = data.aws_canonical_user_id.current.id
    }
  }

  depends_on = [aws_s3_bucket_ownership_controls.cross_account]
}

data "aws_canonical_user_id" "current" {}

resource "aws_s3_bucket_versioning" "cross_account" {
  count  = length(aws_s3_bucket.cross_account)
  bucket = aws_s3_bucket.cross_account[0].id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "cross_account" {
  count  = length(aws_s3_bucket.cross_account)
  bucket = aws_s3_bucket.cross_account[0].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "cross_account" {
  count  = length(aws_s3_bucket.cross_account)
  bucket = aws_s3_bucket.cross_account[0].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

