# Windows Server 2019 Session Manager Plugin Troubleshooting Guide

## Issue: "Session Manager plugin not found" Error

This error occurs when trying to connect to a Windows Server 2019 instance via AWS Systems Manager Session Manager, but the Session Manager plugin is not properly installed or configured.

## Common Causes

1. **SSM Agent not installed** or not running
2. **Session Manager plugin not installed** on the local machine
3. **IAM permissions missing** for Session Manager
4. **Network connectivity issues** between instance and SSM endpoints
5. **SSM Agent version compatibility** issues
6. **Windows Firewall blocking** SSM communication
7. **Instance not registered** with Systems Manager

## Troubleshooting Steps

### Step 1: Verify Instance Registration with SSM

Check if your Windows Server instance is registered with Systems Manager:

```bash
# Check if instance appears in SSM
aws ssm describe-instance-information --filters "Key=InstanceIds,Values=<your-instance-id>"

# Check instance status
aws ssm get-connection-status --target <your-instance-id>
```

**Expected Output**: Instance should appear with status "Connected" or "Ready"

### Step 2: Verify SSM Agent Installation and Status

Connect to your Windows Server instance via RDP and run these PowerShell commands:

```powershell
# Check if SSM Agent service is installed and running
Get-Service -Name "AmazonSSMAgent"

# Check SSM Agent version
Get-WmiObject -Class Win32_Product | Where-Object {$_.Name -like "*Amazon*SSM*"}

# Check SSM Agent logs
Get-Content "C:\ProgramData\Amazon\SSM\Logs\amazon-ssm-agent.log" -Tail 20

# Check if Session Manager plugin is installed
Get-ChildItem "C:\Program Files\Amazon\SSM\Plugins" -Name "*SessionManager*"
```

### Step 3: Install/Update SSM Agent (if needed)

If SSM Agent is not installed or outdated, install the latest version:

```powershell
# Download latest SSM Agent
$ssmAgentUrl = "https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/windows_amd64/AmazonSSMAgentSetup.exe"
$ssmAgentPath = "$env:TEMP\AmazonSSMAgentSetup.exe"

# Download and install
Invoke-WebRequest -Uri $ssmAgentUrl -OutFile $ssmAgentPath -UseBasicParsing
Start-Process -FilePath $ssmAgentPath -ArgumentList "/S" -Wait

# Start the service
Start-Service -Name "AmazonSSMAgent"
Set-Service -Name "AmazonSSMAgent" -StartupType Automatic

# Verify installation
Get-Service -Name "AmazonSSMAgent"
```

### Step 4: Install Session Manager Plugin on Windows Server

The Session Manager plugin needs to be installed on the Windows Server instance:

```powershell
# Download Session Manager plugin
$pluginUrl = "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/windows/SessionManagerPluginSetup.exe"
$pluginPath = "$env:TEMP\SessionManagerPluginSetup.exe"

# Download and install
Invoke-WebRequest -Uri $pluginUrl -OutFile $pluginPath -UseBasicParsing
Start-Process -FilePath $pluginPath -ArgumentList "/S" -Wait

# Verify installation
Get-ChildItem "C:\Program Files\Amazon\SSM\Plugins" -Name "*SessionManager*"
```

### Step 5: Verify IAM Permissions

Ensure your IAM role has the necessary permissions for Session Manager:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ssm:UpdateInstanceInformation",
                "ssm:SendCommand",
                "ssm:ListCommandInvocations",
                "ssm:DescribeInstanceInformation",
                "ssm:GetConnectionStatus"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "ssmmessages:CreateControlChannel",
                "ssmmessages:CreateDataChannel",
                "ssmmessages:OpenControlChannel",
                "ssmmessages:OpenDataChannel"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "ec2messages:AcknowledgeMessage",
                "ec2messages:DeleteMessage",
                "ec2messages:FailMessage",
                "ec2messages:GetEndpoint",
                "ec2messages:GetMessages",
                "ec2messages:SendReply"
            ],
            "Resource": "*"
        }
    ]
}
```

### Step 6: Check Network Connectivity

Verify that your instance can reach SSM endpoints:

```powershell
# Test connectivity to SSM endpoints
Test-NetConnection -ComputerName "ssm.us-east-1.amazonaws.com" -Port 443
Test-NetConnection -ComputerName "ssmmessages.us-east-1.amazonaws.com" -Port 443
Test-NetConnection -ComputerName "ec2messages.us-east-1.amazonaws.com" -Port 443

