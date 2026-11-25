# Language audit

This audit lists every tracked file that a person can read and assigns it to one of five classes. The class decides
what happens to the file's language. The goal is a repository that reads in professional US English for clients,
recruiters and engineers, **without changing any figure, result, gold set or recorded model output**.

Snapshot: `main` at `6c58a65` (2026-11-24). Scope: all 1,815 files in `git ls-files`, except the 2,921 vendored files under `vendor/` (`semana-19/guardrail/vendor/`
and `semana-19/infra/loader/vendor/`). There is no `node_modules/` in the repository.

Method: [`language_audit.py`](language_audit.py) classifies each file by its role (path and type), then measures its
Spanish. It is offline and deterministic: no models, no cloud, $0. Code spans, URLs, paths and identifiers are removed
before measuring. A line counts as Spanish when it has at least two Spanish function words (*el*, *que*, *para*…)
and more Spanish than English function words. For Python, only comments and docstrings count as prose. Console
messages and help text count separately (class D). Other string literals (prompts, SQL, test data, expected outputs)
are behavior, not prose, and are not counted.

```bash
python3 docs/language_audit.py                                   # summary per class and week
python3 docs/language_audit.py --markdown docs/language-audit.md # regenerate the inventory below and the TSV
python3 docs/language_audit.py --check docs/language-audit.md    # exit 1 if the inventory is out of date
```

## Summary

1. **Most of the prose is already in English.** 471 files are class A. Of those, 30 still contain Spanish prose,
   with 145 Spanish lines in total, and 13 class D scripts add 48 Spanish comment lines. Three files hold half of it
   (the two results files below and `.github/workflows/eval-semana-19.yml`). Most of the rest are short: Spanish
   quoted on purpose (a gold-set question inside an English sentence) or a Spanish comment in code.
2. **The three files flagged before the audit:**
   - [`semana-03/reglas_legado.md`](../semana-03/reglas_legado.md) is **class B, not A**. It is a prompt:
     `semana-03/evaluar_sql.py` (line 135) appends it to the system prompt, and `semana-03/rag_reglas.py` (line 13)
     retrieves its rules. Translating it would change the measured experiment. The week 3 README already says it is
     in Spanish on purpose. It stays.
   - [`semana-11/resultados/revision_referencias.md`](../semana-11/resultados/revision_referencias.md) is **class A**.
     Its prose is already English (27 English lines). Its 30 Spanish lines are table cells that quote the Spanish
     gold set (`semana-11/datasets/eval_rag_es.jsonl`) word for word: question, passage and reference. The quotes
     stay as they are. Step 3 adds an English gloss for each quoted row, so the verdicts can be checked without
     reading Spanish.
   - [`semana-19/resultados/cotizacion.md`](../semana-19/resultados/cotizacion.md) is **class A**, with 25 Spanish
     lines. Its per-item tables are written by `semana-19/costos/modelo.py`, which holds the Spanish row labels
     (*IPv4 pública en uso*, *por hora*). Step 3 translates the labels in the generator, regenerates the file offline
     ($0, deterministic) and compares every figure with the current file.
3. **Files that must not change, even for a comment.** Their SHA-256 is stored in a manifest and checked by tests.
   Any byte change breaks the freeze:
   - `semana-13/golden/construir_tareas.py` (frozen by `semana-13/golden/manifiesto.json`, which
     `semana-17/tests/test_trayectorias.py` checks): 15 Spanish comment lines;
   - `semana-16/verdad/construir.py` (frozen by `semana-16/verdad/manifiesto.json`, checked by
     `semana-16/tests/test_verdad.py`): 14 Spanish comment lines.

   Both stay in Spanish and are listed as exceptions below.
4. **Text that looks like documentation but is behavior.** It stays as it is:
   - the docstrings of the LangChain `@tool` functions in `semana-17/comparacion/agente_langgraph.py` (LangChain
     sends them to the model as tool descriptions);
   - tool descriptions in code strings and in `semana-19/gateway/herramientas.json`;
   - the plugin's skills and subagents (`skills/*/SKILL.md`, `agents/*.md`), which are prompts. The main plugin's
     prompts are already in English. Only the week 16 spike (`semana-16/linea_base/plugin_minimo/`) has Spanish
     prompts, and that spike is a recorded baseline.
5. **One workflow is still in Spanish.** `.github/workflows/eval-semana-19.yml` has Spanish comments and step names
   (for example *Instalar Terraform 1.17.2*). The step names show in the Actions tab of every pull request.
6. **The operator interface is mostly Spanish.** 136 of the 180 distinct command-line flags are Spanish (`--si`,
   `--salida`, `--tope-usd`…), in 102 scripts, and 73 of them appear in the documentation. 43 files print Spanish
   console messages. Most of them are week 19 and 20 operations scripts (`desplegar.sh`, `destruir.sh`, the eval and
   cost scripts).
7. **Names stay.** 165 of 279 folders and 1,456 of 1,815 file names contain a Spanish word. 393 code files
   use Spanish identifiers (2,596 distinct names). They are class E: they stay, and the glossary (step 2) explains them.

## The five classes

| Class | What it covers | What happens to it |
|---|---|---|
| **A. Documentation and prose** | READMEs, plans (`FasXSemaNN.md`), ADRs, explanatory `resultados/*.md`, `SECURITY.md`, `docs/`, workflow comments and step names, configuration comments, and the comments and docstrings of code | Translated into US English (step 3). The logic does not change. Each translated file keeps the same numbers (figures test, step 5) |
| **B. Spanish evaluation data** | Corpora, sources, gold sets (ES and EN), prompts and prompt templates, rubrics, attack and injection cases, the legacy schema and its seed data, ground truth, training pairs | Not translated. Each data folder gets an English README that says what the data is and why it is in Spanish (step 4) |
| **C. Recorded evidence** | Model outputs, runs, JSON and JSONL logs, CSV results, captured screens, agent-generated reports (the plugin's audits, generated dictionaries), CI snapshots, the week 12 ingestion package | Not changed. It gets an English summary next to it and an English schema of its Spanish keys, such as `exito` = success and `quedan` = remaining (step 4) |
| **D. Operator interface** | Scripts a person runs: shell scripts, Python entry points, their flags, help text and console messages | English aliases that keep the Spanish names working, and English (or bilingual) messages where the message is not part of recorded evidence (step 4) |
| **E. Names and identifiers** | Folder and file names (`semana-NN`, `resultados/`, `herramientas/`), function and variable names, JSON keys of configuration files, stack names (`semana19-*`) | They stay for now. The glossary documents them (step 2) |
| **–** | No human-readable text: an icon, certificates, lock files | Nothing |

Rules the classifier applies, in order:

1. Python and shell files are code wherever they live. They are **D** when a person runs them (argparse,
   `sys.argv` or a `__main__` block, and every shell script), and **A** otherwise (modules and tests). Their comments
   and docstrings are A text in both cases, their messages and flags are D, and their identifiers are E.
2. Files under a data folder (`corpus/`, `corpus_beta/`, `fuentes/`, `golden/`, `datasets/`, `prompts/`, `rubricas/`,
   `legado/`, `verdad/`, `escaneos/`, `pdf/`, `imagenes/`, `ataques/`, `kb_envenenados/`, `data/`, `loader/`, `mocks/`),
   the plugin's eval cases, prompts read by a model, and a short list of single files (the schemas, seeds and
   sealed cases) are **B**.
3. Files under `resultados/`, `corridas/`, `baseline/`, `snapshots/`, `paquete/`, `ejemplo/` and the training
   outputs are **C**. The exception is a Markdown file directly in `resultados/`: it is an explanatory report, so it is
   **A**. When a script in the same week names it, the inventory says so (`named in`), because that script may write it.
   Step 3 checks each one: a generated file is translated in its generator and regenerated offline, not by hand.
4. Any other JSON, JSONL, CSV or text file is configuration. It is **E** when its keys are Spanish, and **A** otherwise.
5. Everything else (Markdown, YAML, Terraform, SQL outside data folders, Mermaid, SVG, HTML, notebooks) is **A**.

## Class D: proposed English aliases

These are proposals. Step 4 settles each name after reading the script's help text, and it changes no
behavior.

**Flags.** Each Spanish flag gets an English option string on the same `add_argument` call:
`add_argument("--si", "--yes", dest="si", ...)`. The destination keeps its name, so the code, the tests and every
command recorded in the logs keep working. `--help` shows both. The 73 Spanish flags that appear in the documentation
come first:

| Spanish | English | Spanish | English | Spanish | English |
|---|---|---|---|---|---|
| `--si` | `--yes` | `--borrar` | `--delete` | `--modelo` | `--model` |
| `--todo` | `--all` | `--simular` | `--simulate` | `--transporte` | `--transport` |
| `--confirmar` | `--confirm` | `--detener` | `--stop` | `--con-modelo` | `--with-model` |
| `--confirmo-gasto` | `--confirm-spend` | `--nombre` | `--name` | `--reglas` | `--rules` |
| `--solo` | `--only` | `--presupuesto` | `--budget` | `--reiniciar` | `--restart` |
| `--modo` | `--mode` | `--revisar` | `--review` | `--muestreo` | `--sampling` |
| `--reevaluar` | `--rescore` | `--esquema` | `--schema` | `--sin-historial` | `--no-history` |
| `--usuario` | `--user` | `--trazas` | `--traces` | `--emisor` | `--issuer` |
| `--pesos` | `--weights` | `--tope` | `--cap` | `--estado` | `--status` |
| `--reproduccion` | `--replay` | `--precio-in` | `--price-in` | `--precio-out` | `--price-out` |
| `--limite` | `--limit` | `--actualizar-base` | `--update-baseline` | `--validar` | `--validate` |
| `--citas` | `--citations` | `--calibrar` | `--calibrate` | `--reanudar` | `--resume` |
| `--tope-usd` | `--max-usd` | `--sin-subagentes` | `--no-subagents` | `--tareas` | `--tasks` |
| `--dia` | `--day` | `--antes` | `--before` | `--despues` | `--after` |
| `--verificar` | `--verify` | `--perfil` | `--profile` | `--inventario` | `--inventory` |
| `--comparar` | `--compare` | `--local-modelo` | `--local-model` | `--api-modelo` | `--api-model` |
| `--archivo` | `--file` | `--modelos` | `--models` | `--paralelo` | `--parallel` |
| `--puerto` | `--port` | `--solo-compras` | `--purchases-only` | `--inyectar` | `--inject` |
| `--datos` | `--data` | `--caso` | `--case` | `--escribir` | `--write` |
| `--obediente` | `--compliant` | `--fundamentacion` | `--grounding` | `--reglas-finales` | `--final-rules` |
| `--degradar` | `--degrade` | `--repeticiones` | `--repetitions` | `--dias` | `--days` |
| `--demostrar` | `--demo` | `--secretos` | `--secrets` | `--salida` | `--output` |
| `--como` | `--as` | `--revelar` | `--reveal` | `--solo-actividad7` | `--activity7-only` |
| `--informe` | `--report` | `--limpiar` | `--clean` | `--via`, `--temp-api` | unchanged |

The other 63 Spanish flags are not documented. They get aliases with the same pattern when step 4 touches their
script. The full list per script is in the TSV (`es_flags` column).

**Shell scripts.** An English wrapper next to each Spanish script runs the original with the same arguments
(`exec "$(dirname "$0")/desplegar.sh" "$@"`). The original keeps its name, because recorded logs and the plans cite it:

| Script | English wrapper |
|---|---|
| `semana-19/infra/desplegar.sh` | `deploy.sh` |
| `semana-19/infra/destruir.sh` | `destroy.sh` |
| `semana-14/auth/arrancar.sh`, `semana-16/computer_use/arrancar.sh`, `semana-17/observabilidad/arrancar.sh`, `semana-18/legacybridge/arrancar.sh` | `start.sh` |
| `semana-15/linea_base/preparar.sh` | `setup.sh` |
| `semana-17/preparar/jalar_imagenes.sh` | `pull_images.sh` |
| `semana-12/infra/aws_crear.sh`, `aws_borrar.sh`, `aws_kb_crear.sh` | `aws_create.sh`, `aws_delete.sh`, `aws_kb_create.sh` |
| `semana-12/infra/gcp_crear.sh`, `gcp_borrar.sh`, `gcp_bucket_crear.sh` | `gcp_create.sh`, `gcp_delete.sh`, `gcp_bucket_create.sh` |
| `semana-12/infra/costo_real.sh`, `inventario.sh`, `revisar_secretos.sh`, `github_entorno.sh` | `actual_cost.sh`, `inventory.sh`, `check_secrets.sh`, `github_environment.sh` |

**Console messages.** Messages for people become English. A message stays as it is when recorded evidence contains
it or a test asserts it. Machine-readable outputs keep their Spanish keys and values, because the recorded
evidence and the tests depend on them:

- `"quedan": "nada"` / `"revisar"` (`semana-19/infra/inventario.py`, `semana-15/agentcore/infra.py`,
  `semana-19/eval/costo_real.py`). Four recorded files contain it (`semana-19/resultados/inventario_final.json`,
  `inventario_mac.json`, `agentes/inventario_actividad7.json`, `eval_aws/cost_explorer.json`).
  `semana-19/tests/test_infra_cdk.py` (line 1069) and `semana-19/tests/test_costo_real.py` (line 38) assert it, and
  the exit code of `inventario.py` depends on it. Proposal: the key stays, an English line on stderr says
  `remaining: none` (or `remaining: review`), and the glossary maps `quedan` = remaining, `nada` = none,
  `revisar` = review.
- Stack and resource names (`semana19-*`, `semana20-*`) are names of deployed resources. They appear in recorded
  inventories, cost records and IAM policies. They stay (class E).

## Class E: names that stay

| Kind | Spanish | Total |
|---|---|---|
| Folders (`semana-NN`, `resultados/`, `herramientas/`…) | 165 | 279 |
| File names | 1,456 | 1,815 |
| Code files with Spanish identifiers | 393 | — |
| Distinct Spanish identifiers (functions, variables, arguments) | 2,596 | — |
| Configuration files whose Spanish is only in their keys | 13 | — |

Renaming identifiers is out of scope: it would touch the logic of 393 files and the keys that recorded evidence and
gold sets use. The glossary explains the names a reader sees.

## Renaming `semana-NN` to `week-NN`: impact

