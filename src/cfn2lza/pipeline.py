"""L1 entrypoint. Dispatches domain mappers, writes coverage reports.

Direct usage (rare — CLI is preferred):
    python -m cfn2lza.pipeline [domain ...]

Reads profile + paths via env vars set by `cfn2lza.cli` or by the caller:
    CFN2LZA_PROFILE     dotted module name or file path
    CFN2LZA_SOURCE_DIR  source LZ CFN directory
    CFN2LZA_OUT_DIR     UC output directory
    CFN2LZA_REPORTS_DIR coverage report directory (auto if unset)
    CFN2LZA_UNMAPPED_DIR unmapped-item queue directory (auto if unset)
"""
from __future__ import annotations

import sys

from .common import Coverage, write_report, write_unmapped
from .mappers import accounts as accounts_mapper
from .mappers import customizations as customizations_mapper
from .mappers import globalcfg as global_mapper
from .mappers import iam as iam_mapper
from .mappers import network as network_mapper
from .mappers import org as org_mapper
from .mappers import security as security_mapper
from . import profile as _profile


# Ordering matters: security must run before globalcfg (session-manager deferral).
DOMAINS = {
    "org": org_mapper.build_organization_config,
    "security": security_mapper.build_security_config,
    "iam": iam_mapper.build_iam_config,
    "global": global_mapper.build_global_config,
    "network": network_mapper.build_network_config,
    "accounts": accounts_mapper.build_accounts_config,
    "replacements": accounts_mapper.build_replacements_config,
}


def run(domains: list[str] | None = None) -> int:
    domains = domains or list(DOMAINS)
    print(f"[cfn2lza] profile={_profile.PROFILE_NAME}  out={_profile.OUT_DIR}")
    for d in domains:
        if d not in DOMAINS:
            print(f"unknown domain: {d}", file=sys.stderr)
            return 2
        print(f"[cfn2lza] running domain: {d}")
        cov: Coverage = DOMAINS[d]()
        write_report(d, cov)
        write_unmapped(d, cov)
        print(f"  mapped={len(cov.mapped)} unmapped={len(cov.unmapped)} dropped={len(cov.dropped)}")

    print("[cfn2lza] aggregating customizations")
    cust_cov = Coverage()
    customizations_mapper.build_customizations_config(cust_cov)
    write_report("customizations", cust_cov)
    return 0


def main(argv: list[str]) -> int:
    return run(argv or None)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
