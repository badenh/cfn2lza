"""Generic helpers shared across mappers.

[GEN] — nothing Malaysia-specific in here. Reusable across LZ variants.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


from . import profile as _profile


def _p(name: str) -> Path:
    return getattr(_profile, name)


class _PathProxy:
    """Path-like proxy that reads current value from profile shim on every use.

    Mappers that captured `from .common import OUT_DIR` at import time still see
    late CLI-driven overrides applied by `cfn2lza.cli`.
    """

    def __init__(self, attr: str) -> None:
        self._attr = attr

    def _get(self) -> Path:
        return _p(self._attr)

    def __fspath__(self) -> str:
        return str(self._get())

    def __str__(self) -> str:
        return str(self._get())

    def __repr__(self) -> str:
        return repr(self._get())

    def __truediv__(self, other):
        return self._get() / other

    def __getattr__(self, item):
        return getattr(self._get(), item)


SOURCE_DIR = _PathProxy("SOURCE_DIR")
OUT_DIR = _PathProxy("OUT_DIR")
UNMAPPED_DIR = _PathProxy("UNMAPPED_DIR")
REPORTS_DIR = _PathProxy("REPORTS_DIR")

# Back-compat alias for mappers still using the SLZ-era name.
SLZ_CFN = SOURCE_DIR


@dataclass
class Coverage:
    mapped: list[str] = field(default_factory=list)
    unmapped: list[dict[str, Any]] = field(default_factory=list)
    dropped: list[dict[str, Any]] = field(default_factory=list)

    def map(self, source: str, resource_id: str, target: str) -> None:
        self.mapped.append(f"{source}::{resource_id} -> {target}")

    def unmap(self, source: str, resource_id: str, reason: str, hint: str = "") -> None:
        self.unmapped.append(
            {"source": source, "resource_id": resource_id, "reason": reason, "hint": hint}
        )

    def drop(self, source: str, resource_id: str, reason: str) -> None:
        self.dropped.append({"source": source, "resource_id": resource_id, "reason": reason})


def load_cfn(path: Path) -> dict[str, Any]:
    """Load CloudFormation template (JSON or YAML) with CFN short-tag support."""
    text = path.read_text()
    if path.suffix == ".json":
        return json.loads(text)
    return _yaml_load_cfn(text)


def _yaml_load_cfn(text: str) -> dict[str, Any]:
    """SafeLoader extended to accept AWS CFN intrinsic short tags (!Ref, !GetAtt, etc).

    Tags are preserved as {'<Fn::Whatever>': value} dicts so mappers can inspect if
    needed; most mappers just need the resource shape not the intrinsic itself.
    """
    import yaml

    class CfnLoader(yaml.SafeLoader):
        pass

    intrinsics = [
        "Ref", "Condition", "GetAtt", "GetAZs", "ImportValue", "Join", "Select",
        "Split", "Sub", "Base64", "Cidr", "FindInMap", "If", "Not", "Equals",
        "And", "Or", "Transform", "ForEach", "Length", "ToJsonString",
    ]

    def _factory(tag: str):
        def _ctor(loader, node):
            if isinstance(node, yaml.ScalarNode):
                v = loader.construct_scalar(node)
            elif isinstance(node, yaml.SequenceNode):
                v = loader.construct_sequence(node, deep=True)
            elif isinstance(node, yaml.MappingNode):
                v = loader.construct_mapping(node, deep=True)
            else:
                v = None
            key = "Ref" if tag == "Ref" else f"Fn::{tag}"
            if tag == "GetAtt" and isinstance(v, str):
                v = v.split(".")
            return {key: v}
        return _ctor

    for name in intrinsics:
        CfnLoader.add_constructor(f"!{name}", _factory(name))

    return yaml.load(text, Loader=CfnLoader)


def resource_iter(template: dict[str, Any]):
    """Yield (logical_id, resource_dict) pairs."""
    for lid, res in template.get("Resources", {}).items():
        yield lid, res


def cfn_param_default(template: dict[str, Any], name: str, fallback: Any = None) -> Any:
    """Resolve a CFN parameter's Default value; used when Name/Description is a Ref."""
    return template.get("Parameters", {}).get(name, {}).get("Default", fallback)


def resolve_ref(value: Any, template: dict[str, Any]) -> Any:
    """Best-effort resolution of common CFN intrinsics against a template's
    Parameters + Mappings sections. Returns value unchanged if unresolvable.

    Handles: Ref to Parameter, Fn::FindInMap, Fn::Join (of strings + resolvable),
    Fn::Sub of a literal string with no substitutions.
    """
    if isinstance(value, dict):
        if set(value.keys()) == {"Ref"}:
            name = value["Ref"]
            params = template.get("Parameters", {})
            if name in params:
                return params[name].get("Default", value)
            return value
        if set(value.keys()) == {"Fn::FindInMap"}:
            args = value["Fn::FindInMap"]
            if isinstance(args, list) and len(args) == 3:
                map_name, top, key = [resolve_ref(a, template) for a in args]
                mappings = template.get("Mappings", {})
                try:
                    return mappings[map_name][top][key]
                except (KeyError, TypeError):
                    return value
        if set(value.keys()) == {"Fn::Join"}:
            args = value["Fn::Join"]
            if isinstance(args, list) and len(args) == 2:
                sep, parts = args
                if isinstance(parts, list):
                    resolved = [resolve_ref(p, template) for p in parts]
                    if all(isinstance(p, str) for p in resolved) and isinstance(sep, str):
                        return sep.join(resolved)
        if set(value.keys()) == {"Fn::Sub"}:
            arg = value["Fn::Sub"]
            if isinstance(arg, str) and "${" not in arg:
                return arg
    return value


def write_yaml(path: Path, data: Any, header: str = "") -> None:
    import yaml
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        if header:
            for line in header.strip().splitlines():
                f.write(f"# {line}\n" if line else "#\n")
            f.write("\n")
        class NoAliasDumper(yaml.SafeDumper):
            def ignore_aliases(self, _data):
                return True
        yaml.dump(data, f, Dumper=NoAliasDumper, sort_keys=False,
                  default_flow_style=False, allow_unicode=True)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def write_report(name: str, coverage: Coverage) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    p = REPORTS_DIR / f"{name}.md"
    lines = [f"# Coverage report: {name}", ""]
    lines += [f"- mapped: {len(coverage.mapped)}",
              f"- unmapped: {len(coverage.unmapped)}",
              f"- dropped: {len(coverage.dropped)}", ""]
    lines += ["## Mapped", ""]
    lines += [f"- {m}" for m in coverage.mapped] or ["_(none)_"]
    lines += ["", "## Unmapped (feed to L2)", ""]
    if coverage.unmapped:
        for u in coverage.unmapped:
            lines.append(f"- **{u['source']}::{u['resource_id']}** — {u['reason']}")
            if u.get("hint"):
                lines.append(f"    - hint: {u['hint']}")
    else:
        lines.append("_(none)_")
    lines += ["", "## Dropped (intentional — engine handles)", ""]
    if coverage.dropped:
        for d in coverage.dropped:
            lines.append(f"- **{d['source']}::{d['resource_id']}** — {d['reason']}")
    else:
        lines.append("_(none)_")
    p.write_text("\n".join(lines) + "\n")


def write_unmapped(domain: str, coverage: Coverage) -> None:
    """Emit machine-readable UNMAPPED artifact for L2 consumption."""
    UNMAPPED_DIR.mkdir(parents=True, exist_ok=True)
    p = UNMAPPED_DIR / f"{domain}.json"
    p.write_text(json.dumps(coverage.unmapped, indent=2) + "\n")
