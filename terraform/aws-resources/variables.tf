variable "aws_region" {
  type    = string
  default = ""
}

variable "google_region" {
  type    = string
  default = ""
}

variable "gcp_project_id" {
  type    = string
  default = ""
}

variable "project_id" {
  type    = string
  default = ""
}

variable "route53_zone_name" {
  type    = string
  default = ""
}

variable "cross_account_s3_bucket_name" {
  type        = string
  default     = ""
  description = "Name for the cross-account S3 bucket. Leave empty to disable this resource."
}

variable "cross_account_canonical_user_id" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Canonical user ID of the other AWS account (64-char hex). Get it with: aws s3api list-buckets --query Owner.ID --output text"
}
