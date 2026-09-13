# Converter NOTES — running log

> **Note:** Historical development log from the initial Malaysia + Thailand
> conversion phases (before the `cfn2lza` CLI refactor). File paths and
> commands here reflect the pre-refactor layout; retain for context on
> engine design decisions. For current dev conventions see
> [AI-AGENT.md](AI-AGENT.md).

Purpose: capture phasing, staging, rework, and reusability observations as we build.
One-off conversion (Malaysia SLZ → LZA UC) is primary. Second variant may follow, so
mark decisions that are Malaysia-specific vs generic-engine candidates.

Legend:
- **[MY]** Malaysia-specific
- **[GEN]** Generic engine candidate (reusable across LZ variants)
- **[REWORK]** Known deferred rework
- **[STAGE]** Staging / sequencing decision
- **[RISK]** Watch-item

---

## Fixed decisions (from opening scope discussion)

- **[STAGE]** Pipeline order: L1 deterministic extractor → schema validate → L2 LLM fill of UNMAPPED. Not L2-first.
- **[STAGE]** First slice: vertical (org domain end-to-end). Proves dispatcher + schema + diff-back loop before hitting `lz-central-network.json` (3016 lines).
- **[GEN]** Output layout: `converter/{src,out/malaysia-uc,unmapped,reports}`. Source repos untouched.
- **[GEN]** L1 language: Python + `cfn-flip` + `pyyaml`. AWS-native CFN parsing.
- **[MY]** CT coexistence: match SLZ assumption (LZA-with-CT, `controlTower.enable: true`). Downstream can flip.
- **[MY]** Region issues (`ap-southeast-5` service availability) accepted; handle downstream, not in converter.

---

## Phasing plan (mirrors TaskList)

1. Scaffold + notes (this file)
2. **Vertical slice: org domain** — smallest, cleanest map; validates full pipeline
3. Schema-validate org slice
4. L2 fill on org UNMAPPED
5. Security domain
6. IAM + global domains
7. **Network domain** — highest risk, largest source, biggest UNMAPPED expected
8. L2 fill remaining UNMAPPED
9. Accounts + replacements assembly
10. Parity check + LZA engine dry-run
11. **Reusability pass** — factor engine for second variant

Rationale for order: cheap→expensive, low-risk→high-risk, isolated→cross-cutting.
Accounts + replacements last because they reference names defined in earlier configs.

---

## Rework buckets (anticipated)

- **[REWORK]** SCP OU-ID → OU-name rewrites. SLZ SCPs reference OU IDs literally; LZA refs by name. Deferred until accounts-config assembled.
- **[REWORK]** `scpRevertChangesConfig` (LZA default true) may fight any hand-tuned SCPs. Flag in parity check.
- **[REWORK]** NACLs / TGW static routes / NFW policy in `lz-central-network.json` — expect fidelity gaps; hand-review after L1+L2.
- **[REWORK]** KMS CMK key policies — SLZ inline JSON, LZA has structured `keyManagementService` block; may need translation pass.
- **[REWORK]** SLZ bootstrap templates (`lz-organization-setup.yaml`, `-service-access.yaml`, `-guardrails.yaml`, `lz-stackset-roles.yaml`) — discard, engine handles. Note in coverage report so reviewers see they're intentional drops, not misses.

---

## Reusability observations (fill as we go)

Split each mapper into:
- **[GEN]** Pure CFN-resource-type → LZA-schema-fragment mapper (reusable)
- **[MY]** SLZ-specific naming/OU/account-name conventions (per-source config)

Target end-state: `src/mappers/` = generic; `src/profiles/malaysia.py` = SLZ conventions.
Second variant = new profile file, reuse mappers.

Reusability candidates to date:
- (populate as mappers land)

---

## Log

### 2026-09-12 — kickoff
- Repos cloned. Scaffold in place. Tasks #1–#11 created.
- Starting vertical slice: org domain.

### 2026-09-12 — org slice landed
- L1 vertical slice complete. `python3 -m converter.src.run org` produces:
  - `out/malaysia-uc/organization-config.yaml`
  - `out/malaysia-uc/{service-control-policies,rcp-policies,declarative-policies,aiservices-optout}/*.json`
  - `reports/org.md`, `unmapped/org.json`
