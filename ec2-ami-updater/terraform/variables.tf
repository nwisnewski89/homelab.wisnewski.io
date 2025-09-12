# Variables for DDEV instance Terraform configuration

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.medium"
}

variable "key_name" {
  description = "Name of the AWS key pair"
  type        = string
  default     = ""
}

variable "docker_volume_size" {
  description = "Size of the Docker data volume in GB"
  type        = number
  default     = 50
}

variable "sites_volume_size" {
  description = "Size of the DDEV sites volume in GB"
  type        = number
  default     = 100
}

variable "runner_volume_size" {
  description = "Size of the GitHub runner volume in GB"
  type        = number
  default     = 20
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "qa"
}

variable "project_name" {
  description = "Project name for tagging"
  type        = string
  default     = "ddev"
}
