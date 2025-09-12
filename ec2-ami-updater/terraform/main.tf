# Terraform configuration for DDEV instance with persistent EBS volumes

terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# Data source for latest Ubuntu 22.04 AMI
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-*"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# VPC and networking
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# Security group for DDEV instance
resource "aws_security_group" "ddev_sg" {
  name_prefix = "ddev-instance-"
  vpc_id      = data.aws_vpc.default.id

  # SSH access
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # HTTP access for DDEV sites
  ingress {
    from_port   = 8000
    to_port     = 8010
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # All outbound traffic
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "ddev-instance-sg"
  }
}

# IAM role for EC2 instance
resource "aws_iam_role" "ddev_instance_role" {
  name = "ddev-instance-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })
}

# IAM policy for EC2 instance
resource "aws_iam_role_policy" "ddev_instance_policy" {
  name = "ddev-instance-policy"
  role = aws_iam_role.ddev_instance_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ec2:DescribeInstances",
          "ec2:DescribeImages",
          "ec2:CreateVolume",
          "ec2:AttachVolume",
          "ec2:DetachVolume",
          "ec2:DeleteVolume",
          "ec2:DescribeVolumes",
          "ec2:ModifyVolumeAttribute",
          "ssm:UpdateInstanceInformation",
          "ssmmessages:CreateControlChannel",
          "ssmmessages:CreateDataChannel",
          "ssmmessages:OpenControlChannel",
          "ssmmessages:OpenDataChannel"
        ]
        Resource = "*"
      }
    ]
  })
}

# Instance profile
resource "aws_iam_instance_profile" "ddev_instance_profile" {
  name = "ddev-instance-profile"
  role = aws_iam_role.ddev_instance_role.name
}

# EBS volumes for persistent data
resource "aws_ebs_volume" "docker_data" {
  availability_zone = data.aws_subnets.default.ids[0]
  size              = var.docker_volume_size
  type              = "gp3"
  encrypted         = true

  tags = {
    Name        = "ddev-docker-data"
    Purpose     = "Docker persistent data"
    Environment = "QA"
  }
}

resource "aws_ebs_volume" "ddev_sites" {
  availability_zone = data.aws_subnets.default.ids[0]
  size              = var.sites_volume_size
  type              = "gp3"
  encrypted         = true

  tags = {
    Name        = "ddev-sites-data"
    Purpose     = "DDEV sites persistent data"
    Environment = "QA"
  }
}

resource "aws_ebs_volume" "github_runner" {
  availability_zone = data.aws_subnets.default.ids[0]
  size              = var.runner_volume_size
  type              = "gp3"
  encrypted         = true

  tags = {
    Name        = "ddev-github-runner"
    Purpose     = "GitHub runner persistent data"
    Environment = "QA"
  }
}

# User data script
locals {
  user_data = base64encode(templatefile("${path.module}/user_data.sh", {
    docker_volume_id = aws_ebs_volume.docker_data.id
    sites_volume_id  = aws_ebs_volume.ddev_sites.id
    runner_volume_id = aws_ebs_volume.github_runner.id
  }))
}

# EC2 instance
resource "aws_instance" "ddev_instance" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  key_name               = var.key_name
  vpc_security_group_ids = [aws_security_group.ddev_sg.id]
  iam_instance_profile   = aws_iam_instance_profile.ddev_instance_profile.name
  user_data              = local.user_data

  # Root volume
  root_block_device {
    volume_type = "gp3"
    volume_size = 20
    encrypted   = true
  }

  tags = {
    Name        = "ddev-instance"
    Purpose     = "DDEV QA Environment"
    Environment = "QA"
    AMI         = data.aws_ami.ubuntu.id
  }

  lifecycle {
    create_before_destroy = true
  }
}

# Attach EBS volumes
resource "aws_volume_attachment" "docker_data" {
  device_name = "/dev/sdf"
  volume_id   = aws_ebs_volume.docker_data.id
  instance_id = aws_instance.ddev_instance.id
}

resource "aws_volume_attachment" "ddev_sites" {
  device_name = "/dev/sdg"
  volume_id   = aws_ebs_volume.ddev_sites.id
  instance_id = aws_instance.ddev_instance.id
}

resource "aws_volume_attachment" "github_runner" {
  device_name = "/dev/sdh"
  volume_id   = aws_ebs_volume.github_runner.id
  instance_id = aws_instance.ddev_instance.id
}

# Outputs
output "instance_id" {
  description = "ID of the EC2 instance"
  value       = aws_instance.ddev_instance.id
}

output "instance_public_ip" {
  description = "Public IP address of the EC2 instance"
  value       = aws_instance.ddev_instance.public_ip
}

output "instance_private_ip" {
  description = "Private IP address of the EC2 instance"
  value       = aws_instance.ddev_instance.private_ip
}

output "ami_id" {
  description = "AMI ID used for the instance"
  value       = data.aws_ami.ubuntu.id
}

output "volume_ids" {
  description = "IDs of the EBS volumes"
  value = {
    docker_data = aws_ebs_volume.docker_data.id
    ddev_sites  = aws_ebs_volume.ddev_sites.id
    github_runner = aws_ebs_volume.github_runner.id
  }
}
