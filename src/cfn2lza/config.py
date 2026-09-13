"""Runtime config populated by profile module + CLI overrides.

Load order:
  1. CLI parses args, calls `load(profile_path_or_name, source_dir, out_dir, ...)`.
  2. `load()` imports profile module (from file path or dotted name), copies all
     public module attributes into this module's globals.
  3. CLI overrides applied last.

Mappers import `from ..profile import X`. `profile.py` is a re-export shim
that reads from this module.
"""
from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

# Populated at load(). Declared for type hints / IDE.
PROFILE_NAME: str = ""
SOURCE_DIR: Path = Path(".")
OUT_DIR: Path = Path(".")
REPORTS_DIR: Path = Path(".")
UNMAPPED_DIR: Path = Path(".")

_LOADED = False


def _import_profile(profile: str) -> Any:
    """Import a profile module from a file path or dotted module name."""
    p = Path(profile)
    if p.exists() and p.is_file():
        spec = importlib.util.spec_from_file_location(f"_cfn2lza_profile_{p.stem}", p)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load profile file: {p}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        return mod
    # Fall back to dotted module name (e.g. bundled example)
    return importlib.import_module(profile)


def load(
    profile: str,
    *,
    source_dir: Path | None = None,
    out_dir: Path | None = None,
    reports_dir: Path | None = None,
    unmapped_dir: Path | None = None,
) -> None:
    """Load profile module, apply CLI path overrides, populate globals."""
    global _LOADED
    mod = _import_profile(profile)

    for k, v in mod.__dict__.items():
        if k.startswith("_"):
            continue
        globals()[k] = v

    if source_dir is not None:
        globals()["SOURCE_DIR"] = Path(source_dir).resolve()
    if out_dir is not None:
        globals()["OUT_DIR"] = Path(out_dir).resolve()
    if reports_dir is not None:
        globals()["REPORTS_DIR"] = Path(reports_dir).resolve()
    elif "REPORTS_DIR" not in mod.__dict__:
        globals()["REPORTS_DIR"] = globals()["OUT_DIR"].parent / "reports" / globals().get("PROFILE_NAME", "profile")
    if unmapped_dir is not None:
        globals()["UNMAPPED_DIR"] = Path(unmapped_dir).resolve()
    elif "UNMAPPED_DIR" not in mod.__dict__:
        globals()["UNMAPPED_DIR"] = globals()["OUT_DIR"].parent / "unmapped" / globals().get("PROFILE_NAME", "profile")

    _LOADED = True


def _autoload_from_env() -> None:
    """Compatibility path: env-var-driven load (matches pre-CLI behavior)."""
    if _LOADED:
        return
    profile = os.environ.get("CFN2LZA_PROFILE") or os.environ.get("CONVERTER_PROFILE") or "malaysia"
    src = os.environ.get("CFN2LZA_SOURCE_DIR")
    out = os.environ.get("CFN2LZA_OUT_DIR")
    reports = os.environ.get("CFN2LZA_REPORTS_DIR")
    unmapped = os.environ.get("CFN2LZA_UNMAPPED_DIR")
    load(
        profile,
        source_dir=Path(src) if src else None,
        out_dir=Path(out) if out else None,
        reports_dir=Path(reports) if reports else None,
        unmapped_dir=Path(unmapped) if unmapped else None,
    )
