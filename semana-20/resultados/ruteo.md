# Week 20, activity 4: model routing

[Glossary](../../docs/glossary.md) · [Week 20 plan](../Fas5Sema20.md)

Status: in progress. R0 is done (2026-11-27). R1 (the in-house router), R2 (Intelligent Prompt Routing) and R3 (Cascada
on the Mac) follow, in that order.

## 1. R0: the local Haiku 4.5 baseline

**What it is.** The same 20 tasks (the 10 + 10 CI gold tasks) with week 17's local harness: the guarded agent, the
real tools on the CI database (Docker, seed 42), the week 13 verifier and the week 17 graders. The run changed only
what makes the model Haiku 4.5 as deployed:
- the model is `ia/config.py`'s `MODELO_ID`, the `us.` Haiku 4.5 profile, called through Bedrock from the Mac with
  the admin's credentials (no Anthropic API key);
- the request is week 19's Converse adapter's, so it goes without `effort`, as deployed;
- the per-task budget is the deployed ceiling (0.12 USD and 100,000 tokens).

It has no guardrail and no cache point. Week 17's local harness had neither: the guardrail is part of the port, and
the cache is an optimization. Script: [`ruteo/r0_local.py`](../ruteo/r0_local.py). Raw file:
[`ruteo/r0_local.json`](ruteo/r0_local.json). Comparison: [`ruteo/r0_comparacion.json`](ruteo/r0_comparacion.json).

**Cost.** 0.8296453 USD for 101 model calls and 609,643 tokens. The estimate was 0.93 USD, the corrected run's cost
for the same 20 tasks without cache. The caps were 1.50 USD and 1,100,000 tokens, and the cap stopped no task. Prices
come from the Price List's regional Haiku 4.5 SKUs (1.10 and 5.50 USD per million, `JQDUC8Q4K8C6GSGH` and
`X629GDA2GXAP6R54`). The run took 208.6 s.

**Result, task by task.** ✗ is a failure; the other cells pass.

| Task | Week 17 (Haiku 5.5, local) | R0 (Haiku 4.5, local) | Corrected run (AWS) | Cache run (AWS) |
|---|---|---|---|---|
| c02-es | ✓ | ✗ abstained | ✗ abstained | ✗ asked for clarification |
| c02-en | ✓ | ✗ abstained | ✗ abstained | ✓ |
| c06-es | ✓ | ✗ cut by the task budget (`presupuesto_tarea`, at 0.0981 USD) | ✓ | ✓ |
| c06-en | ✓ | ✗ answered, rejected by the verifier | ✓ | ✗ answered, rejected by the verifier |
| r05-es | ✓ | ✓ | ✗ abstained | ✓ |
| r05-en | ✓ | ✓ | ✗ stopped at the step limit (12) | ✗ stopped at the limit after 12 calls |
| the other 14 | ✓ | ✓ | ✓ | ✓ |
| **Success** | **20/20** | **16/20** | **16/20** | **17/20** |
| Silently-wrong answers | 0 | 1 (c06-en) | 0 | 1 (c06-en) |

**Week 10's rule against week 17's 20/20:** R0 is a regression, in Spanish (0.8 against a threshold of 0.9), in
English (0.8 against 0.9) and in total (0.80 against 0.95).

**Conclusion: both, and the model's effect is the larger part.**
- **Model's effect** (R0 fails what week 17 passed): c02 in both languages and c06 in both languages.
  - c02 fails in all three Haiku 4.5 runs: Haiku 4.5 abstains (or asks) where the task expects an answer, locally and
    on AWS. Haiku 5.5 answered it.
  - c06 fails in R0 and in the cache run (c06-en, the same silently-wrong answer), and passes in the corrected run. It
    is Haiku 4.5 at the edge of this task: a long task that one run finishes and another does not.
- **Port's effect** (a deployed run fails what R0 passes): r05 in both languages. R0 answered both, at 0.033 and
  0.068 USD. On AWS, r05-en stopped at 12 calls in both runs (the loop's step limit in the corrected run, `linea_base.md`) and r05-es abstained once. R0 does not tell which part
  of the port it is: the guardrail, the pinned prompt version, the tools behind the Lambda and RDS. The router cannot
  close it, because the router changes only the model.
- Haiku 4.5 alone accounts for the regression. R0, local and without the port, scores 16/20, as low as the corrected
  run. Of the corrected run's 4 failures, 2 are the model's (c02) and 2 are the port's (r05).

**What it decides for R1 (the rule was fixed in the script before the run).** R0 regresses, so:
- R1's week 10 verdict is against the cache run (17/20), the activity's baseline on the same port and with the same
  cache;
- R1 is also reported against week 17's 20/20, because escalating to a stronger model is meant to close the model's
  gap (c02, c06);
- r05 is out of the router's reach. If R1 still fails r05, the cause is the port, not the router.