- Counters: mapped=13, unmapped=5, dropped=0.

**Observations / rework log:**
- **[REWORK]** All 5 UNMAPPED entries are `deploymentTargets` placeholders. SLZ passes
  target OU IDs at deploy time via CFN params — no static mapping. Defaulted to
  `[Infrastructure, Security, Workloads]` + Root for AI opt-out. L2 pass must confirm.
- **[REWORK]** OU tree structure differs from LZA UC default:
  - SLZ: `Workloads/Production`, `Workloads/NonProduction`, plus top-level `Sandbox`, `Forensic`.
  - LZA UC default: `Workloads/{Dev,Test,Prod}`, `Workloads/Sandbox`.
  - Kept SLZ shape verbatim. Downstream: SCP/backup policy defaults in UC assume the LZA
    shape; when we assemble accounts/security/backup configs, tighten `deploymentTargets`
    to SLZ names.
- **[REWORK]** SLZ has no quarantine SCP. Emitted `quarantineNewAccounts.enable: false`.
  LZA UC default is `true`. Flag for reviewer — worth adopting.
- **[GEN]** `POLICY_TYPE_MAP` in `mappers/org.py` cleanly dispatches all 4 AWS policy Types
  seen. Reusable as-is for any CFN-native LZ.
- **[GEN]** `_extract_ou_tree` handles arbitrary-depth nested OUs via `ParentId` Ref chain.
  Reusable.
- **[GEN]** Fixed PyYAML anchor emission (`&id001`) with `NoAliasDumper`. Global change,
  benefits all downstream domains.
- **[MY]** `DECLARATIVE_POLICY_EC2` was bundled inside `lz-organization-scp-guardrails.json`
  alongside the SCP. Handled correctly (dispatch by CFN policy Type). Note for other
  variants: cannot assume one-policy-per-file.
- **[RISK]** RCP `type` field: LZA UC example shows no `type:` on RCP entries; stripped.
  Verify against LZA config schema in task #3.
- **[RISK]** `MYSLZ-` prefix hardcoded in output name. Should be a `{{ AcceleratorPrefix }}`
  token so replacements-config drives it. Defer to task #9 (replacements pass).

**Reusability progress:**
- `src/common.py`, `src/mappers/org.py` — **[GEN]**, no Malaysia strings.
- `src/profile_malaysia.py` — **[MY]** all source-specific conventions isolated here.
- Engine/profile split is working. Second variant = new `profile_<name>.py`.

### 2026-09-12 — org schema validation (task #3)

Verified converter output against LZA source of truth:
`awslabs/landing-zone-accelerator-on-aws source/packages/@aws-accelerator/config/lib/organization-config.ts`

**Findings + fixes applied:**
- **[BLOCKER→FIXED]** `aiServicesOptOutPolicy` field **does not exist** on `OrganizationConfig`
  (confirmed by grep across schema TS + JSON-schema). Only `AISERVICES_OPT_OUT_POLICY`
  string appears in constructs, not user config surface. Removed from
  `organization-config.yaml`; policy body persisted under
  `out/malaysia-uc/customizations/aiservices-optout/` for reviewer to wire via
  `customizations-config.yaml` raw CFN passthrough of
  `AWS::Organizations::Policy Type=AISERVICES_OPT_OUT_POLICY`.
- **[FIX]** Added `strategy: deny-list` to SCP + RCP entries per
  `ServiceControlPolicyConfig` / `ResourceControlPolicyConfig` schema defaults.
- **[FIX]** Stripped `type` from RCP entries; only SCP has `type: customerManaged`.
- **[FIX]** Stripped `type` + `strategy` from declarative-policy entries; schema is
  name/description/policy/deploymentTargets only.

**Confirmed OK:**
- Missing top-level `backupPolicies/taggingPolicies/chatbotPolicies` — all optional,
  SLZ has none. Backup lands in task #5 (security domain has related bits) or later.
- `quarantineNewAccounts.enable: false` valid without `scpPolicyName`.

