#!/bin/bash
# Script to update EC2 instance with new Ubuntu 22.04 AMI
# This script handles the blue-green deployment process

set -e

# Configuration
REGION="${AWS_REGION:-us-east-1}"
OLD_INSTANCE_ID="${OLD_INSTANCE_ID:-}"
NEW_INSTANCE_ID="${NEW_INSTANCE_ID:-}"
DRY_RUN="${DRY_RUN:-false}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if AWS CLI is installed and configured
check_aws_cli() {
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI is not installed"
        exit 1
    fi
    
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS CLI is not configured or credentials are invalid"
        exit 1
    fi
    
    log_info "AWS CLI is configured"
}

# Get latest Ubuntu 22.04 AMI
get_latest_ami() {
    log_info "Getting latest Ubuntu 22.04 AMI..."
    
    AMI_ID=$(aws ec2 describe-images \
        --region "$REGION" \
        --filters \
            "Name=name,Values=ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-*" \
            "Name=architecture,Values=x86_64" \
            "Name=virtualization-type,Values=hvm" \
            "Name=state,Values=available" \
            "Name=owner-id,Values=099720109477" \
        --owners "099720109477" \
        --query 'Images | sort_by(@, &CreationDate) | [-1].ImageId' \
        --output text)
    
    if [ -z "$AMI_ID" ] || [ "$AMI_ID" = "None" ]; then
        log_error "Failed to get latest Ubuntu 22.04 AMI"
        exit 1
    fi
    
    log_info "Latest AMI: $AMI_ID"
    echo "$AMI_ID"
}

# Get current instance details
get_instance_details() {
    local instance_id=$1
    
    log_info "Getting instance details for $instance_id..."
    
    aws ec2 describe-instances \
        --region "$REGION" \
        --instance-ids "$instance_id" \
        --query 'Reservations[0].Instances[0]' \
        --output json
}

# Get instance volumes
get_instance_volumes() {
    local instance_id=$1
    
    log_info "Getting volumes for instance $instance_id..."
    
    aws ec2 describe-instances \
        --region "$REGION" \
        --instance-ids "$instance_id" \
        --query 'Reservations[0].Instances[0].BlockDeviceMappings[?Ebs.VolumeId != null].Ebs.VolumeId' \
        --output text
}

# Create snapshot of volumes
create_volume_snapshots() {
    local instance_id=$1
    local snapshot_ids=()
    
    log_info "Creating snapshots of volumes for instance $instance_id..."
    
    # Get volumes
    local volumes
    volumes=$(get_instance_volumes "$instance_id")
    
    for volume_id in $volumes; do
        log_info "Creating snapshot of volume $volume_id..."
        
        if [ "$DRY_RUN" = "true" ]; then
            log_info "DRY RUN: Would create snapshot of $volume_id"
            snapshot_ids+=("snap-dryrun-$(date +%s)")
        else
            local snapshot_id
            snapshot_id=$(aws ec2 create-snapshot \
                --region "$REGION" \
                --volume-id "$volume_id" \
                --description "Snapshot before AMI update - $(date)" \
                --tag-specifications 'ResourceType=snapshot,Tags=[{Key=Name,Value=pre-update-snapshot},{Key=InstanceId,Value='$instance_id'}]' \
                --query 'SnapshotId' \
                --output text)
            
            snapshot_ids+=("$snapshot_id")
            log_info "Created snapshot: $snapshot_id"
        fi
    done
    
    echo "${snapshot_ids[@]}"
}

# Wait for snapshots to complete
wait_for_snapshots() {
    local snapshot_ids=("$@")
    
    log_info "Waiting for snapshots to complete..."
    
    for snapshot_id in "${snapshot_ids[@]}"; do
        if [ "$snapshot_id" = "snap-dryrun-"* ]; then
            log_info "DRY RUN: Skipping snapshot wait for $snapshot_id"
            continue
        fi
        
        log_info "Waiting for snapshot $snapshot_id..."
        aws ec2 wait snapshot-completed \
            --region "$REGION" \
            --snapshot-ids "$snapshot_id"
        
        log_info "Snapshot $snapshot_id completed"
    done
}

