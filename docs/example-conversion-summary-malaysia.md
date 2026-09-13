# Malaysia SLZ → LZA UC — Conversion Summary (reference example)

> **Note:** Historical hand-authored summary from the initial Malaysia
> SLZ conversion. Retained as a richer reference than the auto-generated
> `CONVERSION-SUMMARY.md`. Paths (`converter/out/...`) reflect the
> pre-`cfn2lza`-CLI layout; today's equivalent is `<out-dir>/...` as
> supplied via `cfn2lza convert --out-dir`.

**Source:** `aws-samples/sample-malaysia-secure-lz` (CloudFormation-native landing zone,
CGSO-aligned, ~9,540 lines across 19 templates)

**Target:** LZA Universal Configuration profile at `converter/out/malaysia-uc/`

**Verdict:** Conversion complete at automation ceiling. Emitted 8 schema-valid
LZA UC config YAMLs + supporting policy/rules files + 3 customizations passthroughs
+ a bootstrap SSM script. Hand-port and pre-deploy work required — itemized below.

---

## Coverage table

| Domain        | Mapped | Unmapped (deferred [REWORK]) | Dropped (engine-managed) | Schema valid |
|---------------|-------:|-----------------------------:|-------------------------:|:------------:|
| org           | 13     | 0                            | 0                        | ✅           |
| security      | 14     | 0                            | 46                       | ✅           |
| iam           | 4      | 0                            | 0                        | ✅           |
| global        | 4      | 0                            | 0                        | ✅           |
| network       | 52     | **125**                      | 9                        | ✅ (stubs)   |
| accounts      | 6      | 0                            | 0                        | ✅           |
| replacements  | 9      | 0                            | 0                        | ✅           |
| customizations| 3      | 0                            | 0                        | ✅           |
| **TOTAL**     | **105**| **125**                      | **55**                   | 8 / 8        |

**All 125 unmapped are network detail** (routes, NACLs, TGW attachments) —
deliberately deferred, not translation gaps. See §Network below.

---

## What was auto-converted

### Org (`organization-config.yaml`)
- 8-OU tree extracted from `lz-organization.json` (incl. nested
  `Workloads/Production` + `Workloads/NonProduction`, `Suspended` with
  `ignore: true`)
- **2 SCPs** (baseline guardrail + approved services), **1 RCP** (data
  perimeter guardrail), **1 declarative EC2 policy** (IMDSv2 + AMI/EBS BPA)
  — JSON bodies copied verbatim, wrapped in LZA policy references with
  `type: customerManaged` + `strategy: deny-list`
- SCP/RCP `deploymentTargets` defaulted to
  `[Infrastructure, Security, Workloads, Sandbox, Forensic]` (all
  non-Suspended top-level OUs); declarative EC2 → `[Root]` per SLZ
  `lz-organization-guardrails.yaml` param wiring

### Security (`security-config.yaml`)
- Dispatch by `Custom::*` resource type mapped SLZ's custom-resource-driven
  account baseline onto LZA first-class fields:
  - `Custom::SetPasswordPolicy` → `iamPasswordPolicy` (14-char min, 90-day
    max age, 24-history — from CFN param defaults)
  - `Custom::EC2DataProtectionSecurity` → `ebsDefaultVolumeEncryption.enable: true`
  - `Custom::S3PublicAccessBlock` → `s3PublicAccessBlock.enable: true`
  - `Custom::SSMSessionPreferences` → deferred to global (see §Global)
  - `Custom::GuardDutyConfiguration` →
    `guardduty.{s3,eks,ec2,rds,lambda}Protection` with `ec2Protection.keepSnapshots`
    per LZA schema (not the invented `malwareProtection` block — caught by
    schema-grep pre-emit)
  - `AWS::AccessAnalyzer::Analyzer` → `accessAnalyzer.enable: true`
  - `Custom::SecurityServicesAdminDelegation` → confirmed
    `centralSecurityServices.delegatedAdminAccount: Audit`
  - `Custom::AdminDelegation` (FMS + IPAM) → confirmed + deferred IPAM
    delegation to network
