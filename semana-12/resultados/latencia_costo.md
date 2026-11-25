# Activity 7: latency and cost

Scripts:
- [`evaluacion/latencia.py`](../evaluacion/latencia.py) (latency) and [`evaluacion/costos.py`](../evaluacion/costos.py) (cost), run on 2026-10-28.

Files:
- Latency: `latencia_resumen.json` and `latencia_detalle.csv`.
- Cost: `costos_resumen.json`.
- Output: `latencia_salida.txt` and `costos_salida.txt`.

## Latency

**Same client, same location, same network:** one Mac in Guadalajara calling us-east-1 (AWS) and `global` (Google Cloud), with **concurrency 1**.
- **Questions:** 100 from the gold set; per language, 40 answerable and the 10 unanswerable.
- **Order:** for each question all options run in **random order** (seed 12), so network drift does not favor any option.
- **Full answer:** retrieval plus the common generator (Haiku 5.5 `medium`, top 5). RetrieveAndGenerate is a single call.

| Option | Retrieval p50 (s) | Retrieval p95 (s) | Full answer p50 (s) | Full answer p95 (s) |
|---|---|---|---|---|
| In-house pipeline (bge-m3 + pgvector + Haiku reranking) | 2.27 | 3.07 | 3.89 | 6.07 |
| In-house pipeline without reranking | 0.06 | 0.06 | 1.74 | 3.33 |
| Bedrock `Retrieve`, `ctl-chunks` | 0.92 | 1.06 | 2.58 | 4.09 |
| **Bedrock RetrieveAndGenerate, `adm-fijo-bda` (Haiku 4.5)** | (included) | (included) | **1.50** | **2.21** |
| Vertex `vx-ctl` + semantic ranker | 0.76 | 1.06 | 2.40 | 3.94 |
| Vertex `vx-adm` + semantic ranker | 0.88 | 1.34 | 2.48 | 3.84 |

- **Reranking is the in-house pipeline's latency cost:** 2.2 s of its 2.3 s retrieval is the Haiku reranking call. Without it, local retrieval takes 0.06 s, because bge-m3 and pgvector run on the same machine with no network.
- **The managed services retrieve in 0.8 to 0.9 s from Mexico,** including the round trip to the cloud. Vertex with its semantic ranker is as fast as Bedrock without one.
- **RetrieveAndGenerate is the fastest full answer** (p50 1.5 s, p95 2.2 s). Retrieval and generation run inside AWS in a single call, with no second round trip from the client.
  - Activity 4 measured a p95 of 9 to 10 s for it. That run used 4 parallel requests, so it reflected queuing and throttling, not single-query latency.

## Cost

Prices: official catalogs from activity 1 (`precios_catalogo_2026-10-28.csv`). The RDS hosting price comes from the AWS Price List API, queried on 2026-10-28.

### One-time ingestion (this corpus: 40 documents, 101 controlled chunks)

| Option | Ingestion USD | Detail |
|---|---|---|
| In-house pipeline | 0.003 | bge-m3 runs locally; Haiku image extraction (week 10) |
| Bedrock `ctl-chunks` | 0.001 | Cohere embeddings of 35,031 characters, S3 Vectors upload |
| Bedrock `adm-fijo-bda` | 0.033 | Cohere embeddings; BDA for 2 PDF pages and 4 images. If BDA also bills the 34 Markdown files: at most + $0.34 |
| Vertex `vx-ctl` | 0 | Digital parser, embeddings included |
| Vertex `vx-adm` | 0.40 | Layout parser on 40 pages: 34 HTML (3,000 characters per page), 2 PDF and 4 images as PDF |

### Fixed monthly cost

| Option | USD per month | Basis |
|---|---|---|
| **In-house pipeline hosted in the cloud** | **13.98** | RDS PostgreSQL with pgvector, db.t4g.micro Single-AZ ($0.016 per hour) plus 20 GB gp3 ($0.115 per GB-month). This is the smallest instance that holds this corpus |
| Bedrock (any configuration) | ≈ 0.0001 | S3 Vectors ($0.06 per GB-month) and S3 Standard for under 2 MB |
| Vertex (any data store) | ≈ 0 | Index inside the 10 GiB free tier; GCS for under 2 MB |

