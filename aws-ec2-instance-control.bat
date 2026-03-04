@echo off
setlocal enabledelayedexpansion

if "%~1"=="" goto usage
if "%~2"=="" goto usage

set CMD=%~1
set INSTANCE_NAME=%~2
set LOCAL_RDP_PORT=%~3

if "%LOCAL_RDP_PORT%"=="" set LOCAL_RDP_PORT=13389

:: Resolve instance name (tag Name) to instance ID
for /f "usebackq delims=" %%i in (`aws ec2 describe-instances --filters "Name=tag:Name,Values=%INSTANCE_NAME%" "Name=instance-state-name,Values=pending,running,stopped,stopping" --query "Reservations[*].Instances[*].InstanceId" --output text 2^>nul`) do set INSTANCE_ID=%%i

if "%INSTANCE_ID%"=="" (
    echo Error: No instance found with Name tag "%INSTANCE_NAME%"
    exit /b 1
)

:: If multiple instances, use first one (optional: could error instead)
for %%a in (%INSTANCE_ID%) do set INSTANCE_ID=%%a & goto :single_id
:single_id

if /i "%CMD%"=="start" goto do_start
if /i "%CMD%"=="stop" goto do_stop
if /i "%CMD%"=="rdp" goto do_rdp
goto usage

:do_start
echo Starting instance %INSTANCE_NAME% (%INSTANCE_ID%)...
aws ec2 start-instances --instance-ids %INSTANCE_ID%
if errorlevel 1 (
    echo Failed to start instance.
    exit /b 1
)
echo Waiting for instance to reach running state...
aws ec2 wait instance-running --instance-ids %INSTANCE_ID%
echo Instance is running.
exit /b 0

:do_stop
echo Stopping instance %INSTANCE_NAME% (%INSTANCE_ID%)...
aws ec2 stop-instances --instance-ids %INSTANCE_ID%
if errorlevel 1 (
    echo Failed to stop instance.
    exit /b 1
)
echo Instance stop requested.
exit /b 0

:do_rdp
echo Starting RDP port forwarding: localhost:%LOCAL_RDP_PORT% -> %INSTANCE_NAME% (%INSTANCE_ID%):3389
echo Connect with: mstsc /v:localhost:%LOCAL_RDP_PORT%
echo.
aws ssm start-session ^
    --target %INSTANCE_ID% ^
    --document-name AWS-StartPortForwardingSession ^
    --parameters "{\"portNumber\":[\"3389\"],\"localPortNumber\":[\"%LOCAL_RDP_PORT%\"]}"
exit /b 0

:usage
echo Usage:
echo   %~nx0 start  ^<instance-name^>                    Start EC2 instance by name
echo   %~nx0 stop   ^<instance-name^>                    Stop EC2 instance by name
echo   %~nx0 rdp    ^<instance-name^> [local-port]       RDP port forward (default local port 13389)
echo.
echo Instance name is the EC2 tag "Name". SSM agent required for RDP forwarding.
exit /b 1
