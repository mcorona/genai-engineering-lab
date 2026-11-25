# Week 8 results (recorded evidence)

[Glossary](../../docs/glossary.md) · [Week 8 README](../README.md)

The reports of the week 8 retrieval runs: chunking, embedding models, BM25 and hybrid search, and the calibration of
the retrieval eval in CI. Each report gives the date or the CI run, the setup and the measured values.

**Recorded evidence:** these reports record the runs as they were measured. They are already in English. The scripts
print their values to the console, and no script writes to this folder, so it holds only the reports: no
per-question output of these runs is stored here. The [week 8 README](../README.md) sums up every activity, including
the vector database, reranking and end-to-end results that have no report in this folder.

## Files

| File(s) | What it is | Written from |
|---|---|---|
| `chunking.md` | Activities 1 and 2: chunking strategies, whole gold passages and recall per strategy | `experimentos/chunking_pasajes.py`, `experimentos/recall_chunking.py` |
| `embeddings_fijo_400_solape_80.md` | Activity 3: embedding models compared on fixed 400-character chunks with an 80-character overlap | `experimentos/embeddings_comparacion.py` |
| `hibrida.md` | Activity 6: BM25, vector and hybrid search with RRF | `experimentos/hibrida_bm25.py` |
| `ci_recuperacion.md` | Activity 9: the first run of the retrieval eval in CI, and why its 0.90 recall@5 threshold was kept | `ci/recuperacion_ci.py`, workflow `recuperacion-semana-08` |
