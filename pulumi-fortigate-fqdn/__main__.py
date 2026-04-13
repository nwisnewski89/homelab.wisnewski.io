#!/usr/bin/env python3
"""
Pulumi stack: FortiOS provider resources for a dual-NIC FortiGate in AWS.

Topology (matches typical AWS dual-NIC bootstrap):
- port1: primary ENI (public / toward IGW)
- port2: secondary ENI (private / internal)

This program creates:
- One firewall address object per configured FQDN (type fqdn)
- One IPv4 policy allowing traffic from port2 -> port1 to those destinations

Configure the FortiGate REST API (API admin + API key) on the management address
reachable from where you run Pulumi (often the EIP on port1 or a bastion path).

Example:
  cd pulumi-fortigate-fqdn
  python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
  pulumi config set fortigate:hostname 203.0.113.10
  pulumi config set --secret fortigate:token '<api-key>'
  pulumi config set fortigate:domains 'example.com,registry.terraform.io'
  pulumi config set fortigate:policy_id 5001
  pulumi up
"""

from __future__ import annotations

import re

import pulumi
import pulumiverse_fortios as fortios


def _fqdn_object_name(domain: str) -> str:
    """FortiOS object name: alphanumeric + underscore; keep it readable."""
    cleaned = re.sub(r"[^0-9a-zA-Z._-]", "_", domain.strip())
    cleaned = re.sub(r"[.\-]+", "_", cleaned)
    return f"fqdn_{cleaned}"[:79]


def main() -> None:
    cfg = pulumi.Config("fortigate")

    hostname = cfg.require("hostname")
    token = cfg.require_secret("token")
    insecure = cfg.get_bool("insecure")
    if insecure is None:
        insecure = True

    vdom = cfg.get("vdom")
    domains_raw = cfg.require("domains")
    domains = [d.strip() for d in domains_raw.split(",") if d.strip()]
    if not domains:
        raise ValueError("fortigate:domains must list at least one domain")

    policy_id = cfg.get_int("policy_id")
    if policy_id is None:
        policy_id = 5000

    # Source side of the session (private/internal). Tighten to a subnet object if needed.
    srcaddr_name = cfg.get("srcaddr") or "all"

    # Service names must exist on the FortiGate (defaults: HTTPS, HTTP). Add DNS if clients
    # resolve through this policy path.
    services_csv = cfg.get("services") or "HTTPS,HTTP"
    service_names = [s.strip() for s in services_csv.split(",") if s.strip()]

    policy_name = cfg.get("policy_name") or "pulumi-fqdn-port2-to-port1"
    comments = cfg.get("comments") or "Pulumi: allow listed FQDNs from port2 to port1"

    provider_args: dict = {
        "hostname": hostname,
        "token": token,
        "insecure": insecure,
    }
    if vdom:
        provider_args["vdom"] = vdom

    fortios_provider = fortios.Provider("fortios", **provider_args)
    prov_opts = pulumi.ResourceOptions(provider=fortios_provider)

    fqdn_specs: list[tuple[str, str]] = [(d, _fqdn_object_name(d)) for d in domains]
    for domain, obj_name in fqdn_specs:
        fortios.firewall.Address(
            f"addr-{obj_name}",
            name=obj_name,
            type="fqdn",
            fqdn=domain,
            comment=f"Pulumi FQDN allow: {domain}",
            opts=prov_opts,
        )

    dstaddrs = [
        fortios.firewall.PolicyDstaddrArgs(name=obj_name) for _, obj_name in fqdn_specs
    ]

    fortios.firewall.Policy(
        "policy-fqdn-port2-port1",
        policyid=policy_id,
        name=policy_name,
        action="accept",
        status="enable",
        schedule="always",
        comments=comments,
        srcintfs=[fortios.firewall.PolicySrcintfArgs(name="port2")],
        dstintfs=[fortios.firewall.PolicyDstintfArgs(name="port1")],
        srcaddrs=[fortios.firewall.PolicySrcaddrArgs(name=srcaddr_name)],
        dstaddrs=dstaddrs,
        services=[
            fortios.firewall.PolicyServiceArgs(name=s) for s in service_names
        ],
        logtraffic=cfg.get("logtraffic") or "utm",
        opts=prov_opts,
    )

    pulumi.export("fqdn_object_names", [obj for _, obj in fqdn_specs])
    pulumi.export("policy_id", policy_id)


main()
