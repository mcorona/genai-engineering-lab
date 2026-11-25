# Week 7 NLQ-Inventory question sets (Spanish data)

[Glossary](../../docs/glossary.md) · [Week 7 README](../README.md)

The bilingual question sets of the NLQ-Inventory evaluation. Each line is one question in one language (`-es` or
`-en` at the end of its id), with its reference SQL over the synthetic `inventory-copilot` database. Each set has a
validated version (`*_validado.jsonl`): `run_eval.py --validar --set <set>` runs every reference SQL and keeps only the
questions whose reference returns rows, so that an empty result cannot count as a correct answer. The evaluation runs
read the validated version. The follow-up and chain sets also carry the previous turns of the conversation. The
sets are held out for measurement: prompts are not tuned on them. The week README describes each set and the
rewordings made after some runs: [Dataset](../README.md#dataset) and the iteration sections that follow it.

**Why it is in Spanish:** the lab measures text-to-SQL in Spanish and in English, so each question exists in both
languages, and the Spanish half is the point of the measurement. Translating it would remove what was measured. The
keys are English; the Spanish ones are explained below.

## Files

| File | What it is | Written by / Read by |
|---|---|---|
| `nlq_bilingual.jsonl` | The easy set: questions generated from templates | Written by `build_dataset.py`; read by `run_eval.py --validar` (`--set facil`, the default) |
| `nlq_hard_bilingual.jsonl` | The harder set: hand-written questions, each with its own tie-break and rounding rule | Written by `build_hard_dataset.py`; read by `run_eval.py --validar --set dificil` |
| `nlq_seguimiento.jsonl` | The follow-up set: a question that depends on one previous turn | No script in the repository writes it; read by `run_eval.py --validar --set seguimiento` |
| `nlq_cadenas.jsonl` | The chain set: a final question that depends on two previous turns. Committed before any run | Written by `build_cadenas_dataset.py`; read by `run_eval.py --validar --set cadenas` |
| `*_validado.jsonl` | The validated version of each set: `nlq_validado.jsonl` (easy), `nlq_hard_validado.jsonl`, `nlq_seguimiento_validado.jsonl`, `nlq_cadenas_validado.jsonl` | Written by `run_eval.py --validar`; read by `run_eval.py` |

## Keys

| Key | Meaning |
|---|---|
| `ejemplos` | The previous turns, sent to the model as earlier conversation: `entrada` (the earlier question) and `salida` (its reference SQL). Reference SQL is used so that model errors do not carry into the next turn. `--sin-historial` leaves them out |
| `entrada` | An earlier question, in the language of the line |
| `salida` | The reference SQL of the earlier question |
| `tags` | Labels of the question. Most are English; the Spanish ones are `seguimiento` (follow-up), `cadena_3_turnos` (three-turn chain), `encadenado` (chained), `correccion` (the user corrects the previous turn), `referencia_lejana` (refers to a turn two steps back), `elipsis` (ellipsis), `filtro` (filter), `mismo_metrica` (same metric), `estado` (status), `fecha` (date), `porcentaje` (percentage), `promedio` (mean), `resta` (subtraction) |
