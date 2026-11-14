# Week 19, activity 3: foundation stack (KMS, VPC, endpoints, IAM, spend controls)

Status: **code and no-AWS tests complete; real deployment not run** (it needs Manuel's OK for the exact diff, and the
steps below that need his action). Nothing in this file is a measured deployment time yet.

## Design

Two stacks per profile (`semana-19/infra/cdk/app.py`, profile values in `semana-19/spike/perfiles.json`):

| Stack | Persists | Contents | How it is deployed |
|---|---|---|---|
| `semana19-control` | yes, $0/h | boundary `semana19-limite`, freeze `semana19-congelar`, CDK execution policy `semana19-cfn-exec`, deploy role `semana19-despliegue`, budget `semana19` ($5, alerts ACTUAL 50 %, ACTUAL 100 %, FORECASTED 100 %), budget action (APPLY_IAM_POLICY at 100 % ACTUAL), role of the action. The Cost Anomaly monitor is **not** in the stack: its price is N (decision b, 2026-11-13) | `aws cloudformation deploy` (no assets, so no bootstrap needed) |
| `semana19-base` | no, per session | KMS key `alias/semana19` (rotation on), VPC (2 private isolated subnets in lab, 3 in prod, no IGW, no NAT, default SG restricted), S3 gateway endpoint, interface endpoints CloudWatch Logs and Step Functions (ADR 0005) in 1 AZ in lab and 3 in prod (ADR 0006), security groups (tools Lambda SG empty; endpoint SG 443 only from it), VPC flow logs to an encrypted group (1 day in lab, 365 in prod), flow-log role | `cdk deploy` with the `s19` qualifier after the bootstrap |
| bootstrap `semana19-cdktoolkit` | no | CDK bootstrap, qualifier `s19`, execution policy `semana19-cfn-exec` (not AdministratorAccess), trust only `semana19-despliegue` | `cdk bootstrap` with the admin profile |

Order of the first deployment (the trust chain has no cycle): control (CLI) → bootstrap (trusts the deploy role
that control created) → base (CDK, through the deploy role).

## Decisions and deviations from the plan

- **Bootstrap name:** `semana19-cdktoolkit` with qualifier `s19`, as in the latest instruction. The earlier answer said `CDKToolkit-s19`; the latest one supersedes it.
- **cdk-nag 2.38.2** (already confirmed in activity 2; 3.0.2 fails on synth).
- **The budget `semana19` is created by the control stack.** `infra/presupuesto.py` was not run with `--si` (checked: `describe-budgets` lists only `My Zero-Spend Budget` and `aip-lab-cero`, which are not ours and are not touched). It is marked superseded.
- **Cost Explorer: 0 calls so far.** The inventory does not call Cost Explorer: the anomaly monitor is checked through its stack. Whether a Cost Anomaly API call costs $0.01 is not confirmed (see prices).
- **Pending-deletion keys:** the base key uses the lab window of 7 days. The bootstrap key has no window in its template, so CloudFormation uses its default of 30 days. A key pending deletion is not billed (official page, quoted below), so it stays in the inventory as an allowed exception with its date.

## Freeze (option B, chosen by Manuel 2026-11-13)

The budget action at 100 % attaches `semana19-congelar` (create and update denied, delete allowed) to:

- `semana19-despliegue` always;
- `cdk-s19-deploy-role-<account>-us-east-1` and `cdk-s19-cfn-exec-role-<account>-us-east-1` **when the parameter
  `BootstrapCreado` is `true`**. Those names contain the account, so they are resolved by a CloudFormation `Fn::If`
  at deploy time and never written in the repo.

`desplegar.sh` deploys the control with `BootstrapCreado=false` before the bootstrap exists, and again with `true`
right after the bootstrap is created (step 2b). Until step 2b, the CDK roles are not frozen; that window is only the
bootstrap itself.

Consequence to know: with the action active, a `cdk deploy` is denied, while `cdk destroy` keeps working (delete is not
in the freeze). To deploy again, detach the policy from the roles in the IAM console or by CLI (a manual step).

## Checks (no AWS, run in CI)

