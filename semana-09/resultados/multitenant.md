# Activity 6: multi-tenant isolation

Run of 2026-10-26. Script: `experimentos/multitenant.py`. No calls to generative models: API cost 0.

## Test tenants

- **alfa:** the 24 week 8 documents (57 chunks).
- **beta:** `corpus_beta/`, 10 documents copied from alfa. Each differs from its pair in a single line: the figure in the reference passage (for example, a return window of 30 instead of 20 days; a safety factor for critical SKUs of 1.5 instead of 2.0). 33 chunks. Generated and validated by `datasets/construir_multitenant.py`: each changed passage appears once and stays whole within one chunk in both tenants.

Both tenants are in the same indexes: `semana9.chunks_mt` in pgvector 0.8.6, `semana9_mt` in Qdrant 1.12.4 and `semana9_mt` in OpenSearch 2.19.1, with `tenant_id` and `roles`. The filter goes inside the query, as in activity 5. The indexes of earlier activities were not touched.

## How it is measured

- **Sweep:** 50 base questions × 2 tenants, with a user who has every role, so that only the tenant filter acts. Leaks are judged against `tenant_id` and `permisos.json`.
- **Overlapping cases** (`datasets/multitenant_{es,en}.jsonl`): the 10 questions whose passage exists almost identically in both tenants, asked from alfa and from beta, with a role that can see the document. That gives 20 cases per database and language.
- **Contrast without the filter:** the same sweep without the filter, split by tenant (how many chunks from the other tenant each user would see).
- **Short results:** filtered searches that return fewer than k chunks although k are visible.

## Results

| Database | Language | Sweep (question × tenant) | Leak with filter | Other tenant's chunks without filter (alfa's / beta's top 10) | Overlapping cases | Own figure in top 5 (with filter) | Other tenant's figure returned (without / with filter) | Other tenant ranked above own (without filter) | Short results |
|---|---|---|---|---|---|---|---|---|---|
| pgvector | es | 100 | **0** | 185 / 315 | 20 | 20/20 | 20/20 / **0/20** | 10/20 | 0 |
| Qdrant | es | 100 | **0** | 191 / 309 | 20 | 20/20 | 20/20 / **0/20** | 10/20 | 0 |
| OpenSearch | es | 100 | **0** | 186 / 314 | 20 | 20/20 | 20/20 / **0/20** | 10/20 | 0 |
| pgvector | en | 100 | **0** | 181 / 319 | 20 | 20/20 | 20/20 / **0/20** | 10/20 | 0 |
| Qdrant | en | 100 | **0** | 187 / 313 | 20 | 20/20 | 20/20 / **0/20** | 10/20 | 0 |
| OpenSearch | en | 100 | **0** | 180 / 320 | 20 | 20/20 | 20/20 / **0/20** | 10/20 | 0 |

Total leak with the filter, including the other tenant's figure: **0**. Exit code 0.

## Reading

- **Complete isolation with the filter:** 0 leaks in all three databases and in both languages. No query returned the other tenant's figure, even though the chunks are almost identical.
- **Each tenant gets its own answer:** 20 of 20 overlapping cases have the tenant's own figure in the top 5.
- **Without the filter, the risk is high:** an alfa user would see 180 to 191 of 500 chunks from beta (36 to 38 %), and a beta user 309 to 320 chunks from alfa (62 to 64 %). In the overlapping cases, the other tenant's figure appears in the top 10 in 20 of 20, and it ranks above the tenant's own in 10 of 20. With almost identical text, the ordering between tenants is practically random, so without the filter a user would get the other company's figure half of the time.
- **No short results:** the filter leaves no search with fewer than k results.

## Correction during the activity

The first version summed, in a single column, the other tenant's chunks without the filter for both users. That sum is always 10 per question (500 in total) by construction, because without the filter the result is the same for both users. It was split by tenant. Leaks, overlapping cases and short results did not change between runs.

## Limitations

- Two tenants in shared indexes, separated by a filter. Physical isolation (one index or collection per tenant) was not tested.
- The beta tenant has 10 documents: the contrast without the filter depends on that size.
- One role per user in the overlapping cases. The permissions and tenants are synthetic.
- The latency with the filter vs. without it was not measured.
