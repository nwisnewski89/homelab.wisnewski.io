# FortiGate Shared VPC Validation Runbook

This runbook validates workload-account egress through FortiGate VMs deployed in a networking account that owns and shares VPC subnets through AWS RAM.

Use this when:
- VPC and route tables are owned by networking account.
- Subnets are shared to workload account.
- Workload resources are launched into shared subnets.
- FortiGate instances have private/public ENIs.

---

## 0) Prerequisites

- AWS CLI v2 installed and authenticated.
- Permissions to read EC2/RAM/CloudWatch in both accounts.
- `jq` installed (optional but recommended).

---

## 1) Fill in environment variables

Copy/paste and set values:

```bash
# Account and region context
export AWS_REGION="us-east-1"
export NETWORK_PROFILE="networking"
export WORKLOAD_PROFILE="workload"
export NETWORK_ACCOUNT_ID="111111111111"
export WORKLOAD_ACCOUNT_ID="222222222222"

# Shared VPC and subnets (owner account objects)
export VPC_ID="vpc-xxxxxxxxxxxxxxxxx"
export WORKLOAD_SUBNET_IDS="subnet-aaa subnet-bbb"
export FGT_PRIVATE_SUBNET_IDS="subnet-ccc subnet-ddd"
export FGT_PUBLIC_SUBNET_IDS="subnet-eee subnet-fff"

# FortiGate ENIs (per AZ, private and public)
export FGT1_PRIVATE_ENI="eni-11111111111111111"
export FGT1_PUBLIC_ENI="eni-22222222222222222"
export FGT2_PRIVATE_ENI="eni-33333333333333333"
export FGT2_PUBLIC_ENI="eni-44444444444444444"

# Optional test instance (in workload account)
export TEST_INSTANCE_ID="i-xxxxxxxxxxxxxxxxx"
```

Sanity check identity:

```bash
aws sts get-caller-identity --profile "$NETWORK_PROFILE"
aws sts get-caller-identity --profile "$WORKLOAD_PROFILE"
```

---

## 2) Validate subnet sharing (RAM) and workload placement

### 2.1 Confirm shared subnets are visible in workload account

```bash
aws ec2 describe-subnets \
  --profile "$WORKLOAD_PROFILE" \
  --region "$AWS_REGION" \
  --filters Name=vpc-id,Values="$VPC_ID" \
  --query 'Subnets[].{SubnetId:SubnetId,OwnerId:OwnerId,Az:AvailabilityZone,Cidr:CidrBlock}' \
  --output table
```

Expected:
- `OwnerId` should be networking account for shared subnets.
- Shared subnets should appear and match intended AZ/CIDR.

### 2.2 Confirm workload ENIs exist in shared subnets

```bash
aws ec2 describe-network-interfaces \
  --profile "$WORKLOAD_PROFILE" \
  --region "$AWS_REGION" \
  --filters Name=vpc-id,Values="$VPC_ID" \
  --query 'NetworkInterfaces[].{ENI:NetworkInterfaceId,Subnet:SubnetId,Owner:OwnerId,Status:Status,PrivateIp:PrivateIpAddress}' \
  --output table
```

Expected:
- Workload ENIs are present in shared subnets.
- ENI owner may differ by resource type; subnet ownership remains networking account.

---

## 3) Validate route tables and next-hop targets

### 3.1 Inspect all default routes in the VPC (networking account)

```bash
aws ec2 describe-route-tables \
  --profile "$NETWORK_PROFILE" \
  --region "$AWS_REGION" \
  --filters Name=vpc-id,Values="$VPC_ID" \
  --query 'RouteTables[].{RTB:RouteTableId,Assoc:Associations[].SubnetId,Default:Routes[?DestinationCidrBlock==`0.0.0.0/0`].[NetworkInterfaceId,NatGatewayId,GatewayId,TransitGatewayId,State]}' \
  --output json
```

Expected:
- Workload subnet route table default route should target FortiGate **private ENI** (`NetworkInterfaceId`) for that AZ/path.
- If a route points somewhere else, traffic will bypass or fail through firewall path.

### 3.2 Verify subnet-to-route-table associations

```bash
aws ec2 describe-route-tables \
  --profile "$NETWORK_PROFILE" \
  --region "$AWS_REGION" \
  --filters Name=vpc-id,Values="$VPC_ID" \
  --query 'RouteTables[].{RTB:RouteTableId,AssociatedSubnets:Associations[].SubnetId}' \
  --output table
```

Expected:
- Each workload subnet is associated to intended route table.
- AZ pathing is consistent with selected FortiGate instance.

---

## 4) Validate FortiGate ENI forwarding requirements

### 4.1 Source/destination check must be disabled

