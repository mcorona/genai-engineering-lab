# Week 10 results (recorded evidence)

[Glossary](../../docs/glossary.md) · [Week 10 README](../README.md)

The results of week 10: text-to-SQL over the legacy schema, PDF tables, OCR, images, question routing, the
integrated assistant, its security tests and the CI calibration. Each activity has an English report (`*.md`) that
names its script and its run. The raw files next to the reports hold the per-question detail, the cached model
responses and the text each extractor recovered.

**Recorded evidence:** the CSV, JSON and TXT files are the raw outputs of the runs, kept exactly as recorded (not
edited, not translated). They were written by the scripts in `../experimentos/` named below. Their Spanish text is
model input or output: questions, answers, SQL, extracted text, script logs. The English summary of the results is in
the [week 10 README](../README.md) and in the reports: [`sql_legado.md`](sql_legado.md),
[`pdf_tablas.md`](pdf_tablas.md), [`ocr.md`](ocr.md), [`imagenes.md`](imagenes.md), [`ruteo.md`](ruteo.md),
[`asistente.md`](asistente.md), [`seguridad.md`](seguridad.md), [`ci_calibracion.md`](ci_calibracion.md) and
[`golden_validacion.md`](golden_validacion.md).

File name suffixes: `_prueba` is a pilot run on a few questions (`--limite`); `_corrida1` is the first full run, kept
as evidence after a correction (the reports explain why); a model and effort level in the name (for example
`claude-haiku-5-5_low`) mark the configuration. The console logs (`seguridad_*.txt`) include a few lines printed by
a week 8 chunking module that the script imports.

## Files

| File(s) | What it is | Written by / Read by |
|---|---|---|
| `*.md` | English reports, one per activity, plus the gold set validation | Written from the runs of the scripts each one names |
| `sql_legado_detalle_*.csv` | Legacy text-to-SQL: one row per question and variant, with the generated SQL and its outcome | `../experimentos/sql_legado.py` |
| `pdf_tablas_detalle.csv` | PDF tables: cell and row metrics per extractor and document, and recall@5 per question | `../experimentos/pdf_tablas.py` |
| `pdf_extracciones/*` | The text each extractor recovered from each PDF (`<extractor>__<document>.txt`; `original_sin_pdf` is the source text, the upper reference), and the cached Claude transcriptions (`.json`) | `../experimentos/pdf_tablas.py` |
| `ocr_detalle.csv` | OCR: character error rate and recall@5 per extractor, document and question | `../experimentos/ocr.py` |
| `ocr_extracciones/*` | The text each extractor recovered from each scan (`original_sin_escanear` is the source text), and the cached Claude transcriptions (`.json`) | `../experimentos/ocr.py` |
| `imagenes_detalle.csv` | Images: facts extracted, recall@5 and direct-answer accuracy per method | `../experimentos/imagenes.py` |
| `imagenes_extracciones/*` | The text Tesseract and Claude recovered from each image, and the cached Claude descriptions and answers (`.json`) | `../experimentos/imagenes.py` |
| `ruteo_*.json`, `ruteo_detalle_*.csv` | Question routing: cached router responses, and one row per question with the expected and the predicted route | `../experimentos/ruteo.py` |
| `asistente_cache*.json`, `asistente_detalle*.csv` | Integrated assistant: cached answers per configuration and question, and one row per question and configuration with the judge's verdict, citations, cost and latency | `../experimentos/asistente.py` |
| `seguridad_cache.json`, `seguridad_detalle.csv`, `seguridad_resumen.json` | Security: cached answers and judge verdicts; one row per case; the privilege audit, the direct statements per layer, the chain and the writes per phase | `../experimentos/seguridad.py` |
| `seguridad_*.txt` | Security: the full console output of the final run (`seguridad_salida.txt`) and of the first run (`seguridad_corrida1.txt`) | Saved from the console of `../experimentos/seguridad.py` |

## Keys

| Key | Meaning |
|---|---|
| `lang`, `idioma` | Language (`es`, `en`) |
| `pregunta` | The question |
| `variante` | Legacy SQL: the prompt variant, `copilot` (original schema, control), `legado` (legacy DDL only), `legado_dic` (legacy DDL + full data dictionary), `legado_rec` (DDL and dictionary of the retrieved tables only). Security: the answer prompt, `actual` (current) or `defensa` (with a defense) |
| `categoria` | Legacy SQL outcome: `correcta` (correct), `resultado_distinto` (different result set), `no_es_select` (not a SELECT), `error_sql` (SQL error) |
| `tablas_necesarias`, `tablas_recuperadas`, `recuperacion_completa` | Tables the question needs, tables retrieved, all needed tables retrieved |
| `documento` | The source document |
| `extractor` | The extraction method (values such as `original (sin PDF)` = the source text, without a PDF; `original (sin escanear)` = the source text, not scanned) |
| `celdas`, `presentes`, `en_su_fila`, `filas`, `filas_integras` | PDF tables: cells, cells present, cells in their row, rows, intact rows |
| `acierto_r5`, `acierto` | Hit: a top-5 chunk from the document contains the answer; for images, the hit of the measure in `medida` |
| `cer` | Character error rate |
| `medida`, `uso`, `respuesta_modelo` | Images: the measure (`recall5`, `hecho` fact, `exactitud` accuracy), how the image is used (for example `sin imagen` no image, `respuesta directa` direct answer), the model's answer |
| `esperado`, `mayoritaria`, `ok_mayoritaria`, `ok_claude` | Routing: expected route, the majority-class baseline, whether each one is right |
| `ruta` | Route: `sql`, `documental` (document), `mixta` (mixed) |
| `respaldo` | `1` if the fallback to documents ran |
| `correcta` | The LLM judge's verdict on the answer |
| `citas_doc`, `citas_doc_con_evidencia`, `cita_sql_correcta` | Document citations, document citations that contain the gold passage, correct SQL citation |
| `grupo` | Security case group: `escritura` (write attempts), `fuga_sql` (leak through SQL), `rol` (leak by role), `tenant` (leak across tenants), `inyeccion` (prompt injection), `inyeccion_literal` (injection with a literal image transcription), `escritura_posterior` (later write cases) |
| `nlq` | NLQ connection: `base` (the week 7 connection) or `endurecida` (hardened) |
| `escritura_generada`, `escritura_ejecutada`, `afirma_modificacion` | A write statement was generated; it ran without error; the answer claims a change was made |
| `chunks_no_autorizados`, `celdas_sql_no_autorizadas`, `dato_no_autorizado_en_respuesta`, `lineas_no_autorizadas_en_respuesta` | Unauthorized chunks in the context, unauthorized SQL cells, unauthorized data in the answer, unauthorized lines in the answer |
| `cifra_propia`, `cifra_otro_tenant` | The user's own tenant figure, the other tenant's figure, found in the answer |
| `expuesta`, `marcador`, `obedece_juez`, `dato_correcto` | Injection: the injected document reached the context; a marker of the instruction is in the answer; the judge says the answer obeyed; the correct figure is in the answer |
| `medio` | Injection medium: `pdf` or `imagen` (image) |
| `usuario_roles`, `usuario_tenant` | The user's roles and tenant |
| `auditoria`, `directas`, `cadena`, `escrituras_por_fase` | `seguridad_resumen.json`: privilege audit per role, direct statements per layer, the chain on one session, database writes per phase |
| `texto`, `respuesta` | Cached model output: the text, the answer |
