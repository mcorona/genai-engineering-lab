# Activity 5: second cloud, Vertex AI Search

Run on 2026-10-28 in project `ejemplo1-9xub`, location `global`.

Scripts:
- [`infra/gcp_bucket_crear.sh`](../infra/gcp_bucket_crear.sh) and [`infra/vertex_crear.py`](../infra/vertex_crear.py): creation and import.
- [`evaluacion/suites.py`](../evaluacion/suites.py): evaluation, the same evaluator as the baseline and Bedrock.

Files:
- Per configuration: `vertex_<store>_<search>_resumen.json`, `_detalle.csv`, `_cache.json` and `_salida.txt`.
- Import log: `vertex_ingesta.txt`.

Azure AI Search was the alternative in the plan. Vertex was chosen because the Google Cloud account already existed.

## Setup

| Item | Value |
|---|---|
| Source | Private GCS bucket `semana12-docs-ejemplo1-9xub` (US), readable only by the operator service account and the Discovery Engine service agent |
| Metadata | `tenant_id`, `roles`, `source`, `doc_id`, `tipo` in `structData`; `tenant_id` and `roles` declared indexable in the schema before import |
| Filter | Inside the query: `tenant_id: ANY("alfa") AND roles: ANY(<user roles>)` |
| Apps | One per data store, Enterprise edition, no LLM add-on |
| Identity | Service account `semana12-operador` by impersonation: `discoveryengine.editor`, `serviceusage.serviceUsageConsumer`, and object access on the bucket only. No keys |
| Request | top 20, `relevanceThreshold: LOWEST`, automatic query expansion |

With default settings the service returned 0 to 7 results per query, and none for several English questions about Spanish documents. With the two settings above it returned 20 results for every query, in every run.

### Data stores

| Data store | Mode | Content | Processing | Imported |
|---|---|---|---|---|
| `vx-adm` | **Managed** | The 40 originals | Layout parser, default chunking (500 tokens) | 40/40 |
| `vx-ctl` | **Controlled** | The in-house pipeline's 101 chunks, one document each | Digital parser, no chunking | 101/101 |

Vertex does not import Markdown with the layout parser (TXT is digital-parser only) or standalone JPG and PNG. So `vx-adm` receives the Markdown converted to HTML (same text, with headings, lists and tables) and each image wrapped in a one-page PDF, which the layout parser OCRs.

### Search modes

| Mode | How |
|---|---|
| `hibrida` | The service's default ranking: keywords plus embeddings |
| `vectorial` | Custom ranking by formula, `semantic_similarity_score` only. It reorders the candidates the service retrieves, so it is not a pure vector index (Vertex does not expose one) |
| `semantico` | Hybrid top 20 reordered by the Ranking API (`semantic-ranker-default@latest`), the semantic ranker |

## Results (ES / EN)

| Option | recall@1 | recall@5 | MRR | doc_recall@5 | Correctness | faithfulness | Citation precision | False abstention |
|---|---|---|---|---|---|---|---|---|
| **In-house pipeline (baseline)** | 0.892 / 0.885 | 1.000 / 1.000 | 0.949 / 0.954 | 1.000 / 1.000 | **1.000 / 1.000** | 0.849 / 0.830 | 0.600 / 0.625 | 0 / 0 |
| `vx-adm` hybrid | 0.777 / 0.731 | 0.831 / 0.823 | 0.823 / 0.797 | 1.000 / 0.992 | 0.923 / 0.923 | 0.871 / 0.861 | 0.583 / 0.663 | 4 / 3 |
| `vx-adm` vector | 0.715 / 0.715 | 0.808 / 0.808 | 0.787 / 0.787 | 0.977 / 0.977 | 0.908 / 0.908 | 0.867 / 0.863 | 0.575 / 0.614 | 4 / 6 |
| `vx-adm` semantic ranker | 0.815 / 0.800 | 0.831 / 0.831 | 0.839 / 0.831 | 1.000 / 1.000 | 0.923 / 0.923 | 0.852 / 0.854 | 0.615 / 0.667 | 4 / 3 |
| `vx-ctl` hybrid | 0.885 / 0.777 | 1.000 / 0.962 | 0.949 / 0.860 | 1.000 / 0.985 | 1.000 / 0.969 | 0.860 / 0.859 | 0.616 / 0.700 | 0 / 0 |
| `vx-ctl` vector | 0.815 / 0.785 | 1.000 / 1.000 | 0.897 / 0.881 | 1.000 / 1.000 | **1.000 / 0.985** | 0.844 / 0.869 | 0.632 / 0.675 | 0 / 0 |
| `vx-ctl` semantic ranker | **0.939 / 0.908** | **1.000 / 1.000** | **0.977 / 0.962** | 1.000 / 1.000 | 0.985 / 0.985 | 0.790 / 0.814 | 0.650 / 0.721 | 0 / 0 |

