# Activity 6: security in the managed services

Script: [`evaluacion/seguridad.py`](../evaluacion/seguridad.py) (run on 2026-10-28). Detail per query: `seguridad_detalle.csv`; summary: `seguridad_resumen.json`; output: `seguridad_salida.txt`.

## Tests (the same as week 10, activity 8)

| Type | Cases | User |
|---|---|---|
| **By role** | 56 (28 per language): every document and non-text question of the week 10 integrated gold set whose document is not open to every role | Tenant `alfa` with a single role that has **no access** to the gold document (the first missing role in week 10's order) |
| **Across tenants** | 40 (10 week 9 multi-tenant questions × 2 tenants × 2 languages). Each document exists in `alfa` and in `beta` with a different figure | One user of `alfa` and one of `beta`, both with every role |

- **Filter inside the query, top 20:**
  - Bedrock `Retrieve`: `equals tenant_id` and `listContains roles`.
  - Vertex search: `tenant_id: ANY(...) AND roles: ANY(...)`.
  - RetrieveAndGenerate: the same Bedrock filter, checked on the references it cites.
- **Leakage:** a result whose tenant or roles do not authorize the user. The tenant and document come from the file's real location (S3 or GCS path, or document id), and the document's roles from the frozen manifest of activity 2, not from the metadata the service returns. A wrong metadata value inside a service would therefore show up as leakage too.

## Results

| System | Leakage by role (56) | Leakage across tenants (40) | Forbidden document in results | Results per query, role / tenant (mean) |
|---|---|---|---|---|
| Bedrock `adm-pred` | **0** | **0** | 0 | 5.3 / 16.2 |
| Bedrock `adm-fijo` | **0** | **0** | 0 | 11.5 / 19.1 |
| Bedrock `adm-fijo-bda` | **0** | **0** | 0 | 11.4 / 18.9 |
| Bedrock `ctl-chunks` | **0** | **0** | 0 | 11.3 / 20 |
| Bedrock `adm-fijo-bda` + RetrieveAndGenerate (cited references) | **0** | **0** | 0 | 0.0 / 1.0 |
| Vertex `vx-adm` | **0** | **0** | 0 | 5.2 / 15 |
| Vertex `vx-ctl` | **0** | **0** | 0 | 11.3 / 20 |
| **Total** | **0 of 672 queries** | | | |

### Controls

**Without a filter, the test detects leakage:**

| Control (same queries, no filter) | Unauthorized chunks | Queries with leakage | Forbidden document returned |
|---|---|---|---|
| Bedrock `ctl-chunks`, by role | 1,025 | 56 / 56 | 56 / 56 |
| Bedrock `ctl-chunks`, across tenants | 401 | 40 / 40 | 40 / 40 |
| Vertex `vx-ctl`, by role | 1,070 | 56 / 56 | 56 / 56 |
| Vertex `vx-ctl`, across tenants | 400 | 40 / 40 | 40 / 40 |

**The filter is applied inside the query, not after the top k.**
- In `ctl-chunks` and `vx-ctl` (one chunk per document), every role query returns exactly min(20, number of chunks that role may see). For example, `ventas` can see 11 chunks of `alfa` and gets 11; `calidad` can see 14 and gets 14.
- A filter applied after picking the top 20 would return fewer, and would vary with the question.
- Users with every role get 20 (`alfa` has 68 chunks, `beta` has 33).
- In the managed modes, the counts follow the services' own chunking: Bedrock's default makes larger chunks, and Vertex's are 500 tokens.

RetrieveAndGenerate cites nothing in the role cases, because the single-role user cannot see any document that answers the question, and it cites one reference per tenant case. Its citations never include another role's or tenant's document.

## Decision

**Both services filter by tenant and role inside the query, with leakage 0 in 672 queries.**
- Leakage 0 holds for every Bedrock configuration, for RetrieveAndGenerate, and for both Vertex data stores.
- Neither service is ruled out for security.
- The non-negotiable criterion (zero leakage) holds, as it did for the in-house pipeline in weeks 9 and 10.

## Limitations

- Filters depend on the metadata attached at ingestion: a document uploaded without `tenant_id` or `roles` would be unreachable, or reachable by everyone, depending on the filter. This week the package validates that every document has both (activity 2).
- The tests check retrieval and citations. They do not test prompt-injection through documents; week 10 covered that for the own assistant.
- **Cost:** ≈ $0.20, almost all of it RetrieveAndGenerate with Haiku 4.5 (96 answers); Bedrock retrieval costs cents, and Vertex search is in the free tier.
