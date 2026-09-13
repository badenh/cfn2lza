"""Network-domain mapper.

Pragmatic partial extraction: emits high-level structural facts (VPC names/CIDRs,
subnet metadata, TGW + route-table names, NFW policy/firewall stub, RAM shares,
VPC endpoint service list, spoke-VPC template shape) into a LZA network-config.yaml
skeleton. Detailed routing/NACL wiring is *not* mechanically translated — CFN
resource-level Route/NetworkAclEntry/TransitGatewayRoute semantics don't map 1:1
onto LZA's higher-level route-table entries; hand review required in task #9.
Suricata rules file is copied verbatim.
"""
from __future__ import annotations

import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

from ..common import (
    Coverage,
    OUT_DIR,
    SLZ_CFN,
    load_cfn,
    resolve_ref,
    resource_iter,
    write_yaml,
)
from ..profile import (
    ACCELERATOR_PREFIX,
    HOME_REGION,
    NETWORK_ACCOUNT,
    NETWORK_SOURCES,
    SPOKE_VPC_TARGET_OUS,
    TGW_ASN,
)


def _az_from_name(subnet_name: str) -> str:
    """SLZ subnet naming convention ends with A/B/C for AZ.
    LZA expects the single lowercase letter suffix, not full region-AZ.
    e.g. NetworkInspectionPubA → 'a'."""
    if subnet_name and subnet_name[-1] in "ABC":
        return subnet_name[-1].lower()
    return ""


def _short_service(arn_or_service: Any) -> str:
    """Extract short service name.

    Handles:
      - `com.amazonaws.<region>.s3` → `s3`
      - `{'Fn::Sub': 'com.amazonaws.${AWS::Region}.s3'}` → `s3`
      - falls back to full stringification
    """
    s = arn_or_service
    if isinstance(s, dict) and set(s.keys()) == {"Fn::Sub"} and isinstance(s["Fn::Sub"], str):
        s = s["Fn::Sub"]
    if isinstance(s, str) and s.startswith("com.amazonaws."):
        return s.rsplit(".", 1)[-1]
    return str(s)


# Types that are backing infra for flow-log delivery, ignored by LZA UC.
BACKING_TYPES = {
    "AWS::IAM::Role",
    "AWS::Logs::LogGroup",
    "AWS::KMS::Key",
    "AWS::KMS::Alias",
}

# Types whose LZA equivalent lives in a higher-level UC construct — SLZ authored
# them individually in CFN; LZA authors them declaratively per-VPC/subnet.
# We count these as "structurally-recognized" but not per-resource-translated.
STRUCTURAL_TYPES = {
    "AWS::EC2::Route",
    "AWS::EC2::RouteTable",
    "AWS::EC2::SubnetRouteTableAssociation",
    "AWS::EC2::NetworkAcl",
    "AWS::EC2::NetworkAclEntry",
    "AWS::EC2::SubnetNetworkAclAssociation",
    "AWS::EC2::InternetGateway",
    "AWS::EC2::VPCGatewayAttachment",
    "AWS::EC2::EIP",
    "AWS::EC2::NatGateway",
    "AWS::EC2::DHCPOptions",
    "AWS::EC2::VPCDHCPOptionsAssociation",
    "AWS::EC2::TransitGatewayAttachment",
    "AWS::EC2::TransitGatewayRoute",
    "AWS::EC2::TransitGatewayRouteTableAssociation",
    "AWS::EC2::TransitGatewayRouteTablePropagation",
    "AWS::EC2::SecurityGroup",
    "AWS::EC2::FlowLog",
}


def _tag(props: dict[str, Any], key: str, default: Any = None) -> Any:
    for t in props.get("Tags") or []:
        if t.get("Key") == key:
            return t.get("Value")
    return default


