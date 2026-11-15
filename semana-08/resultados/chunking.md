# Activities 1 and 2 (week 8): chunking strategies

Run of 2026-10-26. Scripts: `experimentos/chunking_pasajes.py` (chunks and intact passages) and `experimentos/recall_chunking.py` (recall with bge-m3 in LM Studio).
A corpus of 24 documents; the week 8 gold set with 50 questions per language and 50 unique reference passages. No generative models.
A passage counts as retrieved if any of the top-k chunks contains it intact.

## Results

| Strategy | Chunks | Average characters | Intact passages | ES recall@5 | ES recall@10 | EN recall@5 | EN recall@10 |
|---|---|---|---|---|---|---|---|
| Fixed window 400, overlap 80 | 57 | 348 | 50/50 | **1.000** | **1.000** | **1.000** | **1.000** |
| Recursive by paragraph, max. 300 | 84 | 203 | 48/50 | 0.950 | 0.950 | 0.940 | 0.950 |
| By section (inventory-copilot's chunker) | 69 | 242 | 50/50 | 0.970 | **1.000** | 0.960 | **1.000** |

The recursive strategy splits two reference passages (`recepcion_almacen.md`: a partial rejection when the difference exceeds 2 %; `skus_criticos.md`: a critical SKU with less than 7 days of coverage), so it cannot retrieve them whole at any k.

## Decision

The fixed 400/80 window is the default strategy: it is the best or ties in every cell, splits no passage and is the simplest. Its known weakness is that it ignores section boundaries, which can make citations less precise.

## Limitations

- The differences are one to three questions out of 50: a consistent trend, not a strong result.
- A single embedding model (bge-m3) and a single size per strategy.
- A deterministic run (local embeddings and exact similarity search).