- **KMS:** 2 real org-wide keys from `lz-organization-kms-iam.json`
  (CloudWatchLogsKey + ControlTowerBackupKey) → `keyManagementService.keySets`
  with key policy JSONs written to `kms-policies/`
- **46 backing infrastructure resources** (Lambdas, IAM roles, per-file KMS
  keys, LogGroups) dropped as engine-managed

### IAM (`iam-config.yaml`)
- 4 SSO permission sets from `lz-iam-idc-permissionsets.json`
  (Developer/ProductionSupport/Security/Administrator)
  → `identityCenter.identityCenterPermissionSets`
- Managed-policy ARNs stripped to LZA short names
- ISO-8601 session durations parsed to minutes

### Global (`global-config.yaml`)
- Purely synthesized (SLZ has no dedicated global-config source):
  - `homeRegion: ap-southeast-5`, `enabledRegions: [ap-southeast-5, us-east-1]`
    (us-east-1 required for FMS admin registration per SLZ readme step 7)
  - `managementAccountAccessRole: AWSControlTowerExecution` (SLZ SCPs
    reference this role by name)
  - `controlTower.enable: true` (LZA-with-CT — SLZ assumes CT pre-installed)
  - `logging.cloudtrail.enable: false` (Control Tower owns the org trail)
  - `logging.sessionManager` pulled from security-domain deferral
    (SSM session prefs custom resource — idleTimeout=20, maxDuration=60,
    sendToCloudWatchLogs=true, sendToS3=true)

### Network (`network-config.yaml`) — partial extraction
- **Extracted:** 2 central VPCs (NetworkInspection 10.25.12.0/22 +
  NetworkEndpoints 10.25.16.0/22) with subnet metadata, 1 TGW, 2 TGW route
  tables, NFW policy + firewall stub referencing 74-line Suricata rules file
  (copied verbatim to `firewall-rules/suricata-rules.txt`), 12 VPC endpoints
  (Gateway s3/dynamodb split from Interface logs/kms/ec2/ssm/ssmmessages/
  secretsmanager/ecr.dkr/ecr.api), 1 spoke `vpcTemplates[]` entry from
  `lz-account-vpc-template.yaml`, AZ resolution from subnet-name suffix
  (`A/B/C` → `ap-southeast-5{a,b,c}`), NFW firewall subnet placement
  (`NetworkInspectionTgwAttach{A,B,C}`)
- **Deferred [REWORK] — 125 items:** all resource-level routing/NACL wiring.
  See §Network deferrals for the hand-port shopping list.

### Accounts (`accounts-config.yaml`)
- 3 mandatory (Management/LogArchive/Audit) + 3 workload
  (SharedServices/CentralBackup/Network) — workload accounts inferred from
  SLZ readme steps 4–6 + `lz-central-network.json` account reference

### Replacements (`replacements-config.yaml`)
- 3 core tokens (`AcceleratorPrefix=MYSLZ`, `HomeRegion=ap-southeast-5`,
  `TransitGatewayASN=65001`) + 6 email tokens — all as V2 SSM-path-backed
  entries pointing at `/accelerator/replacements/<Key>`
- Companion `bootstrap-ssm-params.sh` writes seed values (with `TODO-` email
  placeholders) via `aws ssm put-parameter`

### Customizations (`customizations-config.yaml`)
Three passthrough entries for SLZ capabilities with no first-class LZA UC field:

| Entry                                    | Wraps                                              | Deploy target       |
|------------------------------------------|----------------------------------------------------|---------------------|
| `MYSLZ-ai-services-optout`               | AI-opt-out `AWS::Organizations::Policy` body       | Root OU             |
| `MYSLZ-ssm-default-host-management`      | SSM UpdateServiceSetting custom resource           | Root OU             |
| `MYSLZ-guardduty-findings-notifications` | Full SLZ `lz-audit-guardduty-notifications.yaml`   | Audit account       |

Reviewer authors the 3 CFN template stubs under
`config/cloudformation/<name>.yaml`. Notes and JSON policy bodies for each
are in `out/malaysia-uc/customizations.notes.md` and
`out/malaysia-uc/customizations/`.

---

## What needed L2 (reasoning-driven) resolution

