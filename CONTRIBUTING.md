# Contributing to cfn2lza

Thanks for your interest. cfn2lza is engine + profile split — most
contributions land in one of two places:

- **Engine (`src/cfn2lza/`)** — CFN-shape parsing, LZA-shape emission,
  reusable across all source LZs. Extend when a new CFN Type / intrinsic
  / LZA schema field pattern needs support.
- **Profile (`examples/*/profile.py` or your own file)** — source-LZ
  conventions (accelerator prefix, home region, source file names).

If a contribution mixes both, split into two PRs.

## Development setup

```bash
git clone <this repo>
cd cfn2lza
pip install -e '.[dev]'
```

## Adding support for a new source LZ

1. `cfn2lza init myprofile --source-dir /path/to/source-lz/cloudformation --sniff`
2. Edit the generated `profile.py` — confirm sniff results, fill blanks.
3. `cfn2lza convert --profile ./profile.py --source-dir ... --out-dir ./out`
4. Iterate on mapper coverage until schema audit passes.

If the mapper hits a gap that would benefit other LZs, land it in
`src/cfn2lza/mappers/` (engine) not in your profile.

## Boundary rules (engine vs profile)

See `docs/REUSABILITY.md` for the full boundary table. Quick check: if a
second source LZ would benefit from the change, it's an engine change;
if it's a source-LZ or customer convention, it's a profile change.

## Running tests

```bash
pytest
```

Smoke tests convert both bundled examples (malaysia + thailand) and
assert schema-valid output. If your change breaks either, either fix the
regression or update the example profile with a rationale in the PR.

## PR checklist

- [ ] Engine change works for both bundled examples (schema audit still 0 errors).
- [ ] New mapper dispatch entries have a source-LZ-neutral name.
- [ ] Docs updated if the CLI surface changed.
- [ ] `NOTES.md` entry if the change is non-obvious.

## Anti-patterns

- ❌ Hard-code source-LZ strings in engine files.
- ❌ Add schema fields without grep-verifying against the LZA source schema.
- ❌ Hand-edit generated YAML to fix validator errors — fix the mapper.
- ❌ Silently drop a source resource without a Coverage.drop() reason.
