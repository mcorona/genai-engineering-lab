# ADR 0014: prompt caching at the end of the agent's history, 5-minute TTL, off until measured

Week 20, activity 3. Measured offline ($0) in `semana-20/resultados/cache_medicion.json`; predicted in
`semana-20/resultados/cache_prediccion.json` before the live run.

## Context

**Bedrock's rules** come from [prompt-caching](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html),
read 2026-11-25. Marks: **D** is that page, **M** is a Price List row with its SKU.

| Rule | Value | Source |
|---|---|---|
| Minimum per cache point, Claude Haiku 4.5 | 4,096 tokens, counted on the whole prefix before the point ("applies cumulatively") | D |
| Points per request | at most 4; in `tools`, `system` and `messages`, read in that order | D |
| A point under the minimum | the call succeeds, nothing is cached | D |
| Lookback | a point also finds earlier cached prefixes, within about 20 content blocks before it | D |
| Hits | not guaranteed. An entry lives on the server that wrote it, and a request served by another server or Region writes instead of reading | D |
| TTL | 5 minutes (default, no `ttl` field) or 1 hour (`"ttl": "1h"`); the 5-minute TTL resets on each hit | D |
| Converse usage | `inputTokens` is the uncached input only; `cacheReadInputTokens` and `cacheWriteInputTokens` come apart | D |
| Prices, Haiku 4.5 regional (us.), USD per 1M | input 1.10; cache read 0.11 (0.1×, VJXPZKPF7EDCFXN3); write 5 min 1.375 (1.25×, CDG7WESKYQ9N9KDN); write 1 h 2.20 (2×, WTCBCUF6TGQ5M3NB) | M, `semana-20/resultados/linea_base.md` §4.1 |

