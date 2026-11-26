# Week 12 results (recorded evidence)

[Glossary](../../docs/glossary.md) · [Week 12 README](../README.md)

The outputs of the week 12 runs: the week 11 suites against the in-house pipeline (the baseline), four Bedrock knowledge
bases and two Vertex AI Search data stores, plus the leakage tests, the latency and cost measurements, the price catalog
and the final comparison. `evaluacion/suites.py` writes one summary, one detail file and one cache per run, and its console output is saved
next to them. `evaluacion/validar_resultados.py` checks them on every PR, and `evaluacion/comparar.py` rebuilds the comparison
table from the summaries.

**Recorded evidence:** these are the raw outputs of the runs, kept exactly as recorded (not edited, not translated).
The model answers in them are in Spanish or English, depending on the question's language. The English summary of the
results is in the [week 12 README](../README.md) (sections 3 to 10) and in the English reports of this folder:
[`linea_base.md`](linea_base.md), [`bedrock.md`](bedrock.md), [`vertex.md`](vertex.md),
[`seguridad.md`](seguridad.md), [`latencia_costo.md`](latencia_costo.md), [`comparacion.md`](comparacion.md),
[`costos_fijos.md`](costos_fijos.md) and [`costo_real.md`](costo_real.md).

## Files

| File(s) | What it is | Written by / Read by |
|---|---|---|
| `linea_base.md`, `bedrock.md`, `vertex.md`, `seguridad.md`, `latencia_costo.md`, `comparacion.md`, `costos_fijos.md`, `costo_real.md` | The English reports of activities 1 and 3 to 10 | Written with the week; they cite the files below |
| `propio_resumen.json`, `bedrock_*_resumen.json`, `vertex_*_resumen.json` | Summary of one suite run: retrieval and generation metrics per language, cost and latency per query, failed questions. `propio` = the in-house pipeline; `bedrock_<config>` = a knowledge base with the common generator, `_rag` = with RetrieveAndGenerate; `vertex_<store>_<search mode>` = a data store with `hibrida` (hybrid), `vectorial` (vector) or `semantico` (semantic ranker) search | Written by `evaluacion/suites.py`; read by `evaluacion/comparar.py`, `evaluacion/costos.py` and `evaluacion/validar_resultados.py` |
| `propio_detalle.csv`, `bedrock_*_detalle.csv`, `vertex_*_detalle.csv` | Per-question detail of the same run, one row per question and language | Written by `evaluacion/suites.py`; read by `evaluacion/validar_resultados.py` |
| `propio_cache.json`, `bedrock_*_cache.json`, `vertex_*_cache.json` | Recorded responses per question, reused when a run is repeated. Entries are keyed `<step>::<question id>::<lang>`: `rec` (the retrieval ranking), `gen` (the generated answer), `clase` (answered or abstained) and one entry per judge metric | Written and read by `evaluacion/suites.py`; read by `evaluacion/validar_resultados.py` |
| `propio_salida.txt`, `bedrock_*_salida.txt`, `vertex_*_salida.txt` | Console output of each suite run, as printed | Printed by `evaluacion/suites.py` |
| `bedrock_ingesta.txt`, `vertex_ingesta.txt` | Logs of the knowledge base creation and ingestion, and of the Vertex AI Search import | `infra/aws_kb_crear.sh`; `infra/gcp_bucket_crear.sh` and `infra/vertex_crear.py` |
| `seguridad_resumen.json`, `seguridad_detalle.csv`, `seguridad_salida.txt` | Leakage tests by role and across tenants, per system, with and without the permission filter: summary, one row per query, console output | Written by `evaluacion/seguridad.py`; the summary is read by `evaluacion/comparar.py` and `evaluacion/validar_resultados.py` |
| `latencia_resumen.json`, `latencia_detalle.csv`, `latencia_cache.json`, `latencia_salida.txt` | Latency and cost of a full answer per option: summary, one row per question and option, recorded measurements, console output | Written by `evaluacion/latencia.py`; the summary is read by `evaluacion/costos.py`, `evaluacion/comparar.py` and `evaluacion/validar_resultados.py` |
| `costos_resumen.json`, `costos_salida.txt` | Cost model: prices used, one-time ingestion cost, fixed monthly cost, cost per query, monthly cost at several volumes and the break-even point against the in-house pipeline | Written by `evaluacion/costos.py`; the summary is read by `evaluacion/comparar.py` and `evaluacion/validar_resultados.py` |
| `precios_catalogo_*.csv` | Prices from the AWS Price List API and the Google Cloud Billing Catalog API, filtered to the services the week uses, with the query date in the file name | Written by `infra/precios.py`; read by `evaluacion/costos.py` |
| `comparacion.json`, `comparacion_tabla.md` | The final comparison table (option × ingestion mode × language), machine-readable and as Markdown. The keys and headers are in English | Written by `evaluacion/comparar.py`; checked unchanged by the `infra-semana-12` CI check |

## Keys