# Create volumes from snapshots
create_volumes_from_snapshots() {
    local snapshot_ids=("$@")
    local volume_ids=()
    
    log_info "Creating volumes from snapshots..."
    
    # Get availability zone
    local az
    az=$(aws ec2 describe-instances \
        --region "$REGION" \
        --instance-ids "$OLD_INSTANCE_ID" \
        --query 'Reservations[0].Instances[0].Placement.AvailabilityZone' \
        --output text)
    
    for snapshot_id in "${snapshot_ids[@]}"; do
        if [ "$snapshot_id" = "snap-dryrun-"* ]; then
            log_info "DRY RUN: Would create volume from $snapshot_id"
            volume_ids+=("vol-dryrun-$(date +%s)")
            continue
        fi
        
        log_info "Creating volume from snapshot $snapshot_id..."
        
        local volume_id
        volume_id=$(aws ec2 create-volume \
            --region "$REGION" \
            --snapshot-id "$snapshot_id" \
            --availability-zone "$az" \
            --volume-type gp3 \
            --tag-specifications 'ResourceType=volume,Tags=[{Key=Name,Value=restored-volume},{Key=SnapshotId,Value='$snapshot_id'}]' \
            --query 'VolumeId' \
            --output text)
        
        volume_ids+=("$volume_id")
        log_info "Created volume: $volume_id"
    done
    
    echo "${volume_ids[@]}"
}

