# Network flow (centralized egress via GWLB + FortiGate)
### Outbound (workload → Internet)
1. A workload in a subnet using private-egress-route table (for example 172.17.80.0/20 or 172.17.96.0/20) sends traffic destined outside the VPC.
2. The subnet’s route table sends 0.0.0.0/0 to a Gateway Load Balancer Endpoint (GWLBE) in that VPC (consumer endpoint for the GWLB service).
3. The GWLBE sends traffic to the GWLB, which load-balances across FortiGate instances registered as Geneve targets.
4. FortiGate receives encapsulated flows on its “private” / inspection side (Geneve from GWLB), applies policy (IPS, app control, URL filter, etc.), then forwards permitted traffic out its “public” / egress ENI.
5. The subnet where that public ENI is attached uses fortigate-egress-route-table: 0.0.0.0/0 → Internet Gateway. FortiGate performs SNAT (replacing NAT Gateway for this path) so return traffic comes back to the firewall’s public address.
6. Traffic leaves the VPC through the IGW to the Internet.
### Return (Internet → same flows)
7. Return packets hit the IGW and are routed to the FortiGate public ENI (same route table / subnet design as your egress side).
8. FortiGate reverses SNAT and sends the flow back through the GWLB/Geneve path toward the original workload subnets (symmetric flow handling is part of the GWLB inspection model).
### Other subnets
* Subnets still on private-route table with only local routes behave as before (no default to inspection).
* Public subnets still use public-route-table to the IGW for resources that are actually public (bastion, ALB, or FortiGate’s egress ENI if you place it in a public subnet).

## Design note
In real builds, GWLBE subnets, FortiGate Geneve subnets, and FortiGate public-egress subnets are often separate subnets and route tables even if the diagram keeps one 172.17.12.0/22 “FortiGate + GWLB” box per AZ for space. The logical split is: egress workloads → GWLBE → GWLB → FortiGate (private/Geneve) → FortiGate public ENI → IGW (+ SNAT).

If you want the drawing to show three subnet types per AZ (GWLBE-only, Geneve target, public egress), say so and we can split the boxes and edges to match.