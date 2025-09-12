# EC2 AMI Updater for DDEV Instances

This solution provides automated AMI updates for EC2 instances running DDEV sites and GitHub runners, with persistent data storage using EBS volumes.

## Architecture Overview

- **EBS Volumes**: Persistent storage for Docker data, DDEV sites, and GitHub runner data
- **Blue-Green Deployment**: Zero-downtime updates by creating new instance before terminating old one
- **AMI Monitoring**: Automated detection of new Ubuntu 22.04 AMI releases
- **Data Migration**: Automatic data migration using EBS snapshots

## Components

### 1. Terraform Infrastructure (`terraform/`)
- **main.tf**: Core infrastructure including EC2 instance and EBS volumes
- **variables.tf**: Configuration variables
- **user_data.sh**: Instance initialization script

### 2. AMI Monitoring (`ami-monitor.py`)
- Python script for continuous AMI monitoring
- Automated instance recreation when new AMIs are available
- Comprehensive logging and error handling

### 3. Update Script (`update-instance.sh`)
- Bash script for manual instance updates
- Blue-green deployment process
- Dry-run capability for testing

## Quick Start

### 1. Deploy Infrastructure

```bash
cd terraform
terraform init
terraform plan
terraform apply
```

### 2. Configure AMI Monitoring

```bash
# Install dependencies
pip install boto3

# Run monitoring (check every hour)
python ami-monitor.py --instance-id i-1234567890abcdef0 --region us-east-1

# Or check once
python ami-monitor.py --instance-id i-1234567890abcdef0 --region us-east-1 --once
```

### 3. Manual Update

```bash
# Update instance with new AMI
./update-instance.sh --old-instance-id i-1234567890abcdef0 --region us-east-1

# Dry run to test
./update-instance.sh --old-instance-id i-1234567890abcdef0 --region us-east-1 --dry-run
```

## Data Persistence Strategy

### EBS Volume Configuration

| Volume | Device | Mount Point | Purpose | Size |
|--------|--------|-------------|---------|------|
| Docker Data | `/dev/sdf` | `/var/lib/docker` | Docker containers and images | 50GB |
| DDEV Sites | `/dev/sdg` | `/home/ubuntu/Sites` | DDEV project files | 100GB |
| GitHub Runner | `/dev/sdh` | `/home/ubuntu/actions-runner` | Runner configuration and cache | 20GB |

### Data Migration Process

1. **Snapshot Creation**: Create snapshots of all EBS volumes
2. **Volume Creation**: Create new volumes from snapshots
3. **Instance Launch**: Launch new instance with latest AMI
4. **Volume Attachment**: Attach new volumes to new instance
5. **Data Migration**: Mount volumes and restore data
6. **Load Balancer Update**: Update target groups with new instance
7. **Cleanup**: Terminate old instance

## Configuration

### Environment Variables

```bash
export AWS_REGION=us-east-1
export OLD_INSTANCE_ID=i-1234567890abcdef0
export DRY_RUN=false
```

### Terraform Variables

```hcl
variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.medium"
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
```

## Usage Examples

### 1. Continuous Monitoring

```bash
# Run as systemd service
sudo cp ami-monitor.service /etc/systemd/system/
sudo systemctl enable ami-monitor
sudo systemctl start ami-monitor
```

### 2. Scheduled Updates

```bash
# Add to crontab for daily checks
0 2 * * * /path/to/ami-monitor.py --instance-id i-1234567890abcdef0 --once
```

### 3. Load Balancer Integration

```bash
# Update ALB target groups
aws elbv2 register-targets \
    --target-group-arn arn:aws:elasticloadbalancing:us-east-1:123456789012:targetgroup/ddev-tg/1234567890123456 \
    --targets Id=i-new-instance-id,Port=8001
```

## Monitoring and Logging

### Log Files

- **AMI Monitor**: `/var/log/ami-updater.log`
- **User Data**: `/var/log/user-data.log`
- **DDEV Sites**: `/home/ubuntu/ddev-manage.sh logs <site-name>`

### Health Checks

```bash
# Check instance health
/home/ubuntu/health-check.sh

# Check DDEV sites status
/home/ubuntu/ddev-manage.sh status

# View system logs
journalctl -u ami-monitor
```

## Troubleshooting

### Common Issues

1. **Volume Attachment Fails**
   - Check instance type supports the number of volumes
   - Verify volume is in same AZ as instance

2. **DDEV Sites Not Starting**
   - Check volume mount points
   - Verify file permissions
   - Check Docker service status

3. **AMI Update Fails**
   - Check AWS permissions
   - Verify instance is in running state
   - Check snapshot creation status

### Debug Commands

```bash
# Check volume status
lsblk
df -h

# Check Docker status
systemctl status docker
docker ps

# Check DDEV status
ddev list
ddev logs

# Check AWS CLI
aws sts get-caller-identity
aws ec2 describe-instances --instance-ids i-1234567890abcdef0
```

## Security Considerations

- **EBS Encryption**: All volumes are encrypted at rest
- **IAM Permissions**: Minimal required permissions for EC2 and EBS operations
- **Network Security**: Security groups restrict access to necessary ports only
- **Data Backup**: Regular snapshots provide data backup and recovery

## Cost Optimization

- **EBS Volumes**: Use GP3 for better price/performance
- **Instance Types**: Choose appropriate instance type for workload
- **Snapshot Lifecycle**: Implement snapshot lifecycle policies
- **Monitoring**: Use CloudWatch for cost monitoring

## Best Practices

1. **Test Updates**: Always test updates in non-production environment
2. **Backup Data**: Create snapshots before major updates
3. **Monitor Logs**: Regularly check logs for errors
4. **Update Dependencies**: Keep Python packages and AWS CLI updated
5. **Document Changes**: Maintain documentation of configuration changes

## Support

For issues and questions:
1. Check logs in `/var/log/ami-updater.log`
2. Review AWS CloudTrail for API calls
3. Check instance system logs
4. Verify network connectivity and permissions
