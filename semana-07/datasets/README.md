# Week 7 NLQ-Inventory question sets (Spanish data)

[Glossary](../../docs/glossary.md) · [Week 7 README](../README.md)

The bilingual question sets of the NLQ-Inventory evaluation. Each line is one question in one language (`-es` or
`-en` at the end of its id), with its reference SQL over the synthetic `inventory-copilot` database. Each set has a
validated version (`*_validado.jsonl`): `run_eval.py --validar --set <set>` runs every reference SQL and keeps only the
lines whose reference runs and returns rows, so that an empty result cannot count as a correct answer. The evaluation runs
read the validated version. The follow-up and chain sets also carry the previous turns of the conversation. Prompts
are not tuned on the sets, but some follow-up and chain questions were reworded after their results were read. The
week README describes each set and lists those rewordings: [Dataset](../README.md#dataset) and the iteration
sections that follow it.

**Why it is in Spanish:** the lab measures text-to-SQL in Spanish and in English, so each question exists in both
languages, and the Spanish half is the point of the measurement. Translating it would remove what was measured. The
keys are English; the Spanish ones are explained below.

## Files

| File | What it is | Written by / Read by |
|---|---|---|
| `nlq_bilingual.jsonl` | The easy set: 100 questions per language, generated from templates over the synthetic data | Written by `build_dataset.py`; read by `run_eval.py --validar` (`--set facil`, the default) |
| `nlq_hard_bilingual.jsonl` | The harder set: 48 hand-written questions per language, each stating its own definitions (time window, threshold, tie-break) so that it has one correct answer | Written by `build_hard_dataset.py`; read by `run_eval.py --validar --set dificil` |
| `nlq_seguimiento.jsonl` | The follow-up set: 20 questions per language, each depending on one previous turn | No script in the repository writes it; read by `run_eval.py --validar --set seguimiento` |
| `nlq_cadenas.jsonl` | The chain set: 16 chains per language, each a final question that depends on two previous turns. Committed before any run; `cad-14` was reworded twice afterward | Written by `build_cadenas_dataset.py`; read by `run_eval.py --validar --set cadenas` |
| `*_validado.jsonl` | The validated version of each set: `nlq_validado.jsonl` (easy), `nlq_hard_validado.jsonl`, `nlq_seguimiento_validado.jsonl`, `nlq_cadenas_validado.jsonl`. Only the harder set loses lines: 43 of 48 questions per language remain | Written by `run_eval.py --validar`; read by `run_eval.py` |

## Keys

| Key | Meaning |
|---|---|
| `ejemplos` | The previous turns, sent to the model as earlier conversation: `entrada` (the earlier question) and `salida` (its reference SQL). Reference SQL is used so that model errors do not carry into the next turn. `--sin-historial` leaves them out |
| `entrada` | An earlier question, in the language of the line |
| `salida` | The reference SQL of the earlier question |
| `tags` | Labels of the question. Most are English; the Spanish ones are `seguimiento` (follow-up), `cadena_3_turnos` (three-turn chain), `encadenado` (chained), `correccion` (the user corrects the previous turn), `referencia_lejana` (refers to a turn two steps back), `elipsis` (ellipsis), `filtro` (filter), `mismo_metrica` (same metric), `estado` (status), `fecha` (date), `porcentaje` (percentage), `promedio` (mean), `resta` (subtraction) |
