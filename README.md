# cfn2lza

Convert a CloudFormation-native AWS Landing Zone into a
[Landing Zone Accelerator on AWS](https://github.com/awslabs/landing-zone-accelerator-on-aws)
(LZA) Universal Configuration.

**What it does:** reads your source LZ's CloudFormation templates and emits
8 schema-valid LZA UC config YAMLs + supporting policy files + a
customizations passthrough queue.

**What it doesn't do:** mechanically translate resource-level network
detail (routes, NACLs, TGW attachments) — those are deliberate
`TODO-*` stubs for hand-port. LZA models routing at a higher abstraction
than raw CFN; silent mis-wiring risk is too high.

**Ceiling:** ~80% auto. Remaining 20% is documented, itemized hand-port
work — enumerated in the auto-generated `CONVERSION-SUMMARY.md`.

Proven on two source LZs:

- [`aws-samples/sample-malaysia-secure-lz`](https://github.com/aws-samples/sample-malaysia-secure-lz)
- [`aws-samples/sample-thailand-secure-lz`](https://github.com/aws-samples/sample-thailand-secure-lz)

Both bundled under `examples/`.

---

## Background — what is LZA UC, and why convert?

**LZA (Landing Zone Accelerator on AWS)** is AWS's opinionated,
CDK-based landing-zone framework, deployed as an accelerator pipeline
that stands up multi-account org guardrails, security services, and
networking. **Universal Configuration (UC)** is LZA's declarative
YAML-based config format that drives what the accelerator deploys —
you edit 8 YAML files instead of authoring/wiring raw CloudFormation.

If you already run a CloudFormation-native Landing Zone (Control-Tower-
based or hand-built), you're at a fork:

- Keep hand-maintaining CFN templates → every new guardrail is a template
  change + deploy sequence you own.
- Adopt LZA → the accelerator owns wiring; you own the declarative
  config. New guardrails become YAML edits, not template changes.

cfn2lza helps you take the second fork by doing the mechanical 80% of
the CFN → LZA UC translation deterministically. What's left is the
20% that requires human review (real email addresses, IdC group IDs,
network detail LZA models at higher abstraction than raw CFN).

## Is this the right tool for you?

**Good fit:**
- Your source LZ is CFN-native (JSON or YAML templates, no CDK synthesis
  step you'd need to re-derive).
- Your source LZ pattern is roughly: OU tree via
  `AWS::Organizations::*`, SCPs/RCPs as policy JSON bodies, custom
  resources for account-baseline enforcement, one central network account
  with TGW + optional NFW.
- You want to *migrate to LZA*, not replace it wholesale.

**Weak fit (converter will run but produce more hand-port than convert):**
- Your LZ has no discrete CFN files per concern (e.g. one giant
  template).
- Your LZ uses runtime-provisioned resources not expressible as LZA UC
  (heavy use of AWS SDK calls in CDK constructs).
- You want to convert *from* LZA UC *to* CFN — cfn2lza is one-way.

**Prerequisite reading if new to LZA:**
- [LZA architecture overview](https://docs.aws.amazon.com/solutions/latest/landing-zone-accelerator-on-aws/architecture-overview.html)
- [LZA UC schema reference](https://awslabs.github.io/landing-zone-accelerator-on-aws/latest/typedocs/latest/)

## The 8 config files cfn2lza emits

| File                            | What it configures                                                       |
|---------------------------------|--------------------------------------------------------------------------|
| `global-config.yaml`            | Home region, enabled regions, Control Tower, CloudTrail, session mgr     |
| `organization-config.yaml`      | OU tree, SCPs (Service Control Policies), RCPs (Resource Control Policies), declarative policies |
| `accounts-config.yaml`          | Mandatory + workload accounts with OU placement                          |
| `security-config.yaml`          | GuardDuty, AccessAnalyzer, IAM password policy, S3 PAB, EBS encryption, KMS org keys |
| `network-config.yaml`           | VPCs, subnets, TGW (Transit Gateway), NFW (Network Firewall), VPC endpoints |
| `iam-config.yaml`               | IdC (IAM Identity Center, formerly SSO) permission sets and assignments  |
| `replacements-config.yaml`      | Named tokens (`{{ ManagementEmail }}` etc) backed by SSM parameters      |
| `customizations-config.yaml`    | Passthrough queue for anything with no first-class LZA UC field          |

Post-conversion your workflow shifts: instead of editing CFN templates
and re-deploying stacks, you edit these YAMLs and re-run the LZA
pipeline.

## Glossary

- **SLZ** — Secure Landing Zone. A pattern of CFN-native landing zones
  (Malaysia CGSO, Thailand, etc.) built on Control Tower.
- **LZA** — Landing Zone Accelerator on AWS. The CDK-based framework
  cfn2lza targets.
- **UC** — Universal Configuration. LZA's declarative YAML config.
- **SCP** — Service Control Policy. Org-wide deny/allow guardrails.
- **RCP** — Resource Control Policy. Resource-level org perimeter.
- **OU** — Organizational Unit.
- **TGW** — Transit Gateway.
- **NFW** — Network Firewall (AWS managed Suricata).
- **IdC** — IAM Identity Center (formerly SSO).
- **CT** — Control Tower.
- **CGSO** — Cyber Government Security Office (Malaysia; source of the
  Malaysia SLZ control mapping).
- **FMS** — Firewall Manager.
- **IPAM** — IP Address Manager.

---

## Install

```bash
pip install cfn2lza
```

Or from source:

```bash
git clone https://github.com/badenh/cfn2lza
cd cfn2lza
pip install -e .
```

Requirements: Python ≥ 3.10, `gh` CLI (for LZA schema fetch on first
`audit` run), Node.js + `yarn` (only if you use `cfn2lza dry-run`).

---

## Try the bundled examples first

Before running against your own LZ, sanity-check by converting one of
the two bundled examples. They exercise the full pipeline end-to-end
against known-good source LZs.

```bash
# 1. Get the source sample LZ that the example profile targets.
git clone https://github.com/aws-samples/sample-malaysia-secure-lz.git ../sample-malaysia-secure-lz

# 2. Convert it.
cfn2lza convert \
    --profile examples/malaysia/profile.py \
    --source-dir ../sample-malaysia-secure-lz/cloudformation \
    --out-dir /tmp/malaysia-uc/out \
    --reports-dir /tmp/malaysia-uc/reports \
    --unmapped-dir /tmp/malaysia-uc/unmapped

# 3. Read the reviewer-facing summary.
$PAGER /tmp/malaysia-uc/reports/CONVERSION-SUMMARY.md
```

Expected result: 103 mapped, 125 unmapped (all deliberate network
deferrals), 55 dropped, schema audit 0 errors. Same shape for the
Thailand example.

---

## 5-minute quickstart

Point cfn2lza at your source LZ:

```bash
# 1. Scaffold a profile (optionally with best-effort resource sniffing).
cfn2lza init mycompany \
    --source-dir /path/to/your-source-lz/cloudformation \
    --sniff

# 2. Edit ./profile.py — confirm the sniff results, fill in
#    ACCELERATOR_PREFIX, HOME_REGION, account list, etc.
$EDITOR ./profile.py

# 3. Run the pipeline.
cfn2lza convert \
    --profile ./profile.py \
    --source-dir /path/to/your-source-lz/cloudformation \
    --out-dir ./out
```

You'll get:

```
out/                                       # UC configs (8 YAMLs + policies)
├── organization-config.yaml
├── security-config.yaml
├── iam-config.yaml
├── global-config.yaml
├── network-config.yaml
├── accounts-config.yaml
├── replacements-config.yaml
├── customizations-config.yaml
├── service-control-policies/
├── rcp-policies/
├── kms-policies/
├── declarative-policies/
├── firewall-rules/
├── customizations/
└── bootstrap-ssm-params.sh
out/../reports/mycompany/                  # coverage + audit reports
├── CONVERSION-SUMMARY.md                  # ← read this first
├── org.md security.md iam.md global.md network.md accounts.md ...
├── schema-audit.md
└── network-l2-cluster.md                  # hand-port shopping list
```

Read `CONVERSION-SUMMARY.md` first — it lists coverage counters, schema
audit results, emitted files, and the hand-port checklist.

---

## Optional: LZA engine dry-run

Validate the emitted UC against the real LZA config validator:

```bash
cfn2lza dry-run --profile ./profile.py --out-dir ./out
```

First run clones `awslabs/landing-zone-accelerator-on-aws` into
`~/.cache/cfn2lza/lza-engine/` and builds it (~5 min, one time). Uses
dummy AWS credentials + `AWS_MAX_ATTEMPTS=1` — fails fast on any real
SSM API call.

Interpret validator output against the `CONVERSION-SUMMARY.md` hand-port
checklist. Every remaining engine complaint should match a documented
TODO stub.

---

## CLI reference

| Command                              | Purpose                                                       |
|--------------------------------------|---------------------------------------------------------------|
| `cfn2lza init <name> --source-dir …` | Scaffold a new profile file. `--sniff` for CFN-file guesses.  |
| `cfn2lza convert --profile …`        | Full pipeline: mappers → schema audit → L2 reports → summary. |
| `cfn2lza audit --profile …`          | Schema audit only (against existing out-dir).                 |
| `cfn2lza report --profile …`         | Re-render L2 cluster + summary.                               |
| `cfn2lza summary --profile …`        | Re-render `CONVERSION-SUMMARY.md` only.                       |
| `cfn2lza dry-run --profile …`        | Invoke LZA engine config-validator.                           |

Common flags on every subcommand except `init`:

```
--profile PATH_OR_MODULE   file path to profile.py (or dotted module name)
--source-dir DIR           source LZ CFN root
--out-dir DIR              UC output directory
--reports-dir DIR          coverage reports (default: <out-dir>/../reports/<profile>)
--unmapped-dir DIR         unmapped queue (default: <out-dir>/../unmapped/<profile>)
```

---

## What auto-converts

- **Org:** OU tree, SCPs, RCPs, declarative EC2 policies
- **Security:** GuardDuty, AccessAnalyzer, IAM password policy, S3 PAB,
  EBS default encryption, KMS org keys, FMS/IPAM delegation
- **IAM:** IdC permission sets (managed-policy short names, ISO-8601 durations)
- **Global:** home region, enabled regions, Control Tower assumption, CT
  trail/log delegation, session-manager preferences
- **Network:** VPCs, subnets (AZ resolved from suffix convention), TGW,
  TGW route tables, NFW policy + firewall, VPC endpoints, spoke
  `vpcTemplates[]` — resource-level routing/NACLs deferred to hand-port
- **Accounts:** mandatory + workload accounts
- **Replacements:** V2 SSM-path-backed replacements + `bootstrap-ssm-params.sh`
- **Customizations:** aggregated passthrough queue for anything with no
  first-class LZA UC field

## What needs hand-port

- Replace `TODO-*@example.com` placeholders with real distribution lists
- Author 2-3 CFN stubs for `customizations-config.yaml` entries
- Complete network hand-port per `network-l2-cluster.md` (routing,
  NACLs, TGW attachments)
- Replace `TODO-rt` / `TODO-endpoint-subnet-a` stubs in `network-config.yaml`
- Wire IdC principal assignments (customer's IdC group IDs required)
- Verify regional service availability for your home region

Full checklist auto-generated in `CONVERSION-SUMMARY.md`.

---

## Extending cfn2lza

- Adding a new source LZ = new profile file. No engine changes needed
  for common cases. See [docs/REUSABILITY.md](docs/REUSABILITY.md).
- Adding a new CFN resource type / intrinsic / LZA schema field pattern
  = engine change. Extends every existing profile automatically.
- Contributing? See [CONTRIBUTING.md](CONTRIBUTING.md).
- AI agent working on this? See [docs/AI-AGENT.md](docs/AI-AGENT.md).

---

## Directory layout

```
cfn2lza/
├── README.md                            you are here
├── CONTRIBUTING.md                      contributor guide
├── CHANGELOG.md
├── LICENSE                              Apache-2.0
├── pyproject.toml
├── src/cfn2lza/
│   ├── cli.py                           entry point
│   ├── config.py                        runtime path/constant store
│   ├── profile.py                       shim; forwards attrs from config
│   ├── pipeline.py                      L1 mapper dispatcher
│   ├── init.py                          `cfn2lza init` scaffolder
│   ├── summary.py                       CONVERSION-SUMMARY.md renderer
│   ├── engine.py                        LZA config-validator wrapper
│   ├── schema_audit.py                  validate emitted YAML vs LZA schema
│   ├── l2_reports.py                    L2 clustering (network hand-port list)
│   ├── common.py                        CFN loader, intrinsic resolver, coverage
│   ├── mappers/                         per-domain CFN → UC mapping
│   └── templates/profile.py.tmpl        `cfn2lza init` scaffold source
├── examples/
│   ├── malaysia/profile.py              reference Malaysia SLZ profile
│   └── thailand/profile.py              reference Thailand SLZ profile
├── tests/                               smoke tests
└── docs/
    ├── REUSABILITY.md                   engine/profile boundary rules
    ├── AI-AGENT.md                      guide for LLM agents extending this
    ├── NOTES.md                         historical decision log
    └── example-conversion-summary-malaysia.md   reference output
```

---

## Troubleshooting

- **Schema audit failure "Additional properties are not allowed"** — schema
  drift. Delete `~/.cache/cfn2lza/schemas/` and rerun `cfn2lza audit`.
- **Engine dry-run hangs 2+ min** — real AWS creds active. `cfn2lza dry-run`
  sets dummy creds, but only for the child process. Make sure nothing
  else in your environment is intercepting. Check `AWS_PROFILE`.
- **"unknown domain"** — typo in a CLI arg or profile constant. Check
  `pipeline.DOMAINS` for valid names.
- **Empty output, no errors** — profile file loaded but empty. Confirm
  `--profile` path is correct + file has `PROFILE_NAME` set.
- **"gh: command not found" during audit** — install [GitHub CLI](https://cli.github.com/)
  and run `gh auth login` (schema audit fetches LZA JSON schemas via `gh api`).

---

## License

Apache-2.0. See [LICENSE](LICENSE). Third-party attribution in
[NOTICE](NOTICE).

## Acknowledgments

Bootstrapped from a Malaysia SLZ → LZA UC conversion done as reference
implementation for the `aws-samples/sample-malaysia-secure-lz` project;
generalized during a subsequent Thailand SLZ conversion.