- **Correct abstention:** 10/10 per language in every configuration.
- **Leakage:** 0 queries with a chunk from another tenant, in every run. Activity 6 tests leakage formally.
- **Judge scores missing:** 0 to 2 per run.

### Cost and latency per query

| Option | Retrieval USD | Retrieval p50 / p95 (s) | Generation USD (common generator) | Generation p50 / p95 (s) |
|---|---|---|---|---|
| In-house pipeline (Haiku reranking) | $0.00049 | 2.31 / 3.84 | $0.00021 | 1.69 / 3.39 |
| Vertex hybrid or vector | $0 within 10,000 queries per month; $0.004 at Enterprise list price | 0.38 to 0.43 / 0.52 to 0.99 | $0.00021 to $0.00034 | 1.6 to 1.8 / 3.1 to 4.5 |
| Vertex + semantic ranker | + $0.001 (Ranking API) | 0.71 to 0.78 / 0.87 to 1.33 | $0.00021 to $0.00032 | 1.6 to 1.8 / 3.4 to 5.6 |

- `vx-adm` generation costs a bit more because its 500-token chunks give the generator a longer context.
- About 2,000 queries this week, all inside the free tier.

## Reading

1. **With the same chunks, Google's semantic ranker beats the in-house pipeline's reranking.**
   - `vx-ctl` + semantic ranker: MRR 0.977 / 0.962 and recall@1 0.94 / 0.91, against the in-house pipeline's 0.949 / 0.954 and 0.89.
   - Retrieval takes 0.7 s instead of 2.3 s, for $0.001 instead of $0.0005 per query.
   - Correctness is 0.985, with one generator slip per language (`rec-02` ES, `rec-23` EN). Their passages were in the context.
2. **Hybrid is good in Spanish and weaker in English.**
   - `vx-ctl` hybrid matches the baseline in Spanish (MRR 0.949, correctness 1.000).
   - It drops in English (MRR 0.860, recall@5 0.962), because its keyword component cannot match English questions against Spanish text. `rec-46` and `rec-47` EN lose their passage.
   - The vector formula removes that language gap (0.897 / 0.881), at the level of a vector-only search (Bedrock `ctl-chunks` 0.863; week 11 own vector search 0.88 / 0.85).
3. **Managed ingestion handles PDFs and scans, but not charts or floor plans.**
   - `vx-adm` reads the 2 PDFs and the 2 scans correctly; all 10 OCR and PDF questions per language are answered.
   - The 5 image questions per language fail. The layout parser's OCR extracts the chart's labels and figures ("97.8% 95.1% 98.6% CEDIS Centro … CEDIS Occidente CEDIS Norte"), but not which value belongs to which distribution center. The generator rightly declines.
   - The attribution rule counts these as generation failures because the literal answer is in the context. The cause is parsing. Week 10 solved the same images with a Haiku description at indexing time.
4. **The exact retrieval metrics undercount `vx-adm`.** Its recall@5 is 0.83 while `doc_recall@5` is 1.000 and correctness is 0.92. Its chunks hold the right document, but the HTML-to-text conversion and the 500-token chunks change line breaks and table layout, so some literal gold passages no longer match character by character.
5. **Correct abstention is 10/10 everywhere.** The managed path's false abstentions (3 to 6 per language) are the image questions plus one or two vector-mode misses.

## Decisions for the comparison (activities 7 and 8)

| Use | Vertex configuration |
|---|---|
| Managed, as a client would set it up from original files | `vx-adm` with the semantic ranker (correctness 0.923; images not understood) |
| Controlled (index and ranking quality) | `vx-ctl` with the semantic ranker (MRR 0.977 / 0.962, correctness 0.985) |

## Cost of the activity

| Item | Cost |
|---|---|
| Evaluation runs: 6 runs, Anthropic generator and judge, plus the Ranking API | $1.37 |
| Smoke tests | ≈ $0.04 |
| Vertex: layout parser on about 60 pages, import, index and storage | estimated < $1; within the free tier for queries and index; to confirm on the bill (activity 10) |
| **Total** | **≈ $2** (estimate $2) |

## Limitations

- **One run per configuration.**
- **"Vector" is a ranking formula over the service's candidates, not a separate vector index.** Vertex does not expose pure vector retrieval for these data stores.
- **Format conversion:** Markdown and images were converted before ingestion because the service does not import them. A client would have to do the same.
- **Chunking:** only the default (500 tokens). Vertex has no overlap setting and its minimum is 100 tokens.