# Check if instance has internet access
Test-NetConnection -ComputerName "8.8.8.8" -Port 53
```

### Step 7: Configure Windows Firewall

Ensure Windows Firewall allows SSM communication:

```powershell
# Allow SSM Agent through Windows Firewall
New-NetFirewallRule -DisplayName "SSM Agent" -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName "SSM Agent Outbound" -Direction Outbound -Protocol TCP -LocalPort 443 -Action Allow -ErrorAction SilentlyContinue

# Allow WinRM for Session Manager
New-NetFirewallRule -DisplayName "WinRM HTTP" -Direction Inbound -Protocol TCP -LocalPort 5985 -Action Allow -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName "WinRM HTTPS" -Direction Inbound -Protocol TCP -LocalPort 5986 -Action Allow -ErrorAction SilentlyContinue
```

### Step 8: Install Session Manager Plugin on Local Machine

If you're connecting from a local machine, ensure the Session Manager plugin is installed:

**For Windows:**
```powershell
# Download and install Session Manager plugin
$pluginUrl = "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/windows/SessionManagerPluginSetup.exe"
$pluginPath = "$env:TEMP\SessionManagerPluginSetup.exe"

Invoke-WebRequest -Uri $pluginUrl -OutFile $pluginPath -UseBasicParsing
Start-Process -FilePath $pluginPath -ArgumentList "/S" -Wait
```

**For macOS:**
```bash
# Install via Homebrew
brew install --cask session-manager-plugin

# Or download directly
curl "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/mac/sessionmanager-bundle.zip" -o "sessionmanager-bundle.zip"
unzip sessionmanager-bundle.zip
sudo ./sessionmanager-bundle/install -i /usr/local/sessionmanagerplugin -b /usr/local/bin/session-manager-plugin
```

**For Linux:**
```bash
# Download and install
curl "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/ubuntu_64bit/session-manager-plugin.deb" -o "session-manager-plugin.deb"
sudo dpkg -i session-manager-plugin.deb
```

### Step 9: Verify Session Manager Plugin Installation

Check if the plugin is properly installed:

```bash
# Check if session-manager-plugin is available
which session-manager-plugin
session-manager-plugin --version

# Test connection
aws ssm start-session --target <your-instance-id>
```

### Step 10: Enable WinRM for Session Manager

Session Manager requires WinRM to be properly configured:

```powershell
# Enable WinRM
Enable-PSRemoting -Force
winrm quickconfig -q

# Configure WinRM settings
winrm set winrm/config/winrs '@{MaxMemoryPerShellMB="512"}'
winrm set winrm/config '@{MaxTimeoutms="1800000"}'
winrm set winrm/config/service '@{AllowUnencrypted="true"}'
winrm set winrm/config/service/auth '@{Basic="true"}'

# Restart WinRM service
Restart-Service WinRM
```

## Updated User Data Script

Here's an updated user data script that includes Session Manager plugin installation:

```powershell
# Set execution policy
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Force

# Enable WinRM for SSM
Enable-PSRemoting -Force
winrm quickconfig -q
winrm set winrm/config/winrs '@{MaxMemoryPerShellMB="512"}'
winrm set winrm/config '@{MaxTimeoutms="1800000"}'
winrm set winrm/config/service '@{AllowUnencrypted="true"}'
winrm set winrm/config/service/auth '@{Basic="true"}'

# Install and configure SSM Agent
$ssmAgentUrl = "https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/windows_amd64/AmazonSSMAgentSetup.exe"
$ssmAgentPath = "$env:TEMP\AmazonSSMAgentSetup.exe"

