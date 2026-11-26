# Week 6 eval runs (recorded evidence)

[Glossary](../../docs/glossary.md) · [Week 6 README](../README.md)

The report of each `evaluar.py` run, named by its UTC timestamp. There are two runs, of 16 cases each, and both pass
all 16. Each report has the run's settings, its pass rate,
and the per-case result: the output obtained, the tool calls for the tool-use cases, and the LLM judge's verdict for
the summaries it scores. The later of the two runs is identical to the baseline in
[`../baseline/`](../baseline/README.md).

**Recorded evidence:** these are the raw outputs of the runs, kept exactly as recorded (not edited, not translated).
The model outputs and the judge's reasons are Spanish. The English summary is in the week README:
[Status](../README.md#status). They were written by an earlier version of `evaluar.py`, before each case was
repeated, so they have no `aprobados` or `repeticiones` keys.

## Files

| File | What it is | Written by / Read by |
|---|---|---|
| `eval_*.json` | One report per run | Written by `evaluar.py` |

## Keys

| Key | Meaning |
|---|---|
| `fecha` | Timestamp of the run, in UTC (`YYYYMMDDTHHMMSSZ`) |
| `modelo` | The model that generates the outputs |
| `juez` | At the top level: the judge model. In a case: the judge's verdict, with `fidelidad` (faithfulness score, 1 to 5) and `motivo` (the judge's reason, in Spanish) |
| `casos` | Number of cases |
| `tasa` | Pass rate |
| `resultados` | Per-case results |
| `id` | The gold-set case id |
| `plantilla` | The week 5 template the case uses |
| `ok` | The case passed |
| `obtenido` | The output obtained: a label, the extracted JSON, or the summary text |
| `herramientas` | For tool-use cases: the tool calls made, with `nombre` (tool name) and `entrada` (its input) |
