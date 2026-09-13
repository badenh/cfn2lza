"""cfn2lza — CLI entry point.

Subcommands:
    init      Scaffold a new profile file for a source LZ.
    convert   Run the full conversion pipeline (mappers + schema audit + reports).
    audit     Re-run schema audit only against an existing out dir.
    report    Re-run L2 clustering + summary against an existing out dir.
    dry-run   Invoke the LZA engine config-validator against out dir.
    summary   Render CONVERSION-SUMMARY.md from coverage + audit + dry-run.

Every subcommand accepts:
    --profile PATH_OR_MODULE  file path to profile.py or dotted module name
    --source-dir DIR          source LZ CFN root directory
    --out-dir DIR             UC output directory
    --reports-dir DIR         coverage reports directory (default: <out-dir>/../reports/<profile>)
    --unmapped-dir DIR        unmapped queue directory (default: <out-dir>/../unmapped/<profile>)
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _add_profile_args(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("--profile", required=True, help="Path to profile.py or dotted module name.")
    sp.add_argument("--source-dir", type=Path, help="Source LZ CloudFormation directory.")
    sp.add_argument("--out-dir", type=Path, help="UC output directory.")
    sp.add_argument("--reports-dir", type=Path, help="Coverage report directory.")
    sp.add_argument("--unmapped-dir", type=Path, help="Unmapped-queue directory.")


def _apply_profile(args: argparse.Namespace) -> None:
    """Apply CLI paths to the runtime config, load profile module."""
    from . import config

    config.load(
        args.profile,
        source_dir=args.source_dir,
        out_dir=args.out_dir,
        reports_dir=args.reports_dir,
        unmapped_dir=args.unmapped_dir,
    )
    # Also plant env vars so subprocesses (`python -m cfn2lza.pipeline` etc.) see them.
    os.environ["CFN2LZA_PROFILE"] = str(args.profile)
    if args.source_dir:
        os.environ["CFN2LZA_SOURCE_DIR"] = str(args.source_dir.resolve())
    if args.out_dir:
        os.environ["CFN2LZA_OUT_DIR"] = str(args.out_dir.resolve())
    if args.reports_dir:
        os.environ["CFN2LZA_REPORTS_DIR"] = str(args.reports_dir.resolve())
    if args.unmapped_dir:
        os.environ["CFN2LZA_UNMAPPED_DIR"] = str(args.unmapped_dir.resolve())


def _cmd_init(args: argparse.Namespace) -> int:
    from . import init as init_mod

    return init_mod.run(
        name=args.name,
        out=args.profile_out,
        source_dir=args.source_dir,
        sniff=args.sniff,
    )


def _cmd_convert(args: argparse.Namespace) -> int:
    _apply_profile(args)
    from . import pipeline, schema_audit, l2_reports, summary

    rc = pipeline.run()
    if rc != 0:
        return rc
    audit_rc = schema_audit.main()
    l2_reports.main()
    summary.render()
    print(f"[cfn2lza] done. audit rc={audit_rc}")
    return audit_rc


def _cmd_audit(args: argparse.Namespace) -> int:
    _apply_profile(args)
    from . import schema_audit

    return schema_audit.main()


def _cmd_report(args: argparse.Namespace) -> int:
    _apply_profile(args)
    from . import l2_reports, summary

    l2_reports.main()
    summary.render()
    return 0


def _cmd_summary(args: argparse.Namespace) -> int:
    _apply_profile(args)
    from . import summary

    summary.render()
    return 0


def _cmd_dryrun(args: argparse.Namespace) -> int:
    _apply_profile(args)
    from . import engine

    return engine.run(
        lza_repo=args.lza_repo,
        home_region=args.home_region,
        partition=args.partition,
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cfn2lza",
        description="Convert a CloudFormation-native AWS Landing Zone into a Landing Zone "
                    "Accelerator Universal Configuration.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # init
    sp = sub.add_parser("init", help="Scaffold a new profile for a source LZ.")
    sp.add_argument("name", help="Profile name (short slug, e.g. 'mycompany').")
    sp.add_argument("--profile-out", type=Path, default=Path("./profile.py"),
                    help="Where to write the scaffolded profile (default: ./profile.py).")
    sp.add_argument("--source-dir", type=Path, required=True,
                    help="Source LZ CloudFormation root directory (used for sniffing).")
    sp.add_argument("--sniff", action="store_true",
                    help="Scan source CFN files and pre-fill role→filename guesses.")
    sp.set_defaults(func=_cmd_init)

    # convert
    sp = sub.add_parser("convert", help="Run the full conversion pipeline.")
    _add_profile_args(sp)
    sp.set_defaults(func=_cmd_convert)

    # audit
    sp = sub.add_parser("audit", help="Re-run schema audit only.")
    _add_profile_args(sp)
    sp.set_defaults(func=_cmd_audit)

    # report
    sp = sub.add_parser("report", help="Re-run L2 clustering + summary.")
    _add_profile_args(sp)
    sp.set_defaults(func=_cmd_report)

    # summary
    sp = sub.add_parser("summary", help="Render CONVERSION-SUMMARY.md.")
    _add_profile_args(sp)
    sp.set_defaults(func=_cmd_summary)

    # dry-run
    sp = sub.add_parser("dry-run", help="Invoke LZA engine config-validator against out dir.")
    _add_profile_args(sp)
    sp.add_argument("--lza-repo", type=Path,
                    default=Path.home() / ".cache" / "cfn2lza" / "lza-engine",
                    help="Location of the LZA source repo checkout (cloned/built on first use).")
    sp.add_argument("--home-region", default=None,
                    help="Override home region (default: from profile).")
    sp.add_argument("--partition", default="aws", help="AWS partition (default: aws).")
    sp.set_defaults(func=_cmd_dryrun)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
