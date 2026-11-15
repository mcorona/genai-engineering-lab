# Unit 4: inference — quantization, latency and cost

Practice: a benchmark of the same set of queries on a local quantized model and on an API, measuring latency, throughput and cost.

## Status

- [x] A benchmark script (`benchmark_modelos.py`): p50/p95 latency, tokens per second and cost per 1 000 queries.
- [x] A set of 50 queries (`consultas.jsonl`): 10 coding, 10 writing, 10 reasoning, 10 business and 10 technical-explanation queries. **Generated for this practice; it is not the query set of Cascada** (the author's separate LLM-routing project), so the results are not comparable with that benchmark.
- [x] Local run (Qwen3.8-27B in MLX format, quantized to 4 bits, in LM Studio), 8192 tokens: `resultados/semana4_local_8k_*`.
- [x] API run (Claude Haiku 5.5), 8192 tokens: `resultados/semana4_api_*`.
- [x] Distillation (extra practice): trained and evaluated. The distilled 7B model reaches a 37.0 % result match, the same as the 7B base. No gain. See `entrenamiento/README.md`.
- [x] DPO (extra practice): not run. The installed `mlx-lm` CLI has no DPO mode. The 42-pair dataset is kept for a framework that supports it. See `entrenamiento/README.md`.

## Targets

| Target | Endpoint | Model | Price (USD per million tokens) |
|---|---|---|---|
| Local | `http://localhost:1234/v1` (LM Studio) | `qwen3.8-27b-mlx@4bit` | 0 (electricity not included) |
| API | `https://api.anthropic.com/v1/` (Anthropic's OpenAI-compatible endpoint) | `claude-haiku-5-5` | input 0.10, output 0.50 |

The Haiku 5.5 price was checked on the [official Anthropic pricing page](https://platform.claude.com/docs/en/about-claude/pricing): USD 0.10 per million input tokens and 0.50 per million output tokens, for prompts up to 100 000 tokens (October 2026). If the price changes, adjust `--precio-in` and `--precio-out`. Haiku 5.5 accepts only `temperature` 1, so the API runs without sending a temperature (`--temp-api` empty). The local model uses temperature 0.

## Results

The same 50 queries, `--max-tokens 8192` on both targets, temperature 0 locally and no temperature on the API.

| Metric | Local: Qwen3.8-27B MLX 4-bit | API: Claude Haiku 5.5 |
|---|---|---|
| p50 latency | 52.4 s | 4.0 s |
| p95 latency | 137.6 s | 10.9 s |
| Mean latency | 53.0 s | 4.9 s |
| Tokens per second (median) | 23.4 | 185.0 |
| Cost per 1 000 queries | USD 0 (electricity not included) | USD 0.47 |
| Errors | 0 | 0 |

Reading the results:

- The API is about 13 times faster at p50, about 12 times faster at p95, and about 8 times faster in tokens per second.
- The local model spends more tokens per answer because the 27B model reasons before it answers. Those reasoning tokens count in `tokens_salida`, so the time per visible answer differs from what the table shows.
- The local cost is zero in the script, but electricity and hardware are not accounted for.

Limitations:

- **This benchmark measures speed and cost, not quality.** The correctness of the answers was not evaluated; that was already measured in unit 3 with SQL.
- The 50-query set is generated; it is not Cascada's set.
- One attempt per query; there are no repetitions or intervals.

Discarded runs, kept for traceability:

- `semana4_api` at 1024 tokens: 19 of 50 answers truncated. Replaced by the 8192-token run.
- `semana4_local` at 1024 tokens: 27 of 50 answers truncated. Replaced by `semana4_local_8k`.

## How to run it

```bash
# from the repository root
read -s ANTHROPIC_API_KEY && export ANTHROPIC_API_KEY   # your key; it is never typed into a chat

# Local (LM Studio with the 27B model loaded)
uv run python semana-04/benchmark_modelos.py --solo local \
  --local-modelo qwen3.8-27b-mlx@4bit --nombre semana4

# API (Haiku 5.5)
uv run python semana-04/benchmark_modelos.py --solo api \
  --api-url https://api.anthropic.com/v1/ --api-modelo claude-haiku-5-5 \
  --api-key-env ANTHROPIC_API_KEY --precio-in 0.10 --precio-out 0.50 --nombre semana4_api
```

Outputs: `resultados/<nombre>_detalle.csv` (one row per query) and `resultados/<nombre>_resumen.json`.
To run both targets in a single execution, omit `--solo` and also pass the local parameters.