try {
    Write-Host "Downloading SSM Agent..."
    Invoke-WebRequest -Uri $ssmAgentUrl -OutFile $ssmAgentPath -UseBasicParsing
    
    Write-Host "Installing SSM Agent..."
    Start-Process -FilePath $ssmAgentPath -ArgumentList "/S" -Wait
    
    Write-Host "Starting SSM Agent service..."
    Start-Service -Name "AmazonSSMAgent"
    Set-Service -Name "AmazonSSMAgent" -StartupType Automatic
    
    Write-Host "SSM Agent installed and started successfully"
} catch {
    Write-Error "Failed to install SSM Agent: $_"
}

# Install Session Manager Plugin
$pluginUrl = "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/windows/SessionManagerPluginSetup.exe"
$pluginPath = "$env:TEMP\SessionManagerPluginSetup.exe"

try {
    Write-Host "Downloading Session Manager Plugin..."
    Invoke-WebRequest -Uri $pluginUrl -OutFile $pluginPath -UseBasicParsing
    
    Write-Host "Installing Session Manager Plugin..."
    Start-Process -FilePath $pluginPath -ArgumentList "/S" -Wait
    
    Write-Host "Session Manager Plugin installed successfully"
} catch {
    Write-Error "Failed to install Session Manager Plugin: $_"
}

# Configure Windows Firewall for SSM
try {
    Write-Host "Configuring Windows Firewall..."
    New-NetFirewallRule -DisplayName "SSM Agent" -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow -ErrorAction SilentlyContinue
    New-NetFirewallRule -DisplayName "SSM Agent Outbound" -Direction Outbound -Protocol TCP -LocalPort 443 -Action Allow -ErrorAction SilentlyContinue
    New-NetFirewallRule -DisplayName "WinRM HTTP" -Direction Inbound -Protocol TCP -LocalPort 5985 -Action Allow -ErrorAction SilentlyContinue
    New-NetFirewallRule -DisplayName "WinRM HTTPS" -Direction Inbound -Protocol TCP -LocalPort 5986 -Action Allow -ErrorAction SilentlyContinue
    
    Write-Host "Windows Firewall configured for SSM"
} catch {
    Write-Error "Failed to configure Windows Firewall: $_"
}

# Create thomas admin user
$username = "thomas"
$userPassword = ConvertTo-SecureString -String "{password}" -AsPlainText -Force

try {
    Write-Host "Creating user: $username"
    New-LocalUser -Name $username -Password $userPassword -FullName "Thomas Admin" -Description "Admin user created by CDK"
    
    # Add to Administrators group
    Add-LocalGroupMember -Group "Administrators" -Member $username
    
    Write-Host "User $username created and added to Administrators group"
} catch {
    Write-Error "Failed to create user: $_"
}

# Install CloudWatch agent (optional but recommended)
try {
    Write-Host "Installing CloudWatch agent..."
    $cloudwatchAgentUrl = "https://s3.amazonaws.com/amazoncloudwatch-agent/windows/amd64/latest/amazon-cloudwatch-agent.msi"
    $cloudwatchAgentPath = "$env:TEMP\amazon-cloudwatch-agent.msi"
    
    Invoke-WebRequest -Uri $cloudwatchAgentUrl -OutFile $cloudwatchAgentPath -UseBasicParsing
    Start-Process msiexec.exe -Wait -ArgumentList '/I', $cloudwatchAgentPath, '/quiet'
    
    Write-Host "CloudWatch agent installed"
} catch {
    Write-Warning "Failed to install CloudWatch agent: $_"
}

# Set timezone to UTC
try {
    Set-TimeZone -Id "UTC"
    Write-Host "Timezone set to UTC"
} catch {
    Write-Warning "Failed to set timezone: $_"
}

# Log completion
Write-Host "Windows Server setup completed successfully at $(Get-Date)"
```

## Diagnostic Script

Create a diagnostic script to check all components:

```powershell
# SSM Diagnostic Script
Write-Host "=== SSM Diagnostic Script ===" -ForegroundColor Green

# Check SSM Agent service
Write-Host "`n1. Checking SSM Agent Service..." -ForegroundColor Yellow
$ssmService = Get-Service -Name "AmazonSSMAgent" -ErrorAction SilentlyContinue
if ($ssmService) {
    Write-Host "   Status: $($ssmService.Status)" -ForegroundColor Green
    Write-Host "   StartType: $($ssmService.StartType)" -ForegroundColor Green
} else {
    Write-Host "   SSM Agent service not found!" -ForegroundColor Red
}

