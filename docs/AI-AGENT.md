# AI agent guide — extending cfn2lza

Read this if you (Claude / other LLM agent) have been asked to convert a
new source LZ to LZA UC, or extend the cfn2lza engine. Assumes you've
read `README.md` and `docs/REUSABILITY.md`.

## Mental model

**Engine + profile split, dispatch-table driven.** Every file under
`src/cfn2lza/` is `[GEN]` — reusable across LZ variants. Profile files
(e.g. `examples/malaysia/profile.py`) are `[MY]` — per-source-LZ
conventions. Adding a source LZ = new profile file, no engine changes
for common cases.

**Paths are supplied at CLI time**, not baked into profiles. Profile
files carry only source-LZ-shape constants (accelerator prefix, home
region, source file names by role, account lists). See any
`examples/*/profile.py`.

**Runtime config flow**:
```
cfn2lza.cli._apply_profile()
  → config.load(profile_path, source_dir=..., out_dir=..., ...)
    → imports profile file, copies attrs into cfn2lza.config globals
    → applies CLI path overrides last (CLI wins)
profile.py shim → __getattr__ forwards to cfn2lza.config
common.py → _PathProxy re-reads paths from profile shim on every use
```

The `_PathProxy` in `common.py` matters: mappers capture
`from .common import OUT_DIR` at module import time, but late CLI-set
overrides still take effect because reads go through the proxy.

## Pipeline order (do NOT rearrange)

```
L1 extraction (deterministic, per-domain mapper)  ← cfn2lza convert
   ↓
schema audit (jsonschema vs cached LZA schemas)   ← cfn2lza audit
   ↓
L2 clustering (network hand-port shopping list)   ← cfn2lza report
   ↓
summary render (CONVERSION-SUMMARY.md)            ← cfn2lza summary
   ↓
engine dry-run (LZA config-validator.ts)          ← cfn2lza dry-run
   ↓
reviewer hand-port (TODO stubs, real emails, CFN stub authoring)
```

`cfn2lza convert` runs the first four in one call. Each layer catches
what the previous missed. **Never skip layers.** Schema audit catches
shape errors; engine catches cross-references + AWS-native format
constraints (emails, AZ naming) the JSON schema doesn't express.

## Repo map (know these files)

| Path                                                 | Role                                              |
|------------------------------------------------------|---------------------------------------------------|
| `src/cfn2lza/cli.py`                                 | argparse entrypoint, subcommand dispatch          |
| `src/cfn2lza/config.py`                              | runtime config store (populated by CLI)           |
| `src/cfn2lza/profile.py`                             | shim: forwards attrs from config to mappers       |
| `src/cfn2lza/common.py`                              | CFN loader, intrinsic resolver, Coverage, `_PathProxy` |
| `src/cfn2lza/pipeline.py`                            | domain dispatcher (`DOMAINS = {...}`)             |
| `src/cfn2lza/schema_audit.py`                        | fetches LZA JSON schemas, validates emitted YAML  |
| `src/cfn2lza/l2_reports.py`                          | network hand-port clustering                      |
| `src/cfn2lza/summary.py`                             | CONVERSION-SUMMARY.md renderer                    |
| `src/cfn2lza/engine.py`                              | LZA engine dry-run wrapper                        |
| `src/cfn2lza/init.py`                                | `cfn2lza init` scaffolder + CFN sniffer           |
| `src/cfn2lza/templates/profile.py.tmpl`              | template for `cfn2lza init`                       |
| `src/cfn2lza/mappers/{org,security,iam,globalcfg,network,accounts,customizations}.py` | per-domain CFN → UC mapping |

## Boundary rules — [GEN] vs [MY]

Before adding a constant / function / helper, decide which side.

| Kind of decision                                    | Bucket | Where                                                  |
|-----------------------------------------------------|--------|--------------------------------------------------------|
| CFN intrinsic resolver (`Ref`, `Fn::Join`, …)       | GEN    | `common.resolve_ref`                                   |
| Dispatch by CFN Type                                | GEN    | mapper dispatch tables (see below)                     |
| LZA schema field name / shape                       | GEN    | `mappers/*.py`                                         |
| Backing-infra resource types to drop                | GEN    | `mappers/security.py BACKING_TYPES` (+ network variant)|
| Custom resource handlers (`Custom::*`)              | GEN    | `mappers/security.py CUSTOM_HANDLERS`                  |
| Whole-file customizations passthrough patterns      | GEN    | `mappers/security.py FILE_TO_CUSTOMIZATIONS`           |
| Source-LZ file names + roles                        | MY     | `<profile>.py {ORG,SECURITY,IAM,NETWORK}_SOURCES`     |
| Accelerator prefix, home region, ASN default        | MY     | `<profile>.py`                                         |
| Account naming convention                           | MY     | `<profile>.py MANDATORY_ACCOUNTS / WORKLOAD_ACCOUNTS`  |
| Default OU targets for policies                     | MY     | `<profile>.py DEFAULT_SCP_TARGET_OUS etc.`             |
| Regional pinning / partition                        | MY     | `<profile>.py`                                         |

