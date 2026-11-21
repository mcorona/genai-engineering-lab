# Week 19, activity 9, step 3: estimate for the live run

Written on 2026-11-21, before any paid call of activity 9. Steps 1 and 2 cost 0 USD: ValidatePolicy is free, and the
read-only checks ran offline. The live run (step 4) waits for Manuel's OK per step and a `cdk diff` before
`desplegar.sh --si`.

## Sources

Every unit price or quantity below comes from one of these.

| Mark | Source |
|---|---|
| CE | Cost Explorer, activity 8 (`resultados/costo_real.md`): fixed 0.037562 USD per hour of the lab stack; model 0.030913 USD per task (mean); every per-query line 0.038562 USD per task (upper bound) |
| ED | `resultados/eval_aws_detalle.jsonl`: 19 deployed-agent tasks with a measured cost. Mean 0.035544 USD, maximum 0.063012 USD. Input tokens: mean 25,231, maximum 40,240. Output tokens: maximum 3,417 |
| TD | `resultados/tiempos_despliegue.jsonl`: the last full teardown (2026-11-19) took 43.0 min, 41 of them for computo |
| PR | AWS pricing pages read on 2026-11-21: IAM Access Analyzer; AWS Budgets; Titan V2 at 0.00002 USD per 1K tokens (`costos/precios.json`) |
| IAM | `ListRoles` and `ListUsers` with `semana19-lectura` on 2026-11-21: 15 roles (11 service-linked, 2 service roles, 2 others) and 2 users |

## Estimate

