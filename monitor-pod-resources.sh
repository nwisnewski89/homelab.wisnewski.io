#!/bin/bash
#
# Monitor Pod Resources in Real-Time
# Continuously monitor pod resource usage with color-coded warnings
#
# Usage: ./monitor-pod-resources.sh <pod-name> [namespace] [interval]
#

POD_NAME=$1
NAMESPACE=${2:-default}
INTERVAL=${3:-2}

if [ -z "$POD_NAME" ]; then
    echo "Usage: $0 <pod-name> [namespace] [interval]"
    echo ""
    echo "Examples:"
    echo "  $0 nginx-deployment-abc123"
    echo "  $0 nginx-deployment-abc123 production"
    echo "  $0 nginx-deployment-abc123 production 5"
    exit 1
fi

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Function to convert memory to MB for comparison
memory_to_mb() {
    local mem=$1
    if [[ $mem == *"Gi"* ]]; then
        echo $(echo "$mem" | sed 's/Gi//' | awk '{print $1*1024}')
    elif [[ $mem == *"Mi"* ]]; then
        echo $(echo "$mem" | sed 's/Mi//')
    elif [[ $mem == *"Ki"* ]]; then
        echo $(echo "$mem" | sed 's/Ki//' | awk '{print $1/1024}')
    else
        echo "0"
    fi
}

# Function to convert CPU to millicores
cpu_to_millicores() {
    local cpu=$1
    if [[ $cpu == *"m"* ]]; then
        echo $(echo "$cpu" | sed 's/m//')
    else
        echo $(echo "$cpu" | awk '{print $1*1000}')
    fi
}

# Main monitoring loop
echo -e "${BLUE}=== Monitoring $POD_NAME in namespace $NAMESPACE ===${NC}"
echo -e "${BLUE}Refresh interval: ${INTERVAL}s (Press Ctrl+C to stop)${NC}"
echo ""

while true; do
    clear
    echo -e "${BLUE}=== Pod Resource Monitor: $POD_NAME ===${NC}"
    echo -e "${BLUE}Namespace: $NAMESPACE | Time: $(date '+%Y-%m-%d %H:%M:%S')${NC}"
    echo ""
    
    # Check if pod exists
    if ! kubectl get pod "$POD_NAME" -n "$NAMESPACE" &> /dev/null; then
        echo -e "${RED}Error: Pod not found${NC}"
        sleep "$INTERVAL"
        continue
    fi
    
    # Get current usage
    echo -e "${GREEN}=== Current Resource Usage ===${NC}"
    USAGE=$(kubectl top pod "$POD_NAME" -n "$NAMESPACE" --containers --no-headers 2>/dev/null)
    
    if [ -z "$USAGE" ]; then
        echo -e "${YELLOW}Metrics not available${NC}"
    else
        echo "$USAGE" | while read -r line; do
            POD=$(echo "$line" | awk '{print $1}')
            CONTAINER=$(echo "$line" | awk '{print $2}')
            CPU=$(echo "$line" | awk '{print $3}')
            MEM=$(echo "$line" | awk '{print $4}')
            
            # Get limits for this container
            CPU_LIMIT=$(kubectl get pod "$POD_NAME" -n "$NAMESPACE" -o json | \
                jq -r ".spec.containers[] | select(.name==\"$CONTAINER\") | .resources.limits.cpu // \"none\"")
            MEM_LIMIT=$(kubectl get pod "$POD_NAME" -n "$NAMESPACE" -o json | \
                jq -r ".spec.containers[] | select(.name==\"$CONTAINER\") | .resources.limits.memory // \"none\"")
            
            # Color code based on usage
            CPU_COLOR=$GREEN
            MEM_COLOR=$GREEN
            
            # Check CPU usage (warn if > 80% of limit)
            if [ "$CPU_LIMIT" != "none" ]; then
                CPU_USAGE_MC=$(cpu_to_millicores "$CPU")
                CPU_LIMIT_MC=$(cpu_to_millicores "$CPU_LIMIT")
                if [ "$CPU_LIMIT_MC" -gt 0 ]; then
                    CPU_PERCENT=$(awk "BEGIN {printf \"%.0f\", ($CPU_USAGE_MC/$CPU_LIMIT_MC)*100}")
                    if [ "$CPU_PERCENT" -gt 80 ]; then
                        CPU_COLOR=$RED
                    elif [ "$CPU_PERCENT" -gt 60 ]; then
                        CPU_COLOR=$YELLOW
                    fi
                fi
            fi
            
            # Check memory usage (warn if > 80% of limit)
            if [ "$MEM_LIMIT" != "none" ]; then
                MEM_USAGE_MB=$(memory_to_mb "$MEM")
                MEM_LIMIT_MB=$(memory_to_mb "$MEM_LIMIT")
                if [ "$MEM_LIMIT_MB" -gt 0 ]; then
                    MEM_PERCENT=$(awk "BEGIN {printf \"%.0f\", ($MEM_USAGE_MB/$MEM_LIMIT_MB)*100}")
                    if [ "$MEM_PERCENT" -gt 80 ]; then
                        MEM_COLOR=$RED
                    elif [ "$MEM_PERCENT" -gt 60 ]; then
                        MEM_COLOR=$YELLOW
                    fi
                fi
            fi
            
            printf "%-20s %-30s ${CPU_COLOR}%10s${NC} / %-10s ${MEM_COLOR}%10s${NC} / %-10s\n" \
                "$POD" "$CONTAINER" "$CPU" "$CPU_LIMIT" "$MEM" "$MEM_LIMIT"
        done
    fi
    
    echo ""
    echo -e "${GREEN}=== Pod Status ===${NC}"
    kubectl get pod "$POD_NAME" -n "$NAMESPACE" -o json | jq -r '
        "Status:        \(.status.phase)
         Node:          \(.spec.nodeName // "none")
         Restarts:      \(.status.containerStatuses[0].restartCount // 0)
         Age:           \(.metadata.creationTimestamp)"'
    
    echo ""
    echo -e "${GREEN}=== Container States ===${NC}"
    kubectl get pod "$POD_NAME" -n "$NAMESPACE" -o json | jq -r '
        .status.containerStatuses[]? | 
        "Container: \(.name) | State: \(.state | keys[0]) | Ready: \(.ready) | Restarts: \(.restartCount)"'
    
    # Show recent events
    echo ""
    echo -e "${GREEN}=== Recent Events (last 5) ===${NC}"
    kubectl get events -n "$NAMESPACE" --field-selector involvedObject.name="$POD_NAME" \
        --sort-by='.lastTimestamp' --no-headers 2>/dev/null | tail -n 5 | \
        awk '{printf "%-8s %-15s %s\n", $5, $4, substr($0, index($0,$6))}'
    
    echo ""
    echo -e "${BLUE}Press Ctrl+C to stop monitoring${NC}"
    
    sleep "$INTERVAL"
done