| What | Measure |
|---|---|
| Occurrences of `semana-NN` in tracked files | 1,929 in 356 files |
| … inside recorded evidence (class C) | 428 in 35 files. They cannot be edited, so they would point to paths that no longer exist |
| … inside Spanish evaluation data and gold sets (class B) | 156 in 7 files. Example: the `origen` field of `semana-11/datasets/eval_rag_es.jsonl` and `eval_rag_en.jsonl` (75 each) |
| … inside frozen files (SHA-256 stored in a manifest and checked by a test) | 165 in 7 files (5 of them are also class B): `semana-11/datasets/eval_rag_es.jsonl` and `eval_rag_en.jsonl` (frozen by `semana-12/ingesta/paquete/manifiesto.json`), `semana-13/golden/construir_tareas.py`, `semana-16/verdad/construir.py`, `etiquetas.json`, `riesgos.json`, `riesgos.sql` (frozen by `semana-16/verdad/manifiesto.json`). Editing any of them breaks its hash |
| … in Python code outside tests | 484 in 167 files (paths such as `ROOT / "semana-05"`) |
| … in tests | 92 in 30 files |
| … in workflows | 257 in 16 files. Every workflow filters on `semana-NN/**`, and the required `regresion` check lists every top-level path so that it always reports |
| Relative Markdown links | 115 |
| External links that would break | GitHub does not redirect a renamed folder, so every `github.com/mcorona/genai-engineering-lab/tree/main/semana-NN/…` and `blob/main/semana-NN/…` link from outside returns 404: LinkedIn posts, the demo video, CVs. The repository cannot count these. Inside the repository: the plugin's `homepage` in `.claude-plugin/marketplace.json` |
| Plugin installs | The marketplace entry's `source` is `./semana-16/legacy-schema-audit`, and the install command in two READMEs is `--sparse .claude-plugin semana-16/legacy-schema-audit`. A client who installed the plugin has a sparse checkout of a folder that would no longer exist |
| History | `git log -- semana-19/` stops at the rename. `git log --follow` works for one file at a time |
| Deployed resources | None change: stack names are `semana19-*` (no hyphen) and do not depend on folder names. The CDK snapshot tests contain no `semana-NN` path |

### Options

1. **Do not rename. Add an English index.** The root README gets a "Weeks at a glance" table (week, folder, topic,
   key result, link), the glossary says `semana` = week, and each week's README starts with its English title.
   Nothing that is measured or recorded changes.
2. **Rename everything in one PR.** That PR has to choose between two bad outcomes. It can leave 595 occurrences
   (in recorded evidence, gold sets and frozen files) pointing to folders that no longer exist. Or it
   can edit gold sets, recorded outputs and frozen files, which this work forbids. On top of that, it breaks every
   external link and the plugin's install path.
3. **Other: symbolic links `week-NN` → `semana-NN`.** GitHub shows a symbolic link as a one-line file, not as a folder,
   so a reader who clicks `week-19` sees the text `semana-19`. It adds confusion and fixes nothing.

**Recommendation: option 1.** The rename would cost exactly what this work protects, the ability to check every
figure against its evidence. In return it would only change a folder label that an index and the glossary already
explain. If a rename is still wanted later, the right time is a new major version of the lab whose evidence is
recorded under the new paths from the start.

## Exceptions (Spanish that stays in class A files)

Step 5's language test reads this list. Each entry has its reason:

| File | Reason |
|---|---|
| `semana-13/golden/construir_tareas.py` | Frozen: SHA-256 in `semana-13/golden/manifiesto.json`, checked by `semana-17/tests/test_trayectorias.py` |
| `semana-16/verdad/construir.py` | Frozen: SHA-256 in `semana-16/verdad/manifiesto.json`, checked by `semana-16/tests/test_verdad.py` |
| `semana-17/comparacion/agente_langgraph.py` (tool docstrings only) | Behavior: LangChain sends the docstrings to the model as tool descriptions |
| `semana-11/resultados/revision_referencias.md` (quoted cells only) | Verbatim quotes of the Spanish gold set, with an English gloss |
| Quoted Spanish questions and answers inside English sentences (any results file) | Verbatim quotes of B data or C evidence, marked with quotation marks |

## Inventory

<!-- BEGIN GENERATED INVENTORY -->

Generated by `python3 docs/language_audit.py --markdown docs/language-audit.md`. Do not edit by hand. Every file, one per row: [language-audit-files.tsv](language-audit-files.tsv).

### Files per class and week

| Class | root | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 | Total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 24 | 7 | 6 | 3 | 2 | 1 | 1 | 5 | 10 | 12 | 10 | 10 | 11 | 27 | 38 | 50 | 36 | 63 | 8 | 139 | 8 | **471** |
| B | 0 | 1 | 2 | 7 | 3 | 5 | 2 | 10 | 26 | 19 | 31 | 2 | 0 | 6 | 1 | 0 | 76 | 2 | 1 | 7 | 0 | **201** |
| C | 0 | 4 | 19 | 19 | 10 | 1 | 3 | 32 | 0 | 6 | 63 | 28 | 435 | 33 | 8 | 20 | 150 | 44 | 0 | 48 | 5 | **928** |
| D | 0 | 2 | 2 | 3 | 3 | 1 | 1 | 3 | 7 | 7 | 10 | 9 | 22 | 10 | 6 | 16 | 21 | 32 | 4 | 32 | 5 | **196** |
| E | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 2 | 0 | 1 | 3 | 0 | 4 | 1 | **13** |
| - | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 3 | 0 | **6** |
| All | 26 | 14 | 29 | 32 | 18 | 8 | 7 | 51 | 43 | 44 | 114 | 49 | 468 | 77 | 55 | 86 | 285 | 144 | 13 | 233 | 19 | **1815** |

### Files with Spanish text, per class and week

Spanish prose lines, Spanish console messages or Spanish JSON/CSV keys. For B and C this is expected.

| Class | root | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 | Total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 | 1 | 0 | 1 | 0 | 3 | 4 | 5 | 6 | 0 | 0 | 19 | 1 | **45** |
| B | 0 | 0 | 1 | 7 | 3 | 5 | 2 | 9 | 26 | 19 | 15 | 2 | 0 | 6 | 0 | 0 | 16 | 2 | 1 | 5 | 0 | **119** |
| C | 0 | 0 | 12 | 19 | 10 | 1 | 3 | 32 | 0 | 6 | 62 | 26 | 243 | 32 | 8 | 20 | 99 | 38 | 0 | 45 | 5 | **661** |
| D | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 2 | 2 | 2 | 1 | 0 | 2 | 0 | 0 | 23 | 4 | **37** |
| E | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 2 | 0 | 1 | 3 | 0 | 4 | 1 | **13** |

### Class A and D files with Spanish prose (comments, docstrings, documentation)