**[REWORK]** SLZ AI opt-out must be wired via customizations-config.yaml at task #9.
Precedent: any SLZ resource lacking a first-class LZA UC field goes to customizations/
subfolder and gets called out in reports.

**Post-fix counters:** mapped=12 (was 13; AI opt-out no longer counts as mapped),
unmapped=5 (4 target-defaulted + 1 AI opt-out blocker), dropped=0.

**[GEN]** Pattern established: **validate mapper output against LZA source schema
before extending to next domain.** Adding to every future domain's Definition of Done.

### 2026-09-12 — org L2 pass (task #4)

Resolved all 5 UNMAPPED items via SLZ CFN param wiring + readme:

- Discovered `lz-organization-guardrails.yaml` nested-stack passes
  `TargetRootOrgIdforEC2Settings` and `TargetRootOrgIdforAIServicesPolicy` from
  `!ImportValue lz-organization-RootId` → both declarative EC2 and AI opt-out target
  Root, not per-OU list.
- SCP baseline + approved-services + RCP guardrail all take runtime
  `TargetOrganizationalUnitIds` (comma list). L2 default: all non-Suspended top-level
  OUs (Infra, Security, Workloads, Sandbox, Forensic). Sandbox+Forensic included so
  those OUs are not silently unprotected.
- AI opt-out: emitted as `customizations-config.yaml` cloudFormationStacks entry
  referencing hand-authored `cloudformation/ai-services-optout.yaml` stub. Reviewer
  authors the stub (5-line CFN wrapping the JSON body persisted at
  `out/malaysia-uc/customizations/aiservices-optout/my-slz-ai-optout.json`).

**Post-L2 counters:** mapped=13, unmapped=0, dropped=0. Org domain closed.

**[GEN] Pattern added:** `src/mappers/customizations.py` aggregator queue. Any domain
mapper facing a "no first-class UC field" case calls a registrar; final pipeline pass
writes single `customizations-config.yaml`. Also emits `customizations.notes.md` with
reviewer instructions per entry. Reusable for all downstream domains.