# Check SSM Agent version
Write-Host "`n2. Checking SSM Agent Version..." -ForegroundColor Yellow
$ssmProduct = Get-WmiObject -Class Win32_Product | Where-Object {$_.Name -like "*Amazon*SSM*"}
if ($ssmProduct) {
    Write-Host "   Version: $($ssmProduct.Version)" -ForegroundColor Green
} else {
    Write-Host "   SSM Agent not found in installed programs!" -ForegroundColor Red
}

# Check Session Manager plugin
Write-Host "`n3. Checking Session Manager Plugin..." -ForegroundColor Yellow
$pluginPath = "C:\Program Files\Amazon\SSM\Plugins\aws:sessionManager"
if (Test-Path $pluginPath) {
    Write-Host "   Session Manager Plugin: Installed" -ForegroundColor Green
} else {
    Write-Host "   Session Manager Plugin: Not found!" -ForegroundColor Red
}

# Check network connectivity
Write-Host "`n4. Checking Network Connectivity..." -ForegroundColor Yellow
$endpoints = @("ssm.us-east-1.amazonaws.com", "ssmmessages.us-east-1.amazonaws.com", "ec2messages.us-east-1.amazonaws.com")
foreach ($endpoint in $endpoints) {
    $test = Test-NetConnection -ComputerName $endpoint -Port 443 -InformationLevel Quiet
    if ($test) {
        Write-Host "   $endpoint: Connected" -ForegroundColor Green
    } else {
        Write-Host "   $endpoint: Failed" -ForegroundColor Red
    }
}

# Check Windows Firewall rules
Write-Host "`n5. Checking Windows Firewall Rules..." -ForegroundColor Yellow
$firewallRules = Get-NetFirewallRule | Where-Object {$_.DisplayName -like "*SSM*" -or $_.DisplayName -like "*WinRM*"}
if ($firewallRules) {
    foreach ($rule in $firewallRules) {
        Write-Host "   $($rule.DisplayName): $($rule.Enabled)" -ForegroundColor Green
    }
} else {
    Write-Host "   No SSM/WinRM firewall rules found!" -ForegroundColor Red
}

# Check WinRM service
Write-Host "`n6. Checking WinRM Service..." -ForegroundColor Yellow
$winrmService = Get-Service -Name "WinRM" -ErrorAction SilentlyContinue
if ($winrmService) {
    Write-Host "   Status: $($winrmService.Status)" -ForegroundColor Green
} else {
    Write-Host "   WinRM service not found!" -ForegroundColor Red
}

Write-Host "`n=== Diagnostic Complete ===" -ForegroundColor Green
```

## Quick Fix Commands

If you need to quickly fix the issue, run these commands on your Windows Server:

```powershell
# Quick fix script
Write-Host "Applying quick fixes..." -ForegroundColor Green

# Restart SSM Agent
Restart-Service -Name "AmazonSSMAgent" -Force

# Restart WinRM
Restart-Service -Name "WinRM" -Force

# Reconfigure WinRM
winrm quickconfig -q

# Check and fix firewall rules
New-NetFirewallRule -DisplayName "SSM Agent" -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName "WinRM HTTP" -Direction Inbound -Protocol TCP -LocalPort 5985 -Action Allow -ErrorAction SilentlyContinue

Write-Host "Quick fixes applied. Wait 2-3 minutes and try connecting again." -ForegroundColor Yellow
```

## Prevention

To prevent this issue in the future:

1. **Use the updated user data script** that includes Session Manager plugin installation
2. **Regularly update SSM Agent** to the latest version
3. **Monitor SSM agent logs** for any issues
4. **Test connectivity** after instance creation
5. **Use IAM roles** with proper permissions

## Additional Resources

- [AWS Systems Manager Session Manager Documentation](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager.html)
- [SSM Agent Installation Guide](https://docs.aws.amazon.com/systems-manager/latest/userguide/ssm-agent.html)
- [Session Manager Plugin Installation](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html)