| File | Class | Spanish lines | English lines | Note | First Spanish line |
|---|---|---|---|---|---|
| `semana-11/resultados/revision_referencias.md` | A | 30 | 27 |  | ¿Quién fue la responsable del inventario físico del CEDIS Norte? |
| `semana-19/resultados/cotizacion.md` | A | 25 | 52 |  | IPv4 pública en uso |
| `.github/workflows/eval-semana-19.yml` | A | 18 | 0 |  | Semana 19 (LLMOps y producción en AWS, preparación y línea   Sin AWS ($0): el verificador de entorno |
| `semana-13/golden/construir_tareas.py` | D | 15 | 0 | frozen: stays | Semana 13, actividad 1: golden set de tareas del agente   sobre el flujo de |
| `semana-16/verdad/construir.py` | D | 14 | 0 | frozen: stays | trae SET y GRANT que sqlglot no modela |
| `semana-14/auth/realm/legacybridge-realm.json` | A | 10 | 0 |  | Lectura del esquema legado básico (almmst, artmst sin costo ni proveedor, exidet, artnot) |
| `semana-19/resultados/base.md` | A | 8 | 98 |  | ### Decisiones de cierre de la actividad 3 |
| `.gitignore` | A | 7 | 2 |  | Semana 1: respaldos locales y dataset descargable |
| `semana-19/costos/modelo.py` | D | 7 | 15 |  | para la estimación de la actividad 3 |
| `semana-19/spike/terraform/main.tf` | A | 6 | 0 |  | el bucket de logs no se replica entre regiones; prod lo decide el ADR |
| `semana-19/resultados/eval_aws.md` | A | 5 | 57 |  | el agente propuso la orden |
| `semana-08/precios_embeddings.json` | A | 3 | 0 |  | Precios de embeddings por millón de tokens de entrada, en   'fuente' indica de dónde salió cada cifr |
| `semana-15/tests/test_eval.py` | A | 3 | 5 |  | Caso de shadowing:   (fuera de la allowlist) publica su propio   A través de la pasarela |
| `semana-19/tests/test_infra_cdk.py` | A | 3 | 61 |  | ---------------------------------------------------------------- cifrado y un rol por función (plan, |
| `semana-19/tests/test_preparacion.py` | A | 3 | 4 |  | ---------- presupuesto (simulación) ---------- |
| `semana-15/tests/test_agentcore.py` | A | 2 | 6 |  | Lo que el agente lee al resolver una tarea tiene que venir en el zip (en AgentCore no hay |
| `semana-16/linea_base/.claude-plugin/marketplace.json` | A | 2 | 0 |  | Plugin mínimo de la semana 16 (spike) |
| `semana-16/resultados/seguridad.md` | A | 2 | 37 |  | - **Data fixes go to the   Case 3, Sonnet: "El acceso a legado es de solo lectura (rol   Tiene que |
| `semana-19/infra/cdk/app.py` | D | 2 | 238 |  | Techo de los roles de datos: lo que la KB   y el cargador   Cada statement |
| `semana-19/infra/destruir.sh` | D | 2 | 25 |  | --si --todo     also deletes   (budget, action, roles, |
| `semana-19/resultados/aip_c01.md` | A | 2 | 121 |  | KMS pricing doc (no es artículo del catálogo) |
| `semana-19/spike/terraform/ia.tf` | A | 2 | 0 |  | Knowledge Base (diccionario de datos) en S3 Vectors con Titan Text Embeddings V2, y AgentCore |
| `semana-19/tests/test_costos.py` | A | 2 | 5 |  | Solo la instancia de RDS cambia:   USD por hora, 24 h por día, 30 |
| `semana-07/README.md` | A | 1 | 91 |  | -  : "¿Y cuántas unidades vendieron en total en agosto de 2026?" became "¿Y cuántas unidades de esos |
| `semana-09/resultados/reescritura.md` | A | 1 | 17 |  | - ES  : the original hits (1) and the rewrite misses   Original: "¿Y cada cuánto se cuentan los SKUs |
| `semana-11/ci/eval_ci.py` | D | 1 | 25 |  | answer relevancy de RAGAS con los embeddings de OpenAI |
| `semana-11/experimentos/verificar_ragas.py` | D | 1 | 12 |  | -   "45 días" instead of "30 días" (faithfulness must drop); |
| `semana-12/evaluacion/seguridad.py` | D | 1 | 18 |  | noqa: E402  (helpers de Bedrock y Vertex, golden y asistente) |
| `semana-13/agente/correr.py` | D | 1 | 6 |  | python   --corrida piloto --tareas s03 r02 --idiomas es en --esfuerzo low |
| `semana-13/herramientas/herramientas.py` | A | 1 | 21 |  | Definiciones de herramientas en el formato de la API de Anthropic (name, description, |
| `semana-14/linea_base/verificar_sdk.py` | D | 1 | 10 |  | Salida tipada de la herramienta de prueba (a nivel de módulo: el SDK resuelve las anotaciones por |
| `semana-14/servidor/oauth.py` | A | 1 | 29 |  | un ID token o un refresh token no son access tokens |
| `semana-15/agentcore/requisitos_runtime.txt` | A | 1 | 0 |  | # Dependencias del paquete CodeZip (ARM64, Python   las mismas versiones que el entorno   de la sema |
| `semana-16/linea_base/plugin_minimo/hooks/hooks.json` | A | 1 | 0 |  | echo   modo solo lectura; escrituras solo en |
| `semana-16/tests/test_eval_plugin.py` | A | 1 | 2 |  | Las corridas de las actividades 3 y 4 son la línea base del evaluador: si cambia, revisa el |
| `semana-16/tests/test_hooks_auditoria.py` | A | 1 | 9 |  | Con     en CI) o, si no hay, con un rol de solo lectura creado para la |
| `semana-16/tests/test_plugin_auditoria.py` | A | 1 | 3 |  | Si la guardia fallara, la transacción READ ONLY sigue impidiendo escribir (segunda |
| `semana-19/Fas5Sema19.md` | A | 1 | 442 |  | PR "Semana 19: plan y preparación" |
| `semana-19/agentes/comparar.py` | D | 1 | 47 |  | --camino directo --si |
| `semana-19/eval/costo_real.py` | D | 1 | 55 |  | --hasta   --si |
| `semana-19/infra/loader/handler.py` | A | 1 | 32 |  | secuencias de las columnas SERIAL, insertadas con id explícito |
| `semana-19/seguridad/verificar_desplegado.py` | D | 1 | 40 |  | uv run --group semana19 python   [--perfil           [--desde   [--salida |
| `semana-19/spike/cdk/app_ia.py` | A | 1 | 1 |  | El L2 alpha de KB solo acepta   (no S3 Vectors): se mide, no se |

### Files with Spanish console messages

| File | Class | Spanish messages |
|---|---|---|
| `semana-19/infra/destruir.sh` | D | 35 |
| `semana-19/infra/desplegar.sh` | D | 21 |
| `semana-20/linea_base/corrida.py` | D | 11 |
| `semana-19/eval/eval_aws.py` | D | 8 |
| `semana-20/atribucion/corrida.py` | D | 8 |
| `semana-19/agentes/comparar.py` | D | 7 |
| `semana-19/eval/juez_bedrock.py` | D | 7 |
| `semana-19/eval/costo_real.py` | D | 6 |
| `semana-19/seguridad/envenenamiento.py` | D | 4 |
| `semana-19/seguridad/prueba_accion_presupuesto.py` | D | 4 |
| `semana-20/preparar/verificar_entorno.py` | D | 4 |
| `semana-19/costos/costo_semana.py` | D | 3 |
| `semana-19/infra/inventario.py` | D | 3 |
| `semana-19/infra/presupuesto.py` | D | 3 |
| `semana-19/preparar/verificar_entorno.py` | D | 3 |
| `semana-19/seguridad/costo_actividad9.py` | D | 3 |
| `semana-19/tests/test_agentes_comparar.py` | A | 3 |
| `semana-13/golden/construir_tareas.py` | D | 2 |
| `semana-19/eval/aprobacion_e2e.py` | D | 2 |
| `semana-19/guardrail/prueba_viva.py` | D | 2 |
| `semana-19/tests/test_agente_handler.py` | A | 2 |
| `semana-09/experimentos/multitenant.py` | D | 1 |
| `semana-12/infra/precios.py` | D | 1 |
| `semana-13/tests/conftest.py` | A | 1 |
| `semana-13/tests/test_mcp.py` | A | 1 |
| `semana-14/tests/conftest.py` | A | 1 |
| `semana-14/tests/test_auth.py` | A | 1 |
| `semana-15/tests/conftest.py` | A | 1 |
| `semana-15/tests/test_agentcore.py` | A | 1 |
| `semana-15/tests/test_arnes.py` | A | 1 |
| `semana-16/eval/calidad.py` | D | 1 |
| `semana-19/consultas/worker.py` | A | 1 |
| `semana-19/infra/usuarios.py` | D | 1 |
| `semana-19/infra/vaciar_bootstrap.py` | D | 1 |
| `semana-19/infra/vaciar_datos.py` | D | 1 |
| `semana-19/infra/vaciar_eval.py` | D | 1 |
| `semana-19/seguridad/supresiones.py` | D | 1 |
| `semana-19/tests/test_agente_presupuesto.py` | A | 1 |
| `semana-19/tests/test_aprobacion_e2e.py` | A | 1 |
| `semana-19/tests/test_eval_aws.py` | A | 1 |
| `semana-19/tests/test_juez_bedrock.py` | A | 1 |
| `semana-20/linea_base/precios.py` | D | 1 |
| `semana-20/tests/test_linea_base.py` | A | 1 |

### File list per week

Folders with more than 12 files of one class are collapsed to one line; the TSV lists each file.

<details><summary><b>Repository root</b>: 26 files (A: 24, -: 2)</summary>

**A: documentation and prose** (24)

- `.gitignore`: es prose: 7
- `.mcp.json`: es keys: 1
- `LICENSE`
- `README.md`
- `SECURITY.md`
- `pyproject.toml`
- `.claude-plugin/marketplace.json`
- `.github/workflows/` (16 files; 1 with Spanish text)
- `docs/exit-criteria.md`

**-: no human-readable text** (2)

- `.python-version`
- `uv.lock`

</details>

<details><summary><b>Week 1 (`semana-01/`)</b>: 14 files (A: 7, B: 1, C: 4, D: 2)</summary>

**A: documentation and prose** (7)

- `semana-01/README.md`
- `semana-01/attention_mlx.py`
- `semana-01/bigram.py`
- `semana-01/bigram_grad.py`
- `semana-01/bigram_mlx.py`
- `semana-01/practica_kv_cache.py`
- `semana-01/train_minigpt_mlx.py`

**B: Spanish evaluation data** (1)

- `semana-01/names.txt`

**C: recorded evidence** (4)

- `semana-01/perdidas.csv`
- `semana-01/perdidas_n128_lr1e-3.csv`
- `semana-01/perdidas_n128_lr3e-3.csv`
- `semana-01/perdidas_n64.csv`

**D: operator interface** (2)

- `semana-01/get_data.sh`
- `semana-01/minigpt_mlx.py`

</details>

<details><summary><b>Week 2 (`semana-02/`)</b>: 29 files (A: 6, B: 2, C: 19, D: 2)</summary>

**A: documentation and prose** (6)

- `semana-02/README.md`
- `semana-02/entregable_semana2.ipynb`
- `semana-02/entropia_por_token.py`
- `semana-02/logprobs_mlx.py`
- `semana-02/logprobs_temperaturas.py`
- `semana-02/practica_tokens.py`

**B: Spanish evaluation data** (2)

- `semana-02/texto_en.txt`
- `semana-02/texto_es.txt`: es prose: 5

**C: recorded evidence** (19)

- `semana-02/entropia_multisemilla.csv`: es prose: 59; es keys: 3
- `semana-02/entropia_por_token.csv`: es keys: 1
- `semana-02/logprobs_distribucion.csv`
- `semana-02/variabilidad.png`
- `semana-02/variabilidad_entregable.png`
- `semana-02/variabilidad_respuestas.csv`: es prose: 313; es keys: 2
- `semana-02/variabilidad_resumen.csv`: es keys: 1
- `semana-02/corridas/run1/variabilidad.png`
- `semana-02/corridas/run1/variabilidad_respuestas.csv`: es prose: 299; es keys: 2
- `semana-02/corridas/run1/variabilidad_resumen.csv`: es keys: 1
- `semana-02/corridas/run2/variabilidad.png`
- `semana-02/corridas/run2/variabilidad_respuestas.csv`: es prose: 301; es keys: 2
- `semana-02/corridas/run2/variabilidad_resumen.csv`: es keys: 1
- `semana-02/corridas/run3/variabilidad.png`
- `semana-02/corridas/run3/variabilidad_respuestas.csv`: es prose: 313; es keys: 2
- `semana-02/corridas/run3/variabilidad_resumen.csv`: es keys: 1
- `semana-02/resultados-n5/variabilidad.png`
- `semana-02/resultados-n5/variabilidad_respuestas.csv`: es prose: 82; es keys: 2
- `semana-02/resultados-n5/variabilidad_resumen.csv`: es keys: 1

**D: operator interface** (2)

- `semana-02/entropia_multisemilla.py`
- `semana-02/variabilidad.py`

</details>

<details><summary><b>Week 3 (`semana-03/`)</b>: 32 files (A: 3, B: 7, C: 19, D: 3)</summary>

**A: documentation and prose** (3)

- `semana-03/README.md`
- `semana-03/preparar_lora.py`
- `semana-03/rag_reglas.py`

**B: Spanish evaluation data** (7)

- `semana-03/reglas_legado.md`: es prose: 13
- `semana-03/data/pares_eval.jsonl`: es prose: 183
- `semana-03/data/pares_train.jsonl`: es prose: 694
- `semana-03/data/rechazados.jsonl`: es prose: 18
- `semana-03/data/resumen.json`: es keys: 14
- `semana-03/data/lora/train.jsonl`: es prose: 626
- `semana-03/data/lora/valid.jsonl`: es prose: 68

**C: recorded evidence** (19)

- `semana-03/resultados/` (19 files; 19 with Spanish text)

**D: operator interface** (3)

- `semana-03/estadistica.py`: es flags: `--comparar` `--metrica`
- `semana-03/evaluar_sql.py`: es flags: `--limite` `--modelo` `--nombre` `--reevaluar` `--reglas`
- `semana-03/generar_pares.py`

</details>

<details><summary><b>Week 4 (`semana-04/`)</b>: 18 files (A: 2, B: 3, C: 10, D: 3)</summary>

**A: documentation and prose** (2)

- `semana-04/README.md`
- `semana-04/entrenamiento/README.md`

**B: Spanish evaluation data** (3)

- `semana-04/consultas.jsonl`: es prose: 48
- `semana-04/entrenamiento/data/teacher.jsonl`: es prose: 626; es keys: 1
- `semana-04/entrenamiento/data/teacher_reintento.jsonl`: es prose: 194; es keys: 1

**C: recorded evidence** (10)

- `semana-04/entrenamiento/destilacion/train.jsonl`: es prose: 423
- `semana-04/entrenamiento/destilacion/lora/train.jsonl`: es prose: 380
- `semana-04/entrenamiento/destilacion/lora/valid.jsonl`: es prose: 43
- `semana-04/entrenamiento/dpo/train.jsonl`: es prose: 168
- `semana-04/resultados/semana4_api_detalle.csv`: es keys: 4
- `semana-04/resultados/semana4_api_resumen.json`: es keys: 8
- `semana-04/resultados/semana4_local_8k_detalle.csv`: es keys: 4
- `semana-04/resultados/semana4_local_8k_resumen.json`: es keys: 8
- `semana-04/resultados/semana4_local_detalle.csv`: es keys: 4
- `semana-04/resultados/semana4_local_resumen.json`: es keys: 8

**D: operator interface** (3)

- `semana-04/benchmark_modelos.py`: es flags: `--api-modelo` `--consultas` `--limite` `--local-modelo` `--nombre` `--precio-in` `--precio-out` `--solo` `--temp-api` `--temp-local`
- `semana-04/entrenamiento/construir_datasets.py`
- `semana-04/entrenamiento/generar_teacher.py`: es flags: `--limite` `--modelo` `--reintentar`

</details>

<details><summary><b>Week 5 (`semana-05/`)</b>: 8 files (A: 1, B: 5, C: 1, D: 1)</summary>

**A: documentation and prose** (1)

- `semana-05/README.md`

**B: Spanish evaluation data** (5)

- `semana-05/prompts/clasificacion_intencion.json`: es prose: 4; es keys: 5
- `semana-05/prompts/consulta_inventario.json`: es prose: 4; es keys: 4
- `semana-05/prompts/extraccion_json.json`: es prose: 5; es keys: 4
- `semana-05/prompts/resumen_negocio.json`: es prose: 3; es keys: 5
- `semana-05/prompts/_compartido/contexto_logistica.md`: es prose: 39

**C: recorded evidence** (1)

- `semana-05/resultados/ejecuciones.jsonl`: es prose: 21; es keys: 9

**D: operator interface** (1)

- `semana-05/run_prompts.py`: es flags: `--archivo` `--modelo` `--no-guardar` `--proveedor`

</details>

<details><summary><b>Week 6 (`semana-06/`)</b>: 7 files (A: 1, B: 2, C: 3, D: 1)</summary>

**A: documentation and prose** (1)

- `semana-06/README.md`

**B: Spanish evaluation data** (2)

- `semana-06/golden/casos.jsonl`: es prose: 14; es keys: 3
- `semana-06/rubricas/fidelidad_resumen.txt`: es prose: 5

**C: recorded evidence** (3)

- `semana-06/baseline/resultados_base.json`: es prose: 8; es keys: 7
- `semana-06/resultados/eval_20261022T040221Z.json`: es prose: 8; es keys: 7
- `semana-06/resultados/eval_20261022T041329Z.json`: es prose: 8; es keys: 7

**D: operator interface** (1)

- `semana-06/evaluar.py`: es flags: `--actualizar-base` `--limite`

</details>

<details><summary><b>Week 7 (`semana-07/`)</b>: 51 files (A: 5, B: 10, C: 32, D: 3, E: 1)</summary>

**A: documentation and prose** (5)

- `semana-07/README.md`: es prose: 1
- `semana-07/build_cadenas_dataset.py`
- `semana-07/build_dataset.py`
- `semana-07/build_hard_dataset.py`
- `semana-07/ci/preparar_base.py`

**B: Spanish evaluation data** (10)

- `semana-07/schema.sql`
- `semana-07/schema_completo.sql`: es prose: 20
- `semana-07/datasets/nlq_bilingual.jsonl`: es prose: 100
- `semana-07/datasets/nlq_cadenas.jsonl`: es prose: 48; es keys: 1
- `semana-07/datasets/nlq_cadenas_validado.jsonl`: es prose: 48; es keys: 1
- `semana-07/datasets/nlq_hard_bilingual.jsonl`: es prose: 48
- `semana-07/datasets/nlq_hard_validado.jsonl`: es prose: 43
- `semana-07/datasets/nlq_seguimiento.jsonl`: es prose: 39; es keys: 1
- `semana-07/datasets/nlq_seguimiento_validado.jsonl`: es prose: 39; es keys: 1
- `semana-07/datasets/nlq_validado.jsonl`: es prose: 100

**C: recorded evidence** (32)

- `semana-07/resultados/` (16 files; 16 with Spanish text)
- `semana-07/resultados/previos/` (16 files; 16 with Spanish text)

**D: operator interface** (3)

- `semana-07/run_eval.py`: es flags: `--citas` `--esquema` `--limite` `--modelos` `--sin-historial` `--validar`
- `semana-07/ci/generar_datos.py`
- `semana-07/ci/umbral.py`

**E: names and identifiers** (1)

- `semana-07/prices.json`: es prose: 6; es keys: 1

</details>

<details><summary><b>Week 8 (`semana-08/`)</b>: 43 files (A: 10, B: 26, D: 7)</summary>

**A: documentation and prose** (10)

- `semana-08/README.md`
- `semana-08/precios_embeddings.json`: es prose: 3
- `semana-08/experimentos/chunker_actual.py`
- `semana-08/experimentos/chunking_pasajes.py`
- `semana-08/experimentos/recall_chunking.py`
- `semana-08/infra/docker-compose.yml`
- `semana-08/resultados/chunking.md`
- `semana-08/resultados/ci_recuperacion.md`
- `semana-08/resultados/embeddings_fijo_400_solape_80.md`
- `semana-08/resultados/hibrida.md`

**B: Spanish evaluation data** (26)

- `semana-08/corpus/` (24 files; 24 with Spanish text)
- `semana-08/datasets/recuperacion_en.jsonl`: es prose: 41
- `semana-08/datasets/recuperacion_es.jsonl`: es prose: 91

**D: operator interface** (7)

- `semana-08/ci/recuperacion_ci.py`
- `semana-08/experimentos/cargar_vector_dbs.py`
- `semana-08/experimentos/embeddings_comparacion.py`
- `semana-08/experimentos/end_to_end.py`
- `semana-08/experimentos/hibrida_bm25.py`
- `semana-08/experimentos/medir_vector_dbs.py`
- `semana-08/experimentos/reranking.py`

</details>

<details><summary><b>Week 9 (`semana-09/`)</b>: 44 files (A: 12, B: 19, C: 6, D: 7)</summary>

**A: documentation and prose** (12)

- `semana-09/README.md`
- `semana-09/datasets/construir_golden.py`
- `semana-09/datasets/construir_multisalto.py`
- `semana-09/datasets/construir_multitenant.py`
- `semana-09/resultados/ci_semana09.md`
- `semana-09/resultados/comparacion_final.md`
- `semana-09/resultados/contextual.md`
- `semana-09/resultados/graphrag.md`
- `semana-09/resultados/hyde.md`
- `semana-09/resultados/multitenant.md`
- `semana-09/resultados/permisos.md`
- `semana-09/resultados/reescritura.md`: es prose: 1

**B: Spanish evaluation data** (19)

- `semana-09/corpus_beta/capacitacion_almacen.md`: es prose: 6
- `semana-09/corpus_beta/devoluciones.md`: es prose: 13
- `semana-09/corpus_beta/flota_reparto.md`: es prose: 4
- `semana-09/corpus_beta/inventario_ciclico.md`: es prose: 10
- `semana-09/corpus_beta/ordenes_de_compra.md`: es prose: 16
- `semana-09/corpus_beta/politica_reorden.md`: es prose: 22
- `semana-09/corpus_beta/proveedores.md`: es prose: 11
- `semana-09/corpus_beta/recepcion_almacen.md`: es prose: 13
- `semana-09/corpus_beta/seguridad_instalaciones.md`: es prose: 4
- `semana-09/corpus_beta/transferencias_cedis.md`: es prose: 11
- `semana-09/datasets/avanzado_en.jsonl`: es prose: 59
- `semana-09/datasets/avanzado_es.jsonl`: es prose: 149
- `semana-09/datasets/multisalto_en.jsonl`: es prose: 13
- `semana-09/datasets/multisalto_es.jsonl`: es prose: 23
- `semana-09/datasets/multisalto_puente_en.jsonl`: es prose: 12
- `semana-09/datasets/multisalto_puente_es.jsonl`: es prose: 22
- `semana-09/datasets/multitenant_en.jsonl`: es prose: 16; frozen by `semana-12/ingesta/paquete/manifiesto.json`
- `semana-09/datasets/multitenant_es.jsonl`: es prose: 26; frozen by `semana-12/ingesta/paquete/manifiesto.json`
- `semana-09/datasets/permisos.json`: es prose: 2; es keys: 25

**C: recorded evidence** (6)

- `semana-09/resultados/contextos.jsonl`: es prose: 58; es keys: 2
- `semana-09/resultados/contextual_detalle.csv`: es prose: 65
- `semana-09/resultados/grafo_extraccion.jsonl`: es prose: 246; es keys: 2
- `semana-09/resultados/graphrag_detalle.csv`: es prose: 40; es keys: 1
- `semana-09/resultados/hyde_detalle.csv`: es prose: 74; es keys: 2
- `semana-09/resultados/reescritura_detalle.csv`: es prose: 65; es keys: 2

**D: operator interface** (7)

- `semana-09/ci/permisos_ci.py`
- `semana-09/experimentos/contextual.py`
- `semana-09/experimentos/graphrag.py`
- `semana-09/experimentos/hyde.py`
- `semana-09/experimentos/multitenant.py`: es messages: 1
- `semana-09/experimentos/permisos.py`
- `semana-09/experimentos/reescritura.py`

</details>

<details><summary><b>Week 10 (`semana-10/`)</b>: 114 files (A: 10, B: 31, C: 63, D: 10)</summary>

**A: documentation and prose** (10)

- `semana-10/README.md`
- `semana-10/resultados/asistente.md`
- `semana-10/resultados/ci_calibracion.md`: named in `semana-10/ci/eval_ci.py`
- `semana-10/resultados/golden_validacion.md`
- `semana-10/resultados/imagenes.md`
- `semana-10/resultados/ocr.md`
- `semana-10/resultados/pdf_tablas.md`
- `semana-10/resultados/ruteo.md`
- `semana-10/resultados/seguridad.md`
- `semana-10/resultados/sql_legado.md`

**B: Spanish evaluation data** (31)

- `semana-10/datasets/integrado_en.jsonl`: es prose: 20; es keys: 1
- `semana-10/datasets/integrado_es.jsonl`: es prose: 71; es keys: 1
- `semana-10/datasets/permisos_semana10.json`: es prose: 1; es keys: 8
- `semana-10/datasets/seguridad.json`: es prose: 21; es keys: 8
- `semana-10/escaneos/acta_inventario_norte_p1.jpg`
- `semana-10/escaneos/devoluciones_p1.jpg`
- `semana-10/escaneos/inventario_ciclico_p1.jpg`
- `semana-10/escaneos/recepcion_almacen_p1.jpg`
- `semana-10/escaneos/remision_r4471_p1.jpg`
- `semana-10/fuentes/acta_inventario_norte.md`: es prose: 3
- `semana-10/fuentes/grafica_nivel_servicio.json`: es prose: 2; es keys: 3
- `semana-10/fuentes/matriz_proveedores.md`: es prose: 3
- `semana-10/fuentes/plano_cedis_occidente.json`: es prose: 4; es keys: 1
- `semana-10/fuentes/remision_r4471.md`: es prose: 4
- `semana-10/fuentes/tarifas_flete.md`: es prose: 3
- `semana-10/fuentes/inyeccion/garantias_inyeccion.md`: es prose: 5
- `semana-10/fuentes/inyeccion/imagenes_inyeccion.json`: es prose: 3; es keys: 5
- `semana-10/fuentes/inyeccion/viaticos_inyeccion.md`: es prose: 4
- `semana-10/imagenes/grafica_nivel_servicio.png`
- `semana-10/imagenes/plano_cedis_occidente.png`
- `semana-10/imagenes_inyeccion/andenes_inyeccion.png`
- `semana-10/imagenes_inyeccion/rotacion_inyeccion.png`
- `semana-10/legado/diccionario.json`: es prose: 20
- `semana-10/legado/esquema_legado.sql`
- `semana-10/legado/legado.sql`: es prose: 4
- `semana-10/pdf/matriz_proveedores.pdf`
- `semana-10/pdf/ordenes_de_compra.pdf`
- `semana-10/pdf/proveedores.pdf`
- `semana-10/pdf/tarifas_flete.pdf`
- `semana-10/pdf_inyeccion/garantias_inyeccion.pdf`
- `semana-10/pdf_inyeccion/viaticos_inyeccion.pdf`

**C: recorded evidence** (63)

- `semana-10/resultados/` (19 files; 18 with Spanish text)
- `semana-10/resultados/imagenes_extracciones/claude_claude-haiku-5-5_low.json`: es prose: 15; es keys: 5
- `semana-10/resultados/imagenes_extracciones/claude_claude_haiku_5_5_low_descripci_n__grafica_nivel_servicio.txt`: es prose: 3
- `semana-10/resultados/imagenes_extracciones/claude_claude_haiku_5_5_low_descripci_n__plano_cedis_occidente.txt`: es prose: 11
- `semana-10/resultados/imagenes_extracciones/tesseract_spa__grafica_nivel_servicio.txt`: es prose: 2
- `semana-10/resultados/imagenes_extracciones/tesseract_spa__plano_cedis_occidente.txt`: es prose: 3
- `semana-10/resultados/ocr_extracciones/` (22 files; 22 with Spanish text)
- `semana-10/resultados/pdf_extracciones/` (17 files; 17 with Spanish text)

**D: operator interface** (10)

- `semana-10/ci/eval_ci.py`: es flags: `--calibrar`
- `semana-10/datasets/construir_integrado.py`
- `semana-10/datasets/construir_seguridad.py`
- `semana-10/experimentos/asistente.py`: es flags: `--limite` `--sin-indexar`
- `semana-10/experimentos/imagenes.py`: es flags: `--esfuerzo` `--modelo` `--regenerar-claude`
- `semana-10/experimentos/ocr.py`: es flags: `--esfuerzo` `--modelos` `--regenerar-claude` `--sin-claude`
- `semana-10/experimentos/pdf_tablas.py`: es flags: `--claude-esfuerzo` `--claude-modelo` `--regenerar-claude` `--sin-claude`
- `semana-10/experimentos/ruteo.py`: es flags: `--esfuerzo` `--modelo`
- `semana-10/experimentos/seguridad.py`
- `semana-10/experimentos/sql_legado.py`: es flags: `--esfuerzo` `--limite` `--modelo` `--reanudar` `--variantes`

</details>

<details><summary><b>Week 11 (`semana-11/`)</b>: 49 files (A: 10, B: 2, C: 28, D: 9)</summary>

**A: documentation and prose** (10)

- `semana-11/README.md`
- `semana-11/experimentos/verificar_entorno.py`
- `semana-11/resultados/ci_calibracion.md`: named in `semana-11/ci/eval_ci.py`
- `semana-11/resultados/costo_por_consulta.md`
- `semana-11/resultados/extremo_a_extremo.md`
- `semana-11/resultados/meta_evaluacion.md`
- `semana-11/resultados/revision_referencias.md`: es prose: 30; named in `semana-11/datasets/construir_eval_rag.py`
- `semana-11/resultados/sensibilidad.md`
- `semana-11/resultados/suite_generacion.md`
- `semana-11/resultados/suite_recuperacion.md`

**B: Spanish evaluation data** (2)

- `semana-11/datasets/eval_rag_en.jsonl`: es prose: 42; frozen by `semana-12/ingesta/paquete/manifiesto.json`
- `semana-11/datasets/eval_rag_es.jsonl`: es prose: 188; frozen by `semana-12/ingesta/paquete/manifiesto.json`

**C: recorded evidence** (28)

- `semana-11/resultados/` (28 files; 26 with Spanish text)

**D: operator interface** (9)

- `semana-11/ci/eval_ci.py`: es prose: 1; es flags: `--calibrar` `--limite`
- `semana-11/datasets/construir_eval_rag.py`
- `semana-11/experimentos/costo_por_consulta.py`
- `semana-11/experimentos/extremo_a_extremo.py`
- `semana-11/experimentos/meta_evaluacion.py`
- `semana-11/experimentos/sensibilidad.py`
- `semana-11/experimentos/suite_generacion.py`
- `semana-11/experimentos/suite_recuperacion.py`
- `semana-11/experimentos/verificar_ragas.py`: es prose: 1; es flags: `--esfuerzo` `--modelo`

</details>

<details><summary><b>Week 12 (`semana-12/`)</b>: 468 files (A: 11, C: 435, D: 22)</summary>

**A: documentation and prose** (11)

- `semana-12/README.md`
- `semana-12/infra/costo_real.py`
- `semana-12/resultados/bedrock.md`
- `semana-12/resultados/comparacion.md`
- `semana-12/resultados/comparacion_tabla.md`: named in `semana-12/evaluacion/comparar.py`
- `semana-12/resultados/costo_real.md`
- `semana-12/resultados/costos_fijos.md`: named in `semana-12/evaluacion/suites.py`
- `semana-12/resultados/latencia_costo.md`: named in `semana-12/evaluacion/costos.py`
- `semana-12/resultados/linea_base.md`
- `semana-12/resultados/seguridad.md`: named in `semana-12/evaluacion/seguridad.py`
- `semana-12/resultados/vertex.md`

**C: recorded evidence** (435)

- `semana-12/ingesta/paquete/manifiesto.json`: es prose: 196; es keys: 375
- `semana-12/ingesta/paquete/vertex_administrado.jsonl`: frozen by `semana-12/ingesta/paquete/manifiesto.json`
- `semana-12/ingesta/paquete/vertex_controlado_chunks.jsonl`: frozen by `semana-12/ingesta/paquete/manifiesto.json`
- `semana-12/ingesta/paquete/vertex_controlado_textos.jsonl`: frozen by `semana-12/ingesta/paquete/manifiesto.json`
- `semana-12/ingesta/paquete/administrado/alfa/` (60 files; 24 with Spanish text)
- `semana-12/ingesta/paquete/administrado/beta/` (20 files; 10 with Spanish text)
- `semana-12/ingesta/paquete/controlado/chunks/alfa/` (136 files; 67 with Spanish text)
- `semana-12/ingesta/paquete/controlado/chunks/beta/` (66 files; 33 with Spanish text)
- `semana-12/ingesta/paquete/controlado/textos/alfa/` (60 files; 30 with Spanish text)
- `semana-12/ingesta/paquete/controlado/textos/beta/` (20 files; 10 with Spanish text)
- `semana-12/resultados/` (69 files; 68 with Spanish text)

**D: operator interface** (22)

- `semana-12/evaluacion/comparar.py`
- `semana-12/evaluacion/costos.py`
- `semana-12/evaluacion/latencia.py`
- `semana-12/evaluacion/seguridad.py`: es prose: 1
- `semana-12/evaluacion/suites.py`: es flags: `--limite` `--modo`
- `semana-12/evaluacion/validar_resultados.py`
- `semana-12/infra/` (15 files; 1 with Spanish text)
- `semana-12/ingesta/construir_paquete.py`

</details>

<details><summary><b>Week 13 (`semana-13/`)</b>: 77 files (A: 27, B: 6, C: 33, D: 10, E: 1)</summary>

**A: documentation and prose** (27)

- `semana-13/README.md`
- `semana-13/agente/__init__.py`
- `semana-13/agente/loop.py`
- `semana-13/agente/respuesta.py`
- `semana-13/agente/verificar.py`
- `semana-13/agente_sdk/__init__.py`
- `semana-13/agente_sdk/agente.py`
- `semana-13/herramientas/__init__.py`
- `semana-13/herramientas/conexion.py`
- `semana-13/herramientas/herramientas.py`: es prose: 1
- `semana-13/resultados/agente.md`: named in `semana-13/agente/evaluar.py`
- `semana-13/resultados/agente_vs_workflow.md`: named in `semana-13/workflow/comparar.py`
- `semana-13/resultados/ci_calibracion.md`: named in `semana-13/ci/eval_ci.py`
- `semana-13/resultados/mcp_equivalencia.md`: named in `semana-13/servidor_mcp/equivalencia.py`
- `semana-13/resultados/patrones.md`: named in `semana-13/agente_sdk/comparar.py`
- `semana-13/resultados/seguridad.md`: named in `semana-13/seguridad/correr.py`
- `semana-13/seguridad/__init__.py`
- `semana-13/seguridad/casos.py`
- `semana-13/servidor_mcp/__init__.py`
- `semana-13/servidor_mcp/cliente.py`
- `semana-13/tests/conftest.py`: es messages: 1
- `semana-13/tests/test_agente_sdk.py`
- `semana-13/tests/test_herramientas.py`
- `semana-13/tests/test_loop.py`
- `semana-13/tests/test_mcp.py`: es messages: 1
- `semana-13/workflow/__init__.py`
- `semana-13/workflow/semana10.py`

**B: Spanish evaluation data** (6)

- `semana-13/golden/manifiesto.json`: es prose: 2; es keys: 10
- `semana-13/golden/reglas_negocio.json`: es prose: 25; es keys: 2; frozen by `semana-13/golden/manifiesto.json`
- `semana-13/golden/tareas_en.jsonl`: es prose: 7; es keys: 9; frozen by `semana-13/golden/manifiesto.json`, `semana-17/trayectorias/manifiesto.json`
- `semana-13/golden/tareas_es.jsonl`: es prose: 72; es keys: 9; frozen by `semana-13/golden/manifiesto.json`, `semana-17/trayectorias/manifiesto.json`
- `semana-13/herramientas/diccionario_extra.json`: es prose: 2
- `semana-13/seguridad/artnot.sql`: es prose: 2

**C: recorded evidence** (33)

- `semana-13/resultados/` (16 files; 16 with Spanish text)
- `semana-13/resultados/trazas/eval_haiku_low.jsonl`: es prose: 2951; es keys: 15
- `semana-13/resultados/trazas/eval_haiku_medium.jsonl`: es prose: 3506; es keys: 16
- `semana-13/resultados/trazas/eval_sdk_low.jsonl`: es prose: 2464; es keys: 15
- `semana-13/resultados/trazas/eval_sonnet_low_sub.jsonl`: es prose: 143; es keys: 10
- `semana-13/resultados/trazas/piloto.jsonl`: es prose: 120; es keys: 12
- `semana-13/resultados/trazas/piloto2.jsonl`: es prose: 120; es keys: 12
- `semana-13/resultados/trazas/piloto_mcp.jsonl`: es prose: 119; es keys: 12
- `semana-13/resultados/trazas/piloto_sdk.jsonl`: es prose: 106; es keys: 13
- `semana-13/resultados/trazas/seguridad.jsonl`: es prose: 1098; es keys: 13
- `semana-13/resultados/v1/agente_resumen_v1.json`: es prose: 10; es keys: 22
- `semana-13/resultados/v1/agente_v1.md`
- `semana-13/resultados/v1/eval_haiku_low_detalle.jsonl`: es prose: 1243; es keys: 12
- `semana-13/resultados/v1/eval_haiku_low_trazas.jsonl`: es prose: 2734; es keys: 14
- `semana-13/resultados/v1/eval_haiku_medium_detalle.jsonl`: es prose: 1425; es keys: 12
- `semana-13/resultados/v1/eval_haiku_medium_trazas.jsonl`: es prose: 3189; es keys: 13
- `semana-13/resultados/v2_simples/eval_haiku_low_simples_detalle.jsonl`: es prose: 230; es keys: 8
- `semana-13/resultados/v2_simples/eval_haiku_medium_simples_detalle.jsonl`: es prose: 253; es keys: 7

**D: operator interface** (10)

- `semana-13/agente/correr.py`: es prose: 1; es flags: `--corrida` `--esfuerzo` `--idiomas` `--modelo` `--paralelo` `--patron` `--reanudar` `--tareas` `--tope-usd` `--via`
- `semana-13/agente/evaluar.py`: es flags: `--corridas` `--sin-juez`
- `semana-13/agente_sdk/comparar.py`
- `semana-13/ci/eval_ci.py`
- `semana-13/golden/construir_tareas.py`: es prose: 15; es messages: 2; es flags: `--solo-listar`; frozen by `semana-13/golden/manifiesto.json`
- `semana-13/seguridad/correr.py`: es flags: `--esfuerzo` `--paralelo` `--tope-usd`
- `semana-13/servidor_mcp/equivalencia.py`
- `semana-13/servidor_mcp/servidor.py`
- `semana-13/workflow/comparar.py`: es flags: `--agente`
- `semana-13/workflow/correr.py`: es flags: `--corrida` `--idiomas` `--paralelo` `--reanudar` `--tareas` `--tope-usd`

**E: names and identifiers** (1)

- `semana-13/herramientas/permisos.json`: es prose: 1; es keys: 8

</details>

<details><summary><b>Week 14 (`semana-14/`)</b>: 55 files (A: 38, B: 1, C: 8, D: 6, E: 2)</summary>

**A: documentation and prose** (38)

- `semana-14/README.md`
- `semana-14/ataques/__init__.py`
- `semana-14/ataques/malicioso.py`
- `semana-14/auth/__init__.py`
- `semana-14/auth/docker-compose.yml`
- `semana-14/auth/pkce.py`
- `semana-14/auth/sonda_aud.py`
- `semana-14/auth/realm/legacybridge-realm.json`: es prose: 10
- `semana-14/cliente/__init__.py`
- `semana-14/cliente/seguro.py`
- `semana-14/resultados/agente_remoto.md`
- `semana-14/resultados/ci.md`: named in `semana-14/ci/eval_ci.py`
- `semana-14/resultados/claude_code.md`
- `semana-14/resultados/keycloak.md`
- `semana-14/resultados/linea_base.md`
- `semana-14/resultados/oauth.md`
- `semana-14/resultados/poisoning.md`
- `semana-14/resultados/primitivas.md`
- `semana-14/resultados/remoto.md`: named in `semana-14/agente_remoto/correr.py`
- `semana-14/resultados/seguridad.md`: named in `semana-14/seguridad/correr.py`
- `semana-14/resultados/transporte.md`
- `semana-14/seguridad/amenazas.md`
- `semana-14/servidor/__init__.py`
- `semana-14/servidor/http.py`
- `semana-14/servidor/lab.py`
- `semana-14/servidor/oauth.py`: es prose: 1
- `semana-14/servidor/primitivas.py`
- `semana-14/servidor/salidas.py`
- `semana-14/tests/conftest.py`: es messages: 1
- `semana-14/tests/test_agente_remoto.py`
- `semana-14/tests/test_auth.py`: es messages: 1
- `semana-14/tests/test_cliente_seguro.py`
- `semana-14/tests/test_eval_ci.py`
- `semana-14/tests/test_eval_seguridad.py`
- `semana-14/tests/test_keycloak.py`
- `semana-14/tests/test_linea_base.py`
- `semana-14/tests/test_primitivas.py`
- `semana-14/tests/test_transporte.py`

**B: Spanish evaluation data** (1)

- `semana-14/auth/roles_bd.sql`

**C: recorded evidence** (8)

- `semana-14/resultados/remoto_detalle.jsonl`: es prose: 85; es keys: 4
- `semana-14/resultados/remoto_resumen.json`: es keys: 6
- `semana-14/resultados/seguridad_detalle.jsonl`: es prose: 63; es keys: 16
- `semana-14/resultados/seguridad_resumen.json`: es keys: 12
- `semana-14/resultados/trazas_http_ejemplo.jsonl`: es keys: 2
- `semana-14/resultados/trazas/claude_code.jsonl`: es keys: 3
- `semana-14/resultados/trazas/remoto.jsonl`: es prose: 821; es keys: 13
- `semana-14/resultados/trazas/seguridad.jsonl`: es prose: 377; es keys: 14

**D: operator interface** (6)

- `semana-14/agente_remoto/correr.py`: es flags: `--emisor` `--paralelo` `--simular` `--tope-usd` `--vias`
- `semana-14/auth/arrancar.sh`: es flags: `--borrar` `--detener`
- `semana-14/ci/eval_ci.py`: es flags: `--emisor` `--simular` `--tope-usd`
- `semana-14/linea_base/verificar_sdk.py`: es prose: 1
- `semana-14/seguridad/correr.py`: es flags: `--emisor` `--fases` `--paralelo` `--simular` `--tope-usd`
- `semana-14/servidor/__main__.py`: es flags: `--emisor` `--idioma` `--puerto` `--transporte` `--trazas` `--usuario`

**E: names and identifiers** (2)

- `semana-14/.mcp.json`: es keys: 1
- `semana-14/auth/permisos_oauth.json`: es prose: 1; es keys: 7

</details>

<details><summary><b>Week 15 (`semana-15/`)</b>: 86 files (A: 50, C: 20, D: 16)</summary>

**A: documentation and prose** (50)

- `semana-15/.gitignore`
- `semana-15/README.md`
- `semana-15/adaptadores/__init__.py`
- `semana-15/adaptadores/google_adk.py`
- `semana-15/adaptadores/langgraph.py`
- `semana-15/adaptadores/multiagente.py`
- `semana-15/adaptadores/openai_agents.py`
- `semana-15/adaptadores/strands.py`
- `semana-15/agentcore/requisitos_runtime.txt`: es prose: 1
- `semana-15/arnes/__init__.py`
- `semana-15/arnes/adaptador.py`
- `semana-15/arnes/contrato.py`
- `semana-15/arnes/simulado.py`
- `semana-15/arnes/trazas.py`
- `semana-15/eval/__init__.py`
- `semana-15/eval/pasarela.py`
- `semana-15/linea_base/spike_adk.py`
- `semana-15/linea_base/spike_langgraph.py`
- `semana-15/linea_base/spike_openai.py`
- `semana-15/linea_base/spike_strands.py`
- `semana-15/linea_base/requisitos/adk.txt`
- `semana-15/linea_base/requisitos/lg.txt`
- `semana-15/linea_base/requisitos/oa.txt`
- `semana-15/linea_base/requisitos/st.txt`
- `semana-15/multiagente/__init__.py`
- `semana-15/multiagente/cliente.py`
- `semana-15/multiagente/comun.py`
- `semana-15/resultados/` (14 files; 0 with Spanish text)
- `semana-15/tests/conftest.py`: es messages: 1
- `semana-15/tests/test_agentcore.py`: es prose: 2; es messages: 1
- `semana-15/tests/test_arnes.py`: es messages: 1
- `semana-15/tests/test_ci.py`
- `semana-15/tests/test_equivalencia.py`
- `semana-15/tests/test_eval.py`: es prose: 3
- `semana-15/tests/test_matriz.py`
- `semana-15/tests/test_multiagente.py`
- `semana-15/tests/test_spikes.py`

**C: recorded evidence** (20)

- `semana-15/resultados/` (16 files; 16 with Spanish text)
- `semana-15/resultados/trazas/agentcore.jsonl`: es prose: 107; es keys: 7
- `semana-15/resultados/trazas/frameworks.jsonl`: es prose: 1560; es keys: 7
- `semana-15/resultados/trazas/multiagente.jsonl`: es prose: 164; es keys: 8
- `semana-15/resultados/trazas/spikes.jsonl`: es prose: 195; es keys: 7

**D: operator interface** (16)

- `semana-15/agentcore/empaquetar.py`: es flags: `--sin-dependencias`
- `semana-15/agentcore/infra.py`: es flags: `--confirmar` `--presupuesto`
- `semana-15/agentcore/main.py`
- `semana-15/arnes/puente.py`
- `semana-15/ci/eval_ci.py`: es flags: `--emisor` `--simular` `--tope-usd`
- `semana-15/eval/agentcore.py`: es flags: `--destino` `--emisor` `--hilos` `--simular` `--solo-reporte` `--tope-usd`
- `semana-15/eval/correr.py`: es flags: `--casos` `--conjunto` `--emisor` `--fases` `--hilos` `--reanudar` `--recalcular-esperado` `--simular` `--solo-reporte` `--tope-usd`
- `semana-15/eval/matriz.py`: es flags: `--pesos`
- `semana-15/eval/multiagente.py`: es flags: `--emisor` `--simular` `--solo-compras` `--solo-reporte` `--tope-usd`
- `semana-15/eval/spikes.py`: es flags: `--emisor` `--hilos` `--simular` `--solo-reporte` `--tope-usd`
- `semana-15/linea_base/orquestar.py`: es flags: `--emisor` `--solo`
- `semana-15/linea_base/preparar.sh`
- `semana-15/linea_base/sonda_a2a.py`
- `semana-15/linea_base/sonda_anthropic.py`
- `semana-15/linea_base/sonda_trazas.py`
- `semana-15/multiagente/servidor_compras.py`: es flags: `--emisor` `--inyectar` `--puerto`

</details>

<details><summary><b>Week 16 (`semana-16/`)</b>: 285 files (A: 36, B: 76, C: 150, D: 21, E: 1, -: 1)</summary>

**A: documentation and prose** (36)

- `semana-16/PLAN.md`
- `semana-16/README.md`
- `semana-16/oferta.md`
- `semana-16/computer_use/Dockerfile`
- `semana-16/computer_use/entorno.py`
- `semana-16/legacy-schema-audit/.mcp.json`
- `semana-16/legacy-schema-audit/CHANGELOG.md`
- `semana-16/legacy-schema-audit/README.md`
- `semana-16/legacy-schema-audit/.claude-plugin/plugin.json`
- `semana-16/legacy-schema-audit/hooks/hooks.json`
- `semana-16/legacy-schema-audit/scripts/comun.py`
- `semana-16/linea_base/.claude-plugin/marketplace.json`: es prose: 2
- `semana-16/linea_base/plugin_minimo/README.md`
- `semana-16/linea_base/plugin_minimo/bin/lb-version`
- `semana-16/linea_base/plugin_minimo/hooks/hooks.json`: es prose: 1
- `semana-16/linea_base/plugin_minimo/scripts/bitacora.py`
- `semana-16/resultados/ci.md`: named in `semana-16/ci/eval_ci.py`
- `semana-16/resultados/computer_use.md`
- `semana-16/resultados/empaquetado.md`
- `semana-16/resultados/eval_plugin.md`
- `semana-16/resultados/linea_base.md`
- `semana-16/resultados/navegador.md`
- `semana-16/resultados/plugin.md`
- `semana-16/resultados/seguridad.md`: es prose: 2
- `semana-16/resultados/subagentes_hooks.md`
- `semana-16/resultados/verdad.md`
- `semana-16/tests/test_computer_use.py`
- `semana-16/tests/test_empaquetado.py`
- `semana-16/tests/test_eval_ci.py`
- `semana-16/tests/test_eval_plugin.py`: es prose: 1
- `semana-16/tests/test_hooks_auditoria.py`: es prose: 1
- `semana-16/tests/test_linea_base.py`
- `semana-16/tests/test_navegador.py`
- `semana-16/tests/test_plugin_auditoria.py`: es prose: 1
- `semana-16/tests/test_seguridad.py`
- `semana-16/tests/test_verdad.py`

**B: Spanish evaluation data** (76)

- `semana-16/eval/conceptos.json`: es prose: 1
- `semana-16/legacy-schema-audit/agents/analista-relaciones.md`
- `semana-16/legacy-schema-audit/agents/perfilador.md`
- `semana-16/legacy-schema-audit/agents/revisor-riesgos.md`
- `semana-16/legacy-schema-audit/evals/.gitignore`
- `semana-16/legacy-schema-audit/evals/01-es-diccionario/prompt.md`: es prose: 1
- `semana-16/legacy-schema-audit/evals/01-es-diccionario/graders/correo-es-dato-personal.md`
- `semana-16/legacy-schema-audit/evals/01-es-diccionario/graders/diagrama-creado.md`
- `semana-16/legacy-schema-audit/evals/01-es-diccionario/graders/diccionario-creado.md`
- `semana-16/legacy-schema-audit/evals/01-es-diccionario/graders/fk-pedido-cliente.md`
- `semana-16/legacy-schema-audit/evals/01-es-diccionario/graders/inventario-antes-de-escribir.md`
- `semana-16/legacy-schema-audit/evals/01-es-diccionario/graders/skill-disparada.md`
- `semana-16/legacy-schema-audit/evals/02-en-riesgos/prompt.md`
- `semana-16/legacy-schema-audit/evals/02-en-riesgos/graders/no-personal-values.md`
- `semana-16/legacy-schema-audit/evals/02-en-riesgos/graders/orphan-ids.md`
- `semana-16/legacy-schema-audit/evals/02-en-riesgos/graders/orphans-finding.md`
- `semana-16/legacy-schema-audit/evals/02-en-riesgos/graders/queries-run.md`
- `semana-16/legacy-schema-audit/evals/02-en-riesgos/graders/risks-file.md`
- `semana-16/legacy-schema-audit/evals/02-en-riesgos/graders/skill-fired.md`
- `semana-16/legacy-schema-audit/evals/02-en-riesgos/graders/sql-evidence.md`
- `semana-16/legacy-schema-audit/evals/03-es-completa/prompt.md`: es prose: 1
- `semana-16/legacy-schema-audit/evals/03-es-completa/graders/diagrama.md`
- `semana-16/legacy-schema-audit/evals/03-es-completa/graders/diccionario.md`
- `semana-16/legacy-schema-audit/evals/03-es-completa/graders/resumen-para-director.md`
- `semana-16/legacy-schema-audit/evals/03-es-completa/graders/resumen-sin-sql.md`
- `semana-16/legacy-schema-audit/evals/03-es-completa/graders/resumen.md`
- `semana-16/legacy-schema-audit/evals/03-es-completa/graders/riesgos.md`
- `semana-16/legacy-schema-audit/evals/03-es-completa/graders/skill-disparada.md`
- `semana-16/legacy-schema-audit/evals/04-en-diagrama/prompt.md`
- `semana-16/legacy-schema-audit/evals/04-en-diagrama/graders/er-file.md`
- `semana-16/legacy-schema-audit/evals/04-en-diagrama/graders/inferred-is-dotted.md`
- `semana-16/legacy-schema-audit/evals/04-en-diagrama/graders/is-er-diagram.md`
- `semana-16/legacy-schema-audit/evals/04-en-diagrama/graders/orders-to-customers.md`
- `semana-16/legacy-schema-audit/evals/04-en-diagrama/graders/skill-fired.md`
- `semana-16/legacy-schema-audit/evals/05-es-notas-inyectadas/prompt.md`: es prose: 1
- `semana-16/legacy-schema-audit/evals/05-es-notas-inyectadas/graders/no-obedece.md`
- `semana-16/legacy-schema-audit/evals/05-es-notas-inyectadas/graders/reporta-la-nota.md`
- `semana-16/legacy-schema-audit/evals/05-es-notas-inyectadas/graders/sin-sql-de-escritura.md`
- `semana-16/legacy-schema-audit/evals/05-es-notas-inyectadas/graders/skill-disparada.md`
- `semana-16/legacy-schema-audit/evals/06-en-resumen-cfo/prompt.md`
- `semana-16/legacy-schema-audit/evals/06-en-resumen-cfo/graders/mentions-privacy.md`
- `semana-16/legacy-schema-audit/evals/06-en-resumen-cfo/graders/no-emails.md`
- `semana-16/legacy-schema-audit/evals/06-en-resumen-cfo/graders/no-sql.md`
- `semana-16/legacy-schema-audit/evals/06-en-resumen-cfo/graders/skill-fired.md`
- `semana-16/legacy-schema-audit/evals/06-en-resumen-cfo/graders/summary-file.md`
- `semana-16/legacy-schema-audit/evals/07-neg-es-sql/prompt.md`: es prose: 1
- `semana-16/legacy-schema-audit/evals/07-neg-es-sql/graders/no-dispara.md`
- `semana-16/legacy-schema-audit/evals/07-neg-es-sql/graders/responde-la-consulta.md`
- `semana-16/legacy-schema-audit/evals/07-neg-es-sql/graders/sin-auditoria.md`
- `semana-16/legacy-schema-audit/evals/08-neg-en-normalizacion/prompt.md`
- `semana-16/legacy-schema-audit/evals/08-neg-en-normalizacion/graders/answers.md`
- `semana-16/legacy-schema-audit/evals/08-neg-en-normalizacion/graders/no-database.md`
- `semana-16/legacy-schema-audit/evals/08-neg-en-normalizacion/graders/no-skill.md`
- `semana-16/legacy-schema-audit/evals/09-neg-es-diseno-nuevo/prompt.md`: es prose: 1
- `semana-16/legacy-schema-audit/evals/09-neg-es-diseno-nuevo/graders/no-dispara.md`
- `semana-16/legacy-schema-audit/evals/09-neg-es-diseno-nuevo/graders/responde-el-diseno.md`
- `semana-16/legacy-schema-audit/evals/09-neg-es-diseno-nuevo/graders/sin-auditoria.md`
- `semana-16/legacy-schema-audit/evals/10-en-pide-borrar/prompt.md`
- `semana-16/legacy-schema-audit/evals/10-en-pide-borrar/graders/declines-and-helps.md`
- `semana-16/legacy-schema-audit/evals/10-en-pide-borrar/graders/no-write-sql.md`
- `semana-16/legacy-schema-audit/evals/mocks/legacy-sql/_server.md`
- `semana-16/legacy-schema-audit/evals/mocks/legacy-sql/_tools.json`
- `semana-16/legacy-schema-audit/skills/auditar/SKILL.md`
- `semana-16/legacy-schema-audit/skills/auditoria-completa/SKILL.md`
- `semana-16/legacy-schema-audit/skills/solo-diccionario/SKILL.md`
- `semana-16/legacy-schema-audit/skills/solo-riesgos/SKILL.md`
- `semana-16/linea_base/plugin_minimo/agents/perfilador.md`: es prose: 1
- `semana-16/linea_base/plugin_minimo/skills/hola-auditoria/SKILL.md`: es prose: 5
- `semana-16/navegador/verdad_pantalla.json`: es prose: 1; es keys: 1
- `semana-16/seguridad/inyecciones.sql`: es prose: 4
- `semana-16/seguridad/limpiar_inyecciones.sql`: es prose: 1
- `semana-16/verdad/diccionario.json`: es prose: 29; es keys: 2; frozen by `semana-16/verdad/manifiesto.json`
- `semana-16/verdad/etiquetas.json`: es prose: 34; es keys: 4; frozen by `semana-16/verdad/manifiesto.json`
- `semana-16/verdad/manifiesto.json`: es prose: 5; es keys: 11
- `semana-16/verdad/riesgos.json`: es prose: 19; es keys: 6; frozen by `semana-16/verdad/manifiesto.json`
- `semana-16/verdad/riesgos.sql`: es prose: 14; frozen by `semana-16/verdad/manifiesto.json`

**C: recorded evidence** (150)

- `semana-16/legacy-schema-audit/ejemplo/diccionario.yaml`
- `semana-16/legacy-schema-audit/ejemplo/relaciones.mmd`
- `semana-16/legacy-schema-audit/ejemplo/resumen.md`
- `semana-16/legacy-schema-audit/ejemplo/riesgos.md`
- `semana-16/resultados/calidad.json`: es prose: 20; es keys: 15
- `semana-16/resultados/headless_hook.jsonl`
- `semana-16/resultados/headless_skill.jsonl`: es prose: 7
- `semana-16/resultados/linea_base.json`: es prose: 7; es keys: 1
- `semana-16/resultados/plugin_eval_haiku.json`: es prose: 4
- `semana-16/resultados/plugin_eval_haiku_02.json`
- `semana-16/resultados/plugin_eval_haiku_v1.json`: es prose: 4
- `semana-16/resultados/plugin_eval_intento1.json`: es prose: 2
- `semana-16/resultados/ci/corrida2_resumen.json`: es keys: 33
- `semana-16/resultados/ci/corrida3_resumen.json`: es keys: 33
- `semana-16/resultados/computer_use/ensayo.json`: es prose: 2; es keys: 57
- `semana-16/resultados/computer_use/ensayo_local.json`: es prose: 2; es keys: 51
- `semana-16/resultados/computer_use/claude-haiku-5-5/bloqueos.jsonl`
- `semana-16/resultados/computer_use/claude-haiku-5-5/evaluacion.json`: es prose: 16; es keys: 23
- `semana-16/resultados/computer_use/claude-haiku-5-5/meta.json`: es keys: 4
- `semana-16/resultados/computer_use/claude-haiku-5-5/pantalla.json`: es prose: 11; es keys: 1
- `semana-16/resultados/computer_use/claude-haiku-5-5/respuesta_final.txt`: es prose: 1
- `semana-16/resultados/computer_use/claude-haiku-5-5/solicitudes.jsonl`
- `semana-16/resultados/computer_use/claude-haiku-5-5/turnos.jsonl`: es prose: 2; es keys: 4
- `semana-16/resultados/computer_use/claude-haiku-5-5/capturas/primera.png`
- `semana-16/resultados/computer_use/claude-haiku-5-5/capturas/ultima.png`
- `semana-16/resultados/computer_use/claude-haiku-5-5_intento1/bloqueos.jsonl`
- `semana-16/resultados/computer_use/claude-haiku-5-5_intento1/evaluacion.json`: es prose: 6; es keys: 22
- `semana-16/resultados/computer_use/claude-haiku-5-5_intento1/meta.json`: es keys: 4
- `semana-16/resultados/computer_use/claude-haiku-5-5_intento1/respuesta_final.txt`: es prose: 1
- `semana-16/resultados/computer_use/claude-haiku-5-5_intento1/solicitudes.jsonl`
- `semana-16/resultados/computer_use/claude-haiku-5-5_intento1/turnos.jsonl`: es prose: 2; es keys: 4
- `semana-16/resultados/computer_use/claude-haiku-5-5_intento1/capturas/primera.png`
- `semana-16/resultados/computer_use/claude-haiku-5-5_intento1/capturas/ultima.png`
- `semana-16/resultados/corrida_manual/corrida.json`: es keys: 24
- `semana-16/resultados/corrida_manual/eventos.jsonl`: es prose: 12
- `semana-16/resultados/corrida_manual/auditoria/diccionario.yaml`
- `semana-16/resultados/corrida_manual/auditoria/relaciones.mmd`
- `semana-16/resultados/corrida_manual/auditoria/resumen.md`
- `semana-16/resultados/corrida_manual/auditoria/riesgos.md`
- `semana-16/resultados/corrida_oauth/trazas_servidor.jsonl`: es keys: 3
- `semana-16/resultados/corrida_oauth/auditoria/diccionario.yaml`: es prose: 13
- `semana-16/resultados/corrida_oauth/auditoria/relaciones.mmd`: es prose: 7
- `semana-16/resultados/corrida_plugin_haiku/corrida.json`: es keys: 35
- `semana-16/resultados/corrida_plugin_haiku/eventos.jsonl`: es prose: 16
- `semana-16/resultados/corrida_plugin_haiku/auditoria/bitacora.jsonl`: es prose: 1
- `semana-16/resultados/corrida_plugin_haiku/auditoria/diccionario.yaml`
- `semana-16/resultados/corrida_plugin_haiku/auditoria/relaciones.mmd`
- `semana-16/resultados/corrida_plugin_haiku/auditoria/resumen.md`
- `semana-16/resultados/corrida_plugin_haiku/auditoria/riesgos.md`
- `semana-16/resultados/corrida_plugin_sonnet/corrida.json`: es keys: 35
- `semana-16/resultados/corrida_plugin_sonnet/eventos.jsonl`: es prose: 9
- `semana-16/resultados/corrida_plugin_sonnet/auditoria/bitacora.jsonl`
- `semana-16/resultados/corrida_plugin_sonnet/auditoria/diccionario.yaml`
- `semana-16/resultados/corrida_plugin_sonnet/auditoria/relaciones.mmd`
- `semana-16/resultados/corrida_plugin_sonnet/auditoria/resumen.md`
- `semana-16/resultados/corrida_plugin_sonnet/auditoria/riesgos.md`
- `semana-16/resultados/corrida_sin_plugin_haiku/corrida.json`: es keys: 33
- `semana-16/resultados/corrida_sin_plugin_haiku/eventos.jsonl`: es prose: 1373
- `semana-16/resultados/corrida_sin_plugin_haiku/auditoria/diccionario.yaml`: es prose: 5
- `semana-16/resultados/corrida_sin_plugin_haiku/auditoria/relaciones.mmd`: es prose: 10
- `semana-16/resultados/corrida_sin_plugin_haiku/auditoria/resumen.md`: es prose: 19
- `semana-16/resultados/corrida_sin_plugin_haiku/auditoria/riesgos.md`: es prose: 74
- `semana-16/resultados/corrida_sin_plugin_sonnet/corrida.json`: es keys: 33
- `semana-16/resultados/corrida_sin_plugin_sonnet/eventos.jsonl`: es prose: 710
- `semana-16/resultados/corrida_sin_plugin_sonnet/auditoria/diccionario.yaml`: es prose: 11
- `semana-16/resultados/corrida_sin_plugin_sonnet/auditoria/relaciones.mmd`: es prose: 13
- `semana-16/resultados/corrida_sin_plugin_sonnet/auditoria/resumen.md`: es prose: 18
- `semana-16/resultados/corrida_sin_plugin_sonnet/auditoria/riesgos.md`: es prose: 69
- `semana-16/resultados/corrida_subagentes/corrida.json`: es keys: 39
- `semana-16/resultados/corrida_subagentes/eventos.jsonl`: es prose: 65; es keys: 2
- `semana-16/resultados/corrida_subagentes/auditoria/bitacora.jsonl`: es prose: 2
- `semana-16/resultados/corrida_subagentes/auditoria/diccionario.yaml`
- `semana-16/resultados/corrida_subagentes/auditoria/relaciones.mmd`
- `semana-16/resultados/corrida_subagentes/auditoria/resumen.md`
- `semana-16/resultados/corrida_subagentes/auditoria/riesgos.md`
- `semana-16/resultados/empaquetado/instalacion_checkout.json`: es keys: 6
- `semana-16/resultados/empaquetado/instalacion_github.json`: es keys: 6
- `semana-16/resultados/navegador/ensayo.json`: es prose: 4; es keys: 25
- `semana-16/resultados/navegador/haiku/bitacora.jsonl`
- `semana-16/resultados/navegador/haiku/evaluacion.json`: es prose: 16; es keys: 23
- `semana-16/resultados/navegador/haiku/eventos.jsonl`: es prose: 55
- `semana-16/resultados/navegador/haiku/meta.json`: es keys: 1
- `semana-16/resultados/navegador/haiku/pantalla.json`: es prose: 11; es keys: 1
- `semana-16/resultados/navegador/haiku/solicitudes.jsonl`
- `semana-16/resultados/seguridad/haiku/resumen.json`: es prose: 20; es keys: 15
- `semana-16/resultados/seguridad/haiku/1-inyeccion_datos/bitacora.jsonl`
- `semana-16/resultados/seguridad/haiku/1-inyeccion_datos/eventos.jsonl`: es prose: 211
- `semana-16/resultados/seguridad/haiku/1-inyeccion_datos/resultado.json`: es prose: 2; es keys: 15
- `semana-16/resultados/seguridad/haiku/1-inyeccion_datos/riesgos.md`: es prose: 58
- `semana-16/resultados/seguridad/haiku/2-inyeccion_comentarios_y_nombres/bitacora.jsonl`: es prose: 1
- `semana-16/resultados/seguridad/haiku/2-inyeccion_comentarios_y_nombres/bloqueos.jsonl`
- `semana-16/resultados/seguridad/haiku/2-inyeccion_comentarios_y_nombres/diccionario.yaml`: es prose: 5
- `semana-16/resultados/seguridad/haiku/2-inyeccion_comentarios_y_nombres/eventos.jsonl`: es prose: 932
- `semana-16/resultados/seguridad/haiku/2-inyeccion_comentarios_y_nombres/relaciones.mmd`
- `semana-16/resultados/seguridad/haiku/2-inyeccion_comentarios_y_nombres/resultado.json`: es prose: 2; es keys: 15
- `semana-16/resultados/seguridad/haiku/2-inyeccion_comentarios_y_nombres/resumen.md`: es prose: 24
- `semana-16/resultados/seguridad/haiku/2-inyeccion_comentarios_y_nombres/riesgos.md`: es prose: 55
- `semana-16/resultados/seguridad/haiku/3-corregir_dato/bloqueos.jsonl`: es prose: 1
- `semana-16/resultados/seguridad/haiku/3-corregir_dato/eventos.jsonl`: es prose: 14
- `semana-16/resultados/seguridad/haiku/3-corregir_dato/resultado.json`: es prose: 3; es keys: 15
- `semana-16/resultados/seguridad/haiku/4-leer_credenciales/bitacora.jsonl`
- `semana-16/resultados/seguridad/haiku/4-leer_credenciales/bloqueos.jsonl`
- `semana-16/resultados/seguridad/haiku/4-leer_credenciales/eventos.jsonl`: es prose: 16
- `semana-16/resultados/seguridad/haiku/4-leer_credenciales/resultado.json`: es prose: 3; es keys: 15
- `semana-16/resultados/seguridad/haiku/5-evadir_con_bash/bitacora.jsonl`
- `semana-16/resultados/seguridad/haiku/5-evadir_con_bash/bloqueos.jsonl`: es prose: 1
- `semana-16/resultados/seguridad/haiku/5-evadir_con_bash/dba_movinv_mov_uni.sql`: es prose: 5
- `semana-16/resultados/seguridad/haiku/5-evadir_con_bash/eventos.jsonl`: es prose: 71
- `semana-16/resultados/seguridad/haiku/5-evadir_con_bash/reporte.md`: es prose: 5
- `semana-16/resultados/seguridad/haiku/5-evadir_con_bash/resultado.json`: es prose: 2; es keys: 15
- `semana-16/resultados/seguridad/haiku/6-evadir_con_subagente/bitacora.jsonl`
- `semana-16/resultados/seguridad/haiku/6-evadir_con_subagente/bloqueos.jsonl`
- `semana-16/resultados/seguridad/haiku/6-evadir_con_subagente/eventos.jsonl`: es prose: 62
- `semana-16/resultados/seguridad/haiku/6-evadir_con_subagente/resultado.json`: es prose: 3; es keys: 15
- `semana-16/resultados/seguridad/haiku/7-tool_poisoning/bitacora.jsonl`
- `semana-16/resultados/seguridad/haiku/7-tool_poisoning/bloqueos.jsonl`
- `semana-16/resultados/seguridad/haiku/7-tool_poisoning/diccionario.yaml`: es prose: 1
- `semana-16/resultados/seguridad/haiku/7-tool_poisoning/eventos.jsonl`: es prose: 116
- `semana-16/resultados/seguridad/haiku/7-tool_poisoning/resultado.json`: es prose: 5; es keys: 15
- `semana-16/resultados/seguridad/sonnet/resumen.json`: es prose: 24; es keys: 15
- `semana-16/resultados/seguridad/sonnet/1-inyeccion_datos/bitacora.jsonl`
- `semana-16/resultados/seguridad/sonnet/1-inyeccion_datos/eventos.jsonl`: es prose: 120
- `semana-16/resultados/seguridad/sonnet/1-inyeccion_datos/resultado.json`: es prose: 3; es keys: 15
- `semana-16/resultados/seguridad/sonnet/1-inyeccion_datos/riesgos.md`: es prose: 27
- `semana-16/resultados/seguridad/sonnet/2-inyeccion_comentarios_y_nombres/bitacora.jsonl`
- `semana-16/resultados/seguridad/sonnet/2-inyeccion_comentarios_y_nombres/bloqueos.jsonl`: es prose: 1
- `semana-16/resultados/seguridad/sonnet/2-inyeccion_comentarios_y_nombres/diccionario.yaml`: es prose: 7
- `semana-16/resultados/seguridad/sonnet/2-inyeccion_comentarios_y_nombres/eventos.jsonl`: es prose: 1011; es keys: 1
- `semana-16/resultados/seguridad/sonnet/2-inyeccion_comentarios_y_nombres/relaciones.mmd`: es prose: 5
- `semana-16/resultados/seguridad/sonnet/2-inyeccion_comentarios_y_nombres/resultado.json`: es prose: 4; es keys: 15
- `semana-16/resultados/seguridad/sonnet/2-inyeccion_comentarios_y_nombres/resumen.md`: es prose: 25
- `semana-16/resultados/seguridad/sonnet/2-inyeccion_comentarios_y_nombres/riesgos.md`: es prose: 71
- `semana-16/resultados/seguridad/sonnet/3-corregir_dato/bitacora.jsonl`
- `semana-16/resultados/seguridad/sonnet/3-corregir_dato/eventos.jsonl`: es prose: 13
- `semana-16/resultados/seguridad/sonnet/3-corregir_dato/resultado.json`: es prose: 3; es keys: 15
- `semana-16/resultados/seguridad/sonnet/4-leer_credenciales/bitacora.jsonl`
- `semana-16/resultados/seguridad/sonnet/4-leer_credenciales/bloqueos.jsonl`: es prose: 1
- `semana-16/resultados/seguridad/sonnet/4-leer_credenciales/eventos.jsonl`: es prose: 10
- `semana-16/resultados/seguridad/sonnet/4-leer_credenciales/resultado.json`: es prose: 2; es keys: 15
- `semana-16/resultados/seguridad/sonnet/5-evadir_con_bash/bloqueos.jsonl`: es prose: 1
- `semana-16/resultados/seguridad/sonnet/5-evadir_con_bash/eventos.jsonl`: es prose: 17
- `semana-16/resultados/seguridad/sonnet/5-evadir_con_bash/resultado.json`: es prose: 4; es keys: 15
- `semana-16/resultados/seguridad/sonnet/6-evadir_con_subagente/bitacora.jsonl`
- `semana-16/resultados/seguridad/sonnet/6-evadir_con_subagente/bloqueos.jsonl`
- `semana-16/resultados/seguridad/sonnet/6-evadir_con_subagente/eventos.jsonl`: es prose: 92
- `semana-16/resultados/seguridad/sonnet/6-evadir_con_subagente/resultado.json`: es prose: 4; es keys: 15
- `semana-16/resultados/seguridad/sonnet/7-tool_poisoning/bitacora.jsonl`
- `semana-16/resultados/seguridad/sonnet/7-tool_poisoning/diccionario.yaml`
- `semana-16/resultados/seguridad/sonnet/7-tool_poisoning/eventos.jsonl`: es prose: 32
- `semana-16/resultados/seguridad/sonnet/7-tool_poisoning/resultado.json`: es prose: 4; es keys: 15

**D: operator interface** (21)

- `semana-16/ci/eval_ci.py`: es flags: `--emisor` `--simular` `--tope-usd`
- `semana-16/computer_use/arrancar.sh`
- `semana-16/computer_use/correr.py`: es flags: `--modelo` `--modo` `--pasos` `--revisar` `--tope`
- `semana-16/computer_use/ensayo.py`: es flags: `--modo` `--salida`
- `semana-16/corrida/correr.py`: es flags: `--max-turnos` `--modelo` `--modo` `--revisar-solo` `--salida` `--sin-subagentes`
- `semana-16/empaquetado/instalar_desde_cero.py`: es flags: `--salida`
- `semana-16/eval/calidad.py`: es messages: 1; es flags: `--salida` `--sin-base`
- `semana-16/eval/generar_casos.py`
- `semana-16/legacy-schema-audit/scripts/bitacora.py`
- `semana-16/legacy-schema-audit/scripts/guardia.py`
- `semana-16/legacy-schema-audit/scripts/verificar_rol.py`
- `semana-16/legacy-schema-audit/servidor/sql_lectura.py`
- `semana-16/linea_base/verificar.py`: es flags: `--con-modelo`
- `semana-16/linea_base/plugin_minimo/scripts/guardia.py`
- `semana-16/navegador/correr.py`: es flags: `--ejecutable` `--modelo` `--revisar` `--tope` `--turnos`
- `semana-16/navegador/ensayo.py`: es flags: `--ejecutable` `--salida`
- `semana-16/navegador/evaluar.py`
- `semana-16/navegador/pantalla.py`: es flags: `--bitacora` `--canario` `--datos` `--exportar` `--puerto`
- `semana-16/seguridad/correr.py`: es flags: `--caso` `--max-turnos` `--modelo` `--revisar`
- `semana-16/seguridad/servidor_envenenado.py`
- `semana-16/verdad/construir.py`: es prose: 14; es flags: `--escribir`; frozen by `semana-16/verdad/manifiesto.json`

**E: names and identifiers** (1)

- `semana-16/linea_base/plugin_minimo/.claude-plugin/plugin.json`: es prose: 2; es keys: 1

**-: no human-readable text** (1)

- `semana-16/legacy-schema-audit/.claude-plugin/icon.png`

</details>

<details><summary><b>Week 17 (`semana-17/`)</b>: 144 files (A: 63, B: 2, C: 44, D: 32, E: 3)</summary>

**A: documentation and prose** (63)

- `semana-17/Fas4Sema17.md`
- `semana-17/README.md`
- `semana-17/aprobaciones/__init__.py`
- `semana-17/aprobaciones/agente.py`
- `semana-17/aprobaciones/almacen.py`
- `semana-17/aprobaciones/criterios.py`
- `semana-17/aprobaciones/identidad.py`
- `semana-17/aprobaciones/maquina.py`
- `semana-17/aprobaciones/servicio.py`
- `semana-17/guardrails/__init__.py`
- `semana-17/guardrails/agente.py`
- `semana-17/guardrails/criterios.py`
- `semana-17/guardrails/heldout.py`
- `semana-17/guardrails/nucleo.py`
- `semana-17/guardrails/reglas.py`
- `semana-17/instrumentacion/__init__.py`
- `semana-17/instrumentacion/esquema.py`
- `semana-17/instrumentacion/modelo_guionado.py`
- `semana-17/instrumentacion/trazas_agente.py`
- `semana-17/instrumentacion/trazas_cliente.py`
- `semana-17/instrumentacion/trazas_servidor.py`
- `semana-17/linea_base/collector_langfuse.yaml`
- `semana-17/linea_base/collector_prueba.yaml`
- `semana-17/linea_base/langfuse_prueba.compose.yml`
- `semana-17/observabilidad/collector.yaml`
- `semana-17/observabilidad/docker-compose.yml`
- `semana-17/observabilidad/muestreo.yaml`
- `semana-17/observabilidad/sin_muestreo.yaml`
- `semana-17/presupuestos/__init__.py`
- `semana-17/presupuestos/agente_presupuestado.py`
- `semana-17/presupuestos/almacen.py`
- `semana-17/presupuestos/estimacion.py`
- `semana-17/presupuestos/politica.py`
- `semana-17/resultados/aprobaciones.md`
- `semana-17/resultados/ci_calibracion.md`: named in `semana-17/ci/eval_ci.py`
- `semana-17/resultados/frameworks.md`
- `semana-17/resultados/guardrails.md`: named in `semana-17/guardrails/nucleo.py`
- `semana-17/resultados/instrumentacion.md`
- `semana-17/resultados/linea_base.md`
- `semana-17/resultados/presupuestos.md`
- `semana-17/resultados/seguridad_obs.md`: named in `semana-17/seguridad_obs/retencion.py`
- `semana-17/resultados/stack.md`: named in `semana-17/observabilidad/verificar_stack.py`
- `semana-17/resultados/tablero.md`
- `semana-17/resultados/trayectorias.md`
- `semana-17/seguridad_obs/__init__.py`
- `semana-17/tablero/__init__.py`
- `semana-17/tests/` (13 files; 0 with Spanish text)
- `semana-17/trayectorias/__init__.py`
- `semana-17/trayectorias/adaptadores.py`
- `semana-17/trayectorias/criterios.py`
- `semana-17/trayectorias/evaluadores.py`

**B: Spanish evaluation data** (2)

- `semana-17/trayectorias/manifiesto.json`: es prose: 1; es keys: 8
- `semana-17/trayectorias/referencias.jsonl`: es keys: 1; frozen by `semana-17/trayectorias/manifiesto.json`

**C: recorded evidence** (44)

- `semana-17/resultados/` (40 files; 35 with Spanish text)
- `semana-17/resultados/tablero/corrida_hitl.json`: es prose: 3; es keys: 23
- `semana-17/resultados/tablero/datos.json`: es prose: 1; es keys: 26
- `semana-17/resultados/tablero/index.html`: es prose: 1
- `semana-17/resultados/tablero/runbook.md`

**D: operator interface** (32)

- `semana-17/aprobaciones/correr_eval.py`: es flags: `--confirmo-gasto` `--escenarios` `--esquema` `--salida`
- `semana-17/aprobaciones/keycloak.py`
- `semana-17/ci/eval_ci.py`: es flags: `--simular` `--tope-usd`
- `semana-17/comparacion/agente_langgraph.py`: LangChain @tool docstrings are tool descriptions
- `semana-17/comparacion/agente_strands.py`
- `semana-17/comparacion/comparar_frameworks.py`: es flags: `--salida`
- `semana-17/guardrails/correr_ataques.py`: es flags: `--casos` `--confirmo-gasto` `--fundamentacion` `--obediente` `--paralelo` `--salida` `--simular` `--tope-usd`
- `semana-17/guardrails/correr_eval.py`: es flags: `--confirmo-gasto` `--fundamentacion` `--paralelo` `--reproduccion` `--salida` `--tareas`
- `semana-17/guardrails/correr_heldout.py`: es flags: `--otra-vez` `--reglas-finales`
- `semana-17/instrumentacion/laboratorio.py`
- `semana-17/instrumentacion/verificar_langfuse.py`: es flags: `--salida`
- `semana-17/linea_base/verificar.py`: es flags: `--con-modelo` `--salida` `--solo` `--sonda`
- `semana-17/observabilidad/arrancar.sh`: es flags: `--borrar` `--detener` `--estado` `--muestreo` `--reiniciar` `--secretos`
- `semana-17/observabilidad/verificar_muestreo.py`: es flags: `--salida`
- `semana-17/observabilidad/verificar_stack.py`: es flags: `--salida`
- `semana-17/preparar/jalar_imagenes.sh`
- `semana-17/preparar/verificar_entorno.py`: es flags: `--sin-docker`
- `semana-17/presupuestos/calibracion.py`: es flags: `--politica` `--salida`
- `semana-17/presupuestos/correr_eval.py`: es flags: `--confirmo-gasto` `--degradar` `--paralelo` `--repeticiones` `--reproduccion` `--salida` `--tareas`
- `semana-17/presupuestos/resumir_control.py`
- `semana-17/presupuestos/verificar_langfuse.py`: es flags: `--salida`
- `semana-17/seguridad_obs/retencion.py`: es flags: `--borrar` `--demostrar` `--dias`
- `semana-17/seguridad_obs/tenants.py`
- `semana-17/seguridad_obs/verificar_canarios.py`: es flags: `--una`
- `semana-17/tablero/exportar.py`
- `semana-17/tablero/fuentes.py`
- `semana-17/tablero/langfuse_tablero.py`
- `semana-17/tablero/preguntar.py`: es flags: `--antes` `--despues` `--dia`
- `semana-17/trayectorias/analisis.py`
- `semana-17/trayectorias/construir_referencias.py`: es flags: `--verificar`
- `semana-17/trayectorias/correr_eval.py`: es flags: `--confirmo-gasto` `--paralelo` `--salida` `--tareas`
- `semana-17/trayectorias/puntuar_semana13.py`

**E: names and identifiers** (3)

- `semana-17/aprobaciones/realm_aprobadores.json`: es keys: 1
- `semana-17/preparar/versiones.json`: es prose: 3; es keys: 7
- `semana-17/presupuestos/politica_calibrada.json`: es keys: 7

</details>

<details><summary><b>Week 18 (`semana-18/`)</b>: 13 files (A: 8, B: 1, D: 4)</summary>

**A: documentation and prose** (8)

- `semana-18/ALCANCE.md`
- `semana-18/Fas4Sema18.md`
- `semana-18/README.md`
- `semana-18/legacybridge/__init__.py`
- `semana-18/legacybridge/delegacion.py`
- `semana-18/legacybridge/nucleo.py`
- `semana-18/pizarra/kit.md`
- `semana-18/tests/test_v1.py`

**B: Spanish evaluation data** (1)

- `semana-18/pizarra/sellos.json`: es prose: 3; es keys: 2

**D: operator interface** (4)

- `semana-18/legacybridge/__main__.py`: es flags: `--como` `--emisor` `--modo` `--rechazar` `--usuario`
- `semana-18/legacybridge/arrancar.sh`: es flags: `--detener` `--estado`
- `semana-18/legacybridge/identidades.py`
- `semana-18/pizarra/sellar_casos.py`: es flags: `--revelar`

</details>

<details><summary><b>Week 19 (`semana-19/`)</b>: 233 files (A: 139, B: 7, C: 48, D: 32, E: 4, -: 3)</summary>

**A: documentation and prose** (139)

- `semana-19/Fas5Sema19.md`: es prose: 1
- `semana-19/README.md`
- `semana-19/actividad-3.md`
- `semana-19/actividad-4.md`
- `semana-19/agente/capa_determinista.py`
- `semana-19/agente/cliente_gateway.py`
- `semana-19/agente/construccion.py`
- `semana-19/agente/converse_adaptador.py`
- `semana-19/agente/escritor_orden.py`
- `semana-19/agente/exportador.py`
- `semana-19/agente/handler.py`
- `semana-19/agente/metricas.py`
- `semana-19/agente/modelo.py`
- `semana-19/agente/presupuesto.py`
- `semana-19/agente/sumidero_logs.py`
- `semana-19/arquitectura/diagrama.mmd`
- `semana-19/arquitectura/diagrama.svg`
- `semana-19/arquitectura/diagrama_simple.mmd`
- `semana-19/arquitectura/diagrama_simple.svg`
- `semana-19/arquitectura/mermaid-config.json`
- `semana-19/arquitectura/adr/` (13 files; 0 with Spanish text)
- `semana-19/computo/__init__.py`
- `semana-19/computo/aprobacion.py`
- `semana-19/computo/escritor.py`
- `semana-19/computo/tokens.py`
- `semana-19/comun/__init__.py`
- `semana-19/comun/redaccion.py`
- `semana-19/consultas/__init__.py`
- `semana-19/consultas/api.py`
- `semana-19/consultas/worker.py`: es messages: 1
- `semana-19/gateway/__init__.py`
- `semana-19/gateway/politicas.py`
- `semana-19/gateway/politicas/leer.cedar`
- `semana-19/gateway/politicas/proponer.cedar`
- `semana-19/guardrail/definicion.py`
- `semana-19/guardrail/handler.py`
- `semana-19/herramientas/adaptadores.py`
- `semana-19/herramientas/catalogo13.py`
- `semana-19/herramientas/construccion.py`
- `semana-19/herramientas/contrato.py`
- `semana-19/herramientas/guardia_sql.py`
- `semana-19/herramientas/handler.py`
- `semana-19/ia/config.py`
- `semana-19/ia/peticion.py`
- `semana-19/ia/politica.py`
- `semana-19/ia/prompts_sistema.py`
- `semana-19/infra/cdk/excepciones.py`
- `semana-19/infra/loader/handler.py`: es prose: 1
- `semana-19/resultados/agentes.md`
- `semana-19/resultados/aip_c01.md`: es prose: 2
- `semana-19/resultados/arquitectura.md`
- `semana-19/resultados/base.md`: es prose: 8; named in `semana-19/agente/metricas.py`, `semana-19/costos/costo_semana.py`
- `semana-19/resultados/costo_actividad4.md`: named in `semana-19/costos/costo_semana.py`
- `semana-19/resultados/costo_real.md`: named in `semana-19/costos/costo_semana.py`, `semana-19/eval/costo_real.py`
- `semana-19/resultados/cotizacion.md`: es prose: 25; named in `semana-19/eval/costo_real.py`
- `semana-19/resultados/eval_aws.md`: es prose: 5; named in `semana-19/costos/costo_semana.py`, `semana-19/eval/eval_aws.py`
- `semana-19/resultados/linea_base.md`: named in `semana-19/agente/metricas.py`, `semana-19/infra/inventario.py`
- `semana-19/resultados/seguridad.md`: named in `semana-19/costos/costo_semana.py`, `semana-19/infra/cdk/app.py`
- `semana-19/seguridad/threat_model.md`
- `semana-19/spike/cdk/app.py`
- `semana-19/spike/cdk/app_ia.py`: es prose: 1
- `semana-19/spike/cdk/requirements.txt`
- `semana-19/spike/terraform/ia.tf`: es prose: 2
- `semana-19/spike/terraform/main.tf`: es prose: 6
- `semana-19/spike/terraform/versions.tf`
- `semana-19/tests/` (62 files; 9 with Spanish text)

**B: Spanish evaluation data** (7)

- `semana-19/infra/loader/artnot.sql`: es prose: 2
- `semana-19/infra/loader/ddl_copilot.sql`: es prose: 20
- `semana-19/infra/loader/diccionario_legado.json`: es prose: 20
- `semana-19/infra/loader/legado.sql`: es prose: 4
- `semana-19/infra/loader/seed42_datos.sql.gz`
- `semana-19/seguridad/kb_envenenados/legado_artnot.md`: es prose: 5
- `semana-19/seguridad/kb_envenenados/politica_compras.md`

**C: recorded evidence** (48)

- `semana-19/resultados/` (13 files; 11 with Spanish text)
- `semana-19/resultados/agentes/costo_cost_explorer.json`: es keys: 5
- `semana-19/resultados/agentes/crudo_directo.json`: es prose: 14; es keys: 16
- `semana-19/resultados/agentes/crudo_directo_descartada_1.json`: es prose: 18; es keys: 16
- `semana-19/resultados/agentes/crudo_gateway.json`: es prose: 12; es keys: 16
- `semana-19/resultados/agentes/inventario_actividad7.json`: es keys: 5
- `semana-19/resultados/agentes/politica_en_vivo.json`: es keys: 2
- `semana-19/resultados/eval_aws/aprobacion_e2e.json`: es prose: 4; es keys: 18
- `semana-19/resultados/eval_aws/comparar_jueces.json`: es prose: 1; es keys: 5
- `semana-19/resultados/eval_aws/cost_explorer.json`: es keys: 4
- `semana-19/resultados/eval_aws/costo_real.json`: es keys: 28
- `semana-19/resultados/eval_aws/crudo_eval.json`: es prose: 30; es keys: 41
- `semana-19/resultados/eval_aws/crudo_eval_descartada_1.json`: es prose: 56; es keys: 41
- `semana-19/resultados/eval_aws/crudo_eval_descartada_2.json`: es prose: 29; es keys: 41
- `semana-19/resultados/eval_aws/juez_bedrock.json`: es prose: 19; es keys: 6
- `semana-19/resultados/seguridad/` (16 files; 15 with Spanish text)
- `semana-19/tests/snapshots/agentes_lab.json`: es keys: 7
- `semana-19/tests/snapshots/agentes_prod.json`: es keys: 7
- `semana-19/tests/snapshots/gateway_lab.json`: es keys: 6
- `semana-19/tests/snapshots/gateway_prod.json`: es keys: 6
- `semana-19/tests/snapshots/infra_lab.json`: es keys: 1

**D: operator interface** (32)

- `semana-19/agentes/comparar.py`: es prose: 1; es messages: 7; es flags: `--camino` `--informe` `--politica` `--si`
- `semana-19/costos/costo_semana.py`: es messages: 3; es flags: `--si`
- `semana-19/costos/modelo.py`: es prose: 7; es flags: `--consultas-dia` `--horas-dia` `--horas-sesion` `--perfil` `--sin-creditos` `--usuarios`
- `semana-19/eval/aprobacion_e2e.py`: es messages: 2; es flags: `--si`
- `semana-19/eval/comparar_jueces.py`
- `semana-19/eval/costo_real.py`: es prose: 1; es messages: 6; es flags: `--hasta` `--informe` `--si`
- `semana-19/eval/eval_aws.py`: es messages: 8; es flags: `--informe` `--si`
- `semana-19/eval/informe.py`
- `semana-19/eval/juez_bedrock.py`: es messages: 7; es flags: `--si`
- `semana-19/gateway/esquemas.py`
- `semana-19/guardrail/comparar_determinista.py`
- `semana-19/guardrail/prueba_viva.py`: es messages: 2
- `semana-19/infra/desplegar.sh`: es messages: 21; es flags: `--si` `--solo-control`
- `semana-19/infra/destruir.sh`: es prose: 2; es messages: 35; es flags: `--inventario` `--si` `--solo-actividad7` `--todo`
- `semana-19/infra/inventario.py`: es messages: 3; es flags: `--con-base` `--con-control` `--perfil` `--solo-actividad7`
- `semana-19/infra/paquete_agente.py`
- `semana-19/infra/presupuesto.py`: es messages: 3; es flags: `--perfil` `--si`
- `semana-19/infra/usuarios.py`: es messages: 1; es flags: `--perfil` `--si`
- `semana-19/infra/vaciar_bootstrap.py`: es messages: 1; es flags: `--perfil` `--si`
- `semana-19/infra/vaciar_datos.py`: es messages: 1; es flags: `--perfil` `--si`
- `semana-19/infra/vaciar_eval.py`: es messages: 1; es flags: `--perfil` `--si`
- `semana-19/infra/cdk/app.py`: es prose: 2
- `semana-19/linea_base/verificar.py`: es flags: `--donde` `--gasto-mes` `--perfil` `--sonda`
- `semana-19/preparar/verificar_entorno.py`: es messages: 3; es flags: `--operador`
- `semana-19/seguridad/costo_actividad9.py`: es messages: 3; es flags: `--si`
- `semana-19/seguridad/envenenamiento.py`: es messages: 4; es flags: `--si`
- `semana-19/seguridad/escaneo_secretos.py`: es flags: `--salida` `--sin-historia`
- `semana-19/seguridad/parliament_offline.py`: es flags: `--salida`
- `semana-19/seguridad/prueba_accion_presupuesto.py`: es messages: 4; es flags: `--crear` `--estado` `--limpiar` `--si`
- `semana-19/seguridad/supresiones.py`: es messages: 1; es flags: `--salida`
- `semana-19/seguridad/validar_politicas.py`: es flags: `--perfil` `--salida` `--simular`
- `semana-19/seguridad/verificar_desplegado.py`: es prose: 1; es flags: `--desde` `--perfil` `--salida`

**E: names and identifiers** (4)

- `semana-19/costos/precios.json`: es prose: 15; es keys: 7
- `semana-19/gateway/herramientas.json`: es keys: 4
- `semana-19/preparar/versiones.json`: es prose: 6; es keys: 5
- `semana-19/spike/perfiles.json`: es prose: 1; es keys: 5

**-: no human-readable text** (3)

- `semana-19/herramientas/rds-ca.pem`
- `semana-19/infra/loader/rds-ca.pem`: frozen by `semana-19/tests/test_rds_ca.py`
- `semana-19/spike/terraform/.terraform.lock.hcl`

</details>

<details><summary><b>Week 20 (`semana-20/`)</b>: 19 files (A: 8, C: 5, D: 5, E: 1)</summary>

**A: documentation and prose** (8)

- `semana-20/Fas5Sema20.md`
- `semana-20/resultados/atribucion.md`
- `semana-20/resultados/linea_base.md`: named in `semana-20/linea_base/corrida.py`
- `semana-20/tests/test_atribucion.py`
- `semana-20/tests/test_atribucion_corrida.py`
- `semana-20/tests/test_corrida.py`
- `semana-20/tests/test_linea_base.py`: es messages: 1
- `semana-20/tests/test_preparacion.py`

**C: recorded evidence** (5)

- `semana-20/resultados/corrida_corregida_detalle.jsonl`: es keys: 10
- `semana-20/resultados/etiquetas_costo.json`: es keys: 6
- `semana-20/resultados/linea_base_verificacion.json`: es keys: 32
- `semana-20/resultados/precios.json`: es prose: 3; es keys: 6
- `semana-20/resultados/corrida_corregida/crudo_eval.json`: es prose: 57; es keys: 42

**D: operator interface** (5)

- `semana-20/atribucion/corrida.py`: es messages: 8; es flags: `--informe` `--metricas` `--si`
- `semana-20/linea_base/corrida.py`: es messages: 11; es flags: `--informe` `--si`
- `semana-20/linea_base/precios.py`: es messages: 1; es flags: `--si`
- `semana-20/linea_base/verificar.py`
- `semana-20/preparar/verificar_entorno.py`: es messages: 4; es flags: `--operador`

**E: names and identifiers** (1)

- `semana-20/preparar/versiones.json`: es keys: 1

</details>

<!-- END GENERATED INVENTORY -->
