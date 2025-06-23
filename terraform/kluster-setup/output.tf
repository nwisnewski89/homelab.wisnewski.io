output "pihole_password" {
  value     = random_password.pihole_password.result
  sensitive = true
}
