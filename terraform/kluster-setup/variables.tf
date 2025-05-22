variable "aws_access_key_id" {
  type = string
}

variable "aws_secret_access_key" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "gcp_project_id" {
  type = string
}

variable "gcp_region" {
  type = string
}

variable "k3s_config_path" {
  type = string
}

variable "argocd_domain" {
  type = string
}

variable "metallb_ip_pool" {
  type = string
}

variable "letsencrypt_email" {
  type = string
}

# variable "github_username" {
#   description = "GitHub username for container registry authentication"
#   type        = string
#   sensitive   = true
# }

# variable "github_pat" {
#   description = "GitHub Personal Access Token for container registry authentication"
#   type        = string
#   sensitive   = true
# }
