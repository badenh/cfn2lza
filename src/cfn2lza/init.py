"""`cfn2lza init` — scaffold a new profile file for a source LZ.

Copies the bundled template, substitutes PROFILE_NAME + SOURCE_LZ_NAME. With
`--sniff`, walks the source CFN directory and inserts best-effort guesses
for role→filename in ORG_SOURCES / SECURITY_SOURCES / NETWORK_SOURCES etc.,
each marked with a `# TODO(cfn2lza-init):` comment for user confirmation.

Sniff heuristics are deliberately shallow — a wrong guess is worse than no
guess. When ambiguous, the entry is omitted and the user gets a
`# TODO(sniff-unresolved):` note.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_TEMPLATE = Path(__file__).parent / "templates" / "profile.py.tmpl"

# Resource-type signatures for role sniffing. Keep small + high-precision.
_SNIFF_SIGNATURES: dict[str, dict[str, tuple[str, ...]]] = {
    "ORG_SOURCES": {
        "ou_tree": ("AWS::Organizations::OrganizationalUnit",),
        "scp_guardrails": ("AWS::Organizations::Policy",),
        "rcp_guardrails": ("AWS::Organizations::ResourcePolicy",),
    },
    "SECURITY_SOURCES": {
        "access_analyzer": ("AWS::AccessAnalyzer::Analyzer",),
        "org_kms": ("AWS::KMS::Key",),
    },
    "IAM_SOURCES": {
        "idc_permission_sets": ("AWS::SSO::PermissionSet",),
    },
    "NETWORK_SOURCES": {
        "central": ("AWS::EC2::TransitGateway", "AWS::NetworkFirewall::Firewall"),
        "spoke": ("AWS::EC2::VPC",),
    },
}


def _load_cfn_types(path: Path) -> set[str]:
    """Extract resource Type set from a CFN template. Best-effort; unrecognized files → empty."""
    try:
        text = path.read_text()
    except (OSError, UnicodeDecodeError):
        return set()
    if path.suffix.lower() == ".json":
        try:
            doc = json.loads(text)
        except json.JSONDecodeError:
            return set()
    else:
        try:
            import yaml
        except ImportError:
            return set()

        class _L(yaml.SafeLoader):
            pass

        for tag in ("Ref", "GetAtt", "Sub", "Join", "Select", "Split", "ImportValue",
                    "FindInMap", "Base64", "Cidr", "If", "Not", "Equals", "And", "Or",
                    "Condition", "GetAZs", "Transform", "ForEach"):
            _L.add_constructor(f"!{tag}", lambda l, n: None)
        try:
            doc = yaml.load(text, Loader=_L)
        except yaml.YAMLError:
            return set()
    if not isinstance(doc, dict):
        return set()
    types = set()
    for r in (doc.get("Resources") or {}).values():
        if isinstance(r, dict) and isinstance(r.get("Type"), str):
            types.add(r["Type"])
    return types


def _sniff(source_dir: Path) -> dict[str, dict[str, str]]:
    """Return {section: {role: filename}} best-effort assignments."""
    files_types: dict[Path, set[str]] = {}
    for p in source_dir.rglob("*"):
        if p.is_file() and p.suffix.lower() in (".json", ".yaml", ".yml"):
            files_types[p] = _load_cfn_types(p)

    result: dict[str, dict[str, str]] = {}
    for section, roles in _SNIFF_SIGNATURES.items():
        result[section] = {}
        for role, needed_types in roles.items():
            candidates = [
                p for p, ts in files_types.items() if all(t in ts for t in needed_types)
            ]
            if len(candidates) == 1:
                result[section][role] = str(candidates[0].relative_to(source_dir))
            elif len(candidates) > 1:
                # Ambiguous — pick shortest name as best heuristic + flag.
                pick = sorted(candidates, key=lambda p: len(p.name))[0]
                result[section][role] = (
                    f"{pick.relative_to(source_dir)}  # TODO(sniff-ambiguous): "
                    f"{len(candidates)} candidates matched"
                )
    return result


def _render_sniff(sniff_result: dict[str, dict[str, str]]) -> str:
    if not any(sniff_result.values()):
        return ""
    lines = ["", "# ---- Sniff results (review each entry) ----", ""]
    for section, roles in sniff_result.items():
        if not roles:
            lines.append(f"# {section}: no matches — fill in manually.")
            continue
        lines.append(f"{section} = {{")
        for role, val in roles.items():
            lines.append(f'    "{role}": "{val}",  # TODO(cfn2lza-init): confirm')
        lines.append("}")
        lines.append("")
    return "\n".join(lines)


def run(
    name: str,
    out: Path,
    source_dir: Path,
    sniff: bool,
) -> int:
    template = _TEMPLATE.read_text()
    body = (
        template
        .replace("{{PROFILE_NAME}}", name)
        .replace("{{SOURCE_LZ_NAME}}", source_dir.name)
    )
    if sniff:
        if not source_dir.is_dir():
            print(f"error: source-dir does not exist: {source_dir}")
            return 2
        body += _render_sniff(_sniff(source_dir))
    if out.exists():
        print(f"error: refuse to overwrite existing file: {out}")
        return 2
    out.write_text(body)
    print(f"[cfn2lza] wrote profile scaffold: {out}")
    print(f"[cfn2lza] next: edit {out}, then run:")
    print(f"          cfn2lza convert --profile {out} --source-dir {source_dir} --out-dir ./out")
    return 0
