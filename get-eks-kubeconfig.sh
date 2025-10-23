#!/bin/bash

# EKS Kubeconfig Retrieval Script
# This script retrieves kubeconfig for all available EKS clusters in the specified region(s)

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Default values
AWS_REGION=""
REGIONS=()
ALL_REGIONS=false
DRY_RUN=false
VERBOSE=false
KUBECONFIG_FILE=""

# Function to show usage
show_usage() {
    cat << EOF
Usage: $0 [OPTIONS]

This script retrieves kubeconfig for all available EKS clusters.

OPTIONS:
    -r, --region REGION       AWS region to check (can be specified multiple times)
    -a, --all-regions         Check all available AWS regions
    -d, --dry-run            Show what would be done without making changes
    -v, --verbose            Enable verbose output
    -k, --kubeconfig FILE    Specify kubeconfig file (default: ~/.kube/config)
    -h, --help               Show this help message

EXAMPLES:
    # Get kubeconfig for clusters in us-west-2
    $0 --region us-west-2

    # Get kubeconfig for clusters in multiple regions
    $0 --region us-west-2 --region us-east-1

    # Get kubeconfig for clusters in all regions
    $0 --all-regions

    # Dry run to see what would be done
    $0 --all-regions --dry-run

    # Verbose output with custom kubeconfig file
    $0 --all-regions --verbose --kubeconfig ~/.kube/my-config

EOF
}

# Function to check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    # Check if required tools are installed
    local tools=("aws" "kubectl" "jq")
    for tool in "${tools[@]}"; do
        if ! command -v "$tool" &> /dev/null; then
            print_error "$tool is not installed or not in PATH"
            exit 1
        fi
    done
    
    # Check AWS CLI configuration
    if ! aws sts get-caller-identity &> /dev/null; then
        print_error "AWS CLI is not configured. Please run 'aws configure'"
        exit 1
    fi
    
    print_success "All prerequisites are satisfied"
}

# Function to get all available AWS regions
get_all_regions() {
    print_status "Getting all available AWS regions..."
    aws ec2 describe-regions --query 'Regions[].RegionName' --output text | tr '\t' '\n' | sort
}

# Function to get EKS clusters in a region
get_clusters_in_region() {
    local region="$1"
    
    if [[ "$VERBOSE" == "true" ]]; then
        print_status "Checking region: $region"
    fi
    
    # Get clusters in the region
    local clusters
    clusters=$(aws eks list-clusters --region "$region" --query 'clusters[]' --output text 2>/dev/null || echo "")
    
    if [[ -z "$clusters" ]]; then
        if [[ "$VERBOSE" == "true" ]]; then
            print_warning "No EKS clusters found in region: $region"
        fi
        return 0
    fi
    
    echo "$clusters"
}

# Function to update kubeconfig for a cluster
update_kubeconfig() {
    local cluster_name="$1"
    local region="$2"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        print_status "Would update kubeconfig for cluster: $cluster_name in region: $region"
        return 0
    fi
    
    print_status "Updating kubeconfig for cluster: $cluster_name in region: $region"
    
    # Update kubeconfig
    if aws eks update-kubeconfig --region "$region" --name "$cluster_name" --kubeconfig "$KUBECONFIG_FILE" &>/dev/null; then
        print_success "Successfully updated kubeconfig for cluster: $cluster_name"
        
        # Test the connection
        if kubectl --kubeconfig="$KUBECONFIG_FILE" cluster-info &>/dev/null; then
            print_success "Cluster connection verified: $cluster_name"
        else
            print_warning "Cluster added but connection test failed: $cluster_name"
        fi
    else
        print_error "Failed to update kubeconfig for cluster: $cluster_name"
        return 1
    fi
}

# Function to process clusters in a region
process_region() {
    local region="$1"
    local clusters
    
    clusters=$(get_clusters_in_region "$region")
    
    if [[ -z "$clusters" ]]; then
        return 0
    fi
    
    print_status "Found $(echo "$clusters" | wc -w) cluster(s) in region: $region"
    
    # Process each cluster
    for cluster in $clusters; do
        update_kubeconfig "$cluster" "$region"
    done
}

# Function to validate inputs
validate_inputs() {
    # Check if at least one region option is provided
    if [[ ${#REGIONS[@]} -eq 0 && "$ALL_REGIONS" == "false" ]]; then
        print_error "You must specify either --region or --all-regions"
        show_usage
        exit 1
    fi
    
    # Set default kubeconfig file if not specified
    if [[ -z "$KUBECONFIG_FILE" ]]; then
        KUBECONFIG_FILE="$HOME/.kube/config"
    fi
    
    # Create kubeconfig directory if it doesn't exist
    local kubeconfig_dir
    kubeconfig_dir=$(dirname "$KUBECONFIG_FILE")
    if [[ ! -d "$kubeconfig_dir" ]]; then
        print_status "Creating kubeconfig directory: $kubeconfig_dir"
        mkdir -p "$kubeconfig_dir"
    fi
}

# Function to show summary
show_summary() {
    print_status "Summary:"
    print_status "  Regions to check: ${#REGIONS[@]}"
    for region in "${REGIONS[@]}"; do
        print_status "    - $region"
    done
    print_status "  Kubeconfig file: $KUBECONFIG_FILE"
    print_status "  Dry run: $DRY_RUN"
    print_status "  Verbose: $VERBOSE"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -r|--region)
            REGIONS+=("$2")
            shift 2
            ;;
        -a|--all-regions)
            ALL_REGIONS=true
            shift
            ;;
        -d|--dry-run)
            DRY_RUN=true
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -k|--kubeconfig)
            KUBECONFIG_FILE="$2"
            shift 2
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Main execution
main() {
    print_status "Starting EKS kubeconfig retrieval..."
    
    # Check prerequisites
    check_prerequisites
    
    # Validate inputs
    validate_inputs
    
    # Get all regions if requested
    if [[ "$ALL_REGIONS" == "true" ]]; then
        print_status "Getting all available AWS regions..."
        REGIONS=($(get_all_regions))
    fi
    
    # Show summary
    show_summary
    
    # Process each region
    local total_clusters=0
    for region in "${REGIONS[@]}"; do
        print_status "Processing region: $region"
        
        # Get clusters in this region
        local clusters
        clusters=$(get_clusters_in_region "$region")
        
        if [[ -n "$clusters" ]]; then
            local cluster_count
            cluster_count=$(echo "$clusters" | wc -w)
            total_clusters=$((total_clusters + cluster_count))
            
            print_status "Found $cluster_count cluster(s) in $region:"
            for cluster in $clusters; do
                print_status "  - $cluster"
            done
            
            # Process clusters in this region
            for cluster in $clusters; do
                update_kubeconfig "$cluster" "$region"
            done
        else
            print_warning "No EKS clusters found in region: $region"
        fi
    done
    
    # Final summary
    print_success "Completed processing all regions"
    print_status "Total clusters processed: $total_clusters"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        print_warning "This was a dry run - no changes were made"
    else
        print_success "Kubeconfig has been updated for all available EKS clusters"
        print_status "You can now use 'kubectl config get-contexts' to see all available contexts"
    fi
}

# Run main function
main "$@"