### Variable cost per query (full answer)

| Option | USD per query | Composition |
|---|---|---|
| In-house pipeline | 0.000703 | Haiku reranking $0.00049 + Cohere query embedding + common generator $0.00021 |
| **Bedrock `Retrieve` + common generator** | **0.000269** | Query embedding and S3 Vectors query ≈ $0.00006 + generator |
| Bedrock RetrieveAndGenerate (Haiku 4.5) | 0.001083 (estimated) | The API returns no token counts; estimated from characters (activity 4). With Haiku 5.5, once the quota is granted, it would be about 10 times lower |
| Vertex `vx-ctl` + semantic ranker + common generator | 0.001213 | Ranking API $0.001 + generator; search is **free for the first 10,000 queries a month**, then $0.004 per query (Enterprise list price) |
| Vertex `vx-adm` + semantic ranker + common generator | 0.001316 | The same, with a slightly longer context |

### Monthly cost by volume and break-even point

| Queries per month | In-house pipeline (hosted) | Bedrock `Retrieve` + generator | Bedrock RetrieveAndGenerate | Vertex `vx-ctl` | Vertex `vx-adm` |
|---|---|---|---|---|---|
| 1,000 | 14.68 | **0.27** | 1.08 | 1.21 | 1.32 |
| 10,000 | 21.01 | **2.69** | 10.83 | 12.13 | 13.16 |
| 50,000 | 49.13 | **13.45** | 54.15 | 220.65 | 225.80 |
| 100,000 | 84.28 | **26.90** | 108.30 | 481.30 | 491.60 |
| 1,000,000 | 716.98 | **269.00** | 1,083.00 | 5,173.00 | 5,276.00 |

**When each option becomes more expensive than the hosted in-house pipeline:**

| Option | Break-even | Why |
|---|---|---|
| Bedrock `Retrieve` + common generator | **Never** | Lower fixed cost and lower cost per query |
| Bedrock RetrieveAndGenerate (Haiku 4.5) | **≈ 37,000 queries a month** | Haiku 4.5 costs 10 times more per token than the common generator. With Haiku 5.5 the gap would disappear |
| Vertex (both data stores, semantic ranker) | **≈ 12,000 queries a month** | Search is free up to 10,000 a month. After that, $0.004 per Enterprise query plus $0.001 for the ranker cost far more than the rest of the pipeline. Standard edition ($0.0015 per query) only moves the point to about 14,000 |

## Reading

- **For this corpus, the managed options have no meaningful fixed cost.** The in-house pipeline only has one when it is hosted ($14 a month for the smallest managed PostgreSQL). Run on an existing server, its cost is just the cost per query.
- **Bedrock `Retrieve` with your own generator is the cheapest option at every volume:** $0.00027 per answer, about 2.6 times cheaper than the in-house pipeline. Its quality is the issue: MRR 0.86 without reranking vs 0.95 for the in-house pipeline (activity 4). Adding Bedrock's reranking, Cohere Rerank 3.5 at $0.002 per search unit, would raise its cost to about the in-house pipeline's.
- **Vertex is the best ranker (MRR 0.97 with its semantic ranker) but the most expensive at volume.** Past 10,000 queries a month, search and ranking dominate the bill: at 100,000 a month it costs almost 6 times the in-house pipeline.
- **RetrieveAndGenerate is the fastest full answer (p50 1.5 s) and the simplest to operate.** With Haiku 4.5 it costs 1.5 to 4 times the in-house pipeline, depending on volume.

## Limitations

- **Latency:** measured from one location (Guadalajara) on a home connection, one query at a time. Production latency inside the same cloud region would be lower for every option, and most for the managed ones.
- **RetrieveAndGenerate cost is estimated,** because the API returns no token counts. Image tokens in `adm-fijo-bda` are not included.
- **Hosting:** the in-house pipeline's hosting model covers only the database. Application compute and egress are the same for every option and are left out. bge-m3 is replaced by Cohere query embeddings in the cloud estimate.
- **List prices before taxes, credits and free tiers** (except Vertex's 10,000 free queries). Activity 10 checks the actual bill for the week.
