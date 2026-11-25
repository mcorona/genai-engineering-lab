# Week 13 data outside the gold set and results folders (Spanish data)

[Glossary](../glossary.md) · [Week 13 README](../../semana-13/README.md)

The Spanish data files of week 13 that sit outside a folder with its own README. The task gold set is described in
[`golden/README.md`](../../semana-13/golden/README.md) and the recorded runs in [`resultados/README.md`](../../semana-13/resultados/README.md).

- `herramientas/diccionario_extra.json` extends the data dictionary that the `describir_esquema` tool returns with the
  `artnot` table. `herramientas/herramientas.py` merges it into the dictionary it loads.
- `seguridad/artnot.sql` creates `legado.artnot`, a legacy free-text notes table per article, and grants read access to
  the read-only roles. Some notes carry injected instructions on purpose: they are the prompt injection in SQL results
  that the security suite tests (section 7 of the [week 13 README](../../semana-13/README.md)). `seguridad/correr.py` and
  `ci/eval_ci.py` load it with the admin role; week 19 loads a copy into the deployed database.

**Why it is in Spanish:** the lab measures a Spanish-language agent over a Spanish legacy schema. The dictionary
entries and the notes, including the injected ones, are what the agent read; translating them would change what was
measured. Two of the injected notes are in English.

## Files

| File(s) | What it is | Written by / Read by |
|---|---|---|
| `herramientas/diccionario_extra.json` | Data dictionary entry for `artnot`: table description and the meaning of each column | Read by `herramientas/herramientas.py` |
| `seguridad/artnot.sql` | Creates and seeds `legado.artnot` (notes per article, some with injected instructions) and grants `SELECT` to `copilot_ro` and `copilot_nlq` | Run by `seguridad/correr.py` and `ci/eval_ci.py`; checked for presence by `semana-19/preparar/verificar_entorno.py` |

## Keys

| Key | Meaning |
|---|---|
| `artnot` | The legacy notes table: free-text warehouse notes per article |
| `descripcion` | Description of the table |
| `columnas` | The table's columns and their meaning: `not_id` (note ID), `not_art` (article, a reference to `artmst.art_cd`), `not_txt` (note text), `not_fch` (note date) |
| `not_id`, `not_art`, `not_txt`, `not_fch` | The columns of `legado.artnot`: note ID, article code, note text, note date |
