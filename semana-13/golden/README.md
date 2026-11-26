# Week 13 task gold set (Spanish data)

[Glossary](../../docs/glossary.md) · [Week 13 README](../README.md)

The frozen gold set of the week 13 agent: business tasks over the legacy schema, in Spanish and in English, and the
business rules the `buscar_regla_negocio` tool returns. `construir_tareas.py` runs each reference SQL against the
database with the read-only role and writes the tasks and the manifest. The agent runners, the evaluator, the CI eval
and the MCP equivalence check read the tasks; later weeks (14, 15, 17 and 19) reuse them. Section 1 of the
[week 13 README](../README.md) gives the task counts, the validation and what the first validation changed.

**Why it is in Spanish:** the lab measures a Spanish-language agent over a Spanish legacy schema. The Spanish tasks,
the rule texts and the reasons for clarification or abstention are what the agent and the LLM judge saw; translating
them would change what was measured. `tareas_en.jsonl` holds the English version of each task, and each rule carries
its English text in `en`. The keys are explained below.

**Frozen:** `manifiesto.json` records the SHA-256 of `tareas_es.jsonl`, `tareas_en.jsonl`, `reglas_negocio.json` and
`construir_tareas.py`. Any change to them requires rebuilding the set and reviewing it in a PR.

## Files

| File(s) | What it is | Written by / Read by |
|---|---|---|
| `tareas_es.jsonl`, `tareas_en.jsonl` | The agent's tasks, one JSON object per line, in Spanish and in English. Each answerable task defines its output as named keys, each with a reference SQL and its expected result | Written by `construir_tareas.py`; read by `agente/correr.py`, `agente/evaluar.py`, `ci/eval_ci.py`, `servidor_mcp/equivalencia.py` and `tests/test_herramientas.py` |
| `reglas_negocio.json` | The business rules of the fictional company, in Spanish and English, each with how it is computed on the schema | Hashed by `construir_tareas.py`; read by `herramientas/herramientas.py` (the `buscar_regla_negocio` tool) |
| `manifiesto.json` | Manifest: task counts per language and type, the number of output keys, the data snapshot, and the SHA-256 hashes that freeze the set | Written by `construir_tareas.py`; read by `semana-19/preparar/verificar_entorno.py` |
| `construir_tareas.py` | The builder of the gold set (code, hashed in the manifest) | Run by hand with `PG_DSN` set |

## Keys

| Key | Meaning |
|---|---|
| `id` | Task ID and language (`s01-es`). The prefix gives the type: `s` simple, `r` business rule, `c` compound, `v` value trap, `a` ambiguous, `n` unanswerable. In `reglas_negocio.json`: the rule ID (`R-COB`) |
| `lang` | Language: `es` or `en` |
| `tipo` | Task type: `simple`, `regla` (business rule), `compuesta` (compound), `valores` (value trap), `ambigua` (ambiguous), `sin_respuesta` (unanswerable). Inside an output key: the result shape, `filas` (rows), `conjunto` (set), `numero` (number) or `texto` (text) |
| `tarea` | The task, as the user asks it |
| `estado_esperado` | Expected final state: `respondida` (answered), `requiere_aclaracion` (needs clarification), `abstenida` (abstained) |
| `salida` | The expected output: one entry per output key (empty for ambiguous and unanswerable tasks) |
| `descripcion` | What the output key must contain. In the manifest: a description of the set |
| `orden` | Whether row order matters when comparing results |
| `sql_ref` | The reference SQL, over the original (non-legacy) tables |
| `esperado` | The expected result of the reference SQL |
| `reglas` | IDs of the business rules the task needs. In `reglas_negocio.json`: the list of rules |
| `pasos_min`, `herramientas_min` | Minimum steps and the tools the task requires. Week 13 reports steps over the minimum; week 17's trajectory eval uses both |
| `motivo` | Why the task needs clarification or has no answer (the reference for the LLM judge) |
| `origen` | The week 7 hard-set question the task comes from (simple tasks) |
| `nombre`, `nombre_en` | Rule name in Spanish and in English |
| `es`, `en` | The rule's text in Spanish and in English |
| `fuente` | Where the rule comes from |
| `nota` | A note on where the rules come from and how they are interpreted |
| `tareas_por_idioma`, `por_tipo` | Tasks per language; tasks per type |
| `claves_de_salida` | Number of output keys across the answerable tasks |
| `datos`, `fecha_corte` | The data snapshot the expected results come from (row counts of the original tables); its cutoff date (the last date with sales) |
| `sha256` | The SHA-256 hashes that freeze the set |
| `resultados_vacios_o_cero` | Output keys whose expected result is empty or zero, listed for review because they do not discriminate (empty in this set) |
