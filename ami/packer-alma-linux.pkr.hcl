packer {
  required_plugins {
    amazon = {
      source  = "github.com/hashicorp/amazon"
      version = "~> 1"
    }
  }
}

variable "aws_region" {
  type        = string
  description = "AWS region to build the AMI in"
  default     = "us-east-1"
}

variable "kms_key_id" {
  type        = string
  description = "KMS key ID for AMI encryption (must allow all accounts in organization)"
  sensitive   = true
}

variable "target_accounts" {
  type        = list(string)
  description = "List of AWS account IDs to share the AMI with"
  default     = []
}

variable "ami_name_prefix" {
  type        = string
  description = "Prefix for the AMI name"
  default     = "alma-linux-provisioned"
}

variable "instance_type" {
  type        = string
  description = "EC2 instance type for building the AMI"
  default     = "t3.medium"
}

variable "ssh_username" {
  type        = string
  description = "SSH username for Alma Linux"
  default     = "ec2-user"
}

variable "subnet_id" {
  type        = string
  description = "Subnet ID to launch the build instance in (optional)"
  default     = ""
}

variable "vpc_id" {
  type        = string
  description = "VPC ID to launch the build instance in (optional)"
  default     = ""
}

variable "security_group_ids" {
  type        = list(string)
  description = "Security group IDs for the build instance (optional)"
  default     = []
}

source "amazon-ebs" "alma_linux" {
  region        = var.aws_region
  # Use source_ami_filter to find latest Alma Linux 9 AMI
  source_ami_filter {
    filters = {
      name                = "almalinux-9-*-x86_64"
      architecture        = "x86_64"
      virtualization-type = "hvm"
      root-device-type    = "ebs"
    }
    most_recent = true
    owners      = ["792107900819"] # AlmaLinux OS Foundation
  }
  instance_type = var.instance_type
  ssh_username  = var.ssh_username

  # Network configuration (optional)
  subnet_id         = var.subnet_id != "" ? var.subnet_id : null
  vpc_id            = var.vpc_id != "" ? var.vpc_id : null
  security_group_ids = length(var.security_group_ids) > 0 ? var.security_group_ids : null

  # AMI configuration
  ami_name        = "${var.ami_name_prefix}-${formatdate("YYYY-MM-DD-hhmm", timestamp())}"
  ami_description = "Alma Linux AMI provisioned with Ansible"

  # Encryption configuration
  encrypt_boot = true
  kms_key_id   = var.kms_key_id

  # AMI sharing configuration
  ami_users = var.target_accounts

  # Tags
  tags = {
    Name        = "${var.ami_name_prefix}-${formatdate("YYYY-MM-DD-hhmm", timestamp())}"
    OS          = "AlmaLinux"
    Version     = "9"
    Provisioner = "Packer"
    Created     = formatdate("YYYY-MM-DD", timestamp())
  }

  # Launch block device mappings
  launch_block_device_mappings {
    device_name           = "/dev/sda1"
    volume_size           = 20
    volume_type           = "gp3"
    delete_on_termination = true
    encrypted             = true
    kms_key_id            = var.kms_key_id
  }
}

build {
  name = "alma-linux-ansible"

  sources = [
    "source.amazon-ebs.alma_linux"
  ]

  # Pre-provisioner: Install ansible-core
  provisioner "shell" {
    name = "install-ansible-core"
    inline = [
      "sudo dnf update -y",
      "sudo dnf install -y python3 python3-pip",
      "sudo pip3 install --upgrade pip",
      "sudo pip3 install ansible-core",
      "ansible --version"
    ]
  }

  # Provisioner: Run Ansible playbook
  provisioner "ansible-local" {
    name              = "ansible-provisioning"
    playbook_file     = "ansible/playbook.yml"
    extra_arguments   = ["-v"]
    galaxy_file       = "ansible/requirements.yml"
    galaxy_force      = true
    galaxy_command    = "ansible-galaxy install -r {{ .GalaxyFile }}"
    inventory_groups  = ["alma_linux"]
    inventory_entries = ["alma_linux ansible_connection=local"]
  }

  # Post-provisioner: Clean up
  provisioner "shell" {
    name = "cleanup"
    inline = [
      "sudo dnf clean all",
      "sudo rm -rf /tmp/*",
      "sudo rm -rf /var/tmp/*",
      "sudo rm -f /root/.ssh/authorized_keys",
      "sudo rm -f /home/${var.ssh_username}/.ssh/authorized_keys",
      "sudo cloud-init clean --logs",
      "sudo rm -rf /var/lib/cloud/instances/*",
      "sudo sync"
    ]
  }
}

