# Week 12 ingestion package (recorded evidence)

[Glossary](../glossary.md) · [Week 12 README](../../semana-12/README.md)

The Spanish data and evidence of week 12 that sit outside a folder with its own README. The results of the runs are
described in [`resultados/README.md`](../../semana-12/resultados/README.md).

This page covers `ingesta/paquete/`, the frozen ingestion package uploaded to S3 (Bedrock Knowledge Bases) and to
GCS (Vertex AI Search). `ingesta/construir_paquete.py` builds it from the in-house pipeline's documents (weeks 8 and 10,
tenant `alfa`) and week 9's tenant `beta`, with the permissions of weeks 9 and 10. The folder has no README of its own:
`construir_paquete.py` hashes every file in it into `manifiesto.json`, `evaluacion/costos.py` sums the size of every
file in it, and the upload scripts sync the folder to the cloud buckets.

**Recorded evidence:** these are the files exactly as built and uploaded for the week 12 runs (not edited, not
translated). The documents are the Spanish corpus of the fictional company; translating them would change what the
managed services indexed and what the week measured. The `infra-semana-12` CI check rebuilds the package on every PR
and fails if any file changes. The English description of the package is in section 2 of the
[week 12 README](../../semana-12/README.md), and the results that used it are summarized in sections 3 to 8.

## Files

| File(s) | What it is | Written by / Read by |
|---|---|---|
| `ingesta/paquete/administrado/**` | Managed mode: the original files per tenant (Markdown, PDF, JPG, PNG), which each service parses, chunks and embeds with its own options. Next to each file, `<file>.metadata.json` carries its permissions in the Bedrock Knowledge Bases format | Written by `ingesta/construir_paquete.py`; uploaded to S3 by `infra/aws_kb_crear.sh`; converted (Markdown to HTML, images to PDF) and uploaded to GCS by `infra/vertex_crear.py`; PDF pages counted by `evaluacion/costos.py` |
| `ingesta/paquete/controlado/textos/**` | Controlled mode: the text the in-house pipeline indexes for each document (pdfplumber for PDFs, Haiku transcription and description for scans and images, Markdown as is), with its `.metadata.json` | Written by `ingesta/construir_paquete.py`; uploaded to S3 by `infra/aws_kb_crear.sh` and to GCS by `infra/vertex_crear.py` |
| `ingesta/paquete/controlado/chunks/**` | Controlled mode: the in-house pipeline's chunks (fixed 400/80), one per file (`<doc>__NNN.txt`), ingested without re-chunking, each with its `.metadata.json` | Written by `ingesta/construir_paquete.py`; uploaded by `infra/aws_kb_crear.sh` and `infra/vertex_crear.py`; read by `evaluacion/costos.py` |
| `ingesta/paquete/vertex_*.jsonl` | One import file per mode for Vertex AI Search: one document per line, with `id`, `structData` (the same permission fields) and `content.uri` in GCS | Written by `ingesta/construir_paquete.py`; read by `infra/vertex_crear.py` |
| `ingesta/paquete/manifiesto.json` | Manifest: the documents and their permissions, the SHA-256 of every file and of the gold sets used, counts and validations | Written by `ingesta/construir_paquete.py`; read by `evaluacion/seguridad.py` and `evaluacion/costos.py` |

## Keys

| Key | Meaning |
|---|---|
| `metadataAttributes` | The Bedrock Knowledge Bases metadata wrapper (in each `.metadata.json`) |
| `tenant_id` | The tenant: `alfa` or `beta` |
| `roles` | The roles allowed to see the document: `almacen` (warehouse), `calidad` (quality), `compras` (purchasing), `finanzas` (finance), `operaciones` (operations), `ventas` (sales) |
| `source` | Document name without extension, the key the week 11 metrics use |
| `doc_id` | `<tenant>__<source>`, plus `__NNN` for chunks |
| `tipo` | Original format: `texto` (text), `pdf`, `jpg` or `png` |
| `chunk` | Chunk index (chunks only) |
| `descripcion` | Description of the package |
| `campos_metadatos` | The metadata fields and their types |
| `documentos` | The documents, with their permission fields |
| `golden` | SHA-256 of the gold sets the package was checked against |
| `validaciones` | The checks run at build time and their results |
| `conteos` | File counts per mode |
| `sha256_archivos` | SHA-256 of every file in the package |
