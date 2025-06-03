variable "vault_addr" {
  type        = string
  description = "The address of the vault server"
}

variable "vault_token" {
  type        = string
  description = "The token to use for the vault server"
}

variable "gcp_project_id" {
  type        = string
  description = "The GCP project ID"
}

variable "gcp_region" {
  type        = string
  description = "The GCP region"
}

variable "kubernetes_host" {
  type        = string
  description = "The host of the Kubernetes cluster"
}

variable "k3s_config_path" {
  type        = string
  description = "The path to the k3s config"
}

variable "domain" {
  type        = string
  description = "The domain of the network"
}

variable "ingress_ip" {
  type        = string
  description = "The ingress IP of the network"
}

variable "pihole_password" {
  type        = string
  description = "The password for the pihole"
}

variable "network_cidr" {
  type        = string
  description = "The CIDR of the network"
}

variable "network_cidr_ipv6" {
  type        = string
  description = "The CIDR of the network"
}

variable "network_cidr_ipv6_v2" {
  type        = string
  description = "The CIDR of the network"
}