def _extract_vpcs(tpl: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract VPC + subnet + endpoint metadata. Groups subnets by VpcId ref."""
    vpcs: dict[str, dict[str, Any]] = {}
    for lid, res in resource_iter(tpl):
        if res.get("Type") != "AWS::EC2::VPC":
            continue
        p = res["Properties"]
        cidr = resolve_ref(p.get("CidrBlock"), tpl)
        raw_name = _tag(p, "Name", lid)
        name = resolve_ref(raw_name, tpl)
        if not isinstance(name, str):
            name = lid
        vpcs[lid] = {
            "name": f"{ACCELERATOR_PREFIX}-{name}",
            "account": NETWORK_ACCOUNT,
            "region": HOME_REGION,
            "cidrs": [cidr] if isinstance(cidr, str) else [],
            "enableDnsHostnames": True,
            "enableDnsSupport": True,
            "subnets": [],
            "routeTables": [],
        }
    # Attach subnets
    for lid, res in resource_iter(tpl):
        if res.get("Type") != "AWS::EC2::Subnet":
            continue
        p = res["Properties"]
        vpc_ref = p.get("VpcId", {})
        vpc_key = vpc_ref.get("Ref") if isinstance(vpc_ref, dict) else None
        if vpc_key not in vpcs:
            continue
        az = resolve_ref(p.get("AvailabilityZone"), tpl)
        cidr = resolve_ref(p.get("CidrBlock"), tpl)
        raw_name = _tag(p, "Name", lid)
        name = resolve_ref(raw_name, tpl)
        if not isinstance(name, str):
            name = lid
        resolved_az = az if isinstance(az, str) and az else _az_from_name(name)
        if not resolved_az:
            resolved_az = "a"  # schema requires non-empty; [REWORK]
        vpcs[vpc_key]["subnets"].append({
            "name": name,
            "availabilityZone": resolved_az,
            "ipv4CidrBlock": cidr if isinstance(cidr, str) else "",
            "routeTable": "TODO-rt",  # [REWORK] hand-port route-table association
        })
    # Attach endpoints (interface + gateway VPC endpoints)
    for lid, res in resource_iter(tpl):
        if res.get("Type") != "AWS::EC2::VPCEndpoint":
            continue
        p = res["Properties"]
        vpc_ref = p.get("VpcId", {})
        vpc_key = vpc_ref.get("Ref") if isinstance(vpc_ref, dict) else None
        if vpc_key not in vpcs:
            continue
        service = resolve_ref(p.get("ServiceName"), tpl)
        etype = p.get("VpcEndpointType") or "Interface"
        # defaultPolicy references an entry in top-level endpointPolicies[].
        # We emit a permissive stub "OpenAccess" — reviewer can tighten per LZA
        # vpc-endpoint-policies/*.json pattern later.
        if etype == "Gateway":
            entry = vpcs[vpc_key].setdefault("gatewayEndpoints", {
                "defaultPolicy": "OpenAccess", "endpoints": [],
            })
        else:
            entry = vpcs[vpc_key].setdefault("interfaceEndpoints", {
                "defaultPolicy": "OpenAccess",
                # LZA schema requires subnets. [REWORK] populate at task #9.
                "subnets": ["TODO-endpoint-subnet-a"],
                "endpoints": [],
            })
        entry["endpoints"].append({"service": _short_service(service)})
    return list(vpcs.values())


def _extract_tgws(tpl: dict[str, Any]) -> list[dict[str, Any]]:
    tgws: list[dict[str, Any]] = []
    for lid, res in resource_iter(tpl):
        if res.get("Type") != "AWS::EC2::TransitGateway":
            continue
        p = res["Properties"]
        asn = resolve_ref(p.get("AmazonSideAsn"), tpl)
        rts = []
        for rlid, r in resource_iter(tpl):
            if r.get("Type") == "AWS::EC2::TransitGatewayRouteTable":
                rname = _tag(r["Properties"], "Name", rlid)
                rts.append({"name": rname if isinstance(rname, str) else rlid, "routes": []})
        tgws.append({
            "name": f"{ACCELERATOR_PREFIX}-{HOME_REGION}-tgw",
            "account": NETWORK_ACCOUNT,
            "region": HOME_REGION,
            "asn": asn if isinstance(asn, int) else TGW_ASN,
            "dnsSupport": "enable",
            "vpnEcmpSupport": "enable",
            "defaultRouteTableAssociation": "disable",
            "defaultRouteTablePropagation": "disable",
            "autoAcceptSharingAttachments":
                "enable" if p.get("AutoAcceptSharedAttachments") == "enable" else "disable",
            "shareTargets": {"organizationalUnits": SPOKE_VPC_TARGET_OUS},
            "routeTables": rts,
        })
    return tgws


def _extract_nfw(tpl: dict[str, Any], cov: Coverage, src: str) -> dict[str, Any]:
    """Emit centralNetworkServices.networkFirewall stub."""
    policies: list[dict[str, Any]] = []
    firewalls: list[dict[str, Any]] = []
    for lid, res in resource_iter(tpl):
        rt = res.get("Type", "")
        if rt == "AWS::NetworkFirewall::FirewallPolicy":
            p = res["Properties"]
            fp_name = resolve_ref(p.get("FirewallPolicyName"), tpl)
            if not isinstance(fp_name, str):
                fp_name = f"{ACCELERATOR_PREFIX}-strict-fw-policy"
            policies.append({
                "name": fp_name,
                "regions": [HOME_REGION],
                "firewallPolicy": {
                    "statelessDefaultActions": ["aws:forward_to_sfe"],
                    "statelessFragmentDefaultActions": ["aws:forward_to_sfe"],
                    "statefulRuleGroups": [
                        {"name": f"{ACCELERATOR_PREFIX}-suricata-rules"}
                    ],
                },
                "shareTargets": {"organizationalUnits": SPOKE_VPC_TARGET_OUS},
            })
            cov.map(src, lid, f"centralNetworkServices.networkFirewall.policies[{fp_name}]")
        elif rt == "AWS::NetworkFirewall::Firewall":
            # SLZ NFW is deployed into NetworkInspection VPC's `TgwAttach{A,B,C}` subnets
            # per SLZ Mapping convention. LZA firewall inherits region from vpc.
            firewalls.append({
                "name": f"{ACCELERATOR_PREFIX}-{HOME_REGION}-firewall",
                "firewallPolicy": policies[0]["name"] if policies else "",
                "vpc": f"{ACCELERATOR_PREFIX}-NetworkInspection",
                "subnets": [
                    "NetworkInspectionTgwAttachA",
                    "NetworkInspectionTgwAttachB",
                    "NetworkInspectionTgwAttachC",
                ],
            })
            cov.map(src, lid, "centralNetworkServices.networkFirewall.firewalls[]")
        elif rt == "AWS::NetworkFirewall::LoggingConfiguration":
            cov.map(src, lid, "networkFirewall logging (per-firewall config)")
    # Copy Suricata rules file verbatim
    rules_src = SLZ_CFN / "network" / "firewall-suricata-rules.txt"
    if rules_src.exists():
        rules_dst = OUT_DIR / "firewall-rules" / "suricata-rules.txt"
        rules_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(rules_src, rules_dst)
        cov.map(str(rules_src), "<file>", "copied verbatim → firewall-rules/suricata-rules.txt")
    return {
        "firewalls": firewalls,
        "policies": policies,
        "rules": [
            {
                "name": f"{ACCELERATOR_PREFIX}-suricata-rules",
                "regions": [HOME_REGION],
                "capacity": 1000,
                "type": "STATEFUL",
                "ruleGroup": {
                    "rulesSource": {
                        "rulesFile": "firewall-rules/suricata-rules.txt",
                    },
                },
                "shareTargets": {"organizationalUnits": SPOKE_VPC_TARGET_OUS},
            }
        ],
    }


def _extract_ram_shares(tpl: dict[str, Any], cov: Coverage, src: str) -> None:
    """RAM shares are represented on the TGW's shareTargets in LZA; log for reviewer."""
    for lid, res in resource_iter(tpl):
        if res.get("Type") == "AWS::RAM::ResourceShare":
            cov.map(src, lid, "modeled via TGW.shareTargets (LZA convention)")


def _extract_flow_logs(tpl: dict[str, Any], cov: Coverage, src: str) -> None:
    for lid, res in resource_iter(tpl):
        if res.get("Type") == "AWS::EC2::FlowLog":
            cov.map(src, lid, "VPC flow logs (folded into vpcFlowLogs config)")


def _extract_spoke_template(tpl: dict[str, Any]) -> dict[str, Any]:
    """Turn lz-account-vpc-template.yaml into a vpcTemplate entry.

    Extracts CIDR + 3-AZ subnet naming pattern. Detailed route/NACL wiring
    left to reviewer.
    """
    vpc_props: dict[str, Any] = {}
    subnets: list[dict[str, Any]] = []
    for lid, res in resource_iter(tpl):
        rt = res.get("Type", "")
        if rt == "AWS::EC2::VPC":
            p = res["Properties"]
            cidr = resolve_ref(p.get("CidrBlock"), tpl)
            vpc_props["cidrs"] = [cidr] if isinstance(cidr, str) else []
        elif rt == "AWS::EC2::Subnet":
            p = res["Properties"]
            az = resolve_ref(p.get("AvailabilityZone"), tpl)
            cidr = resolve_ref(p.get("CidrBlock"), tpl)
            name = resolve_ref(_tag(p, "Name", lid), tpl)
            sn = name if isinstance(name, str) else lid
            resolved_az = az if isinstance(az, str) and az else _az_from_name(sn)
            if not resolved_az:
                resolved_az = "a"
            subnets.append({
                "name": sn,
                "availabilityZone": resolved_az,
                "ipv4CidrBlock": cidr if isinstance(cidr, str) else "",
                "routeTable": "TODO-rt",
            })
    return {
        "name": f"{ACCELERATOR_PREFIX}-spoke-vpc",
        "region": HOME_REGION,
        "deploymentTargets": {"organizationalUnits": SPOKE_VPC_TARGET_OUS},
        "cidrs": vpc_props.get("cidrs", []),
        "enableDnsHostnames": True,
        "enableDnsSupport": True,
        "subnets": subnets,
    }


def build_network_config() -> Coverage:
    cov = Coverage()
    central_tpl = load_cfn(SLZ_CFN / NETWORK_SOURCES["central"])
    spoke_tpl = load_cfn(SLZ_CFN / NETWORK_SOURCES["spoke"])

    vpcs = _extract_vpcs(central_tpl)
    tgws = _extract_tgws(central_tpl)
    nfw = _extract_nfw(central_tpl, cov, NETWORK_SOURCES["central"])
    _extract_ram_shares(central_tpl, cov, NETWORK_SOURCES["central"])
    _extract_flow_logs(central_tpl, cov, NETWORK_SOURCES["central"])
    spoke = _extract_spoke_template(spoke_tpl)

    # Report coverage for the central resources we recognized structurally
    for lid, res in resource_iter(central_tpl):
        rt = res.get("Type", "")
        if rt == "AWS::EC2::VPC":
            cov.map(NETWORK_SOURCES["central"], lid, "vpcs[]")
        elif rt == "AWS::EC2::Subnet":
            cov.map(NETWORK_SOURCES["central"], lid, "vpcs[].subnets[]")
        elif rt == "AWS::EC2::VPCEndpoint":
            cov.map(NETWORK_SOURCES["central"], lid, "vpcs[].interfaceEndpoints[]")
        elif rt == "AWS::EC2::TransitGateway":
            cov.map(NETWORK_SOURCES["central"], lid, "transitGateways[]")
        elif rt == "AWS::EC2::TransitGatewayRouteTable":
            cov.map(NETWORK_SOURCES["central"], lid, "transitGateways[].routeTables[]")
        elif rt == "AWS::RAM::ResourceShare":
            pass  # already logged
        elif rt in STRUCTURAL_TYPES:
            cov.unmap(NETWORK_SOURCES["central"], lid,
                      f"[REWORK] SLZ CFN {rt} — LZA models this declaratively per-VPC/subnet",
                      hint="Hand-port routing/NACL wiring during task #9 review")
        elif rt in BACKING_TYPES:
            cov.drop(NETWORK_SOURCES["central"], lid, f"engine-managed backing infra ({rt})")
        elif rt.startswith("AWS::NetworkFirewall"):
            pass  # already logged
    for lid, res in resource_iter(spoke_tpl):
        rt = res.get("Type", "")
        if rt == "AWS::EC2::VPC":
            cov.map(NETWORK_SOURCES["spoke"], lid, "vpcTemplates[]")
        elif rt == "AWS::EC2::Subnet":
            cov.map(NETWORK_SOURCES["spoke"], lid, "vpcTemplates[].subnets[]")
        elif rt in STRUCTURAL_TYPES:
            cov.unmap(NETWORK_SOURCES["spoke"], lid,
                      f"[REWORK] SLZ CFN {rt}",
                      hint="Hand-port on spoke template during task #9 review")
        elif rt in BACKING_TYPES:
            cov.drop(NETWORK_SOURCES["spoke"], lid, f"engine-managed backing infra ({rt})")

    # Emit stub "OpenAccess" endpoint policy referenced by every VPC endpoint's
    # defaultPolicy. Reviewer authors real policy body under
    # vpc-endpoint-policies/open-access.json.
    open_policy_path = "vpc-endpoint-policies/open-access.json"
    (OUT_DIR / open_policy_path).parent.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / open_policy_path).write_text(
        '{\n  "Version": "2012-10-17",\n  "Statement": [\n'
        '    {"Effect": "Allow", "Principal": "*", "Action": "*", "Resource": "*"}\n'
        '  ]\n}\n'
    )
    network_config: dict[str, Any] = {
        "defaultVpc": {"delete": True, "excludeAccounts": []},
        "endpointPolicies": [{"name": "OpenAccess", "document": open_policy_path}],
        "transitGateways": tgws,
        "vpcs": vpcs,
        "vpcTemplates": [spoke],
        "centralNetworkServices": {
            "delegatedAdminAccount": NETWORK_ACCOUNT,
            "networkFirewall": nfw,
        },
        "vpcFlowLogs": {
            "trafficType": "ALL",
            "maxAggregationInterval": 600,
            "destinations": ["s3", "cloud-watch-logs"],
            "defaultFormat": True,
            "customFields": [],
        },
    }
    header = (
        "Generated by converter L1 (network domain) — PARTIAL EXTRACTION.\n"
        "High-level structure only. Route tables, NACL entries, subnet\n"
        "route-table associations, NAT/IGW wiring, TGW static routes and\n"
        "attachment→routeTable pinning were NOT mechanically translated —\n"
        "SLZ CFN resource-level semantics do not map 1:1 onto LZA schema.\n"
        "Hand-port + verify against sources during task #9 review:\n"
        "  - lz-central-network.json (routing, NACLs, NFW subnet placement)\n"
        "  - lz-account-vpc-template.yaml (spoke subnet routing + NACLs)\n"
        "Suricata rules file copied verbatim to firewall-rules/suricata-rules.txt."
    )
    write_yaml(OUT_DIR / "network-config.yaml", network_config, header=header)
    return cov
