# Activity 9: calibrating the threshold of the retrieval eval in CI

GitHub Actions run: `39877067557` (workflow `recuperacion-semana-08`, PR #15).
Model: `text-embedding-3-small` (OpenAI), a `pgvector/pgvector:pg16` service database, 57 fixed chunks (400/80), 50 queries per language.

| Language | recall@5 in CI | Threshold | Margin |
|---|---|---|---|
| ES | 0.990 | 0.90 | 0.090 |
| EN | 0.950 | 0.90 | 0.050 |

These values match the local run of the same model (`embeddings_fijo_400_solape_80.md`: ES 0.990, EN 0.950), so CI reproduces the local measurement.

Decision: `UMBRAL = 0.90` is kept. With 50 queries per language, each question is worth 0.02 of recall. In EN, losing three questions (0.90) is already at the limit, so the threshold leaves a margin of two questions before failing. Raising it to 0.95 would make the check fail in EN with the current configuration.

Limits: it is a single CI run. The recall of an OpenAI model can vary between versions of the service, and the sample is small.
