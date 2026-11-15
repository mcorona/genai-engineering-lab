# Activity 3: embedding models (fixed chunking 400, overlap 80)

Run of 2026-10-22. 57 chunks, 50 queries per language. Recall per reference passage.

| Model | Language | Dimension | recall@5 | recall@10 | Tokens (chunks + queries) | Cost (USD) |
|---|---|---|---|---|---|---|
| bge-m3 (local) | ES | 1024 | 1.000 | 1.000 | not applicable | 0 (local) |
| bge-m3 (local) | EN | 1024 | 1.000 | 1.000 | not applicable | 0 (local) |
| text-embedding-3-small | ES | 1536 | 0.990 | 1.000 | 6472 | 0.000129 |
| text-embedding-3-small | EN | 1536 | 0.950 | 0.980 | 6221 | 0.000124 |
| text-embedding-3-large | ES | 3072 | 1.000 | 1.000 | 6472 | 0.000841 |
| text-embedding-3-large | EN | 3072 | 1.000 | 1.000 | 6221 | 0.000809 |
| gemini-embedding-2 | ES | 3072 | 0.980 | 1.000 | not reported | pending: $0.20 per million input tokens |
| gemini-embedding-2 | EN | 3072 | 0.980 | 1.000 | not reported | pending: $0.20 per million input tokens |

Prices: OpenAI at https://developers.openai.com/api/docs/models (consulted 2026-10-22). Gemini price: $0.20 per million input tokens, as provided by the author; the exact URL to cite is still missing. The script does not record Gemini tokens, so its cost per run remains pending.

Reading: bge-m3 and text-embedding-3-large tie at the maximum. bge-m3 is local, with no API cost, and its dimension (1024) matches inventory-copilot's `doc_chunks.embedding` column. The differences are one or two passages out of 50 queries: on their own they are not conclusive.

A limitation for CI: bge-m3 runs in LM Studio, which is not available in GitHub Actions. If the retrieval eval runs in CI (activity 9), it has to use OpenAI in CI or store precomputed vectors.