# Launch new instance
launch_new_instance() {
    local ami_id=$1
    local volume_ids=("$@")
    
    log_info "Launching new instance with AMI $ami_id..."
    
    # Get instance details
    local instance_details
    instance_details=$(get_instance_details "$OLD_INSTANCE_ID")
    
    # Extract configuration
    local instance_type
    instance_type=$(echo "$instance_details" | jq -r '.InstanceType')
    
    local security_groups
    security_groups=$(echo "$instance_details" | jq -r '.SecurityGroups[].GroupId' | tr '\n' ' ')
    
    local subnet_id
    subnet_id=$(echo "$instance_details" | jq -r '.SubnetId')
    
    local key_name
    key_name=$(echo "$instance_details" | jq -r '.KeyName // empty')
    
    local iam_profile
    iam_profile=$(echo "$instance_details" | jq -r '.IamInstanceProfile.Arn // empty')
    
    # Create user data script
    local user_data
    user_data=$(cat << 'EOF'
#!/bin/bash
# User data for new instance

# Update system
apt-get update -y
apt-get install -y git curl wget docker.io docker-compose-v2 awscli jq

# Start and enable Docker
systemctl start docker
systemctl enable docker
usermod -a -G docker ubuntu

# Install AWS SSM agent
snap install amazon-ssm-agent --classic || apt-get install -y amazon-ssm-agent
systemctl enable snap.amazon-ssm-agent.amazon-ssm-agent.service || systemctl enable amazon-ssm-agent
systemctl start snap.amazon-ssm-agent.amazon-ssm-agent.service || systemctl start amazon-ssm-agent

# Create mount points
mkdir -p /var/lib/docker
mkdir -p /home/ubuntu/Sites
mkdir -p /home/ubuntu/actions-runner

# Wait for volumes to be available
sleep 30

# Get instance ID
INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)

# Function to setup volume
setup_volume() {
    local device=$1
    local mount_point=$2
    local volume_name=$3
    
    echo "Setting up $volume_name volume..."
    
    # Wait for device to be available
    while [ ! -e $device ]; do
        echo "Waiting for $device to be available..."
        sleep 5
    done
    
    # Mount volume
    mount $device $mount_point
    echo "$device $mount_point ext4 defaults,nofail 0 2" >> /etc/fstab
    
    # Set proper ownership
    chown -R ubuntu:ubuntu $mount_point
    
    echo "$volume_name volume setup completed"
}

# Setup volumes (assuming they're already formatted)
setup_volume "/dev/sdf" "/var/lib/docker" "Docker data"
setup_volume "/dev/sdg" "/home/ubuntu/Sites" "DDEV sites"
setup_volume "/dev/sdh" "/home/ubuntu/actions-runner" "GitHub runner"

# Install DDEV
curl -fsSL https://raw.githubusercontent.com/ddev/ddev/master/scripts/install_ddev.sh | bash

# Create startup script for DDEV sites
cat > /home/ubuntu/start-ddev-sites.sh << 'SCRIPT_EOF'
#!/bin/bash
# Start all DDEV sites

echo "Starting DDEV sites..."

cd /home/ubuntu/Sites
for site in */; do
    if [ -d "$site" ] && [ -f "$site/.ddev/config.yaml" ]; then
        echo "Starting DDEV site: $site"
        cd "$site"
        ddev start
        cd ..
    fi
done

echo "All DDEV sites started"
SCRIPT_EOF

chmod +x /home/ubuntu/start-ddev-sites.sh

# Start DDEV sites
/home/ubuntu/start-ddev-sites.sh

echo "Instance setup completed at $(date)"
EOF
)
    
    # Launch instance
    local new_instance_id
    if [ "$DRY_RUN" = "true" ]; then
        log_info "DRY RUN: Would launch new instance"
        new_instance_id="i-dryrun-$(date +%s)"
    else
        new_instance_id=$(aws ec2 run-instances \
            --region "$REGION" \
            --image-id "$ami_id" \
            --instance-type "$instance_type" \
            --security-group-ids $security_groups \
            --subnet-id "$subnet_id" \
            ${key_name:+--key-name "$key_name"} \
            ${iam_profile:+--iam-instance-profile Arn="$iam_profile"} \
            --user-data "$user_data" \
            --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=ddev-instance-updated},{Key=Purpose,Value=DDEV QA Environment},{Key=Environment,Value=QA}]' \
            --query 'Instances[0].InstanceId' \
            --output text)
        
        log_info "Launched new instance: $new_instance_id"
    fi
    
    echo "$new_instance_id"
}

# Attach volumes to new instance
attach_volumes() {
    local instance_id=$1
    local volume_ids=("$@")
    
    log_info "Attaching volumes to instance $instance_id..."
    
    local devices=("/dev/sdf" "/dev/sdg" "/dev/sdh")
    
    for i in "${!volume_ids[@]}"; do
        local volume_id="${volume_ids[$i]}"
        local device="${devices[$i]}"
        
        if [ "$volume_id" = "vol-dryrun-"* ]; then
            log_info "DRY RUN: Would attach $volume_id to $instance_id as $device"
            continue
        fi
        
        log_info "Attaching volume $volume_id to $instance_id as $device..."
        
        if [ "$DRY_RUN" = "true" ]; then
            log_info "DRY RUN: Would attach $volume_id to $instance_id as $device"
        else
            aws ec2 attach-volume \
                --region "$REGION" \
                --volume-id "$volume_id" \
                --instance-id "$instance_id" \
                --device "$device"
            
            log_info "Attached volume $volume_id to $instance_id as $device"
        fi
    done
}

# Wait for instance to be running
wait_for_instance() {
    local instance_id=$1
    
    log_info "Waiting for instance $instance_id to be running..."
    
    if [ "$DRY_RUN" = "true" ]; then
        log_info "DRY RUN: Skipping instance wait"
        return
    fi
    
    aws ec2 wait instance-running \
        --region "$REGION" \
        --instance-ids "$instance_id"
    
    log_info "Instance $instance_id is running"
}

