"""Thailand SLZ profile — source-specific conventions.

[TH] — Thailand SLZ. Cloned from `malaysia.py` and adjusted for TH divergences:

- Home region ap-southeast-7 (Thailand).
- Org-domain CFN templates live under `cloudformation/organization/` subdir
  (Malaysia had them at `cloudformation/` root). SOURCE_DIR still points at
  the `cloudformation/` root; the ORG_SOURCES values include the subdir.
- Everything else structurally matches Malaysia (same CFN filenames, same
  parameter names, same OU tree, same account roles).
"""
from __future__ import annotations

# Profile identity only. Paths come from CLI.
PROFILE_NAME = "thailand"
SOURCE_LZ_NAME = "sample-thailand-secure-lz"

ACCELERATOR_PREFIX = "THSLZ"
HOME_REGION = "ap-southeast-7"

# TH org templates are under cloudformation/organization/ (not root like MY).
ORG_SOURCES = {
    "ou_tree": "organization/lz-organization.json",
    "scp_guardrails": "organization/lz-organization-scp-guardrails.json",
    "scp_approved_services": "organization/lz-organization-scp-approved-services.json",
    "rcp_guardrails": "organization/lz-organization-rcp-guardrails.json",
    "ai_optout": "organization/lz-organization-ai-optout.json",
}

# Same OU shape as MY per readme feature list (Sandbox + Forensic still present).
DEFAULT_SCP_TARGET_OUS = [
    "Infrastructure",
    "Security",
    "Workloads",
    "Sandbox",
    "Forensic",
]
DEFAULT_RCP_TARGET_OUS = list(DEFAULT_SCP_TARGET_OUS)

DECLARATIVE_EC2_TARGET_OUS = ["Root"]
AI_OPTOUT_TARGET = "Root"


# Security domain sources — TH keeps these at cloudformation/ root, same as MY.
SECURITY_SOURCES = {
    "baseline": "lz-account-baseline.yaml",
    "guardduty": "lz-audit-guardduty.yaml",
    "guardduty_notify": "lz-audit-guardduty-notifications.yaml",
    "ss_delegation": "lz-delegate-security-services.yaml",
    "fms_ipam": "lz-delegate-firewall-manager-ipam.yaml",
    "access_analyzer": "lz-audit-access-analyzer.json",
    "org_kms": "organization/lz-organization-kms-iam.json",
}

DELEGATED_SECURITY_ADMIN = "Audit"


# IAM domain
IAM_SOURCES = {
    "idc_permission_sets": "lz-iam-idc-permissionsets.json",
}
IDENTITY_CENTER_NAME = "identityCenter1"
IDENTITY_CENTER_DELEGATED_ADMIN: str | None = None


# Global domain
# TH readme step 7 deploys FMS delegation in ap-southeast-7 + us-east-1 (us-east-1
# required for FMS admin registration).
ENABLED_REGIONS = [HOME_REGION, "us-east-1"]
MANAGEMENT_ACCOUNT_ACCESS_ROLE = "AWSControlTowerExecution"


# Network domain
NETWORK_SOURCES = {
    "central": "lz-central-network.json",
    "spoke": "lz-account-vpc-template.yaml",
}
NETWORK_ACCOUNT = "Network"
SPOKE_VPC_TARGET_OUS = [
    "Infrastructure",
    "Workloads",
    "Workloads/Production",
    "Workloads/NonProduction",
]
TGW_ASN = 65001


# Accounts. Same shape as MY per TH readme (SharedServices, CentralBackup, Network).
MANDATORY_ACCOUNTS = [
    ("Management", "Root", "AWS Organizations management account (existing)"),
    ("LogArchive", "Security", "Control Tower log archive account"),
    ("Audit", "Security", "Control Tower audit / security aggregator account"),
]
WORKLOAD_ACCOUNTS = [
    ("SharedServices", "Infrastructure",
     "Backup admin, IdC delegation, shared operations (TH readme step 4)"),
    ("CentralBackup", "Infrastructure",
     "Central AWS Backup vault"),
    ("Network", "Infrastructure",
     "Hub network account — TGW, NFW, VPC endpoints (lz-central-network.json)"),
]

# Bootstrap templates handled by LZA engine.
DROPPED_SOURCES = {
    "organization/lz-organization-setup.yaml": "engine-managed bootstrap",
    "lz-organization-setup.yaml": "engine-managed bootstrap",
    "organization/lz-organization-service-access.yaml": "engine-managed org service access",
    "organization/lz-organization-guardrails.yaml": "engine-managed guardrails wiring",
    "organization/lz-stackset-roles.yaml": "engine-managed StackSet roles",
}