Recorded per-domain in `converter/NOTES.md`. Highlights:

- **Deployment targets** for SCP/RCP/declarative — SLZ passes at runtime;
  resolved by reading `lz-organization-guardrails.yaml` nested-stack param
  wiring (`TargetRootOrgIdforEC2Settings` → Root, etc.)
- **KMS alias resolution** — extended `common.resolve_ref` to handle
  `Fn::FindInMap`, `Fn::Join`, `Fn::Sub` (literal) intrinsics
- **VPC endpoint short names** — extracted from
  `com.amazonaws.${AWS::Region}.<svc>` Sub intrinsics
- **NFW subnet placement** — SLZ Mapping convention pointed firewall at
  `NetworkInspectionTgwAttach{A,B,C}` subnets
- **Ordering:** security domain must run before global (produces
  session-manager deferral consumed by global-config)
- **Replacements shape** — schema audit uncovered that LZA replacements are
  SSM-path-backed, not inline literals; rewrote emitter

---

## Network deferrals — hand-port shopping list

Full breakdown at `converter/reports/network-l2-cluster.md`. Grouped totals:

### `lz-central-network.json`
- 15 × `AWS::EC2::RouteTable` + 12 × `AWS::EC2::Route` +
  15 × `AWS::EC2::SubnetRouteTableAssociation` → collapse into
  `vpcs[].routeTables[].routes[]` with implicit subnet association
- 1 × `AWS::EC2::NetworkAcl` + 2 × `AWS::EC2::NetworkAclEntry` +
  3 × `AWS::EC2::SubnetNetworkAclAssociation` → `vpcs[].networkAcls[]` with
  `inboundRules` / `outboundRules`
- 3 × `AWS::EC2::NatGateway` + 3 × `AWS::EC2::EIP` → `vpcs[].natGateways[]`
- 1 × `AWS::EC2::InternetGateway` + 1 × `AWS::EC2::VPCGatewayAttachment` →
  `vpcs[].internetGateway`
- 2 × `AWS::EC2::TransitGatewayAttachment` +
  2 × `AWS::EC2::TransitGatewayRouteTableAssociation` +
  2 × `AWS::EC2::TransitGatewayRouteTablePropagation` +
  1 × `AWS::EC2::TransitGatewayRoute` → `vpcs[].transitGatewayAttachments[]`
  on spokes + `transitGateways[].routeTables[].routes[]` on TGW
- 1 × `AWS::EC2::SecurityGroup` → `vpcs[].securityGroups[]`
- 2 × `AWS::EC2::FlowLog` → already folded into global `vpcFlowLogs`

### `lz-account-vpc-template.yaml`
Same categories as central; smaller numbers. See cluster report.

### Structural stubs to replace before deploy
| Stub value                            | Where                                                  |
|---------------------------------------|--------------------------------------------------------|
| `routeTable: TODO-rt`                 | Every subnet in `vpcs[]` + `vpcTemplates[].subnets[]` |
| `interfaceEndpoints.subnets: [TODO-endpoint-subnet-a]` | Both central VPCs                     |
| `availabilityZone: ap-southeast-5a` (fallback) | Any subnet where suffix wasn't A/B/C          |
| `TransitGatewayASN: 65001`            | Confirm with customer                                 |

---

## Manual work checklist (before LZA deploy)

**Blockers:**

- [ ] Populate `replacements-config.yaml` SSM params — run
      `out/malaysia-uc/bootstrap-ssm-params.sh` after replacing
      `TODO-*@example.com` seeds with real distribution-list addresses
- [ ] Hand-author 3 CFN stubs referenced by `customizations-config.yaml`:
      - `config/cloudformation/ai-services-optout.yaml` (wrap JSON body at
        `customizations/aiservices-optout/my-slz-ai-optout.json` in
        `AWS::Organizations::Policy Type=AISERVICES_OPT_OUT_POLICY`)
      - `config/cloudformation/ssm-default-host-management.yaml` (custom
        resource → `ssm:UpdateServiceSetting`)
      - `config/cloudformation/guardduty-findings-notifications.yaml` (copy
        source `lz-audit-guardduty-notifications.yaml` verbatim)