# Update load balancer targets (placeholder)
update_load_balancer() {
    local new_instance_id=$1
    
    log_info "Updating load balancer targets with new instance $new_instance_id..."
    
    # This would need to be customized based on your specific load balancer setup
    # For now, just log the new instance ID
    log_info "New instance $new_instance_id is ready for load balancer configuration"
    
    # Example for ALB target groups:
    # aws elbv2 register-targets \
    #     --region "$REGION" \
    #     --target-group-arn "$TARGET_GROUP_ARN" \
    #     --targets Id="$new_instance_id",Port=8001
}

# Terminate old instance
terminate_old_instance() {
    local instance_id=$1
    
    log_info "Terminating old instance $instance_id..."
    
    if [ "$DRY_RUN" = "true" ]; then
        log_info "DRY RUN: Would terminate instance $instance_id"
        return
    fi
    
    aws ec2 terminate-instances \
        --region "$REGION" \
        --instance-ids "$instance_id"
    
    log_info "Terminated old instance $instance_id"
}

# Main update process
main() {
    log_info "Starting EC2 instance update process"
    
    # Check prerequisites
    check_aws_cli
    
    if [ -z "$OLD_INSTANCE_ID" ]; then
        log_error "OLD_INSTANCE_ID is required"
        exit 1
    fi
    
    # Get latest AMI
    local latest_ami
    latest_ami=$(get_latest_ami)
    
    # Get current instance AMI
    local current_ami
    current_ami=$(aws ec2 describe-instances \
        --region "$REGION" \
        --instance-ids "$OLD_INSTANCE_ID" \
        --query 'Reservations[0].Instances[0].ImageId' \
        --output text)
    
    if [ "$current_ami" = "$latest_ami" ]; then
        log_info "Instance is already using the latest AMI ($latest_ami)"
        exit 0
    fi
    
    log_info "Current AMI: $current_ami"
    log_info "Latest AMI: $latest_ami"
    
    # Create snapshots
    local snapshot_ids
    read -ra snapshot_ids <<< "$(create_volume_snapshots "$OLD_INSTANCE_ID")"
    
    # Wait for snapshots
    wait_for_snapshots "${snapshot_ids[@]}"
    
    # Create volumes from snapshots
    local volume_ids
    read -ra volume_ids <<< "$(create_volumes_from_snapshots "${snapshot_ids[@]}")"
    
    # Launch new instance
    local new_instance_id
    new_instance_id=$(launch_new_instance "$latest_ami" "${volume_ids[@]}")
    
    # Attach volumes
    attach_volumes "$new_instance_id" "${volume_ids[@]}"
    
    # Wait for instance
    wait_for_instance "$new_instance_id"
    
    # Update load balancer
    update_load_balancer "$new_instance_id"
    
    # Terminate old instance
    terminate_old_instance "$OLD_INSTANCE_ID"
    
    log_info "Update process completed successfully"
    log_info "New instance ID: $new_instance_id"
}

# Show usage
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --old-instance-id ID    Old instance ID to replace"
    echo "  --new-instance-id ID    New instance ID (optional, will be created)"
    echo "  --region REGION         AWS region (default: us-east-1)"
    echo "  --dry-run               Perform a dry run without making changes"
    echo "  --help                  Show this help message"
    echo ""
    echo "Environment variables:"
    echo "  OLD_INSTANCE_ID         Old instance ID to replace"
    echo "  NEW_INSTANCE_ID         New instance ID (optional)"
    echo "  AWS_REGION              AWS region (default: us-east-1)"
    echo "  DRY_RUN                 Set to 'true' for dry run"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --old-instance-id)
            OLD_INSTANCE_ID="$2"
            shift 2
            ;;
        --new-instance-id)
            NEW_INSTANCE_ID="$2"
            shift 2
            ;;
        --region)
            REGION="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN="true"
            shift
            ;;
        --help)
            usage
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Run main function
main