- `semana-19/tests/test_infra_cdk.py` (54 + 11 tests, spike-iac job): synth of both profiles; cdk-nag AwsSolutions with
  zero non-compliant findings in both stacks; every suppression has a reason; checkov with zero failures and every skip
  with a comment; every role has the boundary (including CDK's custom-resource role); every log group has the key and a
  retention; the key has rotation and a window of 7 (lab) or 30 (prod); no key policy with an open principal;
  endpoints are exactly the two interface and one gateway of ADR 0005, with 1 AZ in lab and 3 in prod; endpoints limited
  to the account; the endpoint group accepts 443 only from the tools SG; no NAT, no IGW, no public subnets; the freeze
  does not deny any delete action; the budget action targets only the deploy role at 100 %; no account ID, no email in
  any template; a snapshot of the lab synth.
- `semana-19/tests/test_infra_scripts` (inside test_infra_cdk.py): `desplegar.sh` and `destruir.sh` without `--si` do
  not call `aws` or `cdk` (fake binaries in PATH that fail and leave a marker); `--si` without `ALERTA_EMAIL` stops
  before any AWS call; unknown arguments exit 2.

## Wildcards kept (`*`), by statement Sid

Each one is in `semana-19/infra/cdk/excepciones.py` with its reason. The test compares the set of Sids that contain a
`*` with that register, so a new wildcard fails the build.

| Sid | Where | Reason |
|---|---|---|
| LogsDelGrupoDelProyecto, GruposDeLogs | boundary, cfn-exec | prefix `/semana19/` on the group name |
| LogsDescribir, DescribirGruposDeLogs, DescribirGruposParaFlowLogs | boundary, cfn-exec, flow role | `logs:DescribeLogGroups` takes no ARN |
| CdkAssumeRoles, AsumirRolesCdk | boundary, deploy | `cdk-s19-*` names include account and region |
| CloudFormationLeer, LeerCloudFormation | boundary, deploy | Describe/Get/List without ARN |
| RestringirSgPorDefecto | boundary | DescribeSecurityGroups without ARN; revoke used by CDK's custom resource |
| NoCrearNiActualizarMientrasEsteActiva | freeze (deny) | create actions have no prior ARN |
| VpcYRedes, LlavesKms | cfn-exec | create actions have no prior ARN; `kms:CreateKey` needs `*` |
| FuncionesDeCustomResourceDelProyecto, RolesConLimite, CrearRolesSoloConLimite, NoQuitarNiCambiarElLimite | cfn-exec, deploy | prefix `semana19-*`; the boundary condition is required |
| RaizDeLaCuenta, RolesConNombre, LogsDelProyectoConLaLlave | KMS key policy | in a key policy `*` means this key; root uses `kms:*` for IAM delegation |
| EscribirSoloEnSuGrupo, `-` | flow-log role and CDK's flow-log statement | AWS requires the `<group>:*` stream form |

cdk-nag suppressions (IAM5) carry the same reasons. checkov skips: 3 IAM findings on the control (CKV_AWS_111, CKV_AWS_109)
with their reasons, and 3 Lambda findings (CKV_AWS_115/116/117) on CDK's own custom resource for the default SG, which
runs once and is outside the VPC by CDK's design.

## Results of the synth (lab, no AWS)

| | control | base |
|---|---|---|
| cdk-nag: compliant / suppressed / non-compliant | 6 / 18 / 0 | 9 / 3 / 0 |
| checkov: passed / failed / skipped | 42 / 0 / 3 | 44 / 0 / 3 |
| assets | 0 | 2 (CDK custom resource and the template) |

## Prices (per hour, lab)

Authorized estimate: **0.02273973 USD per hour** (activity 2). The breakdown below is the same figure plus two new lines.

| Line | Price | Source | Mark |
|---|---|---|---|
| KMS keys: base 1 + bootstrap 1 = 2 | 1.00 USD per key-month | Price List, `us-east-1-KMS-Keys`, 2026-11-12 | M |
| Interface endpoints: 2 × 1 AZ | 0.01 USD per endpoint-hour | Price List, `USE1-VpcEndpoint-Hours`, SKU EN2N5TATXE673A3B | M |
| Budgets: 1 budget | 0.00 USD within 62 budget-days per month | Price List, AWSBudgets, `BudgetsUsage`, SKU T2UVJ9XYT52FBFAF | M |
| Pending-deletion KMS key | not billed while pending | [AWS KMS pricing](https://aws.amazon.com/kms/pricing/): "There is no charge for customer managed KMS keys that you manage and are scheduled for deletion." (read 2026-11-13) | D (official page, not Price List) |
| Flow logs, ingestion | 0.50 USD per GB, first 10 TB, Standard class | Price List, `USE1-VendedLog-Bytes`, SKU GHRXAWYBWDN7X39F | M price; **volume N** (not measured) |
| Flow logs, storage | not priced here | — | N |
| Bootstrap storage (S3 assets, ECR) | not priced here | — | N |
| Cost Anomaly Detection | not in the Price List (`AWSCostExplorer` has no anomaly product); not on the official page. Not deployed (decision b) | — | **N** |

Figure without the N lines: 0.02273973 USD/h. The flow-log ingestion, storage and anomaly lines are N and go
into the first real session as measured values, not estimates.

## Official source quoted (KMS)

- Pending deletion: "There is no charge for customer managed KMS keys that you manage and are scheduled for deletion."
- Charge: "Each AWS KMS key that you create in AWS KMS costs $1/month (prorated hourly)."
- Waiting period: 7 to 30 days; default 30; the actual wait can be up to 24 hours longer.

## Pending (needs Manuel)

1. **Authorize the diff** after `desplegar.sh --diff` (it shows what the control creates; it must run first).
2. **Activate the cost allocation tag `proyecto`** in Billing. The budget only sees cost with it, and AWS takes up to 24 h.
3. **Set the alert address** in the shell (`ALERTA_EMAIL`). It is never written to the repo.
4. **After the control stack exists**, add a profile to `~/.aws/config` that assumes `semana19-despliegue` (the bootstrap
   trusts only that role). Run `aws configure`-style editing yourself; I do not edit that file.
5. ~~Decide the freeze limitation~~ (done: option B, see the freeze section).
6. Then, with your OK for each `--si`: deploy (control, bootstrap, base), measure times, inventory before and after,
   teardown, and one Cost Explorer call the next day (2 calls authorized at most, each with your OK).

## Results (2026-11-13): deploy and teardown

Measured in the lab account, with `semana19-lectura` for the inventory:

| Step | Result | Source |
|---|---|---|
| Control stack deploy | 43-44 s (several runs; the first attempt failed on the budget email parameter) | `tiempos_despliegue.jsonl` |
| Bootstrap `s19` deploy | created once, then reused | log |
| `semana19-base` deploy to `CREATE_COMPLETE` | 97 s | `tiempos_despliegue.jsonl` |
| Base stack up, approximately | about 2 h (cap: 2 h); estimated cost about 0.05 USD at 0.02273973 USD/h | log, estimate |
| `semana19-base` delete | not recorded by the script (the first `cdk destroy` hit a `cdk.out` lock; the stack then ended in `DELETE_FAILED`) | events |
| Bootstrap delete | 32 s | `tiempos_despliegue.jsonl` |
| Inventory after teardown | `quedan: nada`, no unexpected items (control kept, as planned) | `inventario.py` |
| Cost Explorer, next day | pending (max 2 calls, each with approval) | - |

### Failures found and what they taught (each one cost a stack rollback)

1. `cdk diff` and `cdk destroy` do not accept `--toolkit-stack-name`.
2. The CDK bootstrap roles lacked, in order: `iam:GetRole`/`DeleteRole` on the flow-logs role, `iam:PassRole` for the flow log
   and for the custom resource Lambda, `iam:PutRolePolicy`/`AttachRolePolicy` on roles the stack creates (they do not carry the
   boundary key in those calls), `s3:GetObject` on the assets bucket and `kms:Decrypt` through S3 (the bucket uses `aws/s3`),
   and `ssm:GetParameter` on `/cdk-bootstrap/s19/version`.
3. The permissions simulator (`simulate-custom-policy`) catches these before a deploy, read-only and free. It should have run
   before the first deploy attempt, not after.
4. Teardown: `vaciar_bootstrap.py` used a non-paginable operation; the bootstrap bucket has `DeletionPolicy: Retain`
   and is deleted explicitly after emptying; `destruir.sh` needs the Python with `boto3`.
5. **Known limit, not fixed on purpose:** the default-SG custom resource's Lambda role has `Authorize*` on the default SG,
   but the permissions boundary (`semana19-limite`) allows only `Describe` and `Revoke*`. Creation works; deletion does
   not. The boundary is the security cap and was kept. `destruir.sh` now retains only that custom resource (it is not an
   AWS resource) when the base stack ends in `DELETE_FAILED`. Revisit before any future base deploy.

### Freeze

The budget action attaches `semana19-congelar` to `semana19-despliegue` always, and to the `cdk-s19-*` roles once the
bootstrap exists. It denies create and update, not delete, so the teardown still worked.

### Cost Explorer, 2026-11-13 (preliminary, not conclusive)

- First approved call (account total, grouped by service, no filter): **−0.0000000023 USD**, no service with positive cost.
- Expected from the stack: about 0.06 to 0.07 USD (see the uptime section). Zero is not plausible for ~2 h of two interface endpoints and two KMS keys, so the day was most likely not closed yet.
- Second approved call: **not used**. It is kept for a re-check of 2026-11-13 on 2026-11-15 (the tag `proyecto` was activated on 2026-11-13 and does not apply retroactively).
- The row "real cost from Cost Explorer the next day" stays open until that re-check.
