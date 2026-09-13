"""Security-domain mappers.

[GEN] handlers dispatch on CFN resource Type. Custom::* handlers are named for AWS
        idioms not Malaysia specifics; reusable if another LZ uses the same custom
        resources.
[MY] source file list + delegated admin account name live in profile.

SLZ uses Custom::* CFN resources backed by Lambdas to configure account-level
security settings (password policy, EBS encryption, S3 BPA, SSM prefs, GuardDuty
delegation, security-service delegation). LZA UC exposes these as first-class fields;
the backing Lambdas/Roles/LogGroups are engine-managed and dropped.
"""
from __future__ import annotations

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
    DELEGATED_SECURITY_ADMIN,
    HOME_REGION,
    SECURITY_SOURCES,
)


# Resource types that are backing infra for Custom::* resources — engine handles them.
BACKING_TYPES = {
    "AWS::Lambda::Function",
    "AWS::IAM::Role",
    "AWS::Logs::LogGroup",
    "AWS::SNS::TopicPolicy",
    "AWS::Events::Rule",
}

# Whole-file overrides: these SLZ files have no first-class LZA UC equivalent and
# must be wired via customizations-config.yaml. Register once + suppress per-resource
# unmapped noise for anything not already recognized as backing infra.
FILE_TO_CUSTOMIZATIONS = {
    "lz-audit-guardduty-notifications.yaml": (
        "guardduty-findings-notifications",
        "GuardDuty findings → EventBridge → SNS → email subscriptions. "
        "No first-class LZA UC field. Passthrough entire template.",
    ),
}
# KMS keys created inside per-file scope back the custom resource / lambda logging;
# real org-wide keys live in lz-organization-kms-iam.json (handled separately).
BACKING_KMS_TYPES = {"AWS::KMS::Key", "AWS::KMS::Alias"}


def _s(v: Any) -> Any:
    """Cast CFN string 'true'/'True'/'false' to bool; leave others as-is."""
    if isinstance(v, str) and v.lower() in ("true", "false"):
        return v.lower() == "true"
    return v


def _resolve(val: Any, tpl: dict[str, Any]) -> Any:
    """Resolve Ref to param default, then cast bools."""
    return _s(resolve_ref(val, tpl))


# ----- Custom::* handlers --------------------------------------------------


def _h_password_policy(props: dict[str, Any], tpl: dict[str, Any]) -> dict[str, Any]:
    r = lambda k: _resolve(props.get(k), tpl)
    return {
        "iamPasswordPolicy": {
            "minimumPasswordLength": r("MinimumPasswordLength"),
            "requireSymbols": r("RequireSymbols"),
            "requireNumbers": r("RequireNumbers"),
            "requireUppercaseCharacters": r("RequireUppercaseCharacters"),
            "requireLowercaseCharacters": r("RequireLowercaseCharacters"),
            "maxPasswordAge": r("MaxPasswordAge"),
            "passwordReusePrevention": r("PasswordReusePrevention"),
            "allowUsersToChangePassword": True,
            "hardExpiry": False,
        }
    }


def _h_s3_bpa(props: dict[str, Any], tpl: dict[str, Any]) -> dict[str, Any]:
    r = lambda k: _resolve(props.get(k), tpl)
    return {
        "centralSecurityServices.s3PublicAccessBlock": {
            "enable": all(r(k) for k in ("BlockPublicAcls", "BlockPublicPolicy",
                                          "IgnorePublicAcls", "RestrictPublicBuckets")),
            "excludeAccounts": [],
        }
    }


def _h_ebs_encryption(props: dict[str, Any], tpl: dict[str, Any]) -> dict[str, Any]:
    return {
        "centralSecurityServices.ebsDefaultVolumeEncryption": {
            "enable": _resolve(props.get("EbsDefaultEncryption"), tpl),
            "excludeRegions": [],
        }
    }


def _h_ssm_session(props: dict[str, Any], tpl: dict[str, Any]) -> dict[str, Any]:
    # SLZ SSM Session Preferences maps to global-config.yaml logging.sessionManager
    # (not security-config) — record as a note for the global domain mapper.
    r = lambda k: _resolve(props.get(k), tpl)
    return {
        "_defer_to_global": {
            "sessionManager": {
                "sendToCloudWatchLogs": True,
                "sendToS3": True,
                "idleTimeoutMinutes": r("IdleTimeout"),
                "maxSessionDurationMinutes": r("MaxDuration"),
                "runAsDefaultUser": None,
                "attachPolicyToIamRoles": [],
            }
        }
    }


