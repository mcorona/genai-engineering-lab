# Week 16 ground truth (Spanish data)

[Glossary](../../docs/glossary.md) · [Week 16 README](../README.md)

The answer key of the legacy schema audit: the correct data dictionary of the `legado` schema, the risks seeded in it
with their evidence, the business rules that live outside the database and the injected notes. `construir.py` computes
the truth from the database catalog and the data, plus the hand labels of `etiquetas.json`, and freezes it with a hash
manifest. `eval/calidad.py`, `corrida/correr.py`, `ci/eval_ci.py` and `navegador/evaluar.py` read it to score the
plugin. [`../resultados/verdad.md`](../resultados/verdad.md) explains how each field is computed, in English.

**Why it is in Spanish:** the lab audits a Spanish legacy schema, so the meanings, risk descriptions, labels and note
texts are Spanish, and so are the keys the evaluators read. The plugin is scored against these exact files.
Translating them would change what was measured and break the manifest's hashes. The main keys are explained below.

`manifiesto.json` pins the SHA-256 of `diccionario.json`, `riesgos.json`, `etiquetas.json`, `riesgos.sql` and
`construir.py` (`tests/test_verdad.py` checks them). This README is not hashed.

## Files

| File(s) | What it is | Written by / Read by |
|---|---|---|
| `riesgos.sql` | Creates two native legacy tables, `prvcto` (supplier contacts) and `movinv` (inventory movements), with the seeded risks. All personal data is synthetic | Written by hand; applied by the `eval-semana-16` workflow; `corrida/correr.py` reads its seeded personal values to check that none leaked into a deliverable |
| `etiquetas.json` | The hand labels: meanings of the native tables, logical foreign keys, units, personal-data columns and hard negatives, each seeded risk with its evidence query, and the type of each injected note | Written by hand; read by `construir.py` |
| `construir.py` | Computes the truth from the catalog and the data. `--escribir` freezes it; with no flags it recomputes and compares | Run by hand; imported by `tests/test_verdad.py` |
| `diccionario.json` | The correct data dictionary, one object per column | `construir.py --escribir`; read by `eval/calidad.py`, `corrida/correr.py`, `ci/eval_ci.py`, `navegador/evaluar.py` |
| `riesgos.json` | The seeded risks with their recomputed evidence, the rules that live outside the database, and the injected and clean notes | `construir.py --escribir`; read by `eval/calidad.py`, `corrida/correr.py` |
| `manifiesto.json` | Counts and SHA-256 hashes that freeze the files above | `construir.py --escribir`; read by `tests/test_verdad.py` |

## Keys

| Key | Meaning |
|---|---|
| `tabla`, `columna` | Table, column (legacy names) |
| `original` | The table and column of the modern schema that the legacy view maps, or `null` for native tables |
| `significado` | Meaning of the column |
| `tipo` | Data type, from the catalog |
| `llave_primaria` | Primary key (`true` or `false`) |
| `llave_foranea` | Foreign key: the referenced `table.column`, or `null` |
| `fuente_llave_foranea` | Source of the foreign key: `restriccion_tabla_base` (a constraint of the base table) or `etiqueta` (a hand label: a logical key that is not declared) |
| `unidad` | Unit of measure |
| `datos_personales` | Personal data (PII). In `etiquetas.json`, the personal-data columns with what each one holds |
| `no_personales` | Hard negatives: columns that look personal but are not |
| `significados_nativos` | Meanings of the native tables and their columns |
| `fk_logicas` | Logical foreign keys (inferred from the data, not declared) |
| `unidades` | Units per column |
| `riesgos` | Seeded risks |
| `categoria` | Risk category: `datos_personales` (personal data), `huerfanos` (orphan rows), `duplicados` (duplicates), `nulos_en_clave` (nulls in a key), `unidades_inconsistentes` (inconsistent units), `reglas_fuera_de_la_base` (rules outside the database), `instrucciones_inyectadas` (injected instructions) |
| `descripcion` | Description |
| `sql`, `evidencia` | The evidence query, and the ids or values it returns |
| `reglas_fuera_de_la_base` | Business rules that live outside the database; each has `nombre` (name), `fuente` (source) and `columnas_citadas` (cited columns) |
| `notas_inyectadas`, `notas_limpias` | Injected notes of `legado.artnot` (with `not_id`, `not_art`, `tipo` and `sha256_texto`, the hash of the note text), and the ids of the clean notes |
| `inyecciones` | The type of each injected note, by note id |
| `tablas`, `columnas`, `llaves_primarias`, `llaves_foraneas` | Counts in the manifest: tables, columns, primary keys, foreign keys |
| `riesgos_por_categoria` | Seeded risks per category |
