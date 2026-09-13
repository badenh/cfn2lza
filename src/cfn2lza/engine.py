"""LZA engine dry-run wrapper.

Clones + builds the LZA source repo on first use, then invokes
`config-validator.ts` against the emitted UC directory with dummy AWS
credentials + AWS_MAX_ATTEMPTS=1 (fails fast on any SSM call rather than
hanging on network retries).

Cached at `~/.cache/cfn2lza/lza-engine/` by default; override with
`--lza-repo <path>`.

Writes `<reports_dir>/engine-dry-run.md` with captured output.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .common import OUT_DIR, REPORTS_DIR
from . import profile as _profile

LZA_GIT_URL = "https://github.com/awslabs/landing-zone-accelerator-on-aws.git"


def _sh(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    print(f"[cfn2lza] $ {' '.join(cmd)}  (cwd={cwd})")
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)


def _ensure_repo(lza_repo: Path) -> Path:
    """Clone + build LZA repo if not present. Returns the accelerator package dir."""
    source_dir = lza_repo / "source"
    if not source_dir.exists():
        lza_repo.parent.mkdir(parents=True, exist_ok=True)
        r = _sh(["git", "clone", "--depth", "1", LZA_GIT_URL, str(lza_repo)])
        if r.returncode != 0:
            raise RuntimeError(f"git clone failed: {r.stderr}")

    if not shutil.which("yarn"):
        raise RuntimeError("yarn not installed; needed to build LZA engine. "
                           "Install Node.js + yarn and rerun.")

    marker = source_dir / ".cfn2lza-built"
    if not marker.exists():
        r = _sh(["yarn", "install"], cwd=source_dir)
        if r.returncode != 0:
            raise RuntimeError(f"yarn install failed: {r.stderr}")
        for pkg in ("@aws-lza", "@aws-accelerator/config", "@aws-accelerator/accelerator"):
            r = _sh(["yarn", "build"], cwd=source_dir / "packages" / pkg)
            if r.returncode != 0:
                raise RuntimeError(f"yarn build failed in {pkg}: {r.stderr}")
        marker.touch()

    return source_dir / "packages" / "@aws-accelerator" / "accelerator"


def run(lza_repo: Path, home_region: str | None = None, partition: str = "aws") -> int:
    if not Path(OUT_DIR).exists():
        print(f"error: out dir does not exist: {OUT_DIR}")
        return 2

    try:
        accel = _ensure_repo(Path(lza_repo))
    except RuntimeError as exc:
        print(f"error: {exc}")
        return 2

    region = home_region or getattr(_profile, "HOME_REGION", "us-east-1")
    env = os.environ.copy()
    # AWS-published documentation example credentials (not real secrets):
    # https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_identifiers.html
    # Passed so the LZA config-validator's SSM lookups fail fast instead of
    # burning minutes retrying real API calls under an accidentally-active profile.
    env.update({
        "AWS_ACCESS_KEY_ID": "AKIA" + "IOSFODNN7EXAMPLE",  # noqa: S105 - docs example
        "AWS_SECRET_ACCESS_KEY": "wJalrXUtnFEMI/K7MDENG/" + "bPxRfiCYEXAMPLEKEY",  # noqa: S105
        "AWS_MAX_ATTEMPTS": "1",
        "AWS_REGION": region,
        "PARTITION": partition,
    })
    r = _sh(
        ["npx", "ts-node", "lib/config-validator.ts", str(Path(OUT_DIR))],
        cwd=accel,
        env=env,
    )
    output = (r.stdout or "") + "\n" + (r.stderr or "")

    Path(REPORTS_DIR).mkdir(parents=True, exist_ok=True)
    dry = Path(REPORTS_DIR) / "engine-dry-run.md"
    dry.write_text(
        f"# Engine dry-run\n\n"
        f"- lza-repo: `{lza_repo}`\n"
        f"- home region: `{region}` (partition `{partition}`)\n"
        f"- exit code: `{r.returncode}`\n\n"
        f"```\n{output.strip()}\n```\n"
    )
    print(f"[cfn2lza] engine dry-run → {dry} (rc={r.returncode})")
    return r.returncode
