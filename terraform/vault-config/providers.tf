terraform {
  required_providers {
    vault = {
      source  = "hashicorp/vault"
      version = "~> 3.0"
    }
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.0"
    }
  }
}

provider "kubernetes" {
  config_path = var.k3s_config_path
}

provider "vault" {
  address = var.vault_addr
  token   = var.vault_token
}

provider "google" {
  project = var.gcp_project_id
  region  = var.gcp_region
}