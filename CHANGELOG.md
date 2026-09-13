# Changelog

## 0.1.0 — Initial OSS release

- Extracted from internal Malaysia + Thailand SLZ → LZA UC conversions.
- Engine + profile split; two bundled example profiles (`examples/malaysia/`,
  `examples/thailand/`).
- `cfn2lza` CLI: `init`, `convert`, `audit`, `report`, `summary`, `dry-run`.
- Path-agnostic profile loader — profile files carry conventions only;
  paths supplied via CLI flags.
- `cfn2lza init --sniff` scaffolds a new profile with best-effort
  role→filename guesses.
- Templated `CONVERSION-SUMMARY.md` generator.
- Wrapped LZA engine dry-run (auto-clones + builds LZA on first use).
- Apache-2.0 license.
