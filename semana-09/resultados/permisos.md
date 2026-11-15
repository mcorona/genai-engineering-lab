# Activity 5: metadata filters and ACLs

Run of 2026-10-26. Script: `experimentos/permisos.py`. No calls to generative models: API cost 0.

The 57 week 8 chunks (fixed 400/80, bge-m3) were loaded into new indexes with `tenant_id = "alfa"` and the `roles` of their document according to `datasets/permisos.json` (a synthetic test model):
pgvector (`semana9.chunks`, pgvector 0.8.6), Qdrant (`semana9_acl`, v1.12.4) and OpenSearch (`semana9_acl`, 2.19.1). The week 8 indexes were not touched.

## Where the filter goes

The filter goes inside the search query in all three databases; it is not applied to results already retrieved:

- **pgvector:** `WHERE tenant_id = %s AND roles && %s::text[]` in the same SQL as the `ORDER BY embedding <=> ...`. With `hnsw.iterative_scan = strict_order` (pgvector ≥ 0.8), the HNSW index keeps searching until it fills k with rows that satisfy the filter.
- **Qdrant:** a `filter` with `must` on `tenant_id` and `roles` (match any) inside `points/query`, with `keyword` payload indexes on both fields.
- **OpenSearch:** a `filter` (bool with `term` and `terms`) inside the `knn` clause, which filters during the search instead of afterwards.

## How it is measured

- **Permission leak:** top-10 chunks returned to a user whose tenant does not match or whose roles do not intersect the document's. It is judged against `permisos.json`, not against what the database stores, so a loading error would also count as a leak.
- **Sweep:** 50 base questions × 6 roles = 300 queries per database and language, with and without the filter (contrast).
- **recall@5 with vs. without the filter:** on the 112 question–role pairs where the role can see the reference document.
- **Permission cases from the gold set:** 5 allowed (recall@5) and 5 forbidden (the passage must not appear).
- **Short results:** filtered searches that return fewer than k chunks although k are visible.

## Results

| Database | Language | Queries | Leak with filter | Unauthorized chunks without filter | recall@5 without filter | recall@5 with filter | Allowed recall@5 (without / with) | Forbidden returned (without / with) | Short results |
|---|---|---|---|---|---|---|---|---|---|
| pgvector | es | 300 | **0** | 1983 | 1.000 | 0.991 | 1.000 / 1.000 | 5/5 / **0/5** | 0 |
| Qdrant | es | 300 | **0** | 1983 | 1.000 | 0.991 | 1.000 / 1.000 | 5/5 / **0/5** | 0 |
| OpenSearch | es | 300 | **0** | 1974 | 1.000 | 0.991 | 1.000 / 1.000 | 5/5 / **0/5** | 0 |
| pgvector | en | 300 | **0** | 1980 | 1.000 | 0.991 | 1.000 / 1.000 | 5/5 / **0/5** | 0 |
| Qdrant | en | 300 | **0** | 1980 | 1.000 | 0.991 | 1.000 / 1.000 | 5/5 / **0/5** | 0 |
| OpenSearch | en | 300 | **0** | 1984 | 1.000 | 0.991 | 1.000 / 1.000 | 5/5 / **0/5** | 0 |

Total leak with the filter: **0**. The script exits with code 0; with any leak it exits with code 1.

## Reading

- **0 leaks in all three databases and in both languages.** The non-negotiable criterion is met with a single tenant (the cross-tenant test is activity 6).
- **Without the filter, the risk is real:** about 1,980 of the 3,000 chunks returned (66 %) were not authorized for the user, and all 5 forbidden passages of the gold set appeared.
- **The 0.991 recall with the filter is the correct behavior, not a loss.** It is reproduced exactly by the permissions alone: in `rec-47`, the `compras` role cannot see `transferencias_cedis.md`, and in `rec-49`, the `almacen` role cannot see `ordenes_de_compra.md`. These are questions with two reference passages, and the filter hides the one the user is not allowed to see. The 5 allowed cases keep a recall@5 of 1.000.
- **No short results.** In pgvector, `iterative_scan` prevents the filter from leaving the HNSW search with fewer than k results.
- **Small differences without the filter** (1,974 to 1,984) between databases come from each engine ordering the approximate neighbors at the tail of the top 10 differently. They do not affect the leak with the filter.

## Limitations

- A single tenant (`alfa`). Isolation between tenants is tested in activity 6.
- Document-level permissions, with one role per user. Users with several roles and per-chunk permissions were not tested.
- Synthetic roles (`permisos.json`), not real inventory-copilot permissions.
- A small corpus (57 chunks): with many more documents, filtering inside HNSW becomes more demanding, and short results and latency would have to be measured again.
- The latency with the filter vs. without it was not measured.
