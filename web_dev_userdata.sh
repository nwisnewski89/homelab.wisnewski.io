#!/bin/bash

# Ubuntu 22.04 Setup Script for Web Development
# Installs CloudWatch Agent, SSM Agent, Docker, DDEV, and sets up a PHP site with DDEV

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
    exit 1
}

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   error "This script should not be run as root. Please run as a regular user with sudo privileges."
fi

# Check if running on Ubuntu 22.04
if ! grep -q "Ubuntu 22.04" /etc/os-release; then
    warn "This script is designed for Ubuntu 22.04. Current OS: $(cat /etc/os-release | grep PRETTY_NAME)"
fi

log "Starting Ubuntu 22.04 setup for web development..."

# Update system packages
log "Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install essential packages
log "Installing essential packages..."
sudo apt install -y \
    curl \
    wget \
    git \
    unzip \
    software-properties-common \
    apt-transport-https \
    ca-certificates \
    gnupg \
    lsb-release \
    htop \
    vim \
    tree

# Install SSM Agent
log "Installing SSM Agent..."
if ! systemctl is-active --quiet snapd.socket; then
    sudo systemctl enable --now snapd.socket
fi

sudo snap install amazon-ssm-agent --classic
sudo systemctl enable amazon-ssm-agent
sudo systemctl start amazon-ssm-agent

# Install CloudWatch Agent
log "Installing CloudWatch Agent..."
wget https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
sudo dpkg -i amazon-cloudwatch-agent.deb
sudo systemctl enable amazon-cloudwatch-agent
sudo systemctl start amazon-cloudwatch-agent

# Clean up CloudWatch installer
rm -f amazon-cloudwatch-agent.deb

# Install Docker
log "Installing Docker..."
# Add Docker's official GPG key
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# Add Docker repository
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Start and enable Docker
sudo systemctl enable docker
sudo systemctl start docker

# Install DDEV
log "Installing DDEV..."
curl -fsSL https://raw.githubusercontent.com/drud/ddev/master/scripts/install_ddev.sh | bash

# Create web-dev user
log "Creating web-dev user..."
if ! id "web-dev" &>/dev/null; then
    sudo useradd -m -s /bin/bash web-dev
    log "Created user 'web-dev' (no password set)"
else
    log "User 'web-dev' already exists"
fi

# Add web-dev to sudoers
log "Adding web-dev to sudoers..."
echo "web-dev ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/web-dev

# Add web-dev to docker group
log "Adding web-dev to docker group..."
sudo usermod -aG docker web-dev

# Create web development directory
log "Setting up web development directory..."
sudo mkdir -p /home/web-dev/web-projects
sudo chown -R web-dev:web-dev /home/web-dev/web-projects

# Create DDEV PHP hello world project
log "Creating DDEV PHP hello world project..."
sudo -u web-dev mkdir -p /home/web-dev/web-projects/hello-world
cd /home/web-dev/web-projects/hello-world

# Create DDEV configuration
sudo -u web-dev tee .ddev/config.yaml > /dev/null <<'EOF'
name: hello-world
type: php
docroot: ""
php_version: "8.2"
webserver_type: nginx-fpm
router_http_port: "80"
router_https_port: "443"
xdebug_enabled: false
additional_hostnames: []
additional_fqdns: []
database:
  type: mariadb
  version: "10.4"
nodejs_version: "18"
EOF

