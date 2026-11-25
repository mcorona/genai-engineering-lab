# Week 2 variability runs (recorded evidence)

[Glossary](../../docs/glossary.md) · [Week 2 README](../README.md)

The runs of the response-variability experiment, one folder per run. In each run, `variabilidad.py` asks the local
model the same Spanish prompt N times per condition (a `temperature` sweep and a `top_p` sweep), then measures how
much the responses differ. The script writes its outputs to the week folder; each run's files were then saved here.
The deliverable notebook (`entregable_semana2.ipynb`) reads every `run*/variabilidad_respuestas.csv` and combines the
runs.

**Recorded evidence:** these are the raw outputs of the runs, kept exactly as recorded (not edited, not translated).
The responses are the model's Spanish answers. The English summary of the results, with the per-run figures and the
combined confidence intervals, is in the week README:
[Part 2: response variability](../README.md#part-2-response-variability).

## Files

| File | What it is | Written by / Read by |
|---|---|---|
| `run*/variabilidad_respuestas.csv` | Every response of the run: one row per condition and response | Written by `variabilidad.py`; read by `entregable_semana2.ipynb` |
| `run*/variabilidad_resumen.csv` | The variability of each condition, with its standard deviation and 95% confidence interval | Written by `variabilidad.py` |
| `run*/variabilidad.png` | The run's chart: variability against `temperature` and against `top_p` | Written by `variabilidad.py` |

## Keys

| Key | Meaning |
|---|---|
| `barrido` | The parameter swept: `temperature` (with `top_p` = 1.0) or `top_p` (with `temperature` = 1.0) |
| `valor` | The value of the swept parameter |
| `corrida` | The number of the response within its condition (1 to N), not the run. The run is the folder name |
| `respuesta` | The model's response, in Spanish |
| `n` | Number of responses per condition (20 in every run) |
| `variabilidad` | 1 minus the mean Jaccard similarity between the responses of a condition (0 = all identical) |
| `desv_estandar` | Standard deviation of the per-response variability |
| `ic95_inf`, `ic95_sup` | Lower and upper bounds of the 95% confidence interval |
