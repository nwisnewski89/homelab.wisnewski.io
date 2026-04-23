output "etcd_backups_access_key" {
  value     = aws_iam_access_key.etcd_backups_access_key.id
  sensitive = true
}

output "etcd_backups_secret_key" {
  value     = aws_iam_access_key.etcd_backups_access_key.secret
  sensitive = true
}

output "etcd_backups_bucket_name" {
  value = aws_s3_bucket.etcd_backups.bucket
}

output "dns_soa_record" {
  value = aws_route53_zone.dns_zone.name_servers
}

output "dns_zone_id" {
  value = aws_route53_zone.dns_zone.zone_id
}

output "cross_account_bucket_name" {
  value       = length(aws_s3_bucket.cross_account) > 0 ? aws_s3_bucket.cross_account[0].id : null
  description = "Name of the S3 bucket shared via ACL with another account."
}