## Create fake A records for letsencrypt to work

resource "aws_route53_record" "argocd" {
  zone_id = aws_route53_zone.dns_zone.zone_id
  name    = "argocd"
  type    = "A"
  ttl     = 60
  records = ["10.0.0.1"] 
}

resource "aws_route53_record" "pihole" {
  zone_id = aws_route53_zone.dns_zone.zone_id
  name    = "pihole"
  type    = "A"
  ttl     = 60
  records = ["10.43.0.2"]
}