If you're about to hard-code a source-LZ string in a mapper, stop —
push it up to the profile constants.

Adding a new profile constant? Just define it in the profile file. The
`profile.py __getattr__` shim forwards any attribute; mappers do
`from ..profile import YOUR_NEW_CONST`.

## Working with the schema audit

**Always** validate against LZA source schema before extending a mapper.
Use `gh api` (no clone needed):

```bash
gh api repos/awslabs/landing-zone-accelerator-on-aws/contents/source/packages/@aws-accelerator/config/lib/schemas/<name>-config.json \
  | python3 -c "import json,sys,base64; print(base64.b64decode(json.load(sys.stdin)['content']).decode())"
```

For the TypeScript source (richer type info than the JSON schema):

```bash
gh api repos/awslabs/landing-zone-accelerator-on-aws/contents/source/packages/@aws-accelerator/config/lib/<name>-config.ts \
  | python3 -c "import json,sys,base64; print(base64.b64decode(json.load(sys.stdin)['content']).decode())"
```

Do this **before** emitting new fields. Invented fields (the historical
`guardduty.malwareProtection` cautionary tale) waste iterations;
schema-grep catches them in seconds.

Schema cache: `~/.cache/cfn2lza/schemas/` (override with
`$CFN2LZA_SCHEMA_CACHE`). Delete + rerun `cfn2lza audit` to refetch
after upstream schema updates.

## L1 → L2 handoff protocol

- L1 (`cfn2lza convert`) emits deterministic output + per-domain
  `<unmapped-dir>/<domain>.json` with reason + hint per gap.
- L2 (`cfn2lza report`) reads those JSON files, clusters network items
  into a hand-port shopping list, renders summary.
- Reasoning-driven fixes: read the source LZ's README (deploy steps
  often name real targets), nested-stack CFN files (parent → child
  parameter wiring reveals intent), source repo commits.
- L2 output paths:
  - Fixes that generalize → update mapper dispatch or extend profile constants
  - Reviewer-only choices → `<reports-dir>/*-l2-cluster.md`
  - Real blockers → `customizations-config.yaml` passthrough entry

## Handling "no first-class LZA UC field" cases

1. Verify absence via `gh api` schema grep (must confirm, not guess).
2. If genuinely absent: use `mappers/customizations.py` aggregator queue.
   Call `register_file_passthrough(...)` or `register_<specific>(...)`.
   Persist policy body / template body under
   `<out-dir>/customizations/<subdir>/`.
3. Emit reviewer note describing which CFN stub they must author.

Do NOT invent fake fields. Do NOT hand-edit generated YAML — fix the
mapper.

## Common failure modes (learned from Malaysia + Thailand conversions)

- **CFN YAML short-tag load failure** → use `common._yaml_load_cfn`
  (extends SafeLoader with `!Ref/!GetAtt/!Sub/!ImportValue/…`).
- **Values wrapped in intrinsics** (`Ref`, `Fn::FindInMap`, `Fn::Sub`,
  `Fn::Join`) → use `common.resolve_ref`; extend if new intrinsic.
- **`Fn::Sub` with pseudo-params** (`${AWS::Region}`) → resolver returns
  unchanged; use domain-specific extractor (see
  `mappers/network._short_service` for the pattern).
- **Custom resources backed by Lambdas** — the Lambda / IAM / LogGroup /
  KMS aren't domain; only the `Custom::*` resource's Properties are.
  Add backing types to `BACKING_TYPES`, dispatch `Custom::*` via
  `CUSTOM_HANDLERS`.
- **Multiple LZA schema versions for same field** (e.g. replacements V1
  vs V2) — check `anyOf` branches in the JSON schema; pick the shape
  that supports what you're expressing.
- **Empty required list** — many LZA fields require empty `[]` not
  missing key. Schema audit surfaces these fast.
- **Wrong cwd on `--profile` relative paths** — CLI resolves profile as
  file path first, then falls back to dotted module. Use absolute paths
  or run from the cfn2lza repo root.

