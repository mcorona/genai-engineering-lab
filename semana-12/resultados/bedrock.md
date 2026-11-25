# Activity 4: Bedrock Knowledge Bases

Run on 2026-10-28 in us-east-1.

Scripts:
- [`infra/aws_kb_crear.sh`](../infra/aws_kb_crear.sh): creation and ingestion.
- [`evaluacion/suites.py`](../evaluacion/suites.py): evaluation, the same evaluator as the baseline.

Files:
- Per configuration: `bedrock_<config>[_rag]_resumen.json`, `_detalle.csv`, `_cache.json` and `_salida.txt`.
- Ingestion log: `bedrock_ingesta.txt`.

## Setup

| Item | Value |
|---|---|
| Source | S3 bucket `semana12-docs-<account>` (private), loaded with the activity 2 package; metadata in `.metadata.json` sidecars |
| Vector store | S3 Vectors: one vector bucket, one index per knowledge base (1024 dimensions, cosine, float32; Bedrock's text and internal metadata marked non-filterable so `tenant_id` and `roles` stay filterable) |
| Embeddings | Cohere Embed Multilingual v3. It needs an AWS Marketplace subscription, accepted once by the administrator |
| Retrieval | `Retrieve`, vector search (S3 Vectors has no hybrid search), top 20, filter `tenant_id = alfa` and `roles` in the user's roles inside the query, no reranking |
| Common generator | Haiku 5.5 `medium` through the Anthropic API, `solo_documentos` prompt, same as the baseline |
| Managed mode | `RetrieveAndGenerate` with Claude Haiku 4.5 (`us.` profile; Haiku 5.5 has quota 0 on this account) and Bedrock's default prompt template |

### Configurations

| KB | Documents | Chunking | Parser | Indexed |
|---|---|---|---|---|
| `adm-pred` | originals (md, PDF, JPG, PNG) | Bedrock default | default | 36/40: the 2 JPG and 2 PNG are "not supported" |
| `adm-fijo` | originals | fixed 100 tokens, 20% overlap (closest to 400/80 characters) | default | 36/40 (same 4 images) |
| `adm-fijo-bda` | originals | fixed 100 tokens, 20% | **Bedrock Data Automation, multimodal** | **40/40** |
| `ctl-chunks` | the in-house pipeline's chunks | none (`NONE`) | default | 101/101 |

Getting BDA to read images took three tries:
1. Text-only BDA ignores JPG and PNG.
2. Multimodal BDA requires a supplemental storage location on the knowledge base.
3. That location must be the root of a bucket, not a prefix. It got its own private bucket, `semana12-multimodal-<account>`, writable only by the knowledge base role.

## Results (Spanish; English within 0.03 unless noted)

| Option | recall@1 | recall@5 | MRR | doc_recall@5 | Correctness ES / EN | faithfulness | answer relevancy | Citation precision | False abstention | Correct abstention |
|---|---|---|---|---|---|---|---|---|---|---|
| **In-house pipeline (baseline)** | 0.892 | 1.000 | 0.949 | 1.000 | **1.000 / 1.000** | 0.849 | 0.879 | 0.600 | 0/65 | 10/10 |
| `adm-pred` | 0.677 | 0.823 | 0.755 | 0.831 | 0.815 / 0.815 | 0.815 | 0.750 | 0.604 | 11/65 | 10/10 |
| `adm-fijo` | 0.631 | 0.815 | 0.728 | 0.846 | 0.831 / 0.831 | 0.888 | 0.761 | 0.455 | 10/65 | 10/10 |
| `adm-fijo-bda` | 0.569 | 0.739 | 0.659 | 0.985 | 0.708 / 0.739 | 0.761 | 0.694 | 0.391 | 15/65 | 10/10 |
| `ctl-chunks` | 0.746 | **1.000** | 0.863 | 1.000 | **0.985 / 0.985** | 0.881 | 0.870 | 0.682 | 0/65 | 10/10 |
| `adm-pred` + RetrieveAndGenerate | 0.677 | 0.823 | 0.755 | 0.831 | 0.815 / 0.815 | 0.938 | 0.749 | 0.864 | 11/65 | 10/10 |
| `adm-fijo-bda` + RetrieveAndGenerate | 0.569 | 0.739 | 0.659 | 0.985 | **0.969 / 0.969** | 0.739* | 0.899 | 0.681 | 1/65 | 10/10 |
| `ctl-chunks` + RetrieveAndGenerate | 0.746 | 1.000 | 0.863 | 1.000 | **0.985 / 0.985** | **0.947** | **0.918** | **0.895** | 0/65 | 10/10 |

The retrieval columns of each RetrieveAndGenerate row repeat the `Retrieve` measurement of the same knowledge base.

\* With images in the context, the judge sees only text. Image chunks reach it empty, so faithfulness and citation precision undercount for `adm-fijo-bda`.

**Leakage:** 0 queries returned a chunk from another tenant, in every run. Activity 6 tests leakage by role and across tenants formally.

### Cost and latency per query

| Option | Retrieval USD | Retrieval p50 / p95 (s) | Generation USD | Generation p50 / p95 (s) |
|---|---|---|---|---|
| In-house pipeline (with reranking) | $0.00049 | 2.31 / 3.84 | $0.00021 | 1.69 / 3.39 |
| Bedrock `Retrieve` (`adm-*`, `ctl-chunks`) | ≈ $0.00006 | 0.49 to 0.50 / 0.64 to 0.71 | $0.00021 to $0.00029 (common generator) | 1.8 / 3.1 to 3.2 |
| Bedrock `Retrieve` with BDA multimodal | ≈ $0.00006 | 0.98 / 2.44 | $0.00022 | 2.0 / 4.0 |
| RetrieveAndGenerate (Haiku 4.5) | (included) | — | ≈ $0.0011 to $0.0017 (estimated) | 1.6 to 1.9 / 8.7 to 10.2 |

- Bedrock retrieval is an estimate: Cohere query embedding plus the S3 Vectors query, from the activity 1 prices.
- RetrieveAndGenerate returns no token counts. Its cost is estimated at 4 characters per token, which leaves out image tokens in `adm-fijo-bda`. Actual cost is checked on the bill in activity 10.

## Reading

1. **Ingestion explains almost all of the gap, not Bedrock's search.**
   - With the in-house pipeline's chunks (`ctl-chunks`), Bedrock gets every gold passage into the top 5 and is correct on 0.985. It misses only `rec-17`, the chunk-boundary case already seen in week 11.
   - Its MRR (0.86) matches the own vector search without reranking in week 11 (0.88 / 0.85).
   - **The remaining gap to the in-house pipeline (MRR 0.95, recall@1 0.89) is the reranking step.** Bedrock `Retrieve` on S3 Vectors does not rerank by default.
2. **With the originals and the default parser, every scan and image question is lost.**
   - The default parser skips JPG and PNG. That loses 5 OCR and 5 image questions per language; the generator correctly says the information is not in the context.
   - `rec-11` and `rec-48` also fail, because Bedrock's chunking split their passages.
   - Fixed 100-token chunking is no better than Bedrock's default: correctness 0.831 vs 0.815, lower MRR.
3. **BDA multimodal finds the right documents (`doc_recall@5` 0.985 / 1.000) but returns PDF and image chunks as images, not text.**
   - 319 of the 2,868 retrieved chunks arrive with empty text, all from the 6 PDF and image sources.
   - A text-only generator cannot use them, so this configuration even loses the PDF questions the default parser handled (0.708 correctness).
   - **The managed path does use them:** RetrieveAndGenerate passes the images to Claude and reaches **0.969**, the best managed result on original files.
4. **RetrieveAndGenerate with good retrieval matches the in-house pipeline on quality:**
   - `ctl-chunks` + RetrieveAndGenerate: correctness 0.985, faithfulness 0.947, citation precision 0.89.
   - Its service-side citations are much more precise than the common generator's `[Dn]` citations (0.86 to 0.95 vs 0.45 to 0.70).
   - It costs about 5 to 8 times more per answer, because Haiku 4.5 is priced 10 times above Haiku 5.5, and its p95 latency is about 3 times higher (9 to 10 s).
   - When nothing relevant is found, its default template sometimes answers Spanish questions in English ("Sorry, I am unable to assist you with this request.").

## Decisions for the comparison (activities 7 and 8)

| Use | Bedrock configuration |
|---|---|
| Managed, as a client would set it up from original files | `adm-fijo-bda` + RetrieveAndGenerate (0.969) |
| Controlled (index and ranking quality) | `ctl-chunks` with `Retrieve` (recall@5 1.000, MRR 0.86) |
| Not adopted | `adm-pred` and `adm-fijo` (images lost); `adm-fijo-bda` with a text-only generator |

## Cost of the activity

| Item | Cost |
|---|---|
| Evaluation runs: 7 runs with the Anthropic generator and judge, plus Bedrock retrieval | $1.67 |
| Smoke tests | ≈ $0.03 |
| Bedrock ingestion: Cohere embeddings, BDA parsing, S3, S3 Vectors | estimated < $0.50; to confirm on the bill (activity 10) |
| **Total** | **≈ $2.2** (estimate was $2 to $3) |

## Limitations

- **One run per configuration;** Haiku and the managed generator are not deterministic.
- **Reranking:** Bedrock supports reranking models in `Retrieve`, but they were not enabled here, so the comparison is with the service's default retrieval.
- **Region and model:** S3 Vectors offers no hybrid search, and Haiku 5.5 is not available on this account (quota 0).
- **Multimodal judging:** the judge (text) cannot verify claims supported only by images, so `adm-fijo-bda` faithfulness and citation precision are lower bounds.
