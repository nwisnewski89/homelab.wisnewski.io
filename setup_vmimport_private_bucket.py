import requests

OPNSENSE = "https://<opnsense-lan-ip>"
API_KEY = "<key>"
API_SECRET = "<secret>"

session = requests.Session()
session.auth = (API_KEY, API_SECRET)
session.verify = False  # replace with CA validation in production
session.headers.update({"Content-Type": "application/json"})


def post(path, payload):
    r = session.post(f"{OPNSENSE}{path}", json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def ensure_alias(name, alias_type, content_lines, description=""):
    # simple create-only example; in production, search/update by name first
    payload = {
        "alias": {
            "enabled": "1",
            "name": name,
            "type": alias_type,  # "network" or "host"
            "content": "\n".join(content_lines),
            "description": description,
        }
    }
    out = post("/api/firewall/alias/addItem", payload)
    if out.get("result") != "saved":
        raise RuntimeError(f"Alias create failed for {name}: {out}")
    return out


def add_rule(description, action, source_alias, dest_alias_or_any, interface="lan"):
    destination_net = dest_alias_or_any if dest_alias_or_any else "any"
    payload = {
        "rule": {
            "enabled": "1",
            "action": action,          # "pass" or "block"
            "interface": interface,    # your LAN/appliance interface
            "ipprotocol": "inet",      # IPv4
            "protocol": "any",         # or tcp/udp if you want tighter control
            "source_net": source_alias,
            "destination_net": destination_net,
            "description": description,
            "quick": "1",
            "log": "1",
        }
    }
    out = post("/api/firewall/filter/addRule", payload)
    if out.get("result") != "saved":
        raise RuntimeError(f"Rule create failed: {description}: {out}")
    return out


# 1) source alias (your two /20s)
ensure_alias(
    name="SRC_PRIVATE_20S",
    alias_type="network",
    content_lines=["10.10.0.0/20", "10.10.16.0/20"],
    description="Two private /20 workload subnets",
)

# 2) fqdn alias (approved domains)
ensure_alias(
    name="ALLOWED_FQDNS",
    alias_type="host",
    content_lines=[
        "api.github.com",
        "objects.githubusercontent.com",
        "s3.us-east-1.amazonaws.com",
    ],
    description="Approved outbound FQDNs",
)

# 3) pass to approved FQDNs
add_rule(
    description="Allow egress from private /20s to approved FQDNs",
    action="pass",
    source_alias="SRC_PRIVATE_20S",
    dest_alias_or_any="ALLOWED_FQDNS",
    interface="lan",
)

# 4) explicit block everything else from those subnets
add_rule(
    description="Block other egress from private /20s",
    action="block",
    source_alias="SRC_PRIVATE_20S",
    dest_alias_or_any=None,  # any
    interface="lan",
)

# 5) apply alias + filter changes
post("/api/firewall/alias/reconfigure", {})
post("/api/firewall/filter/apply", {})

print("Done.")