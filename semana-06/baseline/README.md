# Week 6 eval baseline (recorded evidence)

[Glossary](../../docs/glossary.md) · [Week 6 README](../README.md)

The baseline that every eval run is compared with. `evaluar.py --actualizar-base` saves its run here, and every later
run of `evaluar.py` reads it: the run fails if a case that passed in the baseline now fails, or if the pass rate
drops by more than the tolerance (0.05). The file is the same report as the run it was saved from, `eval_20261022T041329Z.json` in
[`../resultados/`](../resultados/README.md): 16 cases, all passing. It is versioned in Git, and an update goes in the same commit as the
change that justifies it.

**Recorded evidence:** this is the raw output of the run, kept exactly as recorded (not edited, not translated). The
model outputs and the judge's reasons are Spanish. The English summary is in the week README:
[Regression](../README.md#regression) and [Status](../README.md#status). It was written by an earlier version of
`evaluar.py`, before each case was repeated, so it has no `aprobados` or `repeticiones` keys.

## Files

| File | What it is | Written by / Read by |
|---|---|---|
| `resultados_base.json` | The baseline report: the run's settings, pass rate and per-case results | Written by `evaluar.py --actualizar-base`; read by `evaluar.py` |

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
