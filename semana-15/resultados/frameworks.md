# Activity 5: LangGraph vs Strands, same agent

Harness: [`eval/correr.py`](../eval/correr.py) and [`eval/pasarela.py`](../eval/pasarela.py). Generated tables: [`frameworks_tablas.md`](frameworks_tablas.md). Detail: [`frameworks_detalle.jsonl`](frameworks_detalle.jsonl) (240 runs), [`frameworks_seguridad_detalle.jsonl`](frameworks_seguridad_detalle.jsonl) (76 cases), common traces in `trazas/frameworks.jsonl`. Tests without API: [`tests/test_eval.py`](../tests/test_eval.py).

**Setup**
- **Agent:** the same in both frameworks (activities 3 and 4): the week 13 prompt, `responder` and limits; Haiku 5.5 `low`.
- **Tools:** the week 14 MCP server over Streamable HTTP + OAuth, with the analyst's real Keycloak token, renewed before it expires.
- **Tasks:** the week 14 stratified subset (20 tasks per language), k = 3, checked by re-running the SQL.
- **Cost:** **$0.8572** (estimate $0.85, cap $1.20). The database fingerprint was unchanged.

## Results

| Agent | pass@1 (95% CI) | pass^3 | Cost / task | p50 / p95 (s) | Steps | Tool calls |
|---|---|---|---|---|---|---|
| **LangGraph** | **0.900** (0.833 to 0.942) | 0.900 | $0.0030 | 6.84 / 15.82 | 3.71 | 5.65 |
| **Strands** | **0.900** (0.833 to 0.942) | 0.900 | $0.0030 | 6.74 / 14.05 | 3.67 | 5.58 |
| Own loop (week 13, in process) | 0.917 (0.853 to 0.954) | 0.900 | $0.0028 | 6.89 / 14.92 | 3.69 | 5.55 |
| Claude Agent SDK (week 13, in process) | 0.875 (0.804 to 0.923) | 0.825 | $0.0021 | 10.07 / 19.66 | 6.37 | 5.34 |

Paired comparison, bootstrap over the 40 tasks:

| Comparison | Difference | 95% CI |
|---|---|---|
| LangGraph − Strands | **+0.000** | +0.000 to +0.000 |
| LangGraph or Strands − own loop | −0.017 | −0.050 to +0.000 |
| LangGraph or Strands − Claude Agent SDK | +0.025 | −0.008 to +0.075 |

**Security** (the 38 week 14 cases with client defenses, in each framework): **38/38 in LangGraph and 38/38 in Strands**, with 0 instructions obeyed, 0 writes and 0 leaks. The 2 calls to a "malicious" server per framework are the legitimate use of `tipos_cambio` in the result-injection case (`ir-1`). That server is approved; its injected result arrived as data, and neither the DELETE nor the proposal was executed, the same as in week 14.

**Development cost**

| | LangGraph | Strands |
|---|---|---|
| Own code (adapter) | 145 lines | 166 lines |
| Direct dependencies / installed packages | 3 / 65 | 1 / 77 |
| Request to merged PR, tests included | 12 min | 17 min |

## Reading

1. **The framework does not change the result.** LangGraph and Strands failed **exactly the same 12 runs**: `c05` and `a03`, in both languages, 3 out of 3 times. Those are the same tasks that failed in week 13 in process and in week 14 over MCP. Cost per task, tokens, steps and latency agree within 2%. Same model, same prompt, same tools and same rules give the same agent. What differs is the code that expresses it and what each framework makes easy or hard (activities 3 and 4).
2. **Moving from in-process to MCP costs little.** The two frameworks sit 0.017 below the own loop (CI −0.050 to 0.000). That is the run-to-run variation of the same `c05` failure (20/24 composite tasks against 18/24), and it reproduces the week 14 result. Cost per task rises from $0.0028 to $0.0030 because MCP tool results reach the model as text, slightly longer.
3. **Both beat the Claude Agent SDK on consistency** (pass^3 0.900 against 0.825), with fewer steps (3.7 against 6.4) and lower p95 latency. The success difference (+0.025) is not significant with 40 tasks.
4. **Security does not depend on the framework but on where the defenses live.** Putting the week 14 secure client behind an **MCP gateway** gave both frameworks the same defenses with no code in either adapter. It is the pattern to recommend to a client running several frameworks.
5. **Development cost is the real difference.** LangGraph needed fewer lines and less time. Strands needs fewer direct dependencies, but more knowledge of its internals: when metrics update, how a cancelled call is reported, and that tools run concurrently by default.

## Findings

- **Unbounded SDK timeouts.** The first run hung for 30 minutes at 188/240 tasks: a model call never returned, and both SDKs default to a 10-minute timeout with retries, while the orchestrator waited forever for each worker. Fixes:
  - 120 s per model call in both adapters.
  - A 10-minute limit per worker that restarts it and records the run as a failure.
  - `--reanudar`, which keeps the finished runs and only launches the missing ones; money already spent still counts toward the cap.

  The resumed run (52 tasks and 76 cases, 2.6 min) had no timeouts. Lesson for production: an agent without per-call timeouts is a cost and availability risk, whatever the framework.
- **Language.** 53 of 60 English tasks were answered in Spanish in both frameworks, the same as in weeks 13 and 14. The week 13 prompt causes it, not the framework. It stays on the week 17 list.
