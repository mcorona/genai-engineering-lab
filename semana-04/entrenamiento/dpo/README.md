# Week 4 DPO preference set (recorded evidence)

[Glossary](../../../docs/glossary.md) · [Week 4 README](../../README.md) · [Distillation and DPO README](../README.md)

The preference pairs for DPO: for each training question where the teacher's result did not match the reference,
`chosen` is the reference SQL and `rejected` is the teacher's SQL. `construir_datasets.py` builds the file from the
teacher answers in [`../data/`](../data/README.md). DPO was not trained: the installed mlx-lm CLI has no DPO mode,
so no script reads this file yet.

**Recorded evidence:** this file is the preference set built from the recorded teacher run, kept exactly as written
(not edited, not translated). The questions and the system prompt are the Spanish ones of week 3. The decision on DPO
is explained in English in [Decision on DPO](../README.md#decision-on-dpo).

## Files

| File | What it is | Written by / Read by |
|---|---|---|
| `train.jsonl` | The preference pairs, one per line: `prompt` (system prompt and question), `chosen`, `rejected` | Written by `construir_datasets.py`; not read by any script (DPO was not trained) |