def _h_guardduty(props: dict[str, Any], tpl: dict[str, Any]) -> dict[str, Any]:
    r = lambda k: _resolve(props.get(k), tpl)
    return {
        "centralSecurityServices.guardduty": {
            "enable": True,
            "excludeRegions": [],
            "s3Protection": {"enable": r("S3Protection"), "excludeRegions": []},
            "eksProtection": {"enable": r("EKSAuditLog"), "excludeRegions": []},
            "ec2Protection": {
                "enable": r("MalwareProtectionEC2"),
                "keepSnapshots": False,
                "excludeRegions": [],
            },
            "rdsProtection": {"enable": r("RDSProtection"), "excludeRegions": []},
            "lambdaProtection": {"enable": r("LambdaProtection"), "excludeRegions": []},
            "exportConfiguration": {
                "enable": True,
                "overrideExisting": False,
                "destinationType": "S3",
                "exportFrequency": "FIFTEEN_MINUTES",
            },
        }
    }


def _h_access_analyzer(props: dict[str, Any], tpl: dict[str, Any]) -> dict[str, Any]:
    # AWS::AccessAnalyzer::Analyzer resource type (not Custom::*)
    return {"accessAnalyzer": {"enable": True}}


def _h_ss_delegation(props: dict[str, Any], tpl: dict[str, Any]) -> dict[str, Any]:
    # LZA handles delegation via centralSecurityServices.delegatedAdminAccount;
    # nothing to emit beyond confirming the default. Return sentinel for reporting.
    return {"_ack": f"delegated to {DELEGATED_SECURITY_ADMIN}"}


def _h_ssm_dhmc(props: dict[str, Any], tpl: dict[str, Any]) -> dict[str, Any]:
    """SSM Default Host Management → customizations passthrough (no UC field)."""
    from .customizations import register_ssm_dhmc
    register_ssm_dhmc()
    return {"_customizations": "ssm-default-host-management"}


def _h_fms_ipam_delegation(props: dict[str, Any], tpl: dict[str, Any]) -> dict[str, Any]:
    # FMS delegation lives at security-config.centralSecurityServices (implicit),
    # IPAM delegation lives at network-config. Emit both as deferred notes.
    return {
        "_defer_to_network": {
            "centralNetworkServices.delegatedAdminAccount": "Network",
        },
        "_ack": "FMS + IPAM admin delegation acknowledged",
    }


CUSTOM_HANDLERS = {
    "Custom::SetPasswordPolicy": _h_password_policy,
    "Custom::S3PublicAccessBlock": _h_s3_bpa,
    "Custom::EC2DataProtectionSecurity": _h_ebs_encryption,
    "Custom::SSMSessionPreferences": _h_ssm_session,
    "Custom::SSMDefaultHostManagement": _h_ssm_dhmc,
    "Custom::GuardDutyConfiguration": _h_guardduty,
    "Custom::SecurityServicesAdminDelegation": _h_ss_delegation,
    "Custom::AdminDelegation": _h_fms_ipam_delegation,
    "AWS::AccessAnalyzer::Analyzer": _h_access_analyzer,
}

# Custom types recognised as intentionally unmapped (no first-class LZA field).
UNMAPPED_CUSTOM = {
    "Custom::SNSSubscriptions": (
        "GuardDuty finding notifications (SNS + EventBridge) have no first-class "
        "LZA UC field. Route via customizations-config.yaml passthrough."
    ),
}


def _merge(target: dict[str, Any], patch: dict[str, Any]) -> None:
    """Merge patch into target. Supports dotted keys like 'a.b.c' for nested placement."""
    for k, v in patch.items():
        if k.startswith("_"):
            continue
        if "." in k:
            parts = k.split(".")
            cur = target
            for p in parts[:-1]:
                cur = cur.setdefault(p, {})
            cur[parts[-1]] = v
        else:
            if isinstance(v, dict) and isinstance(target.get(k), dict):
                target[k].update(v)
            else:
                target[k] = v


def _collect_kms(cov: Coverage) -> list[dict[str, Any]]:
    """Extract real org-wide KMS CMKs from lz-organization-kms-iam.json.

    Backing-infra KMS keys (per-file) are dropped elsewhere.
    """
    src = SECURITY_SOURCES["org_kms"]
    tpl = load_cfn(SLZ_CFN / src)
    keys: list[dict[str, Any]] = []
    # Build alias-by-key map so we can name the KeyConfig entries meaningfully
    aliases: dict[str, str] = {}
    for lid, res in resource_iter(tpl):
        if res.get("Type") == "AWS::KMS::Alias":
            props = res["Properties"]
            target = props.get("TargetKeyId")
            alias_name = resolve_ref(props.get("AliasName", ""), tpl)
            if not isinstance(alias_name, str):
                alias_name = ""
            if isinstance(target, dict) and "Ref" in target:
                aliases[target["Ref"]] = alias_name
    for lid, res in resource_iter(tpl):
        if res.get("Type") == "AWS::KMS::Key":
            props = res["Properties"]
            desc = resolve_ref(props.get("Description", lid), tpl)
            if not isinstance(desc, str):
                desc = lid
            alias = aliases.get(lid, "")
            name = alias.replace("alias/", "").replace("/", "-") or lid.lower()
            keys.append({
                "name": f"{ACCELERATOR_PREFIX}-{name}",
                "alias": alias.replace("alias/", "") if alias else f"{name}-alias",
                "description": desc if isinstance(desc, str) else lid,
                "policy": f"kms-policies/{name}.json",
                "deploymentTargets": {"organizationalUnits": ["Root"]},
            })
            # Persist key policy body (best-effort — may contain intrinsics)
            key_policy = props.get("KeyPolicy")
            if key_policy is not None:
                from ..common import write_json
                write_json(OUT_DIR / f"kms-policies/{name}.json", key_policy)
            cov.map(src, lid, f"keyManagementService.keySets[{name}]")
        elif res.get("Type") == "AWS::KMS::Alias":
            cov.map(src, lid, "attached to KeyConfig (implicit)")
        elif res.get("Type") == "AWS::IAM::Role":
            cov.drop(src, lid, "IAM role for KMS key access — engine-managed under LZA")
    return keys


