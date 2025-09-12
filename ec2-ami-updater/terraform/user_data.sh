#!/bin/bash
# User data script for DDEV instance with persistent EBS volumes
# This script sets up the instance with persistent data storage

set -e

# Log everything
exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1

echo "Starting user data script at $(date)"

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
echo "Waiting for EBS volumes to be available..."
sleep 30

# Get instance ID
INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)
echo "Instance ID: $INSTANCE_ID"

# Get volume IDs from Terraform variables
DOCKER_VOLUME_ID="${docker_volume_id}"
SITES_VOLUME_ID="${sites_volume_id}"
RUNNER_VOLUME_ID="${runner_volume_id}"

echo "Docker volume ID: $DOCKER_VOLUME_ID"
echo "Sites volume ID: $SITES_VOLUME_ID"
echo "Runner volume ID: $RUNNER_VOLUME_ID"

# Function to setup volume
setup_volume() {
    local volume_id=$1
    local device=$2
    local mount_point=$3
    local volume_name=$4
    
    echo "Setting up $volume_name volume..."
    
    # Wait for device to be available
    while [ ! -e $device ]; do
        echo "Waiting for $device to be available..."
        sleep 5
    done
    
    # Check if volume is already formatted
    if ! blkid $device >/dev/null 2>&1; then
        echo "Formatting $device..."
        mkfs.ext4 $device
    else
        echo "$device is already formatted"
    fi
    
    # Mount volume
    mount $device $mount_point
    echo "$device $mount_point ext4 defaults,nofail 0 2" >> /etc/fstab
    
    # Set proper ownership
    chown -R ubuntu:ubuntu $mount_point
    
    echo "$volume_name volume setup completed"
}

# Setup volumes
setup_volume "$DOCKER_VOLUME_ID" "/dev/sdf" "/var/lib/docker" "Docker data"
setup_volume "$SITES_VOLUME_ID" "/dev/sdg" "/home/ubuntu/Sites" "DDEV sites"
setup_volume "$RUNNER_VOLUME_ID" "/dev/sdh" "/home/ubuntu/actions-runner" "GitHub runner"

# Stop Docker to move data to EBS volume
systemctl stop docker

# Move existing Docker data to EBS volume (if any)
if [ -d "/var/lib/docker" ] && [ "$(ls -A /var/lib/docker)" ]; then
    echo "Moving existing Docker data to EBS volume..."
    # This would only happen if there's existing data
fi

# Start Docker
systemctl start docker

# Install DDEV
echo "Installing DDEV..."
curl -fsSL https://raw.githubusercontent.com/ddev/ddev/master/scripts/install_ddev.sh | bash

# Create startup script for DDEV sites
cat > /home/ubuntu/start-ddev-sites.sh << 'EOF'
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
EOF

chmod +x /home/ubuntu/start-ddev-sites.sh

# Create DDEV management script
cat > /home/ubuntu/ddev-manage.sh << 'EOF'
#!/bin/bash
# DDEV management script

case "$1" in
    start)
        /home/ubuntu/start-ddev-sites.sh
        ;;
    stop)
        cd /home/ubuntu/Sites
        for site in */; do
            if [ -d "$site" ]; then
                echo "Stopping DDEV site: $site"
                cd "$site"
                ddev stop
                cd ..
            fi
        done
        ;;
    restart)
        $0 stop
        sleep 5
        $0 start
        ;;
    status)
        ddev list
        ;;
    logs)
        if [ -n "$2" ]; then
            cd "/home/ubuntu/Sites/$2"
            ddev logs
        else
            echo "Usage: $0 logs <site-name>"
        fi
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs}"
        exit 1
        ;;
esac
EOF

chmod +x /home/ubuntu/ddev-manage.sh

# Create systemd service for DDEV sites
cat > /etc/systemd/system/ddev-sites.service << 'EOF'
[Unit]
Description=DDEV Sites
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
User=ubuntu
WorkingDirectory=/home/ubuntu
ExecStart=/home/ubuntu/start-ddev-sites.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

systemctl enable ddev-sites.service

# Start DDEV sites
echo "Starting DDEV sites..."
/home/ubuntu/start-ddev-sites.sh

# Create README
cat > /home/ubuntu/README.md << 'EOF'
# DDEV Instance with Persistent Data

This instance has been set up with persistent EBS volumes for:
- Docker data: /var/lib/docker
- DDEV sites: /home/ubuntu/Sites  
- GitHub runner: /home/ubuntu/actions-runner

## Management Commands
- Start all sites: /home/ubuntu/ddev-manage.sh start
- Stop all sites: /home/ubuntu/ddev-manage.sh stop
- Restart all sites: /home/ubuntu/ddev-manage.sh restart
- Check site status: /home/ubuntu/ddev-manage.sh status
- View site logs: /home/ubuntu/ddev-manage.sh logs <site-name>

## Data Persistence
All data is stored on EBS volumes and will persist across instance recreations.

## Volume Information
- Docker data: /dev/sdf -> /var/lib/docker
- DDEV sites: /dev/sdg -> /home/ubuntu/Sites
- GitHub runner: /dev/sdh -> /home/ubuntu/actions-runner

## Adding New Sites
1. Create directory: mkdir -p /home/ubuntu/Sites/new-site
2. Navigate to directory: cd /home/ubuntu/Sites/new-site
3. Configure DDEV: ddev config --project-name=new-site --project-type=php
4. Start site: ddev start

## System Information
- OS: Ubuntu 22.04 LTS
- Docker: Pre-installed and configured
- DDEV: Pre-installed and configured
- Persistent storage: EBS volumes
EOF

# Create health check script
cat > /home/ubuntu/health-check.sh << 'EOF'
#!/bin/bash
# Health check script for load balancer

# Check if Docker is running
if ! systemctl is-active --quiet docker; then
    echo "Docker is not running"
    exit 1
fi

# Check if DDEV sites are running
cd /home/ubuntu/Sites
for site in */; do
    if [ -d "$site" ]; then
        cd "$site"
        if ! ddev describe --json | jq -e '.status == "running"' >/dev/null 2>&1; then
            echo "Site $site is not running"
            exit 1
        fi
        cd ..
    fi
done

echo "All systems healthy"
exit 0
EOF

chmod +x /home/ubuntu/health-check.sh

# Set up log rotation
cat > /etc/logrotate.d/ddev << 'EOF'
/var/log/user-data.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    create 644 root root
}
EOF

echo "User data script completed at $(date)"
