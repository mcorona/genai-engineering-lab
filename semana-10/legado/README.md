# Week 10 legacy schema (Spanish data)

[Glossary](../../docs/glossary.md) · [Week 10 README](../README.md)

The legacy schema of activity 2 (text-to-SQL over a legacy schema). It renames the inventory-copilot tables and
columns with short, cryptic Spanish names, as many old business systems do, without changing the data. The model
must write SQL against these names, with or without the data dictionary. The [glossary](../../docs/glossary.md#the-legacy-schema)
gives the English meaning of every table and column. The results are in
[`../resultados/sql_legado.md`](../resultados/sql_legado.md).

Later weeks reuse these files: week 13's tools read the data dictionary, and the CI workflows of weeks 13 to 18
(`eval-semana-13` to `eval-semana-18`) load `legado.sql` into their test database.

**Why it is in Spanish:** the cryptic names are the point of the experiment: they test whether a model can map a
question to an unfamiliar schema. The data dictionary is the Spanish documentation the model receives in the prompt.
Translating either would change what was measured.

## Files

| File(s) | What it is | Written by / Read by |
|---|---|---|
| `legado.sql` | Creates schema `legado`: one view with cryptic names per inventory-copilot table, and read access for `copilot_ro` | Run with an admin role before the experiment. Run by `../ci/eval_ci.py`, `semana-13/ci/eval_ci.py` and the CI workflows of weeks 13 to 18 |
| `esquema_legado.sql` | The legacy DDL that the model sees in its prompt: the same tables and columns as `CREATE TABLE` statements, with no data | Read by `../experimentos/sql_legado.py` |
| `diccionario.json` | The data dictionary: for each legacy table, its original name, a Spanish description and a Spanish description of each column | Read by `../experimentos/sql_legado.py` and `semana-13/herramientas/herramientas.py` |

## Keys

| Key | Meaning |
|---|---|
| `original` | The original inventory-copilot table that the legacy table renames |
| `descripcion` | Description of the table, in Spanish |
| `columnas` | The columns: legacy column name → Spanish description |