def build_security_config() -> Coverage:
    cov = Coverage()
    security: dict[str, Any] = {
        "centralSecurityServices": {
            "delegatedAdminAccount": DELEGATED_SECURITY_ADMIN,
            "ebsDefaultVolumeEncryption": {"enable": False, "excludeRegions": []},
            "s3PublicAccessBlock": {"enable": False, "excludeAccounts": []},
            "scpRevertChangesConfig": {"enable": True},
            "snsSubscriptions": [],
            "guardduty": {"enable": False, "excludeRegions": []},
            "securityHub": {"enable": False, "excludeRegions": [], "standards": []},
            "ssmAutomation": {"excludeRegions": [], "documentSets": []},
        },
        "accessAnalyzer": {"enable": False},
        "iamPasswordPolicy": {},
        "awsConfig": {"enableConfigurationRecorder": False, "ruleSets": []},
        "cloudWatch": {"metricSets": [], "alarmSets": []},
        "keyManagementService": {"keySets": []},
    }
    global_deferrals: list[dict[str, Any]] = []
    network_deferrals: list[dict[str, Any]] = []

    for key, src in SECURITY_SOURCES.items():
        if key == "org_kms":
            continue  # handled separately below
        tpl = load_cfn(SLZ_CFN / src)

        # Whole-file passthrough (no first-class UC equivalence for the bundle)
        if src in FILE_TO_CUSTOMIZATIONS:
            from .customizations import register_file_passthrough
            stem, note = FILE_TO_CUSTOMIZATIONS[src]
            register_file_passthrough(stem, src, note)
            cov.map(src, "<file>",
                    f"customizations-config.yaml passthrough ({stem})")
            for lid, _res in resource_iter(tpl):
                cov.drop(src, lid, "included in whole-file customizations passthrough")
            continue

        for lid, res in resource_iter(tpl):
            rtype = res.get("Type", "")
            props = res.get("Properties", {})
            if rtype in CUSTOM_HANDLERS:
                patch = CUSTOM_HANDLERS[rtype](props, tpl) or {}
                _merge(security, patch)
                if "_defer_to_global" in patch:
                    global_deferrals.append(patch["_defer_to_global"])
                if "_defer_to_network" in patch:
                    network_deferrals.append(patch["_defer_to_network"])
                emitted = ",".join(k for k in patch if not k.startswith("_")) or "(ack)"
                cov.map(src, lid, f"{rtype} -> {emitted}")
                continue
            if rtype in UNMAPPED_CUSTOM:
                cov.unmap(src, lid, UNMAPPED_CUSTOM[rtype],
                          hint=f"Type={rtype}; consider customizations-config.yaml passthrough")
                continue
            if rtype in BACKING_TYPES or rtype in BACKING_KMS_TYPES:
                cov.drop(src, lid, f"engine-managed backing infra ({rtype})")
                continue
            cov.unmap(src, lid, f"unhandled resource type {rtype}")

    # KMS pass (real org-wide keys, not backing infra)
    security["keyManagementService"]["keySets"] = _collect_kms(cov)

    # Persist deferrals for downstream mappers
    if global_deferrals:
        from ..common import write_json
        write_json(OUT_DIR / "_deferrals/global.json", global_deferrals)
    if network_deferrals:
        from ..common import write_json
        write_json(OUT_DIR / "_deferrals/network.json", network_deferrals)

    header = (
        "Generated by converter L1 (security domain). Sources:\n"
        "  lz-account-baseline.yaml, lz-audit-guardduty*.yaml,\n"
        "  lz-delegate-security-services.yaml, lz-delegate-firewall-manager-ipam.yaml,\n"
        "  lz-audit-access-analyzer.json, lz-organization-kms-iam.json.\n"
        "SSM session prefs deferred to global-config (see _deferrals/global.json).\n"
        "IPAM delegation deferred to network-config (see _deferrals/network.json)."
    )
    write_yaml(OUT_DIR / "security-config.yaml", security, header=header)
    return cov
