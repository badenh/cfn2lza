"""Templated CONVERSION-SUMMARY.md generator.

Reads:
  - per-domain coverage report md files in REPORTS_DIR (line counts of
    "mapped / unmapped / dropped" from each)
  - REPORTS_DIR / "schema-audit.md" (parses total error line)
  - REPORTS_DIR / "engine-dry-run.md" (if present)
  - OUT_DIR listing (which YAMLs got produced)

Writes:
  - REPORTS_DIR / "CONVERSION-SUMMARY.md"

Deliberately mechanical. Hand-authored context (like "Malaysia CGSO
context...") stays out — this file just reports facts.
"""
from __future__ import annotations

import re
from pathlib import Path

from .common import OUT_DIR, REPORTS_DIR
from . import profile as _profile

_DOMAINS = ("org", "security", "iam", "global", "network", "accounts",
            "replacements", "customizations")

_COUNT_RE = re.compile(r"^- (mapped|unmapped|dropped): (\d+)$", re.MULTILINE)


def _read_counts(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    return {k: int(v) for k, v in _COUNT_RE.findall(path.read_text())}


def _read_schema_audit() -> tuple[int | None, list[str]]:
    p = Path(REPORTS_DIR) / "schema-audit.md"
    if not p.exists():
        return None, []
    text = p.read_text()
    m = re.search(r"\*\*Total errors: (\d+)\*\*", text)
    total = int(m.group(1)) if m else None
    files_ok = re.findall(r"^## (✅|❌) (\S+\.yaml)$", text, re.MULTILINE)
    return total, files_ok


def _emitted_yamls() -> list[str]:
    out = Path(OUT_DIR)
    if not out.exists():
        return []
    return sorted(p.name for p in out.glob("*.yaml"))


def render() -> Path:
    lines = [
        f"# Conversion summary — {getattr(_profile, 'PROFILE_NAME', '<profile>')}",
        "",
        f"**Source LZ:** `{getattr(_profile, 'SOURCE_LZ_NAME', '<unknown>')}`",
        f"**Output:** `{OUT_DIR}`",
        "",
        "## Coverage",
        "",
        "| Domain | Mapped | Unmapped | Dropped |",
        "|---|---:|---:|---:|",
    ]
    totals = {"mapped": 0, "unmapped": 0, "dropped": 0}
    for d in _DOMAINS:
        counts = _read_counts(Path(REPORTS_DIR) / f"{d}.md")
        m = counts.get("mapped", 0)
        u = counts.get("unmapped", 0)
        dr = counts.get("dropped", 0)
        totals["mapped"] += m
        totals["unmapped"] += u
        totals["dropped"] += dr
        lines.append(f"| {d} | {m} | {u} | {dr} |")
    lines.append(
        f"| **TOTAL** | **{totals['mapped']}** | **{totals['unmapped']}** | **{totals['dropped']}** |"
    )
    lines.append("")

    # Schema audit
    total, files_ok = _read_schema_audit()
    lines += ["## Schema audit", ""]
    if total is None:
        lines.append("_Not run — invoke `cfn2lza audit` to produce schema-audit.md._")
    else:
        pass_ct = sum(1 for e, _ in files_ok if e == "✅")
        lines.append(f"- Files validated: {len(files_ok)}")
        lines.append(f"- Files passing: {pass_ct}")
        lines.append(f"- Total errors: {total}")
    lines.append("")

    # Engine dry-run
    dry = Path(REPORTS_DIR) / "engine-dry-run.md"
    lines += ["## Engine dry-run", ""]
    if dry.exists():
        first_lines = "\n".join(dry.read_text().splitlines()[:15])
        lines += ["```", first_lines, "```",
                  f"See `{dry.name}` for full output."]
    else:
        lines.append("_Not run — invoke `cfn2lza dry-run` to validate against the LZA engine._")
    lines.append("")

    # Emitted files
    lines += ["## Emitted files", ""]
    yamls = _emitted_yamls()
    if yamls:
        for y in yamls:
            lines.append(f"- `{y}`")
    else:
        lines.append("_No YAML files found in out dir._")
    lines.append("")

    # Hand-port checklist stub
    lines += [
        "## Hand-port checklist",
        "",
        "- [ ] Populate `replacements-config.yaml` SSM parameters (run "
        "`bootstrap-ssm-params.sh` after replacing TODO placeholders).",
        "- [ ] Author any CFN stubs referenced by `customizations-config.yaml`.",
        "- [ ] Hand-port network detail per `network-l2-cluster.md`.",
        "- [ ] Replace all `TODO-*` stubs in `network-config.yaml`.",
        "- [ ] Wire IdC principal assignments in `iam-config.yaml`.",
        "- [ ] Verify regional service availability for your home region.",
        "",
    ]

    out = Path(REPORTS_DIR) / "CONVERSION-SUMMARY.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines))
    print(f"[cfn2lza] summary → {out}")
    return out