**[REWORK deferred to task #9]:** hand-author `cloudformation/ai-services-optout.yaml`
stub inside the output profile before deploy. Trivial (~15 lines of CFN).

**[GEN observation]:** L1→L2 flow works as designed. L1 emitted 5 unmapped placeholders;
L2 reading source CFN + readme resolved all 5 into concrete choices logged in profile.
Confidence check for downstream domains.

### 2026-09-12 — security domain (task #5)

**Counters:** mapped=13, unmapped=1, dropped=46. `security-config.yaml` +
2 KMS key policy files emitted. Customizations queue grew from 1 → 2.

**[GEN pattern added]** CFN short-tag YAML support: `common._yaml_load_cfn`
extends SafeLoader with `!Ref/!GetAtt/!Sub/!ImportValue/!Join/!If/!And/!Or/…`
so SLZ YAML templates parse. Preserves intrinsics as `{'Fn::X': ...}` dicts so
mappers can still inspect if needed. Used by every domain from here on.

**[GEN pattern added]** Dispatch tables: `CUSTOM_HANDLERS`, `UNMAPPED_CUSTOM`,
`BACKING_TYPES`, `FILE_TO_CUSTOMIZATIONS`. Adding a new handler = 1 dict entry
+ 1 function. Backing infra dropped by type; whole files can be routed to
customizations passthrough by adding to FILE_TO_CUSTOMIZATIONS. Both reusable.

**[GEN pattern added]** Cross-domain deferrals via `out/malaysia-uc/_deferrals/*.json`.
Security handlers can push a `_defer_to_global` / `_defer_to_network` fragment;
downstream mappers merge them. Prevents duplicate logic when SSM/IPAM
delegation intent originates in a security-domain source file.

**[GEN pattern added]** `register_file_passthrough` in customizations aggregator —
whole-file bundles registered by file stem + note. Complements per-resource
`register_ai_optout`.

**Mapper decisions this round (all L2-confirmed against LZA source schema):**
- `guardduty.ec2Protection = {enable, keepSnapshots:false}` — SLZ
  `MalwareProtectionEC2` param maps to LZA GuardDutyEc2ProtectionConfig, not to
  a fictional `malwareProtection` block (my first attempt). Schema-grep caught.
- `guardduty.eksProtection` — no `auditLogs` field per schema; dropped.
- `guardduty.exportConfiguration` fields verified.
- `accessAnalyzer.enable: true` from AWS::AccessAnalyzer::Analyzer presence.
- `iamPasswordPolicy` fields all filled from CFN Param Defaults.
- KMS: only `lz-organization-kms-iam.json` yields real org-wide keys
  (CloudWatchLogsKey + ControlTowerBackupKey → `keyManagementService.keySets`).
  All per-file KMS keys are backing infra for Lambda log encryption — dropped.
- `centralSecurityServices.delegatedAdminAccount = 'Audit'` per SLZ readme
  step 7 ("Set Security Audit Admin Account to Control Tower audit account").
  Matches LZA default.

**Whole-file passthrough registered:**
- `lz-audit-guardduty-notifications.yaml` → customizations entry
  `MYSLZ-guardduty-findings-notifications`. GuardDuty→EventBridge→SNS→email
  pipeline has no first-class LZA UC field. Reviewer copies template verbatim
  into `config/cloudformation/guardduty-findings-notifications.yaml` at deploy.

**[REWORK] deferred:**
- `Custom::SSMDefaultHostManagement` — remaining unmapped. Options at task #8:
  (a) SSM document via `security-config.yaml centralSecurityServices.ssmAutomation`,
  (b) customizations passthrough. Trivial custom-resource; (a) preferred.
- CloudWatchLogsKey alias resolved from `Fn::FindInMap`, not a Parameter Ref.
  Extractor fell back to `<name>-alias` placeholder. Add `Fn::FindInMap` +
  `Mappings` resolution to `common.resolve_ref` when a domain actually needs it.
- SLZ ControlTower KMS-CMK ("control-tower-key") from readme step 2 is created
  manually pre-LZA — not in any CFN template. LZA-with-CT expects a CT KMS key
  to already exist. Confirm at task #9 during accounts-config assembly.
- `awsConfig.enableConfigurationRecorder: false` — SLZ delegates Config to CT.
  Verify at task #10 dry-run that LZA-with-CT mode leaves this off correctly.

**Reusability observation:** dispatch-table + per-file passthrough pattern is
paying off. Adding network mappers next will be N handlers, not N conditionals.

### 2026-09-12 — iam + global (task #6)

**Counters:** iam mapped=4/unmapped=0/dropped=0; global mapped=4/unmapped=0/dropped=0.

**IAM mapper (`mappers/iam.py`):**
- 4 `AWS::SSO::PermissionSet` → `identityCenter.identityCenterPermissionSets`
- `ManagedPolicies` ARNs stripped to LZA `awsManaged` short names
- `SessionDuration` (ISO-8601 `PT<n>H`) → minutes integer
- `identityCenterAssignments: []` — SLZ does not define assignments in CFN
  (post-deploy console work). Flagged in file header for reviewer.

**Global mapper (`mappers/globalcfg.py`):**
- Largely synthesized (no dedicated SLZ CFN source; SLZ delegates
  CloudTrail/Config to Control Tower).
- Consumes security-domain `_deferrals/global.json` for `logging.sessionManager`
  values (idleTimeout/maxDuration from SSM session prefs custom resource).
- `homeRegion: ap-southeast-5`; `enabledRegions: [ap-southeast-5, us-east-1]`
  (SLZ readme step 7 requires us-east-1 for FMS delegation).
- `controlTower.enable: true` — LZA-with-CT mode matches SLZ assumption.
- `managementAccountAccessRole: AWSControlTowerExecution` — used by SLZ SCPs
  as the escape-hatch principal.
- `logging.cloudtrail.enable: false` — Control Tower manages the org trail;
  double-enabling would create duplicate trails.

**[GEN pattern added]** Domain-ordering matters: security must run before global
(deferral producer/consumer). `run.py` `DOMAINS` dict is now order-sensitive;
documented in the module.

**[GEN pattern added]** Synthesized mappers alongside extraction mappers. Global
is our first purely-synthesized domain — no dedicated CFN input file, just
profile constants + upstream deferrals. Reusable pattern for domains where the
source LZ lacks explicit config (e.g., logging in LZA-with-CT variants).

**[REWORK deferred to task #9]:**
- IdC principal assignments (`identityCenterAssignments`). Requires knowing the
  IdC groups defined by the customer's IdP. SLZ leaves this to console; UC
  requires it declared. Emit stub during accounts assembly + flag as blocker.
- Global-config `tags`, `snsTopics`, `backup` — not in SLZ scope; leave empty.

**[RISK]** `logging.sessionManager.attachPolicyToIamRoles: []` — SLZ's SSM
session baseline attaches a policy to per-account roles. LZA has this list
but empty means "no attach", which will diverge from SLZ behaviour. Reviewer
must populate at task #9.

### 2026-09-12 — network domain (task #7) — PARTIAL

**Counters:** mapped=52, unmapped=125 (all [REWORK]-flagged), dropped=9.
`network-config.yaml` (244 lines) + `firewall-rules/suricata-rules.txt` (verbatim).

**Deliberate scope:** high-level structural extraction only. Full mechanical
CFN → LZA translation of Route / RouteTable / NetworkAclEntry / TransitGatewayRoute
etc. is not attempted — SLZ authored these individually in CFN whereas LZA
models routing declaratively per-VPC/subnet with implicit association.
Attempting a per-resource translation risks silently mis-wiring the netfabric.
Emit skeleton with correct high-level shape; flag detail as [REWORK] for
hand-port at task #9.

**What was extracted structurally:**
- 2 central VPCs (NetworkInspection 10.25.12.0/22 + NetworkEndpoints 10.25.16.0/22)
  with subnet lists (name + CIDR)
- 1 TGW with 2 route tables (TGW-Network-Main-Core, TGW-Network-Main-Spoke)
- 12 VPC endpoints (services listed under NetworkEndpoints VPC)
- NFW policy + firewall stub (Suricata rules referenced)
- 1 spoke `vpcTemplates[]` entry from `lz-account-vpc-template.yaml`
- Suricata rules copied to `firewall-rules/suricata-rules.txt` (verbatim, 74 lines)
- RAM ResourceShare recognized (modeled via TGW.shareTargets convention)
- VPC FlowLog entries recognized (folded into `vpcFlowLogs` global)

**What was DELIBERATELY not translated (all [REWORK] flagged):**
- Subnet route-table associations — LZA per-subnet `routeTable:` field left empty
- All AWS::EC2::Route entries — LZA models routes inline under routeTables[]
- NACL rules (2 in central + 8 in spoke) — LZA has `networkAcls` block per-VPC
- IGW/NAT/EIP wiring — LZA models `natGateways:` + `internetGateway:` per-VPC
- TGW attachments + static routes — LZA `transitGatewayAttachments:` on VPCs
- NFW firewall.subnets — needs subnet-name resolution across VPCs
- Security group (only 1, likely for endpoints) — needs SG translation

**Known [REWORK]:**
- Subnet `availabilityZone` empty. SLZ uses `Fn::Select` on `Fn::GetAZs` which the
  resolver doesn't handle. Trivial: default to `${homeRegion}a/b/c` at task #9.
- TGW ASN defaulted to 64512 (SLZ Ref has no default). L2 pick — validate with
  customer.
- Firewall `subnets: []` — pending subnet-name mapping.
- `centralNetworkServices.gatewayLoadBalancers` (for NFW inspection) — SLZ
  routes via TGW appliance mode instead; may or may not port cleanly.
- Endpoint policies (`endpointPolicies: []`) — LZA supports per-endpoint
  policies via `vpc-endpoint-policies/*.json` files; SLZ uses default. Fine.

**[GEN pattern added]** Distinction between:
- **structural-recognised** types (`STRUCTURAL_TYPES`) — LZA models them at a
  higher abstraction, so per-resource CFN unmap → [REWORK] hint, not blocker
- **backing-infra** types (`BACKING_TYPES`) — dropped silently as engine-managed
- **primary** types (VPC/Subnet/TGW/TGW-RT/RAM/NFW) — extracted to LZA fields

Reusable across any CFN-native network baseline; per-LZ profile just needs
account name + share targets.

**[GEN pattern added]** Intrinsic-function resolver extended in `common.resolve_ref`
to handle `Fn::FindInMap`, `Fn::Join`, `Fn::Sub` (literal). Enables VPC/subnet
CIDR extraction from Mappings. Any future domain benefits.

**[REWORK deferred to task #9] – material hand-port required:**
- Central-network routing/NACLs/TGW attachments (highest risk surface)
- Spoke-template routing/NACLs
- NFW firewall subnet placement
- TGW ASN + AZ defaults
- Attach `firewalls[0].subnets` to specific inspection VPC subnet names
- Populate endpoint services per LZA `interfaceEndpoints.endpoints` schema
  (currently emits `{service: <full-arn>}` — LZA expects short service names
  like `s3`, `ec2`, etc.)

**[RISK highest so far]** This is the largest translation surface and the one
most likely to diverge from SLZ intent under casual review. Recommend the
task #10 dry-run + a manual `diff -u` between deployed CFN synthesis and
original SLZ templates for the network stack.

### 2026-09-12 — L2 pass on remaining UNMAPPED (task #8)

**Actions taken:**

- **Security SSM DHMC:** Added `_h_ssm_dhmc` handler in `mappers/security.py`
  that registers a customizations passthrough entry. Security unmapped 1 → 0.
  Total customizations queue now 3 entries: AI opt-out, SSM DHMC, GuardDuty
  notifications.
- **Network low-hanging fruit fixed in-mapper (no new UNMAPPED bucket):**
  - AZ resolution from subnet-name suffix (A/B/C → `ap-southeast-5{a,b,c}`)
  - Endpoint service short-name extraction (handles both literal strings and
    `{'Fn::Sub': 'com.amazonaws.${AWS::Region}.s3'}` intrinsic form)
  - NFW firewall subnet placement (SLZ convention: `NetworkInspectionTgwAttach{A,B,C}`)
  - TGW ASN default `65001` (private-ASN range; SLZ CFN param has no default)
- **Network heavy detail clustered, not resolved:** new script
  `src/l2_reports.py` reads `unmapped/network.json` and emits
  `reports/network-l2-cluster.md` — reviewer-oriented shopping list by
  source-file × CFN resource type with hand-port guidance for each cluster
  (Routes+RouteTables, NACLs, NATs+EIPs, IGW, TGW attachments/routes, DHCP,
  SecurityGroups, FlowLogs).

**Post-L2 counters:** mapped=87, unmapped=125 (all network, all clustered
into 8 hand-port groups documented in `network-l2-cluster.md`), dropped=55.

**Decision:** Do not attempt further mechanical resolution of network routing.
CFN-level `AWS::EC2::Route` + associations don't cleanly project onto LZA's
inline `routeTables[].routes[]` when SLZ uses multi-file StackSet composition
(TGW attachment refs cross template boundaries). Getting this wrong ships
broken traffic isolation. Cluster-and-defer is safer than guess-and-emit.

**Remaining known [RISK] surfaces to catch at task #10 dry-run:**
- Endpoint gateway-vs-interface segregation (currently all under
  `interfaceEndpoints`; LZA has separate `gatewayEndpoints`)
- Endpoint service short names for compound services (`ecr.dkr` came out
  as `dkr`; should be `ecr-dkr` per LZA convention — trivial fix)
- Central VPC route wiring (TGW attachment → route table pinning)
- Spoke VPC template routing (all subnets currently have `routeTable: ""`)

### 2026-09-12 — accounts + replacements (task #9)

**Counters:** accounts mapped=6/0/0; replacements mapped=7/0/0.

**Accounts (`accounts-config.yaml`):** 3 mandatory (Management/LogArchive/Audit)
+ 3 workload (SharedServices/CentralBackup/Network) inferred from SLZ readme
steps 4/5/6 + network-config account ref. Emails emitted as `{{ NameEmail }}`
Jinja tokens; reviewer resolves via replacements-config.

**Replacements (`replacements-config.yaml`):** 3 core tokens
(AcceleratorPrefix, HomeRegion, TransitGatewayASN) + 6 email placeholders
(`TODO-*@example.com`).

**[REWORK] before deploy:**
- Replace `TODO-*@example.com` email placeholders with real distribution lists
  (SLZ readme step 8: unique addresses required).
- Confirm Network account name matches whatever the customer creates in CT
  Account Factory before deploy.
- IdC assignments (from task #6) still need principal→permissionSet wiring;
  requires knowing the customer's IdC group IDs.
- Author 3 hand-written CFN stubs at `config/cloudformation/`:
  - `ai-services-optout.yaml`
  - `ssm-default-host-management.yaml`
  - `guardduty-findings-notifications.yaml` (or just copy SLZ
    `lz-audit-guardduty-notifications.yaml`)
- Hand-port network detail per `reports/network-l2-cluster.md`.

**Polish:** `common.write_yaml` now `allow_unicode=True` so em-dashes in
descriptions render literally instead of `—`.

**[GEN pattern added]** Purely synthesized mapper (`mappers/accounts.py`) with
no CFN input. Emits token-driven scaffolding for reviewer completion.
Complements globalcfg mapper — both consume profile constants only.

**Pipeline output (full):**
- 8 YAML config files: organization, security, iam, global, network, accounts,
  replacements, customizations
- 5 policy body dirs: service-control-policies/, rcp-policies/,
  declarative-policies/, kms-policies/, customizations/aiservices-optout/
- 1 firewall rules dir: firewall-rules/suricata-rules.txt
- 3 customizations passthroughs queued (reviewer authors CFN stubs)
- 7 coverage reports + 1 network L2 cluster report

### 2026-09-12 — schema audit (task #10a — SHAPE-CLEAN)

New tool: `src/schema_audit.py`. Fetches LZA JSON schemas from awslabs repo,
caches under `converter/.schemas/`, validates each of the 8 emitted YAMLs
against its root definition. Report at `reports/schema-audit.md`.

**Iteration 1:** 51 errors across 5 files.
**Iteration 2 (after fixes):** 0 errors, all 8 configs green.

**Fixes applied:**
- `organization-config.yaml`: added required empty `taggingPolicies`, `backupPolicies`,
  `chatbotPolicies` lists.
- `security-config.yaml`: added required empty `securityHub.standards` list.
- `iam-config.yaml`: omit `identityCenter.delegatedAdminAccount` when None
  (was serializing as YAML null; schema requires string).
- `replacements-config.yaml`: fundamental shape correction. LZA V1/V2
  replacements are **SSM-path-backed**, not inline `value` literals. Switched
  to `key`+`path`+`type` shape. Dropped disallowed `description` field. Added
  companion `bootstrap-ssm-params.sh` script that reviewer runs to
  pre-populate the SSM params before pipeline execution.
- `network-config.yaml`:
  - Dropped invalid `firewall.region` field (inherits from vpc).
  - Renamed `firewallPolicy.statefulRuleGroupReferences` →
    `firewallPolicy.statefulRuleGroups` per schema.
  - Added required `rules[].capacity: 1000`.
  - Dropped internal `_type` field on `interfaceEndpoints`; split
    Gateway-type endpoints (s3, dynamodb) into `gatewayEndpoints`.
  - `interfaceEndpoints.subnets` required — emitted `["TODO-endpoint-subnet-a"]`
    stub (reviewer replaces).
  - Empty `subnets[].routeTable` → `"TODO-rt"` stub (reviewer replaces).
  - Empty `availabilityZone` → `ap-southeast-5a` fallback (reviewer verifies).

**Practical outcome:** schema-valid does NOT mean deploy-ready. TODO stubs will
fail at LZA engine validation phase (task #10b). Purpose of stubs: make it
possible to *load* the config into engine without JSON-parse errors, so the
engine's own semantic validation runs and produces actionable errors.

**[GEN pattern added]** Schema-audit-then-fix loop as standard step per domain.
Tool is generic (dispatches by filename → schema+root-def map). Reusable for
any UC profile.

**[RISK cleared]** All 8 configs now parse against LZA schemas. Structural
shape confirmed. Content correctness (routing intent, account mapping) still
requires task #10b engine dry-run.

### 2026-09-12 — reusability extraction (task #11)

Refactored engine/profile split so second variant = drop-in new profile file.

**Changes:**
- New `src/profile.py` — profile loader. Reads `CONVERTER_PROFILE` env var
  (defaults to `malaysia`), imports `converter.src.profiles.<name>`, re-exports
  all constants. Mappers now import from `..profile`, not `..profile_malaysia`.
- Moved `profile_malaysia.py` → `src/profiles/malaysia.py`. Added path
  constants (`SOURCE_DIR`, `OUT_DIR`, `UNMAPPED_DIR`, `REPORTS_DIR`) to
  profile so `common.py` is fully generic.
- `common.py` reads paths from `_profile`; `SLZ_CFN` retained as back-compat
  alias for `SOURCE_DIR`.
- Reports + unmapped now under per-profile subdirs
  (`reports/malaysia/`, `unmapped/malaysia/`) so multiple profiles coexist.
- `run.py` accepts `--profile <name>` CLI arg; sets env var before mapper
  imports trigger profile load. Also prints `profile=` + `out=` at start.
- New `src/profiles/_template.py` — reference template. Copy → fill → run.
- New `converter/REUSABILITY.md` — reviewer guide: layout, how to add a
  profile, when to extend engine vs profile, `[GEN]` vs `[MY]` boundary.

**Post-refactor verification:**
- `python -m converter.src.run --profile malaysia` — green, identical output
  to pre-refactor pipeline (mapped=105 / unmapped=125 / dropped=55).
- `python -m converter.src.schema_audit` — 8/8 pass.
- `python -m converter.src.run --profile _template` — fails with source-file
  not-found (expected; template has placeholder paths).

**Engine/profile boundary reaffirmed:**
- `[GEN]`: common.py, profile.py, run.py, schema_audit.py, l2_reports.py, all
  mappers/*.py, customizations aggregator
- `[MY]`: profiles/malaysia.py only

Second variant conversion is now: `cp _template.py <name>.py && fill && run`.

### 2026-09-12 — LZA engine dry-run (task #12/10b)

**Setup:** Cloned `awslabs/landing-zone-accelerator-on-aws@main` (v1.16.2) to
`lza-engine/`. `yarn install` + built `@aws-lza` then `@aws-accelerator/config`
and `@aws-accelerator/accelerator`. Ran `config-validator.ts` against
`out/malaysia-uc/` with dummy AWS creds + `AWS_MAX_ATTEMPTS=1` (fail-fast).

**Iterated 4×, converged 58 → 28 network / 12 accounts / 3 customizations.**
All 43 remaining issues = deliberate TODO stubs.

**Fixes applied to mapper source (not one-off patches):**
1. `mappers/network.py _az_from_name` — return single letter `"a"` not
   `f"{HOME_REGION}a"`. Both fallbacks updated.
2. `mappers/accounts.py build_replacements_config` — LZA V2 `type=String/Number`
   uses inline `value` field; `path` only for `type=SSM`. Rewrote emitter,
   dropped `bootstrap-ssm-params.sh` (no longer needed).
3. `mappers/network.py _extract_vpcs` — split Gateway vs Interface endpoints
   into `gatewayEndpoints` / `interfaceEndpoints`. defaultPolicy required
   on both by schema; added stub `OpenAccess` reference.
4. `mappers/network.py build_network_config` — synthesize top-level
   `endpointPolicies: [{name: OpenAccess, document: ...}]` entry + write
   permissive `vpc-endpoint-policies/open-access.json` stub.

**Engine catches what Python schema audit missed:**
- Cross-reference validation (routeTable name must exist in same VPC)
- Email format validation
- CFN template file existence check under customizations
- AZ naming convention (single letter)

Confirms engine dry-run is the real gate; jsonschema audit is necessary but
not sufficient.

**Report:** `converter/reports/malaysia/engine-dry-run.md`.

**[GEN pattern added]** Engine dry-run loop as final validation step per
profile. Add to reusability guide: after schema audit passes, run LZA
engine `config-validator.ts` before declaring conversion done.

**Verdict:** conversion is at automation ceiling. All fixes discoverable
by the engine are applied to the mapper source. Remaining 43 issues are
enumerated hand-port items reviewer expects.
