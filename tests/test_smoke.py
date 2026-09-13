"""Smoke tests — convert each bundled example, assert emitted YAMLs exist.

Schema audit is exercised in CI (needs `gh` for schema fetch on first run).
These tests only cover the deterministic mapper pipeline.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLES_ROOT = REPO_ROOT.parent

EXAMPLES = [
    ("malaysia", "sample-malaysia-secure-lz"),
    ("thailand", "sample-thailand-secure-lz"),
]

EXPECTED_YAMLS = [
    "accounts-config.yaml",
    "customizations-config.yaml",
    "global-config.yaml",
    "iam-config.yaml",
    "network-config.yaml",
    "organization-config.yaml",
    "replacements-config.yaml",
    "security-config.yaml",
]


@pytest.mark.parametrize("profile,source_repo", EXAMPLES)
def test_convert(profile, source_repo, tmp_path):
    source_dir = SAMPLES_ROOT / source_repo / "cloudformation"
    if not source_dir.exists():
        pytest.skip(f"source sample repo not checked out at {source_dir}")

    profile_file = REPO_ROOT / "examples" / profile / "profile.py"
    out_dir = tmp_path / "out"
    reports_dir = tmp_path / "reports"
    unmapped_dir = tmp_path / "unmapped"

    r = subprocess.run(
        [
            sys.executable, "-m", "cfn2lza.cli", "convert",
            "--profile", str(profile_file),
            "--source-dir", str(source_dir),
            "--out-dir", str(out_dir),
            "--reports-dir", str(reports_dir),
            "--unmapped-dir", str(unmapped_dir),
        ],
        capture_output=True, text=True,
    )
    # We accept schema-audit failure (non-zero) because gh may not be
    # authenticated in some environments — but pipeline itself must succeed.
    assert out_dir.exists(), f"convert failed: {r.stdout}\n{r.stderr}"
    for y in EXPECTED_YAMLS:
        assert (out_dir / y).exists(), f"missing {y}"

    summary = reports_dir / "CONVERSION-SUMMARY.md"
    assert summary.exists(), "summary was not rendered"
