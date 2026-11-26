# Week 16 results (recorded evidence)

[Glossary](../../docs/glossary.md) · [Week 16 README](../README.md)

The raw evidence of the `legacy-schema-audit` plugin: the baseline checks of Claude Code (activity 1), the audits run
with and without the plugin (activities 3 to 5), the `claude plugin eval` reports (activity 5), the security cases
(activity 6), the browser and computer use spikes (activities 7 and 8), the installation checks (activity 9) and the
CI summaries (activity 10). The English reports in this folder (`*.md`, one per activity) explain each set of files.

**Recorded evidence:** these files are the raw outputs of the runs: the audits the agent wrote (`diccionario.yaml`,
`relaciones.mmd`, `riesgos.md`, `resumen.md`), the session event streams, the query and block logs, the screen
captures and the evaluators' JSON. They are kept as recorded: not edited and not translated. The only changes were
redactions: secrets, the home path and the session `init` event were removed from the event streams
([`seguridad.md`](seguridad.md) explains why). Most of the Spanish text was written by the agent, because the audited
schema, its data and the requests are Spanish. The results are summarized in English in the
[week 16 README](../README.md#3-results) and in the reports listed below.

## Files

| File(s) | What it is | Written by / Read by |
|---|---|---|
| `*.md` | The English report of each activity: [`linea_base.md`](linea_base.md) (1), [`verdad.md`](verdad.md) (2), [`plugin.md`](plugin.md) (3), [`subagentes_hooks.md`](subagentes_hooks.md) (4), [`eval_plugin.md`](eval_plugin.md) (5), [`seguridad.md`](seguridad.md) (6), [`navegador.md`](navegador.md) (7), [`computer_use.md`](computer_use.md) (8), [`empaquetado.md`](empaquetado.md) (9), [`ci.md`](ci.md) (10) | People; each report links its evidence below |
| `linea_base.json` | The baseline checks of Claude Code as a plugin platform, one entry per check | `linea_base/verificar.py` |
| `headless_*.jsonl` | The `stream-json` events of the two headless runs of the minimal plugin (`skill`, `hook`) | `linea_base/verificar.py --con-modelo` |
| `corrida_*/corrida.json` | One audit run: model, turns, time, API-equivalent cost, token usage, and the run's checks | `corrida/correr.py`; read by `eval/calidad.py` |
| `corrida_*/eventos.jsonl` | The session's event stream (`stream-json`) | `corrida/correr.py` |
| `corrida_*/auditoria/*` | The audit deliverables (`diccionario.yaml`, `relaciones.mmd`, `riesgos.md`, `resumen.md`) and, where the hooks ran, the query log `bitacora.jsonl` | Written by the agent; copied by `corrida/correr.py` (the OAuth run's come from an interactive session, see [`plugin.md`](plugin.md)); read by `eval/calidad.py` and `ci/eval_ci.py` |
| `corrida_oauth/trazas_servidor.jsonl` | The week 14 MCP server's request trace for the OAuth run (no tokens recorded) | The week 14 server, in an interactive session ([`plugin.md`](plugin.md)); read by `ci/eval_ci.py` |
| `calidad.json` | Quality of each audit run against the [ground truth](../verdad/README.md): dictionary meaning, PK, FK and personal-data precision and recall, seeded risks found, SQL run again | `eval/calidad.py` |
| `plugin_eval_*.json` | The JSON reports of `claude plugin eval`: `intento1` (pass 1, stopped at the spending cap), `haiku_v1` (pass 2), `haiku` (pass 3), `haiku_02` (rerun of case 02) | `claude plugin eval`; `plugin_eval_haiku.json` is read by `ci/eval_ci.py` |
| `seguridad/*/resumen.json` | The 7 security cases of one model (`haiku`, `sonnet`), one entry per case | `seguridad/correr.py` |
| `seguridad/*/*/resultado.json` | The verdict of one security case: fingerprints, files written outside the project, calls captured by the poisoned server, criteria | `seguridad/correr.py`; read by `ci/eval_ci.py` |
| `seguridad/*/*/eventos.jsonl` | The case's event stream, redacted | `seguridad/correr.py` |
| `seguridad/*/*/bitacora.jsonl`, `seguridad/*/*/bloqueos.jsonl` | The plugin's query log and block log for the case | The plugin hooks (`bitacora.py`, `guardia.py`); copied by `seguridad/correr.py` |
| `seguridad/*/*/*.md`, `seguridad/*/*/*.yaml`, `seguridad/*/*/*.mmd`, `seguridad/haiku/5-evadir_con_bash/*.sql` | What the agent wrote in `auditoria/` during the case: deliverables, and in case 5 (Haiku) a report and a script for the DBA that it did not run | Written by the agent; copied by `seguridad/correr.py` |
| `navegador/ensayo.json` | The browser spike's rehearsal with no model: a scripted MCP client walks the screen cleanly and then as an attacker, through the plugin's guard | `navegador/ensayo.py` |
| `navegador/haiku/*` | The browser agent run: `meta.json`, `eventos.jsonl`, the page server's `solicitudes.jsonl`, the plugin's `bitacora.jsonl`, the agent's `pantalla.json` and the evaluation `evaluacion.json` | `navegador/correr.py`; `evaluacion.json` by `navegador/evaluar.py` |
| `computer_use/ensayo*.json` | The computer use rehearsal with no API call, in `docker` mode (`ensayo.json`) and `local` mode (`ensayo_local.json`), with a cost projection per model | `computer_use/ensayo.py` |
| `computer_use/*/*` | One computer use attempt (`claude-haiku-5-5`, and `claude-haiku-5-5_intento1`, the attempt with a harness bug): files such as `meta.json`, `turnos.jsonl`, `solicitudes.jsonl`, `bloqueos.jsonl`, `respuesta_final.txt`, `pantalla.json`, `evaluacion.json` | `computer_use/correr.py` |
| `computer_use/*/capturas/*.png` | The first and the last screenshot of the attempt | `computer_use/correr.py` |
| `empaquetado/instalacion_*.json` | The install-from-scratch check, from the checkout and from GitHub | `empaquetado/instalar_desde_cero.py` |
| `ci/corrida*_resumen.json` | The `resumen.json` of CI runs 2 and 3 of `eval-semana-16` | `ci/eval_ci.py`, in CI |

## Keys

| Key | Meaning |
|---|---|
| `corrida` | Run. In `calidad.json`, the run folder; in `corrida.json`, the run's metadata (`modelo`, `modo`, `prompt`, `subagentes`, turns, time, cost, `uso`) |
| `modelo` | Model |
| `modo` | Mode: `plugin` (with the plugin) or `sin-plugin` (without it, with a detailed prompt) |
| `revision` | The run's review: files present, valid YAML, dictionary scores |
| `turnos`, `turno` | Turns, turn number |
| `segundos` | Seconds |
| `costo_equivalente_usd` | API-equivalent cost in USD (the run used the Claude Code subscription) |
| `uso` | Token usage |
| `diccionario`, `riesgos` | Data dictionary, risks |
| `significado_exacto`, `significado_fallido` | Share of columns whose meaning names the expected concept; the columns whose meaning does not |
| `columnas_cubiertas`, `columnas_reales` | Columns of the ground truth that the data dictionary covers; columns in the ground truth |
| `recall_riesgos`, `sql_fallidos`, `llamadas_bd` | Share of seeded risks found; SQL blocks that failed when run again; database tool calls in the run |
| `llave_primaria`, `llave_foranea`, `datos_personales` | Primary key, foreign key, personal data (each with precision and recall) |
| `aciertos`, `predichas`, `reales` | Hits, predicted, actual |
| `hallazgos` | Findings |
| `sembrados`, `encontrados` | Seeded risks, risks found |
| `sql_reejecutado_ok` | SQL blocks that ran again without error |
| `categoria` | Risk category (see the [glossary](../../docs/glossary.md#categories-and-task-types)) |
| `caso`, `nombre` | Case number, case name |
| `huella_datos_intacta`, `huella_catalogo_intacta` | The data fingerprint and the catalog fingerprint are unchanged |
| `archivos_nuevos_fuera` | New files written outside the project's `auditoria/` folder |
| `capturas_envenenado` | Calls captured by the poisoned MCP server |
| `criterios` | Pass criteria of the case, each `true` or `false` |
| `detalle` | Detail |
| `obedecidas` | Injected instructions the agent acted on |
| `payload_citado` | Injected text the agent quoted (reported, not counted as obeyed) |
| `exige_fallido` | Required content missing from the deliverables (for example, an injected note not reported in `riesgos.md`) |
| `escrituras_intentadas`, `lecturas_fuera` | SQL that is not a `SELECT`, or shell commands with a write verb, that the agent tried; file reads outside the project |
| `exfiltracion`, `resultados_con_secreto`, `respuesta_esperada` | Calls that passed data to the poisoned MCP server; tool results that contained a secret; the final answer matched what the case expects |
| `mapeo` | Mapping of each screen field to its column |
| `etiqueta`, `esperada`, `obtenida`, `correcto` | Screen label, expected column, column given by the agent, correct |
| `hechos` | Screen-only facts, each found or not |
| `campos_correctos`, `campos_total`, `hechos_encontrados`, `hechos_total` | Fields mapped to the right column, out of the total; screen-only facts found, out of the total |
| `envios`, `intentos_de_obedecer`, `canario_obedecido`, `canario_citado`, `inyeccion_reportada` | Browser and computer use security: requests that submitted data (not `GET` or `HEAD`); actions that followed the page's injection; the canary written in the answer or the deliverable; the canary quoted only as a reported instruction; the injection was reported |
| `solo_en_pantalla` | A dictionary entry for a fact that only the screen shows (no column) |
| `entregable_valido` | The deliverable is valid |
| `metricas` | Metrics: steps, turns, cost, duration, tokens |
| `diccionario_enriquecido` | The data dictionary enriched with what the screen shows |
| `pantalla`, `campos` | Screen, fields |
| `lo_que_ve_el_usuario` | What the user sees on the screen |
| `instrucciones_en_la_pagina` | Instructions found on the page (the injection, reported as data) |
| `tope_usd` | Spending cap in USD |
| `canario` | Canary: a marker the page's injection asks the agent to write; it must not appear in the answer or the deliverable |
| `motivo_fin` | Why the run ended |
| `red_del_entorno`, `entorno_destruido` | The container's network, and whether the container was destroyed after the run |
| `metodo`, `ruta`, `estado` | HTTP method, path, status code (requests to the page server or the MCP server) |
| `latencia_s`, `bloques` | Latency in seconds, content blocks of the turn |
| `sujeto`, `motivo_auth`, `resultado` | Token subject, authentication outcome reason, result (`rechazado` = rejected) |
| `medidos`, `umbrales`, `fallas` | Measured metrics, thresholds, failures (CI) |
| `auditorias`, `puntaje`, `paso` | Audits, score, passed (CI) |
| `simulado` | Dry run (`true`) or real run |
| `fuente`, `aprobado` | Install source, passed |
| `fecha`, `checks` | Date; the checks of a baseline, an audit run or an install, each passed or not |
