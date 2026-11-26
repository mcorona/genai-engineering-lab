# Week 4 inference benchmark runs (recorded evidence)

[Glossary](../../docs/glossary.md) · [Week 4 README](../README.md)

The runs of `benchmark_modelos.py`: the same query set (`../consultas.jsonl`) on a local quantized model in LM Studio
and on the Claude API. Each run is named with `--nombre`, and writes one detail file (one row per query and target)
and one summary file (the run settings and one summary per target).

**Recorded evidence:** these are the raw outputs of the runs, kept exactly as recorded (not edited, not translated).
The English summary of the results, with the comparison of the two targets and its limitations, is in the week
README: [Results](../README.md#results).

## Files

| File | What it is | Written by / Read by |
|---|---|---|
| `semana4_api_*` | API run (Claude Haiku 5.5) with an output limit of 8192 tokens | Written by `benchmark_modelos.py` |
| `semana4_local_8k_*` | Local run (Qwen3.8-27B MLX 4-bit) with an output limit of 8192 tokens. The local run the week README reports | Written by `benchmark_modelos.py` |
| `semana4_local_detalle.csv`, `semana4_local_resumen.json` | Discarded local run with an output limit of 1024 tokens: 27 of 50 answers stopped at the limit. Kept for traceability | Written by `benchmark_modelos.py` |

## Keys

| Key | Meaning |
|---|---|
| `destino` | Target: `local` (LM Studio) or `api` |
| `latencia_s` | Latency of the query, in seconds |
| `tokens_entrada`, `tokens_salida` | Input and output tokens. On the local model, the output includes its reasoning tokens |
| `tokens_por_s` | Output tokens per second |
| `costo_usd` | Cost of the query, in USD (0 for the local model: electricity and hardware are not counted) |
| `error` | The exception class when the call failed; empty when it succeeded |
| `nombre` | The run name given with `--nombre` |
| `consultas_archivo` | The query file used, as a path on the author's machine |
| `temp_local`, `temp_api` | The temperature setting for each target (`null` = none sent). Both are recorded even when the run covers one target |
| `resumenes` | One summary per target |
| `consultas`, `errores` | Queries sent, queries that failed |
| `latencia_p50_s`, `latencia_p95_s`, `latencia_media_s` | Median, 95th-percentile and mean latency, in seconds |
| `tokens_por_s_mediana` | Median output tokens per second |
| `costo_total_usd`, `costo_por_1k_consultas_usd` | Total cost of the run and cost per 1,000 queries, in USD |
