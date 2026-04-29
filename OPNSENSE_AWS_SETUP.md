# OPNsense on AWS — Setup Guide

OPNsense 26.1.x deployed as a virtual firewall appliance on AWS EC2, imported via the VM Import/Export pipeline in this repo.

## Architecture Overview

```
Internet
    │
    ▼
[IGW]
    │
[Public Subnets /20 — 2x AZs]
    │
[OPNsense EC2 — WAN ENI]
    │
[Appliance Subnets /22 — 2x AZs]  ← OPNsense LAN ENI + VPC Endpoints
    │
[Private Isolated Subnets /20 — 2x AZs]
```

Traffic from the private `/20` subnets is routed through the OPNsense LAN ENI (in the appliance `/22` subnet) for both internet egress and VPC endpoint access. OPNsense is co-located with the VPC endpoints, so no static route overrides are needed for endpoint traffic.

**Subnet layout:**

| Type              | CIDR   | Count | Route Target                        |
|-------------------|--------|-------|-------------------------------------|
| Public            | /20    | 2     | IGW                                 |
| Appliance         | /22    | 2     | OPNsense LAN ENI + VPC Endpoints    |
| Private Isolated  | /20    | 2     | OPNsense LAN ENI (in appliance /22) |

---

## Step 1: Import OPNsense AMI

Deploy the CDK pipeline to download, convert, and register the OPNsense image as an AMI.

```bash
cd homelab.wisnewski.io
pip install -r requirements.txt
cdk deploy \
  -c imageUrl="https://mirrors.nycbug.org/pub/opnsense/releases/mirror/OPNsense-26.1.2-nano-amd64.img.bz2" \
  -c imageKey="opnsense/opnsense-26.1.2-nano-amd64.raw" \
  -c importDescription="OPNsense 26.1.2 nano"
```

The CodeBuild project will output an `ami-output.env` artifact containing the resulting `AMI_ID`. Note this value for the next step.

---

## Step 2: Launch OPNsense EC2 Instance

```bash
aws ec2 run-instances \
  --image-id <AMI_ID> \
  --instance-type t3.small \
  --network-interfaces \
    "DeviceIndex=0,SubnetId=<PUBLIC_SUBNET_ID>,Groups=<WAN_SG_ID>,DeleteOnTermination=true" \
    "DeviceIndex=1,SubnetId=<APPLIANCE_SUBNET_ID>,Groups=<LAN_SG_ID>,DeleteOnTermination=true" \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=opnsense-fw}]'
```

> Use subnets from the same AZ for both ENIs on a single instance. The LAN ENI goes into the appliance `/22` subnet — the same subnet as your VPC endpoints.

---

## Step 3: AWS Pre-requisites

These must be configured before touching OPNsense itself.

### 3a. Disable Source/Dest Check

Disable on **every ENI** attached to the OPNsense instance, or forwarded traffic will be silently dropped by AWS.

```bash
# Get ENI IDs attached to the instance
aws ec2 describe-instances \
  --instance-ids <INSTANCE_ID> \
  --query 'Reservations[].Instances[].NetworkInterfaces[].[NetworkInterfaceId,Attachment.DeviceIndex]' \
  --output table

# Disable source/dest check on each ENI
aws ec2 modify-network-interface-attribute \
  --network-interface-id <ENI_ID> \
  --no-source-dest-check
```

### 3b. Security Groups

**WAN Security Group** (attached to `eth0` / public-facing ENI):

| Direction | Protocol | Port  | Source              | Purpose              |
|-----------|----------|-------|---------------------|----------------------|
| Inbound   | TCP      | 443   | Your IP/CIDR        | GUI access (temp)    |
| Inbound   | TCP      | 22    | Your IP/CIDR        | SSH (optional)       |
| Outbound  | All      | All   | 0.0.0.0/0           | Egress               |

**LAN Security Group** (attached to `eth1` / appliance subnet ENI):

| Direction | Protocol | Port | Source                  | Purpose                               |
|-----------|----------|------|-------------------------|---------------------------------------|
| Inbound   | All      | All  | Private /20 subnet CIDR | Allow traffic from private subnets    |
| Inbound   | TCP      | 443  | Private /20 subnet CIDR | GUI access from private subnet hosts  |
| Outbound  | All      | All  | 0.0.0.0/0               | Egress (internet + VPC endpoints)     |

### 3c. VPC Route Tables

**Private subnet route table** — route all egress through OPNsense LAN ENI (in appliance subnet):

```bash
aws ec2 create-route \
  --route-table-id <PRIVATE_RTB_ID> \
  --destination-cidr-block 0.0.0.0/0 \
  --network-interface-id <LAN_ENI_ID>
```

**Public subnet route table** — standard IGW route (already set if using CDK/Terraform):

```
0.0.0.0/0 → igw-xxx
```