**What the agent sends** was measured from the corrected run's spans, 20 tasks plus 2 warm-ups:
- **Fixed prefix.** It is the 6 tool definitions (week 13's read tools without `validar_sql`, the proposal and `responder`) and the system prompt, 7,825 characters of Converse JSON.
  - That is 2,664 tokens at the median characters-per-token ratio, and 2,898 at the lowest ratio, the most tokens.
  - Both are under 4,096, so a point on the system prompt or the tools caches nothing on Haiku 4.5.
  - The system prompt is week 13's `SISTEMA`. It is equal to the Prompt Management English version with its variable rendered; a test checks this.
- **Token counting.** It is an estimate, and its margin is the spread of the ratios: 2.70 to 3.57, median 2.94.
  - The repository has no Haiku 4.5 tokenizer, and the spans record tokens per task, not per call.
  - Each task's ratio is fitted so that its rebuilt steps sum to its real input tokens.
- **History per step.**
  - The first call is 2,681 to 3,140 tokens.
  - The prefix reaches 4,096 at call 2 in 13 of the 20 tasks, at call 3 in 2, and at call 4 in 1.
  - In 4 it never does: a01 and n01, in both languages, with 2 or 3 calls.
- **Times.**
  - A call takes 4.17 s (median) and at most 16.72 s, the cold warm-up.
  - Queries ran 0.92 s apart (median), at most 6.76 s.

## Alternatives (where the points go)

For a measured task, s06-es, with 6 calls, the input per call is 2,969 / 4,290 / 4,599 / 5,000 / 5,373 / 5,701.

| Option | Points | Tokens per call (uncached / read / written) | Model USD (corrected run: 0.039234) |
|---|---|---|---|
| (a) `sistema`: after the system prompt (covers the tools) | 1 | everything uncached: the prefix is under the minimum | 0.039234 |
| (b) one point at the end of the history (rolling) | 1 | call 1: 2,969 / 0 / 0. Call 2: 0 / 0 / 4,290. Calls 3–6: read the previous call's prefix, write the difference (309, 401, 373, 328) | 0.021732 (all hits) |
| (c) (b) plus a point where the previous call put its point | 2 | same as (b) | 0.021732 (all hits) |
| (d) (c) plus (a) | 3 | same as (b) on Haiku 4.5 | 0.021732 (all hits) |

The rule per call k ≥ 2, when its prefix I_k reaches the minimum:
- **Hit:** read I_(k−1), write I_k − I_(k−1).
- **Miss** (another server): read 0, write I_k.

A write costs 1.25× input with 5 minutes and 2× with 1 hour; a read costs 0.1×.

## Decision

1. **Points: (c), `CACHE_PROMPT=historial`.**
   - (b) gives the same tokens but finds the previous prefix only through the ~20-block lookback. One call adds 2 to 4 blocks today, but a long parallel tool turn could pass that.
   - (c) names that position explicitly, with 2 of the 4 points.
   - (d) spends a point that caches nothing on Haiku 4.5. It is kept as `historial+sistema` for a model whose minimum the fixed prefix reaches (Haiku 5.5: 512).
   - No point on the first call.
2. **TTL: 5 minutes.**
   - A query's calls are seconds apart, far inside 5 minutes.
   - The 1-hour TTL pays only when a prefix is read across queries more than 5 minutes apart: users who share a prefix.
   - Here no two queries share a cached prefix. The first call, the only one two users could share, is never cached. Every later prefix holds this query's own `toolUseId`s (see the boundary below).
   - With every call a hit, 1 hour would cost 0.602 USD for the 20 tasks against 0.511 with 5 minutes.
3. **Off by default** (`ia/config.py` `CACHE_PROMPT = "off"`).
   - The activity 3 run deploys computo with `CACHE_PROMPT=historial` at synth time, so caching is measured alone.
   - Activity 9 decides the combined default.
4. **The budget counts the cache by its dollar weight.**
   - USD: each cache token at its own price.
   - Tokens: a read counts 0.1 and a write 1.25 (`tokens_equivalentes`).
   - The next call's estimate prices the prefix already cached as a read.
   - So a cached task is not cut before the same task without the cache.
5. **The span and EMF cost add the cache tokens at their prices.** Each call gets a `chat` span with its read and written tokens, and its duration goes on the agent line (`duracion_pasos_ms`).

### Cross-region inference

- **Where calls can go.** The agent calls its application profile `semana19-agente`, which copies the `us.` system profile. Its foundation model is in us-east-1, us-east-2 and us-west-2 (`get-inference-profile`, 2026-11-15, `ia/config.py`).
- **What the docs say.**
  - Caching works with cross-region inference.
  - The service picks the optimal Region.
  - "At times of high demand, these optimizations may lead to increased cache writes."
  - They give no share.
- **The prediction therefore gives scenarios, not a rate:**

  | Scenario | Hit probability | Total for the 20 tasks | Saving |
  |---|---|---|---|
  | Optimistic (central for quote v3) | every call on one server | 0.511 USD | 45.0% |
  | Pessimistic | a uniform draw among the 3 Regions, p = 1/3 | 0.892 USD | 3.9% |
  | Worst | p = 0: every write at 1.25× | 1.083 USD | −16.7% (costs more) |

  The break-even is p = 0.27.
- **How it is measured.**
  - Converse does not return the Region (Converse API reference, read 2026-11-25: no Region field in the response).
  - So the hit rate is measured from tokens: among the calls whose previous call wrote, the share that read.

### Application inference profile and Guardrail

- **Application inference profile.** The docs are silent: prompt-caching and inference-profiles-create, read 2026-11-25, say nothing either way.
  - The live run is the test. If no call with a point reports cache tokens, caching does not work through the profile.
  - That costs nothing extra, because nothing is written. The run reports it, and the decision changes.
- **Guardrail.**
  - With `guardrailConfig` and no `guardContent` blocks, the guardrail evaluates all messages in the request ([Converse API reference](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html), read 2026-11-25).
  - It does not evaluate tool results, tool definitions or tool inputs ([guardrails-use-converse-api](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-use-converse-api.html), read 2026-11-25).
  - No page says whether the guardrail re-evaluates content read from the cache. A cache point adds no content, so the text the guardrail sees, and its text units, are the same with or without the cache. This is an inference, not a documented rule.
  - ApplyGuardrail's cost does not change with the cache. Its price stays N in the quote.
  - The pinned guardrail id and version, and the prompt, are unchanged by every value of the flag (tests).

### The security boundary (for week 21)

The cache is per account and needs an exact prefix match.
- **What is cached:**
  - The tools and the system prompt. They are the same for every user and hold nothing of the user (test: two users with different `sub`, tenant and question).
  - The query's own history, from the second call on: the question, the model's turns and the tool results.
- **Why another query cannot hit it.** That history always contains the `toolUseId`s the model generated for this query (test: the cached prefixes of two users share none). No other query can produce the same prefix, so it is never read across users or tenants.
- **The one prefix two users could share** is the first call: system, tools and the question. It never carries a point. So a cache hit cannot reveal that someone else asked the same question.
- This is surface T3.7 in `semana-19/seguridad/threat_model.md`.

## Consequences

- `agente/converse_adaptador.py` places the points (`peticion_a_converse(..., cache=, ttl=)`). With `off`, the request is week 19's byte for byte (`tests/snapshots/converse_semana19.json`). The week 13 loop does not change.
- A prefix under the minimum gets no history point on the first call. The `sistema` point is sent and caches nothing, and the test says so. Sending it costs nothing.
- The quote gains v3 (`costos/modelo.py`), priced from `cache_prediccion.json`.

## Costs

- **Offline:** $0.
- **Cache prices:** M (Price List SKUs above). The writes are paid only when a point is cached; a point under the minimum costs nothing.
- **Live run:** quote v3's range for the 22 tasks is 0.565 USD (optimistic) to 1.175 USD (worst), plus the stacks' hours. The script's cap is 1.50 USD.
- **ApplyGuardrail:** N, unchanged by the cache.
