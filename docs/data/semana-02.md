# Week 2 data and results (recorded evidence)

[Glossary](../glossary.md) · [Week 2 README](../../semana-02/README.md)

This guide describes the input texts of the token count and the results files that the week 2 scripts write to the
week folder. The runs
of the variability experiment are in [`corridas/`](../../semana-02/corridas/README.md), and the preliminary runs with 5 responses
per condition are in [`resultados-n5/`](../../semana-02/resultados-n5/README.md); each folder has its own README.

**Why it is in Spanish:** `texto_es.txt` is the Spanish text whose token count is measured, and `texto_en.txt` is the
same content in English, for the comparison. Translating the Spanish text would remove what was measured.

**Recorded evidence:** the CSV and PNG files are the raw outputs of the runs, kept exactly as recorded (not edited,
not translated). The responses in them are the model's Spanish answers. The English summary of the results is in
the week README: [Part 1: tokens per language](../../semana-02/README.md#part-1-tokens-per-language),
[Part 2: response variability](../../semana-02/README.md#part-2-response-variability) and
[Per-token probabilities](../../semana-02/README.md#per-token-probabilities).

## Files

| File | What it is | Written by / Read by |
|---|---|---|
| `texto_*.txt` | The same text (an inventory reorder policy) in Spanish (`texto_es.txt`) and English (`texto_en.txt`) | Read by `practica_tokens.py` and `entregable_semana2.ipynb` |
| `variabilidad_respuestas.csv`, `variabilidad_resumen.csv`, `variabilidad.png` | Outputs of the latest `variabilidad.py` run: every response, the variability per condition, and its chart. They are identical to the files in `corridas/run3/` | Written by `variabilidad.py` |
| `variabilidad_entregable.png` | The deliverable's chart: the mean variability per condition over all the runs in `corridas/`, with its 95% confidence interval, and each run's mean as a separate mark | Written by `entregable_semana2.ipynb` |
| `logprobs_distribucion.csv` | The first-token probability distribution for the prompt "Di hola" ("Say hello") at temperatures 0.0, 0.7 and 1.0: the 50 most likely tokens with a nonzero probability (at 0.0, a single token) | Written by `logprobs_temperaturas.py` |
| `entropia_*.csv` | Entropy along a response, at temperatures 0.7 and 1.0: per token for one response (seed 1) at each temperature (`entropia_por_token.csv`), and per response for 20 seeds (`entropia_multisemilla.csv`) | Written by `entropia_por_token.py` and `entropia_multisemilla.py` |

## Keys

| Key | Meaning |
|---|---|
| `barrido` | The parameter swept: `temperature` (with `top_p` = 1.0) or `top_p` (with `temperature` = 1.0) |
| `valor` | The value of the swept parameter |
| `corrida` | In `variabilidad_respuestas.csv`: the number of the response within its condition (1 to N), not a run |
| `respuesta` | The model's response, in Spanish |
| `n` | Number of responses per condition |
| `variabilidad` | 1 minus the mean Jaccard similarity between the responses of a condition (0 = all identical) |
| `desv_estandar` | Standard deviation of the per-response variability |
| `ic95_inf`, `ic95_sup` | Lower and upper bounds of the 95% confidence interval |
| `temperatura` | Sampling temperature |
| `semilla` | Random seed of the response |
| `tokens` | Number of tokens in the response |
| `entropia_media_bits`, `entropia_max_bits` | Mean and maximum next-token entropy along the response, in bits |
| `posicion` | Position of the token in the response |
| `p_elegido` | Probability of the token that was chosen |
| `entropia_bits` | Next-token entropy at that position, in bits |
| `probabilidad` | Probability of the token |
