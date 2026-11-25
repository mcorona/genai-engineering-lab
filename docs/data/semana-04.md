# Week 4 benchmark queries (Spanish data)

[Glossary](../glossary.md) · [Week 4 README](../../semana-04/README.md)

The query set of the inference benchmark. `benchmark_modelos.py` sends each query to the local model and to the API,
and measures latency, throughput and cost. The set was generated for this practice; the week README explains why it
is not comparable with other benchmarks. The benchmark runs are in [`resultados/`](../../semana-04/resultados/README.md), and the
distillation and DPO data are in `entrenamiento/` ([data](../../semana-04/entrenamiento/data/README.md),
[distillation](../../semana-04/entrenamiento/destilacion/README.md), [DPO](../../semana-04/entrenamiento/dpo/README.md)); each folder has its own
README.

**Why it is in Spanish:** the queries are Spanish because the lab measures models serving Spanish-language users,
and Spanish text costs a different number of tokens than English (week 2). Translating them would change the
latency and the cost that were measured.

## Files

| File | What it is | Written by / Read by |
|---|---|---|
| `consultas.jsonl` | The benchmark queries, one JSON object per line, spread evenly over five categories | Read by `benchmark_modelos.py` (`--consultas`) |

## Keys

| Key | Meaning |
|---|---|
| `categoria` | Query category: `codigo` (coding), `redaccion` (writing), `razonamiento` (reasoning), `negocio` (business), `explicacion` (technical explanation) |
| `pregunta` | The query, in Spanish |
