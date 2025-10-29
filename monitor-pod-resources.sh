aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=your-instance-name" \
  --output json | jq -r '.Reservations[].Instances[] | select(.State.Name=="running") | "\(.InstanceId) - \(.Tags[] | select(.Key=="Name") | .Value)"'