## When to build engine features vs profile-level workarounds

Extend the engine (`[GEN]`) if:
- New CFN Type appears in ≥2 LZ variants (add handler)
- New CFN intrinsic pattern appears (extend `common.resolve_ref`)
- New "no UC field" case appears (add registrar in `customizations.py`)
- New LZA schema field type appears (extend mapper builder)

Keep it in the profile (`[MY]`) if:
- Naming convention (subnet suffix scheme, account name style)
- Region/partition choice
- Deployment-target OU defaults
- Which source files play which role

Test: "would a second source LZ benefit from this being generic?" Yes →
`[GEN]`. If it's a customer/source choice → `[MY]`.

## Testing your changes (fast loop)

```bash
# Regenerate + audit
cfn2lza convert \
    --profile examples/malaysia/profile.py \
    --source-dir ../sample-malaysia-secure-lz/cloudformation \
    --out-dir /tmp/cfn2lza-test/my/out \
    --reports-dir /tmp/cfn2lza-test/my/reports \
    --unmapped-dir /tmp/cfn2lza-test/my/unmapped

# Check both bundled examples still pass
pytest tests/ -v
```

Engine dry-run only when schema audit is 0 errors:

```bash
cfn2lza dry-run \
    --profile examples/malaysia/profile.py \
    --source-dir ... --out-dir /tmp/cfn2lza-test/my/out \
    --reports-dir /tmp/cfn2lza-test/my/reports \
    --lza-repo ~/.cache/cfn2lza/lza-engine
```

Iterate 3-5× normal. Each iteration: cluster errors by type + fix in bulk.

## What to write in `docs/NOTES.md` when you land a change

- **[GEN]** if the change is engine-level and benefits future profiles.
- **[MY]** if it's profile-only.
- **[REWORK]** if you deferred something.
- **[RISK]** if you emitted a stub that could ship broken.
- Cite file paths + line numbers. Note counters (mapped/unmapped/dropped
  deltas). Note what upstream source data you used to make the decision.

Future-you (or the next agent) reads NOTES.md to understand why the
converter is shaped the way it is. Terse is fine; missing is not.

## What to hand back to the human

Every conversion run should produce:
1. `<out-dir>/` — the 8 config YAMLs + policy/rule files
2. `<reports-dir>/` — per-domain coverage + schema-audit + network-l2-cluster + CONVERSION-SUMMARY.md + engine-dry-run.md (if ran)
3. `<unmapped-dir>/` — per-domain JSON queues (machine-readable)
4. Updated `docs/NOTES.md` — running log entry
5. **TODO stubs enumerated in CONVERSION-SUMMARY.md** — never leave a silent stub

The summary is auto-generated by `cfn2lza summary` — do NOT hand-author
it. Fix the summary generator (`summary.py`) if the auto content is wrong.

## Anti-patterns (do not do)

- ❌ Hand-edit generated YAML to fix a validator error. Fix the mapper.
- ❌ Invent a schema field without grep-verifying it exists.
- ❌ Skip schema audit + jump to engine dry-run. Schema audit is cheaper.
- ❌ Skip engine dry-run because schema audit passed. Engine catches more.
- ❌ Attempt mechanical translation of network routing detail without
   hand-review. LZA models routing at higher abstraction — cluster and defer.
- ❌ Add source-LZ strings to `[GEN]` files. Push to profile.
- ❌ Silently drop a source resource. Always emit a mapped/unmapped/dropped
   entry with reason.
- ❌ Trust `{{ tokens }}` will resolve without SSM/inline value backing.
   LZA V2 replacements need explicit `type` + either `value` or `path`.
- ❌ Bake paths into a profile file. Paths are CLI-supplied only.
- ❌ Hand-author `CONVERSION-SUMMARY.md`. It's auto-generated; fix the generator.

## Convergence signal

Engine dry-run "remaining issues" count monotonically decreases across
iterations. When the count matches the enumerated TODO stubs in
`CONVERSION-SUMMARY.md` §Manual work checklist exactly (no unaccounted
diff), you're done — hand back to reviewer.

Reference baselines (both bundled examples):
- Malaysia: converges at **43 issues** (28 network `TODO-rt` +
  `TODO-endpoint-subnet-a` + 12 email placeholders + 3 missing
  customizations CFN stubs).
- Thailand: same 43-issue convergence, same categories.

If your run converges at a different number, either:
- your source LZ is genuinely different (document in summary), or
- you regressed a mapper (bisect against the smoke tests).