| Key | Meaning |
|---|---|
| `config` | The configuration measured: a knowledge base (`adm-pred`, `adm-fijo`, `adm-fijo-bda`, `ctl-chunks`) or a data store and search mode (`vx-adm:semantico`). `adm-*` = managed ingestion of the originals; `ctl-*` = the lab's own chunks |
| `modo` | Generation mode: `comun` = the common generator (the same model and prompt for every option); `rag` = Bedrock RetrieveAndGenerate |
| `fecha` | Run date |
| `preguntas` | Number of questions in the run |
| `generador`, `juez` | The generator model and settings; the LLM judge |
| `k_contexto` | Passages passed to the generator |
| `backend` | The retrieval system: `propio` (the in-house pipeline), `bedrock` or `vertex` |
| `chunks_fuera_del_tenant` | Queries whose results include a chunk from another tenant (leakage) |
| `recuperacion` | Retrieval metrics per language (`es`, `en`): recall@k, MRR, nDCG@10, AP@5, `doc_recall@5` |
| `generacion` | Generation metrics per language |
| `exactitud` | Correctness, scored by the LLM judge against the reference answer |
| `precision_citas` | Citation precision: share of citations that contain a gold passage |
| `cobertura_cita` | Share of answers with at least one citation that contains a gold passage |
| `abstencion_falsa` | Answerable questions where the model abstained (count / total) |
| `abstencion_correcta` | Unanswerable questions where the model abstained (count / total) |
| `costo_usd_por_consulta` | Mean cost per query in USD, split into retrieval and generation |
| `latencia_s` | Latency in seconds (p50, p95), split into retrieval and generation |
| `fallas` | Failed questions, with `atribucion`: the step blamed for the failure (the values of `falla` below) |
| `metricas_sin_puntaje` | Judge metrics with no score |
| `costo_evaluacion_corrida_usd` | Cost of evaluating the run, in USD |
| `resultados_por_consulta` | Vertex AI Search only: results returned per query (`media` mean, `cero` queries with none, `menos_de_5` queries with fewer than 5) |
| `rerank_fallido` | Queries whose reranking failed |
| `respondible` | Whether the question is answerable from the documents |
| `tipo` | In the suite detail: question type (`base`, `no_textual` non-text document, `sin_respuesta` unanswerable). In the security detail: test type (`rol` by role, `tenant` across tenants) |
| `clase` | What the model did: `responde` answered, `abstiene` abstained |
| `falla` | Empty when the question passed; otherwise the step blamed (`recuperación`, `generación`, `generación (inventa)` = answered an unanswerable question) |
| `lat_rec`, `lat_gen`, `costo_rec`, `costo_gen` | Retrieval and generation latency (s) and cost (USD) for one question |
| `citas`, `citas_con_pasaje`, `pasajes_en_contexto` | Citations in the answer, citations that contain a gold passage, share of gold passages in the context |
| `respuesta` | The generated answer, as returned |
| `opcion`, `pregunta` | In the latency detail: the option measured and the question (`<id>::<lang>`) |
| `rec`, `total` | Retrieval latency and full-answer latency (retrieval, then generation), in seconds. `rec` is empty for RetrieveAndGenerate, which returns the full answer in one call |
| `recuperacion_p50`, `total_p50`, `costo_rec_media`, `costo_gen_media` | In the latency summary, per option: retrieval and full-answer latency percentiles (also `_p95`), and the mean retrieval and generation cost per question |
| `propio_sin_rerank` | The in-house pipeline without Haiku reranking |
| `concurrencia`, `orden` | Concurrency (1) and the order in which options were called (random per question, seed 12) |
| `sistema`, `usuario` | The system tested; the simulated user (tenant and roles) |
| `resultados`, `no_autorizados` | Number of results returned; number of them the user is not allowed to see |
| `documento_prohibido` | By role: the forbidden reference document was returned. Across tenants: a result from another tenant was returned. A count in the summary |
| `ejemplo` | Up to three unauthorized results, as `<tenant>/<source>` |
| `casos`, `sistemas`, `control_sin_filtro` | Test counts by type; results per system with the filter; the same queries without the filter (the control) |
| `consultas`, `consultas_con_fuga`, `chunks_no_autorizados`, `fuga_total` | Queries, queries with leakage, unauthorized chunks, and the unauthorized chunks of all filtered systems (must be 0) |
| `resultados_media`, `resultados_min` | Mean and minimum number of results per query |
| `precios`, `paquete` | The prices the cost model uses; the size of the ingestion package |
| `ingesta_usd`, `fijo_mensual_usd`, `variable_por_consulta_usd`, `costo_mensual_usd` | One-time ingestion cost, fixed monthly cost, variable cost per query, monthly cost by query volume |
| `equilibrio_contra_propio_consultas_mes` | The lowest monthly query volume, in steps of 1,000, at which the option costs more than the in-house pipeline (`null` = not up to 5 million) |
| `fuente`, `servicio`, `modelo`, `descripcion`, `unidad` | Price catalog columns: source, service, model, description, unit (`id` is the price id and `usd` the price) |
