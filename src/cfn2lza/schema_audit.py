"""Schema audit — validate emitted UC YAML against LZA JSON schemas.

Fetches schemas from awslabs/landing-zone-accelerator-on-aws via `gh api`,
caches in .schemas/, validates each of the 8 emitted YAMLs against its
corresponding schema's root definition. Reports errors per file.
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path

import yaml
from jsonschema import Draft7Validator, RefResolver

from .common import OUT_DIR, REPORTS_DIR

# Cache in user's home; portable across install locations. Overridable via env.
import os as _os
SCHEMA_CACHE = Path(
    _os.environ.get("CFN2LZA_SCHEMA_CACHE")
    or (Path.home() / ".cache" / "cfn2lza" / "schemas")
)
LZA_REPO = "awslabs/landing-zone-accelerator-on-aws"
LZA_SCHEMA_PATH = "source/packages/@aws-accelerator/config/lib/schemas"

SCHEMAS = {
    "organization-config.yaml": ("organization-config.json", "IOrganizationConfig"),
    "security-config.yaml": ("security-config.json", "ISecurityConfig"),
    "iam-config.yaml": ("iam-config.json", "IIamConfig"),
    "global-config.yaml": ("global-config.json", "IGlobalConfig"),
    "network-config.yaml": ("network-config.json", "INetworkConfig"),
    "accounts-config.yaml": ("accounts-config.json", "IAccountsConfig"),
    "replacements-config.yaml": ("replacements-config.json", "IReplacementsConfig"),
    "customizations-config.yaml": ("customizations-config.json", "ICustomizationsConfig"),
}


def _fetch_schema(name: str) -> dict:
    cached = SCHEMA_CACHE / name
    if not cached.exists():
        SCHEMA_CACHE.mkdir(parents=True, exist_ok=True)
        out = subprocess.check_output(
            ["gh", "api", f"repos/{LZA_REPO}/contents/{LZA_SCHEMA_PATH}/{name}"],
            text=True,
        )
        content = json.loads(out)["content"]
        cached.write_bytes(base64.b64decode(content))
    return json.loads(cached.read_text())


def _load_yaml(path: Path):
    class SloppyLoader(yaml.SafeLoader):
        pass

    # Config YAMLs may contain {{ token }} which is not YAML but templated strings.
    # Load with defaults; treat unresolved tokens as plain strings.
    return yaml.load(path.read_text(), Loader=SloppyLoader)


def _validate(file_name: str, schema_file: str, root_def: str) -> tuple[int, list[str]]:
    schema = _fetch_schema(schema_file)
    root = {"$ref": f"#/definitions/{root_def}", **{k: v for k, v in schema.items() if k != "properties"}}
    # Use RefResolver so $refs to other definitions resolve
    resolver = RefResolver.from_schema(schema)
    validator = Draft7Validator(root, resolver=resolver)
    doc = _load_yaml(OUT_DIR / file_name)
    errors = []
    for e in sorted(validator.iter_errors(doc), key=lambda x: list(x.path)):
        loc = ".".join(str(p) for p in e.path) or "<root>"
        errors.append(f"{loc}: {e.message}")
    return len(errors), errors


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report = REPORTS_DIR / "schema-audit.md"
    lines = ["# Schema audit", "",
             f"Validated against LZA schemas from `{LZA_REPO}`.", ""]
    total_errors = 0
    for yaml_file, (schema_file, root_def) in SCHEMAS.items():
        try:
            n, errs = _validate(yaml_file, schema_file, root_def)
        except Exception as exc:
            lines += [f"## ❌ {yaml_file}", "", f"- audit-failed: {exc}", ""]
            total_errors += 1
            continue
        emoji = "✅" if n == 0 else "❌"
        lines += [f"## {emoji} {yaml_file}", "",
                  f"- schema: `{schema_file}#/definitions/{root_def}`",
                  f"- errors: {n}", ""]
        if errs:
            lines += ["```"]
            lines += errs[:50]
            if len(errs) > 50:
                lines += [f"... ({len(errs)-50} more truncated)"]
            lines += ["```", ""]
        total_errors += n
    lines += ["---", f"**Total errors: {total_errors}**"]
    report.write_text("\n".join(lines) + "\n")
    print(f"schema audit → {report}  (total_errors={total_errors})")
    return 0 if total_errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
