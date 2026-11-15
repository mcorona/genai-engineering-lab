# Activity 2: query rewriting with claude-haiku-5-5

The week 8 vector search (bge-m3, `semana8` index, fixed 400/80). Script: `experimentos/reescritura.py`.
Two runs of the same code on 2026-10-22. Detail per query of the second: `reescritura_detalle.csv`.

## Second run

| Type | Language | Variant | recall@5 | nDCG@10 | MRR | Rewrite unchanged | Cost per query (USD) | Rewrite latency p50 / p95 (ms) |
|---|---|---|---|---|---|---|---|---|
| follow-up | es | original | 0.933 | 0.809 | 0.747 | - | - | - |
| follow-up | es | rewritten | 0.800 | 0.711 | 0.618 | 0/15 | 0.000040 | 872 / 3316 |
| base (control) | es | original | 1.000 | 0.904 | 0.874 | - | - | - |
| base (control) | es | rewritten | 1.000 | 0.898 | 0.861 | 49/50 | 0.000085 | 1279 / 2327 |
| follow-up | en | original | 0.867 | 0.802 | 0.739 | - | - | - |
| follow-up | en | rewritten | 0.933 | 0.793 | 0.727 | 0/15 | 0.000081 | 1218 / 2134 |
| base (control) | en | original | 1.000 | 0.885 | 0.845 | - | - | - |
| base (control) | en | rewritten | 1.000 | 0.885 | 0.845 | 50/50 | 0.000098 | 1509 / 2696 |

## First run (PR #19, on `main`)

| Type | Language | Variant | recall@5 | Rewrite unchanged |
|---|---|---|---|---|
| follow-up | es | original → rewritten | 0.933 → 0.800 | 0/15 |
| follow-up | en | original → rewritten | 0.867 → 1.000 | 0/15 |
| base (control) | es | original → rewritten | 1.000 → 0.980 | 49/50 |
| base (control) | en | original → rewritten | 1.000 → 1.000 | 49/50 |

## Cases whose hit changes in the second run

- ES `seg-02`: the original hits (1) and the rewrite misses (0). Original: "¿Y cada cuánto se cuentan los SKUs de clase A para llegar a esa meta?" ("And how often are class A SKUs counted to reach that goal?"). Rewritten: "¿Cada cuánto se cuentan los SKUs de clase A para llegar a la meta de exactitud de inventario de cada CEDIS?" ("How often are class A SKUs counted to reach each distribution center's inventory accuracy goal?").
- ES `seg-14`: the original hits (1) and the rewrite misses (0). Original: "¿Y qué hago si me da una respuesta incorrecta?" ("And what do I do if it gives me a wrong answer?"). Rewritten: "¿Qué hago si el copiloto me da una respuesta incorrecta?" ("What do I do if the copilot gives me a wrong answer?").
- EN `seg-02`: the original misses (0) and the rewrite hits (1).
- EN `seg-10`: the original misses (0) and the rewrite hits (1).
- EN `seg-14`: the original hits (1) and the rewrite misses (0).

The rewrites of the cases that get worse are faithful to the original question. The change in the hit comes from how the rephrasing ranks in the vector search, not from a wrong rewrite.

## Variability between runs

With the same code, results changed between the first and second runs: EN follow-ups went from 1.000 to 0.933 and ES base from 0.980 to 1.000. Haiku's rewrites are not deterministic, so a difference of one or two questions per language is noise, not signal.

## Cost

The cost is the billed one: input tokens × $0.10/M + output tokens × $0.50/M (the price in `semana-07/prices.json`, author's source, 2026-10-21).

A difference observed in the second run: ES follow-ups have 227 input tokens and 35 output tokens; ES base has 188 input and 133 output. Follow-ups carry more input, as expected, but on base questions almost nothing changes and yet the output is larger. Hypothesis: the API bills reasoning tokens that do not appear in the returned text. It is not confirmed; confirming it requires checking the block types of the API response in a call. (The HyDE activity later confirmed that Haiku returns `thinking` blocks, billed as output; see `hyde.md`.)

## Conclusion

- No demonstrable effect in this sample. EN follow-ups improve in one run and get worse in the other, with differences of one or two questions.
- ES follow-ups drop from 0.933 to 0.800 in both runs, but the cases that change are faithful rewrites; this is not a rewriting error.
- Query rewriting is not adopted as a default step.
- To decide properly: three runs per language, averaged, with the same frozen gold set.

## Limitations

- 15 follow-up questions per language: one question moves recall by 0.067.
- One run of each version; the observed variability is of the same order as the effect.
- The follow-up baseline already has a high recall, so there is little room to improve.
