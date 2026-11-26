# Week 2 preliminary variability run, N = 5 (recorded evidence)

[Glossary](../../docs/glossary.md) · [Week 2 README](../README.md)

A preliminary run of the response-variability experiment with 5 responses per condition, made before moving to 20.
It was written by an earlier version of `variabilidad.py`, so its summary has fewer columns than the later runs in
[`../corridas/`](../corridas/README.md). The week's conclusions do not use it.

**Recorded evidence:** these are the raw outputs of the run, kept exactly as recorded (not edited, not translated).
The responses are the model's Spanish answers. The English summary of the variability results, from the runs with
N = 20, is in the week README: [Part 2: response variability](../README.md#part-2-response-variability).

## Files

| File | What it is | Written by / Read by |
|---|---|---|
| `variabilidad_respuestas.csv` | Every response: one row per condition and response | Written by `variabilidad.py` (earlier version) |
| `variabilidad_resumen.csv` | The variability of each condition (no deviation or interval yet) | Written by `variabilidad.py` (earlier version) |
| `variabilidad.png` | The run's chart: variability against `temperature` and against `top_p` | Written by `variabilidad.py` (earlier version) |

## Keys

| Key | Meaning |
|---|---|
| `barrido` | The parameter swept: `temperature` (with `top_p` = 1.0) or `top_p` (with `temperature` = 1.0) |
| `valor` | The value of the swept parameter |
| `corrida` | The number of the response within its condition (1 to 5), not a run |
| `respuesta` | The model's response, in Spanish |
| `variabilidad` | 1 minus the mean Jaccard similarity between the responses of a condition (0 = all identical) |
