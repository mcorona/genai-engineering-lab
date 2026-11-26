# Week 16 data and evidence outside the data folders (Spanish data)

[Glossary](../glossary.md) · [Week 16 README](../../semana-16/README.md)

The week's Spanish data and recorded evidence that do not sit in [`resultados/`](../../semana-16/resultados/README.md) or
[`verdad/`](../../semana-16/verdad/README.md). Most of them are part of the [`legacy-schema-audit`](../../semana-16/legacy-schema-audit/README.md)
plugin: the agents and skills a model reads, the `claude plugin eval` suite, and the sample report. The plugin folders
get no README of their own: they ship to clients as they are, the plugin's guard reads every `agents/*.md`, and
`eval/generar_casos.py` rewrites every `evals/*/graders/*.md`. The rest are the minimal plugin of the activity 1 spike, the concepts of the quality evaluator,
the ground truth of the legacy screen and the security injections.

**Why it is in Spanish:** the lab measures Spanish-language systems over a Spanish legacy schema. The plugin's agent and
skill names, its deliverable names and the evaluator's labels are Spanish; their instructions are in English. The eval
suite has Spanish (`es`) and English (`en`) cases on purpose, to test the plugin in both languages. The injections and
the screen are Spanish because the legacy system is. Translating any of these files would change what was measured.

**Recorded evidence:** [`legacy-schema-audit/ejemplo/`](../../semana-16/legacy-schema-audit/ejemplo) holds the four deliverables of
the measured Sonnet run, byte for byte the same as `resultados/corrida_plugin_sonnet/auditoria/`
(`tests/test_empaquetado.py` checks it). They are kept as recorded: not edited and not translated. The English
summary is in the plugin README's [Sample report](../../semana-16/legacy-schema-audit/README.md#sample-report) section and in
[`resultados/empaquetado.md`](../../semana-16/resultados/empaquetado.md).

## Files

| File(s) | What it is | Written by / Read by |
|---|---|---|
| `legacy-schema-audit/agents/*.md` | The plugin's three subagents (`perfilador` profiler, `analista-relaciones` relationship analyst, `revisor-riesgos` risk reviewer): frontmatter with the allowed tools and model, then the instructions (in English) | Read by Claude Code; `scripts/comun.py` reads each `tools:` line as the guard's allowlist |
| `legacy-schema-audit/skills/*/SKILL.md` | The `auditar` skill (audit) and three commands that run it in one mode: `auditoria-completa` (full audit), `solo-diccionario` (data dictionary only), `solo-riesgos` (risks and the executive summary only) | Read by Claude Code |
| `legacy-schema-audit/evals/*/prompt.md` | The 10 eval cases: frontmatter (turns, timeout, allowed tools, runs) and the user's request, in Spanish or English | Written by `eval/generar_casos.py`; read by `claude plugin eval`, which `ci/eval_ci.py` runs on 5 of the cases |
| `legacy-schema-audit/evals/*/graders/*.md` | The 45 graders of the cases: `regex`, `file_exists`, `tool_used`, `tool_order` or `llm`, with their target or rubric | Written by `eval/generar_casos.py`; read by `claude plugin eval` |
| `legacy-schema-audit/evals/mocks/legacy-sql/*` | The mocked read-only SQL server: `_server.md` (an agent that plays a 3-table `ventas` schema) and `_tools.json` (its tool list) | Written by hand; read by `claude plugin eval` |
| `legacy-schema-audit/evals/.gitignore` | Keeps the eval's local outputs (`results/`, `mocks/.replay/`) out of git | Written by hand |
| `legacy-schema-audit/ejemplo/*` | The sample report: `diccionario.yaml`, `relaciones.mmd`, `riesgos.md`, `resumen.md` | Copied from the measured Sonnet run; read by clients and `tests/test_empaquetado.py` |
| `linea_base/plugin_minimo/**` | The minimal plugin of the activity 1 spike: a README, one skill (`hola-auditoria`), one subagent, hooks, two hook scripts and `bin/` | Written by hand; read by `linea_base/verificar.py` |
| `eval/conceptos.json` | For each `table.column`, a regular expression of the concept its meaning must name (Spanish or English) to count as exact | Written by hand; read by `eval/calidad.py` |
| `navegador/verdad_pantalla.json` | Ground truth of the MOV-010 legacy screen: the column each visible field writes, and the screen-only facts, each with a pattern. Fixed before any model run | Written by hand; read by `navegador/evaluar.py` |
| `seguridad/*.sql` | `inyecciones.sql` puts injected instructions in a table comment, a column comment and a view name; `limpiar_inyecciones.sql` removes them | Written by hand; applied by `seguridad/correr.py` |

## Keys

| Key | Meaning |
|---|---|
| `descripcion` | Description (of the file, or of one fact) |
| `tabla`, `columna` | Table, column of `legado` |
| `campos` | The screen's visible fields |
| `etiqueta` | The field's label on the screen |
| `hechos` | Screen-only facts the agent should report for the field, each with an `id` |
| `patron` | Regular expression that must appear in what the agent wrote |
| `todos` | Patterns that must all appear |