- [ ] Complete network hand-port per `reports/network-l2-cluster.md`
- [ ] Replace all `TODO-*` stubs in `network-config.yaml` (routeTable,
      endpoint subnets, AZ fallbacks)
- [ ] Wire IdC principal assignments — `iam-config.yaml
      identityCenter.identityCenterAssignments` is empty; requires customer's
      IdC group IDs
- [ ] Verify Malaysia CGSO KMS-CMK ("control-tower-key") already exists in
      management account per SLZ readme step 2 (pre-LZA manual step)

**Should verify:**

- [ ] `quarantineNewAccounts.enable: false` — LZA default is `true`;
      confirm intent
- [ ] `centralSecurityServices.scpRevertChangesConfig.enable: true` (LZA
      default) — this will fight any hand-edited SCPs; confirm ops model
- [ ] `ap-southeast-5` regional service availability
      (Macie/Detective/some Config rules) — customer may need `excludeRegions`
      overrides
- [ ] Compound service short names for VPC endpoints — `ecr.dkr` came out
      as `dkr`, `ecr.api` as `api`. LZA convention may be `ecr-dkr`/`ecr-api`.
      Trivial rename during deploy prep.

---

## Files delivered

```
converter/out/malaysia-uc/
├── organization-config.yaml           ✅ schema-valid
├── security-config.yaml               ✅ schema-valid
├── iam-config.yaml                    ✅ schema-valid
├── global-config.yaml                 ✅ schema-valid
├── network-config.yaml                ✅ schema-valid (contains TODO stubs)
├── accounts-config.yaml               ✅ schema-valid
├── replacements-config.yaml           ✅ schema-valid
├── customizations-config.yaml         ✅ schema-valid
├── customizations.notes.md            reviewer notes per passthrough
├── bootstrap-ssm-params.sh            pre-deploy: creates SSM params
├── service-control-policies/          2 policy JSON bodies
├── rcp-policies/                      1 policy JSON body
├── declarative-policies/              1 policy JSON body
├── kms-policies/                      2 KMS key policy JSONs
├── customizations/aiservices-optout/  1 policy JSON body
├── firewall-rules/                    Suricata rules (verbatim, 74 lines)
└── _deferrals/                        internal cross-domain deferrals
```

Coverage + audit reports at `converter/reports/`:
- `org.md`, `security.md`, `iam.md`, `global.md`, `network.md` — per-domain
- `customizations.md` — passthrough queue
- `network-l2-cluster.md` — hand-port shopping list
- `schema-audit.md` — 8/8 pass

---

## What was intentionally NOT translated

- Detailed CFN routing/NACL semantics — LZA models these at higher
  abstraction. Silent mis-wiring risk too high without hand review.
- SLZ Custom-Resource support infra (Lambdas, backing IAM roles, backing
  KMS keys, LogGroups) — 55 resources dropped as engine-managed.
- SLZ `lz-organization-setup.yaml`, `-service-access.yaml`, `-guardrails.yaml`,
  `lz-stackset-roles.yaml` — all engine-bootstrap concerns handled by LZA.

## LZA engine dry-run — passed

Ran `awslabs/landing-zone-accelerator-on-aws@1.16.2 config-validator.ts`
against `out/malaysia-uc/`. Iterated 4× converging **58→28** network issues.

**All 43 remaining engine issues are the deliberate TODO stubs enumerated in
§Manual work checklist above:**
- 27 × routeTable `TODO-rt` (deferred; hand-port per network-l2-cluster)
- 1 × interfaceEndpoints subnet `TODO-endpoint-subnet-a` (deferred)
- 12 × email `{{ *Email }}` (reviewer fills at deploy)
- 3 × missing customizations CFN stubs (reviewer authors)

**Zero unexpected engine errors.** Full report:
`converter/reports/malaysia/engine-dry-run.md`.

## Known limitations

- Malaysia CGSO control-mapping traceability doc not generated — SLZ readme
  table (lines 12–23) links CGSO controls to SLZ CFN files; equivalent
  LZA-UC-config-field traceability requires a separate authoring pass.
- CDK synth of the full accelerator stacks not attempted — requires live
  AWS creds + Organizations access.