**Appliance subnet route table** — OPNsense LAN ENI lives here; needs a default route to the WAN ENI so OPNsense itself can reach the internet and VPC endpoints can return traffic:

```
0.0.0.0/0 → igw-xxx   (or via TGW if using transit gateway)
```

> VPC endpoints in the appliance subnet are reachable directly from OPNsense without any static route override — they are on the same subnet as the LAN ENI.

---

## Step 4: Interface Assignment via EC2 Serial Console

Access the instance via EC2 Serial Console (no key pair required):

```
AWS Console → EC2 → Instance → Connect → EC2 Serial Console
```

At the OPNsense console menu:

1. **Option 1 — Assign interfaces**
   - Answer `n` to VLAN setup
   - Identify NICs by cross-referencing MAC addresses with ENI MACs shown in EC2 console
   - Assign:
     - `WAN → vtnet0` (public subnet ENI)
     - `LAN → vtnet1` (appliance /22 subnet ENI)

2. **Option 2 — Set interface IP addresses**
   - **WAN**: select DHCP — AWS will assign the ENI's private IP automatically
   - **LAN**: select DHCP — AWS will assign the LAN ENI's private IP automatically
   - When asked to enable DHCP server on LAN, answer `n` (AWS handles DHCP for EC2 instances)

---

## Step 5: Access the OPNsense GUI

The GUI is available at `https://<LAN_ENI_PRIVATE_IP>` (the OPNsense LAN ENI IP in the appliance `/22` subnet).

**Default credentials:** `root` / `opnsense`

Options to reach it:
- From an EC2 instance in the private `/20` subnet via SSM Session Manager — traffic routes through OPNsense to reach the appliance subnet
- From another host directly in the appliance `/22` subnet (e.g. a bastion or management instance)
- Temporarily via WAN IP (EIP) with a permissive WAN SG rule + OPNsense WAN allow rule

> Change the default password immediately under System → Access → Users.

---

## Step 6: OPNsense GUI Configuration

### Interfaces

Navigate to **Interfaces → Assignments** and confirm:
- `WAN` → `vtnet0` (public /20 subnet)
- `LAN` → `vtnet1` (appliance /22 subnet)

**WAN interface settings** (Interfaces → [WAN]):
- IPv4 config: DHCP
- Uncheck **"Block private networks"** — WAN IP is RFC1918 in AWS

**LAN interface settings** (Interfaces → [LAN]):
- IPv4 config: DHCP (AWS assigns the appliance subnet private IP)
- This interface is co-located with your VPC endpoints — no additional routing needed to reach them

### Gateway

Verify under **System → Gateways** that the WAN gateway was learned via DHCP.
It should be the `.1` address of the public subnet (AWS VPC router).

### DNS

System → Settings → General:
- Set upstream DNS to `169.254.169.253` (AWS VPC resolver)

### NAT — Outbound

Firewall → NAT → Outbound:
- Set mode to **Automatic outbound NAT**
- This enables private subnet hosts to reach the internet via OPNsense

### Firewall Rules — Minimum Viable

**LAN rules** (Firewall → Rules → LAN):

| Action | Protocol | Source  | Destination | Purpose             |
|--------|----------|---------|-------------|---------------------|
| Pass   | Any      | LAN net | Any         | Allow LAN egress    |

**WAN rules** — add only if you need GUI access from WAN temporarily:

| Action | Protocol | Source   | Destination    | Port | Purpose  |
|--------|----------|----------|----------------|------|----------|
| Pass   | TCP      | Your IP  | This Firewall  | 443  | GUI      |

---

## Step 7: Validate

From a private subnet host (via SSM):

```bash
# Confirm GUI reachable from private subnet host
curl -k -I https://<APPLIANCE_SUBNET_LAN_ENI_IP>

# Confirm internet routing via OPNsense
curl -s https://ifconfig.me

# Confirm VPC endpoints reachable (OPNsense LAN is on same subnet as endpoints)
curl https://s3.<region>.amazonaws.com
aws ssm describe-instance-information   # SSM endpoint reachable
```

In OPNsense, verify under **Interfaces → Overview** that both WAN and LAN show assigned IPs and status **up**.

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| GUI unreachable from private subnet | Route table missing OPNsense entry | Add `0.0.0.0/0 → LAN ENI` to private /20 RTB |
| Private hosts can't reach internet | Source/dest check enabled on ENI | Disable on all OPNsense ENIs |
| Traffic loops or asymmetric routing | Subnet overlap between WAN and LAN | Verify /20 public, /22 appliance, /20 private don't overlap |
| GUI accessible but no internet | NAT not configured | Set outbound NAT to Automatic |
| VPC endpoints unreachable from private subnet | OPNsense blocking endpoint return traffic | Add LAN rule allowing appliance /22 CIDR inbound |
| Interface shows wrong IP | vtnet0/vtnet1 swapped | Re-assign interfaces in console option 1; LAN must be appliance subnet ENI |
