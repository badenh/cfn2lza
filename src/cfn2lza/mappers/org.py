"""Org-domain mappers.

[GEN] handlers below are pure CFN-resource-type → UC-fragment. Reusable.
[MY] arrangement (which files, which default OU targets) lives in profile.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..common import (
    Coverage,
    OUT_DIR,
    SLZ_CFN,
    cfn_param_default,
    load_cfn,
    resolve_ref,
    resource_iter,
    write_json,
    write_yaml,
)
from ..profile import (
    ACCELERATOR_PREFIX,
    AI_OPTOUT_TARGET,
    DECLARATIVE_EC2_TARGET_OUS,
    DEFAULT_RCP_TARGET_OUS,
    DEFAULT_SCP_TARGET_OUS,
    ORG_SOURCES,
)


# LZA UC policy-type dispatch by CFN Type field
POLICY_TYPE_MAP = {
    "SERVICE_CONTROL_POLICY": ("serviceControlPolicies", "service-control-policies"),
    "RESOURCE_CONTROL_POLICY": ("resourceControlPolicies", "rcp-policies"),
    "AISERVICES_OPT_OUT_POLICY": ("aiServicesOptOutPolicy", None),
    "DECLARATIVE_POLICY_EC2": ("declarativePolicies", "declarative-policies"),
}


def _slug(name: str) -> str:
    return name.lower().replace(" ", "-").replace("_", "-")


def _extract_ou_tree(cov: Coverage) -> list[dict[str, Any]]:
    """[GEN] Walk AWS::Organizations::OrganizationalUnit resources into LZA OU list.

    Handles nested OUs via ParentId Ref to another OU logical id.
    """
    src = ORG_SOURCES["ou_tree"]
    tpl = load_cfn(SLZ_CFN / src)

    # Build logical_id -> (name, parent_logical_id_or_ROOT)
    nodes: dict[str, tuple[str, str]] = {}
    for lid, res in resource_iter(tpl):
        if res.get("Type") != "AWS::Organizations::OrganizationalUnit":
            cov.unmap(src, lid, f"unexpected type {res.get('Type')}")
            continue
        props = res["Properties"]
        name = resolve_ref(props["Name"], tpl)
        parent = props["ParentId"]
        if isinstance(parent, dict) and "Ref" in parent:
            parent_ref = parent["Ref"]
            # Ref to OrganizationRootId parameter = top level
            if parent_ref in tpl.get("Parameters", {}):
                parent_key = "ROOT"
            else:
                parent_key = parent_ref
        else:
            parent_key = "ROOT"
        nodes[lid] = (name, parent_key)
        cov.map(src, lid, f"organizationalUnits[{name}]")

    # Resolve nested names: LZA uses "Parent/Child" paths
    def path_for(lid: str) -> str:
        name, parent = nodes[lid]
        if parent == "ROOT":
            return name
        return f"{path_for(parent)}/{name}"

    ous: list[dict[str, Any]] = []
    for lid in nodes:
        entry: dict[str, Any] = {"name": path_for(lid)}
        # SLZ Suspended OU semantically matches LZA ignore:true convention
        if nodes[lid][0].lower() == "suspended":
            entry["ignore"] = True
        ous.append(entry)
    # Stable ordering: top-level first, then depth
    ous.sort(key=lambda e: (e["name"].count("/"), e["name"]))
    return ous


def _extract_policies(cov: Coverage) -> dict[str, list[dict[str, Any]]]:
    """[GEN] Extract AWS::Organizations::Policy resources across SLZ policy files.

    Returns dict keyed by LZA org-config field name, e.g.:
      {"serviceControlPolicies": [...], "resourceControlPolicies": [...],
       "declarativePolicies": [...], "aiServicesOptOutPolicy": {...}}
    Policy JSON bodies are written to out/ subfolders.
    """
    out: dict[str, list[dict[str, Any]]] = {
        "serviceControlPolicies": [],
        "resourceControlPolicies": [],
        "declarativePolicies": [],
    }
    for key in ("scp_guardrails", "scp_approved_services", "rcp_guardrails", "ai_optout"):
        src = ORG_SOURCES[key]
        tpl = load_cfn(SLZ_CFN / src)
        for lid, res in resource_iter(tpl):
            if res.get("Type") != "AWS::Organizations::Policy":
                cov.unmap(src, lid, f"unexpected type {res.get('Type')}")
                continue
            props = res["Properties"]
            ptype = props.get("Type")
            if ptype not in POLICY_TYPE_MAP:
                cov.unmap(src, lid, f"unknown policy Type={ptype}")
                continue
            field, subfolder = POLICY_TYPE_MAP[ptype]

            name = resolve_ref(props.get("Name"), tpl) or lid
            description = resolve_ref(props.get("Description", ""), tpl)
            content = props["Content"]

            # AI opt-out has no first-class LZA UC field (verified against
            # awslabs/landing-zone-accelerator-on-aws organization-config schema).
            # Persist the policy body under customizations/ and flag as blocker
            # for reviewer to wire via customizations-config.yaml passthrough of
            # the AWS::Organizations::Policy CFN resource.
            if ptype == "AISERVICES_OPT_OUT_POLICY":
                from .customizations import register_ai_optout
                policy_path = f"customizations/aiservices-optout/{_slug(name)}.json"
                write_json(OUT_DIR / policy_path, content)
                register_ai_optout(policy_path, name)
                cov.map(
                    src,
                    lid,
                    f"customizations-config.yaml passthrough (Type=AISERVICES_OPT_OUT_POLICY)",
                )
                continue

            # Per-type deploymentTargets defaults (L2-resolved from SLZ readme
            # + lz-organization-guardrails.yaml nested-stack param wiring).
            if ptype == "SERVICE_CONTROL_POLICY":
                default_targets = DEFAULT_SCP_TARGET_OUS
            elif ptype == "RESOURCE_CONTROL_POLICY":
                default_targets = DEFAULT_RCP_TARGET_OUS
            elif ptype == "DECLARATIVE_POLICY_EC2":
                default_targets = DECLARATIVE_EC2_TARGET_OUS
            else:
                default_targets = DEFAULT_SCP_TARGET_OUS

            policy_path = f"{subfolder}/{_slug(name)}.json"
            write_json(OUT_DIR / policy_path, content)

            entry: dict[str, Any] = {
                "name": f"{ACCELERATOR_PREFIX}-{name}",
                "description": description,
                "policy": policy_path,
                "type": "customerManaged",
                "strategy": "deny-list",
                "deploymentTargets": {"organizationalUnits": list(default_targets)},
            }
            if ptype == "DECLARATIVE_POLICY_EC2":
                # DeclarativePolicyConfig: name/description/policy/deploymentTargets only
                entry.pop("type", None)
                entry.pop("strategy", None)
            elif ptype == "RESOURCE_CONTROL_POLICY":
                # ResourceControlPolicyConfig has strategy but no 'type' field
                entry.pop("type", None)
            out[field].append(entry)
            cov.map(
                src,
                lid,
                f"{field}[{name}] targets={default_targets} (L2-resolved)",
            )

    return {k: v for k, v in out.items() if v}


def build_organization_config() -> Coverage:
    cov = Coverage()
    ous = _extract_ou_tree(cov)
    policies = _extract_policies(cov)

    org_config: dict[str, Any] = {
        "enable": True,
        "organizationalUnits": ous,
        "quarantineNewAccounts": {
            "enable": False,  # SLZ has no quarantine SCP; leave off, L2 can enable
        },
        # Schema-required even when empty (LZA IOrganizationConfig).
        "taggingPolicies": [],
        "backupPolicies": [],
        "chatbotPolicies": [],
    }
    # Merge policy sections in LZA-expected key order
    for key in ("declarativePolicies", "resourceControlPolicies", "serviceControlPolicies"):
        if key in policies:
            org_config[key] = policies[key]

    header = (
        "Generated by converter L1 (org domain). Do not hand-edit generated blocks;\n"
        "re-run the pipeline. UNMAPPED items live in converter/unmapped/org.json.\n"
        "Source: sample-malaysia-secure-lz/cloudformation/lz-organization*.json"
    )
    write_yaml(OUT_DIR / "organization-config.yaml", org_config, header=header)
    return cov
