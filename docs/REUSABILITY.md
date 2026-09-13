# Reusability guide — engine + profile split

cfn2lza is dispatch-table driven with a hard boundary between engine
(reusable across LZ variants) and profile (per-source-LZ conventions).
Adding a new source LZ = new profile file. No engine changes for common
cases.

## Layout

```
src/cfn2lza/
├── common.py           [GEN] CFN loader, intrinsic resolver, coverage
├── config.py           [GEN] runtime path/constant store (CLI-populated)
├── profile.py          [GEN] shim: forwards attrs from config to mappers
├── pipeline.py         [GEN] mapper dispatcher
├── cli.py              [GEN] argparse entry point
├── init.py             [GEN] `cfn2lza init` scaffolder + CFN sniffer
├── summary.py          [GEN] CONVERSION-SUMMARY.md renderer
├── engine.py           [GEN] LZA engine dry-run wrapper
├── schema_audit.py     [GEN] validates emitted YAML vs LZA JSON schema
├── l2_reports.py       [GEN] network hand-port clustering
├── mappers/
│   ├── org.py          [GEN] AWS::Organizations::* handlers
│   ├── security.py     [GEN] Custom::* + AccessAnalyzer + KMS handlers
│   ├── iam.py          [GEN] AWS::SSO::PermissionSet handlers
│   ├── globalcfg.py    [GEN] synthesized global-config
│   ├── network.py      [GEN] VPC/TGW/NFW/endpoint handlers
│   ├── accounts.py     [GEN] synthesized accounts + replacements
│   └── customizations.py [GEN] passthrough queue aggregator
└── templates/
    └── profile.py.tmpl [GEN] template for `cfn2lza init`
examples/
├── malaysia/profile.py [MY]  reference Malaysia SLZ profile
└── thailand/profile.py [MY]  reference Thailand SLZ profile
```

`[GEN]` = engine, reusable. `[MY]` = per-source-LZ. Nothing else.

## Adding a new profile

```bash
cfn2lza init myco \
    --source-dir /path/to/myco-lz/cloudformation \
    --sniff
$EDITOR ./profile.py     # confirm sniff results + fill blanks
cfn2lza convert \
    --profile ./profile.py \
    --source-dir /path/to/myco-lz/cloudformation \
    --out-dir ./out
```

Iterate. Most errors trace back to a missing/misnamed source file in the
profile, or a source-LZ pattern the mappers don't yet recognize.

## What lives in the profile ([MY])

Per-source-LZ constants only. See the bundled examples for the full list.

| Kind of value                                       | Example                                    |
|-----------------------------------------------------|--------------------------------------------|
| Profile identity                                    | `PROFILE_NAME = "myco"`                    |
| Accelerator prefix                                  | `ACCELERATOR_PREFIX = "MYCO"`              |
| Home region, enabled regions                        | `HOME_REGION = "ap-southeast-5"`           |
| Management-role name                                | `MANAGEMENT_ACCOUNT_ACCESS_ROLE = "…"`     |
| Source CFN file names by role                       | `ORG_SOURCES = {"ou_tree": "...", ...}`    |
| Default deployment-target OUs                       | `DEFAULT_SCP_TARGET_OUS = [...]`           |
| Delegated admin account name                        | `DELEGATED_SECURITY_ADMIN = "Audit"`       |
| Account list                                        | `MANDATORY_ACCOUNTS`, `WORKLOAD_ACCOUNTS`  |
| TGW ASN                                             | `TGW_ASN = 65001`                          |
| Files known to be engine-managed (drop with reason) | `DROPPED_SOURCES = {"...": "reason"}`      |

Paths are *not* in the profile any more — CLI supplies them.

## What lives in the engine ([GEN])

- CFN intrinsic resolver (`common.resolve_ref`)
- Dispatch by CFN Type (`Custom::*`, `AWS::EC2::VPC`, `AWS::SSO::PermissionSet`, …)
- LZA schema field name / shape
- Backing-type sets (`BACKING_TYPES` — Lambdas, IAM roles, LogGroups)
- File-to-customizations passthrough patterns
- Coverage bookkeeping + report/summary generation

## When to extend the engine (not just the profile)

Signal that you're stretching the profile too far:

- Adding a new `Custom::*` type your source LZ uses → extend
  `mappers/security.py CUSTOM_HANDLERS`
- Adding a new whole-file customizations passthrough pattern → extend
  `mappers/security.py FILE_TO_CUSTOMIZATIONS`
- Adding a new CFN intrinsic pattern the resolver doesn't handle →
  extend `common.resolve_ref`
- Adding a new SLZ→UC field mapping the mapper doesn't emit → extend the
  relevant mapper's builder

These are engine changes. Every existing profile inherits them
automatically. Land as engine PRs, not profile PRs.

## Test any engine change against both bundled examples

```bash
pytest -v
```

If your engine change breaks either malaysia or thailand smoke test,
either fix the regression or update the example profile with a
rationale in the PR description.