```bash
aws ec2 describe-network-interfaces \
  --profile "$NETWORK_PROFILE" \
  --region "$AWS_REGION" \
  --network-interface-ids "$FGT1_PRIVATE_ENI" "$FGT1_PUBLIC_ENI" "$FGT2_PRIVATE_ENI" "$FGT2_PUBLIC_ENI" \
  --query 'NetworkInterfaces[].{ENI:NetworkInterfaceId,SrcDstCheck:SourceDestCheck,Subnet:SubnetId,PrivateIp:PrivateIpAddress,Status:Status}' \
  --output table
```

Expected:
- `SrcDstCheck = false` for all FortiGate ENIs used for forwarding.

### 4.2 Confirm ENIs are in expected subnets

Expected:
- Private ENIs in private/firewall ingress subnets.
- Public ENIs in egress/public subnets.

---

## 5) Validate SG/NACL allowance for transit traffic

### 5.1 Security groups on FortiGate ENIs

```bash
aws ec2 describe-network-interfaces \
  --profile "$NETWORK_PROFILE" \
  --region "$AWS_REGION" \
  --network-interface-ids "$FGT1_PRIVATE_ENI" "$FGT1_PUBLIC_ENI" "$FGT2_PRIVATE_ENI" "$FGT2_PUBLIC_ENI" \
  --query 'NetworkInterfaces[].{ENI:NetworkInterfaceId,SGs:Groups[].GroupId,Subnet:SubnetId}' \
  --output json
```

Expected:
- Inbound from workload CIDRs/subnets to FortiGate private side is allowed.
- Outbound return and egress from FortiGate are allowed.

### 5.2 NACLs on workload, firewall-private, firewall-public subnets

```bash
aws ec2 describe-network-acls \
  --profile "$NETWORK_PROFILE" \
  --region "$AWS_REGION" \
  --filters Name=vpc-id,Values="$VPC_ID" \
  --query 'NetworkAcls[].{NaclId:NetworkAclId,Associations:Associations[].SubnetId,Entries:Entries[*].[RuleNumber,Egress,RuleAction,Protocol,CidrBlock,PortRange.From,PortRange.To]}' \
  --output json
```

Expected:
- Stateless rules permit forward and return traffic (including ephemeral ports).

---

## 6) Validate FortiGate dataplane config (on appliance)

In FortiGate UI/CLI, confirm:
- Default route points to intended upstream path on public-side interface.
- Policy allows workload subnets to approved destinations.
- NAT/SNAT configured as intended for internet egress.
- Session/log view shows accepted flows from workload test host.

If you are using FQDN allow-listing:
- Ensure resolved IPs for allowed domains are current.
- Ensure explicit policy order does not deny before allow rule.

---

## 7) Functional test from workload instance

Run from a workload instance in shared subnet (SSM preferred):

```bash
curl -4 ifconfig.me
curl -I https://www.google.com
traceroute -n 8.8.8.8 || tracepath 8.8.8.8
```

Expected:
- `ifconfig.me` returns expected egress public IP.
- HTTPS to Google succeeds when policy allows.
- Path behavior aligns with firewall insertion design.

---

## 8) Optional: VPC Flow Logs triage

Enable/check flow logs on:
- Workload subnet(s)
- FortiGate private subnet(s)
- FortiGate public subnet(s)

Then correlate same 5-tuple across legs:
- Workload ENI -> FortiGate private ENI
- FortiGate public ENI -> external destination
- Return path accepted back to workload

CloudWatch Insights starter query:

```sql
fields @timestamp, interfaceId, srcAddr, srcPort, dstAddr, dstPort, action, protocol, packets, bytes
| filter action = "ACCEPT"
| sort @timestamp desc
| limit 200
```

---

## 9) Common failure signatures and fixes

- Route points to wrong target
  - Symptom: no traffic on FortiGate private ENI
  - Fix: set workload route table `0.0.0.0/0` to correct FortiGate private ENI

- Source/dest check left enabled
  - Symptom: one-way or dropped forwarding
  - Fix: disable source/destination check on FortiGate ENIs

- SG/NACL mismatch
  - Symptom: SYN out, no SYN-ACK back
  - Fix: allow return paths and ephemeral ports

- FortiGate policy/NAT order issue
  - Symptom: FortiGate receives flow, then denies/no SNAT
  - Fix: adjust policy order, destination object, and NAT settings

- Asymmetric AZ routing
  - Symptom: intermittent failures, uneven success by subnet/AZ
  - Fix: ensure per-AZ route alignment or intentional centralized design with correct return path

---

## 10) Answer to "do I need to share additional resources?"

In this architecture, usually **no additional RAM shares are needed for traffic forwarding** beyond sharing the subnets (and any required SG-sharing pattern you intentionally use).  
The key is correct route targets, FortiGate forwarding prerequisites, and appliance/security policy correctness in the networking-owned VPC objects.

