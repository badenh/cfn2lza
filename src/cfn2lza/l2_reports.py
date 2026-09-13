"""L2 pass — post-L1 clustering + reviewer summaries.

Reads per-domain UNMAPPED artifacts and emits reviewer-oriented cluster reports.
Does NOT run mappers; runs after `run.py` main pipeline.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from .common import REPORTS_DIR, UNMAPPED_DIR


def _cluster_network() -> str:
    p = UNMAPPED_DIR / "network.json"
    if not p.exists():
        return "no network.json to cluster"
    items = json.loads(p.read_text())
    by_source: dict[str, Counter] = defaultdict(Counter)
    for u in items:
        r = u["reason"]
        if "SLZ CFN " in r:
            t = r.split("SLZ CFN ", 1)[1].split(" ", 1)[0]
        else:
            t = "OTHER"
        by_source[u["source"]][t] += 1
    lines = ["# L2 cluster: network domain hand-port shopping list", "",
             "Items are [REWORK]-flagged from L1 — LZA models these at higher",
             "abstraction than SLZ CFN. Reviewer must hand-port during task #9.",
             ""]
    for src, cnt in sorted(by_source.items()):
        lines += [f"## `{src}` ({sum(cnt.values())} items)", ""]
        for t, n in cnt.most_common():
            lines.append(f"- **{n}× {t}** → hand-port to LZA equivalent")
        lines.append("")
    lines += [
        "## Hand-port guidance",
        "",
        "**Routes + RouteTables + SubnetRouteTableAssociations:** collapse into "
        "`vpcs[].routeTables[].routes[]` per LZA schema.",
        "",
        "**NetworkAcls + NetworkAclEntries + SubnetNetworkAclAssociations:** collapse "
        "into `vpcs[].networkAcls[]` with inline `inboundRules` / `outboundRules`.",
        "",
        "**NatGateways + EIPs:** collapse into `vpcs[].natGateways[]` with "
        "`subnet:` and `allocationId:` fields.",
        "",
        "**InternetGateway + VPCGatewayAttachment:** collapse into `vpcs[].internetGateway`.",
        "",
        "**TGW attachments + route-table assoc + propagation + static routes:** "
        "collapse into `vpcs[].transitGatewayAttachments[]` on spoke VPCs and "
        "`transitGateways[].routeTables[].routes[]` on the central TGW.",
        "",
        "**DHCPOptions + Association:** `vpcs[].dhcpOptions:` block.",
        "",
        "**SecurityGroup:** `vpcs[].securityGroups[]`.",
        "",
        "**FlowLog:** already folded into `vpcFlowLogs` global block; per-VPC "
        "entries can be dropped.",
    ]
    out = REPORTS_DIR / "network-l2-cluster.md"
    out.write_text("\n".join(lines) + "\n")
    return f"emitted {out}"


def main() -> int:
    print("[L2] clustering network unmapped items")
    print("  ", _cluster_network())
    return 0


if __name__ == "__main__":
    sys.exit(main())
