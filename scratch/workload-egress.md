# Network flow (centralized egress via GWLB + FortiGate)

The VPC diagram uses **three subnet roles per AZ**: GWLBE (endpoint ENIs), Geneve/GWLB targets (FortiGate inspection leg), and FortiGate egress (public ENI + SNAT to IGW).

### Subnet layout (per AZ)

| Role | AZ a (example CIDR) | AZ b (example CIDR) |
|------|---------------------|---------------------|
| Gateway Load Balancer Endpoint (GWLBE) | 172.17.12.0/24 | 172.17.104.0/24 |
| GWLB + FortiGate Geneve targets | 172.17.13.0/24 | 172.17.105.0/24 |
| FortiGate egress (public ENI) | 172.17.14.0/24 | 172.17.106.0/24 |

Associate **gwlbe-endpoint-route-table** with GWLBE subnets, **fortigate-geneve-route-table** with Geneve subnets, and **fortigate-egress-route-table** with FortiGate egress subnets.

### Outbound (workload → Internet)

1. A workload in a subnet using **private-egress-route-table** (for example 172.17.80.0/20 or 172.17.96.0/20) sends traffic destined outside the VPC.
2. That route table sends **0.0.0.0/0** to the **Gateway Load Balancer Endpoint** object; the endpoint’s ENIs live in the **GWLBE subnets**.
3. The GWLBE sends traffic to **GWLB**, which load-balances across **FortiGate** instances registered as **Geneve** targets in the **Geneve subnets**.
4. FortiGate decapsulates on the Geneve leg, applies policy, then forwards permitted traffic out its **egress ENI** in the **FortiGate egress subnet**.
5. **fortigate-egress-route-table** on those subnets: **0.0.0.0/0 → Internet Gateway**. FortiGate performs **SNAT** (replacing NAT Gateway for this path).
6. Traffic leaves the VPC through the **IGW** to the Internet.

### Return (Internet → same flows)

7. Return packets hit the **IGW** and are routed to the FortiGate **egress ENI**.
8. FortiGate reverses SNAT and returns the flow through the **GWLB / Geneve** path toward the original workload subnets.

### Other subnets

- Subnets on **private-route-table** with only **local** routes behave as before (no default to inspection).
- **Public** subnets use **public-route-table** (**0.0.0.0/0 → IGW**) for truly public workloads (bastion, ALB, etc.). FortiGate egress subnets use a **separate** route table with IGW for the firewall leg only.

### Route table summary

- **private-egress-route-table**: `172.17.0.0/16 → local`; `0.0.0.0/0 → GWLBE`.
- **gwlbe-endpoint-route-table**: `172.17.0.0/16 → local` (no default internet route on endpoint subnets).
- **fortigate-geneve-route-table**: `172.17.0.0/16 → local` (Geneve encapsulation from GWLB; refine per Fortinet/AWS guidance if you add asymmetric routing).
- **fortigate-egress-route-table**: `172.17.0.0/16 → local`; `0.0.0.0/0 → IGW`.
- **public-route-table**: `172.17.0.0/16 → local`; `0.0.0.0/0 → IGW`.

CIDRs in the table are examples; size and numbering should match your IPAM and AZ pairing.