| Item | Quantity | Unit price | Nominal (USD) | Upper bound (USD) | Notes |
|---|---|---|---|---|---|
| Stack hours (lab, without the comparison stack) | 4 h nominal; 8 h upper | 0.037562 USD/h (CE) | 0.150 | 0.300 | Deploy about 1 h (no full deploy from scratch was timed: an assumption); checks 0.25 h; Access Analyzer 0.5 h; poisoning 1.5 h; teardown 0.75 h (TD) |
| External access analyzer | 1 analyzer | free (PR: "provided at no additional charge") | 0 | 0 | Deleted after the findings are read |
| Unused access analyzer | 39 roles + 2 users at creation (15 now + 17 project roles + 5 CDK bootstrap roles (assumed) + the test role + the analyzer's service-linked role) | 0.20 USD per role or user per month, charged at setup and again on the 1st of each month (PR) | **not recommended** | 8.20 (5.80 if service-linked roles are not billed; the docs do not say) | See the recommendation below |
| Poisoning: model | 4 data cases (week 13 iny-d1 to iny-d4) × ES and EN = 8 tasks | 0.035544 mean, 0.063012 max per task (ED) | 0.284 | 0.504 | Script cap below |
| Poisoning: ApplyGuardrail, Titan, Bedrock other | 8 tasks | ≤ 0.007589 USD per task: activity 8's "Amazon Bedrock" line (0.432590 USD) over 57 tasks; it also contains the judge (CE) | ≤ 0.061 | 0.061 | Upper bound |
| KB re-ingestion (poisoned prefix in, then out) | 2 ingestions of < 10K tokens (the docs come from a 2.6 KB dictionary plus the poisoned documents) | 0.00002 USD per 1K tokens (PR) | < 0.001 | 0.001 | Plus the S3 Vectors writes and queries: not priced, below 0.001 at this size |
| S3, API Gateway, DynamoDB (Lambda and Step Functions billed 0) | 8 tasks | 0.0000595 USD per task: the remaining per-query lines (0.003391 USD) over 57 tasks (CE) | < 0.001 | < 0.001 | |
| Test budget with an action | 1 budget, under 1 day | free: the first 2 action-enabled budgets each month (PR). The account has `semana19` (with an action, while the stack is up) and 2 budgets without actions | 0 | 0 | The test budget is the 2nd action-enabled budget |
| Cost Explorer (step 4.7) | 2 calls | 0.01 USD per call (CE) | 0.020 | 0.020 | Manuel already approved it |
| **Total without the unused access analyzer** | | | **≈ 0.52** | **≈ 0.89** | |
| Total with the unused access analyzer | | | ≈ 6.32 to 8.72 | ≈ 6.69 to 9.09 | |

## Room in the week

The cap is 10 USD per week. What is known of this week: about 2.68 USD up to 2026-11-18 (the note in the
authorization), plus 3.678 USD of usage over 2026-11-19 and 2026-11-20 (CE). That is about 6.36 USD, before the
weekly closing in Cost Explorer. About 3.6 USD are left.

- Activity 9 without the unused access analyzer fits: ≤ 0.89 USD.
- With it, the week goes over the cap.

## Recommendation on the unused access analyzer: do not create it this week

The documentation says that the analyzer "will only evaluate permissions for IAM entities ... that have existed for
the entire tracking period". The minimum tracking period is 1 day (`unusedAccessAge` between 1 and 365).

- **It would find nothing in the project.** The project's roles would be a few hours old when it runs, so it would
  evaluate none of them.
- **It would still cost 5.80 to 8.20 USD.** It bills every role and user it analyzes, which includes the account's 15
  other roles and 2 users, all outside the project.
- **The free alternative** answers "which permissions did the run not use" for the project roles:
  - IAM service last accessed (`GenerateServiceLastAccessedDetails` and `GetServiceLastAccessedDetails`), with
    `semana19-lectura`, after the poisoning run;
  - the action-level detail that ValidatePolicy already gave (6 REDUNDANT_RESOURCE suggestions).
- **When to run it instead:** with a stack that lives at least one tracking period. In prod, run it continuously; the
  findings for week 21 would come from there.

If Manuel still wants it:

1. Create it after the poisoning run, with `unusedAccessAge` of 1 day.
2. Keep the stack up 24 h more: about 0.90 USD at 0.037562 USD/h.
3. Read the findings, then delete it with `aws accessanalyzer delete-analyzer` before 2026-12-01, the date of the next
   monthly charge.
4. Verify with `inventario.py` that `analizadores` is empty.

## Caps the scripts will carry

| Script | Cap |
|---|---|
| Poisoning run (`seguridad/envenenamiento.py`, step 4.4) | At most 8 tasks. Each task keeps the agent's own week 17 budget. The run stops before the next task when the spans add up to 0.60 USD or 400,000 tokens (8 × the maximum measured input of 40,240 tokens, plus margin) |
| KB | At most 2 ingestion jobs (the poisoned prefix in, then out); at most 20 `Retrieve` calls |
| Whole activity | 1.00 USD, checked in Cost Explorer at step 4.7 against this table |

## Decisions Manuel needs to make before step 4

1. **The unused access analyzer.** Recommended: do not create it (above).
2. **The data poisoning cases are already in the deployed database.**
   - `infra/loader/artnot.sql` loads week 13's notes into `legado.artnot`, the poisoned ones included: for example
     the note on SKU-0009 that asks for `DELETE FROM exidet`.
   - These are not the CI seed-42 rows. They are week 13's cases, marked by their `not_id`.
   - Recommended: run iny-d1 to iny-d4 on those rows, with a table fingerprint before and after (read-only), and
     insert nothing more.
   - The alternative is to insert copies with new `not_id`s in a separate schema. That would test the same text a
     second time.
3. **The KB channel cannot reach the agent: finding H2.** No code calls `Retrieve`. Recommended:
   - upload 2 poisoned documents to `docs/envenenados/` and re-ingest;
   - call `Retrieve` directly. This is a data-plane call that `semana19-lectura` probably cannot make, so it would be
     a 🔵 command for Manuel;
   - show that the poisoned chunks come back, which means the KB would serve them;
   - run one API task that would need them, to show that the agent never sees them;
   - then delete the prefix, re-ingest, and verify.

   The result is reported as "not reachable today (H2)", not as "blocked".
4. **Week 13's rule cases (iny-r1 and iny-r2) have no channel in AWS.** The rules travel inside the tools Lambda's
   package (`herramientas/catalogo13.py`), not as data. Poisoning them means changing the deployed code, which is a
   supply-chain case (F10), not indirect injection. Recommended: report them as not applicable, with this reason.
