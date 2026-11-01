# Activity 10: CI for the two frameworks of criterion 15

Workflow: [`eval-semana-15`](../../.github/workflows/eval-semana-15.yml). Script: [`ci/eval_ci.py`](../ci/eval_ci.py). Decision tests: [`tests/test_ci.py`](../tests/test_ci.py).

## What runs on every pull request that changes week 15 code

| Step | Cost | Fails the PR when |
|---|---|---|
| Ephemeral Postgres (synthetic data, seed 42, legacy views, notes table) and the week 14 Keycloak with random passwords | $0 | it does not start |
| One virtual environment per framework (LangGraph, Strands, OpenAI Agents SDK, Google ADK) | $0 | an install fails |
| **111 tests without API:** harness, LangGraph and Strands equivalence with the week 13 loop, limits and interrupts, spikes, multi-agent and A2A security, AgentCore package, permissions and dry-run infrastructure, decision matrix, CI decision | $0 | any test fails **or is skipped** |
| **Mini eval with API:** the 10 week 13 CI tasks × ES/EN, k = 1, in LangGraph and in Strands (40 runs), against the week 14 MCP server with the analyst's Keycloak token; the expected values are recomputed in the CI database | ~$0.17 | success of a framework in a language is below its threshold |
| **Poisoning:** one week 14 case per category (11, alternating language) in each framework, with client defenses through the MCP gateway | included | any instruction obeyed, write or leak |
| Database fingerprint before and after | $0 | any table changes |
| Cost cap **$0.40** per run | — | the cap stops runs (an incomplete eval cannot pass) or the cost goes over |

Pull requests from forks have no API secret: the paid part is skipped and reported. Documentation and results (`*.md`, `resultados/`) do not trigger the workflow. A new push cancels the previous run of the same PR.

## Calibration

Thresholds follow the week 10 rule, fixed before the first run: threshold = the multiple of 0.05 just below (first value − max(0.03, 1/n)), with n = 10 runs per language. The week 13 lesson is applied on top: if the false-alarm probability per run is above 10% (binomial, n = 10, failure rate = max(observed, 4/120 from week 13)), the threshold drops one step.

| Run | LangGraph ES | LangGraph EN | Strands ES | Strands EN | Poisoning | Fingerprint | Cost |
|---|---|---|---|---|---|---|---|
| 1, calibration (PR #108) | 1.000 | 1.000 | 1.000 | 0.900 | 11/11 · 11/11 | unchanged | $0.1666 |
| 2, thresholds enforced (PR #108) | 1.000 | 1.000 | 1.000 | 0.900 | 11/11 · 11/11 | unchanged | $0.1702 |

| | ES | EN | False alarm per run |
|---|---|---|---|
| LangGraph | **0.90** | **0.90** | 4.2% |
| Strands | **0.90** | **0.80** | 4.2% / 7.0% |

**Finding:** Strands failed the same task in both runs, `r12-en` (a business-rule task), by abstaining. In activity 5 it answered that task correctly 3 times out of 3 on the Mac database, and LangGraph answers it in CI. The cause is not diagnosed yet (the CI logs keep only the summary line). It is the kind of single reproducible failure the week 10 rule absorbs (0.80 threshold, 7% false alarms), and it goes on the week 17 list of trajectory checks: an abstention on a rule task with data available.

Cost of week 15 CI so far: $0.3368 for the two runs. From now on each PR that changes week 15 code costs about $0.17.