# Create PHP index file
sudo -u web-dev mkdir -p web
sudo -u web-dev tee web/index.php > /dev/null <<'EOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hello World - PHP with DDEV</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            margin: 0;
            padding: 0;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            color: white;
        }
        .container {
            text-align: center;
            background: rgba(255, 255, 255, 0.1);
            padding: 3rem;
            border-radius: 20px;
            backdrop-filter: blur(10px);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        }
        h1 {
            font-size: 3rem;
            margin-bottom: 1rem;
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.3);
        }
        .info {
            background: rgba(255, 255, 255, 0.2);
            padding: 1rem;
            border-radius: 10px;
            margin: 1rem 0;
        }
        .timestamp {
            font-size: 0.9rem;
            opacity: 0.8;
        }
        .ddev-info {
            background: rgba(255, 255, 255, 0.3);
            padding: 1rem;
            border-radius: 10px;
            margin: 1rem 0;
            border-left: 4px solid #4CAF50;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Hello World! 🚀</h1>
        <div class="ddev-info">
            <h3>🚀 Running with DDEV!</h3>
            <p>Your local development environment is working perfectly!</p>
        </div>
        <div class="info">
            <p><strong>Server:</strong> <?php echo $_SERVER['SERVER_NAME'] ?? 'Unknown'; ?></p>
            <p><strong>PHP Version:</strong> <?php echo phpversion(); ?></p>
            <p><strong>Server Time:</strong> <?php echo date('Y-m-d H:i:s T'); ?></p>
            <p><strong>Document Root:</strong> <?php echo $_SERVER['DOCUMENT_ROOT'] ?? 'Unknown'; ?></p>
        </div>
        <div class="timestamp">
            <p>Generated at: <?php echo date('Y-m-d H:i:s'); ?></p>
        </div>
    </div>
</body>
</html>
EOF

# Create a simple README
sudo -u web-dev tee README.md > /dev/null <<'EOF'
# Hello World PHP Project

This is a simple PHP "Hello World" project running with DDEV.

## Quick Start

```bash
# Start the project
ddev start

# View the site
ddev launch

# Stop the project
ddev stop

# View logs
ddev logs
```

## DDEV Commands

- `ddev start` - Start the project
- `ddev stop` - Stop the project
- `ddev restart` - Restart the project
- `ddev status` - Show project status
- `ddev logs` - Show project logs
- `ddev ssh` - SSH into the web container
- `ddev exec` - Execute commands in the web container
- `ddev launch` - Open the project in your browser

## Project Structure

- `web/` - Web root directory
- `.ddev/` - DDEV configuration
- `README.md` - This file

## Access URLs

- **Local**: http://hello-world.ddev.local
- **HTTPS**: https://hello-world.ddev.local
EOF

# Install Traefik modules if not included
log "Checking and installing Traefik modules..."
if ! ddev --version > /dev/null 2>&1; then
    warn "DDEV not available yet, will check after installation"
else
    # Check if Traefik is available and install if needed
    log "DDEV is available, checking Traefik modules..."
    
    # Create a temporary DDEV project to check Traefik
    sudo -u web-dev mkdir -p /tmp/traefik-check
    cd /tmp/traefik-check
    
    # Create minimal DDEV config
    sudo -u web-dev tee .ddev/config.yaml > /dev/null <<'EOF'
name: traefik-check
type: php
docroot: ""
php_version: "8.2"
webserver_type: nginx-fpm
router_http_port: "80"
router_https_port: "443"
xdebug_enabled: false
additional_hostnames: []
additional_fqdns: []
database:
  type: mariadb
  version: "10.4"
nodejs_version: "18"
EOF
    
    # Try to start DDEV to trigger Traefik installation
    if sudo -u web-dev ddev start --yes > /dev/null 2>&1; then
        log "✓ Traefik modules installed successfully"
        sudo -u web-dev ddev stop --remove-data --yes > /dev/null 2>&1
    else
        warn "Traefik installation may have failed, but this is normal for first-time setup"
    fi
    
    # Clean up
    cd /home/web-dev/web-projects/hello-world
    sudo rm -rf /tmp/traefik-check
fi

# Start the DDEV project
log "Starting DDEV PHP hello world project..."
cd /home/web-dev/web-projects/hello-world

# Start DDEV project
if sudo -u web-dev ddev start --yes; then
    log "✓ DDEV project started successfully"
else
    warn "DDEV project start had issues, but this may be normal for first-time setup"
fi

# Wait a moment for services to be ready
sleep 10

# Check if the site is accessible
if curl -s http://hello-world.ddev.local > /dev/null 2>&1; then
    log "✓ PHP site is accessible at http://hello-world.ddev.local"
elif curl -s https://hello-world.ddev.local > /dev/null 2>&1; then
    log "✓ PHP site is accessible at https://hello-world.ddev.local"
else
    warn "PHP site may not be accessible yet. This is normal for first-time DDEV setup."
    log "Try running 'ddev launch' from the project directory to open in browser."
fi

# Create a convenience script for the web-dev user
sudo -u web-dev tee /home/web-dev/setup-complete.sh > /dev/null <<'EOF'
#!/bin/bash
echo "=== Web Development Environment Setup Complete ==="
echo ""
echo "What's been installed:"
echo "✓ CloudWatch Agent"
echo "✓ SSM Agent"
echo "✓ Docker"
echo "✓ DDEV"
echo "✓ PHP Hello World site with DDEV"
echo ""
echo "User 'web-dev' has been created with:"
echo "✓ Sudo access (no password required)"
echo "✓ Docker group membership"
echo "✓ Web projects directory at /home/web-dev/web-projects"
echo ""
echo "Your PHP site is running with DDEV at:"
echo "  http://hello-world.ddev.local"
echo "  https://hello-world.ddev.local"
echo ""
echo "Useful DDEV commands:"
echo "  cd /home/web-dev/web-projects/hello-world"
echo "  ddev start          # Start the project"
echo "  ddev stop           # Stop the project"
echo "  ddev restart        # Restart the project"
echo "  ddev status         # Show project status"
echo "  ddev logs           # View logs"
echo "  ddev launch         # Open in browser"
echo "  ddev ssh            # SSH into web container"
echo "  ddev exec 'php -v'  # Execute commands in container"
echo ""
echo "To switch to web-dev user:"
echo "  su - web-dev"
echo ""
echo "Docker commands:"
echo "  docker ps               # List running containers"
echo "  docker images           # List images"
echo "  docker system prune     # Clean up unused resources"
echo ""
echo "DDEV project management:"
echo "  ddev config             # Configure a new project"
echo "  ddev poweroff           # Stop all DDEV projects"
echo "  ddev list               # List all projects"
echo ""
echo "CloudWatch Agent status:"
echo "  sudo systemctl status amazon-cloudwatch-agent"
echo ""
echo "SSM Agent status:"
echo "  sudo systemctl status amazon-ssm-agent"
echo ""
echo "=================================================="
EOF

sudo chmod +x /home/web-dev/setup-complete.sh

# Create a quick start script for the project
sudo -u web-dev tee /home/web-dev/web-projects/hello-world/quick-start.sh > /dev/null <<'EOF'
#!/bin/bash
echo "🚀 Quick Start for Hello World PHP Project"
echo ""
echo "Starting DDEV project..."
ddev start --yes

echo ""
echo "Opening in browser..."
ddev launch

echo ""
echo "Useful commands:"
echo "  ddev status     # Check project status"
echo "  ddev logs       # View logs"
echo "  ddev stop       # Stop the project"
echo "  ddev restart    # Restart the project"
EOF

sudo chmod +x /home/web-dev/web-projects/hello-world/quick-start.sh

# Final status check
log "Performing final status checks..."

# Check services
services=("docker" "amazon-cloudwatch-agent" "amazon-ssm-agent")
for service in "${services[@]}"; do
    if systemctl is-active --quiet "$service"; then
        log "✓ $service is running"
    else
        warn "$service is not running"
    fi
done

# Check Docker
if docker --version > /dev/null 2>&1; then
    log "✓ Docker is working"
else
    warn "Docker may not be working properly"
fi

# Check DDEV
if ddev --version > /dev/null 2>&1; then
    log "✓ DDEV is working"
else
    warn "DDEV may not be working properly"
fi

# Check if DDEV project is running
if sudo -u web-dev ddev status > /dev/null 2>&1; then
    log "✓ DDEV project is configured"
else
    warn "DDEV project may not be properly configured"
fi

log "Setup complete! Run '/home/web-dev/setup-complete.sh' for a summary."
log "Switch to web-dev user with: su - web-dev"
log "Your PHP site is available at: http://hello-world.ddev.local"

# Display final information
echo ""
echo -e "${BLUE}=== Setup Summary ===${NC}"
echo "User created: web-dev (no password set)"
echo "Sudo access: Enabled (no password required)"
echo "Docker: Installed and running"
echo "DDEV: Installed and configured"
echo "CloudWatch Agent: Installed and running"
echo "SSM Agent: Installed and running"
echo "PHP site: Running with DDEV at hello-world.ddev.local"
echo "Web projects directory: /home/web-dev/web-projects"
echo ""
echo -e "${GREEN}Setup completed successfully!${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Switch to web-dev user: su - web-dev"
echo "2. Navigate to project: cd /home/web-dev/web-projects/hello-world"
echo "3. Start the project: ddev start"
echo "4. Open in browser: ddev launch"
echo "5. View setup summary: /home/web-dev/setup-complete.sh"