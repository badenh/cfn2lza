"""Malaysia SLZ profile — source-specific conventions.

[MY] — everything here is Malaysia-SLZ-specific. Second variant = new profile file.
"""
from __future__ import annotations

# Profile identity only. SOURCE_DIR / OUT_DIR / REPORTS_DIR / UNMAPPED_DIR
# are supplied by CLI (`cfn2lza convert --source-dir ... --out-dir ...`);
# only source-LZ-shape constants live in this file.
PROFILE_NAME = "malaysia"
SOURCE_LZ_NAME = "sample-malaysia-secure-lz"

ACCELERATOR_PREFIX = "MYSLZ"
HOME_REGION = "ap-southeast-5"

# Which SLZ CFN files belong to the org-domain vertical slice.
ORG_SOURCES = {
    "ou_tree": "lz-organization.json",
    "scp_guardrails": "lz-organization-scp-guardrails.json",
    "scp_approved_services": "lz-organization-scp-approved-services.json",
    "rcp_guardrails": "lz-organization-rcp-guardrails.json",
    "ai_optout": "lz-organization-ai-optout.json",
}

# SLZ deploys policies with runtime TargetOrganizationalUnitIds params (comma list of
# OU IDs). SLZ readme deploy step 8 shows these are user-supplied at deploy.
# L2 default: all non-Suspended top-level OUs. Includes Sandbox + Forensic per SLZ
# tree so those OUs are not silently unprotected.
DEFAULT_SCP_TARGET_OUS = [
    "Infrastructure",
    "Security",
    "Workloads",
    "Sandbox",
    "Forensic",
]
DEFAULT_RCP_TARGET_OUS = list(DEFAULT_SCP_TARGET_OUS)

# SLZ nested-stack `lz-organization-guardrails.yaml` passes RootId via
# !ImportValue lz-organization-RootId for both declarative EC2 + AI opt-out.
DECLARATIVE_EC2_TARGET_OUS = ["Root"]
AI_OPTOUT_TARGET = "Root"


# Security domain sources
SECURITY_SOURCES = {
    "baseline": "lz-account-baseline.yaml",
    "guardduty": "lz-audit-guardduty.yaml",
    "guardduty_notify": "lz-audit-guardduty-notifications.yaml",
    "ss_delegation": "lz-delegate-security-services.yaml",
    "fms_ipam": "lz-delegate-firewall-manager-ipam.yaml",
    "access_analyzer": "lz-audit-access-analyzer.json",
    "org_kms": "lz-organization-kms-iam.json",
}

# SLZ readme step 7: Security Audit Admin Account = Control Tower audit account.
# LZA default account name for the audit account is 'Audit'.
DELEGATED_SECURITY_ADMIN = "Audit"


# IAM domain
IAM_SOURCES = {
    "idc_permission_sets": "lz-iam-idc-permissionsets.json",
}
IDENTITY_CENTER_NAME = "identityCenter1"
# SLZ delegates IdC to Management Account (Control Tower default); leave undefined
# to inherit CT default. Set to explicit account name if SLZ documents otherwise.
IDENTITY_CENTER_DELEGATED_ADMIN: str | None = None


# Global domain
# SLZ readme step 7 deploys FMS delegation StackSet in ap-southeast-5 + us-east-1
# (us-east-1 is required for FMS admin registration).
ENABLED_REGIONS = [HOME_REGION, "us-east-1"]
# Control Tower installs this role in every account it manages; SLZ SCP guardrails
# reference `arn:aws:iam::*:role/AWSControlTowerExecution` as the escape hatch.
MANAGEMENT_ACCOUNT_ACCESS_ROLE = "AWSControlTowerExecution"


# Network domain
NETWORK_SOURCES = {
    "central": "lz-central-network.json",
    "spoke": "lz-account-vpc-template.yaml",
}
NETWORK_ACCOUNT = "Network"
# SLZ shares TGW + NFW to workload OUs. Excludes Sandbox by convention (isolated).
SPOKE_VPC_TARGET_OUS = [
    "Infrastructure",
    "Workloads",
    "Workloads/Production",
    "Workloads/NonProduction",
]
# TGW ASN: SLZ CFN parameter `TransitGatewayASN` has no default; L2 pick private-ASN.
# 65001 is a common private-ASN choice within 64512-65534 range.
TGW_ASN = 65001


# Accounts (name, OU, purpose). LZA UC requires the three mandatory accounts;
# workload accounts inferred from SLZ readme steps 4/5/6 and network-config.
MANDATORY_ACCOUNTS = [
    ("Management", "Root", "AWS Organizations management account (existing)"),
    ("LogArchive", "Security", "Control Tower log archive account"),
    ("Audit", "Security", "Control Tower audit / security aggregator account"),
]
WORKLOAD_ACCOUNTS = [
    ("SharedServices", "Infrastructure",
     "Backup admin, delegated admin, shared operations (SLZ readme step 4)"),
    ("CentralBackup", "Infrastructure",
     "Central AWS Backup vault (SLZ readme step 5)"),
    ("Network", "Infrastructure",
     "Hub network account — TGW, NFW, VPC endpoints (lz-central-network.json)"),
]

# SLZ bootstrap templates handled by LZA engine — drop with reason.
DROPPED_SOURCES = {
    "lz-organization-setup.yaml": "engine-managed bootstrap",
    "lz-organization-service-access.yaml": "engine-managed org service access",
    "lz-organization-guardrails.yaml": "engine-managed guardrails wiring",
    "lz-stackset-roles.yaml": "engine-managed StackSet roles",
}
