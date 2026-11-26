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
| `pregunta` | The question: its text in the routing detail, its ID in the PDF and OCR detail |
| `config` | Assistant: `integrado` (integrated, routed), `integrado_sin_abstencion` (integrated, the NLQ tool cannot abstain), `solo_sql` (SQL only), `solo_docs` (documents only). Security: `integrado` or `solo_sql` |
| `tipo` | Assistant and routing: the question type, with the medium for non-text questions (`no_textual/pdf`, `no_textual/ocr`, `no_textual/imagen`). OCR: `pasaje` (a week 9 gold passage) or `respuesta` (an exact answer) |
| `variante` | Legacy SQL: the prompt variant, `copilot` (original schema, control), `legado` (legacy DDL only), `legado_dic` (legacy DDL + full data dictionary), `legado_rec` (DDL and dictionary of the retrieved tables only). Security: the answer prompt, `actual` (current) or `defensa` (with a defense) |
| `categoria`, `ok` | Legacy SQL outcome: `correcta` (correct), `resultado_distinto` (different result set), `no_es_select` (not a SELECT), `error_sql` (SQL error); `ok` is `1` when it is `correcta` |
| `tablas_necesarias`, `tablas_recuperadas`, `recuperacion_completa` | Tables the question needs, tables retrieved, all needed tables retrieved |
| `documento` | The source document |
| `extractor` | The extraction method (values such as `original (sin PDF)` = the source text, without a PDF; `original (sin escanear)` = the source text, not scanned) |
| `celdas`, `presentes`, `en_su_fila`, `filas`, `filas_integras` | PDF tables: cells, cells present, cells in their row, rows, intact rows |
| `acierto_r5`, `acierto` | Hit: a top-5 chunk from the document contains the gold passage or the exact answer; for images, the hit of the measure in `medida` |
| `cer` | Character error rate |
| `medida`, `uso`, `item`, `respuesta_modelo` | Images: the measure (`recall5`, `hecho` fact, `exactitud` accuracy), how the image is used (`sin imagen` no image, a Tesseract transcription, a Claude `descripción` description, or `respuesta directa`: the model answers from the image), the fact or question ID measured, the model's answer |
| `esperado`, `claude`, `mayoritaria`, `ok_claude`, `ok_mayoritaria` | Routing: the expected route, the route Claude chose, the majority-class baseline (always `documental`), and whether each one is right |
| `ruta` | Route: `sql`, `documental` (document), `mixta` (mixed) |
| `respaldo` | `1` if the fallback to documents ran |
| `correcta` | The LLM judge's verdict on the answer (`1` correct) |
| `costo_juez_usd` | The LLM judge's cost for the answer, in USD |
| `citas_doc`, `citas_doc_con_evidencia`, `cita_sql_correcta` | Document citations; document citations whose passage contains the gold passage or the exact answer; the answer cites `[SQL]` and the query's result matches the reference (empty when the question has no SQL) |
| `grupo` | Security case group: `escritura` (write attempts), `fuga_sql` (leak through SQL), `rol` (leak by role), `tenant` (leak across tenants), `inyeccion` (prompt injection), `inyeccion_literal` (injection with a literal image transcription), `escritura_posterior` (later write cases) |
| `nlq` | NLQ connection: `base` (the week 7 connection) or `endurecida` (hardened) |
| `escritura_generada`, `escritura_ejecutada`, `afirma_modificacion` | A write statement was generated; a write statement ran without error; the answer claims a change was made (LLM judge) |
| `sql_error`, `lee_chunks` | Security: the NLQ tool's error (`abstencion` abstention, `no_es_select` not a SELECT); `1` if the generated SQL reads the document table |
| `chunks_no_autorizados`, `celdas_sql_no_autorizadas`, `dato_no_autorizado_en_respuesta`, `lineas_no_autorizadas_en_respuesta` | Unauthorized chunks in the context, unauthorized SQL cells, unauthorized data in the answer, unauthorized lines in the answer |
| `marcadores` | Leak by role: the number of markers of the protected document's data that were searched for in the answer |
| `cifra_propia`, `cifra_otro_tenant` | The value of the user's own tenant is in the answer; the other tenant's value is in the answer and not in the context |
| `expuesta`, `marcador`, `obedece_juez`, `dato_correcto` | Injection: the injected document reached the context; a marker of the instruction is in the answer; the judge says the answer obeyed; the correct figure is in the answer |
| `medio` | Injection medium: `pdf` or `imagen` (image) |
| `usuario_roles`, `usuario_tenant` | The user's roles and tenant |
| `auditoria`, `directas`, `cadena`, `escrituras_por_fase` | `seguridad_resumen.json`: privilege audit per role, direct statements per layer, the chain on one session, database writes per phase |
| `lee`, `escribe`, `superusuario`, `crea_roles`, `crea_bd` | Privilege audit: the tables a role reads, the tables it writes, and whether it is a superuser, may create roles, may create databases |
| `filtro`, `sesion_base`, `sesion_endurecida`, `privilegios_copilot_ro`, `privilegios_copilot_nlq` | Direct statements: the outcome at each defense layer (the week 7 single-SELECT filter, the week 7 session, the hardened session, the privileges of each role): `bloqueado` (blocked, with the error), `ejecutado` (executed) or, for the filter, `pasa` (passes) |
| `texto`, `respuesta` | Cached model output: the text, the answer |
