# Week 7 schemas (Spanish data)

[Glossary](../glossary.md) · [Week 7 README](../../semana-07/README.md)

This guide describes the two database schemas that `run_eval.py` puts in the system prompt of the text-to-SQL models. `--esquema corto`
(the default) uses `schema.sql`; `--esquema completo` uses `schema_completo.sql`, to test the effect of a longer
context. The CI database is also created from `schema_completo.sql`. The question sets are in
[`datasets/`](../../semana-07/datasets/README.md) and the runs are in [`resultados/`](../../semana-07/resultados/README.md); each folder has its own
README.

**Why it is in Spanish:** the table and column names are English, but the schemas carry Spanish value hints (for
example the category names) and, in the full snapshot, the original Spanish comments of `inventory-copilot`. They
are part of the prompt that was measured, so they stay as they are.

## Files

| File | What it is | Written by / Read by |
|---|---|---|
| `schema.sql` | The short schema given to the model: only the columns the questions use, with value hints | Read by `run_eval.py` |
| `schema_completo.sql` | The full schema snapshot of `inventory-copilot` (its `db/init` files 01 to 03), with the roles, grants and extensions left out and the same value hints as `schema.sql` | Read by `run_eval.py --esquema completo` and `ci/preparar_base.py` |
