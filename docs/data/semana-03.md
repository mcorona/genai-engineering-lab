# Week 3 business rules (Spanish data)

[Glossary](../glossary.md) · [Week 3 README](../../semana-03/README.md)

The business rules of the legacy billing and inventory schema, numbered, that the model must apply when it writes
SQL. `evaluar_sql.py --reglas` appends the whole file to the system prompt, and `evaluar_sql.py --rag` appends only
the rules that `rag_reglas.py` selects by keyword. In week 4, `entrenamiento/generar_teacher.py` gives the same rules
to the teacher model. The question and SQL pairs are in [`data/`](../../semana-03/data/README.md) and the runs are in
[`resultados/`](../../semana-03/resultados/README.md); each folder has its own README.

**Why it is in Spanish:** the rules are part of the prompt, and the lab measures a model that answers Spanish
questions with Spanish instructions. Translating them would change the prompt that was measured. The
[Data](../../semana-03/README.md#data) section of the week README lists what the rules cover, in English.

## Files

| File | What it is | Written by / Read by |
|---|---|---|
| `reglas_legado.md` | The numbered business rules of the legacy schema (current records, amounts stored as text, `CHAR(8)` dates, currency, invoice lines, stock, units, and free text treated as data) | Taken from the LegacyBridge defect list (no script writes it); read by `evaluar_sql.py`, `rag_reglas.py` and `../semana-04/entrenamiento/generar_teacher.py` |
