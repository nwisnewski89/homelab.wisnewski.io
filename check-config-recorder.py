#!/usr/bin/env python3
"""
Script to check if AWS Config Recorder is enabled across multiple AWS profiles
in the us-east-1 region.
"""

import boto3
import sys
from botocore.exceptions import ClientError, ProfileNotFound, BotoCoreError
from typing import List, Dict, Optional

 
def check_config_recorder(profile: str, region: str = "us-east-1") -> Dict[str, any]:
    """
    Check if Config Recorder is enabled for a given AWS profile and region.
    
    Args:
        profile: AWS profile name
        region: AWS region to check (default: us-east-1)
    
    Returns:
        Dictionary with status information
    """
    result = {
        "profile": profile,
        "region": region,
        "status": "unknown",
        "recorder_name": None,
        "recording": False,
        "error": None,
        "account_id": None
    }
    
    try:
        # Create session witjh the specified profile
        session = boto3.Session(profile_name=profile)
        
        # Get account ID
        try:
            sts_client = session.client('sts', region_name=region)
            account_id = sts_client.get_caller_identity()['Account']
            result["account_id"] = account_id
        except Exception as e:
            result["error"] = f"Failed to get account ID: {str(e)}"
            result["status"] = "error"
            return result
        
        # Create Config client
        config_client = session.client('config', region_name=region)
        
        # Check if Config Recorder exists and is enabled
        try:
            response = config_client.describe_configuration_recorders()
            
            if not response.get('ConfigurationRecorders'):
                result["status"] = "not_found"
                result["error"] = "No Config Recorder found"
                return result
            
            # Get the first recorder (usually there's only one)
            recorder = response['ConfigurationRecorders'][0]
            result["recorder_name"] = recorder.get('name', 'default')
            
            # Check if recording is enabled
            recording_status = config_client.describe_configuration_recorder_status(
                ConfigurationRecorderNames=[result["recorder_name"]]
            )
            
            if recording_status.get('ConfigurationRecordersStatus'):
                status_info = recording_status['ConfigurationRecordersStatus'][0]
                result["recording"] = status_info.get('recording', False)
                
                if result["recording"]:
                    result["status"] = "enabled"
                else:
                    result["status"] = "disabled"
                    result["error"] = f"Recorder exists but recording is disabled. Last status: {status_info.get('lastStatus', 'unknown')}"
            else:
                result["status"] = "unknown"
                result["error"] = "Could not determine recording status"
                
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code == 'NoSuchConfigurationRecorderException':
                result["status"] = "not_found"
                result["error"] = "Config Recorder not found"
            else:
                result["status"] = "error"
                result["error"] = f"AWS API error: {str(e)}"
                
    except ProfileNotFound:
        result["status"] = "error"
        result["error"] = f"Profile '{profile}' not found in AWS credentials"
    except BotoCoreError as e:
        result["status"] = "error"
        result["error"] = f"Boto3 error: {str(e)}"
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"Unexpected error: {str(e)}"
    
    return result


def print_results(results: List[Dict[str, any]]):
    """Print results in a formatted table."""
    print("\n" + "=" * 100)
    print(f"{'Profile':<20} {'Account ID':<15} {'Status':<15} {'Recording':<12} {'Details':<40}")
    print("=" * 100)
    
    for result in results:
        profile = result.get("profile", "unknown")
        account_id = result.get("account_id", "N/A")
        status = result.get("status", "unknown")
        recording = "Yes" if result.get("recording") else "No"
        error = result.get("error", "")
        recorder_name = result.get("recorder_name", "")
        
        details = error if error else (f"Recorder: {recorder_name}" if recorder_name else "")
        if len(details) > 38:
            details = details[:35] + "..."
        
        print(f"{profile:<20} {account_id:<15} {status:<15} {recording:<12} {details:<40}")
    
    print("=" * 100)
    
    # Summary
    enabled_count = sum(1 for r in results if r.get("status") == "enabled")
    disabled_count = sum(1 for r in results if r.get("status") == "disabled")
    not_found_count = sum(1 for r in results if r.get("status") == "not_found")
    error_count = sum(1 for r in results if r.get("status") == "error")
    
    print(f"\nSummary:")
    print(f"  Enabled:   {enabled_count}")
    print(f"  Disabled:  {disabled_count}")
    print(f"  Not Found: {not_found_count}")
    print(f"  Errors:    {error_count}")
    print(f"  Total:     {len(results)}")


def main():
    """Main function."""
    # Default list of profiles - modify this list as needed
    # You can also pass profiles as command-line arguments
    default_profiles = [
        "default",
        # Add more profiles here as needed
    ]
    
    if len(sys.argv) > 1:
        profiles = sys.argv[1:]
    else:
        profiles = default_profiles
        print("No profiles specified. Using default profile.")
        print("Usage: python check-config-recorder.py <profile1> <profile2> ...")
        print("Example: python check-config-recorder.py prod staging dev\n")
    
    if not profiles:
        print("Error: No profiles specified.")
        sys.exit(1)
    
    print(f"Checking Config Recorder status for {len(profiles)} profile(s) in us-east-1...")
    print(f"Profiles: {', '.join(profiles)}\n")
    
    results = []
    for profile in profiles:
        print(f"Checking profile: {profile}...", end=" ")
        result = check_config_recorder(profile)
        results.append(result)
        
        if result["status"] == "enabled":
            print("✓ Enabled")
        elif result["status"] == "disabled":
            print("✗ Disabled")
        elif result["status"] == "not_found":
            print("✗ Not Found")
        else:
            print("✗ Error")
    
    print_results(results)
    
    # Exit with error code if any profiles have issues
    if any(r.get("status") in ["disabled", "not_found", "error"] for r in results):
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()

