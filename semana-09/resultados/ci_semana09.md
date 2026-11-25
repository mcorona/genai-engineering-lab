# Activity 9: retrieval and permissions eval in CI

Workflow: `.github/workflows/recuperacion-semana-09.yml`, on every PR that touches `semana-09/**`. Script: `ci/permisos_ci.py`.
Database: a pgvector service (`pgvector/pgvector:pg16`, pgvector 0.8.7 with `hnsw.iterative_scan = strict_order`), with the alfa (57 chunks) and beta (33 chunks) tenants, `tenant_id` and `roles`, and the filter inside the query.
Embeddings: `text-embedding-3-small` (OpenAI, the `OPENAI_API_KEY` secret), because bge-m3 runs in LM Studio, which is not available in GitHub Actions. Approximate cost: $0.0003 per run. No Anthropic models.

## What makes the check fail

1. recall@5 of the 50 base questions (an alfa user with every role) below the threshold in ES or EN.
2. Any leak by role: unauthorized chunks in the top 10 (50 questions × 6 roles) or forbidden passages returned (5 cases per language).
3. Any leak across tenants: chunks from the other tenant (50 questions × 2 tenants) or the other tenant's figure in the 20 near-identical cases.

Leaks have no threshold: they must be 0.

## Calibration with the first run

GitHub Actions run `40390705860` (PR #29, 2026-10-26).

| Language | recall@5 | Threshold | Margin | Leak by role | Forbidden returned | Leak across tenants | Other tenant's figure | Own figure in top 5 |
|---|---|---|---|---|---|---|---|---|
| ES | 0.990 | 0.90 | 0.090 | 0 | 0/5 | 0 | 0/20 | 20/20 |
| EN | 0.950 | 0.90 | 0.050 | 0 | 0/5 | 0 | 0/20 | 20/20 |

The recall matches the week 8 CI (`semana-08/resultados/ci_recuperacion.md`: ES 0.990, EN 0.950), with the same model and the same alfa corpus: adding the beta tenant with the filter active did not change alfa's recall.

**Decision:** `UMBRAL = 0.90` is kept. With 50 questions, each is worth 0.02 of recall: in EN the threshold leaves a margin of two questions before failing. Raising it to 0.95 would make the check fail in EN with any minimal variation.

## Incidents

- **First run (run `40390060225`):** it failed with an HTTP 500 from OpenAI's embeddings API while embedding the questions; it was neither a leak nor a recall problem. Retries with increasing backoff were added, only for transient errors (429 and 5xx), up to 4 attempts. The calibration run needed no retry.

## Maintenance items

GitHub reported two warnings in the run, with no effect on the result at the time:

- `actions/checkout@v4` and `actions/setup-python@v5` used Node.js 20, which is deprecated on the runners.
- `ubuntu-latest` moves to Ubuntu 26 from October 19, 2026.

They also affected the workflows of weeks 6 to 8. Both are resolved: the workflows now use `actions/checkout` v5 and `actions/setup-python` v6, pinned by SHA, on `ubuntu-24.04`.

## Limitations

- Only pgvector runs in CI. Qdrant and OpenSearch were verified with 0 leaks locally (activities 5 and 6).
- CI uses `text-embedding-3-small`, not the bge-m3 model of the local measurements.
- A single calibration run.
