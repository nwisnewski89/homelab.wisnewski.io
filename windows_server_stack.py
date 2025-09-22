#!/usr/bin/env python3
"""
CDK Stack for Windows Server 2019 with SSM Fleet Manager enrollment
"""

import secrets
import string
from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_ssm as ssm,
    CfnOutput,
    Duration,
    Tags
)
from constructs import Construct


class WindowsServerStack(Stack):
    """CDK Stack for Windows Server 2019 with SSM Fleet Manager"""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Generate a random password for the thomas user
        password = self._generate_random_password()
        
        # Store the password in SSM Parameter Store for retrieval
        self.password_parameter = ssm.StringParameter(
            self, "ThomasPassword",
            parameter_name="/windows-server/thomas/password",
            string_value=password,
            description="Password for thomas admin user on Windows Server",
            tier=ssm.ParameterTier.STANDARD
        )

        # Create VPC and networking
        self.vpc = self._create_vpc()
        
        # Create IAM role for SSM
        self.ssm_role = self._create_ssm_role()
        
        # Create security group
        self.security_group = self._create_security_group()
        
        # Create user data script
        user_data = self._create_user_data_script(password)
        
        # Create Windows Server 2019 instance
        self.instance = self._create_windows_instance(user_data)
        
        # Add tags
        Tags.of(self.instance).add("Name", "Windows-Server-2019-SSM")
        Tags.of(self.instance).add("Environment", "Development")
        Tags.of(self.instance).add("ManagedBy", "SSM")

        # Outputs
        CfnOutput(
            self, "InstanceId",
            value=self.instance.instance_id,
            description="Windows Server Instance ID"
        )
        
        CfnOutput(
            self, "PasswordParameterName",
            value=self.password_parameter.parameter_name,
            description="SSM Parameter name containing thomas user password"
        )
        
        CfnOutput(
            self, "SSMConnectCommand",
            value=f"aws ssm start-session --target {self.instance.instance_id}",
            description="Command to connect via SSM Session Manager"
        )

    def _generate_random_password(self) -> str:
        """Generate a secure random password meeting Windows requirements"""
        # Windows password requirements: 8+ chars, uppercase, lowercase, number, special char
        length = 16
        lowercase = string.ascii_lowercase
        uppercase = string.ascii_uppercase
        digits = string.digits
        special_chars = "!@#$%^&*"
        
        # Ensure at least one character from each required category
        password = [
            secrets.choice(lowercase),
            secrets.choice(uppercase),
            secrets.choice(digits),
            secrets.choice(special_chars)
        ]
        
        # Fill the rest with random characters
        all_chars = lowercase + uppercase + digits + special_chars
        for _ in range(length - 4):
            password.append(secrets.choice(all_chars))
        
        # Shuffle the password
        secrets.SystemRandom().shuffle(password)
        return ''.join(password)

    def _create_vpc(self) -> ec2.Vpc:
        """Create VPC with public and private subnets"""
        return ec2.Vpc(
            self, "WindowsServerVpc",
            max_azs=2,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24
                )
            ]
        )

    def _create_ssm_role(self) -> iam.Role:
        """Create IAM role for SSM with necessary permissions"""
        return iam.Role(
            self, "SSMRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"),
                iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchAgentServerPolicy"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMDirectoryServiceAccess")
            ],
            inline_policies={
                "SSMAdditionalPermissions": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "ssm:UpdateInstanceInformation",
                                "ssm:SendCommand",
                                "ssm:ListCommandInvocations",
                                "ssm:DescribeInstanceInformation",
                                "ssm:GetConnectionStatus"
                            ],
                            resources=["*"]
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "ssm:GetParameter",
                                "ssm:GetParameters",
                                "ssm:GetParametersByPath"
                            ],
                            resources=[
                                f"arn:aws:ssm:{self.region}:{self.account}:parameter/windows-server/*"
                            ]
                        )
                    ]
                )
            }
        )

    def _create_security_group(self) -> ec2.SecurityGroup:
        """Create security group with necessary rules"""
        sg = ec2.SecurityGroup(
            self, "WindowsServerSG",
            vpc=self.vpc,
            description="Security group for Windows Server with SSM",
            allow_all_outbound=True
        )
        
        # Allow RDP access (for initial setup if needed)
        sg.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(3389),
            description="RDP access"
        )
        
        # Allow HTTPS for SSM agent communication
        sg.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(443),
            description="HTTPS for SSM agent"
        )
        
        # Allow WinRM for PowerShell remoting
        sg.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(5985),
            description="WinRM HTTP"
        )
        
        sg.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(5986),
            description="WinRM HTTPS"
        )
        
        return sg

    def _create_user_data_script(self, password: str) -> ec2.UserData:
        """Create user data script for Windows Server setup"""
        user_data = ec2.UserData.for_windows()
        
        # PowerShell script to set up the instance
        powershell_script = f"""
# Set execution policy
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Force

# Enable WinRM for SSM
Enable-PSRemoting -Force
winrm quickconfig -q
winrm set winrm/config/winrs '@{{MaxMemoryPerShellMB="512"}}'
winrm set winrm/config '@{{MaxTimeoutms="1800000"}}'
winrm set winrm/config/service '@{{AllowUnencrypted="true"}}'
winrm set winrm/config/service/auth '@{{Basic="true"}}'

# Install and configure SSM Agent
$ssmAgentUrl = "https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/windows_amd64/AmazonSSMAgentSetup.exe"
$ssmAgentPath = "$env:TEMP\\AmazonSSMAgentSetup.exe"

try {{
    Write-Host "Downloading SSM Agent..."
    Invoke-WebRequest -Uri $ssmAgentUrl -OutFile $ssmAgentPath -UseBasicParsing
    
    Write-Host "Installing SSM Agent..."
    Start-Process -FilePath $ssmAgentPath -ArgumentList "/S" -Wait
    
    Write-Host "Starting SSM Agent service..."
    Start-Service -Name "AmazonSSMAgent"
    Set-Service -Name "AmazonSSMAgent" -StartupType Automatic
    
    Write-Host "SSM Agent installed and started successfully"
}} catch {{
    Write-Error "Failed to install SSM Agent: $_"
}}

# Create thomas admin user
$username = "thomas"
$userPassword = ConvertTo-SecureString -String "{password}" -AsPlainText -Force

try {{
    Write-Host "Creating user: $username"
    New-LocalUser -Name $username -Password $userPassword -FullName "Thomas Admin" -Description "Admin user created by CDK"
    
    # Add to Administrators group
    Add-LocalGroupMember -Group "Administrators" -Member $username
    
    Write-Host "User $username created and added to Administrators group"
}} catch {{
    Write-Error "Failed to create user: $_"
}}

# Configure Windows Firewall for SSM
try {{
    Write-Host "Configuring Windows Firewall..."
    New-NetFirewallRule -DisplayName "SSM Agent" -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow
    New-NetFirewallRule -DisplayName "WinRM HTTP" -Direction Inbound -Protocol TCP -LocalPort 5985 -Action Allow
    New-NetFirewallRule -DisplayName "WinRM HTTPS" -Direction Inbound -Protocol TCP -LocalPort 5986 -Action Allow
    
    Write-Host "Windows Firewall configured for SSM"
}} catch {{
    Write-Error "Failed to configure Windows Firewall: $_"
}}

# Install CloudWatch agent (optional but recommended)
try {{
    Write-Host "Installing CloudWatch agent..."
    $cloudwatchAgentUrl = "https://s3.amazonaws.com/amazoncloudwatch-agent/windows/amd64/latest/amazon-cloudwatch-agent.msi"
    $cloudwatchAgentPath = "$env:TEMP\\amazon-cloudwatch-agent.msi"
    
    Invoke-WebRequest -Uri $cloudwatchAgentUrl -OutFile $cloudwatchAgentPath -UseBasicParsing
    Start-Process msiexec.exe -Wait -ArgumentList '/I', $cloudwatchAgentPath, '/quiet'
    
    Write-Host "CloudWatch agent installed"
}} catch {{
    Write-Warning "Failed to install CloudWatch agent: $_"
}}

# Set timezone to UTC
try {{
    Set-TimeZone -Id "UTC"
    Write-Host "Timezone set to UTC"
}} catch {{
    Write-Warning "Failed to set timezone: $_"
}}

# Log completion
Write-Host "Windows Server setup completed successfully at $(Get-Date)"
"""
        
        user_data.add_commands(powershell_script)
        return user_data

    def _create_windows_instance(self, user_data: ec2.UserData) -> ec2.Instance:
        """Create Windows Server 2019 EC2 instance"""
        # Get the latest Windows Server 2019 AMI
        ami = ec2.MachineImage.latest_windows(
            version=ec2.WindowsVersion.WINDOWS_SERVER_2019_ENGLISH_FULL_BASE
        )
        
        return ec2.Instance(
            self, "WindowsServerInstance",
            instance_type=ec2.InstanceType.of(
                instance_class=ec2.InstanceClass.T3,
                instance_size=ec2.InstanceSize.MEDIUM
            ),
            machine_image=ami,
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PUBLIC
            ),
            security_group=self.security_group,
            role=self.ssm_role,
            user_data=user_data,
            key_name=None,  # No key pair needed for SSM access
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/sda1",
                    volume=ec2.BlockDeviceVolume.ebs(
                        volume_size=30,
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                        encrypted=True,
                        delete_on_termination=True
                    )
                )
            ],
            detailed_monitoring=True,
            ssm_session_permissions=True
        )
