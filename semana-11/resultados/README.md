# Week 11 results (recorded evidence)

[Glossary](../../docs/glossary.md) · [Week 11 README](../README.md)

The results of the week 11 RAG evaluation: the retrieval suite, the meta-evaluation of the generation metrics, the
generation suite, the end-to-end run with failure attribution, the sensitivity of the suites, the cost per query and
the CI calibration. Each experiment has an English report (`*.md`) that names its script and its
results files. The raw files next to the reports hold the per-question detail, the cached rankings, answers and judge
scores that the scripts reuse, and the console output of each run.

**Recorded evidence:** the CSV, JSON and TXT files are the raw outputs of the runs, kept exactly as recorded (not
edited, not translated). They were written by the scripts in `../experimentos/` and `../datasets/` named below. Their
Spanish text is model input or output: retrieved chunks, answers, judge verdicts, script logs. The English summary of
the results is in the [week 11 README](../README.md) and in the reports:
[`suite_recuperacion.md`](suite_recuperacion.md), [`meta_evaluacion.md`](meta_evaluacion.md),
[`suite_generacion.md`](suite_generacion.md), [`extremo_a_extremo.md`](extremo_a_extremo.md),
[`sensibilidad.md`](sensibilidad.md), [`costo_por_consulta.md`](costo_por_consulta.md) and
[`ci_calibracion.md`](ci_calibracion.md).

File name suffixes: `_detalle` is one row per question; `_cache` holds cached model responses or rankings, reused when
a run is repeated; `_salida` is the console output of the run; `_corrida1` is a first run kept as evidence
(the reports explain why).

## Files

| File(s) | What it is | Written by / Read by |
|---|---|---|
| `*.md` | English reports, one per experiment, plus the manual review of the reference answers ([`revision_referencias.md`](revision_referencias.md), which quotes the Spanish gold set verbatim, and its English gloss [`revision_referencias_en.md`](revision_referencias_en.md)) | Written from the runs of the scripts each one names |
| `referencias_cache.json` | The model's reference answers for the gold set, per question and language, with tokens and cost | Written and read by `../datasets/construir_eval_rag.py` |
| `suite_recuperacion_*` | Retrieval suite: rankings and RAGAS scores per configuration and question (cache), metrics per question (detail), console output | `../experimentos/suite_recuperacion.py`. The cache is also read by the generation suite, the meta-evaluation, the end-to-end run, the sensitivity run and the cost run |
| `meta_evaluacion_*` | Meta-evaluation: scores per judge, metric, question and rule-built answer variant (cache and detail), console output; the first run kept as evidence | `../experimentos/meta_evaluacion.py` |
| `contextos_generacion.json` | Generation suite: the fixed contexts per question (gold chunks plus distractors), frozen before generating | Written and read by `../experimentos/suite_generacion.py`; read by `../experimentos/sensibilidad.py` and `../ci/eval_ci.py` |
| `suite_generacion_*` | Generation suite: answers and scores per question (cache), metrics per question (detail), console output | `../experimentos/suite_generacion.py` |
| `e2e_*` | End to end: the retrieved contexts per configuration, answers and scores per configuration (`e2e_cache_<config>.json`), metrics and failure attribution per question, console output | `../experimentos/extremo_a_extremo.py` |
| `sensibilidad_*`, `contextos_generacion_rec300.json` | Sensitivity: rankings per change (cache), one generation run per variant (`sensibilidad_gen_<variant>.json`), the generation contexts rebuilt with recursive 300 chunking, console output | `../experimentos/sensibilidad.py` |
| `costo_por_consulta_*` | Cost per query: cost and latency per stage and question (cache), console output of the final run and of the first run | `../experimentos/costo_por_consulta.py` |

## Keys

| Key | Meaning |
|---|---|
| `tipo` | Question type: `base`, `no_textual` (non-text), `sin_respuesta` (unanswerable). The meta-evaluation keeps the medium: `no_textual/pdf`, `no_textual/ocr`, `no_textual/imagen` |
| `config` | Configuration: `base` (vector + filter), `adoptado` (adopted, with reranking); end to end: `adoptado_top5`, `estres_base_top3` (stress: no reranking, top 3) |
| `ragas_error`, `error` | The error raised when a RAGAS score or a judge score could not be computed |
| `rerank_fallo` | Cached retrieval: `true` if the reranking call failed |
| `costo_rerank`, `costo_gen`, `costo` | Cost of reranking, of generation, of one call, in USD |
| `latencia_gen_s` | Generation latency in seconds |
| `lat_embedding`, `lat_busqueda`, `lat_rerank`, `lat` | Cost per query cache: the latency, in seconds, of the embedding, the search, the reranking, and of each generation or judge call |
| `rerank_in`, `rerank_out`, `in`, `out`, `llamadas`, `errores` | Cost per query cache: reranking input and output tokens; input and output tokens; calls; errors |
| `respuesta` | The generated answer |
| `exactitud` | Correctness, scored by the custom LLM judge |
| `clase` | The abstention judge's class: `responde` (answers) or `abstiene` (abstains) |
| `citas`, `citas_con_pasaje` | Citations in the answer; citations to a chunk that contains a gold passage |
| `n_chunks` | Number of chunks in the fixed context |
| `n_oro` | `contextos_generacion.json`: the number of gold chunks in the fixed context (0 for unanswerable questions) |
| `recall_contexto` | Share of the gold passages that reached the context |
| `falla`, `atribucion` | The answer failed (judged wrong, or no abstention on an unanswerable question); the stage the failure is attributed to, `recuperación` (retrieval: a gold passage did not reach the context) or `generación` (generation) |
| `juez` | Judge model: `haiku` or `sonnet` |
| `metrica` | Metric: `faithfulness`, `answer_relevancy`, `exactitud_propia` (the custom correctness judge) |
| `variante` | Meta-evaluation answer variant: `control`, `cifra_cambiada` (changed figure), `inventada` (invented claim), `fuera_de_tema` (off-topic), `evasiva` (evasive) |
| `valor` | The score |
| `chunks`, `ranking`, `top5` | Cached retrieval: the context chunks, the full ranking, the top 5; each chunk is a document name and its text |
| `texto` | Cached model output text |
